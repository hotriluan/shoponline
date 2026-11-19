"""Rows for the accountants' Shop Online history file: preview, download, confirm as pasted.

A downloaded file remembers its orders (sales_history_file_order). Confirming the file moves
them into sales_history_exported, so the next download leaves them out; unconfirming takes back
exactly what that file confirmed.
"""

from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import delete, func, literal, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from shoponline.clock import today_vn
from shoponline.db.models import (
    AppUser,
    GeneratedFile,
    SalesHistoryExported,
    SalesHistoryFileOrder,
)
from shoponline.domain import states
from shoponline.exports.sales_history_workbook import (
    CUSTOMER,
    REPORT_NAME,
    SETTLEMENT,
    TAX_INVOICE,
    HistoryRows,
    build_history_workbook,
    collect_rows,
    history_draft_file_name,
    history_file_name,
    is_draftable,
)
from shoponline.importers.excel_table import FileRejected
from shoponline.maintenance import retention
from shoponline.reconcile.report_ingest import ingest_settlement
from shoponline.sapjobs.queue import DuplicateJob
from shoponline.sapjobs.report_requests import request_zrsd003
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
from shoponline.web.uploads import UploadRejected, save_generated, save_upload

router = APIRouter()
KIND = "sales_history"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
RECENT_FILES = 20


def _fix_link(kind: str, batch_id: int) -> str | None:
    if kind == CUSTOMER:
        return f"/customers?batch_id={batch_id}"
    if kind == REPORT_NAME:
        return "/report-names?missing=true"
    if kind == TAX_INVOICE:
        return "#tax-invoice"
    if kind == SETTLEMENT:
        return "#settlement"
    return None


def _invoice_range(result: HistoryRows) -> tuple[date, date] | None:
    """Billing dates that cover every order waiting for its invoice: an invoice is issued after
    the DO, which comes after the order, so billing date >= order date."""
    waiting = [
        b.ordered_at.date() for b in result.blocked if any(r.kind == TAX_INVOICE for r in b.reasons)
    ]
    return (min(waiting), today_vn()) if waiting else None


def _settlement_range(result: HistoryRows) -> tuple[date, date] | None:
    """Order dates to export from the platforms: settlement comes after the order."""
    waiting = [
        b.ordered_at.date() for b in result.blocked if any(r.kind == SETTLEMENT for r in b.reasons)
    ]
    return (min(waiting), today_vn()) if waiting else None


def _only_settlement(blocked) -> bool:
    return all(r.kind == SETTLEMENT for r in blocked.reasons)


def _recent_files(db: Session) -> list[dict]:
    files = db.scalars(
        select(GeneratedFile)
        .where(GeneratedFile.kind == KIND)
        .order_by(GeneratedFile.created_at.desc(), GeneratedFile.id.desc())
        .limit(RECENT_FILES)
    ).all()
    ids = [f.id for f in files]
    in_file = dict(
        db.execute(
            select(SalesHistoryFileOrder.generated_file_id, func.count())
            .where(SalesHistoryFileOrder.generated_file_id.in_(ids))
            .group_by(SalesHistoryFileOrder.generated_file_id)
        ).all()
    )
    confirmed = dict(
        db.execute(
            select(SalesHistoryExported.generated_file_id, func.count())
            .where(SalesHistoryExported.generated_file_id.in_(ids))
            .group_by(SalesHistoryExported.generated_file_id)
        ).all()
    )
    return [
        dict(
            file=f,
            orders=in_file.get(f.id, 0),
            confirmed=confirmed.get(f.id, 0),
            stored=Path(f.stored_path).is_file(),
        )
        for f in files
    ]


@router.get("/sales-history")
def sales_history_page(
    request: Request,
    until: date | None = None,
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    until = until or today_vn()
    result = collect_rows(db, until)
    rows = [
        dict(order=b, reasons=[(r.text, _fix_link(r.kind, b.order_batch_id)) for r in b.reasons])
        for b in result.blocked
    ]
    blocked = [row for row in rows if not _only_settlement(row["order"])]
    waiting_settlement = [row for row in rows if _only_settlement(row["order"])]
    settlement_count = sum(any(r.kind == SETTLEMENT for r in b.reasons) for b in result.blocked)
    invoice_range = _invoice_range(result)
    waiting_invoice = sum(any(r.kind == TAX_INVOICE for r in b.reasons) for b in result.blocked)
    return render(
        request,
        "sales_history.html",
        user,
        until=until,
        invoice_range=invoice_range,
        waiting_invoice=waiting_invoice,
        robot_refusal=robot_refusal(sap_config(request, db)) if invoice_range else None,
        orders=len(result.order_ids),
        draft_orders=len(result.order_ids) + sum(is_draftable(b.reasons) for b in result.blocked),
        lines=len(result.rows),
        blocked=blocked,
        waiting_settlement=waiting_settlement,
        settlement_count=settlement_count,
        settlement_range=_settlement_range(result),
        files=_recent_files(db),
    )


@router.get("/sales-history/file")
def download_history_file(
    request: Request,
    until: date | None = None,
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    """Computed again from scratch, so the file holds exactly the orders recorded for it.

    Blocked orders are left out and stay pending, so they go into a later file once complete.
    """
    until = until or today_vn()
    back = f"/sales-history?until={until.isoformat()}"
    result = collect_rows(db, until)
    if not result.rows:
        if result.blocked:
            message = "Chưa có đơn nào sẵn sàng xuất: các đơn còn lại đang chờ hoặc bị chặn."
        else:
            message = "Không có đơn nào chờ xuất."
        flash(request, message, "error")
        return redirect(back)
    file_name = history_file_name(today_vn())
    record = save_generated(
        db,
        request.app.state.settings,
        build_history_workbook(result.rows),
        file_name,
        KIND,
        user.username,
    )
    db.add_all(
        SalesHistoryFileOrder(generated_file_id=record.id, sales_order_id=order_id)
        for order_id in result.order_ids
    )
    db.commit()
    return FileResponse(record.stored_path, filename=file_name, media_type=XLSX)


@router.get("/sales-history/draft")
def download_draft_file(
    request: Request,
    until: date | None = None,
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    """A preview that also holds the orders waiting for an invoice or settlement.

    Nothing is stored: no generated file, no order record, so it cannot be confirmed as pasted.
    """
    until = until or today_vn()
    result = collect_rows(db, until, draft=True)
    if not result.rows:
        flash(request, "Không có đơn nào để xuất nháp.", "error")
        return redirect(f"/sales-history?until={until.isoformat()}")
    buffer = BytesIO()
    build_history_workbook(result.rows, draft=True).save(buffer)
    name = quote(history_draft_file_name(today_vn()))
    return Response(
        buffer.getvalue(),
        media_type=XLSX,
        headers={"Content-Disposition": f"attachment; filename*=utf-8''{name}"},
    )


@router.post("/sales-history/read-zrsd003")
def read_zrsd003(
    request: Request,
    until: date = Form(...),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    """Ask the robot to read zrsd003 over the billing dates of the orders waiting for invoices."""
    back = f"/sales-history?until={until.isoformat()}"
    invoice_range = _invoice_range(collect_rows(db, until))
    if invoice_range is None:
        flash(request, "Không có đơn nào chờ Tax Invoice Doc.", "error")
        return redirect(back)
    config = sap_config(request, db)
    refusal = robot_refusal(config)
    if refusal:
        flash(request, refusal, "error")
        return redirect(back)
    start, end = invoice_range
    try:
        job = request_zrsd003(db, config.target, start, end, user.username)
    except DuplicateJob as exc:
        flash(request, str(exc), "error")
        return redirect(back)
    db.commit()
    flash(request, f"Robot sẽ đọc zrsd003 từ {start:%d/%m/%Y} đến {end:%d/%m/%Y} (việc #{job.id}).")
    return redirect(back)


@router.post("/sales-history/settlement")
async def upload_settlement(
    request: Request,
    until: date = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    """Read a Shopee or TikTok settlement file once: it holds the seller's login and, for TikTok,
    withdrawal history, so only order ids, amounts and dates are kept."""
    settings = request.app.state.settings
    back = f"/sales-history?until={until.isoformat()}"
    new_file = None
    try:
        record, created = await save_upload(
            settings, file, kind="settlement", platform=None, actor=user.username
        )
        new_file = record.stored_path if created else None
        result = ingest_settlement(db, record, user.username)
    except (UploadRejected, FileRejected) as exc:
        db.rollback()
        retention.discard_unused(db, settings, [new_file])
        flash(request, str(exc), "error")
        return redirect(back)
    except Exception:
        db.rollback()
        retention.discard_unused(db, settings, [new_file])
        raise
    db.commit()
    retention.discard_unused(db, settings, [record.stored_path])
    name = {"SHOPEE": "Shopee", "TIKTOK": "TikTok"}[result.platform]
    flash(
        request,
        f"Tiền vô {name}: {result.kept} giao dịch của {result.orders} đơn "
        f"({result.new} mới, {result.updated} đổi, {result.unchanged} không đổi), "
        f"bỏ qua {len(result.skipped)} dòng.",
    )
    if result.skipped:
        shown = result.skipped[:10]
        more = len(result.skipped) - len(shown)
        detail = "; ".join(shown) + (f"; … và {more} dòng khác" if more > 0 else "")
        flash(request, f"Dòng bị bỏ qua: {detail}", "error")
    return redirect(back)


def _history_file(db: Session, file_id: int) -> GeneratedFile:
    record = db.get(GeneratedFile, file_id)
    if record is None or record.kind != KIND:
        raise HTTPException(404, "Không có file này")
    return record


@router.get("/sales-history/files/{file_id}")
def download_saved_file(
    request: Request,
    file_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    """The file exactly as downloaded then, not rebuilt."""
    record = _history_file(db, file_id)
    if not Path(record.stored_path).is_file():
        flash(request, "File đã bị xóa sau khi xác nhận đã dán.", "error")
        return redirect("/sales-history")
    return FileResponse(record.stored_path, filename=record.file_name, media_type=XLSX)


@router.post("/sales-history/files/{file_id}/confirm")
def confirm_file(
    request: Request,
    file_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    record = _history_file(db, file_id)
    in_file = select(
        SalesHistoryFileOrder.sales_order_id,
        literal(record.id),
        literal(user.username),
    ).where(SalesHistoryFileOrder.generated_file_id == record.id)
    total = db.scalar(select(func.count()).select_from(in_file.subquery()))
    # An order already confirmed through another file keeps that file (primary key).
    confirmed = len(
        db.scalars(
            insert(SalesHistoryExported)
            .from_select(["sales_order_id", "generated_file_id", "confirmed_by"], in_file)
            .on_conflict_do_nothing(index_elements=["sales_order_id"])
            .returning(SalesHistoryExported.sales_order_id)
        ).all()
    )
    skipped = total - confirmed
    states.log_event(
        db,
        user.username,
        "sales_history_confirmed",
        detail={"file_id": record.id, "confirmed": confirmed, "skipped": skipped},
    )
    db.commit()
    # This file, and any other file sharing its orders, goes once all its orders are confirmed.
    sharing = select(SalesHistoryFileOrder.sales_order_id).where(
        SalesHistoryFileOrder.generated_file_id == record.id
    )
    paths = db.scalars(
        select(GeneratedFile.stored_path)
        .join(SalesHistoryFileOrder, SalesHistoryFileOrder.generated_file_id == GeneratedFile.id)
        .where(SalesHistoryFileOrder.sales_order_id.in_(sharing))
        .distinct()
    ).all()
    retention.discard_unused(db, request.app.state.settings, paths)
    flash(
        request,
        f"Đã xác nhận {confirmed} đơn, bỏ qua {skipped} đơn đã xác nhận ở file khác.",
    )
    return redirect("/sales-history")


@router.post("/sales-history/files/{file_id}/unconfirm")
def unconfirm_file(
    request: Request,
    file_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    record = _history_file(db, file_id)
    removed = db.execute(
        delete(SalesHistoryExported).where(SalesHistoryExported.generated_file_id == record.id)
    ).rowcount
    states.log_event(
        db,
        user.username,
        "sales_history_unconfirmed",
        detail={"file_id": record.id, "removed": removed},
    )
    db.commit()
    flash(request, f"Đã gỡ xác nhận {removed} đơn; các đơn này sẽ có lại trong lần xuất sau.")
    return redirect("/sales-history")
