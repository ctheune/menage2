"""Periodic housekeeping, run by the ``menage2_sweep`` command.

One place for everything that has to happen on a schedule rather than in a
request: catching up recurrences and dropping hold markers that have lapsed.
"""

import datetime

from menage2.models.item import purge_lapsed_holds
from menage2.recurrence import run_sweep


def run_housekeeping(
    dbsession, today: datetime.date, now_utc: datetime.datetime
) -> int:
    """Run every periodic task; returns how many todos the sweep created."""
    spawned = run_sweep(dbsession, today, now_utc)
    purge_lapsed_holds(dbsession, now_utc)
    return spawned
