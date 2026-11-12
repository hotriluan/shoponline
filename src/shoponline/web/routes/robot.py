from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.db.models import AppUser, SapJob
from shoponline.sapjobs import queue
from shoponline.web.app import current_user, flash, get_db, redirect, render, require_admin

router = APIRouter()


@router.get("/robot")
def robot_page(
    request: Request,
    status: str | None = None,
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    stmt = select(SapJob).order_by(SapJob.id.desc()).limit(200)
    if status in queue.LABELS:
        stmt = stmt.where(SapJob.status == status)
    return render(
        request,
        "robot.html",
        user,
        control=queue.control(db),
        jobs=db.scalars(stmt).all(),
        status=status,
        read_kinds=queue.READ_KINDS,
        retryable=(queue.FAILED, queue.UNKNOWN, queue.NEED_REVIEW),
        target=request.app.state.settings.sap_target,
        payload_of=queue.payload_of,
        result_of=queue.result_of,
    )


@router.post("/robot/pause")
def pause_robot(
    request: Request,
    reason: str = Form(""),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    queue.pause(db, user.username, reason.strip() or f"{user.username} tạm dừng")
    db.commit()
    flash(request, "Đã tạm dừng robot; việc đang chạy (nếu có) vẫn chạy xong.")
    return redirect("/robot")


@router.post("/robot/resume")
def resume_robot(
    request: Request, db: Session = Depends(get_db), user: AppUser = Depends(require_admin)
):
    queue.resume(db, user.username)
    db.commit()
    flash(request, "Đã bật lại robot.")
    return redirect("/robot")


def _job(db: Session, job_id: int) -> SapJob:
    job = db.get(SapJob, job_id)
    if job is None:
        raise HTTPException(404, "Không có việc này")
    return job


@router.post("/robot/jobs/{job_id}/retry")
def retry_job(
    request: Request,
    job_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    try:
        queue.retry(db, _job(db, job_id), user.username)
    except queue.JobStateError as exc:
        db.rollback()
        flash(request, str(exc), "error")
        return redirect("/robot")
    db.commit()
    flash(request, f"Việc #{job_id} đã về hàng chờ.")
    return redirect("/robot")


@router.get("/robot/jobs/{job_id}/evidence")
def job_evidence(
    request: Request,
    job_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    job = _job(db, job_id)
    root = request.app.state.settings.evidence_dir.resolve()
    path = Path(job.evidence_path).resolve() if job.evidence_path else None
    if path is None or not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404, "Không có ảnh (có thể đã quá hạn giữ và bị xóa)")
    return FileResponse(path, media_type="image/png")
