"""The shop catalog: which shops each platform has, which are selling, and their Division."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shoponline.db.models import AppUser, ImportBatch, PlatformSetting, SalesOrder, Shop
from shoponline.domain import shops as catalog
from shoponline.domain import states
from shoponline.web.app import current_user, flash, get_db, redirect, render, require_admin

router = APIRouter()
CODE = re.compile(r"[A-Z0-9_]{2,30}")
MAX_DIVISION = 50


def _division_problem(db: Session, division: str, own_code: str | None = None) -> str:
    if not division:
        return "Chưa nhập tên Division"
    if len(division) > MAX_DIVISION or any(c < " " or c == "\x7f" for c in division):
        return f"Division tối đa {MAX_DIVISION} ký tự, không có ký tự điều khiển"
    other = db.scalar(select(Shop).where(Shop.division == division))
    if other is not None and other.code != own_code:
        return f"Division '{division}' đã là của shop {other.code}"
    return ""


@router.get("/shops")
def list_shops(
    request: Request, db: Session = Depends(get_db), user: AppUser = Depends(current_user)
):
    rows = list(db.scalars(select(Shop).order_by(Shop.platform, Shop.sort_order, Shop.code)))
    order_counts = {
        code: n
        for code, n in db.execute(
            select(SalesOrder.shop_code, func.count()).group_by(SalesOrder.shop_code)
        )
    }
    return render(
        request,
        "shops.html",
        user,
        shops=rows,
        order_counts=order_counts,
        platforms=list(
            db.scalars(select(PlatformSetting.platform).order_by(PlatformSetting.platform))
        ),
    )


@router.post("/shops/{code}/update")
def update_shop(
    request: Request,
    code: str,
    division: str = Form(...),
    active: str = Form(""),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    shop = db.get(Shop, code)
    if shop is None:
        flash(request, f"Không có shop {code}", "error")
        return redirect("/shops")
    division = division.strip()
    problem = _division_problem(db, division, code)
    if problem:
        flash(request, problem, "error")
        return redirect("/shops")
    want_active = active == "on"
    if shop.active and not want_active and len(catalog.active_shops(db, shop.platform)) == 1:
        flash(request, f"Sàn {shop.platform} phải còn ít nhất một shop đang bán", "error")
        return redirect("/shops")
    before = (shop.division, shop.active)
    shop.division, shop.active = division, want_active
    if before != (shop.division, shop.active):
        states.log_event(
            db,
            user.username,
            "shop_updated",
            detail={
                "shop": code,
                "division": [before[0], division],
                "active": [before[1], want_active],
            },
        )
    db.commit()
    flash(request, f"Đã lưu shop {code}.")
    return redirect("/shops")


@router.post("/shops")
def add_shop(
    request: Request,
    code: str = Form(...),
    platform: str = Form(...),
    division: str = Form(...),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    code, division = code.strip().upper(), division.strip()
    problem = ""
    if not CODE.fullmatch(code):
        problem = "Mã shop gồm 2–30 ký tự A–Z, 0–9 và dấu gạch dưới"
    elif db.get(Shop, code) is not None:
        problem = f"Đã có shop {code}"
    elif db.get(PlatformSetting, platform) is None:
        problem = f"Không có sàn {platform}"
    else:
        problem = _division_problem(db, division)
    if problem:
        flash(request, problem, "error")
        return redirect("/shops")
    last = db.scalar(
        select(Shop.sort_order).where(Shop.platform == platform).order_by(Shop.sort_order.desc())
    )
    db.add(
        Shop(
            code=code, platform=platform, division=division, active=True, sort_order=(last or 0) + 1
        )
    )
    states.log_event(db, user.username, "shop_added", detail={"shop": code, "platform": platform})
    db.commit()
    flash(request, f"Đã thêm shop {code}.")
    return redirect("/shops")


@router.post("/shops/{code}/delete")
def delete_shop(
    request: Request,
    code: str,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    shop = db.get(Shop, code)
    if shop is None:
        flash(request, f"Không có shop {code}", "error")
    elif catalog.has_orders(db, code) or db.scalar(
        select(ImportBatch.id).where(ImportBatch.shop_code == code).limit(1)
    ):
        flash(
            request,
            f"Shop {code} đã có đơn hoặc file tải lên, không xóa được; hãy tắt shop.",
            "error",
        )
    elif shop.active and len(catalog.active_shops(db, shop.platform)) == 1:
        flash(request, f"Sàn {shop.platform} phải còn ít nhất một shop đang bán", "error")
    else:
        db.delete(shop)
        states.log_event(db, user.username, "shop_deleted", detail={"shop": code})
        db.commit()
        flash(request, f"Đã xóa shop {code}.")
    return redirect("/shops")
