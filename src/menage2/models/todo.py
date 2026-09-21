import datetime

from sqlalchemy import Column, Constraint, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Re-exported: these used to live here, and migrations, views and tests all
# import them from this module. See models/item.py for where they went.
from .item import (  # noqa: F401
    Item,
    RecurrenceKind,
    RecurrenceRule,
    RecurrenceUnit,
    TagSet,
    TodoStatus,
)
from .meta import Base


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


class Todo(Item):
    """A task: an item with a status, a due date and a place in a chain."""

    __tablename__ = "todos"

    id: Mapped[int] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    tags: set[str] = Column(TagSet, nullable=False, server_default="{}")
    assignees = Column(TagSet, nullable=False, server_default="{}")

    #: The instance this one spawned, if any — the chain is written forwards.
    #:
    #: A predecessor pointer cannot keep a chain straight: two requests that
    #: both spawn from the same item each write their own row, nothing
    #: collides, and the chain quietly becomes a tree. Written forwards there
    #: is one column per item to hold a successor, so a second spawn has
    #: nowhere to put itself, and UNIQUE stops two items claiming the same
    #: successor. Claiming it is a conditional UPDATE, so the loser finds out.
    recurred_into_id = Column(
        Integer, ForeignKey("todos.id"), nullable=True, unique=True
    )

    # 1-to-1 link to a ProtocolRun. Set when this todo was spawned for a
    # protocol run (the user's calendar trigger). UNIQUE so each run has
    # exactly one todo.
    protocol_run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("protocol_runs.id"),
        unique=True,
        nullable=True,
    )

    attachments: Mapped[list["TodoAttachment"]] = relationship(
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
    recurred_into = relationship(
        "Todo", remote_side="Todo.id", foreign_keys=[recurred_into_id]
    )
    protocol_run = relationship(
        "ProtocolRun",
        back_populates="todo",
        foreign_keys=[protocol_run_id],
        lazy="joined",
    )

    __mapper_args__ = {"polymorphic_identity": "todo"}

    def marker_text(self) -> str:
        """This todo as the marker string its edit affordances show and parse back."""
        from menage2.markers import format_markers

        return format_markers(
            self.text,
            tags=self.tags,
            assignees=self.assignees,
            links=self.links_rel,
            due_date=self.due_date,
            recurrence=self.recurrence.label if self.recurrence else None,
            note=self.note,
        )


class TodoAttachment(Base):
    __tablename__: str = "todo_attachments"
    __table_args__: tuple[Index | Constraint, ...] = (
        Index("ix_todo_attachments_todo_id", "todo_id"),
        Index("ix_todo_attachments_uuid", "uuid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    todo_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("todos.id", ondelete="CASCADE"),
        nullable=False,
    )
    uuid: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    mimetype: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )

    todo: Mapped[list[Todo]] = relationship("Todo", back_populates="attachments")
