"""Browser tests for the mobile todo list.

The mobile UI is chosen by User-Agent (``HEADER_MOBILE_DEVICE``), so the context
below pretends to be an iPhone. It has no selection checkboxes and no batch
menu: a swipe across a row is the only way to act on it, and the hidden buttons
in the list form are what the gesture submits.

Swipe distances are measured against a threshold of a quarter of the row width,
so the offsets here are expressed in those terms rather than raw pixels.
"""

import io
import re

import pytest
from PIL import Image
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

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


@pytest.fixture
def as_alice(playwright, second_user, live_server):
    """A request context logged in as the other user.

    A task that came *from* somebody else cannot be made through the admin's
    own session, so the tests that need one post it as her.
    """
    request_context = playwright.request.new_context()
    resp = request_context.post(
        f"{live_server}/login",
        form={
            "username": second_user["username"],
            "password": "alicepassword1!",
            "came_from": "/todos",
        },
        max_redirects=0,
    )
    assert resp.status == 303, f"Alice could not log in: {resp.status}"
    yield request_context
    request_context.dispose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _item(text: str) -> str:
    return f'.todo-item[data-todo-text="{text}"]'


def _add_todo_via(request_context, live_server, raw: str) -> None:
    """Create a todo through the add endpoint, as whoever that context is.

    The endpoint takes the owner from the session, so who posts decides whose
    task it becomes — which is the whole difference between the filters.
    """
    resp = request_context.post(
        f"{live_server}/todos/add", form={"text": raw}, max_redirects=0
    )
    assert resp.status == 303, f"Adding {raw!r} failed: {resp.status}"


def _add_todo(context, live_server, raw: str) -> None:
    """Create a todo as the logged-in admin."""
    _add_todo_via(context.request, live_server, raw)


def _open_list(page, url: str = "/todos") -> None:
    page.goto(url)
    page.wait_for_selector("#todo-list .todo-item, .todo-list-empty", timeout=10000)


def _wait_wired(page, selector: str) -> None:
    """Wait until hyperscript has wired the element's handlers.

    The list arrives by htmx swap and hyperscript initialises the new nodes
    afterwards; a gesture or tap dispatched in between is simply dropped.
    `_hyperscript.initialized` is the flag hyperscript sets once it has.
    """
    page.wait_for_selector(selector, timeout=10000)
    page.wait_for_function(
        """(selector) => {
            const el = document.querySelector(selector);
            return !!(el && el._hyperscript && el._hyperscript.initialized);
        }""",
        arg=selector,
        timeout=10000,
    )


def _wait_swipe_ready(page, text: str) -> None:
    _wait_wired(page, _item(text))


def _select(page, text: str) -> None:
    """Tick a row's checkbox. Ticking selects; it does not act on its own."""
    checkbox = f"{_item(text)} .todo-checkbox"
    page.wait_for_selector(checkbox, timeout=10000)
    page.locator(checkbox).click()
    page.wait_for_selector("#mobile-selection-actions:not(.d-none)", timeout=5000)


def _save_edit(page) -> None:
    """Save the edit sheet.

    A field with a picker leaves its dropdown over the buttons. Moving focus to
    the title closes it first — which is what a real tap does too, since the
    blur lands before the click.
    """
    page.locator("#mobile-edit-title").click()
    page.locator("#mobile-edit-form button[type=submit]").click()


def _set_title(page, text: str) -> None:
    """Retitle the open task.

    The title lives in the sheet header and edits in place, the way it does on
    the desktop panel; hyperscript writes it through to the form's field.
    """
    page.locator("#mobile-edit-title").fill(text)


def _add_tag(page, tag: str) -> None:
    """Type a tag into the pill field and commit it with a space.

    The entry span is empty, so it has no size to tap; the box around it is
    what takes the tap and hands the focus on, on a phone as on the desktop.
    """
    page.locator("#field-tags .form-control").click()
    page.keyboard.type(tag)
    page.keyboard.press(" ")


def _remove_tag(page, tag: str) -> None:
    page.locator(f'#field-tags .badge:has-text("{tag}") .bi-x').click()


def _act(page, label: str) -> None:
    page.locator(f"#mobile-selection-actions button:has-text('{label}')").click()


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
# Coming back to the app
# ---------------------------------------------------------------------------


def _become(page, state: str) -> None:
    """Fake a visibility transition.

    Headless Chromium keeps every page visible — `bring_to_front` does not
    change `document.visibilityState` — so the state is overridden and the
    event the handler listens for is dispatched directly.
    """
    page.evaluate(
        """(state) => {
            Object.defineProperty(document, 'visibilityState', {
                configurable: true, get: () => state,
            });
            document.dispatchEvent(new Event('visibilitychange'));
        }""",
        state,
    )


def test_list_refreshes_when_the_app_becomes_visible(page, context, live_server):
    _open_list(page)
    # Something lands while the phone is showing something else.
    _add_todo(context, live_server, "Added while away")
    assert page.locator(_item("Added while away")).count() == 0

    _become(page, "visible")
    page.wait_for_selector(_item("Added while away"), timeout=10000)


def test_list_does_not_refresh_on_the_way_out(page, context, live_server):
    """visibilitychange fires when hiding too; only becoming visible reloads."""
    _open_list(page)
    _add_todo(context, live_server, "Added while away")

    _become(page, "hidden")
    page.wait_for_timeout(1000)
    assert page.locator(_item("Added while away")).count() == 0


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


# ---------------------------------------------------------------------------
# The edit sheet
# ---------------------------------------------------------------------------


def _open_edit(page, text: str, attempts: int = 3):
    """Tap a row's text — the checkbox is the other target and completes it.

    The span carries both the hx-get and the hyperscript that opens the sheet,
    so it has to be wired first; and because opening is idempotent, a tap the
    list swallowed mid-swap can simply be repeated.

    What it waits for is the tab strip rather than the form: a task with a
    checklist opens on the checklist, leaving the form in a pane that is
    present but not on screen.
    """
    target = f"{_item(text)} .flex-grow-1"
    for attempt in range(attempts):
        _wait_wired(page, target)
        page.locator(target).first.click()
        try:
            page.wait_for_selector("#mobile-edit.show .tab-content", timeout=3000)
            return
        except PlaywrightTimeoutError:
            if attempt == attempts - 1:
                raise


def test_tapping_a_row_opens_the_edit_sheet_filled_in(page, context, live_server):
    _add_todo(context, live_server, "Edit me #garden ^today ~water it")
    _open_list(page)
    _open_edit(page, "Edit me")
    assert page.locator("#mobile-edit-title").inner_text() == "Edit me"
    assert page.locator("#m-text").input_value() == "Edit me"
    assert page.locator('#field-tags input[name="tags[]"]').input_value() == "garden"
    assert page.locator("#m-due").input_value() != ""
    assert page.locator("#m-note").input_value() == "water it"


def test_editing_the_title_saves_and_closes_the_sheet(page, context, live_server):
    _add_todo(context, live_server, "Old title")
    _open_list(page)
    _open_edit(page, "Old title")
    _set_title(page, "New title")
    _save_edit(page)
    page.wait_for_selector(_item("New title"), timeout=10000)
    page.wait_for_selector("#mobile-edit.show", state="detached", timeout=10000)


def test_editing_tags_as_pills(page, context, live_server):
    _add_todo(context, live_server, "Retag me #old")
    _open_list(page)
    _open_edit(page, "Retag me")
    _remove_tag(page, "old")
    _add_tag(page, "kitchen")
    _add_tag(page, "garden")
    _save_edit(page)
    page.wait_for_selector('.tag-group-header[data-tag="garden"]', timeout=10000)
    assert page.locator('.tag-group-header[data-tag="kitchen"]').count() == 1
    assert page.locator('.tag-group-header[data-tag="old"]').count() == 0


def test_editing_accepts_a_smart_due_date(page, context, live_server):
    _add_todo(context, live_server, "Schedule me")
    _open_list(page)
    _open_edit(page, "Schedule me")
    page.locator("#m-due").fill("next week")
    _save_edit(page)
    _wait_gone(page, "Schedule me")
    page.goto("/todos?status=scheduled")
    page.wait_for_selector(_item("Schedule me"), timeout=10000)


def test_clearing_the_repeat_field_removes_the_rule(page, context, live_server):
    _add_todo(context, live_server, "Stop repeating *every week")
    _open_list(page)
    page.wait_for_selector(f"{_item('Stop repeating')} .todo-recurrence", timeout=10000)
    _open_edit(page, "Stop repeating")
    assert "every week" in page.locator("#m-recurrence").input_value()
    page.locator("#m-recurrence").fill("")
    _save_edit(page)
    page.wait_for_function(
        f"document.querySelectorAll('{_item('Stop repeating')} .todo-recurrence')"
        ".length === 0",
        timeout=10000,
    )


def test_cancel_closes_the_sheet_without_saving(page, context, live_server):
    _add_todo(context, live_server, "Leave me be")
    _open_list(page)
    _open_edit(page, "Leave me be")
    _set_title(page, "changed")
    page.locator("#mobile-edit-form button:has-text('Cancel')").click()
    page.wait_for_selector("#mobile-edit.show", state="detached", timeout=5000)
    page.reload()
    page.wait_for_selector(_item("Leave me be"), timeout=10000)


def test_the_title_edits_in_the_sheet_header(page, context, live_server):
    """The header carries the title, and writes it through to the form."""
    _add_todo(context, live_server, "Header title")
    _open_list(page)
    _open_edit(page, "Header title")
    title = page.locator("#mobile-edit-title")
    assert title.get_attribute("contenteditable") == "plaintext-only"
    # The body has no title field of its own; the header stands in for it.
    assert page.locator("#mobile-edit-body input[type=text][name=text]").count() == 0
    title.fill("Retitled from the header")
    assert page.locator("#m-text").input_value() == "Retitled from the header"


def test_editing_assignees_as_pills(page, context, live_server):
    _add_todo(context, live_server, "Hand me over @admin")
    _open_list(page)
    _open_edit(page, "Hand me over")
    pill = page.locator('#field-assignees input[name="assignees[]"]')
    assert pill.input_value() == "admin"
    page.locator('#field-assignees .badge:has-text("admin") .bi-x').click()
    _save_edit(page)
    _open_edit(page, "Hand me over")
    page.wait_for_selector(
        '#field-assignees input[name="assignees[]"]', state="detached", timeout=10000
    )


def test_links_are_shown_but_not_editable(page, context, live_server):
    """Links are there to follow on a phone; editing one needs a pointer."""
    _add_todo(context, live_server, "Read up [Docs](https://docs.example.com)")
    _open_list(page)
    _open_edit(page, "Read up")
    link = page.locator("#m-links a").first
    assert link.inner_text() == "Docs"
    assert link.get_attribute("href") == "https://docs.example.com"
    assert page.locator("#m-links .new-link").count() == 0


# ---------------------------------------------------------------------------
# Checking off is a separate target from editing
# ---------------------------------------------------------------------------


def test_ticking_selects_but_does_not_complete(page, context, live_server):
    """Ticking is a selection; the row stays until an action is chosen."""
    _add_todo(context, live_server, "Tick me")
    _open_list(page)
    _select(page, "Tick me")
    page.wait_for_timeout(1000)
    assert page.locator(_item("Tick me")).count() == 1
    assert page.locator("#undo-toast").count() == 0
    assert page.locator("#mobile-edit.show").count() == 0


def test_the_action_bar_appears_only_with_a_selection(page, context, live_server):
    _add_todo(context, live_server, "Pick me")
    _open_list(page)
    assert page.locator("#mobile-selection-actions.d-none").count() == 1
    _select(page, "Pick me")
    page.locator(f"{_item('Pick me')} .todo-checkbox").click()
    page.wait_for_selector(
        "#mobile-selection-actions.d-none", state="attached", timeout=5000
    )


def test_completing_a_selection_from_the_action_bar(page, context, live_server):
    _add_todo(context, live_server, "Finish me")
    _open_list(page)
    _select(page, "Finish me")
    _act(page, "Done")
    _wait_gone(page, "Finish me")
    page.goto("/todos?status=done")
    page.wait_for_selector(_item("Finish me"), timeout=10000)


def test_a_held_task_can_be_brought_back(page, context, live_server):
    """Activate is why the checkbox is a selection rather than a shortcut."""
    _add_todo(context, live_server, "Held thing")
    _open_list(page)
    _swipe(page, "Held thing", -0.4)
    _wait_gone(page, "Held thing")

    page.goto("/todos?status=on_hold")
    _select(page, "Held thing")
    _act(page, "Activate")
    _wait_gone(page, "Held thing")
    page.goto("/todos?status=active")
    page.wait_for_selector(_item("Held thing"), timeout=10000)


def test_a_finished_task_can_be_brought_back(page, context, live_server):
    _add_todo(context, live_server, "Finished thing")
    _open_list(page)
    _select(page, "Finished thing")
    _act(page, "Done")
    _wait_gone(page, "Finished thing")

    page.goto("/todos?status=done")
    _select(page, "Finished thing")
    _act(page, "Activate")
    _wait_gone(page, "Finished thing")
    page.goto("/todos?status=active")
    page.wait_for_selector(_item("Finished thing"), timeout=10000)


def test_an_action_bar_completion_raises_an_undo_bubble(page, context, live_server):
    _add_todo(context, live_server, "Tick then undo")
    _open_list(page)
    _select(page, "Tick then undo")
    _act(page, "Done")
    page.wait_for_selector("#undo-toast", timeout=10000)
    _wait_gone(page, "Tick then undo")
    page.locator("#undo-toast").click()
    page.wait_for_selector(_item("Tick then undo"), timeout=10000)


# ---------------------------------------------------------------------------
# Adding, filtering, logging out
# ---------------------------------------------------------------------------


def _open_add(page):
    page.locator("nav a[aria-label='New task']").click()
    page.wait_for_selector("#mobile-add.show #n-text", timeout=5000)


def test_adding_a_task_from_the_bottom_nav(page, context, live_server):
    """The title still takes markers, so a one-liner works untouched."""
    _open_list(page)
    _open_add(page)
    page.locator("#n-text").fill("Added on the phone #errands")
    page.locator("#mobile-add form button[type=submit]").click()
    page.wait_for_selector(_item("Added on the phone"), timeout=10000)
    assert page.locator('.tag-group-header[data-tag="errands"]').count() == 1


def test_adding_a_task_field_by_field(page, context, live_server):
    """The new sheet has the same fields as the edit sheet."""
    _open_list(page)
    _open_add(page)
    page.locator("#n-text").fill("Fully specified")
    page.locator("#n-tags").fill("kitchen")
    page.locator("#n-note").fill("from the fields")
    page.locator("#mobile-add form button[type=submit]").click()
    page.wait_for_selector(_item("Fully specified"), timeout=10000)
    assert page.locator('.tag-group-header[data-tag="kitchen"]').count() == 1
    note = page.locator(f"{_item('Fully specified')} .todo-note-display")
    assert "from the fields" in note.inner_text()


def test_adding_with_a_smart_due_date_field(page, context, live_server):
    _open_list(page)
    _open_add(page)
    page.locator("#n-text").fill("Due next week")
    page.locator("#n-due").fill("next week")
    # Dismiss the picker it opened — it sits over the buttons below.
    page.locator("#n-text").click()
    page.locator("#mobile-add form button[type=submit]").click()
    # The add swaps the whole body; navigating before that lands would race it.
    page.wait_for_selector("#mobile-add.show", state="detached", timeout=10000)
    page.goto("/todos?status=scheduled")
    page.wait_for_selector(_item("Due next week"), timeout=10000)


def test_markers_in_the_title_and_fields_combine(page, context, live_server):
    """A tag typed in the title is kept alongside one typed in the field."""
    _open_list(page)
    _open_add(page)
    page.locator("#n-text").fill("Both ways #fromtitle")
    page.locator("#n-tags").fill("fromfield")
    page.locator("#mobile-add form button[type=submit]").click()
    page.wait_for_selector(_item("Both ways"), timeout=10000)
    assert page.locator('.tag-group-header[data-tag="fromtitle"]').count() == 1
    assert page.locator('.tag-group-header[data-tag="fromfield"]').count() == 1


# ---------------------------------------------------------------------------
# The desktop pickers, on the phone
# ---------------------------------------------------------------------------


def test_due_field_opens_the_date_picker_and_fills_from_it(page, context, live_server):
    """A quick option hands over the date it resolved, not the label it shows."""
    _open_list(page)
    _open_add(page)
    page.locator("#n-due").click()
    page.wait_for_selector("#n-due + .picker .todo-mini-cal", timeout=10000)
    option = page.locator("#n-due + .picker li[data-picker-value]").first
    picked = option.get_attribute("data-picker-value")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", picked)
    option.click()
    assert page.locator("#n-due").input_value() == picked


def test_repeat_field_opens_the_recurrence_picker(page, context, live_server):
    _open_list(page)
    _open_add(page)
    page.locator("#n-recurrence").click()
    page.wait_for_selector(
        "#n-recurrence + .picker li[data-picker-value]", timeout=10000
    )


def test_edit_sheet_pickers_see_the_current_value(page, context, live_server):
    """The picker echoes what is typed, which is what mobile has to pass along."""
    _add_todo(context, live_server, "Picker echo")
    _open_list(page)
    _open_edit(page, "Picker echo")
    page.locator("#m-due").fill("tomorrow")
    # The first row is what the picker made of the text it was given, which is
    # the bit mobile has to pass along without a JS expression. The picker
    # answers on focus too, so wait for the one carrying the typed text.
    page.wait_for_function(
        """() => {
            const row = document.querySelector('#m-due + .picker li');
            return !!row && row.textContent.includes('tomorrow');
        }""",
        timeout=10000,
    )


def test_menu_switches_which_items_are_shown(page, context, live_server):
    _add_todo(context, live_server, "An active one")
    _add_todo(context, live_server, "A held one")
    _open_list(page)
    _swipe(page, "A held one", -0.4)
    _wait_gone(page, "A held one")

    page.locator("nav a[aria-label='Menu']").click()
    page.wait_for_selector("#offcanvasBottom.show", timeout=5000)
    page.locator("#offcanvasBottom a:has-text('On hold')").click()
    page.wait_for_selector(_item("A held one"), timeout=10000)
    assert page.locator(_item("An active one")).count() == 0


def test_menu_offers_log_off(page, live_server):
    _open_list(page)
    page.locator("nav a[aria-label='Menu']").click()
    page.wait_for_selector("#offcanvasBottom.show", timeout=5000)
    page.locator("#offcanvasBottom button:has-text('Log off')").click()
    page.wait_for_url("**/login**", timeout=10000)


def _add_sheet_pick(
    page, field: str, typed: str, wanted: str, attempts: int = 5
) -> None:
    """Type into an add-sheet field and tap `wanted` in the picker it opens.

    The field asks the picker again on every keystroke, so a tap can land on a
    row that htmx is in the middle of replacing. Tapping the same option twice
    does no harm — the second one writes the same word — so simply retry until
    the field takes it.
    """
    option = f"{field} + .picker li[data-picker-value='{wanted}']"
    for attempt in range(attempts):
        # Focusing is what opens the picker, so a retry starts from there.
        page.locator(field).click()
        page.locator(field).fill(typed)
        try:
            # The field asks again on focus and on every keystroke, so two
            # answers can be on their way at once. Waiting for the field to be
            # out of flight means the row tapped below is the one that stays.
            page.wait_for_function(
                """([selector, word]) => {
                    const field = document.querySelector(selector);
                    if (!field || field.classList.contains('htmx-request')) {
                        return false;
                    }
                    const box = field.nextElementSibling;
                    return !!box && !!box.querySelector(
                        `li[data-picker-value="${word}"]`);
                }""",
                arg=[field, wanted],
                timeout=5000,
            )
            page.locator(option).click(timeout=3000)
            # A pick always leaves a trailing space, which is what tells it
            # apart from the same word simply having been typed.
            page.wait_for_function(
                """([selector, word]) => {
                    const field = document.querySelector(selector);
                    return field && field.value.endsWith(word + ' ');
                }""",
                arg=[field, wanted],
                timeout=2000,
            )
            return
        except PlaywrightTimeoutError:
            if attempt == attempts - 1:
                raise


@pytest.mark.flaky(reruns=2)
def test_tag_picker_fills_the_add_sheet_field(page, context, live_server):
    """The new sheet has no pills, so a pick replaces the word being typed."""
    _add_todo(context, live_server, "Something tagged #garden")
    _open_list(page)
    _open_add(page)
    _add_sheet_pick(page, "#n-tags", "gar", "garden")
    assert page.locator("#n-tags").input_value() == "garden "
    # A second pick appends rather than overwriting what is already there.
    _add_sheet_pick(page, "#n-tags", "garden kitch", "kitch")
    assert page.locator("#n-tags").input_value() == "garden kitch "


@pytest.mark.flaky(reruns=2)
def test_assignee_picker_fills_the_add_sheet_field(page, context, live_server):
    _open_list(page)
    _open_add(page)
    _add_sheet_pick(page, "#n-assignees", "adm", "admin")
    assert page.locator("#n-assignees").input_value() == "admin "


def test_opening_a_picker_does_not_move_the_fields_below_it(page, context, live_server):
    """The picker floats over the sheet.

    Laid out inline it pushed everything under it down as it opened and closed,
    so moving from field to field made the whole page jump.
    """
    _open_list(page)
    _open_add(page)
    page.locator("#n-note").click()
    before = page.locator("#n-note").bounding_box()["y"]
    page.locator("#n-due").click()
    page.wait_for_selector("#n-due + .picker .todo-mini-cal", timeout=10000)
    assert page.locator("#n-note").bounding_box()["y"] == before
    # Tapping straight through an open picker hits the picker, so close it the
    # way a thumb does — somewhere clear of it first.
    page.locator("#mobile-add-title").click()
    page.locator("#n-recurrence").click()
    page.wait_for_selector(
        "#n-recurrence + .picker li[data-picker-value]", timeout=10000
    )
    assert page.locator("#n-note").bounding_box()["y"] == before


# ---------------------------------------------------------------------------
# Looking at the pictures
# ---------------------------------------------------------------------------


def _attach(context, live_server, todo_id: int, *names: str) -> None:
    """Upload one small picture per name to a todo."""
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color=(200, 30, 30)).save(buf, format="JPEG")
    jpeg = buf.getvalue()
    # One request each: a multipart body here is a mapping, so it cannot
    # carry the same field name more than once.
    for name in names:
        resp = context.request.post(
            f"{live_server}/todos/{todo_id}/attachments",
            multipart={
                "files[]": {"name": name, "mimeType": "image/jpeg", "buffer": jpeg}
            },
        )
        assert resp.ok, f"Uploading {name} failed: {resp.status}"


def _todo_id(page, text: str) -> int:
    return int(page.locator(_item(text)).first.get_attribute("data-todo-id"))


def _open_photo(page, text: str, nth: int = 0):
    thumb = page.locator(f"{_item(text)} .todo-attachment-thumbs img").nth(nth)
    thumb.click()
    page.wait_for_selector("#mobile-photo.show", timeout=5000)
    return thumb


def test_tapping_a_picture_opens_it_instead_of_the_edit_sheet(
    page, context, live_server, attachments_dir
):
    _add_todo(context, live_server, "Look at this")
    _open_list(page)
    _attach(context, live_server, _todo_id(page, "Look at this"), "holiday.jpg")
    page.reload()
    _wait_wired(page, f"{_item('Look at this')} .todo-attachment-thumbs")

    # The row fetches its edit panel the moment it is tapped, so recording
    # what was asked for says more than looking at the sheet, which would not
    # have opened yet either way.
    asked: list[str] = []
    page.on("request", lambda request: asked.append(request.url))

    _open_photo(page, "Look at this")
    # The full picture, not the thumbnail the list shows.
    assert page.locator("#mobile-photo-image").get_attribute("src").endswith("/full")
    assert page.locator("#mobile-photo-name").inner_text() == "holiday.jpg"
    # The tap stopped at the picture; the row never went for its panel.
    assert [url for url in asked if "details-panel" in url] == []
    assert page.locator("#mobile-edit.show").count() == 0


def test_a_single_picture_offers_nothing_to_page_through(
    page, context, live_server, attachments_dir
):
    _add_todo(context, live_server, "Just the one")
    _open_list(page)
    _attach(context, live_server, _todo_id(page, "Just the one"), "only.jpg")
    page.reload()
    _wait_wired(page, f"{_item('Just the one')} .todo-attachment-thumbs")

    _open_photo(page, "Just the one")
    assert page.locator("#mobile-photo-nav.d-none").count() == 1


def test_paging_through_a_row_of_pictures(page, context, live_server, attachments_dir):
    _add_todo(context, live_server, "Three of them")
    _open_list(page)
    _attach(
        context,
        live_server,
        _todo_id(page, "Three of them"),
        "first.jpg",
        "second.jpg",
        "third.jpg",
    )
    page.reload()
    _wait_wired(page, f"{_item('Three of them')} .todo-attachment-thumbs")

    _open_photo(page, "Three of them", nth=1)
    assert page.locator("#mobile-photo-name").inner_text() == "second.jpg"
    assert page.locator("#mobile-photo-nav.d-none").count() == 0

    page.locator("#mobile-photo-nav button[aria-label='Next']").click()
    page.wait_for_function(
        "() => document.getElementById('mobile-photo-name').textContent === 'third.jpg'",
        timeout=5000,
    )
    # Past the last one it comes back round rather than dead-ending.
    page.locator("#mobile-photo-nav button[aria-label='Next']").click()
    page.wait_for_function(
        "() => document.getElementById('mobile-photo-name').textContent === 'first.jpg'",
        timeout=5000,
    )
    page.locator("#mobile-photo-nav button[aria-label='Previous']").click()
    page.wait_for_function(
        "() => document.getElementById('mobile-photo-name').textContent === 'third.jpg'",
        timeout=5000,
    )


def test_tapping_the_picture_closes_the_viewer(
    page, context, live_server, attachments_dir
):
    _add_todo(context, live_server, "Close me")
    _open_list(page)
    _attach(context, live_server, _todo_id(page, "Close me"), "shut.jpg")
    page.reload()
    _wait_wired(page, f"{_item('Close me')} .todo-attachment-thumbs")

    _open_photo(page, "Close me")
    page.locator("#mobile-photo-image").click()
    page.wait_for_selector("#mobile-photo.show", state="detached", timeout=5000)


# ---------------------------------------------------------------------------
# Whose tasks to show
# ---------------------------------------------------------------------------


def _menu(page):
    page.locator("nav a[aria-label='Menu']").click()
    page.wait_for_selector("#offcanvasBottom.show", timeout=5000)


def _choose(page, group: str, label: str) -> None:
    """Pick an entry from one of the menu's two lists."""
    page.locator(
        f"#offcanvasBottom h6:has-text('{group}') + .list-group a:has-text('{label}')"
    ).click()


def test_the_menu_offers_the_other_peoples_lists(page, context, live_server):
    _add_todo(context, live_server, "Mine alone")
    _open_list(page)
    _menu(page)
    whose = "#offcanvasBottom h6:has-text('Whose') + .list-group"
    assert [
        entry.strip() for entry in page.locator(f"{whose} a").all_inner_texts()
    ] == ["My Tasks\n1", "Assigned\n0", "Delegated\n0", "All\n1"]


def test_switching_whose_tasks_keeps_the_status(page, context, live_server):
    """The two menus are one pair; changing either must not reset the other."""
    _add_todo(context, live_server, "Somebody else's *every week")
    _open_list(page, "/todos?status=done")
    _menu(page)
    _choose(page, "Whose", "All")
    page.wait_for_url("**/todos?**", timeout=10000)
    assert "status=done" in page.url
    assert "filter=all" in page.url
    _menu(page)
    # And back the other way: the filter survives a change of status.
    _choose(page, "Show", "Active")
    page.wait_for_selector(_item("Somebody else's"), timeout=10000)
    assert "filter=all" in page.url


def test_the_list_says_which_list_it_is(page, context, live_server):
    _open_list(page, "/todos?status=scheduled&filter=delegated_in")
    header = page.locator("#mobile-list-header")
    assert "Assigned" in header.inner_text()
    assert "Scheduled" in header.inner_text()
    # And it is the way back to the menu.
    header.click()
    page.wait_for_selector("#offcanvasBottom.show", timeout=5000)


def test_a_delegated_task_is_only_reachable_through_its_filter(
    page, context, live_server
):
    """Which is the whole point: handing a task on takes it off your own list,
    and until now a phone had no way back to it."""
    _add_todo(context, live_server, "Handed off @alice")
    _add_todo(context, live_server, "Kept for myself")

    _open_list(page)
    page.wait_for_selector(_item("Kept for myself"), timeout=10000)
    assert page.locator(_item("Handed off")).count() == 0

    _menu(page)
    _choose(page, "Whose", "Delegated")
    page.wait_for_selector(_item("Handed off"), timeout=10000)
    assert page.locator(_item("Kept for myself")).count() == 0


def test_a_task_from_someone_else_shows_up_under_assigned(
    page, context, live_server, as_alice
):
    """ "Assigned" narrows your own list down to what other people put there."""
    _add_todo_via(as_alice, live_server, "Please look at this @admin")
    _add_todo(context, live_server, "Thought of it myself")

    # Both are on the default list: a task assigned to you is yours too.
    _open_list(page)
    page.wait_for_selector(_item("Please look at this"), timeout=10000)
    assert page.locator(_item("Thought of it myself")).count() == 1

    _menu(page)
    _choose(page, "Whose", "Assigned")
    page.wait_for_selector(_item("Please look at this"), timeout=10000)
    assert page.locator(_item("Thought of it myself")).count() == 0

    # And the menu counts it, which is what says the list is worth opening.
    _menu(page)
    assigned = page.locator(
        "#offcanvasBottom h6:has-text('Whose') + .list-group a:has-text('Assigned')"
    )
    assert assigned.locator(".badge").inner_text() == "1"


# ---------------------------------------------------------------------------
# A task that is also a checklist
# ---------------------------------------------------------------------------


def _protocol_run(context, live_server, title: str, items: list[str]) -> None:
    """Create a protocol, give it items and start a run, all through the API.

    The run's own todo is what turns up in the list, and it is the one that
    carries the checklist.
    """
    resp = context.request.post(
        f"{live_server}/protocols/new", form={"title": title}, max_redirects=0
    )
    assert resp.status == 303, f"Creating the protocol failed: {resp.status}"
    protocol_id = resp.headers["location"].rstrip("/").split("/")[-2]
    for text in items:
        resp = context.request.post(
            f"{live_server}/protocols/{protocol_id}/items", form={"text": text}
        )
        assert resp.ok, f"Adding item {text!r} failed: {resp.status}"
    resp = context.request.post(
        f"{live_server}/protocols/{protocol_id}/start", max_redirects=0
    )
    assert resp.status == 303, f"Starting the run failed: {resp.status}"


def test_a_task_with_a_checklist_shows_it(page, context, live_server):
    """It was not reachable at all on a phone before: the sheet only ever
    showed the fields."""
    _protocol_run(context, live_server, "Weekly tidy", ["fridge", "pantry"])
    _open_list(page)
    _open_edit(page, "Weekly tidy")

    # The checklist is what comes up, since it is why you opened this one.
    page.wait_for_selector("#mobile-checklist-pane.active #protocol-run", timeout=5000)
    assert page.locator("#mobile-checklist-pane .protocol-run-item").count() == 2
    assert page.locator("#mobile-checklist-pane").inner_text().count("fridge") == 1


def test_the_other_tab_still_edits_the_task(page, context, live_server):
    _protocol_run(context, live_server, "Weekly tidy", ["fridge"])
    _open_list(page)
    _open_edit(page, "Weekly tidy")
    page.wait_for_selector("#mobile-checklist-pane.active", timeout=5000)

    page.locator("#mobile-details-tab").click()
    page.wait_for_selector(
        "#mobile-details-pane.active #mobile-edit-form", timeout=5000
    )
    page.locator("#m-note").fill("start with the freezer")
    _save_edit(page)

    _open_edit(page, "Weekly tidy")
    page.locator("#mobile-details-tab").click()
    page.wait_for_selector("#mobile-details-pane.active", timeout=5000)
    assert page.locator("#m-note").input_value() == "start with the freezer"


def test_an_ordinary_task_gets_no_tabs(page, context, live_server):
    """Nothing to choose between, so nothing to choose from."""
    _add_todo(context, live_server, "Just a task")
    _open_list(page)
    _open_edit(page, "Just a task")

    assert page.locator("#mobile-checklist-tab").count() == 0
    # And the fields are simply there, rather than behind a hidden tab.
    assert page.locator("#mobile-details-pane.active #m-note").is_visible()


def test_ticking_a_checklist_item_off_works_from_the_sheet(page, context, live_server):
    _protocol_run(context, live_server, "Weekly tidy", ["fridge", "pantry"])
    _open_list(page)
    _open_edit(page, "Weekly tidy")
    page.wait_for_selector("#mobile-checklist-pane .protocol-run-item", timeout=5000)

    page.locator('#mobile-checklist-pane [data-action="done"]').first.click()
    page.wait_for_selector(
        "#mobile-checklist-pane .protocol-run-item.status-done", timeout=5000
    )


def test_the_sheet_closes_when_the_last_item_is_ticked_off(page, context, live_server):
    """The run closes with its last item, and there is nothing left in here."""
    _protocol_run(context, live_server, "One thing", ["fridge"])
    _open_list(page)
    _open_edit(page, "One thing")
    page.wait_for_selector("#mobile-checklist-pane .protocol-run-item", timeout=5000)

    page.locator('#mobile-checklist-pane [data-action="done"]').first.click()
    page.wait_for_selector("#mobile-edit.show", state="detached", timeout=10000)


def test_the_checklist_and_its_tabs_reach_the_edges(page, context, live_server):
    """A phone has little enough width without the sheet padding it twice.

    The checklist rows bring their own spacing, so the sheet adds none.
    """
    _protocol_run(context, live_server, "Weekly tidy", ["fridge"])
    _open_list(page)
    _open_edit(page, "Weekly tidy")
    page.wait_for_selector("#mobile-checklist-pane #protocol-run", timeout=5000)

    sheet = page.locator("#mobile-edit").bounding_box()
    for selector in ("#mobile-edit .nav-tabs", "#mobile-checklist-pane #protocol-run"):
        box = page.locator(selector).bounding_box()
        assert box["x"] == sheet["x"], selector
        assert box["width"] == sheet["width"], selector


def test_the_fields_keep_their_breathing_room(page, context, live_server):
    """Taking the padding off the sheet must not push the form to the edge."""
    _add_todo(context, live_server, "Just a task")
    _open_list(page)
    _open_edit(page, "Just a task")

    sheet = page.locator("#mobile-edit").bounding_box()
    field = page.locator("#m-note").bounding_box()
    assert field["x"] > sheet["x"]
    assert field["x"] + field["width"] < sheet["x"] + sheet["width"]
