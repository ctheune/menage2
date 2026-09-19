"""The marker language has to survive a trip in both directions.

`format_markers` writes the string the edit affordances show; `parse_todo_input`
reads whatever comes back. Anything these two disagree about silently corrupts
a todo the moment someone opens an editor and presses Enter without typing.
"""

import datetime

import pytest

from menage2.markers import format_markers
from menage2.models.protocol import Protocol, ProtocolItem, ProtocolRunItem
from menage2.models.todo import (
    RecurrenceKind,
    RecurrenceRule,
    RecurrenceUnit,
    Todo,
    TodoLink,
)
from menage2.views.todo import parse_todo_input

TODAY = datetime.date(2026, 5, 1)


# ---------------------------------------------------------------------------
# Forwards: fields → marker string
# ---------------------------------------------------------------------------


def test_format_plain_text():
    assert format_markers("buy milk") == "buy milk"


def test_format_trims_surrounding_whitespace():
    assert format_markers("  buy milk  ") == "buy milk"


def test_format_sorts_tags_so_output_is_stable():
    assert format_markers("x", tags={"shop", "food", "abc"}) == "x #abc #food #shop"


def test_format_sorts_assignees():
    assert format_markers("x", assignees={"bob", "alice"}) == "x @alice @bob"


def test_format_due_date_is_iso():
    assert format_markers("x", due_date=datetime.date(2026, 5, 1)) == "x ^2026-05-01"


def test_format_recurrence_label():
    assert format_markers("x", recurrence="every week") == "x *every week"


def test_format_note_comes_last():
    got = format_markers("x", tags={"t"}, note="a longer remark")
    assert got == "x #t ~a longer remark"


def test_format_links_come_before_markers():
    """`^`, `*` and `~` swallow text up to the next marker, so links precede them."""
    link = TodoLink(label="Docs", url="https://example.com")
    got = format_markers("x", links=[link], due_date=datetime.date(2026, 5, 1))
    assert got == "x [Docs](https://example.com) ^2026-05-01"


def test_format_link_without_label():
    link = TodoLink(label=None, url="https://example.com")
    assert format_markers("x", links=[link]) == "x [](https://example.com)"


def test_format_everything_at_once():
    link = TodoLink(label="Docs", url="https://example.com")
    got = format_markers(
        "buy milk",
        tags={"shop"},
        assignees={"alice"},
        links=[link],
        due_date=datetime.date(2026, 5, 1),
        recurrence="every week",
        note="the oat one",
    )
    assert got == (
        "buy milk [Docs](https://example.com) #shop @alice "
        "^2026-05-01 *every week ~the oat one"
    )


def test_format_empty_values_are_skipped():
    assert format_markers("x", tags=set(), assignees=set(), note="", links=[]) == "x"


def test_format_whitespace_only_note_is_skipped():
    assert format_markers("x", note="   ") == "x"


# ---------------------------------------------------------------------------
# Backwards: marker string → fields
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fields",
    [
        {"text": "buy milk"},
        {"text": "buy milk", "tags": {"shop"}},
        {"text": "buy milk", "tags": {"shop", "food"}},
        {"text": "buy milk", "assignees": {"alice"}},
        {"text": "buy milk", "tags": {"shop"}, "assignees": {"alice", "bob"}},
        {"text": "buy milk", "due_date": datetime.date(2026, 5, 1)},
        {"text": "buy milk", "note": "the oat one"},
        {"text": "buy milk", "tags": {"shop"}, "note": "the oat one please"},
        {
            "text": "buy milk",
            "tags": {"shop"},
            "assignees": {"alice"},
            "due_date": datetime.date(2026, 5, 1),
            "note": "the oat one",
        },
    ],
)
def test_round_trip_fields_survive_format_then_parse(fields):
    parsed = parse_todo_input(format_markers(**fields), TODAY)
    assert parsed.text == fields["text"]
    assert parsed.tags == fields.get("tags", set())
    assert parsed.assignees == fields.get("assignees", set())
    assert parsed.due_date == fields.get("due_date")
    assert parsed.note == fields.get("note", "")


def test_round_trip_links_survive():
    link = TodoLink(label="Docs", url="https://example.com")
    parsed = parse_todo_input(format_markers("read up", links=[link]), TODAY)
    assert parsed.text == "read up"
    assert [(link.label, link.url) for link in parsed.links] == [
        ("Docs", "https://example.com")
    ]


def test_round_trip_link_and_due_date_together():
    """The link has to sit before `^`, or the date marker eats it."""
    link = TodoLink(label="Docs", url="https://example.com")
    raw = format_markers("read up", links=[link], due_date=datetime.date(2026, 5, 1))
    parsed = parse_todo_input(raw, TODAY)
    assert parsed.text == "read up"
    assert parsed.due_date == datetime.date(2026, 5, 1)
    assert [(link.label, link.url) for link in parsed.links] == [
        ("Docs", "https://example.com")
    ]


def test_round_trip_recurrence_survives():
    parsed = parse_todo_input(format_markers("water", recurrence="every week"), TODAY)
    assert parsed.text == "water"
    assert parsed.recurrence is not None
    assert parsed.recurrence.label() == "every week"


def test_round_trip_due_date_and_recurrence_together():
    raw = format_markers(
        "water", due_date=datetime.date(2026, 5, 1), recurrence="every week"
    )
    parsed = parse_todo_input(raw, TODAY)
    assert parsed.text == "water"
    assert parsed.due_date == datetime.date(2026, 5, 1)
    assert parsed.recurrence.label() == "every week"


def test_round_trip_note_keeps_trailing_markers_out():
    """The note comes last so it can hold spaces without swallowing markers."""
    raw = format_markers("x", tags={"a", "b"}, note="two words")
    parsed = parse_todo_input(raw, TODAY)
    assert parsed.note == "two words"
    assert parsed.tags == {"a", "b"}


def test_round_trip_string_is_stable_across_two_passes():
    raw = format_markers(
        "buy milk",
        tags={"shop"},
        assignees={"alice"},
        due_date=datetime.date(2026, 5, 1),
        recurrence="every week",
        note="the oat one",
    )
    parsed = parse_todo_input(raw, TODAY)
    again = format_markers(
        parsed.text,
        tags=parsed.tags,
        assignees=parsed.assignees,
        due_date=parsed.due_date,
        recurrence=parsed.recurrence.label() if parsed.recurrence else None,
        note=parsed.note,
    )
    assert again == raw


# ---------------------------------------------------------------------------
# The model methods the templates call
# ---------------------------------------------------------------------------


def _rule(**kwargs):
    defaults = dict(
        kind=RecurrenceKind.every,
        interval_value=1,
        interval_unit=RecurrenceUnit.week,
        weekday=None,
        month_day=None,
    )
    defaults.update(kwargs)
    return RecurrenceRule(**defaults)


def test_recurrence_rule_label():
    assert _rule().label == "every week"


def test_todo_marker_text():
    todo = Todo(
        text="buy milk",
        tags={"shop"},
        assignees={"alice"},
        due_date=datetime.date(2026, 5, 1),
        note="the oat one",
    )
    todo.links_rel = [TodoLink(label="Docs", url="https://example.com", position=0)]
    todo.recurrence = _rule()
    assert todo.marker_text() == (
        "buy milk [Docs](https://example.com) #shop @alice "
        "^2026-05-01 *every week ~the oat one"
    )


def test_todo_marker_text_round_trips():
    todo = Todo(text="buy milk", tags={"shop"}, assignees={"alice"}, note="oat")
    parsed = parse_todo_input(todo.marker_text(), TODAY)
    assert parsed.text == todo.text
    assert parsed.tags == todo.tags
    assert parsed.assignees == todo.assignees
    assert parsed.note == todo.note


def test_todo_marker_text_bare_todo():
    assert Todo(text="plain", tags=set(), assignees=set()).marker_text() == "plain"


def test_protocol_item_marker_text():
    item = ProtocolItem(text="check fridge", tags={"kitchen"}, assignees={"alice"})
    assert item.marker_text() == "check fridge #kitchen @alice"


def test_protocol_run_item_marker_text():
    item = ProtocolRunItem(text="count towels", tags={"bad"}, note="top shelf")
    assert item.marker_text() == "count towels #bad ~top shelf"


def test_protocol_marker_text_uses_the_title():
    protocol = Protocol(title="Weekly inventory", tags={"haus"}, note="bring a pen")
    protocol.recurrence = _rule()
    assert protocol.marker_text() == ("Weekly inventory #haus *every week ~bring a pen")


def test_protocol_marker_text_round_trips_into_the_title():
    protocol = Protocol(title="Weekly inventory", tags={"haus"}, note="bring a pen")
    protocol.recurrence = _rule()
    parsed = parse_todo_input(protocol.marker_text(), TODAY)
    assert parsed.text == protocol.title
    assert parsed.tags == protocol.tags
    assert parsed.note == protocol.note
    assert parsed.recurrence.label() == "every week"


# ---------------------------------------------------------------------------
# The bracketed spelling: M[...] holds anything, including marker characters
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected_note",
    [
        ("x ~[with ^ inside]", "with ^ inside"),
        ("x ~[with # and @ and * inside]", "with # and @ and * inside"),
        (r"x ~[a \[bracketed\] aside]", "a [bracketed] aside"),
        (r"x ~[ends with a backslash \\]", "ends with a backslash \\"),
        ("x ~[]", ""),
    ],
)
def test_bracketed_note_payload(raw, expected_note):
    parsed = parse_todo_input(raw, TODAY)
    assert parsed.note == expected_note


def test_bracketed_note_keeps_the_text_intact():
    parsed = parse_todo_input("buy milk ~[the ^oat one] #shop", TODAY)
    assert parsed.text == "buy milk"
    assert parsed.note == "the ^oat one"
    assert parsed.tags == {"shop"}


def test_bracketed_date_and_recurrence():
    parsed = parse_todo_input("water ^[2026-05-01] *[every week]", TODAY)
    assert parsed.due_date == datetime.date(2026, 5, 1)
    assert parsed.recurrence.label() == "every week"


def test_bracketed_tag_may_contain_spaces():
    parsed = parse_todo_input("x #[two words]", TODAY)
    assert parsed.tags == {"two words"}


def test_bracketed_assignee_may_contain_spaces():
    parsed = parse_todo_input("x @[team lead]", TODAY)
    assert parsed.assignees == {"team lead"}


def test_unterminated_bracket_stays_literal_text():
    parsed = parse_todo_input("x ~[never closed", TODAY)
    assert parsed.note == "[never closed"
    assert parsed.text == "x"


def test_bare_marker_still_stops_at_the_next_marker():
    parsed = parse_todo_input("x ~a note #tag", TODAY)
    assert parsed.note == "a note"
    assert parsed.tags == {"tag"}


# ---------------------------------------------------------------------------
# Escaping: \* \^ \# … put a marker character in the text itself
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("marker", list("#@^*~"))
def test_escaped_marker_is_literal_text(marker):
    parsed = parse_todo_input(rf"a \{marker}b c", TODAY)
    assert parsed.text == f"a {marker}b c"
    assert parsed.tags == set()
    assert parsed.assignees == set()
    assert parsed.note == ""


def test_escaped_hash_is_not_a_tag():
    parsed = parse_todo_input(r"C\# basics #dev", TODAY)
    assert parsed.text == "C# basics"
    assert parsed.tags == {"dev"}


def test_escaped_bracket_is_not_a_link():
    parsed = parse_todo_input(r"see \[Docs\](https://example.com)", TODAY)
    assert parsed.links == []
    assert parsed.text == "see [Docs](https://example.com)"


def test_escaped_backslash_is_literal():
    parsed = parse_todo_input(r"path C:\\tmp", TODAY)
    assert parsed.text == r"path C:\tmp"


def test_escape_inside_a_bare_payload():
    parsed = parse_todo_input(r"x ~costs 5 \# per item", TODAY)
    assert parsed.note == "costs 5 # per item"
    assert parsed.tags == set()


# ---------------------------------------------------------------------------
# Writing picks the spelling that survives the trip back
# ---------------------------------------------------------------------------


def test_format_brackets_a_note_containing_a_marker():
    assert format_markers("x", note="the ^oat one") == "x ~[the ^oat one]"


def test_format_brackets_a_tag_containing_a_space():
    assert format_markers("x", tags={"two words"}) == "x #[two words]"


def test_format_escapes_brackets_in_a_payload():
    assert format_markers("x", note="an [aside]") == r"x ~[an \[aside\]]"


def test_format_escapes_markers_in_the_text():
    assert format_markers("C# basics") == r"C\# basics"


def test_format_leaves_plain_payloads_bare():
    """Brackets only show up when they earn their keep."""
    assert (
        format_markers("x", tags={"shop"}, note="plain words") == "x #shop ~plain words"
    )


@pytest.mark.parametrize(
    "fields",
    [
        {"text": "C# basics"},
        {"text": "weigh 50% *of* it"},
        {"text": "email @ work", "tags": {"admin"}},
        {"text": "x", "note": "the ^oat one"},
        {"text": "x", "note": "costs 5 # per item"},
        {"text": "x", "note": "an [aside] and a ] brace"},
        {"text": "x", "tags": {"two words"}},
        {"text": "x", "assignees": {"team lead"}},
        {"text": "x", "tags": {"a#b"}},
        {"text": "tricky ~ text", "tags": {"t"}, "note": "note with # and @"},
    ],
)
def test_round_trip_survives_awkward_values(fields):
    parsed = parse_todo_input(format_markers(**fields), TODAY)
    assert parsed.text == fields["text"]
    assert parsed.tags == fields.get("tags", set())
    assert parsed.assignees == fields.get("assignees", set())
    assert parsed.note == fields.get("note", "")


def test_round_trip_marker_heavy_todo_via_model():
    todo = Todo(
        text="C# and F# notes",
        tags={"dev lang"},
        assignees={"team lead"},
        note="see the ^old doc [here]",
    )
    todo.links_rel = []
    parsed = parse_todo_input(todo.marker_text(), TODAY)
    assert parsed.text == todo.text
    assert parsed.tags == todo.tags
    assert parsed.assignees == todo.assignees
    assert parsed.note == todo.note
