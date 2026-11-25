"""Money Lazada paid out, typed in by an admin.

Lazada's balance file carries no order id, so nothing can be read per order. The amount goes into
the same platform_settlement table as Shopee and TikTok, one row per order with line_key
"manual:<order id>" and source "manual", so every report that reads the table sees it. Setting an
amount again replaces the row; removing deletes it. Every change is logged with the old and new
amount (never a name or an address).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from shoponline.clock import today_vn
from shoponline.db.models import PlatformSettlement, SalesOrder
from shoponline.domain import states

PLATFORM = "LAZADA"
SOURCE = "manual"
DATE_FORMAT = "%d/%m/%Y"
SEPARATORS = re.compile(r"[.,\s]")


class SettlementError(ValueError):
    """A typed value that is refused; the message says why, in words the admin can act on."""


@dataclass(frozen=True)
class ParsedLine:
    line_no: int
    order_id: str
    amount: int | None
    settled_on: date | None
    error: str = ""


def line_key(order_id: str) -> str:
    return f"{SOURCE}:{order_id}"


def parse_amount(text: str) -> int:
    """A whole number of dong; dots, commas and spaces are thousands separators."""
    digits = SEPARATORS.sub("", text.strip())
    if not digits.isdigit():
        raise SettlementError(f"Số tiền '{text.strip()}' không phải số nguyên không âm")
    return int(digits)


def parse_date(text: str) -> date:
    try:
        return datetime.strptime(text.strip(), DATE_FORMAT).date()
    except ValueError:
        raise SettlementError(f"Ngày '{text.strip()}' không đúng dạng dd/mm/yyyy") from None


def parse_paste(text: str) -> list[ParsedLine]:
    """One line per order: order id, amount, date (dd/mm/yyyy), split by tabs. Blank lines are
    skipped; a line that cannot be read comes back with its error."""
    lines = []
    for number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        parts = [p.strip() for p in raw.split("\t")]
        order_id = parts[0]
        try:
            if len(parts) != 3 or not order_id:
                raise SettlementError("Cần đủ 3 cột: mã đơn, số tiền, ngày (cách nhau bằng Tab)")
            lines.append(ParsedLine(number, order_id, parse_amount(parts[1]), parse_date(parts[2])))
        except SettlementError as exc:
            lines.append(ParsedLine(number, order_id, None, None, str(exc)))
    return lines


def check(
    session: Session, order_id: str, amount: int, settled_on: date, today: date | None = None
) -> SalesOrder:
    """The order the amount is for; raises SettlementError when the values cannot be saved."""
    order = session.scalar(
        select(SalesOrder).where(
            SalesOrder.platform == PLATFORM, SalesOrder.platform_order_id == order_id
        )
    )
    if order is None:
        raise SettlementError(f"Không có đơn Lazada {order_id}")
    if amount < 0:
        raise SettlementError("Số tiền không được âm")
    if settled_on > (today or today_vn()):
        raise SettlementError("Ngày nhận tiền không được ở tương lai")
    if settled_on < order.ordered_at.date():
        raise SettlementError("Ngày nhận tiền không được trước ngày đặt đơn")
    return order


def _row(session: Session, order_id: str) -> PlatformSettlement | None:
    return session.scalar(
        select(PlatformSettlement).where(
            PlatformSettlement.platform == PLATFORM,
            PlatformSettlement.line_key == line_key(order_id),
        )
    )


def set_amount(
    session: Session,
    order_id: str,
    amount: int,
    settled_on: date,
    actor: str,
    today: date | None = None,
) -> None:
    """Record or replace the money received for a Lazada order. The caller commits."""
    check(session, order_id, amount, settled_on, today)
    moment = datetime.combine(settled_on, time())
    row = _row(session, order_id)
    old = None
    if row is None:
        session.add(
            PlatformSettlement(
                platform=PLATFORM,
                platform_order_id=order_id,
                line_key=line_key(order_id),
                amount=amount,
                settled_at=moment,
                source=SOURCE,
                entered_by=actor,
            )
        )
    else:
        old = row.amount
        row.amount, row.settled_at, row.entered_by = amount, moment, actor
    states.log_event(
        session,
        actor,
        "settlement_manual_set",
        platform=PLATFORM,
        platform_order_id=order_id,
        detail={"old": old, "new": amount, "settled_on": settled_on.isoformat()},
    )
    session.flush()


def remove(session: Session, order_id: str, actor: str) -> bool:
    """Delete the typed amount of an order; False when there was none. The caller commits."""
    row = _row(session, order_id)
    if row is None:
        return False
    old = row.amount
    session.delete(row)
    states.log_event(
        session,
        actor,
        "settlement_manual_removed",
        platform=PLATFORM,
        platform_order_id=order_id,
        detail={"old": old, "new": None},
    )
    session.flush()
    return True


def pending_orders(session: Session, month: date | None = None) -> list[SalesOrder]:
    """Lazada orders that have a DO but no money recorded, oldest first. `month` (any day of it)
    limits them to the orders placed in that month."""
    has_money = (
        select(PlatformSettlement.id)
        .where(
            PlatformSettlement.platform == SalesOrder.platform,
            PlatformSettlement.platform_order_id == SalesOrder.platform_order_id,
        )
        .exists()
    )
    stmt = select(SalesOrder).where(
        SalesOrder.platform == PLATFORM, SalesOrder.do_number.is_not(None), ~has_money
    )
    if month is not None:
        first = month.replace(day=1)
        after = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
        stmt = stmt.where(
            and_(
                SalesOrder.ordered_at >= datetime.combine(first, time()),
                SalesOrder.ordered_at < datetime.combine(after, time()),
            )
        )
    return list(session.scalars(stmt.order_by(SalesOrder.ordered_at, SalesOrder.platform_order_id)))


def entered(session: Session) -> list[PlatformSettlement]:
    """Every typed amount, newest settlement first."""
    return list(
        session.scalars(
            select(PlatformSettlement)
            .where(PlatformSettlement.platform == PLATFORM, PlatformSettlement.source == SOURCE)
            .order_by(PlatformSettlement.settled_at.desc(), PlatformSettlement.platform_order_id)
        )
    )
