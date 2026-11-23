"""The Sao lưu page: status, "back up now", Google Drive connection, schedule and retention.

Every route except the page itself is admin only (require_admin), including the ones that only
read: they expose what is on Drive or change the connection. Secrets never reach a template.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.backup import (
    KIND_LABELS,
    KINDS,
    inventory,
    manage,
    restore,
    runner,
    status,
    trigger,
)
from shoponline.backup.drive import DriveClient, DriveError, friendly_error
from shoponline.backup.staging import staging_dir
from shoponline.clock import VIETNAM
from shoponline.db.models import AppUser, BackupRequest, BackupRun, EventLog
from shoponline.web.app import current_user, flash, get_db, redirect, render, require_admin
from shoponline.web.auth import authenticate
from shoponline.web.pagination import paginate

log = logging.getLogger(__name__)
router = APIRouter()

WEEKDAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ nhật"]
CARDS = [
    (
        "db",
        "Sao lưu Database",
        "Toàn bộ dữ liệu nghiệp vụ: đơn, dòng hàng, ánh xạ SAP, số SO/DO/hóa đơn, sổ gửi kế "
        "toán, tiền về, người dùng web, cấu hình SAP, nhật ký sự kiện.",
    ),
    (
        "app",
        "Sao lưu Ứng dụng",
        "Mã nguồn đang chạy (git bundle), file .env (không gồm mật khẩu sao lưu), config/*.yaml "
        "và thư mục dữ liệu. Không gồm .venv.",
    ),
    ("full", "Sao lưu Toàn bộ", "Database và Ứng dụng trong một file; là gói để chuyển máy."),
]
LOCAL_LABELS = {
    "running": "Đang chạy",
    "ok": "Thành công",
    "partial": "Một phần",
    "failed": "Lỗi",
    "interrupted": "Bị dừng giữa chừng",
    "rotated": "Đã xóa theo số bản giữ",
    "deleted": "Đã xóa",
    "missing": "Không có (chỉ trên Drive)",
}
DRIVE_LABELS = {
    None: "Không yêu cầu",
    "uploading": "Đang tải lên",
    "ok": "Đã lên Drive (MD5 khớp)",
    "failed": "Lỗi Drive",
    "not_connected": "Chưa kết nối",
    "rotated": "Đã xóa theo số bản giữ",
    "deleted": "Đã xóa",
}
SOURCE_LABELS = {
    "schedule": "Theo lịch",
    "manual": "Bấm tay",
    "deploy": "Trước deploy",
    "safety": "An toàn trước phục hồi",
    "migration": "Chuyển máy",
    "upload": "Tải lên",
    "drive_found": "Tìm thấy trên Drive",
}


STATE_FILTERS = [
    ("ok", "Thành công"),
    ("failed", "Lỗi"),
    ("running", "Đang chạy"),
    ("drive_failed", "Lỗi Drive"),
    ("only_drive", "Chỉ trên Drive"),
    ("deleted", "Đã xóa"),
]


def drive_client(request: Request) -> DriveClient:
    return request.app.state.drive


def web_context(request: Request, db: Session) -> runner.Context:
    """What backup code needs, built for a web request (no locks are taken from the web)."""
    return runner.Context(
        settings=request.app.state.settings,
        session_factory=request.app.state.session_factory,
        engine=db.get_bind(),
        repo_root=restore.CODE_ROOT,
        drive=request.app.state.drive,
    )


def _drive_listing(request: Request, db: Session, connected: bool):
    """The cached Drive list (None when not connected or unreadable) and an error text."""
    if not connected:
        return None, None
    listing = request.app.state.drive_listing
    files, error = listing.get(request.app.state.drive, inventory.newest_finish(db))
    if files is not None:
        inventory.add_drive_found(db, files)
    return files, error


def _filtered_runs(request: Request):
    stmt = select(BackupRun).order_by(BackupRun.started_at.desc(), BackupRun.id.desc())
    params = request.query_params
    if params.get("kind") in KINDS:
        stmt = stmt.where(BackupRun.kind == params["kind"])
    if params.get("source") in SOURCE_LABELS:
        stmt = stmt.where(BackupRun.source == params["source"])
    state = params.get("state")
    if state == "ok":
        stmt = stmt.where(BackupRun.local_status.in_(("ok", "partial")))
    elif state == "failed":
        stmt = stmt.where(BackupRun.local_status.in_(("failed", "interrupted")))
    elif state == "running":
        stmt = stmt.where(BackupRun.local_status == "running")
    elif state == "drive_failed":
        stmt = stmt.where(BackupRun.drive_status == "failed")
    elif state == "only_drive":
        stmt = stmt.where(BackupRun.local_status == "missing")
    elif state == "deleted":
        stmt = stmt.where(BackupRun.deleted_at.is_not(None))
    return stmt


def _hhmm(value) -> str:
    return value.strftime("%H:%M")


def _places(db: Session) -> list[dict]:
    """Per kind: the latest successful backup on this machine and on Drive."""
    return [
        {
            "kind": kind,
            "label": KIND_LABELS[kind],
            "local": status.last_success(db, kind, "local"),
            "drive": status.last_success(db, kind, "drive"),
        }
        for kind in KINDS
    ]


@router.get("/backup")
def backup_page(
    request: Request, db: Session = Depends(get_db), user: AppUser = Depends(current_user)
):
    client = drive_client(request)
    drive = client.state()
    settings = runner.backup_settings(db)
    listing, listing_error = _drive_listing(request, db, drive["status"] == "connected")
    stmt = _filtered_runs(request)
    page = paginate(
        request, db, stmt, BackupRun.file_name, BackupRun.actor, BackupRun.source, BackupRun.kind
    )
    rows = inventory.build_rows(
        page.items,
        inventory.local_names(request.app.state.settings),
        listing,
        drive["status"] == "connected",
        restore.known_revisions(),
    )
    waiting = db.scalars(
        select(BackupRequest)
        .where(BackupRequest.status.in_(("pending", "running")))
        .order_by(BackupRequest.id)
    ).all()
    return render(
        request,
        "backup.html",
        user,
        drive=drive,
        busy=status.is_busy(db),
        settings=settings,
        form={
            "db_time": _hhmm(settings.db_time),
            "full_time": _hhmm(settings.full_time),
        },
        weekdays=list(enumerate(WEEKDAYS)),
        next_runs=status.next_runs(db),
        places=_places(db),
        rows=rows,
        page=page,
        waiting=waiting,
        listing_error=listing_error,
        filters={k: request.query_params.get(k, "") for k in ("kind", "source", "state")},
        state_options=STATE_FILTERS,
        source_options=list(SOURCE_LABELS.items()),
        max_upload_mb=manage.MAX_UPLOAD // 2**20,
        cards=CARDS,
        local_labels=LOCAL_LABELS,
        drive_labels=DRIVE_LABELS,
        source_labels=SOURCE_LABELS,
        kind_labels=KIND_LABELS,
    )


# --- back up now ------------------------------------------------------------------------------


@router.post("/backup/run")
def run_backup_now(
    request: Request,
    kind: str = Form(...),
    to_drive: str = Form(""),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    if kind not in KINDS:
        flash(request, "Loại sao lưu không hợp lệ.", "error")
        return redirect("/backup")
    want_drive = bool(to_drive) and drive_client(request).connected()
    queued = trigger.enqueue(
        db, "backup", user.username, kind=kind, to_drive=want_drive, exclusive=True
    )
    if queued is None:
        flash(request, "Đang có bản sao lưu chạy.", "error")
    elif trigger.start_task(trigger.BACKUP_TASK):
        flash(request, f"Đã bắt đầu sao lưu {KIND_LABELS[kind]}.")
    else:
        flash(
            request,
            f"Đã xếp yêu cầu sao lưu {KIND_LABELS[kind]}; sẽ chạy trong vòng 15 phút.",
        )
    return redirect("/backup")


# --- Google Drive -----------------------------------------------------------------------------


def _drive_action(request: Request, work) -> bool:
    """Run a Drive call; its failure becomes a flash message. True when it worked."""
    try:
        work()
    except DriveError as exc:
        flash(request, str(exc), "error")
    except Exception as exc:
        log.exception("Thao tác Google Drive lỗi")
        flash(request, friendly_error(exc), "error")
    else:
        return True
    return False


@router.post("/backup/drive/client")
def save_drive_client(
    request: Request,
    client_id: str = Form(""),
    client_secret: str = Form(""),
    user: AppUser = Depends(require_admin),
):
    drive = drive_client(request)
    saved = _drive_action(
        request, lambda: drive.set_client(client_id, client_secret, user.username)
    )
    if saved and not drive.state()["has_secret"]:
        flash(request, "Chưa có Client Secret; nhập cả Client ID và Secret.", "error")
    elif saved:
        flash(request, "Đã lưu Client ID và Secret.")
    return redirect("/backup")


@router.post("/backup/drive/connect")
def connect_drive(request: Request, user: AppUser = Depends(require_admin)):
    drive = drive_client(request)
    _drive_action(request, lambda: drive.start_device_flow(user.username))
    return redirect("/backup")


@router.post("/backup/drive/poll")
def poll_drive(request: Request, user: AppUser = Depends(require_admin)):
    """Called by the page every few seconds while the person approves on google.com/device."""
    try:
        result = drive_client(request).poll_device_flow()
    except DriveError as exc:
        flash(request, str(exc), "error")
        result = {"status": "error", "message": str(exc), "interval": 5}
    except Exception as exc:
        log.exception("Hỏi Google về mã thiết bị lỗi")
        result = {"status": "error", "message": friendly_error(exc), "interval": 5}
        flash(request, result["message"], "error")
    if result["status"] == "connected":
        flash(request, result["message"])
    elif result["status"] in ("denied", "expired"):
        flash(request, result["message"], "error")
    return JSONResponse(result)


@router.post("/backup/drive/check")
def check_drive(request: Request, user: AppUser = Depends(require_admin)):
    drive = drive_client(request)

    def work():
        info = drive.check()
        flash(request, f"Kết nối Google Drive tốt: {info['email']}.")

    _drive_action(request, work)
    return redirect("/backup")


@router.post("/backup/drive/disconnect")
def disconnect_drive(request: Request, user: AppUser = Depends(require_admin)):
    drive = drive_client(request)

    def work():
        drive.disconnect(user.username)
        flash(
            request,
            "Đã ngắt kết nối Google Drive. File trên Drive vẫn còn; bản sao lưu mới "
            "chỉ ở máy chủ cho tới khi kết nối lại.",
        )

    _drive_action(request, work)
    return redirect("/backup")


@router.get("/backup/drive/files")
def drive_files(
    request: Request, db: Session = Depends(get_db), user: AppUser = Depends(require_admin)
):
    files, error = [], None
    try:
        files = drive_client(request).list_backups()
    except DriveError as exc:
        error = str(exc)
    except Exception as exc:
        log.exception("Liệt kê Google Drive lỗi")
        error = friendly_error(exc)
    known = (
        {
            row.file_name: row
            for row in db.scalars(
                select(BackupRun).where(BackupRun.file_name.in_([f["name"] for f in files]))
            )
        }
        if files
        else {}
    )
    files.sort(key=lambda f: f["name"], reverse=True)
    return render(
        request, "backup_drive_files.html", user, files=files, known=known, files_error=error
    )


# --- schedule and retention -------------------------------------------------------------------


def _time(text: str, label: str, errors: list[str]):
    try:
        return datetime.strptime(text.strip(), "%H:%M").time()
    except ValueError:
        errors.append(f"{label} phải có dạng HH:MM, ví dụ 16:30.")
        return None


def _number(text: str, label: str, low: int, high: int, errors: list[str]) -> int | None:
    if not text.strip().isdigit() or not low <= int(text) <= high:
        errors.append(f"{label} phải là số từ {low} đến {high}.")
        return None
    return int(text)


@router.post("/backup/settings")
def save_settings(
    request: Request,
    db_time: str = Form(...),
    full_weekday: str = Form(...),
    full_time: str = Form(...),
    keep_db: str = Form(...),
    keep_app: str = Form(...),
    full_max_days: str = Form(...),
    drive_on_schedule: str = Form(""),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    errors: list[str] = []
    values = {
        "db_time": _time(db_time, "Giờ sao lưu Database", errors),
        "full_weekday": _number(full_weekday, "Ngày sao lưu Toàn bộ", 0, 6, errors),
        "full_time": _time(full_time, "Giờ sao lưu Toàn bộ", errors),
        "keep_db": _number(keep_db, "Số bản Database giữ", 1, 100, errors),
        "keep_app": _number(keep_app, "Số bản Ứng dụng giữ", 1, 100, errors),
        "full_max_days": _number(full_max_days, "Số ngày giữ bản Toàn bộ", 7, 90, errors),
    }
    if errors:
        flash(request, "\n".join(errors), "error")
        return redirect("/backup")
    row = runner.backup_settings(db)
    for name, value in values.items():
        setattr(row, name, value)
    row.drive_on_schedule = bool(drive_on_schedule)
    row.changed_by, row.changed_at = user.username, datetime.now(VIETNAM)
    db.commit()
    flash(request, "Đã lưu lịch và số bản giữ. Áp dụng ngay từ lần kiểm tra kế tiếp (15 phút).")
    return redirect("/backup")


# --- the backup list: files and actions -------------------------------------------------------


def _run_or_none(db: Session, run_id: int) -> BackupRun | None:
    return db.get(BackupRun, run_id)


def _wake(request: Request, task: str, what: str) -> None:
    if trigger.start_task(task):
        flash(request, f"Đã bắt đầu {what}.")
    else:
        flash(request, f"Đã xếp yêu cầu {what}; sẽ chạy trong vòng 15 phút.")


@router.get("/backup/runs/{run_id}/status")
def run_status(run_id: int, db: Session = Depends(get_db), user: AppUser = Depends(require_admin)):
    """What the page polls for a running row. Labels only: never the raw error text."""
    run = _run_or_none(db, run_id)
    if run is None:
        return JSONResponse({"ok": False}, status_code=404)
    local, _ = inventory._local_state(run, True, False)
    drive, _ = inventory._drive_state(run, None, True)
    done = run.local_status != "running" and run.drive_status != "uploading"
    return JSONResponse({"ok": True, "local": local, "drive": drive, "finished": done})


@router.get("/backup/runs/{run_id}/download")
def download_backup(
    request: Request,
    run_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    run = _run_or_none(db, run_id)
    if run is None:
        flash(request, "Không có bản sao lưu này.", "error")
        return redirect("/backup")
    try:
        path = restore.fetch(web_context(request, db), str(run_id))
    except (restore.RestoreError, DriveError) as exc:
        flash(request, str(exc), "error")
        return redirect("/backup")
    db.add(EventLog(actor=user.username, kind="backup_download", detail=run.file_name))
    db.commit()
    return FileResponse(path, filename=run.file_name, media_type="application/x-7z-compressed")


@router.post("/backup/runs/{run_id}/verify")
def verify_backup(
    request: Request,
    run_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    if _run_or_none(db, run_id) is None:
        flash(request, "Không có bản sao lưu này.", "error")
        return redirect("/backup")
    trigger.enqueue(db, "verify", user.username, target_run_id=run_id)
    _wake(request, trigger.BACKUP_TASK, "kiểm tra bản sao lưu")
    return redirect("/backup")


@router.post("/backup/runs/{run_id}/retry-drive")
def retry_drive(
    request: Request,
    run_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    """Upload the same file again; no new backup is made."""
    run = _run_or_none(db, run_id)
    if run is None:
        flash(request, "Không có bản sao lưu này.", "error")
    elif not drive_client(request).connected():
        flash(request, "Chưa kết nối Google Drive.", "error")
    else:
        request.app.state.drive_listing.invalidate()
        trigger.enqueue(db, "retry_drive", user.username, target_run_id=run_id, to_drive=True)
        _wake(request, trigger.BACKUP_TASK, "tải lại lên Google Drive")
    return redirect("/backup")


@router.post("/backup/runs/{run_id}/delete")
def delete_backup(
    request: Request,
    run_id: int,
    where: str = Form("local"),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    if where not in ("local", "drive", "both"):
        flash(request, "Chọn nơi cần xóa.", "error")
        return redirect("/backup")
    try:
        message = manage.delete_files(web_context(request, db), run_id, where, user.username)
    except (manage.ManageError, DriveError) as exc:
        flash(request, str(exc), "error")
    except Exception as exc:
        log.exception("Xóa bản sao lưu lỗi")
        flash(request, friendly_error(exc), "error")
    else:
        flash(request, message)
    db.commit()
    request.app.state.drive_listing.invalidate()
    return redirect("/backup")


@router.post("/backup/runs/{run_id}/restore")
def restore_backup(
    request: Request,
    run_id: int,
    mode: str = Form("drill"),
    password: str = Form(""),
    confirm_name: str = Form(""),
    force: str = Form(""),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    run = _run_or_none(db, run_id)
    if run is None or run.kind == "app":
        flash(request, "Bản này không phục hồi trên máy đang chạy.", "error")
        return redirect("/backup")
    if mode == "drill":
        trigger.enqueue(db, "drill", user.username, target_run_id=run_id)
        _wake(request, trigger.BACKUP_TASK, "diễn tập phục hồi")
        return redirect("/backup")
    problem = _production_refusal(request, db, user, run, password, confirm_name, force)
    if problem:
        flash(request, problem, "error")
        return redirect("/backup")
    queued = trigger.enqueue(
        db,
        "restore",
        user.username,
        target_run_id=run_id,
        result={"force": bool(force)},
    )
    if trigger.start_task(trigger.RESTORE_TASK):
        return redirect(f"/backup/restoring/{queued.id}")
    queued.status, queued.finished_at = "failed", datetime.now(VIETNAM)
    queued.message = "Không chạy được tác vụ phục hồi (shoponline-restore)"
    db.commit()
    flash(
        request,
        "Không chạy được tác vụ phục hồi (shoponline-restore). Kiểm tra tác vụ trong Task "
        "Scheduler, hoặc phục hồi bằng dòng lệnh trên máy chủ.",
        "error",
    )
    return redirect("/backup")


def _production_refusal(request, db, user, run, password, confirm_name, force) -> str | None:
    if authenticate(db, user.username, password) is None:
        return "Sai mật khẩu của bạn; không phục hồi."
    if confirm_name.strip() != run.file_name:
        return "Tên file gõ lại không khớp; không phục hồi."
    revision = (run.manifest or {}).get("alembic_revision")
    if revision and revision not in restore.known_revisions():
        return f"Bản từ phiên bản mới hơn (revision {revision}); cập nhật mã trước."
    busy = db.scalar(
        select(BackupRequest.id).where(
            BackupRequest.action == "restore", BackupRequest.status.in_(("pending", "running"))
        )
    )
    if busy:
        return "Đang có yêu cầu phục hồi khác chờ hoặc chạy."
    if run.manifest is None and not force:
        return "Bản cũ không có manifest: tích ô xác nhận đã hiểu rồi gửi lại (nên diễn tập trước)."
    if restore.other_active_users(db, user.username) and not force:
        return "Có người dùng khác đang dùng web; tích ô xác nhận rồi gửi lại."
    return None


@router.get("/backup/restoring/{request_id}")
def restoring_page(
    request: Request,
    request_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    return render(request, "backup_restoring.html", user, request_id=request_id)


@router.get("/backup/restoring/{request_id}/status")
def restoring_status(
    request_id: int, db: Session = Depends(get_db), user: AppUser = Depends(require_admin)
):
    req = db.get(BackupRequest, request_id)
    if req is None:
        return JSONResponse({"ok": False}, status_code=404)
    return JSONResponse({"ok": True, "status": req.status, "message": req.message})


# --- upload -----------------------------------------------------------------------------------


def _upload_reply(request: Request, ok: bool, message: str, status_code: int = 200):
    flash(request, message, "info" if ok else "error")
    return JSONResponse({"ok": ok, "message": message}, status_code=status_code)


@router.post("/backup/upload")
async def upload_backup(
    request: Request, db: Session = Depends(get_db), user: AppUser = Depends(require_admin)
):
    """The file is the request body itself (not multipart), so its size is known and limited
    before anything is written, and a refused file never reaches the disk beyond the limit."""
    length = request.headers.get("content-length", "")
    if not length.isdigit() or int(length) == 0:
        return _upload_reply(request, False, "Thiếu kích thước file.", 411)
    size = int(length)
    if size > manage.MAX_UPLOAD:
        return _upload_reply(request, False, "File quá lớn (tối đa 1 GB).", 413)
    settings = request.app.state.settings
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(settings.data_dir).free < 2 * size:
        return _upload_reply(request, False, "Không đủ chỗ trống trên ổ dữ liệu.", 507)
    name = unquote(request.headers.get("x-file-name", "")).strip()
    ctx = web_context(request, db)
    with staging_dir(settings.backup_work_dir, "upload") as work:
        part = work / "upload.7z"
        received = 0
        with part.open("wb") as out:
            async for chunk in request.stream():
                received += len(chunk)
                if received > size or received > manage.MAX_UPLOAD:
                    break
                out.write(chunk)
        if received != size:
            return _upload_reply(request, False, "File tải lên không đủ hoặc vượt giới hạn.", 400)
        try:
            run = await run_in_threadpool(manage.ingest_upload, ctx, part, name, user.username)
        except manage.ManageError as exc:
            return _upload_reply(request, False, str(exc), 422)
    db.commit()
    request.app.state.drive_listing.invalidate()
    return _upload_reply(request, True, f"Đã nhận bản sao lưu {run.file_name}.")
