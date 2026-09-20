"""Browser tests for the todo feature.

The add form is a plain text input; everything that used to need a picker
(tags, due date, recurrence, note, links, assignees) is expressed with the
inline markers `#`, `^`, `*`, `~`, `[label](url)` and `@` that
``parse_todo_input`` understands.  Views are selected via the ``status`` query
parameter on ``/todos``, and the details pane is the server-rendered
``_todo_details_panel.pt`` form.
"""

import datetime

import pytest

from ._browser_helpers import select_row

STATUS_ACTIVE = "/todos?status=active"
STATUS_HOLD = "/todos?status=on_hold"
STATUS_SCHEDULED = "/todos?status=scheduled"
STATUS_DONE = "/todos?status=done"


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
    assert resp.status == 303, f"Login failed with HTTP {resp.status}"
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
# Helpers
# ---------------------------------------------------------------------------


def _item(text: str) -> str:
    """Selector for the row of the todo whose stored text is `text`."""
    return f'.todo-item[data-todo-text="{text}"]'


def _js_item_count(text: str) -> str:
    """JS expression counting the rows for `text` (for wait_for_function)."""
    escaped = text.replace('"', '\\"')
    return (
        "document.querySelectorAll("
        f"'.todo-item[data-todo-text=\\\"{escaped}\\\"]').length"
    )


def _add_todo(page, raw: str, expect: str | None = None) -> None:
    """Submit the add form and wait until the resulting row is rendered.

    `expect` is the text the todo ends up with once the markers in `raw` have
    been stripped; it defaults to `raw` for marker-free input.
    """
    inp = page.locator("#input-add-todo-text")
    inp.fill(raw)
    inp.press("Enter")
    page.wait_for_selector(_item(expect if expect is not None else raw), timeout=10000)


def _select(page, text: str) -> None:
    """Select a row, open the details pane, and release focus.

    Blurring matters: the list-level shortcuts are bound `from body` and bail
    out while an input or contenteditable has focus.
    """
    select_row(page, _item(text), "#details-panel #todo-edit-form")
    page.evaluate("document.activeElement && document.activeElement.blur()")


def _wait_gone(page, text: str) -> None:
    page.wait_for_function(f"{_js_item_count(text)} === 0", timeout=10000)


# ---------------------------------------------------------------------------
# Adding todos — plain input plus inline markers
# ---------------------------------------------------------------------------


def test_add_todo_plain_text(page):
    page.goto(STATUS_ACTIVE)
    count_before = page.locator(".todo-item").count()
    _add_todo(page, "Buy bread")
    assert page.locator(".todo-item").count() == count_before + 1


def test_add_todo_with_inline_tag(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "Buy milk #shopping", "Buy milk")
    assert page.locator('.tag-group-header[data-tag="shopping"]').count() == 1
    assert (
        page.locator('#tag-list-shopping .todo-item[data-todo-text="Buy milk"]').count()
        == 1
    )


def test_add_todo_only_tags_shows_error(page):
    page.goto(STATUS_ACTIVE)
    inp = page.locator("#input-add-todo-text")
    inp.fill("#shopping")
    inp.press("Enter")
    page.wait_for_selector("#error-toast", timeout=5000)
    assert page.locator("#error-toast").is_visible()


def test_add_todo_with_note_marker(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "Call plumber ~ask about the boiler", "Call plumber")
    note = page.locator(f"{_item('Call plumber')} .todo-note-display")
    assert "boiler" in note.inner_text()


def test_add_todo_with_link_shows_badge(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "Read article [Example](https://example.com)", "Read article")
    badge = page.locator(f"{_item('Read article')} .todo-link-badge")
    assert badge.count() == 1
    assert badge.first.get_attribute("href") == "https://example.com"
    assert "Example" in badge.first.inner_text()


def test_add_todo_with_due_date_marker_lands_in_scheduled(page):
    page.goto(STATUS_ACTIVE)
    inp = page.locator("#input-add-todo-text")
    inp.fill("Renew passport ^next week")
    inp.press("Enter")
    page.goto(STATUS_SCHEDULED)
    page.wait_for_selector(_item("Renew passport"), timeout=10000)
    assert page.locator(f"{_item('Renew passport')} .todo-due").count() == 1


def test_add_todo_with_recurrence_marker_shows_badge(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "Water plants *every week", "Water plants")
    item = page.locator(_item("Water plants"))
    assert item.locator(".todo-recurrence").count() == 1
    assert "every week" in item.locator(".todo-recurrence-label").inner_text()


# ---------------------------------------------------------------------------
# Details pane
# ---------------------------------------------------------------------------


def test_click_row_opens_details_pane(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "Pane subject")
    _select(page, "Pane subject")
    assert page.locator("#details-pane").is_visible()
    assert page.locator("#field-title h5").inner_text().strip() == "Pane subject"


def test_escape_closes_details_pane(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "Escape subject")
    _select(page, "Escape subject")
    page.keyboard.press("Escape")
    page.wait_for_selector("#details-pane.d-none", state="attached", timeout=5000)


def test_details_pane_shows_existing_tags(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "Tagged subject #garden", "Tagged subject")
    _select(page, "Tagged subject")
    page.wait_for_function(
        '!!document.querySelector(\'#field-tags input[name="tags[]"][value="garden"]\')',
        timeout=5000,
    )


def test_details_pane_shows_existing_links(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(
        page, "Link subject [Restore](https://restore.example.com)", "Link subject"
    )
    _select(page, "Link subject")
    page.wait_for_selector("#field-links a", timeout=5000)
    link = page.locator("#field-links a").first
    assert "Restore" in link.inner_text()
    assert link.get_attribute("href") == "https://restore.example.com"


def test_typing_a_link_names_it_straight_away(page):
    """The label has to be there while the panel is still open.

    It is the only chance to change it: once a save closes the panel, a
    label that only appeared then would be out of reach.
    """
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "Read later")
    _select(page, "Read later")
    page.wait_for_selector("#field-links .new-link", state="attached", timeout=5000)

    # The entry span is empty and has no size; the box around it hands the
    # focus on, which is what a click on the field does for a person too.
    page.locator("#field-links > .form-control").click()
    page.keyboard.type("https://www.example.com/blog/2024/the-article?utm_source=x")
    page.keyboard.press("Enter")

    link = page.locator("#field-links .badge a").first
    page.wait_for_selector("#field-links .badge a", timeout=5000)
    assert link.inner_text() == "example.com/blog/2024/the-article"
    # The URL itself is untouched — only what you read of it is shortened.
    assert link.get_attribute("href") == (
        "https://www.example.com/blog/2024/the-article?utm_source=x"
    )


def test_a_link_label_can_still_be_changed_by_hand(page):
    """Naming it automatically must not take the naming away."""
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "Rename my link")
    _select(page, "Rename my link")
    page.wait_for_selector("#field-links .new-link", state="attached", timeout=5000)

    page.locator("#field-links > .form-control").click()
    page.keyboard.type("https://example.com/some/page")
    page.keyboard.press("Enter")
    page.wait_for_selector("#field-links .badge a", timeout=5000)

    page.locator("#field-links .bi-pencil").first.click()
    label_field = page.locator('#field-links input[name="link.label"]')
    label_field.wait_for(state="visible", timeout=5000)
    label_field.fill("The good bit")
    page.locator("#field-links button:has-text('Set')").click()

    page.wait_for_function(
        """() => {
            const a = document.querySelector('#field-links .badge a');
            return a && a.textContent.trim() === 'The good bit';
        }""",
        timeout=5000,
    )


def test_details_pane_shows_recurrence_label(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "Rec subject *every month", "Rec subject")
    _select(page, "Rec subject")
    value = page.locator("#field-recurrence input[name='recurrence']").input_value()
    assert "every month" in value


def test_details_pane_shows_due_date(page):
    page.goto(STATUS_ACTIVE)
    inp = page.locator("#input-add-todo-text")
    inp.fill("Due subject ^tomorrow")
    inp.press("Enter")
    page.goto(STATUS_SCHEDULED)
    page.wait_for_selector(_item("Due subject"), timeout=10000)
    _select(page, "Due subject")
    assert page.locator("#field-due-date input[name='due_date']").input_value() != ""


def test_selecting_two_items_shows_multi_panel(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "Multi one")
    _add_todo(page, "Multi two")
    page.wait_for_selector(_item("Multi one"), timeout=10000)
    page.locator(f"{_item('Multi one')} .todo-checkbox").click()
    page.locator(f"{_item('Multi two')} .todo-checkbox").click()
    page.wait_for_selector("#details-panel:has-text('2 selected')", timeout=5000)


# ---------------------------------------------------------------------------
# Editing through the details pane
# ---------------------------------------------------------------------------


def test_e_key_focuses_title(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "Focus title subject")
    _select(page, "Focus title subject")
    page.keyboard.press("e")
    page.wait_for_function(
        "document.activeElement === document.querySelector('#field-title h5')",
        timeout=5000,
    )


def test_d_key_focuses_due_date(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "Focus due subject")
    _select(page, "Focus due subject")
    page.keyboard.press("d")
    page.wait_for_function(
        "document.activeElement === "
        "document.querySelector('#field-due-date input[name=\"due_date\"]')",
        timeout=5000,
    )


def test_f_key_focuses_recurrence(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "Focus rec subject")
    _select(page, "Focus rec subject")
    page.keyboard.press("f")
    page.wait_for_function(
        "document.activeElement === "
        "document.querySelector('#field-recurrence input[name=\"recurrence\"]')",
        timeout=5000,
    )


def test_edit_title_updates_row_without_duplicating(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "rename me")
    count_before = page.locator(".todo-item").count()
    _select(page, "rename me")
    title = page.locator("#field-title h5")
    title.click()
    title.press("ControlOrMeta+a")
    title.type("renamed")
    title.press("Enter")
    page.locator("#todo-edit-form input[type='submit']").click()
    page.wait_for_selector(_item("renamed"), timeout=10000)
    _wait_gone(page, "rename me")
    assert page.locator(".todo-item").count() == count_before


def test_set_recurrence_from_details_pane(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "repeat me")
    _select(page, "repeat me")
    rec = page.locator("#field-recurrence input[name='recurrence']")
    rec.fill("every week")
    rec.blur()
    page.locator("#todo-edit-form input[type='submit']").click()
    page.wait_for_selector(f"{_item('repeat me')} .todo-recurrence", timeout=10000)


def test_set_due_date_from_details_pane_moves_to_scheduled(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "schedule me")
    _select(page, "schedule me")
    due = page.locator("#field-due-date input[name='due_date']")
    due.fill("next week")
    due.blur()
    page.locator("#todo-edit-form input[type='submit']").click()
    _wait_gone(page, "schedule me")
    page.goto(STATUS_SCHEDULED)
    page.wait_for_selector(_item("schedule me"), timeout=10000)


# ---------------------------------------------------------------------------
# List actions (batch buttons driven by keyboard shortcuts)
# ---------------------------------------------------------------------------


def test_c_key_marks_selected_done(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "Done me")
    _select(page, "Done me")
    page.keyboard.press("c")
    _wait_gone(page, "Done me")
    page.goto(STATUS_DONE)
    page.wait_for_selector(_item("Done me"), timeout=10000)


def test_undo_toast_appears_and_u_restores(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "Undo me")
    _select(page, "Undo me")
    page.keyboard.press("c")
    page.wait_for_selector("#undo-toast", timeout=5000)
    _wait_gone(page, "Undo me")
    page.keyboard.press("u")
    page.wait_for_selector(_item("Undo me"), timeout=10000)


def test_h_key_puts_selected_on_hold(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "Hold me")
    _select(page, "Hold me")
    page.keyboard.press("h")
    _wait_gone(page, "Hold me")
    page.goto(STATUS_HOLD)
    page.wait_for_selector(_item("Hold me"), timeout=10000)


def test_a_key_activates_from_hold(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "Reactivate me")
    _select(page, "Reactivate me")
    page.keyboard.press("h")
    _wait_gone(page, "Reactivate me")

    page.goto(STATUS_HOLD)
    _select(page, "Reactivate me")
    page.keyboard.press("a")
    _wait_gone(page, "Reactivate me")
    page.goto(STATUS_ACTIVE)
    page.wait_for_selector(_item("Reactivate me"), timeout=10000)


def test_shift_p_postpones_selected_by_one_day(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "Postpone me")
    _select(page, "Postpone me")
    page.keyboard.press("Shift+P")
    _wait_gone(page, "Postpone me")
    page.goto(STATUS_SCHEDULED)
    row = page.locator(_item("Postpone me"))
    assert row.count() == 1
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    assert row.first.get_attribute("data-due-date") == tomorrow


def test_postpone_with_an_unparsable_interval_shows_an_error(page):
    """A bad interval reaches the user as a toast, not a silent 400."""
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "Bad interval")
    _select(page, "Bad interval")
    page.evaluate("document.getElementById('interval').value = 'not-a-date-at-all'")
    page.keyboard.press("Shift+P")
    page.wait_for_selector("#error-toast", timeout=5000)
    assert "not-a-date-at-all" in page.locator("#error-toast").inner_text()
    # And the todo stayed put.
    assert page.locator(_item("Bad interval")).count() == 1


def test_collapsing_a_tag_group_hides_its_items(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "Mow lawn #garden", "Mow lawn")
    header = page.locator('.tag-group-header[data-tag="garden"]')
    header.click()
    page.wait_for_selector(f"{_item('Mow lawn')}", state="hidden", timeout=5000)
    assert header.get_attribute("data-open") == "false"
    header.click()
    page.wait_for_selector(f"{_item('Mow lawn')}", state="visible", timeout=5000)
    assert header.get_attribute("data-open") == "true"


def test_bracket_keys_collapse_and_expand_all_groups(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "Mow lawn #garden", "Mow lawn")
    _add_todo(page, "Buy nails #diy", "Buy nails")
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.keyboard.press("[")
    page.wait_for_selector(_item("Mow lawn"), state="hidden", timeout=5000)
    page.wait_for_selector(_item("Buy nails"), state="hidden", timeout=5000)
    page.keyboard.press("]")
    page.wait_for_selector(_item("Mow lawn"), state="visible", timeout=5000)
    page.wait_for_selector(_item("Buy nails"), state="visible", timeout=5000)


@pytest.mark.flaky(reruns=2)
def test_activate_all_on_hold_button(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "Bulk activate me")
    _select(page, "Bulk activate me")
    page.keyboard.press("h")
    _wait_gone(page, "Bulk activate me")

    page.goto(STATUS_HOLD)
    page.wait_for_selector(_item("Bulk activate me"), timeout=10000)
    page.get_by_role("button", name="Activate all").click()
    page.wait_for_url("**/todos", timeout=10000)
    page.goto(STATUS_ACTIVE)
    page.wait_for_selector(_item("Bulk activate me"), timeout=10000)


# ---------------------------------------------------------------------------
# Recurrence history
# ---------------------------------------------------------------------------


@pytest.mark.flaky(reruns=2)
def test_recurrence_history_panel_opens_on_badge_click(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "Yoga *every month", "Yoga")
    page.wait_for_selector(f"{_item('Yoga')} .todo-recurrence", timeout=10000)
    page.locator(f"{_item('Yoga')} .todo-recurrence").click()
    page.wait_for_selector(".todo-history-panel", timeout=5000)
    assert page.locator(".todo-history-entry").count() >= 1
    page.locator(".todo-history-close").click()
    page.wait_for_selector(".todo-history-panel", state="detached", timeout=5000)


def test_recurrence_badge_toggles_the_history_panel(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "Pilates *every week", "Pilates")
    badge = page.locator(f"{_item('Pilates')} .todo-recurrence")
    badge.wait_for(timeout=10000)
    badge.click()
    page.wait_for_selector(".todo-history-panel", timeout=5000)
    # Clicking the same badge again closes it rather than re-fetching.
    badge.click()
    page.wait_for_selector(".todo-history-panel", state="detached", timeout=5000)
    badge.click()
    page.wait_for_selector(".todo-history-panel", timeout=5000)


def test_another_items_badge_replaces_the_open_history_panel(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "Pilates *every week", "Pilates")
    _add_todo(page, "Sauna *every month", "Sauna")
    page.locator(f"{_item('Pilates')} .todo-recurrence").click()
    page.wait_for_selector(".todo-history-panel", timeout=5000)
    page.locator(f"{_item('Sauna')} .todo-recurrence").click()
    page.wait_for_selector(".todo-history-panel:has-text('Sauna')", timeout=5000)
    assert page.locator(".todo-history-panel").count() == 1


# ---------------------------------------------------------------------------
# Help overlay
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url", [STATUS_ACTIVE, STATUS_HOLD, STATUS_SCHEDULED, STATUS_DONE]
)
def test_help_overlay_opens_with_question_mark(page, url):
    page.goto(url)
    page.keyboard.press("?")
    page.wait_for_selector("#kbd-help-overlay", state="visible", timeout=5000)
    page.keyboard.press("Escape")
    page.wait_for_selector("#kbd-help-overlay", state="hidden", timeout=5000)


def test_help_overlay_persists_after_htmx_swap(page):
    page.goto(STATUS_ACTIVE)
    _add_todo(page, "after-swap probe")
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.keyboard.press("?")
    page.wait_for_selector("#kbd-help-overlay", state="visible", timeout=5000)
