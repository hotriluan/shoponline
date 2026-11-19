"""Take a stored zrsd001, zrsd003 or zrsd004 file into the database.

The web upload and the robot both go through these functions, so a report read by the robot
gives exactly the result of the same file uploaded by the admin.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from shoponline.db.models import ImportBatch, OrderBatch, PlatformSetting, SapTaxInvoice
from shoponline.exports.accounting_workbook import (
    AccountingFile,
    build_accounting_workbook,
    database_lookup,
)
from shoponline.importers.sap_reports import (
    DeliveryRow,
    read_zrsd001,
    read_zrsd003,
    read_zrsd004,
)
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


@dataclass
class TaxInvoiceImport:
    kept: int
    skipped_other_customers: int
    new: int
    updated: int


def ingest_zrsd003(session: Session, record: ImportBatch, actor: str) -> TaxInvoiceImport:
    """Store the invoices billed to a platform's SAP customer, keyed by DO. Other customers' rows
    (business customers, with names and tax codes) are dropped, never stored."""
    rows = read_zrsd003(Path(record.stored_path))
    customers = set(session.scalars(select(PlatformSetting.sap_customer)))
    kept = {row.delivery: row for row in rows if row.bill_to in customers}
    session.add(record)
    session.flush()
    existing: set[str] = set()
    if kept:
        existing = set(
            session.scalars(select(SapTaxInvoice.delivery).where(SapTaxInvoice.delivery.in_(kept)))
        )
        stmt = insert(SapTaxInvoice)
        # A list of rows runs as executemany, which SQLAlchemy splits into multi-row INSERTs of
        # bounded size, so a read over a long date range stays under the parameter limit.
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=[SapTaxInvoice.delivery],
                set_={
                    "tax_invoice_doc": stmt.excluded.tax_invoice_doc,
                    "billing_doc": stmt.excluded.billing_doc,
                    "billing_date": stmt.excluded.billing_date,
                    "bill_to": stmt.excluded.bill_to,
                    "import_batch_id": stmt.excluded.import_batch_id,
                    "updated_at": func.now(),
                },
            ),
            [
                {
                    "delivery": row.delivery,
                    "tax_invoice_doc": row.tax_invoice_doc,
                    "billing_doc": row.billing_doc,
                    "billing_date": row.billing_date,
                    "bill_to": row.bill_to,
                    "import_batch_id": record.id,
                }
                for row in kept.values()
            ],
        )
    record.new_count = len(kept) - len(existing)
    record.updated_count = len(existing)
    return TaxInvoiceImport(
        kept=len(kept),
        skipped_other_customers=len(rows) - len(kept),
        new=record.new_count,
        updated=record.updated_count,
    )
