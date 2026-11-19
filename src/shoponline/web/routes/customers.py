from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from shoponline.db.models import AppUser, CustomerInfo, OrderBatch, PlatformSetting, SalesOrder
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
from shoponline.web.pagination import paginate

router = APIRouter()


@router.get("/customers")
def list_customers(
    request: Request,
    batch_id: str = "",  # the filter's "no batch" option submits an empty value
    platform: str | None = None,
    missing: bool = False,
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    batch = db.get(OrderBatch, int(batch_id)) if batch_id.strip().isdigit() else None
    page = None  # only the per-platform list is paged on the server
    if batch is not None:
        order_ids = [o.platform_order_id for o in sorted(batch.orders, key=lambda o: o.ordered_at)]
        found = {
            c.platform_order_id: c
            for c in db.scalars(
                select(CustomerInfo).where(
                    CustomerInfo.platform == batch.platform,
                    CustomerInfo.platform_order_id.in_(order_ids),
                )
            )
        }
        rows = [
            found.get(oid) or CustomerInfo(platform=batch.platform, platform_order_id=oid)
            for oid in order_ids
        ]
        platform = batch.platform
    else:
        platform = platform or "LAZADA"
        stmt = (
            select(CustomerInfo)
            .where(CustomerInfo.platform == platform)
            .order_by(CustomerInfo.updated_at.desc(), CustomerInfo.id.desc())
        )
        if missing:
            stmt = stmt.where(
                or_(
                    func.coalesce(CustomerInfo.customer_name, "") == "",
                    func.coalesce(CustomerInfo.address, "") == "",
                )
            )
        page = paginate(
            request,
            db,
            stmt,
            CustomerInfo.platform_order_id,
            CustomerInfo.customer_name,
            CustomerInfo.address,
        )
        rows = page.items
    if batch is not None and missing:
        rows = [r for r in rows if not r.customer_name or not r.address]
    batches = db.scalars(
        select(OrderBatch).order_by(OrderBatch.processing_date.desc()).limit(30)
    ).all()
    platforms = list(
        db.scalars(select(PlatformSetting.platform).order_by(PlatformSetting.platform))
    )
    return render(
        request,
        "customers.html",
        user,
        rows=rows,
        page=page,
        batch=batch,
        batches=batches,
        platform=platform,
        platforms=platforms,
        missing=missing,
    )


@router.post("/customers/save")
def save_customer(
    request: Request,
    platform: str = Form(...),
    platform_order_id: str = Form(...),
    customer_name: str = Form(""),
    address: str = Form(""),
    return_to: str = Form("/customers"),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    order_id = platform_order_id.strip()
    if not order_id or db.get(PlatformSetting, platform) is None:
        if is_autosave(request):
            return autosave_reply("Cần sàn và mã đơn.", ok=False)
        flash(request, "Cần sàn và mã đơn.", "error")
        return redirect(_safe(return_to))
    info = db.scalar(
        select(CustomerInfo).where(
            CustomerInfo.platform == platform, CustomerInfo.platform_order_id == order_id
        )
    )
    if info is None:
        info = CustomerInfo(platform=platform, platform_order_id=order_id)
        db.add(info)
    info.customer_name = customer_name.strip() or None
    info.address = address.strip() or None
    has_order = db.scalar(
        select(SalesOrder.id).where(
            SalesOrder.platform == platform, SalesOrder.platform_order_id == order_id
        )
    )
    db.commit()
    note = "" if has_order else " (chưa có đơn nào mang mã này)"
    if is_autosave(request):
        return autosave_reply(f"Đã lưu{note}")
    flash(request, f"Đã lưu khách hàng của đơn {order_id}{note}.")
    return redirect(_safe(return_to))


def _safe(url: str) -> str:
    """Only allow local redirects."""
    return url if url.startswith("/") and not url.startswith("//") else "/customers"
