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

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship

from .meta import Base
from .todo import TagSet


class ProtocolRunItemStatus(enum.Enum):
    pending = "pending"
    done = "done"
    sent_to_todo = "sent_to_todo"


class Protocol(Base):
    __tablename__ = "protocols"

    id = Column(Integer, primary_key=True)
    title = Column(Text, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assignees = Column(TagSet, nullable=False, server_default="{}")
    recurrence_id = Column(Integer, ForeignKey("recurrence_rules.id"), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    archived_at = Column(DateTime(timezone=True))

    owner = relationship("User", foreign_keys=[owner_id])
    items = relationship(
        "ProtocolItem",
        back_populates="protocol",
        order_by="ProtocolItem.position",
        cascade="all, delete-orphan",
    )
    runs = relationship(
        "ProtocolRun",
        back_populates="protocol",
        order_by="ProtocolRun.spawned_at.desc()",
    )
    recurrence = relationship("RecurrenceRule", lazy="joined")


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
