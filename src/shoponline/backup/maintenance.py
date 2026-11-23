"""The marker file a deploy or a restore keeps while it works, so the two never overlap.

The file is maintenance.json in the data folder; it holds {"kind": "deploy"|"restore"|"migration",
"pid", "started_at"}.
update-production.ps1 reads and writes the same file. A marker older than 2 hours is stale (the
process that wrote it died) and counts as absent.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta

from shoponline.config import Settings

NAME = "maintenance.json"
STALE_AFTER = timedelta(hours=2)


def _path(settings: Settings):
    return settings.data_dir / NAME


def read(settings: Settings, now: datetime | None = None) -> dict | None:
    """The marker, or None when there is none, it is unreadable or it is stale."""
    try:
        marker = json.loads(_path(settings).read_text(encoding="utf-8-sig"))
        started = datetime.fromisoformat(marker["started_at"])
    except (OSError, ValueError, KeyError):
        return None
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    if (now or datetime.now(UTC)) - started > STALE_AFTER:
        return None
    return marker


def active(settings: Settings, kind: str) -> bool:
    marker = read(settings)
    return marker is not None and marker.get("kind") == kind


def write(settings: Settings, kind: str) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    marker = {"kind": kind, "pid": os.getpid(), "started_at": datetime.now(UTC).isoformat()}
    _path(settings).write_text(json.dumps(marker), encoding="utf-8")


def clear(settings: Settings, kind: str) -> None:
    """Remove the marker only when it is ours (a deploy never removes a restore's marker)."""
    marker = read(settings)
    if marker is not None and marker.get("kind") == kind:
        _path(settings).unlink(missing_ok=True)
