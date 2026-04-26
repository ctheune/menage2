"""Integration tests for admin user management."""


def test_list_users(authenticated_testapp, admin_user):
    res = authenticated_testapp.get("/admin/users", status=200)
    assert b"admin" in res.body.lower()


def test_create_user(authenticated_testapp):
    res = authenticated_testapp.post("/admin/users/new", {
        "username": "newuser",
        "real_name": "New User",
        "email": "new@example.com",
        "password": "somepassword",
    }, status=303)
    assert "admin/users" in res.location


def test_create_user_duplicate_username(authenticated_testapp, admin_user):
    res = authenticated_testapp.post("/admin/users/new", {
        "username": "admin",
        "real_name": "Dup",
        "email": "dup@example.com",
        "password": "pw",
    }, status=200)
    assert b"already" in res.body.lower()


def test_edit_user(authenticated_testapp, regular_user):
    res = authenticated_testapp.post(f"/admin/users/{regular_user.id}/edit", {
        "real_name": "Updated Name",
        "email": "updated@example.com",
        "is_active": "1",
    }, status=303)
    assert "admin/users" in res.location


def test_deactivate_user(authenticated_testapp, regular_user):
    res = authenticated_testapp.post(f"/admin/users/{regular_user.id}/deactivate", status=303)
    assert "admin/users" in res.location


def test_cannot_deactivate_self(authenticated_testapp, admin_user):
    authenticated_testapp.post(f"/admin/users/{admin_user.id}/deactivate", status=400)


def test_delete_user(authenticated_testapp, regular_user):
    res = authenticated_testapp.post(f"/admin/users/{regular_user.id}/delete", status=303)
    assert "admin/users" in res.location


def test_cannot_delete_self(authenticated_testapp, admin_user):
    authenticated_testapp.post(f"/admin/users/{admin_user.id}/delete", status=400)


def test_cannot_delete_last_admin(authenticated_testapp, admin_user):
    authenticated_testapp.post(f"/admin/users/{admin_user.id}/delete", status=400)


def test_dashboard_token_view(authenticated_testapp):
    res = authenticated_testapp.get("/admin/dashboard-token", status=200)
    assert b"dashboard" in res.body.lower()


def test_dashboard_token_reset(authenticated_testapp):
    res = authenticated_testapp.post("/admin/dashboard-token", status=200)
    assert b"dashboard" in res.body.lower()
