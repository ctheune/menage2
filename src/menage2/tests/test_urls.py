"""What a link's label looks like when it is made from the URL itself."""

import pytest

from menage2.urls import DEFAULT_LABEL_LENGTH, shorten_url

# ---------------------------------------------------------------------------
# What gets dropped
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url, expected",
    [
        # The scheme says nothing about where a link goes.
        ("https://example.com/page", "example.com/page"),
        ("http://example.com/page", "example.com/page"),
        ("example.com/page", "example.com/page"),
        # Neither does `www.`, and it costs four characters.
        ("https://www.example.com/page", "example.com/page"),
        # A host that merely starts with "www" keeps its name.
        ("https://wwwomatic.example.com", "wwwomatic.example.com"),
        # The query string is usually where the length comes from.
        ("https://example.com/page?utm_source=newsletter&ref=x", "example.com/page"),
        ("https://example.com/?q=1", "example.com"),
        # As is the fragment.
        ("https://example.com/page#section-4", "example.com/page"),
        # Credentials and ports are plumbing.
        ("https://user:secret@example.com/page", "example.com/page"),
        ("https://example.com:8443/page", "example.com/page"),
        # A trailing slash is noise.
        ("https://example.com/page/", "example.com/page"),
        ("https://example.com/", "example.com"),
        # Empty path segments collapse.
        ("https://example.com//a//b", "example.com/a/b"),
    ],
)
def test_the_unimportant_parts_go(url, expected):
    assert shorten_url(url) == expected


# ---------------------------------------------------------------------------
# What survives when it does not all fit
# ---------------------------------------------------------------------------


def test_a_short_url_is_left_alone():
    assert shorten_url("https://example.com/a/b/c") == "example.com/a/b/c"


def test_the_front_of_the_path_gives_way_first():
    """The last segments name the thing; the first ones are filing."""
    url = "https://example.com/blog/archive/2024/january/hello-world"
    # "blog/archive" is enough to give way — it stops as soon as it fits,
    # rather than throwing away path it did not need to.
    assert shorten_url(url) == "example.com/…/2024/january/hello-world"


def test_it_keeps_dropping_until_it_fits():
    url = "https://example.com/a/b/c/d/e/some-fairly-long-final-segment"
    # Even with every leading segment gone this one does not fit, so the
    # last segment is cut too.
    assert shorten_url(url) == "example.com/…/some-fairly-long-final-se…"
    assert len(shorten_url(url)) == DEFAULT_LABEL_LENGTH


def test_a_single_long_segment_is_cut_at_the_end():
    """Nothing left to drop, so the slug itself gives way — from the end,
    where a slug says least."""
    url = "https://example.com/this-is-a-very-long-slug-indeed-it-is"
    result = shorten_url(url)
    assert len(result) == DEFAULT_LABEL_LENGTH
    assert result.startswith("example.com/this-is-a-very-long-slug")
    assert result.endswith("…")


def test_a_host_too_long_on_its_own_keeps_its_tail():
    """What identifies a host is the end of it, not the start."""
    host = "a-really-quite-unreasonably-long-subdomain.example.com"
    result = shorten_url(f"https://{host}/page")
    assert len(result) == DEFAULT_LABEL_LENGTH
    assert result.endswith("example.com")
    assert result.startswith("…")


def test_the_limit_is_honoured_for_every_shape():
    urls = [
        "https://example.com",
        "https://example.com/a/b/c/d/e/f/g/h/i/j/k/l/m/n/o/p/q/r/s/t/u/v",
        "https://sub.domain.example.co.uk/very/deep/path/to/a/particular/thing",
        "https://" + "x" * 300,
        "https://example.com/" + "y" * 300,
        "mailto:" + "z" * 300 + "@example.com",
        "obsidian://open?vault=" + "V" * 300 + "&file=" + "F" * 300,
        "obsidian://open?vault=Notes&file=" + "/".join("part" for _ in range(50)),
    ]
    for limit in (5, 10, 20, 40, 80):
        for url in urls:
            assert len(shorten_url(url, limit)) <= limit, (url, limit)


# ---------------------------------------------------------------------------
# Schemes that are not the web
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url, expected",
    [
        # Who it goes to is the whole of what the link says; the scheme only
        # repeats what the symbol shows.
        ("mailto:someone@example.com", "✉ someone@example.com"),
        # The subject and the rest of the headers are not the address.
        ("mailto:a@b.com?subject=Hello%20there", "✉ a@b.com"),
        ("mailto:some%2Bone@example.com", "✉ some+one@example.com"),
        ("mailto:", "✉"),
    ],
)
def test_a_mail_link_is_the_address(url, expected):
    assert shorten_url(url) == expected


@pytest.mark.parametrize(
    "url, expected",
    [
        # The vault and the file are the two things worth knowing.
        ("obsidian://open?vault=Notes&file=Inbox", "📝 Notes/Inbox"),
        ("obsidian://open?vault=Notes&file=Inbox/Today", "📝 Notes/Inbox/Today"),
        ("obsidian://open?vault=Notes&file=A%20Note", "📝 Notes/A Note"),
        # Older and alternate spellings of the same thing.
        ("obsidian://open?vault=Notes&filepath=Inbox", "📝 Notes/Inbox"),
        # A vault on its own still says where it went.
        ("obsidian://open?vault=Notes", "📝 Notes"),
    ],
)
def test_an_obsidian_link_is_its_vault_and_file(url, expected):
    assert shorten_url(url) == expected


def test_a_long_obsidian_path_keeps_its_end():
    url = "obsidian://open?vault=Work&file=Projects/2024/Q1/the-one-that-matters"
    result = shorten_url(url)
    assert len(result) <= DEFAULT_LABEL_LENGTH
    assert result.startswith("📝 Work/…/")
    assert result.endswith("the-one-that-matters")


def test_a_scheme_we_cannot_read_is_kept_whole():
    """Better a URL nobody shortened than one shortened wrongly."""
    assert shorten_url("file:///etc/hosts") == "file:///etc/hosts"
    # Not an obsidian URL we recognise the shape of.
    assert shorten_url("obsidian://search?q=x") == "obsidian://search?q=x"


def test_a_scheme_we_cannot_read_is_still_cut_to_the_limit():
    result = shorten_url("zoommtg://zoom.us/join?confno=" + "9" * 100)
    assert len(result) == DEFAULT_LABEL_LENGTH
    assert result.startswith("zoommtg://zoom.us/join?confno=")


# ---------------------------------------------------------------------------
# Nothing to shorten
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("url", ["", "   ", None])
def test_nothing_in_nothing_out(url):
    assert shorten_url(url) == ""


def test_surrounding_space_is_ignored():
    assert shorten_url("  https://example.com/page  ") == "example.com/page"


def test_a_path_without_a_host_is_still_readable():
    assert shorten_url("/notes/today.md") == "notes/today.md"


@pytest.mark.parametrize("limit", [0, -1])
def test_no_room_means_no_label(limit):
    assert shorten_url("https://example.com", limit) == ""
