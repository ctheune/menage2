"""Browser tests for the mobile todo list.

The mobile UI is chosen by User-Agent (``HEADER_MOBILE_DEVICE``), so the context
below pretends to be an iPhone. It has no selection checkboxes and no batch
menu: a swipe across a row is the only way to act on it, and the hidden buttons
in the list form are what the gesture submits.

Swipe distances are measured against a threshold of a quarter of the row width,
so the offsets here are expressed in those terms rather than raw pixels.
"""

import pytest

IPHONE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, live_server):
    return {
        **browser_context_args,
        "base_url": live_server,
        "viewport": {"width": 390, "height": 844},
        "user_agent": IPHONE_UA,
        "has_touch": True,
        "is_mobile": True,
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
    assert resp.status == 303, f"Login failed with HTTP {resp.status}"
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _item(text: str) -> str:
    return f'.todo-item[data-todo-text="{text}"]'


def _add_todo(context, live_server, raw: str) -> None:
    """Create a todo through the add endpoint — mobile has no add form yet."""
    resp = context.request.post(
        f"{live_server}/todos/add", form={"text": raw}, max_redirects=0
    )
    assert resp.status == 303, f"Adding {raw!r} failed: {resp.status}"


def _open_list(page, url: str = "/todos") -> None:
    page.goto(url)
    page.wait_for_selector("#todo-list .todo-item, .todo-list-empty", timeout=10000)


def _wait_swipe_ready(page, text: str) -> None:
    """Wait until hyperscript has wired the row's gesture handlers.

    The list arrives by htmx swap and hyperscript initialises the new rows
    afterwards; a touch sequence dispatched in between is simply dropped.
    `_hyperscript.initialized` is the flag hyperscript sets once it has.
    """
    page.wait_for_selector(_item(text), timeout=10000)
    page.wait_for_function(
        """(selector) => {
            const el = document.querySelector(selector);
            return !!(el && el._hyperscript && el._hyperscript.initialized);
        }""",
        arg=_item(text),
        timeout=10000,
    )


def _swipe(page, text: str, fraction: float) -> None:
    """Drag the row for `text` sideways by `fraction` of its own width.

    The handler reads `changedTouches[0].pageX`, so the synthetic events carry
    real `Touch` objects rather than plain dicts.
    """
    _wait_swipe_ready(page, text)
    page.evaluate(
        """([selector, fraction]) => {
            const item = document.querySelector(selector);
            const width = item.getBoundingClientRect().width;
            const start = 180;
            const end = start + width * fraction;
            const at = (x) => new Touch({
                identifier: 1, target: item, pageX: x, pageY: 100,
                clientX: x, clientY: 100,
            });
            const fire = (type, x) => item.dispatchEvent(new TouchEvent(type, {
                touches: type === 'touchend' ? [] : [at(x)],
                changedTouches: [at(x)],
                bubbles: true,
            }));
            fire('touchstart', start);
            fire('touchmove', end);
            fire('touchend', end);
        }""",
        [_item(text), fraction],
    )


def _wait_gone(page, text: str) -> None:
    page.wait_for_function(
        f"document.querySelectorAll('{_item(text)}').length === 0", timeout=10000
    )


# ---------------------------------------------------------------------------
# The gesture reaches the batch endpoint
# ---------------------------------------------------------------------------


def test_swipe_right_marks_the_row_done(page, context, live_server):
    _add_todo(context, live_server, "Swipe me done")
    _open_list(page)
    _swipe(page, "Swipe me done", 0.5)
    _wait_gone(page, "Swipe me done")

    page.goto("/todos?status=done")
    page.wait_for_selector(_item("Swipe me done"), timeout=10000)


def test_swipe_left_puts_the_row_on_hold(page, context, live_server):
    _add_todo(context, live_server, "Swipe me hold")
    _open_list(page)
    # Past one threshold but not two — the "hold" band.
    _swipe(page, "Swipe me hold", -0.4)
    _wait_gone(page, "Swipe me hold")

    page.goto("/todos?status=on_hold")
    page.wait_for_selector(_item("Swipe me hold"), timeout=10000)


def test_long_left_swipe_postpones_the_row(page, context, live_server):
    """Landing in `scheduled` with a due badge is the visible proof of postpone.

    The exact date the interval produces is pinned by the desktop test
    `test_shift_p_postpones_selected_by_one_day`; mobile rows carry no
    `data-due-date` to compare against.
    """
    _add_todo(context, live_server, "Swipe me later")
    _open_list(page)
    # Past two thresholds — the "postpone" band.
    _swipe(page, "Swipe me later", -0.75)
    _wait_gone(page, "Swipe me later")

    page.goto("/todos?status=scheduled")
    page.wait_for_selector(_item("Swipe me later"), timeout=10000)
    assert page.locator(f"{_item('Swipe me later')} .todo-due").count() == 1


def test_short_swipe_leaves_the_row_alone(page, context, live_server):
    """Below the threshold the row springs back and nothing is submitted."""
    _add_todo(context, live_server, "Barely moved")
    _open_list(page)
    _swipe(page, "Barely moved", 0.1)
    page.wait_for_timeout(1000)
    assert page.locator(_item("Barely moved")).count() == 1
    assert page.locator("#undo-toast").count() == 0


def test_swipe_acts_on_the_swiped_row_only(page, context, live_server):
    _add_todo(context, live_server, "Keep me")
    _add_todo(context, live_server, "Take me")
    _open_list(page)
    _swipe(page, "Take me", 0.5)
    _wait_gone(page, "Take me")
    assert page.locator(_item("Keep me")).count() == 1


# ---------------------------------------------------------------------------
# The undo bubble
# ---------------------------------------------------------------------------


def test_swipe_done_raises_an_undo_bubble(page, context, live_server):
    _add_todo(context, live_server, "Undo me done")
    _open_list(page)
    _swipe(page, "Undo me done", 0.5)
    toast = page.locator("#undo-toast")
    toast.wait_for(timeout=10000)
    assert "Undo me done" in toast.inner_text()


def test_swipe_hold_raises_an_undo_bubble(page, context, live_server):
    _add_todo(context, live_server, "Undo me hold")
    _open_list(page)
    _swipe(page, "Undo me hold", -0.4)
    toast = page.locator("#undo-toast")
    toast.wait_for(timeout=10000)
    assert "Undo me hold" in toast.inner_text()


def test_tapping_the_undo_bubble_restores_the_row(page, context, live_server):
    _add_todo(context, live_server, "Bring me back")
    _open_list(page)
    _swipe(page, "Bring me back", 0.5)
    page.wait_for_selector("#undo-toast", timeout=10000)
    _wait_gone(page, "Bring me back")

    page.locator("#undo-toast").click()
    page.wait_for_selector(_item("Bring me back"), timeout=10000)


def test_swipe_postpone_raises_an_undo_bubble(page, context, live_server):
    _add_todo(context, live_server, "Undo me later")
    _open_list(page)
    _swipe(page, "Undo me later", -0.75)
    toast = page.locator("#undo-toast")
    toast.wait_for(timeout=10000)
    assert "Undo me later" in toast.inner_text()
    assert "postponed" in toast.inner_text()


def test_undo_after_a_postpone_swipe_brings_the_row_back_undated(
    page, context, live_server
):
    """The row was undated, so undo has to clear the date the swipe gave it."""
    _add_todo(context, live_server, "Later then back")
    _open_list(page)
    _swipe(page, "Later then back", -0.75)
    page.wait_for_selector("#undo-toast", timeout=10000)
    _wait_gone(page, "Later then back")

    page.locator("#undo-toast").click()
    page.wait_for_selector(_item("Later then back"), timeout=10000)
    # Back on the active list with no due badge, exactly as it started.
    assert page.locator(f"{_item('Later then back')} .todo-due").count() == 0


def test_undo_after_a_hold_swipe_restores_the_row(page, context, live_server):
    _add_todo(context, live_server, "Held then back")
    _open_list(page)
    _swipe(page, "Held then back", -0.4)
    page.wait_for_selector("#undo-toast", timeout=10000)
    _wait_gone(page, "Held then back")

    page.locator("#undo-toast").click()
    page.wait_for_selector(_item("Held then back"), timeout=10000)
