import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from shoponline.db.models import EventLog, SapJob
from shoponline.sapjobs import queue
from shoponline.sapjobs.queue import SapTarget

QA = SapTarget("QAS", "300")


def _enqueue(db, key="read_zrsd001:batch:1", kind=queue.READ_ZRSD001):
    return queue.enqueue(db, kind, QA, key, {"batch_id": 1}, "admin")


def test_same_key_is_refused_while_the_first_job_is_open(db):
    first = _enqueue(db)
    with pytest.raises(queue.DuplicateJob, match=f"#{first.id}"):
        _enqueue(db)
    job = queue.claim(db)
    queue.complete(db, job, {"new": 1})
    assert _enqueue(db).id != first.id  # a finished job no longer blocks a new read


def test_unique_index_blocks_a_concurrent_duplicate(db):
    _enqueue(db)
    db.add(
        SapJob(
            kind=queue.READ_ZRSD001,
            target_system="QAS",
            target_client="300",
            dedupe_key="read_zrsd001:batch:1",
            payload="{}",
            status=queue.PENDING,
            created_by="x",
        )
    )
    with pytest.raises(Exception, match="uq_sap_job_active_key"):
        db.flush()


def test_two_robots_never_claim_the_same_job(db_engine):
    """Two sessions on separate connections, both inside an open transaction."""
    with Session(db_engine) as setup:
        ids = [
            queue.enqueue(setup, queue.READ_ZRSD004, QA, f"concurrency-{i}", {}, "t").id
            for i in range(2)
        ]
        setup.commit()
    try:
        with Session(db_engine) as a, Session(db_engine) as b:
            job_a = queue.claim(a)  # row lock held until a commits
            job_b = queue.claim(b)
            assert {job_a.id, job_b.id} == set(ids)
            c_job = None
            with Session(db_engine) as c:
                c_job = queue.claim(c)
                c.rollback()
            assert c_job is None  # both rows locked: third claimer skips them
            a.commit()
            b.commit()
    finally:
        with Session(db_engine) as cleanup:
            cleanup.execute(delete(SapJob).where(SapJob.id.in_(ids)))
            cleanup.execute(delete(EventLog).where(EventLog.kind.like("sap_job_%")))
            cleanup.commit()


def test_claim_takes_oldest_and_counts_attempts(db):
    first = _enqueue(db, "k1")
    _enqueue(db, "k2")
    job = queue.claim(db)
    assert job.id == first.id and job.status == queue.RUNNING and job.attempts == 1


def test_finish_requires_running(db):
    job = _enqueue(db)
    with pytest.raises(queue.JobStateError):
        queue.complete(db, job, {})


def test_retry_only_for_failed_read_jobs(db):
    read = _enqueue(db, "r")
    queue.claim(db)
    queue.fail(db, read, "boom")
    queue.retry(db, read, "admin")
    assert read.status == queue.PENDING and read.error == "boom"

    write = _enqueue(db, "w", kind="create_so")
    queue.claim(db)  # read job again (older)
    job = queue.claim(db)
    assert job.id == write.id
    queue.mark_unknown(db, write, "lost session")
    with pytest.raises(queue.JobStateError, match="Chỉ việc đọc"):
        queue.retry(db, write, "admin")


def test_interrupted_jobs_after_restart(db):
    read = _enqueue(db, "r")
    write = _enqueue(db, "w", kind="create_so")
    queue.claim(db)
    queue.claim(db)
    queue.requeue_interrupted(db)
    assert read.status == queue.PENDING
    assert write.status == queue.UNKNOWN  # might have saved in SAP: never re-run blindly


def test_consecutive_failures_pause_and_only_resume_clears(db):
    for _ in range(2):
        assert queue.record_outcome(db, False, max_failures=3) is False
    assert queue.record_outcome(db, True, max_failures=3) is False  # success resets
    for _ in range(2):
        queue.record_outcome(db, False, max_failures=3)
    assert queue.record_outcome(db, False, max_failures=3) is True
    row = queue.control(db)
    assert row.paused and "3 việc lỗi" in row.paused_reason
    queue.resume(db, "admin")
    assert not row.paused and row.consecutive_failures == 0
    kinds = db.scalars(select(EventLog.kind).where(EventLog.kind.like("robot_%"))).all()
    assert kinds == ["robot_paused", "robot_resumed"]
