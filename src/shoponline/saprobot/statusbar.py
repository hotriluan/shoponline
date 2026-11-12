"""Read the SAP status bar after each step."""

from __future__ import annotations

from dataclasses import dataclass

from shoponline.saprobot.errors import SapMessageError
from shoponline.saprobot.guard import GuardedSession

# MessageType of the status bar: S success, W warning, E error, A abort, I info, "" none.
ERROR_TYPES = frozenset({"E", "A"})


@dataclass(frozen=True)
class StatusMessage:
    type: str
    text: str

    @property
    def is_error(self) -> bool:
        return self.type in ERROR_TYPES

    def __str__(self) -> str:
        return f"[{self.type or '-'}] {self.text}" if self.text else "(thanh trạng thái trống)"


def read_status(session: GuardedSession) -> StatusMessage:
    bar = session.find("wnd[0]/sbar")
    return StatusMessage(
        type=(bar.get("MessageType") or "").strip(), text=(bar.get("Text") or "").strip()
    )


def check_status(session: GuardedSession) -> StatusMessage:
    """Return the status message; raise when SAP reports an error or abort."""
    message = read_status(session)
    if message.is_error:
        raise SapMessageError(f"SAP báo lỗi: {message}")
    return message
