"""When the scheduled backups are due, in Vietnam time.

The backup task runs every 15 minutes with --if-due. A kind is due when no scheduled backup of
it succeeded since its latest planned time, so a machine that was off at that time catches up
once when it comes back. Application backups are never scheduled (a full backup contains one).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, time, timedelta

from shoponline.clock import VIETNAM

SCHEDULED_KINDS = ("db", "full")  # in this order when both are due


def _at(day, moment: time) -> datetime:
    return datetime.combine(day, moment, VIETNAM)


def last_slot(kind: str, now: datetime, settings) -> datetime | None:
    """The latest planned time of `kind` at or before `now`; None for unscheduled kinds."""
    local = now.astimezone(VIETNAM)
    if kind == "db":
        slot = _at(local.date(), settings.db_time)
        return slot if slot <= local else slot - timedelta(days=1)
    if kind == "full":
        back = (local.weekday() - settings.full_weekday) % 7
        slot = _at(local.date() - timedelta(days=back), settings.full_time)
        return slot if slot <= local else slot - timedelta(days=7)
    return None


def next_slot(kind: str, now: datetime, settings) -> datetime | None:
    slot = last_slot(kind, now, settings)
    if slot is None:
        return None
    return slot + timedelta(days=1 if kind == "db" else 7)


def is_due(kind: str, now: datetime, settings, last_success: datetime | None) -> bool:
    slot = last_slot(kind, now, settings)
    if slot is None:
        return False
    return last_success is None or last_success < slot


def due_kinds(now: datetime, settings, last_success: Mapping[str, datetime | None]) -> list[str]:
    return [k for k in SCHEDULED_KINDS if is_due(k, now, settings, last_success.get(k))]
