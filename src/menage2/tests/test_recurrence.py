"""Tests for menage2.recurrence — spawn helpers and the daily-sweep gate."""
import datetime
import threading

import pytest

from menage2.dateparse import RecurrenceSpec
from menage2.models.config import ConfigItem
from menage2.models.todo import (
    RecurrenceKind,
    RecurrenceRule,
    RecurrenceUnit,
    Todo,
    TodoStatus,
)
from menage2.recurrence import (
    _LAST_SWEEP_KEY,
    chain_history,
    force_recurrence_sweep,
    rule_to_spec,
    spawn_after,
    spawn_due_every_if_needed,
    spawn_every_on_completion,
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
# spawn_after
# ---------------------------------------------------------------------------


def test_spawn_after_creates_clone_with_new_due_date(dbsession):
    rule = _make_rule(dbsession, "after", "week", n=1)
    parent = _make_todo(dbsession, text="Water plants", tags={"chores"}, recurrence_id=rule.id)
    completion = datetime.date(2026, 5, 10)
    new = spawn_after(parent, completion, _now(), dbsession)
    assert new is not None
    assert new.text == "Water plants"
    assert new.tags == {"chores"}
    assert new.recurrence_id == rule.id
    assert new.recurred_from_id == parent.id
    assert new.status == TodoStatus.todo
    assert new.due_date == datetime.date(2026, 5, 17)


def test_spawn_after_returns_none_for_non_after_rule(dbsession):
    rule = _make_rule(dbsession, "every", "week", n=1)
    parent = _make_todo(dbsession, recurrence_id=rule.id)
    assert spawn_after(parent, datetime.date(2026, 5, 1), _now(), dbsession) is None


def test_spawn_after_returns_none_for_no_rule(dbsession):
    parent = _make_todo(dbsession)
    assert spawn_after(parent, datetime.date(2026, 5, 1), _now(), dbsession) is None


# ---------------------------------------------------------------------------
# spawn_every_on_completion
# ---------------------------------------------------------------------------


def test_spawn_every_on_completion_creates_next_instance(dbsession):
    today = datetime.date(2026, 4, 29)  # Wed
    rule = _make_rule(dbsession, "every", "week", weekday=2)
    todo = _make_todo(dbsession, text="Yoga", recurrence_id=rule.id, due_date=today,
                      status=TodoStatus.done, done_at=_now())
    spawned = spawn_every_on_completion(todo, today, _now(), dbsession)
    assert spawned == 1
    pending = dbsession.query(Todo).filter(
        Todo.recurrence_id == rule.id,
        Todo.status == TodoStatus.todo,
    ).all()
    assert len(pending) == 1
    assert pending[0].due_date == datetime.date(2026, 5, 6)
    assert pending[0].recurred_from_id == todo.id


def test_spawn_every_on_completion_skips_if_future_already_active(dbsession):
    today = datetime.date(2026, 4, 29)
    rule = _make_rule(dbsession, "every", "week", weekday=2)
    # Sweep already created next-Wed before this completion
    _make_todo(dbsession, text="next", recurrence_id=rule.id,
               due_date=datetime.date(2026, 5, 6))
    completed = _make_todo(dbsession, text="now", recurrence_id=rule.id,
                           due_date=today, status=TodoStatus.done, done_at=_now())
    spawned = spawn_every_on_completion(completed, today, _now(), dbsession)
    assert spawned == 0


def test_spawn_every_on_completion_no_op_for_after_rule(dbsession):
    rule = _make_rule(dbsession, "after", "week", n=1)
    todo = _make_todo(dbsession, recurrence_id=rule.id)
    assert spawn_every_on_completion(todo, datetime.date(2026, 5, 1), _now(), dbsession) == 0


def test_spawn_every_on_completion_no_op_for_no_rule(dbsession):
    todo = _make_todo(dbsession)
    assert spawn_every_on_completion(todo, datetime.date(2026, 5, 1), _now(), dbsession) == 0


# ---------------------------------------------------------------------------
# spawn_due_every_if_needed (daily gate, sweeps)
# ---------------------------------------------------------------------------


def test_sweep_creates_no_op_when_marker_already_today(dbsession):
    today = datetime.date(2026, 4, 29)
    dbsession.add(ConfigItem(key=_LAST_SWEEP_KEY, value=today.isoformat()))
    rule = _make_rule(dbsession, "every", "week", weekday=2)
    _make_todo(dbsession, text="Yoga", recurrence_id=rule.id, due_date=datetime.date(2026, 4, 22))
    spawned = spawn_due_every_if_needed(dbsession, today, _now())
    assert spawned == 0
    # Only the original anchor exists
    assert dbsession.query(Todo).count() == 1


def test_sweep_writes_marker_after_running(dbsession):
    today = datetime.date(2026, 4, 29)
    rule = _make_rule(dbsession, "every", "week", n=1)
    _make_todo(dbsession, text="Weekly rev", recurrence_id=rule.id, due_date=today)
    spawn_due_every_if_needed(dbsession, today, _now())
    item = dbsession.get(ConfigItem, _LAST_SWEEP_KEY)
    assert item.value == today.isoformat()


def test_sweep_skips_when_today_active_anchor(dbsession):
    """An active anchor due today already satisfies 'has today-or-future'."""
    today = datetime.date(2026, 4, 29)  # Wed
    rule = _make_rule(dbsession, "every", "week", weekday=2)
    _make_todo(dbsession, text="Weekly", recurrence_id=rule.id, due_date=today)
    spawned = spawn_due_every_if_needed(dbsession, today, _now())
    assert spawned == 0


def test_sweep_creates_next_when_today_anchor_already_done(dbsession):
    """Today's instance done → spawn the next so the chain stays alive."""
    today = datetime.date(2026, 4, 29)  # Wed
    rule = _make_rule(dbsession, "every", "week", weekday=2)
    _make_todo(dbsession, text="Weekly", recurrence_id=rule.id, due_date=today,
               status=TodoStatus.done, done_at=_now())
    spawned = spawn_due_every_if_needed(dbsession, today, _now())
    assert spawned >= 1
    pending = dbsession.query(Todo).filter(
        Todo.recurrence_id == rule.id,
        Todo.status == TodoStatus.todo,
    ).all()
    assert len(pending) == 1
    assert pending[0].due_date == datetime.date(2026, 5, 6)


def test_sweep_catches_up_missed_occurrences(dbsession):
    today = datetime.date(2026, 4, 29)  # Wed
    rule = _make_rule(dbsession, "every", "week", weekday=2)
    _make_todo(dbsession, text="catchup", recurrence_id=rule.id,
               due_date=datetime.date(2026, 4, 1))  # Wed, 4 weeks before today
    spawn_due_every_if_needed(dbsession, today, _now())
    children = dbsession.query(Todo).filter(Todo.recurrence_id == rule.id).all()
    # We require: at least one due_date today-or-later (the chain is alive again)
    assert any(c.due_date >= today for c in children)
    # All children share the rule.
    assert all(c.recurrence_id == rule.id for c in children)


def test_sweep_creates_until_today_or_future_when_only_past_active(dbsession):
    """Past-active instance counts as 'no today-or-future' → catch up."""
    today = datetime.date(2026, 4, 29)  # Wed
    rule = _make_rule(dbsession, "every", "week", weekday=2)
    _make_todo(dbsession, text="overdue", recurrence_id=rule.id,
               due_date=datetime.date(2026, 4, 8), status=TodoStatus.todo)
    spawn_due_every_if_needed(dbsession, today, _now())
    actives = dbsession.query(Todo).filter(
        Todo.recurrence_id == rule.id,
        Todo.status == TodoStatus.todo,
    ).all()
    # Original past one stays + at least one with due_date >= today is now present.
    assert any(t.due_date >= today for t in actives)


def test_sweep_skips_when_future_active_exists(dbsession):
    today = datetime.date(2026, 4, 29)
    rule = _make_rule(dbsession, "every", "week", n=1)
    _make_todo(dbsession, text="anchor", recurrence_id=rule.id,
               due_date=datetime.date(2026, 4, 1))
    # Already-pending future instance — sweep should leave well alone.
    _make_todo(dbsession, text="pending", recurrence_id=rule.id,
               due_date=datetime.date(2026, 5, 6), status=TodoStatus.todo)
    before = dbsession.query(Todo).count()
    spawn_due_every_if_needed(dbsession, today, _now())
    assert dbsession.query(Todo).count() == before


def test_force_recurrence_sweep_bypasses_daily_marker(dbsession):
    today = datetime.date(2026, 4, 29)
    dbsession.add(ConfigItem(key=_LAST_SWEEP_KEY, value=today.isoformat()))
    rule = _make_rule(dbsession, "every", "week", weekday=2)
    _make_todo(dbsession, text="forced", recurrence_id=rule.id,
               due_date=datetime.date(2026, 4, 1))
    spawned = force_recurrence_sweep(dbsession, today, _now())
    assert spawned >= 1
    pending = dbsession.query(Todo).filter(
        Todo.recurrence_id == rule.id,
        Todo.status == TodoStatus.todo,
        Todo.due_date >= today,
    ).count()
    assert pending == 1


def test_sweep_concurrent_calls_collapse_to_one(dbsession):
    today = datetime.date(2026, 4, 29)
    rule = _make_rule(dbsession, "every", "week", n=1)
    # Past-due anchor → the chain has no today-or-future, so a sweep would
    # spawn. We expect only the first thread to actually do so.
    _make_todo(dbsession, recurrence_id=rule.id,
               due_date=datetime.date(2026, 4, 1))

    results = []
    barrier = threading.Barrier(3)

    def worker():
        barrier.wait()
        spawned = spawn_due_every_if_needed(dbsession, today, _now())
        results.append(spawned)

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads: t.start()
    for t in threads: t.join()

    # Exactly one thread did the spawn; the others saw the marker.
    assert results.count(0) == 2
    assert sum(results) >= 1


# ---------------------------------------------------------------------------
# chain_history
# ---------------------------------------------------------------------------


def test_chain_history_walks_oldest_first(dbsession):
    rule = _make_rule(dbsession, "every", "week", n=1)
    a = _make_todo(dbsession, text="A", recurrence_id=rule.id)
    b = _make_todo(dbsession, text="B", recurrence_id=rule.id, recurred_from_id=a.id)
    c = _make_todo(dbsession, text="C", recurrence_id=rule.id, recurred_from_id=b.id)
    chain = chain_history(dbsession, c)
    assert [t.text for t in chain] == ["A", "B", "C"]


def test_chain_history_single_item_when_no_parent(dbsession):
    t = _make_todo(dbsession, text="solo")
    assert chain_history(dbsession, t) == [t]
