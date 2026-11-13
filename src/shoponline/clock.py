"""One notion of "today" for the whole application: the calendar day in Vietnam."""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

VIETNAM = ZoneInfo("Asia/Saigon")


def today_vn(now: datetime | None = None) -> date:
    """The date in Asia/Saigon; `now` (any timezone, naive means UTC) is for tests."""
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(VIETNAM).date()
