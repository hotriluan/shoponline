"""Document numbers `NNN/MM.YYYY ALK-KH.STMĐT`: the sequence restarts every year.

Only the system issues numbers. The first number is entered once, by `shoponline return-number
start`, when the feature goes live; a number that was issued is never given again.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from shoponline.db.models import DocumentCounter, SalesReturn
from shoponline.domain.states import log_event

DOC_TYPE = "invoice_adjustment"
DOC_SUFFIX = "ALK-KH.STMĐT"
_LOCK_KEY = 0x52455455  # serializes `start` and `repair` against each other


class NumberingNotConfigured(RuntimeError):
    """No starting number was entered yet, so no document may be numbered."""


class NumberingAlreadyStarted(ValueError):
    """The starting number can be entered only once."""


def format_doc_no(seq: int, month: int, year: int) -> str:
    return f"{seq:03d}/{month:02d}.{year} {DOC_SUFFIX}"


def is_configured(session: Session) -> bool:
    count = session.scalar(
        select(func.count())
        .select_from(DocumentCounter)
        .where(DocumentCounter.doc_type == DOC_TYPE)
    )
    return bool(count)


def set_start(session: Session, year: int, start: int, actor: str) -> None:
    """Enter the first number of `year`. Allowed once, while nothing was numbered."""
    if start < 1:
        raise ValueError("Số bắt đầu phải là số nguyên dương")
    session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})
    if is_configured(session) or session.scalar(select(func.count()).select_from(SalesReturn)):
        raise NumberingAlreadyStarted(
            "Đã nhập số bắt đầu hoặc đã có phiếu trả hàng; không nhập lại. "
            "Dùng `shoponline return-number repair` nếu bộ đếm bị lùi sau khi khôi phục."
        )
    session.add(DocumentCounter(doc_type=DOC_TYPE, year=year, next_seq=start))
    log_event(session, actor, "return_number_started", detail={"year": year, "start": start})
    session.flush()


def next_number(session: Session, issued_on: date) -> tuple[int, int, str]:
    """Take the next number of `issued_on`'s year; the counter row stays locked until the
    transaction ends. `issued_on` is the day in Vietnam (`today_vn()`), never the UTC date."""
    year = issued_on.year
    if not is_configured(session):
        raise NumberingNotConfigured(
            "Chưa nhập số bắt đầu của biên bản. Chạy `shoponline return-number start <số>`."
        )
    row = _locked_row(session, year)
    if row is None:
        has_earlier_year = session.scalar(
            select(func.count())
            .select_from(DocumentCounter)
            .where(DocumentCounter.doc_type == DOC_TYPE, DocumentCounter.year < year)
        )
        if not has_earlier_year:
            raise NumberingNotConfigured(
                f"Năm {year} chưa có số biên bản và không có năm trước để nối tiếp."
            )
        # Two first-of-year issues may both get here: the loser of the insert does nothing and
        # then waits on the winner's row lock, so each takes a different number.
        session.execute(
            insert(DocumentCounter)
            .values(doc_type=DOC_TYPE, year=year, next_seq=1)
            .on_conflict_do_nothing(index_elements=["doc_type", "year"])
        )
        row = _locked_row(session, year)
    seq = row.next_seq
    row.next_seq = seq + 1
    session.flush()
    return year, seq, format_doc_no(seq, issued_on.month, year)


def _locked_row(session: Session, year: int) -> DocumentCounter | None:
    return session.scalar(
        select(DocumentCounter)
        .where(DocumentCounter.doc_type == DOC_TYPE, DocumentCounter.year == year)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def counters(session: Session) -> list[tuple[int, int]]:
    """(year, next number) for every year that has one."""
    rows = session.execute(
        select(DocumentCounter.year, DocumentCounter.next_seq)
        .where(DocumentCounter.doc_type == DOC_TYPE)
        .order_by(DocumentCounter.year)
    ).all()
    return [(year, seq) for year, seq in rows]


def repair(session: Session, year: int, actor: str) -> tuple[int, int]:
    """Set the year's next number to one past the highest number issued; returns (old, new).

    After restoring an older backup the counter can sit below numbers already printed.
    """
    highest = session.scalar(
        select(func.max(SalesReturn.doc_seq)).where(SalesReturn.doc_year == year)
    )
    if highest is None:
        raise ValueError(f"Năm {year} chưa có phiếu nào, không có gì để sửa bộ đếm")
    session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})
    row = _locked_row(session, year)
    if row is None:
        raise ValueError(f"Năm {year} chưa có bộ đếm")
    old, row.next_seq = row.next_seq, highest + 1
    log_event(
        session,
        actor,
        "return_number_repaired",
        detail={"year": year, "from": old, "to": highest + 1},
    )
    session.flush()
    return old, row.next_seq
