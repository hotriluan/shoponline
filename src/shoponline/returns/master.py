"""The master of invoice item names (`invoice_item_text`), filled from invoice PDFs.

A PDF is read only to learn how Bkav prints a material; it is accepted only when it is the
invoice of this very order, and nothing is written unless every check passes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.config import Settings
from shoponline.db.models import InvoiceItemText, SalesOrder, SapSoRef, SapTaxInvoice
from shoponline.domain.states import log_event
from shoponline.importers.excel_table import FileRejected
from shoponline.importers.invoice_pdf import InvoicePdf
from shoponline.reconcile.so_link import is_main_line
from shoponline.returns.amounts import Blocked, invoice_lines


def order_materials(session: Session, order: SalesOrder) -> list[str]:
    """Materials of the invoice lines (main SAP lines) of the order, in line order."""
    ref = session.get(SapSoRef, order.so_number) if order.so_number else None
    if ref is None:
        return []
    seen: list[str] = []
    for item in ref.items:
        if is_main_line(item.item_no) and item.material_number not in seen:
            seen.append(item.material_number)
    return seen


def missing_materials(session: Session, order: SalesOrder) -> list[str]:
    materials = order_materials(session, order)
    known = set(
        session.scalars(
            select(InvoiceItemText.material_number).where(
                InvoiceItemText.material_number.in_(materials)
            )
        )
    )
    return [m for m in materials if m not in known]


@dataclass(frozen=True)
class TextChange:
    material_number: str
    old_name: str
    old_unit: str
    new_name: str
    new_unit: str


@dataclass
class LearnResult:
    added: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    # Materials whose stored name or unit differs from the PDF. Without confirmation they are
    # only listed: nothing at all is written.
    differing: list[TextChange] = field(default_factory=list)
    overwritten: bool = False

    @property
    def needs_confirmation(self) -> bool:
        return bool(self.differing) and not self.overwritten


def learn_from_pdf(
    session: Session,
    order: SalesOrder,
    pdf: InvoicePdf,
    actor: str,
    settings: Settings,
    *,
    confirm_overwrite: bool = False,
) -> LearnResult:
    invoice = session.get(SapTaxInvoice, order.do_number) if order.do_number else None
    ref = session.get(SapSoRef, order.so_number) if order.so_number else None
    problems = _mismatches(order, pdf, invoice, ref, settings)
    if problems:
        raise FileRejected("Hóa đơn PDF không khớp đơn này, không ghi gì", problems)

    figures = invoice_lines(ref.items, invoice.net_value_vnd, invoice.tax_vnd)
    if isinstance(figures, Blocked):
        raise FileRejected("Không dò được số liệu hóa đơn của đơn, không ghi gì", figures.reasons)
    problems = _line_mismatches(pdf, figures)
    if problems:
        raise FileRejected("Dòng hàng của PDF không khớp đơn này, không ghi gì", problems)

    texts: dict[str, tuple[str, str]] = {}
    for line, pdf_line in zip(figures.lines, pdf.lines, strict=True):
        pair = (pdf_line.name, pdf_line.unit)
        if texts.setdefault(line.material_number, pair) != pair:
            raise FileRejected(
                "Một mã vật tư có hai cách viết trên cùng hóa đơn, không ghi gì",
                [f"Mã {line.material_number}"],
            )

    stored = {
        row.material_number: row
        for row in session.scalars(
            select(InvoiceItemText).where(InvoiceItemText.material_number.in_(texts))
        )
    }
    result = LearnResult()
    for material, (name, unit) in texts.items():
        row = stored.get(material)
        if row is None:
            result.added.append(material)
        elif (row.invoice_name, row.invoice_unit) == (name, unit):
            result.unchanged.append(material)
        else:
            result.differing.append(
                TextChange(material, row.invoice_name, row.invoice_unit, name, unit)
            )
    if result.differing and not confirm_overwrite:
        return result

    changes = []
    for material in result.added:
        name, unit = texts[material]
        session.add(
            InvoiceItemText(
                material_number=material,
                invoice_name=name,
                invoice_unit=unit,
                source=pdf.number,
                updated_by=actor,
            )
        )
        changes.append({"material": material, "new_name": name})
    for change in result.differing:
        row = stored[change.material_number]
        row.invoice_name, row.invoice_unit = change.new_name, change.new_unit
        row.source, row.updated_by = pdf.number, actor
        changes.append(
            {
                "material": change.material_number,
                "old_name": change.old_name,
                "new_name": change.new_name,
            }
        )
    result.overwritten = bool(result.differing)
    if changes:
        log_event(
            session,
            actor,
            "invoice_text_learned",
            platform=order.platform,
            platform_order_id=order.platform_order_id,
            detail={"invoice": pdf.number, "materials": changes},
        )
    session.flush()
    return result


def _mismatches(
    order: SalesOrder,
    pdf: InvoicePdf,
    invoice: SapTaxInvoice | None,
    ref: SapSoRef | None,
    settings: Settings,
) -> list[str]:
    problems: list[str] = []
    if invoice is None:
        return ["Đơn chưa có hóa đơn trong zrsd003"]
    if ref is None or not ref.items:
        problems.append("Đơn chưa có dòng SO từ zrsd001")
    if invoice.net_value_vnd is None or invoice.tax_vnd is None:
        problems.append("Hóa đơn chưa có tiền từ zrsd003: đọc lại zrsd003 của tháng hóa đơn trước")
    if pdf.delivery != order.do_number:
        problems.append(f"Số DO trên PDF {pdf.delivery}, đơn có {order.do_number}")
    if pdf.po != order.platform_order_id:
        problems.append(f"Số PO trên PDF {pdf.po}, đơn có {order.platform_order_id}")
    if not pdf.number.isdigit() or not invoice.tax_invoice_doc.isdigit():
        problems.append("Số hóa đơn không đọc được")
    elif int(pdf.number) != int(invoice.tax_invoice_doc):
        problems.append(f"Số hóa đơn trên PDF {pdf.number}, zrsd003 có {invoice.tax_invoice_doc}")
    expected_symbol = settings.invoice_symbol(invoice.billing_date)
    if pdf.symbol != expected_symbol:
        problems.append(f"Ký hiệu trên PDF {pdf.symbol}, cần {expected_symbol}")
    if invoice.net_value_vnd is not None and (pdf.net, pdf.tax) != (
        invoice.net_value_vnd,
        invoice.tax_vnd,
    ):
        problems.append(
            f"Tiền trên PDF (hàng {pdf.net:,}, thuế {pdf.tax:,}) khác zrsd003 "
            f"({invoice.net_value_vnd:,}, {invoice.tax_vnd:,})"
        )
    return problems


def _line_mismatches(pdf: InvoicePdf, figures) -> list[str]:
    if len(pdf.lines) != len(figures.lines):
        return [f"PDF có {len(pdf.lines)} dòng hàng, SO có {len(figures.lines)}"]
    problems = []
    for position, (line, pdf_line) in enumerate(
        zip(figures.lines, pdf.lines, strict=True), start=1
    ):
        if pdf_line.quantity != line.quantity:
            problems.append(
                f"Dòng {position}: số lượng PDF {pdf_line.quantity}, SO {line.quantity}"
            )
        if pdf_line.amount != line.net:
            problems.append(
                f"Dòng {position}: thành tiền PDF {pdf_line.amount:,}, tính ra {line.net:,}"
            )
    return problems
