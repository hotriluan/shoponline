"""What each order has received after delivery: the tax invoice of its DO (zrsd003) and the money
the platform paid for it (settlement files). Both arrive days after the DO, so they are read from
the tables the reports fill instead of being kept as order statuses."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shoponline.db.models import PlatformSettlement, SalesOrder, SapTaxInvoice
from shoponline.exports.sales_history_workbook import SETTLEMENT_LOOKUP_PLATFORMS


@dataclass(frozen=True)
class OrderProgress:
    invoice: str | None
    paid: int | None


@dataclass(frozen=True)
class BatchProgress:
    invoiced: int = 0
    paid: int = 0


def order_progress(db: Session, orders: Iterable[SalesOrder]) -> dict[int, OrderProgress]:
    """Progress per order id. `paid` stays None when no settlement is known (for Lazada, until
    an admin types the amount in)."""
    orders = list(orders)
    deliveries = {o.do_number for o in orders if o.do_number}
    invoices = (
        dict(
            db.execute(
                select(SapTaxInvoice.delivery, SapTaxInvoice.tax_invoice_doc).where(
                    SapTaxInvoice.delivery.in_(deliveries)
                )
            ).all()
        )
        if deliveries
        else {}
    )
    settled_ids = {o.platform_order_id for o in orders if o.platform in SETTLEMENT_LOOKUP_PLATFORMS}
    totals = (
        {
            (platform, order_id): total
            for platform, order_id, total in db.execute(
                select(
                    PlatformSettlement.platform,
                    PlatformSettlement.platform_order_id,
                    func.sum(PlatformSettlement.amount),
                )
                .where(
                    PlatformSettlement.platform.in_(SETTLEMENT_LOOKUP_PLATFORMS),
                    PlatformSettlement.platform_order_id.in_(settled_ids),
                )
                .group_by(PlatformSettlement.platform, PlatformSettlement.platform_order_id)
            )
        }
        if settled_ids
        else {}
    )
    return {
        o.id: OrderProgress(
            invoice=invoices.get(o.do_number or ""),
            paid=int(totals[(o.platform, o.platform_order_id)])
            if (o.platform, o.platform_order_id) in totals
            else None,
        )
        for o in orders
    }


def batch_progress(db: Session, batches: Iterable) -> dict[int, BatchProgress]:
    """Count of orders with an invoice and with money received, per order batch id."""
    batches = list(batches)
    progress = order_progress(db, [o for b in batches for o in b.orders])
    result = {}
    for b in batches:
        rows = [progress[o.id] for o in b.orders]
        result[b.id] = BatchProgress(
            invoiced=sum(1 for p in rows if p.invoice),
            paid=sum(1 for p in rows if p.paid is not None),
        )
    return result
