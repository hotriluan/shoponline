"""Screenshots of the SAP window when a job goes wrong; old ones are deleted."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

from shoponline.saprobot.guard import GuardedSession

log = logging.getLogger(__name__)


def capture(session: GuardedSession, evidence_dir: Path, job_id: int) -> Path | None:
    """Save the active SAP window as PNG. Never raises: evidence must not hide the real error."""
    try:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        path = evidence_dir / f"job-{job_id}-{datetime.now():%Y%m%d-%H%M%S}.png"
        session.hardcopy(str(path))
        return path if path.is_file() else None
    except Exception as exc:
        log.warning("Không chụp được màn hình cho việc #%s: %s", job_id, exc)
        return None


def prune(evidence_dir: Path, keep_days: int, now: float | None = None) -> int:
    """Delete screenshots older than keep_days; they may show customer data."""
    if not evidence_dir.is_dir():
        return 0
    cutoff = (now or time.time()) - keep_days * 86400
    removed = 0
    for path in evidence_dir.glob("job-*.png"):
        if path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)
            removed += 1
    return removed
