"""Browser tests for the @mention / assignee feature in todo context."""

import pytest


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, live_server):
    return {
        **browser_context_args,
        "base_url": live_server,
        "viewport": {"width": 1280, "height": 900},
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
    assert resp.status == 303, f"Login failed: {resp.status}"
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


# ---------------------------------------------------------------------------
# Assignee display in todo rows (needs a peer user in DB)
# ---------------------------------------------------------------------------


def _add_delegated(page, raw: str, expect: str) -> None:
    """Add a todo assigned to someone else and show it via the `all` filter.

    A delegated-out todo is hidden from the personal filter, so the row it
    creates only becomes visible once we switch filters.
    """
    inp = page.locator("#input-add-todo-text")
    inp.fill(raw)
    inp.press("Enter")
    page.goto("/todos?filter=all")
    page.wait_for_selector(f'.todo-item[data-todo-text="{expect}"]', timeout=10000)


def test_assignee_display_in_todo_row(page, second_user):
    page.goto("/todos")
    _add_delegated(page, "Feed cat @alice", "Feed cat")
    row = page.locator('.todo-item[data-todo-text="Feed cat"]')
    assert row.count() == 1
    assert "@alice" in row.locator(".todo-assignees").inner_text()


def test_filter_toggle_all_visible(page, second_user):
    page.goto("/todos")
    _add_delegated(page, "Personal task @alice", "Personal task")
    assert page.locator('.todo-item[data-todo-text="Personal task"]').count() == 1


def test_edit_todo_preserves_assignees(page, second_user):
    page.goto("/todos")
    _add_delegated(page, "Wash car @alice", "Wash car")
    row = page.locator('.todo-item[data-todo-text="Wash car"]')
    assert row.count() == 1
    # Click the row to select it — the details pane renders every field,
    # assignees included.
    row.first.click()
    page.wait_for_selector("#details-panel #field-assignees", timeout=5000)
    page.wait_for_function(
        "!!document.querySelector("
        '\'#field-assignees input[name="assignees[]"][value="alice"]\')',
        timeout=5000,
    )
