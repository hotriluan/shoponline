import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from shoponline.config import Settings
from shoponline.db.models import (
    AccountingRun,
    AccountingRunRead,
    AccountingRunSource,
    AccountingSentDelivery,
    CustomerInfo,
    EventLog,
    GeneratedFile,
    ImportBatch,
    OrderBatch,
    SalesHistoryExported,
    SalesHistoryFileOrder,
    SalesOrder,
    SapJob,
)
from shoponline.domain import states
from shoponline.maintenance import retention
from tests.shop_codes import SHOP

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
OLD = NOW - timedelta(days=91)
RECENT = NOW - timedelta(days=89)
SPENT = NOW - timedelta(hours=2)  # older than the sweep's one-hour grace
KEEP_DAYS = 7  # evidence_keep_days


def _settings(tmp_path):
    return Settings(database_url="unused", secret_key="s" * 40, data_dir=tmp_path / "data")


def _customer(db, platform, order_id, updated_at, status=None, batch=None, do_number=None):
    if status is not None:
        db.add(
            SalesOrder(
                platform=platform,
                shop_code=SHOP[platform],
                platform_order_id=order_id,
                order_batch_id=batch.id,
                ordered_at=datetime(2026, 8, 1),
                status=status,
                do_number=do_number,
            )
        )
    info = CustomerInfo(
        platform=platform,
        platform_order_id=order_id,
        customer_name="Khách thử",
        address="Địa chỉ thử",
    )
    db.add(info)
    db.flush()
    info.updated_at = updated_at  # set after insert: onupdate would otherwise overwrite it
    db.flush()
    return info


def _batch(db):
    batch = OrderBatch(
        platform="SHOPEE", processing_date=date(2026, 8, 1), gi_date=date(2026, 8, 3)
    )
    db.add(batch)
    db.flush()
    return batch


def _generated(db, path, kind):
    record = GeneratedFile(
        kind=kind, file_name=path.name, stored_path=str(path), sha256="0" * 64, created_by="t"
    )
    db.add(record)
    db.flush()
    return record


def _exported(db, *order_ids, record=None):
    """Record the orders as pasted into the Shop Online history file."""
    record = record or _generated(db, Path("h"), "sales_history")
    for order_id in order_ids:
        order = db.scalar(select(SalesOrder).where(SalesOrder.platform_order_id == order_id))
        db.add(
            SalesHistoryExported(
                sales_order_id=order.id, generated_file_id=record.id, confirmed_by="t"
            )
        )
    db.flush()


def _file(path, mtime):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    os.utime(path, (mtime.timestamp(), mtime.timestamp()))
    return path


def _upload(db, path, kind="zrsd004", by="admin", imported_at=None):
    batch = ImportBatch(
        kind=kind, file_name=path.name, sha256="1" * 64, stored_path=str(path), imported_by=by
    )
    db.add(batch)
    db.flush()
    if imported_at is not None:
        batch.imported_at = imported_at
        db.flush()
    return batch


def _run(db, status):
    run = AccountingRun(status=status, created_by="t")
    if status == "FINALIZED":
        run.finalized_at = NOW - timedelta(days=30)
    db.add(run)
    db.flush()
    return run


def _job(db, status, batch=None):
    job = SapJob(
        kind="READ_ZRSD004",
        target_system="DEV",
        target_client="100",
        dedupe_key=f"k-{status}-{batch.id if batch else 0}",
        status=status,
        created_by="t",
        import_batch_id=batch.id if batch else None,
    )
    db.add(job)
    db.flush()
    return job


def _read(db, run, job):
    db.add(
        AccountingRunRead(
            run_id=run.id, platform="SHOPEE", gi_date=date(2026, 11, 1), sap_job_id=job.id
        )
    )
    db.flush()


def _job_dir(settings, job_id, mtime):
    folder = settings.robot_work_dir / f"job-{job_id}"
    _file(folder / "report.XLSX", mtime)
    os.utime(folder, (mtime.timestamp(), mtime.timestamp()))
    return folder


def _sweep(db, settings):
    return retention.sweep_files(db, settings, KEEP_DAYS, "test", now=NOW)


# ---------------------------------------------------------------- customer data


def test_customer_data_is_never_deleted_whatever_its_age_or_the_order_status(db, tmp_path):
    batch = _batch(db)
    db.add(AccountingSentDelivery(delivery="1900000001"))
    _customer(db, "SHOPEE", "R-DELIVERED", OLD, states.DELIVERED, batch, "1900000001")
    _customer(db, "SHOPEE", "R-CANCELLED", OLD, states.CANCELLED, batch)
    _customer(db, "SHOPEE", "R-NO-ORDER", OLD)  # Lazada-style row without sales_order

    _sweep(db, _settings(tmp_path))

    left = set(db.scalars(select(CustomerInfo.platform_order_id)).all())
    assert left == {"R-DELIVERED", "R-CANCELLED", "R-NO-ORDER"}
    assert not db.scalars(select(EventLog).where(EventLog.kind == "retention_purge")).all()


# ---------------------------------------------------------------- files


def test_sweep_keeps_zrsd004_of_an_open_run_and_hand_uploads_waiting_for_a_run(db, tmp_path):
    settings = _settings(tmp_path)
    up = settings.upload_dir
    open_run, cancelled = _run(db, "OPEN"), _run(db, "CANCELLED")
    _run(db, "FINALIZED")  # 30 days before NOW
    attached = _upload(db, _file(up / "attached.xlsx", SPENT))
    db.add(AccountingRunSource(run_id=open_run.id, import_batch_id=attached.id))
    robot_open = _upload(db, _file(up / "robot-open.xlsx", SPENT), by="robot")
    _read(db, open_run, _job(db, "DONE", robot_open))
    robot_closed = _upload(db, _file(up / "robot-closed.xlsx", SPENT), by="robot")
    _read(db, cancelled, _job(db, "DONE", robot_closed))
    waiting = _upload(db, _file(up / "waiting.xlsx", SPENT))
    too_old = _upload(db, _file(up / "too-old.xlsx", SPENT), imported_at=OLD)
    before_last_run = _upload(
        db, _file(up / "before.xlsx", SPENT), imported_at=NOW - timedelta(days=31)
    )
    zrsd001 = _upload(db, _file(up / "zrsd001.xlsx", SPENT), kind="zrsd001")
    orders = _upload(db, _file(up / "shopee.xlsx", SPENT), kind="shopee_orders")
    orphan = _file(up / "orphan.xlsx", SPENT)  # left by a rejected upload
    fresh = _file(up / "fresh.xlsx", NOW - timedelta(minutes=30))  # row not committed yet

    result = _sweep(db, settings)

    gone = [Path(b.stored_path) for b in (robot_closed, too_old, before_last_run, zrsd001, orders)]
    assert sorted(result.files) == sorted([*gone, orphan])
    assert not any(p.exists() for p in result.files)
    assert all(Path(b.stored_path).exists() for b in (attached, robot_open, waiting))
    assert fresh.exists()


def test_sweep_keeps_run_files_and_history_files_with_unconfirmed_orders(db, tmp_path):
    settings = _settings(tmp_path)
    ex = settings.export_dir
    batch = _batch(db)
    db.add_all(
        SalesOrder(
            platform="SHOPEE",
            shop_code=SHOP["SHOPEE"],
            platform_order_id=order_id,
            order_batch_id=batch.id,
            ordered_at=datetime(2026, 11, 1),
            status=states.DELIVERED,
        )
        for order_id in ("R-1", "R-2")
    )
    db.flush()
    final = _generated(db, _file(ex / "final.xlsx", SPENT), "accounting_file")
    _run(db, "REVOKED").generated_file_id = final.id
    order_file = _generated(db, _file(ex / "order.xlsx", SPENT), "order_file")
    partly = _generated(db, _file(ex / "partly.xlsx", SPENT), "sales_history")
    done = _generated(db, _file(ex / "done.xlsx", SPENT), "sales_history")
    ids = dict(db.execute(select(SalesOrder.platform_order_id, SalesOrder.id)).all())
    db.add_all(
        [
            SalesHistoryFileOrder(generated_file_id=partly.id, sales_order_id=ids["R-1"]),
            SalesHistoryFileOrder(generated_file_id=partly.id, sales_order_id=ids["R-2"]),
            SalesHistoryFileOrder(generated_file_id=done.id, sales_order_id=ids["R-1"]),
        ]
    )
    _exported(db, "R-1", record=done)

    result = _sweep(db, settings)

    assert sorted(result.files) == sorted([Path(order_file.stored_path), Path(done.stored_path)])
    assert Path(final.stored_path).exists() and Path(partly.stored_path).exists()


def test_sweep_keeps_the_folder_of_an_unfinished_job_for_the_evidence_period(db, tmp_path):
    settings = _settings(tmp_path)
    failed = _job_dir(settings, _job(db, "FAILED").id, NOW - timedelta(days=2))
    failed_old = _job_dir(settings, _job(db, "NEED_REVIEW").id, NOW - timedelta(days=8))
    running = _job_dir(settings, _job(db, "RUNNING").id, NOW - timedelta(minutes=5))
    done = _job_dir(settings, _job(db, "DONE").id, SPENT)  # deleting failed when the job ended
    no_job = _job_dir(settings, 999999, SPENT)
    stray = _file(settings.robot_work_dir / "stray.txt", SPENT)
    shot_old = _file(settings.evidence_dir / "job-1-20261101-000000.png", NOW - timedelta(days=8))
    shot_new = _file(settings.evidence_dir / "job-2-20261112-000000.png", NOW - timedelta(days=1))

    result = _sweep(db, settings)

    assert sorted(result.files) == sorted([failed_old, done, no_job, stray])
    assert not any(p.exists() for p in result.files)
    assert failed.is_dir() and running.is_dir()
    assert settings.robot_work_dir.is_dir()
    assert result.screenshots == 1
    assert not shot_old.exists() and shot_new.exists()
    event = db.scalars(select(EventLog).where(EventLog.kind == "retention_files")).one()
    assert json.loads(event.detail) == {"files": 4, "screenshots": 1}


def test_discard_unused_deletes_only_what_no_rule_keeps(db, tmp_path):
    settings = _settings(tmp_path)
    up = settings.upload_dir
    open_run, finalized = _run(db, "OPEN"), _run(db, "FINALIZED")
    # Files are named by content: the same file imported twice, into a closed and an open run.
    shared = _file(up / "shared.xlsx", NOW)
    for run in (open_run, finalized):
        batch = _upload(db, shared)
        db.add(AccountingRunSource(run_id=run.id, import_batch_id=batch.id))
    spent = _upload(db, _file(up / "zrsd001.xlsx", NOW), kind="zrsd001")

    removed = retention.discard_unused(db, settings, [shared, spent.stored_path, None])

    assert removed == [Path(spent.stored_path)]
    assert shared.exists()
    assert retention.discard_unused(db, settings, [None]) == []


def test_discard_unused_never_deletes_outside_the_stored_folders(db, tmp_path):
    settings = _settings(tmp_path)
    elsewhere = _upload(db, _file(tmp_path / "elsewhere.xlsx", NOW), kind="zrsd001")

    assert retention.discard_unused(db, settings, [elsewhere.stored_path]) == []
    assert Path(elsewhere.stored_path).exists()


def test_sweep_keeps_every_accounting_file_even_one_no_run_points_to(db, tmp_path):
    settings = _settings(tmp_path)
    ex = settings.export_dir
    before_runs = _generated(db, _file(ex / "old-final.xlsx", SPENT), "accounting_file")
    by_cancelled_run = _generated(db, _file(ex / "cancelled.xlsx", SPENT), "accounting_file")
    _run(db, "CANCELLED").generated_file_id = by_cancelled_run.id
    order_file = _generated(db, _file(ex / "order.xlsx", SPENT), "order_file")

    result = _sweep(db, settings)

    assert result.files == [Path(order_file.stored_path)]
    assert Path(before_runs.stored_path).exists() and Path(by_cancelled_run.stored_path).exists()


def test_sweep_refuses_when_a_stored_path_is_outside_the_data_folder(db, tmp_path):
    settings = _settings(tmp_path)
    elsewhere = _file(tmp_path / "other-machine" / "uploads" / "a.xlsx", SPENT)
    _upload(db, elsewhere, kind="zrsd004")
    stray = _file(settings.upload_dir / "stray.xlsx", SPENT)

    with pytest.raises(retention.ForeignStoredPaths):
        _sweep(db, settings)

    assert stray.exists() and elsewhere.exists()


def test_sweep_skips_a_file_that_vanishes_between_listing_and_stat(db, tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    ghost = _file(settings.upload_dir / "ghost.xlsx", SPENT)
    other = _file(settings.upload_dir / "other.xlsx", SPENT)
    real_stat = Path.stat

    def stat(self, *args, **kwargs):
        if self.name == "ghost.xlsx":
            raise FileNotFoundError(str(self))
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)

    result = _sweep(db, settings)

    assert result.files == [other]
    assert ghost.exists()


def test_sweep_never_deletes_a_file_a_sales_return_points_to_whatever_its_kind(db, tmp_path):
    from tests.returns import factory

    settings = _settings(tmp_path)
    ex = settings.export_dir
    word = _generated(db, _file(ex / "bbdc.docx", SPENT), "legacy_kind")
    sheet = _generated(db, _file(ex / "rrg.xlsx", SPENT), "invoice_adjustment")
    stray = _generated(db, _file(ex / "stray.xlsx", SPENT), "order_file")
    made = factory.sales_return(db, factory.delivered_order(db), year=2026, seq=80)
    made.docx_file_id, made.xlsx_file_id = word.id, sheet.id
    db.flush()

    result = _sweep(db, settings)

    assert result.files == [Path(stray.stored_path)]
    assert Path(word.stored_path).exists() and Path(sheet.stored_path).exists()


def test_a_voided_sales_return_keeps_its_files_too(db, tmp_path):
    from tests.returns import factory

    settings = _settings(tmp_path)
    word = _generated(db, _file(settings.export_dir / "bbdc.docx", SPENT), "invoice_adjustment")
    made = factory.sales_return(db, factory.delivered_order(db), year=2026, seq=80, status="VOID")
    made.docx_file_id = word.id
    db.flush()

    assert _sweep(db, settings).files == []
    assert Path(word.stored_path).exists()
