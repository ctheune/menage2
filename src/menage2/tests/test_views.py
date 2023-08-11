from menage2 import models
from menage2.views.recipe import list_recipes
from menage2.views.notfound import notfound_view


def test_list_recipes_success(app_request, dbsession):
    model = models.Recipe(id=1, title="Gulasch")
    dbsession.add(model)
    dbsession.flush()

    info = list_recipes(app_request)
    assert app_request.response.status_int == 200
    assert info["recipes"][0].title == "Gulasch"


def test_notfound_view(app_request):
    info = notfound_view(app_request)
    assert app_request.response.status_int == 404
    assert info == {}
