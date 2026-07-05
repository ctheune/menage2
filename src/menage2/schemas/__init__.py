"""Pydantic schemas for request/response validation."""

import datetime as _dt
from datetime import date, datetime
from enum import Enum
from typing import Annotated, List, Literal, Optional, Set

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    constr,
    field_validator,
)

from menage2.dateparse import RecurrenceSpec
from menage2.dateparse import parse_date as _parse_date
from menage2.dateparse import parse_recurrence


class TodoStatus(str, Enum):
    todo = "todo"
    done = "done"
    on_hold = "on_hold"


class TodoLinkCreate(BaseModel):
    """Schema for creating a todo link."""

    label: Optional[str] = None
    url: str


class TodoLinkUpdate(BaseModel):
    """Schema for updating a todo link."""

    label: Optional[str] = None
    url: Optional[str] = None


class TodoLink(BaseModel):
    """Schema for a todo link."""

    id: int
    label: Optional[str]
    url: str
    position: int

    model_config = ConfigDict(from_attributes=True)


TagString = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^[\p{Letter}0-9:\-]+$")
]


class TodoUpdate(BaseModel):
    """Schema for updating a todo - all fields optional for partial updates.

    `clear_fields` names fields the client wants explicitly cleared, since
    form-json simply omits absent inputs and the view otherwise can't
    distinguish "not sent" from "set to empty". Sent from the form as
    indexed inputs (`clear_fields.0`, `clear_fields.1`, …).
    """

    text: Optional[str] = None
    tags: Optional[Set[TagString]] = None
    assignees: Optional[Set[str]] = None
    due_date: Optional[date] = None
    recurrence: Optional[RecurrenceSpec] = None
    note: Optional[str] = None
    links: Optional[List[TodoLinkCreate]] = None
    attachments: Optional[Set[str]] = None
    clear_fields: Set[str] = Field(default_factory=set)

    @field_validator("due_date", mode="before")
    @classmethod
    def parse_due_date(cls, v: object) -> date | None:
        if not v:
            return None
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            parsed = _parse_date(v, _dt.date.today())
            if parsed:
                return parsed.date
        raise ValueError(f"Cannot parse date: {v!r}")

    @field_validator("recurrence", mode="before")
    @classmethod
    def parse_recurrence(cls, v: object) -> RecurrenceSpec | None:
        if not v:
            return None
        if isinstance(v, RecurrenceSpec):
            return v
        if isinstance(v, str):
            parsed = parse_recurrence(v)
            if parsed:
                return parsed
        raise ValueError(f"Cannot parse recurrence: {v!r}")


class TodoCreate(BaseModel):
    """Schema for creating a new todo."""

    text: str
    tags: Set[str] = Field(default_factory=set)
    assignees: Set[str] = Field(default_factory=set)
    due_date: Optional[date] = None
    recurrence: Optional[RecurrenceSpec] = None
    note: Optional[str] = None
    links: List[TodoLinkCreate] = Field(default_factory=list)


class TodoResponse(BaseModel):
    """Schema for todo response."""

    id: int
    text: str
    tags: Set[str]
    assignees: Set[str]
    status: TodoStatus
    due_date: Optional[date]
    note: Optional[str]
    recurrence: Optional[RecurrenceSpec]
    links: List[TodoLink]
    created_at: datetime
    done_at: Optional[datetime]
    on_hold_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class BatchAction(BaseModel):
    """Schema for batch actions on todos."""

    action: Literal["done", "hold", "postpone", "activate", "edit"]
    todo_ids: List[int]
    interval: Optional[str] = None  # "1d", "1w", "1mo", etc. — used by postpone
    todo: Optional[TodoUpdate] = None  # used by edit
