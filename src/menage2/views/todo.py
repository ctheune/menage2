import calendar as _cal
import datetime
import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse as _urlparse

from dateutil.relativedelta import relativedelta
from pydantic import BaseModel
from pyramid.httpexceptions import HTTPSeeOther
from pyramid.renderers import render, render_to_response
from pyramid.request import Request
from pyramid.view import view_config
from sqlalchemy import asc, nulls_last, or_, select, text
from sqlalchemy.orm import joinedload

from menage2.dateparse import (
    RecurrenceSpec,
    parse_date,
    parse_recurrence,
)
from menage2.fuzzy import fuzzy_filter, fuzzy_highlight
from menage2.models.team import Team
from menage2.models.todo import (
    RecurrenceKind,
    RecurrenceRule,
    RecurrenceUnit,
    Todo,
    TodoAttachment,
    TodoLink,
    TodoStatus,
)
from menage2.models.user import User
from menage2.principals import (
    get_all_principals,
    get_user_team_memberships,
    todo_matches_filter,
)
from menage2.recurrence import (
    chain_history,
    rule_to_spec,
    spawn_after,
    spawn_due_every_if_needed,
    spawn_every_on_completion,
    spawn_protocol_after,
    spawn_protocol_every_on_completion,
    spec_to_rule,
)

HEADER_MOBILE_DEVICE = r"User-Agent:.*(iPhone|Android).*"
_TAG_RE = re.compile(r"#(\S+)")
_ASSIGNEE_RE = re.compile(r"@(\S+)")
# Match ^...  up to next marker or end-of-string. Lookahead never consumes.
_DATE_RE = re.compile(r"\^([^#*^~@]+?)(?=\s*[#*^~@]|$)")
_RECURRENCE_MARKER_RE = re.compile(r"\*([^#*^~@]+?)(?=\s*[#*^~@]|$)")
_NOTE_RE = re.compile(r"~([^#*^~@]+?)(?=\s*[#*^~@]|$)")
# [label](url) — captures any non-whitespace, non-paren URL; scheme validated via urlparse.
# Note: `[` is intentionally absent from _NOTE_RE's exclusion set so that [...]() inside
# a note stays in the note text.
_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
# Same pattern anchored for parsing a single stored link string.
_PARSE_LINK_RE = re.compile(r"^\[([^\]]*)\]\(([^)\s]+)\)$")
# For rendering inline [label](url) inside note text.
_INLINE_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
# Schemes blocked from rendering as <a> to prevent XSS.
_UNSAFE_SCHEMES = frozenset({"javascript", "data", "vbscript"})


def _normalize_url(url: str) -> str:
    """Prepend http:// when url has no scheme (e.g. 'example.org/path' → 'http://example.org/path')."""
    return url if _urlparse(url).scheme else "http://" + url


def render_note_html(note: str) -> str:
    """Return HTML-safe note text with [label](url) rendered as clickable <a> tags."""
    import html as _html

    escaped = _html.escape(note)

    def _replace(m: re.Match) -> str:
        raw_url = _html.unescape(m.group(2))
        url = _normalize_url(raw_url)
        scheme = _urlparse(url).scheme.lower()
        if scheme in _UNSAFE_SCHEMES:
            return _html.escape(m.group(0))
        label = _html.unescape(m.group(1)) or url
        safe_url = _html.escape(url, quote=True)
        safe_label = _html.escape(label)
        return f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer">{safe_label}</a>'

    return _INLINE_LINK_RE.sub(_replace, escaped)


def parse_link(link_str: str) -> tuple[str, str]:
    """Return (label, url) from a '[label](url)' string stored in todo.links."""
    m = _PARSE_LINK_RE.match(link_str)
    if not m:
        return (link_str, "")
    url = _normalize_url(m.group(2))
    label = m.group(1) or url
    return (label, url)


@dataclass
class ParsedTodoInput:
    text: str
    tags: set[str] = field(default_factory=set)
    assignees: set[str] = field(default_factory=set)
    due_date: datetime.date | None = None
    recurrence: RecurrenceSpec | None = None
    note: str = ""
    links: list[TodoLink] = field(default_factory=list)


def parse_todo_input(raw: str, today: datetime.date | None = None) -> ParsedTodoInput:
    """Decompose a raw input string into text + #tags + ^due-date + *recurrence + ~note + [links]().

    Extraction order matters:
    - Note is extracted before links so that inline [...]() within note text
      stay in the note and are not mistaken for standalone link pills.
    - Links are extracted after note removal so URL #fragments don't pollute tag extraction.
    """
    if today is None:
        today = datetime.date.today()

    text = raw

    due_date: datetime.date | None = None
    m = _DATE_RE.search(text)
    if m:
        parsed = parse_date(m.group(1).strip(), today)
        if parsed:
            due_date = parsed.date
            text = text[: m.start()] + text[m.end() :]

    recurrence: RecurrenceSpec | None = None
    m = _RECURRENCE_MARKER_RE.search(text)
    if m:
        spec = parse_recurrence(m.group(1).strip())
        if spec:
            recurrence = spec
            text = text[: m.start()] + text[m.end() :]

    note = ""
    m = _NOTE_RE.search(text)
    if m:
        note = m.group(1).strip()
        text = text[: m.start()] + text[m.end() :]

    links = [
        TodoLink(label=lm.group(1), url=_normalize_url(lm.group(2)), position=i)
        for i, lm in enumerate(_LINK_RE.finditer(text))
    ]
    text = _LINK_RE.sub("", text)

    tags = set(_TAG_RE.findall(text))
    assignees = set(_ASSIGNEE_RE.findall(text))
    text = _TAG_RE.sub("", text)
    text = _ASSIGNEE_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return ParsedTodoInput(
        text=text,
        tags=tags,
        assignees=assignees,
        due_date=due_date,
        recurrence=recurrence,
        note=note,
        links=links,
    )


def _apply_recurrence_spec(todo: Todo, spec: RecurrenceSpec | None, dbsession) -> None:
    """Attach a rule to a todo, updating in place when one already exists.

    A ``None`` spec clears the link (the rule itself is left in place because
    sibling todos in the spawn chain may still reference it).
    """
    if spec is None:
        todo.recurrence = None
        return
    if todo.recurrence is not None:
        r = todo.recurrence
        r.kind = RecurrenceKind(spec.kind)
        r.interval_value = spec.interval_value
        r.interval_unit = RecurrenceUnit(spec.interval_unit)
        r.weekday = spec.weekday
        r.month_day = spec.month_day
    else:
        rule = spec_to_rule(spec)
        dbsession.add(rule)
        dbsession.flush()
        todo.recurrence = rule


def _insert(node: dict, segments: list, full_tag: str, todo: Todo) -> None:
    head, *rest = segments
    if head not in node:
        # full_tag for this node = everything up to (not including) the remaining segments
        if rest:
            prefix_len = len(full_tag) - len(":" + ":".join(rest))
            node_full_tag = full_tag[:prefix_len]
        else:
            node_full_tag = full_tag
        node[head] = {"full_tag": node_full_tag, "items": [], "children": {}}
    if not rest:
        node[head]["items"].append(todo)
    else:
        _insert(node[head]["children"], rest, full_tag, todo)


def _subtree_count(node: dict) -> int:
    return len(node["items"]) + sum(
        _subtree_count(c) for c in node["children"].values()
    )


def _flatten(node: dict, result: list, depth: int) -> None:
    for name, data in sorted(node.items()):
        full_tag = data["full_tag"]
        parent_tag = full_tag.rsplit(":", 1)[0] if ":" in full_tag else ""
        result.append(
            {
                "name": name,
                "full_tag": full_tag,
                "breadcrumbs": " / ".join(full_tag.split(":")),
                "parent_tag": parent_tag,
                "depth": depth,
                "items": data["items"],
                "total_count": _subtree_count(data),
            }
        )
        _flatten(data["children"], result, depth + 1)


def build_tag_tree(todos: list) -> list[dict]:
    """Return flat list [{name, full_tag, parent_tag, depth, items, total_count}]."""
    tree: dict = {}
    untagged = []
    for todo in todos:
        if not todo.tags:
            untagged.append(todo)
            continue
        tags = sorted(todo.tags)
        # Only insert under the most specific tags; skip prefix tags that have children
        filtered_tags = [
            t for t in tags if not any(other.startswith(t + ":") for other in tags)
        ]
        for tag in filtered_tags:
            _insert(tree, tag.split(":"), tag, todo)
    result: list = []
    _flatten(tree, result, 0)
    if untagged:
        result.append(
            {
                "name": "(untagged)",
                "full_tag": "(untagged)",
                "breadcrumbs": "(untagged)",
                "parent_tag": "",
                "depth": 0,
                "items": untagged,
                "total_count": len(untagged),
            }
        )
    return result


def _humanize_delta(days: int) -> str:
    """Convert an absolute number of days to a humanized relative time string."""
    abs_days = abs(days)
    if abs_days < 7:
        return f"{abs_days} days"
    weeks = abs_days // 7
    if weeks < 5:
        return f"{weeks} week{'s' if weeks > 1 else ''}"
    months = abs_days // 30
    if months < 12:
        return f"{months} month{'s' if months > 1 else ''}"
    years = abs_days // 365
    return f"{years} year{'s' if years > 1 else ''}"


def _format_date_group(date: datetime.date, today: datetime.date) -> str:
    """Format a date for group headers.

    Returns strings like "Today, 07.05.2026", "Sunday, 10.05.2026 (in 3 days)", "Monday, 27.04.2026 (2 weeks ago)".
    """
    weekday = date.strftime("%A")
    date_str = date.strftime("%d.%m.%Y")

    if date == today:
        return f"Today, {date_str}"
    if date == today + datetime.timedelta(days=1):
        return f"Tomorrow, {date_str}"
    if date == today - datetime.timedelta(days=1):
        return f"Yesterday, {date_str}"

    delta = (date - today).days
    if delta > 0:
        relative = _humanize_delta(delta)
        return f"{weekday}, {date_str} (in {relative})"
    else:
        relative = _humanize_delta(delta)
        return f"{weekday}, {date_str} ({relative} ago)"


def build_date_groups(
    todos: list[Todo],
    key_fn,
    sort_key_fn,
    today: datetime.date,
) -> list[dict]:
    """Group todos by a date-extraction function.

    Args:
        todos: Pre-ordered todos from _filter_todos
        key_fn: Callable(todo) -> datetime.date | None
        sort_key_fn: Callable(keys: list[date]) -> list[date]

    Returns flat list [{name, full_tag, parent_tag, depth, items, total_count}].
    """
    groups_dict: dict[datetime.date, list] = {}

    for todo in todos:
        key = key_fn(todo)
        if key is None:
            continue
        if key not in groups_dict:
            groups_dict[key] = []
        groups_dict[key].append(todo)

    result: list = []
    sorted_keys = sort_key_fn(list(groups_dict.keys()))

    for date_key in sorted_keys:
        items = groups_dict[date_key]
        name = _format_date_group(date_key, today)
        result.append(
            {
                "name": name,
                "full_tag": name,
                "parent_tag": "",
                "depth": 0,
                "items": items,
                "total_count": len(items),
            }
        )

    return result


def _now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _today() -> datetime.date:
    return datetime.date.today()


def _safe_next(request, fallback_route: str) -> str:
    """Return a safe redirect target. Accepts ``next`` form param or Referer
    when it's a relative same-app URL; otherwise the fallback route."""
    candidates = [request.params.get("next", ""), request.referer or ""]
    for c in candidates:
        if c and c.startswith("/") and not c.startswith("//"):
            return c
        if c and c.startswith(request.application_url):
            return c
    return request.route_url(fallback_route)


def _render_todo_form(request, next_url: str) -> str:
    return render(
        "menage2:templates/_todo_form.pt",
        {"next_url": next_url},
        request=request,
    )


def _filter_todos(
    dbsession,
    today: datetime.date,
    user,
    filter_mode: str = "personal",
    status: str = "active",
) -> list[Todo]:
    """Items shown in the main list: status=todo and due today/earlier (or undated)."""

    query = dbsession.query(Todo).options(joinedload(Todo.protocol_run))

    if status == "active":
        query = query.where(
            Todo.status == TodoStatus.todo,
            or_(Todo.due_date.is_(None), Todo.due_date <= today),
        )
        query = query.order_by(nulls_last(asc(Todo.due_date)), asc(Todo.created_at))
    elif status == "on_hold":
        query = query.where(Todo.status == TodoStatus.on_hold)
        query = query.order_by(nulls_last(asc(Todo.due_date)), asc(Todo.created_at))
    elif status == "scheduled":
        query = query.where(Todo.status == TodoStatus.todo, Todo.due_date > today)
        query = query.order_by(asc(Todo.due_date), asc(Todo.created_at))
    elif status == "done":
        query = query.where(Todo.status == TodoStatus.done)
        query = query.order_by(Todo.done_at.desc())

    todos = query.all()
    memberships = get_user_team_memberships(dbsession, user)
    return [t for t in todos if todo_matches_filter(t, user, memberships, filter_mode)]


@view_config(route_name="home")
def home(request):
    return HTTPSeeOther(request.route_url("list_todos"))


_VALID_FILTER_MODES = {
    "personal": "My Tasks",
    "delegated_in": "Assigned",
    "delegated_out": "Delegated",
    "all": "All",
}


def _validate_filter(candidate: str):
    if candidate not in _VALID_FILTER_MODES:
        candidate = list(_VALID_FILTER_MODES)[0]
    return candidate


_VALID_STATUS_FILTERS = {"active", "on_hold", "scheduled", "done"}


class SubnavSection(BaseModel):
    title: str
    badge: str | None = None
    active: bool
    url: str


@view_config(
    route_name="task_subnav",
    request_method="GET",
    renderer="menage2:templates/_task_subnav.pt",
)
def task_subnav_partial(request: Request):
    current_url = request.headers.get("HX-Current-URL", "")
    path = _urlparse(current_url).path if current_url else ""

    filter_mode = _validate_filter(request.params.get("filter"))
    sections: list[SubnavSection] = []

    for section_filter, section_title in _VALID_FILTER_MODES.items():
        section_todos = len(
            _filter_todos(
                request.dbsession,
                _today(),
                user=request.identity,
                filter_mode=section_filter,
            )
        )
        section = SubnavSection(
            title=section_title,
            url=request.route_url("list_todos", _query=dict(filter=section_filter)),
            badge=str(section_todos),
            active=(
                request.route_path("list_todos") == path
                and filter_mode == section_filter
            ),
        )
        sections.append(section)

    sections.append(
        SubnavSection(
            title="Protocols",
            url=request.route_url("list_protocols"),
            active=path.startswith(request.route_path("list_protocols")),
        )
    )
    return {"sections": sections}


def _list_todo_groups(request):
    today = _today()
    status = request.params.get("status", "active")
    if status not in _VALID_STATUS_FILTERS:
        status = "active"
    filter_mode = request.params.get("filter", "personal")
    if filter_mode not in _VALID_FILTER_MODES:
        filter_mode = "personal"
    user = request.identity
    todos = _filter_todos(
        request.dbsession, today, user=user, filter_mode=filter_mode, status=status
    )

    if status == "scheduled":
        groups = build_date_groups(
            todos,
            key_fn=lambda t: t.due_date,
            sort_key_fn=lambda keys: sorted(keys),
            today=today,
        )
    elif status == "done":
        groups = build_date_groups(
            todos,
            key_fn=lambda t: t.done_at.date() if t.done_at else None,
            sort_key_fn=lambda keys: sorted(keys, reverse=True),
            today=today,
        )
    else:
        groups = build_tag_tree(todos)

    return {
        "status": status,
        "groups": groups,
        "render_note_html": render_note_html,
        "today": today,
        "parse_link": parse_link,
    }


@view_config(
    route_name="list_todo_groups",
    request_method="GET",
    renderer="menage2:templates/_todo_groups.pt",
)
def list_todo_groups(request):
    return _list_todo_groups(request)


@view_config(
    route_name="list_todo_groups",
    header=HEADER_MOBILE_DEVICE,
    renderer="menage2:templates/mobile/_todo_groups.pt",
)
def list_todo_groups_mobile(request):
    return _list_todo_groups(request)


def _list_todos(request):
    today = _today()
    # XXX
    spawn_due_every_if_needed(request.dbsession, today, _now_utc())

    status = request.params.get("status", "active")
    if status not in _VALID_STATUS_FILTERS:
        status = "active"
    filter_mode = request.params.get("filter", "personal")
    if filter_mode not in _VALID_FILTER_MODES:
        filter_mode = "personal"
    return {
        "status": status,
        "filter_mode": filter_mode,
        "form_html": _render_todo_form(request, request.route_url("list_todos")),
    }


@view_config(route_name="list_todos", renderer="menage2:templates/list_todos.pt")
def list_todos(request):
    return _list_todos(request)


@view_config(
    route_name="list_todos",
    header=HEADER_MOBILE_DEVICE,
    renderer="menage2:templates/mobile/list_todos.pt",
)
def list_todos_mobile(request):
    return _list_todos(request)


@view_config(route_name="add_todo", request_method="POST")
def add_todo(request):
    raw = request.params.get("text", "").strip()
    next_url = _safe_next(request, "list_todos")
    if not raw:
        return HTTPSeeOther(next_url)
    parsed = parse_todo_input(raw, _today())
    if not parsed.text:
        request.response.status_int = 422
        request.response.headers["HX-Reswap"] = "none"
        request.response.hx_trigger("showAddTodoError", {"input": raw})
        return request.response
    owner_id = request.identity.id if request.identity else None
    todo = Todo(
        text=parsed.text,
        tags=parsed.tags,
        assignees=parsed.assignees,
        note=parsed.note,
        due_date=parsed.due_date,
        links_rel=parsed.links,
        owner_id=owner_id,
        status=TodoStatus.todo,
        created_at=_now_utc(),
    )
    request.dbsession.add(todo)
    if parsed.recurrence is not None:
        request.dbsession.flush()
        _apply_recurrence_spec(todo, parsed.recurrence, request.dbsession)
    return HTTPSeeOther(next_url)


@view_config(route_name="todos_done", request_method="POST")
def todos_done(request):
    """Mark todos done.

    Accepts `todo_ids` either as a single comma-separated value (legacy keydown
    handler) or as repeated values from the form-driven POST.
    """
    todo_ids: list[int] = []
    for entry in request.params.getall("todo_ids"):
        for x in str(entry).split(","):
            x = x.strip()
            if x:
                todo_ids.append(int(x))
    today = _today()
    now = _now_utc()
    texts = []
    for todo_id in todo_ids:
        todo = request.dbsession.get(Todo, todo_id)
        if todo:
            texts.append(todo.text)
            todo.status = TodoStatus.done
            todo.done_at = now
            spawn_after(todo, today, now, request.dbsession)
            spawn_every_on_completion(todo, today, now, request.dbsession)
            # Protocol-run todos: close the run and trigger the protocol's own
            # recurrence (spawn the next run if rule is after/every).
            if todo.protocol_run is not None:
                run = todo.protocol_run
                if run.closed_at is None:
                    run.closed_at = now
                spawn_protocol_after(run, today, now, request.dbsession)
                spawn_protocol_every_on_completion(run, today, now, request.dbsession)
    request.dbsession.flush()
    response = request.response
    response.content_type = "text/html"
    response.text = ""
    response.hx_trigger("todo-updated")
    response.hx_trigger.undo(todo_ids, "todo", texts, "completed")
    response.hx_trigger(
        "todo-closed"
    )  # XXX the ui should rather check whether the item is still in the list
    return response


@view_config(route_name="todos_hold", request_method="POST")
def todos_hold(request):
    """Put items 'on hold' indefinitely (the renamed paused/postponed action).

    Accepts `todo_ids` either as a single comma-separated value (legacy keydown
    handler) or as repeated values from the form-driven POST.
    """
    todo_ids: list[int] = []
    for entry in request.params.getall("todo_ids"):
        for x in str(entry).split(","):
            x = x.strip()
            if x:
                todo_ids.append(int(x))
    texts = []
    for todo_id in todo_ids:
        todo = request.dbsession.get(Todo, todo_id)
        if todo:
            texts.append(todo.text)
            todo.status = TodoStatus.on_hold
            todo.on_hold_at = _now_utc()
    request.dbsession.flush()
    response = request.response
    response.content_type = "text/html"
    response.text = ""
    response.hx_trigger("todo-updated")
    response.hx_trigger.undo(todo_ids, "todo", texts, "put on hold")
    return request.response


@view_config(route_name="todos_activate_all_on_hold", request_method="POST")
def todos_activate_all_on_hold(request):
    held = (
        request.dbsession.execute(select(Todo).where(Todo.status == TodoStatus.on_hold))
        .scalars()
        .all()
    )
    for todo in held:
        todo.status = TodoStatus.todo
        todo.on_hold_at = None
    return HTTPSeeOther(request.route_url("list_todos"))


def _bump_due_date(
    current: datetime.date | None, today: datetime.date, interval: str
) -> datetime.date:
    """Apply a postpone interval, snapping overdue items to today first.

    Parses the interval using parse_date from menage2.dateparse, which handles
    formats like "1d", "2w", "1mo", "tomorrow", etc.
    """
    if current is None:
        base = today
    elif current >= today:
        base = current
    else:
        base = today - datetime.timedelta(days=1)

    result = parse_date(interval, base)
    if result is None:
        raise ValueError(f"Invalid postpone interval: {interval}")
    return result.date


def _batch_postpone(
    dbsession, todo_ids: list[int], interval: str, today: datetime.date
) -> None:
    """Apply postpone interval to a batch of todos.

    Updates due_date for each todo, snapping overdue items to today first.
    """
    for todo_id in todo_ids:
        todo = dbsession.get(Todo, todo_id)
        if todo and todo.status in (TodoStatus.on_hold, TodoStatus.todo):
            todo.due_date = _bump_due_date(todo.due_date, today, interval)
    dbsession.flush()


@view_config(route_name="todos_postpone", request_method="POST")
def postpone_todos(request) -> None:
    """Bump or set due_date for one or more todos via POST.

    Accepts todo_ids as comma-separated or repeated form values. The optional
    interval (default "1d") bumps relative to the current date / today.
    """
    todo_ids: list[int] = []
    for entry in request.params.getall("todo_ids"):
        for x in str(entry).split(","):
            x = x.strip()
            if x:
                todo_ids.append(int(x))

    interval = request.params.get("interval", "1d")
    today = _today()
    _batch_postpone(request.dbsession, todo_ids, interval, today)
    request.dbsession.flush()
    response = request.response
    response.content_type = "text/html"
    response.text = ""
    response.hx_trigger("todo-updated")
    return request.response


# XXX
@view_config(route_name="parse_date_preview", request_method="GET", renderer="json")
def parse_date_preview(request):
    """Live-preview endpoint: ``GET /todos/parse-date?q=tomorrow`` → JSON."""
    raw = request.params.get("q", "").strip()
    if not raw:
        return {"ok": False}
    parsed = parse_date(raw, _today())
    if not parsed:
        return {"ok": False}
    return {"ok": True, "date": parsed.date.isoformat(), "label": parsed.label}


@view_config(
    route_name="parse_recurrence_preview", request_method="GET", renderer="json"
)
def parse_recurrence_preview(request):
    raw = request.params.get("q", "").strip()
    if not raw:
        return {"ok": False}
    spec = parse_recurrence(raw)
    if not spec:
        return {"ok": False}
    return {
        "ok": True,
        "label": spec.label(),
        "kind": spec.kind,
        "interval_value": spec.interval_value,
        "interval_unit": spec.interval_unit,
        "weekday": spec.weekday,
        "month_day": spec.month_day,
    }


@view_config(
    route_name="recurrence_history",
    request_method="GET",
    renderer="menage2:templates/_recurrence_history.pt",
)
def recurrence_history(request):
    todo_id = int(request.matchdict["id"])
    todo = request.dbsession.get(Todo, todo_id)
    if not todo:
        request.response.status_int = 404
        return {}
    chain = chain_history(request.dbsession, todo)
    return {
        "chain": chain,
        "current_id": todo.id,
        "rule_label": rule_to_spec(todo.recurrence).label()
        if todo.recurrence
        else None,
    }


@view_config(route_name="todo_undo", request_method="POST")
def todo_undo(request):
    todo_ids: list[int] = []
    for entry in request.params.getall("todo_ids"):
        for x in str(entry).split(","):
            x = x.strip()
            if x:
                todo_ids.append(int(x))
    prev_status_str = request.params.get("prev_status", "todo")
    try:
        prev_status = TodoStatus(prev_status_str)
    except ValueError:
        prev_status = TodoStatus.todo
    texts = []
    for todo_id in todo_ids:
        todo = request.dbsession.get(Todo, todo_id)
        if todo:
            texts.append(todo.text)
            todo.status = prev_status
            if prev_status == TodoStatus.done:
                todo.done_at = _now_utc()
            if prev_status != TodoStatus.done:
                todo.done_at = None
            if prev_status != TodoStatus.on_hold:
                todo.on_hold_at = None
    request.dbsession.flush()
    label = texts[0] if len(texts) == 1 else f"{len(texts)} items"
    request.response.content_type = "text/html"
    request.response.text = ""
    request.response.hx_trigger("showUndoConfirm", {"label": label})
    request.response.hx_trigger("todo-updated")
    return request.response


@view_config(route_name="todo_update", request_method="PUT")
def todo_update(request):
    """Update a todo using JSON/Pydantic validation. All fields are optional for partial updates."""
    from menage2.models.todo import TodoLink

    todo_id = int(request.matchdict["id"])
    todo = request.dbsession.get(Todo, todo_id)
    if not todo:
        request.response.status_int = 404
        return request.response

    try:
        update_data = request.json_body
    except (ValueError, AttributeError):
        request.response.status_int = 400
        return request.response

    print(update_data)

    from menage2.schemas import TodoUpdate

    try:
        validated = TodoUpdate(**update_data)
    except Exception as e:
        request.response.status_int = 422
        request.response.hx_trigger("showValidationError", {"message": str(e)})
        return request.response

    clear_fields = validated.clear_fields

    from sqlalchemy import delete as sqla_delete

    if validated.text is not None:
        todo.text = validated.text
    if "tags" in clear_fields:
        todo.tags = set()
    elif validated.tags is not None:
        todo.tags = validated.tags
    if "assignees" in clear_fields:
        todo.assignees = set()
    elif validated.assignees is not None:
        todo.assignees = validated.assignees
    todo.due_date = validated.due_date
    if "note" in clear_fields:
        todo.note = None
    elif validated.note is not None:
        todo.note = validated.note
    if "recurrence" in clear_fields:
        todo.recurrence_id = None
    elif validated.recurrence is not None:
        from menage2.dateparse import RecurrenceSpec as DateparseRecurrenceSpec

        spec = DateparseRecurrenceSpec(
            kind=validated.recurrence.kind,
            interval_value=validated.recurrence.interval_value,
            interval_unit=validated.recurrence.interval_unit,
            weekday=validated.recurrence.weekday,
            month_day=validated.recurrence.month_day,
        )
        _apply_recurrence_spec(todo, spec, request.dbsession)
    if "links" in clear_fields:
        request.dbsession.execute(
            sqla_delete(TodoLink).where(TodoLink.todo_id == todo.id)
        )
    elif validated.links is not None:
        request.dbsession.execute(
            sqla_delete(TodoLink).where(TodoLink.todo_id == todo.id)
        )

        for position, link_data in enumerate(validated.links):
            link = TodoLink(
                todo_id=todo.id,
                label=link_data.label,
                url=link_data.url,
                position=position,
            )
            request.dbsession.add(link)

    if validated.attachments is not None:
        from pathlib import Path

        from menage2.models.todo import TodoAttachment
        from menage2.views.attachment import _ext_for, _get_attachments_dir

        attachments_dir = _get_attachments_dir(request)
        existing_uuids = {att.uuid for att in todo.attachments}
        to_keep = validated.attachments
        to_remove = existing_uuids - to_keep

        for uuid_str in to_remove:
            att = request.dbsession.execute(
                select(TodoAttachment).where(
                    TodoAttachment.todo_id == todo.id,
                    TodoAttachment.uuid == uuid_str,
                )
            ).scalar_one_or_none()
            if att:
                ext = _ext_for(att)
                for suffix in ("", "_thumb"):
                    path = attachments_dir / (uuid_str + suffix + ext)
                    if path.exists():
                        path.unlink()
                request.dbsession.delete(att)

    response = HTTPSeeOther(
        request.route_url(
            "todo_details_panel", _query=dict(todo_ids=str(todo.id), updated="true")
        ),
    )
    return response


@view_config(route_name="todo_batch_action", request_method="POST")
def todo_batch_action(request):
    """Handle batch actions: done, hold, postpone, activate."""
    from menage2.schemas import BatchAction

    try:
        action_data = request.json_body
    except (ValueError, AttributeError):
        request.response.status_int = 400
        return request.response

    try:
        validated = BatchAction(**action_data)
    except Exception:
        request.response.status_int = 422
        return request.response

    action = validated.action
    todo_ids = validated.todo_ids

    today = _today()
    now = _now_utc()
    texts = []

    if action == "done":
        for todo_id in todo_ids:
            todo = request.dbsession.get(Todo, todo_id)
            if todo:
                texts.append(todo.text)
                todo.status = TodoStatus.done
                todo.done_at = now
                spawn_after(todo, today, now, request.dbsession)
                spawn_every_on_completion(todo, today, now, request.dbsession)
                if todo.protocol_run is not None:
                    run = todo.protocol_run
                    if run.closed_at is None:
                        run.closed_at = now
                    spawn_protocol_after(run, today, now, request.dbsession)
                    spawn_protocol_every_on_completion(
                        run, today, now, request.dbsession
                    )
        request.response.hx_trigger.undo(todo_ids, "todo", texts, "completed")
    elif action == "hold":
        for todo_id in todo_ids:
            todo = request.dbsession.get(Todo, todo_id)
            if todo and todo.status == TodoStatus.todo:
                texts.append(todo.text)
                todo.status = TodoStatus.on_hold
                todo.on_hold_at = now
        request.response.hx_trigger.undo(todo_ids, "todo", texts, "put on hold")
    elif action == "postpone":
        interval = validated.interval
        if not interval:
            request.response.status_int = 400
            return request.response
        _batch_postpone(request.dbsession, todo_ids, interval, today)
    elif action == "edit":
        update = validated.todo
        if update is None:
            request.response.status_int = 400
            return request.response

        clear_fields = update.clear_fields
        for todo_id in todo_ids:
            todo = request.dbsession.get(Todo, todo_id)
            if not todo:
                continue
            if "tags" in clear_fields:
                todo.tags = set()
            elif update.tags is not None:
                todo.tags = update.tags
            if "assignees" in clear_fields:
                todo.assignees = set()
            elif update.assignees is not None:
                todo.assignees = update.assignees
            if "due_date" in clear_fields:
                todo.due_date = None
            elif update.due_date is not None:
                todo.due_date = update.due_date
    elif action == "activate":
        prev_status = None
        for todo_id in todo_ids:
            todo = request.dbsession.get(Todo, todo_id)
            if todo and todo.status in (TodoStatus.done, TodoStatus.on_hold):
                texts.append(todo.text)
                if prev_status and todo.status != prev_status:
                    request.response.status_int = 400
                    return request.response
                else:
                    prev_status = todo.status
                todo.status = TodoStatus.todo
                todo.done_at = None
                todo.on_hold_at = None
        if prev_status is not None:
            request.response.hx_trigger.undo(
                todo_ids, prev_status.name, texts, "reactivated"
            )
    else:
        request.response.status_int = 400
        return request.response

    request.response.hx_trigger("todo-updated")
    request.response.content_type = "text/html"
    request.response.text = ""
    return request.response


@view_config(
    route_name="todo_date_picker",
    request_method="GET",
    renderer="menage2:templates/_todo_date_picker.pt",
)
def todo_date_picker(request):
    """Render a picker for a date.

    This automatically binds to the closest, previous input field.

    """
    today = datetime.date.today()
    value = request.params.get("value")
    parsed = parse_date(value, today)

    options = [
        parse_date("today", today),
        parse_date("tomorrow", today),
        parse_date("2d", today),
        parse_date("3d", today),
        parse_date("4d", today),
        parse_date("5d", today),
        parse_date("6d", today),
        parse_date("1w", today),
        parse_date("2w", today),
        parse_date("1m", today),
    ]

    month_param = request.params.get("month")
    display_year: int
    display_month: int
    if month_param:
        try:
            display_year = int(month_param[:4])
            display_month = int(month_param[5:7])
        except (ValueError, IndexError):
            month_param = None
    if not month_param:
        ref = parsed.date if parsed else today
        display_year, display_month = ref.year, ref.month

    first = datetime.date(display_year, display_month, 1)
    start_weekday = first.weekday()
    days_in_month = _cal.monthrange(display_year, display_month)[1]
    selected_iso = parsed.date.isoformat() if parsed else None

    cells: list[dict[str, object] | None] = [None] * start_weekday
    for d in range(1, days_in_month + 1):
        date_obj = datetime.date(display_year, display_month, d)
        cells.append(
            {
                "day": d,
                "iso": date_obj.isoformat(),
                "is_today": date_obj == today,
                "is_selected": date_obj.isoformat() == selected_iso,
            }
        )
    while len(cells) % 7:
        cells.append(None)
    weeks = [cells[i : i + 7] for i in range(0, len(cells), 7)]

    if display_month == 1:
        prev_y, prev_m = display_year - 1, 12
    else:
        prev_y, prev_m = display_year, display_month - 1
    if display_month == 12:
        next_y, next_m = display_year + 1, 1
    else:
        next_y, next_m = display_year, display_month + 1

    def _nav_url(y: int, m: int) -> str:
        q: dict[str, str] = {"month": f"{y:04d}-{m:02d}"}
        if value:
            q["value"] = value
        return request.route_url("todo_date_picker", _query=q)

    calendar = {
        "month_label": first.strftime("%B %Y"),
        "day_headers": ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"],
        "weeks": weeks,
        "prev_url": _nav_url(prev_y, prev_m),
        "next_url": _nav_url(next_y, next_m),
    }

    return {"value": value, "parsed": parsed, "options": options, "calendar": calendar}


@view_config(
    route_name="todo_recurrence_picker",
    request_method="GET",
    renderer="menage2:templates/_todo_recurrence_picker.pt",
)
def todo_recurrence_picker(request):
    """Render a picker for a recurrence.

    This automatically binds to the closest, previous input field.

    """
    value = request.params.get("value")

    # ensure we can parse and provide a preview what the
    # next date would be
    parsed = parse_recurrence(value)

    options = [
        parse_recurrence("every day"),
        parse_recurrence("every week"),
        parse_recurrence("every month"),
        parse_recurrence("every year"),
        parse_recurrence("after a day"),
        parse_recurrence("after a week"),
        parse_recurrence("after a month"),
        parse_recurrence("after a year"),
    ]

    return {"value": value, "parsed": parsed, "options": options}


@view_config(
    route_name="todo_tag_picker",
    request_method="GET",
    renderer="menage2:templates/_todo_tag_picker.pt",
)
def todo_tag_picker(request):
    """Render a picker for tags.

    This automatically binds to the closest, previous input field.

    """
    value = request.params.get("value")

    if not value:
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            days=30
        )
        rows = request.dbsession.execute(
            text(
                "SELECT tag, count(*) AS cnt"
                " FROM todos, unnest(tags) AS tag"
                " WHERE created_at >= :cutoff AND owner_id = :uid"
                " GROUP BY tag ORDER BY cnt DESC, tag LIMIT 5"
            ),
            {"cutoff": cutoff, "uid": request.identity.id},
        ).fetchall()
        tags = [row[0] for row in rows]
    else:
        # filtered by substring
        from menage2.models.protocol import Protocol, ProtocolItem

        user = request.identity
        all_tags: set[str] = set()

        for row in request.dbsession.execute(
            select(Todo.tags).where(Todo.owner_id == user.id)
        ).scalars():
            all_tags.update(row or set())

        for row in request.dbsession.execute(
            select(Protocol.tags).where(Protocol.owner_id == user.id)
        ).scalars():
            all_tags.update(row or set())

        for row in request.dbsession.execute(
            select(ProtocolItem.tags).join(Protocol).where(Protocol.owner_id == user.id)
        ).scalars():
            all_tags.update(row or set())

        tags = fuzzy_filter(all_tags, value)

    new = None
    if value and value not in tags:
        new = value

    return {"value": value, "options": tags, "new": new, "highlight": fuzzy_highlight}


@view_config(
    route_name="todo_assignee_picker",
    request_method="GET",
    renderer="menage2:templates/_todo_assignee_picker.pt",
)
def todo_assignee_picker(request):
    """Render a picker for assignees.

    This automatically binds to the closest, previous input field.

    """

    names: set[str] = set()

    names.update(request.dbsession.execute(select(User.username)).scalars())
    names.update(request.dbsession.execute(select(Team.name)).scalars())

    value = request.params.get("value")
    if value:
        names = set(fuzzy_filter(names, value))

    new = None
    if value and value not in names:
        new = value

    return {"value": value, "options": names, "new": new, "highlight": fuzzy_highlight}


@view_config(route_name="todo_details_panel", request_method="GET")
def todo_details_panel(request: Request):
    """Render the details panel for selected todos."""
    # XXX turn into form-json
    raw_ids = request.params.getall("todo_ids[]")
    todo_ids = [int(x) for x in raw_ids]

    if request.params.get("updated", False):
        request.response.hx_trigger("todo-updated")

    if not todo_ids:
        return render_to_response(
            "menage2:templates/_todo_details_panel_empty.pt",
            {},
            request=request,
            response=request.response,
        )

    todos: list[Todo] = [request.dbsession.get(Todo, todo_id) for todo_id in todo_ids]
    if len(todos) > 1:
        return render_to_response(
            "menage2:templates/_todo_details_panel_multiple.pt",
            {
                "todos": todos,
            },
            request=request,
            response=request.response,
        )

    todo = todos[0]
    if todo.protocol_run:
        todo.protocol_run.ensure_snapshot_run_items()

    response = render_to_response(
        "menage2:templates/_todo_details_panel.pt",
        {
            "todo": todo,
            "attachments_json": json.dumps(
                [
                    {
                        "url": request.route_url(
                            "todo_attachment_thumbnail", todo_id=todo.id, uuid=att.uuid
                        ),
                        "filename": att.original_filename,
                    }
                    for att in todo.attachments
                ]
            ),
            "tags_json": json.dumps(list(todo.tags)),
            "links_json": json.dumps(
                [
                    {"label": t.label, "url": t.url}
                    for t in sorted(todo.links_rel, key=lambda t: t.position)
                ]
            ),
            "render_note_html": render_note_html,
        },
        request=request,
        response=request.response,
    )
    return response


@view_config(route_name="list_principals_json", renderer="json")
def list_principals_json(request):
    """All principals (active users + teams) for @mention autocomplete."""
    return get_all_principals(request.dbsession)


@view_config(
    route_name="todo_picker_postpone",
    request_method="GET",
    renderer="menage2:templates/_postpone_picker.pt",
)
def postpone_picker_partial(request):
    today = datetime.date.today()

    if month_str := request.params.get("month"):
        current_month = datetime.datetime.strptime(month_str, "%B %Y").date()
    else:
        current_month = today

    current_month = current_month.replace(day=1)

    # todo_id = int(request.matchdict["id"])
    # todo = request.dbsession.get(Todo, todo_id)
    # if not todo:
    #     request.response.status_int = 404
    #     return {}
    #

    last_month = current_month - relativedelta(months=1)
    next_month = current_month + relativedelta(months=1)

    days = []
    cursor = current_month
    while cursor.month == current_month.month:
        days.append(cursor)
        cursor += datetime.timedelta(days=1)

    mute_days = [None for d in range(days[0].weekday())]
    days = mute_days + days

    return {
        "days": days,
        "today": today,
        "current_month": current_month.strftime("%B %Y"),
        "next_month": next_month.strftime("%B %Y"),
        "last_month": last_month.strftime("%B %Y"),
    }
