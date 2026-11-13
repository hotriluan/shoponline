"""Building blocks for accounting run tests: platform orders, robot reads and zrsd004 files."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from shoponline.db.models import CustomerInfo, ImportBatch, OrderBatch, SalesOrder, SapJob
from shoponline.domain import states
from shoponline.sapjobs import queue
from shoponline.sapjobs.queue import SapTarget
from tests.fixtures.build_fixtures import zrsd004_file, zrsd004_row

TODAY = date(2026, 11, 13)
QA = SapTarget("QAS", "300")
OTHER = SapTarget("PRD", "100")
SHOPEE = "1200001145"
TIKTOK = "1200001146"


def make_batch(
    session: Session,
    platform: str = "SHOPEE",
    processing: date = date(2026, 11, 11),
    gi: date = date(2026, 11, 12),
) -> OrderBatch:
    batch = OrderBatch(platform=platform, processing_date=processing, gi_date=gi)
    session.add(batch)
    session.flush()
    return batch


def make_order(
    session: Session,
    batch: OrderBatch,
    order_id: str,
    so: str | None = None,
    status: str = states.SO_LINKED,
    do: str | None = None,
    *,
    with_customer: bool = True,
) -> SalesOrder:
    order = SalesOrder(
        platform=batch.platform,
        platform_order_id=order_id,
        order_batch_id=batch.id,
        ordered_at=datetime(2026, 11, 11, 8),
        status=status,
        so_number=so,
        do_number=do,
    )
    session.add(order)
    if with_customer:
        session.add(
            CustomerInfo(
                platform=batch.platform,
                platform_order_id=order_id,
                customer_name=f"Khách {order_id}",
                address=f"Địa chỉ {order_id}",
            )
        )
    session.flush()
    return order


def make_source(
    session: Session,
    path: Path,
    rows: list[dict],
    *,
    imported_by: str = "robot",
    ingest: bool = True,
) -> ImportBatch:
    """Write a zrsd004 file and store it as an import; the robot marks orders delivered too."""
    from shoponline.reconcile.report_ingest import ingest_zrsd004

    zrsd004_file(path, rows)
    record = ImportBatch(
        kind="zrsd004",
        file_name=path.name,
        sha256=path.stem.ljust(64, "0")[:64],
        stored_path=str(path),
        imported_by=imported_by,
    )
    if ingest:
        ingest_zrsd004(session, record, imported_by)
    else:
        session.add(record)
        session.flush()
    return record


def delivery_row(delivery: str, so: str, *, sold_to: str = SHOPEE, gi: date = date(2026, 11, 12)):
    return zrsd004_row(delivery, so, "100000001", sold_to=sold_to, gi_date=gi)


def finish_job(
    session: Session,
    job_id: int,
    *,
    record: ImportBatch | None = None,
    no_data: bool = False,
    status: str = queue.DONE,
    error: str | None = None,
) -> SapJob:
    """Put a queued job into a final state, as the robot would."""
    job = session.get(SapJob, job_id)
    job.status = status
    job.finished_at = datetime.now(UTC)
    job.error = error
    if record is not None:
        job.import_batch_id = record.id
        job.result = json.dumps({"rows": 1, "delivered": 1, "warnings": []})
    elif no_data:
        job.result = json.dumps({"rows": 0, "delivered": 0, "warnings": [], "no_data": True})
    session.flush()
    return job
