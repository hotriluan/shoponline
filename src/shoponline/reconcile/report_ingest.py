"""Take a stored zrsd001 or zrsd004 file into the database.

The web upload and the robot both go through these functions, so a report read by the robot
gives exactly the result of the same file uploaded by the admin.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from shoponline.db.models import ImportBatch, OrderBatch
from shoponline.exports.accounting_workbook import (
    AccountingFile,
    build_accounting_workbook,
    database_lookup,
)
from shoponline.importers.sap_reports import DeliveryRow, read_zrsd001, read_zrsd004
from shoponline.reconcile.so_link import SoImportResult, mark_delivered, store_so_reports


def ingest_zrsd001(
    session: Session,
    record: ImportBatch,
    actor: str,
    expect_batch: OrderBatch | None = None,
) -> SoImportResult:
    """Raises FileRejected before anything is written when the file does not read cleanly."""
    reports = read_zrsd001(Path(record.stored_path))
    session.add(record)
    session.flush()
    return store_so_reports(session, reports, actor, record, expect_batch=expect_batch)


@dataclass
class DeliveryImport:
    rows: list[DeliveryRow]
    delivered: int
    preview: AccountingFile


def ingest_zrsd004(session: Session, record: ImportBatch, actor: str) -> DeliveryImport:
    rows = read_zrsd004(Path(record.stored_path))
    preview = build_accounting_workbook(Path(record.stored_path), database_lookup(session))
    session.add(record)
    session.flush()
    delivered = mark_delivered(session, rows, actor)
    record.updated_count = delivered
    return DeliveryImport(rows=rows, delivered=delivered, preview=preview)
