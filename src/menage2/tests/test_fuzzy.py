"""Tests for menage2.fuzzy — pure functions, no DB."""

import pytest

from menage2.fuzzy import fuzzy_filter, fuzzy_highlight

# --- Basic matching ---


def test_exact_match():
    assert fuzzy_filter(["apple"], "apple") == ["apple"]


def test_subsequence_match():
    assert "foobar" in fuzzy_filter(["foobar"], "fbr")


def test_non_match_excluded():
    assert fuzzy_filter(["hello"], "xyz") == []


def test_empty_pattern_returns_all():
    strings = ["alpha", "beta", "gamma"]
    assert fuzzy_filter(strings, "") == strings


def test_case_insensitive():
    assert fuzzy_filter(["FooBar"], "fb") == ["FooBar"]
    assert fuzzy_filter(["foobar"], "FB") == ["foobar"]


def test_pattern_longer_than_string():
    assert fuzzy_filter(["ab"], "abc") == []


def test_single_character_pattern():
    result = fuzzy_filter(["apple", "banana", "cherry"], "a")
    assert "apple" in result
    assert "banana" in result
    assert "cherry" not in result


def test_returns_only_matches():
    strings = ["foobar", "hello", "fizzbuzz", "world"]
    result = fuzzy_filter(strings, "fb")
    assert "foobar" in result
    assert "fizzbuzz" in result
    assert "hello" not in result
    assert "world" not in result


# --- Ordering ---


def test_consecutive_run_ranks_higher_than_scattered():
    # "abc" at positions 0,1,2 in "abcdef" vs scattered 0,2,4 in "axbxcx"
    result = fuzzy_filter(["axbxcx", "abcdef"], "abc")
    assert result.index("abcdef") < result.index("axbxcx")


def test_start_of_string_ranks_higher():
    # "foo" starting at 0 beats "foo" buried in the middle
    result = fuzzy_filter(["xyzfoo", "foobar"], "foo")
    assert result.index("foobar") < result.index("xyzfoo")


def test_boundary_match_ranks_higher():
    # "fb" matching at word boundary "foo-bar" beats mid-word "afoobar"
    result = fuzzy_filter(["afoobar", "foo-bar"], "fb")
    assert result.index("foo-bar") < result.index("afoobar")


def test_shorter_string_ranks_higher_when_otherwise_equal():
    # "ab" and "ab_extra" both match "ab" exactly — shorter wins
    result = fuzzy_filter(["ab_extra", "ab"], "ab")
    assert result.index("ab") < result.index("ab_extra")


def test_order_is_stable_for_unrelated_strings():
    strings = ["avocado", "apricot", "banana"]
    result = fuzzy_filter(strings, "a")
    # All three contain 'a'; we just care that the result is deterministic.
    assert sorted(result) == sorted(strings)


# --- Edge cases ---


def test_empty_list():
    assert fuzzy_filter([], "foo") == []


def test_empty_pattern_empty_list():
    assert fuzzy_filter([], "") == []


def test_pattern_equals_single_char_string():
    assert fuzzy_filter(["a"], "a") == ["a"]


def test_duplicate_characters_in_pattern():
    # "ll" requires two l's in order
    assert fuzzy_filter(["hello"], "ll") == ["hello"]
    assert fuzzy_filter(["helo"], "ll") == []


def test_segment_separators_all_trigger_boundary_bonus():
    candidates = [
        "a-b",  # hyphen
        "a_b",  # underscore
        "a:b",  # colon
        "a.b",  # dot
        "a/b",  # slash
        "a b",  # space
        "xab",  # no boundary
    ]
    result = fuzzy_filter(candidates, "ab")
    boundary_matches = ["a-b", "a_b", "a:b", "a.b", "a/b", "a b"]
    for bm in boundary_matches:
        assert result.index(bm) < result.index("xab")


# --- fuzzy_highlight ---


def test_highlight_wraps_matched_chars():
    assert fuzzy_highlight("foobar", "fb") == "<b>f</b>oo<b>b</b>ar"


def test_highlight_merges_consecutive_into_one_b_tag():
    assert fuzzy_highlight("foobar", "foo") == "<b>foo</b>bar"


def test_highlight_empty_pattern_returns_escaped_text():
    assert fuzzy_highlight("hello", "") == "hello"


def test_highlight_no_match_returns_escaped_text():
    assert fuzzy_highlight("hello", "xyz") == "hello"


def test_highlight_case_insensitive_preserves_original_case():
    result = fuzzy_highlight("FooBar", "fb")
    assert result == "<b>F</b>oo<b>B</b>ar"


def test_highlight_escapes_html_in_unmatched_chars():
    # '<' and '>' in unmatched region must be escaped
    assert fuzzy_highlight("a<b>c", "ac") == "<b>a</b>&lt;b&gt;<b>c</b>"


def test_highlight_escapes_html_in_matched_chars():
    assert fuzzy_highlight("<em>", "em") == "&lt;<b>em</b>&gt;"


def test_highlight_full_match_single_b_tag():
    assert fuzzy_highlight("abc", "abc") == "<b>abc</b>"


def test_highlight_single_char_pattern():
    assert fuzzy_highlight("hello", "h") == "<b>h</b>ello"


def test_highlight_match_at_end():
    assert fuzzy_highlight("foobar", "ar") == "foob<b>ar</b>"
