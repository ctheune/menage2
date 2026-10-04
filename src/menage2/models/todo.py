from typing import ClassVar

from sqlalchemy import Column, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Re-exported: these used to live here, and migrations, views and tests all
# import them from this module. See models/item.py for where they went.
from .item import Item


class Todo(Item):
    """A basic todo item that is shown on todo lists."""

    __tablename__ = "todos"

    id: Mapped[int] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )

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

    recurred_into = relationship(
        "Todo", remote_side="Todo.id", foreign_keys=[recurred_into_id]
    )

    __mapper_args__: ClassVar = {"polymorphic_identity": "todo"}

    def marker_text(self) -> str:
        """This todo as the marker string its edit affordances show and parse back."""
        from menage2.markers import format_markers

        return format_markers(
            self.text,
            tags=self.tags,
            assignees=self.assignees,
            links=self.links,
            due_date=self.due_date,
            recurrence=self.recurrence.label if self.recurrence else None,
            note=self.note,
        )
