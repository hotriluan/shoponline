"""Queue the robot's report reads: zrsd001 after batch confirmation, zrsd004 on goods issue day."""

from __future__ import annotations

from datetime import date

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


def request_zrsd004(session: Session, target: SapTarget, gi_date: date, actor: str) -> SapJob:
    """zrsd004 covers every platform, so one read per goods issue date."""
    return queue.enqueue(
        session,
        queue.READ_ZRSD004,
        target,
        f"{queue.READ_ZRSD004}:{gi_date.isoformat()}",
        {"gi_date": gi_date.isoformat()},
        actor,
    )
