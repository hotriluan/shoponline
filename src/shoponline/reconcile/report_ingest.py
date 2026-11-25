"""Take a stored zrsd001, zrsd003, zrsd004 or platform settlement file into the database.

The web upload and the robot both go through these functions, so a report read by the robot
gives exactly the result of the same file uploaded by the admin.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from shoponline.db.models import (
    ImportBatch,
    OrderBatch,
    PlatformSetting,
    PlatformSettlement,
    SapTaxInvoice,
)
from shoponline.exports.accounting_workbook import (
    AccountingFile,
    build_accounting_workbook,
    database_lookup,
)
from shoponline.importers.sap_reports import (
    DeliveryRow,
    TaxInvoiceRow,
    read_zrsd001,
    read_zrsd003,
    read_zrsd004,
)
from shoponline.importers.settlement_files import read_settlement_file
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


def _invoice_order(row: TaxInvoiceRow) -> tuple[date, str, str]:
    return (row.billing_date, row.billing_doc, row.tax_invoice_doc)


@dataclass
class TaxInvoiceImport:
    kept: int
    skipped_other_customers: int
    new: int
    updated: int


def ingest_zrsd003(session: Session, record: ImportBatch, actor: str) -> TaxInvoiceImport:
    """Store the invoices billed to a platform's SAP customer, keyed by DO. Other customers' rows
    (business customers, with names and tax codes) are dropped, never stored."""
    customers = set(session.scalars(select(PlatformSetting.sap_customer)))
    rows = read_zrsd003(Path(record.stored_path), customers)
    # One invoice per DO. When a file lists a DO twice, the newest invoice wins whatever the row
    # order, so a cancelled or superseded invoice listed after it cannot take its place.
    kept: dict[str, TaxInvoiceRow] = {}
    for row in rows:
        if row.bill_to not in customers:
            continue
        current = kept.get(row.delivery)
        if current is None or _invoice_order(row) > _invoice_order(current):
            kept[row.delivery] = row
    session.add(record)
    session.flush()
    existing: dict[str, date] = {}
    if kept:
        existing = dict(
            session.execute(
                select(SapTaxInvoice.delivery, SapTaxInvoice.billing_date).where(
                    SapTaxInvoice.delivery.in_(kept)
                )
            ).all()
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
                    # A file without the money columns must not erase money already stored.
                    "net_value_vnd": func.coalesce(
                        stmt.excluded.net_value_vnd, SapTaxInvoice.net_value_vnd
                    ),
                    "tax_vnd": func.coalesce(stmt.excluded.tax_vnd, SapTaxInvoice.tax_vnd),
                    "import_batch_id": stmt.excluded.import_batch_id,
                    "updated_at": func.now(),
                },
                # An older file read later never replaces a newer invoice.
                where=SapTaxInvoice.billing_date <= stmt.excluded.billing_date,
            ),
            [
                {
                    "delivery": row.delivery,
                    "tax_invoice_doc": row.tax_invoice_doc,
                    "billing_doc": row.billing_doc,
                    "billing_date": row.billing_date,
                    "bill_to": row.bill_to,
                    "net_value_vnd": row.net_value_vnd,
                    "tax_vnd": row.tax_vnd,
                    "import_batch_id": record.id,
                }
                for row in kept.values()
            ],
        )
    replaced = sum(
        1 for d, row in kept.items() if d in existing and existing[d] <= row.billing_date
    )
    record.new_count = len(kept) - len(existing)
    record.updated_count = replaced
    return TaxInvoiceImport(
        kept=len(kept),
        skipped_other_customers=len(rows) - len(kept),
        new=record.new_count,
        updated=record.updated_count,
    )


@dataclass
class SettlementImport:
    platform: str
    kept: int
    skipped: list[str]
    orders: int
    new: int
    updated: int
    unchanged: int


def ingest_settlement(session: Session, record: ImportBatch, actor: str) -> SettlementImport:
    """Store one row per settlement transaction, keyed by (platform, line_key), so reading a
    file again, or one covering an overlapping period, never counts a transaction twice."""
    parsed = read_settlement_file(Path(record.stored_path))
    record.platform = parsed.platform
    session.add(record)
    session.flush()
    keys = [row.line_key for row in parsed.rows]
    existing = {
        key: (amount, settled_at)
        for key, amount, settled_at in session.execute(
            select(
                PlatformSettlement.line_key,
                PlatformSettlement.amount,
                PlatformSettlement.settled_at,
            ).where(
                PlatformSettlement.platform == parsed.platform,
                PlatformSettlement.line_key.in_(keys),
            )
        )
    }
    new = updated = 0
    for row in parsed.rows:
        before = existing.get(row.line_key)
        if before is None:
            new += 1
        elif before != (row.amount, row.settled_at):
            updated += 1
    stmt = insert(PlatformSettlement)
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=[PlatformSettlement.platform, PlatformSettlement.line_key],
            set_={
                "platform_order_id": stmt.excluded.platform_order_id,
                "amount": stmt.excluded.amount,
                "settled_at": stmt.excluded.settled_at,
                "import_batch_id": stmt.excluded.import_batch_id,
                "updated_at": func.now(),
            },
        ),
        [
            {
                "platform": parsed.platform,
                "platform_order_id": row.platform_order_id,
                "line_key": row.line_key,
                "amount": row.amount,
                "settled_at": row.settled_at,
                "import_batch_id": record.id,
            }
            for row in parsed.rows
        ],
    )
    record.new_count = new
    record.updated_count = updated
    record.unchanged_count = len(parsed.rows) - new - updated
    return SettlementImport(
        platform=parsed.platform,
        kept=len(parsed.rows),
        skipped=parsed.skipped,
        orders=len({row.platform_order_id for row in parsed.rows}),
        new=new,
        updated=updated,
        unchanged=record.unchanged_count,
    )
