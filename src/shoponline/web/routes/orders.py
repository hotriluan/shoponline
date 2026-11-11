from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.db.models import AppUser, CustomerInfo, EventLog, SalesOrder
from shoponline.domain import states
from shoponline.domain.expected_value import expected_so_value
from shoponline.importers.order_import import evaluate_order
from shoponline.web.app import current_user, flash, get_db, redirect, render, require_admin

router = APIRouter()


def _order(db: Session, order_id: int) -> SalesOrder:
    order = db.get(SalesOrder, order_id)
    if order is None:
        raise HTTPException(404, "Không có đơn này")
    return order


@router.get("/orders/{order_id}")
def order_detail(
    request: Request,
    order_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    order = _order(db, order_id)
    customer = db.scalar(
        select(CustomerInfo).where(
            CustomerInfo.platform == order.platform,
            CustomerInfo.platform_order_id == order.platform_order_id,
        )
    )
    events = db.scalars(
        select(EventLog)
        .where(
            EventLog.platform == order.platform,
            EventLog.platform_order_id == order.platform_order_id,
        )
        .order_by(EventLog.at, EventLog.id)
    ).all()
    return render(
        request,
        "order_detail.html",
        user,
        order=order,
        customer=customer,
        events=events,
        expected=expected_so_value(order.items),
        can_cancel=states.CANCELLED in states.ALLOWED[order.status],
    )


@router.post("/orders/{order_id}/cancel")
def cancel_order(
    request: Request,
    order_id: int,
    reason: str = Form(""),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    order = _order(db, order_id)
    try:
        states.transition(db, order, states.CANCELLED, user.username, reason.strip() or "Admin hủy")
    except states.InvalidTransition as exc:
        flash(request, str(exc), "error")
        return redirect(f"/orders/{order_id}")
    db.commit()
    flash(request, f"Đã đánh dấu hủy đơn {order.platform_order_id}.")
    return redirect(f"/orders/{order_id}")


@router.post("/orders/{order_id}/review-ok")
def accept_review(
    request: Request,
    order_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    """Admin checked a NEED_REVIEW order (e.g. TikTok discount rounding) by hand."""
    order = _order(db, order_id)
    if order.status != states.NEED_REVIEW:
        flash(request, "Đơn không ở trạng thái cần kiểm tra.", "error")
        return redirect(f"/orders/{order_id}")
    note = order.review_note
    order.review_note = None
    evaluate_order(db, order, user.username)
    states.log_event(
        db,
        user.username,
        "review_accepted",
        platform=order.platform,
        platform_order_id=order.platform_order_id,
        detail={"note": note},
    )
    db.commit()
    flash(request, f"Đơn {order.platform_order_id} chuyển sang {states.LABELS[order.status]}.")
    return redirect(f"/orders/{order_id}")
