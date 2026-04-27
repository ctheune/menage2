"""Browser-based tests for the todo feature.

The test server (port 6544) must be running — `devenv up` starts it automatically.
Run with: uv run pytest src/menage2/tests/test_todos_browser.py
"""

import pytest


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, live_server):
    """Set base_url and viewport for all browser tests."""
    return {
        **browser_context_args,
        "base_url": live_server,
        "viewport": {"width": 390, "height": 844},
    }


@pytest.fixture(autouse=True)
def login(page, context, browser_admin_user, live_server):
    """Insert admin, inject session cookie before each browser test."""
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


def _first_seg(page):
    """Return a locator for the first editable text segment inside #todo-text."""
    return page.locator("#todo-text .todo-text-seg").first


def _add_todo(page, text):
    _first_seg(page).fill(text)
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")


def test_add_todo_plain_text(page):
    """Typing plain text and pressing Enter creates a todo."""
    page.goto("/todos")
    count_before = page.locator(".todo-item").count()
    _add_todo(page, "Buy bread")
    assert page.locator(".todo-item").count() == count_before + 1
    assert page.locator("text=Buy bread").first.is_visible()


def test_add_todo_with_inline_tag(page):
    """A #tag followed by space is extracted as a pill; remaining text becomes the todo."""
    page.goto("/todos")
    count_before = page.locator(".todo-item").count()
    _first_seg(page).fill("Buy bread #shopping ")
    page.wait_for_timeout(100)
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")
    assert page.locator(".todo-item").count() == count_before + 1
    assert page.locator("text=Buy bread").first.is_visible()
    assert page.locator("text=shopping").count() >= 1


def test_add_todo_only_tags_shows_error(page):
    """Submitting only a tag (no text) shows the error toast, not a new todo."""
    page.goto("/todos")
    _first_seg(page).fill("#shopping ")
    page.wait_for_timeout(100)
    page.keyboard.press("Enter")
    page.wait_for_selector("#error-toast", timeout=3000)
    assert page.locator("#error-toast").is_visible()


def _check_and_blur(page, nth=0):
    page.locator(".todo-checkbox").nth(nth).check()
    page.evaluate("document.activeElement.blur()")


def test_keyboard_c_single_item_marks_done(page):
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


def test_undo_with_u_key_restores_item(page):
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
    count_after_done = page.locator(".todo-checkbox").count()
    page.keyboard.press("u")
    page.wait_for_function(
        f"document.querySelectorAll('.todo-checkbox').length > {count_after_done}",
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
        item.dispatchEvent(new TouchEvent('touchmove', {touches: [touch(160)], bubbles: true}));
        item.dispatchEvent(new TouchEvent('touchend', {changedTouches: [touch(160)], bubbles: true}));
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
        item.dispatchEvent(new TouchEvent('touchmove', {touches: [touch(150)], bubbles: true}));
        item.dispatchEvent(new TouchEvent('touchend', {changedTouches: [touch(150)], bubbles: true}));
    }""")
    page.wait_for_function(
        f"document.querySelectorAll('.todo-item').length < {count_before}", timeout=5000
    )
    assert page.locator(".todo-item").count() == count_before - 1
    assert page.locator("text=On hold").first.is_visible()


# ---------------------------------------------------------------------------
# Scheduling — due date feature
# ---------------------------------------------------------------------------


def _hover_and_blur(page, selector):
    """Move pointer onto an item AND drop input focus so document keydown fires."""
    page.hover(selector)
    page.evaluate(
        "document.activeElement && document.activeElement.blur && document.activeElement.blur()"
    )


def test_caret_opens_picker_and_adds_pill(page):
    """Typing ^ in the composite input pops the picker; selecting a chip
    inserts an editable date pill, and submitting attaches the due date."""
    page.goto("/todos")
    _first_seg(page).fill("Buy bread ")
    # Type ^ as a single keystroke so the input handler sees it.
    _first_seg(page).press("^")
    page.wait_for_selector(".todo-popover[data-role='date-picker']", timeout=2000)
    page.click("text=Today")
    # Pill should now exist in the composite input.
    page.wait_for_selector(".todo-date-pill", timeout=2000)
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")
    item = page.locator('.todo-item[data-todo-text="Buy bread"]')
    assert item.count() == 1
    chip = item.locator(".todo-due")
    assert chip.count() == 1
    assert "todo-due--today" in chip.first.get_attribute("class")


def test_d_key_opens_date_picker(page):
    page.goto("/todos")
    _add_todo(page, "Date picker subject")
    page.wait_for_selector('.todo-item[data-todo-text="Date picker subject"]')
    _hover_and_blur(page, '.todo-item[data-todo-text="Date picker subject"]')
    page.keyboard.press("d")
    page.wait_for_selector(".todo-popover[data-role='date-picker']", timeout=2000)
    assert page.locator(".todo-popover[data-role='date-picker']").is_visible()


def test_p_key_postpones_one_day(page):
    """Pressing 'p' on a hovered item bumps its due_date to today+1 (off the active list)."""
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
    assert page.locator(".todo-popover[data-role='postpone-palette']").is_visible()
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
    assert page.locator("text=On hold").first.is_visible()


def test_picker_custom_input_has_live_preview(page):
    """Inside the picker, typing a natural-language phrase updates the preview."""
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
    """Adding a todo causes a body swap; ? must still open the help dialog."""
    page.goto("/todos")
    _add_todo(page, "after-swap probe")
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.keyboard.press("?")
    page.wait_for_selector("#kbd-help-overlay", state="visible", timeout=2000)


# ---------------------------------------------------------------------------
# Repetition feature
# ---------------------------------------------------------------------------


def test_star_opens_recurrence_picker_and_adds_pill(page):
    page.goto("/todos")
    _first_seg(page).fill("Water plants ")
    page.locator("#todo-text .todo-text-seg").last.press("*")
    page.wait_for_selector(".todo-popover[data-role='recurrence-picker']", timeout=2000)
    page.click("text=every week")
    page.wait_for_selector(".todo-rec-pill", timeout=2000)
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")
    item = page.locator('.todo-item[data-todo-text="Water plants"]')
    assert item.count() == 1
    # Recurrence badge should be present on the rendered row
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
    _first_seg(page).fill("Yoga ")
    page.locator("#todo-text .todo-text-seg").last.press("*")
    page.wait_for_selector(".todo-popover[data-role='recurrence-picker']")
    page.click("text=every month")
    page.wait_for_selector(".todo-rec-pill")
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")
    page.locator('.todo-item[data-todo-text="Yoga"] .todo-recurrence').click()
    page.wait_for_selector(".todo-history-panel", timeout=2000)
    assert page.locator(".todo-history-panel").is_visible()
    assert page.locator(".todo-history-entry").count() >= 1


def test_scheduled_view_shows_recurrence_badge_and_history(page):
    """Scheduled-view items must surface the ↻ badge and the history panel."""
    page.goto("/todos")
    # Create a future-dated, recurring item via the composite input.
    _first_seg(page).fill("Cosmetics check ")
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


def test_e_key_loads_recurrence_pill(page):
    """The 'e' shortcut must load the recurrence pill, just like the pencil."""
    page.goto("/todos")
    _first_seg(page).fill("ekey rec ")
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


def test_recurrence_label_visible_next_to_badge(page):
    page.goto("/todos")
    _first_seg(page).fill("rule label vis ")
    page.locator("#todo-text .todo-text-seg").last.press("*")
    page.wait_for_selector(".todo-popover[data-role='recurrence-picker']")
    page.click("text=every month")
    page.wait_for_selector(".todo-rec-pill")
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")

    item = page.locator('.todo-item[data-todo-text="rule label vis"]')
    label = item.locator(".todo-recurrence-label")
    assert label.count() == 1
    assert "every month" in label.first.inner_text()


def test_scheduled_view_edit_loads_recurrence_pill(page):
    """Editing a recurring item from /todos/scheduled pre-fills the rec pill."""
    page.goto("/todos")
    _first_seg(page).fill("Inventory check ")
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
    pill_text = page.locator(".todo-rec-pill").first.inner_text()
    assert "every week" in pill_text


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


def test_scheduled_view_can_edit_item(page):
    """Editing a scheduled item via the form keeps the user on /todos/scheduled."""
    page.goto("/todos")
    # Add an item with a future date via the picker
    _first_seg(page).fill("scheduled item ")
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
    _first_seg(page).fill("scheduled item edited")
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")
    # Must still be on the scheduled page after edit
    assert "/todos/scheduled" in page.url
    assert (
        page.locator('.todo-item[data-todo-text="scheduled item edited"]').count() == 1
    )


# ---------------------------------------------------------------------------
# contentEditable compound input
# ---------------------------------------------------------------------------


def test_todo_input_is_contenteditable(page):
    """The first text segment inside #todo-text is contentEditable."""
    page.goto("/todos")
    seg = _first_seg(page)
    assert seg.get_attribute("contenteditable") == "true"


def test_pills_render_inside_contenteditable(page):
    """After typing #tag<space> the tag pill appears inside #todo-text."""
    page.goto("/todos")
    _first_seg(page).press_sequentially("pizza #ctag123")
    _first_seg(page).press("Space")  # triggers the #tag→pill conversion
    page.wait_for_function(
        "document.querySelector('#todo-text .todo-tag-pill[data-tag=\"ctag123\"]') !== null",
        timeout=2000,
    )
    pill = page.locator('#todo-text .todo-tag-pill[data-tag="ctag123"]').first
    assert "ctag123" in pill.inner_text()


def test_tag_conversion_ensures_single_space(page):
    """Converting #tag to pill should leave exactly one space between text and pill.

    Regression: previously, typing "text#tag " would leave no space, but typing
    "text #tag " would collapse multiple spaces. Both should produce exactly one space.
    """
    page.goto("/todos")
    _first_seg(page).press_sequentially("abc #deftag")
    _first_seg(page).press("Space")
    page.wait_for_selector(".todo-tag-pill[data-tag='deftag']", timeout=2000)

    # Get the first seg's text content - should be "abc " with exactly one trailing space
    first_text = page.evaluate("""() => {
        var seg = document.querySelector('#todo-text .todo-text-seg');
        return seg ? seg.textContent : '';
    }""")
    assert first_text == "abc ", (
        f"First seg should have exactly one trailing space, got: '{first_text}'"
    )

    # Also test case where there's no trailing whitespace before the tag
    page.reload()
    page.wait_for_load_state("networkidle")
    _first_seg(page).press_sequentially("xyz#notrail")
    _first_seg(page).press("Space")
    page.wait_for_selector(".todo-tag-pill[data-tag='notrail']", timeout=2000)

    first_text2 = page.evaluate("""() => {
        var seg = document.querySelector('#todo-text .todo-text-seg');
        return seg ? seg.textContent : '';
    }""")
    assert first_text2 == "xyz ", (
        f"First seg should have exactly one trailing space, got: '{first_text2}'"
    )


def test_edit_mode_shows_title_then_pills(page):
    """Enter edit mode: first seg contains the title; rec pill follows it."""
    page.goto("/todos")
    _first_seg(page).press_sequentially("edit order test ")
    _first_seg(page).press("*")
    page.wait_for_selector(".todo-popover[data-role='recurrence-picker']")
    page.click("text=every week")
    page.wait_for_selector(".todo-rec-pill")
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")

    page.locator('.todo-item[data-todo-text="edit order test"] .todo-edit-btn').click()
    page.wait_for_selector("#todo-tag-input.todo-tag-input--editing", timeout=2000)

    # First seg must hold the title text; rec pill must follow in #todo-text
    # Note: there may be a trailing space before the pill due to proper whitespace handling
    first_seg_has_title = page.evaluate("""() => {
        var seg = document.querySelector('#todo-text .todo-text-seg');
        return seg !== null && (seg.textContent === 'edit order test' || seg.textContent === 'edit order test ');
    }""")
    assert first_seg_has_title, "First text segment should contain the todo title"

    pill = page.locator("#todo-text .todo-rec-pill")
    assert pill.count() == 1


def test_backspace_removes_pill_from_state(page):
    """Backspace at the start of the seg after a tag pill removes it from state."""
    page.goto("/todos")
    _first_seg(page).press_sequentially("rm test #xtag456")
    _first_seg(page).press("Space")
    page.wait_for_function(
        "document.querySelector('#todo-text .todo-tag-pill[data-tag=\"xtag456\"]') !== null",
        timeout=2000,
    )
    # After #tag<space>, focus is already in the last (empty) seg right after the pill.
    # Backspace at its start removes the pill.
    page.keyboard.press("Backspace")
    page.wait_for_function(
        "document.querySelector('#todo-text .todo-tag-pill[data-tag=\"xtag456\"]') === null",
        timeout=2000,
    )
    assert page.locator('#todo-text .todo-tag-pill[data-tag="xtag456"]').count() == 0


def test_cmd_left_right_jumps_to_absolute_boundary(page):
    """Cmd+Left/Right jump to the absolute start/end of the virtual textfield."""
    page.goto("/todos")
    _first_seg(page).press_sequentially("hello")
    _first_seg(page).press("^")
    page.wait_for_selector(".todo-popover[data-role='date-picker']", timeout=2000)
    page.click("text=Today")
    page.wait_for_selector(".todo-date-pill", timeout=2000)
    # Two segs exist now; focus is on the last (empty) seg after the pill
    page.keyboard.press("Meta+ArrowLeft")
    first_is_active = page.evaluate("""() => {
        var segs = Array.from(document.querySelectorAll('#todo-text .todo-text-seg'));
        return segs.length > 0 && document.activeElement === segs[0];
    }""")
    assert first_is_active, "Cmd+Left should focus the first seg"

    page.keyboard.press("Meta+ArrowRight")
    last_is_active = page.evaluate("""() => {
        var segs = Array.from(document.querySelectorAll('#todo-text .todo-text-seg'));
        return segs.length > 0 && document.activeElement === segs[segs.length - 1];
    }""")
    assert last_is_active, "Cmd+Right should focus the last seg"


def test_cmd_a_selects_across_all_segs(page):
    """Cmd+A selects all content across the entire virtual textfield."""
    page.goto("/todos")
    _first_seg(page).press_sequentially("hello")
    _first_seg(page).press("^")
    page.wait_for_selector(".todo-popover[data-role='date-picker']", timeout=2000)
    page.click("text=Today")
    page.wait_for_selector(".todo-date-pill", timeout=2000)
    # Focus is on the last seg after the pill; Cmd+A should select across all segs
    page.keyboard.press("Meta+a")
    selection_info = page.evaluate("""() => {
        var sel = window.getSelection();
        if (!sel || !sel.rangeCount) return {text: '', collapsed: true};
        var r = sel.getRangeAt(0);
        return {text: r.toString(), collapsed: r.collapsed};
    }""")
    assert not selection_info["collapsed"], (
        "Cmd+A should produce a non-collapsed selection"
    )
    assert "hello" in selection_info["text"], "Selection should include the typed text"


def test_placeholder_shown_when_empty(page):
    """Placeholder text is on the first text segment and the empty class is applied."""
    page.goto("/todos")
    placeholder = _first_seg(page).get_attribute("data-placeholder")
    assert placeholder == "New todo…"
    # After clearing sessionStorage and reloading, the first seg should show the placeholder
    page.evaluate("sessionStorage.removeItem('todo-tags')")
    page.reload()
    page.wait_for_load_state("networkidle")
    assert page.locator("#todo-text .todo-text-seg.todo-input-empty").count() == 1


def test_pill_click_opens_edit_palette(page):
    """Clicking a date pill in the input opens the date picker."""
    page.goto("/todos")
    _first_seg(page).press("^")
    page.wait_for_selector(".todo-popover[data-role='date-picker']")
    page.click("text=Today")
    page.wait_for_selector(".todo-date-pill")
    # Click the pill label (not the × button) — should reopen the picker
    page.locator("#todo-text .todo-date-pill").click()
    page.wait_for_selector(".todo-popover[data-role='date-picker']", timeout=2000)
    assert page.locator(".todo-popover[data-role='date-picker']").is_visible()


def test_arrow_right_navigates_past_pill_from_nonempty_seg(page):
    """ArrowRight at the end of a non-empty seg jumps to the seg after the pill.

    Regression: compareBoundaryPoints across node types returned false for
    text-node cursors even when logically at the end, so navigation was broken
    when the first seg contained text.
    """
    page.goto("/todos")
    _first_seg(page).press_sequentially("asdf")
    _first_seg(page).press("^")
    page.wait_for_selector(".todo-popover[data-role='date-picker']", timeout=2000)
    page.click("text=Today")
    page.wait_for_selector(".todo-date-pill", timeout=2000)

    # Click the first seg to focus it, then move cursor to its end.
    _first_seg(page).click()
    page.keyboard.press("End")

    # ArrowRight should cross the pill and land in the following empty seg.
    page.keyboard.press("ArrowRight")

    active_is_last_seg = page.evaluate("""() => {
        var segs = Array.from(document.querySelectorAll('#todo-text .todo-text-seg'));
        return segs.length > 1 && document.activeElement === segs[segs.length - 1];
    }""")
    assert active_is_last_seg, (
        "Cursor should have jumped to the seg after the date pill"
    )
