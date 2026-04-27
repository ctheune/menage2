"""Integration tests for account management."""

from argon2 import PasswordHasher

_ph = PasswordHasher()


def test_account_page_authenticated(authenticated_testapp, admin_user):
    res = authenticated_testapp.get("/account", status=200)
    assert b"admin" in res.body.lower()


def test_account_unauthenticated_redirects(testapp, admin_user):
    res = testapp.get("/account", status="3*")
    assert "/login" in res.location


def test_change_password_page(authenticated_testapp):
    res = authenticated_testapp.get("/account/password", status=200)
    assert b"password" in res.body.lower()


def test_change_password_success(authenticated_testapp, admin_user):
    res = authenticated_testapp.post(
        "/account/password",
        {
            "current_password": "correct-password",
            "new_password": "new-strong-password",
            "confirm_password": "new-strong-password",
        },
        status=200,
    )
    assert b"success" in res.body.lower() or b"changed" in res.body.lower()
    # admin_user is in the shared session; the view updated it in-memory
    assert _ph.verify(admin_user.password_hash, "new-strong-password")


def test_change_password_wrong_current(authenticated_testapp):
    res = authenticated_testapp.post(
        "/account/password",
        {
            "current_password": "wrong",
            "new_password": "newpw",
            "confirm_password": "newpw",
        },
        status=200,
    )
    assert (
        b"incorrect" in res.body.lower()
        or b"wrong" in res.body.lower()
        or b"error" in res.body.lower()
    )


def test_change_password_mismatch(authenticated_testapp):
    res = authenticated_testapp.post(
        "/account/password",
        {
            "current_password": "correct-password",
            "new_password": "newpw1",
            "confirm_password": "newpw2",
        },
        status=200,
    )
    assert b"do not match" in res.body.lower() or b"mismatch" in res.body.lower()


def test_passkeys_page(authenticated_testapp):
    res = authenticated_testapp.get("/account/passkeys", status=200)
    assert b"passkey" in res.body.lower()
