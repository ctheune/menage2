"""Browser-based tests for the recipe ingredient feature."""

import pytest

from ._browser_helpers import click_until


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
            "came_from": "/recipes",
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


def _create_recipe(context, live_server):
    """Create a new recipe and return its edit URL."""
    resp = context.request.put(f"{live_server}/recipe", max_redirects=0)
    assert resp.status == 303
    return resp.headers["location"]


def _add_ingredient_row(page):
    """Click ➕ to clone a new ingredient row and return its locator."""
    before = page.locator(".ingredient-row:not(.template):not(.d-none)").count()
    page.locator("button.btn-link.text-success").click()
    page.wait_for_function(
        f"document.querySelectorAll('.ingredient-row:not(.template):not(.d-none)').length > {before}",
        timeout=3000,
    )
    return page.locator(".ingredient-row:not(.template):not(.d-none)").last


def _select_suggestion(page, value):
    """
    Select a suggestion radio by value.

    Hyperscript's 'on change' handler should set the suggest-id and remove the
    dropdown, but the MutationObserver-based init doesn't run in Playwright's
    headless context.  We reproduce the same side-effects via evaluate instead.
    """
    page.evaluate(f"""() => {{
        const radio = document.querySelector('.suggest-dropdown input[type="radio"][value="{value}"]');
        if (!radio) return;
        const td = radio.closest('td');
        const sid = td && td.querySelector('.suggest-id');
        if (sid) sid.value = '{value}';
        // For existing ingredients, update the visible text input too
        if ('{value}' !== 'new') {{
            const sinput = sid && sid.nextElementSibling;
            if (sinput && sinput.classList.contains('suggest-input')) {{
                const label = radio.closest('label');
                if (label) sinput.value = label.textContent.trim();
            }}
        }}
        const dropdown = radio.closest('.suggest-dropdown');
        if (dropdown) dropdown.remove();
    }}""")


def test_add_new_ingredient_to_recipe(page, context, live_server):
    """Clicking ➕, choosing 'Neue Zutat', filling fields, and saving persists the ingredient."""
    edit_url = _create_recipe(context, live_server)
    page.goto(edit_url)
    page.wait_for_load_state("networkidle")

    new_row = _add_ingredient_row(page)

    # Type to trigger the autocomplete fetch (keyup debounced at 300ms)
    new_row.locator(".suggest-input").press_sequentially("Karotte", delay=50)
    page.wait_for_selector(".suggest-dropdown", timeout=5000)

    # "Neue Zutat" option must appear since no ingredient named Karotte exists yet
    assert page.locator(
        '.suggest-dropdown input[type="radio"][value="new"]'
    ).is_visible()

    _select_suggestion(page, "new")

    # Fill amount and unit
    new_row.locator("input[placeholder='1, 2, 3 ...']").fill("3")
    new_row.locator("input[name*='unit']").fill("Stk")

    # Save
    page.locator('input[value="Speichern"]').click()
    page.wait_for_load_state("networkidle")

    # After HTMX swap the ingredient row must be present with the correct name
    saved_row = page.locator(".ingredient-row:not(.template):not(.d-none)")
    assert saved_row.count() == 1
    ingredient_value = saved_row.locator(".suggest-input").evaluate("el => el.value")
    assert ingredient_value == "Karotte", (
        f"Expected 'Karotte', got {ingredient_value!r}"
    )


def test_add_existing_ingredient_via_autocomplete(page, context, live_server):
    """Selecting an existing ingredient from the autocomplete list saves it correctly."""
    # First create recipe A and add "Karotte" so it exists in the DB
    edit_url_a = _create_recipe(context, live_server)
    page.goto(edit_url_a)
    page.wait_for_load_state("networkidle")

    row_a = _add_ingredient_row(page)
    row_a.locator(".suggest-input").press_sequentially("Karotte", delay=50)
    page.wait_for_selector(".suggest-dropdown", timeout=5000)
    _select_suggestion(page, "new")
    page.locator('input[value="Speichern"]').click()
    page.wait_for_load_state("networkidle")

    # Now create recipe B and pick the existing "Karotte" from autocomplete
    edit_url_b = _create_recipe(context, live_server)
    page.goto(edit_url_b)
    page.wait_for_load_state("networkidle")

    row_b = _add_ingredient_row(page)
    row_b.locator(".suggest-input").press_sequentially("Kar", delay=50)
    page.wait_for_selector(".suggest-dropdown", timeout=5000)

    # An existing ingredient radio (not "new") must appear
    existing_option = page.locator(
        '.suggest-dropdown input[type="radio"]:not([value="new"])'
    )
    assert existing_option.count() >= 1
    existing_id = existing_option.first.get_attribute("value")

    _select_suggestion(page, existing_id)

    row_b.locator("input[placeholder='1, 2, 3 ...']").fill("2")

    page.locator('input[value="Speichern"]').click()
    page.wait_for_load_state("networkidle")

    saved_row_b = page.locator(".ingredient-row:not(.template):not(.d-none)")
    assert saved_row_b.count() == 1
    ingredient_value_b = saved_row_b.locator(".suggest-input").evaluate(
        "el => el.value"
    )
    assert ingredient_value_b == "Karotte", (
        f"Expected 'Karotte', got {ingredient_value_b!r}"
    )


# ---------------------------------------------------------------------------
# An ingredient is an item, and gets an item's affordances
# ---------------------------------------------------------------------------


def _an_ingredient(dbengine, name: str) -> str:
    """Put one straight in, under a name of its own.

    Unique per call: these tests share a database for the session, so a
    fixed name means the second run of one is looking at the first run's
    leftovers.
    """
    import uuid

    from sqlalchemy import text

    unique = f"{name}-{uuid.uuid4().hex[:8]}"
    with dbengine.begin() as connection:
        item_id = connection.execute(
            text(
                "INSERT INTO items (kind, text, created_at) "
                "VALUES ('ingredient', :name, now()) RETURNING id"
            ),
            {"name": unique},
        ).scalar()
        connection.execute(
            text("INSERT INTO ingredients (id) VALUES (:id)"), {"id": item_id}
        )
    return unique


def test_an_ingredient_can_be_tagged_from_the_real_vocabulary(
    page, context, live_server, dbengine
):
    """It used to offer six hardcoded tags and nothing else.

    The vocabulary is a table now, shared with tasks and checklists, so the
    ingredient list gets the same picker everything else uses.
    """
    from sqlalchemy import text

    with dbengine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO items (kind, text, created_at) "
                "VALUES ('ingredient', 'Zimt', now()) RETURNING id"
            )
        )
        item_id = connection.execute(
            text("SELECT id FROM items WHERE text = 'Zimt'")
        ).scalar()
        connection.execute(
            text("INSERT INTO ingredients (id) VALUES (:id)"), {"id": item_id}
        )

    page.goto("/ingredient")
    page.wait_for_selector("#ingredients", timeout=10000)
    page.locator("#ingredients li", has_text="Zimt").locator("span.flex-grow-1").click()
    page.wait_for_selector("#field-tags", timeout=10000)

    field = page.locator("#field-tags")
    field.locator(".form-control").first.click()
    page.keyboard.type("einkaufen:supermarkt")
    page.keyboard.press("Enter")
    # The pill is what says the field took it; saving before that would be
    # saving an empty set and calling it a pass.
    field.locator('input[name="tags[]"]').wait_for(state="attached", timeout=10000)
    # The pane arrives by swap; a click before its handlers are attached is
    # dropped, and saving the same tag twice is harmless.
    click_until(
        page,
        '#item-pane button[type="submit"]',
        "#ingredients li:has-text('einkaufen:supermarkt')",
    )


def test_the_editor_sits_beside_the_list_and_stays_put(
    page, context, live_server, dbengine
):
    """Two columns, and the editor does not scroll away from the list.

    The pane is sticky through Bootstrap's `sticky-lg-top`; this pins that the
    ingredient page actually gets it, because a column that quietly stacks
    or scrolls off is the sort of thing nothing else would notice.
    """
    name = _an_ingredient(dbengine, "Kardamom")

    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto("/ingredient")
    click_until(page, f"#ingredients li:has-text('{name}')", "#item-pane #field-tags")

    list_box = page.locator("#ingredients").bounding_box()
    pane_box = page.locator("#item-pane").bounding_box()
    assert pane_box["x"] >= list_box["x"] + list_box["width"] - 1

    assert (
        page.evaluate(
            "() => getComputedStyle(document.querySelector('#item-pane')).position"
        )
        == "sticky"
    )
