"""Integration tests for authentication flows (no browser required)."""

from datetime import datetime, timedelta, timezone

import pytest
from argon2 import PasswordHasher

from menage2 import SETUP_TOKEN_KEY
from menage2.models.config import ConfigItem
from menage2.models.user import User

_ph = PasswordHasher()


def _now():
    return datetime.now(timezone.utc)


def _seed_setup_token(dbsession, token="test-setup-token"):
    item = dbsession.get(ConfigItem, SETUP_TOKEN_KEY)
    if item:
        item.value = token
    else:
        dbsession.add(ConfigItem(key=SETUP_TOKEN_KEY, value=token))
    dbsession.flush()
    return token


# ---------------------------------------------------------------------------
# Setup (first-run)
# ---------------------------------------------------------------------------


def test_setup_page_shows_token_entry_when_no_token_param(testapp, dbsession):
    _seed_setup_token(dbsession)
    res = testapp.get("/setup", status=200)
    assert b"token" in res.body.lower()


def test_setup_page_shows_form_with_valid_token(testapp, dbsession):
    token = _seed_setup_token(dbsession)
    res = testapp.get(f"/setup?token={token}", status=200)
    assert b"Create Admin Account" in res.body


def test_setup_page_rejects_invalid_token(testapp, dbsession):
    _seed_setup_token(dbsession)
    res = testapp.get("/setup?token=wrongtoken", status=200)
    assert b"Invalid" in res.body


def test_setup_redirects_when_users_exist(testapp, admin_user):
    res = testapp.get("/setup", status="3*")
    assert "todos" in res.location


def test_setup_post_creates_admin(testapp, dbsession):
    token = _seed_setup_token(dbsession)
    res = testapp.post(
        "/setup",
        {
            "token": token,
            "username": "founder",
            "real_name": "Founder",
            "email": "founder@example.com",
            "password": "strongpassword",
            "confirm_password": "strongpassword",
        },
        status=303,
    )
    assert res.location
    # Token should be destroyed
    assert dbsession.get(ConfigItem, SETUP_TOKEN_KEY) is None


def test_setup_post_rejects_invalid_token(testapp, dbsession):
    _seed_setup_token(dbsession)
    res = testapp.post(
        "/setup",
        {
            "token": "wrongtoken",
            "username": "founder",
            "real_name": "Founder",
            "email": "founder@example.com",
            "password": "strongpassword",
            "confirm_password": "strongpassword",
        },
        status=200,
    )
    assert b"Invalid" in res.body


def test_setup_post_validates_required_fields(testapp, dbsession):
    token = _seed_setup_token(dbsession)
    res = testapp.post(
        "/setup",
        {
            "token": token,
            "username": "",
            "real_name": "",
            "email": "",
            "password": "",
            "confirm_password": "",
        },
        status=200,
    )
    assert b"required" in res.body.lower()


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


def test_login_page_renders(testapp, admin_user):
    res = testapp.get("/login", status=200)
    assert b"login" in res.body.lower() or b"sign in" in res.body.lower()


def test_login_success_redirects(testapp, admin_user):
    res = testapp.post(
        "/login",
        {
            "username": "admin",
            "password": "correct-password",
        },
        status=303,
    )
    assert res.location.endswith("/todos") or "todos" in res.location


def test_login_wrong_password_shows_error(testapp, admin_user):
    res = testapp.post(
        "/login",
        {
            "username": "admin",
            "password": "wrong-password",
        },
        status=200,
    )
    assert b"Invalid" in res.body


def test_login_unknown_user_shows_error(testapp, admin_user):
    res = testapp.post(
        "/login",
        {
            "username": "nobody",
            "password": "anything",
        },
        status=200,
    )
    assert b"Invalid" in res.body


def test_login_inactive_user_rejected(testapp, dbsession):
    user = User(
        username="inactive",
        real_name="Inactive",
        email="inactive@example.com",
        password_hash=_ph.hash("pw"),
        is_admin=False,
        is_active=False,
        created_at=_now(),
    )
    dbsession.add(user)
    dbsession.flush()

    res = testapp.post(
        "/login",
        {
            "username": "inactive",
            "password": "pw",
        },
        status=200,
    )
    assert b"Invalid" in res.body


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


def test_logout_clears_session(authenticated_testapp):
    authenticated_testapp.post("/logout", status=303)
    # After logout, accessing a protected page redirects to login
    res = authenticated_testapp.get("/todos", status="3*")
    assert "/login" in res.location


# ---------------------------------------------------------------------------
# Protected route redirection
# ---------------------------------------------------------------------------


def test_protected_route_redirects_unauthenticated(testapp, admin_user):
    res = testapp.get("/todos", status="3*")
    assert "/login" in res.location


def test_admin_route_denies_regular_user(user_testapp):
    user_testapp.get("/admin/users", status=403)


# ---------------------------------------------------------------------------
# Forgot password
# ---------------------------------------------------------------------------


def test_forgot_password_page_renders(testapp, admin_user):
    res = testapp.get("/forgot-password", status=200)
    assert b"email" in res.body.lower()


def test_forgot_password_always_succeeds(testapp, admin_user):
    """Should show success even for non-existent email (prevent enumeration)."""
    res = testapp.post(
        "/forgot-password", {"email": "nonexistent@example.com"}, status=200
    )
    assert b"sent" in res.body.lower() or b"check" in res.body.lower()


def test_forgot_password_sets_token(testapp, admin_user):
    testapp.post("/forgot-password", {"email": "admin@example.com"}, status=200)
    # admin_user is in the shared session; check the in-memory updated value
    assert admin_user.password_reset_token is not None
    assert admin_user.password_reset_token_expires_at > _now()


# ---------------------------------------------------------------------------
# Reset password
# ---------------------------------------------------------------------------


def test_reset_password_invalid_token(testapp, admin_user):
    res = testapp.get("/reset-password/invalidtoken", status=200)
    assert b"invalid" in res.body.lower() or b"expired" in res.body.lower()


def test_reset_password_valid_token(testapp, admin_user, dbsession):
    token = "validtoken123"
    admin_user.password_reset_token = token
    admin_user.password_reset_token_expires_at = _now() + timedelta(hours=1)
    dbsession.flush()

    res = testapp.get(f"/reset-password/{token}", status=200)
    assert b"new password" in res.body.lower() or b"password" in res.body.lower()


def test_reset_password_expired_token(testapp, admin_user, dbsession):
    token = "expiredtoken123"
    admin_user.password_reset_token = token
    admin_user.password_reset_token_expires_at = _now() - timedelta(hours=1)
    dbsession.flush()

    res = testapp.get(f"/reset-password/{token}", status=200)
    assert b"invalid" in res.body.lower() or b"expired" in res.body.lower()


def test_reset_password_post_changes_password(testapp, admin_user, dbsession):
    token = "resettoken456"
    admin_user.password_reset_token = token
    admin_user.password_reset_token_expires_at = _now() + timedelta(hours=1)
    dbsession.flush()

    res = testapp.post(
        f"/reset-password/{token}",
        {
            "password": "new-strong-password",
            "confirm_password": "new-strong-password",
        },
        status=303,
    )
    assert "login" in res.location
    # admin_user is in the shared session; check in-memory values
    assert admin_user.password_reset_token is None
    assert _ph.verify(admin_user.password_hash, "new-strong-password")
