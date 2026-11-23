"""Work folders for backup contents, inside <SHOPONLINE_DATA_DIR>\\backup-work.

Decrypted dumps and data never go to %TEMP%: the data folder carries the account-only access
rights, and every work folder is removed when the work ends, also on an error. A process killed
mid-run leaves its folder behind; sweep_stale removes those at the start of the next run.
"""

from __future__ import annotations

import shutil
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

STALE_SECONDS = 24 * 3600
# Data items moved aside by a restore of a full backup stay a week as a manual way back.
BEFORE_RESTORE_PREFIX = "before-restore-"
BEFORE_RESTORE_SECONDS = 7 * 24 * 3600


@contextmanager
def staging_dir(work_root: Path, label: str = "work") -> Iterator[Path]:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path = work_root / f"{label}-{stamp}-{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def sweep_stale(work_root: Path, now: float | None = None) -> list[Path]:
    """Remove leftover work folders; returns what was removed."""
    if not work_root.is_dir():
        return []
    moment = time.time() if now is None else now
    removed = []
    for child in work_root.iterdir():
        limit = (
            BEFORE_RESTORE_SECONDS
            if child.name.startswith(BEFORE_RESTORE_PREFIX)
            else STALE_SECONDS
        )
        try:
            age = moment - child.stat().st_mtime
        except OSError:
            continue
        if age > limit:
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
            removed.append(child)
    return removed
