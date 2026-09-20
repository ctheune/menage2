"""Turning a URL into something worth reading.

A link entered without a label of its own gets one made from its URL. The
whole URL is no use on a badge in a list: most of its length is scheme,
tracking parameters and repetition, and the part that says where it actually
goes is buried in the middle.
"""

import re
from urllib.parse import parse_qs, unquote

#: What a label is trimmed to unless asked otherwise.
DEFAULT_LABEL_LENGTH = 40

#: One character wide, which is what makes the arithmetic below honest.
_ELLIPSIS = "…"

#: Stand-ins for a scheme that has been dropped. A label is stored and shown
#: as plain text, so this is a character rather than an icon element.
_MAIL_ICON = "✉"  # ✉
_NOTE_ICON = "\U0001f4dd"  # 📝

#: `scheme://rest`, or `scheme:rest` for the ones that carry no host.
_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.\-]*):(//)?")

#: Schemes whose host-and-path shape is worth taking apart.
_WEB_SCHEMES = {"", "http", "https"}


def _split_scheme(url: str) -> tuple[str, str]:
    """Split `url` into its scheme and everything after it."""
    match = _SCHEME_RE.match(url)
    if not match:
        return "", url
    return match.group(1).lower(), url[match.end() :]


def _clip(value: str, limit: int) -> str:
    """Cut `value` down to `limit`, marking where it was cut."""
    if len(value) <= limit:
        return value
    if limit <= 1:
        return value[:limit]
    return value[: limit - 1] + _ELLIPSIS


def _clip_front(value: str, limit: int) -> str:
    """Same, but keeping the end — what identifies a host is its tail."""
    if len(value) <= limit:
        return value
    if limit <= 1:
        return value[-limit:] if limit else ""
    return _ELLIPSIS + value[-(limit - 1) :]


def _fit(head: str, segments: list[str], limit: int) -> str:
    """`head` and as much of the end of `segments` as `limit` allows.

    The last segments are what name the thing being linked to, so they are
    the last to go; the ones in front are the site's own filing system.
    """
    if not head:
        return _clip("/".join(segments), limit)

    whole = "/".join([head, *segments])
    if len(whole) <= limit:
        return whole

    # Drop leading segments one at a time, stopping as soon as it fits, so
    # no more of the path is thrown away than has to be.
    for first in range(1, len(segments)):
        candidate = head + "/" + _ELLIPSIS + "/" + "/".join(segments[first:])
        if len(candidate) <= limit:
            return candidate

    # Down to the head and one segment, and still too long. The head says
    # more than a slug does, so the slug gives way — as long as enough of it
    # is left to read.
    if segments and len(head) + 5 <= limit:
        keep = limit - len(head) - 1
        if len(segments) > 1:
            keep -= 2  # the "…/" standing in for what was dropped
            return head + "/" + _ELLIPSIS + "/" + _clip(segments[-1], keep)
        return head + "/" + _clip(segments[-1], keep)

    return _clip_front(head, limit)


def _segments(path: str) -> list[str]:
    return [segment for segment in path.split("/") if segment]


def _mail_label(rest: str, limit: int) -> str:
    """`mailto:someone@example.com` → `✉ someone@example.com`.

    Who the mail goes to is the whole of what the link says; the scheme only
    repeats what the symbol already shows.
    """
    address = unquote(rest.split("?", 1)[0])
    if not address:
        return _MAIL_ICON
    return _MAIL_ICON + " " + _clip_front(address, max(limit - 2, 1))


def _note_label(rest: str, limit: int) -> str:
    """`obsidian://open?vault=Notes&file=Inbox/Today` → `📝 Notes/Inbox/Today`.

    The vault and the file are the two things worth knowing; everything else
    in these URLs is how the app is asked to open them.
    """
    query = rest.split("?", 1)[1] if "?" in rest else ""
    params = parse_qs(query)
    vault = (params.get("vault") or [""])[0]
    note = (params.get("file") or params.get("filepath") or params.get("path") or [""])[
        0
    ]
    if not vault and not note:
        return None
    room = max(limit - 2, 1)
    return _NOTE_ICON + " " + _fit(vault, _segments(note), room)


def shorten_url(url: str, limit: int = DEFAULT_LABEL_LENGTH) -> str:
    """A readable label for `url`, at most `limit` characters long.

    What survives, in the order of how much it says about where a link goes:
    the site it points at, then the end of the path — the last segment is
    usually the name of the thing — then as much of the middle as still fits.

    The scheme, a `www.` prefix, any credentials, the port, the query string
    and the fragment are all dropped: none of them help anyone recognise a
    link, and the query string is usually where the length comes from.

        >>> shorten_url("https://www.example.com/a/b/page?utm_source=x#top")
        'example.com/a/b/page'

    A scheme that is not the web gets read on its own terms, because there
    the scheme carries the meaning rather than the plumbing.

        >>> shorten_url("mailto:someone@example.com")
        '✉ someone@example.com'
    """
    url = (url or "").strip()
    if not url or limit <= 0:
        return ""

    scheme, rest = _split_scheme(url)

    if scheme == "mailto":
        return _mail_label(rest, limit)
    if scheme == "obsidian":
        note = _note_label(rest, limit)
        if note is not None:
            return note

    if scheme not in _WEB_SCHEMES:
        # Not one we know how to read: leave it as it stands rather than
        # take apart somebody else's URL and lose the part that mattered.
        return _clip(url.split("#", 1)[0], limit)

    rest = rest.split("#", 1)[0].split("?", 1)[0]
    host, _, path = rest.partition("/")
    host = host.rsplit("@", 1)[-1]  # credentials
    host = host.split(":", 1)[0]  # port
    if host.lower().startswith("www."):
        host = host[4:]

    return _fit(host, _segments(path), limit)
