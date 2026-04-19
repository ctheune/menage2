import datetime
import json
import re

from pyramid.httpexceptions import HTTPSeeOther
from pyramid.renderers import render
from pyramid.view import view_config
from sqlalchemy import func, select

from menage2.models.todo import Todo, TodoStatus

_TAG_RE = re.compile(r"#(\S+)")


def parse_todo_input(raw: str) -> tuple[str, set[str]]:
    """Extract #tags from raw text, return (clean_text, tags_set)."""
    tags = set(_TAG_RE.findall(raw))
    clean = re.sub(r"\s+", " ", _TAG_RE.sub("", raw)).strip()
    return clean, tags


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


def _postponed_count(request) -> int:
    request.dbsession.flush()
    return request.dbsession.execute(
        select(func.count()).select_from(Todo).where(Todo.status == TodoStatus.postponed)
    ).scalar()


def _done_count(request) -> int:
    request.dbsession.flush()
    return request.dbsession.execute(
        select(func.count()).select_from(Todo).where(Todo.status == TodoStatus.done)
    ).scalar()


_PILL_STYLE = (
    "display:inline-flex;align-items:center;gap:0.35rem;"
    "border-radius:9999px;padding:0.25rem 0.65rem;"
    "font-size:0.75rem;font-weight:500;"
)
_BADGE_STYLE = (
    "display:inline-flex;align-items:center;justify-content:center;"
    "background:rgba(255,255,255,0.25);border-radius:9999px;"
    "padding:0 0.4rem;font-size:0.7rem;font-weight:700;min-width:1.2em;"
)


def _postponed_section_oob(request) -> str:
    count = _postponed_count(request)
    activate_url = request.route_url("todos_activate_all_postponed")
    if count > 0:
        btn = (
            f'<button hx-post="{activate_url}" hx-target="body" '
            f'style="{_PILL_STYLE}background:#64748b;color:#fff;cursor:pointer;">'
            f'⏸ Paused <span style="{_BADGE_STYLE}">{count}</span></button>'
        )
    else:
        btn = (
            f'<span style="{_PILL_STYLE}background:#e2e8f0;color:#94a3b8;">'
            f'⏸ Paused <span style="{_BADGE_STYLE}background:rgba(0,0,0,0.1);color:#94a3b8;">0</span></span>'
        )
    return f'<div id="postponed-section" hx-swap-oob="true">{btn}</div>'


@view_config(route_name="home")
def home(request):
    return HTTPSeeOther(request.route_url("list_todos"))


@view_config(route_name="list_todos", renderer="menage2:templates/list_todos.pt")
def list_todos(request):
    todos = (
        request.dbsession.execute(
            select(Todo).where(Todo.status == TodoStatus.todo).order_by(Todo.created_at)
        )
        .scalars()
        .all()
    )
    postponed_count = request.dbsession.execute(
        select(func.count()).select_from(Todo).where(Todo.status == TodoStatus.postponed)
    ).scalar()
    done_count = request.dbsession.execute(
        select(func.count()).select_from(Todo).where(Todo.status == TodoStatus.done)
    ).scalar()
    return {
        "groups": build_tag_tree(todos),
        "postponed_count": postponed_count,
        "done_count": done_count,
    }


@view_config(route_name="add_todo", request_method="POST")
def add_todo(request):
    raw = request.params.get("text", "").strip()
    if not raw:
        return HTTPSeeOther(request.route_url("list_todos"))
    text, tags = parse_todo_input(raw)
    if not text:
        request.response.status_int = 422
        request.response.headers["HX-Reswap"] = "none"
        request.response.headers["HX-Trigger"] = json.dumps(
            {"showAddTodoError": {"input": raw}}
        )
        return request.response
    todo = Todo(text=text, tags=tags, status=TodoStatus.todo, created_at=_now_utc())
    request.dbsession.add(todo)
    return HTTPSeeOther(request.route_url("list_todos"))



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
    todos = (
        request.dbsession.execute(
            select(Todo).where(Todo.status == TodoStatus.todo).order_by(Todo.created_at)
        )
        .scalars()
        .all()
    )
    body = render(
        "menage2:templates/_todo_groups.pt",
        {"groups": build_tag_tree(todos)},
        request=request,
    )
    request.response.content_type = "text/html"
    request.response.text = body
    request.response.headers["HX-Trigger"] = _undo_trigger(todo_ids, "todo", texts, "completed")
    return request.response


@view_config(route_name="todos_postpone", request_method="POST")
def todos_postpone(request):
    raw_ids = request.params.get("todo_ids", "")
    todo_ids = [int(x) for x in raw_ids.split(",") if x.strip()]
    texts = []
    for todo_id in todo_ids:
        todo = request.dbsession.get(Todo, todo_id)
        if todo:
            texts.append(todo.text)
            todo.status = TodoStatus.postponed
            todo.postponed_at = _now_utc()
    todos = (
        request.dbsession.execute(
            select(Todo).where(Todo.status == TodoStatus.todo).order_by(Todo.created_at)
        )
        .scalars()
        .all()
    )
    body = render(
        "menage2:templates/_todo_groups.pt",
        {"groups": build_tag_tree(todos)},
        request=request,
    )
    request.response.content_type = "text/html"
    request.response.text = body + _postponed_section_oob(request)
    request.response.headers["HX-Trigger"] = _undo_trigger(todo_ids, "todo", texts, "postponed")
    return request.response


@view_config(route_name="todos_activate_all_postponed", request_method="POST")
def todos_activate_all_postponed(request):
    postponed = (
        request.dbsession.execute(
            select(Todo).where(Todo.status == TodoStatus.postponed)
        )
        .scalars()
        .all()
    )
    ids = [t.id for t in postponed]
    for todo in postponed:
        todo.status = TodoStatus.todo
        todo.postponed_at = None
    return HTTPSeeOther(request.route_url("list_todos"))


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
            if prev_status != TodoStatus.postponed:
                todo.postponed_at = None
    todos = (
        request.dbsession.execute(
            select(Todo).where(Todo.status == TodoStatus.todo).order_by(Todo.created_at)
        )
        .scalars()
        .all()
    )
    body = render(
        "menage2:templates/_todo_groups.pt",
        {"groups": build_tag_tree(todos)},
        request=request,
    )
    label = texts[0] if len(texts) == 1 else f"{len(texts)} items"
    request.response.content_type = "text/html"
    request.response.text = body + _postponed_section_oob(request)
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


@view_config(route_name="edit_todo", request_method="POST")
def edit_todo(request):
    todo_id = int(request.matchdict["id"])
    raw = request.params.get("text", "").strip()
    todo = request.dbsession.get(Todo, todo_id)
    if not todo or not raw:
        return HTTPSeeOther(request.route_url("list_todos"))
    text, tags = parse_todo_input(raw)
    if not text:
        request.response.status_int = 422
        request.response.headers["HX-Reswap"] = "none"
        request.response.headers["HX-Trigger"] = json.dumps(
            {"showAddTodoError": {"input": raw}}
        )
        return request.response
    todo.text = text
    todo.tags = tags
    return HTTPSeeOther(request.route_url("list_todos"))


@view_config(route_name="todos_activate_batch", request_method="POST")
def todos_activate_batch(request):
    raw_ids = request.params.get("todo_ids", "")
    todo_ids = [int(x) for x in raw_ids.split(",") if x.strip()]
    for todo_id in todo_ids:
        todo = request.dbsession.get(Todo, todo_id)
        if todo:
            todo.status = TodoStatus.todo
            todo.done_at = None
            todo.postponed_at = None
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
