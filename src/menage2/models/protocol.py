"""Protocol — recurring multi-item lists you "run through" periodically.

A Protocol is a *template* (title + ordered items + optional recurrence rule).
A ProtocolRun is one *instance* of working through the template; each run
freezes a snapshot of the template's items into ProtocolRunItem rows when it
is first opened (so last-minute template edits flow into the next un-opened
run, while an open run is stable).

A ProtocolRun is paired 1-to-1 with a Todo (``Todo.protocol_run_id``). The
Todo is the user-facing trigger on the active list — its due_date drives
"when is this run due"; clicking through opens the run page; ticking the
Todo done closes the run.
"""

import datetime
from typing import ClassVar, Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    object_session,
    relationship,
    synonym,
)

from menage2.recurrence import (
    RecurrenceRule,
    spawn_protocol_after,
    spawn_protocol_every_on_completion,
)

from .item import Item, TodoStatus
from .todo import Todo


class Protocol(Item):
    """A checklist template: a title, an ordered set of items, a cadence."""

    __tablename__ = "protocols"

    id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    archived_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    #: A protocol's text *is* its title. Both names read naturally in the
    #: places that use them, so both stay.
    title = synonym("text")

    __mapper_args__: ClassVar = {"polymorphic_identity": "protocol"}

    items: Mapped[list["ProtocolItem"]] = relationship(
        "ProtocolItem",
        back_populates="protocol",
        order_by="ProtocolItem.position",
        cascade="all, delete-orphan",
        # Two paths link these tables now: an item belongs to a protocol,
        # and both are items. This is the one that means belonging.
        foreign_keys="ProtocolItem.protocol_id",
    )
    runs: Mapped[list["ProtocolRun"]] = relationship(
        "ProtocolRun",
        back_populates="protocol",
        order_by="ProtocolRun.created_at.desc()",
        # A run belongs to a protocol, and both are items; this is belonging.
        foreign_keys="ProtocolRun.protocol_id",
    )
    recurrence: Mapped[Optional["RecurrenceRule"]] = relationship(
        "RecurrenceRule", lazy="joined"
    )


class ProtocolItem(Item):
    """One line of a checklist template."""

    __tablename__ = "protocol_items"

    id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    protocol_id = Column(Integer, ForeignKey("protocols.id"), nullable=False)
    position = Column(Integer, nullable=False, default=0)

    __mapper_args__: ClassVar = {
        "polymorphic_identity": "protocol_item",
        "inherit_condition": id == Item.id,
    }

    protocol = relationship(
        "Protocol", back_populates="items", foreign_keys=[protocol_id]
    )


class ProtocolRun(Todo):
    """One working-through of a checklist -- and the task that says it is due.

    These used to be two rows: a run, and a todo paired with it 1-to-1 whose
    text, tags, due date and status were the run's in everything but name.
    Ticking the todo closed the run and closing the run ticked the todo,
    which is a long way of saying they were the same thing. A run is a todo
    that has a checklist behind it.
    """

    __tablename__ = "protocol_runs"

    id = Column(Integer, ForeignKey("todos.id", ondelete="CASCADE"), primary_key=True)
    protocol_id = Column(Integer, ForeignKey("protocols.id"), nullable=False)
    #: When the items were snapshotted -- the one date that is the run's own.
    #: Spawning is `created_at` and closing is `done_at`, on the item.
    opened_at = Column(DateTime(timezone=True))

    __mapper_args__: ClassVar = {
        "polymorphic_identity": "protocol_run",
        "inherit_condition": id == Todo.id,
        # The task list loads todos and runs together; without this each run
        # row on the list costs a query of its own.
        "polymorphic_load": "selectin",
    }

    protocol = relationship(
        "Protocol", back_populates="runs", foreign_keys=[protocol_id]
    )
    items = relationship(
        "ProtocolRunItem",
        back_populates="run",
        order_by="ProtocolRunItem.position",
        cascade="all, delete-orphan",
        foreign_keys="ProtocolRunItem.run_id",
    )

    def sorted_items(self) -> list["ProtocolRunItem"]:
        return sorted(
            self.items,
            key=lambda i: (not i.is_pending, i.position),
        )

    def ensure_snapshot_run_items(self):
        """Copy current Protocol items into ProtocolRunItem rows.

        Idempotent: held under the module-level snapshot lock + a re-check of
        ``opened_at`` so concurrent first-opens snapshot exactly once.
        """
        if self.opened_at is not None:
            return

        protocol = self.protocol
        session = object_session(self)
        for src in sorted(protocol.items, key=lambda i: i.position):
            session.add(
                ProtocolRunItem.from_item(
                    src,
                    run=self,
                    position=src.position,
                    assignees=set(src.assignees or protocol.assignees),
                    status=TodoStatus.todo,
                )
            )
        self.opened_at = datetime.datetime.now(datetime.UTC)

    def maybe_close_run(self):
        """Tick it off when every item is resolved.

        Closing the run and completing the task are one act now; they were
        always meant to be the same one.
        """
        if any(i.is_pending for i in self.items):
            return
        if self.status != TodoStatus.todo:
            return
        now = datetime.datetime.now(datetime.UTC)
        self.status = TodoStatus.done
        self.done_at = now
        dbsession = object_session(self)
        spawn_protocol_after(self, now.date(), now, dbsession)
        spawn_protocol_every_on_completion(self, now.date(), now, dbsession)


class ProtocolRunItem(Item):
    """One line of a run: the same three states any item has, plus where it went."""

    __tablename__ = "protocol_run_items"

    id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    run_id = Column(Integer, ForeignKey("protocol_runs.id"), nullable=False)
    position = Column(Integer, nullable=False, default=0)
    sent_todo_id = Column(Integer, ForeignKey("todos.id"), nullable=True)

    __mapper_args__: ClassVar = {
        "polymorphic_identity": "protocol_run_item",
        "inherit_condition": id == Item.id,
    }

    run = relationship("ProtocolRun", back_populates="items", foreign_keys=[run_id])

    @property
    def is_pending(self) -> bool:
        return self.status == TodoStatus.todo

    @property
    def state(self) -> str:
        """`pending`, `done` or `sent_to_todo`.

        A line that was sent off is done here and waiting elsewhere, so it
        is a done item that knows where it went rather than a fourth state
        of its own. The markup and its styling still want one word for it.
        """
        if self.is_pending:
            return "pending"
        return "sent_to_todo" if self.sent_todo_id is not None else "done"

    def marker_text(self) -> str:
        """This run item as the marker string its inline editor shows and parses back."""
        from menage2.markers import format_markers

        return format_markers(
            self.text, tags=self.tags, assignees=self.assignees, note=self.note
        )
