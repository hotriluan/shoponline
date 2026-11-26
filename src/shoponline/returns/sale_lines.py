"""What a return takes off each platform order line, at the marketplace price.

A return is chosen on SAP order lines (main lines only); the Shop Online file and the reports
count platform order lines. The two share the material number, and `reconcile.so_link` already
requires the same material and quantity on both sides, so a material's returned share is spread
over the platform lines of that material. When the share does not land on whole units, nothing is
guessed: the return is blocked with the reason.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from shoponline.db.models import SalesReturn, SalesReturnSaleLine
from shoponline.returns.amounts import Blocked


@dataclass(frozen=True)
class SaleLine:
    sales_order_item_id: int
    quantity: int
    customer_paid: int


@dataclass(frozen=True)
class ReturnedQuantity:
    material_number: str
    invoice_qty: Decimal
    return_qty: Decimal


def split(order_items: Iterable, return_lines: Iterable) -> list[SaleLine] | Blocked:
    """order_items: platform lines (id, material_number, quantity, unit_price, unit_subsidy);
    return_lines: SAP lines of the return (material_number, invoice_qty, return_qty)."""
    items = list(order_items)
    invoiced: dict[str, Decimal] = defaultdict(Decimal)
    taken: dict[str, Decimal] = defaultdict(Decimal)
    for line in return_lines:
        invoiced[line.material_number] += Decimal(line.invoice_qty)
        taken[line.material_number] += Decimal(line.return_qty)

    reasons: list[str] = []
    if all(taken[m] == invoiced[m] for m in invoiced):
        # The whole invoice: every platform line must go, or the order would not net to zero.
        stray = sorted({i.material_number or "?" for i in items} - set(invoiced))
        if stray:
            reasons.append(f"Mã {', '.join(stray)} của đơn sàn không có trên hóa đơn")
    found: list[SaleLine] = []
    for material, quantity in taken.items():
        if quantity <= 0:
            continue
        own = [i for i in items if i.material_number == material]
        if not own:
            reasons.append(f"Mã {material} không có trên đơn sàn")
            continue
        on_platform = sum(i.quantity for i in own)
        if on_platform != invoiced[material]:
            reasons.append(
                f"Mã {material}: đơn sàn có {on_platform}, hóa đơn có "
                f"{_plain(invoiced[material])}; không quy đổi được"
            )
            continue
        share = Fraction(quantity) / Fraction(invoiced[material])
        lines = []
        for item in own:
            part = item.quantity * share
            if part.denominator != 1:
                reasons.append(
                    f"Mã {material} trả {_plain(quantity)} không chia đúng vào các dòng của đơn sàn"
                )
                break
            if part:
                count = int(part)
                lines.append(
                    SaleLine(item.id, count, (item.unit_price - (item.unit_subsidy or 0)) * count)
                )
        else:
            found += lines
    if reasons:
        return Blocked(tuple(reasons))
    return sorted(found, key=lambda line: line.sales_order_item_id)


def backfill(session: Session) -> tuple[list[str], list[tuple[str, str]]]:
    """Write the sale lines of every return issued before they existed, VOID ones included.
    Returns (document numbers written, (document number, reason) not written). The caller
    commits; running it again only picks up what is still missing."""
    missing = session.scalars(
        select(SalesReturn)
        .where(~exists().where(SalesReturnSaleLine.return_id == SalesReturn.id))
        .order_by(SalesReturn.id)
    ).all()
    written: list[str] = []
    blocked: list[tuple[str, str]] = []
    for sales_return in missing:
        found = split(sales_return.order.items, sales_return.lines)
        if isinstance(found, Blocked):
            blocked.append((sales_return.doc_no, found.reason))
            continue
        sales_return.sale_lines = [
            SalesReturnSaleLine(
                sales_order_item_id=line.sales_order_item_id,
                quantity=line.quantity,
                customer_paid=line.customer_paid,
            )
            for line in found
        ]
        written.append(sales_return.doc_no)
    session.flush()
    return written, blocked


def _plain(quantity: Decimal) -> str:
    return format(Decimal(quantity).normalize(), "f")
