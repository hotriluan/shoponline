"""The only door between the robot and SAP GUI: a wrapper that keeps the robot inside two reports.

Every action (type text, select, press, send a key, open a T-code) reads Info.Transaction before
and after it runs. A T-code outside ALLOWED_TRANSACTIONS trips the guard: it raises
GuardViolation, and from then on refuses every action, so the robot presses nothing more.
Reads (texts, status bar, grid cells) do not change SAP and are not checked.

The lists live in code, not in YAML, so editing configuration cannot widen them. Widening one
needs a code change with a test.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from shoponline.saprobot.errors import GuardViolation

# Info.Transaction values seen on AEP/300 with user AL17016 (System → Status, 2026-11-12):
# login screen, main menu, and the two reports (filter screen and ALV result screen).
ALLOWED_TRANSACTIONS = frozenset({"S000", "SESSION_MANAGER", "ZRSD001", "ZRSD004"})
# T-codes the robot may open itself through the command field.
OPENABLE_TRANSACTIONS = frozenset({"ZRSD001", "ZRSD004"})

# SAP GUI virtual keys.
VKEY_ENTER = 0
VKEY_F8_EXECUTE = 8
VKEY_SAVE = 11  # Ctrl+S: never sent, even if someone adds it to ALLOWED_VKEYS
ALLOWED_VKEYS = frozenset({VKEY_ENTER, VKEY_F8_EXECUTE})

# Methods that only read an element (ALV grid cells and column titles).
READ_METHODS = frozenset({"GetCellValue", "GetColumnTitles", "GetDisplayedColumnTitle"})
READABLE_TYPES = (str, int, float, bool, type(None))

COMMAND_FIELD = "wnd[0]/tbar[0]/okcd"
_COMMAND_FIELD_RE = re.compile(r"okcd", re.IGNORECASE)
HARDCOPY_PNG = 2  # GuiFrameWindow.HardCopy image type 2 is PNG


class GuardedSession:
    """Wraps one SAP GUI session; the raw session never leaves this module."""

    def __init__(self, raw_session):
        self._raw = raw_session
        self.tripped: str | None = None

    # ---------------------------------------------------------------- checks

    @property
    def transaction(self) -> str:
        return str(self._raw.Info.Transaction or "").strip().upper()

    def check(self) -> str:
        """Return the current T-code; trip the guard when it is not allowed."""
        if self.tripped:
            raise GuardViolation(f"Lớp chặn đã dừng robot: {self.tripped}", self)
        tcode = self.transaction
        if tcode not in ALLOWED_TRANSACTIONS:
            self._trip(f"phiên SAP đang ở T-code {tcode or '(trống)'} ngoài danh sách được phép")
        return tcode

    def _trip(self, reason: str) -> None:
        self.tripped = reason
        raise GuardViolation(f"Lớp chặn T-code: {reason}", self)

    def _act(self, action: Callable[[], object]) -> None:
        self.check()
        action()
        self.check()

    # ---------------------------------------------------------------- actions

    def find(self, element_id: str) -> GuardedElement:
        if _COMMAND_FIELD_RE.search(element_id):
            self._trip(f"thao tác trực tiếp vào ô lệnh '{element_id}' bị cấm")
        return GuardedElement(self, self._raw.findById(element_id), element_id)

    def send_vkey(self, key: int) -> None:
        if key == VKEY_SAVE or key not in ALLOWED_VKEYS:
            self._trip(f"phím {key} không nằm trong danh sách được phép")
        self._act(lambda: self._raw.findById("wnd[0]").sendVKey(key))

    def start_transaction(self, tcode: str) -> None:
        """Open a report from any allowed screen (/n leaves the current one without saving)."""
        tcode = tcode.strip().upper()
        if tcode not in OPENABLE_TRANSACTIONS:
            self._trip(f"không được mở T-code {tcode}")

        def open_tcode() -> None:
            self._raw.findById(COMMAND_FIELD).text = f"/n{tcode}"
            self._raw.findById("wnd[0]").sendVKey(VKEY_ENTER)

        self._act(open_tcode)

    # ---------------------------------------------------------------- reads

    def window_count(self) -> int:
        return int(self._raw.Children.Count)

    def window_text(self, index: int) -> tuple[str, str]:
        """Title and dialog text of window wnd[index]."""
        window = self._raw.Children(index)
        try:
            text = window.PopupDialogText or ""
        except Exception:  # not every modal window exposes it
            text = ""
        return window.Text or "", text

    def hardcopy(self, path: str) -> None:
        """Screenshot of the active window; allowed after a trip, it changes nothing in SAP."""
        self._raw.ActiveWindow.HardCopy(path, HARDCOPY_PNG)


class GuardedElement:
    """One screen element; every change goes through the session's before/after check."""

    def __init__(self, session: GuardedSession, raw_element, element_id: str):
        self._session = session
        self._raw = raw_element
        self.id = element_id

    @property
    def text(self) -> str:
        return str(self._raw.text or "")

    def set_text(self, value: str) -> None:
        self._session._act(lambda: setattr(self._raw, "text", value))

    def select(self) -> None:
        """Tick a radio button or checkbox."""
        self._session._act(lambda: setattr(self._raw, "selected", True))

    def press(self) -> None:
        self._session._act(self._raw.press)

    def get(self, name: str):
        """Read a plain property value; methods and sub-objects are refused."""
        value = getattr(self._raw, name)
        if not isinstance(value, READABLE_TYPES):
            raise GuardViolation(f"'{self.id}.{name}' không phải giá trị đọc được", self._session)
        return value

    def call(self, method: str, *args):
        """Call a read-only method such as GetCellValue(row, column)."""
        if method not in READ_METHODS:
            raise GuardViolation(f"Hàm '{method}' không nằm trong danh sách chỉ đọc", self._session)
        return getattr(self._raw, method)(*args)
