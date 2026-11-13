from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.db.models import AppUser, ImportBatch, OrderBatch
from shoponline.exports.accounting_workbook import build_accounting_workbook, database_lookup
from shoponline.importers.excel_table import FileRejected
from shoponline.reconcile.report_ingest import ingest_zrsd001, ingest_zrsd004
from shoponline.web.app import current_user, flash, get_db, redirect, render, require_admin
from shoponline.web.uploads import UploadRejected, save_generated, save_upload

router = APIRouter()
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _page(request, db, user, **extra):
    batches = db.scalars(
        select(OrderBatch)
        .order_by(OrderBatch.processing_date.desc(), OrderBatch.platform)
        .limit(30)
    ).all()
    recent = db.scalars(
        select(ImportBatch)
        .where(ImportBatch.kind.in_(("zrsd001", "zrsd004")))
        .order_by(ImportBatch.imported_at.desc())
        .limit(10)
    ).all()
    return render(request, "sap_reports.html", user, batches=batches, recent=recent, **extra)


@router.get("/sap-reports")
def sap_reports(
    request: Request,
    batch_id: int | None = None,
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    return _page(request, db, user, selected_batch=batch_id)


@router.post("/sap-reports/zrsd001")
async def upload_zrsd001(
    request: Request,
    batch_id: int | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    batch = db.get(OrderBatch, batch_id) if batch_id else None
    try:
        record = await save_upload(
            request.app.state.settings, file, kind="zrsd001", platform=None, actor=user.username
        )
        result = ingest_zrsd001(db, record, user.username, expect_batch=batch)
    except (UploadRejected, FileRejected) as exc:
        db.rollback()
        return _page(request, db, user, error=str(exc), selected_batch=batch_id)
    db.commit()
    flash(
        request,
        f"zrsd001: {result.new} SO mới, {result.updated} cập nhật, {result.unchanged} không đổi; "
        f"nối được {len(result.linked)} đơn.",
    )
    for warning in result.warnings:
        flash(request, warning, "error")
    return redirect(f"/batches/{batch.id}" if batch else "/sap-reports")


@router.post("/sap-reports/zrsd004")
async def upload_zrsd004(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    try:
        record = await save_upload(
            request.app.state.settings, file, kind="zrsd004", platform=None, actor=user.username
        )
        imported = ingest_zrsd004(db, record, user.username)
    except (UploadRejected, FileRejected) as exc:
        db.rollback()
        return _page(request, db, user, error=str(exc))
    db.commit()
    return render(
        request,
        "accounting_preview.html",
        user,
        record=record,
        preview=imported.preview,
        delivered=imported.delivered,
        row_count=len(imported.rows),
    )


@router.get("/sap-reports/zrsd004/{record_id}/accounting-file")
def download_accounting_file(
    request: Request,
    record_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    record = db.get(ImportBatch, record_id)
    if record is None or record.kind != "zrsd004":
        raise HTTPException(404, "Không có file zrsd004 này")
    if not Path(record.stored_path).is_file():
        raise HTTPException(404, "File zrsd004 này đã quá thời hạn lưu và bị xóa")
    result = build_accounting_workbook(Path(record.stored_path), database_lookup(db))
    path = save_generated(
        db,
        request.app.state.settings,
        result.workbook,
        result.file_name,
        "accounting_file",
        user.username,
    )
    db.commit()
    return FileResponse(path, filename=result.file_name, media_type=XLSX)
