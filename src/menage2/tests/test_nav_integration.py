"""Integration tests for the new navigation structure and on-hold todos list."""

import datetime

import pytest

from menage2.models.todo import Todo, TodoStatus


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


# ---------------------------------------------------------------------------
# Navigation structure
# ---------------------------------------------------------------------------


def test_food_nav_active_on_recipes(authenticated_testapp):
    res = authenticated_testapp.get("/recipes", status=200)
    assert b"Food" in res.body
    assert b"Recipes" in res.body


def test_tasks_nav_active_on_todos(authenticated_testapp):
    res = authenticated_testapp.get("/todos", status=200)
    assert b"Tasks" in res.body
    assert b"Active" in res.body
    assert b"On Hold" in res.body
    assert b"Scheduled" in res.body
    assert b"Done" in res.body
    assert b"Protocols" in res.body


def test_tasks_subnav_on_protocols(authenticated_testapp):
    res = authenticated_testapp.get("/protocols", status=200)
    assert b"Tasks" in res.body
    assert b"Protocols" in res.body


def test_task_subnav_partial_returns_nav_items(authenticated_testapp):
    res = authenticated_testapp.get(
        "/todos/subnav",
        headers={"HX-Current-URL": "http://localhost/todos"},
        status=200,
    )
    assert b"Active" in res.body
    assert b"On Hold" in res.body
    assert b"Scheduled" in res.body
    assert b"Done" in res.body
    assert b"Protocols" in res.body


def test_task_subnav_partial_active_state_on_hold(authenticated_testapp):
    res = authenticated_testapp.get(
        "/todos/subnav",
        headers={"HX-Current-URL": "http://example.com/todos/hold"},
        status=200,
    )
    assert b"nav-link active" in res.body
    assert b"On Hold" in res.body
    # Active tab should not be highlighted
    active_idx = res.body.index(b"nav-link active")
    on_hold_idx = res.body.index(b"On Hold")
    assert active_idx < on_hold_idx


def test_task_subnav_partial_active_state_protocols(authenticated_testapp):
    res = authenticated_testapp.get(
        "/todos/subnav",
        headers={"HX-Current-URL": "http://example.com/protocols"},
        status=200,
    )
    assert b"nav-link active" in res.body
    assert b"Protocols" in res.body
    active_idx = res.body.index(b"nav-link active")
    protocols_idx = res.body.index(b"Protocols")
    assert active_idx < protocols_idx


def test_maintenance_nav_active_on_admin_users(authenticated_testapp):
    res = authenticated_testapp.get("/admin/users", status=200)
    assert b"Maintenance" in res.body
    assert b"Crew" in res.body
    assert b"Departments" in res.body


def test_logoff_label(authenticated_testapp):
    res = authenticated_testapp.get("/todos", status=200)
    assert b"Log off" in res.body
    assert b"Sign out" not in res.body


# ---------------------------------------------------------------------------
# On-hold todos list
# ---------------------------------------------------------------------------


def test_list_todos_hold_empty(authenticated_testapp):
    res = authenticated_testapp.get("/todos/hold", status=200)
    assert b"Nothing on hold" in res.body


def test_list_todos_hold_shows_on_hold_item(
    authenticated_testapp, dbsession, admin_user
):
    todo = Todo(
        text="Paused task",
        tags=set(),
        status=TodoStatus.on_hold,
        owner_id=admin_user.id,
        created_at=_now(),
    )
    dbsession.add(todo)
    dbsession.flush()

    res = authenticated_testapp.get("/todos/hold", status=200)
    assert b"Paused task" in res.body


def test_list_todos_hold_activate_all(authenticated_testapp, dbsession, admin_user):
    todo = Todo(
        text="On hold item",
        tags=set(),
        status=TodoStatus.on_hold,
        owner_id=admin_user.id,
        created_at=_now(),
    )
    dbsession.add(todo)
    dbsession.flush()

    res = authenticated_testapp.post("/todos/activate-on-hold", status=303)
    assert "/todos" in res.location


def test_list_todos_hold_requires_auth(testapp, admin_user):
    testapp.get("/todos/hold", status="3*")


# ---------------------------------------------------------------------------
# Admin operations combined page
# ---------------------------------------------------------------------------


def test_admin_operations_shows_dashboard_section(authenticated_testapp):
    res = authenticated_testapp.get("/admin/operations", status=200)
    assert b"Kitchen Dashboard" in res.body
    assert b"Recurrence Sweep" in res.body


def test_admin_operations_shows_sweep_result(authenticated_testapp):
    res = authenticated_testapp.get("/admin/operations?sweep_spawned=3", status=200)
    assert b"3 todo" in res.body


def test_admin_operations_requires_admin(user_testapp):
    user_testapp.get("/admin/operations", status=403)


def test_admin_operations_title_is_maintenance(authenticated_testapp):
    res = authenticated_testapp.get("/admin/operations", status=200)
    assert b"Maintenance" in res.body


def test_composite_playground_requires_admin(user_testapp):
    user_testapp.get("/admin/composite-playground", status=403)


# ---------------------------------------------------------------------------
# Protocol archive button in actions slot
# ---------------------------------------------------------------------------


def test_protocol_archive_in_actions(authenticated_testapp, dbsession, admin_user):
    from menage2.models.protocol import Protocol

    p = Protocol(title="Test protocol", owner_id=admin_user.id)
    dbsession.add(p)
    dbsession.flush()

    res = authenticated_testapp.get(f"/protocols/{p.id}/edit", status=200)
    assert b"Archive" in res.body
