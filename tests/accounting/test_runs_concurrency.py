"""Two real connections: one run opened, one run finalized, never twice."""

import threading
import time
from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shoponline.accounting import runs
from shoponline.config import Settings
from shoponline.db.models import AccountingRun, AccountingRunRead, AccountingSentDelivery, SapJob
from tests.accounting.scenario import (
    QA,
    TODAY,
    delivery_row,
    finish_job,
    make_batch,
    make_order,
    make_source,
)


@pytest.fixture
def old_cutoff():
    """These tests commit for real; the `committed` fixture sets the cutoff instead."""


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url="unused", secret_key="s" * 40, data_dir=tmp_path / "data")


def _waiting_order(engine):
    with Session(engine) as session:
        make_order(session, make_batch(session, gi=date(2026, 11, 12)), "A1", "210000001")
        session.commit()


def _in_thread(work):
    outcome = {}

    def target():
        try:
            outcome["value"] = work()
        except Exception as exc:  # handed back to the test thread
            outcome["error"] = exc

    thread = threading.Thread(target=target)
    thread.start()
    return thread, outcome


def test_two_connections_starting_a_run_share_one_run(committed):
    _waiting_order(committed)
    a, b = Session(committed), Session(committed)
    try:
        first = runs.start_run(a, QA, "a", TODAY)  # not committed yet: holds the open-run slot

        def second():
            run = runs.start_run(b, QA, "b", TODAY)
            b.commit()
            return run.id

        thread, outcome = _in_thread(second)
        time.sleep(0.5)  # the second connection waits on the unique index
        first_id = first.id
        a.commit()
        thread.join(15)

        assert "error" not in outcome, outcome.get("error")
        assert outcome["value"] == first_id
    finally:
        a.close()
        b.close()
    with Session(committed) as check:
        assert check.scalar(select(func.count()).select_from(AccountingRun)) == 1
        assert check.scalar(select(func.count()).select_from(SapJob)) == 2  # two days, queued once


def test_two_connections_finalizing_record_the_deliveries_once(committed, tmp_path, settings):
    _waiting_order(committed)
    with Session(committed) as setup:
        run = runs.start_run(setup, QA, "admin", TODAY)
        reads = setup.scalars(
            select(AccountingRunRead)
            .where(AccountingRunRead.run_id == run.id)
            .order_by(AccountingRunRead.gi_date)
        ).all()
        record = make_source(setup, tmp_path / "a.xlsx", [delivery_row("1900000001", "210000001")])
        finish_job(setup, reads[0].sap_job_id, record=record)
        finish_job(setup, reads[1].sap_job_id, no_data=True)
        run_id = run.id
        fingerprint = runs.reconcile(setup, run, TODAY).fingerprint
        setup.commit()

    a, b = Session(committed), Session(committed)
    try:
        runs.finalize(
            a,
            settings,
            run_id,
            "a",
            fingerprint,
            allow_partial=False,
            ack_missing=False,
            today=TODAY,
        )  # holds the run row until it commits

        def second():
            return runs.finalize(
                b,
                settings,
                run_id,
                "b",
                fingerprint,
                allow_partial=False,
                ack_missing=False,
                today=TODAY,
            )

        thread, outcome = _in_thread(second)
        time.sleep(0.5)
        a.commit()
        thread.join(15)

        assert isinstance(outcome.get("error"), runs.RunNotOpen), outcome
    finally:
        a.close()
        b.close()
    with Session(committed) as check:
        sent = check.scalars(select(AccountingSentDelivery)).all()
        assert [(d.delivery, d.run_id) for d in sent] == [("1900000001", run_id)]
        assert len(list(settings.export_dir.glob("*.xlsx"))) == 1
