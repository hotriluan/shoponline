"""SAP job queue in PostgreSQL: enqueue with a dedupe key, claim with SKIP LOCKED, record outcome.

Callers own the transaction: every function flushes, none commits.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shoponline.db.models import RobotControl, SapJob
from shoponline.domain import states

PENDING = "PENDING"
RUNNING = "RUNNING"
DONE = "DONE"
FAILED = "FAILED"
UNKNOWN = "UNKNOWN"
NEED_REVIEW = "NEED_REVIEW"
ACTIVE_STATUSES = frozenset({PENDING, RUNNING, UNKNOWN, NEED_REVIEW})

READ_ZRSD001 = "read_zrsd001"
READ_ZRSD004 = "read_zrsd004"
# Jobs that only read SAP; they can be retried without risk of creating a second document.
# Logs on, reads who is logged on, logs off. It sends no T-code, so it also runs while the robot is
# paused or the configured system has not been verified yet.
CHECK_CONNECTION = "check_connection"
READ_KINDS = frozenset({READ_ZRSD001, READ_ZRSD004, CHECK_CONNECTION})
CHECK_KEY = "check_connection"

LABELS = {
    PENDING: "Chờ",
    RUNNING: "Đang chạy",
    DONE: "Xong",
    FAILED: "Lỗi",
    UNKNOWN: "Chưa rõ",
    NEED_REVIEW: "Cần kiểm tra",
}


@dataclass(frozen=True)
class SapTarget:
    system: str
    client: str

    def __str__(self) -> str:
        return f"{self.system}/{self.client}"


class DuplicateJob(ValueError):
    pass


class JobStateError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def payload_of(job: SapJob) -> dict:
    return json.loads(job.payload or "{}")


def result_of(job: SapJob) -> dict:
    return json.loads(job.result) if job.result else {}


def target_of(job: SapJob) -> SapTarget:
    return SapTarget(job.target_system, job.target_client)


def enqueue(
    session: Session,
    kind: str,
    target: SapTarget,
    dedupe_key: str,
    payload: dict,
    actor: str,
) -> SapJob:
    """Add a PENDING job. A second job with the key of an unfinished one is refused."""
    existing = session.scalar(
        select(SapJob).where(SapJob.dedupe_key == dedupe_key, SapJob.status.in_(ACTIVE_STATUSES))
    )
    if existing is not None:
        raise DuplicateJob(f"Đã có việc #{existing.id} ({existing.status}) cho {dedupe_key}")
    job = SapJob(
        kind=kind,
        target_system=target.system,
        target_client=target.client,
        dedupe_key=dedupe_key,
        payload=json.dumps(payload, ensure_ascii=False),
        status=PENDING,
        attempts=0,
        created_by=actor,
    )
    try:
        with session.begin_nested():
            session.add(job)
            session.flush()
    except IntegrityError as exc:  # another session enqueued the same key concurrently
        raise DuplicateJob(f"Đã có việc đang mở cho {dedupe_key}") from exc
    states.log_event(session, actor, "sap_job_enqueued", detail=_brief(job))
    return job


def claim(session: Session, kinds: frozenset[str] | None = None) -> SapJob | None:
    """Take the oldest PENDING job (of the given kinds); concurrent claimers skip locked rows."""
    stmt = select(SapJob).where(SapJob.status == PENDING)
    if kinds is not None:
        stmt = stmt.where(SapJob.kind.in_(kinds))
    job = session.scalar(stmt.order_by(SapJob.id).limit(1).with_for_update(skip_locked=True))
    if job is None:
        return None
    job.status = RUNNING
    job.attempts += 1
    job.started_at = _now()
    job.finished_at = None
    job.error = None
    job.evidence_path = None
    session.flush()
    return job


def _finish(session: Session, job: SapJob, status: str, actor: str, **fields) -> None:
    if job.status != RUNNING:
        raise JobStateError(f"Việc #{job.id} đang ở {job.status}, không phải {RUNNING}")
    job.status = status
    job.finished_at = _now()
    for name, value in fields.items():
        setattr(job, name, value)
    session.flush()
    states.log_event(session, actor, f"sap_job_{status.lower()}", detail=_brief(job))


def complete(session: Session, job: SapJob, result: dict, actor: str = "robot") -> None:
    _finish(session, job, DONE, actor, result=json.dumps(result, ensure_ascii=False))


def fail(
    session: Session,
    job: SapJob,
    error: str,
    evidence: str | None = None,
    actor: str = "robot",
    result: dict | None = None,
) -> None:
    fields = {"error": error, "evidence_path": evidence}
    if result is not None:
        fields["result"] = json.dumps(result, ensure_ascii=False)
    _finish(session, job, FAILED, actor, **fields)


def mark_unknown(
    session: Session, job: SapJob, error: str, evidence: str | None = None, actor: str = "robot"
) -> None:
    """The job may or may not have changed SAP; only a lookup in SAP can tell."""
    _finish(session, job, UNKNOWN, actor, error=error, evidence_path=evidence)


def need_review(
    session: Session, job: SapJob, error: str, evidence: str | None = None, actor: str = "robot"
) -> None:
    _finish(session, job, NEED_REVIEW, actor, error=error, evidence_path=evidence)


def retry(session: Session, job: SapJob, actor: str) -> None:
    """Put a read job back to PENDING. Write jobs are never retried blindly."""
    if job.kind not in READ_KINDS:
        raise JobStateError("Chỉ việc đọc báo cáo được chạy lại từ web")
    if job.status not in (FAILED, UNKNOWN, NEED_REVIEW):
        raise JobStateError(f"Việc #{job.id} đang ở {job.status}, không chạy lại được")
    clash = session.scalar(
        select(SapJob).where(
            SapJob.dedupe_key == job.dedupe_key,
            SapJob.id != job.id,
            SapJob.status.in_(ACTIVE_STATUSES),
        )
    )
    if clash is not None:
        raise JobStateError(f"Việc #{clash.id} cùng nội dung đang mở")
    job.status = PENDING
    job.finished_at = None
    session.flush()
    states.log_event(session, actor, "sap_job_retry", detail=_brief(job))


def supersede_checks(session: Session, actor: str) -> int:
    """Close the connection checks still waiting, so a new click is not blocked by an old one.

    With the robot off a check can wait for a long time; the person who clicks again wants a
    fresh check, not the dedupe refusal.
    """
    waiting = session.scalars(
        select(SapJob).where(SapJob.kind == CHECK_CONNECTION, SapJob.status == PENDING)
    ).all()
    for job in waiting:
        job.status = FAILED
        job.error = "Thay bằng lần kiểm tra mới"
        job.finished_at = _now()
        states.log_event(session, actor, "sap_job_failed", detail=_brief(job))
    session.flush()
    return len(waiting)


def requeue_interrupted(session: Session, actor: str = "robot") -> list[SapJob]:
    """At robot start no job can still be running; one left RUNNING was cut off mid-way.

    Read jobs go back to PENDING; any other job becomes UNKNOWN.
    """
    stale = session.scalars(select(SapJob).where(SapJob.status == RUNNING)).all()
    for job in stale:
        if job.kind in READ_KINDS:
            job.status = PENDING
        else:
            job.status = UNKNOWN
            job.error = "Robot dừng giữa chừng khi đang chạy việc này"
            job.finished_at = _now()
        states.log_event(session, actor, "sap_job_interrupted", detail=_brief(job))
    session.flush()
    return list(stale)


def _brief(job: SapJob) -> dict:
    return {
        "job_id": job.id,
        "kind": job.kind,
        "target": f"{job.target_system}/{job.target_client}",
        "status": job.status,
    }


# ---------------------------------------------------------------- stop switch


def control(session: Session, *, lock: bool = False) -> RobotControl:
    stmt = select(RobotControl).where(RobotControl.id == 1)
    if lock:
        stmt = stmt.with_for_update()
    row = session.scalar(stmt)
    if row is None:  # the migration inserts it; recreate if it was deleted
        row = RobotControl(id=1, paused=False, consecutive_failures=0)
        session.add(row)
        session.flush()
    return row


def pause(session: Session, actor: str, reason: str) -> None:
    row = control(session, lock=True)
    row.paused = True
    row.paused_reason = reason
    row.changed_by = actor
    row.changed_at = _now()
    session.flush()
    states.log_event(session, actor, "robot_paused", detail={"reason": reason})


def resume(session: Session, actor: str) -> None:
    row = control(session, lock=True)
    row.paused = False
    row.paused_reason = None
    row.consecutive_failures = 0
    row.changed_by = actor
    row.changed_at = _now()
    session.flush()
    states.log_event(session, actor, "robot_resumed")


def record_outcome(session: Session, ok: bool, max_failures: int) -> bool:
    """Count consecutive failures; pause the robot at the threshold. Returns True if it paused."""
    row = control(session, lock=True)
    if ok:
        row.consecutive_failures = 0
        session.flush()
        return False
    row.consecutive_failures += 1
    session.flush()
    if row.consecutive_failures >= max_failures and not row.paused:
        pause(session, "robot", f"{row.consecutive_failures} việc lỗi liên tiếp")
        return True
    return False
