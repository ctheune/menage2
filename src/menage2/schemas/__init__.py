"""Pydantic schemas for request/response validation."""

from datetime import date, datetime
from enum import Enum
from typing import List, Optional, Set

from pydantic import BaseModel, ConfigDict, Field


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


class RecurrenceSpec(BaseModel):
    """Schema for recurrence specification."""

    kind: str
    interval_value: int
    interval_unit: str
    weekday: Optional[int] = None
    month_day: Optional[int] = None


class TodoUpdate(BaseModel):
    """Schema for updating a todo - all fields optional for partial updates.

    `clear_fields` names fields the client wants explicitly cleared, since
    form-json simply omits absent inputs and the view otherwise can't
    distinguish "not sent" from "set to empty". Sent from the form as
    indexed inputs (`clear_fields.0`, `clear_fields.1`, …).
    """

    text: Optional[str] = None
    tags: Optional[Set[str]] = None
    assignees: Optional[Set[str]] = None
    due_date: Optional[date] = None
    recurrence: Optional[RecurrenceSpec] = None
    note: Optional[str] = None
    links: Optional[List[TodoLinkCreate]] = None
    clear_fields: Set[str] = Field(default_factory=set)


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

    action: str  # "done", "hold", "postpone", "activate"
    todo_ids: List[int]
    postpone_interval: Optional[str] = None  # "1d", "1w", "1mo", etc.
