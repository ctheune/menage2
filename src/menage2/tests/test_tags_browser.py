"""Browser tests for tidying up the tag vocabulary.

The endpoints are covered elsewhere; what is here is the wiring — the form
that previews as you type, and the button that fills it in from the table.
"""

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
    name, value = resp.headers["set-cookie"].split(";")[0].split("=", 1)
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


def _add_todo(context, live_server, raw: str) -> None:
    resp = context.request.post(
        f"{live_server}/todos/add", form={"text": raw}, max_redirects=0
    )
    assert resp.status == 303, f"Adding {raw!r} failed: {resp.status}"


def _open(page, tag: str) -> None:
    """Click a tag, which turns it into a field in place."""
    page.locator(f'button[data-tag="{tag}"]').click()
    page.wait_for_selector("tr.tag-editing .tag-target", timeout=5000)


def _field(page):
    return page.locator("tr.tag-editing .tag-target")


def _preview(page) -> str:
    return page.locator("tr.tag-editing .tag-preview").inner_text()


def test_the_tag_becomes_a_field_where_it_stood(page, context, live_server):
    """The same swap the checklist items use, rather than a form elsewhere."""
    _add_todo(context, live_server, "Bread #alt")
    page.goto("/admin/tags")

    assert page.locator(".tag-target:visible").count() == 0
    button = page.locator('button[data-tag="alt"]')
    before = button.bounding_box()

    _open(page, "alt")

    assert not button.is_visible(), "the tag is still there beside its own field"
    field = _field(page).bounding_box()
    # In the cell the tag was in, not in a row of its own underneath.
    assert abs(field["y"] - before["y"]) < 20


def test_the_name_starts_as_the_tag_itself(page, context, live_server):
    """Renaming is usually a small edit, not a retype."""
    _add_todo(context, live_server, "Bread #einkaufen")
    page.goto("/admin/tags")

    _open(page, "einkaufen")

    assert _field(page).input_value() == "einkaufen"


def test_the_rest_of_the_form_comes_with_it(page, context, live_server):
    _add_todo(context, live_server, "Bread #einkaufen")
    page.goto("/admin/tags")
    _open(page, "einkaufen")

    row = page.locator("tr.tag-editing")
    assert row.locator("button:has-text('Rename')").is_visible()
    assert row.locator("button:has-text('Delete')").is_visible()
    assert row.locator("input[name=children]").is_visible()
    # And what it says it is carried by is still on screen beside them.
    assert "1 tasks" in row.inner_text()


def test_the_other_tags_are_offered_for_completion(page, context, live_server):
    """Merging is renaming onto a name already in use.

    The app's own picker, not a browser datalist: that one is drawn by the
    browser, so it looks nothing like the rest and cannot be themed.
    """
    _add_todo(context, live_server, "Apples #obst-u-gemuese")
    _add_todo(context, live_server, "Pears #obst-und-gemuese")
    page.goto("/admin/tags")
    _open(page, "obst-und-gemuese")

    _field(page).fill("obst-u")
    page.wait_for_selector(
        "tr.tag-editing .picker li[data-picker-value='obst-u-gemuese']", timeout=5000
    )


def test_picking_a_name_fills_the_field(page, context, live_server):
    _add_todo(context, live_server, "Apples #obst-u-gemuese")
    _add_todo(context, live_server, "Pears #obst-und-gemuese")
    page.goto("/admin/tags")
    _open(page, "obst-und-gemuese")

    _field(page).fill("obst-u")
    option = "tr.tag-editing .picker li[data-picker-value='obst-u-gemuese']"
    page.wait_for_selector(option, timeout=5000)
    page.locator(option).click()

    # The whole field, not a word within it: a tag name is the entire value.
    assert _field(page).input_value() == "obst-u-gemuese"
    # And the preview keeps up with a name that was picked rather than typed.
    page.wait_for_function(
        "() => document.querySelector('tr.tag-editing .tag-preview')"
        ".innerText.includes('\u2192')",
        timeout=5000,
    )


def test_the_picker_is_the_apps_own(page, context, live_server):
    """It carries the same card and list-group the task panel's picker does,
    so it is themed with everything else."""
    _add_todo(context, live_server, "Apples #obst-u-gemuese")
    page.goto("/admin/tags")
    _open(page, "obst-u-gemuese")

    _field(page).fill("obst")
    panel = "tr.tag-editing .picker > div"
    page.wait_for_selector(panel, timeout=5000)
    classes = page.locator(panel).get_attribute("class")
    assert "card" in classes
    assert page.locator(f"{panel} ul.list-group").count() == 1


def test_the_preview_follows_what_is_typed(page, context, live_server):
    _add_todo(context, live_server, "Bread #alt")
    page.goto("/admin/tags")
    _open(page, "alt")

    _field(page).fill("neu")
    page.wait_for_function(
        "() => document.querySelector('tr.tag-editing .tag-preview')"
        ".innerText.includes('neu')",
        timeout=5000,
    )
    assert "alt → neu" in _preview(page)


def test_ticking_sub_tags_shows_them_before_anything_happens(
    page, context, live_server
):
    _add_todo(context, live_server, "Parent #Schulmaterial")
    _add_todo(context, live_server, "Child #Schulmaterial:Matti")
    page.goto("/admin/tags")
    _open(page, "Schulmaterial")

    page.locator("tr.tag-editing input[name=children]").check()

    page.wait_for_function(
        "() => document.querySelector('tr.tag-editing .tag-preview')"
        ".innerText.includes('Schulmaterial:Matti')",
        timeout=5000,
    )
    assert "2 tasks" in _preview(page)


def test_only_one_row_is_open_at_a_time(page, context, live_server):
    _add_todo(context, live_server, "Bread #alt #neu")
    page.goto("/admin/tags")

    _open(page, "alt")
    _open(page, "neu")

    assert page.locator("tr.tag-editing").count() == 1
    assert _field(page).input_value() == "neu"


def test_cancelling_puts_the_tag_back(page, context, live_server):
    _add_todo(context, live_server, "Bread #alt")
    page.goto("/admin/tags")
    _open(page, "alt")

    page.locator("tr.tag-editing button:has-text('Cancel')").click()

    page.wait_for_selector("tr.tag-editing", state="detached", timeout=5000)
    assert page.locator('button[data-tag="alt"]').is_visible()


def test_escape_puts_the_tag_back_too(page, context, live_server):
    _add_todo(context, live_server, "Bread #alt")
    page.goto("/admin/tags")
    _open(page, "alt")

    _field(page).press("Escape")

    page.wait_for_selector("tr.tag-editing", state="detached", timeout=5000)


def test_merging_two_spellings_into_one(page, context, live_server):
    """The whole reason for the page."""
    _add_todo(context, live_server, "Apples #obst-u-gemuese")
    _add_todo(context, live_server, "Pears #obst-und-gemuese")
    page.goto("/admin/tags")
    _open(page, "obst-und-gemuese")

    _field(page).fill("obst-u-gemuese")
    page.locator("tr.tag-editing button:has-text('Rename')").click()

    page.wait_for_url("**/admin/tags?done=**", timeout=10000)
    listed = page.locator("table tbody button[data-tag]").all_inner_texts()
    assert listed == ["#obst-u-gemuese"]


def test_deleting_a_tag_from_the_page(page, context, live_server):
    """Delete has a button of its own; the name field is beside the point."""
    _add_todo(context, live_server, "Typo #asdfgh")
    page.goto("/admin/tags")
    _open(page, "asdfgh")

    page.locator("tr.tag-editing button:has-text('Delete')").click()

    page.wait_for_url("**/admin/tags?done=**", timeout=10000)
    assert page.locator('button[data-tag="asdfgh"]').count() == 0


def test_the_list_reads_alphabetically(page, context, live_server):
    """How you find a duplicate in the first place."""
    _add_todo(context, live_server, "One #zebra #Mango #apple")
    page.goto("/admin/tags")

    listed = page.locator("table tbody button[data-tag]").all_inner_texts()
    assert listed == ["#apple", "#Mango", "#zebra"]
