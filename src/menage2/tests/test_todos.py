import datetime
import json

import pytest

from menage2.models.todo import Todo, TodoStatus
from menage2.views.todo import (
    add_todo,
    build_tag_tree,
    edit_todo,
    list_todos,
    list_todos_done,
    parse_todo_input,
    todo_undo,
    todos_activate_all_postponed,
    todos_activate_batch,
    todos_done,
    todos_postpone,
)


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _todo(text="Test", tags=None, status=TodoStatus.todo, **kwargs):
    """Helper to build an unsaved Todo."""
    return Todo(text=text, tags=tags if tags is not None else set(), status=status, created_at=_now(), **kwargs)


# ---------------------------------------------------------------------------
# Pure function tests (no DB)
# ---------------------------------------------------------------------------


def test_parse_todo_input_extracts_tags():
    text, tags = parse_todo_input("Buy milk #shopping #food:dairy")
    assert text == "Buy milk"
    assert tags == {"shopping", "food:dairy"}


def test_parse_todo_input_collapses_whitespace():
    text, tags = parse_todo_input("  Get  #a  bread  ")
    assert text == "Get bread"


def test_parse_todo_input_no_tags():
    text, tags = parse_todo_input("plain text")
    assert text == "plain text"
    assert tags == set()


def test_parse_todo_input_dashes_and_special_chars():
    text, tags = parse_todo_input("Buy things #einkaufen:bio-laden #to-do")
    assert text == "Buy things"
    assert tags == {"einkaufen:bio-laden", "to-do"}


def test_parse_todo_input_only_tags():
    text, tags = parse_todo_input("#foo #bar")
    assert text == ""
    assert tags == {"foo", "bar"}


def test_build_tag_tree_single_level():
    t1 = _todo("A", {"shopping"})
    t2 = _todo("B", {"work"})
    flat = build_tag_tree([t1, t2])
    names = [g["name"] for g in flat]
    assert "shopping" in names
    assert "work" in names
    shopping = next(g for g in flat if g["name"] == "shopping")
    assert shopping["depth"] == 0
    assert t1 in shopping["items"]


def test_build_tag_tree_nested():
    t = _todo("X", {"food:dairy"})
    flat = build_tag_tree([t])
    assert flat[0]["name"] == "food"
    assert flat[0]["depth"] == 0
    assert flat[0]["items"] == []
    assert flat[1]["name"] == "dairy"
    assert flat[1]["depth"] == 1
    assert t in flat[1]["items"]


def test_build_tag_tree_unlimited_depth():
    t = _todo("X", {"a:b:c:d"})
    flat = build_tag_tree([t])
    assert [r["depth"] for r in flat] == [0, 1, 2, 3]
    assert t in flat[3]["items"]


def test_build_tag_tree_untagged_last():
    t_tagged = _todo("A", {"z"})
    t_untagged = _todo("B", set())
    flat = build_tag_tree([t_tagged, t_untagged])
    assert flat[-1]["name"] == "(untagged)"
    assert t_untagged in flat[-1]["items"]


def test_build_tag_tree_empty():
    assert build_tag_tree([]) == []


def test_build_tag_tree_total_count_includes_descendants():
    t1 = _todo("A", {"food:dairy"})
    t2 = _todo("B", {"food:meat"})
    flat = build_tag_tree([t1, t2])
    food = next(g for g in flat if g["name"] == "food")
    assert food["total_count"] == 2
    dairy = next(g for g in flat if g["name"] == "dairy")
    assert dairy["total_count"] == 1


def test_build_tag_tree_parent_tag():
    t = _todo("X", {"food:dairy"})
    flat = build_tag_tree([t])
    dairy = next(g for g in flat if g["name"] == "dairy")
    assert dairy["parent_tag"] == "food"
    food = next(g for g in flat if g["name"] == "food")
    assert food["parent_tag"] == ""


def test_build_tag_tree_untagged_has_stable_full_tag():
    t = _todo("X", set())
    flat = build_tag_tree([t])
    assert flat[-1]["full_tag"] == "__untagged__"
    assert flat[-1]["parent_tag"] == ""


def test_build_tag_tree_multiple_tags_per_todo():
    t = _todo("X", {"shopping", "urgent"})
    flat = build_tag_tree([t])
    items_with_todo = [g for g in flat if t in g["items"]]
    assert len(items_with_todo) == 2


def test_build_tag_tree_prefix_tag_not_duplicated():
    # todo with both #einkaufen and #einkaufen:obst should only appear under :obst
    t = _todo("X", {"einkaufen", "einkaufen:obst"})
    flat = build_tag_tree([t])
    items_with_todo = [g for g in flat if t in g["items"]]
    assert len(items_with_todo) == 1
    assert items_with_todo[0]["name"] == "obst"


def test_build_tag_tree_prefix_parent_node_is_empty():
    # parent "einkaufen" node has no items when only :obst tag is present
    t = _todo("X", {"einkaufen:obst"})
    flat = build_tag_tree([t])
    parent = next(g for g in flat if g["name"] == "einkaufen")
    assert parent["items"] == []
    child = next(g for g in flat if g["name"] == "obst")
    assert t in child["items"]


# ---------------------------------------------------------------------------
# View tests (with DB)
# ---------------------------------------------------------------------------


def test_add_todo_creates_record(app_request, dbsession):
    app_request.method = "POST"
    app_request.POST["text"] = "Buy milk #shopping"
    add_todo(app_request)
    todo = dbsession.query(Todo).one()
    assert todo.text == "Buy milk"
    assert todo.tags == {"shopping"}
    assert todo.status == TodoStatus.todo
    assert todo.created_at is not None
    assert todo.created_at.tzinfo is not None


def test_add_todo_empty_text_redirects(app_request, dbsession):
    app_request.method = "POST"
    app_request.POST["text"] = "  "
    response = add_todo(app_request)
    assert response.status_int == 303
    assert dbsession.query(Todo).count() == 0


def test_add_todo_only_tags_returns_error(app_request, dbsession):
    app_request.method = "POST"
    app_request.POST["text"] = "#foo #bar"
    response = add_todo(app_request)
    assert response.status_int == 422
    assert response.headers["HX-Reswap"] == "none"
    trigger = json.loads(response.headers["HX-Trigger"])
    assert "showAddTodoError" in trigger
    assert trigger["showAddTodoError"]["input"] == "#foo #bar"
    assert dbsession.query(Todo).count() == 0


def test_todos_done_sets_status_and_timestamp(app_request, dbsession):
    todo = _todo()
    dbsession.add(todo)
    dbsession.flush()
    app_request.method = "POST"
    app_request.POST["todo_ids"] = str(todo.id)
    todos_done(app_request)
    dbsession.flush()
    dbsession.refresh(todo)
    assert todo.status == TodoStatus.done
    assert todo.done_at is not None
    assert todo.done_at.tzinfo is not None


def test_todos_done_response_has_hx_trigger(app_request, dbsession):
    todo = _todo()
    dbsession.add(todo)
    dbsession.flush()
    app_request.method = "POST"
    app_request.POST["todo_ids"] = str(todo.id)
    todos_done(app_request)
    trigger = json.loads(app_request.response.headers["HX-Trigger"])
    assert "showUndoToast" in trigger
    assert str(todo.id) in trigger["showUndoToast"]["ids"]
    assert trigger["showUndoToast"]["prevStatus"] == "todo"
    assert trigger["showUndoToast"]["action"] == "completed"
    assert trigger["showUndoToast"]["label"] == "Test"


def test_todos_postpone_sets_status(app_request, dbsession):
    todo = _todo()
    dbsession.add(todo)
    dbsession.flush()
    app_request.method = "POST"
    app_request.POST["todo_ids"] = str(todo.id)
    todos_postpone(app_request)
    dbsession.flush()
    dbsession.refresh(todo)
    assert todo.status == TodoStatus.postponed
    assert todo.postponed_at is not None
    assert todo.postponed_at.tzinfo is not None


def test_todos_activate_batch_restores_status(app_request, dbsession):
    todo = _todo(status=TodoStatus.done, done_at=_now())
    dbsession.add(todo)
    dbsession.flush()
    app_request.method = "POST"
    app_request.POST["todo_ids"] = str(todo.id)
    todos_activate_batch(app_request)
    dbsession.flush()
    dbsession.refresh(todo)
    assert todo.status == TodoStatus.todo
    assert todo.done_at is None


def test_todos_done_marks_multiple(app_request, dbsession):
    todos = [_todo(f"T{i}") for i in range(3)]
    for t in todos:
        dbsession.add(t)
    dbsession.flush()
    app_request.method = "POST"
    app_request.POST["todo_ids"] = ",".join(str(t.id) for t in todos)
    todos_done(app_request)
    dbsession.flush()
    for t in todos:
        dbsession.refresh(t)
        assert t.status == TodoStatus.done


def test_todos_activate_all_postponed(app_request, dbsession):
    todos = [_todo(f"P{i}", status=TodoStatus.postponed) for i in range(2)]
    for t in todos:
        dbsession.add(t)
    dbsession.flush()
    todos_activate_all_postponed(app_request)
    dbsession.flush()
    for t in todos:
        dbsession.refresh(t)
        assert t.status == TodoStatus.todo
        assert t.postponed_at is None


def test_todo_undo_reverts_done_to_todo(app_request, dbsession):
    todo = _todo(status=TodoStatus.done, done_at=_now())
    dbsession.add(todo)
    dbsession.flush()
    app_request.method = "POST"
    app_request.POST["todo_ids"] = str(todo.id)
    app_request.POST["prev_status"] = "todo"
    todo_undo(app_request)
    dbsession.flush()
    dbsession.refresh(todo)
    assert todo.status == TodoStatus.todo
    assert todo.done_at is None


def test_todo_undo_reverts_postponed_to_todo(app_request, dbsession):
    todo = _todo(status=TodoStatus.postponed, postponed_at=_now())
    dbsession.add(todo)
    dbsession.flush()
    app_request.method = "POST"
    app_request.POST["todo_ids"] = str(todo.id)
    app_request.POST["prev_status"] = "todo"
    todo_undo(app_request)
    dbsession.flush()
    dbsession.refresh(todo)
    assert todo.status == TodoStatus.todo
    assert todo.postponed_at is None


def test_todo_undo_returns_list_html_with_confirm_trigger(app_request, dbsession):
    todo = _todo("Undo me", status=TodoStatus.done, done_at=_now())
    dbsession.add(todo)
    dbsession.flush()
    app_request.method = "POST"
    app_request.POST["todo_ids"] = str(todo.id)
    app_request.POST["prev_status"] = "todo"
    todo_undo(app_request)
    assert app_request.response.content_type == "text/html"
    trigger = json.loads(app_request.response.headers["HX-Trigger"])
    assert "showUndoConfirm" in trigger
    assert trigger["showUndoConfirm"]["label"] == "Undo me"


def test_list_todos_done_ordered_by_done_at(app_request, dbsession):
    now = _now()
    t1 = _todo("First", status=TodoStatus.done, done_at=now - datetime.timedelta(seconds=60))
    t2 = _todo("Second", status=TodoStatus.done, done_at=now)
    dbsession.add_all([t1, t2])
    dbsession.flush()
    info = list_todos_done(app_request)
    assert info["todos"][0].text == "Second"


def test_list_todos_only_shows_active(app_request, dbsession):
    t_active = _todo("Active")
    t_done = _todo("Done", status=TodoStatus.done, done_at=_now())
    t_postponed = _todo("Postponed", status=TodoStatus.postponed)
    dbsession.add_all([t_active, t_done, t_postponed])
    dbsession.flush()
    info = list_todos(app_request)
    all_items = [item for g in info["groups"] for item in g["items"]]
    assert len(all_items) == 1
    assert all_items[0].text == "Active"


def test_list_todos_counts_postponed(app_request, dbsession):
    dbsession.add(_todo("P1", status=TodoStatus.postponed))
    dbsession.add(_todo("P2", status=TodoStatus.postponed))
    dbsession.flush()
    info = list_todos(app_request)
    assert info["postponed_count"] == 2


# ---------------------------------------------------------------------------
# Integration tests (WebTest)
# ---------------------------------------------------------------------------


def test_get_todos_page(testapp):
    res = testapp.get("/todos", status=200)
    assert b"Add todo" in res.body


def test_add_todo_workflow(testapp, dbsession):
    testapp.post("/todos/add", {"text": "Walk dog #chores"}, status=303)
    res = testapp.get("/todos", status=200)
    assert b"Walk dog" in res.body
    assert b"chores" in res.body


def test_done_view_shows_completed(testapp, dbsession):
    todo = _todo("Completed", status=TodoStatus.done, done_at=_now())
    dbsession.add(todo)
    dbsession.flush()
    res = testapp.get("/todos/done", status=200)
    assert b"Completed" in res.body


def test_activate_postponed_restores(testapp, dbsession):
    todo = _todo("PostponedItem", status=TodoStatus.postponed)
    dbsession.add(todo)
    dbsession.flush()
    testapp.post("/todos/activate-postponed", status=303)
    dbsession.flush()
    dbsession.refresh(todo)
    assert todo.status == TodoStatus.todo


def test_batch_done_endpoint(testapp, dbsession):
    todos = [_todo(f"Batch{i}") for i in range(2)]
    for t in todos:
        dbsession.add(t)
    dbsession.flush()
    ids = ",".join(str(t.id) for t in todos)
    res = testapp.post("/todos/done-items", {"todo_ids": ids}, status=200)
    for t in todos:
        dbsession.refresh(t)
        assert t.status == TodoStatus.done


def test_edit_todo_updates_text_and_tags(app_request, dbsession):
    todo = _todo("Old text", {"old-tag"})
    dbsession.add(todo)
    dbsession.flush()
    app_request.matchdict = {"id": str(todo.id)}
    app_request.method = "POST"
    app_request.POST["text"] = "New text #new-tag"
    edit_todo(app_request)
    dbsession.flush()
    dbsession.refresh(todo)
    assert todo.text == "New text"
    assert todo.tags == {"new-tag"}


def test_edit_todo_only_tags_returns_422(app_request, dbsession):
    todo = _todo("Something")
    dbsession.add(todo)
    dbsession.flush()
    app_request.matchdict = {"id": str(todo.id)}
    app_request.method = "POST"
    app_request.POST["text"] = "#only-tag"
    response = edit_todo(app_request)
    assert response.status_int == 422
    assert todo.text == "Something"


def test_edit_todo_workflow(testapp, dbsession):
    todo = _todo("Original")
    dbsession.add(todo)
    dbsession.flush()
    testapp.post(f"/todos/{todo.id}/edit", {"text": "Updated #work"}, status=303)
    dbsession.flush()
    dbsession.refresh(todo)
    assert todo.text == "Updated"
    assert todo.tags == {"work"}
