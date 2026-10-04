"""View-level + integration tests for the Protocols feature."""

import datetime

from menage2.models.item import (
    RecurrenceKind,
    RecurrenceRule,
    RecurrenceUnit,
    TodoStatus,
)
from menage2.models.protocol import (
    Protocol,
    ProtocolItem,
    ProtocolRun,
)
from menage2.models.todo import Todo


def _now():
    return datetime.datetime.now(datetime.UTC)


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
# Unit tests (no DB)
# ---------------------------------------------------------------------------


def test_sorted_run_items_pending_first():
    from types import SimpleNamespace

    from menage2.models.protocol import ProtocolRun

    done = SimpleNamespace(is_pending=False, position=0)
    sent = SimpleNamespace(is_pending=False, position=1)
    pending_a = SimpleNamespace(is_pending=True, position=2)
    pending_b = SimpleNamespace(is_pending=True, position=3)

    run = SimpleNamespace(items=[done, sent, pending_a, pending_b])
    result = ProtocolRun.sorted_items(run)

    assert result[0] is pending_a
    assert result[1] is pending_b
    assert result[2] is done
    assert result[3] is sent


def test_sorted_run_items_preserves_position_within_group():
    from types import SimpleNamespace

    from menage2.models.protocol import ProtocolRun

    pending_2 = SimpleNamespace(is_pending=True, position=2)
    pending_0 = SimpleNamespace(is_pending=True, position=0)
    done_1 = SimpleNamespace(is_pending=False, position=1)
    done_3 = SimpleNamespace(is_pending=False, position=3)

    run = SimpleNamespace(items=[pending_2, done_3, pending_0, done_1])
    result = ProtocolRun.sorted_items(run)

    assert result[0] is pending_0
    assert result[1] is pending_2
    assert result[2] is done_1
    assert result[3] is done_3


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


def test_edit_protocol_in_the_panel(authenticated_testapp, dbsession, admin_user, cast):
    p = _make_protocol(dbsession, admin_user)
    authenticated_testapp.post_json(
        f"/items/{p.id}",
        {
            "text": "Clean house",
            "tags": ["household"],
            "assignees": ["alice", "bob"],
            "note": "check corners",
        },
        status=200,
    )
    dbsession.flush()
    dbsession.refresh(p)
    assert p.title == "Clean house"
    assert p.tags == {"household"}
    assert p.assignees == {"alice", "bob"}
    assert p.note == "check corners"


def test_edit_protocol_sets_recurrence(authenticated_testapp, dbsession, admin_user):
    p = _make_protocol(dbsession, admin_user)
    authenticated_testapp.post_json(
        f"/items/{p.id}", {"recurrence": "every wednesday"}, status=200
    )
    dbsession.flush()
    dbsession.refresh(p)
    assert p.recurrence is not None
    assert p.recurrence.weekday == 2
    # A repeating checklist always has a run waiting.
    assert (
        dbsession.query(ProtocolRun).filter(ProtocolRun.protocol_id == p.id).count()
        == 1
    )


def test_edit_protocol_clears_recurrence(authenticated_testapp, dbsession, admin_user):
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
    authenticated_testapp.post_json(
        f"/items/{p.id}", {"clear_fields": ["recurrence"]}, status=200
    )
    dbsession.flush()
    dbsession.refresh(p)
    assert p.recurrence_id is None


def test_edit_protocol_leaves_recurrence_alone_when_not_sent(
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
    authenticated_testapp.post_json(f"/items/{p.id}", {"note": "x"}, status=200)
    dbsession.flush()
    dbsession.refresh(p)
    assert p.recurrence is rule


def test_a_protocol_item_does_not_repeat(authenticated_testapp, dbsession, admin_user):
    """Only the checklist has a cadence; a recurrence sent for a line is ignored."""
    p = _make_protocol(dbsession, admin_user, items=["initial"])
    item = p.items[0]
    authenticated_testapp.post_json(
        f"/items/{item.id}", {"recurrence": "every week"}, status=200
    )
    dbsession.flush()
    dbsession.refresh(p)
    assert p.recurrence is None


def test_update_protocol_item_in_the_panel(
    authenticated_testapp, dbsession, admin_user
):
    p = _make_protocol(dbsession, admin_user, items=["initial"])
    item = p.items[0]
    authenticated_testapp.post_json(
        f"/items/{item.id}",
        {"text": "updated", "tags": ["tag"], "note": "my note"},
        status=200,
    )
    dbsession.flush()
    dbsession.refresh(item)
    assert item.text == "updated"
    assert item.tags == {"tag"}
    assert item.note == "my note"


def test_edit_protocol_title_syncs_to_active_run_todos(
    authenticated_testapp, dbsession, admin_user
):
    p = _make_protocol(dbsession, admin_user, title="Old title", items=["x"])
    authenticated_testapp.post(f"/protocols/{p.id}/start", status=303)
    run = dbsession.query(ProtocolRun).filter(ProtocolRun.protocol_id == p.id).one()
    assert run.text == "Old title"
    authenticated_testapp.post_json(f"/items/{p.id}", {"text": "New title"}, status=200)
    dbsession.flush()
    dbsession.refresh(run)
    assert run.text == "New title"


def test_the_edit_page_has_no_inline_editors(
    authenticated_testapp, dbsession, admin_user
):
    """The lines and the title open the panel; there is nothing to type into."""
    p = _make_protocol(dbsession, admin_user, items=["one"])
    body = authenticated_testapp.get(f"/protocols/{p.id}/edit", status=200).text
    assert 'name="composite"' not in body
    assert "proto-item-edit" not in body
    assert f"/items/{p.id}/panel" in body
    assert f"/items/{p.items[0].id}/panel" in body


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
    res = authenticated_testapp.post(
        f"/protocols/{p.id}/items",
        {"text": "Check fridge #shopping:groceries"},
        status=200,
    )
    assert b'id="proto-items"' in res.body
    dbsession.flush()
    dbsession.refresh(p)
    assert len(p.items) == 1
    item = p.items[0]
    assert item.text == "Check fridge"
    assert item.tags == {"shopping:groceries"}


def test_add_protocol_item_extracts_note(authenticated_testapp, dbsession, admin_user):
    p = _make_protocol(dbsession, admin_user)
    authenticated_testapp.post(
        f"/protocols/{p.id}/items",
        {"text": "Check fridge ~look in the back"},
        status=200,
    )
    dbsession.flush()
    dbsession.refresh(p)
    item = p.items[0]
    assert item.text == "Check fridge"
    assert item.note == "look in the back"


def test_delete_protocol_item(authenticated_testapp, dbsession, admin_user):
    p = _make_protocol(dbsession, admin_user, items=["one", "two"])
    item = p.items[0]
    item_id = item.id
    res = authenticated_testapp.post(
        f"/protocols/{p.id}/items/{item_id}/delete",
        status=200,
    )
    # Empty body: htmx swaps the row away with hx-swap="outerHTML".
    assert res.body == b""
    assert dbsession.query(ProtocolItem).filter(ProtocolItem.id == item_id).count() == 0


# ---------------------------------------------------------------------------
# Start run + snapshot
# ---------------------------------------------------------------------------


def test_start_protocol_run_creates_run_and_todo(
    authenticated_testapp, dbsession, admin_user
):
    p = _make_protocol(dbsession, admin_user, items=["a", "b"])
    authenticated_testapp.post(f"/protocols/{p.id}/start", status=303)
    run = dbsession.query(ProtocolRun).filter(ProtocolRun.protocol_id == p.id).one()
    todo = run  # the run is the task; one row, not two
    assert todo.text == p.title
    assert todo.due_date == _today()
    assert run.opened_at is None
    assert run.items == []  # snapshot deferred


def test_start_protocol_run_copies_assignees_to_todo(
    authenticated_testapp, dbsession, admin_user, cast
):
    p = _make_protocol(dbsession, admin_user, items=["a"])
    p.assignees = {"alice", "bob"}
    dbsession.flush()
    authenticated_testapp.post(f"/protocols/{p.id}/start", status=303)
    run = dbsession.query(ProtocolRun).filter(ProtocolRun.protocol_id == p.id).one()
    todo = run  # the run is the task; one row, not two
    assert todo.assignees == {"alice", "bob"}


def test_start_protocol_run_copies_tags_to_todo(
    authenticated_testapp, dbsession, admin_user
):
    p = _make_protocol(dbsession, admin_user, items=["a"])
    p.tags = {"maintenance", "weekly"}
    dbsession.flush()
    authenticated_testapp.post(f"/protocols/{p.id}/start", status=303)
    run = dbsession.query(ProtocolRun).filter(ProtocolRun.protocol_id == p.id).one()
    todo = run  # the run is the task; one row, not two
    assert todo.tags == {"maintenance", "weekly"}


def test_show_run_snapshots_items_on_first_open(
    authenticated_testapp, dbsession, admin_user
):
    p = _make_protocol(dbsession, admin_user, items=["alpha", "beta", "gamma"])
    authenticated_testapp.post(f"/protocols/{p.id}/start", status=303)
    run = dbsession.query(ProtocolRun).filter(ProtocolRun.protocol_id == p.id).one()
    todo = run  # the run is the task; one row, not two
    res = authenticated_testapp.get(
        f"/todos/details-panel?todo_ids[]={todo.id}", status=200
    )
    assert b"alpha" in res.body
    assert b"beta" in res.body
    dbsession.flush()
    dbsession.refresh(run)
    assert run.opened_at is not None
    assert len(run.items) == 3
    assert all(i.is_pending for i in run.items)


def test_show_run_reuses_snapshot_after_template_edit(
    authenticated_testapp, dbsession, admin_user
):
    """A run's snapshot is frozen after first open; later template edits don't leak in."""
    p = _make_protocol(dbsession, admin_user, items=["original-1", "original-2"])
    authenticated_testapp.post(f"/protocols/{p.id}/start", status=303)
    run = dbsession.query(ProtocolRun).filter(ProtocolRun.protocol_id == p.id).one()
    todo = run  # the run is the task; one row, not two
    authenticated_testapp.get(f"/todos/details-panel?todo_ids[]={todo.id}", status=200)
    # Now mutate the template
    authenticated_testapp.post(
        f"/protocols/{p.id}/items",
        {"text": "leak-attempt"},
        status=200,
    )
    res = authenticated_testapp.get(
        f"/todos/details-panel?todo_ids[]={todo.id}", status=200
    )
    assert b"leak-attempt" not in res.body
    assert b"original-1" in res.body


# ---------------------------------------------------------------------------
# Run-item actions
# ---------------------------------------------------------------------------


def _start_and_open_run(testapp, dbsession, p):
    testapp.post(f"/protocols/{p.id}/start", status=303)
    run = dbsession.query(ProtocolRun).filter(ProtocolRun.protocol_id == p.id).one()
    todo = run  # the run is the task; one row, not two
    testapp.get(f"/todos/details-panel?todo_ids[]={todo.id}", status=200)
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
    assert item.state == "done"


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
    assert item.state == "sent_to_todo"
    assert item.sent_todo_id is not None
    todo = dbsession.get(Todo, item.sent_todo_id)
    assert todo.text == "buy bread"


def _dress_up(dbsession, line):
    """Give a checklist line everything an item can carry."""
    from menage2.models.item import ItemAttachment, ItemLink

    line.note = "the big one"
    line.tags = {"kitchen"}
    line.links = [ItemLink(label="Manual", url="https://example.com/m", position=0)]
    line.attachments = [
        ItemAttachment(
            uuid="11111111-2222-3333-4444-555555555555",
            original_filename="shelf.jpg",
            mimetype="image/jpeg",
        )
    ]
    dbsession.flush()


def _carries_everything(item):
    assert item.note == "the big one"
    assert item.tags == {"kitchen"}
    assert [(link.label, link.url) for link in item.links] == [
        ("Manual", "https://example.com/m")
    ]
    assert [att.uuid for att in item.attachments] == [
        "11111111-2222-3333-4444-555555555555"
    ]


def test_a_run_item_carries_everything_its_line_has(
    authenticated_testapp, dbsession, admin_user
):
    p = _make_protocol(dbsession, admin_user, items=["descale kettle"])
    line = p.items[0]
    _dress_up(dbsession, line)

    run = _start_and_open_run(authenticated_testapp, dbsession, p)

    _carries_everything(run.items[0])
    # Copied, not moved: the template line keeps its own.
    dbsession.expire_all()
    _carries_everything(line)


def test_a_sent_todo_carries_everything_its_run_item_has(
    authenticated_testapp, dbsession, admin_user
):
    p = _make_protocol(dbsession, admin_user, items=["descale kettle"])
    _dress_up(dbsession, p.items[0])
    run = _start_and_open_run(authenticated_testapp, dbsession, p)
    item = run.items[0]

    authenticated_testapp.post(
        f"/protocols/run/{run.id}/items/{item.id}/send", status=200
    )
    dbsession.expire_all()

    _carries_everything(dbsession.get(Todo, item.sent_todo_id))
    _carries_everything(item)


def test_a_shared_file_stays_while_another_item_has_it(
    authenticated_testapp, dbsession, admin_user, attachments_dir
):
    """The run item and its line share one stored image; dropping it from
    the run item must not take it away from the line."""
    p = _make_protocol(dbsession, admin_user, items=["descale kettle"])
    line = p.items[0]
    _dress_up(dbsession, line)
    stored = attachments_dir / "11111111-2222-3333-4444-555555555555.jpg"
    stored.write_bytes(b"jpeg")
    run = _start_and_open_run(authenticated_testapp, dbsession, p)
    item = run.items[0]

    authenticated_testapp.post_json(
        f"/items/{item.id}", {"attachments": []}, status=200
    )
    dbsession.expire_all()

    assert item.attachments == []
    assert len(line.attachments) == 1
    assert stored.exists()

    authenticated_testapp.post_json(
        f"/items/{line.id}", {"attachments": []}, status=200
    )
    assert not stored.exists()


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
    assert run.status == TodoStatus.done
    todo = run
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
    todo = run  # the run is the task; one row, not two
    authenticated_testapp.post(
        "/todos/done-items", {"todo_ids": str(todo.id)}, status=200
    )
    dbsession.flush()
    dbsession.refresh(run)
    assert run.status == TodoStatus.done


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


def test_automatic_protocol_run_copies_assignees_and_tags(
    authenticated_testapp, dbsession, admin_user, cast
):
    rule = RecurrenceRule(
        kind=RecurrenceKind.after,
        interval_value=1,
        interval_unit=RecurrenceUnit.week,
    )
    dbsession.add(rule)
    dbsession.flush()
    p = _make_protocol(dbsession, admin_user, items=["a"])
    p.recurrence = rule
    p.assignees = {"carol"}
    p.tags = {"automated"}
    dbsession.flush()
    run = _start_and_open_run(authenticated_testapp, dbsession, p)
    first_todo = run
    assert first_todo.assignees == {"carol"}
    assert first_todo.tags == {"automated"}
    # Now complete and spawn the next run
    item = run.items[0]
    authenticated_testapp.post(
        f"/protocols/run/{run.id}/items/{item.id}/done", status=200
    )
    dbsession.flush()
    runs = (
        dbsession.query(ProtocolRun)
        .filter(ProtocolRun.protocol_id == p.id)
        .order_by(ProtocolRun.created_at)
        .all()
    )
    assert len(runs) == 2
    second_run = runs[1]
    second_todo = second_run
    assert second_todo.assignees == {"carol"}
    assert second_todo.tags == {"automated"}


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
    first_todo = first_run
    authenticated_testapp.post(
        "/todos/done-items", {"todo_ids": str(first_todo.id)}, status=200
    )
    runs = dbsession.query(ProtocolRun).filter(ProtocolRun.protocol_id == p.id).all()
    assert len(runs) == 2
    new_todo = (
        dbsession.query(Todo)
        .filter(
            Todo.id.in_([r.id for r in runs]),
            Todo.status == TodoStatus.todo,
        )
        .one()
    )
    assert new_todo.due_date == _today() + datetime.timedelta(days=7)
