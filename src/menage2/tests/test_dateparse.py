"""Unit tests for menage2.dateparse — pure functions, no DB."""
import datetime

import pytest

from menage2.dateparse import ParsedDate, label_date, parse_date


# Reference "today" used by every test. Wednesday, 29 April 2026 — chosen so
# weekday-dependent assertions are easy to reason about (mid-week, mid-month).
TODAY = datetime.date(2026, 4, 29)


def _date(s):
    return datetime.date.fromisoformat(s)


# ---------------------------------------------------------------------------
# Empty / nonsense input
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["", "   ", "   \t  ", "5", "blah", "in a hour", "tomorrow morning"])
def test_returns_none_for_unrecognised(raw):
    assert parse_date(raw, TODAY) is None


# ---------------------------------------------------------------------------
# Bare keywords
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    ("today", "2026-04-29"),
    ("now", "2026-04-29"),
    ("tomorrow", "2026-04-30"),
    ("yesterday", "2026-04-28"),
    ("TOMORROW", "2026-04-30"),
    ("  Today  ", "2026-04-29"),
])
def test_bare_keywords(raw, expected):
    result = parse_date(raw, TODAY)
    assert result is not None
    assert result.date == _date(expected)


# ---------------------------------------------------------------------------
# ISO format
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    ("2026-05-12", "2026-05-12"),
    ("2027-01-01", "2027-01-01"),
    ("2026-4-9", "2026-04-09"),
])
def test_iso_format(raw, expected):
    result = parse_date(raw, TODAY)
    assert result is not None
    assert result.date == _date(expected)


@pytest.mark.parametrize("raw", ["2026-13-01", "2026-02-30", "abcd-ef-gh"])
def test_iso_invalid_returns_none(raw):
    assert parse_date(raw, TODAY) is None


# ---------------------------------------------------------------------------
# German numeric DD.MM.[YYYY]
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    ("12.5.", "2026-05-12"),
    ("12.5", "2026-05-12"),
    ("01.06.2027", "2027-06-01"),
    ("1.6.2027", "2027-06-01"),
])
def test_german_format(raw, expected):
    result = parse_date(raw, TODAY)
    assert result is not None
    assert result.date == _date(expected)


def test_german_short_rolls_to_next_year_if_past():
    # 1.1 with today=2026-04-29 should be 1 Jan 2027 (next occurrence)
    result = parse_date("1.1.", TODAY)
    assert result.date == _date("2027-01-01")


def test_german_short_today_stays_same_year():
    result = parse_date("29.4.", TODAY)
    assert result.date == _date("2026-04-29")


# ---------------------------------------------------------------------------
# Relative units
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    ("in 7 days", "2026-05-06"),
    ("7 days", "2026-05-06"),
    ("7d", "2026-05-06"),
    ("3d", "2026-05-02"),
    ("2 weeks", "2026-05-13"),
    ("2w", "2026-05-13"),
    ("a week", "2026-05-06"),
    ("an hour", None),  # hours not supported
    ("one day", "2026-04-30"),
    ("in a week", "2026-05-06"),
    ("a month", "2026-05-29"),
    ("1mo", "2026-05-29"),
    ("3 months", "2026-07-29"),
    ("a year", "2027-04-29"),
    ("2 years", "2028-04-29"),
])
def test_relative(raw, expected):
    result = parse_date(raw, TODAY)
    if expected is None:
        assert result is None
    else:
        assert result is not None
        assert result.date == _date(expected)


def test_next_week_is_next_monday():
    # today=Wed 29 Apr. Next Monday = 4 May.
    result = parse_date("next week", TODAY)
    assert result.date == _date("2026-05-04")


def test_next_month_keeps_day_of_month():
    result = parse_date("next month", TODAY)
    assert result.date == _date("2026-05-29")


def test_next_year_keeps_day_of_year():
    result = parse_date("next year", TODAY)
    assert result.date == _date("2027-04-29")


# ---------------------------------------------------------------------------
# Weekdays
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    ("monday", "2026-05-04"),
    ("mon", "2026-05-04"),
    ("tuesday", "2026-05-05"),
    ("wednesday", "2026-05-06"),  # today is Wed → soonest Wed is +7
    ("wed", "2026-05-06"),
    ("thursday", "2026-04-30"),
    ("friday", "2026-05-01"),
    ("saturday", "2026-05-02"),
    ("sunday", "2026-05-03"),
])
def test_weekdays(raw, expected):
    result = parse_date(raw, TODAY)
    assert result is not None
    assert result.date == _date(expected)


def test_next_weekday_jumps_extra_week():
    # today=Wed. "next wed" = +14, "next thursday" = +8.
    assert parse_date("next wed", TODAY).date == _date("2026-05-13")
    assert parse_date("next thursday", TODAY).date == _date("2026-05-07")


# ---------------------------------------------------------------------------
# Months
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    ("march", "2027-03-01"),  # today is April → next March is 2027
    ("may", "2026-05-01"),
    ("december", "2026-12-01"),
    ("dec", "2026-12-01"),
    ("january 2030", "2030-01-01"),
    ("jan 2030", "2030-01-01"),
])
def test_bare_months(raw, expected):
    result = parse_date(raw, TODAY)
    assert result is not None
    assert result.date == _date(expected)


def test_next_march_jumps_a_year():
    # bare "march" already yields 2027-03-01 (today is April 2026); "next" adds
    # another year on top.
    assert parse_date("next march", TODAY).date == _date("2028-03-01")


@pytest.mark.parametrize("raw,expected", [
    ("15 march", "2027-03-15"),
    ("15 may", "2026-05-15"),
    ("march 15", "2027-03-15"),
    ("may 15", "2026-05-15"),
    ("15 march 2030", "2030-03-15"),
    ("march 15 2030", "2030-03-15"),
])
def test_day_with_month(raw, expected):
    result = parse_date(raw, TODAY)
    assert result is not None
    assert result.date == _date(expected)


def test_invalid_day_in_month_returns_none():
    assert parse_date("31 february", TODAY) is None


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("d,expected", [
    ("2026-04-29", "today"),
    ("2026-04-30", "tomorrow"),
    ("2026-04-28", "yesterday"),
    ("2026-05-01", "Fri"),       # +2 days, same week
    ("2026-05-02", "Sat"),       # +3 days
    ("2026-05-04", "Mon"),       # +5 days, still in 1..6 range
    ("2026-05-06", "Wed, 6 May"),  # +7 days, switches to date form
    ("2026-12-25", "Fri, 25 Dec"),
    ("2027-01-01", "1 Jan 2027"),
])
def test_label_date(d, expected):
    assert label_date(_date(d), TODAY) == expected


def test_parsed_date_carries_label():
    result = parse_date("tomorrow", TODAY)
    assert result == ParsedDate(date=_date("2026-04-30"), label="tomorrow")
