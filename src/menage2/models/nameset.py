"""A ``set[str]`` view over a relationship to rows that have names.

Tags and assignees are both sets of names in every rule this application
has: the tag tree, the marker language, the visibility filters and the
templates all read them that way, and hundreds of tests write them that
way. Underneath they are now rows, joined to an item through a link table.

This is what keeps both true at once. Reading gives the names, writing
takes them, and what turns a name into a row is passed in -- a tag is made
on first use, a principal has to exist already.

Names given to an item that is not in a session yet -- ``Todo(text=...,
tags={"garden"})`` -- cannot be looked up, so they wait on the instance and
are resolved when the session next flushes. Reading them back in the
meantime returns what was set, so the wait is invisible.
"""

from typing import Any, Self, overload

from sqlalchemy import event
from sqlalchemy.orm import Session, object_session


class NameSet:
    """Descriptor: `item.tags` is a set of strings over `item.tag_links`."""

    def __init__(self, collection: str, lookup):
        #: The relationship holding the rows.
        self.collection = collection
        #: (session, name) -> row. May refuse a name that names nothing.
        self.lookup = lookup

    def __set_name__(self, owner, name: str) -> None:
        self.field = name
        self.pending = f"_{name}_pending"

    @overload
    def __get__(self, item: None, owner: Any = None) -> Self: ...

    @overload
    def __get__(self, item: object, owner: Any = None) -> set[str]: ...

    def __get__(self, item, owner=None):
        if item is None:
            return self
        waiting = item.__dict__.get(self.pending)
        if waiting is not None:
            return set(waiting)
        return {row.name for row in getattr(item, self.collection)}

    def __set__(self, item, names) -> None:
        if isinstance(names, str):
            # A string is iterable, so this would otherwise quietly become
            # one name per letter.
            raise TypeError(
                f"{self.field} is a set of names, not one string: {names!r}"
            )
        item.__dict__[self.pending] = {str(name) for name in (names or ())}
        if object_session(item) is not None:
            self.resolve(item)

    def resolve(self, item) -> None:
        """Turn the names waiting on `item` into the rows it should carry."""
        names = item.__dict__.pop(self.pending, None)
        if names is None:
            return
        session = object_session(item)
        if session is None:  # pragma: no cover -- only mid-detach
            item.__dict__[self.pending] = names
            return
        links = getattr(item, self.collection)
        wanted = {self.lookup(session, name) for name in names}
        for gone in set(links) - wanted:
            links.remove(gone)
        for added in wanted - set(links):
            links.add(added)


def _namesets(item):
    for attribute in type(item).__mro__:
        for value in vars(attribute).values():
            if isinstance(value, NameSet):
                yield value


@event.listens_for(Session, "before_flush")
def _resolve_waiting_names(session, flush_context, instances):
    """Give every item waiting on a session the rows it asked for."""
    for item in list(session.new) + list(session.dirty):
        for nameset in _namesets(item):
            if nameset.pending in item.__dict__:
                nameset.resolve(item)
