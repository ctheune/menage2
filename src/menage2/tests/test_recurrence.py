"""Tests for menage2.recurrence — spawn helpers and the daily-sweep gate."""

import datetime

import pytest

from menage2.dateparse import RecurrenceSpec
from menage2.models.protocol import Protocol, ProtocolRun
from menage2.models.todo import (
    RecurrenceKind,
    RecurrenceRule,
    RecurrenceUnit,
    Todo,
    TodoStatus,
)
from menage2.models.user import User
from menage2.recurrence import (
    chain_history,
    ensure_protocol_has_run,
    rule_to_spec,
    run_sweep,
    spawn_after,
    spawn_every_on_completion,
    spawn_protocol_after,
    spawn_protocol_every_on_completion,
    spawn_protocol_run,
    spec_to_rule,
)


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _make_rule(dbsession, kind, unit, n=1, weekday=None, month_day=None):
    rule = RecurrenceRule(
        kind=RecurrenceKind(kind),
        interval_value=n,
        interval_unit=RecurrenceUnit(unit),
        weekday=weekday,
        month_day=month_day,
    )
    dbsession.add(rule)
    dbsession.flush()
    return rule


def _make_todo(dbsession, **kwargs):
    todo = Todo(
        text=kwargs.pop("text", "T"),
        tags=kwargs.pop("tags", set()),
        status=kwargs.pop("status", TodoStatus.todo),
        created_at=kwargs.pop("created_at", _now()),
        owner=kwargs.pop("owner"),
        **kwargs,
    )
    dbsession.add(todo)
    dbsession.flush()
    return todo


# ---------------------------------------------------------------------------
# spec/rule round-trip
# ---------------------------------------------------------------------------


def test_spec_rule_roundtrip(dbsession):
    spec = RecurrenceSpec("every", 2, "week", weekday=2)
    rule = spec_to_rule(spec)
    dbsession.add(rule)
    dbsession.flush()
    again = rule_to_spec(rule)
    assert again == spec


# ---------------------------------------------------------------------------
# The chain cannot fork
# ---------------------------------------------------------------------------


def test_an_item_only_ever_spawns_once(dbsession, admin_user):
    """The whole point of writing the chain forwards.

    Two requests completing the same item used to produce two successors and
    a chain shaped like a tree. Now the second one finds the place taken.
    """
    from menage2.models.todo import Todo

    rule = _make_rule(dbsession, "after", "week", n=1)
    parent = _make_todo(
        dbsession, text="Water", recurrence_id=rule.id, owner=admin_user
    )
    completion = datetime.date(2026, 5, 10)

    first = spawn_after(parent, completion, _now(), dbsession)
    second = spawn_after(parent, completion, _now(), dbsession)

    assert first is not None
    assert second is None
    assert parent.recurred_into_id == first.id
    assert dbsession.query(Todo).filter(Todo.recurrence_id == rule.id).count() == 2, (
        "the second spawn left a branch behind"
    )


def test_claiming_a_successor_twice_is_refused_by_the_database(dbsession, admin_user):
    """Not just the in-memory check: the UPDATE is what arbitrates.

    Two workers each hold their own idea of the parent, so neither can see
    the other's claim. Only the conditional UPDATE can tell them apart.
    """
    from menage2.recurrence import _claim_successor

    rule = _make_rule(dbsession, "after", "week", n=1)
    parent = _make_todo(
        dbsession, text="Water", recurrence_id=rule.id, owner=admin_user
    )
    mine = _make_todo(dbsession, text="mine", recurrence_id=rule.id, owner=admin_user)
    theirs = _make_todo(
        dbsession, text="theirs", recurrence_id=rule.id, owner=admin_user
    )

    assert _claim_successor(dbsession, parent, mine) is True
    assert _claim_successor(dbsession, parent, theirs) is False
    assert parent.recurred_into_id == mine.id


def test_two_items_cannot_claim_the_same_successor(dbsession, admin_user):
    """The other half: UNIQUE stops a chain joining back onto itself."""
    import sqlalchemy.exc

    rule = _make_rule(dbsession, "after", "week", n=1)
    one = _make_todo(dbsession, text="one", recurrence_id=rule.id, owner=admin_user)
    two = _make_todo(dbsession, text="two", recurrence_id=rule.id, owner=admin_user)
    shared = _make_todo(
        dbsession, text="shared", recurrence_id=rule.id, owner=admin_user
    )

    one.recurred_into_id = shared.id
    dbsession.flush()
    two.recurred_into_id = shared.id
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        dbsession.flush()
    dbsession.rollback()


# ---------------------------------------------------------------------------
# spawn_after
# ---------------------------------------------------------------------------


def test_spawn_after_creates_clone_with_new_due_date(dbsession, admin_user):
    rule = _make_rule(dbsession, "after", "week", n=1)
    parent = _make_todo(
        dbsession,
        text="Water plants",
        tags={"chores"},
        recurrence_id=rule.id,
        owner=admin_user,
    )
    completion = datetime.date(2026, 5, 10)
    new = spawn_after(parent, completion, _now(), dbsession)
    assert new is not None
    assert new.text == "Water plants"
    assert new.tags == {"chores"}
    assert new.recurrence_id == rule.id
    assert parent.recurred_into_id == new.id
    assert new.status == TodoStatus.todo
    assert new.due_date == datetime.date(2026, 5, 17)


def test_spawn_after_returns_none_for_non_after_rule(dbsession, admin_user):
    rule = _make_rule(dbsession, "every", "week", n=1)
    parent = _make_todo(dbsession, recurrence_id=rule.id, owner=admin_user)
    assert spawn_after(parent, datetime.date(2026, 5, 1), _now(), dbsession) is None


def test_spawn_after_returns_none_for_no_rule(dbsession, admin_user):
    parent = _make_todo(dbsession, owner=admin_user)
    assert spawn_after(parent, datetime.date(2026, 5, 1), _now(), dbsession) is None


# ---------------------------------------------------------------------------
# spawn_every_on_completion
# ---------------------------------------------------------------------------


def test_spawn_every_on_completion_creates_next_instance(dbsession, admin_user):
    today = datetime.date(2026, 4, 29)  # Wed
    rule = _make_rule(dbsession, "every", "week", weekday=2)
    todo = _make_todo(
        dbsession,
        text="Yoga",
        recurrence_id=rule.id,
        due_date=today,
        status=TodoStatus.done,
        done_at=_now(),
        owner=admin_user,
    )
    spawned = spawn_every_on_completion(todo, today, _now(), dbsession)
    pending = (
        dbsession.query(Todo)
        .filter(
            Todo.recurrence_id == rule.id,
            Todo.status == TodoStatus.todo,
        )
        .all()
    )
    assert len(pending) == 1
    assert pending[0].due_date == datetime.date(2026, 5, 6)
    assert todo.recurred_into_id == pending[0].id
    assert pending[0] is spawned


def test_spawn_every_on_completion_skips_if_future_already_active(
    dbsession, admin_user
):
    today = datetime.date(2026, 4, 29)
    rule = _make_rule(dbsession, "every", "week", weekday=2)
    # Sweep already created next-Wed before this completion
    _make_todo(
        dbsession,
        text="next",
        recurrence_id=rule.id,
        due_date=datetime.date(2026, 5, 6),
        owner=admin_user,
    )
    completed = _make_todo(
        dbsession,
        text="now",
        recurrence_id=rule.id,
        due_date=today,
        status=TodoStatus.done,
        done_at=_now(),
        owner=admin_user,
    )
    spawned = spawn_every_on_completion(completed, today, _now(), dbsession)
    assert spawned is None


def test_spawn_every_on_completion_no_op_for_after_rule(dbsession, admin_user):
    rule = _make_rule(dbsession, "after", "week", n=1)
    todo = _make_todo(dbsession, recurrence_id=rule.id, owner=admin_user)
    assert (
        spawn_every_on_completion(todo, datetime.date(2026, 5, 1), _now(), dbsession)
        == 0
    )


def test_spawn_every_on_completion_no_op_for_no_rule(dbsession, admin_user):
    todo = _make_todo(dbsession, owner=admin_user)
    assert (
        spawn_every_on_completion(todo, datetime.date(2026, 5, 1), _now(), dbsession)
        == 0
    )


# ---------------------------------------------------------------------------
# run_sweep (the catch-up)
# ---------------------------------------------------------------------------


def test_sweeping_twice_creates_nothing_the_second_time(dbsession, admin_user):
    """What replaces the per-day marker.

    The sweep runs on a schedule now, as often as the schedule says. Nothing
    stops it running twice in a row, so running twice has to be harmless.
    """
    today = datetime.date(2026, 4, 29)
    rule = _make_rule(dbsession, "every", "week", weekday=2)
    _make_todo(
        dbsession,
        text="Yoga",
        recurrence_id=rule.id,
        due_date=datetime.date(2026, 4, 22),
        owner=admin_user,
    )
    assert run_sweep(dbsession, today, _now()) == 1
    before = dbsession.query(Todo).count()
    assert run_sweep(dbsession, today, _now()) == 0
    assert dbsession.query(Todo).count() == before


def test_sweep_skips_when_today_active_anchor(dbsession, admin_user):
    """An active anchor due today already satisfies 'has today-or-future'."""
    today = datetime.date(2026, 4, 29)  # Wed
    rule = _make_rule(dbsession, "every", "week", weekday=2)
    _make_todo(
        dbsession,
        text="Weekly",
        recurrence_id=rule.id,
        due_date=today,
        owner=admin_user,
    )
    spawned = run_sweep(dbsession, today, _now())
    assert spawned == 0


def test_sweep_creates_next_when_today_anchor_already_done(dbsession, admin_user):
    """Today's instance done → spawn the next so the chain stays alive."""
    today = datetime.date(2026, 4, 29)  # Wed
    rule = _make_rule(dbsession, "every", "week", weekday=2)
    _make_todo(
        dbsession,
        text="Yoga",
        recurrence_id=rule.id,
        due_date=today,
        status=TodoStatus.done,
        done_at=_now(),
        owner=admin_user,
    )
    spawned = run_sweep(dbsession, today, _now())
    assert spawned >= 1
    pending = (
        dbsession.query(Todo)
        .filter(
            Todo.recurrence_id == rule.id,
            Todo.status == TodoStatus.todo,
        )
        .all()
    )
    assert len(pending) == 1
    assert pending[0].due_date == datetime.date(2026, 5, 6)


def test_sweep_catches_up_missed_occurrences(dbsession, admin_user):
    today = datetime.date(2026, 4, 29)  # Wed
    rule = _make_rule(dbsession, "every", "week", weekday=2)
    _make_todo(
        dbsession,
        text="catchup",
        recurrence_id=rule.id,
        due_date=datetime.date(2026, 4, 1),
        owner=admin_user,
    )  # Wed, 4 weeks before today
    run_sweep(dbsession, today, _now())
    children = dbsession.query(Todo).filter(Todo.recurrence_id == rule.id).all()
    # We require: at least one due_date today-or-later (the chain is alive again)
    assert any(c.due_date >= today for c in children)
    # All children share the rule.
    assert all(c.recurrence_id == rule.id for c in children)


def test_sweep_creates_until_today_or_future_when_only_past_active(
    dbsession, admin_user
):
    """Past-active instance counts as 'no today-or-future' → catch up."""
    today = datetime.date(2026, 4, 29)  # Wed
    rule = _make_rule(dbsession, "every", "week", weekday=2)
    _make_todo(
        dbsession,
        text="overdue",
        recurrence_id=rule.id,
        due_date=datetime.date(2026, 4, 8),
        status=TodoStatus.todo,
        owner=admin_user,
    )
    run_sweep(dbsession, today, _now())
    actives = (
        dbsession.query(Todo)
        .filter(
            Todo.recurrence_id == rule.id,
            Todo.status == TodoStatus.todo,
        )
        .all()
    )
    # Original past one stays + at least one with due_date >= today is now present.
    assert any(t.due_date >= today for t in actives)


def test_sweep_skips_when_future_active_exists(dbsession, admin_user):
    today = datetime.date(2026, 4, 29)
    rule = _make_rule(dbsession, "every", "week", n=1)
    _make_todo(
        dbsession,
        text="anchor",
        recurrence_id=rule.id,
        due_date=datetime.date(2026, 4, 1),
        owner=admin_user,
    )
    # Already-pending future instance — sweep should leave well alone.
    _make_todo(
        dbsession,
        text="pending",
        recurrence_id=rule.id,
        due_date=datetime.date(2026, 5, 6),
        status=TodoStatus.todo,
        owner=admin_user,
    )
    before = dbsession.query(Todo).count()
    run_sweep(dbsession, today, _now())
    assert dbsession.query(Todo).count() == before


def test_sweep_catches_up_a_rule_nobody_has_touched(dbsession, admin_user):
    today = datetime.date(2026, 4, 29)
    rule = _make_rule(dbsession, "every", "week", weekday=2)
    _make_todo(
        dbsession,
        text="forced",
        recurrence_id=rule.id,
        due_date=datetime.date(2026, 4, 1),
        owner=admin_user,
    )
    spawned = run_sweep(dbsession, today, _now())
    assert spawned >= 1
    pending = (
        dbsession.query(Todo)
        .filter(
            Todo.recurrence_id == rule.id,
            Todo.status == TodoStatus.todo,
            Todo.due_date >= today,
        )
        .count()
    )
    assert pending == 1


def test_two_workers_spawning_at_once_produce_one_successor(clean_db, dbengine):
    """The race this was all about, across two real connections.

    Both read the item before either writes, so neither can see the other
    coming — which is exactly what two web workers handling the same
    completion look like. Only the database can tell them apart.
    """
    from sqlalchemy.orm import sessionmaker

    from menage2.models.todo import RecurrenceKind, RecurrenceRule, RecurrenceUnit

    Session = sessionmaker(bind=dbengine)

    setup = Session()
    rule = RecurrenceRule(
        kind=RecurrenceKind.after,
        interval_value=1,
        interval_unit=RecurrenceUnit.week,
    )
    setup.add(rule)
    setup.flush()
    parent = Todo(
        text="Water",
        tags=set(),
        status=TodoStatus.todo,
        created_at=_now(),
        due_date=datetime.date(2026, 5, 3),
        recurrence_id=rule.id,
    )
    setup.add(parent)
    setup.commit()
    parent_id, rule_id = parent.id, rule.id
    setup.close()

    one, two = Session(), Session()
    try:
        mine = one.get(Todo, parent_id)
        theirs = two.get(Todo, parent_id)
        assert theirs.recurred_into_id is None  # neither has written yet

        completion = datetime.date(2026, 5, 10)
        first = spawn_after(mine, completion, _now(), one)
        one.commit()
        second = spawn_after(theirs, completion, _now(), two)
        two.commit()

        assert first is not None
        assert second is None, "the second worker added a branch"

        check = Session()
        successors = (
            check.query(Todo)
            .filter(Todo.recurrence_id == rule_id, Todo.id != parent_id)
            .all()
        )
        assert len(successors) == 1
        assert check.get(Todo, parent_id).recurred_into_id == successors[0].id
        check.close()
    finally:
        one.close()
        two.close()


# ---------------------------------------------------------------------------
# chain_history
# ---------------------------------------------------------------------------


def _chain(dbsession, admin_user, rule, *texts):
    """Build a chain of todos, each one spawned by the one before it."""
    todos = [
        _make_todo(dbsession, text=text, recurrence_id=rule.id, owner=admin_user)
        for text in texts
    ]
    for earlier, later in zip(todos, todos[1:]):
        earlier.recurred_into_id = later.id
    dbsession.flush()
    return todos


def test_chain_history_reads_oldest_first(dbsession, admin_user):
    rule = _make_rule(dbsession, "every", "week", n=1)
    a, b, c = _chain(dbsession, admin_user, rule, "A", "B", "C")
    assert [t.text for t in chain_history(dbsession, c)] == ["A", "B", "C"]


def test_chain_history_reads_the_same_from_anywhere_in_the_chain(dbsession, admin_user):
    """It is one chain, so it should not matter which link you ask."""
    rule = _make_rule(dbsession, "every", "week", n=1)
    a, b, c = _chain(dbsession, admin_user, rule, "A", "B", "C")
    for member in (a, b, c):
        assert [t.text for t in chain_history(dbsession, member)] == ["A", "B", "C"]


def test_chain_history_single_item_when_no_parent(dbsession, admin_user):
    t = _make_todo(dbsession, text="solo", owner=admin_user)
    assert chain_history(dbsession, t) == [t]


# ---------------------------------------------------------------------------
# Protocol spawn helpers
# ---------------------------------------------------------------------------


def _make_protocol(dbsession, admin_user, title="Weekly inventory", recurrence=None):
    p = Protocol(
        title=title,
        owner_id=admin_user.id,
        recurrence_id=recurrence.id if recurrence else None,
    )
    dbsession.add(p)
    dbsession.flush()
    return p


def test_spawn_protocol_run_creates_run_and_todo(dbsession, admin_user):
    p = _make_protocol(dbsession, admin_user)
    today = datetime.date(2026, 4, 29)
    run = spawn_protocol_run(p, today, _now(), dbsession)
    assert run.protocol_id == p.id
    assert run.opened_at is None
    assert run.closed_at is None
    todo = dbsession.query(Todo).filter(Todo.protocol_run_id == run.id).one()
    assert todo.text == "Weekly inventory"
    assert todo.due_date == today
    assert todo.status == TodoStatus.todo


def test_spawn_protocol_after_creates_next_run(dbsession, admin_user):
    rule = _make_rule(dbsession, "after", "week", n=1)
    p = _make_protocol(dbsession, admin_user, recurrence=rule)
    initial = spawn_protocol_run(p, datetime.date(2026, 4, 29), _now(), dbsession)
    completion = datetime.date(2026, 5, 2)  # completed 3 days late
    new_run = spawn_protocol_after(initial, completion, _now(), dbsession)
    assert new_run is not None
    new_todo = dbsession.query(Todo).filter(Todo.protocol_run_id == new_run.id).one()
    assert new_todo.due_date == datetime.date(2026, 5, 9)


def test_spawn_protocol_after_no_op_for_every(dbsession, admin_user):
    rule = _make_rule(dbsession, "every", "week", weekday=2)
    p = _make_protocol(dbsession, admin_user, recurrence=rule)
    run = spawn_protocol_run(p, datetime.date(2026, 4, 29), _now(), dbsession)
    assert (
        spawn_protocol_after(run, datetime.date(2026, 5, 1), _now(), dbsession) is None
    )


def test_spawn_protocol_every_on_completion_creates_next(dbsession, admin_user):
    today = datetime.date(2026, 4, 29)  # Wed
    rule = _make_rule(dbsession, "every", "week", weekday=2)
    p = _make_protocol(dbsession, admin_user, recurrence=rule)
    run = spawn_protocol_run(p, today, _now(), dbsession)
    # Simulate completion: mark the run's todo done so the future-active check
    # no longer counts it.
    run.todo.status = TodoStatus.done
    run.todo.done_at = _now()
    run.closed_at = _now()
    dbsession.flush()
    spawned = spawn_protocol_every_on_completion(run, today, _now(), dbsession)
    assert spawned == 1
    futures = (
        dbsession.query(Todo)
        .join(ProtocolRun, ProtocolRun.id == Todo.protocol_run_id)
        .filter(
            ProtocolRun.protocol_id == p.id,
            Todo.due_date >= today + datetime.timedelta(days=1),
        )
        .all()
    )
    assert len(futures) == 1
    assert futures[0].due_date == datetime.date(2026, 5, 6)


def test_spawn_protocol_every_skips_when_future_active_run_exists(
    dbsession, admin_user
):
    today = datetime.date(2026, 4, 29)
    rule = _make_rule(dbsession, "every", "week", weekday=2)
    p = _make_protocol(dbsession, admin_user, recurrence=rule)
    spawn_protocol_run(p, today, _now(), dbsession)  # already today-active
    run = spawn_protocol_run(p, today - datetime.timedelta(days=7), _now(), dbsession)
    spawned = spawn_protocol_every_on_completion(run, today, _now(), dbsession)
    assert spawned == 0


def test_daily_sweep_includes_protocols(dbsession, admin_user):
    today = datetime.date(2026, 4, 29)
    rule = _make_rule(dbsession, "every", "week", weekday=2)
    p = _make_protocol(dbsession, admin_user, recurrence=rule)
    # Past run only — chain has no today-or-future active.
    spawn_protocol_run(p, today - datetime.timedelta(days=14), _now(), dbsession)
    spawned = run_sweep(dbsession, today, _now())
    assert spawned >= 1
    actives = (
        dbsession.query(Todo)
        .join(ProtocolRun, ProtocolRun.id == Todo.protocol_run_id)
        .filter(ProtocolRun.protocol_id == p.id, Todo.due_date >= today)
        .count()
    )
    assert actives >= 1


def test_daily_sweep_skips_archived_protocols(dbsession, admin_user):
    today = datetime.date(2026, 4, 29)
    rule = _make_rule(dbsession, "every", "week", weekday=2)
    p = _make_protocol(dbsession, admin_user, recurrence=rule)
    p.archived_at = _now()
    spawn_protocol_run(p, today - datetime.timedelta(days=14), _now(), dbsession)
    before = (
        dbsession.query(ProtocolRun).filter(ProtocolRun.protocol_id == p.id).count()
    )
    run_sweep(dbsession, today, _now())
    after = dbsession.query(ProtocolRun).filter(ProtocolRun.protocol_id == p.id).count()
    assert before == after


def test_ensure_protocol_has_run_creates_first_run(dbsession, admin_user):
    today = datetime.date(2026, 4, 29)  # Wed
    rule = _make_rule(dbsession, "every", "week", weekday=2)
    p = _make_protocol(dbsession, admin_user, recurrence=rule)
    ensure_protocol_has_run(p, today, _now(), dbsession)
    runs = dbsession.query(ProtocolRun).filter(ProtocolRun.protocol_id == p.id).all()
    assert len(runs) >= 1
    todos = [
        dbsession.query(Todo).filter(Todo.protocol_run_id == r.id).one() for r in runs
    ]
    assert any(t.due_date >= today for t in todos)


def test_ensure_protocol_has_run_no_op_when_active_exists(dbsession, admin_user):
    today = datetime.date(2026, 4, 29)
    rule = _make_rule(dbsession, "every", "week", weekday=2)
    p = _make_protocol(dbsession, admin_user, recurrence=rule)
    spawn_protocol_run(p, today, _now(), dbsession)
    before = (
        dbsession.query(ProtocolRun).filter(ProtocolRun.protocol_id == p.id).count()
    )
    ensure_protocol_has_run(p, today, _now(), dbsession)
    after = dbsession.query(ProtocolRun).filter(ProtocolRun.protocol_id == p.id).count()
    assert before == after


def test_ensure_protocol_has_run_no_op_without_recurrence(dbsession, admin_user):
    today = datetime.date(2026, 4, 29)
    p = _make_protocol(dbsession, admin_user)  # no recurrence
    ensure_protocol_has_run(p, today, _now(), dbsession)
    assert (
        dbsession.query(ProtocolRun).filter(ProtocolRun.protocol_id == p.id).count()
        == 0
    )


# ---------------------------------------------------------------------------
# The migration's clean-up of branches that already exist
# ---------------------------------------------------------------------------


def _prune_branches(dbsession) -> int:
    """Run the migration's own SQL against the test database.

    Imported from the migration rather than copied, so what is tested is what
    ships. The file name starts with a date, hence the long way round.
    """
    import importlib.util
    import pathlib

    path = (
        pathlib.Path(__file__).parent.parent
        / "alembic"
        / "versions"
        / "20260920_c1f4a7e3b210.py"
    )
    spec = importlib.util.spec_from_file_location("_migration_c1f4a7e3b210", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    removed = migration.prune_branches(dbsession.connection())
    dbsession.expire_all()
    return removed


def _fork(dbsession, admin_user, rule):
    """A chain that branched: A spawned B, and C — a copy of A — spawned D.

    What parallel spawning used to leave behind. It can no longer be built
    through the spawn helpers, hence the direct links.
    """
    a, b = _chain(dbsession, admin_user, rule, "A", "B")
    c, d = _chain(dbsession, admin_user, rule, "C", "D")
    return a, b, c, d


def test_a_rule_that_never_branched_is_left_alone(dbsession, admin_user):
    rule = _make_rule(dbsession, "every", "week", n=1)
    _chain(dbsession, admin_user, rule, "A", "B", "C")

    assert _prune_branches(dbsession) == 0

    left = dbsession.query(Todo).filter(Todo.recurrence_id == rule.id).all()
    assert sorted(t.text for t in left) == ["A", "B", "C"]


def test_only_the_newest_chain_survives(dbsession, admin_user):
    rule = _make_rule(dbsession, "every", "week", n=1)
    _fork(dbsession, admin_user, rule)

    assert _prune_branches(dbsession) == 2

    # D is the newest, so its chain — C then D — is what the rule is up to.
    left = dbsession.query(Todo).filter(Todo.recurrence_id == rule.id).all()
    assert sorted(t.text for t in left) == ["C", "D"]


def test_completed_instances_on_a_branch_go_too(dbsession, admin_user):
    """They are a copy of history, not history."""
    rule = _make_rule(dbsession, "every", "week", n=1)
    a, b, c, d = _fork(dbsession, admin_user, rule)
    a.status = TodoStatus.done
    a.done_at = _now()
    dbsession.flush()

    _prune_branches(dbsession)

    assert dbsession.query(Todo).filter(Todo.text == "A").count() == 0


def test_other_rules_are_left_alone(dbsession, admin_user):
    rule = _make_rule(dbsession, "every", "week", n=1)
    other = _make_rule(dbsession, "every", "week", n=2)
    _fork(dbsession, admin_user, rule)
    _chain(dbsession, admin_user, other, "X", "Y")

    _prune_branches(dbsession)

    kept = dbsession.query(Todo).filter(Todo.recurrence_id == other.id).all()
    assert sorted(t.text for t in kept) == ["X", "Y"]


def test_a_todo_with_no_rule_at_all_is_left_alone(dbsession, admin_user):
    rule = _make_rule(dbsession, "every", "week", n=1)
    _fork(dbsession, admin_user, rule)
    _make_todo(dbsession, text="ordinary", owner=admin_user)

    _prune_branches(dbsession)

    assert dbsession.query(Todo).filter(Todo.text == "ordinary").count() == 1


def test_a_protocol_runs_todo_is_kept_where_it_is(dbsession, admin_user):
    """Deleting it would take the run with it."""
    protocol = Protocol(title="Bins", owner_id=admin_user.id)
    dbsession.add(protocol)
    dbsession.flush()
    run = ProtocolRun(
        protocol_id=protocol.id, spawned_at=_now(), owner_id=admin_user.id
    )
    dbsession.add(run)
    dbsession.flush()

    rule = _make_rule(dbsession, "every", "week", n=1)
    a, b, c, d = _fork(dbsession, admin_user, rule)
    a.protocol_run_id = run.id
    dbsession.flush()

    # A stays, and B — which it pointed at — still goes.
    assert _prune_branches(dbsession) == 1
    left = sorted(
        t.text for t in dbsession.query(Todo).filter(Todo.recurrence_id == rule.id)
    )
    assert left == ["A", "C", "D"]
    assert dbsession.get(Todo, a.id).recurred_into_id is None


def test_the_migration_copes_with_the_column_it_is_replacing(
    clean_db, dbengine, ini_file
):
    """The branches are still pointed at by whatever spawned them.

    Deleting one while the old predecessor column is still there fails on its
    foreign key. Only a round trip through the migration can catch that:
    anything built afterwards has no old column to trip over, which is why
    this went out green and fell over on a real database.
    """
    import alembic.command
    import alembic.config
    from sqlalchemy import text

    config = alembic.config.Config(ini_file)
    alembic.command.downgrade(config, "a9df32556402")
    try:
        with dbengine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO recurrence_rules (id, kind, interval_value,
                                                  interval_unit)
                         VALUES (1, 'every', 1, 'week')
                    """
                )
            )
            # A forked chain: 1 spawned both 2 and 3, and 3 spawned 4.
            for todo_id, parent in ((1, None), (2, 1), (3, 1), (4, 3)):
                conn.execute(
                    text(
                        """
                        INSERT INTO todos (id, text, tags, assignees, status,
                                           created_at, recurrence_id,
                                           recurred_from_id)
                             VALUES (:id, :text, '{}', '{}', 'todo', now(), 1,
                                     :parent)
                        """
                    ),
                    {"id": todo_id, "text": f"T{todo_id}", "parent": parent},
                )

        alembic.command.upgrade(config, "head")

        with dbengine.begin() as conn:
            left = sorted(
                row[0] for row in conn.execute(text("SELECT id FROM todos")).fetchall()
            )
            # 4 is newest, so its chain — 1, 3, 4 — stays and 2 goes.
            assert left == [1, 3, 4]
            successors = dict(
                conn.execute(text("SELECT id, recurred_into_id FROM todos")).fetchall()
            )
            assert successors == {1: 3, 3: 4, 4: None}
    finally:
        # Whatever happened, the rest of the suite needs the schema back.
        alembic.command.upgrade(config, "head")
