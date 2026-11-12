from io import BytesIO
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.db.models import AppUser, PlatformSetting, SalesOrder, SalesOrderItem, SkuMapping
from shoponline.domain import states
from shoponline.domain.sku_mapping import upsert_mapping
from shoponline.importers.excel_table import FileRejected
from shoponline.importers.order_import import reevaluate_mapping_errors
from shoponline.importers.sku_mapping_file import (
    REQUIRED,
    build_mapping_template,
    import_mapping_file,
)
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
from shoponline.web.uploads import UploadRejected, save_upload

router = APIRouter()
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
BULK_FIELDS = ("product_name", "variation_name", "material_number", "sap_name")


def _platforms(db: Session) -> list[str]:
    return list(db.scalars(select(PlatformSetting.platform).order_by(PlatformSetting.platform)))


def _unmapped(db: Session, platform: str) -> list[tuple[str, str]]:
    """Distinct product/variation pairs that keep orders in MAPPING_ERROR."""
    rows = db.execute(
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
    return [(product, variation or "") for product, variation in rows]


def _page(
    request: Request,
    db: Session,
    user: AppUser,
    platform: str,
    entered: list[dict] | None = None,
):
    """Render the mapping page; `entered` refills the unmapped rows after a rejected save."""
    mappings = db.scalars(
        select(SkuMapping)
        .where(SkuMapping.platform == platform)
        .order_by(SkuMapping.product_name, SkuMapping.variation_name)
    ).all()
    previous = {(e["product_name"], e["variation_name"]): e for e in entered or []}
    unmapped = [
        previous.get(
            (product, variation),
            dict(
                product_name=product,
                variation_name=variation,
                material_number="",
                sap_name="",
                error="",
            ),
        )
        for product, variation in _unmapped(db, platform)
    ]
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


@router.get("/sku-mappings")
def list_mappings(
    request: Request,
    platform: str = "SHOPEE",
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    return _page(request, db, user, platform)


@router.get("/sku-mappings/unmapped.xlsx")
def download_unmapped(
    platform: str = "SHOPEE",
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    """The unmapped list in the upload layout: fill Mã SAP and Tên SAP, then import it back."""
    buffer = BytesIO()
    build_mapping_template(_unmapped(db, platform)).save(buffer)
    file_name = quote(f"ÁNH XẠ CÒN THIẾU {platform}.xlsx")
    return Response(
        buffer.getvalue(),
        media_type=XLSX,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{file_name}"},
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
        if is_autosave(request):
            return autosave_reply(str(exc), ok=False)
        flash(request, str(exc), "error")
        return redirect(f"/sku-mappings?platform={platform}")
    fixed = reevaluate_mapping_errors(db, platform, user.username)
    db.commit()
    if is_autosave(request):
        return autosave_reply(f"Đã lưu, {fixed} đơn sẵn sàng")
    flash(request, f"Đã lưu ánh xạ. {fixed} đơn chuyển sang sẵn sàng.")
    return redirect(f"/sku-mappings?platform={platform}")


@router.post("/sku-mappings/bulk")
async def save_unmapped(
    request: Request,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    """Save every unmapped row that has Mã SAP or Tên SAP typed in; untouched rows are skipped.

    All-or-nothing: when any filled row is invalid nothing is saved and the page comes back
    with every typed value kept and the bad rows marked, so no input is lost.
    """
    form = await request.form()
    platform = str(form.get("platform") or "")
    columns = [[str(v) for v in form.getlist(name)] for name in BULK_FIELDS]
    if not platform or len({len(c) for c in columns}) != 1:
        flash(request, "Dữ liệu gửi lên không hợp lệ, hãy tải lại trang.", "error")
        return redirect(f"/sku-mappings?platform={platform}")
    entered = [
        dict(zip(BULK_FIELDS, values, strict=True), error="")
        for values in zip(*columns, strict=True)
    ]
    filled = [e for e in entered if e["material_number"].strip() or e["sap_name"].strip()]
    if not filled:
        flash(request, "Chưa nhập Mã SAP / Tên SAP cho dòng nào.", "error")
        return _page(request, db, user, platform, entered)
    for row in filled:
        try:
            upsert_mapping(
                db,
                platform,
                row["product_name"],
                row["variation_name"],
                row["material_number"],
                row["sap_name"],
                user.username,
            )
        except ValueError as exc:
            row["error"] = str(exc)
    failed = sum(1 for row in filled if row["error"])
    if failed:
        db.rollback()
        flash(
            request,
            f"{failed} dòng sai nên chưa lưu dòng nào. Sửa các dòng báo đỏ rồi bấm lưu lại.",
            "error",
        )
        return _page(request, db, user, platform, entered)
    fixed = reevaluate_mapping_errors(db, platform, user.username)
    db.commit()
    flash(request, f"Đã lưu {len(filled)} ánh xạ. {fixed} đơn chuyển sang sẵn sàng.")
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
    skipped = f", {result.skipped} dòng để trống bỏ qua" if result.skipped else ""
    flash(
        request,
        f"Đã lưu {result.saved} ánh xạ, {result.unchanged} không đổi{skipped}; "
        f"{result.fixed_orders} đơn chuyển sang sẵn sàng.",
    )
    return redirect(f"/sku-mappings?platform={platform}")
