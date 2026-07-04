"""Subsequence (fuzzy) matching and ranking utilities.

A pattern is a *subsequence* of a string when every character of the pattern
appears in the string in order, with arbitrary gaps between them.  This is the
algorithm used by editors like Sublime Text for "match anywhere" filtering.

Scoring prefers:
  - longer consecutive runs of matched characters
  - matches at word/segment boundaries (start of string, after - _ : . / space)
  - smaller total span of the match
  - shorter string length as a tiebreaker
"""

import html as _html
from typing import Iterable

_SEPARATORS = frozenset(" -_:./")


def _score(text: str, pattern: str) -> int | None:
    """Return a quality score if *pattern* is a subsequence of *text*, else None.

    Higher score means a better match.  Case-insensitive.
    """
    if not pattern:
        return 0

    tl = text.lower()
    pl = pattern.lower()

    # Walk forward through text collecting match positions.
    positions: list[int] = []
    pi = 0
    for ti, ch in enumerate(tl):
        if ch == pl[pi]:
            positions.append(ti)
            pi += 1
            if pi == len(pl):
                break

    if pi < len(pl):
        return None  # pattern is not a subsequence

    score = 0

    # Consecutive-run bonus: each additional consecutive character adds more.
    run = 1
    for i in range(1, len(positions)):
        if positions[i] == positions[i - 1] + 1:
            run += 1
            score += run * 10
        else:
            run = 1

    # Boundary bonus: match at start of string or after a separator.
    for pos in positions:
        if pos == 0 or text[pos - 1] in _SEPARATORS:
            score += 20

    # Prefer tight matches (small span).
    score -= positions[-1] - positions[0]

    # Prefer shorter strings as a tiebreaker.
    score -= len(text) // 4

    return score


def fuzzy_filter(strings: Iterable[str], pattern: str) -> list[str]:
    """Return the subset of *strings* that contain *pattern* as a subsequence.

    Results are sorted best-match first.  An empty pattern returns all strings
    unchanged.
    """
    if not pattern:
        return sorted(list(strings))

    scored: list[tuple[int, str]] = []
    for s in strings:
        sc = _score(s, pattern)
        if sc is not None:
            scored.append((sc, s))

    scored.sort(key=lambda t: (-t[0], t[1]))
    return [s for _, s in scored]


def fuzzy_highlight(text: str, pattern: str) -> str:
    """Return *text* as an HTML fragment with matched chars wrapped in ``<b>``.

    Consecutive matched characters are merged into a single ``<b>`` run.
    All characters are HTML-escaped.  Returns plain escaped text when
    *pattern* is empty or is not a subsequence of *text*.
    """
    if not pattern:
        return _html.escape(text)

    tl = text.lower()
    pl = pattern.lower()

    matched: set[int] = set()
    pi = 0
    for ti, ch in enumerate(tl):
        if pi < len(pl) and ch == pl[pi]:
            matched.add(ti)
            pi += 1
            if pi == len(pl):
                break

    if pi < len(pl):
        return _html.escape(text)

    parts: list[str] = []
    in_bold = False
    for i, ch in enumerate(text):
        if i in matched:
            if not in_bold:
                parts.append("<b>")
                in_bold = True
        else:
            if in_bold:
                parts.append("</b>")
                in_bold = False
        parts.append(_html.escape(ch))
    if in_bold:
        parts.append("</b>")

    return "".join(parts)
