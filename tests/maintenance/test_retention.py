import os
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from shoponline.config import Settings
from shoponline.db.models import (
    AccountingRun,
    AccountingRunSource,
    AccountingSentDelivery,
    CustomerInfo,
    EventLog,
    GeneratedFile,
    ImportBatch,
    OrderBatch,
    SalesOrder,
)
from shoponline.domain import states
from shoponline.maintenance import retention

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
OLD = NOW - timedelta(days=91)
RECENT = NOW - timedelta(days=89)


def _settings(tmp_path):
    return Settings(database_url="unused", secret_key="s" * 40, data_dir=tmp_path / "data")


def _customer(db, platform, order_id, updated_at, status=None, batch=None, do_number=None):
    if status is not None:
        db.add(
            SalesOrder(
                platform=platform,
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


def _file(path, mtime):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    os.utime(path, (mtime.timestamp(), mtime.timestamp()))
    return path


def test_erases_old_customer_data_only_for_orders_sent_to_accounting(db, tmp_path):
    batch = _batch(db)
    db.add_all(
        AccountingSentDelivery(delivery=d) for d in ("1900000001", "1900000002")
    )
    _customer(db, "SHOPEE", "R-DELIVERED", OLD, states.DELIVERED, batch, "1900000001")
    _customer(db, "SHOPEE", "R-CANCELLED", OLD, states.CANCELLED, batch)
    _customer(db, "SHOPEE", "R-LINKED", OLD, states.SO_LINKED, batch)  # no DO yet
    _customer(db, "SHOPEE", "R-NOT-SENT", OLD, states.DELIVERED, batch, "1900000077")
    _customer(db, "SHOPEE", "R-RECENT", RECENT, states.DELIVERED, batch, "1900000002")
    _customer(db, "SHOPEE", "R-NO-ORDER", OLD)  # Lazada-style row without sales_order

    plan = retention.find_expired(db, _settings(tmp_path), now=NOW)

    assert sorted(o for _, o in plan.customer_orders) == [
        "R-CANCELLED",
        "R-DELIVERED",
        "R-NO-ORDER",
    ]
    assert sorted(plan.held_orders) == [("SHOPEE", "R-LINKED"), ("SHOPEE", "R-NOT-SENT")]

    retention.apply(db, plan, "test")
    db.flush()
    left = set(db.scalars(select(CustomerInfo.platform_order_id)).all())
    assert {"R-LINKED", "R-NOT-SENT", "R-RECENT"} <= left
    assert not left & {"R-DELIVERED", "R-CANCELLED", "R-NO-ORDER"}
    # Orders stay; only personal data goes.
    assert db.scalar(select(SalesOrder).where(SalesOrder.platform_order_id == "R-DELIVERED"))
    event = db.scalars(select(EventLog).where(EventLog.kind == "retention_purge")).one()
    assert "Khách thử" not in (event.detail or "")


def test_list_mode_changes_nothing(db, tmp_path):
    settings = _settings(tmp_path)
    _customer(db, "SHOPEE", "R-OLD", OLD)
    old_file = _file(settings.upload_dir / "a.xlsx", OLD)

    plan = retention.find_expired(db, settings, now=NOW)

    assert plan.customer_orders == [("SHOPEE", "R-OLD")]
    assert plan.files == [old_file]
    assert old_file.exists()
    assert db.scalar(select(CustomerInfo).where(CustomerInfo.platform_order_id == "R-OLD"))


def test_deletes_old_files_and_empty_robot_folders(db, tmp_path):
    settings = _settings(tmp_path)
    old_upload = _file(settings.upload_dir / "old.xlsx", OLD)
    new_upload = _file(settings.upload_dir / "new.xlsx", RECENT)
    old_export = _file(settings.export_dir / "old-accounting_file.xlsx", OLD)
    old_work = _file(settings.robot_work_dir / "job-7" / "zrsd004-7.XLSX", OLD)
    evidence = _file(settings.evidence_dir / "job-7-x.png", OLD)  # own, shorter period
    running_job = settings.robot_work_dir / "job-8"  # created by the robot, export not saved yet
    running_job.mkdir(parents=True)

    plan = retention.find_expired(db, settings, now=NOW)
    retention.apply(db, plan, "test")
    retention.delete_files(settings, plan)

    assert not old_upload.exists() and not old_export.exists() and not old_work.exists()
    assert not old_work.parent.exists()
    assert running_job.is_dir()
    assert new_upload.exists()
    assert evidence.exists()
    assert settings.robot_work_dir.is_dir()


def test_keeps_finalized_accounting_file_and_sources_of_an_open_run(db, tmp_path):
    settings = _settings(tmp_path)
    final = _file(settings.export_dir / "final.xlsx", OLD)
    draft = _file(settings.export_dir / "other.xlsx", OLD)
    attached = _file(settings.upload_dir / "attached.xlsx", OLD)
    closed_source = _file(settings.upload_dir / "closed.xlsx", OLD)
    record = GeneratedFile(
        kind="accounting_file",
        file_name="x.xlsx",
        stored_path=str(final),
        sha256="0" * 64,
        created_by="t",
    )
    db.add(record)
    db.flush()
    db.add(AccountingRun(status="FINALIZED", created_by="t", generated_file_id=record.id))
    open_run = AccountingRun(status="OPEN", created_by="t")
    closed_run = AccountingRun(status="CANCELLED", created_by="t")
    db.add_all([open_run, closed_run])
    in_open = ImportBatch(
        kind="zrsd004", file_name="a", sha256="1" * 64, stored_path=str(attached), imported_by="t"
    )
    in_closed = ImportBatch(
        kind="zrsd004",
        file_name="b",
        sha256="2" * 64,
        stored_path=str(closed_source),
        imported_by="t",
    )
    db.add_all([in_open, in_closed])
    db.flush()
    db.add_all(
        [
            AccountingRunSource(run_id=open_run.id, import_batch_id=in_open.id),
            AccountingRunSource(run_id=closed_run.id, import_batch_id=in_closed.id),
        ]
    )
    db.flush()

    plan = retention.find_expired(db, settings, now=NOW)

    assert sorted(plan.files) == sorted([draft, closed_source])
