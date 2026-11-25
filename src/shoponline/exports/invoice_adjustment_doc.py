"""Biên bản điều chỉnh hóa đơn (.docx), filled from the stored snapshot of a sales return.

The sample form is edited in place into a template (exports/templates/invoice_adjustment.docx):
only the fields that were red are placeholders, everything else keeps the sample's formatting.
Scalars go through docxtpl with autoescape; the item rows are copies of the template's data row.
The text comes from the snapshot, never from live data, so a download made later is identical.
"""

from __future__ import annotations

import copy
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from docx import Document
from docxtpl import DocxTemplate

from shoponline.exports.text_clean import clean_text
from shoponline.returns.money import format_vnd

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
TEMPLATE = Path(__file__).parent / "templates" / "invoice_adjustment.docx"
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

REASON_TEXT = {"CANCEL": "hủy đơn hàng đã đặt", "RETURN": "trả lại hàng đã mua"}
ORDER_REF_TEXT = {"CANCEL": "đã bị hủy", "RETURN": "bị trả lại"}


def format_qty(quantity: Decimal | float | int, *, negative: bool = False) -> str:
    value = Decimal(quantity).normalize()
    text = f"{value:f}".replace(".", ",") if value != value.to_integral_value() else str(int(value))
    return f"-{text}" if negative else text


def _signed(amount: int, negative: bool) -> str:
    return format_vnd(-amount if negative else amount)


def _line(line, *, after: bool) -> dict[str, str]:
    quantity = line.return_qty if after else line.invoice_qty
    amount = line.amount_returned if after else line.amount_before
    return {
        "name": clean_text(line.invoice_name),
        "unit": clean_text(line.invoice_unit),
        "qty": format_qty(quantity, negative=after),
        "unit_price": format_vnd(line.unit_price),
        "amount": _signed(amount, after),
    }


def _totals(net: int, tax: int, *, negative: bool) -> dict[str, str]:
    return {
        "net": _signed(net, negative),
        "tax": _signed(tax, negative),
        "total": _signed(net + tax, negative),
    }


def context(sales_return) -> dict:
    kind = sales_return.reason_kind
    return {
        "doc_no": clean_text(sales_return.doc_no),
        "year": str(sales_return.doc_year),
        "buyer_name": clean_text(sales_return.buyer_name),
        "buyer_address": clean_text(sales_return.buyer_address),
        "platform_name": clean_text(sales_return.platform_name),
        "invoice_symbol": clean_text(sales_return.invoice_symbol),
        "invoice_no": sales_return.tax_invoice_doc.zfill(8),
        "invoice_date": f"{sales_return.billing_date:%d/%m/%Y}",
        "platform_order_id": clean_text(sales_return.order.platform_order_id),
        "reason_text": REASON_TEXT[kind],
        "order_ref_text": ORDER_REF_TEXT[kind],
        "vat_rate": str(sales_return.vat_rate),
        "before_lines": [_line(line, after=False) for line in sales_return.lines],
        "after_lines": [
            _line(line, after=True) for line in sales_return.lines if line.return_qty > 0
        ],
        "before": _totals(sales_return.invoice_net, sales_return.invoice_tax, negative=False),
        "after": _totals(sales_return.returned_net, sales_return.returned_tax, negative=True),
    }


def _expand_rows(template: bytes, counts: tuple[tuple[str, int], ...]) -> bytes:
    """Repeat each item table's data row once per line, pointing each copy at its own item."""
    document = Document(BytesIO(template))
    for table, (key, count) in zip(document.tables, counts, strict=True):
        data_row = table.rows[1]._tr
        pristine = copy.deepcopy(data_row)  # copies must come from the unedited row
        previous = data_row
        for index in range(count):
            row = data_row if index == 0 else copy.deepcopy(pristine)
            for text in row.iter(f"{{{W_NS}}}t"):
                if text.text and "{{ l." in text.text:
                    text.text = text.text.replace("{{ l.", f"{{{{ {key}[{index}].")
            if index:
                previous.addnext(row)
                previous = row
    out = BytesIO()
    document.save(out)
    return out.getvalue()


def render(sales_return) -> bytes:
    values = context(sales_return)
    counts = (
        ("before_lines", len(values["before_lines"])),
        ("after_lines", len(values["after_lines"])),
    )
    expanded = _expand_rows(TEMPLATE.read_bytes(), counts)
    template = DocxTemplate(BytesIO(expanded))
    template.render(values, autoescape=True)
    out = BytesIO()
    template.save(out)
    return out.getvalue()
