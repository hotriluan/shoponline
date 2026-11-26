"""Issue and void invoice adjustments for delivered orders that were already invoiced.

`build_preview` works the figures out from live data (or says exactly why it cannot); `issue`
rebuilds that preview inside its own transaction, checks the admin saw the same numbers, takes a
document number, stores the snapshot and renders the two files. Nothing is written to SAP or Bkav.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shoponline.clock import today_vn
from shoponline.config import Settings
from shoponline.db.models import (
    CustomerInfo,
    GeneratedFile,
    InvoiceItemText,
    PlatformSetting,
    SalesOrder,
    SalesReturn,
    SalesReturnLine,
    SalesReturnSaleLine,
    SapSoRef,
    SapTaxInvoice,
    SkuMapping,
)
from shoponline.domain import states
from shoponline.exports import invoice_adjustment_doc, return_request_workbook
from shoponline.returns import numbering, sale_lines
from shoponline.returns.amounts import Blocked, InvoiceLines, invoice_lines, returned
from shoponline.web.uploads import save_generated_bytes

REASON_KINDS = ("CANCEL", "RETURN")
ONE_ISSUED_INDEX = "uq_sales_return_one_issued"
# The forms write the platform the way it is spelled, not in the capitals the SAP file uses.
PLATFORM_BRAND = {"SHOPEE": "Shopee", "LAZADA": "Lazada", "TIKTOK": "TikTok"}
KIND_DOCX = "invoice_adjustment"
KIND_XLSX = "return_request"


class ReturnBlocked(ValueError):
    """The return cannot be issued; `blocked` says why."""

    def __init__(self, blocked: Blocked):
        super().__init__(blocked.reason)
        self.blocked = blocked


class StaleReturn(ValueError):
    """The data changed since the admin looked at the draft."""


@dataclass(frozen=True)
class Buyer:
    name: str = ""
    address: str = ""


@dataclass(frozen=True)
class PreviewLine:
    so_item_no: int
    material_number: str
    sap_name: str
    invoice_name: str
    invoice_unit: str
    stock_unit: str
    invoice_qty: Decimal
    return_qty: Decimal
    unit_price: int
    amount_before: int
    amount_returned: int


@dataclass(frozen=True)
class Preview:
    order_id: int
    reason_kind: str
    lines: tuple[PreviewLine, ...]
    full_return: bool
    delivery: str
    tax_invoice_doc: str
    invoice_symbol: str
    billing_date: date
    invoice_net: int
    invoice_tax: int
    vat_rate: int
    returned_net: int
    returned_tax: int
    buyer_name: str
    buyer_address: str
    platform_name: str
    sale_lines: tuple[sale_lines.SaleLine, ...]
    fingerprint: str


def _plain(quantity: Decimal) -> str:
    """1, Decimal('1') and Decimal('1.000') are the same quantity: one text for all three."""
    return format(Decimal(quantity).normalize(), "f")


def _fingerprint(preview: dict) -> str:
    """Everything the admin approves on screen except the buyer, whom the form carries itself."""
    text = json.dumps(preview, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _sap_names(session: Session, order: SalesOrder, materials: list[str]) -> tuple[dict, list[str]]:
    """SAP item name per material: the order's own lines first, else the platform mapping."""
    names: dict[str, str] = {}
    problems: list[str] = []
    for material in materials:
        own = {i.sap_name for i in order.items if i.material_number == material and i.sap_name}
        if not own:
            own = set(
                session.scalars(
                    select(SkuMapping.sap_name).where(
                        SkuMapping.platform == order.platform,
                        SkuMapping.material_number == material,
                    )
                )
            )
        if len(own) == 1:
            names[material] = next(iter(own))
        elif own:
            problems.append(f"Mã {material} có nhiều tên SAP khác nhau; sửa ở Ánh xạ SAP")
        else:
            problems.append(f"Mã {material} chưa có tên SAP; thêm ở Ánh xạ SAP")
    return names, problems


def invoice_of(session: Session, order: SalesOrder) -> tuple[SapTaxInvoice, InvoiceLines] | Blocked:
    """The order's invoice and its lines, or why they cannot be worked out."""
    if order.status != states.DELIVERED or not order.do_number:
        return Blocked(
            (
                "Chỉ lập phiếu cho đơn đã giao và đã có DO. Đơn hủy trước khi có DO "
                "chưa có hóa đơn nên không cần biên bản.",
            )
        )
    invoice = session.get(SapTaxInvoice, order.do_number)
    if invoice is None:
        return Blocked(
            ("Đơn chưa có hóa đơn trong zrsd003; đọc zrsd003 của tháng xuất hóa đơn trước",),
            frozenset({"missing_money"}),
        )
    if invoice.net_value_vnd is None or invoice.tax_vnd is None:
        return Blocked(
            ("Hóa đơn chưa có tiền hàng và thuế (nhập trước khi có cột này); đọc lại zrsd003",),
            frozenset({"missing_money"}),
        )
    ref = session.get(SapSoRef, order.so_number) if order.so_number else None
    if ref is None or not ref.items:
        return Blocked(("Đơn chưa có dòng SO từ zrsd001; đọc zrsd001 của đơn này trước",))
    figures = invoice_lines(ref.items, invoice.net_value_vnd, invoice.tax_vnd)
    if isinstance(figures, Blocked):
        return figures
    return invoice, figures


@dataclass(frozen=True)
class DraftLine:
    so_item_no: int
    material_number: str
    quantity: Decimal
    invoice_name: str
    invoice_unit: str


def draft_lines(session: Session, order: SalesOrder) -> list[DraftLine]:
    """The invoice lines the form lets the admin choose from; empty when there is no invoice yet."""
    found = invoice_of(session, order)
    if isinstance(found, Blocked):
        return []
    _, figures = found
    texts = {
        t.material_number: t
        for t in session.scalars(
            select(InvoiceItemText).where(
                InvoiceItemText.material_number.in_(
                    [line.material_number for line in figures.lines]
                )
            )
        )
    }
    return [
        DraftLine(
            line.so_item_no,
            line.material_number,
            line.quantity,
            texts[line.material_number].invoice_name if line.material_number in texts else "",
            texts[line.material_number].invoice_unit if line.material_number in texts else "",
        )
        for line in figures.lines
    ]


def build_preview(
    session: Session,
    settings: Settings,
    order_id: int,
    reason_kind: str,
    selection: Mapping[int, Decimal | int] | None = None,
    buyer: Buyer | None = None,
) -> Preview | Blocked:
    """selection: SO item number -> quantity returned; None returns the whole order."""
    order = session.get(SalesOrder, order_id)
    if order is None:
        return Blocked(("Không thấy đơn hàng",))
    if reason_kind not in REASON_KINDS:
        return Blocked(("Chọn lý do: hủy đơn hàng hoặc trả lại hàng",))
    found = invoice_of(session, order)
    if isinstance(found, Blocked):
        return found
    invoice, figures = found

    reasons: list[str] = []
    codes: set[str] = set()
    materials = [line.material_number for line in figures.lines]
    texts = {
        t.material_number: t
        for t in session.scalars(
            select(InvoiceItemText).where(InvoiceItemText.material_number.in_(materials))
        )
    }
    absent = [m for m in dict.fromkeys(materials) if m not in texts]
    if absent:
        reasons.append(
            "Thiếu tên trên hóa đơn của mã " + ", ".join(absent) + ": tải PDF hóa đơn của đơn này"
        )
        codes.add("missing_texts")
    sap_names, name_problems = _sap_names(session, order, materials)
    reasons += name_problems

    given = buyer or Buyer()
    customer = session.scalar(
        select(CustomerInfo).where(
            CustomerInfo.platform == order.platform,
            CustomerInfo.platform_order_id == order.platform_order_id,
        )
    )
    buyer_name = (given.name or (customer.customer_name if customer else "") or "").strip()
    buyer_address = (given.address or (customer.address if customer else "") or "").strip()
    if not buyer_name:
        reasons.append("Thiếu tên người mua: nhập vào ô tên người mua")
    if not buyer_address:
        reasons.append("Thiếu địa chỉ người mua: nhập vào ô địa chỉ")

    existing = session.scalar(
        select(SalesReturn).where(
            SalesReturn.sales_order_id == order.id, SalesReturn.status == "ISSUED"
        )
    )
    if existing is not None:
        reasons.append(f"Đơn đã có phiếu {existing.doc_no}; hủy phiếu đó trước khi lập lại")
    if not numbering.is_configured(session):
        reasons.append("Chưa nhập số bắt đầu của biên bản: nhập ở trang Phiếu trả hàng")
        codes.add("numbering")

    chosen = returned(
        figures,
        selection
        if selection is not None
        else {line.so_item_no: line.quantity for line in figures.lines},
    )
    taken: list[sale_lines.SaleLine] = []
    if isinstance(chosen, Blocked):
        reasons += chosen.reasons
    else:
        returned_qty = {line.so_item_no: line.return_qty for line in chosen.lines}
        split = sale_lines.split(
            order.items,
            (
                sale_lines.ReturnedQuantity(
                    line.material_number, line.quantity, returned_qty[line.so_item_no]
                )
                for line in figures.lines
            ),
        )
        if isinstance(split, Blocked):
            reasons += split.reasons
        else:
            taken = split
    if reasons:
        return Blocked(tuple(reasons), frozenset(codes))

    amounts = {line.so_item_no: line for line in chosen.lines}
    lines = tuple(
        PreviewLine(
            so_item_no=line.so_item_no,
            material_number=line.material_number,
            sap_name=sap_names[line.material_number],
            invoice_name=texts[line.material_number].invoice_name,
            invoice_unit=texts[line.material_number].invoice_unit,
            stock_unit=texts[line.material_number].stock_unit,
            invoice_qty=line.quantity,
            return_qty=amounts[line.so_item_no].return_qty,
            unit_price=line.unit_price,
            amount_before=line.net,
            amount_returned=amounts[line.so_item_no].amount,
        )
        for line in figures.lines
    )
    platform = session.get(PlatformSetting, order.platform)
    symbol = settings.invoice_symbol(invoice.billing_date)
    fields = {
        "lines": [
            (
                line.so_item_no,
                line.material_number,
                line.invoice_name,
                line.sap_name,
                line.invoice_unit,
                line.stock_unit,
                _plain(line.invoice_qty),
                _plain(line.return_qty),
                line.unit_price,
                line.amount_before,
                line.amount_returned,
            )
            for line in lines
        ],
        "figures": [chosen.net, chosen.tax, figures.net, figures.tax, figures.vat_rate],
        "invoice": [invoice.tax_invoice_doc, invoice.billing_date, invoice.delivery, symbol],
        "sale_lines": [(t.sales_order_item_id, t.quantity, t.customer_paid) for t in taken],
    }
    return Preview(
        order_id=order.id,
        reason_kind=reason_kind,
        lines=lines,
        full_return=chosen.full_return,
        delivery=invoice.delivery,
        tax_invoice_doc=invoice.tax_invoice_doc,
        invoice_symbol=symbol,
        billing_date=invoice.billing_date,
        invoice_net=figures.net,
        invoice_tax=figures.tax,
        vat_rate=figures.vat_rate,
        returned_net=chosen.net,
        returned_tax=chosen.tax,
        buyer_name=buyer_name,
        buyer_address=buyer_address,
        platform_name=PLATFORM_BRAND.get(order.platform)
        or (platform.display_name if platform else order.platform).title(),
        sale_lines=tuple(taken),
        fingerprint=_fingerprint(fields),
    )


def _file_name(prefix: str, sales_return: SalesReturn, suffix: str) -> str:
    number = f"{sales_return.doc_seq:03d}-{sales_return.doc_no.split('/')[1].split(' ')[0]}"
    order_id = sales_return.order.platform_order_id
    return f"{prefix} {number} {order_id}{suffix}".replace("/", "-")


def issue(
    session: Session,
    settings: Settings,
    order_id: int,
    reason_kind: str,
    selection: Mapping[int, Decimal | int] | None,
    buyer: Buyer,
    fingerprint: str,
    actor: str,
) -> SalesReturn:
    """Number, store and render one return. The caller commits. A failure here removes the files
    already written; if the caller's commit fails, it removes `files_of(...)` the same way."""
    # Two admins issuing the same order queue here; the second then sees the first one's return.
    session.scalar(select(SalesOrder.id).where(SalesOrder.id == order_id).with_for_update())
    preview = build_preview(session, settings, order_id, reason_kind, selection, buyer)
    if isinstance(preview, Blocked):
        raise ReturnBlocked(preview)
    if preview.fingerprint != fingerprint:
        raise StaleReturn("Dữ liệu đã đổi, xem lại bản nháp")
    try:
        year, seq, doc_no = numbering.next_number(session, today_vn())
    except numbering.NumberingNotConfigured as exc:
        raise ReturnBlocked(Blocked((str(exc),), frozenset({"numbering"}))) from exc

    sales_return = SalesReturn(
        sales_order_id=order_id,
        reason_kind=preview.reason_kind,
        status="ISSUED",
        doc_year=year,
        doc_seq=seq,
        doc_no=doc_no,
        full_return=preview.full_return,
        delivery=preview.delivery,
        tax_invoice_doc=preview.tax_invoice_doc,
        invoice_symbol=preview.invoice_symbol,
        billing_date=preview.billing_date,
        invoice_net=preview.invoice_net,
        invoice_tax=preview.invoice_tax,
        vat_rate=preview.vat_rate,
        returned_net=preview.returned_net,
        returned_tax=preview.returned_tax,
        buyer_name=preview.buyer_name,
        buyer_address=preview.buyer_address,
        platform_name=preview.platform_name,
        issued_by=actor,
    )
    sales_return.lines = [
        SalesReturnLine(
            line_no=number,
            so_item_no=line.so_item_no,
            material_number=line.material_number,
            sap_name=line.sap_name,
            invoice_name=line.invoice_name,
            invoice_unit=line.invoice_unit,
            stock_unit=line.stock_unit,
            invoice_qty=line.invoice_qty,
            return_qty=line.return_qty,
            unit_price=line.unit_price,
            amount_before=line.amount_before,
            amount_returned=line.amount_returned,
        )
        for number, line in enumerate(preview.lines, start=1)
    ]
    sales_return.sale_lines = [
        SalesReturnSaleLine(
            sales_order_item_id=line.sales_order_item_id,
            quantity=line.quantity,
            customer_paid=line.customer_paid,
        )
        for line in preview.sale_lines
    ]
    session.add(sales_return)
    try:
        # Before any file is written: a second issue of the same order stops here, with no file.
        session.flush()
    except IntegrityError as exc:
        if getattr(getattr(exc.orig, "diag", None), "constraint_name", None) == ONE_ISSUED_INDEX:
            raise ReturnBlocked(Blocked(("Đơn đã có phiếu trả hàng chưa hủy",))) from exc
        raise

    written: list[GeneratedFile] = []
    try:
        docx = save_generated_bytes(
            session,
            settings,
            invoice_adjustment_doc.render(sales_return),
            ".docx",
            _file_name("BBDC", sales_return, ".docx"),
            KIND_DOCX,
            actor,
        )
        written.append(docx)
        xlsx = save_generated_bytes(
            session,
            settings,
            return_request_workbook.render(sales_return),
            ".xlsx",
            _file_name("RRG", sales_return, ".xlsx"),
            KIND_XLSX,
            actor,
        )
        written.append(xlsx)
        sales_return.docx_file_id, sales_return.xlsx_file_id = docx.id, xlsx.id
        states.log_event(
            session,
            actor,
            "sales_return_issued",
            platform=sales_return.order.platform,
            platform_order_id=sales_return.order.platform_order_id,
            detail={
                "return_id": sales_return.id,
                "doc_no": doc_no,
                "reason": preview.reason_kind,
                "full_return": preview.full_return,
                "returned_net": preview.returned_net,
                "returned_tax": preview.returned_tax,
            },
        )
        session.flush()
    except Exception:
        remove_files(written)
        raise
    return sales_return


def files_of(session: Session, sales_return: SalesReturn) -> list[GeneratedFile]:
    ids = [i for i in (sales_return.docx_file_id, sales_return.xlsx_file_id) if i]
    return (
        list(session.scalars(select(GeneratedFile).where(GeneratedFile.id.in_(ids)))) if ids else []
    )


def remove_files(records: list[GeneratedFile]) -> None:
    """Delete files written by a transaction that did not commit."""
    for record in records:
        Path(record.stored_path).unlink(missing_ok=True)


def void(session: Session, return_id: int, reason: str, actor: str) -> SalesReturn:
    """Cancel an issued return. The number and the files stay; the order can be returned again."""
    text = (reason or "").strip()
    if not text:
        raise ValueError("Nhập lý do hủy phiếu")
    sales_return = session.scalar(
        select(SalesReturn)
        .where(SalesReturn.id == return_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if sales_return is None:
        raise ValueError("Không thấy phiếu trả hàng")
    if sales_return.status != "ISSUED":
        raise ValueError("Phiếu này đã hủy")
    sales_return.status = "VOID"
    sales_return.voided_by = actor
    sales_return.voided_at = datetime.now(UTC)
    sales_return.void_reason = text
    states.log_event(
        session,
        actor,
        "sales_return_voided",
        platform=sales_return.order.platform,
        platform_order_id=sales_return.order.platform_order_id,
        detail={"return_id": sales_return.id, "doc_no": sales_return.doc_no},
    )
    session.flush()
    return sales_return
