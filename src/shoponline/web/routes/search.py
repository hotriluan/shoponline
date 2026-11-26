"""Quick order lookup: one box that takes a platform order id, a VAT invoice number, an SO, a DO
or a return document number and leads to the order."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from shoponline.db.models import AppUser, SalesOrder, SalesReturn, SapTaxInvoice
from shoponline.web.app import current_user, get_db, redirect, render
from shoponline.web.pagination import search_filter, search_words

router = APIRouter()

PARTIAL_MIN = 4
PARTIAL_LIMIT = 50
PARTIAL = "Khớp một phần"


def _like_prefix(key: str) -> str:
    return key.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def exact_matches(db: Session, key: str) -> dict[int, list[str]]:
    """Order ids that the whole key identifies, each with the kinds of code it matched."""
    found: dict[int, list[str]] = {}

    def add(order_id: int, label: str) -> None:
        labels = found.setdefault(order_id, [])
        if label not in labels:
            labels.append(label)

    for (order_id,) in db.execute(
        select(SalesOrder.id).where(func.upper(SalesOrder.platform_order_id) == key)
    ):
        add(order_id, "Mã đơn")
    digits = key.lstrip("0")
    if digits:
        for (order_id,) in db.execute(
            select(SalesOrder.id)
            .join(SapTaxInvoice, SapTaxInvoice.delivery == SalesOrder.do_number)
            .where(func.ltrim(SapTaxInvoice.tax_invoice_doc, "0") == digits)
        ):
            add(order_id, "Hóa đơn VAT")
    for (order_id,) in db.execute(select(SalesOrder.id).where(SalesOrder.so_number == key)):
        add(order_id, "SO")
    for (order_id,) in db.execute(select(SalesOrder.id).where(SalesOrder.do_number == key)):
        add(order_id, "DO")
    doc_no = func.replace(func.upper(SalesReturn.doc_no), " ", "")
    for order_id, number, status in db.execute(
        select(SalesReturn.sales_order_id, SalesReturn.doc_no, SalesReturn.status).where(
            doc_no.like(_like_prefix(key), escape="\\")
        )
    ):
        add(order_id, f"Phiếu trả {number}" + (" (đã hủy)" if status == "VOID" else ""))
    return found


def partial_matches(db: Session, raw: str) -> dict[int, list[str]]:
    condition = search_filter(
        raw, SalesOrder.platform_order_id, SalesOrder.so_number, SalesOrder.do_number
    )
    stmt = select(SalesOrder.id).where(condition).order_by(SalesOrder.ordered_at.desc())
    return {order_id: [PARTIAL] for order_id in db.scalars(stmt.limit(PARTIAL_LIMIT))}


def _orders(db: Session, matches: dict[int, list[str]]) -> list[SalesOrder]:
    orders = db.scalars(
        select(SalesOrder)
        .where(SalesOrder.id.in_(list(matches)))
        .options(selectinload(SalesOrder.batch), selectinload(SalesOrder.shop))
        .order_by(SalesOrder.ordered_at.desc(), SalesOrder.id)
    )
    return list(orders)


@router.get("/search")
def search(
    request: Request,
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    raw = search_words(request)
    if not raw:
        return redirect(request.headers.get("referer") or "/")
    key = raw.replace(" ", "").upper()
    matches = exact_matches(db, key)
    if len(matches) == 1:
        return redirect(f"/orders/{next(iter(matches))}")
    if not matches and len(key) >= PARTIAL_MIN:
        matches = partial_matches(db, raw)
    orders = _orders(db, matches) if matches else []
    return render(request, "search.html", user, q=raw, orders=orders, matches=matches)
