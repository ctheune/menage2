"""Browser-based tests for the todo feature.

The test server (port 6544) must be running — `devenv up` starts it automatically.
Run with: uv run pytest src/menage2/tests/test_todos_browser.py
"""
import pytest


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, live_server):
    """Set base_url and viewport for all browser tests."""
    return {**browser_context_args, "base_url": live_server, "viewport": {"width": 390, "height": 844}}


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
    context.add_cookies([{
        "name": name.strip(),
        "value": value.strip(),
        "domain": "localhost",
        "path": "/",
    }])


def _add_todo(page, text):
    page.fill('#todo-text', text)
    page.press('#todo-text', "Enter")
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
    page.fill('#todo-text', "Buy bread #shopping ")
    page.wait_for_timeout(100)
    page.press('#todo-text', "Enter")
    page.wait_for_load_state("networkidle")
    assert page.locator(".todo-item").count() == count_before + 1
    assert page.locator("text=Buy bread").first.is_visible()
    assert page.locator("text=shopping").count() >= 1


def test_add_todo_only_tags_shows_error(page):
    """Submitting only a tag (no text) shows the error toast, not a new todo."""
    page.goto("/todos")
    page.fill('#todo-text', "#shopping ")
    page.wait_for_timeout(100)
    page.press('#todo-text', "Enter")
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
    page.wait_for_function(f"document.querySelectorAll('.todo-checkbox').length < {count_before}", timeout=5000)
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
    page.wait_for_function(f"document.querySelectorAll('.todo-checkbox').length < {count_before}", timeout=5000)
    count_after_done = page.locator(".todo-checkbox").count()
    page.keyboard.press("u")
    page.wait_for_function(f"document.querySelectorAll('.todo-checkbox').length > {count_after_done}", timeout=5000)
    assert page.locator(".todo-checkbox").count() >= count_before


def test_done_view_shows_completed_items(page):
    page.goto("/todos")
    _add_todo(page, "Done view test")
    page.wait_for_selector('.todo-item[data-todo-text="Done view test"]')
    count_before = page.locator(".todo-checkbox").count()
    page.locator('.todo-item[data-todo-text="Done view test"] .todo-checkbox').first.check()
    page.evaluate("document.activeElement.blur()")
    page.keyboard.press("c")
    page.wait_for_function(f"document.querySelectorAll('.todo-checkbox').length < {count_before}", timeout=5000)
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
    page.wait_for_function(f"document.querySelectorAll('.todo-item').length < {count_before}", timeout=5000)
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
    page.wait_for_function(f"document.querySelectorAll('.todo-item').length < {count_before}", timeout=5000)
    assert page.locator(".todo-item").count() == count_before - 1
    assert page.locator("text=On hold").first.is_visible()


# ---------------------------------------------------------------------------
# Scheduling — due date feature
# ---------------------------------------------------------------------------


def _hover_and_blur(page, selector):
    """Move pointer onto an item AND drop input focus so document keydown fires."""
    page.hover(selector)
    page.evaluate("document.activeElement && document.activeElement.blur && document.activeElement.blur()")


def test_caret_opens_picker_and_adds_pill(page):
    """Typing ^ in the composite input pops the picker; selecting a chip
    inserts an editable date pill, and submitting attaches the due date."""
    page.goto("/todos")
    page.fill('#todo-text', "Buy bread ")
    # Type ^ as a single keystroke so the input handler sees it.
    page.locator('#todo-text').press("^")
    page.wait_for_selector(".todo-popover[data-role='date-picker']", timeout=2000)
    page.click("text=Today")
    # Pill should now exist in the composite input.
    page.wait_for_selector(".todo-date-pill", timeout=2000)
    page.locator('#todo-text').press("Enter")
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
    page.fill('#todo-text', "Water plants ")
    page.locator('#todo-text').press("*")
    page.wait_for_selector(".todo-popover[data-role='recurrence-picker']", timeout=2000)
    page.click("text=every week")
    page.wait_for_selector(".todo-rec-pill", timeout=2000)
    page.locator('#todo-text').press("Enter")
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
    page.fill('#todo-text', "Yoga ")
    page.locator('#todo-text').press("*")
    page.wait_for_selector(".todo-popover[data-role='recurrence-picker']")
    page.click("text=every month")
    page.wait_for_selector(".todo-rec-pill")
    page.locator('#todo-text').press("Enter")
    page.wait_for_load_state("networkidle")
    page.locator('.todo-item[data-todo-text="Yoga"] .todo-recurrence').click()
    page.wait_for_selector(".todo-history-panel", timeout=2000)
    assert page.locator(".todo-history-panel").is_visible()
    assert page.locator(".todo-history-entry").count() >= 1


def test_scheduled_view_shows_recurrence_badge_and_history(page):
    """Scheduled-view items must surface the ↻ badge and the history panel."""
    page.goto("/todos")
    # Create a future-dated, recurring item via the composite input.
    page.fill('#todo-text', "Cosmetics check ")
    page.locator('#todo-text').press("^")
    page.wait_for_selector(".todo-popover[data-role='date-picker']")
    page.click("text=+1 week")
    page.wait_for_selector(".todo-date-pill")
    page.locator('#todo-text').press("*")
    page.wait_for_selector(".todo-popover[data-role='recurrence-picker']")
    page.click("text=every month")
    page.wait_for_selector(".todo-rec-pill")
    page.locator('#todo-text').press("Enter")
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
    page.fill('#todo-text', "ekey rec ")
    page.locator('#todo-text').press("*")
    page.wait_for_selector(".todo-popover[data-role='recurrence-picker']")
    page.click("text=every week")
    page.wait_for_selector(".todo-rec-pill")
    page.locator('#todo-text').press("Enter")
    page.wait_for_load_state("networkidle")

    _hover_and_blur(page, '.todo-item[data-todo-text="ekey rec"]')
    page.keyboard.press("e")
    page.wait_for_selector(".todo-rec-pill", timeout=2000)
    assert "every week" in page.locator(".todo-rec-pill").first.inner_text()


def test_recurrence_label_visible_next_to_badge(page):
    page.goto("/todos")
    page.fill('#todo-text', "rule label vis ")
    page.locator('#todo-text').press("*")
    page.wait_for_selector(".todo-popover[data-role='recurrence-picker']")
    page.click("text=every month")
    page.wait_for_selector(".todo-rec-pill")
    page.locator('#todo-text').press("Enter")
    page.wait_for_load_state("networkidle")

    item = page.locator('.todo-item[data-todo-text="rule label vis"]')
    label = item.locator(".todo-recurrence-label")
    assert label.count() == 1
    assert "every month" in label.first.inner_text()


def test_scheduled_view_edit_loads_recurrence_pill(page):
    """Editing a recurring item from /todos/scheduled pre-fills the rec pill."""
    page.goto("/todos")
    page.fill('#todo-text', "Inventory check ")
    page.locator('#todo-text').press("^")
    page.wait_for_selector(".todo-popover[data-role='date-picker']")
    page.click("text=+1 week")
    page.wait_for_selector(".todo-date-pill")
    page.locator('#todo-text').press("*")
    page.wait_for_selector(".todo-popover[data-role='recurrence-picker']")
    page.click("text=every week")
    page.wait_for_selector(".todo-rec-pill")
    page.locator('#todo-text').press("Enter")
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
    page.wait_for_selector(".todo-popover[data-role='recurrence-picker'] input", timeout=2000)
    page.fill(".todo-popover input", "every wednesday")
    page.wait_for_function(
        "Array.from(document.querySelectorAll('.todo-popover-preview')).some(el => /wednesday/i.test(el.textContent))",
        timeout=5000,
    )


def test_scheduled_view_can_edit_item(page):
    """Editing a scheduled item via the form keeps the user on /todos/scheduled."""
    page.goto("/todos")
    # Add an item with a future date via the picker
    page.fill('#todo-text', "scheduled item ")
    page.locator('#todo-text').press("^")
    page.wait_for_selector(".todo-popover[data-role='date-picker']")
    page.click("text=+1 week")
    page.wait_for_selector(".todo-date-pill")
    page.locator('#todo-text').press("Enter")
    page.wait_for_load_state("networkidle")

    page.goto("/todos/scheduled")
    page.wait_for_selector('.todo-item[data-todo-text="scheduled item"]')
    page.locator('.todo-item[data-todo-text="scheduled item"] .todo-edit-btn').click()
    page.wait_for_function("document.getElementById('todo-text').value === 'scheduled item'")
    page.fill('#todo-text', "scheduled item edited")
    page.locator('#todo-text').press("Enter")
    page.wait_for_load_state("networkidle")
    # Must still be on the scheduled page after edit
    assert "/todos/scheduled" in page.url
    assert page.locator('.todo-item[data-todo-text="scheduled item edited"]').count() == 1
