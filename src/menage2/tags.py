"""The tag vocabulary: what is in it, and putting it in order.

A tag is a row now, and carrying one is a row in `item_tags`. What used to
mean reading four array columns and one comma-separated string and merging
them in Python is one grouped query; what used to mean rewriting every
record that carried a tag is an update to the one row that is the tag.

The hierarchy is still in the name -- `einkaufen:supermarkt` is one tag --
so `_matches` and `_renamed` are unchanged, and so is everything that reads
a tag as a string.
"""

from typing import Iterable, Optional

from pydantic import BaseModel
from sqlalchemy import delete, func, select, text, update

from menage2.models.item import Item
from menage2.models.tag import Tag, item_tags

#: Which kind of item a tag is on, under the name it is shown by. A run is
#: a task on the list, and is counted as one.
_LABELS: dict[str, str] = {
    "todo": "Tasks",
    "protocol_run": "Tasks",
    "protocol": "Checklists",
    "protocol_item": "Checklists",
    "protocol_run_item": "Checklists",
    "ingredient": "Ingredients",
}

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


def _matching(dbsession, source: str, with_children: bool) -> list[Tag]:
    """The tags a rename of `source` would touch."""
    return [
        tag
        for tag in dbsession.execute(select(Tag)).scalars()
        if _matches(tag.name, source, with_children)
    ]


def _count_by_label(dbsession, tags: Iterable[Tag]) -> dict[str, int]:
    """How many items of each kind carry any of `tags`.

    Counted per item, not per tag: renaming a parent and its children
    rewrites a record once however many of them it carries.
    """
    ids = [tag.id for tag in tags]
    if not ids:
        return {}
    rows = dbsession.execute(
        select(Item.kind, func.count(func.distinct(item_tags.c.item_id)))
        .join(item_tags, item_tags.c.item_id == Item.id)
        .where(item_tags.c.tag_id.in_(ids))
        .group_by(Item.kind)
    ).all()
    counts: dict[str, int] = {}
    for kind, count in rows:
        label = _LABELS.get(kind, kind)
        counts[label] = counts.get(label, 0) + count
    return counts


def list_tags(dbsession) -> list[TagCount]:
    """Every tag in use, in alphabetical order.

    Case is ignored for the ordering, which puts `Packliste` next to
    `packliste` — two spellings of one tag sitting together is exactly what
    somebody looking for a merge wants to see. The separator sorts the
    hierarchy into place for free.
    """
    rows = dbsession.execute(
        select(Tag.name, Item.kind, func.count())
        .join(item_tags, item_tags.c.tag_id == Tag.id)
        .join(Item, Item.id == item_tags.c.item_id)
        .group_by(Tag.name, Item.kind)
    ).all()

    counts: dict[str, dict[str, int]] = {}
    for name, kind, count in rows:
        label = _LABELS.get(kind, kind)
        found = counts.setdefault(name, {})
        found[label] = found.get(label, 0) + count

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
    touched = _matching(dbsession, source, with_children)
    plan.rows = _count_by_label(dbsession, touched)
    plan.renames = sorted(
        (tag.name, _renamed(tag.name, source, target)) for tag in touched
    )
    return plan


def apply_retag(
    dbsession, source: str, target: Optional[str] = None, with_children: bool = False
) -> RetagPlan:
    """Do it, and say what was done.

    A rename is now an update to one row. A merge is the same thing arriving
    at a name that already exists: the items are repointed at the tag that
    is already there and the empty one goes. Nothing that carries a tag is
    touched either way, which is the point of the tag being a row.
    """
    plan = plan_retag(dbsession, source, target, with_children)
    if plan.empty and not plan.renames:
        return plan

    by_name = {tag.name: tag for tag in dbsession.execute(select(Tag)).scalars()}
    for old, new in plan.renames:
        tag = by_name.get(old)
        if tag is None:
            continue
        if new is None:
            dbsession.execute(delete(Tag).where(Tag.id == tag.id))
            continue
        existing = by_name.get(new)
        if existing is None or existing.id == tag.id:
            dbsession.execute(update(Tag).where(Tag.id == tag.id).values(name=new))
            by_name.pop(old, None)
            tag.name = new
            by_name[new] = tag
            continue
        # A merge: move what carried it, then drop the name that is spare.
        dbsession.execute(
            text(
                "INSERT INTO item_tags (item_id, tag_id) "
                "SELECT item_id, :target FROM item_tags WHERE tag_id = :source "
                "ON CONFLICT DO NOTHING"
            ),
            {"target": existing.id, "source": tag.id},
        )
        dbsession.execute(delete(Tag).where(Tag.id == tag.id))
        by_name.pop(old, None)

    dbsession.expire_all()
    dbsession.flush()
    return plan
