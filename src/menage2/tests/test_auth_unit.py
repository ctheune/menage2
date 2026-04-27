"""Unit tests for auth logic (no DB interaction)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from menage2.security import PERM_ADMIN, PERM_AUTHENTICATED, SessionSecurityPolicy

_ph = PasswordHasher()


def _now():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def test_password_hash_and_verify():
    pw = "hunter2"
    h = _ph.hash(pw)
    assert _ph.verify(h, pw)


def test_password_hash_different_each_call():
    pw = "hunter2"
    assert _ph.hash(pw) != _ph.hash(pw)


def test_wrong_password_raises():
    h = _ph.hash("correct")
    with pytest.raises(VerifyMismatchError):
        _ph.verify(h, "wrong")


# ---------------------------------------------------------------------------
# SecurityPolicy
# ---------------------------------------------------------------------------


def _make_identity_request(session_user_id=None, db_user=None):
    """Request mock for testing identity() directly."""
    request = MagicMock()
    request.session = {}
    if session_user_id is not None:
        request.session["user_id"] = session_user_id
    request.dbsession.get.return_value = db_user
    return request


def _make_permits_request(identity):
    """Request mock for testing permits() - identity is already resolved."""
    request = MagicMock()
    request.identity = identity
    return request


def test_security_policy_no_session():
    policy = SessionSecurityPolicy()
    request = _make_identity_request()
    assert policy.identity(request) is None


def test_security_policy_with_valid_user():
    mock_user = MagicMock()
    mock_user.is_active = True
    policy = SessionSecurityPolicy()
    request = _make_identity_request(session_user_id=1, db_user=mock_user)
    assert policy.identity(request) is mock_user


def test_security_policy_inactive_user_returns_none():
    mock_user = MagicMock()
    mock_user.is_active = False
    policy = SessionSecurityPolicy()
    request = _make_identity_request(session_user_id=1, db_user=mock_user)
    assert policy.identity(request) is None


def test_security_policy_missing_user_returns_none():
    policy = SessionSecurityPolicy()
    request = _make_identity_request(session_user_id=999, db_user=None)
    assert policy.identity(request) is None


def test_permits_authenticated_for_active_user():
    mock_user = MagicMock()
    mock_user.is_active = True
    mock_user.is_admin = False

    policy = SessionSecurityPolicy()
    request = _make_permits_request(identity=mock_user)

    result = policy.permits(request, None, PERM_AUTHENTICATED)
    assert bool(result) is True


def test_permits_admin_for_admin_user():
    mock_user = MagicMock()
    mock_user.is_active = True
    mock_user.is_admin = True

    policy = SessionSecurityPolicy()
    request = _make_permits_request(identity=mock_user)

    result = policy.permits(request, None, PERM_ADMIN)
    assert bool(result) is True


def test_denies_admin_for_non_admin_user():
    mock_user = MagicMock()
    mock_user.is_active = True
    mock_user.is_admin = False

    policy = SessionSecurityPolicy()
    request = _make_permits_request(identity=mock_user)

    result = policy.permits(request, None, PERM_ADMIN)
    assert bool(result) is False


def test_denies_unauthenticated():
    policy = SessionSecurityPolicy()
    request = _make_permits_request(identity=None)

    result = policy.permits(request, None, PERM_AUTHENTICATED)
    assert bool(result) is False


# ---------------------------------------------------------------------------
# First-run tween
# ---------------------------------------------------------------------------


def test_first_run_tween_redirects_when_no_users():
    from menage2.tweens import first_run_tween_factory

    handler = MagicMock()
    tween = first_run_tween_factory(handler, None)

    request = MagicMock()
    request.path = "/todos"
    request.dbsession.query.return_value.count.return_value = 0
    request.route_url.return_value = "/setup"

    response = tween(request)
    assert response.location == "/setup"
    handler.assert_not_called()


def test_first_run_tween_passes_through_setup():
    from menage2.tweens import first_run_tween_factory

    handler = MagicMock(return_value="ok")
    tween = first_run_tween_factory(handler, None)

    request = MagicMock()
    request.path = "/setup"

    result = tween(request)
    assert result == "ok"
    handler.assert_called_once_with(request)


def test_first_run_tween_passes_through_login():
    from menage2.tweens import first_run_tween_factory

    handler = MagicMock(return_value="ok")
    tween = first_run_tween_factory(handler, None)

    request = MagicMock()
    request.path = "/login"

    result = tween(request)
    assert result == "ok"


def test_first_run_tween_passes_through_static():
    from menage2.tweens import first_run_tween_factory

    handler = MagicMock(return_value="ok")
    tween = first_run_tween_factory(handler, None)

    request = MagicMock()
    request.path = "/static/tailwind.css"

    result = tween(request)
    assert result == "ok"


def test_first_run_tween_passes_when_users_exist():
    from menage2.tweens import first_run_tween_factory

    handler = MagicMock(return_value="ok")
    tween = first_run_tween_factory(handler, None)

    request = MagicMock()
    request.path = "/todos"
    request.dbsession.query.return_value.count.return_value = 1

    result = tween(request)
    assert result == "ok"
    handler.assert_called_once_with(request)
