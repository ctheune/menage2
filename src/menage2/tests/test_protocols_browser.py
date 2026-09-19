"""Browser-based tests for the Protocols feature.

Protocols are set up through the server's own form endpoints rather than
through the edit page: the edit page's title/item widgets are JS-driven and
are exercised separately.  What these tests cover is the *run* — how a started
protocol shows up in the todo list and behaves in the details pane.
"""

import pytest


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


def _make_protocol(context, live_server, title, items):
    """Create a protocol with `items` via the form endpoints; return its id."""
    resp = context.request.post(
        f"{live_server}/protocols/new", form={"title": title}, max_redirects=0
    )
    assert resp.status == 303, f"Creating the protocol failed: {resp.status}"
    protocol_id = resp.headers["location"].rstrip("/").split("/")[-2]
    for text in items:
        resp = context.request.post(
            f"{live_server}/protocols/{protocol_id}/items",
            form={"text": text},
            max_redirects=0,
        )
        assert resp.status == 303, f"Adding item {text!r} failed: {resp.status}"
    return protocol_id


def _start_run(page, protocol_id):
    """Open the protocol and start a run, landing on the todo list."""
    page.goto(f"/protocols/{protocol_id}/edit")
    page.click('button:has-text("Start a run now")')
    page.wait_for_url("**/todos")


def _open_run(page, title):
    """Click the run's todo row and wait for the checklist in the details pane.

    The row has to be there before we click it: `#todo-list` loads its own
    contents, and a click that lands during that swap goes nowhere.
    """
    selector = f'.todo-item[data-todo-text="{title}"]'
    page.wait_for_selector(selector, timeout=10000)
    page.locator(selector).first.click()
    page.wait_for_selector("#protocol-run", timeout=10000)


def test_create_protocol_and_start_run(page, context, live_server):
    pid = _make_protocol(
        context, live_server, "Browser inv", ["check fridge", "check pantry"]
    )
    _start_run(page, pid)
    _open_run(page, "Browser inv")
    assert page.locator(".protocol-run-item").count() == 2
    assert page.locator("text=check fridge").count() >= 1


def test_run_done_action(page, context, live_server):
    pid = _make_protocol(context, live_server, "Done flow", ["item-A", "item-B"])
    _start_run(page, pid)
    _open_run(page, "Done flow")
    first = page.locator(".protocol-run-item").first
    first.locator('.protocol-run-action[data-action="done"]').click()
    page.wait_for_function(
        "document.querySelectorAll('.protocol-run-item.status-done').length === 1",
        timeout=3000,
    )


def test_run_send_to_todo_action(page, context, live_server):
    pid = _make_protocol(context, live_server, "Send flow", ["buy bread"])
    _start_run(page, pid)
    _open_run(page, "Send flow")
    item = page.locator(".protocol-run-item").first
    item.locator('.protocol-run-action[data-action="send"]').click()
    page.wait_for_function(
        "document.querySelectorAll('.protocol-run-item.status-sent_to_todo').length === 1",
        timeout=3000,
    )
    assert page.locator('.todo-item[data-todo-text="buy bread"]').count() == 1


def test_run_keyboard_done_via_c_key(page, context, live_server):
    pid = _make_protocol(context, live_server, "Key flow", ["one", "two"])
    _start_run(page, pid)
    _open_run(page, "Key flow")
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.keyboard.press("c")
    page.wait_for_function(
        "document.querySelectorAll('.protocol-run-item.status-done').length === 1",
        timeout=3000,
    )


def test_run_navigation_with_j_k(page, context, live_server):
    pid = _make_protocol(context, live_server, "Nav flow", ["one", "two", "three"])
    _start_run(page, pid)
    _open_run(page, "Nav flow")
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.keyboard.press("j")
    page.keyboard.press("j")
    page.wait_for_function(
        "document.querySelectorAll('.protocol-run-item.is-current').length === 1 && "
        "document.querySelectorAll('.protocol-run-item')[2].classList.contains('is-current')",
        timeout=2000,
    )


def test_linked_todo_badge_opens_run(page, context, live_server):
    pid = _make_protocol(context, live_server, "Linked", ["only"])
    # Start a run, land on the todo list, click the clipboard badge
    _start_run(page, pid)
    page.wait_for_selector(".todo-protocol-link", timeout=10000)
    badge = page.locator(".todo-protocol-link")
    assert badge.count() == 1
    badge.first.click()
    # Badge now opens the panel inline instead of navigating
    page.wait_for_selector("#protocol-run", timeout=10000)
    assert page.url.endswith("/todos")


def test_completing_linked_todo_closes_run(page, context, live_server):
    """Marking the run-todo done from /todos should close the run."""
    pid = _make_protocol(context, live_server, "ClosingProto", ["x"])
    _start_run(page, pid)
    _item_sel = '.todo-item[data-todo-text="ClosingProto"]'
    page.wait_for_selector(_item_sel, timeout=10000)
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
