import json
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.clock import today_vn
from shoponline.db.models import AppUser, OrderBatch, PlatformSetting, SapJob
from shoponline.sapjobs import queue, sap_settings
from shoponline.sapjobs.report_requests import request_zrsd001, request_zrsd004
from shoponline.sapjobs.sap_settings import SapSettingsError
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

router = APIRouter()

RECENT_BATCHES = 60  # confirmed batches offered in the command form


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
    config = sap_config(request, db)
    batches = platforms = []
    if user.role == "admin" and config.target is not None:
        batches = db.scalars(
            select(OrderBatch)
            .where(OrderBatch.confirmed_at.is_not(None))
            .order_by(OrderBatch.processing_date.desc(), OrderBatch.platform)
            .limit(RECENT_BATCHES)
        ).all()
        platforms = db.scalars(select(PlatformSetting).order_by(PlatformSetting.platform)).all()
    return render(
        request,
        "robot.html",
        user,
        control=queue.control(db),
        jobs=db.scalars(stmt).all(),
        status=status,
        read_kinds=queue.READ_KINDS,
        retryable=(queue.FAILED, queue.UNKNOWN, queue.NEED_REVIEW),
        target=config.target,
        command_refusal=robot_refusal(config),
        batches=batches,
        platforms=platforms,
        today=today_vn(),
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


@router.post("/robot/jobs/new")
def command_robot(
    request: Request,
    report: str = Form(...),
    batch_id: str = Form(""),
    platform: str = Form(""),
    gi_date: str = Form(""),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    """Ask the robot to read zrsd001 for a confirmed batch or zrsd004 for a platform and GI date."""
    if report not in ("zrsd001", "zrsd004"):
        raise HTTPException(400, "Báo cáo không hợp lệ")
    config = sap_config(request, db)
    refusal = robot_refusal(config)
    if refusal:
        flash(request, refusal, "error")
        return redirect("/robot")
    try:
        if report == "zrsd001":
            batch = db.get(OrderBatch, int(batch_id)) if batch_id.strip().isdigit() else None
            if batch is None:
                raise ValueError("Chọn một lô để đọc zrsd001.")
            if batch.confirmed_at is None:
                raise ValueError("Lô chưa xác nhận nên chưa đọc zrsd001 được.")
            job = request_zrsd001(db, config.target, batch, user.username)
            done = f"Robot sẽ đọc zrsd001 của lô {batch.platform} {batch.processing_date:%d/%m/%Y}"
        else:
            try:
                day = date.fromisoformat(gi_date)
            except ValueError:
                raise ValueError("Chọn ngày goods issue để đọc zrsd004.") from None
            if day > today_vn():
                raise ValueError("Ngày goods issue chưa tới nên SAP chưa có dữ liệu.")
            job = request_zrsd004(db, config.target, platform, day, user.username)
            done = f"Robot sẽ đọc zrsd004 của {platform} ngày {day:%d/%m/%Y}"
    except ValueError as exc:  # includes DuplicateJob, which names the open job
        db.rollback()
        flash(request, str(exc), "error")
        return redirect("/robot")
    db.commit()
    flash(request, f"{done} (việc #{job.id}).")
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


# ---------------------------------------------------------------- SAP connection settings

FORM_FIELDS = (
    "system",
    "client",
    "connection",
    "sap_user",
    "language",
    "max_failures",
    "evidence_keep_days",
)


def _latest_check(db: Session) -> SapJob | None:
    return db.scalar(
        select(SapJob)
        .where(SapJob.kind == queue.CHECK_CONNECTION)
        .order_by(SapJob.id.desc())
        .limit(1)
    )


def _wait_message(db: Session, check: SapJob, alive: bool) -> str:
    """Why a check that is still open has not finished yet."""
    if check.status == queue.RUNNING:
        return "Robot đang đăng nhập SAP để kiểm tra…"
    other = db.scalar(
        select(SapJob)
        .where(SapJob.status == queue.RUNNING, SapJob.kind != queue.CHECK_CONNECTION)
        .order_by(SapJob.id)
        .limit(1)
    )
    if other is not None:
        return f"Đang chờ robot xong việc #{other.id}"
    if not alive:
        return "Robot không chạy — việc kiểm tra sẽ chạy khi robot bật lại"
    return "Đang chờ robot nhận việc kiểm tra…"


def _connection_page(
    request: Request,
    db: Session,
    user: AppUser,
    form: dict | None = None,
    error: str | None = None,
    status_code: int = 200,
):
    config = sap_config(request, db)
    control = queue.control(db)
    check = _latest_check(db)
    alive = sap_settings.robot_alive(control)
    checking = check is not None and check.status in (queue.PENDING, queue.RUNNING)
    values = form or {name: getattr(config, name) for name in FORM_FIELDS}
    return render(
        request,
        "sap_connection.html",
        user,
        status_code=status_code,
        error=error,
        config=config,
        form=values,
        control=control,
        alive=alive,
        entries=json.loads(control.saplogon_entries or "[]"),
        check=check,
        checking=checking,
        wait_message=_wait_message(db, check, alive) if checking else None,
        check_result=queue.result_of(check) if check is not None else {},
    )


@router.get("/robot/sap-connection")
def sap_connection_page(
    request: Request, db: Session = Depends(get_db), user: AppUser = Depends(current_user)
):
    return _connection_page(request, db, user)


@router.post("/robot/sap-connection")
def save_sap_connection(
    request: Request,
    action: str = Form("save"),
    system: str = Form(""),
    client: str = Form(""),
    connection: str = Form(""),
    sap_user: str = Form(""),
    language: str = Form(""),
    max_failures: str = Form(""),
    evidence_keep_days: str = Form(""),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    """Save the form (save, save_check) and/or queue a connection check (check, save_check)."""
    form = {
        "system": system,
        "client": client,
        "connection": connection,
        "sap_user": sap_user,
        "language": language,
        "max_failures": max_failures,
        "evidence_keep_days": evidence_keep_days,
    }
    messages = []
    if action in ("save", "save_check"):
        try:
            changes = sap_settings.save(db, user.username, request.app.state.env, **form)
        except SapSettingsError as exc:
            db.rollback()
            return _connection_page(request, db, user, form, str(exc), status_code=422)
        db.commit()
        messages.append("Đã lưu cấu hình SAP." if changes else "Cấu hình không đổi.")
        if "system" in changes or "client" in changes:
            messages.append("Đã đổi hệ thống hoặc client: cần kiểm tra kết nối thành công.")
    if action in ("check", "save_check"):
        config = sap_config(request, db)
        if config.target is None:
            flash(request, "Chưa đặt hệ thống và client SAP nên chưa kiểm tra được.", "error")
            return redirect("/robot/sap-connection")
        queue.supersede_checks(db, user.username)
        try:
            job = queue.enqueue(
                db, queue.CHECK_CONNECTION, config.target, queue.CHECK_KEY, {}, user.username
            )
        except queue.DuplicateJob as exc:
            db.rollback()
            flash(request, f"{exc}. Chờ lần kiểm tra đó xong rồi bấm lại.", "error")
            return redirect("/robot/sap-connection")
        db.commit()
        messages.append(f"Đã xếp việc kiểm tra #{job.id} cho {config.target}.")
    flash(request, " ".join(messages))
    return redirect("/robot/sap-connection")
