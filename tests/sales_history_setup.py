"""Delivered orders with everything the Shop Online history file needs, for tests."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.db.models import (
    CustomerInfo,
    ImportBatch,
    OrderBatch,
    PlatformSettlement,
    ReportItemName,
    SalesOrder,
    SalesOrderItem,
    SapTaxInvoice,
)
from shoponline.domain import states
from shoponline.domain.provinces import place_key
from shoponline.domain.report_names import province_of
from tests.shop_codes import SHOP

MATERIAL = "100001787"
ADDRESS = "Phường Sài Gòn, Thành phố Hồ Chí Minh, Việt Nam"
AUTO = "auto"
SETTLED = 99000


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
    settlement: int | str | None = AUTO,
    shop_code: str | None = None,
) -> SalesOrder:
    """lines: (material, quantity, unit_price, unit_subsidy) per order line. A delivered order
    gets a tax invoice for its DO ("HD" + order id) unless invoice is None. A Shopee or TikTok
    order gets one settlement row of SETTLED unless settlement is None (or another amount)."""
    created = SalesOrder(
        platform=platform,
        shop_code=shop_code or SHOP[platform],
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
                platform=platform,
                platform_order_id=order_id,
                customer_name=name,
                address=address,
                province=province_of(address),
                place_key=place_key(address),
            )
        )
    if created.do_number and invoice is not None:
        tax_invoice(db, created.do_number, f"HD{order_id}" if invoice == AUTO else invoice)
    if platform in ("SHOPEE", "TIKTOK") and settlement is not None:
        paid(db, platform, order_id, SETTLED if settlement == AUTO else settlement)
    db.flush()
    return created


def paid(
    db: Session, platform: str, order_id: str, amount: int, key: str | None = None
) -> PlatformSettlement:
    record = ImportBatch(
        kind="settlement",
        platform=platform,
        file_name="s.xlsx",
        sha256="0" * 64,
        stored_path="s.xlsx",
        imported_by="t",
    )
    db.add(record)
    db.flush()
    row = PlatformSettlement(
        platform=platform,
        platform_order_id=order_id,
        line_key=key or f"{order_id}|{amount}",
        amount=amount,
        settled_at=datetime(2026, 11, 14),
        import_batch_id=record.id,
    )
    db.add(row)
    db.flush()
    return row


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


def returned(
    db: Session,
    order: SalesOrder,
    seq: int,
    *,
    taken: dict[int, int] | None = None,
    reason: str = "CANCEL",
    status: str = "ISSUED",
):
    """An issued return of the order with its sale lines. taken: line_no -> quantity returned;
    None returns the whole order."""
    from shoponline.db.models import SalesReturn, SalesReturnSaleLine

    quantities = taken or {i.line_no: i.quantity for i in order.items}
    full = taken is None
    created = SalesReturn(
        sales_order_id=order.id,
        reason_kind=reason,
        status=status,
        doc_year=2026,
        doc_seq=seq,
        doc_no=f"{seq:03d}/11.2026 ALK-KH.STMĐT",
        full_return=full,
        delivery=order.do_number,
        tax_invoice_doc=f"HD{order.platform_order_id}",
        invoice_symbol="1C26TAL",
        billing_date=date(2026, 11, 13),
        invoice_net=111111,
        invoice_tax=8889,
        vat_rate=8,
        returned_net=111111,
        returned_tax=8889,
        buyer_name="Nguyễn Văn A",
        buyer_address=ADDRESS,
        platform_name="Shopee",
        issued_by="t",
    )
    created.sale_lines = [
        SalesReturnSaleLine(
            sales_order_item_id=item.id,
            quantity=quantities[item.line_no],
            customer_paid=(item.unit_price - item.unit_subsidy) * quantities[item.line_no],
        )
        for item in order.items
        if quantities.get(item.line_no)
    ]
    db.add(created)
    db.flush()
    return created


def pasted_order(db: Session, order: SalesOrder, file_id: int) -> None:
    from shoponline.db.models import SalesHistoryExported

    db.add(
        SalesHistoryExported(sales_order_id=order.id, generated_file_id=file_id, confirmed_by="t")
    )
    db.flush()


def pasted_return(db: Session, sales_return, kind: str, file_id: int) -> None:
    from shoponline.db.models import SalesReturnHistoryExported

    db.add(
        SalesReturnHistoryExported(
            return_id=sales_return.id, kind=kind, generated_file_id=file_id, confirmed_by="t"
        )
    )
    db.flush()


def history_file(db: Session) -> int:
    from shoponline.db.models import GeneratedFile

    record = GeneratedFile(
        kind="sales_history",
        file_name="f.xlsx",
        stored_path="f.xlsx",
        sha256="0" * 64,
        created_by="t",
    )
    db.add(record)
    db.flush()
    return record.id
