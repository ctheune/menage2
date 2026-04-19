"""Browser-based tests for the todo feature.

Prerequisites:
  1. `devenv up` must be running (dev server on http://localhost:6543)
  2. Run `uv run playwright install chromium` once to install the browser

Run separately (requires live server):
  uv run pytest src/menage2/tests/test_todos_browser.py --live-server
"""
import pytest

# Skip the entire module unless --live-server flag is passed
def pytest_addoption_browser(parser):
    parser.addoption("--live-server", action="store_true", default=False,
                     help="Run browser tests against live dev server")


pytestmark = pytest.mark.skipif(
    "not config.getoption('--live-server', default=False)",
    reason="Pass --live-server to run browser tests",
)

LIVE_URL = "http://localhost:6543"


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "viewport": {"width": 390, "height": 844}}


def _clear_todos(page):
    """Navigate to todos and remove all items via the server (helper)."""
    page.goto(f"{LIVE_URL}/todos")


def test_add_todo_appears_in_list(page):
    page.goto(f"{LIVE_URL}/todos")
    page.fill('input[name="text"]', "Buy bread #shopping")
    page.press('input[name="text"]', "Enter")
    page.wait_for_selector("text=Buy bread")
    assert page.locator("text=Buy bread").is_visible()
    assert page.locator("text=#shopping").count() >= 1


def test_keyboard_c_single_item_marks_done(page):
    page.goto(f"{LIVE_URL}/todos")
    # Ensure at least one todo exists
    page.fill('input[name="text"]', "Keyboard test item")
    page.press('input[name="text"]', "Enter")
    page.wait_for_selector(".todo-checkbox")
    initial_count = page.locator(".todo-checkbox").count()
    page.check('.todo-checkbox >> nth=0')
    page.keyboard.press("c")
    page.wait_for_timeout(500)
    assert page.locator(".todo-checkbox").count() == initial_count - 1


def test_undo_toast_appears_after_done(page):
    page.goto(f"{LIVE_URL}/todos")
    page.fill('input[name="text"]', "Undo test item")
    page.press('input[name="text"]', "Enter")
    page.wait_for_selector(".todo-checkbox")
    page.check('.todo-checkbox >> nth=0')
    page.keyboard.press("c")
    page.wait_for_selector("#undo-toast", timeout=2000)
    assert page.locator("#undo-toast").is_visible()


def test_undo_with_u_key_restores_item(page):
    page.goto(f"{LIVE_URL}/todos")
    page.fill('input[name="text"]', "Undo restore item")
    page.press('input[name="text"]', "Enter")
    page.wait_for_selector(".todo-checkbox")
    count_before = page.locator(".todo-checkbox").count()
    page.check('.todo-checkbox >> nth=0')
    page.keyboard.press("c")
    page.wait_for_selector("#undo-toast", timeout=2000)
    page.keyboard.press("u")
    page.wait_for_timeout(1000)
    assert page.locator(".todo-checkbox").count() >= count_before


def test_done_view_shows_completed_items(page):
    page.goto(f"{LIVE_URL}/todos")
    page.fill('input[name="text"]', "Done view test")
    page.press('input[name="text"]', "Enter")
    page.wait_for_selector(".todo-checkbox")
    page.check('.todo-checkbox >> nth=0')
    page.keyboard.press("c")
    page.wait_for_timeout(500)
    page.goto(f"{LIVE_URL}/todos/done")
    assert page.locator("text=Done view test").count() >= 1


def test_swipe_right_marks_item_done(page):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{LIVE_URL}/todos")
    page.fill('input[name="text"]', "Swipe done item")
    page.press('input[name="text"]', "Enter")
    page.wait_for_selector(".todo-item")
    count_before = page.locator(".todo-item").count()

    # Simulate swipe right via JS touch events
    page.evaluate("""() => {
        const item = document.querySelector('.todo-item');
        if (!item) return;
        const touch = (x) => new Touch({identifier: 1, target: item, clientX: x, clientY: 100});
        item.dispatchEvent(new TouchEvent('touchstart', {touches: [touch(20)], bubbles: true}));
        item.dispatchEvent(new TouchEvent('touchmove', {touches: [touch(160)], bubbles: true}));
        item.dispatchEvent(new TouchEvent('touchend', {changedTouches: [touch(160)], bubbles: true}));
    }""")
    page.wait_for_timeout(1000)
    assert page.locator(".todo-item").count() == count_before - 1


def test_swipe_left_postpones_item(page):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{LIVE_URL}/todos")
    page.fill('input[name="text"]', "Swipe postpone item")
    page.press('input[name="text"]', "Enter")
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
    page.wait_for_timeout(1000)
    assert page.locator(".todo-item").count() == count_before - 1
    # Verify "activate postponed" button appears
    assert page.locator("text=Activate postponed").is_visible()
