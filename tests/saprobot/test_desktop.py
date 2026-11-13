"""The Windows dialogs of SAP's Spreadsheet export, answered against a fake pywinauto desktop.

The fake follows the windows seen in the export recordings: Save As, then SAP GUI Security
asking to open the saved file, then Excel showing it.
"""

from pathlib import Path

import pytest

from shoponline.saprobot import desktop as desktop_mod
from shoponline.saprobot.desktop import (
    CANCEL_BUTTON_ID,
    EXCEL_CLASS,
    FILE_NAME_COMBO_ID,
    OK_BUTTON_ID,
    SAVE_AS_TITLE,
    SECURITY_TITLE,
    ExportSave,
)
from shoponline.saprobot.errors import RobotError


class Control:
    def __init__(self, window, text="", on_click=None):
        self.window, self.text, self.on_click = window, text, on_click
        self.edit_text = ""

    def window_text(self) -> str:
        return self.text

    def set_edit_text(self, text: str) -> None:
        self.edit_text = text

    def click(self) -> None:
        self.window.screen.clicks.append((self.window.title, self.text))
        if self.on_click:
            self.on_click()


class Window:
    def __init__(self, screen, title: str, class_name: str = "#32770", texts: list[str] = ()):
        self.screen, self.title, self.class_name = screen, title, class_name
        self.handle = len(screen.opened) + 1
        self.controls: dict = {}
        self.texts = list(texts)
        screen.opened.append(self)

    # wrapper side
    def window_text(self) -> str:
        return self.title

    def close(self) -> None:
        self.screen.clicks.append((self.title, "close"))
        self.screen.top.remove(self)

    # specification side
    def child_window(self, **criteria):
        key = criteria.get("control_id") or criteria.get("title_re") or criteria.get("class_name")
        if key == FILE_NAME_COMBO_ID and criteria.get("class_name") != "Edit":
            # the real dialog has a ComboBoxEx32, a ComboBox and an Edit with this ID
            raise RuntimeError("There are 3 elements that match the criteria")
        return self.controls[key]

    def descendants(self) -> list:
        return [Control(self, t) for t in self.texts]

    def children(self) -> list:
        return []


class FakeScreen:
    """Top-level windows plus the reactions of SAP GUI and Excel to the robot's clicks."""

    def __init__(self, security_path: str | None = None, open_excel: bool = True):
        self.top: list[Window] = []
        self.opened: list[Window] = []
        self.clicks: list = []
        self.security_path = security_path
        self.open_excel = open_excel

    def windows(self, visible_only=True, title=None, class_name=None) -> list:
        return [
            w
            for w in self.top
            if (title is None or w.title == title)
            and (class_name is None or w.class_name == class_name)
        ]

    def window(self, handle: int) -> Window:
        return next(w for w in self.opened if w.handle == handle)

    def show_save_as(self) -> None:
        dialog = Window(self, SAVE_AS_TITLE)
        edit = Control(dialog)
        dialog.controls[FILE_NAME_COMBO_ID] = edit
        dialog.controls[CANCEL_BUTTON_ID] = Control(
            dialog, "Cancel", on_click=lambda: self.top.remove(dialog)
        )
        dialog.controls[OK_BUTTON_ID] = Control(
            dialog, "&Save", on_click=lambda: self._saved(dialog, edit.edit_text)
        )
        self.top.append(dialog)

    def _saved(self, dialog: Window, path: str) -> None:
        self.top.remove(dialog)
        Path(path).write_bytes(b"PK xlsx")
        shown = self.security_path or path
        security = Window(
            self,
            SECURITY_TITLE,
            texts=["The system is trying to execute the program/display the file", shown],
        )
        security.controls["&?Allow"] = Control(security, "Allow", on_click=self._allowed(path))
        security.controls["&?Deny"] = Control(security, "Deny", lambda: self.top.remove(security))
        self.top.append(security)

    def _allowed(self, path: str):
        def allow() -> None:
            self.top[:] = [w for w in self.top if w.title != SECURITY_TITLE]
            if self.open_excel:
                self.top.append(Window(self, f"{Path(path).name} - Excel", EXCEL_CLASS))

        return allow


@pytest.fixture(autouse=True)
def short_waits(monkeypatch):
    monkeypatch.setattr(desktop_mod, "SAVE_AS_TIMEOUT", 1.0)
    monkeypatch.setattr(desktop_mod, "AFTER_SAVE_TIMEOUT", 1.0)
    monkeypatch.setattr(desktop_mod, "POLL_SECONDS", 0.01)


def _export(screen: FakeScreen, target: Path) -> ExportSave:
    screen.show_save_as()
    return ExportSave(target, desktop_factory=lambda: screen)


def test_saves_to_the_target_allows_only_it_and_closes_excel(tmp_path):
    screen = FakeScreen()
    target = tmp_path / "zrsd001-job-7.xlsx"
    assert _export(screen, target).wait() == target.resolve()
    assert target.read_bytes() == b"PK xlsx"
    assert screen.clicks == [
        (SAVE_AS_TITLE, "&Save"),
        (SECURITY_TITLE, "Allow"),
        ("zrsd001-job-7.xlsx - Excel", "close"),
    ]
    assert screen.top == []


def test_security_question_about_another_file_is_denied(tmp_path):
    screen = FakeScreen(security_path=r"C:\Windows\System32\cmd.exe")
    with pytest.raises(RobotError, match="file khác"):
        _export(screen, tmp_path / "zrsd004-job-1.xlsx").wait()
    assert (SECURITY_TITLE, "Deny") in screen.clicks
    assert (SECURITY_TITLE, "Allow") not in screen.clicks


def test_no_save_as_dialog_times_out(tmp_path):
    screen = FakeScreen()
    with pytest.raises(RobotError, match="Save As"):
        ExportSave(tmp_path / "x.xlsx", desktop_factory=lambda: screen).wait()
    assert screen.clicks == []


def test_saved_file_without_excel_is_still_read(tmp_path):
    screen = FakeScreen(open_excel=False)
    target = tmp_path / "zrsd004-job-2.xlsx"
    assert _export(screen, target).wait() == target.resolve()


def test_cancel_stops_waiting(tmp_path):
    screen = FakeScreen()
    save = ExportSave(tmp_path / "x.xlsx", desktop_factory=lambda: screen)
    save.cancel()
    with pytest.raises(RobotError, match="hủy"):
        save.wait()


def test_save_as_is_cancelled_when_the_dialog_cannot_be_answered(tmp_path):
    screen = FakeScreen()
    screen.show_save_as()
    dialog = screen.top[0]
    dialog.controls.pop(OK_BUTTON_ID)  # a Save As that differs from the recording
    with pytest.raises(RobotError, match="Save As khác dự kiến"):
        ExportSave(tmp_path / "x.xlsx", desktop_factory=lambda: screen).wait()
    assert (SAVE_AS_TITLE, "Cancel") in screen.clicks  # SAP's blocked call is released
    assert screen.top == []
