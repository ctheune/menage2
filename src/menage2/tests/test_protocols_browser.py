"""Browser-based tests for the Protocols feature."""

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
            "came_from": "/protocols",
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


def _make_protocol_via_ui(page, title, items):
    page.goto("/protocols")
    page.click('button:has-text("New protocol")')
    page.wait_for_url("**/protocols/*/edit")
    fill_composite(page.locator("#proto-title-ci"), title)
    page.wait_for_load_state("networkidle")
    for i, txt in enumerate(items, start=1):
        fill_composite(page.locator(".proto-new-item-ci"), txt)
        page.wait_for_function(
            f"document.querySelectorAll(\"li[id^='item-']\").length >= {i}",
            timeout=5000,
        )


def test_create_protocol_and_start_run(page):
    _make_protocol_via_ui(page, "Browser inv", ["check fridge", "check pantry"])
    page.click('button:has-text("Start a run now")')
    page.wait_for_url("**/protocols/run/*")
    assert page.locator(".protocol-run-item").count() == 2
    assert page.locator("text=check fridge").count() >= 1


def test_run_done_action(page):
    _make_protocol_via_ui(page, "Done flow", ["item-A", "item-B"])
    page.click('button:has-text("Start a run now")')
    page.wait_for_url("**/protocols/run/*")
    first = page.locator(".protocol-run-item").first
    first.locator('.protocol-run-action[data-action="done"]').click()
    page.wait_for_function(
        "document.querySelectorAll('.protocol-run-item.status-done').length === 1",
        timeout=3000,
    )


def test_run_send_to_todo_action(page):
    _make_protocol_via_ui(page, "Send flow", ["buy bread"])
    page.click('button:has-text("Start a run now")')
    page.wait_for_url("**/protocols/run/*")
    item = page.locator(".protocol-run-item").first
    item.locator('.protocol-run-action[data-action="send"]').click()
    page.wait_for_function(
        "document.querySelectorAll('.protocol-run-item.status-sent_to_todo').length === 1",
        timeout=3000,
    )
    page.goto("/todos")
    assert page.locator('.todo-item[data-todo-text="buy bread"]').count() == 1


def test_run_keyboard_done_via_c_key(page):
    _make_protocol_via_ui(page, "Key flow", ["one", "two"])
    page.click('button:has-text("Start a run now")')
    page.wait_for_url("**/protocols/run/*")
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.keyboard.press("c")
    page.wait_for_function(
        "document.querySelectorAll('.protocol-run-item.status-done').length === 1",
        timeout=3000,
    )


def test_run_navigation_with_j_k(page):
    _make_protocol_via_ui(page, "Nav flow", ["one", "two", "three"])
    page.click('button:has-text("Start a run now")')
    page.wait_for_url("**/protocols/run/*")
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.keyboard.press("j")
    page.keyboard.press("j")
    page.wait_for_function(
        "document.querySelectorAll('.protocol-run-item.is-current').length === 1 && "
        "document.querySelectorAll('.protocol-run-item')[2].classList.contains('is-current')",
        timeout=2000,
    )


def test_palette_opens_with_r_and_starts_run(page):
    _make_protocol_via_ui(page, "PaletteProto", ["only one"])
    page.goto("/todos")
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.keyboard.press("r")
    page.wait_for_selector(".protocol-palette", timeout=2000)
    page.fill(".protocol-palette-input", "Palette")
    page.locator(".protocol-palette-input").press("Enter")
    page.wait_for_url("**/protocols/run/*")
    assert page.locator(".protocol-run-item").count() == 1


def test_linked_todo_badge_opens_run(page):
    _make_protocol_via_ui(page, "Linked", ["only"])
    # Start a run, navigate back to todo list, click the clipboard badge
    page.click('button:has-text("Start a run now")')
    page.wait_for_url("**/protocols/run/*")
    page.goto("/todos")
    badge = page.locator(".todo-protocol-link")
    assert badge.count() == 1
    badge.first.click()
    # Badge now opens the panel inline instead of navigating
    page.wait_for_selector("#protocol-run", timeout=5000)
    assert page.url.endswith("/todos")


def test_completing_linked_todo_closes_run(page):
    """Marking the run-todo done from /todos should close the run."""
    _make_protocol_via_ui(page, "ClosingProto", ["x"])
    page.click('button:has-text("Start a run now")')
    page.wait_for_url("**/protocols/run/*")
    page.goto("/todos")
    _item_sel = '.todo-item[data-todo-text="ClosingProto"]'
    item = page.locator(_item_sel)
    assert item.count() == 1
    # Click item to select it (checks the checkbox), then press c to mark done
    item.click()
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.keyboard.press("c")
    page.wait_for_function(
        f"document.querySelectorAll('{_item_sel}').length === 0",
        timeout=3000,
    )
