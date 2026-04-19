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


def _flatten(node: dict, result: list, depth: int) -> None:
    for name, data in sorted(node.items()):
        result.append(
            {
                "name": name,
                "full_tag": data["full_tag"],
                "depth": depth,
                "items": data["items"],
            }
        )
        _flatten(data["children"], result, depth + 1)


def build_tag_tree(todos: list) -> list[dict]:
    """Return flat list [{name, full_tag, depth, items}] for template iteration."""
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
            {"name": "(untagged)", "full_tag": "", "depth": 0, "items": untagged}
        )
    return result


def _now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _undo_trigger(todo_ids: list[int], prev_status: str) -> str:
    return json.dumps(
        {"showUndoToast": {"ids": ",".join(str(i) for i in todo_ids), "prevStatus": prev_status}}
    )


def _postponed_count(request) -> int:
    request.dbsession.flush()
    return request.dbsession.execute(
        select(func.count()).select_from(Todo).where(Todo.status == TodoStatus.postponed)
    ).scalar()


def _postponed_section_oob(request) -> str:
    count = _postponed_count(request)
    activate_url = request.route_url("todos_activate_all_postponed")
    if count > 0:
        btn = (
            f'<button hx-post="{activate_url}" hx-target="body" '
            f'class="rounded-full bg-slate-500 px-3 py-1 text-xs text-white shadow hover:bg-slate-600">'
            f"⏸ Activate {count}</button>"
        )
    else:
        btn = ""
    return f'<div id="postponed-section" hx-swap-oob="true">{btn}</div>'


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
        select(Todo).where(Todo.status == TodoStatus.postponed)
    ).scalars().all()
    return {
        "groups": build_tag_tree(todos),
        "postponed_count": len(postponed_count),
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


@view_config(route_name="todo_activate", request_method="POST")
def todo_activate(request):
    todo_id = int(request.matchdict["id"])
    todo = request.dbsession.get(Todo, todo_id)
    todo.status = TodoStatus.todo
    todo.done_at = None
    todo.postponed_at = None
    return HTTPSeeOther(request.route_url("list_todos"))


@view_config(route_name="todos_done", request_method="POST")
def todos_done(request):
    raw_ids = request.params.get("todo_ids", "")
    todo_ids = [int(x) for x in raw_ids.split(",") if x.strip()]
    for todo_id in todo_ids:
        todo = request.dbsession.get(Todo, todo_id)
        if todo:
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
    request.response.headers["HX-Trigger"] = _undo_trigger(todo_ids, "todo")
    return request.response


@view_config(route_name="todos_postpone", request_method="POST")
def todos_postpone(request):
    raw_ids = request.params.get("todo_ids", "")
    todo_ids = [int(x) for x in raw_ids.split(",") if x.strip()]
    for todo_id in todo_ids:
        todo = request.dbsession.get(Todo, todo_id)
        if todo:
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
    request.response.headers["HX-Trigger"] = _undo_trigger(todo_ids, "todo")
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
    for todo_id in todo_ids:
        todo = request.dbsession.get(Todo, todo_id)
        if todo:
            todo.status = prev_status
            if prev_status != TodoStatus.done:
                todo.done_at = None
            if prev_status != TodoStatus.postponed:
                todo.postponed_at = None
    return HTTPSeeOther(request.route_url("list_todos"))


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
