import datetime
import json
import re
from dataclasses import dataclass, field

from dateutil.relativedelta import relativedelta
from pyramid.httpexceptions import HTTPSeeOther
from pyramid.renderers import render
from pyramid.view import view_config
from sqlalchemy import asc, func, nulls_last, or_, select

from menage2.dateparse import parse_date
from menage2.models.todo import Todo, TodoStatus

_TAG_RE = re.compile(r"#(\S+)")
# Match ^...  up to next marker or end-of-string. Lookahead never consumes.
_DATE_RE = re.compile(r"\^([^#*^]+?)(?=\s*[#*^]|$)")


@dataclass
class ParsedTodoInput:
    text: str
    tags: set[str] = field(default_factory=set)
    due_date: datetime.date | None = None


def parse_todo_input(raw: str, today: datetime.date | None = None) -> ParsedTodoInput:
    """Decompose a raw input string into text + #tags + ^due-date.

    ``today`` is injected for testability. The ``^`` fragment runs from the
    marker up to the next ``#``/``*``/``^`` or end-of-string. If that fragment
    fails to parse it is left untouched in the text.
    """
    if today is None:
        today = datetime.date.today()

    tags = set(_TAG_RE.findall(raw))
    text = raw

    due_date: datetime.date | None = None
    m = _DATE_RE.search(text)
    if m:
        parsed = parse_date(m.group(1).strip(), today)
        if parsed:
            due_date = parsed.date
            text = text[:m.start()] + text[m.end():]

    text = _TAG_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return ParsedTodoInput(text=text, tags=tags, due_date=due_date)


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
    return len(node["items"]) + sum(_subtree_count(c) for c in node["children"].values())


def _flatten(node: dict, result: list, depth: int) -> None:
    for name, data in sorted(node.items()):
        full_tag = data["full_tag"]
        parent_tag = full_tag.rsplit(":", 1)[0] if ":" in full_tag else ""
        result.append(
            {
                "name": name,
                "full_tag": full_tag,
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
        filtered_tags = [t for t in tags if not any(other.startswith(t + ":") for other in tags)]
        for tag in filtered_tags:
            _insert(tree, tag.split(":"), tag, todo)
    result: list = []
    _flatten(tree, result, 0)
    if untagged:
        result.append(
            {
                "name": "(untagged)",
                "full_tag": "__untagged__",
                "parent_tag": "",
                "depth": 0,
                "items": untagged,
                "total_count": len(untagged),
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


def _undo_trigger(todo_ids: list[int], prev_status: str, texts: list[str], action: str) -> str:
    label = texts[0] if len(texts) == 1 else f"{len(texts)} items"
    return json.dumps({
        "showUndoToast": {
            "ids": ",".join(str(i) for i in todo_ids),
            "prevStatus": prev_status,
            "label": label,
            "action": action,
        }
    })


def _on_hold_count(request) -> int:
    request.dbsession.flush()
    return request.dbsession.execute(
        select(func.count()).select_from(Todo).where(Todo.status == TodoStatus.on_hold)
    ).scalar()


def _scheduled_count(request, today: datetime.date) -> int:
    request.dbsession.flush()
    return request.dbsession.execute(
        select(func.count())
        .select_from(Todo)
        .where(Todo.status == TodoStatus.todo, Todo.due_date > today)
    ).scalar()


def _done_count(request) -> int:
    request.dbsession.flush()
    return request.dbsession.execute(
        select(func.count()).select_from(Todo).where(Todo.status == TodoStatus.done)
    ).scalar()


def _on_hold_section_oob(request) -> str:
    count = _on_hold_count(request)
    activate_url = request.route_url("todos_activate_all_on_hold")
    if count > 0:
        btn = (
            f'<button hx-post="{activate_url}" hx-target="body" '
            f'class="btn btn-sm btn-secondary rounded-pill">'
            f'<i class="bi bi-pause-fill"></i> On hold '
            f'<span class="badge bg-light text-secondary ms-1">{count}</span></button>'
        )
    else:
        btn = (
            f'<span class="badge bg-secondary rounded-pill py-2 px-3">'
            f'<i class="bi bi-pause-fill"></i> On hold '
            f'<span class="badge bg-dark ms-1">0</span></span>'
        )
    return f'<div id="on-hold-section" hx-swap-oob="true">{btn}</div>'


def _scheduled_section_oob(request) -> str:
    today = _today()
    count = _scheduled_count(request, today)
    url = request.route_url("list_todos_scheduled")
    if count > 0:
        btn = (
            f'<a href="{url}" class="btn btn-sm btn-outline-primary rounded-pill">'
            f'<i class="bi bi-calendar-event"></i> Scheduled '
            f'<span class="badge bg-primary text-white ms-1">{count}</span></a>'
        )
    else:
        btn = (
            f'<span class="badge bg-light text-muted rounded-pill py-2 px-3 border">'
            f'<i class="bi bi-calendar-event"></i> Scheduled '
            f'<span class="badge bg-secondary ms-1">0</span></span>'
        )
    return f'<div id="scheduled-section" hx-swap-oob="true">{btn}</div>'


def _active_todos(dbsession, today: datetime.date) -> list[Todo]:
    """Items shown in the main list: status=todo and due today/earlier (or undated)."""
    return (
        dbsession.execute(
            select(Todo)
            .where(
                Todo.status == TodoStatus.todo,
                or_(Todo.due_date.is_(None), Todo.due_date <= today),
            )
            .order_by(nulls_last(asc(Todo.due_date)), asc(Todo.created_at))
        )
        .scalars()
        .all()
    )


@view_config(route_name="home")
def home(request):
    return HTTPSeeOther(request.route_url("list_todos"))


@view_config(route_name="list_todos", renderer="menage2:templates/list_todos.pt")
def list_todos(request):
    today = _today()
    todos = _active_todos(request.dbsession, today)
    groups = build_tag_tree(todos)
    groups_html = render(
        "menage2:templates/_todo_groups.pt",
        {"groups": groups, "today": today},
        request=request,
    )
    return {
        "groups": groups,
        "groups_html": groups_html,
        "form_html": _render_todo_form(request, request.route_url("list_todos")),
        "on_hold_count": _on_hold_count(request),
        "scheduled_count": _scheduled_count(request, today),
        "done_count": _done_count(request),
        "today": today,
    }


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
        request.response.headers["HX-Trigger"] = json.dumps(
            {"showAddTodoError": {"input": raw}}
        )
        return request.response
    todo = Todo(
        text=parsed.text,
        tags=parsed.tags,
        due_date=parsed.due_date,
        status=TodoStatus.todo,
        created_at=_now_utc(),
    )
    request.dbsession.add(todo)
    return HTTPSeeOther(next_url)


@view_config(route_name="todos_done", request_method="POST")
def todos_done(request):
    raw_ids = request.params.get("todo_ids", "")
    todo_ids = [int(x) for x in raw_ids.split(",") if x.strip()]
    texts = []
    for todo_id in todo_ids:
        todo = request.dbsession.get(Todo, todo_id)
        if todo:
            texts.append(todo.text)
            todo.status = TodoStatus.done
            todo.done_at = _now_utc()
    todos = _active_todos(request.dbsession, _today())
    body = render(
        "menage2:templates/_todo_groups.pt",
        {"groups": build_tag_tree(todos), "today": _today()},
        request=request,
    )
    request.response.content_type = "text/html"
    request.response.text = body
    request.response.headers["HX-Trigger"] = _undo_trigger(todo_ids, "todo", texts, "completed")
    return request.response


@view_config(route_name="todos_hold", request_method="POST")
def todos_hold(request):
    """Put items 'on hold' indefinitely (the renamed paused/postponed action)."""
    raw_ids = request.params.get("todo_ids", "")
    todo_ids = [int(x) for x in raw_ids.split(",") if x.strip()]
    texts = []
    for todo_id in todo_ids:
        todo = request.dbsession.get(Todo, todo_id)
        if todo:
            texts.append(todo.text)
            todo.status = TodoStatus.on_hold
            todo.on_hold_at = _now_utc()
    todos = _active_todos(request.dbsession, _today())
    body = render(
        "menage2:templates/_todo_groups.pt",
        {"groups": build_tag_tree(todos), "today": _today()},
        request=request,
    )
    request.response.content_type = "text/html"
    request.response.text = body + _on_hold_section_oob(request)
    request.response.headers["HX-Trigger"] = _undo_trigger(todo_ids, "todo", texts, "put on hold")
    return request.response


@view_config(route_name="todos_activate_all_on_hold", request_method="POST")
def todos_activate_all_on_hold(request):
    held = (
        request.dbsession.execute(
            select(Todo).where(Todo.status == TodoStatus.on_hold)
        )
        .scalars()
        .all()
    )
    for todo in held:
        todo.status = TodoStatus.todo
        todo.on_hold_at = None
    return HTTPSeeOther(request.route_url("list_todos"))


# Postpone interval choices for the Shift+P palette.
_POSTPONE_INTERVALS = {
    "1d": ("days", 1),
    "2d": ("days", 2),
    "3d": ("days", 3),
    "1w": ("days", 7),
    "2w": ("days", 14),
    "1mo": ("months", 1),
}


def _bump_due_date(current: datetime.date | None, today: datetime.date, interval: str) -> datetime.date:
    """Apply a postpone interval, snapping overdue items to today first."""
    base = current if (current is not None and current > today) else today
    unit, n = _POSTPONE_INTERVALS[interval]
    if unit == "days":
        return base + datetime.timedelta(days=n)
    if unit == "months":
        return base + relativedelta(months=n)
    raise ValueError(f"Unknown postpone unit: {unit}")


@view_config(route_name="todos_postpone", request_method="POST")
def todos_postpone(request):
    """Bump or set due_date for one or more todos.

    If ``due_date`` is provided (ISO date or empty string for "no date"), it
    overrides any interval and applies absolutely. Otherwise the optional
    ``interval`` (default ``1d``) bumps relative to the current date / today.
    """
    raw_ids = request.params.get("todo_ids", "")
    today = _today()
    todo_ids = [int(x) for x in raw_ids.split(",") if x.strip()]

    absolute_raw = request.params.get("due_date")
    use_absolute = absolute_raw is not None
    absolute_date: datetime.date | None = None
    if use_absolute and absolute_raw.strip():
        try:
            absolute_date = datetime.date.fromisoformat(absolute_raw.strip())
        except ValueError:
            request.response.status_int = 422
            return request.response

    interval = request.params.get("interval", "1d")
    if interval not in _POSTPONE_INTERVALS:
        interval = "1d"

    for todo_id in todo_ids:
        todo = request.dbsession.get(Todo, todo_id)
        if not todo:
            continue
        if use_absolute:
            todo.due_date = absolute_date
        else:
            todo.due_date = _bump_due_date(todo.due_date, today, interval)
    todos = _active_todos(request.dbsession, today)
    body = render(
        "menage2:templates/_todo_groups.pt",
        {"groups": build_tag_tree(todos), "today": today},
        request=request,
    )
    request.response.content_type = "text/html"
    request.response.text = body + _scheduled_section_oob(request)
    return request.response


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


@view_config(route_name="set_due_date", request_method="POST")
def set_due_date(request):
    """Set or clear the due date on a single todo. Empty string clears."""
    todo_id = int(request.matchdict["id"])
    raw = request.params.get("due_date", "").strip()
    todo = request.dbsession.get(Todo, todo_id)
    if not todo:
        request.response.status_int = 404
        return request.response
    today = _today()
    if not raw:
        todo.due_date = None
    else:
        parsed = parse_date(raw, today)
        if not parsed:
            request.response.status_int = 422
            request.response.headers["HX-Trigger"] = json.dumps(
                {"showAddTodoError": {"input": raw}}
            )
            return request.response
        todo.due_date = parsed.date
    todos = _active_todos(request.dbsession, today)
    body = render(
        "menage2:templates/_todo_groups.pt",
        {"groups": build_tag_tree(todos), "today": today},
        request=request,
    )
    request.response.content_type = "text/html"
    request.response.text = body + _scheduled_section_oob(request)
    return request.response


@view_config(route_name="todo_undo", request_method="POST")
def todo_undo(request):
    raw_ids = request.params.get("todo_ids", "")
    prev_status_str = request.params.get("prev_status", "todo")
    todo_ids = [int(x) for x in raw_ids.split(",") if x.strip()]
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
            if prev_status != TodoStatus.done:
                todo.done_at = None
            if prev_status != TodoStatus.on_hold:
                todo.on_hold_at = None
    todos = _active_todos(request.dbsession, _today())
    body = render(
        "menage2:templates/_todo_groups.pt",
        {"groups": build_tag_tree(todos), "today": _today()},
        request=request,
    )
    label = texts[0] if len(texts) == 1 else f"{len(texts)} items"
    request.response.content_type = "text/html"
    request.response.text = body + _on_hold_section_oob(request)
    request.response.headers["HX-Trigger"] = json.dumps({"showUndoConfirm": {"label": label}})
    return request.response


@view_config(route_name="list_todos_done", renderer="menage2:templates/list_todos_done.pt")
def list_todos_done(request):
    todos = (
        request.dbsession.execute(
            select(Todo)
            .where(Todo.status == TodoStatus.done)
            .order_by(Todo.done_at.desc())
        )
        .scalars()
        .all()
    )
    return {"todos": todos}


@view_config(route_name="list_todos_scheduled", renderer="menage2:templates/list_todos_scheduled.pt")
def list_todos_scheduled(request):
    today = _today()
    todos = (
        request.dbsession.execute(
            select(Todo)
            .where(Todo.status == TodoStatus.todo, Todo.due_date > today)
            .order_by(asc(Todo.due_date), asc(Todo.created_at))
        )
        .scalars()
        .all()
    )
    # Group by date for a calendar-style header.
    groups: list[dict] = []
    current_date: datetime.date | None = None
    for todo in todos:
        if todo.due_date != current_date:
            current_date = todo.due_date
            groups.append({"date": current_date, "items": []})
        groups[-1]["items"].append(todo)
    return {
        "groups": groups,
        "today": today,
        "form_html": _render_todo_form(request, request.route_url("list_todos_scheduled")),
    }


@view_config(route_name="edit_todo", request_method="POST")
def edit_todo(request):
    todo_id = int(request.matchdict["id"])
    raw = request.params.get("text", "").strip()
    next_url = _safe_next(request, "list_todos")
    todo = request.dbsession.get(Todo, todo_id)
    if not todo or not raw:
        return HTTPSeeOther(next_url)
    parsed = parse_todo_input(raw, _today())
    if not parsed.text:
        request.response.status_int = 422
        request.response.headers["HX-Reswap"] = "none"
        request.response.headers["HX-Trigger"] = json.dumps(
            {"showAddTodoError": {"input": raw}}
        )
        return request.response
    todo.text = parsed.text
    todo.tags = parsed.tags
    todo.due_date = parsed.due_date
    return HTTPSeeOther(next_url)


@view_config(route_name="todos_activate_batch", request_method="POST")
def todos_activate_batch(request):
    raw_ids = request.params.get("todo_ids", "")
    todo_ids = [int(x) for x in raw_ids.split(",") if x.strip()]
    for todo_id in todo_ids:
        todo = request.dbsession.get(Todo, todo_id)
        if todo:
            todo.status = TodoStatus.todo
            todo.done_at = None
            todo.on_hold_at = None
    todos = (
        request.dbsession.execute(
            select(Todo)
            .where(Todo.status == TodoStatus.done)
            .order_by(Todo.done_at.desc())
        )
        .scalars()
        .all()
    )
    body = render(
        "menage2:templates/_done_items.pt",
        {"todos": todos},
        request=request,
    )
    request.response.content_type = "text/html"
    request.response.text = body
    return request.response
