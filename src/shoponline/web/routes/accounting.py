"""Gửi kế toán: the accounting runs that merge every platform into one file."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shoponline.accounting import ledger, runs
from shoponline.clock import today_vn
from shoponline.db.models import (
    AccountingRun,
    AccountingRunRead,
    AccountingSentDelivery,
    AppUser,
    GeneratedFile,
    ImportBatch,
)
from shoponline.importers.excel_table import FileRejected
from shoponline.reconcile.report_ingest import ingest_zrsd004
from shoponline.sapjobs import queue
from shoponline.web.app import (
    current_user,
    flash,
    get_db,
    redirect,
    render,
    require_admin,
    robot_refusal,
    sap_config,
)
from shoponline.web.uploads import UploadRejected, save_upload

router = APIRouter()
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
RECENT_RUNS = 20
RETRYABLE = (runs.ERROR, runs.NO_DATA, runs.MISSING_FILE, runs.NO_JOB)


def _run(db: Session, run_id: int) -> AccountingRun:
    run = db.get(AccountingRun, run_id)
    if run is None:
        raise HTTPException(404, "Không có đợt này")
    return run


def _target(request: Request, db: Session):
    """The SAP target the robot can be given now, and the reason when there is none."""
    config = sap_config(request, db)
    refusal = robot_refusal(config)
    return (None if refusal else config.target), refusal


def begin_run(request: Request, db: Session, user: AppUser):
    """Open a run (or join the open one) and go to its page; shared with the batch page button."""
    target, refusal = _target(request, db)
    try:
        run = runs.start_run(db, target, user.username, today_vn())
    except runs.NothingDue as exc:
        db.rollback()
        flash(request, str(exc), "error")
        return redirect("/accounting")
    db.commit()
    if refusal:
        flash(
            request,
            f"{refusal} Đợt đã mở không có việc cho robot: tải zrsd004 lên đợt này để tiếp tục.",
            "error",
        )
    else:
        flash(
            request, f"Đợt gửi kế toán #{run.id}: robot sẽ đọc zrsd004 cho từng sàn và từng ngày."
        )
    return redirect(f"/accounting/runs/{run.id}")


def _delivery_counts(db: Session, run_ids: list[int]) -> dict[int, int]:
    rows = db.execute(
        select(AccountingSentDelivery.run_id, func.count())
        .where(AccountingSentDelivery.run_id.in_(run_ids))
        .group_by(AccountingSentDelivery.run_id)
    ).all()
    return dict(rows)


@router.get("/accounting")
def accounting_page(
    request: Request, db: Session = Depends(get_db), user: AppUser = Depends(current_user)
):
    today = today_vn()
    open_run = runs.open_run(db)
    recent = db.scalars(
        select(AccountingRun).order_by(AccountingRun.id.desc()).limit(RECENT_RUNS)
    ).all()
    due = None if open_run else runs.due_pairs(db, today)
    return render(
        request,
        "accounting.html",
        user,
        open_run=open_run,
        recent=recent,
        counts=_delivery_counts(db, [r.id for r in recent]),
        due=due,
    )


@router.post("/accounting/runs")
def start_accounting_run(
    request: Request, db: Session = Depends(get_db), user: AppUser = Depends(require_admin)
):
    return begin_run(request, db, user)


@router.get("/accounting/runs/{run_id}")
def run_page(
    request: Request,
    run_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    run = _run(db, run_id)
    today = today_vn()
    target = None
    if run.status == ledger.OPEN:
        target, _ = _target(request, db)
        if user.role == "admin" and runs.sync_pairs(db, run, user.username, target, today):
            db.commit()
    statuses = runs.run_status(db, run)
    context: dict = {"run": run, "statuses": statuses, "retryable": RETRYABLE}
    context["reading"] = any(s.state == runs.READING for s in statuses)
    context["can_retry"] = target is not None
    if run.status == ledger.OPEN:
        context["uploads"] = runs.available_uploads(db)
        if not context["reading"]:
            try:
                context["rec"] = runs.reconcile(db, run, today)
            except FileRejected as exc:
                context["rec_error"] = str(exc)
    else:
        file = db.get(GeneratedFile, run.generated_file_id) if run.generated_file_id else None
        context["file"] = file
        context["file_on_disk"] = bool(file and Path(file.stored_path).is_file())
        context["note"] = json.loads(run.missing_note) if run.missing_note else None
        context["delivery_count"] = ledger.run_delivery_count(db, run.id)
        context["reads"] = db.scalars(
            select(AccountingRunRead).where(AccountingRunRead.run_id == run.id)
        ).all()
    return render(request, "accounting_run.html", user, **context)


@router.post("/accounting/runs/{run_id}/reads/{read_id}/retry")
def retry_read(
    request: Request,
    run_id: int,
    read_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    run = _run(db, run_id)
    read = db.get(AccountingRunRead, read_id)
    if read is None or read.run_id != run.id:
        raise HTTPException(404, "Không có dòng đọc này")
    target, refusal = _target(request, db)
    if target is None:
        flash(request, refusal, "error")
        return redirect(f"/accounting/runs/{run_id}")
    try:
        job = runs.retry_read(db, run, read, user.username, target)
    except (runs.RunNotOpen, queue.JobStateError) as exc:
        db.rollback()
        flash(request, str(exc), "error")
        return redirect(f"/accounting/runs/{run_id}")
    db.commit()
    flash(
        request,
        f"Robot sẽ đọc lại zrsd004 của {read.platform} ngày {read.gi_date:%d/%m/%Y} "
        f"(việc #{job.id}).",
    )
    return redirect(f"/accounting/runs/{run_id}")


@router.post("/accounting/runs/{run_id}/upload")
async def upload_to_run(
    request: Request,
    run_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    run = _run(db, run_id)
    try:
        record = await save_upload(
            request.app.state.settings, file, kind="zrsd004", platform=None, actor=user.username
        )
        imported = ingest_zrsd004(db, record, user.username)
        runs.attach_upload(db, run, record, user.username)
    except (UploadRejected, FileRejected, runs.RunNotOpen) as exc:
        db.rollback()
        flash(request, str(exc), "error")
        return redirect(f"/accounting/runs/{run_id}")
    db.commit()
    flash(
        request,
        f"Đã thêm file zrsd004 vào đợt: {len(imported.rows)} dòng DO, "
        f"{imported.delivered} đơn chuyển sang Đã có DO.",
    )
    return redirect(f"/accounting/runs/{run_id}")


@router.post("/accounting/runs/{run_id}/attach")
def attach_to_run(
    request: Request,
    run_id: int,
    import_batch_id: int = Form(...),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    run = _run(db, run_id)
    batch = db.get(ImportBatch, import_batch_id)
    try:
        if batch is None or batch.id not in {b.id for b in runs.available_uploads(db)}:
            raise FileRejected("File này không còn trong danh sách thêm được")
        runs.attach_upload(db, run, batch, user.username)
    except (FileRejected, runs.RunNotOpen) as exc:
        db.rollback()
        flash(request, str(exc), "error")
        return redirect(f"/accounting/runs/{run_id}")
    db.commit()
    flash(request, f"Đã thêm {batch.file_name} vào đợt.")
    return redirect(f"/accounting/runs/{run_id}")


@router.get("/accounting/runs/{run_id}/draft")
def download_draft(
    request: Request,
    run_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    run = _run(db, run_id)
    if run.status != ledger.OPEN:
        flash(request, "Đợt này đã đóng, không còn bản nháp.", "error")
        return redirect(f"/accounting/runs/{run_id}")
    try:
        draft = runs.draft_file(db, run, today_vn())
    except FileRejected as exc:
        flash(request, str(exc), "error")
        return redirect(f"/accounting/runs/{run_id}")
    buffer = BytesIO()
    draft.workbook.save(buffer)
    return Response(
        buffer.getvalue(),
        media_type=XLSX,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(draft.file_name)}"},
    )


@router.post("/accounting/runs/{run_id}/finalize")
def finalize_run(
    request: Request,
    run_id: int,
    fingerprint: str = Form(""),
    allow_partial: str = Form(""),
    ack_missing: str = Form(""),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    record = None
    try:
        record = runs.finalize(
            db,
            request.app.state.settings,
            run_id,
            user.username,
            fingerprint,
            allow_partial=bool(allow_partial),
            ack_missing=bool(ack_missing),
            today=today_vn(),
        )
        db.commit()
    except ValueError as exc:  # refusals: stale draft, unread pairs, unacknowledged orders
        db.rollback()
        if record is not None:
            Path(record.stored_path).unlink(missing_ok=True)
        flash(request, str(exc), "error")
        return redirect(f"/accounting/runs/{run_id}")
    except Exception:
        db.rollback()
        if record is not None:
            Path(record.stored_path).unlink(missing_ok=True)
        raise
    flash(request, f"Đã chốt đợt #{run_id} và ghi sổ. File: {record.file_name}.")
    return redirect(f"/accounting/runs/{run_id}")


@router.post("/accounting/runs/{run_id}/cancel")
def cancel_run(
    request: Request,
    run_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    try:
        runs.cancel_run(db, run_id, user.username)
    except runs.RunNotOpen as exc:
        db.rollback()
        flash(request, str(exc), "error")
        return redirect(f"/accounting/runs/{run_id}")
    db.commit()
    flash(request, f"Đã hủy đợt #{run_id}; sổ không đổi.")
    return redirect("/accounting")


@router.get("/accounting/runs/{run_id}/file")
def download_final_file(
    run_id: int, db: Session = Depends(get_db), user: AppUser = Depends(current_user)
):
    run = _run(db, run_id)
    record = db.get(GeneratedFile, run.generated_file_id) if run.generated_file_id else None
    if record is None:
        raise HTTPException(404, "Đợt này chưa có file đã chốt")
    if not Path(record.stored_path).is_file():
        raise HTTPException(404, "File đã chốt không còn trên máy chủ (đã bị xóa hoặc mất)")
    return FileResponse(record.stored_path, filename=record.file_name, media_type=XLSX)
