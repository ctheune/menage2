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
from sqlalchemy import select

from menage2.models.item import Item
from menage2.principals import (
    get_user_team_memberships,
    is_protocol_editor,
    item_visible_to_user,
)
from menage2.schemas import ItemUpdate, validate_request
from menage2.views.todo import files_of, reject_unknown_assignees

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

    validated = validate_request(request, ItemUpdate)
    if validated is None:
        return request.response

    clear_fields = validated.clear_fields

    if validated.text is not None:
        item.text = validated.text

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
        from menage2.models.item import ItemAttachment
        from menage2.views.attachment import _ext_for, _get_attachments_dir

        attachments_dir = _get_attachments_dir(request)
        existing_uuids = {att.uuid for att in item.attachments}
        to_keep = validated.attachments
        to_remove = existing_uuids - to_keep

        for uuid_str in to_remove:
            att = request.dbsession.execute(
                select(ItemAttachment).where(
                    ItemAttachment.item_id == item.id,
                    ItemAttachment.uuid == uuid_str,
                )
            ).scalar_one_or_none()
            if att:
                ext = _ext_for(att)
                for suffix in ("", "_thumb"):
                    path = attachments_dir / (uuid_str + suffix + ext)
                    if path.exists():
                        path.unlink()
                request.dbsession.delete(att)

    request.dbsession.flush()
    # The list beside the panel shows what was just changed, so it refetches.
    request.response.hx_trigger("item-updated")
    return _panel(request, item)
