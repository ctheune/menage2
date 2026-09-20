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

    from menage2.models.todo import (
        RecurrenceKind,
        RecurrenceRule,
        RecurrenceUnit,
        Todo,
    )

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


# ---------------------------------------------------------------------------
# Tag maintenance
# ---------------------------------------------------------------------------


def _tagged(dbsession, admin_user, text, tags):
    import datetime

    from menage2.models.todo import Todo, TodoStatus

    todo = Todo(
        text=text,
        tags=set(tags),
        assignees=set(),
        status=TodoStatus.todo,
        owner=admin_user,
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )
    dbsession.add(todo)
    dbsession.flush()
    return todo


def test_tags_page_lists_what_is_in_use(authenticated_testapp, dbsession, admin_user):
    _tagged(dbsession, admin_user, "Bread", {"einkaufen:supermarkt"})
    dbsession.flush()

    res = authenticated_testapp.get("/admin/tags", status=200)

    assert b"einkaufen:supermarkt" in res.body
    assert b"1 tasks" in res.body


def test_tag_preview_says_what_would_change(
    authenticated_testapp, dbsession, admin_user
):
    todo = _tagged(dbsession, admin_user, "Bread", {"alt"})
    dbsession.flush()

    res = authenticated_testapp.get(
        "/admin/tags/preview", {"source": "alt", "target": "neu"}, status=200
    )

    assert b"alt" in res.body and b"neu" in res.body
    # Nothing has happened yet — that is the point of a preview.
    assert todo.tags == {"alt"}


def test_tag_preview_of_an_unused_tag_offers_nothing(
    authenticated_testapp, dbsession, admin_user
):
    res = authenticated_testapp.get(
        "/admin/tags/preview", {"source": "nonesuch", "target": "neu"}, status=200
    )
    assert b"Nothing carries" in res.body
    assert b"<form" not in res.body


def test_applying_a_merge(authenticated_testapp, dbsession, admin_user):
    both = _tagged(dbsession, admin_user, "Both", {"alt", "neu"})
    only = _tagged(dbsession, admin_user, "Only", {"alt"})
    dbsession.flush()

    res = authenticated_testapp.post(
        "/admin/tags/apply", {"source": "alt", "target": "neu"}, status=303
    )

    assert "done=" in res.location
    assert both.tags == {"neu"}
    assert only.tags == {"neu"}


def test_applying_a_removal(authenticated_testapp, dbsession, admin_user):
    """Delete ignores whatever is in the name field."""
    todo = _tagged(dbsession, admin_user, "Junk", {"asdfgh", "keep"})
    dbsession.flush()

    authenticated_testapp.post(
        "/admin/tags/apply",
        {"source": "asdfgh", "target": "asdfgh", "action": "delete"},
        status=303,
    )

    assert todo.tags == {"keep"}


def test_renaming_without_a_name_is_refused(
    authenticated_testapp, dbsession, admin_user
):
    """Emptying the field is not how a tag is deleted any more."""
    todo = _tagged(dbsession, admin_user, "Keep me", {"alt"})
    dbsession.flush()

    authenticated_testapp.post(
        "/admin/tags/apply",
        {"source": "alt", "target": "", "action": "rename"},
        status=400,
    )

    assert todo.tags == {"alt"}


def test_renaming_to_the_same_name_does_nothing(
    authenticated_testapp, dbsession, admin_user
):
    todo = _tagged(dbsession, admin_user, "Bread", {"alt"})
    dbsession.flush()

    authenticated_testapp.post(
        "/admin/tags/apply",
        {"source": "alt", "target": "alt", "action": "rename"},
        status=303,
    )

    assert todo.tags == {"alt"}


def test_applying_with_sub_tags(authenticated_testapp, dbsession, admin_user):
    parent = _tagged(dbsession, admin_user, "Parent", {"Schulmaterial"})
    child = _tagged(dbsession, admin_user, "Child", {"Schulmaterial:Matti"})
    dbsession.flush()

    authenticated_testapp.post(
        "/admin/tags/apply",
        {
            "source": "Schulmaterial",
            "target": "schulmaterial",
            "children": "on",
            "action": "rename",
        },
        status=303,
    )

    assert parent.tags == {"schulmaterial"}
    assert child.tags == {"schulmaterial:Matti"}


def test_applying_without_a_tag_is_refused(authenticated_testapp):
    authenticated_testapp.post(
        "/admin/tags/apply", {"source": "", "action": "delete"}, status=400
    )


def test_tags_page_requires_admin(user_testapp):
    user_testapp.get("/admin/tags", status=403)
    user_testapp.post(
        "/admin/tags/apply", {"source": "x", "action": "delete"}, status=403
    )
