"""Editing anything that is an item.

A checklist, a checklist line and an ingredient all carry text, tags,
assignees, a note and files, so they are all edited through one panel and
saved through one endpoint. A checklist also repeats, which is the one
field it has that the others do not. A todo is not here: it has a status,
a due date and sometimes a checklist behind it, and its own panel says so.
"""

import json

from pyramid.httpexceptions import HTTPForbidden, HTTPNotFound
from pyramid.view import view_config

from menage2.models.item import Item
from menage2.principals import (
    get_user_team_memberships,
    is_protocol_editor,
    item_visible_to_user,
)
from menage2.schemas import (
    ItemUpdate,
    RecurringUpdate,
    validate_request,
    validation_error,
)
from menage2.views.protocol import rename_open_runs, set_protocol_recurrence
from menage2.views.todo import files_of, reject_unknown_assignees

#: An ingredient is not handed to anybody; the rest are.
_NO_ASSIGNEES = {"ingredient"}

#: Only a checklist repeats; its lines and its runs' lines do not.
_RECURRING = {"protocol"}

#: Kinds this panel edits. A todo has its own.
_EDITABLE = {"protocol", "protocol_item", "protocol_run_item", "ingredient"}


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
        "wants_assignees": item.kind not in _NO_ASSIGNEES,
        "wants_recurrence": item.kind in _RECURRING,
        "tags_json": json.dumps(sorted(item.tags)),
        "assignees_json": json.dumps(sorted(item.assignees)),
        "links_json": json.dumps(
            [
                {"label": t.label, "url": t.url}
                for t in sorted(item.links, key=lambda t: t.position)
            ]
        ),
        **files_of(request, item),
    }


@view_config(
    route_name="item_panel",
    request_method="GET",
    renderer="menage2:templates/item/panel.pt",
)
def item_panel(request):
    return _panel(request, _get_editable(request))


@view_config(
    route_name="item_update",
    request_method="POST",
    renderer="menage2:templates/item/panel.pt",
)
def item_update(request):
    """Save what the panel changed and hand it back, filled in again."""
    item = _get_editable(request)

    from sqlalchemy import delete as sqla_delete

    from menage2.models.item import ItemLink

    schema = RecurringUpdate if item.kind in _RECURRING else ItemUpdate
    validated = validate_request(request, schema)
    if validated is None:
        return request.response

    clear_fields = validated.clear_fields

    renamed = False
    if validated.text is not None:
        text = validated.text.strip()
        if not text:
            return validation_error(request, "It needs a name.")
        renamed = text != item.text
        item.text = text

    if "tags" in clear_fields:
        item.tags = set()
    elif validated.tags is not None:
        item.tags = validated.tags

    if item.kind not in _NO_ASSIGNEES:
        if "assignees" in clear_fields:
            item.assignees = set()
        elif validated.assignees is not None:
            rejected = reject_unknown_assignees(request, validated.assignees)
            if rejected is not None:
                return rejected
            item.assignees = validated.assignees

    if "note" in clear_fields:
        item.note = ""
    elif validated.note is not None:
        item.note = validated.note

    if "links" in clear_fields:
        request.dbsession.execute(
            sqla_delete(ItemLink).where(ItemLink.item_id == item.id)
        )
    elif validated.links is not None:
        request.dbsession.execute(
            sqla_delete(ItemLink).where(ItemLink.item_id == item.id)
        )

        for position, link_data in enumerate(validated.links):
            link = ItemLink(
                item_id=item.id,
                label=link_data.label,
                url=link_data.url,
                position=position,
            )
            request.dbsession.add(link)

    if validated.attachments is not None:
        from menage2.views.attachment import remove_attachment

        for att in list(item.attachments):
            if att.uuid not in validated.attachments:
                remove_attachment(request, att)

    if item.kind == "protocol":
        if renamed:
            rename_open_runs(request.dbsession, item)
        if isinstance(validated, RecurringUpdate):
            if "recurrence" in clear_fields:
                set_protocol_recurrence(item, None, request.dbsession)
            elif validated.recurrence is not None:
                set_protocol_recurrence(item, validated.recurrence, request.dbsession)

    request.dbsession.flush()
    # The list beside the panel shows what was just changed, so it refetches.
    request.response.hx_trigger("item-updated")
    return _panel(request, item)
