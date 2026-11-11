"""Suggested goods issue date for a processing day D."""

from __future__ import annotations

from datetime import date, timedelta


def suggest_gi_date(processing_date: date) -> date:
    """Next working day (skip Saturday and Sunday); D itself if that day is in another month.

    Public holidays are not known; admins edit the date on the batch screen.
    """
    candidate = processing_date + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    if (candidate.year, candidate.month) != (processing_date.year, processing_date.month):
        return processing_date
    return candidate
