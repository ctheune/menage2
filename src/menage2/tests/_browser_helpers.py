"""Shared helpers for Playwright browser tests."""

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

# `#todo-list` fetches its own contents (hx-trigger "load", "todo-updated" and
# window "focus"). A click aimed at a row while one of those swaps is in flight
# is lost together with the row it landed on, so every interaction with the list
# waits for the row first and then confirms the click actually registered.


def select_row(page, selector: str, expect: str, attempts: int = 3) -> None:
    """Click a todo row and wait for `expect` to show up in the details pane.

    Re-clicking after a swallowed click is safe — and only happens then: the
    row's checkbox is still unchecked, so the next click selects it rather than
    toggling the selection back off.
    """
    page.wait_for_selector(selector, timeout=10000)
    row = page.locator(selector).first
    for attempt in range(attempts):
        row.click()
        try:
            page.wait_for_selector(f"{selector} .todo-checkbox:checked", timeout=2000)
        except PlaywrightTimeoutError:
            if attempt == attempts - 1:
                raise AssertionError(
                    f"clicking {selector} never selected it — the list kept "
                    f"swapping underneath the click"
                )
            continue
        page.wait_for_selector(expect, timeout=10000)
        return
