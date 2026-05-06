import datetime
import enum

from sqlalchemy import Column, Date, DateTime, Enum, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator

from .meta import Base


class TagSet(TypeDecorator):
    impl = ARRAY(Text)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return sorted(value) if value else []

    def process_result_value(self, value, dialect):
        return set(value) if value else set()


class LinkList(TypeDecorator):
    """Ordered PostgreSQL TEXT[] — preserves insertion order, returns list."""

    impl = ARRAY(Text)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return list(value) if value else []

    def process_result_value(self, value, dialect):
        return list(value) if value else []


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

    __tablename__ = "recurrence_rules"

    id = Column(Integer, primary_key=True)
    kind = Column(Enum(RecurrenceKind, name="recurrencekind"), nullable=False)
    interval_value = Column(Integer, nullable=False, default=1)
    interval_unit = Column(Enum(RecurrenceUnit, name="recurrenceunit"), nullable=False)
    weekday = Column(Integer, nullable=True)  # 0=Mon..6=Sun for "every <weekday>"
    month_day = Column(Integer, nullable=True)  # 1..31 for "every Nth"


class TodoLink(Base):
    """Structured storage for todo links, replacing the old '[label](url)' string format."""

    __tablename__ = "todo_links"

    id = Column(Integer, primary_key=True)
    todo_id = Column(
        Integer,
        ForeignKey("todos.id", ondelete="CASCADE"),
        nullable=False,
    )
    label = Column(Text, nullable=True)
    url = Column(Text, nullable=False)
    position = Column(Integer, nullable=False, default=0)

    todo = relationship("Todo", back_populates="links_rel")

    __table_args__ = (Index("ix_todo_links_todo_id", "todo_id"),)


class Todo(Base):
    __tablename__ = "todos"

    id = Column(Integer, primary_key=True)
    text = Column(Text, nullable=False)
    tags = Column(TagSet, nullable=False, server_default="{}")
    status = Column(
        Enum(TodoStatus, name="todostatus"),
        nullable=False,
        server_default="todo",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    done_at = Column(DateTime(timezone=True))
    on_hold_at = Column(DateTime(timezone=True))
    due_date = Column(Date)
    note = Column(Text)
    # Deprecated: Use TodoLink relationship instead. Kept for migration purposes.
    links = Column(LinkList, nullable=False, server_default="{}")

    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assignees = Column(TagSet, nullable=False, server_default="{}")

    recurrence_id = Column(Integer, ForeignKey("recurrence_rules.id"), nullable=True)
    recurred_from_id = Column(Integer, ForeignKey("todos.id"), nullable=True)

    # 1-to-1 link to a ProtocolRun. Set when this todo was spawned for a
    # protocol run (the user's calendar trigger). UNIQUE so each run has
    # exactly one todo.
    protocol_run_id = Column(
        Integer,
        ForeignKey("protocol_runs.id"),
        unique=True,
        nullable=True,
    )

    owner = relationship("User", foreign_keys=[owner_id])
    attachments = relationship(
        "TodoAttachment",
        back_populates="todo",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="TodoAttachment.created_at",
    )
    links_rel = relationship(
        "TodoLink",
        back_populates="todo",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="TodoLink.position",
    )
    recurrence = relationship("RecurrenceRule", lazy="joined")
    recurred_from = relationship(
        "Todo", remote_side="Todo.id", foreign_keys=[recurred_from_id]
    )
    protocol_run = relationship(
        "ProtocolRun",
        back_populates="todo",
        foreign_keys=[protocol_run_id],
        lazy="joined",
    )

    __table_args__ = (
        Index("ix_todos_due_date", "due_date"),
        Index("ix_todos_recurrence_id", "recurrence_id"),
        Index("ix_todos_owner_id", "owner_id"),
        Index("ix_todos_assignees", "assignees", postgresql_using="gin"),
    )


class TodoAttachment(Base):
    __tablename__ = "todo_attachments"

    id = Column(Integer, primary_key=True)
    todo_id = Column(
        Integer,
        ForeignKey("todos.id", ondelete="CASCADE"),
        nullable=False,
    )
    uuid = Column(Text, nullable=False, unique=True)
    original_filename = Column(Text, nullable=False)
    mimetype = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )

    todo = relationship("Todo", back_populates="attachments")

    __table_args__ = (Index("ix_todo_attachments_todo_id", "todo_id"),)
