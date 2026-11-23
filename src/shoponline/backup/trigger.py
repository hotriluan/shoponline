"""Queue a background action and wake the task that performs it.

The web never runs pg_dump itself: it writes a row to ops.backup_request and asks Task
Scheduler to start the task now. When that is not possible (a development machine, or the
account may not start the task) the request stays pending and the 15-minute backup task
handles it.
"""

from __future__ import annotations

import logging
import subprocess

from sqlalchemy import text
from sqlalchemy.orm import Session

from shoponline.db.models import BackupRequest

log = logging.getLogger(__name__)

BACKUP_TASK = "shoponline-backup"
RESTORE_TASK = "shoponline-restore"
ENQUEUE_LOCK_KEY = 0x5A9_0B09  # serialises "is anything running?" with the insert


def start_task(name: str) -> bool:
    """Ask Task Scheduler to run the task now; False when it could not be started."""
    try:
        result = subprocess.run(
            ["schtasks", "/Run", "/TN", name], capture_output=True, check=False, timeout=20
        )
    except (OSError, subprocess.SubprocessError):
        log.warning("Không gọi được schtasks để chạy %s", name)
        return False
    if result.returncode != 0:
        log.warning("schtasks /Run %s trả mã %s", name, result.returncode)
    return result.returncode == 0


def enqueue(
    db: Session,
    action: str,
    actor: str,
    *,
    kind: str | None = None,
    target_run_id: int | None = None,
    to_drive: bool = False,
    exclusive: bool = False,
    result: dict | None = None,
) -> BackupRequest | None:
    """Add a request and commit. With exclusive=True nothing is added (None) when a backup is
    already waiting or running; the check and the insert are one step, so two clicks at the same
    moment make one request."""
    from shoponline.backup import status

    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": ENQUEUE_LOCK_KEY})
    if exclusive and status.is_busy(db):
        db.rollback()
        return None
    request = BackupRequest(
        action=action,
        kind=kind,
        target_run_id=target_run_id,
        to_drive=to_drive,
        requested_by=actor[:50],
        result=result,
    )
    db.add(request)
    db.commit()
    return request
