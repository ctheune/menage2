"""Integration tests for admin user management."""


def test_list_users(authenticated_testapp, admin_user):
    res = authenticated_testapp.get("/admin/users", status=200)
    assert b"admin" in res.body.lower()


def test_create_user(authenticated_testapp):
    res = authenticated_testapp.post(
        "/admin/users/new",
        {
            "username": "newuser",
            "real_name": "New User",
            "email": "new@example.com",
            "password": "somepassword",
        },
        status=303,
    )
    assert "admin/users" in res.location


def test_create_user_duplicate_username(authenticated_testapp, admin_user):
    res = authenticated_testapp.post(
        "/admin/users/new",
        {
            "username": "admin",
            "real_name": "Dup",
            "email": "dup@example.com",
            "password": "pw",
        },
        status=200,
    )
    assert b"already" in res.body.lower()


def test_edit_user(authenticated_testapp, regular_user):
    res = authenticated_testapp.post(
        f"/admin/users/{regular_user.id}/edit",
        {
            "real_name": "Updated Name",
            "email": "updated@example.com",
            "is_active": "1",
        },
        status=303,
    )
    assert "admin/users" in res.location


def test_deactivate_user(authenticated_testapp, regular_user):
    res = authenticated_testapp.post(
        f"/admin/users/{regular_user.id}/deactivate", status=303
    )
    assert "admin/users" in res.location


def test_cannot_deactivate_self(authenticated_testapp, admin_user):
    authenticated_testapp.post(f"/admin/users/{admin_user.id}/deactivate", status=400)


def test_delete_user(authenticated_testapp, regular_user):
    res = authenticated_testapp.post(
        f"/admin/users/{regular_user.id}/delete", status=303
    )
    assert "admin/users" in res.location


def test_cannot_delete_self(authenticated_testapp, admin_user):
    authenticated_testapp.post(f"/admin/users/{admin_user.id}/delete", status=400)


def test_cannot_delete_last_admin(authenticated_testapp, admin_user):
    authenticated_testapp.post(f"/admin/users/{admin_user.id}/delete", status=400)


def test_admin_operations_view(authenticated_testapp):
    res = authenticated_testapp.get("/admin/operations", status=200)
    assert b"dashboard" in res.body.lower()


def test_dashboard_token_redirect(authenticated_testapp):
    res = authenticated_testapp.get("/admin/dashboard-token", status=303)
    assert "admin/operations" in res.location


def test_dashboard_token_reset(authenticated_testapp):
    res = authenticated_testapp.post("/admin/dashboard-token", status=303)
    assert "admin/operations" in res.location
    follow = authenticated_testapp.get(res.location, status=200)
    assert b"dashboard" in follow.body.lower()


def test_recurrence_sweep_admin_action(authenticated_testapp, dbsession, admin_user):
    """The admin button forces a sweep regardless of the daily marker."""
    import datetime

    from menage2.models.config import ConfigItem
    from menage2.models.todo import (
        RecurrenceKind,
        RecurrenceRule,
        RecurrenceUnit,
        Todo,
    )
    from menage2.recurrence import _LAST_SWEEP_KEY

    today = datetime.date.today()
    rule = RecurrenceRule(
        kind=RecurrenceKind.every,
        interval_value=1,
        interval_unit=RecurrenceUnit.week,
    )
    dbsession.add(rule)
    dbsession.flush()
    dbsession.add(
        Todo(
            text="Bills",
            tags=set(),
            recurrence_id=rule.id,
            due_date=today - datetime.timedelta(days=14),
            created_at=datetime.datetime.now(datetime.timezone.utc),
            owner=admin_user,
        )
    )
    dbsession.add(ConfigItem(key=_LAST_SWEEP_KEY, value=today.isoformat()))
    dbsession.flush()

    res = authenticated_testapp.post("/admin/recurrence-sweep", status=303)
    assert "sweep_spawned=" in res.location

    actives = (
        dbsession.query(Todo)
        .filter(Todo.recurrence_id == rule.id, Todo.due_date >= today)
        .count()
    )
    assert actives >= 1

    follow = authenticated_testapp.get(res.location, status=200)
    assert b"sweep ran" in follow.body.lower()


def test_recurrence_sweep_requires_admin(user_testapp):
    """Non-admin users hit the @PERM_ADMIN guard."""
    user_testapp.post("/admin/recurrence-sweep", status=403)
