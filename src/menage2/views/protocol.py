"""Protocol views — CRUD for templates, plus run-page interactions.

Snapshotting (templating items into run-items) happens lazily on the first
GET of /protocols/run/{id}, idempotent under the recurrence module's lock.
"""

import datetime
import threading

from pyramid.httpexceptions import HTTPForbidden, HTTPNotFound, HTTPSeeOther
from pyramid.renderers import render
from pyramid.view import view_config
from sqlalchemy import select

from menage2.dateparse import label_recurrence, parse_recurrence
from menage2.models.protocol import (
    Protocol,
    ProtocolItem,
    ProtocolRun,
    ProtocolRunItem,
    ProtocolRunItemStatus,
)
from menage2.models.todo import Todo, TodoStatus
from menage2.principals import get_user_team_memberships
from menage2.recurrence import (
    ensure_protocol_has_run,
    rule_to_spec,
    spawn_protocol_after,
    spawn_protocol_every_on_completion,
    spawn_protocol_run,
)
from menage2.views.todo import _apply_recurrence_spec, parse_todo_input

_snapshot_lock = threading.Lock()


def _now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def _today():
    return datetime.date.today()


def _rule_label(protocol):
    if not protocol.recurrence:
        return None
    return label_recurrence(rule_to_spec(protocol.recurrence))


def _get_or_404(request, model, id_param="id"):
    obj = request.dbsession.get(model, int(request.matchdict[id_param]))
    if obj is None:
        raise HTTPNotFound()
    return obj


def _is_protocol_owner(request, protocol):
    user = request.identity
    return user is not None and user.id == protocol.owner_id


def _require_owner(request, protocol):
    if not _is_protocol_owner(request, protocol):
        raise HTTPForbidden()


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


@view_config(
    route_name="list_protocols", renderer="menage2:templates/protocols/list.pt"
)
def list_protocols(request):
    user = request.identity

    def _filter(stmt):
        if user is None:
            return stmt
        from sqlalchemy import Text, cast, or_
        from sqlalchemy.dialects.postgresql import ARRAY

        def _contains(name):
            return Protocol.assignees.contains(cast([name], ARRAY(Text)))

        memberships = get_user_team_memberships(request.dbsession, user)
        team_clauses = [_contains(team_name) for team_name in memberships]
        visible_clauses = [
            Protocol.owner_id == user.id,
            Protocol.owner_id.is_(None),
            _contains(user.username),
        ] + team_clauses
        return stmt.where(or_(*visible_clauses))

    active = (
        request.dbsession.execute(
            _filter(
                select(Protocol)
                .where(Protocol.archived_at.is_(None))
                .order_by(Protocol.title)
            )
        )
        .scalars()
        .all()
    )
    archived = (
        request.dbsession.execute(
            _filter(
                select(Protocol)
                .where(Protocol.archived_at.is_not(None))
                .order_by(Protocol.title)
            )
        )
        .scalars()
        .all()
    )
    return {
        "active": active,
        "archived": archived,
        "rule_label": _rule_label,
    }


@view_config(route_name="list_protocols_palette", renderer="json")
def list_protocols_palette(request):
    """JSON used by the r-key palette on the todo list."""
    rows = (
        request.dbsession.execute(
            select(Protocol)
            .where(Protocol.archived_at.is_(None))
            .order_by(Protocol.title)
        )
        .scalars()
        .all()
    )
    return [{"id": p.id, "title": p.title} for p in rows]


# ---------------------------------------------------------------------------
# Create / archive
# ---------------------------------------------------------------------------


@view_config(route_name="new_protocol", request_method="POST")
def new_protocol(request):
    title = request.params.get("title", "").strip() or "Untitled protocol"
    owner_id = request.identity.id if request.identity else None
    p = Protocol(title=title, owner_id=owner_id, created_at=_now_utc())
    request.dbsession.add(p)
    request.dbsession.flush()
    return HTTPSeeOther(request.route_url("edit_protocol", id=p.id))


@view_config(route_name="archive_protocol", request_method="POST")
def archive_protocol(request):
    p = _get_or_404(request, Protocol)
    _require_owner(request, p)
    p.archived_at = _now_utc()
    return HTTPSeeOther(request.route_url("list_protocols"))


@view_config(route_name="unarchive_protocol", request_method="POST")
def unarchive_protocol(request):
    p = _get_or_404(request, Protocol)
    _require_owner(request, p)
    p.archived_at = None
    return HTTPSeeOther(request.route_url("list_protocols"))


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------


def _render_protocol_item(request, protocol, item, is_owner=True):
    return render(
        "menage2:templates/protocols/_protocol_item.pt",
        {"protocol": protocol, "item": item, "is_owner": is_owner},
        request=request,
    )


@view_config(
    route_name="edit_protocol",
    request_method="GET",
    renderer="menage2:templates/protocols/edit.pt",
)
def edit_protocol(request):
    p = _get_or_404(request, Protocol)
    is_owner = _is_protocol_owner(request, p)
    return {
        "protocol": p,
        "rule_label": _rule_label(p),
        "is_owner": is_owner,
        "render_item": lambda item: _render_protocol_item(request, p, item, is_owner),
    }


@view_config(route_name="edit_protocol", request_method="POST")
def update_protocol(request):
    p = _get_or_404(request, Protocol)
    _require_owner(request, p)
    title = request.params.get("title", "").strip()
    if title and title != p.title:
        p.title = title
        # Sync title to any active linked todos
        active_runs = (
            request.dbsession.execute(
                select(ProtocolRun).where(
                    ProtocolRun.protocol_id == p.id,
                    ProtocolRun.closed_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        for run in active_runs:
            if run.todo and run.todo.status.value == "todo":
                run.todo.text = title
    if "assignees" in request.params:
        raw_assignees = request.params.get("assignees", "")
        p.assignees = set(
            a.lstrip("@").strip()
            for a in raw_assignees.split(",")
            if a.strip().lstrip("@")
        )
    raw_recurrence = request.params.get("recurrence", "")
    if "recurrence" in request.params:
        if raw_recurrence.strip():
            spec = parse_recurrence(raw_recurrence.strip())
            if not spec:
                request.response.status_int = 422
                return request.response
            _apply_protocol_recurrence(p, spec, request.dbsession)
            request.dbsession.flush()
            ensure_protocol_has_run(p, _today(), _now_utc(), request.dbsession)
        else:
            _apply_protocol_recurrence(p, None, request.dbsession)
    return HTTPSeeOther(request.route_url("edit_protocol", id=p.id))


def _apply_protocol_recurrence(protocol, spec, dbsession):
    """Mirror of _apply_recurrence_spec for protocols."""
    if spec is None:
        protocol.recurrence = None
        return
    if protocol.recurrence is not None:
        from menage2.models.todo import RecurrenceKind, RecurrenceUnit

        r = protocol.recurrence
        r.kind = RecurrenceKind(spec.kind)
        r.interval_value = spec.interval_value
        r.interval_unit = RecurrenceUnit(spec.interval_unit)
        r.weekday = spec.weekday
        r.month_day = spec.month_day
    else:
        from menage2.recurrence import spec_to_rule

        rule = spec_to_rule(spec)
        dbsession.add(rule)
        dbsession.flush()
        protocol.recurrence = rule


@view_config(route_name="add_protocol_item", request_method="POST")
def add_protocol_item(request):
    p = _get_or_404(request, Protocol)
    _require_owner(request, p)
    raw = request.params.get("text", "").strip()
    if not raw:
        return HTTPSeeOther(request.route_url("edit_protocol", id=p.id))
    parsed = parse_todo_input(raw)
    if not parsed.text:
        return HTTPSeeOther(request.route_url("edit_protocol", id=p.id))
    next_pos = (
        request.dbsession.execute(
            select(ProtocolItem.position)
            .where(ProtocolItem.protocol_id == p.id)
            .order_by(ProtocolItem.position.desc())
            .limit(1)
        ).scalar()
        or 0
    ) + 1
    item = ProtocolItem(
        protocol_id=p.id,
        position=next_pos,
        text=parsed.text,
        tags=parsed.tags,
        assignees=parsed.assignees,
        note=parsed.note,
    )
    request.dbsession.add(item)
    return HTTPSeeOther(request.route_url("edit_protocol", id=p.id))


@view_config(route_name="update_protocol_item", request_method="POST")
def update_protocol_item(request):
    item = _get_or_404(request, ProtocolItem, "item_id")
    _require_owner(request, item.protocol)
    raw = request.params.get("text", "").strip()
    if not raw:
        return HTTPSeeOther(request.route_url("edit_protocol", id=item.protocol_id))
    parsed = parse_todo_input(raw)
    if not parsed.text:
        return HTTPSeeOther(request.route_url("edit_protocol", id=item.protocol_id))
    item.text = parsed.text
    item.tags = parsed.tags
    item.assignees = parsed.assignees
    item.note = parsed.note
    return HTTPSeeOther(request.route_url("edit_protocol", id=item.protocol_id))


@view_config(route_name="update_protocol_item_partial", request_method="POST")
def update_protocol_item_partial(request):
    item = _get_or_404(request, ProtocolItem, "item_id")
    p = _get_or_404(request, Protocol)
    _require_owner(request, p)
    raw = request.params.get("text", "").strip()
    if raw:
        parsed = parse_todo_input(raw)
        if parsed.text:
            item.text = parsed.text
            item.tags = parsed.tags
            item.assignees = parsed.assignees
            item.note = parsed.note
    request.dbsession.flush()
    body = _render_protocol_item(request, p, item)
    request.response.content_type = "text/html"
    request.response.text = body
    return request.response


@view_config(route_name="delete_protocol_item", request_method="POST")
def delete_protocol_item(request):
    item = _get_or_404(request, ProtocolItem, "item_id")
    _require_owner(request, item.protocol)
    protocol_id = item.protocol_id
    request.dbsession.delete(item)
    return HTTPSeeOther(request.route_url("edit_protocol", id=protocol_id))


# ---------------------------------------------------------------------------
# Start a run
# ---------------------------------------------------------------------------


@view_config(route_name="start_protocol_run", request_method="POST")
def start_protocol_run(request):
    p = _get_or_404(request, Protocol)
    owner_id = request.identity.id if request.identity else None
    run = spawn_protocol_run(
        p, _today(), _now_utc(), request.dbsession, owner_id=owner_id
    )
    return HTTPSeeOther(request.route_url("show_protocol_run", id=run.id))


# ---------------------------------------------------------------------------
# Run page (snapshot + actions)
# ---------------------------------------------------------------------------


def _snapshot_run_items(run, dbsession):
    """Copy current Protocol items into ProtocolRunItem rows.

    Idempotent: held under the module-level snapshot lock + a re-check of
    ``opened_at`` so concurrent first-opens snapshot exactly once.
    """
    with _snapshot_lock:
        dbsession.flush()
        dbsession.refresh(run)
        if run.opened_at is not None:
            return
        protocol = run.protocol
        for src in sorted(protocol.items, key=lambda i: i.position):
            item_assignees = (
                set(src.assignees) if src.assignees else set(protocol.assignees)
            )
            dbsession.add(
                ProtocolRunItem(
                    run_id=run.id,
                    position=src.position,
                    text=src.text,
                    tags=set(src.tags),
                    assignees=item_assignees,
                    note=src.note,
                    status=ProtocolRunItemStatus.pending,
                )
            )
        run.opened_at = _now_utc()
        dbsession.flush()


@view_config(
    route_name="show_protocol_run",
    request_method="GET",
    renderer="menage2:templates/protocols/run.pt",
)
def show_protocol_run(request):
    run = _get_or_404(request, ProtocolRun)
    if run.opened_at is None:
        _snapshot_run_items(run, request.dbsession)
    items = sorted(run.items, key=lambda i: i.position)
    items_html = _render_run_partial(request, run, items)
    return {
        "run": run,
        "protocol": run.protocol,
        "items_html": items_html,
    }


def _maybe_close_run(run, dbsession, now):
    """Close the run + auto-complete its todo when every item is resolved."""
    items = sorted(run.items, key=lambda i: i.position)
    if not items:
        return
    if any(i.status == ProtocolRunItemStatus.pending for i in items):
        return
    if run.closed_at is None:
        run.closed_at = now
    if run.todo and run.todo.status == TodoStatus.todo:
        run.todo.status = TodoStatus.done
        run.todo.done_at = now
        today = now.date()
        spawn_protocol_after(run, today, now, dbsession)
        spawn_protocol_every_on_completion(run, today, now, dbsession)


def _render_run_partial(request, run, items):
    return render(
        "menage2:templates/protocols/_run_items.pt",
        {
            "run": run,
            "items": items,
            "all_resolved": all(
                i.status != ProtocolRunItemStatus.pending for i in items
            ),
        },
        request=request,
    )


def _run_partial_response(request, run):
    items = sorted(run.items, key=lambda i: i.position)
    body = _render_run_partial(request, run, items)
    request.response.content_type = "text/html"
    request.response.text = body
    return request.response


@view_config(route_name="run_item_done", request_method="POST")
def run_item_done(request):
    item = _get_or_404(request, ProtocolRunItem, "item_id")
    item.status = ProtocolRunItemStatus.done
    _maybe_close_run(item.run, request.dbsession, _now_utc())
    return _run_partial_response(request, item.run)


@view_config(route_name="run_item_send", request_method="POST")
def run_item_send(request):
    item = _get_or_404(request, ProtocolRunItem, "item_id")
    owner_id = request.identity.id if request.identity else None
    new_todo = Todo(
        text=item.text,
        tags=set(item.tags),
        assignees=set(item.assignees),
        note=item.note,
        owner_id=owner_id,
        status=TodoStatus.todo,
        created_at=_now_utc(),
    )
    request.dbsession.add(new_todo)
    request.dbsession.flush()
    item.status = ProtocolRunItemStatus.sent_to_todo
    item.sent_todo_id = new_todo.id
    _maybe_close_run(item.run, request.dbsession, _now_utc())
    return _run_partial_response(request, item.run)


@view_config(route_name="run_item_edit", request_method="POST")
def run_item_edit(request):
    """Update text/tags before sending or marking done — useful when the user
    wants to tweak phrasing before it lands on the active list."""
    item = _get_or_404(request, ProtocolRunItem, "item_id")
    raw = request.params.get("text", "").strip()
    if not raw:
        return _run_partial_response(request, item.run)
    parsed = parse_todo_input(raw)
    if not parsed.text:
        return _run_partial_response(request, item.run)
    item.text = parsed.text
    item.tags = parsed.tags
    item.assignees = parsed.assignees
    if parsed.note:
        item.note = parsed.note
    return _run_partial_response(request, item.run)
