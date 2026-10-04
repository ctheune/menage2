"""The one editor that a checklist, a checklist line and an ingredient share."""

import datetime

from menage2.models.item import TodoStatus
from menage2.models.protocol import Protocol, ProtocolItem
from menage2.models.recipe import Ingredient
from menage2.models.todo import Todo


def _now():
    return datetime.datetime.now(datetime.UTC)


def _panel(testapp, item_id, **kwargs):
    return testapp.get(f"/items/{item_id}/panel", **kwargs)


def test_an_ingredient_is_not_handed_to_anybody(
    authenticated_testapp, dbsession, admin_user
):
    """So it is offered tags and files, and no assignee field."""
    ingredient = Ingredient(description="Zimt")
    dbsession.add(ingredient)
    dbsession.flush()

    body = _panel(authenticated_testapp, ingredient.id).body.decode()

    assert "field-tags" in body
    assert "field-attachments" in body
    assert "field-assignees" not in body
    assert "field-title" in body


def test_a_checklist_is(authenticated_testapp, dbsession, admin_user):
    protocol = Protocol(title="Spring clean", owner_id=admin_user.id)
    dbsession.add(protocol)
    dbsession.flush()

    body = _panel(authenticated_testapp, protocol.id).body.decode()

    assert "field-assignees" in body
    assert "field-attachments" in body
    assert "field-title" in body
    # A checklist repeats; its lines do not.
    assert "field-recurrence" in body


def test_a_checklist_line_gets_the_same_editor(
    authenticated_testapp, dbsession, admin_user
):
    """Which is how a line comes to have files at all."""
    protocol = Protocol(title="Spring clean", owner_id=admin_user.id)
    dbsession.add(protocol)
    dbsession.flush()
    line = ProtocolItem(protocol_id=protocol.id, text="Windows", position=0)
    dbsession.add(line)
    dbsession.flush()

    body = _panel(authenticated_testapp, line.id).body.decode()

    assert "field-attachments" in body
    assert f"/items/{line.id}/attachments" in body
    assert "field-recurrence" not in body


def test_a_todo_keeps_its_own(authenticated_testapp, dbsession, admin_user):
    """It has a status, a due date and a repetition; this panel has none."""
    todo = Todo(text="Bins", status=TodoStatus.todo, created_at=_now())
    dbsession.add(todo)
    dbsession.flush()

    _panel(authenticated_testapp, todo.id, status=404)


def test_saving_writes_what_the_fields_say(
    authenticated_testapp, dbsession, admin_user
):
    ingredient = Ingredient(description="Zimt")
    dbsession.add(ingredient)
    dbsession.flush()

    authenticated_testapp.post_json(
        f"/items/{ingredient.id}",
        {"text": "Ceylon-Zimt", "note": "das gute", "tags": ["einkaufen:supermarkt"]},
        status=200,
    )

    dbsession.expire_all()
    assert ingredient.description == "Ceylon-Zimt"
    assert ingredient.note == "das gute"
    assert ingredient.tags == {"einkaufen:supermarkt"}


def test_saving_refuses_a_name_that_is_not_there(
    authenticated_testapp, dbsession, admin_user
):
    ingredient = Ingredient(description="Zimt")
    dbsession.add(ingredient)
    dbsession.flush()

    response = authenticated_testapp.post_json(
        f"/items/{ingredient.id}", {"text": "  "}, status=422
    )

    assert "It needs a name" in response.headers["HX-Trigger"]


def test_saving_refuses_an_assignee_that_is_nobody(
    authenticated_testapp, dbsession, admin_user
):
    protocol = Protocol(title="Spring clean", owner_id=admin_user.id)
    dbsession.add(protocol)
    dbsession.flush()

    response = authenticated_testapp.post_json(
        f"/items/{protocol.id}",
        {"text": "Spring clean", "assignees": ["nobdoy"]},
        status=422,
    )

    assert "nobdoy" in response.headers["HX-Trigger"]


def _as_regular(testapp):
    testapp.post(
        "/login", {"username": "user", "password": "user-password"}, status=303
    )


def test_somebody_who_may_not_edit_a_checklist_cannot_open_it(
    testapp, dbsession, admin_user, regular_user
):
    """Seeing a checklist and being allowed to change it are two questions."""
    protocol = Protocol(title="Admin's list", owner_id=admin_user.id)
    protocol.assignees = {regular_user.username}
    dbsession.add(protocol)
    dbsession.flush()

    _as_regular(testapp)

    assert _panel(testapp, protocol.id, expect_errors=True).status_int == 403


def test_a_stranger_gets_nothing(testapp, dbsession, admin_user, regular_user):
    protocol = Protocol(title="Admin's list", owner_id=admin_user.id)
    dbsession.add(protocol)
    dbsession.flush()

    _as_regular(testapp)

    assert _panel(testapp, protocol.id, expect_errors=True).status_int == 404
