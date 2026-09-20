"""The tag vocabulary: what is in it, and putting it in order.

Tags are not objects. One exists because something carries it, and typing
`#something` into the add box is how a new one is made — that is what the
marker language is for, not an oversight. So the vocabulary is derived here
rather than stored, and tidying it up means rewriting the things that carry
a tag rather than editing a row that represents it.

Four tables carry tags as an array, and ingredients carry them as one
comma-separated string. The `einkaufen:` part of the vocabulary is shared
between ingredients and tasks — a shopping list copies an ingredient's tags
onto the todos it generates — so a rename that skipped ingredients would be
undone by the next shopping list.
"""

from typing import Iterable, Optional

from pydantic import BaseModel
from sqlalchemy import select

from menage2.models.protocol import Protocol, ProtocolItem, ProtocolRunItem
from menage2.models.recipe import Ingredient
from menage2.models.todo import Todo

#: Tables carrying tags as an array, under the name they are shown by.
_ARRAY_SOURCES: tuple[tuple[str, type], ...] = (
    ("Tasks", Todo),
    ("Checklists", Protocol),
    ("Checklists", ProtocolItem),
    ("Checklists", ProtocolRunItem),
)

#: What separates the levels of a tag such as `einkaufen:supermarkt:kühlung`.
SEPARATOR = ":"


class TagCount(BaseModel):
    """One tag in the vocabulary, and what carries it."""

    tag: str
    counts: dict[str, int]

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    @property
    def summary(self) -> str:
        """`12 tasks, 3 ingredients` — what a merge would be touching."""
        return ", ".join(
            f"{count} {name.lower()}" for name, count in sorted(self.counts.items())
        )


class RetagPlan(BaseModel):
    """What a rename, merge or removal would do, before it does it."""

    source: str
    #: None removes the tag instead of renaming it.
    target: Optional[str] = None
    with_children: bool = False
    #: Every tag that changes, and what it becomes (None where it goes).
    renames: list[tuple[str, Optional[str]]] = []
    #: How many records each source would have rewritten.
    rows: dict[str, int] = {}

    @property
    def empty(self) -> bool:
        return not self.rows

    @property
    def total_rows(self) -> int:
        return sum(self.rows.values())


def _matches(tag: str, source: str, with_children: bool) -> bool:
    if tag == source:
        return True
    return with_children and tag.startswith(source + SEPARATOR)


def _renamed(tag: str, source: str, target: Optional[str]) -> Optional[str]:
    """What `tag` becomes. None means it goes away.

    A child keeps whatever hangs off the part being renamed, so merging
    `Schulmaterial` into `schulmaterial` takes `Schulmaterial:Matti` with it.
    """
    if target is None:
        return None
    return target + tag[len(source) :]


def _rewrite(tags: Iterable[str], source: str, target: Optional[str], children: bool):
    """The new tag set for something currently carrying `tags`."""
    result: set[str] = set()
    for tag in tags:
        if _matches(tag, source, children):
            new = _renamed(tag, source, target)
            if new:
                result.add(new)
        else:
            result.add(tag)
    return result


def list_tags(dbsession) -> list[TagCount]:
    """Every tag in use, in alphabetical order.

    Case is ignored for the ordering, which puts `Packliste` next to
    `packliste` — two spellings of one tag sitting together is exactly what
    somebody looking for a merge wants to see. The separator sorts the
    hierarchy into place for free.
    """
    counts: dict[str, dict[str, int]] = {}

    def note(name: str, tag: str) -> None:
        counts.setdefault(tag, {}).setdefault(name, 0)
        counts[tag][name] += 1

    for name, model in _ARRAY_SOURCES:
        for (tags,) in dbsession.execute(select(model.tags)):
            for tag in tags or ():
                note(name, tag)

    for ingredient in dbsession.execute(select(Ingredient)).scalars():
        for tag in ingredient.tags_set:
            note("Ingredients", tag)

    return sorted(
        (TagCount(tag=tag, counts=found) for tag, found in counts.items()),
        key=lambda entry: (entry.tag.lower(), entry.tag),
    )


def plan_retag(
    dbsession, source: str, target: Optional[str] = None, with_children: bool = False
) -> RetagPlan:
    """What renaming `source` to `target` would change, changing nothing.

    `target` of None removes the tag. Renaming to a name already in use is a
    merge; there is nothing else to it, so it is not a separate operation.
    """
    plan = RetagPlan(source=source, target=target, with_children=with_children)
    renames: dict[str, Optional[str]] = {}

    for name, model in _ARRAY_SOURCES:
        for (tags,) in dbsession.execute(select(model.tags)):
            touched = [t for t in (tags or ()) if _matches(t, source, with_children)]
            if not touched:
                continue
            plan.rows[name] = plan.rows.get(name, 0) + 1
            for tag in touched:
                renames[tag] = _renamed(tag, source, target)

    for ingredient in dbsession.execute(select(Ingredient)).scalars():
        touched = [t for t in ingredient.tags_set if _matches(t, source, with_children)]
        if not touched:
            continue
        plan.rows["Ingredients"] = plan.rows.get("Ingredients", 0) + 1
        for tag in touched:
            renames[tag] = _renamed(tag, source, target)

    plan.renames = sorted(renames.items())
    return plan


def apply_retag(
    dbsession, source: str, target: Optional[str] = None, with_children: bool = False
) -> RetagPlan:
    """Do it, and say what was done.

    Every carrier is loaded and rewritten rather than updated in place. The
    vocabulary is small and this runs when somebody asks it to, so being
    plainly correct is worth more here than being clever — and it is the one
    piece of code that has to handle both the arrays and the ingredients'
    comma-separated string.
    """
    plan = plan_retag(dbsession, source, target, with_children)
    if plan.empty:
        return plan

    for _, model in _ARRAY_SOURCES:
        for carrier in dbsession.execute(select(model)).scalars():
            if any(_matches(t, source, with_children) for t in carrier.tags or ()):
                carrier.tags = _rewrite(carrier.tags, source, target, with_children)

    for ingredient in dbsession.execute(select(Ingredient)).scalars():
        current = ingredient.tags_set
        if any(_matches(t, source, with_children) for t in current):
            ingredient.tags_set = sorted(
                _rewrite(current, source, target, with_children)
            )

    dbsession.flush()
    return plan
