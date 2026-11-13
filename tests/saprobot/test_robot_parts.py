import os
import time
from datetime import date

import pytest

from shoponline.sapjobs.queue import SapTarget
from shoponline.saprobot import evidence
from shoponline.saprobot.errors import (
    SapMessageError,
    ScreenConfigMissing,
    SessionUnavailable,
    UnknownPopup,
    WrongSystem,
)
from shoponline.saprobot.guard import GuardedSession
from shoponline.saprobot.popups import PopupRule, handle_popups, load_rules
from shoponline.saprobot.screen import Screens
from shoponline.saprobot.session import (
    LoginConfig,
    ensure_session,
    logoff,
    logoff_sessions_of,
    scripting_engine,
)
from shoponline.saprobot.statusbar import check_status, read_status
from tests.saprobot.fake_sap import FakeEngine, FakeSession, Info, engine_with

QA = SapTarget("QAS", "300")
LOGIN = LoginConfig(connection="QA robot", user="robot01", password="secret-pw")
SCREENS = Screens(
    {"login": {"user": "wnd[0]/usr/user", "password": "wnd[0]/usr/pw", "language": "wnd[0]/usr/l"}}
)
NO_DATA = PopupRule("no_data", "Information", "No data", "tbar[0]/btn[0]", "no_data")


def _session(system="QAS", client="300", user="ROBOT01") -> FakeSession:
    return FakeSession(Info(system, client, user))


# ---------------------------------------------------------------- status bar


def test_status_bar_error_raises_and_success_passes():
    s = _session()
    s.status.MessageType, s.status.Text = "S", "Saved"
    assert str(check_status(GuardedSession(s))) == "[S] Saved"
    s.status.MessageType, s.status.Text = "E", "Sold-to party not found"
    assert read_status(GuardedSession(s)).is_error
    with pytest.raises(SapMessageError, match="Sold-to party"):
        check_status(GuardedSession(s))


# ---------------------------------------------------------------- popups


def test_known_popup_is_answered_and_reported():
    s = _session()
    s.popup("Information", "No data was selected")
    seen = handle_popups(GuardedSession(s), [NO_DATA])
    assert [p.outcome for p in seen] == ["no_data"]
    assert ("press", "wnd[1]/tbar[0]/btn[0]") in s.actions
    assert s.Children.Count == 1


def test_unknown_popup_is_left_open_and_nothing_pressed():
    s = _session()
    s.popup("Save document?", "Data will be lost")
    with pytest.raises(UnknownPopup, match="Save document"):
        handle_popups(GuardedSession(s), [NO_DATA])
    assert s.actions == [] and s.Children.Count == 2


def test_popup_loop_is_bounded():
    s = _session()
    s.on_press = lambda element_id: None  # dialog never closes
    s.popup("Information", "No data")
    with pytest.raises(UnknownPopup, match="Quá"):
        handle_popups(GuardedSession(s), [NO_DATA])


def test_popup_config_loads_and_rejects_rules_matching_everything(tmp_path):
    good = tmp_path / "p.yaml"
    good.write_text(
        "popups:\n  - name: no_data\n    title_contains: Information\n"
        "    button: tbar[0]/btn[0]\n    outcome: no_data\n",
        encoding="utf-8",
    )
    assert load_rules(good)[0].outcome == "no_data"
    bad = tmp_path / "bad.yaml"
    bad.write_text("popups:\n  - name: any\n    button: tbar[0]/btn[0]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="title_contains"):
        load_rules(bad)


def test_repo_config_files_load():
    from shoponline.cli import REPO_ROOT

    rules = load_rules(REPO_ROOT / "config" / "sap_popups.yaml")
    assert [r.name for r in rules] == ["select_spreadsheet"]
    assert rules[0].matches("Select Spreadsheet", "") and not rules[0].matches("Information", "")
    screens = Screens.load(REPO_ROOT / "config" / "sap_screens.yaml")
    assert screens.id("login", "user").startswith("wnd[0]/usr/")
    assert screens.date_text(date(2026, 11, 2)) == "02.11.2026"


def test_missing_date_format_names_the_key():
    with pytest.raises(ScreenConfigMissing, match="formats.date"):
        SCREENS.date_text(date(2026, 11, 2))


def test_missing_screen_id_names_the_key():
    with pytest.raises(ScreenConfigMissing, match="zrsd001.po_no"):
        SCREENS.id("zrsd001", "po_no")


# ---------------------------------------------------------------- session


def test_picks_the_session_of_the_target_system():
    prod, qa = _session("PRD", "100"), _session("QAS", "300")
    gui, ident = ensure_session(engine_with(prod, qa), QA, LOGIN, SCREENS, [])
    assert gui is qa and str(ident) == "QAS/300 user ROBOT01"


def test_refuses_when_only_another_system_is_open():
    engine = engine_with(_session("PRD", "100"))
    with pytest.raises(WrongSystem, match="PRD/100"):
        ensure_session(engine, QA, LOGIN, SCREENS, [])
    assert engine.opened == []  # never logs in next to someone else's session


def test_other_user_on_the_right_system_is_refused():
    with pytest.raises(WrongSystem):
        ensure_session(engine_with(_session(user="ANNA")), QA, LOGIN, SCREENS, [])


def test_logs_in_again_when_the_session_dropped():
    dropped = _session()
    dropped.broken = True
    engine = engine_with(dropped)
    engine.login_as = Info("QAS", "300", "ROBOT01")
    gui, _ = ensure_session(engine, QA, LOGIN, SCREENS, [])
    assert engine.opened == ["QA robot"]
    assert gui.text_of("wnd[0]/usr/user") == "robot01"
    assert gui.text_of("wnd[0]/usr/pw") == "secret-pw"


def test_login_into_wrong_system_is_refused():
    engine = FakeEngine(login_as=Info("PRD", "100", "ROBOT01"))
    with pytest.raises(WrongSystem):
        ensure_session(engine, QA, LOGIN, SCREENS, [])


def test_failed_login_is_reported_without_password():
    engine = FakeEngine(login_as=None)
    with pytest.raises(SessionUnavailable) as err:
        ensure_session(engine, QA, LOGIN, SCREENS, [])
    assert "secret-pw" not in str(err.value)


# ---------------------------------------------------------------- evidence


def test_capture_saves_png_and_never_raises(tmp_path):
    path = evidence.capture(GuardedSession(_session()), tmp_path / "ev", 7)
    assert path is not None and path.name.startswith("job-7-")

    class Broken:
        @property
        def ActiveWindow(self):  # noqa: N802
            raise RuntimeError("gone")

    assert evidence.capture(GuardedSession(Broken()), tmp_path / "ev", 8) is None


def test_prune_removes_only_old_screenshots(tmp_path):
    old, new = tmp_path / "job-1-a.png", tmp_path / "job-2-b.png"
    old.write_bytes(b"x")
    new.write_bytes(b"x")
    month_ago = time.time() - 31 * 86400
    os.utime(old, (month_ago, month_ago))
    assert evidence.prune(tmp_path, keep_days=30) == 1
    assert not old.exists() and new.exists()


def test_logoff_sessions_of_closes_only_the_robot_user():
    robot, person, other_system = _session(), _session(user="ANNA"), _session("PRD", "100")
    engine = engine_with(robot, person, other_system)
    assert logoff_sessions_of(engine, QA, "robot01") == 1
    assert robot.Parent.closed  # one connection holds all three sessions in this fake
    assert engine.closed == [robot.Parent]


def test_logoff_never_raises():
    logoff(object())  # no Parent: logged as a warning, robot goes on


def test_scripting_engine_starts_sap_logon_when_it_is_not_running(tmp_path, monkeypatch):
    exe = tmp_path / "saplogon.exe"
    exe.write_bytes(b"")
    monkeypatch.setenv("SHOPONLINE_SAPLOGON_PATH", str(exe))
    launched, calls = [], []

    def running():
        calls.append(1)
        if not launched:
            raise SessionUnavailable("not running")
        return "engine"

    assert scripting_engine(running_engine=running, launch=launched.append) == "engine"
    assert launched == [[str(exe)]]


def test_scripting_engine_without_start_does_not_launch(monkeypatch):
    def running():
        raise SessionUnavailable("not running")

    launched = []
    with pytest.raises(SessionUnavailable):
        scripting_engine(start=False, running_engine=running, launch=launched.append)
    assert launched == []
