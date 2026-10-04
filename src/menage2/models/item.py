"""The thing a todo, a checklist and an ingredient all are underneath.

Five kinds of record in this application carry the same handful of
attributes -- some text, a note, tags, assignees, who owns it -- each in its
own columns and each with its own editor. That is why attachments and links
exist on todos and nowhere else, and why finding out which tags are in use
meant reading four array columns and one comma-separated string.

``Item`` owns what they share. Each kind is a joined-table subtype: its own
table keeps only what is genuinely its own, and its primary key is also a
foreign key to this one. ``kind`` says which, and is what makes a query for
tasks a query for tasks rather than for everything.

``status`` is nullable on purpose. A checklist template is not "to do" and
an ingredient is not "done", and giving them a default status would mean a
query that forgot its ``kind`` filter quietly returned three hundred
ingredients as tasks. Left NULL, ``status == todo`` excludes them by itself.
"""

import datetime
import enum
from typing import ClassVar

from sqlalchemy import (
    ARRAY,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .assignee import item_assignees, principal_named
from .meta import Base
from .nameset import NameSet
from .tag import item_tags, tag_named


class TodoStatus(enum.Enum):
    todo = "todo"
    done = "done"
    on_hold = "on_hold"


class RecurrenceKind(enum.Enum):
    after = "after"
    every = "every"


class RecurrenceUnit(enum.Enum):
    day = "day"
    week = "week"
    month = "month"
    year = "year"


class RecurrenceRule(Base):
    """A repetition rule shared by an item and every instance spawned from it.

    Two ``kind`` semantics:

    * ``after`` — a spawn is created when the previous instance is marked done,
      anchored ``interval_value × interval_unit`` after the completion date.
    * ``every`` — instances fire on a fixed cadence regardless of completion.
      ``weekdays`` (0=Mon..6=Sun) anchors weekly rules ("every Wednesday",
      "every Monday, Friday"). ``month_day`` anchors monthly rules ("every
      15th"), and with ``month`` yearly ones ("every October 31st").
    """

    __tablename__: str = "recurrence_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[RecurrenceKind] = mapped_column(
        Enum(RecurrenceKind, name="recurrencekind"), nullable=False
    )
    interval_value: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    interval_unit: Mapped[RecurrenceUnit] = mapped_column(
        Enum(RecurrenceUnit, name="recurrenceunit"), nullable=False
    )
    #: 0=Mon..6=Sun, sorted, for "every <weekday>[, <weekday>...]"
    weekdays: Mapped[list[int] | None] = mapped_column(ARRAY(Integer))
    month_day: Mapped[int | None] = mapped_column(Integer)  # 1..31: "every Nth"
    month: Mapped[int | None] = mapped_column(Integer)  # 1..12: "every <month> <Nth>"

    @property
    def label(self) -> str:
        """Human-readable rule ("every Wednesday") — the `*` marker's payload."""
        # Deferred: menage2.recurrence imports this module.
        from menage2.recurrence import rule_to_spec

        return rule_to_spec(self).label()


class Item(Base):
    __tablename__ = "items"

    __table_args__ = (
        Index("ix_items_kind", "kind"),
        Index("ix_items_owner_id", "owner_id"),
        Index("ix_items_recurrence_id", "recurrence_id"),
        Index(
            "ix_items_status_due",
            "status",
            "due_date",
            postgresql_where=Column("status").isnot(None),
        ),
    )

    __mapper_args__: ClassVar = {
        "polymorphic_on": "kind",
        "polymorphic_identity": "item",
    }

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)

    text: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(Text)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.UTC),
    )
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    owner = relationship("User", foreign_keys=[owner_id])

    due_date = Column(Date)
    status = Column(Enum(TodoStatus, name="todostatus"), nullable=True)
    done_at = Column(DateTime(timezone=True))
    on_hold_at = Column(DateTime(timezone=True))

    recurrence_id = Column(Integer, ForeignKey("recurrence_rules.id"), nullable=True)
    recurrence = relationship("RecurrenceRule", lazy="joined")

    #: The rows. `tags` below is the set of strings everything else speaks.
    #: selectin, because the task list reads the tags of every row it shows.
    tag_links = relationship(
        "Tag",
        secondary=item_tags,
        back_populates="items",
        collection_class=set,
        lazy="selectin",
    )

    assignee_links = relationship(
        "Principal",
        secondary=item_assignees,
        collection_class=set,
        lazy="selectin",
    )

    links = relationship(
        "ItemLink",
        back_populates="item",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="ItemLink.position",
    )
    attachments = relationship(
        "ItemAttachment",
        back_populates="item",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="ItemAttachment.created_at",
    )

    #: Both are sets of strings in both directions; the rows are underneath.
    #: A tag is made the first time it is used. A principal has to exist,
    #: so an item cannot be assigned to somebody who is not there.
    tags = NameSet("tag_links", tag_named)
    assignees = NameSet("assignee_links", principal_named)

    @classmethod
    def from_item(cls, item: "Item", **kw):
        """A new item of this kind carrying what `item` says.

        Text, note, tags, assignees, links and files -- what every kind has.
        Links and files are copied, not handed over: a row belongs to one
        item, so passing the source's own rows would move them off it. A
        copied file shares the stored image, which is only deleted once no
        item refers to it any more (`views.attachment.remove_attachment`).

        Anything in `kw` replaces what was copied.
        """
        values = {
            "text": item.text,
            "note": item.note,
            "tags": set(item.tags),
            "assignees": set(item.assignees),
            "links": [
                ItemLink(label=link.label, url=link.url, position=link.position)
                for link in item.links
            ],
            "attachments": [
                ItemAttachment(
                    uuid=att.uuid,
                    original_filename=att.original_filename,
                    mimetype=att.mimetype,
                    created_at=att.created_at,
                )
                for att in item.attachments
            ],
        }
        values.update(kw)
        return cls(**values)


class ItemLink(Base):
    """A link on an item. Ordered, because the order was chosen."""

    __tablename__ = "item_links"

    id = Column(Integer, primary_key=True)
    item_id = Column(
        Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False
    )
    label = Column(Text, nullable=True)
    url = Column(Text, nullable=False)
    position = Column(Integer, nullable=False, default=0)

    item = relationship("Item", back_populates="links")

    __table_args__ = (Index("ix_item_links_item_id", "item_id"),)


class ItemAttachment(Base):
    """A file on an item -- a photo of the packaging, a scan, a receipt."""

    __tablename__ = "item_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False
    )
    uuid: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    mimetype: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.UTC),
    )

    item = relationship("Item", back_populates="attachments")

    __table_args__ = (
        Index("ix_item_attachments_item_id", "item_id"),
        Index("ix_item_attachments_uuid", "uuid"),
    )
