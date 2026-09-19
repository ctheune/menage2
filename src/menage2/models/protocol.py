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
import enum
from typing import Optional

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, object_session, relationship

from menage2.models.user import User
from menage2.recurrence import (
    RecurrenceRule,
    ensure_protocol_has_run,
    rule_to_spec,
    spawn_protocol_after,
    spawn_protocol_every_on_completion,
    spawn_protocol_run,
)

from .meta import Base
from .todo import TagSet, TodoStatus


class ProtocolRunItemStatus(enum.Enum):
    pending = "pending"
    done = "done"
    sent_to_todo = "sent_to_todo"


class Protocol(Base):
    __tablename__ = "protocols"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column()
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    tags: Mapped[set] = mapped_column(TagSet, server_default="{}")
    note: Mapped[str] = mapped_column()
    assignees: Mapped[set] = mapped_column(TagSet, server_default="{}")
    recurrence_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("recurrence_rules.id")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    archived_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    owner: Mapped["User"] = relationship("User", foreign_keys=[owner_id])
    items: Mapped[list["ProtocolItem"]] = relationship(
        "ProtocolItem",
        back_populates="protocol",
        order_by="ProtocolItem.position",
        cascade="all, delete-orphan",
    )
    runs: Mapped[list["ProtocolRun"]] = relationship(
        "ProtocolRun",
        back_populates="protocol",
        order_by="ProtocolRun.spawned_at.desc()",
    )
    recurrence: Mapped[Optional["RecurrenceRule"]] = relationship(
        "RecurrenceRule", lazy="joined"
    )

    def marker_text(self) -> str:
        """This protocol as the marker string its title line shows and parses back.

        The title takes the place a todo's text would.
        """
        from menage2.markers import format_markers

        return format_markers(
            self.title,
            tags=self.tags,
            assignees=self.assignees,
            recurrence=self.recurrence.label if self.recurrence else None,
            note=self.note,
        )


class ProtocolItem(Base):
    __tablename__ = "protocol_items"

    id = Column(Integer, primary_key=True)
    protocol_id = Column(Integer, ForeignKey("protocols.id"), nullable=False)
    position = Column(Integer, nullable=False, default=0)
    text = Column(Text, nullable=False)
    tags = Column(TagSet, nullable=False, server_default="{}")
    assignees = Column(TagSet, nullable=False, server_default="{}")
    note = Column(Text)

    protocol = relationship("Protocol", back_populates="items")

    def marker_text(self) -> str:
        """This item as the marker string its edit line shows and parses back."""
        from menage2.markers import format_markers

        return format_markers(
            self.text, tags=self.tags, assignees=self.assignees, note=self.note
        )


class ProtocolRun(Base):
    __tablename__ = "protocol_runs"

    id = Column(Integer, primary_key=True)
    protocol_id = Column(Integer, ForeignKey("protocols.id"), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    spawned_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    opened_at = Column(DateTime(timezone=True))
    closed_at = Column(DateTime(timezone=True))

    protocol = relationship("Protocol", back_populates="runs")
    owner = relationship("User", foreign_keys=[owner_id])
    items = relationship(
        "ProtocolRunItem",
        back_populates="run",
        order_by="ProtocolRunItem.position",
        cascade="all, delete-orphan",
    )
    # 1-to-1 with Todo via Todo.protocol_run_id (the FK lives on Todo).
    todo = relationship(
        "Todo",
        back_populates="protocol_run",
        uselist=False,
        foreign_keys="Todo.protocol_run_id",
    )

    def sorted_items(self) -> list["ProtocolRunItem"]:
        return sorted(
            self.items,
            key=lambda i: (i.status != ProtocolRunItemStatus.pending, i.position),
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
            item_assignees = (
                set(src.assignees) if src.assignees else set(protocol.assignees)
            )
            session.add(
                ProtocolRunItem(
                    run=self,
                    position=src.position,
                    text=src.text,
                    tags=set(src.tags),
                    assignees=item_assignees,
                    note=src.note,
                    status=ProtocolRunItemStatus.pending,
                )
            )
        self.opened_at = datetime.datetime.now(datetime.timezone.utc)

    def maybe_close_run(self):
        """Close the run + auto-complete its todo when every item is resolved."""
        now = datetime.datetime.now(datetime.timezone.utc)
        today = now.date()
        if any(i.status == ProtocolRunItemStatus.pending for i in self.items):
            return
        if self.closed_at is None:
            self.closed_at = now
        todo = self.todo
        if todo and todo.status == TodoStatus.todo:
            todo.status = TodoStatus.done
            todo.done_at = now
            dbsession = object_session(self)
            spawn_protocol_after(self, today, now, dbsession)
            spawn_protocol_every_on_completion(self, today, now, dbsession)


class ProtocolRunItem(Base):
    __tablename__ = "protocol_run_items"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("protocol_runs.id"), nullable=False)
    position = Column(Integer, nullable=False, default=0)
    text = Column(Text, nullable=False)
    tags = Column(TagSet, nullable=False, server_default="{}")
    assignees = Column(TagSet, nullable=False, server_default="{}")
    note = Column(Text)
    status = Column(
        Enum(ProtocolRunItemStatus, name="protocolrunitemstatus"),
        nullable=False,
        server_default="pending",
    )
    sent_todo_id = Column(Integer, ForeignKey("todos.id"), nullable=True)

    run = relationship("ProtocolRun", back_populates="items")

    @property
    def is_pending(self) -> bool:
        return self.status == ProtocolRunItemStatus.pending

    def marker_text(self) -> str:
        """This run item as the marker string its inline editor shows and parses back."""
        from menage2.markers import format_markers

        return format_markers(
            self.text, tags=self.tags, assignees=self.assignees, note=self.note
        )
