"""Unit tests for Pydantic schemas — no DB required."""

import datetime

import pytest
from pydantic import ValidationError

from menage2.schemas import TodoUpdate


def test_due_date_accepts_iso_string():
    u = TodoUpdate(due_date="2026-06-15")
    assert u.due_date == datetime.date(2026, 6, 15)


def test_due_date_accepts_natural_language_today():
    u = TodoUpdate(due_date="today")
    assert u.due_date == datetime.date.today()


def test_due_date_accepts_relative_expression():
    u = TodoUpdate(due_date="2d")
    assert u.due_date == datetime.date.today() + datetime.timedelta(days=2)


def test_due_date_accepts_date_object():
    d = datetime.date(2026, 7, 1)
    u = TodoUpdate(due_date=d)
    assert u.due_date == d


def test_due_date_accepts_none():
    u = TodoUpdate(due_date=None)
    assert u.due_date is None


def test_due_date_rejects_unparseable_string():
    with pytest.raises(ValidationError):
        TodoUpdate(due_date="not a date at all !@#")
