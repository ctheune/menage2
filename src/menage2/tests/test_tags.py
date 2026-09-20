"""Tidying the tag vocabulary: what is in it, and merging or removing a tag."""

import datetime

from menage2.models.protocol import Protocol, ProtocolItem
from menage2.models.recipe import Ingredient
from menage2.models.todo import Todo, TodoStatus
from menage2.tags import apply_retag, list_tags, plan_retag


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _todo(dbsession, text, tags):
    todo = Todo(
        text=text,
        tags=set(tags),
        assignees=set(),
        status=TodoStatus.todo,
        created_at=_now(),
    )
    dbsession.add(todo)
    dbsession.flush()
    return todo


def _ingredient(dbsession, description, tags):
    ingredient = Ingredient(description=description, tags=",".join(tags))
    dbsession.add(ingredient)
    dbsession.flush()
    return ingredient


# ---------------------------------------------------------------------------
# What is in the vocabulary
# ---------------------------------------------------------------------------


def test_the_list_is_what_things_carry(dbsession):
    _todo(dbsession, "Bread", {"einkaufen:supermarkt", "privat"})
    _todo(dbsession, "Milk", {"einkaufen:supermarkt"})
    _ingredient(dbsession, "Butter", {"einkaufen:supermarkt"})

    found = {entry.tag: entry for entry in list_tags(dbsession)}
    assert set(found) == {"einkaufen:supermarkt", "privat"}
    assert found["einkaufen:supermarkt"].counts == {"Tasks": 2, "Ingredients": 1}
    assert found["einkaufen:supermarkt"].total == 3
    assert found["privat"].counts == {"Tasks": 1}


def test_the_list_is_alphabetical(dbsession):
    _todo(dbsession, "One", {"zebra", "apple"})
    _todo(dbsession, "Two", {"Mango"})

    # Case is ignored, so two spellings of one tag end up side by side —
    # which is what somebody hunting for a merge is looking for.
    assert [entry.tag for entry in list_tags(dbsession)] == [
        "apple",
        "Mango",
        "zebra",
    ]


def test_a_hierarchy_sorts_into_place(dbsession):
    _todo(dbsession, "One", {"einkaufen:supermarkt", "einkaufen", "einkaufen:dm"})

    assert [entry.tag for entry in list_tags(dbsession)] == [
        "einkaufen",
        "einkaufen:dm",
        "einkaufen:supermarkt",
    ]


def test_a_tag_on_a_checklist_counts_too(dbsession, admin_user):
    protocol = Protocol(title="Bins", owner_id=admin_user.id, tags={"haushalt"})
    dbsession.add(protocol)
    dbsession.flush()
    dbsession.add(
        ProtocolItem(protocol_id=protocol.id, text="wheel it out", tags={"haushalt"})
    )
    dbsession.flush()

    found = {entry.tag: entry for entry in list_tags(dbsession)}
    assert found["haushalt"].counts == {"Checklists": 2}


def test_nothing_tagged_means_nothing_listed(dbsession):
    _todo(dbsession, "Untagged", set())
    assert list_tags(dbsession) == []


# ---------------------------------------------------------------------------
# Saying what would happen
# ---------------------------------------------------------------------------


def test_a_plan_changes_nothing(dbsession):
    todo = _todo(dbsession, "Bread", {"alt"})

    plan = plan_retag(dbsession, "alt", "neu")

    assert plan.rows == {"Tasks": 1}
    assert plan.renames == [("alt", "neu")]
    assert todo.tags == {"alt"}


def test_a_plan_for_a_tag_nobody_uses_is_empty(dbsession):
    _todo(dbsession, "Bread", {"alt"})
    plan = plan_retag(dbsession, "nonesuch", "neu")
    assert plan.empty
    assert plan.total_rows == 0


def test_a_plan_counts_every_kind_of_carrier(dbsession):
    _todo(dbsession, "Bread", {"einkaufen"})
    _ingredient(dbsession, "Butter", {"einkaufen"})

    plan = plan_retag(dbsession, "einkaufen", "shopping")

    assert plan.rows == {"Tasks": 1, "Ingredients": 1}
    assert plan.total_rows == 2


# ---------------------------------------------------------------------------
# Renaming, merging, removing
# ---------------------------------------------------------------------------


def test_renaming_a_tag(dbsession):
    todo = _todo(dbsession, "Bread", {"alt", "keep"})

    apply_retag(dbsession, "alt", "neu")

    assert todo.tags == {"neu", "keep"}


def test_merging_into_a_tag_already_there(dbsession):
    """The whole point: two spellings of one thing become one of them."""
    both = _todo(dbsession, "Both", {"obst-u-gemuese", "obst-und-gemüse"})
    one = _todo(dbsession, "One", {"obst-und-gemüse"})

    apply_retag(dbsession, "obst-und-gemüse", "obst-u-gemuese")

    assert both.tags == {"obst-u-gemuese"}, "merging left a duplicate behind"
    assert one.tags == {"obst-u-gemuese"}


def test_removing_a_tag(dbsession):
    todo = _todo(dbsession, "Bread", {"asdfgh", "keep"})

    apply_retag(dbsession, "asdfgh")

    assert todo.tags == {"keep"}


def test_an_ingredient_is_renamed_too(dbsession):
    """Skipping these would let the next shopping list undo the merge."""
    ingredient = _ingredient(
        dbsession, "Apples", {"einkaufen:supermarkt:obst-u-gemuese", "diet:vegan"}
    )

    apply_retag(
        dbsession,
        "einkaufen:supermarkt:obst-u-gemuese",
        "einkaufen:supermarkt:obst-und-gemüse",
    )

    assert ingredient.tags_set == {
        "einkaufen:supermarkt:obst-und-gemüse",
        "diet:vegan",
    }


def test_other_tags_are_left_alone(dbsession):
    todo = _todo(dbsession, "Bread", {"privat", "privat:finanzen"})

    apply_retag(dbsession, "privat", "personal")

    # Without asking for the children, only the exact tag moves.
    assert todo.tags == {"personal", "privat:finanzen"}


def test_a_tag_that_merely_starts_the_same_is_not_touched(dbsession):
    todo = _todo(dbsession, "Bread", {"privateer"})
    apply_retag(dbsession, "privat", "personal", with_children=True)
    assert todo.tags == {"privateer"}


# ---------------------------------------------------------------------------
# Taking the children along
# ---------------------------------------------------------------------------


def test_children_come_along_when_asked(dbsession):
    parent = _todo(dbsession, "Parent", {"Schulmaterial"})
    child = _todo(dbsession, "Child", {"Schulmaterial:Matti"})
    deeper = _todo(dbsession, "Deeper", {"Schulmaterial:Matti:heft"})

    plan = apply_retag(dbsession, "Schulmaterial", "schulmaterial", with_children=True)

    assert parent.tags == {"schulmaterial"}
    assert child.tags == {"schulmaterial:Matti"}
    assert deeper.tags == {"schulmaterial:Matti:heft"}
    assert plan.renames == [
        ("Schulmaterial", "schulmaterial"),
        ("Schulmaterial:Matti", "schulmaterial:Matti"),
        ("Schulmaterial:Matti:heft", "schulmaterial:Matti:heft"),
    ]


def test_children_can_be_removed_along_with_their_parent(dbsession):
    parent = _todo(dbsession, "Parent", {"gone", "keep"})
    child = _todo(dbsession, "Child", {"gone:child"})

    apply_retag(dbsession, "gone", None, with_children=True)

    assert parent.tags == {"keep"}
    assert child.tags == set()


def test_without_asking_the_children_stay_put(dbsession):
    child = _todo(dbsession, "Child", {"gone:child"})
    apply_retag(dbsession, "gone", None)
    assert child.tags == {"gone:child"}
