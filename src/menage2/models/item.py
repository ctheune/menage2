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

from sqlalchemy import Column, Date, DateTime, Enum, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from .meta import Base


class TagSet(TypeDecorator):
    impl = ARRAY(Text)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return sorted(value) if value else []

    def process_result_value(self, value, dialect):
        return set(value) if value else set()


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
      ``weekday`` (0=Mon..6=Sun) anchors weekly rules ("every Wednesday").
      ``month_day`` anchors monthly rules ("every 15th").
    """

    __tablename__: str = "recurrence_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind = Column(Enum(RecurrenceKind, name="recurrencekind"), nullable=False)
    interval_value = Column(Integer, nullable=False, default=1)
    interval_unit = Column(Enum(RecurrenceUnit, name="recurrenceunit"), nullable=False)
    weekday = Column(Integer, nullable=True)  # 0=Mon..6=Sun for "every <weekday>"
    month_day = Column(Integer, nullable=True)  # 1..31 for "every Nth"

    @property
    def label(self) -> str:
        """Human-readable rule ("every Wednesday") — the `*` marker's payload."""
        # Deferred: menage2.recurrence imports this module.
        from menage2.recurrence import rule_to_spec

        return rule_to_spec(self).label()


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)

    text = Column(Text, nullable=False)
    note = Column(Text)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    due_date = Column(Date)
    status = Column(Enum(TodoStatus, name="todostatus"), nullable=True)
    done_at = Column(DateTime(timezone=True))
    on_hold_at = Column(DateTime(timezone=True))

    recurrence_id = Column(Integer, ForeignKey("recurrence_rules.id"), nullable=True)

    owner = relationship("User", foreign_keys=[owner_id])
    recurrence = relationship("RecurrenceRule", lazy="joined")

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

    __mapper_args__ = {
        "polymorphic_on": kind,
        "polymorphic_identity": "item",
    }
