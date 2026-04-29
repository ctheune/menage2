"""Browser tests for the @mention / assignee feature in todo context."""

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


def _todo_ci(page):
    return page.locator("#todo-text")


# ---------------------------------------------------------------------------
# Assignee display in todo rows (needs a peer user in DB)
# ---------------------------------------------------------------------------


def test_assignee_display_in_todo_row(page, second_user):
    page.goto("/todos")
    fill_composite(_todo_ci(page), "Feed cat @alice")
    page.wait_for_load_state("networkidle")
    # Delegated-out todos are hidden from personal filter; check with filter=all
    page.goto("/todos?filter=all")
    row = page.locator('.todo-item[data-todo-text="Feed cat"]')
    assert row.count() == 1
    assert "@alice" in row.locator(".todo-assignees").inner_text()


def test_filter_toggle_all_visible(page, second_user):
    page.goto("/todos")
    fill_composite(_todo_ci(page), "Personal task @alice")
    page.wait_for_load_state("networkidle")
    page.goto("/todos?filter=all")
    assert page.locator('.todo-item[data-todo-text="Personal task"]').count() == 1


def test_edit_todo_preserves_assignees(page, second_user):
    page.goto("/todos")
    fill_composite(_todo_ci(page), "Wash car @alice")
    page.wait_for_load_state("networkidle")
    page.goto("/todos?filter=all")
    row = page.locator('.todo-item[data-todo-text="Wash car"]')
    assert row.count() == 1
    row.locator(".todo-edit-btn").click()
    page.wait_for_timeout(300)
    pills = page.locator(".todo-assignee-pill")
    assert pills.count() >= 1
    assert "alice" in pills.first.inner_text()
