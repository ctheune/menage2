"""Browser tests for the CompositeInput widget in isolation.

Tests run against /admin/composite-playground which hosts the widget
without any HTMX side-effects. The #pg-full-textarea reflects the
hidden-input canonical string every 100 ms, giving a simple assertion target.
"""

import re

import pytest

from ._browser_helpers import fill_composite


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, live_server):
    return {
        **browser_context_args,
        "base_url": live_server,
        "viewport": {"width": 1024, "height": 768},
    }


@pytest.fixture(autouse=True)
def login(page, context, browser_admin_user, live_server):
    resp = context.request.post(
        f"{live_server}/login",
        form={
            "username": browser_admin_user["username"],
            "password": browser_admin_user["password"],
            "came_from": "/admin/composite-playground",
        },
        max_redirects=0,
    )
    assert resp.status == 303
    cookie_part = resp.headers.get("set-cookie", "").split(";")[0]
    name, value = cookie_part.split("=", 1)
    context.add_cookies(
        [
            {
                "name": name.strip(),
                "value": value.strip(),
                "domain": "localhost",
                "path": "/",
            }
        ]
    )


@pytest.fixture(autouse=True)
def goto_playground(page, login):
    page.goto("/admin/composite-playground")
    page.wait_for_load_state("networkidle")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seg(page):
    """First text segment of the full composite input."""
    return page.locator("#pg-full-ci .todo-text-seg").first


def _canonical(page) -> str:
    """Current canonical value reflected in the playground textarea (waits for interval)."""
    page.wait_for_timeout(200)
    return page.locator("#pg-full-textarea").input_value()


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


def test_input_is_contenteditable(page):
    assert _seg(page).get_attribute("contenteditable") == "true"


def test_placeholder_shown_when_empty(page):
    assert _seg(page).get_attribute("data-placeholder") is not None
    assert page.locator("#pg-full-ci .todo-text-seg.todo-input-empty").count() == 1


# ---------------------------------------------------------------------------
# Tag pills
# ---------------------------------------------------------------------------


def test_tag_pill_renders(page):
    _seg(page).press_sequentially("pizza #ctag123")
    _seg(page).press("Space")
    page.wait_for_function(
        "document.querySelector('#pg-full-ci .todo-tag-pill[data-tag=\"ctag123\"]') !== null",
        timeout=2000,
    )
    assert (
        "ctag123"
        in page.locator(
            '#pg-full-ci .todo-tag-pill[data-tag="ctag123"]'
        ).first.inner_text()
    )


def test_tag_conversion_single_space(page):
    _seg(page).press_sequentially("abc #deftag")
    _seg(page).press("Space")
    page.wait_for_selector(
        "#pg-full-ci .todo-tag-pill[data-tag='deftag']", timeout=2000
    )
    first_text = page.evaluate(
        "() => { var s = document.querySelector('#pg-full-ci .todo-text-seg'); return s ? s.textContent : ''; }"
    )
    assert first_text == "abc ", f"expected 'abc ', got {first_text!r}"

    # No trailing space before tag
    page.reload()
    page.wait_for_load_state("networkidle")
    _seg(page).press_sequentially("xyz#notrail")
    _seg(page).press("Space")
    page.wait_for_selector(
        "#pg-full-ci .todo-tag-pill[data-tag='notrail']", timeout=2000
    )
    first_text2 = page.evaluate(
        "() => { var s = document.querySelector('#pg-full-ci .todo-text-seg'); return s ? s.textContent : ''; }"
    )
    assert first_text2 == "xyz ", f"expected 'xyz ', got {first_text2!r}"


def test_backspace_removes_pill(page):
    _seg(page).press_sequentially("rm test #xtag456")
    _seg(page).press("Space")
    page.wait_for_function(
        "document.querySelector('#pg-full-ci .todo-tag-pill[data-tag=\"xtag456\"]') !== null",
        timeout=2000,
    )
    page.keyboard.press("Backspace")
    page.wait_for_function(
        "document.querySelector('#pg-full-ci .todo-tag-pill[data-tag=\"xtag456\"]') === null",
        timeout=2000,
    )
    assert page.locator('#pg-full-ci .todo-tag-pill[data-tag="xtag456"]').count() == 0


# ---------------------------------------------------------------------------
# Date picker (^ shortcut)
# ---------------------------------------------------------------------------


def test_caret_opens_date_picker_and_sets_canonical(page):
    _seg(page).fill("hello ")
    _seg(page).press("^")
    page.wait_for_selector(".todo-popover[data-role='date-picker']", timeout=2000)
    page.click("text=Today")
    page.wait_for_selector("#pg-full-ci .todo-date-pill", timeout=2000)
    assert re.search(r"\^202\d-\d\d-\d\d", _canonical(page))


def test_date_pill_preserves_existing_text(page):
    _seg(page).click()
    page.keyboard.type("Walk the dog")
    _seg(page).press("^")
    page.wait_for_selector(".todo-popover[data-role='date-picker']", timeout=2000)
    page.click("text=Today")
    page.wait_for_selector("#pg-full-ci .todo-date-pill", timeout=2000)
    assert "Walk the dog" in _seg(page).inner_text()


def test_pill_click_reopens_date_picker(page):
    _seg(page).press("^")
    page.wait_for_selector(".todo-popover[data-role='date-picker']")
    page.click("text=Today")
    page.wait_for_selector("#pg-full-ci .todo-date-pill")
    page.locator("#pg-full-ci .todo-date-pill").click()
    page.wait_for_selector(".todo-popover[data-role='date-picker']", timeout=2000)
    assert page.locator(".todo-popover[data-role='date-picker']").is_visible()


# ---------------------------------------------------------------------------
# Recurrence picker (* shortcut)
# ---------------------------------------------------------------------------


def test_star_opens_recurrence_picker_and_sets_canonical(page):
    _seg(page).fill("Water plants ")
    page.locator("#pg-full-ci .todo-text-seg").last.press("*")
    page.wait_for_selector(".todo-popover[data-role='recurrence-picker']", timeout=2000)
    page.click("text=every week")
    page.wait_for_selector("#pg-full-ci .todo-rec-pill", timeout=2000)
    assert "*" in _canonical(page)


def test_rec_pill_preserves_existing_text(page):
    _seg(page).click()
    page.keyboard.type("Daily standup")
    _seg(page).press("*")
    page.wait_for_selector(".todo-popover[data-role='recurrence-picker']", timeout=2000)
    page.click("text=every day")
    page.wait_for_selector("#pg-full-ci .todo-rec-pill", timeout=2000)
    assert "Daily standup" in _seg(page).inner_text()


# ---------------------------------------------------------------------------
# Note popover (~ shortcut)
# ---------------------------------------------------------------------------


def test_tilde_opens_note_popover_and_sets_canonical(page):
    _seg(page).click()
    page.keyboard.type("Feed the cat")
    _seg(page).press("~")
    page.wait_for_selector(".todo-note-popover", timeout=2000)
    page.fill(".todo-note-popover input", "dry food only")
    page.keyboard.press("Enter")
    page.wait_for_selector("#pg-full-ci .todo-note-pill", timeout=2000)
    assert "Feed the cat" in _seg(page).inner_text()
    assert "~dry food only" in _canonical(page)


# ---------------------------------------------------------------------------
# Link picker ([ shortcut)
# ---------------------------------------------------------------------------


def test_bracket_opens_link_picker(page):
    _seg(page).click()
    page.keyboard.type("Check docs ")
    _seg(page).press("[")
    page.wait_for_selector(".todo-link-popover", timeout=2000)
    assert page.locator(".todo-link-popover").is_visible()


def test_link_pill_url_only(page):
    _seg(page).click()
    page.keyboard.type("Visit site ")
    _seg(page).press("[")
    page.wait_for_selector(".todo-link-popover", timeout=2000)
    page.locator(".todo-link-popover input").first.fill("https://example.com")
    page.keyboard.press("Enter")
    page.wait_for_selector("#pg-full-ci .todo-link-pill", timeout=2000)
    assert "[](https://example.com)" in _canonical(page)


def test_link_pill_with_label(page):
    _seg(page).click()
    page.keyboard.type("See ref ")
    _seg(page).press("[")
    page.wait_for_selector(".todo-link-popover", timeout=2000)
    inputs = page.locator(".todo-link-popover input")
    inputs.nth(0).fill("https://example.com")
    inputs.nth(1).fill("Docs")
    page.keyboard.press("Enter")
    page.wait_for_selector("#pg-full-ci .todo-link-pill", timeout=2000)
    pill = page.locator("#pg-full-ci .todo-link-pill").first
    assert "Docs" in pill.inner_text()
    assert "[Docs](https://example.com)" in _canonical(page)


def test_link_pill_remove(page):
    _seg(page).click()
    page.keyboard.type("Remove test ")
    _seg(page).press("[")
    page.wait_for_selector(".todo-link-popover", timeout=2000)
    page.locator(".todo-link-popover input").first.fill("https://example.com")
    page.keyboard.press("Enter")
    page.wait_for_selector("#pg-full-ci .todo-link-pill", timeout=2000)
    page.locator("#pg-full-ci .todo-link-remove").first.click()
    page.wait_for_function(
        "document.querySelectorAll('#pg-full-ci .todo-link-pill').length === 0",
        timeout=2000,
    )
    assert page.locator("#pg-full-ci .todo-link-pill").count() == 0


def test_link_picker_empty_url_stays_open(page):
    _seg(page).click()
    page.keyboard.type("Task ")
    _seg(page).press("[")
    page.wait_for_selector(".todo-link-popover", timeout=2000)
    # Leave URL empty and try to commit — popover should stay open
    page.keyboard.press("Enter")
    assert page.locator(".todo-link-popover").is_visible()


def test_link_pill_edit_reopens_picker(page):
    _seg(page).click()
    page.keyboard.type("Edit link test ")
    _seg(page).press("[")
    page.wait_for_selector(".todo-link-popover", timeout=2000)
    inputs = page.locator(".todo-link-popover input")
    inputs.nth(0).fill("https://original.com")
    inputs.nth(1).fill("Original")
    page.keyboard.press("Enter")
    page.wait_for_selector("#pg-full-ci .todo-link-pill", timeout=2000)
    # Click pill body (not the × button)
    page.locator("#pg-full-ci .todo-link-pill").first.click()
    page.wait_for_selector(".todo-link-popover", timeout=2000)
    # Existing URL should be pre-filled
    assert (
        page.locator(".todo-link-popover input").first.input_value()
        == "https://original.com"
    )


def test_link_cancel_closes_picker(page):
    _seg(page).click()
    page.keyboard.type("Cancel test ")
    _seg(page).press("[")
    page.wait_for_selector(".todo-link-popover", timeout=2000)
    page.locator(".todo-link-popover .btn-link").click()
    page.wait_for_function(
        "document.querySelectorAll('.todo-link-popover').length === 0",
        timeout=2000,
    )
    assert page.locator(".todo-link-pill").count() == 0


# ---------------------------------------------------------------------------
# Keyboard navigation
# ---------------------------------------------------------------------------


def test_cmd_left_right_boundary(page):
    _seg(page).press_sequentially("hello")
    _seg(page).press("^")
    page.wait_for_selector(".todo-popover[data-role='date-picker']", timeout=2000)
    page.click("text=Today")
    page.wait_for_selector("#pg-full-ci .todo-date-pill", timeout=2000)
    page.keyboard.press("Meta+ArrowLeft")
    assert page.evaluate(
        "() => { var ss = Array.from(document.querySelectorAll('#pg-full-ci .todo-text-seg')); "
        "return ss.length > 0 && document.activeElement === ss[0]; }"
    )
    page.keyboard.press("Meta+ArrowRight")
    assert page.evaluate(
        "() => { var ss = Array.from(document.querySelectorAll('#pg-full-ci .todo-text-seg')); "
        "return ss.length > 0 && document.activeElement === ss[ss.length - 1]; }"
    )


def test_cmd_a_selects_all_segs(page):
    _seg(page).press_sequentially("hello")
    _seg(page).press("^")
    page.wait_for_selector(".todo-popover[data-role='date-picker']", timeout=2000)
    page.click("text=Today")
    page.wait_for_selector("#pg-full-ci .todo-date-pill", timeout=2000)
    page.keyboard.press("Meta+a")
    sel = page.evaluate(
        "() => { var s = window.getSelection(); if (!s || !s.rangeCount) return {text:'',collapsed:true}; "
        "var r = s.getRangeAt(0); return {text: r.toString(), collapsed: r.collapsed}; }"
    )
    assert not sel["collapsed"]
    assert "hello" in sel["text"]


def test_arrow_right_navigates_past_pill(page):
    _seg(page).press_sequentially("asdf")
    _seg(page).press("^")
    page.wait_for_selector(".todo-popover[data-role='date-picker']", timeout=2000)
    page.click("text=Today")
    page.wait_for_selector("#pg-full-ci .todo-date-pill", timeout=2000)
    # Wait for renderAllPills() to finish rebuilding both text segs around the pill.
    page.wait_for_function(
        "document.querySelectorAll('#pg-full-ci .todo-text-seg').length >= 2",
        timeout=2000,
    )
    # Place cursor at exact end of first seg via JS, then navigate right.
    page.evaluate(
        """() => {
            var seg = document.querySelector('#pg-full-ci .todo-text-seg');
            seg.focus();
            var range = document.createRange();
            range.selectNodeContents(seg);
            range.collapse(false);
            var sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
        }"""
    )
    page.keyboard.press("ArrowRight")
    page.wait_for_function(
        "() => { var ss = Array.from(document.querySelectorAll('#pg-full-ci .todo-text-seg')); "
        "return ss.length > 1 && document.activeElement === ss[ss.length - 1]; }",
        timeout=2000,
    )


# ---------------------------------------------------------------------------
# @mention autocomplete (requires DB fixtures)
# ---------------------------------------------------------------------------


def test_at_mention_autocomplete_shows_users(page, second_user):
    _seg(page).click()
    page.keyboard.type("Fix bug @")
    page.keyboard.type("a")
    page.wait_for_timeout(600)
    dropdown = page.locator("#pg-full-ci .todo-tag-autocomplete")
    assert dropdown.is_visible()
    assert "alice" in dropdown.inner_text()


def test_at_mention_autocomplete_shows_teams(page, team_with_alice):
    _seg(page).click()
    page.keyboard.type("Clean @")
    page.keyboard.type("h")
    page.wait_for_timeout(600)
    dropdown = page.locator("#pg-full-ci .todo-tag-autocomplete")
    assert dropdown.is_visible()
    assert "house" in dropdown.inner_text()


def test_at_mention_space_completes_pill(page, second_user):
    _seg(page).click()
    page.keyboard.type("Walk dog @alice ")
    page.wait_for_timeout(200)
    pill = page.locator("#pg-full-ci .todo-assignee-pill")
    assert pill.count() >= 1
    assert "alice" in pill.first.inner_text()
