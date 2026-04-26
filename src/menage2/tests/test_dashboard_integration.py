"""Integration tests for the secret-token dashboard."""
import secrets

from menage2.models.config import ConfigItem
from menage2.views.auth import DASHBOARD_TOKEN_KEY


def test_dashboard_valid_token(testapp, admin_user, dbsession):
    """Dashboard is accessible without login if the correct token is in the URL."""
    token = secrets.token_urlsafe(64)
    dbsession.add(ConfigItem(key=DASHBOARD_TOKEN_KEY, value=token))
    dbsession.flush()

    res = testapp.get(f"/dashboard/{token}", status=200)
    assert res.status_code == 200


def test_dashboard_invalid_token(testapp, admin_user, dbsession):
    """Wrong token returns 403."""
    token = secrets.token_urlsafe(64)
    dbsession.add(ConfigItem(key=DASHBOARD_TOKEN_KEY, value=token))
    dbsession.flush()

    testapp.get("/dashboard/wrongtoken", status=403)


def test_dashboard_no_token_configured(testapp, admin_user, dbsession):
    """When no token exists in config, returns 404."""
    testapp.get("/dashboard/anytoken", status=404)
