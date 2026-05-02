"""Browser tests for the todo feature."""

import pytest

from ._browser_helpers import fill_composite


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, live_server):
    return {
        **browser_context_args,
        "base_url": live_server,
        "viewport": {"width": 390, "height": 844},
    }


@pytest.fixture(autouse=True)
def login(page, context, browser_admin_user, live_server):
    resp = context.request.post(
        f"{live_server}/login",
        form={
            "username": browser_admin_user["username"],
            "password": browser_admin_user["password"],
            "came_from": "/todos",
        },
        max_redirects=0,
    )
    assert resp.status == 303, f"Login failed with HTTP {resp.status}"
    cookie_header = resp.headers.get("set-cookie", "")
    cookie_part = cookie_header.split(";")[0]
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


def _todo_ci(page):
    """Locator for the main todo composite input container."""
    return page.locator("#todo-text")


def _todo_seg(page):
    """First editable segment inside the main todo composite input."""
    return page.locator("#todo-text .todo-text-seg").first


def _add_todo(page, text: str) -> None:
    fill_composite(_todo_ci(page), text)
    page.wait_for_load_state("networkidle")


def _hover_and_blur(page, selector: str) -> None:
    """Hover an item and drop focus so document keydown fires."""
    page.hover(selector)
    page.evaluate(
        "document.activeElement && document.activeElement.blur && document.activeElement.blur()"
    )


# ---------------------------------------------------------------------------
# Basic todo creation
# ---------------------------------------------------------------------------


def test_add_todo_plain_text(page):
    page.goto("/todos")
    count_before = page.locator(".todo-item").count()
    _add_todo(page, "Buy bread")
    assert page.locator(".todo-item").count() == count_before + 1
    assert page.locator("text=Buy bread").first.is_visible()


def test_add_todo_with_inline_tag(page):
    page.goto("/todos")
    count_before = page.locator(".todo-item").count()
    _add_todo(page, "Buy bread #shopping")
    assert page.locator(".todo-item").count() == count_before + 1
    assert page.locator("text=Buy bread").first.is_visible()
    assert page.locator("text=shopping").count() >= 1


def test_add_todo_only_tags_shows_error(page):
    page.goto("/todos")
    fill_composite(_todo_ci(page), "#shopping")
    page.wait_for_selector("#error-toast", timeout=3000)
    assert page.locator("#error-toast").is_visible()


# ---------------------------------------------------------------------------
# Keyboard shortcuts on items
# ---------------------------------------------------------------------------


def _check_and_blur(page, nth=0):
    page.locator(".todo-checkbox").nth(nth).check()
    page.evaluate("document.activeElement.blur()")


def test_keyboard_c_marks_done(page):
    page.goto("/todos")
    _add_todo(page, "Keyboard test item")
    page.wait_for_selector(".todo-checkbox")
    count_before = page.locator(".todo-checkbox").count()
    _check_and_blur(page)
    page.keyboard.press("c")
    page.wait_for_function(
        f"document.querySelectorAll('.todo-checkbox').length < {count_before}",
        timeout=5000,
    )
    assert page.locator(".todo-checkbox").count() == count_before - 1


def test_undo_toast_appears_after_done(page):
    page.goto("/todos")
    _add_todo(page, "Undo test item")
    page.wait_for_selector(".todo-checkbox")
    _check_and_blur(page)
    page.keyboard.press("c")
    page.wait_for_selector("#undo-toast", timeout=3000)
    assert page.locator("#undo-toast").is_visible()


def test_undo_restores_item(page):
    page.goto("/todos")
    _add_todo(page, "Undo restore item")
    page.wait_for_selector(".todo-checkbox")
    count_before = page.locator(".todo-checkbox").count()
    _check_and_blur(page)
    page.keyboard.press("c")
    page.wait_for_function(
        f"document.querySelectorAll('.todo-checkbox').length < {count_before}",
        timeout=5000,
    )
    count_after = page.locator(".todo-checkbox").count()
    page.keyboard.press("u")
    page.wait_for_function(
        f"document.querySelectorAll('.todo-checkbox').length > {count_after}",
        timeout=5000,
    )
    assert page.locator(".todo-checkbox").count() >= count_before


def test_done_view_shows_completed_items(page):
    page.goto("/todos")
    _add_todo(page, "Done view test")
    page.wait_for_selector('.todo-item[data-todo-text="Done view test"]')
    count_before = page.locator(".todo-checkbox").count()
    page.locator(
        '.todo-item[data-todo-text="Done view test"] .todo-checkbox'
    ).first.check()
    page.evaluate("document.activeElement.blur()")
    page.keyboard.press("c")
    page.wait_for_function(
        f"document.querySelectorAll('.todo-checkbox').length < {count_before}",
        timeout=5000,
    )
    page.goto("/todos/done")
    assert page.locator("text=Done view test").count() >= 1


def test_d_key_opens_date_picker(page):
    page.goto("/todos")
    _add_todo(page, "Date picker subject")
    page.wait_for_selector('.todo-item[data-todo-text="Date picker subject"]')
    _hover_and_blur(page, '.todo-item[data-todo-text="Date picker subject"]')
    page.keyboard.press("d")
    page.wait_for_selector(".todo-popover[data-role='date-picker']", timeout=2000)
    assert page.locator(".todo-popover[data-role='date-picker']").is_visible()


def test_p_key_postpones_one_day(page):
    page.goto("/todos")
    _add_todo(page, "Postpone target")
    page.wait_for_selector('.todo-item[data-todo-text="Postpone target"]')
    _hover_and_blur(page, '.todo-item[data-todo-text="Postpone target"]')
    page.keyboard.press("p")
    page.wait_for_function(
        "document.querySelectorAll('.todo-item[data-todo-text=\\\"Postpone target\\\"]').length === 0",
        timeout=5000,
    )
    page.goto("/todos/scheduled")
    assert page.locator("text=Postpone target").count() >= 1


def test_shift_p_opens_postpone_palette(page):
    page.goto("/todos")
    _add_todo(page, "Palette target")
    page.wait_for_selector('.todo-item[data-todo-text="Palette target"]')
    _hover_and_blur(page, '.todo-item[data-todo-text="Palette target"]')
    page.keyboard.press("Shift+P")
    page.wait_for_selector(".todo-popover[data-role='postpone-palette']", timeout=2000)
    assert page.locator("text=+1 week").is_visible()


def test_h_key_puts_item_on_hold(page):
    page.goto("/todos")
    _add_todo(page, "Hold target")
    page.wait_for_selector('.todo-item[data-todo-text="Hold target"]')
    _hover_and_blur(page, '.todo-item[data-todo-text="Hold target"]')
    page.keyboard.press("h")
    page.wait_for_function(
        "document.querySelectorAll('.todo-item[data-todo-text=\\\"Hold target\\\"]').length === 0",
        timeout=5000,
    )
    page.goto("/todos/hold")
    assert page.locator("text=Hold target").count() >= 1


def test_picker_custom_input_has_live_preview(page):
    page.goto("/todos")
    _add_todo(page, "preview probe")
    page.wait_for_selector('.todo-item[data-todo-text="preview probe"]')
    _hover_and_blur(page, '.todo-item[data-todo-text="preview probe"]')
    page.keyboard.press("d")
    page.wait_for_selector(".todo-popover[data-role='date-picker'] input", timeout=2000)
    page.fill(".todo-popover input", "tomorrow")
    page.wait_for_function(
        "Array.from(document.querySelectorAll('.todo-popover-preview')).some(el => /tomorrow/i.test(el.textContent))",
        timeout=5000,
    )


# ---------------------------------------------------------------------------
# Swipe gestures
# ---------------------------------------------------------------------------


def test_swipe_right_marks_item_done(page):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto("/todos")
    _add_todo(page, "Swipe done item")
    page.wait_for_selector(".todo-item")
    count_before = page.locator(".todo-item").count()
    page.evaluate("""() => {
        const item = document.querySelector('.todo-item');
        if (!item) return;
        const touch = (x) => new Touch({identifier: 1, target: item, clientX: x, clientY: 100});
        item.dispatchEvent(new TouchEvent('touchstart', {touches: [touch(20)], bubbles: true}));
        item.dispatchEvent(new TouchEvent('touchmove',  {touches: [touch(160)], bubbles: true}));
        item.dispatchEvent(new TouchEvent('touchend',   {changedTouches: [touch(160)], bubbles: true}));
    }""")
    page.wait_for_function(
        f"document.querySelectorAll('.todo-item').length < {count_before}", timeout=5000
    )
    assert page.locator(".todo-item").count() == count_before - 1


def test_swipe_left_holds_item(page):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto("/todos")
    _add_todo(page, "Swipe hold item")
    page.wait_for_selector(".todo-item")
    count_before = page.locator(".todo-item").count()
    page.evaluate("""() => {
        const item = document.querySelector('.todo-item');
        if (!item) return;
        const touch = (x) => new Touch({identifier: 1, target: item, clientX: x, clientY: 100});
        item.dispatchEvent(new TouchEvent('touchstart', {touches: [touch(300)], bubbles: true}));
        item.dispatchEvent(new TouchEvent('touchmove',  {touches: [touch(150)], bubbles: true}));
        item.dispatchEvent(new TouchEvent('touchend',   {changedTouches: [touch(150)], bubbles: true}));
    }""")
    page.wait_for_function(
        f"document.querySelectorAll('.todo-item').length < {count_before}", timeout=5000
    )
    assert page.locator(".todo-item").count() == count_before - 1
    page.goto("/todos/hold")
    assert page.locator("text=Swipe hold item").count() >= 1


# ---------------------------------------------------------------------------
# Help overlay
# ---------------------------------------------------------------------------


def test_help_overlay_opens_with_question_mark(page):
    page.goto("/todos")
    page.keyboard.press("?")
    page.wait_for_selector("#kbd-help-overlay", state="visible", timeout=2000)
    assert page.locator("#kbd-help-overlay").is_visible()
    page.keyboard.press("Escape")
    page.wait_for_selector("#kbd-help-overlay", state="hidden", timeout=2000)


def test_help_overlay_works_on_scheduled_view(page):
    page.goto("/todos/scheduled")
    page.keyboard.press("?")
    page.wait_for_selector("#kbd-help-overlay", state="visible", timeout=2000)
    assert page.locator("#kbd-help-overlay").is_visible()


def test_help_overlay_works_on_done_view(page):
    page.goto("/todos/done")
    page.keyboard.press("?")
    page.wait_for_selector("#kbd-help-overlay", state="visible", timeout=2000)
    assert page.locator("#kbd-help-overlay").is_visible()


def test_help_overlay_persists_after_htmx_swap(page):
    page.goto("/todos")
    _add_todo(page, "after-swap probe")
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.keyboard.press("?")
    page.wait_for_selector("#kbd-help-overlay", state="visible", timeout=2000)


# ---------------------------------------------------------------------------
# Recurrence — full todo workflow (creation via picker + result verification)
# ---------------------------------------------------------------------------


def test_star_creates_recurring_todo(page):
    page.goto("/todos")
    _todo_seg(page).fill("Water plants ")
    page.locator("#todo-text .todo-text-seg").last.press("*")
    page.wait_for_selector(".todo-popover[data-role='recurrence-picker']", timeout=2000)
    page.click("text=every week")
    page.wait_for_selector(".todo-rec-pill", timeout=2000)
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")
    item = page.locator('.todo-item[data-todo-text="Water plants"]')
    assert item.count() == 1
    assert item.locator(".todo-recurrence").count() == 1


def test_f_key_opens_recurrence_picker_for_hovered(page):
    page.goto("/todos")
    _add_todo(page, "F-key target")
    page.wait_for_selector('.todo-item[data-todo-text="F-key target"]')
    _hover_and_blur(page, '.todo-item[data-todo-text="F-key target"]')
    page.keyboard.press("f")
    page.wait_for_selector(".todo-popover[data-role='recurrence-picker']", timeout=2000)
    assert page.locator(".todo-popover[data-role='recurrence-picker']").is_visible()


def test_recurrence_history_panel_opens_on_badge_click(page):
    page.goto("/todos")
    _todo_seg(page).fill("Yoga ")
    page.locator("#todo-text .todo-text-seg").last.press("*")
    page.wait_for_selector(".todo-popover[data-role='recurrence-picker']")
    page.click("text=every month")
    page.wait_for_selector(".todo-rec-pill")
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")
    page.locator('.todo-item[data-todo-text="Yoga"] .todo-recurrence').click()
    page.wait_for_selector(".todo-history-panel", timeout=2000)
    assert page.locator(".todo-history-entry").count() >= 1


def test_recurrence_label_visible_on_row(page):
    page.goto("/todos")
    _todo_seg(page).fill("rule label vis ")
    page.locator("#todo-text .todo-text-seg").last.press("*")
    page.wait_for_selector(".todo-popover[data-role='recurrence-picker']")
    page.click("text=every month")
    page.wait_for_selector(".todo-rec-pill")
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")
    label = page.locator(
        '.todo-item[data-todo-text="rule label vis"] .todo-recurrence-label'
    )
    assert label.count() == 1
    assert "every month" in label.first.inner_text()


def test_e_key_opens_edit_with_rec_pill(page):
    page.goto("/todos")
    _todo_seg(page).fill("ekey rec ")
    page.locator("#todo-text .todo-text-seg").last.press("*")
    page.wait_for_selector(".todo-popover[data-role='recurrence-picker']")
    page.click("text=every week")
    page.wait_for_selector(".todo-rec-pill")
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")
    _hover_and_blur(page, '.todo-item[data-todo-text="ekey rec"]')
    page.keyboard.press("e")
    page.wait_for_selector(".todo-rec-pill", timeout=2000)
    assert "every week" in page.locator(".todo-rec-pill").first.inner_text()


def test_recurrence_picker_custom_input_preview(page):
    page.goto("/todos")
    _add_todo(page, "preview rec")
    _hover_and_blur(page, '.todo-item[data-todo-text="preview rec"]')
    page.keyboard.press("f")
    page.wait_for_selector(
        ".todo-popover[data-role='recurrence-picker'] input", timeout=2000
    )
    page.fill(".todo-popover input", "every wednesday")
    page.wait_for_function(
        "Array.from(document.querySelectorAll('.todo-popover-preview')).some(el => /wednesday/i.test(el.textContent))",
        timeout=5000,
    )


# ---------------------------------------------------------------------------
# Scheduling — dated todos
# ---------------------------------------------------------------------------


def test_scheduled_view_shows_recurrence_badge(page):
    page.goto("/todos")
    _todo_seg(page).fill("Cosmetics check ")
    page.locator("#todo-text .todo-text-seg").last.press("^")
    page.wait_for_selector(".todo-popover[data-role='date-picker']")
    page.click("text=+1 week")
    page.wait_for_selector(".todo-date-pill")
    page.locator("#todo-text .todo-text-seg").last.press("*")
    page.wait_for_selector(".todo-popover[data-role='recurrence-picker']")
    page.click("text=every month")
    page.wait_for_selector(".todo-rec-pill")
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")
    page.goto("/todos/scheduled")
    item = page.locator('.todo-item[data-todo-text="Cosmetics check"]')
    assert item.count() == 1
    assert item.locator(".todo-recurrence").count() == 1
    item.locator(".todo-recurrence").click()
    page.wait_for_selector(".todo-history-panel", timeout=2000)


def test_scheduled_view_can_edit_item(page):
    page.goto("/todos")
    _todo_seg(page).fill("scheduled item ")
    page.locator("#todo-text .todo-text-seg").last.press("^")
    page.wait_for_selector(".todo-popover[data-role='date-picker']")
    page.click("text=+1 week")
    page.wait_for_selector(".todo-date-pill")
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")
    page.goto("/todos/scheduled")
    page.wait_for_selector('.todo-item[data-todo-text="scheduled item"]')
    page.locator('.todo-item[data-todo-text="scheduled item"] .todo-edit-btn').click()
    page.wait_for_selector("#todo-tag-input.todo-tag-input--editing", timeout=2000)
    _todo_seg(page).fill("scheduled item edited")
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")
    assert "/todos/scheduled" in page.url
    assert (
        page.locator('.todo-item[data-todo-text="scheduled item edited"]').count() == 1
    )


def test_scheduled_view_edit_loads_rec_pill(page):
    page.goto("/todos")
    _todo_seg(page).fill("Inventory check ")
    page.locator("#todo-text .todo-text-seg").last.press("^")
    page.wait_for_selector(".todo-popover[data-role='date-picker']")
    page.click("text=+1 week")
    page.wait_for_selector(".todo-date-pill")
    page.locator("#todo-text .todo-text-seg").last.press("*")
    page.wait_for_selector(".todo-popover[data-role='recurrence-picker']")
    page.click("text=every week")
    page.wait_for_selector(".todo-rec-pill")
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")
    page.goto("/todos/scheduled")
    page.locator('.todo-item[data-todo-text="Inventory check"] .todo-edit-btn').click()
    page.wait_for_selector(".todo-rec-pill", timeout=2000)
    assert "every week" in page.locator(".todo-rec-pill").first.inner_text()


# ---------------------------------------------------------------------------
# Edit mode — duplicate prevention
# ---------------------------------------------------------------------------


def test_edit_mode_shows_title_then_rec_pill(page):
    page.goto("/todos")
    _todo_seg(page).press_sequentially("edit order test ")
    _todo_seg(page).press("*")
    page.wait_for_selector(".todo-popover[data-role='recurrence-picker']")
    page.click("text=every week")
    page.wait_for_selector(".todo-rec-pill")
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")
    page.locator('.todo-item[data-todo-text="edit order test"] .todo-edit-btn').click()
    page.wait_for_selector("#todo-tag-input.todo-tag-input--editing", timeout=2000)
    first_has_title = page.evaluate(
        "() => { var s = document.querySelector('#todo-text .todo-text-seg'); "
        "return s !== null && (s.textContent === 'edit order test' || s.textContent === 'edit order test '); }"
    )
    assert first_has_title
    assert page.locator("#todo-text .todo-rec-pill").count() == 1


def test_active_view_edit_does_not_create_duplicate(page):
    page.goto("/todos")
    _add_todo(page, "no dup active")
    page.wait_for_selector('.todo-item[data-todo-text="no dup active"]')
    count_before = page.locator(".todo-item").count()
    page.locator('.todo-item[data-todo-text="no dup active"] .todo-edit-btn').click()
    page.wait_for_selector("#todo-tag-input.todo-tag-input--editing", timeout=2000)
    _todo_seg(page).click()
    page.keyboard.press("Meta+a")
    page.keyboard.type("no dup active edited")
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")
    page.goto("/todos")
    assert page.locator(".todo-item").count() == count_before
    assert page.locator('.todo-item[data-todo-text="no dup active"]').count() == 0
    assert (
        page.locator('.todo-item[data-todo-text="no dup active edited"]').count() == 1
    )


def test_scheduled_view_edit_does_not_create_duplicate(page):
    page.goto("/todos")
    _todo_seg(page).fill("no dup scheduled ")
    page.locator("#todo-text .todo-text-seg").last.press("^")
    page.wait_for_selector(".todo-popover[data-role='date-picker']")
    page.click("text=+1 week")
    page.wait_for_selector(".todo-date-pill")
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")
    page.goto("/todos/scheduled")
    page.wait_for_selector('.todo-item[data-todo-text="no dup scheduled"]')
    count_before = page.locator(".todo-item").count()
    page.locator('.todo-item[data-todo-text="no dup scheduled"] .todo-edit-btn').click()
    page.wait_for_selector("#todo-tag-input.todo-tag-input--editing", timeout=2000)
    _todo_seg(page).fill("no dup scheduled edited")
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")
    page.goto("/todos/scheduled")
    assert page.locator(".todo-item").count() == count_before
    assert page.locator('.todo-item[data-todo-text="no dup scheduled"]').count() == 0
    assert (
        page.locator('.todo-item[data-todo-text="no dup scheduled edited"]').count()
        == 1
    )


# ---------------------------------------------------------------------------
# Link badges — end-to-end
# ---------------------------------------------------------------------------


def _add_todo_with_link(page, text: str, url: str, label: str = "") -> None:
    """Add a todo item using the composite input with a link pill attached."""
    seg = _todo_seg(page)
    seg.fill(text + " ")
    page.locator("#todo-text .todo-text-seg").last.press("[")
    page.wait_for_selector(".todo-link-popover", timeout=2000)
    page.locator(".todo-link-popover input").first.fill(url)
    if label:
        page.locator(".todo-link-popover input").nth(1).fill(label)
    page.locator(".todo-link-popover .btn-dark").click()
    page.wait_for_selector("#todo-text .todo-link-pill", timeout=2000)
    page.locator("#todo-text .todo-text-seg").last.press("Enter")
    page.wait_for_load_state("networkidle")


def test_add_todo_with_link_shows_badge(page):
    page.goto("/todos")
    _add_todo_with_link(page, "Read article", "https://example.com", "Example")
    item = page.locator('.todo-item[data-todo-text="Read article"]')
    assert item.count() == 1
    badge = item.locator(".todo-link-badge")
    assert badge.count() == 1
    assert badge.get_attribute("href") == "https://example.com"


def test_add_todo_with_link_badge_shows_label(page):
    page.goto("/todos")
    _add_todo_with_link(page, "Link label test", "https://example.org", "Org Site")
    item = page.locator('.todo-item[data-todo-text="Link label test"]')
    badge = item.locator(".todo-link-badge")
    assert "Org Site" in badge.inner_text()


def test_edit_todo_restores_link_pill(page):
    page.goto("/todos")
    _add_todo_with_link(
        page, "Edit link restore", "https://restore.example.com", "Restore"
    )
    page.wait_for_selector('.todo-item[data-todo-text="Edit link restore"]')
    page.locator(
        '.todo-item[data-todo-text="Edit link restore"] .todo-edit-btn'
    ).click()
    page.wait_for_selector("#todo-tag-input.todo-tag-input--editing", timeout=2000)
    # Link pill should be restored in composite input
    pill = page.locator("#todo-text .todo-link-pill")
    assert pill.count() == 1
    assert "Restore" in pill.first.inner_text()


# ---------------------------------------------------------------------------
# Quick-pick chip visibility
# ---------------------------------------------------------------------------


def _quick_pick(page):
    return page.locator("#todo-quick-pick")


def _seed_and_show_chips(page):
    """Add a tagged todo so top-tags has data, focus the composite, wait for chips."""
    page.goto("/todos")
    _add_todo(page, "seed task #groceries")
    # Explicitly click the seg: if auto-focus already ran, this is a no-op for
    # focusin; either way renderQuickPick will have been called with a fresh fetch.
    _todo_seg(page).click()
    page.wait_for_selector("#todo-quick-pick button", timeout=5000)


def test_quickpick_shows_on_focus(page, browser_admin_user):
    _seed_and_show_chips(page)
    assert _quick_pick(page).is_visible()


def test_quickpick_hides_on_tab(page, browser_admin_user):
    """Tab moves focus outside the form — chips must disappear."""
    _seed_and_show_chips(page)
    page.keyboard.press("Tab")
    page.wait_for_timeout(50)
    assert not _quick_pick(page).is_visible()


def test_quickpick_hides_on_click_elsewhere(page, browser_admin_user):
    """Clicking a non-focusable element outside the form must hide chips."""
    _seed_and_show_chips(page)
    # Click somewhere in the body below the form (the todo-list area).
    page.mouse.click(200, 500)
    page.wait_for_timeout(50)
    assert not _quick_pick(page).is_visible()


def test_quickpick_hides_on_url_bar_blur(page, browser_admin_user):
    """Blurring the document active element (as when clicking the URL bar) hides chips."""
    _seed_and_show_chips(page)
    page.evaluate("document.activeElement?.blur()")
    page.wait_for_timeout(50)
    assert not _quick_pick(page).is_visible()
