"""Protocol views — CRUD for templates, plus run-page interactions.

Snapshotting (templating items into run-items) happens lazily on the first
GET of /protocols/run/{id}, idempotent under the recurrence module's lock.
"""

import datetime
import threading

from pyramid.httpexceptions import HTTPForbidden, HTTPNotFound, HTTPSeeOther
from pyramid.renderers import render, render_to_response
from pyramid.response import Response
from pyramid.view import view_config
from sqlalchemy import select

from menage2.dateparse import label_recurrence
from menage2.models.protocol import (
    Protocol,
    ProtocolItem,
    ProtocolRun,
    ProtocolRunItem,
    ProtocolRunItemStatus,
)
from menage2.models.todo import Todo, TodoStatus
from menage2.principals import (
    get_user_team_memberships,
    is_protocol_editor,
    protocol_visible_to_user,
)
from menage2.recurrence import (
    ensure_protocol_has_run,
    rule_to_spec,
    spawn_protocol_run,
)
from menage2.views.todo import parse_todo_input

_snapshot_lock = threading.Lock()


def _now_utc():
    return datetime.datetime.now(tz=datetime.timezone.utc)


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


def _is_protocol_editor(request, protocol):
    user = request.identity
    if user is None:
        return False
    memberships = get_user_team_memberships(request.dbsession, user)
    return is_protocol_editor(user, protocol, memberships)


def _require_editor(request, protocol):
    if not _is_protocol_editor(request, protocol):
        raise HTTPForbidden()


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


@view_config(
    route_name="list_protocols", renderer="menage2:templates/protocols/list.pt"
)
def list_protocols(request):
    user = request.identity
    memberships = get_user_team_memberships(request.dbsession, user) if user else {}
    all_active = (
        request.dbsession.execute(
            select(Protocol)
            .where(Protocol.archived_at.is_(None))
            .order_by(Protocol.title)
        )
        .scalars()
        .all()
    )
    all_archived = (
        request.dbsession.execute(
            select(Protocol)
            .where(Protocol.archived_at.is_not(None))
            .order_by(Protocol.title)
        )
        .scalars()
        .all()
    )
    active = (
        [p for p in all_active if protocol_visible_to_user(p, user, memberships)]
        if user
        else all_active
    )
    archived = (
        [p for p in all_archived if protocol_visible_to_user(p, user, memberships)]
        if user
        else all_archived
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
    _require_editor(request, p)
    p.archived_at = _now_utc()
    return HTTPSeeOther(request.route_url("list_protocols"))


@view_config(route_name="unarchive_protocol", request_method="POST")
def unarchive_protocol(request):
    p = _get_or_404(request, Protocol)
    _require_editor(request, p)
    p.archived_at = None
    return HTTPSeeOther(request.route_url("list_protocols"))


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------


def _render_protocol_item(request, protocol, item, is_editor=True):
    return render(
        "menage2:templates/protocols/_protocol_item.pt",
        {"protocol": protocol, "item": item, "is_editor": is_editor},
        request=request,
    )


@view_config(
    route_name="edit_protocol",
    request_method="GET",
    renderer="menage2:templates/protocols/edit.pt",
)
def edit_protocol(request):
    p = _get_or_404(request, Protocol)
    is_editor = _is_protocol_editor(request, p)
    return {
        "protocol": p,
        "rule_label": _rule_label(p),
        "is_editor": is_editor,
        "render_item": lambda item: _render_protocol_item(request, p, item, is_editor),
    }


@view_config(route_name="edit_protocol", request_method="POST")
def update_protocol(request):
    p = _get_or_404(request, Protocol)
    _require_editor(request, p)

    # Composite input (title + #tags + *recurrence + ~note)
    composite = request.params.get("composite", "").strip()
    if composite:
        parsed = parse_todo_input(composite, _today())
        new_title = parsed.text.strip() or p.title
        if new_title != p.title:
            p.title = new_title
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
                    run.todo.text = new_title
        p.tags = parsed.tags
        p.assignees = set(parsed.assignees)
        p.note = parsed.note or None
        if parsed.recurrence:
            _apply_protocol_recurrence(p, parsed.recurrence, request.dbsession)
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
    _require_editor(request, p)
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
    _require_editor(request, item.protocol)
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
    _require_editor(request, p)
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
    _require_editor(request, item.protocol)
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
    spawn_protocol_run(p, _today(), _now_utc(), request.dbsession, owner_id=owner_id)
    return HTTPSeeOther(request.route_url("list_todos"))


# ---------------------------------------------------------------------------
# Run page (snapshot + actions)
# ---------------------------------------------------------------------------


def _run_partial_response(request, run):
    """Empty 200 OK + ``HX-Trigger: todo-updated``.

    Send a partial with additional triggers.

    """
    events = set(["todo-updated"])
    if run.closed_at:
        events.add("todo-closed")
    response = Response()
    response.headers["HX-Trigger"] = ",".join(events)
    return render_to_response(
        "menage2:templates/_protocol_run_partial.pt",
        {
            "run": run,
        },
        request=request,
        response=response,
    )


@view_config(route_name="run_item_done", request_method="POST")
def run_item_done(request):
    item = _get_or_404(request, ProtocolRunItem, "item_id")
    item.status = ProtocolRunItemStatus.done
    item.run.maybe_close_run()
    # XXX redirect to refresh the details panel fully
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
    item.run.maybe_close_run()
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
