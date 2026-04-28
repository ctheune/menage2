"""View-level + integration tests for the Protocols feature."""

import datetime

from menage2.models.protocol import (
    Protocol,
    ProtocolItem,
    ProtocolRun,
    ProtocolRunItemStatus,
)
from menage2.models.todo import (
    RecurrenceKind,
    RecurrenceRule,
    RecurrenceUnit,
    Todo,
    TodoStatus,
)


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _today():
    return datetime.date.today()


def _make_protocol(dbsession, admin_user, title="Weekly inventory", items=()):
    p = Protocol(title=title, owner_id=admin_user.id, created_at=_now())
    dbsession.add(p)
    dbsession.flush()
    for i, txt in enumerate(items):
        dbsession.add(ProtocolItem(protocol_id=p.id, position=i, text=txt))
    dbsession.flush()
    return p


# ---------------------------------------------------------------------------
# Protocol CRUD endpoints
# ---------------------------------------------------------------------------


def test_list_protocols_page(authenticated_testapp, dbsession, admin_user):
    _make_protocol(dbsession, admin_user, title="Pantry sweep")
    res = authenticated_testapp.get("/protocols", status=200)
    assert b"Pantry sweep" in res.body


def test_new_protocol_creates_and_redirects_to_editor(authenticated_testapp, dbsession):
    res = authenticated_testapp.post(
        "/protocols/new", {"title": "Cosmetics check"}, status=303
    )
    assert "/edit" in res.location
    assert (
        dbsession.query(Protocol).filter(Protocol.title == "Cosmetics check").count()
        == 1
    )


def test_edit_protocol_composite_tags_and_note(
    authenticated_testapp, dbsession, admin_user
):
    p = _make_protocol(dbsession, admin_user)
    authenticated_testapp.post(
        f"/protocols/{p.id}/edit",
        {"composite": "Cleaning round #household ~check corners"},
        status=303,
    )
    dbsession.flush()
    dbsession.refresh(p)
    assert p.title == "Cleaning round"
    assert "household" in p.tags
    assert p.note == "check corners"


def test_edit_protocol_composite_assignees(
    authenticated_testapp, dbsession, admin_user
):
    p = _make_protocol(dbsession, admin_user)
    authenticated_testapp.post(
        f"/protocols/{p.id}/edit",
        {"composite": "Clean house #household @alice @bob"},
        status=303,
    )
    dbsession.flush()
    dbsession.refresh(p)
    assert p.title == "Clean house"
    assert "household" in p.tags
    assert "alice" in p.assignees
    assert "bob" in p.assignees


def test_edit_protocol_composite_clears_assignees(
    authenticated_testapp, dbsession, admin_user
):
    p = _make_protocol(dbsession, admin_user)
    p.assignees = {"alice"}
    dbsession.flush()
    authenticated_testapp.post(
        f"/protocols/{p.id}/edit",
        {"composite": "Clean house"},
        status=303,
    )
    dbsession.flush()
    dbsession.refresh(p)
    assert p.assignees == set()


def test_edit_protocol_composite_shows_in_form(
    authenticated_testapp, dbsession, admin_user
):
    p = _make_protocol(dbsession, admin_user)
    res = authenticated_testapp.get(f"/protocols/{p.id}/edit", status=200)
    assert b"ci-container" in res.body
    assert b"ci-hidden-input" in res.body


def test_edit_protocol_updates_title_and_recurrence(
    authenticated_testapp, dbsession, admin_user
):
    p = _make_protocol(dbsession, admin_user)
    authenticated_testapp.post(
        f"/protocols/{p.id}/edit",
        {"composite": "Renamed *every wednesday"},
        status=303,
    )
    dbsession.flush()
    dbsession.refresh(p)
    assert p.title == "Renamed"
    assert p.recurrence is not None
    assert p.recurrence.weekday == 2


def test_edit_protocol_clears_recurrence_when_empty(
    authenticated_testapp, dbsession, admin_user
):
    rule = RecurrenceRule(
        kind=RecurrenceKind.every,
        interval_value=1,
        interval_unit=RecurrenceUnit.week,
    )
    dbsession.add(rule)
    dbsession.flush()
    p = _make_protocol(dbsession, admin_user)
    p.recurrence = rule
    dbsession.flush()
    authenticated_testapp.post(
        f"/protocols/{p.id}/edit",
        {"composite": p.title},
        status=303,
    )
    dbsession.flush()
    dbsession.refresh(p)
    assert p.recurrence_id is None


def test_archive_and_unarchive(authenticated_testapp, dbsession, admin_user):
    p = _make_protocol(dbsession, admin_user)
    authenticated_testapp.post(f"/protocols/{p.id}/archive", status=303)
    dbsession.flush()
    dbsession.refresh(p)
    assert p.archived_at is not None
    authenticated_testapp.post(f"/protocols/{p.id}/unarchive", status=303)
    dbsession.flush()
    dbsession.refresh(p)
    assert p.archived_at is None


def test_add_protocol_item_extracts_tags(authenticated_testapp, dbsession, admin_user):
    p = _make_protocol(dbsession, admin_user)
    authenticated_testapp.post(
        f"/protocols/{p.id}/items",
        {"text": "Check fridge #shopping:groceries"},
        status=303,
    )
    dbsession.flush()
    dbsession.refresh(p)
    assert len(p.items) == 1
    item = p.items[0]
    assert item.text == "Check fridge"
    assert item.tags == {"shopping:groceries"}


def test_update_protocol_item(authenticated_testapp, dbsession, admin_user):
    p = _make_protocol(dbsession, admin_user, items=["initial"])
    item = p.items[0]
    authenticated_testapp.post(
        f"/protocols/{p.id}/items/{item.id}",
        {"text": "updated #tag"},
        status=303,
    )
    dbsession.flush()
    dbsession.refresh(item)
    assert item.text == "updated"
    assert item.tags == {"tag"}


def test_add_protocol_item_extracts_note(authenticated_testapp, dbsession, admin_user):
    p = _make_protocol(dbsession, admin_user)
    authenticated_testapp.post(
        f"/protocols/{p.id}/items",
        {"text": "Check fridge ~look in the back"},
        status=303,
    )
    dbsession.flush()
    dbsession.refresh(p)
    item = p.items[0]
    assert item.text == "Check fridge"
    assert item.note == "look in the back"


def test_update_protocol_item_partial_returns_html(
    authenticated_testapp, dbsession, admin_user
):
    p = _make_protocol(dbsession, admin_user, items=["original"])
    item = p.items[0]
    res = authenticated_testapp.post(
        f"/protocols/{p.id}/items/{item.id}/partial",
        {"text": "updated #tag ~my note"},
        status=200,
    )
    assert res.content_type == "text/html"
    assert b"updated" in res.body
    dbsession.flush()
    dbsession.refresh(item)
    assert item.text == "updated"
    assert item.tags == {"tag"}
    assert item.note == "my note"


def test_delete_protocol_item(authenticated_testapp, dbsession, admin_user):
    p = _make_protocol(dbsession, admin_user, items=["one", "two"])
    item = p.items[0]
    item_id = item.id
    authenticated_testapp.post(
        f"/protocols/{p.id}/items/{item_id}/delete",
        status=303,
    )
    assert dbsession.query(ProtocolItem).filter(ProtocolItem.id == item_id).count() == 0


# ---------------------------------------------------------------------------
# Palette endpoint
# ---------------------------------------------------------------------------


def test_palette_json_returns_active_protocols(
    authenticated_testapp, dbsession, admin_user
):
    _make_protocol(dbsession, admin_user, title="Active")
    archived = _make_protocol(dbsession, admin_user, title="Archived")
    archived.archived_at = _now()
    dbsession.flush()
    res = authenticated_testapp.get("/protocols/palette.json", status=200)
    body = res.json
    titles = [p["title"] for p in body]
    assert "Active" in titles
    assert "Archived" not in titles


# ---------------------------------------------------------------------------
# Start run + snapshot
# ---------------------------------------------------------------------------


def test_start_protocol_run_creates_run_and_todo(
    authenticated_testapp, dbsession, admin_user
):
    p = _make_protocol(dbsession, admin_user, items=["a", "b"])
    res = authenticated_testapp.post(f"/protocols/{p.id}/start", status=303)
    assert "/protocols/run/" in res.location
    run = dbsession.query(ProtocolRun).filter(ProtocolRun.protocol_id == p.id).one()
    todo = dbsession.query(Todo).filter(Todo.protocol_run_id == run.id).one()
    assert todo.text == p.title
    assert todo.due_date == _today()
    assert run.opened_at is None
    assert run.items == []  # snapshot deferred


def test_show_run_snapshots_items_on_first_open(
    authenticated_testapp, dbsession, admin_user
):
    p = _make_protocol(dbsession, admin_user, items=["alpha", "beta", "gamma"])
    authenticated_testapp.post(f"/protocols/{p.id}/start", status=303)
    run = dbsession.query(ProtocolRun).filter(ProtocolRun.protocol_id == p.id).one()
    res = authenticated_testapp.get(f"/protocols/run/{run.id}", status=200)
    assert b"alpha" in res.body
    assert b"beta" in res.body
    dbsession.flush()
    dbsession.refresh(run)
    assert run.opened_at is not None
    assert len(run.items) == 3
    assert all(i.status == ProtocolRunItemStatus.pending for i in run.items)


def test_show_run_reuses_snapshot_after_template_edit(
    authenticated_testapp, dbsession, admin_user
):
    """A run's snapshot is frozen after first open; later template edits don't leak in."""
    p = _make_protocol(dbsession, admin_user, items=["original-1", "original-2"])
    authenticated_testapp.post(f"/protocols/{p.id}/start", status=303)
    run = dbsession.query(ProtocolRun).filter(ProtocolRun.protocol_id == p.id).one()
    authenticated_testapp.get(f"/protocols/run/{run.id}", status=200)
    # Now mutate the template
    authenticated_testapp.post(
        f"/protocols/{p.id}/items",
        {"text": "leak-attempt"},
        status=303,
    )
    res = authenticated_testapp.get(f"/protocols/run/{run.id}", status=200)
    assert b"leak-attempt" not in res.body
    assert b"original-1" in res.body


# ---------------------------------------------------------------------------
# Run-item actions
# ---------------------------------------------------------------------------


def _start_and_open_run(testapp, dbsession, p):
    testapp.post(f"/protocols/{p.id}/start", status=303)
    run = dbsession.query(ProtocolRun).filter(ProtocolRun.protocol_id == p.id).one()
    testapp.get(f"/protocols/run/{run.id}", status=200)
    dbsession.flush()
    dbsession.refresh(run)
    return run


def test_run_item_done_marks_status(authenticated_testapp, dbsession, admin_user):
    p = _make_protocol(dbsession, admin_user, items=["one", "two"])
    run = _start_and_open_run(authenticated_testapp, dbsession, p)
    item = run.items[0]
    authenticated_testapp.post(
        f"/protocols/run/{run.id}/items/{item.id}/done",
        status=200,
    )
    dbsession.flush()
    dbsession.refresh(item)
    assert item.status == ProtocolRunItemStatus.done


def test_run_item_send_creates_todo_and_links_back(
    authenticated_testapp, dbsession, admin_user
):
    p = _make_protocol(dbsession, admin_user, items=["buy bread"])
    run = _start_and_open_run(authenticated_testapp, dbsession, p)
    item = run.items[0]
    authenticated_testapp.post(
        f"/protocols/run/{run.id}/items/{item.id}/send",
        status=200,
    )
    dbsession.flush()
    dbsession.refresh(item)
    assert item.status == ProtocolRunItemStatus.sent_to_todo
    assert item.sent_todo_id is not None
    todo = dbsession.get(Todo, item.sent_todo_id)
    assert todo.text == "buy bread"


def test_run_item_edit_updates_text(authenticated_testapp, dbsession, admin_user):
    p = _make_protocol(dbsession, admin_user, items=["original"])
    run = _start_and_open_run(authenticated_testapp, dbsession, p)
    item = run.items[0]
    authenticated_testapp.post(
        f"/protocols/run/{run.id}/items/{item.id}/edit",
        {"text": "tweaked #tag"},
        status=200,
    )
    dbsession.flush()
    dbsession.refresh(item)
    assert item.text == "tweaked"
    assert item.tags == {"tag"}


def test_run_auto_closes_when_all_resolved(
    authenticated_testapp, dbsession, admin_user
):
    p = _make_protocol(dbsession, admin_user, items=["a", "b"])
    run = _start_and_open_run(authenticated_testapp, dbsession, p)
    for item in run.items:
        authenticated_testapp.post(
            f"/protocols/run/{run.id}/items/{item.id}/done",
            status=200,
        )
    dbsession.flush()
    dbsession.refresh(run)
    assert run.closed_at is not None
    todo = run.todo
    dbsession.flush()
    dbsession.refresh(todo)
    assert todo.status == TodoStatus.done


# ---------------------------------------------------------------------------
# Linked-todo completion side-effects
# ---------------------------------------------------------------------------


def test_completing_protocol_run_todo_closes_run(
    authenticated_testapp, dbsession, admin_user
):
    p = _make_protocol(dbsession, admin_user, items=["x"])
    authenticated_testapp.post(f"/protocols/{p.id}/start", status=303)
    run = dbsession.query(ProtocolRun).filter(ProtocolRun.protocol_id == p.id).one()
    todo = dbsession.query(Todo).filter(Todo.protocol_run_id == run.id).one()
    authenticated_testapp.post(
        "/todos/done-items", {"todo_ids": str(todo.id)}, status=200
    )
    dbsession.flush()
    dbsession.refresh(run)
    assert run.closed_at is not None


def test_edit_protocol_title_syncs_to_active_run_todos(
    authenticated_testapp, dbsession, admin_user
):
    p = _make_protocol(dbsession, admin_user, title="Old title", items=["x"])
    authenticated_testapp.post(f"/protocols/{p.id}/start", status=303)
    run = dbsession.query(ProtocolRun).filter(ProtocolRun.protocol_id == p.id).one()
    todo = dbsession.query(Todo).filter(Todo.protocol_run_id == run.id).one()
    assert todo.text == "Old title"
    authenticated_testapp.post(
        f"/protocols/{p.id}/edit", {"composite": "New title"}, status=303
    )
    dbsession.flush()
    dbsession.refresh(todo)
    assert todo.text == "New title"


def test_run_all_done_spawns_next_for_after_rule(
    authenticated_testapp, dbsession, admin_user
):
    rule = RecurrenceRule(
        kind=RecurrenceKind.after,
        interval_value=1,
        interval_unit=RecurrenceUnit.week,
    )
    dbsession.add(rule)
    dbsession.flush()
    p = _make_protocol(dbsession, admin_user, items=["a"])
    p.recurrence_id = rule.id
    dbsession.flush()
    run = _start_and_open_run(authenticated_testapp, dbsession, p)
    item = run.items[0]
    authenticated_testapp.post(
        f"/protocols/run/{run.id}/items/{item.id}/done", status=200
    )
    runs = dbsession.query(ProtocolRun).filter(ProtocolRun.protocol_id == p.id).all()
    assert len(runs) == 2


def test_completing_protocol_todo_with_after_rule_spawns_next(
    authenticated_testapp, dbsession, admin_user
):
    rule = RecurrenceRule(
        kind=RecurrenceKind.after,
        interval_value=1,
        interval_unit=RecurrenceUnit.week,
    )
    dbsession.add(rule)
    dbsession.flush()
    p = _make_protocol(dbsession, admin_user, items=["x"])
    p.recurrence_id = rule.id
    dbsession.flush()
    authenticated_testapp.post(f"/protocols/{p.id}/start", status=303)
    first_run = (
        dbsession.query(ProtocolRun).filter(ProtocolRun.protocol_id == p.id).one()
    )
    first_todo = (
        dbsession.query(Todo).filter(Todo.protocol_run_id == first_run.id).one()
    )
    authenticated_testapp.post(
        "/todos/done-items", {"todo_ids": str(first_todo.id)}, status=200
    )
    runs = dbsession.query(ProtocolRun).filter(ProtocolRun.protocol_id == p.id).all()
    assert len(runs) == 2
    new_todo = (
        dbsession.query(Todo)
        .filter(
            Todo.protocol_run_id.in_([r.id for r in runs]),
            Todo.status == TodoStatus.todo,
        )
        .one()
    )
    assert new_todo.due_date == _today() + datetime.timedelta(days=7)


# ---------------------------------------------------------------------------
# Tag JSON endpoints
# ---------------------------------------------------------------------------


def test_list_tags_json_includes_protocol_tags(
    authenticated_testapp, dbsession, admin_user
):
    p = _make_protocol(dbsession, admin_user)
    p.tags = {"maintenance", "weekly"}
    dbsession.flush()
    res = authenticated_testapp.get("/todos/tags.json", status=200)
    data = res.json
    assert "maintenance" in data
    assert "weekly" in data


def test_list_tags_json_includes_protocol_item_tags(
    authenticated_testapp, dbsession, admin_user
):
    p = _make_protocol(dbsession, admin_user, items=["check fridge"])
    item = p.items[0]
    item.tags = {"cold", "kitchen"}
    dbsession.flush()
    res = authenticated_testapp.get("/todos/tags.json", status=200)
    data = res.json
    assert "cold" in data
    assert "kitchen" in data


def test_list_top_tags_json_returns_list(authenticated_testapp):
    res = authenticated_testapp.get("/todos/top-tags.json", status=200)
    assert isinstance(res.json, list)
    assert len(res.json) <= 5
