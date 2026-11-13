from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session

from shoponline.clock import today_vn
from shoponline.db.models import AppUser
from shoponline.importers.excel_table import FileRejected
from shoponline.importers.order_import import READERS, import_orders
from shoponline.web.app import current_user, get_db, render, require_admin
from shoponline.web.uploads import UploadRejected, save_upload

router = APIRouter()


def _form(request, user, **extra):
    return render(
        request,
        "import_form.html",
        user,
        platforms=sorted(READERS),
        today=today_vn().isoformat(),
        **extra,
    )


@router.get("/imports")
def import_form(request: Request, user: AppUser = Depends(current_user)):
    return _form(request, user)


@router.post("/imports")
async def import_file(
    request: Request,
    platform: str = Form(...),
    processing_date: date = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    if platform not in READERS:
        return _form(request, user, error=f"Chưa có bộ đọc cho sàn {platform}")
    try:
        record = await save_upload(
            request.app.state.settings,
            file,
            kind=f"{platform.lower()}_orders",
            platform=platform,
            actor=user.username,
        )
        parsed = READERS[platform](Path(record.stored_path))
        db.add(record)
        db.flush()
        result = import_orders(db, parsed, platform, processing_date, user.username, record)
    except (UploadRejected, FileRejected) as exc:
        db.rollback()
        return _form(request, user, error=str(exc))
    db.commit()
    return render(request, "import_result.html", user, result=result, record=record)
