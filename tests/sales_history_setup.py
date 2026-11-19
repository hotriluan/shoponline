"""Delivered orders with everything the Shop Online history file needs, for tests."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.db.models import (
    CustomerInfo,
    OrderBatch,
    ReportItemName,
    SalesOrder,
    SalesOrderItem,
    SapTaxInvoice,
)
from shoponline.domain import states

MATERIAL = "100001787"
ADDRESS = "Phường Sài Gòn, Thành phố Hồ Chí Minh, Việt Nam"
AUTO = "auto"


def batch(db: Session, platform: str = "SHOPEE", day: date = date(2026, 11, 10)) -> OrderBatch:
    found = db.scalar(
        select(OrderBatch).where(OrderBatch.platform == platform, OrderBatch.processing_date == day)
    )
    if found:
        return found
    created = OrderBatch(platform=platform, processing_date=day, gi_date=day)
    db.add(created)
    db.flush()
    return created


def report_name(db: Session, material: str = MATERIAL) -> ReportItemName:
    row = ReportItemName(
        material_number=material,
        item_name=f"Propan - SƠN {material}",
        size="0.8 lít",
        variation="Màu sắc:2004 Cánh gián",
        updated_by="t",
    )
    db.add(row)
    db.flush()
    return row


def order(
    db: Session,
    order_id: str,
    ordered_at: datetime,
    *,
    platform: str = "SHOPEE",
    status: str = states.DELIVERED,
    lines: tuple[tuple[str | None, int, int, int], ...] = ((MATERIAL, 1, 120000, 0),),
    name: str | None = "Nguyễn Văn A",
    address: str | None = ADDRESS,
    customer: bool = True,
    invoice: str | None = AUTO,
) -> SalesOrder:
    """lines: (material, quantity, unit_price, unit_subsidy) per order line. A delivered order
    gets a tax invoice for its DO ("HD" + order id) unless invoice is None."""
    created = SalesOrder(
        platform=platform,
        platform_order_id=order_id,
        order_batch_id=batch(db, platform).id,
        ordered_at=ordered_at,
        status=status,
        do_number="80" + order_id[-8:] if status == states.DELIVERED else None,
    )
    created.items = [
        SalesOrderItem(
            line_no=n,
            product_name="P",
            variation_name=f"V{n}",
            quantity=quantity,
            unit_price=price,
            unit_subsidy=subsidy,
            material_number=material,
            sap_name="SAP" if material else None,
        )
        for n, (material, quantity, price, subsidy) in enumerate(lines, start=1)
    ]
    db.add(created)
    if customer:
        db.add(
            CustomerInfo(
                platform=platform, platform_order_id=order_id, customer_name=name, address=address
            )
        )
    if created.do_number and invoice is not None:
        tax_invoice(db, created.do_number, f"HD{order_id}" if invoice == AUTO else invoice)
    db.flush()
    return created


def tax_invoice(db: Session, delivery: str, number: str) -> SapTaxInvoice:
    row = SapTaxInvoice(
        delivery=delivery,
        tax_invoice_doc=number,
        billing_doc="1930000001",
        billing_date=date(2026, 11, 13),
        bill_to="1200001145",
    )
    db.add(row)
    db.flush()
    return row
