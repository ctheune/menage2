import datetime
import json

import pytest

from menage2.dateparse import RecurrenceSpec
from menage2.models.todo import (
    RecurrenceKind,
    RecurrenceRule,
    RecurrenceUnit,
    Todo,
    TodoStatus,
)
from menage2.views.todo import (
    ParsedTodoInput,
    _bump_due_date,
    add_todo,
    build_tag_tree,
    edit_todo,
    list_todos,
    list_todos_done,
    list_todos_scheduled,
    parse_recurrence_preview,
    parse_todo_input,
    recurrence_history,
    set_due_date,
    set_recurrence,
    todo_undo,
    todos_activate_all_on_hold,
    todos_activate_batch,
    todos_done,
    todos_hold,
    todos_postpone,
)


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _today():
    return datetime.date.today()


def _todo(text="Test", tags=None, status=TodoStatus.todo, **kwargs):
    """Helper to build an unsaved Todo."""
    return Todo(text=text, tags=tags if tags is not None else set(), status=status, created_at=_now(), **kwargs)


# ---------------------------------------------------------------------------
# Pure function tests (no DB)
# ---------------------------------------------------------------------------


def test_parse_todo_input_extracts_tags():
    parsed = parse_todo_input("Buy milk #shopping #food:dairy")
    assert parsed.text == "Buy milk"
    assert parsed.tags == {"shopping", "food:dairy"}
    assert parsed.due_date is None


def test_parse_todo_input_collapses_whitespace():
    parsed = parse_todo_input("  Get  #a  bread  ")
    assert parsed.text == "Get bread"


def test_parse_todo_input_no_tags():
    parsed = parse_todo_input("plain text")
    assert parsed.text == "plain text"
    assert parsed.tags == set()


def test_parse_todo_input_dashes_and_special_chars():
    parsed = parse_todo_input("Buy things #einkaufen:bio-laden #to-do")
    assert parsed.text == "Buy things"
    assert parsed.tags == {"einkaufen:bio-laden", "to-do"}


def test_parse_todo_input_only_tags():
    parsed = parse_todo_input("#foo #bar")
    assert parsed.text == ""
    assert parsed.tags == {"foo", "bar"}


def test_parse_todo_input_extracts_simple_date():
    today = datetime.date(2026, 4, 29)
    parsed = parse_todo_input("Buy bread ^tomorrow", today=today)
    assert parsed.text == "Buy bread"
    assert parsed.due_date == datetime.date(2026, 4, 30)


def test_parse_todo_input_extracts_multiword_date_before_tag():
    today = datetime.date(2026, 4, 29)
    parsed = parse_todo_input("Buy bread ^next week #shopping", today=today)
    assert parsed.text == "Buy bread"
    assert parsed.tags == {"shopping"}
    assert parsed.due_date == datetime.date(2026, 5, 4)  # next Monday


def test_parse_todo_input_unparseable_date_kept_as_text():
    today = datetime.date(2026, 4, 29)
    parsed = parse_todo_input("Buy ^next week bread", today=today)
    # Whole "^next week bread" fragment fails to parse → leave it in text.
    assert parsed.due_date is None
    assert "^next week bread" in parsed.text


def test_parse_todo_input_iso_date():
    today = datetime.date(2026, 4, 29)
    parsed = parse_todo_input("Pay rent ^2026-05-01", today=today)
    assert parsed.text == "Pay rent"
    assert parsed.due_date == datetime.date(2026, 5, 1)


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
# Postpone interval math
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("current,interval,expected", [
    # Undated → snap to today, then bump
    (None, "1d", "2026-04-30"),
    (None, "1w", "2026-05-06"),
    (None, "1mo", "2026-05-29"),
    # Future-dated → bump from current
    (datetime.date(2026, 5, 5), "1d", "2026-05-06"),
    (datetime.date(2026, 5, 5), "2w", "2026-05-19"),
    # Overdue → snap to today first
    (datetime.date(2026, 4, 1), "1d", "2026-04-30"),
    (datetime.date(2026, 4, 1), "1w", "2026-05-06"),
    # Today → bump from today
    (datetime.date(2026, 4, 29), "3d", "2026-05-02"),
])
def test_bump_due_date(current, interval, expected):
    today = datetime.date(2026, 4, 29)
    assert _bump_due_date(current, today, interval) == datetime.date.fromisoformat(expected)


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
    assert todo.due_date is None


def test_add_todo_persists_due_date(app_request, dbsession):
    app_request.method = "POST"
    app_request.POST["text"] = "Pay rent ^2030-05-01"
    add_todo(app_request)
    todo = dbsession.query(Todo).one()
    assert todo.text == "Pay rent"
    assert todo.due_date == datetime.date(2030, 5, 1)


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


def test_todos_hold_sets_status(app_request, dbsession):
    todo = _todo()
    dbsession.add(todo)
    dbsession.flush()
    app_request.method = "POST"
    app_request.POST["todo_ids"] = str(todo.id)
    todos_hold(app_request)
    dbsession.flush()
    dbsession.refresh(todo)
    assert todo.status == TodoStatus.on_hold
    assert todo.on_hold_at is not None
    assert todo.on_hold_at.tzinfo is not None


def test_todos_postpone_sets_due_date_one_day_default(app_request, dbsession):
    todo = _todo()
    dbsession.add(todo)
    dbsession.flush()
    app_request.method = "POST"
    app_request.POST["todo_ids"] = str(todo.id)
    todos_postpone(app_request)
    dbsession.flush()
    dbsession.refresh(todo)
    assert todo.due_date == _today() + datetime.timedelta(days=1)
    assert todo.status == TodoStatus.todo  # status untouched


def test_todos_postpone_with_interval(app_request, dbsession):
    todo = _todo()
    dbsession.add(todo)
    dbsession.flush()
    app_request.method = "POST"
    app_request.POST["todo_ids"] = str(todo.id)
    app_request.POST["interval"] = "1w"
    todos_postpone(app_request)
    dbsession.flush()
    dbsession.refresh(todo)
    assert todo.due_date == _today() + datetime.timedelta(days=7)


def test_todos_postpone_overdue_snaps_to_today_first(app_request, dbsession):
    todo = _todo(due_date=_today() - datetime.timedelta(days=5))
    dbsession.add(todo)
    dbsession.flush()
    app_request.method = "POST"
    app_request.POST["todo_ids"] = str(todo.id)
    app_request.POST["interval"] = "1d"
    todos_postpone(app_request)
    dbsession.flush()
    dbsession.refresh(todo)
    # Overdue items snap to today, then +1 day.
    assert todo.due_date == _today() + datetime.timedelta(days=1)


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


def test_todos_activate_all_on_hold(app_request, dbsession):
    todos = [_todo(f"H{i}", status=TodoStatus.on_hold) for i in range(2)]
    for t in todos:
        dbsession.add(t)
    dbsession.flush()
    todos_activate_all_on_hold(app_request)
    dbsession.flush()
    for t in todos:
        dbsession.refresh(t)
        assert t.status == TodoStatus.todo
        assert t.on_hold_at is None


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


def test_todo_undo_reverts_on_hold_to_todo(app_request, dbsession):
    todo = _todo(status=TodoStatus.on_hold, on_hold_at=_now())
    dbsession.add(todo)
    dbsession.flush()
    app_request.method = "POST"
    app_request.POST["todo_ids"] = str(todo.id)
    app_request.POST["prev_status"] = "todo"
    todo_undo(app_request)
    dbsession.flush()
    dbsession.refresh(todo)
    assert todo.status == TodoStatus.todo
    assert todo.on_hold_at is None


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
    t_held = _todo("Held", status=TodoStatus.on_hold)
    dbsession.add_all([t_active, t_done, t_held])
    dbsession.flush()
    info = list_todos(app_request)
    all_items = [item for g in info["groups"] for item in g["items"]]
    assert len(all_items) == 1
    assert all_items[0].text == "Active"


def test_list_todos_hides_future_dated(app_request, dbsession):
    today = _today()
    visible = _todo("Visible", due_date=today)
    overdue = _todo("Overdue", due_date=today - datetime.timedelta(days=2))
    future = _todo("Future", due_date=today + datetime.timedelta(days=3))
    undated = _todo("Undated")
    dbsession.add_all([visible, overdue, future, undated])
    dbsession.flush()
    info = list_todos(app_request)
    all_items = [item for g in info["groups"] for item in g["items"]]
    texts = {t.text for t in all_items}
    assert texts == {"Visible", "Overdue", "Undated"}


def test_list_todos_counts(app_request, dbsession):
    today = _today()
    dbsession.add(_todo("H1", status=TodoStatus.on_hold))
    dbsession.add(_todo("H2", status=TodoStatus.on_hold))
    dbsession.add(_todo("S1", due_date=today + datetime.timedelta(days=2)))
    dbsession.flush()
    info = list_todos(app_request)
    assert info["on_hold_count"] == 2
    assert info["scheduled_count"] == 1


def test_list_todos_sorted_due_first_then_undated(app_request, dbsession):
    today = _today()
    a_undated = _todo("A_undated", tags={"x"})
    b_due_today = _todo("B_today", tags={"x"}, due_date=today)
    c_overdue = _todo("C_overdue", tags={"x"}, due_date=today - datetime.timedelta(days=3))
    dbsession.add_all([a_undated, b_due_today, c_overdue])
    dbsession.flush()
    info = list_todos(app_request)
    items = info["groups"][0]["items"]
    # Most overdue first, then today, then undated.
    assert [t.text for t in items] == ["C_overdue", "B_today", "A_undated"]


# ---------------------------------------------------------------------------
# Scheduled view
# ---------------------------------------------------------------------------


def test_list_todos_scheduled_only_future(app_request, dbsession):
    today = _today()
    today_item = _todo("Today", due_date=today)
    future = _todo("Future", due_date=today + datetime.timedelta(days=3))
    far_future = _todo("Far", due_date=today + datetime.timedelta(days=10))
    dbsession.add_all([today_item, future, far_future])
    dbsession.flush()
    info = list_todos_scheduled(app_request)
    flat = [item for g in info["groups"] for item in g["items"]]
    assert [t.text for t in flat] == ["Future", "Far"]


def test_list_todos_scheduled_grouped_by_date(app_request, dbsession):
    today = _today()
    a = _todo("A", due_date=today + datetime.timedelta(days=2))
    b = _todo("B", due_date=today + datetime.timedelta(days=2))
    c = _todo("C", due_date=today + datetime.timedelta(days=5))
    dbsession.add_all([a, b, c])
    dbsession.flush()
    info = list_todos_scheduled(app_request)
    assert len(info["groups"]) == 2
    assert len(info["groups"][0]["items"]) == 2
    assert len(info["groups"][1]["items"]) == 1


# ---------------------------------------------------------------------------
# set_due_date
# ---------------------------------------------------------------------------


def test_set_due_date_with_natural_language(app_request, dbsession):
    todo = _todo()
    dbsession.add(todo)
    dbsession.flush()
    app_request.matchdict = {"id": str(todo.id)}
    app_request.method = "POST"
    app_request.POST["due_date"] = "tomorrow"
    set_due_date(app_request)
    dbsession.flush()
    dbsession.refresh(todo)
    assert todo.due_date == _today() + datetime.timedelta(days=1)


def test_set_due_date_clears_when_empty(app_request, dbsession):
    todo = _todo(due_date=_today() + datetime.timedelta(days=2))
    dbsession.add(todo)
    dbsession.flush()
    app_request.matchdict = {"id": str(todo.id)}
    app_request.method = "POST"
    app_request.POST["due_date"] = ""
    set_due_date(app_request)
    dbsession.flush()
    dbsession.refresh(todo)
    assert todo.due_date is None


def test_set_due_date_invalid_input_returns_422(app_request, dbsession):
    todo = _todo()
    dbsession.add(todo)
    dbsession.flush()
    app_request.matchdict = {"id": str(todo.id)}
    app_request.method = "POST"
    app_request.POST["due_date"] = "not a date"
    response = set_due_date(app_request)
    assert response.status_int == 422
    assert todo.due_date is None


# ---------------------------------------------------------------------------
# Integration tests (WebTest)
# ---------------------------------------------------------------------------


def test_get_todos_page(authenticated_testapp):
    res = authenticated_testapp.get("/todos", status=200)
    assert b'id="todo-form"' in res.body
    assert b'placeholder="New todo' in res.body


def test_add_todo_workflow(authenticated_testapp, dbsession):
    authenticated_testapp.post("/todos/add", {"text": "Walk dog #chores"}, status=303)
    res = authenticated_testapp.get("/todos", status=200)
    assert b"Walk dog" in res.body
    assert b"chores" in res.body


def test_done_view_shows_completed(authenticated_testapp, dbsession):
    todo = _todo("Completed", status=TodoStatus.done, done_at=_now())
    dbsession.add(todo)
    dbsession.flush()
    res = authenticated_testapp.get("/todos/done", status=200)
    assert b"Completed" in res.body


def test_scheduled_view_lists_future_items(authenticated_testapp, dbsession):
    todo = _todo("Pay rent", due_date=_today() + datetime.timedelta(days=5))
    dbsession.add(todo)
    dbsession.flush()
    res = authenticated_testapp.get("/todos/scheduled", status=200)
    assert b"Pay rent" in res.body


def test_activate_on_hold_restores(authenticated_testapp, dbsession):
    todo = _todo("HeldItem", status=TodoStatus.on_hold)
    dbsession.add(todo)
    dbsession.flush()
    authenticated_testapp.post("/todos/activate-on-hold", status=303)
    dbsession.flush()
    dbsession.refresh(todo)
    assert todo.status == TodoStatus.todo


def test_batch_done_endpoint(authenticated_testapp, dbsession):
    todos = [_todo(f"Batch{i}") for i in range(2)]
    for t in todos:
        dbsession.add(t)
    dbsession.flush()
    ids = ",".join(str(t.id) for t in todos)
    res = authenticated_testapp.post("/todos/done-items", {"todo_ids": ids}, status=200)
    for t in todos:
        dbsession.refresh(t)
        assert t.status == TodoStatus.done


def test_postpone_endpoint_bumps_due_date(authenticated_testapp, dbsession):
    todo = _todo("Bump me")
    dbsession.add(todo)
    dbsession.flush()
    authenticated_testapp.post("/todos/postpone-items", {"todo_ids": str(todo.id), "interval": "2w"}, status=200)
    dbsession.refresh(todo)
    assert todo.due_date == _today() + datetime.timedelta(days=14)


def test_set_due_date_endpoint(authenticated_testapp, dbsession):
    todo = _todo("Schedule me")
    dbsession.add(todo)
    dbsession.flush()
    authenticated_testapp.post(f"/todos/{todo.id}/due-date", {"due_date": "tomorrow"}, status=200)
    dbsession.refresh(todo)
    assert todo.due_date == _today() + datetime.timedelta(days=1)


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


def test_edit_todo_workflow(authenticated_testapp, dbsession):
    todo = _todo("Original")
    dbsession.add(todo)
    dbsession.flush()
    authenticated_testapp.post(f"/todos/{todo.id}/edit", {"text": "Updated #work"}, status=303)
    dbsession.flush()
    dbsession.refresh(todo)
    assert todo.text == "Updated"
    assert todo.tags == {"work"}


# ---------------------------------------------------------------------------
# Recurrence — parse_todo_input + add/edit/done flows
# ---------------------------------------------------------------------------


def test_parse_todo_input_extracts_recurrence():
    parsed = parse_todo_input("Water plants *every week #garden")
    assert parsed.text == "Water plants"
    assert parsed.tags == {"garden"}
    assert parsed.recurrence == RecurrenceSpec(
        kind="every", interval_value=1, interval_unit="week"
    )


def test_parse_todo_input_extracts_after_recurrence():
    parsed = parse_todo_input("Vacuum *after 10 days")
    assert parsed.text == "Vacuum"
    assert parsed.recurrence == RecurrenceSpec(
        kind="after", interval_value=10, interval_unit="day"
    )


def test_parse_todo_input_extracts_weekday_recurrence():
    parsed = parse_todo_input("Yoga *every wednesday #fitness")
    assert parsed.text == "Yoga"
    assert parsed.recurrence == RecurrenceSpec(
        kind="every", interval_value=1, interval_unit="week", weekday=2
    )


def test_parse_todo_input_unparseable_recurrence_kept_as_text():
    parsed = parse_todo_input("nope *blah blah")
    assert parsed.recurrence is None
    assert "*blah blah" in parsed.text


def test_add_todo_creates_recurrence_rule(app_request, dbsession):
    app_request.method = "POST"
    app_request.POST["text"] = "Water plants *every week"
    add_todo(app_request)
    todo = dbsession.query(Todo).one()
    assert todo.text == "Water plants"
    assert todo.recurrence_id is not None
    rule = dbsession.get(RecurrenceRule, todo.recurrence_id)
    assert rule.kind == RecurrenceKind.every
    assert rule.interval_unit == RecurrenceUnit.week
    assert rule.interval_value == 1


def test_edit_todo_updates_existing_rule_in_place(app_request, dbsession):
    rule = RecurrenceRule(
        kind=RecurrenceKind.every,
        interval_value=1,
        interval_unit=RecurrenceUnit.week,
    )
    dbsession.add(rule)
    dbsession.flush()
    todo = _todo("Yoga", recurrence_id=rule.id)
    dbsession.add(todo)
    dbsession.flush()
    app_request.matchdict = {"id": str(todo.id)}
    app_request.method = "POST"
    app_request.POST["text"] = "Yoga *every 2 weeks"
    edit_todo(app_request)
    dbsession.flush()
    dbsession.refresh(todo)
    dbsession.refresh(rule)
    assert todo.recurrence_id == rule.id
    assert rule.interval_value == 2


def test_edit_todo_clears_recurrence_when_dropped(app_request, dbsession):
    rule = RecurrenceRule(
        kind=RecurrenceKind.every,
        interval_value=1,
        interval_unit=RecurrenceUnit.week,
    )
    dbsession.add(rule)
    dbsession.flush()
    todo = _todo("Yoga", recurrence_id=rule.id)
    dbsession.add(todo)
    dbsession.flush()
    app_request.matchdict = {"id": str(todo.id)}
    app_request.method = "POST"
    app_request.POST["text"] = "Yoga"
    edit_todo(app_request)
    dbsession.flush()
    dbsession.refresh(todo)
    assert todo.recurrence_id is None


def test_todos_done_spawns_after_instance(app_request, dbsession):
    rule = RecurrenceRule(
        kind=RecurrenceKind.after,
        interval_value=1,
        interval_unit=RecurrenceUnit.week,
    )
    dbsession.add(rule)
    dbsession.flush()
    todo = _todo("Vacuum", recurrence_id=rule.id)
    dbsession.add(todo)
    dbsession.flush()
    app_request.method = "POST"
    app_request.POST["todo_ids"] = str(todo.id)
    todos_done(app_request)
    dbsession.flush()
    children = dbsession.query(Todo).filter(Todo.recurred_from_id == todo.id).all()
    assert len(children) == 1
    assert children[0].text == "Vacuum"
    assert children[0].recurrence_id == rule.id
    assert children[0].due_date == _today() + datetime.timedelta(days=7)


def test_todos_done_spawns_every_instance(app_request, dbsession):
    """Completing the only active in an every-chain must spawn the next."""
    rule = RecurrenceRule(
        kind=RecurrenceKind.every,
        interval_value=1,
        interval_unit=RecurrenceUnit.week,
        weekday=_today().weekday(),
    )
    dbsession.add(rule)
    dbsession.flush()
    todo = _todo("Weekly", recurrence_id=rule.id, due_date=_today())
    dbsession.add(todo)
    dbsession.flush()
    app_request.method = "POST"
    app_request.POST["todo_ids"] = str(todo.id)
    todos_done(app_request)
    dbsession.flush()
    pending = dbsession.query(Todo).filter(
        Todo.recurrence_id == rule.id,
        Todo.status == TodoStatus.todo,
    ).all()
    assert len(pending) == 1
    assert pending[0].due_date == _today() + datetime.timedelta(days=7)
    assert pending[0].recurred_from_id == todo.id


# ---------------------------------------------------------------------------
# set_recurrence / parse_recurrence_preview / recurrence_history
# ---------------------------------------------------------------------------


def test_set_recurrence_creates_rule(app_request, dbsession):
    todo = _todo("Subject")
    dbsession.add(todo)
    dbsession.flush()
    app_request.matchdict = {"id": str(todo.id)}
    app_request.method = "POST"
    app_request.POST["recurrence"] = "every wednesday"
    set_recurrence(app_request)
    dbsession.flush()
    dbsession.refresh(todo)
    assert todo.recurrence_id is not None
    assert todo.recurrence.weekday == 2


def test_set_recurrence_clears_when_empty(app_request, dbsession):
    rule = RecurrenceRule(
        kind=RecurrenceKind.every,
        interval_value=1,
        interval_unit=RecurrenceUnit.week,
    )
    dbsession.add(rule)
    dbsession.flush()
    todo = _todo("Subject", recurrence_id=rule.id)
    dbsession.add(todo)
    dbsession.flush()
    app_request.matchdict = {"id": str(todo.id)}
    app_request.method = "POST"
    app_request.POST["recurrence"] = ""
    set_recurrence(app_request)
    dbsession.flush()
    dbsession.refresh(todo)
    assert todo.recurrence_id is None


def test_set_recurrence_invalid_returns_422(app_request, dbsession):
    todo = _todo("Subject")
    dbsession.add(todo)
    dbsession.flush()
    app_request.matchdict = {"id": str(todo.id)}
    app_request.method = "POST"
    app_request.POST["recurrence"] = "garbled"
    response = set_recurrence(app_request)
    assert response.status_int == 422


def test_parse_recurrence_preview_endpoint(authenticated_testapp):
    res = authenticated_testapp.get("/todos/parse-recurrence?q=every+monday", status=200)
    body = json.loads(res.body)
    assert body["ok"] is True
    assert body["label"] == "every Monday"
    assert body["weekday"] == 0


def test_parse_recurrence_preview_unparseable(authenticated_testapp):
    res = authenticated_testapp.get("/todos/parse-recurrence?q=blah", status=200)
    body = json.loads(res.body)
    assert body["ok"] is False


def test_recurrence_history_returns_chain(authenticated_testapp, dbsession):
    rule = RecurrenceRule(
        kind=RecurrenceKind.every,
        interval_value=1,
        interval_unit=RecurrenceUnit.week,
    )
    dbsession.add(rule)
    dbsession.flush()
    a = _todo("A", recurrence_id=rule.id, status=TodoStatus.done, done_at=_now())
    dbsession.add(a)
    dbsession.flush()
    b = _todo("B", recurrence_id=rule.id, recurred_from_id=a.id)
    dbsession.add(b)
    dbsession.flush()
    res = authenticated_testapp.get(f"/todos/{b.id}/history", status=200)
    assert b"A" in res.body
    assert b"B" in res.body
    assert b"every Monday" not in res.body  # rule label is "every a week" here
    assert b"Repetition history" in res.body


def test_list_todos_runs_daily_sweep_creating_future_instance(app_request, dbsession):
    rule = RecurrenceRule(
        kind=RecurrenceKind.every,
        interval_value=1,
        interval_unit=RecurrenceUnit.week,
    )
    dbsession.add(rule)
    dbsession.flush()
    today = _today()
    # Anchor in the past so the chain has no today-or-future active item yet.
    anchor = _todo("Sweep", recurrence_id=rule.id,
                   due_date=today - datetime.timedelta(days=14))
    dbsession.add(anchor)
    dbsession.flush()
    list_todos(app_request)
    dbsession.flush()
    actives = dbsession.query(Todo).filter(
        Todo.recurrence_id == rule.id,
        Todo.due_date >= today,
    ).all()
    assert len(actives) >= 1
