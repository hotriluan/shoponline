"""Pick the SAP GUI session that matches the job's system, client and robot user.

Works on the SAP GUI Scripting object model (engine → connections → sessions); tests pass a
fake engine with the same shape, so this module never imports win32com itself.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from shoponline.sapjobs.queue import SapTarget
from shoponline.saprobot.errors import SessionUnavailable, WrongSystem
from shoponline.saprobot.guard import VKEY_ENTER, GuardedSession
from shoponline.saprobot.popups import PopupRule, handle_popups
from shoponline.saprobot.screen import Screens
from shoponline.saprobot.statusbar import read_status

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Identity:
    system: str
    client: str
    user: str

    def __str__(self) -> str:
        return f"{self.system}/{self.client} user {self.user}"


@dataclass(frozen=True)
class LoginConfig:
    """How the robot logs in again; the password comes from the robot machine's secret store."""

    connection: str  # SAP Logon entry name, bound to exactly one system
    user: str
    password: str
    language: str = ""


def _children(collection) -> list:
    return [collection(i) for i in range(collection.Count)]


def identity(gui_session) -> Identity:
    info = gui_session.Info
    return Identity(
        system=str(info.SystemName).strip(),
        client=str(info.Client).strip(),
        user=str(info.User).strip().upper(),
    )


def open_sessions(engine) -> list:
    """Every live session; a session whose connection dropped raises on access and is skipped."""
    sessions = []
    for connection in _children(engine.Children):
        try:
            sessions.extend(_children(connection.Children))
        except Exception as exc:
            log.warning("Bỏ qua kết nối SAP không đọc được: %s", exc)
    live = []
    for gui_session in sessions:
        try:
            identity(gui_session)
        except Exception as exc:
            log.warning("Bỏ qua phiên SAP không đọc được: %s", exc)
            continue
        live.append(gui_session)
    return live


def check_identity(gui_session, target: SapTarget, user: str) -> Identity:
    found = identity(gui_session)
    expected = Identity(target.system, target.client, user.upper())
    if found != expected:
        raise WrongSystem(f"Phiên SAP đang mở là {found}, việc cần {expected}")
    return found


def login(engine, config: LoginConfig, screens: Screens, popups: list[PopupRule]):
    """Open the configured SAP Logon entry and log in; returns the new (raw) session.

    The login screen is typed through the T-code guard like every other screen.
    """
    try:
        connection = engine.OpenConnection(config.connection, True)
        gui_session = connection.Children(0)
    except Exception as exc:
        raise SessionUnavailable(f"Không mở được kết nối '{config.connection}': {exc}") from exc
    guarded = GuardedSession(gui_session)
    screens.set_text(guarded, "login", "user", config.user)
    screens.set_text(guarded, "login", "password", config.password)
    if config.language:
        screens.set_text(guarded, "login", "language", config.language)
    guarded.send_vkey(VKEY_ENTER)
    handle_popups(guarded, popups)
    status = read_status(guarded)
    if status.is_error:
        raise SessionUnavailable(f"Đăng nhập SAP không thành công: {status}")
    return gui_session


def ensure_session(
    engine, target: SapTarget, config: LoginConfig, screens: Screens, popups: list[PopupRule]
) -> tuple[object, Identity]:
    """Return the session for target, logging in again when no session is open at all.

    Open sessions that all belong to another system mean someone is using the machine or the
    configuration is wrong: the robot refuses instead of logging in next to them. The caller
    wraps the returned session in GuardedSession before any action.
    """
    sessions = open_sessions(engine)
    for gui_session in sessions:
        try:
            return gui_session, check_identity(gui_session, target, config.user)
        except WrongSystem:
            continue
    if sessions:
        found = ", ".join(str(identity(s)) for s in sessions)
        raise WrongSystem(f"Không có phiên nào của {target} user {config.user}; đang mở: {found}")
    log.info("Không có phiên SAP nào, đăng nhập lại qua '%s'", config.connection)
    gui_session = login(engine, config, screens, popups)
    return gui_session, check_identity(gui_session, target, config.user)


def scripting_engine():
    """The running SAP GUI's scripting engine (needs pywin32 and SAP Logon started)."""
    try:
        import win32com.client
    except ImportError as exc:
        raise SessionUnavailable("Thiếu pywin32: chạy 'uv sync --extra robot'") from exc
    try:
        return win32com.client.GetObject("SAPGUI").GetScriptingEngine
    except Exception as exc:
        raise SessionUnavailable(f"SAP Logon chưa chạy hoặc chưa bật scripting: {exc}") from exc
