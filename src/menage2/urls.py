"""Turning a URL into something worth reading.

A link entered without a label of its own gets one made from its URL. The
whole URL is no use on a badge in a list: most of its length is scheme,
tracking parameters and repetition, and the part that says where it actually
goes is buried in the middle.
"""

import re

#: What a label is trimmed to unless asked otherwise.
DEFAULT_LABEL_LENGTH = 40

#: One character wide, which is what makes the arithmetic below honest.
_ELLIPSIS = "…"

#: `scheme://rest`, or `scheme:rest` for the ones that carry no host.
_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.\-]*):(//)?")

#: Schemes worth taking apart into host and path. Any other one is kept as it
#: stands, because for `mailto:` or `obsidian:` the scheme is the part that
#: says what the link even is.
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
    """
    url = (url or "").strip()
    if not url or limit <= 0:
        return ""

    scheme, rest = _split_scheme(url)
    if scheme not in _WEB_SCHEMES:
        # Keep it as it stands: `mailto:someone@example.com` says more than
        # the address alone, and an app's URL is not ours to take apart.
        return _clip(url.split("#", 1)[0], limit)

    rest = rest.split("#", 1)[0].split("?", 1)[0]
    host, _, path = rest.partition("/")
    host = host.rsplit("@", 1)[-1]  # credentials
    host = host.split(":", 1)[0]  # port
    if host.lower().startswith("www."):
        host = host[4:]
    segments = [segment for segment in path.split("/") if segment]

    if not host:
        # Nothing but a path — a relative link, or a `file:` one.
        return _clip("/".join(segments), limit)

    whole = "/".join([host, *segments])
    if len(whole) <= limit:
        return whole

    # Drop path segments from the front, one at a time: the last ones name
    # the thing, the first ones are the site's own filing system.
    for first in range(1, len(segments)):
        candidate = host + "/" + _ELLIPSIS + "/" + "/".join(segments[first:])
        if len(candidate) <= limit:
            return candidate

    # Down to the host and one segment, and still too long. A host says more
    # than a slug does, so the slug gives way first — but only to the point
    # where a few characters of it are still readable.
    if segments and len(host) + 5 <= limit:
        keep = limit - len(host) - 1
        if len(segments) > 1:
            keep -= 2  # the "…/" standing in for what was dropped
            return host + "/" + _ELLIPSIS + "/" + _clip(segments[-1], keep)
        return host + "/" + _clip(segments[-1], keep)

    return _clip_front(host, limit)
