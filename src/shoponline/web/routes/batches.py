from collections import Counter
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.db.models import AppUser, CustomerInfo, OrderBatch, PlatformSetting, SalesOrder
from shoponline.domain import states
from shoponline.exports.order_workbook import build_order_workbook
from shoponline.reconcile.so_link import LinkError, batch_report, link_manually
from shoponline.sapjobs.queue import DuplicateJob
from shoponline.sapjobs.report_requests import request_zrsd001, request_zrsd004
from shoponline.web.app import (
    autosave_reply,
    current_user,
    flash,
    get_db,
    is_autosave,
    redirect,
    render,
    require_admin,
    sap_config,
)
from shoponline.web.uploads import save_generated

router = APIRouter()

UNVERIFIED_MESSAGE = (
    "Đã đổi hệ thống SAP, cần kiểm tra kết nối thành công trước (trang Kết nối SAP)"
)


def _batch(db: Session, batch_id: int) -> OrderBatch:
    batch = db.get(OrderBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "Không có lô này")
    return batch


@router.get("/batches")
def list_batches(
    request: Request, db: Session = Depends(get_db), user: AppUser = Depends(current_user)
):
    batches = db.scalars(
        select(OrderBatch)
        .order_by(OrderBatch.processing_date.desc(), OrderBatch.platform)
        .limit(60)
    ).all()
    counts = {b.id: Counter(o.status for o in b.orders) for b in batches}
    return render(request, "batches.html", user, batches=batches, counts=counts)


@router.get("/batches/{batch_id}")
def batch_detail(
    request: Request,
    batch_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    batch = _batch(db, batch_id)
    orders = sorted(batch.orders, key=lambda o: o.ordered_at)
    customers = {
        c.platform_order_id: c
        for c in db.scalars(
            select(CustomerInfo).where(
                CustomerInfo.platform == batch.platform,
                CustomerInfo.platform_order_id.in_([o.platform_order_id for o in orders]),
            )
        )
    }
    excluded = sum(1 for o in orders if o.status in (states.MAPPING_ERROR, states.NEED_REVIEW))
    report = batch_report(db, batch) if batch.confirmed_at else None
    open_orders = [o for o in orders if o.status in states.OPEN_STATUSES and not o.so_number]
    return render(
        request,
        "batch_detail.html",
        user,
        batch=batch,
        orders=orders,
        customers=customers,
        excluded=excluded,
        report=report,
        open_orders=open_orders,
    )


@router.post("/batches/{batch_id}/gi-date")
def set_gi_date(
    request: Request,
    batch_id: int,
    gi_date: date = Form(...),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    batch = _batch(db, batch_id)
    if gi_date < batch.processing_date:
        if is_autosave(request):
            return autosave_reply("Ngày goods issue không được trước ngày xử lý.", ok=False)
        flash(request, "Ngày goods issue không được trước ngày xử lý.", "error")
        return redirect(f"/batches/{batch_id}")
    old = batch.gi_date
    batch.gi_date = gi_date
    states.log_event(
        db,
        user.username,
        "gi_date_changed",
        platform=batch.platform,
        detail={"batch_id": batch.id, "from": old.isoformat(), "to": gi_date.isoformat()},
    )
    db.commit()
    if is_autosave(request):
        return autosave_reply(f"Đã lưu ngày {gi_date:%d/%m/%Y}")
    flash(request, f"Đã đặt ngày goods issue {gi_date:%d/%m/%Y}.")
    return redirect(f"/batches/{batch_id}")


@router.get("/batches/{batch_id}/order-file")
def download_order_file(
    request: Request,
    batch_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    batch = _batch(db, batch_id)
    setting = db.get(PlatformSetting, batch.platform)
    order_file = build_order_workbook(setting, batch, batch.orders)
    path = save_generated(
        db,
        request.app.state.settings,
        order_file.workbook,
        order_file.file_name,
        "order_file",
        user.username,
    )
    db.commit()
    return FileResponse(
        path,
        filename=order_file.file_name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.post("/batches/{batch_id}/confirm")
def confirm_batch(
    request: Request,
    batch_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    batch = _batch(db, batch_id)
    if batch.confirmed_at is None:
        batch.confirmed_by = user.username
        batch.confirmed_at = datetime.now(UTC)
        states.log_event(
            db,
            user.username,
            "batch_confirmed",
            platform=batch.platform,
            detail={"batch_id": batch.id},
        )
        config = sap_config(request, db)
        if config.target is None:
            message = "Đã ghi nhận sales admin đã tạo SO và DO. Tải zrsd001 lên để đối chiếu."
        elif not config.target_verified:
            message = f"Đã xác nhận lô. {UNVERIFIED_MESSAGE}."
        else:
            try:
                job = request_zrsd001(db, config.target, batch, user.username)
                message = f"Đã xác nhận lô; robot sẽ đọc zrsd001 (việc #{job.id})."
            except DuplicateJob as exc:
                message = f"Đã xác nhận lô. {exc}"
        db.commit()
        flash(request, message)
    return redirect(f"/batches/{batch_id}")


@router.post("/batches/{batch_id}/accounting-file")
def request_accounting_file(
    request: Request,
    batch_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    """Ask the robot to read zrsd004 for the batch's goods issue date."""
    batch = _batch(db, batch_id)
    config = sap_config(request, db)
    if config.target is None:
        flash(request, "Robot chưa được bật; tải zrsd004 lên ở trang Báo cáo SAP.", "error")
        return redirect(f"/batches/{batch_id}")
    if not config.target_verified:
        flash(request, UNVERIFIED_MESSAGE, "error")
        return redirect(f"/batches/{batch_id}")
    try:
        job = request_zrsd004(db, config.target, batch, user.username)
    except DuplicateJob as exc:
        flash(request, str(exc), "error")
        return redirect(f"/batches/{batch_id}")
    db.commit()
    flash(
        request,
        f"Robot sẽ đọc zrsd004 ngày {batch.gi_date:%d/%m/%Y} (việc #{job.id}); "
        "file gửi kế toán có ở trang Báo cáo SAP khi việc xong.",
    )
    return redirect(f"/batches/{batch_id}")


@router.post("/batches/{batch_id}/link")
def link_so(
    request: Request,
    batch_id: int,
    so_number: str = Form(...),
    order_id: int = Form(...),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    _batch(db, batch_id)
    order = db.get(SalesOrder, order_id)
    if order is None or order.order_batch_id != batch_id:
        raise HTTPException(404, "Không có đơn này trong lô")
    try:
        link_manually(db, order, so_number.strip(), user.username)
    except LinkError as exc:
        db.rollback()
        flash(request, str(exc), "error")
        return redirect(f"/batches/{batch_id}")
    db.commit()
    flash(request, f"Đã nối SO {so_number} với đơn {order.platform_order_id}.")
    return redirect(f"/batches/{batch_id}")
