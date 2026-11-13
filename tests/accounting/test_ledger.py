from datetime import date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from shoponline.accounting import ledger
from shoponline.accounting.ledger import LedgerError
from shoponline.db.models import (
    AccountingBaseline,
    AccountingRun,
    AccountingRunRead,
    AccountingSentDelivery,
    EventLog,
    OrderBatch,
    SalesOrder,
)
from shoponline.domain import states


def _batch(db):
    batch = OrderBatch(
        platform="SHOPEE", processing_date=date(2026, 11, 11), gi_date=date(2026, 11, 12)
    )
    db.add(batch)
    db.flush()
    return batch


def _order(db, batch, order_id, status, do_number=None):
    order = SalesOrder(
        platform="SHOPEE",
        platform_order_id=order_id,
        order_batch_id=batch.id,
        ordered_at=datetime(2026, 11, 11, 8),
        status=status,
        do_number=do_number,
    )
    db.add(order)
    db.flush()
    return order


def _run(db, status=ledger.OPEN):
    run = AccountingRun(status=status, created_by="test")
    db.add(run)
    db.flush()
    return run


# ---------------------------------------------------------------- table constraints


def test_only_one_open_run(db):
    _run(db)
    db.add(AccountingRun(status=ledger.OPEN, created_by="test"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_closed_runs_can_be_many(db):
    _run(db, ledger.FINALIZED)
    _run(db, ledger.CANCELLED)
    _run(db, ledger.OPEN)


def test_run_status_must_be_known(db):
    db.add(AccountingRun(status="WHATEVER", created_by="test"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_one_read_per_run_platform_and_day(db):
    run = _run(db)
    db.add(AccountingRunRead(run_id=run.id, platform="SHOPEE", gi_date=date(2026, 11, 12)))
    db.flush()
    db.add(AccountingRunRead(run_id=run.id, platform="SHOPEE", gi_date=date(2026, 11, 12)))
    with pytest.raises(IntegrityError):
        db.flush()


def test_baseline_is_a_single_row(db):
    db.execute(AccountingBaseline.__table__.delete())
    db.add(AccountingBaseline(id=1, cutoff_date=date(2026, 1, 1)))
    db.flush()
    db.add(AccountingBaseline(id=2, cutoff_date=date(2026, 1, 1)))
    with pytest.raises(IntegrityError):
        db.flush()


# ---------------------------------------------------------------- opening ledger


def test_seed_baseline_takes_delivered_orders_with_a_do(db):
    batch = _batch(db)
    _order(db, batch, "A", states.DELIVERED, "1900000001")
    _order(db, batch, "B", states.DELIVERED, None)
    _order(db, batch, "C", states.SO_LINKED, None)
    _order(db, batch, "D", states.CANCELLED, "1900000009")
    db.execute(AccountingSentDelivery.__table__.delete())

    added = ledger.seed_baseline(db.connection(), date(2026, 11, 13))

    assert added == 1
    assert ledger.sent_deliveries(db) == {"1900000001"}
    assert ledger.get_cutoff(db) == date(2026, 11, 13)


def test_seed_baseline_twice_adds_nothing(db):
    batch = _batch(db)
    _order(db, batch, "A", states.DELIVERED, "1900000001")
    db.execute(AccountingSentDelivery.__table__.delete())
    ledger.seed_baseline(db.connection(), date(2026, 11, 13))

    assert ledger.seed_baseline(db.connection(), date(2026, 11, 14)) == 0
    assert ledger.get_cutoff(db) == date(2026, 11, 14)


def test_add_and_remove_baseline_log_the_actor(db):
    added = ledger.add_baseline(db, ["1900000001", " 1900000002 ", "1900000001"], "luan")
    assert added == ["1900000001", "1900000002"]
    assert ledger.add_baseline(db, ["1900000001"], "luan") == []

    removed = ledger.remove_baseline(db, ["1900000002"], "luan")

    assert removed == ["1900000002"]
    assert "1900000002" not in ledger.sent_deliveries(db)
    kinds = set(db.scalars(select(EventLog.kind).where(EventLog.actor == "luan")))
    assert {"accounting_ledger_added", "accounting_ledger_removed"} <= kinds


def test_remove_refuses_a_delivery_of_a_run(db):
    run = _run(db, ledger.FINALIZED)
    db.add(AccountingSentDelivery(delivery="1900000005", run_id=run.id))
    db.flush()

    with pytest.raises(LedgerError, match="1900000005"):
        ledger.remove_baseline(db, ["1900000005"], "luan")
    assert "1900000005" in ledger.sent_deliveries(db)


def test_empty_delivery_list_is_refused(db):
    with pytest.raises(LedgerError):
        ledger.add_baseline(db, [" "], "luan")


def test_list_baseline_names_the_order(db):
    batch = _batch(db)
    _order(db, batch, "R-1", states.DELIVERED, "1900000001")
    ledger.add_baseline(db, ["1900000001", "1900000777"], "luan")
    entries = {e.delivery: e for e in ledger.list_baseline(db)}
    assert entries["1900000001"].platform_order_id == "R-1"
    assert entries["1900000777"].platform is None


def test_cutoff_change_is_logged(db):
    ledger.set_cutoff(db, date(2026, 11, 1), "luan")
    assert ledger.get_cutoff(db) == date(2026, 11, 1)
    event = db.scalars(
        select(EventLog)
        .where(EventLog.kind == "accounting_cutoff_changed")
        .order_by(EventLog.id.desc())
    ).first()
    assert event.actor == "luan" and "2026-11-01" in event.detail


# ---------------------------------------------------------------- revoke


def _finalized_run(db):
    run = _run(db, ledger.FINALIZED)
    db.add_all(
        AccountingSentDelivery(delivery=d, run_id=run.id) for d in ("1900000011", "1900000012")
    )
    db.add(AccountingSentDelivery(delivery="1900000099", run_id=None))
    db.flush()
    return run


def test_revoke_without_apply_changes_nothing(db):
    run = _finalized_run(db)
    assert ledger.revoke_run(db, run.id, "luan", apply=False) == 2
    assert run.status == ledger.FINALIZED
    assert {"1900000011", "1900000012"} <= ledger.sent_deliveries(db)


def test_revoke_removes_only_that_runs_deliveries(db):
    run = _finalized_run(db)
    other = _run(db, ledger.FINALIZED)
    db.add(AccountingSentDelivery(delivery="1900000021", run_id=other.id))
    db.flush()

    assert ledger.revoke_run(db, run.id, "luan", apply=True) == 2

    sent = ledger.sent_deliveries(db)
    assert not sent & {"1900000011", "1900000012"}
    assert {"1900000099", "1900000021"} <= sent
    db.refresh(run)
    assert run.status == ledger.REVOKED
    assert db.scalars(select(EventLog).where(EventLog.kind == "accounting_run_revoked")).one()


@pytest.mark.parametrize("status", [ledger.OPEN, ledger.CANCELLED, ledger.REVOKED])
def test_revoke_refuses_a_run_that_is_not_finalized(db, status):
    run = _run(db, status)
    with pytest.raises(LedgerError):
        ledger.revoke_run(db, run.id, "luan", apply=True)


def test_revoke_unknown_run(db):
    with pytest.raises(LedgerError):
        ledger.revoke_run(db, 999999, "luan", apply=True)
