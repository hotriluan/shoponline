"""The ledger of deliveries (DO) already sent to accounting, and the cutoff date.

Callers own the transaction: every function flushes, none commits.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import Connection, delete, func, select, text
from sqlalchemy.orm import Session

from shoponline.clock import today_vn
from shoponline.db.models import (
    AccountingBaseline,
    AccountingRun,
    AccountingSentDelivery,
    SalesOrder,
)
from shoponline.domain import states

OPEN = "OPEN"
FINALIZED = "FINALIZED"
CANCELLED = "CANCELLED"
REVOKED = "REVOKED"


class LedgerError(ValueError):
    pass


def seed_baseline(connection: Connection, cutoff: date | None = None) -> int:
    """Opening ledger: the cutoff date, and the DO of every order already at "Đã có DO".

    Returns the number of deliveries added. Safe to run on a database that already has rows.
    """
    connection.execute(
        text(
            "INSERT INTO accounting_baseline (id, cutoff_date) VALUES (1, :day) "
            "ON CONFLICT (id) DO UPDATE SET cutoff_date = EXCLUDED.cutoff_date"
        ),
        {"day": cutoff or today_vn()},
    )
    result = connection.execute(
        text(
            "INSERT INTO accounting_sent_delivery (delivery, run_id, sent_at) "
            "SELECT DISTINCT do_number, CAST(NULL AS integer), now() FROM sales_order "
            "WHERE status = 'DELIVERED' AND do_number IS NOT NULL "
            "ON CONFLICT (delivery) DO NOTHING"
        )
    )
    return result.rowcount


def get_cutoff(session: Session) -> date | None:
    return session.scalar(select(AccountingBaseline.cutoff_date).where(AccountingBaseline.id == 1))


def set_cutoff(session: Session, day: date, actor: str) -> None:
    row = session.get(AccountingBaseline, 1)
    old = row.cutoff_date if row else None
    if row is None:
        session.add(AccountingBaseline(id=1, cutoff_date=day))
    else:
        row.cutoff_date = day
    session.flush()
    states.log_event(
        session,
        actor,
        "accounting_cutoff_changed",
        detail={"from": old.isoformat() if old else None, "to": day.isoformat()},
    )


@dataclass(frozen=True)
class LedgerEntry:
    delivery: str
    platform: str | None
    platform_order_id: str | None


def list_baseline(session: Session) -> list[LedgerEntry]:
    """Opening-ledger deliveries with the order they belong to, when the web knows one."""
    rows = session.execute(
        select(
            AccountingSentDelivery.delivery,
            SalesOrder.platform,
            SalesOrder.platform_order_id,
        )
        .outerjoin(SalesOrder, SalesOrder.do_number == AccountingSentDelivery.delivery)
        .where(AccountingSentDelivery.run_id.is_(None))
        .order_by(AccountingSentDelivery.delivery)
    ).all()
    return [LedgerEntry(d, p, o) for d, p, o in rows]


def sent_deliveries(session: Session) -> set[str]:
    return set(session.scalars(select(AccountingSentDelivery.delivery)))


def add_baseline(session: Session, deliveries: list[str], actor: str) -> list[str]:
    """Add deliveries as already sent. Returns the ones that were new."""
    wanted = _clean(deliveries)
    have = set(
        session.scalars(
            select(AccountingSentDelivery.delivery).where(
                AccountingSentDelivery.delivery.in_(wanted)
            )
        )
    )
    added = [d for d in wanted if d not in have]
    session.add_all(AccountingSentDelivery(delivery=d, run_id=None) for d in added)
    session.flush()
    states.log_event(session, actor, "accounting_ledger_added", detail={"deliveries": added})
    return added


def remove_baseline(session: Session, deliveries: list[str], actor: str) -> list[str]:
    """Remove opening-ledger deliveries. A delivery that belongs to a run is refused."""
    wanted = _clean(deliveries)
    rows = session.scalars(
        select(AccountingSentDelivery).where(AccountingSentDelivery.delivery.in_(wanted))
    ).all()
    in_runs = sorted(r.delivery for r in rows if r.run_id is not None)
    if in_runs:
        raise LedgerError(
            "DO thuộc một đợt đã chốt, không gỡ riêng được (dùng accounting-run revoke): "
            + ", ".join(in_runs)
        )
    removed = sorted(r.delivery for r in rows)
    for row in rows:
        session.delete(row)
    session.flush()
    states.log_event(session, actor, "accounting_ledger_removed", detail={"deliveries": removed})
    return removed


def run_delivery_count(session: Session, run_id: int) -> int:
    return session.scalar(
        select(func.count())
        .select_from(AccountingSentDelivery)
        .where(AccountingSentDelivery.run_id == run_id)
    )


def revoke_run(session: Session, run_id: int, actor: str, *, apply: bool) -> int:
    """Take a finalized run's deliveries out of the ledger and mark the run REVOKED.

    Returns the number of deliveries involved. Without `apply` nothing changes.
    The saved file is kept. Only a FINALIZED run can be revoked.
    """
    run = session.scalar(select(AccountingRun).where(AccountingRun.id == run_id).with_for_update())
    if run is None:
        raise LedgerError(f"Không có đợt #{run_id}")
    if run.status != FINALIZED:
        raise LedgerError(f"Đợt #{run_id} đang ở {run.status}, chỉ gỡ được đợt FINALIZED")
    count = run_delivery_count(session, run_id)
    if not apply:
        return count
    session.execute(delete(AccountingSentDelivery).where(AccountingSentDelivery.run_id == run_id))
    run.status = REVOKED
    session.flush()
    states.log_event(
        session, actor, "accounting_run_revoked", detail={"run_id": run_id, "deliveries": count}
    )
    return count


def _clean(deliveries: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for item in deliveries:
        value = item.strip()
        if value:
            seen[value] = None
    if not seen:
        raise LedgerError("Chưa nhập số Delivery nào")
    return list(seen)
