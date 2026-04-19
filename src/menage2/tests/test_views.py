from menage2 import models
from menage2.views.recipe import list_recipes
from menage2.views.notfound import notfound_view


def test_list_recipes_success(app_request, dbsession):
    model = models.Recipe()
    model.title = "Gulasch"
    dbsession.add(model)
    dbsession.flush()

    info = list_recipes(app_request)
    assert app_request.response.status_int == 200
    assert info["recipes"][0].title == "Gulasch"


def test_list_recipes_empty_shows_add_button(testapp):
    res = testapp.get("/recipes", status=200)
    assert b"add_recipe" in res.body or b"Rezept" in res.body
    assert b"Neues Rezept" in res.body or b"Erstes Rezept" in res.body


def test_list_weeks_empty_shows_add_button(testapp):
    res = testapp.get("/weeks", status=200)
    assert b"Neue Woche" in res.body or b"Erste Woche" in res.body


def test_notfound_view(app_request):
    info = notfound_view(app_request)
    assert app_request.response.status_int == 404
    assert info == {}
