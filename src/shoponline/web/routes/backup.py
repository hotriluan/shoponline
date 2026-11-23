"""The Sao lưu page: status, "back up now", Google Drive connection, schedule and retention.

Every route except the page itself is admin only (require_admin), including the ones that only
read: they expose what is on Drive or change the connection. Secrets never reach a template.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.backup import KIND_LABELS, KINDS, runner, status, trigger
from shoponline.backup.drive import DriveClient, DriveError, friendly_error
from shoponline.clock import VIETNAM
from shoponline.db.models import AppUser, BackupRun
from shoponline.web.app import current_user, flash, get_db, redirect, render, require_admin

log = logging.getLogger(__name__)
router = APIRouter()

RECENT_RUNS = 10
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


def drive_client(request: Request) -> DriveClient:
    return request.app.state.drive


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
    drive = drive_client(request).state()
    settings = runner.backup_settings(db)
    runs = db.scalars(select(BackupRun).order_by(BackupRun.id.desc()).limit(RECENT_RUNS)).all()
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
        runs=runs,
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
