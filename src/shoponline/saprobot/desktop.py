"""Windows dialogs around SAP's Spreadsheet export, which SAP GUI Scripting cannot reach.

After the robot picks Spreadsheet export, SAP GUI shows a Save As dialog, then asks through
"SAP GUI Security" whether it may open the saved file, then opens it in Excel (seen in the
recordings of 2026-11-12). The SAP call that started the export blocks until Save As closes,
so a helper thread answers these windows:

- Save As: type the full target path and press Save (control IDs of the Windows common dialog,
  independent of the UI language);
- Confirm Save As (file exists): Yes, only reached when deleting the old file failed;
- SAP GUI Security: Allow, only when the dialog names the target file, never "Remember";
- Excel window of the target file: closed, the file is read by the robot afterwards.

Only windows with these exact titles are touched. pywinauto is imported lazily so the module
loads on machines without the robot extra (tests pass a fake desktop instead).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from shoponline.saprobot.errors import RobotError

log = logging.getLogger(__name__)

SAVE_AS_TITLE = "Save As"
OVERWRITE_TITLE = "Confirm Save As"
SECURITY_TITLE = "SAP GUI Security"
EXCEL_CLASS = "XLMAIN"

# Windows common dialog control IDs: file name combo (cmb13), OK/Save (IDOK), Cancel, Yes (IDYES).
# The ComboBoxEx32, its ComboBox and its Edit all carry the file name ID, so a lookup by ID alone
# is ambiguous: the Edit is selected by class as well.
FILE_NAME_COMBO_ID = 1148
OK_BUTTON_ID = 1
CANCEL_BUTTON_ID = 2
YES_BUTTON_ID = 6

SAVE_AS_TIMEOUT = 60.0  # SAP may take a while to build the spreadsheet
AFTER_SAVE_TIMEOUT = 60.0  # file written, security question answered, Excel up and closed
POLL_SECONDS = 0.3


def _pywinauto_desktop():
    from pywinauto import Desktop

    return Desktop(backend="win32")


class ExportSave:
    """One export: answers the Windows dialogs in a background thread."""

    def __init__(self, target: Path, desktop_factory: Callable[[], object] | None = None):
        self.target = target.resolve()  # typed into Save As and matched in SAP GUI Security
        self._desktop_factory = desktop_factory or _pywinauto_desktop
        self._stop = threading.Event()
        self._error: BaseException | None = None
        self._thread = threading.Thread(target=self._run, name="sap-export-save", daemon=True)
        self._thread.start()

    def wait(self) -> Path:
        self._thread.join(SAVE_AS_TIMEOUT + AFTER_SAVE_TIMEOUT + 5)
        if self._thread.is_alive():
            self.cancel()
            raise RobotError("Hết giờ chờ hộp thoại lưu file của SAP")
        if self._error is not None:
            raise RobotError(f"Không lưu được file xuất: {self._error}") from self._error
        return self.target

    def cancel(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------ helper thread

    def _run(self) -> None:
        desktop = None
        try:
            desktop = self._desktop_factory()
            self._answer(desktop)
        except BaseException as exc:  # reported to the robot thread by wait()
            self._error = exc
            # The SAP call that opened Save As blocks until it closes, and wait() only runs after
            # that call returns: leave Save As open and the robot hangs without reporting why.
            self._close_save_as(desktop)

    def _close_save_as(self, desktop) -> None:
        try:
            for window in desktop.windows(visible_only=True, title=SAVE_AS_TITLE):
                button = desktop.window(handle=window.handle).child_window(
                    control_id=CANCEL_BUTTON_ID, class_name="Button"
                )
                button.click()
        except Exception:
            log.exception("Không đóng được hộp Save As sau lỗi")

    def _dialogs(self, desktop, title: str, answered: set[int]) -> list:
        """Specifications of the visible top-level windows with this title, not yet answered."""
        found = []
        for window in desktop.windows(visible_only=True, title=title):
            if window.handle not in answered:
                answered.add(window.handle)
                found.append(desktop.window(handle=window.handle))
        return found

    def _answer(self, desktop) -> None:
        answered: set[int] = set()
        deadline = time.monotonic() + SAVE_AS_TIMEOUT
        while not (save_as := self._dialogs(desktop, SAVE_AS_TITLE, answered)):
            self._tick(deadline, "Không thấy hộp Save As của SAP")
        self._save_as(save_as[0])

        deadline = time.monotonic() + AFTER_SAVE_TIMEOUT
        # "<name> - Excel", or "<name>.xlsx - Excel" when Windows shows file extensions
        stem = self.target.stem.lower()
        while True:
            for dialog in self._dialogs(desktop, OVERWRITE_TITLE, answered):
                log.info("Ghi đè file xuất %s", self.target.name)
                dialog.child_window(control_id=YES_BUTTON_ID, class_name="Button").click()
            for dialog in self._dialogs(desktop, SECURITY_TITLE, answered):
                self._allow_own_file(dialog)
            excel = [
                w
                for w in desktop.windows(visible_only=True, class_name=EXCEL_CLASS)
                if w.window_text().lower().startswith(stem)
            ]
            if excel:
                for window in excel:
                    window.close()
                return
            if time.monotonic() > deadline and self.target.is_file():
                log.warning("Không thấy Excel mở %s; file đã lưu, đọc tiếp", self.target.name)
                return
            self._tick(deadline, "SAP không lưu file xuất sau khi bấm Save")

    def _save_as(self, dialog) -> None:
        try:
            edit = dialog.child_window(control_id=FILE_NAME_COMBO_ID, class_name="Edit")
            edit.set_edit_text(str(self.target))
            dialog.child_window(control_id=OK_BUTTON_ID, class_name="Button").click()
        except Exception as exc:
            controls = [
                (c.class_name(), c.control_id(), c.window_text()) for c in dialog.children()
            ]
            raise RobotError(f"Hộp Save As khác dự kiến ({exc}); các phần tử: {controls}") from exc

    def _allow_own_file(self, dialog) -> None:
        text = " ".join(c.window_text() for c in dialog.descendants())
        if str(self.target).lower() not in text.lower():
            dialog.child_window(title_re="&?Deny").click()
            raise RobotError(f"SAP GUI Security hỏi một file khác file xuất: {text.strip()!r}")
        dialog.child_window(title_re="&?Allow").click()

    def _tick(self, deadline: float, message: str) -> None:
        if self._stop.is_set():
            raise RobotError("Đã hủy chờ hộp thoại lưu file")
        if time.monotonic() > deadline:
            raise RobotError(message)
        time.sleep(POLL_SECONDS)


class PendingSave(Protocol):
    def wait(self) -> Path: ...

    def cancel(self) -> None: ...


class SaveDialogs(Protocol):
    """Starts answering the Windows dialogs of one export, before the SAP call opens them."""

    def start_save(self, target: Path) -> PendingSave: ...


class WindowsDesktop:
    def start_save(self, target: Path) -> ExportSave:
        return ExportSave(target)
