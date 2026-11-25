"""Load the accountants' history file into history_sale_line.

`plan` reads and reports without writing. `apply` writes in one transaction: the lines not yet
stored (a line already stored is skipped, so the same or a longer file can be loaded again), one
import_batch of kind history_sales and one event_log row. The file is copied to exports/history/
as evidence and kept by the retention rules.
"""

from __future__ import annotations

import hashlib
import shutil
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.config import Settings
from shoponline.db.models import BackupRun, HistorySaleLine, ImportBatch, ProvinceAlias, Shop
from shoponline.domain import states
from shoponline.domain.provinces import resolve
from shoponline.importers.history_file import HistoryLine, Rejected, division_key, read_history

KIND = "history_sales"
BACKUP_MAX_AGE = timedelta(hours=2)
INSERT_CHUNK = 500


class BackupMissing(RuntimeError):
    """No database backup finished in the last two hours."""


@dataclass
class HistoryPlan:
    file_name: str
    new_lines: list[HistoryLine] = field(default_factory=list)
    existing: int = 0
    rejected: list[Rejected] = field(default_factory=list)
    unresolved_cities: Counter = field(default_factory=Counter)
    # Customer paid of the accepted lines (new and existing) by (year, shop code), for checking
    # against the file's own sums.
    totals: dict[tuple[int, str], int] = field(default_factory=dict)


def aliases(session: Session) -> dict[str, str]:
    return {a.raw_key: a.province for a in session.scalars(select(ProvinceAlias))}


def plan(session: Session, path: Path) -> HistoryPlan:
    divisions = {division_key(s.division): s.code for s in session.scalars(select(Shop))}
    read = read_history(path, divisions)
    stored = set(session.scalars(select(HistorySaleLine.line_key)))
    known = aliases(session)
    result = HistoryPlan(file_name=path.name, rejected=read.rejected)
    totals: Counter = Counter()
    for line in read.lines:
        totals[(line.period.year, line.shop_code)] += line.customer_paid
        if line.line_key in stored:
            result.existing += 1
            continue
        result.new_lines.append(line)
        if line.city_raw and resolve(line.city_raw, known) is None:
            result.unresolved_cities[line.city_raw] += 1
    result.totals = dict(totals)
    return result


def recent_backup(session: Session, now: datetime | None = None) -> bool:
    """A database backup (kind db or full) finished ok within the last two hours."""
    since = (now or datetime.now(UTC)) - BACKUP_MAX_AGE
    found = session.scalar(
        select(BackupRun.id)
        .where(
            BackupRun.kind.in_(("db", "full")),
            BackupRun.local_status.in_(("ok", "partial")),
            BackupRun.finished_at >= since,
        )
        .limit(1)
    )
    return found is not None


def apply(
    session: Session,
    settings: Settings,
    path: Path,
    actor: str,
    *,
    skip_backup_check: bool = False,
) -> HistoryPlan:
    """Store the new lines. Raises BackupMissing without a recent backup unless skipped."""
    if not skip_backup_check and not recent_backup(session):
        raise BackupMissing(
            "Chưa có bản sao lưu database trong 2 giờ qua. "
            "Chạy `shoponline backup run --kind db` rồi nạp lại."
        )
    result = plan(session, path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    target = settings.export_dir / "history" / f"{digest[:12]}-{path.name}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.copyfile(path, target)
    batch = ImportBatch(
        kind=KIND,
        file_name=path.name,
        sha256=digest,
        stored_path=str(target),
        imported_by=actor,
        new_count=len(result.new_lines),
        unchanged_count=result.existing,
    )
    session.add(batch)
    session.flush()
    for start in range(0, len(result.new_lines), INSERT_CHUNK):
        session.add_all(
            HistorySaleLine(
                period=line.period,
                ordered_on=line.ordered_on,
                shop_code=line.shop_code,
                customer_name=line.customer_name,
                customer_phone=line.customer_phone,
                city_raw=line.city_raw,
                city_key=line.city_key,
                item_name=line.item_name,
                size=line.size,
                variation=line.variation,
                quantity=line.quantity,
                customer_paid=line.customer_paid,
                unit_price=line.unit_price,
                seller_discount=line.seller_discount,
                shipping_fee=line.shipping_fee,
                order_key=line.order_key,
                line_key=line.line_key,
                source_row=line.source_row,
                import_batch_id=batch.id,
            )
            for line in result.new_lines[start : start + INSERT_CHUNK]
        )
        session.flush()
    detail = {
        "file": path.name,
        "new": len(result.new_lines),
        "existing": result.existing,
        "rejected": len(result.rejected),
    }
    if skip_backup_check:
        detail["backup_check_skipped"] = True
    states.log_event(session, actor, "history_imported", detail=detail)
    return result
