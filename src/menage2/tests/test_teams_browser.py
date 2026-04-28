"""Browser tests for the @mention / assignee feature."""

import pytest
from sqlalchemy.orm import sessionmaker

from menage2.models.team import Team, TeamMember
from menage2.models.user import User


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


def _first_seg(page):
    return page.locator("#todo-text .todo-text-seg").first


# ---------------------------------------------------------------------------
# Helper to insert a second user and a team directly via DB
# ---------------------------------------------------------------------------


@pytest.fixture
def second_user(clean_db, dbengine):
    from datetime import datetime, timezone

    from argon2 import PasswordHasher

    _ph = PasswordHasher()
    Session = sessionmaker(bind=dbengine)
    session = Session()
    user = User(
        username="alice",
        real_name="Alice",
        email="alice@test.local",
        password_hash=_ph.hash("alicepassword1!"),
        is_admin=False,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.commit()
    uid = user.id
    session.close()
    return {"id": uid, "username": "alice"}


@pytest.fixture
def team_with_alice(clean_db, dbengine, second_user, browser_admin_user):
    from datetime import datetime, timezone

    Session = sessionmaker(bind=dbengine)
    session = Session()
    team = Team(name="house", created_at=datetime.now(timezone.utc))
    session.add(team)
    session.flush()
    member = TeamMember(team_id=team.id, user_id=second_user["id"], role="assignee")
    session.add(member)
    session.commit()
    tid = team.id
    session.close()
    return {"id": tid, "name": "house"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_at_mention_autocomplete_shows_users(page, second_user):
    page.goto("/todos")
    _first_seg(page).click()
    page.keyboard.type("Fix bug @")
    page.keyboard.type("a")
    page.wait_for_timeout(600)
    dropdown = page.locator(".todo-tag-autocomplete")
    assert dropdown.is_visible()
    assert "alice" in dropdown.inner_text()


def test_at_mention_autocomplete_shows_teams(page, team_with_alice):
    page.goto("/todos")
    _first_seg(page).click()
    page.keyboard.type("Clean @")
    page.keyboard.type("h")
    page.wait_for_timeout(600)
    dropdown = page.locator(".todo-tag-autocomplete")
    assert dropdown.is_visible()
    assert "house" in dropdown.inner_text()


def test_at_mention_space_completes_pill(page, second_user):
    page.goto("/todos")
    _first_seg(page).click()
    page.keyboard.type("Walk dog @alice ")
    page.wait_for_timeout(200)
    pill = page.locator(".todo-assignee-pill")
    assert pill.count() >= 1
    assert "alice" in pill.first.inner_text()


def test_assignee_display_in_todo_row(page, second_user):
    page.goto("/todos")
    _first_seg(page).click()
    page.keyboard.type("Feed cat @alice ")
    page.wait_for_timeout(200)
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")
    row = page.locator('.todo-item[data-todo-text="Feed cat"]')
    assert row.count() == 1
    assert "@alice" in row.locator(".todo-assignees").inner_text()


def test_filter_toggle_all_visible(page, second_user):
    page.goto("/todos")
    _first_seg(page).click()
    page.keyboard.type("Personal task @alice ")
    page.wait_for_timeout(200)
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")
    assert page.locator('.todo-item[data-todo-text="Personal task"]').count() == 1
    page.goto("/todos?filter=all")
    assert page.locator('.todo-item[data-todo-text="Personal task"]').count() == 1


def test_edit_todo_preserves_assignees(page, second_user):
    page.goto("/todos")
    _first_seg(page).click()
    page.keyboard.type("Wash car @alice ")
    page.wait_for_timeout(200)
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")

    row = page.locator('.todo-item[data-todo-text="Wash car"]')
    assert row.count() == 1
    row.locator(".todo-edit-btn").click()
    page.wait_for_timeout(300)
    pills = page.locator(".todo-assignee-pill")
    assert pills.count() >= 1
    assert "alice" in pills.first.inner_text()
