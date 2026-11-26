"""Money Lazada paid out per order, typed in by an admin (Lazada's file has no order id)."""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.accounting import manual_settlement as manual
from shoponline.accounting import settlement_invoice_file as invoice_file
from shoponline.clock import today_vn
from shoponline.db.models import AppUser, SalesOrder
from shoponline.importers.excel_table import FileRejected
from shoponline.returns import flags
from shoponline.web.app import (
    autosave_reply,
    current_user,
    flash,
    get_db,
    is_autosave,
    redirect,
    render,
    require_admin,
)
from shoponline.web.uploads import ALLOWED_SUFFIXES, MAX_UPLOAD_BYTES

router = APIRouter()
PAGE = "/settlements/lazada"


def _month(text: str) -> date | None:
    try:
        return datetime.strptime(text, "%Y-%m").date()
    except ValueError:
        return None


def _back(month: str) -> str:
    return f"{PAGE}?month={month}" if _month(month) else PAGE


def _flags_by_order_id(db: Session, order_ids: set[str]) -> dict[str, flags.ReturnFlag]:
    """Lazada order id -> its return flag, for the orders on the page that have one."""
    if not order_ids:
        return {}
    ids = dict(
        db.execute(
            select(SalesOrder.id, SalesOrder.platform_order_id).where(
                SalesOrder.platform == manual.PLATFORM,
                SalesOrder.platform_order_id.in_(order_ids),
            )
        ).all()
    )
    return {ids[order_id]: flag for order_id, flag in flags.of(db, ids).items()}


def _page(
    request: Request,
    db: Session,
    user: AppUser,
    month: str,
    paste: str = "",
    preview=None,
    file_preview=None,
    carry: str = "",
):
    pending = manual.pending_orders(db, _month(month))
    entered = manual.entered(db)
    shown = {o.platform_order_id for o in pending}
    shown |= {r["line"].order_id for r in preview or [] if r["line"].order_id}
    shown |= {r.order_id for r in file_preview or [] if r.order_id}
    return render(
        request,
        "lazada_settlements.html",
        user,
        month=month if _month(month) else "",
        pending=pending,
        invoices=manual.invoice_numbers(db, pending),
        entered=entered,
        entered_invoices=manual.invoice_numbers_by_order(
            db, [s.platform_order_id for s in entered]
        ),
        today=today_vn(),
        paste=paste,
        preview=preview,
        file_preview=file_preview,
        carry=carry,
        flags=_flags_by_order_id(db, shown),
    )


@router.get(PAGE)
def lazada_settlements(
    request: Request,
    month: str = "",
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    return _page(request, db, user, month)


@router.post(PAGE + "/set")
def set_settlement(
    request: Request,
    order_id: str = Form(...),
    amount: str = Form(...),
    settled_on: str = Form(...),
    month: str = Form(""),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    try:
        value = manual.parse_amount(amount)
        day = datetime.strptime(settled_on, "%Y-%m-%d").date()
        manual.set_amount(db, order_id, value, day, user.username)
    except ValueError as exc:  # SettlementError, or a date the browser sent in another shape
        if is_autosave(request):
            return autosave_reply(str(exc), ok=False)
        flash(request, f"Đơn {order_id}: {exc}", "error")
        return redirect(_back(month))
    db.commit()
    if is_autosave(request):
        return autosave_reply(f"Đã lưu {value:,} đồng")
    flash(request, f"Đã lưu tiền về {value:,} đồng cho đơn {order_id}.")
    return redirect(_back(month))


@router.post(PAGE + "/remove")
def remove_settlement(
    request: Request,
    order_id: str = Form(...),
    month: str = Form(""),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    if manual.remove(db, order_id, user.username):
        db.commit()
        flash(request, f"Đã xóa tiền về của đơn {order_id}.")
    else:
        flash(request, f"Đơn {order_id} chưa có tiền nhập tay.", "error")
    return redirect(_back(month))


def _checked(db: Session, text: str) -> list[dict]:
    """Every pasted line with the reason it cannot be saved ('' when it can)."""
    today = today_vn()
    rows = []
    for line in manual.parse_paste(text):
        error = line.error
        if not error:
            try:
                manual.check(db, line.order_id, line.amount, line.settled_on, today)
            except manual.SettlementError as exc:
                error = str(exc)
        rows.append({"line": line, "error": error})
    return rows


@router.post(PAGE + "/preview")
def preview_paste(
    request: Request,
    paste: str = Form(""),
    month: str = Form(""),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    rows = _checked(db, paste)
    if not rows:
        flash(request, "Chưa dán dòng nào.", "error")
        return redirect(_back(month))
    return _page(request, db, user, month, paste, rows)


@router.post(PAGE + "/save-paste")
def save_paste(
    request: Request,
    paste: str = Form(""),
    month: str = Form(""),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    """Save every pasted line that passes the checks again; the rest are named and left out."""
    rows = _checked(db, paste)
    saved = 0
    for row in rows:
        line = row["line"]
        if not row["error"]:
            manual.set_amount(db, line.order_id, line.amount, line.settled_on, user.username)
            saved += 1
    db.commit()
    skipped = [f"dòng {r['line'].line_no}: {r['error']}" for r in rows if r["error"]]
    flash(request, f"Đã lưu {saved} đơn." + (f" Bỏ qua {len(skipped)} dòng." if skipped else ""))
    if skipped:
        flash(request, "\n".join(skipped), "error")
    return redirect(_back(month))


@router.post(PAGE + "/preview-file")
async def preview_file(
    request: Request,
    file: UploadFile = File(...),
    month: str = Form(""),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    """Read the accounting file and show each line with its order; nothing is stored."""
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        if not (file.filename or "").lower().endswith(ALLOWED_SUFFIXES):
            raise FileRejected("Chỉ nhận file .xlsx")
        if len(data) > MAX_UPLOAD_BYTES:
            raise FileRejected("File lớn hơn 20 MB")
        if not data:
            raise FileRejected("File rỗng")
        lines = invoice_file.read_file(data)
        if not lines:
            raise FileRejected("File không có dòng nào")
    except FileRejected as exc:
        flash(request, str(exc), "error")
        return redirect(_back(month))
    rows = invoice_file.resolve(db, lines)
    return _page(request, db, user, month, file_preview=rows, carry=invoice_file.to_carry(lines))


@router.post(PAGE + "/save-file")
def save_file(
    request: Request,
    carry: str = Form(""),
    month: str = Form(""),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    """Check every previewed line again and save the good ones; the rest are named and left out."""
    try:
        lines = invoice_file.from_carry(carry)
    except ValueError:
        flash(request, "Dữ liệu xem trước không đọc được, hãy tải lại file.", "error")
        return redirect(_back(month))
    rows = invoice_file.resolve(db, lines)
    saved = 0
    for row in rows:
        if not row.error:
            manual.set_amount(db, row.order_id, row.line.amount, row.line.settled_on, user.username)
            saved += 1
    db.commit()
    skipped = [f"dòng {r.line.line_no}: {r.error}" for r in rows if r.error]
    flash(request, f"Đã lưu {saved} đơn." + (f" Bỏ qua {len(skipped)} dòng." if skipped else ""))
    if skipped:
        flash(request, "\n".join(skipped), "error")
    return redirect(_back(month))
