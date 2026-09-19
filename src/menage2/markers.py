"""The ``#tag @who ^date *rule ~note`` marker language, both directions.

:func:`menage2.views.todo.parse_todo_input` reads a marker string into fields;
:func:`format_markers` writes those fields back out. Every edit affordance —
the todo add box, the protocol title, protocol items, the run-item editor —
shows the written form and hands whatever the user typed back to the parser, so
the two directions have to round-trip.

Every marker has two spellings:

``~note text``
    The bare form. It runs to the next marker character or the end of the
    string, so it cannot contain one; ``#`` and ``@`` additionally stop at the
    first space.

``~[note text]``
    The bracketed form. The payload runs to the matching ``]`` and may contain
    anything, marker characters included. Literal brackets are written
    markdown-style, ``\\[`` and ``\\]``, and a literal backslash as ``\\\\``.

:func:`format_markers` emits the bare form when it is unambiguous and reaches
for brackets only when the payload needs them, so the common case stays
readable. Marker order still matters for the bare form: anything not
introduced by a marker (the text, and ``[label](url)`` links) comes first, and
the note comes last.

Outside a marker, a backslash makes the next character literal: ``C\\# basics``
is text, not a ``#basics`` tag, and ``\\[a\\](b)`` is text rather than a link.
:func:`escape_text` applies that to a whole string, so a todo whose text is
full of marker characters still survives being written out and read back.
"""

from __future__ import annotations

import dataclasses
import datetime
import re
from typing import Iterable, Optional

#: The characters that introduce a marker.
MARKERS = "#@^*~"

#: Markers whose bare form stops at the first space.
_WORD_MARKERS = "#@"

#: Characters that have to be backslashed to appear literally in free text.
_TEXT_SPECIALS = "\\" + MARKERS + "[]"

#: ``[label](url)`` — the label may not contain ``]``, the url no spaces.
_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")


def escape_text(value: str) -> str:
    """Backslash anything in `value` the parser would otherwise read as markup."""
    out: list[str] = []
    for char in value:
        if char in _TEXT_SPECIALS:
            out.append("\\")
        out.append(char)
    return "".join(out)


def escape_payload(value: str) -> str:
    """Escape a payload for the bracketed form, markdown-style."""
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def read_bracketed(text: str, open_at: int) -> Optional[tuple[str, int]]:
    """Read the ``[...]`` payload whose ``[`` sits at `open_at`.

    Returns ``(payload, index after the closing bracket)``, with escapes
    resolved, or ``None`` when the bracket is never closed — in which case the
    caller should treat the text as literal.
    """
    out: list[str] = []
    i = open_at + 1
    while i < len(text):
        char = text[i]
        if char == "\\" and i + 1 < len(text):
            out.append(text[i + 1])
            i += 2
            continue
        if char == "]":
            return "".join(out), i + 1
        out.append(char)
        i += 1
    return None


@dataclasses.dataclass(frozen=True)
class Token:
    """One piece of a marker string.

    `kind` is ``"text"``, ``"marker"`` or ``"link"``. `raw` is the source the
    token came from, so a marker that turns out not to parse — ``^next
    thursdya`` — can be put back into the text verbatim.
    """

    kind: str
    value: str = ""
    marker: str = ""
    url: str = ""
    raw: str = ""


def _read_bare(source: str, start: int) -> tuple[str, int]:
    """Read the bare payload of the marker at `start`.

    Runs to the next unescaped marker character — plus the next space for
    ``#`` and ``@`` — or the end of the string.
    """
    stop_at_space = source[start] in _WORD_MARKERS
    out: list[str] = []
    i = start + 1
    while i < len(source):
        char = source[i]
        if char == "\\" and i + 1 < len(source):
            out.append(source[i + 1])
            i += 2
            continue
        if char in MARKERS:
            break
        if stop_at_space and char.isspace():
            break
        out.append(char)
        i += 1
    return "".join(out).strip(), i


def scan(source: str) -> list[Token]:
    """Split a marker string into text, markers and links, honouring escapes.

    A single left-to-right pass, so a marker payload swallows whatever follows
    it up to its own terminator — which is what keeps ``[a](b)`` inside a note
    from being read as a link.
    """
    tokens: list[Token] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            tokens.append(Token("text", "".join(buf)))
            buf.clear()

    i = 0
    while i < len(source):
        char = source[i]

        if char == "\\" and i + 1 < len(source):
            # `\#`, `\*`, `\[`, `\\` … the next character is literal text.
            buf.append(source[i + 1])
            i += 2
            continue

        if char in MARKERS:
            if source[i + 1 : i + 2] == "[":
                bracketed = read_bracketed(source, i + 1)
                if bracketed is not None:
                    value, end = bracketed
                    flush()
                    tokens.append(Token("marker", value, char, raw=source[i:end]))
                    i = end
                    continue
            value, end = _read_bare(source, i)
            if value:
                flush()
                tokens.append(Token("marker", value, char, raw=source[i:end]))
                i = end
                continue

        if char == "[":
            match = _LINK_RE.match(source, i)
            if match:
                flush()
                tokens.append(
                    Token(
                        "link",
                        match.group(1),
                        url=match.group(2),
                        raw=match.group(0),
                    )
                )
                i = match.end()
                continue

        buf.append(char)
        i += 1

    flush()
    return tokens


def _needs_brackets(value: str, *, bare_allows_spaces: bool) -> bool:
    if not value:
        return True
    if any(char in MARKERS for char in value) or "[" in value or "]" in value:
        return True
    if not bare_allows_spaces and any(char.isspace() for char in value):
        return True
    return False


def _marker(char: str, value: str) -> str:
    """Render one marker, bracketing the payload only when the bare form can't hold it."""
    if _needs_brackets(value, bare_allows_spaces=char not in _WORD_MARKERS):
        return f"{char}[{escape_payload(value)}]"
    return f"{char}{value}"


def format_markers(
    text: str,
    *,
    tags: Iterable[str] = (),
    assignees: Iterable[str] = (),
    links: Iterable = (),
    due_date: Optional[datetime.date] = None,
    recurrence: Optional[str] = None,
    note: Optional[str] = None,
) -> str:
    """Render fields as the marker string a user edits and the parser reads back.

    `links` are objects with ``label`` and ``url``; `recurrence` is an already
    rendered rule label such as ``"every week"``. Tags and assignees are sorted
    so the output is stable regardless of set ordering.
    """
    parts: list[str] = []
    if text and text.strip():
        parts.append(escape_text(text.strip()))
    parts.extend(f"[{link.label or ''}]({link.url})" for link in links or ())
    parts.extend(_marker("#", tag) for tag in sorted(tags or ()))
    parts.extend(_marker("@", who) for who in sorted(assignees or ()))
    if due_date is not None:
        parts.append(_marker("^", due_date.isoformat()))
    if recurrence:
        parts.append(_marker("*", recurrence))
    if note and note.strip():
        parts.append(_marker("~", note.strip()))
    return " ".join(parts)
