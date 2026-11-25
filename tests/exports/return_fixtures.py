"""A sales return as the exporters read it, without a database."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace


def line(
    no=1, *, name="SƠN V-09 REDDISH CLAY 2004 VN", unit="LON 0.8 LT", qty=1, ret=1, net=111111
):
    return SimpleNamespace(
        line_no=no,
        so_item_no=no * 10,
        material_number="100001787",
        sap_name="V-09 REDDISH CLAY 2004 VN-0.8L",
        invoice_name=name,
        invoice_unit=unit,
        stock_unit="PC",
        invoice_qty=Decimal(qty),
        return_qty=Decimal(ret),
        unit_price=net // qty,
        amount_before=net,
        amount_returned=net if ret == qty else net * ret // qty,
    )


def sales_return(lines=None, **overrides):
    lines = lines or [line()]
    returned = sum(item.amount_returned for item in lines)
    data = dict(
        doc_no="080/11.2026 ALK-KH.STMĐT",
        doc_year=2026,
        doc_seq=80,
        reason_kind="CANCEL",
        buyer_name="Nguyen Van A",
        buyer_address="1 Duong Thu Nghiem, Quan Thu Nghiem",
        platform_name="Shopee",
        invoice_symbol="1C26TAL",
        tax_invoice_doc="8038",
        billing_date=date(2026, 11, 17),
        vat_rate=8,
        invoice_net=sum(item.amount_before for item in lines),
        invoice_tax=8889,
        returned_net=returned,
        returned_tax=8889 if returned == 111111 else returned * 8 // 100,
        order=SimpleNamespace(platform_order_id="261115BUCPCSEN"),
        lines=lines,
    )
    data.update(overrides)
    return SimpleNamespace(**data)
