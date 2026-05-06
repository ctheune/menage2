"""Repetition scheduling for todos.

Two flavours of recurrence rule are spawned by different triggers:

* ``after`` rules fire when an item is marked done. A new Todo is spawned with
  ``due_date = completion_date + interval``. Triggered from ``todos_done``.
* ``every`` rules fire on a fixed cadence regardless of completion. The view
  pipeline calls :func:`spawn_due_every_if_needed` which sweeps every active
  ``every`` rule and creates any missing occurrences whose ``due_date`` is on
  or before today. Gated by a per-day ``ConfigItem`` marker plus a
  process-wide :class:`threading.Lock` so concurrent web requests sweep at
  most once per day.
"""

from __future__ import annotations

import datetime
import threading
from typing import TYPE_CHECKING, Iterable

from sqlalchemy import select

import menage2.models.protocol
from menage2.dateparse import RecurrenceSpec, next_occurrence
from menage2.models.config import ConfigItem
from menage2.models.todo import (
    RecurrenceKind,
    RecurrenceRule,
    RecurrenceUnit,
    Todo,
    TodoStatus,
)

if TYPE_CHECKING:  # avoid circular import; models.protocol imports from this module
    from menage2.models.protocol import Protocol, ProtocolRun

_LAST_SWEEP_KEY = "last_recurrence_sweep_date"
_sweep_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Rule ↔ spec translation
# ---------------------------------------------------------------------------


def rule_to_spec(rule: RecurrenceRule) -> RecurrenceSpec:
    return RecurrenceSpec(
        kind=rule.kind.value,
        interval_value=rule.interval_value,
        interval_unit=rule.interval_unit.value,
        weekday=rule.weekday,
        month_day=rule.month_day,
    )


def spec_to_rule(spec: RecurrenceSpec) -> RecurrenceRule:
    return RecurrenceRule(
        kind=RecurrenceKind(spec.kind),
        interval_value=spec.interval_value,
        interval_unit=RecurrenceUnit(spec.interval_unit),
        weekday=spec.weekday,
        month_day=spec.month_day,
    )


# ---------------------------------------------------------------------------
# Spawn helpers
# ---------------------------------------------------------------------------


def _clone_for_recurrence(
    parent: Todo, due_date: datetime.date, now_utc: datetime.datetime
) -> Todo:
    return Todo(
        text=parent.text,
        tags=set(parent.tags),
        note=parent.note,
        status=TodoStatus.todo,
        created_at=now_utc,
        due_date=due_date,
        recurrence_id=parent.recurrence_id,
        recurred_from_id=parent.id,
        owner_id=parent.owner_id,
    )


def spawn_after(
    completed_todo: Todo,
    completion_date: datetime.date,
    now_utc: datetime.datetime,
    dbsession,
) -> Todo | None:
    """Spawn the next instance for an ``after`` rule. Returns the new Todo or
    None if the completed item carries no rule (or the rule isn't ``after``)."""
    rule = completed_todo.recurrence
    if rule is None or rule.kind != RecurrenceKind.after:
        return None
    next_date = next_occurrence(rule_to_spec(rule), completion_date)
    new_todo = _clone_for_recurrence(completed_todo, next_date, now_utc)
    dbsession.add(new_todo)
    dbsession.flush()
    return new_todo


def spawn_every_on_completion(
    completed_todo: Todo, today: datetime.date, now_utc: datetime.datetime, dbsession
) -> int:
    """Spawn the next ``every`` occurrence as soon as one is completed.

    Without this, completing the only active item in a chain would leave the
    chain empty until the next daily sweep, which forces the user to dig the
    item out of /todos/done to see what's next. Delegates to the same chain
    logic the sweep uses so the today-or-future invariant lives in one place
    and short-circuits when a future-active instance already exists.
    """
    rule = completed_todo.recurrence
    if rule is None or rule.kind != RecurrenceKind.every:
        return 0
    return _spawn_every_chain(dbsession, completed_todo, today, now_utc)


def _latest_due_for_rule(dbsession, rule_id: int) -> datetime.date | None:
    """Most recent ``due_date`` of any todo (active or done) tied to this rule."""
    return dbsession.execute(
        select(Todo.due_date)
        .where(Todo.recurrence_id == rule_id, Todo.due_date.is_not(None))
        .order_by(Todo.due_date.desc())
        .limit(1)
    ).scalar()


def _has_today_or_future_active(dbsession, rule_id: int, today: datetime.date) -> bool:
    """Whether the rule already has an active instance due today or later."""
    return (
        dbsession.execute(
            select(Todo.id)
            .where(
                Todo.recurrence_id == rule_id,
                Todo.status == TodoStatus.todo,
                Todo.due_date >= today,
            )
            .limit(1)
        ).scalar()
        is not None
    )


def _spawn_every_chain(
    dbsession, anchor_todo: Todo, today: datetime.date, now_utc: datetime.datetime
) -> int:
    """Materialise occurrences for one ``every`` rule.

    Guarantees: after a successful sweep the chain has at least one active
    todo with ``due_date >= today``. Walks forward from the latest known
    ``due_date`` (active or done), spawning one Todo per occurrence until the
    next one is ``>= today``. Idempotent: skips entirely if such an active
    instance already exists.
    """
    rule = anchor_todo.recurrence
    if rule is None or rule.kind != RecurrenceKind.every:
        return 0
    if _has_today_or_future_active(dbsession, rule.id, today):
        return 0
    spec = rule_to_spec(rule)
    anchor = _latest_due_for_rule(dbsession, rule.id) or anchor_todo.due_date or today
    spawned = 0
    parent = anchor_todo
    while True:
        nxt = next_occurrence(spec, anchor)
        new_todo = _clone_for_recurrence(parent, nxt, now_utc)
        dbsession.add(new_todo)
        dbsession.flush()
        spawned += 1
        if nxt >= today:
            # Chain now has a today-or-future active instance — done.
            break
        anchor = nxt
        parent = new_todo
        if spawned > 50:  # safety bound for pathological catch-ups
            break
    return spawned


def _today_marker(today: datetime.date) -> str:
    return today.isoformat()


def _read_marker(dbsession) -> str | None:
    item = dbsession.get(ConfigItem, _LAST_SWEEP_KEY)
    return item.value if item else None


def _write_marker(dbsession, value: str) -> None:
    item = dbsession.get(ConfigItem, _LAST_SWEEP_KEY)
    if item is None:
        dbsession.add(ConfigItem(key=_LAST_SWEEP_KEY, value=value))
    else:
        item.value = value


def spawn_due_every_if_needed(
    dbsession, today: datetime.date, now_utc: datetime.datetime
) -> int:
    """Sweep ``every`` rules — todos AND protocols — at most once per day.

    Holds the process-wide :data:`_sweep_lock` to serialise concurrent
    requests within a single worker. The marker check + write happens inside
    the lock so simultaneous list views collapse to a single sweep.

    Returns the total number of todos and protocol-run-todos spawned.
    """
    today_str = _today_marker(today)
    with _sweep_lock:
        if _read_marker(dbsession) == today_str:
            return 0
        spawned = _sweep_every_rules(dbsession, today, now_utc)
        spawned += _sweep_every_protocols(dbsession, today, now_utc)
        _write_marker(dbsession, today_str)
        return spawned


def force_recurrence_sweep(
    dbsession, today: datetime.date, now_utc: datetime.datetime
) -> int:
    """Run the sweep regardless of the daily marker (admin action).

    Still serialised by :data:`_sweep_lock`. The marker is bumped to today
    on success so the automatic per-day check stays consistent.
    """
    today_str = _today_marker(today)
    with _sweep_lock:
        spawned = _sweep_every_rules(dbsession, today, now_utc)
        spawned += _sweep_every_protocols(dbsession, today, now_utc)
        _write_marker(dbsession, today_str)
        return spawned


def _sweep_every_rules(
    dbsession, today: datetime.date, now_utc: datetime.datetime
) -> int:
    """Find one anchor Todo per ``every`` rule and call _spawn_every_chain."""
    every_rules: Iterable[RecurrenceRule] = (
        dbsession.execute(
            select(RecurrenceRule).where(RecurrenceRule.kind == RecurrenceKind.every)
        )
        .scalars()
        .all()
    )
    total = 0
    for rule in every_rules:
        anchor = dbsession.execute(
            select(Todo)
            .where(Todo.recurrence_id == rule.id)
            .order_by(Todo.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if anchor is None:
            continue
        total += _spawn_every_chain(dbsession, anchor, today, now_utc)
    return total


# ---------------------------------------------------------------------------
# Protocol spawning
# ---------------------------------------------------------------------------


def spawn_protocol_run(
    protocol: menage2.models.Protocol,
    due_date: datetime.date,
    now_utc: datetime.datetime,
    dbsession,
    owner_id: int | None = None,
) -> menage2.models.ProtocolRun:
    """Create one ProtocolRun + its calendar Todo. Items are NOT snapshotted
    yet — that happens lazily when the user opens the run page.
    """
    effective_owner = owner_id if owner_id is not None else protocol.owner_id
    run = menage2.models.ProtocolRun(
        protocol_id=protocol.id, spawned_at=now_utc, owner_id=effective_owner
    )
    dbsession.add(run)
    dbsession.flush()
    todo = Todo(
        text=protocol.title,
        tags=set(),
        assignees=set(protocol.assignees) if protocol.assignees else set(),
        status=TodoStatus.todo,
        created_at=now_utc,
        due_date=due_date,
        protocol_run_id=run.id,
        owner_id=effective_owner,
    )
    dbsession.add(todo)
    dbsession.flush()
    return run


def _has_today_or_future_active_run(
    dbsession, protocol_id: int, today: datetime.date
) -> bool:
    """Whether the protocol has an active run-todo due today or later."""
    return (
        dbsession.execute(
            select(Todo.id)
            .join(
                menage2.models.protocol.ProtocolRun,
                menage2.models.protocol.ProtocolRun.id == Todo.protocol_run_id,
            )
            .where(
                menage2.models.protocol.ProtocolRun.protocol_id == protocol_id,
                Todo.status == TodoStatus.todo,
                Todo.due_date >= today,
            )
            .limit(1)
        ).scalar()
        is not None
    )


def _latest_run_due_for_protocol(dbsession, protocol_id: int) -> datetime.date | None:
    """The most recent due_date of any run-todo for this protocol."""
    ProtocolRun = menage2.models.protocol.ProtocolRun
    return dbsession.execute(
        select(Todo.due_date)
        .join(ProtocolRun, ProtocolRun.id == Todo.protocol_run_id)
        .where(ProtocolRun.protocol_id == protocol_id, Todo.due_date.is_not(None))
        .order_by(Todo.due_date.desc())
        .limit(1)
    ).scalar()


def spawn_protocol_after(
    closed_run: ProtocolRun,
    completion_date: datetime.date,
    now_utc: datetime.datetime,
    dbsession,
) -> ProtocolRun | None:
    """Spawn the next run for an ``after`` rule when the previous one closes."""
    protocol = closed_run.protocol
    rule = protocol.recurrence if protocol else None
    if rule is None or rule.kind != RecurrenceKind.after:
        return None
    next_date = next_occurrence(rule_to_spec(rule), completion_date)
    return spawn_protocol_run(protocol, next_date, now_utc, dbsession)


def spawn_protocol_every_on_completion(
    closed_run: ProtocolRun, today: datetime.date, now_utc: datetime.datetime, dbsession
) -> int:
    """Mirror of spawn_every_on_completion for protocols."""
    protocol = closed_run.protocol
    rule = protocol.recurrence if protocol else None
    if rule is None or rule.kind != RecurrenceKind.every:
        return 0
    if _has_today_or_future_active_run(dbsession, protocol.id, today):
        return 0
    spec = rule_to_spec(rule)
    anchor = _latest_run_due_for_protocol(dbsession, protocol.id) or today
    spawned = 0
    while True:
        nxt = next_occurrence(spec, anchor)
        spawn_protocol_run(protocol, nxt, now_utc, dbsession)
        spawned += 1
        if nxt >= today:
            break
        anchor = nxt
        if spawned > 50:
            break
    return spawned


def ensure_protocol_has_run(
    protocol: Protocol, today: datetime.date, now_utc: datetime.datetime, dbsession
) -> None:
    """Immediately create a run for a newly-recurrent protocol if none active.

    Bypasses the daily-sweep marker so the first run appears right away when
    the user sets a recurrence rather than waiting until the next page load.
    """
    rule = protocol.recurrence
    if rule is None:
        return
    if _has_today_or_future_active_run(dbsession, protocol.id, today):
        return
    spec = rule_to_spec(rule)
    anchor = _latest_run_due_for_protocol(dbsession, protocol.id)
    if anchor is None:
        anchor = today - datetime.timedelta(days=1)
    nxt = next_occurrence(spec, anchor)
    while nxt < today:
        spawn_protocol_run(protocol, nxt, now_utc, dbsession)
        anchor = nxt
        nxt = next_occurrence(spec, anchor)
    spawn_protocol_run(protocol, nxt, now_utc, dbsession)


def _sweep_every_protocols(
    dbsession, today: datetime.date, now_utc: datetime.datetime
) -> int:
    """Daily sweep equivalent for every-rule protocols."""
    every_protocols = (
        dbsession.execute(
            select(menage2.models.protocol.Protocol)
            .join(
                RecurrenceRule,
                RecurrenceRule.id == menage2.models.protocol.Protocol.recurrence_id,
            )
            .where(
                RecurrenceRule.kind == RecurrenceKind.every,
                menage2.models.protocol.Protocol.archived_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    total = 0
    for protocol in every_protocols:
        if _has_today_or_future_active_run(dbsession, protocol.id, today):
            continue
        spec = rule_to_spec(protocol.recurrence)
        anchor = _latest_run_due_for_protocol(dbsession, protocol.id) or today
        spawned_here = 0
        while True:
            nxt = next_occurrence(spec, anchor)
            spawn_protocol_run(protocol, nxt, now_utc, dbsession)
            spawned_here += 1
            if nxt >= today:
                break
            anchor = nxt
            if spawned_here > 50:
                break
        total += spawned_here
    return total


# ---------------------------------------------------------------------------
# History helpers
# ---------------------------------------------------------------------------


def chain_history(dbsession, todo: Todo) -> list[Todo]:
    """Walk ``recurred_from_id`` backwards. Returns oldest-first list."""
    chain = [todo]
    cursor = todo
    seen = {todo.id}
    while cursor.recurred_from_id is not None:
        prev = dbsession.get(Todo, cursor.recurred_from_id)
        if prev is None or prev.id in seen:
            break
        chain.append(prev)
        seen.add(prev.id)
        cursor = prev
    return list(reversed(chain))
