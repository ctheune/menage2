"""Repetition scheduling for todos.

Completing an item is what normally produces the next one, for both flavours
of rule: ``after`` counts the interval from the completion date, ``every``
takes the next occurrence of a fixed cadence. That happens there and then,
so the next item appears while you are looking at the list.

:func:`run_sweep` is the catch-up for everything completion cannot cover — a
rule nobody has touched, an ``every`` rule whose date has come round with
its last instance still open, a run that was missed while the app was down.
It is idempotent, and it belongs to the ``menage2_sweep`` command rather
than to a request: sweeping from whichever request happened to arrive first
meant several of them sweeping at once.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Iterable, Optional

from sqlalchemy import select
from sqlalchemy import update as sqla_update

import menage2.models.protocol
from menage2.dateparse import RecurrenceSpec, next_occurrence
from menage2.models.todo import (
    RecurrenceKind,
    RecurrenceRule,
    RecurrenceUnit,
    Todo,
    TodoAttachment,
    TodoLink,
    TodoStatus,
)

if TYPE_CHECKING:  # avoid circular import; models.protocol imports from this module
    from menage2.models.protocol import Protocol, ProtocolRun

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
        assignees=set(parent.assignees),
        note=parent.note,
        status=TodoStatus.todo,
        created_at=now_utc,
        due_date=due_date,
        recurrence_id=parent.recurrence_id,
        owner_id=parent.owner_id,
        links_rel=[
            TodoLink(label=lnk.label, url=lnk.url, position=lnk.position)
            for lnk in parent.links_rel
        ],
        attachments=[
            TodoAttachment(
                uuid=att.uuid,
                original_filename=att.original_filename,
                mimetype=att.mimetype,
                created_at=att.created_at,
            )
            for att in parent.attachments
        ],
    )


def _claim_successor(dbsession, parent: Todo, child: Todo) -> bool:
    """Record `child` as what `parent` spawned, if nothing else has.

    This is the whole of the chain guarantee. The UPDATE only matches while
    the successor is still unset, so of two requests spawning from the same
    item exactly one comes back with a row — the other learns it lost instead
    of quietly adding a second branch.
    """
    claimed = dbsession.execute(
        sqla_update(Todo)
        .where(Todo.id == parent.id, Todo.recurred_into_id.is_(None))
        .values(recurred_into_id=child.id)
    )
    if claimed.rowcount != 1:
        return False
    dbsession.expire(parent, ["recurred_into_id"])
    return True


def _spawn_linked(
    dbsession, parent: Todo, due_date: datetime.date, now_utc: datetime.datetime
) -> Todo | None:
    """Add the next instance after `parent`, or nothing if it already has one."""
    if parent.recurred_into_id is not None:
        return None
    child = _clone_for_recurrence(parent, due_date, now_utc)
    dbsession.add(child)
    dbsession.flush()
    if not _claim_successor(dbsession, parent, child):
        # Somebody else got there first. Take ours back out rather than leave
        # it behind as the branch this is all meant to prevent.
        dbsession.delete(child)
        dbsession.flush()
        return None
    return child


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
    return _spawn_linked(dbsession, completed_todo, next_date, now_utc)


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
) -> Optional[Todo]:
    """Materialise at least one current or future todo for every recurrence rule.

    Guarantees: after a successful sweep the chain has at least one active
    todo with ``due_date >= today``. Walks forward from the latest known
    ``due_date`` (active or done), spawning one Todo per occurrence until the
    next one is ``>= today``. Idempotent: skips entirely if such an active
    instance already exists.

    """
    rule = anchor_todo.recurrence
    if rule is None or rule.kind != RecurrenceKind.every:
        return None
    if _has_today_or_future_active(dbsession, rule.id, today):
        return None
    spec = rule_to_spec(rule)
    anchor = _latest_due_for_rule(dbsession, rule.id) or anchor_todo.due_date or today
    while (nxt := next_occurrence(spec, anchor)) < today:
        anchor = nxt
    return _spawn_linked(dbsession, anchor_todo, nxt, now_utc)


def run_sweep(dbsession, today: datetime.date, now_utc: datetime.datetime) -> int:
    """Create whatever is missing for every ``every`` rule, todos and protocols.

    Catch-up only: completing an item already produces its successor, so on
    most runs this finds nothing to do and says so by returning 0.

    Safe to run as often as you like — every rule that already has something
    due today or later is skipped, and a spawn that loses a race to another
    sweep takes its own row back out. There is no per-day marker any more:
    the command's schedule says when it runs, and running twice costs a
    couple of queries.

    Returns how many todos and protocol-run-todos were created.
    """
    spawned = _sweep_every_rules(dbsession, today, now_utc)
    spawned += _sweep_every_protocols(dbsession, today, now_utc)
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
        total += 1 if _spawn_every_chain(dbsession, anchor, today, now_utc) else 0
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
        tags=set(protocol.tags) if protocol.tags else set(),
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


def _predecessor(dbsession, todo: Todo) -> Todo | None:
    """Whatever spawned `todo`. At most one, because the column is UNIQUE."""
    return dbsession.execute(
        select(Todo).where(Todo.recurred_into_id == todo.id)
    ).scalar_one_or_none()


def chain_history(dbsession, todo: Todo) -> list[Todo]:
    """The whole chain `todo` belongs to, oldest first.

    Walks back to the first instance and then forward to the last, so it
    reads the same from whichever member it is handed. The `seen` guard is
    for data that predates the UNIQUE column rather than for anything the
    chain can do now.
    """
    seen = {todo.id}

    earlier: list[Todo] = []
    cursor = todo
    while (previous := _predecessor(dbsession, cursor)) is not None:
        if previous.id in seen:
            break
        earlier.append(previous)
        seen.add(previous.id)
        cursor = previous

    later: list[Todo] = []
    cursor = todo
    while cursor.recurred_into_id is not None:
        following = dbsession.get(Todo, cursor.recurred_into_id)
        if following is None or following.id in seen:
            break
        later.append(following)
        seen.add(following.id)
        cursor = following

    return list(reversed(earlier)) + [todo] + later
