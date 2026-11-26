"""Which orders were cancelled or returned after their invoice, and by which return document.

There is no order status for it: the label follows the order's ISSUED return, so voiding the
return removes the label. An order cancelled before any invoice keeps its own CANCELLED status
and has no return; this module does not cover it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.db.models import SalesOrder, SalesReturn

CANCELLED_AFTER_INVOICE = "Hủy sau HĐ"
RETURNED = "Trả hàng"
PARTLY_RETURNED = "Trả một phần"


@dataclass(frozen=True)
class ReturnFlag:
    label: str
    doc_no: str
    reason_kind: str
    full_return: bool
    return_id: int


def label_of(reason_kind: str, full_return: bool) -> str:
    if not full_return:
        return PARTLY_RETURNED
    return CANCELLED_AFTER_INVOICE if reason_kind == "CANCEL" else RETURNED


def of(session: Session, order_ids: Iterable[int]) -> dict[int, ReturnFlag]:
    """Order id -> its flag, for the orders that have an ISSUED return; one query for all."""
    ids = list(set(order_ids))
    if not ids:
        return {}
    rows = session.execute(
        select(
            SalesReturn.sales_order_id,
            SalesReturn.id,
            SalesReturn.doc_no,
            SalesReturn.reason_kind,
            SalesReturn.full_return,
        ).where(SalesReturn.sales_order_id.in_(ids), SalesReturn.status == "ISSUED")
    ).all()
    return {
        order_id: ReturnFlag(label_of(kind, full), doc_no, kind, full, return_id)
        for order_id, return_id, doc_no, kind, full in rows
    }


@dataclass(frozen=True)
class FlaggedDelivery:
    delivery: str
    order_id: int
    platform: str
    platform_order_id: str
    flag: ReturnFlag


def by_delivery(session: Session, deliveries: Iterable[str]) -> list[FlaggedDelivery]:
    """The deliveries (DO numbers) whose order has an ISSUED return, in DO order."""
    wanted = list(set(deliveries))
    if not wanted:
        return []
    orders = session.execute(
        select(
            SalesOrder.id, SalesOrder.do_number, SalesOrder.platform, SalesOrder.platform_order_id
        ).where(SalesOrder.do_number.in_(wanted))
    ).all()
    found = of(session, [o.id for o in orders])
    return sorted(
        (
            FlaggedDelivery(o.do_number, o.id, o.platform, o.platform_order_id, found[o.id])
            for o in orders
            if o.id in found
        ),
        key=lambda d: d.delivery,
    )
