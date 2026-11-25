from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session

from shoponline.clock import today_vn
from shoponline.db.models import AppUser
from shoponline.domain import shops
from shoponline.importers.excel_table import FileRejected
from shoponline.importers.order_import import READERS, import_orders
from shoponline.maintenance import retention
from shoponline.web.app import current_user, get_db, render, require_admin
from shoponline.web.uploads import UploadRejected, save_upload

router = APIRouter()


def _form(request, user, db, **extra):
    platforms = sorted(READERS)
    return render(
        request,
        "import_form.html",
        user,
        platforms=platforms,
        shops=shops.active_shops(db),
        default_shops={p: shops.default_shop_code(db, p) for p in platforms},
        today=today_vn().isoformat(),
        **extra,
    )


@router.get("/imports")
def import_form(
    request: Request, db: Session = Depends(get_db), user: AppUser = Depends(current_user)
):
    return _form(request, user, db)


@router.post("/imports")
async def import_file(
    request: Request,
    platform: str = Form(...),
    processing_date: date = Form(...),
    shop_code: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    if platform not in READERS:
        return _form(request, user, db, error=f"Chưa có bộ đọc cho sàn {platform}")
    try:
        shops.require_choice(db, platform, shop_code)
    except shops.ShopRefused as exc:
        return _form(request, user, db, error=str(exc))
    settings = request.app.state.settings
    new_file = None
    try:
        record, created = await save_upload(
            settings,
            file,
            kind=f"{platform.lower()}_orders",
            platform=platform,
            actor=user.username,
        )
        new_file = record.stored_path if created else None
        parsed = READERS[platform](Path(record.stored_path))
        db.add(record)
        db.flush()
        result = import_orders(
            db, parsed, platform, processing_date, user.username, record, shop_code
        )
    except (UploadRejected, FileRejected) as exc:
        db.rollback()
        retention.discard_unused(db, settings, [new_file])
        return _form(request, user, db, error=str(exc))
    db.commit()
    retention.discard_unused(db, settings, [record.stored_path])  # read once, at import
    return render(request, "import_result.html", user, result=result, record=record)
