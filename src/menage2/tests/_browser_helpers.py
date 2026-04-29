"""Shared helpers for Playwright browser tests."""


def fill_composite(composite, text: str) -> None:
    """Fill the first editable segment of a composite input with text and press Enter.

    Works for plain text, #tags, and @mentions (which buildCompositeText picks up
    from raw text). Does NOT work for ^date or *recurrence — those require picker
    interaction via keyboard shortcuts.
    """
    seg = composite.locator(".todo-text-seg").first
    seg.fill(text)
    seg.press("Enter")
