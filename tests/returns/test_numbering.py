import threading
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.clock import today_vn
from shoponline.db.models import DocumentCounter, EventLog
from shoponline.returns import numbering
from shoponline.returns.numbering import (
    NumberingAlreadyStarted,
    NumberingNotConfigured,
    next_number,
    set_start,
)
from tests.returns import factory


def test_refuses_to_number_before_a_start_is_entered(db):
    with pytest.raises(NumberingNotConfigured, match="return-number start"):
        next_number(db, date(2026, 11, 25))


def test_numbers_follow_the_entered_start_and_the_issue_month(db):
    set_start(db, 2026, 80, "t")
    assert next_number(db, date(2026, 11, 25)) == (2026, 80, "080/11.2026 ALK-KH.STMĐT")
    assert next_number(db, date(2026, 12, 2)) == (2026, 81, "081/12.2026 ALK-KH.STMĐT")


def test_the_start_can_be_entered_only_once(db):
    set_start(db, 2026, 80, "t")
    with pytest.raises(NumberingAlreadyStarted):
        set_start(db, 2026, 5, "t")
    assert db.scalar(select(DocumentCounter.next_seq)) == 80


def test_the_start_is_refused_when_a_return_already_exists(db):
    factory.sales_return(db, factory.delivered_order(db), year=2026, seq=1)
    with pytest.raises(NumberingAlreadyStarted):
        set_start(db, 2026, 80, "t")


def test_a_start_must_be_positive_and_is_logged(db):
    with pytest.raises(ValueError, match="nguyên dương"):
        set_start(db, 2026, 0, "t")
    set_start(db, 2026, 80, "admin")
    event = db.scalar(select(EventLog).where(EventLog.kind == "return_number_started"))
    assert event.actor == "admin" and '"start": 80' in event.detail


def test_a_new_year_starts_again_from_001(db):
    set_start(db, 2026, 80, "t")
    next_number(db, date(2026, 12, 31))
    assert next_number(db, date(2027, 1, 4)) == (2027, 1, "001/01.2027 ALK-KH.STMĐT")
    assert next_number(db, date(2027, 1, 5))[1] == 2


def test_a_year_with_no_earlier_year_to_continue_is_refused(db):
    set_start(db, 2026, 80, "t")
    with pytest.raises(NumberingNotConfigured, match="2025"):
        next_number(db, date(2025, 12, 31))


def test_the_month_is_the_vietnam_month_not_the_utc_month(db):
    set_start(db, 2026, 80, "t")
    just_after_midnight_in_vietnam = datetime(2026, 11, 30, 17, 30, tzinfo=UTC)
    _, _, doc_no = next_number(db, today_vn(just_after_midnight_in_vietnam))
    assert doc_no == "080/12.2026 ALK-KH.STMĐT"


def test_repair_sets_the_counter_one_past_the_highest_issued_number(db):
    set_start(db, 2026, 80, "t")
    order = factory.delivered_order(db)
    factory.sales_return(db, order, year=2026, seq=95, status="VOID")
    old, new = numbering.repair(db, 2026, "t")
    assert (old, new) == (80, 96)
    assert next_number(db, date(2026, 11, 25))[1] == 96


def test_repair_refuses_a_year_without_returns(db):
    set_start(db, 2026, 80, "t")
    with pytest.raises(ValueError, match="chưa có phiếu"):
        numbering.repair(db, 2026, "t")


def _issue(engine, issued_on, results, barrier):
    with Session(engine) as session:
        barrier.wait()
        results.append(next_number(session, issued_on)[1])
        session.commit()


@pytest.mark.parametrize("first_of_year", [False, True])
def test_two_sessions_never_get_the_same_number(committed, first_of_year):
    with Session(committed) as session:
        set_start(session, 2026, 80, "t")
        session.commit()
    issued_on = date(2027, 1, 4) if first_of_year else date(2026, 11, 25)
    results: list[int] = []
    barrier = threading.Barrier(2)
    threads = [
        threading.Thread(target=_issue, args=(committed, issued_on, results, barrier))
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert sorted(results) == ([1, 2] if first_of_year else [80, 81])
