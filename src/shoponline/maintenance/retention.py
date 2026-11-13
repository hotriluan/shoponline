"""Delete customer data and stored workbooks older than the retention period.

Orders themselves stay (platform order id, SKU lines, SO and DO numbers): they hold no
personal data and keep re-imports idempotent. What goes:

- customer_info rows (name, address) untouched for retention_days, unless the order is
  still in progress, i.e. its accounting file has not been built yet (status not DELIVERED
  or CANCELLED). Rows typed in by hand for an order id with no sales_order go by age alone.
- files under uploads/, exports/ and robot-work/ older than retention_days.

Robot screenshots have their own, shorter period (saprobot.evidence.prune).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import and_, delete, select
from sqlalchemy.orm import Session

from shoponline.config import Settings
from shoponline.db.models import CustomerInfo, SalesOrder
from shoponline.domain import states

# The accounting file is built from zrsd004, which moves orders to DELIVERED.
FINISHED_STATUSES = (states.DELIVERED, states.CANCELLED)


@dataclass
class RetentionPlan:
    cutoff: datetime
    customer_ids: list[int] = field(default_factory=list)
    customer_orders: list[tuple[str, str]] = field(default_factory=list)  # (platform, order id)
    held_orders: list[tuple[str, str]] = field(default_factory=list)  # expired but unfinished
    files: list[Path] = field(default_factory=list)


def stored_dirs(settings: Settings) -> tuple[Path, ...]:
    return (settings.upload_dir, settings.export_dir, settings.robot_work_dir)


def find_expired(
    session: Session, settings: Settings, now: datetime | None = None
) -> RetentionPlan:
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=settings.retention_days)
    plan = RetentionPlan(cutoff=cutoff)

    rows = session.execute(
        select(
            CustomerInfo.id,
            CustomerInfo.platform,
            CustomerInfo.platform_order_id,
            SalesOrder.status,
        )
        .outerjoin(
            SalesOrder,
            and_(
                SalesOrder.platform == CustomerInfo.platform,
                SalesOrder.platform_order_id == CustomerInfo.platform_order_id,
            ),
        )
        .where(CustomerInfo.updated_at < cutoff)
        .order_by(CustomerInfo.platform, CustomerInfo.platform_order_id)
    ).all()
    for info_id, platform, order_id, status in rows:
        if status is None or status in FINISHED_STATUSES:
            plan.customer_ids.append(info_id)
            plan.customer_orders.append((platform, order_id))
        else:
            plan.held_orders.append((platform, order_id))

    limit = cutoff.timestamp()
    for root in stored_dirs(settings):
        if root.is_dir():
            plan.files.extend(
                sorted(p for p in root.rglob("*") if p.is_file() and p.stat().st_mtime < limit)
            )
    return plan


def apply(session: Session, plan: RetentionPlan, actor: str) -> None:
    """Delete the expired customer rows and log the purge. The caller commits, then delete_files."""
    if plan.customer_ids:
        session.execute(delete(CustomerInfo).where(CustomerInfo.id.in_(plan.customer_ids)))
    states.log_event(
        session,
        actor,
        "retention_purge",
        detail={
            "cutoff": plan.cutoff.isoformat(),
            "customers": len(plan.customer_ids),
            "held": len(plan.held_orders),
            "files": len(plan.files),
        },
    )


def delete_files(settings: Settings, plan: RetentionPlan) -> None:
    roots = set(stored_dirs(settings))
    emptied: set[Path] = set()
    for path in plan.files:
        path.unlink(missing_ok=True)
        if path.parent not in roots:
            emptied.add(path.parent)
    # Robot jobs leave one folder each. Only folders that held an expired file are removed, so a
    # job folder the robot has just created (still empty) is never pulled from under it.
    for folder in sorted(emptied, reverse=True):
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
