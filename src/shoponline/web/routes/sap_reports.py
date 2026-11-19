from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.db.models import AppUser, ImportBatch, OrderBatch
from shoponline.importers.excel_table import FileRejected
from shoponline.maintenance import retention
from shoponline.reconcile.report_ingest import ingest_zrsd001, ingest_zrsd003, ingest_zrsd004
from shoponline.web.app import current_user, flash, get_db, redirect, render, require_admin
from shoponline.web.uploads import UploadRejected, save_upload

router = APIRouter()


def _page(request, db, user, **extra):
    batches = db.scalars(
        select(OrderBatch)
        .order_by(OrderBatch.processing_date.desc(), OrderBatch.platform)
        .limit(30)
    ).all()
    recent = db.scalars(
        select(ImportBatch)
        .where(ImportBatch.kind.in_(("zrsd001", "zrsd003", "zrsd004")))
        .order_by(ImportBatch.imported_at.desc())
        .limit(10)
    ).all()
    return render(request, "sap_reports.html", user, batches=batches, recent=recent, **extra)


@router.get("/sap-reports")
def sap_reports(
    request: Request,
    batch_id: str = "",  # an empty value means no batch is preselected
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    selected = int(batch_id) if batch_id.strip().isdigit() else None
    return _page(request, db, user, selected_batch=selected)


@router.post("/sap-reports/zrsd001")
async def upload_zrsd001(
    request: Request,
    batch_id: int | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    batch = db.get(OrderBatch, batch_id) if batch_id else None
    settings = request.app.state.settings
    new_file = None
    try:
        record, created = await save_upload(
            settings, file, kind="zrsd001", platform=None, actor=user.username
        )
        new_file = record.stored_path if created else None
        result = ingest_zrsd001(db, record, user.username, expect_batch=batch)
    except (UploadRejected, FileRejected) as exc:
        db.rollback()
        retention.discard_unused(db, settings, [new_file])
        return _page(request, db, user, error=str(exc), selected_batch=batch_id)
    db.commit()
    retention.discard_unused(db, settings, [record.stored_path])  # read once, at import
    flash(
        request,
        f"zrsd001: {result.new} SO mới, {result.updated} cập nhật, {result.unchanged} không đổi; "
        f"nối được {len(result.linked)} đơn.",
    )
    for warning in result.warnings:
        flash(request, warning, "error")
    return redirect(f"/batches/{batch.id}" if batch else "/sap-reports")


@router.post("/sap-reports/zrsd003")
async def upload_zrsd003(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    settings = request.app.state.settings
    new_file = None
    try:
        record, created = await save_upload(
            settings, file, kind="zrsd003", platform=None, actor=user.username
        )
        new_file = record.stored_path if created else None
        result = ingest_zrsd003(db, record, user.username)
    except (UploadRejected, FileRejected) as exc:
        db.rollback()
        retention.discard_unused(db, settings, [new_file])
        return _page(request, db, user, error=str(exc))
    db.commit()
    # Read once, at import: the file also holds business customers' names and tax codes.
    retention.discard_unused(db, settings, [record.stored_path])
    flash(
        request,
        f"zrsd003: {result.kept} hóa đơn của sàn ({result.new} mới, {result.updated} cập nhật), "
        f"bỏ qua {result.skipped_other_customers} dòng khách khác.",
    )
    return redirect("/sap-reports")


@router.post("/sap-reports/zrsd004")
async def upload_zrsd004(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    settings = request.app.state.settings
    new_file = None
    try:
        record, created = await save_upload(
            settings, file, kind="zrsd004", platform=None, actor=user.username
        )
        new_file = record.stored_path if created else None
        imported = ingest_zrsd004(db, record, user.username)
    except (UploadRejected, FileRejected) as exc:
        db.rollback()
        retention.discard_unused(db, settings, [new_file])
        return _page(request, db, user, error=str(exc))
    db.commit()
    # Normally kept: it waits to be attached to an accounting run.
    retention.discard_unused(db, settings, [record.stored_path])
    return render(
        request,
        "accounting_preview.html",
        user,
        record=record,
        preview=imported.preview,
        delivered=imported.delivered,
        row_count=len(imported.rows),
    )
