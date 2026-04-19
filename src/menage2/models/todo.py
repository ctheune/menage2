import datetime
import enum

from sqlalchemy import Column, DateTime, Enum, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY
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
    postponed = "postponed"


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
    postponed_at = Column(DateTime(timezone=True))
