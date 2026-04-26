def test_list__success(authenticated_testapp):
    res = authenticated_testapp.get("/todos", status=200)
    assert res.body


def test_notfound(authenticated_testapp):
    res = authenticated_testapp.get("/badurl", status=404)
    assert res.status_code == 404


def test_unauthenticated_redirects_to_login(testapp, admin_user):
    """Any protected page without a session redirects to login."""
    res = testapp.get("/todos", status="3*")
    assert "/login" in res.location
