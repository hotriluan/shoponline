"""Invoice adjustments for returned orders: draft, issue, list, download, void.

Everything that shows or writes the buyer's name and address is admin-only, and so are the two
files: they are the only place that name and address outlive the 90-day customer data rule.
"""

from __future__ import annotations

import asyncio
from calendar import monthrange
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.clock import today_vn
from shoponline.db.models import (
    AppUser,
    GeneratedFile,
    OrderBatch,
    SalesOrder,
    SalesReturn,
    SapTaxInvoice,
)
from shoponline.exports.invoice_adjustment_doc import DOCX_MEDIA_TYPE
from shoponline.importers.excel_table import FileRejected
from shoponline.importers.invoice_pdf import MAX_BYTES, read_invoice_pdf
from shoponline.returns import master, numbering, service
from shoponline.returns.amounts import Blocked
from shoponline.sapjobs.queue import DuplicateJob
from shoponline.sapjobs.report_requests import MAX_READ_DAYS, request_zrsd003, split_range
from shoponline.web.app import (
    current_user,
    flash,
    get_db,
    redirect,
    render,
    require_admin,
    robot_refusal,
    sap_config,
)
from shoponline.web.pagination import paginate

router = APIRouter()
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF_SECONDS = 30
REASONS = {"CANCEL": "Hủy đơn hàng", "RETURN": "Trả lại hàng"}


def _order(db: Session, order_id: int) -> SalesOrder:
    order = db.get(SalesOrder, order_id)
    if order is None:
        raise HTTPException(404, "Không có đơn này")
    return order


def _quantities(form) -> tuple[dict[int, Decimal], dict[int, str], str | None]:
    """The returned quantity of each line from the form fields qty_<SO item number>."""
    chosen: dict[int, Decimal] = {}
    raw: dict[int, str] = {}
    error = None
    for key, value in form.multi_items():
        if not key.startswith("qty_") or not key[4:].isdigit():
            continue
        item_no, text = int(key[4:]), str(value).strip().replace(",", ".")
        raw[item_no] = text
        try:
            chosen[item_no] = Decimal(text or "0")
        except InvalidOperation:
            error = f"Số lượng trả của dòng {item_no} không phải số"
    return chosen, raw, error


def _form_page(
    request: Request,
    db: Session,
    user: AppUser,
    order: SalesOrder,
    *,
    reason: str = "CANCEL",
    raw_quantities: dict[int, str] | None = None,
    buyer: service.Buyer | None = None,
    quantity_error: str | None = None,
    confirm: master.LearnResult | None = None,
):
    settings = request.app.state.settings
    chosen = None
    if raw_quantities is not None and not quantity_error:
        chosen = {n: Decimal(v or "0") for n, v in raw_quantities.items()}
    draft = service.build_preview(db, settings, order.id, reason, chosen, buyer)
    lines = service.draft_lines(db, order)
    shown = {
        line.so_item_no: (raw_quantities or {}).get(
            line.so_item_no, format(line.quantity.normalize(), "f")
        )
        for line in lines
    }
    preview = draft if isinstance(draft, service.Preview) else None
    blocked = draft if isinstance(draft, Blocked) else None
    return render(
        request,
        "return_form.html",
        user,
        order=order,
        reason=reason,
        reasons=REASONS,
        lines=lines,
        quantities=shown,
        quantity_error=quantity_error,
        preview=preview,
        blocked=blocked,
        missing_texts=master.missing_materials(db, order),
        buyer_name=(buyer.name if buyer and buyer.name else None)
        or (preview.buyer_name if preview else ""),
        buyer_address=(buyer.address if buyer and buyer.address else None)
        or (preview.buyer_address if preview else ""),
        confirm=confirm,
        max_mb=MAX_BYTES // 1024 // 1024,
    )


@router.get("/orders/{order_id}/return")
def return_form(
    request: Request,
    order_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    order = _order(db, order_id)
    buyer = _default_buyer(db, order)
    return _form_page(request, db, user, order, buyer=buyer)


def _default_buyer(db: Session, order: SalesOrder) -> service.Buyer:
    from shoponline.db.models import CustomerInfo

    customer = db.scalar(
        select(CustomerInfo).where(
            CustomerInfo.platform == order.platform,
            CustomerInfo.platform_order_id == order.platform_order_id,
        )
    )
    if customer is None:
        return service.Buyer()
    return service.Buyer(customer.customer_name or "", customer.address or "")


@router.post("/orders/{order_id}/return/preview")
async def return_preview(
    request: Request,
    order_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    """Redraw the draft after the admin changed the reason, a quantity or the buyer. A POST, so
    the buyer's name and address never travel in a URL (and so never reach an access log)."""
    order = _order(db, order_id)
    form = await request.form()
    _, raw, error = _quantities(form)
    return _form_page(
        request,
        db,
        user,
        order,
        reason=str(form.get("reason", "CANCEL")),
        raw_quantities=raw,
        buyer=service.Buyer(str(form.get("buyer_name", "")), str(form.get("buyer_address", ""))),
        quantity_error=error,
    )


@router.post("/orders/{order_id}/return")
async def issue_return(
    request: Request,
    order_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    order = _order(db, order_id)
    form = await request.form()
    chosen, raw, error = _quantities(form)
    reason = str(form.get("reason", ""))
    buyer = service.Buyer(str(form.get("buyer_name", "")), str(form.get("buyer_address", "")))

    def back(message: str):
        flash(request, message, "error")
        return _form_page(
            request, db, user, order, reason=reason or "CANCEL", raw_quantities=raw, buyer=buyer
        )

    if error:
        return back(error)
    settings = request.app.state.settings
    try:
        created = service.issue(
            db,
            settings,
            order.id,
            reason,
            chosen,
            buyer,
            str(form.get("fingerprint", "")),
            user.username,
        )
    except service.ReturnBlocked as exc:
        db.rollback()
        return back("Chưa lập được phiếu: " + exc.blocked.reason)
    except service.StaleReturn as exc:
        db.rollback()
        return back(str(exc))
    written = service.files_of(db, created)
    return_id, doc_no = created.id, created.doc_no
    try:
        db.commit()
    except Exception:
        db.rollback()
        service.remove_files(written)
        raise
    flash(request, f"Đã lập phiếu {doc_no}.")
    return redirect(f"/returns/{return_id}")


@router.post("/orders/{order_id}/return/invoice-pdf")
async def upload_invoice_pdf(
    request: Request,
    order_id: int,
    pdf: UploadFile = File(...),
    confirm_overwrite: str = Form(""),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    """Learn how Bkav printed this order's items. The PDF is read and thrown away."""
    order = _order(db, order_id)
    back = f"/orders/{order_id}/return"
    announced = request.headers.get("content-length")
    if announced and announced.isdigit() and int(announced) > MAX_BYTES + 64 * 1024:
        flash(request, f"File PDF quá {MAX_BYTES // 1024 // 1024} MB.", "error")
        return redirect(back)
    data = await pdf.read(MAX_BYTES + 1)
    try:
        # The file is untrusted: parsed in a worker thread, and given up on after a time limit.
        invoice = await asyncio.wait_for(
            run_in_threadpool(read_invoice_pdf, data), timeout=PDF_SECONDS
        )
        result = master.learn_from_pdf(
            db,
            order,
            invoice,
            user.username,
            request.app.state.settings,
            confirm_overwrite=confirm_overwrite == "1",
        )
    except TimeoutError:
        flash(request, "Đọc PDF quá lâu nên đã dừng. Thử file khác.", "error")
        return redirect(back)
    except FileRejected as exc:
        db.rollback()
        flash(request, str(exc), "error")
        return redirect(back)
    if result.needs_confirmation:
        return _form_page(request, db, user, order, buyer=_default_buyer(db, order), confirm=result)
    db.commit()
    flash(
        request,
        f"Đã ghi tên trên hóa đơn: thêm {len(result.added)} mã, "
        f"{len(result.differing)} mã đổi tên, {len(result.unchanged)} mã giữ nguyên.",
    )
    return redirect(back)


@router.post("/orders/{order_id}/return/read-zrsd003")
def read_zrsd003_for_return(
    request: Request,
    order_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    """Ask the robot to read zrsd003 around this order's invoice, so its money is stored."""
    order = _order(db, order_id)
    back = f"/orders/{order_id}/return"
    config = sap_config(request, db)
    refusal = robot_refusal(config)
    if refusal:
        flash(request, refusal, "error")
        return redirect(back)
    first, last = _invoice_window(db, order)
    pieces = split_range(first, last)
    jobs = []
    for start, end in pieces:
        try:
            jobs.append(request_zrsd003(db, config.target, start, end, user.username))
        except DuplicateJob as exc:
            flash(request, str(exc), "error")
    if not jobs:
        return redirect(back)
    db.commit()
    note = f" ({len(jobs)} việc, mỗi việc tối đa {MAX_READ_DAYS} ngày)" if len(pieces) > 1 else ""
    flash(request, f"Robot sẽ đọc zrsd003 từ {first:%d/%m/%Y} đến {last:%d/%m/%Y}{note}.")
    return redirect(back)


def _invoice_window(db: Session, order: SalesOrder) -> tuple[date, date]:
    """The invoice month; for an order with no invoice yet, its batch day up to today."""
    today = today_vn()
    invoice = db.get(SapTaxInvoice, order.do_number) if order.do_number else None
    if invoice is not None:
        first = invoice.billing_date.replace(day=1)
        return first, min(first.replace(day=monthrange(first.year, first.month)[1]), today)
    batch = db.get(OrderBatch, order.order_batch_id)
    return min(batch.processing_date, today), today


@router.get("/returns")
def returns_list(
    request: Request, db: Session = Depends(get_db), user: AppUser = Depends(current_user)
):
    page = paginate(
        request,
        db,
        select(SalesReturn)
        .join(SalesOrder, SalesOrder.id == SalesReturn.sales_order_id)
        .order_by(SalesReturn.id.desc()),
        SalesReturn.doc_no,
        SalesOrder.platform_order_id,
        SalesReturn.tax_invoice_doc,
    )
    return render(
        request,
        "returns.html",
        user,
        page=page,
        rows=page.items,
        reasons=REASONS,
        numbered=numbering.is_configured(db),
        this_year=today_vn().year,
    )


@router.post("/returns/start-number")
def start_number(
    request: Request,
    start: int = Form(...),
    year: int = Form(...),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    """Enter the number of the first document, once; the number cannot be changed afterwards."""
    try:
        numbering.set_start(db, year, start, user.username)
    except ValueError as exc:
        db.rollback()
        flash(request, str(exc), "error")
        return redirect("/returns")
    db.commit()
    flash(request, f"Đã đặt số bắt đầu: phiếu đầu tiên của năm {year} sẽ là số {start:03d}.")
    return redirect("/returns")


def _return(db: Session, return_id: int) -> SalesReturn:
    found = db.get(SalesReturn, return_id)
    if found is None:
        raise HTTPException(404, "Không có phiếu này")
    return found


@router.get("/returns/{return_id}")
def return_detail(
    request: Request,
    return_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    found = _return(db, return_id)
    return render(request, "return_detail.html", user, sr=found, reasons=REASONS)


def _download(db: Session, return_id: int, which: str):
    found = _return(db, return_id)
    file_id = found.docx_file_id if which == "docx" else found.xlsx_file_id
    record = db.get(GeneratedFile, file_id) if file_id else None
    if record is None or not Path(record.stored_path).is_file():
        raise HTTPException(404, "File của phiếu không còn trên máy chủ")
    media = DOCX_MEDIA_TYPE if which == "docx" else XLSX
    return FileResponse(record.stored_path, filename=record.file_name, media_type=media)


@router.get("/returns/{return_id}/docx")
def download_docx(
    return_id: int, db: Session = Depends(get_db), user: AppUser = Depends(require_admin)
):
    return _download(db, return_id, "docx")


@router.get("/returns/{return_id}/xlsx")
def download_xlsx(
    return_id: int, db: Session = Depends(get_db), user: AppUser = Depends(require_admin)
):
    return _download(db, return_id, "xlsx")


@router.post("/returns/{return_id}/void")
def void_return(
    request: Request,
    return_id: int,
    reason: str = Form(""),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    try:
        voided = service.void(db, return_id, reason, user.username)
    except ValueError as exc:
        db.rollback()
        flash(request, str(exc), "error")
        return redirect(f"/returns/{return_id}")
    db.commit()
    flash(request, f"Đã hủy phiếu {voided.doc_no}. Số này không được dùng lại.")
    return redirect(f"/returns/{return_id}")
