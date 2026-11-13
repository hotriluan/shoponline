"""FastAPI application: server-rendered pages, session login, admin/viewer roles."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from shoponline.config import Settings
from shoponline.db.models import AppUser
from shoponline.db.session import session_factory as default_session_factory
from shoponline.domain import states
from shoponline.sapjobs import sap_settings
from shoponline.sapjobs.queue import LABELS as JOB_LABELS
from shoponline.sapjobs.queue import control as robot_control

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
TEMPLATES.env.globals["STATUS_LABELS"] = states.LABELS
TEMPLATES.env.globals["JOB_LABELS"] = JOB_LABELS
TEMPLATES.env.filters["money"] = lambda v: "" if v is None else f"{int(v):,}".replace(",", ".")
TEMPLATES.env.filters["localtime"] = lambda v, fmt="%d/%m/%Y %H:%M": (
    "" if v is None else (v.astimezone() if v.tzinfo else v).strftime(fmt)
)
BACKUP_MAX_AGE = timedelta(hours=36)


class LoginRequired(Exception):
    pass


class AdminRequired(Exception):
    pass


def get_db(request: Request) -> Iterator[Session]:
    """Handlers commit explicitly; anything left uncommitted is rolled back."""
    session: Session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def current_user(request: Request, db: Session = Depends(get_db)) -> AppUser:
    user_id = request.session.get("user_id")
    user = db.get(AppUser, user_id) if user_id else None
    if user is None or not user.active:
        raise LoginRequired()
    return user


def require_admin(user: AppUser = Depends(current_user)) -> AppUser:
    if user.role != "admin":
        raise AdminRequired()
    return user


def flash(request: Request, message: str, kind: str = "info") -> None:
    request.session.setdefault("flash", []).append({"kind": kind, "message": message})


def backup_warning(settings: Settings) -> str | None:
    marker = settings.backup_marker
    try:
        last = datetime.fromisoformat(marker.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return "Chưa có bản sao lưu database nào được ghi nhận."
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    if datetime.now(UTC) - last > BACKUP_MAX_AGE:
        return f"Bản sao lưu gần nhất lúc {last.astimezone():%d/%m/%Y %H:%M}, đã quá 36 giờ."
    return None


@dataclass(frozen=True)
class RobotState:
    enabled: bool = False  # a SAP system and client are configured
    verified: bool = True  # a connection check succeeded for that system and client
    warning: str | None = None  # shown on every page until an admin acts


def sap_config(request: Request, db: Session) -> sap_settings.SapSettings:
    return sap_settings.load(db, request.app.state.env)


def robot_state(request: Request) -> RobotState:
    with request.app.state.session_factory() as db:
        config = sap_config(request, db)
        if config.target is None:
            return RobotState()
        if not config.target_verified:
            return RobotState(
                True,
                False,
                f"Cấu hình SAP {config.target} chưa được xác nhận: robot chưa đọc báo cáo "
                "cho đến khi kiểm tra kết nối thành công.",
            )
        row = robot_control(db)
        if not row.paused:
            return RobotState(True, True)
        reason = row.paused_reason or "không rõ lý do"
        return RobotState(True, True, f"Robot SAP đang dừng: {reason}")


def render(
    request: Request, template: str, user: AppUser | None, status_code: int = 200, **context
):
    messages = request.session.pop("flash", [])
    settings: Settings = request.app.state.settings
    robot = robot_state(request) if user else RobotState()
    return TEMPLATES.TemplateResponse(
        request,
        template,
        {
            "user": user,
            "messages": messages,
            "backup_warning": backup_warning(settings) if user else None,
            "robot_warning": robot.warning,
            "robot_enabled": robot.enabled,
            "robot_verified": robot.verified,
            **context,
        },
        status_code=status_code,
    )


def is_autosave(request: Request) -> bool:
    """Set by the page script that saves a row or field as soon as it is edited."""
    return request.headers.get("x-autosave") == "1"


def autosave_reply(message: str, ok: bool = True, status: int | None = None) -> JSONResponse:
    return JSONResponse({"ok": ok, "message": message}, status_code=status or (200 if ok else 422))


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def create_app(
    settings: Settings,
    session_factory: Callable[[], Session] | None = None,
    env: Mapping[str, str] | None = None,
) -> FastAPI:
    from shoponline.web.routes import (
        batches,
        customers,
        imports,
        login,
        orders,
        robot,
        sap_reports,
        sku_mapping,
    )

    app = FastAPI(title="shoponline", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    # The SAP settings in the database fall back to these environment values.
    app.state.env = dict(os.environ if env is None else env)
    app.state.session_factory = session_factory or default_session_factory(settings.database_url)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        same_site="strict",
        max_age=12 * 3600,
        session_cookie="shoponline_session",
    )

    @app.exception_handler(LoginRequired)
    async def _login_required(request: Request, _exc: LoginRequired):
        if is_autosave(request):
            return autosave_reply("Phiên đăng nhập đã hết, hãy đăng nhập lại.", False, 401)
        return redirect("/login")

    @app.exception_handler(AdminRequired)
    async def _admin_required(request: Request, _exc: AdminRequired):
        if is_autosave(request):
            return autosave_reply("Tài khoản xem không được thay đổi dữ liệu.", False, 403)
        flash(request, "Tài khoản xem không được thay đổi dữ liệu.", "error")
        return redirect(request.headers.get("referer") or "/batches")

    @app.get("/")
    def home():
        return redirect("/batches")

    for module in (login, imports, batches, orders, sku_mapping, customers, sap_reports, robot):
        app.include_router(module.router)
    return app
