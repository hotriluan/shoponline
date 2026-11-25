"""Rows for return tests: a delivered order with its SAP reference, invoice and invoice names."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from shoponline.db.models import (
    InvoiceItemText,
    SalesOrder,
    SalesReturn,
    SapSoRef,
    SapSoRefItem,
    SapTaxInvoice,
)
from tests import sales_history_setup as setup

MATERIAL = setup.MATERIAL
INVOICE_NAME = "SƠN V-09 REDDISH CLAY 2004 VN"
INVOICE_UNIT = "LON 0.8 LT"
SAP_NAME = "V-09 REDDISH CLAY 2004 VN-0.8L"
BILLING_DATE = date(2026, 11, 17)


def invoice_text(db: Session, material: str = MATERIAL, **overrides) -> InvoiceItemText:
    row = InvoiceItemText(
        material_number=material,
        invoice_name=overrides.pop("invoice_name", INVOICE_NAME),
        invoice_unit=overrides.pop("invoice_unit", INVOICE_UNIT),
        stock_unit=overrides.pop("stock_unit", "PC"),
        source=overrides.pop("source", "manual"),
        updated_by="t",
    )
    assert not overrides, overrides
    db.add(row)
    db.flush()
    return row


def delivered_order(
    db: Session,
    order_id: str = "261115BUCPCSEN",
    *,
    lines: tuple[tuple[str, int, int], ...] = ((MATERIAL, 1, 120000),),
    so_items: tuple[tuple[int, str, int, int], ...] | None = None,
    net: int | None = 111111,
    tax: int | None = 8889,
    invoice_no: str = "8038",
    billing_date: date = BILLING_DATE,
    platform: str = "SHOPEE",
    texts: bool = True,
    name: str | None = "Nguyen Van A",
    address: str | None = "1 Duong Thu Nghiem, Quan Thu Nghiem, Thanh pho Thu Nghiem",
) -> SalesOrder:
    """lines: (material, quantity, line total incl. VAT) per order line. so_items replaces the
    SAP side with (item_no, material, quantity, total incl. VAT), for kit tests."""
    order = setup.order(
        db,
        order_id,
        datetime(2026, 11, 15, 9, 0),
        platform=platform,
        lines=tuple((m, q, total // q, 0) for m, q, total in lines),
        name=name,
        address=address,
        invoice=None,
        settlement=None,
    )
    for item in order.items:
        item.sap_name = SAP_NAME
    order.so_number = "SO" + order_id[-8:]
    items = so_items or tuple(
        (n * 10, m, q, total) for n, (m, q, total) in enumerate(lines, start=1)
    )
    db.add(
        SapSoRef(
            so_number=order.so_number,
            po_no=order_id,
            sold_to="1200001145",
            doc_date=date(2026, 11, 15),
            net_value_incl=sum(total for _, _, _, total in items),
            items=[
                SapSoRefItem(item_no=n, material_number=m, quantity=q, net_value_incl=total)
                for n, m, q, total in items
            ],
        )
    )
    db.add(
        SapTaxInvoice(
            delivery=order.do_number,
            tax_invoice_doc=invoice_no,
            billing_doc="1930000001",
            billing_date=billing_date,
            bill_to="1200001145",
            net_value_vnd=net,
            tax_vnd=tax,
        )
    )
    if texts:
        for material in {m for m, _, _ in lines}:
            invoice_text(db, material)
    db.flush()
    return order


def sales_return(
    db: Session, order: SalesOrder, *, year: int, seq: int, status: str = "ISSUED"
) -> SalesReturn:
    row = SalesReturn(
        sales_order_id=order.id,
        reason_kind="CANCEL",
        status=status,
        doc_year=year,
        doc_seq=seq,
        doc_no=f"{seq:03d}/11.{year} ALK-KH.STMĐT",
        full_return=True,
        delivery=order.do_number,
        tax_invoice_doc="8038",
        invoice_symbol="1C26TAL",
        billing_date=BILLING_DATE,
        invoice_net=111111,
        invoice_tax=8889,
        vat_rate=8,
        returned_net=111111,
        returned_tax=8889,
        buyer_name="Nguyen Van A",
        buyer_address="1 Duong Thu Nghiem",
        platform_name="Shopee",
        issued_by="t",
    )
    db.add(row)
    db.flush()
    return row
