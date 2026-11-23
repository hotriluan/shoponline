"""The home page: what needs doing today. Read-only; every figure is one cheap query over data
that other pages already keep."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shoponline.accounting import runs
from shoponline.clock import today_vn
from shoponline.db.models import (
    AppUser,
    OrderBatch,
    SalesHistoryExported,
    SalesOrder,
)
from shoponline.domain import states
from shoponline.web.app import current_user, get_db, render

router = APIRouter()


@dataclass
class TodayFigures:
    needs_attention: int
    awaiting_sales_admin: int
    awaiting_reconcile: int
    run_reading: int
    run_errors: int
    due_pairs: int
    shop_online_pending: int


def collect(db: Session) -> tuple[TodayFigures, object | None]:
    needs_attention = (
        db.scalar(
            select(func.count())
            .select_from(SalesOrder)
            .where(SalesOrder.status.in_((states.MAPPING_ERROR, states.NEED_REVIEW)))
        )
        or 0
    )
    ready_batches = (
        select(SalesOrder.order_batch_id)
        .where(SalesOrder.status == states.READY)
        .distinct()
        .subquery()
    )
    awaiting_sales_admin = (
        db.scalar(
            select(func.count())
            .select_from(OrderBatch)
            .where(OrderBatch.id.in_(select(ready_batches.c.order_batch_id)))
            .where(OrderBatch.confirmed_at.is_(None))
        )
        or 0
    )
    unlinked_batches = (
        select(SalesOrder.order_batch_id)
        .where(SalesOrder.status == states.READY, SalesOrder.so_number.is_(None))
        .distinct()
        .subquery()
    )
    awaiting_reconcile = (
        db.scalar(
            select(func.count())
            .select_from(OrderBatch)
            .where(OrderBatch.id.in_(select(unlinked_batches.c.order_batch_id)))
            .where(OrderBatch.confirmed_at.is_not(None))
        )
        or 0
    )
    run = runs.open_run(db)
    reading = errors = due_pairs = 0
    if run is not None:
        for status in runs.run_status(db, run):
            if status.state == runs.READING:
                reading += 1
            elif status.state in (runs.ERROR, runs.MISSING_FILE):
                errors += 1
    else:
        due_pairs = len(runs.due_pairs(db, today_vn()).pairs)
    exported = select(SalesHistoryExported.sales_order_id)
    shop_online_pending = (
        db.scalar(
            select(func.count())
            .select_from(SalesOrder)
            .where(SalesOrder.status == states.DELIVERED)
            .where(SalesOrder.id.not_in(exported))
        )
        or 0
    )
    return (
        TodayFigures(
            needs_attention,
            awaiting_sales_admin,
            awaiting_reconcile,
            reading,
            errors,
            due_pairs,
            shop_online_pending,
        ),
        run,
    )


@router.get("/")
def today_page(
    request: Request, db: Session = Depends(get_db), user: AppUser = Depends(current_user)
):
    figures, run = collect(db)
    return render(request, "today.html", user, figures=figures, run=run, today=today_vn())
