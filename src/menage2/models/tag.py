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

``Item.tags`` is a ``NameSet`` over these rows; see models/nameset.py for
how a set of strings and a set of rows stay the same thing.
"""

from sqlalchemy import Column, ForeignKey, Index, Integer, Table, Text, event, select
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

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


@event.listens_for(Session, "after_commit")
@event.listens_for(Session, "after_rollback")
def _forget_tags_seen(session):
    """The cached rows belong to the transaction that made them."""
    session.info.pop("tags_seen", None)
