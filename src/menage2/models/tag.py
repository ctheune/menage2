"""Tags, as rows rather than as text repeated wherever it is used.

A tag used to exist only because something spelled it. Four array columns
and one comma-separated string held the whole vocabulary between them, so
answering "which tags are there" meant reading all five and merging in
Python, and renaming one meant rewriting every row that carried it.

Now a tag is a row and carrying one is a row in `item_tags`. The hierarchy
stays in the name -- `einkaufen:supermarkt` is one tag, not two -- because
that is what the marker language types and what the tag tree reads.

``Item.tags`` is still a ``set[str]`` in both directions. That is
deliberate: every rule about tags in this application is written in terms
of sets of strings, from the tag tree to the marker formatter to the
templates, and none of it had to change. What changed is where the strings
are kept.

Setting tags on an item that is not in a session yet -- ``Todo(text=...,
tags={"garden"})`` -- cannot look a tag up, so the names are held on the
instance and resolved when the session next flushes. Reading them back
before that returns what was set, so the buffer is invisible.
"""

from sqlalchemy import Column, ForeignKey, Index, Integer, Table, Text, event, select
from sqlalchemy.orm import Mapped, Session, mapped_column, object_session, relationship

from .meta import Base

#: What an item carries. Indexed the other way round too: renaming a tag
#: wants every item carrying it, which is the direction the primary key
#: cannot answer.
item_tags = Table(
    "item_tags",
    Base.metadata,
    Column(
        "item_id",
        Integer,
        ForeignKey("items.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        Integer,
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Index("ix_item_tags_tag_id", "tag_id"),
)

#: Where a pending set of names waits on an instance with no session.
_PENDING = "_tags_pending"


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    #: The whole `:`-separated path, as typed.
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    items = relationship("Item", secondary=item_tags, back_populates="tag_links")

    def __repr__(self) -> str:
        return f"<Tag {self.name!r}>"


def tag_named(session: Session, name: str) -> Tag:
    """The row for `name`, making it if this is the first time it is used.

    Cached per session, because two items given the same new tag in one
    request would otherwise each make a row and collide on the unique index.
    """
    cache = session.info.setdefault("tags_seen", {})
    tag = cache.get(name)
    if tag is not None:
        return tag
    with session.no_autoflush:
        tag = session.execute(select(Tag).where(Tag.name == name)).scalar_one_or_none()
    if tag is None:
        tag = Tag(name=name)
        session.add(tag)
    cache[name] = tag
    return tag


def resolve(item) -> None:
    """Turn the names waiting on `item` into the rows it should carry."""
    names = item.__dict__.pop(_PENDING, None)
    if names is None:
        return
    session = object_session(item)
    if session is None:  # pragma: no cover -- only reachable mid-detach
        item.__dict__[_PENDING] = names
        return
    wanted = {tag_named(session, name) for name in names}
    current = set(item.tag_links)
    for gone in current - wanted:
        item.tag_links.remove(gone)
    for added in wanted - current:
        item.tag_links.add(added)


def get_tags(item) -> set[str]:
    pending = item.__dict__.get(_PENDING)
    if pending is not None:
        return set(pending)
    return {tag.name for tag in item.tag_links}


def set_tags(item, names) -> None:
    if isinstance(names, str):
        # A string is iterable, so this would otherwise quietly become one
        # tag per letter. It was a comma-separated string on ingredients
        # until recently, which is exactly who would try it.
        raise TypeError(f"tags is a set of names, not one string: {names!r}")
    item.__dict__[_PENDING] = {str(name) for name in (names or ())}
    if object_session(item) is not None:
        resolve(item)


@event.listens_for(Session, "before_flush")
def _resolve_pending_tags(session, flush_context, instances):
    """Give every item waiting on a session the rows it asked for."""
    for item in list(session.new) + list(session.dirty):
        if _PENDING in item.__dict__:
            resolve(item)


@event.listens_for(Session, "after_commit")
@event.listens_for(Session, "after_rollback")
def _forget_tags_seen(session):
    """The cached rows belong to the transaction that made them."""
    session.info.pop("tags_seen", None)
