import menage2
from menage2 import models
from menage2.views.notfound import notfound_view
from menage2.views.recipe import list_recipes


def test_list_recipes_success(app_request, dbsession):
    model = models.Recipe()
    model.title = "Gulasch"
    dbsession.add(model)
    dbsession.flush()

    info = list_recipes(app_request)
    assert app_request.response.status_int == 200
    assert info["recipes"][0].title == "Gulasch"


def test_list_recipes_empty_shows_add_button(authenticated_testapp):
    res = authenticated_testapp.get("/recipes", status=200)
    assert b"add_recipe" in res.body or b"Rezept" in res.body
    assert b"Neues Rezept" in res.body or b"Erstes Rezept" in res.body


def test_list_weeks_empty_shows_add_button(authenticated_testapp):
    res = authenticated_testapp.get("/weeks", status=200)
    assert b"Neue Woche" in res.body or b"Erste Woche" in res.body


def test_notfound_view(app_request):
    info = notfound_view(app_request)
    assert app_request.response.status_int == 404
    assert info == {}


def test_templates_only_name_routes_that_exist():
    """A template naming a route that is gone fails silently.

    `layout.pt` decides which nav item is highlighted by asking whether the
    matched route is in a tuple of names. A name that no longer exists
    simply never matches, so the nav quietly stops lighting up and nothing
    says so -- nine of them had accumulated that way, including one for a
    route that was replaced by the tag picker.
    """
    import pathlib
    import re

    root = pathlib.Path(menage2.__file__).parent
    defined = set(
        re.findall(
            r'add_route\(\s*["\']([^"\']+)["\']', (root / "routes.py").read_text()
        )
    )

    named: dict[str, set[str]] = {}
    for template in (root / "templates").rglob("*.pt"):
        source = template.read_text()
        used = set(re.findall(r'route_(?:url|path)\(\s*["\']([^"\']+)["\']', source))
        for group in re.findall(r"route_name in \(([^)]*)\)", source):
            used.update(re.findall(r"'([^']+)'", group))
        missing = used - defined
        if missing:
            named[str(template.relative_to(root))] = missing

    assert named == {}
