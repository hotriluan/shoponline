"""Rows for the accountants' Shop Online history file: preview, download, confirm as pasted.

A downloaded file remembers its orders (sales_history_file_order) and its return rows
(sales_history_file_return). Confirming the file moves them into sales_history_exported and
sales_return_history_exported, so the next download leaves them out; unconfirming takes back
exactly what that file confirmed.
"""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Sequence
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy import and_, delete, exists, func, literal, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from shoponline.clock import today_vn
from shoponline.db.models import (
    AppUser,
    CustomerInfo,
    GeneratedFile,
    SalesHistoryExported,
    SalesHistoryFileOrder,
    SalesHistoryFileReturn,
    SalesOrder,
    SalesReturn,
    SalesReturnHistoryExported,
)
from shoponline.domain import states
from shoponline.exports.sales_history_workbook import (
    ALL_SHEET,
    CUSTOMER,
    REPORT_NAME,
    SETTLEMENT,
    TAX_INVOICE,
    VOID,
    HistoryRows,
    build_history_workbook,
    collect_all_rows,
    collect_rows,
    history_all_file_name,
    history_draft_file_name,
    history_file_name,
    is_draftable,
)
from shoponline.importers.excel_table import FileRejected
from shoponline.maintenance import retention
from shoponline.reconcile.report_ingest import ingest_settlement
from shoponline.sapjobs.queue import DuplicateJob
from shoponline.sapjobs.report_requests import (
    MAX_READ_DAYS,
    request_zrsd003,
    split_range,
)
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
from shoponline.web.pagination import Page, paginate
from shoponline.web.uploads import UploadRejected, save_generated, save_upload

router = APIRouter()
KIND = "sales_history"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MONTH = r"^\d{4}-(0[1-9]|1[0-2])$"  # YYYY-MM, as sent by <input type="month">


def _month_bounds(month: str | None) -> tuple[str, date, date]:
    """The chosen order month as YYYY-MM, its first and its last day.

    Without a choice it is last month: the file for a month is made early in the next one.
    """
    if month is None:
        first = (today_vn().replace(day=1) - timedelta(days=1)).replace(day=1)
    else:
        first = date.fromisoformat(f"{month}-01")
    last = first.replace(day=monthrange(first.year, first.month)[1])
    return first.strftime("%Y-%m"), first, last


def _back(month: str) -> str:
    return f"/sales-history?month={month}"


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


def _invoice_range(result: HistoryRows, first_day: date) -> tuple[date, date] | None:
    """Billing dates from the first day of the chosen month (or an older order still waiting)
    up to today: an invoice is issued after the DO, which comes after the order, so the invoice
    of an order placed at the end of the month is billed in the next one."""
    waiting = [
        b.ordered_at.date() for b in result.blocked if any(r.kind == TAX_INVOICE for r in b.reasons)
    ]
    return (min(first_day, *waiting), today_vn()) if waiting else None


def _settlement_range(result: HistoryRows) -> tuple[date, date] | None:
    """Order dates to export from the platforms: settlement comes after the order."""
    waiting = [
        b.ordered_at.date() for b in result.blocked if any(r.kind == SETTLEMENT for r in b.reasons)
    ]
    return (min(waiting), today_vn()) if waiting else None


def _only_settlement(blocked) -> bool:
    return all(r.kind == SETTLEMENT for r in blocked.reasons)


def _recent_files(request: Request, db: Session) -> tuple[Page, list[dict]]:
    page = paginate(
        request,
        db,
        select(GeneratedFile)
        .where(GeneratedFile.kind == KIND)
        .order_by(GeneratedFile.created_at.desc(), GeneratedFile.id.desc()),
        GeneratedFile.file_name,
        GeneratedFile.created_by,
    )
    files = page.items
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
    returns = dict(
        db.execute(
            select(SalesHistoryFileReturn.generated_file_id, func.count())
            .where(SalesHistoryFileReturn.generated_file_id.in_(ids))
            .group_by(SalesHistoryFileReturn.generated_file_id)
        ).all()
    )
    returns_confirmed = dict(
        db.execute(
            select(SalesReturnHistoryExported.generated_file_id, func.count())
            .where(SalesReturnHistoryExported.generated_file_id.in_(ids))
            .group_by(SalesReturnHistoryExported.generated_file_id)
        ).all()
    )
    return page, [
        dict(
            file=f,
            orders=in_file.get(f.id, 0),
            confirmed=confirmed.get(f.id, 0),
            returns=returns.get(f.id, 0),
            returns_confirmed=returns_confirmed.get(f.id, 0),
            stored=Path(f.stored_path).is_file(),
        )
        for f in files
    ]


@router.get("/sales-history")
def sales_history_page(
    request: Request,
    month: str | None = Query(None, pattern=MONTH),
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    month, first_day, until = _month_bounds(month)
    result = collect_rows(db, until)
    rows = [
        dict(order=b, reasons=[(r.text, _fix_link(r.kind, b.order_batch_id)) for r in b.reasons])
        for b in result.blocked
    ]
    blocked = [row for row in rows if not _only_settlement(row["order"])]
    waiting_settlement = [row for row in rows if _only_settlement(row["order"])]
    settlement_count = sum(any(r.kind == SETTLEMENT for r in b.reasons) for b in result.blocked)
    files_page, files = _recent_files(request, db)
    invoice_range = _invoice_range(result, first_day)
    waiting_invoice = sum(any(r.kind == TAX_INVOICE for r in b.reasons) for b in result.blocked)
    return render(
        request,
        "sales_history.html",
        user,
        month=month,
        first_day=first_day,
        until=until,
        invoice_range=invoice_range,
        waiting_invoice=waiting_invoice,
        robot_refusal=robot_refusal(sap_config(request, db)) if invoice_range else None,
        orders=len(result.order_ids),
        draft_orders=len(result.order_ids) + sum(is_draftable(b.reasons) for b in result.blocked),
        lines=len(result.rows),
        return_docs=len(result.return_ids),
        return_lines=len(result.return_rows),
        blocked=blocked,
        waiting_settlement=waiting_settlement,
        settlement_count=settlement_count,
        settlement_range=_settlement_range(result),
        files=files,
        files_page=files_page,
    )


@router.get("/sales-history/file")
def download_history_file(
    request: Request,
    month: str | None = Query(None, pattern=MONTH),
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    """Computed again from scratch, so the file holds exactly the orders recorded for it.

    Blocked orders are left out and stay pending, so they go into a later file once complete.
    """
    month, _, until = _month_bounds(month)
    back = _back(month)
    result = collect_rows(db, until)
    if not result.all_rows:
        if result.blocked:
            message = "Chưa có đơn nào sẵn sàng xuất: các đơn còn lại đang chờ hoặc bị chặn."
        else:
            message = "Không có đơn nào chờ xuất."
        flash(request, message, "error")
        return redirect(back)
    overlapping = _unconfirmed_files_holding(db, result.order_ids, result.return_ids)
    file_name = history_file_name(today_vn())
    record = save_generated(
        db,
        request.app.state.settings,
        build_history_workbook(result.all_rows),
        file_name,
        KIND,
        user.username,
    )
    db.add_all(
        SalesHistoryFileOrder(generated_file_id=record.id, sales_order_id=order_id)
        for order_id in result.order_ids
    )
    db.add_all(
        SalesHistoryFileReturn(generated_file_id=record.id, return_id=return_id, kind=kind)
        for return_id, kind in result.return_ids
    )
    db.commit()
    if overlapping:
        flash(
            request,
            f"Đã có {len(overlapping)} file chưa xác nhận chứa cùng đơn với file vừa tải "
            f"({', '.join(f'#{n}' for n in overlapping)}). Chỉ dán một file; khi xác nhận một "
            "file, các file chưa xác nhận chứa cùng đơn sẽ bị xóa.",
            "error",
        )
    return FileResponse(record.stored_path, filename=file_name, media_type=XLSX)


@router.get("/sales-history/draft")
def download_draft_file(
    request: Request,
    month: str | None = Query(None, pattern=MONTH),
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    """A preview that also holds the orders waiting for an invoice or settlement.

    Nothing is stored: no generated file, no order record, so it cannot be confirmed as pasted.
    """
    month, _, until = _month_bounds(month)
    result = collect_rows(db, until, draft=True)
    if not result.all_rows:
        flash(request, "Không có đơn nào để xuất nháp.", "error")
        return redirect(_back(month))
    return _xlsx_response(
        build_history_workbook(result.all_rows, draft=True), history_draft_file_name(today_vn())
    )


def _xlsx_response(workbook, file_name: str) -> Response:
    buffer = BytesIO()
    workbook.save(buffer)
    return Response(
        buffer.getvalue(),
        media_type=XLSX,
        headers={"Content-Disposition": f"attachment; filename*=utf-8''{quote(file_name)}"},
    )


@router.get("/sales-history/all")
def download_all_orders(
    request: Request,
    first: str | None = Query(None, alias="from"),
    last: str | None = Query(None, alias="to"),
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    """Every order placed in the range, in any status, pasted or not, for reconciling only.

    Nothing is stored: no generated file, no order record, so it cannot be confirmed as pasted.
    """
    try:
        start, end = date.fromisoformat(first or ""), date.fromisoformat(last or "")
    except ValueError:
        flash(request, "Chọn đủ Từ ngày và Đến ngày (đúng định dạng ngày).", "error")
        return redirect("/sales-history")
    if start > end:
        flash(request, "Từ ngày phải trước hoặc bằng Đến ngày.", "error")
        return redirect("/sales-history")
    rows = collect_all_rows(db, start, end)
    if not rows:
        flash(request, "Không có đơn nào trong khoảng này.", "error")
        return redirect("/sales-history")
    return _xlsx_response(
        build_history_workbook(rows, draft=True, title=ALL_SHEET),
        history_all_file_name(start, end),
    )


@router.post("/sales-history/read-zrsd003")
def read_zrsd003(
    request: Request,
    month: str = Form(..., pattern=MONTH),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    """Ask the robot to read zrsd003 over the billing dates of the chosen month's orders."""
    month, first_day, until = _month_bounds(month)
    back = _back(month)
    invoice_range = _invoice_range(collect_rows(db, until), first_day)
    if invoice_range is None:
        flash(request, "Không có đơn nào chờ Tax Invoice Doc.", "error")
        return redirect(back)
    config = sap_config(request, db)
    refusal = robot_refusal(config)
    if refusal:
        flash(request, refusal, "error")
        return redirect(back)
    start, end = invoice_range
    pieces = split_range(start, end)
    jobs = []
    for piece_start, piece_end in pieces:
        try:
            jobs.append(request_zrsd003(db, config.target, piece_start, piece_end, user.username))
        except DuplicateJob as exc:
            flash(request, str(exc), "error")
    if not jobs:
        return redirect(back)
    db.commit()
    if len(pieces) > 1:
        flash(
            request,
            f"Khoảng đọc {start:%d/%m/%Y} đến {end:%d/%m/%Y} dài hơn {MAX_READ_DAYS} ngày vì có "
            f"đơn rất cũ còn chờ hóa đơn: robot đọc thành {len(jobs)} việc, mỗi việc tối đa "
            "31 ngày. Đơn không bao giờ có hóa đơn sẽ kéo khoảng này dài mãi: xem sổ tay.",
            "error",
        )
    else:
        flash(
            request,
            f"Robot sẽ đọc zrsd003 từ {start:%d/%m/%Y} đến {end:%d/%m/%Y} (việc #{jobs[0].id}).",
        )
    return redirect(back)


@router.post("/sales-history/settlement")
async def upload_settlement(
    request: Request,
    month: str = Form(..., pattern=MONTH),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    """Read a Shopee or TikTok settlement file once: it holds the seller's login and, for TikTok,
    withdrawal history, so only order ids, amounts and dates are kept."""
    settings = request.app.state.settings
    back = _back(month)
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


def _unconfirmed_files_holding(
    db: Session,
    order_ids: Sequence[int],
    return_keys: Sequence[tuple[int, str]] = (),
    *,
    besides: int | None = None,
) -> list[int]:
    """Ids of history files with nothing confirmed that hold any of these orders or return rows
    (return id, ISSUE | VOID)."""
    holds_order = exists().where(
        SalesHistoryFileOrder.generated_file_id == GeneratedFile.id,
        SalesHistoryFileOrder.sales_order_id.in_(order_ids),
    )
    holds_return = exists().where(
        SalesHistoryFileReturn.generated_file_id == GeneratedFile.id,
        tuple_(SalesHistoryFileReturn.return_id, SalesHistoryFileReturn.kind).in_(
            list(return_keys)
        ),
    )
    stmt = (
        select(GeneratedFile.id)
        .where(
            GeneratedFile.kind == KIND,
            or_(holds_order, holds_return) if return_keys else holds_order,
            ~exists().where(SalesHistoryExported.generated_file_id == GeneratedFile.id),
            ~exists().where(SalesReturnHistoryExported.generated_file_id == GeneratedFile.id),
        )
        .order_by(GeneratedFile.id)
    )
    if besides is not None:
        stmt = stmt.where(GeneratedFile.id != besides)
    return list(db.scalars(stmt))


def _returns_in(db: Session, file_id: int) -> list[tuple[int, str]]:
    return [
        (return_id, kind)
        for return_id, kind in db.execute(
            select(SalesHistoryFileReturn.return_id, SalesHistoryFileReturn.kind).where(
                SalesHistoryFileReturn.generated_file_id == file_id
            )
        )
    ]


def _drop_unconfirmed_file(db: Session, actor: str, record: GeneratedFile, **detail) -> str:
    """Delete a history file that was never confirmed and its order list; returns its path.
    The caller commits, then removes the stored file."""
    db.execute(
        delete(SalesHistoryFileOrder).where(SalesHistoryFileOrder.generated_file_id == record.id)
    )
    db.execute(
        delete(SalesHistoryFileReturn).where(SalesHistoryFileReturn.generated_file_id == record.id)
    )
    path = record.stored_path
    states.log_event(
        db,
        actor,
        "sales_history_deleted",
        detail={"file_id": record.id, "file_name": record.file_name, **detail},
    )
    db.delete(record)
    return path


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
    returns_in_file = select(
        SalesHistoryFileReturn.return_id,
        SalesHistoryFileReturn.kind,
        literal(record.id),
        literal(user.username),
    ).where(SalesHistoryFileReturn.generated_file_id == record.id)
    # Return rows already confirmed through another file keep that file, like orders.
    returns_confirmed = len(
        db.execute(
            insert(SalesReturnHistoryExported)
            .from_select(
                ["return_id", "kind", "generated_file_id", "confirmed_by"], returns_in_file
            )
            .on_conflict_do_nothing(index_elements=["return_id", "kind"])
            .returning(SalesReturnHistoryExported.return_id)
        ).all()
    )
    in_this_file = list(
        db.scalars(
            select(SalesHistoryFileOrder.sales_order_id).where(
                SalesHistoryFileOrder.generated_file_id == record.id
            )
        )
    )
    returns_here = _returns_in(db, record.id)
    # Another file never confirmed that holds the same orders would paste them a second time:
    # drop it (it was never recorded as pasted, so nothing is lost; its other orders go into the
    # next download).
    superseded = [
        _drop_unconfirmed_file(db, user.username, other, superseded_by=record.id)
        for other in db.scalars(
            select(GeneratedFile).where(
                GeneratedFile.id.in_(
                    _unconfirmed_files_holding(db, in_this_file, returns_here, besides=record.id)
                )
            )
        )
    ]
    states.log_event(
        db,
        user.username,
        "sales_history_confirmed",
        detail={
            "file_id": record.id,
            "confirmed": confirmed,
            "skipped": skipped,
            "returns_confirmed": returns_confirmed,
        },
    )
    db.commit()
    # This file, and any other file sharing its orders, goes once all its rows are confirmed.
    sharing = select(SalesHistoryFileOrder.sales_order_id).where(
        SalesHistoryFileOrder.generated_file_id == record.id
    )
    paths = [
        record.stored_path,
        *db.scalars(
            select(GeneratedFile.stored_path)
            .join(
                SalesHistoryFileOrder, SalesHistoryFileOrder.generated_file_id == GeneratedFile.id
            )
            .where(SalesHistoryFileOrder.sales_order_id.in_(sharing))
            .distinct()
        ).all(),
    ]
    retention.discard_unused(db, request.app.state.settings, [*paths, *superseded])
    note = f" Đã xóa {len(superseded)} file chưa xác nhận chứa cùng đơn." if superseded else ""
    returned = f", {returns_confirmed} phiếu trả hàng" if returns_here else ""
    flash(
        request,
        f"Đã xác nhận {confirmed} đơn{returned}, bỏ qua {skipped} đơn đã xác nhận ở file khác."
        f"{note}",
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
    nameless = db.scalar(
        select(func.count())
        .select_from(SalesHistoryFileOrder)
        .join(SalesOrder, SalesOrder.id == SalesHistoryFileOrder.sales_order_id)
        .outerjoin(
            CustomerInfo,
            and_(
                CustomerInfo.platform == SalesOrder.platform,
                CustomerInfo.platform_order_id == SalesOrder.platform_order_id,
            ),
        )
        .where(
            SalesHistoryFileOrder.generated_file_id == record.id,
            CustomerInfo.id.is_(None),
        )
    )
    if nameless:
        flash(
            request,
            f"Không gỡ xác nhận được: {nameless} đơn trong file không còn tên khách, "
            "các đơn này sẽ bị chặn mãi vì thiếu tên khách.",
            "error",
        )
        return redirect("/sales-history")
    # A reversal pasted later stands on these negative rows: that file comes off first.
    issued_here = select(SalesReturnHistoryExported.return_id).where(
        SalesReturnHistoryExported.generated_file_id == record.id,
        SalesReturnHistoryExported.kind == "ISSUE",
    )
    reversed_later = db.execute(
        select(SalesReturn.doc_no, GeneratedFile.file_name)
        .join(SalesReturnHistoryExported, SalesReturnHistoryExported.return_id == SalesReturn.id)
        .join(GeneratedFile, GeneratedFile.id == SalesReturnHistoryExported.generated_file_id)
        .where(
            SalesReturnHistoryExported.kind == VOID,
            SalesReturnHistoryExported.return_id.in_(issued_here),
            SalesReturnHistoryExported.generated_file_id != record.id,
        )
        .order_by(SalesReturn.doc_no)
    ).all()
    if reversed_later:
        flash(
            request,
            "Không gỡ xác nhận được: dòng đảo của phiếu "
            + ", ".join(doc for doc, _ in reversed_later)
            + " đã xác nhận ở file sau ("
            + ", ".join(dict.fromkeys(name for _, name in reversed_later))
            + "); gỡ xác nhận file đó trước.",
            "error",
        )
        return redirect("/sales-history")
    removed = db.execute(
        delete(SalesHistoryExported).where(SalesHistoryExported.generated_file_id == record.id)
    ).rowcount
    returns_removed = db.execute(
        delete(SalesReturnHistoryExported).where(
            SalesReturnHistoryExported.generated_file_id == record.id
        )
    ).rowcount
    states.log_event(
        db,
        user.username,
        "sales_history_unconfirmed",
        detail={"file_id": record.id, "removed": removed, "returns_removed": returns_removed},
    )
    db.commit()
    returned = f" và {returns_removed} phiếu trả hàng" if returns_removed else ""
    flash(
        request,
        f"Đã gỡ xác nhận {removed} đơn{returned}; các dòng này sẽ có lại trong lần xuất sau.",
    )
    return redirect("/sales-history")


@router.post("/sales-history/files/{file_id}/delete")
def delete_file(
    request: Request,
    file_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    """Clear a file that will never be pasted. Its orders were not confirmed through it, so
    the ones still pending go into the next download; a confirmed file must be unconfirmed first,
    or the record of what was pasted would be lost."""
    record = _history_file(db, file_id)
    confirmed = db.scalar(
        select(func.count())
        .select_from(SalesHistoryExported)
        .where(SalesHistoryExported.generated_file_id == record.id)
    ) or db.scalar(
        select(func.count())
        .select_from(SalesReturnHistoryExported)
        .where(SalesReturnHistoryExported.generated_file_id == record.id)
    )
    if confirmed:
        flash(request, "File đã xác nhận đã dán: gỡ xác nhận trước khi xóa.", "error")
        return redirect("/sales-history")
    name = record.file_name
    path = _drop_unconfirmed_file(db, user.username, record)
    db.commit()
    retention.discard_unused(db, request.app.state.settings, [path])
    flash(request, f"Đã xóa file {name}; các đơn chưa xác nhận sẽ có trong lần xuất sau.")
    return redirect("/sales-history")
