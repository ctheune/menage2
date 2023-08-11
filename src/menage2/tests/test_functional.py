from menage2 import models


def test_list__success(testapp, dbsession):
    model = models.Recipe(title="Gulasch")
    dbsession.add(model)
    dbsession.flush()

    res = testapp.get("/", status=200)
    assert res.body


def test_notfound(testapp):
    res = testapp.get("/badurl", status=404)
    assert res.status_code == 404
