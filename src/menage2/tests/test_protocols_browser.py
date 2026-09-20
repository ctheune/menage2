"""Browser-based tests for the Protocols feature.

Protocols are set up through the server's own form endpoints rather than
through the edit page: the edit page's title/item widgets are JS-driven and
are exercised separately.  What these tests cover is the *run* — how a started
protocol shows up in the todo list and behaves in the details pane.
"""

import pytest

from ._browser_helpers import click_until, select_row


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
        # Answers with the re-rendered item list, not a redirect.
        assert resp.status == 200, f"Adding item {text!r} failed: {resp.status}"
    return protocol_id


def _start_run(page, protocol_id):
    """Open the protocol and start a run, landing on the todo list."""
    page.goto(f"/protocols/{protocol_id}/edit")
    page.click('button:has-text("Start a run now")')
    page.wait_for_url("**/todos")


def _open_run(page, title):
    """Select the run's todo row and wait for the checklist in the details pane."""
    select_row(page, f'.todo-item[data-todo-text="{title}"]', "#protocol-run")


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
    assert page.locator(".todo-protocol-link").count() == 1
    # Badge opens the panel inline instead of navigating.
    click_until(page, ".todo-protocol-link", "#protocol-run")
    assert page.url.endswith("/todos")


def test_completing_linked_todo_closes_run(page, context, live_server):
    """Marking the run-todo done from /todos should close the run."""
    pid = _make_protocol(context, live_server, "ClosingProto", ["x"])
    _start_run(page, pid)
    _item_sel = '.todo-item[data-todo-text="ClosingProto"]'
    # Select the row (c is a no-op without a selection), then mark it done.
    select_row(page, _item_sel, "#protocol-run")
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.keyboard.press("c")
    page.wait_for_function(
        f"document.querySelectorAll('{_item_sel}').length === 0",
        timeout=10000,
    )


# ---------------------------------------------------------------------------
# Editing — plain text inputs with a view/edit toggle per line
# ---------------------------------------------------------------------------


def test_add_item_through_the_form_keeps_the_input_focused(page, context, live_server):
    """Only the list is swapped, so the input survives and the next item can be typed."""
    pid = _make_protocol(context, live_server, "Typing flow", [])
    page.goto(f"/protocols/{pid}/edit")
    new_item = page.locator("#proto-new-item-form input[name='text']")
    new_item.fill("check fridge #kitchen")
    new_item.press("Enter")
    page.wait_for_selector(".proto-item", timeout=10000)

    view = page.locator(".proto-item .proto-item-view").first
    assert "check fridge" in view.inner_text()
    assert "#kitchen" in view.inner_text()
    assert page.evaluate(
        "document.activeElement === "
        "document.querySelector(\"#proto-new-item-form input[name='text']\")"
    )
    assert new_item.input_value() == ""


def test_clicking_an_item_opens_its_editor_with_the_marker_text(
    page, context, live_server
):
    pid = _make_protocol(context, live_server, "Edit flow", ["wipe counter #kitchen"])
    page.goto(f"/protocols/{pid}/edit")
    page.wait_for_selector(".proto-item-view", timeout=10000)
    page.locator(".proto-item-view").first.click()
    page.wait_for_selector(".proto-item-edit:not(.d-none)", timeout=5000)
    field = page.locator(".proto-item-edit input[name='text']").first
    assert field.input_value() == "wipe counter #kitchen"
    assert page.evaluate(
        "document.activeElement === "
        "document.querySelector(\".proto-item-edit input[name='text']\")"
    )


def test_editing_an_item_saves_and_returns_to_view_mode(page, context, live_server):
    pid = _make_protocol(context, live_server, "Save flow", ["old text"])
    page.goto(f"/protocols/{pid}/edit")
    page.wait_for_selector(".proto-item-view", timeout=10000)
    page.locator(".proto-item-view").first.click()
    field = page.locator(".proto-item-edit input[name='text']").first
    field.fill("new text #done @alice ~with a note")
    field.press("Enter")
    page.wait_for_selector(".proto-item-view:has-text('new text')", timeout=10000)
    view = page.locator(".proto-item-view").first
    assert "#done" in view.inner_text()
    assert "@alice" in view.inner_text()
    assert "~with a note" in view.inner_text()
    # Back in view mode: the editor is hidden again.
    assert page.locator(".proto-item-edit:not(.d-none)").count() == 0


def test_escape_cancels_an_item_edit(page, context, live_server):
    pid = _make_protocol(context, live_server, "Cancel flow", ["keep me"])
    page.goto(f"/protocols/{pid}/edit")
    page.wait_for_selector(".proto-item-view", timeout=10000)
    page.locator(".proto-item-view").first.click()
    field = page.locator(".proto-item-edit input[name='text']").first
    field.fill("discard me")
    field.press("Escape")
    page.wait_for_selector(".proto-item-view:not(.d-none)", timeout=5000)
    assert "keep me" in page.locator(".proto-item-view").first.inner_text()
    page.reload()
    assert "keep me" in page.locator(".proto-item-view").first.inner_text()


def test_deleting_an_item_removes_the_row(page, context, live_server):
    pid = _make_protocol(context, live_server, "Delete flow", ["one", "two"])
    page.on("dialog", lambda dialog: dialog.accept())
    page.goto(f"/protocols/{pid}/edit")
    page.wait_for_selector(".proto-item", timeout=10000)
    assert page.locator(".proto-item").count() == 2
    page.locator(".proto-item").first.locator("button[hx-post]").click()
    page.wait_for_function(
        "document.querySelectorAll('.proto-item').length === 1", timeout=10000
    )
    assert "two" in page.locator(".proto-item-view").first.inner_text()


def test_editing_the_title_updates_the_rendered_view(page, context, live_server):
    pid = _make_protocol(context, live_server, "Old title", [])
    page.goto(f"/protocols/{pid}/edit")
    page.locator(".proto-title-view").click()
    field = page.locator(".proto-title-edit input[name='composite']")
    field.fill("New title #weekly *every month ~remember the keys")
    field.press("Enter")
    page.wait_for_selector(".proto-title-view:has-text('New title')", timeout=10000)
    view = page.locator(".proto-title-view")
    assert "#weekly" in view.inner_text()
    assert "every month" in view.inner_text()
    assert "~remember the keys" in view.inner_text()


def test_run_item_edit_via_e_key(page, context, live_server):
    """`e` clicks the row's pencil, which is what opens the inline field now."""
    pid = _make_protocol(context, live_server, "Key edit", ["first", "second"])
    _start_run(page, pid)
    _open_run(page, "Key edit")
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.keyboard.press("e")
    page.wait_for_selector(".run-item-edit:not(.d-none)", timeout=5000)
    assert page.evaluate(
        "document.activeElement === document.querySelector('.run-item-input')"
    )


def test_run_item_edit_button_opens_an_inline_field(page, context, live_server):
    pid = _make_protocol(context, live_server, "Inline edit", ["rough wording"])
    _start_run(page, pid)
    _open_run(page, "Inline edit")
    page.locator('.protocol-run-action[data-action="edit"]').first.click()
    page.wait_for_selector(".run-item-edit:not(.d-none)", timeout=5000)
    # The editor replaces the text in place: the parsed view is hidden while
    # it is open, so the line does not grow a second row.
    assert page.locator(".run-item-view").count() == 1
    assert page.locator(".run-item-view:not(.d-none)").count() == 0
    field = page.locator(".run-item-input").first
    field.fill("polished wording #later")
    # The hidden field that actually gets posted tracks the contenteditable.
    assert (
        page.locator(".run-item-edit input[name='text']").first.input_value()
        == "polished wording #later"
    )
    field.press("Enter")
    # Wait for the re-rendered view, not for the text: the still-open editor
    # contains the new text too, so matching on it alone races the swap.
    page.wait_for_selector(".run-item-view .badge", timeout=10000)
    view = page.locator(".run-item-view").first
    assert "polished wording" in view.inner_text()
    assert "#later" in view.inner_text()
