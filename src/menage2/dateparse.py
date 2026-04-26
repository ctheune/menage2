"""Parse natural-language date fragments into a single calendar date.

Pure functions only. No I/O, no globals, no Pyramid. The caller passes ``today``
explicitly so the parser is fully deterministic and trivially testable.

Supported forms (English, plus German numeric ``DD.MM.[YYYY]``):

* ``today``, ``tomorrow``, ``yesterday``, ``now``
* ISO ``YYYY-MM-DD``
* German numeric ``DD.MM.`` / ``DD.MM.YYYY``
* Relative: ``in 7 days``, ``7 days``, ``2w``, ``3d``, ``1mo``, ``a week``,
  ``one month``, ``next week``, ``next month``, ``next year``
* Weekdays: ``wed``, ``wednesday``, ``next wed``
* Months: ``march``, ``next march``, ``march 2026``, ``15 march``, ``march 15``
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass

from dateutil.relativedelta import relativedelta


@dataclass(frozen=True)
class ParsedDate:
    date: datetime.date
    label: str  # short, human-friendly form for the live preview popover


_WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

_MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

# Canonical unit deltas: (days, months, years)
_UNITS = {
    "day": (1, 0, 0), "days": (1, 0, 0), "d": (1, 0, 0),
    "week": (7, 0, 0), "weeks": (7, 0, 0), "w": (7, 0, 0),
    "month": (0, 1, 0), "months": (0, 1, 0), "mo": (0, 1, 0), "mon": (0, 1, 0),
    "year": (0, 0, 1), "years": (0, 0, 1), "y": (0, 0, 1), "yr": (0, 0, 1),
}

_WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_MONTH_LABELS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def label_date(d: datetime.date, today: datetime.date) -> str:
    """Render a short label suitable for the input live-preview popover."""
    delta = (d - today).days
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    if delta == -1:
        return "yesterday"
    if 1 < delta < 7:
        return _WEEKDAY_LABELS[d.weekday()]
    if d.year == today.year:
        return f"{_WEEKDAY_LABELS[d.weekday()]}, {d.day} {_MONTH_LABELS[d.month - 1]}"
    return f"{d.day} {_MONTH_LABELS[d.month - 1]} {d.year}"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _add_units(today: datetime.date, n: int, unit: str) -> datetime.date:
    days, months, years = _UNITS[unit]
    return today + datetime.timedelta(days=n * days) + relativedelta(months=n * months, years=n * years)


def _soonest_weekday(today: datetime.date, weekday: int, extra_weeks: int = 0) -> datetime.date:
    """Soonest future date matching ``weekday`` (today never counts)."""
    delta = (weekday - today.weekday()) % 7 or 7
    return today + datetime.timedelta(days=delta + 7 * extra_weeks)


def _try_iso(text: str) -> datetime.date | None:
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if not m:
        return None
    try:
        return datetime.date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def _try_german(text: str, today: datetime.date) -> datetime.date | None:
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.?(\d{4})?", text)
    if not m:
        return None
    day, month = int(m[1]), int(m[2])
    explicit_year = m[3]
    year = int(explicit_year) if explicit_year else today.year
    try:
        d = datetime.date(year, month, day)
    except ValueError:
        return None
    if not explicit_year and d < today:
        try:
            d = datetime.date(year + 1, month, day)
        except ValueError:
            return None
    return d


def _try_relative(text: str, today: datetime.date) -> datetime.date | None:
    # "next week" / "next month" / "next year"
    if text == "next week":
        return _soonest_weekday(today, 0)
    if text == "next month":
        return today + relativedelta(months=1)
    if text == "next year":
        return today + relativedelta(years=1)

    # "in a week" / "a week" / "one month" / "an hour" (rejected)
    m = re.fullmatch(r"(?:in\s+)?(?:a|an|one)\s+(\w+)", text)
    if m and m[1] in _UNITS:
        return _add_units(today, 1, m[1])

    # "in 7 days" / "7 days" / "2w" / "3 mo"
    m = re.fullmatch(r"(?:in\s+)?(\d+)\s*(\w+)", text)
    if m and m[2] in _UNITS:
        return _add_units(today, int(m[1]), m[2])

    return None


def _try_weekday(text: str, today: datetime.date) -> datetime.date | None:
    m = re.fullmatch(r"(?:(next|this)\s+)?(\w+)", text)
    if not m or m[2] not in _WEEKDAYS:
        return None
    extra = 1 if m[1] == "next" else 0
    return _soonest_weekday(today, _WEEKDAYS[m[2]], extra_weeks=extra)


def _try_month(text: str, today: datetime.date) -> datetime.date | None:
    # "march", "next march", "march 2026"
    m = re.fullmatch(r"(?:(next)\s+)?(\w+)(?:\s+(\d{4}))?", text)
    if m and m[2] in _MONTHS:
        month = _MONTHS[m[2]]
        if m[3]:
            year = int(m[3])
        else:
            year = today.year if today.month < month else today.year + 1
            if m[1] == "next":
                year += 1
        return datetime.date(year, month, 1)

    # "15 march", "15 march 2026"
    m = re.fullmatch(r"(\d{1,2})\s+(\w+)(?:\s+(\d{4}))?", text)
    if m and m[2] in _MONTHS:
        return _build_day_month(int(m[1]), _MONTHS[m[2]], m[3], today)

    # "march 15", "march 15 2026"
    m = re.fullmatch(r"(\w+)\s+(\d{1,2})(?:\s+(\d{4}))?", text)
    if m and m[1] in _MONTHS:
        return _build_day_month(int(m[2]), _MONTHS[m[1]], m[3], today)

    return None


def _build_day_month(day: int, month: int, explicit_year: str | None, today: datetime.date) -> datetime.date | None:
    year = int(explicit_year) if explicit_year else today.year
    try:
        d = datetime.date(year, month, day)
    except ValueError:
        return None
    if not explicit_year and d < today:
        try:
            d = datetime.date(year + 1, month, day)
        except ValueError:
            return None
    return d


def parse_date(text: str, today: datetime.date) -> ParsedDate | None:
    """Resolve a fragment of natural language into a single date.

    Returns ``None`` for empty input or unrecognised text. Never raises.
    """
    if not text or not text.strip():
        return None
    s = _normalize(text)

    if s in ("today", "now"):
        return ParsedDate(today, label_date(today, today))
    if s == "tomorrow":
        d = today + datetime.timedelta(days=1)
        return ParsedDate(d, label_date(d, today))
    if s == "yesterday":
        d = today - datetime.timedelta(days=1)
        return ParsedDate(d, label_date(d, today))

    d = (
        _try_iso(s)
        or _try_german(s, today)
        or _try_relative(s, today)
        or _try_weekday(s, today)
        or _try_month(s, today)
    )
    if d:
        return ParsedDate(d, label_date(d, today))
    return None
