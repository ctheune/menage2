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


def test_swipe_left_postpones_item(page):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto("/todos")
    _add_todo(page, "Swipe postpone item")
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
    assert page.locator("text=Paused").first.is_visible()
