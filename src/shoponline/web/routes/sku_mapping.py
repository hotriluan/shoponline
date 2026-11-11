from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.db.models import AppUser, PlatformSetting, SalesOrder, SalesOrderItem, SkuMapping
from shoponline.domain import states
from shoponline.domain.sku_mapping import upsert_mapping
from shoponline.importers.excel_table import FileRejected
from shoponline.importers.order_import import reevaluate_mapping_errors
from shoponline.importers.sku_mapping_file import REQUIRED, import_mapping_file
from shoponline.web.app import current_user, flash, get_db, redirect, render, require_admin
from shoponline.web.uploads import UploadRejected, save_upload

router = APIRouter()


def _platforms(db: Session) -> list[str]:
    return list(db.scalars(select(PlatformSetting.platform).order_by(PlatformSetting.platform)))


@router.get("/sku-mappings")
def list_mappings(
    request: Request,
    platform: str = "SHOPEE",
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    mappings = db.scalars(
        select(SkuMapping)
        .where(SkuMapping.platform == platform)
        .order_by(SkuMapping.product_name, SkuMapping.variation_name)
    ).all()
    unmapped = db.execute(
        select(SalesOrderItem.product_name, SalesOrderItem.variation_name)
        .join(SalesOrder)
        .where(
            SalesOrder.platform == platform,
            SalesOrder.status == states.MAPPING_ERROR,
            SalesOrderItem.material_number.is_(None),
        )
        .distinct()
        .order_by(SalesOrderItem.product_name, SalesOrderItem.variation_name)
    ).all()
    return render(
        request,
        "sku_mappings.html",
        user,
        platform=platform,
        platforms=_platforms(db),
        mappings=mappings,
        unmapped=unmapped,
        columns=REQUIRED,
    )


@router.post("/sku-mappings")
def save_mapping(
    request: Request,
    platform: str = Form(...),
    product_name: str = Form(...),
    variation_name: str = Form(""),
    material_number: str = Form(...),
    sap_name: str = Form(...),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    try:
        upsert_mapping(
            db, platform, product_name, variation_name, material_number, sap_name, user.username
        )
    except ValueError as exc:
        db.rollback()
        flash(request, str(exc), "error")
        return redirect(f"/sku-mappings?platform={platform}")
    fixed = reevaluate_mapping_errors(db, platform, user.username)
    db.commit()
    flash(request, f"Đã lưu ánh xạ. {fixed} đơn chuyển sang sẵn sàng.")
    return redirect(f"/sku-mappings?platform={platform}")


@router.post("/sku-mappings/import")
async def import_mappings(
    request: Request,
    platform: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    try:
        record = await save_upload(
            request.app.state.settings,
            file,
            kind="sku_mapping",
            platform=platform,
            actor=user.username,
        )
        result = import_mapping_file(db, Path(record.stored_path), platform, user.username)
    except (UploadRejected, FileRejected, ValueError) as exc:
        db.rollback()
        flash(request, str(exc), "error")
        return redirect(f"/sku-mappings?platform={platform}")
    record.new_count = result.saved
    record.unchanged_count = result.unchanged
    db.add(record)
    db.commit()
    flash(
        request,
        f"Đã lưu {result.saved} ánh xạ, {result.unchanged} không đổi; "
        f"{result.fixed_orders} đơn chuyển sang sẵn sàng.",
    )
    return redirect(f"/sku-mappings?platform={platform}")
