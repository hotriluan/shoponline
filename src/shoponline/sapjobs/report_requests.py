"""Queue the robot's report reads: zrsd001 after batch confirmation, zrsd004 on goods issue
day, zrsd003 once the invoices of delivered orders are out."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from shoponline.db.models import OrderBatch, PlatformSetting, SapJob
from shoponline.sapjobs import queue
from shoponline.sapjobs.queue import SapTarget


def request_zrsd001(session: Session, target: SapTarget, batch: OrderBatch, actor: str) -> SapJob:
    """zrsd001 with "Complete", filtered to the platform's SAP customer and the batch day."""
    setting = session.get(PlatformSetting, batch.platform)
    day = batch.processing_date.isoformat()
    return queue.enqueue(
        session,
        queue.READ_ZRSD001,
        target,
        f"{queue.READ_ZRSD001}:batch:{batch.id}",
        {
            "batch_id": batch.id,
            "platform": batch.platform,
            "sold_to": setting.sap_customer,
            "date_from": day,
            "date_to": day,
            "selection": "complete",
        },
        actor,
    )


def zrsd004_key(platform: str, gi_date: date) -> str:
    return f"{queue.READ_ZRSD004}:{platform}:{gi_date.isoformat()}"


def request_zrsd004(
    session: Session, target: SapTarget, platform: str, gi_date: date, actor: str
) -> SapJob:
    """zrsd004 filtered to the platform's SAP customer: one read per platform and GI date.

    Without the customer filter the report lists every delivery of the sales organization,
    and the accounting file built from it would carry other customers' rows.
    """
    setting = session.get(PlatformSetting, platform)
    if setting is None:
        raise ValueError(f"Không có sàn {platform}")
    day = gi_date.isoformat()
    return queue.enqueue(
        session,
        queue.READ_ZRSD004,
        target,
        zrsd004_key(platform, gi_date),
        {"platform": platform, "sold_to": setting.sap_customer, "gi_date": day},
        actor,
    )


def zrsd003_key(date_from: date, date_to: date) -> str:
    return f"{queue.READ_ZRSD003}:{date_from.isoformat()}:{date_to.isoformat()}"


MAX_READ_DAYS = 62  # a longer range is read in pieces, so one job never runs for too long
CHUNK_DAYS = 31


def split_range(date_from: date, date_to: date) -> list[tuple[date, date]]:
    """[date_from, date_to] as one range, or consecutive pieces of at most CHUNK_DAYS days when
    it is longer than MAX_READ_DAYS. No day is left out or read twice."""
    if (date_to - date_from).days + 1 <= MAX_READ_DAYS:
        return [(date_from, date_to)]
    pieces = []
    start = date_from
    while start <= date_to:
        end = min(start + timedelta(days=CHUNK_DAYS - 1), date_to)
        pieces.append((start, end))
        start = end + timedelta(days=1)
    return pieces


def request_zrsd003(
    session: Session, target: SapTarget, date_from: date, date_to: date, actor: str
) -> SapJob:
    """zrsd003 for every invoice of the sales office billed in [date_from, date_to].

    The report cannot filter by customer, so one read serves every platform; the import keeps
    only the platforms' rows.
    """
    if date_from > date_to:
        raise ValueError("Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.")
    return queue.enqueue(
        session,
        queue.READ_ZRSD003,
        target,
        zrsd003_key(date_from, date_to),
        {"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
        actor,
    )
