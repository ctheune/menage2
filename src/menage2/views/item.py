"""Editing anything that is an item.

A checklist, a checklist line and an ingredient all carry text, tags,
assignees, a note and files, so they are all edited through one panel and
saved through one endpoint. A todo is not here: it has a status, a due
date, a repetition and sometimes a checklist behind it, and its own panel
says so.
"""

import json

from pyramid.httpexceptions import HTTPForbidden, HTTPNotFound
from pyramid.view import view_config

from menage2.models.item import Item
from menage2.principals import (
    get_user_team_memberships,
    is_protocol_editor,
    item_visible_to_user,
    unknown_principals,
)
from menage2.views.todo import _validation_error, files_of

#: What the text field is called, per kind. A checklist's text is its
#: title and an ingredient's is what it is called; neither reads as "text".
_TEXT_LABEL = {
    "protocol": "Title",
    "protocol_item": "Text",
    "protocol_run_item": "Text",
    "ingredient": "Name",
}

#: An ingredient is not handed to anybody; the rest are.
_NO_ASSIGNEES = {"ingredient"}

#: Kinds this panel edits. A todo has its own.
_EDITABLE = set(_TEXT_LABEL)


def _protocol_behind(item):
    """The checklist that decides who may edit `item`, if one does."""
    if item.kind == "protocol":
        return item
    if item.kind == "protocol_item":
        return item.protocol
    if item.kind == "protocol_run_item":
        return item.run.protocol if item.run else None
    return None


def _get_editable(request) -> Item:
    """The item, if this user may see it and it is one this panel edits."""
    user = request.identity
    if user is None:
        raise HTTPNotFound()
    item = request.dbsession.get(Item, int(request.matchdict["id"]))
    if item is None or item.kind not in _EDITABLE:
        raise HTTPNotFound()
    memberships = get_user_team_memberships(request.dbsession, user)
    if not item_visible_to_user(item, user, memberships):
        raise HTTPNotFound()
    protocol = _protocol_behind(item)
    if protocol is not None and not is_protocol_editor(user, protocol, memberships):
        # Seeing a checklist and being allowed to change it are different
        # questions, and this is the second one.
        raise HTTPForbidden()
    return item


def _panel(request, item) -> dict:
    return {
        "item": item,
        "text_label": _TEXT_LABEL[item.kind],
        "wants_assignees": item.kind not in _NO_ASSIGNEES,
        "tags_json": json.dumps(sorted(item.tags)),
        "assignees_json": json.dumps(sorted(item.assignees)),
        **files_of(request, item),
    }


@view_config(
    route_name="item_panel",
    request_method="GET",
    renderer="menage2:templates/_item_panel.pt",
)
def item_panel(request):
    return _panel(request, _get_editable(request))


@view_config(
    route_name="item_update",
    request_method="POST",
    renderer="menage2:templates/_item_panel.pt",
)
def item_update(request):
    """Save what the panel changed and hand it back, filled in again."""
    item = _get_editable(request)
    cleared = request.params.getall("clear_fields[]")

    text = request.params.get("text", "").strip()
    if not text:
        return _validation_error(request, "It needs a name.")
    item.text = text

    item.note = request.params.get("note", "").strip() or None
    item.tags = set() if "tags" in cleared else set(request.params.getall("tags[]"))

    if item.kind not in _NO_ASSIGNEES:
        assignees = (
            set()
            if "assignees" in cleared
            else set(request.params.getall("assignees[]"))
        )
        unknown = sorted(unknown_principals(request.dbsession, assignees))
        if unknown:
            return _validation_error(request, f"No user or team called @{unknown[0]}.")
        item.assignees = assignees

    request.dbsession.flush()
    # The list beside the panel shows what was just changed, so it refetches.
    request.response.hx_trigger("item-updated")
    return _panel(request, item)
