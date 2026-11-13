import json
from datetime import date, timedelta

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from shoponline.accounting import ledger, runs
from shoponline.config import Settings
from shoponline.db.models import (
    AccountingRun,
    AccountingRunRead,
    AccountingSentDelivery,
    EventLog,
    GeneratedFile,
    SapJob,
)
from shoponline.domain import states
from shoponline.importers.excel_table import FileRejected
from shoponline.sapjobs import queue
from tests.accounting.scenario import (
    OTHER,
    QA,
    SHOPEE,
    TODAY,
    delivery_row,
    finish_job,
    make_batch,
    make_order,
    make_source,
)


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url="unused", secret_key="s" * 40, data_dir=tmp_path / "data")


def _pairs(db, today=TODAY):
    return runs.due_pairs(db, today).pairs


def _reads(db, run):
    return list(
        db.scalars(
            select(AccountingRunRead)
            .where(AccountingRunRead.run_id == run.id)
            .order_by(AccountingRunRead.platform, AccountingRunRead.gi_date)
        )
    )


# ---------------------------------------------------------------- due_pairs


def test_every_day_from_the_oldest_waiting_order_to_today(db):
    make_order(db, make_batch(db, gi=date(2026, 11, 11)), "A1", "210000001")
    make_order(db, make_batch(db, gi=date(2026, 11, 12), processing=date(2026, 11, 10)), "A2", "2")

    assert _pairs(db) == [("SHOPEE", date(2026, 11, d)) for d in (11, 12, 13)]


def test_each_platform_has_its_own_window_and_idle_platforms_have_none(db):
    make_order(db, make_batch(db, "SHOPEE", gi=date(2026, 11, 12)), "A1", "210000001")
    make_order(db, make_batch(db, "TIKTOK", gi=date(2026, 11, 13)), "T1", "210000002")

    assert _pairs(db) == [
        ("SHOPEE", date(2026, 11, 12)),
        ("SHOPEE", date(2026, 11, 13)),
        ("TIKTOK", date(2026, 11, 13)),
    ]


def test_nothing_waiting_gives_no_pairs(db):
    assert _pairs(db) == []


def test_orders_sent_or_not_due_yet_do_not_wait(db):
    batch = make_batch(db, gi=date(2026, 11, 12))
    future = make_batch(db, gi=date(2026, 11, 14), processing=date(2026, 11, 12))
    make_order(db, future, "F1", "210000009")
    make_order(db, batch, "D1", "210000001", states.DELIVERED, "1900000001")
    ledger.add_baseline(db, ["1900000001"], "t")

    assert _pairs(db) == []

    make_order(db, batch, "D2", "210000002", states.DELIVERED, "1900000002")  # DO not sent yet
    assert _pairs(db) == [("SHOPEE", date(2026, 11, 12)), ("SHOPEE", date(2026, 11, 13))]


def test_window_stops_31_days_back_and_warns(db):
    old = TODAY - timedelta(days=40)
    make_order(db, make_batch(db, gi=old, processing=old - timedelta(days=1)), "A1", "210000001")

    due = runs.due_pairs(db, TODAY)

    assert due.pairs[0] == ("SHOPEE", TODAY - timedelta(days=31))
    assert due.pairs[-1] == ("SHOPEE", TODAY)
    assert len(due.pairs) == 32
    assert "SHOPEE" in due.warnings[0] and "1 đơn" in due.warnings[0]


def test_pairs_of_a_revoked_run_return_until_a_later_run_holds_them(db):
    reads = [("SHOPEE", date(2026, 11, 9))]
    revoked = AccountingRun(status=ledger.REVOKED, created_by="t")
    db.add(revoked)
    db.flush()
    db.add(AccountingRunRead(run_id=revoked.id, platform=reads[0][0], gi_date=reads[0][1]))
    db.flush()

    assert _pairs(db) == reads

    later = AccountingRun(status=ledger.FINALIZED, created_by="t")
    db.add(later)
    db.flush()
    db.add(AccountingRunRead(run_id=later.id, platform=reads[0][0], gi_date=reads[0][1]))
    db.flush()
    assert _pairs(db) == []


# ---------------------------------------------------------------- start_run


def _waiting(db):
    return make_order(db, make_batch(db, gi=date(2026, 11, 12)), "A1", "210000001")


def test_start_run_queues_one_job_per_pair(db):
    _waiting(db)
    run = runs.start_run(db, QA, "admin", TODAY)

    reads = _reads(db, run)
    assert [r.gi_date for r in reads] == [date(2026, 11, 12), date(2026, 11, 13)]
    jobs = [db.get(SapJob, r.sap_job_id) for r in reads]
    assert all(j.status == queue.PENDING and j.kind == queue.READ_ZRSD004 for j in jobs)
    assert queue.payload_of(jobs[0])["sold_to"] == SHOPEE


def test_second_start_returns_the_open_run_without_new_jobs(db):
    _waiting(db)
    first = runs.start_run(db, QA, "admin", TODAY)
    before = db.scalars(select(SapJob.id)).all()

    again = runs.start_run(db, QA, "admin", TODAY)

    assert again.id == first.id
    assert db.scalars(select(SapJob.id)).all() == before


def test_nothing_waiting_refuses_to_start(db):
    with pytest.raises(runs.NothingDue):
        runs.start_run(db, QA, "admin", TODAY)


def test_without_a_verified_target_the_reads_have_no_jobs(db):
    _waiting(db)
    run = runs.start_run(db, None, "admin", TODAY)
    assert [r.sap_job_id for r in _reads(db, run)] == [None, None]
    assert {s.state for s in runs.run_status(db, run)} == {runs.NO_JOB}


def test_a_waiting_job_for_this_target_is_taken_over(db):
    _waiting(db)
    old = queue.enqueue(db, queue.READ_ZRSD004, QA, "read_zrsd004:SHOPEE:2026-11-12", {}, "x")

    run = runs.start_run(db, QA, "admin", TODAY)

    assert _reads(db, run)[0].sap_job_id == old.id and old.status == queue.PENDING


@pytest.mark.parametrize("old_status", ["UNKNOWN", "NEED_REVIEW", "WRONG_TARGET"])
def test_other_open_jobs_are_closed_and_replaced(db, old_status):
    _waiting(db)
    target = OTHER if old_status == "WRONG_TARGET" else QA
    old = queue.enqueue(db, queue.READ_ZRSD004, target, "read_zrsd004:SHOPEE:2026-11-12", {}, "x")
    if old_status != "WRONG_TARGET":
        old.status = old_status
        db.flush()

    run = runs.start_run(db, QA, "admin", TODAY)

    new_id = _reads(db, run)[0].sap_job_id
    assert new_id != old.id
    db.refresh(old)
    assert old.status == queue.FAILED and "đợt gửi kế toán" in old.error
    assert db.get(SapJob, new_id).status == queue.PENDING


def test_sync_adds_pairs_that_became_due(db):
    _waiting(db)
    run = runs.start_run(db, QA, "admin", TODAY)
    make_order(db, make_batch(db, "TIKTOK", gi=date(2026, 11, 13)), "T1", "210000002")

    assert runs.sync_pairs(db, run, "admin", QA, TODAY) == 1
    assert ("TIKTOK", date(2026, 11, 13)) in {(r.platform, r.gi_date) for r in _reads(db, run)}
    assert runs.sync_pairs(db, run, "admin", QA, TODAY) == 0


# ---------------------------------------------------------------- status and reading again


def test_status_of_each_kind_of_job(db, tmp_path):
    batch = make_batch(db, gi=date(2026, 11, 10), processing=date(2026, 11, 9))
    make_order(db, batch, "A1", "210000001")
    run = runs.start_run(db, QA, "admin", TODAY)
    reads = _reads(db, run)  # 10, 11, 12, 13 November
    record = make_source(db, tmp_path / "a.xlsx", [delivery_row("1900000001", "210000001")])
    finish_job(db, reads[0].sap_job_id, record=record)
    finish_job(db, reads[1].sap_job_id, no_data=True)
    finish_job(db, reads[2].sap_job_id, status=queue.FAILED, error="SAP lỗi")
    # reads[3] stays PENDING

    states_by_day = {s.read.gi_date.day: s for s in runs.run_status(db, run)}

    assert states_by_day[10].state == runs.HAS_DATA
    assert states_by_day[11].state == runs.NO_DATA
    assert states_by_day[12].state == runs.ERROR and "SAP lỗi" in states_by_day[12].detail
    assert states_by_day[13].state == runs.READING

    (tmp_path / "a.xlsx").unlink()
    assert runs.run_status(db, run)[0].state == runs.MISSING_FILE


def test_retry_puts_a_failed_job_back_and_replaces_a_finished_one(db):
    _waiting(db)
    run = runs.start_run(db, QA, "admin", TODAY)
    failed, no_data = _reads(db, run)
    failed_job = finish_job(db, failed.sap_job_id, status=queue.FAILED, error="x")
    finish_job(db, no_data.sap_job_id, no_data=True)

    assert runs.retry_read(db, run, failed, "admin", QA).id == failed_job.id
    assert failed_job.status == queue.PENDING

    finished_id = no_data.sap_job_id
    new = runs.retry_read(db, run, no_data, "admin", QA)
    assert new.id != finished_id and no_data.sap_job_id == new.id
    assert new.status == queue.PENDING

    with pytest.raises(queue.JobStateError):
        runs.retry_read(db, run, failed, "admin", QA)  # now waiting


def test_retry_refuses_a_closed_run(db):
    _waiting(db)
    run = runs.start_run(db, QA, "admin", TODAY)
    read = _reads(db, run)[0]
    runs.cancel_run(db, run.id, "admin")
    with pytest.raises(runs.RunNotOpen):
        runs.retry_read(db, run, read, "admin", QA)


def test_an_uploaded_file_covers_its_pair(db, tmp_path):
    _waiting(db)
    run = runs.start_run(db, QA, "admin", TODAY)
    finish_job(db, _reads(db, run)[0].sap_job_id, status=queue.FAILED, error="x")
    upload = make_source(
        db, tmp_path / "up.xlsx", [delivery_row("1900000001", "210000001")], imported_by="luan"
    )

    assert upload in runs.available_uploads(db)
    runs.attach_upload(db, run, upload, "admin")

    first = runs.run_status(db, run)[0]
    assert first.state == runs.HAS_DATA and "tải lên" in first.detail
    assert upload not in runs.available_uploads(db)
    assert runs.reconcile(db, run, TODAY).source_ids == [upload.id]


def test_robot_files_are_not_offered_as_uploads(db, tmp_path):
    make_source(db, tmp_path / "r.xlsx", [delivery_row("1900000001", "210000001")])
    assert runs.available_uploads(db) == []


# ---------------------------------------------------------------- reconcile and finalize


def _ready(db, tmp_path, *, extra_orders=()):
    """An order with its SO, a run whose two reads are done: one with the DO, one without data."""
    order = _waiting(db)
    for order_id, so in extra_orders:
        make_order(
            db, make_batch(db, gi=date(2026, 11, 12), processing=date(2026, 11, 9)), order_id, so
        )
    run = runs.start_run(db, QA, "admin", TODAY)
    first, second = _reads(db, run)
    record = make_source(db, tmp_path / "a.xlsx", [delivery_row("1900000001", "210000001")])
    finish_job(db, first.sap_job_id, record=record)
    finish_job(db, second.sap_job_id, no_data=True)
    return run, order


def _finalize(db, settings, run, rec=None, **kwargs):
    rec = rec or runs.reconcile(db, run, TODAY)
    options = {"allow_partial": False, "ack_missing": False, "today": TODAY}
    options.update(kwargs)
    return runs.finalize(db, settings, run.id, "admin", rec.fingerprint, **options)


def test_reconcile_of_a_complete_run(db, tmp_path):
    run, order = _ready(db, tmp_path)
    rec = runs.reconcile(db, run, TODAY)

    assert rec.deliveries == {"1900000001"}
    assert rec.missing == [] and rec.unknown == [] and rec.incomplete == []
    assert order.status == states.DELIVERED  # read, but its DO is not sent yet
    assert rec.summary == "Web đáng ra có 1 đơn, file có 1 DO, thiếu 0"
    assert rec.fingerprint == runs.reconcile(db, run, TODAY).fingerprint


def test_an_order_without_a_do_is_missing(db, tmp_path):
    run, _ = _ready(db, tmp_path, extra_orders=[("A2", "210000002")])
    rec = runs.reconcile(db, run, TODAY)

    assert [(m.platform, m.order_id, m.so_number) for m in rec.missing] == [
        ("SHOPEE", "A2", "210000002")
    ]
    assert rec.summary == "Web đáng ra có 2 đơn, file có 1 DO, thiếu 1"


def test_a_delivery_not_issued_yet_is_named_in_the_missing_list(db, tmp_path):
    order = _waiting(db)
    run = runs.start_run(db, QA, "admin", TODAY)
    first, second = _reads(db, run)
    unissued = delivery_row("1900000001", "210000001")
    unissued["Total Movement Goods Stat"] = "A"
    record = make_source(db, tmp_path / "a.xlsx", [unissued], ingest=False)
    finish_job(db, first.sap_job_id, record=record)
    finish_job(db, second.sap_job_id, no_data=True)

    rec = runs.reconcile(db, run, TODAY)

    assert rec.merged is None
    assert [m.order_id for m in rec.missing] == [order.platform_order_id]


def test_a_delivery_of_no_web_order_is_reported_as_unknown(db, tmp_path):
    run, _ = _ready(db, tmp_path)
    record = make_source(
        db, tmp_path / "b.xlsx", [delivery_row("1900000777", "299999999")], imported_by="luan"
    )
    runs.attach_upload(db, run, record, "admin")

    rec = runs.reconcile(db, run, TODAY)

    assert rec.unknown == [("1900000777", "299999999")]


def test_finalize_records_the_deliveries_and_closes_the_run(db, tmp_path, settings):
    run, order = _ready(db, tmp_path)

    record = _finalize(db, settings, run)

    assert run.status == ledger.FINALIZED and run.generated_file_id == record.id
    assert ledger.sent_deliveries(db) >= {"1900000001"}
    assert db.get(AccountingSentDelivery, "1900000001").run_id == run.id
    sheet = load_workbook(record.stored_path).worksheets[0]
    assert "1900000001" in {c.value for row in sheet.iter_rows() for c in row}
    event = db.scalars(select(EventLog).where(EventLog.kind == "accounting_run_finalized")).one()
    assert json.loads(event.detail)["deliveries"] == 1
    assert run.missing_note is None
    with pytest.raises(runs.NothingDue):
        runs.start_run(db, QA, "admin", TODAY)


def test_finalizing_twice_is_refused(db, tmp_path, settings):
    run, _ = _ready(db, tmp_path)
    rec = runs.reconcile(db, run, TODAY)
    _finalize(db, settings, run, rec)
    with pytest.raises(runs.RunNotOpen):
        _finalize(db, settings, run, rec)
    sent = db.scalars(select(AccountingSentDelivery).where(AccountingSentDelivery.run_id == run.id))
    assert [d.delivery for d in sent] == ["1900000001"]


def test_missing_orders_must_be_acknowledged_and_are_logged(db, tmp_path, settings):
    run, _ = _ready(db, tmp_path, extra_orders=[("A2", "210000002")])
    with pytest.raises(runs.MissingNotAcknowledged):
        _finalize(db, settings, run)
    assert run.status == ledger.OPEN and not ledger.sent_deliveries(db)

    _finalize(db, settings, run, ack_missing=True)

    note = json.loads(run.missing_note)
    assert note["orders"] == ["SHOPEE A2"]
    event = db.scalars(select(EventLog).where(EventLog.kind == "accounting_run_finalized")).one()
    assert json.loads(event.detail)["missing_orders"] == ["SHOPEE A2"]


def test_an_incomplete_read_must_be_accepted_by_name(db, tmp_path, settings):
    run, _ = _ready(db, tmp_path)
    finish_job(db, _reads(db, run)[1].sap_job_id, status=queue.FAILED, error="SAP lỗi")

    with pytest.raises(runs.ReadsIncomplete) as caught:
        _finalize(db, settings, run)
    assert "SHOPEE 13/11/2026" in caught.value.pairs[0]
    assert run.status == ledger.OPEN

    _finalize(db, settings, run, allow_partial=True)

    assert "SHOPEE 13/11/2026" in json.loads(run.missing_note)["pairs"][0]


def test_a_changed_review_is_refused(db, tmp_path, settings):
    run, _ = _ready(db, tmp_path)
    reviewed = runs.reconcile(db, run, TODAY)
    extra = make_source(
        db, tmp_path / "c.xlsx", [delivery_row("1900000888", "210000888")], imported_by="luan"
    )
    runs.attach_upload(db, run, extra, "admin")

    with pytest.raises(runs.StaleReview):
        _finalize(db, settings, run, reviewed)
    assert run.status == ledger.OPEN and not db.scalars(select(GeneratedFile)).all()


def test_nothing_new_changes_nothing(db, tmp_path, settings):
    run, _ = _ready(db, tmp_path)
    ledger.add_baseline(db, ["1900000001"], "t")  # already sent by another way
    rec = runs.reconcile(db, run, TODAY)

    with pytest.raises(FileRejected, match="Không có DO mới"):
        _finalize(db, settings, run, rec)

    assert run.status == ledger.OPEN and not db.scalars(select(GeneratedFile)).all()


def test_draft_is_named_and_stores_nothing(db, tmp_path, settings):
    run, _ = _ready(db, tmp_path)
    before = db.scalars(select(AccountingSentDelivery.delivery)).all()

    draft = runs.draft_file(db, run, TODAY)

    assert draft.file_name == "NHÁP SHOP ONLINE 121126.xlsx"
    assert draft.fingerprint == runs.reconcile(db, run, TODAY).fingerprint
    assert db.scalars(select(AccountingSentDelivery.delivery)).all() == before
    assert not db.scalars(select(GeneratedFile)).all()
    assert not (settings.export_dir).exists()


def test_cancel_leaves_the_ledger_and_allows_a_new_run(db, tmp_path):
    _waiting(db)
    run = runs.start_run(db, QA, "admin", TODAY)
    runs.cancel_run(db, run.id, "admin")
    assert run.status == ledger.CANCELLED
    assert runs.start_run(db, QA, "admin", TODAY).id != run.id
    with pytest.raises(runs.RunNotOpen):
        runs.cancel_run(db, run.id, "admin")


def test_a_revoked_run_makes_its_pairs_due_again(db, tmp_path, settings):
    run, order = _ready(db, tmp_path)
    _finalize(db, settings, run)
    assert runs.due_pairs(db, TODAY).pairs == []

    runs.revoke_run(db, run.id, "admin", apply=True)

    assert not ledger.sent_deliveries(db) & {"1900000001"}
    new = runs.start_run(db, QA, "admin", TODAY)
    assert {(r.platform, r.gi_date) for r in _reads(db, new)} == {
        ("SHOPEE", date(2026, 11, 12)),
        ("SHOPEE", date(2026, 11, 13)),
    }
    assert order.status == states.DELIVERED


def test_cutoff_keeps_old_deliveries_out_and_the_order_shows_as_missing(db, tmp_path):
    run, _ = _ready(db, tmp_path)
    ledger.set_cutoff(db, date(2026, 11, 12), "t")

    rec = runs.reconcile(db, run, TODAY)

    assert rec.merged is None  # the only delivery is on the cutoff day
    assert [m.order_id for m in rec.missing] == ["A1"]
