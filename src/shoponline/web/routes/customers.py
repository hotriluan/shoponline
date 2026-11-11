from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.db.models import AppUser, CustomerInfo, OrderBatch, PlatformSetting, SalesOrder
from shoponline.web.app import current_user, flash, get_db, redirect, render, require_admin

router = APIRouter()


@router.get("/customers")
def list_customers(
    request: Request,
    batch_id: int | None = None,
    platform: str | None = None,
    missing: bool = False,
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    batch = db.get(OrderBatch, batch_id) if batch_id else None
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
        rows = list(
            db.scalars(
                select(CustomerInfo)
                .where(CustomerInfo.platform == platform)
                .order_by(CustomerInfo.updated_at.desc())
                .limit(200)
            )
        )
    if missing:
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
    note = "" if has_order or platform == "LAZADA" else " (chưa có đơn nào mang mã này)"
    flash(request, f"Đã lưu khách hàng của đơn {order_id}{note}.")
    return redirect(_safe(return_to))


def _safe(url: str) -> str:
    """Only allow local redirects."""
    return url if url.startswith("/") and not url.startswith("//") else "/customers"
