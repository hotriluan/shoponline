"""Store parsed platform orders: additive upsert that never moves an order backwards."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.db.models import CustomerInfo, ImportBatch, OrderBatch, SalesOrder, SalesOrderItem
from shoponline.domain import states
from shoponline.domain.gi_date import suggest_gi_date
from shoponline.domain.order import ParsedOrder
from shoponline.domain.provinces import place_key
from shoponline.domain.report_names import province_of
from shoponline.domain.shops import default_shop, require_choice
from shoponline.domain.sku_mapping import find_mapping
from shoponline.importers.excel_table import FileRejected
from shoponline.importers.lazada_orders import read_lazada_orders
from shoponline.importers.shopee_orders import read_shopee_orders
from shoponline.importers.tiktok_orders import read_tiktok_orders

READERS: dict[str, Callable[[str | Path | BinaryIO], list[ParsedOrder]]] = {
    "SHOPEE": read_shopee_orders,
    "TIKTOK": read_tiktok_orders,
    "LAZADA": read_lazada_orders,
}
MAX_DAYS_FROM_PROCESSING_DATE = 31


@dataclass
class ImportResult:
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    problem_orders: list[SalesOrder] = field(default_factory=list)
    # Orders kept as they are (SO, DO or cancelled) although this file says something different.
    changed_after_so: list[SalesOrder] = field(default_factory=list)
    # Orders already in a batch of another processing date: they stay there.
    in_other_batch: list[tuple[SalesOrder, OrderBatch]] = field(default_factory=list)
    # Orders that already belong to another shop than the one chosen for this file: they stay.
    in_other_shop: list[SalesOrder] = field(default_factory=list)
    shop_code: str = ""
    batch: OrderBatch | None = None


def get_or_create_batch(session: Session, platform: str, processing_date: date) -> OrderBatch:
    batch = session.scalar(
        select(OrderBatch).where(
            OrderBatch.platform == platform, OrderBatch.processing_date == processing_date
        )
    )
    if batch is None:
        batch = OrderBatch(
            platform=platform,
            processing_date=processing_date,
            gi_date=suggest_gi_date(processing_date),
        )
        session.add(batch)
        session.flush()
    return batch


def evaluate_order(session: Session, order: SalesOrder, actor: str) -> None:
    """Fill SAP material per line and set READY / MAPPING_ERROR / NEED_REVIEW."""
    if order.status not in states.OPEN_STATUSES:
        return
    missing: list[str] = []
    for item in order.items:
        mapping = find_mapping(session, order.platform, item.product_name, item.variation_name)
        if mapping is None:
            item.material_number = None
            item.sap_name = None
            missing.append(f"{item.product_name} | {item.variation_name}")
        else:
            item.material_number = mapping.material_number
            item.sap_name = mapping.sap_name
    if missing:
        states.transition(
            session, order, states.MAPPING_ERROR, actor, "Thiếu ánh xạ: " + "; ".join(missing)
        )
    elif order.review_note:
        states.transition(session, order, states.NEED_REVIEW, actor, order.review_note)
    else:
        states.transition(session, order, states.READY, actor, None)


def reevaluate_mapping_errors(session: Session, platform: str, actor: str) -> int:
    """Re-check every MAPPING_ERROR order of a platform. Returns how many became READY."""
    orders = session.scalars(
        select(SalesOrder).where(
            SalesOrder.platform == platform, SalesOrder.status == states.MAPPING_ERROR
        )
    ).all()
    fixed = 0
    for order in orders:
        evaluate_order(session, order, actor)
        fixed += order.status == states.READY
    session.flush()
    return fixed


def _item_signature(items) -> list[tuple]:
    return [
        (i.product_name, i.variation_name, i.quantity, i.unit_price, i.unit_subsidy) for i in items
    ]


def _set_items(order: SalesOrder, parsed: ParsedOrder) -> None:
    order.items.clear()
    for line_no, item in enumerate(parsed.items, start=1):
        order.items.append(
            SalesOrderItem(
                line_no=line_no,
                product_name=item.product_name,
                variation_name=item.variation_name,
                quantity=item.quantity,
                unit_price=item.unit_price,
                unit_subsidy=item.unit_subsidy,
            )
        )


def _check_dates(orders: list[ParsedOrder], processing_date: date) -> None:
    far = [
        f"{o.platform_order_id}: {o.ordered_at:%d/%m/%Y}"
        for o in orders
        if abs((o.ordered_at.date() - processing_date).days) > MAX_DAYS_FROM_PROCESSING_DATE
    ]
    if far:
        raise FileRejected(
            f"Ngày đặt lệch quá {MAX_DAYS_FROM_PROCESSING_DATE} ngày so với ngày xử lý "
            f"{processing_date:%d/%m/%Y} (có thể đọc nhầm ngày/tháng)",
            far,
        )


def import_orders(
    session: Session,
    parsed_orders: list[ParsedOrder],
    platform: str,
    processing_date: date,
    actor: str,
    import_batch: ImportBatch | None = None,
    shop_code: str | None = None,
) -> ImportResult:
    """New orders get `shop_code` (an active shop of the platform); without one, the platform's
    default shop. An order already stored keeps the shop it has."""
    wrong_platform = {o.platform for o in parsed_orders} - {platform}
    if wrong_platform:
        raise FileRejected(f"File chứa đơn của sàn khác: {', '.join(sorted(wrong_platform))}")
    _check_dates(parsed_orders, processing_date)

    shop = (
        require_choice(session, platform, shop_code)
        if shop_code
        else default_shop(session, platform)
    )
    result = ImportResult(shop_code=shop.code)
    if import_batch is not None:
        import_batch.shop_code = shop.code
    batch = get_or_create_batch(session, platform, processing_date)
    result.batch = batch
    for parsed in parsed_orders:
        review_note = "; ".join(parsed.review_reasons) or None
        order = session.scalar(
            select(SalesOrder).where(
                SalesOrder.platform == platform,
                SalesOrder.platform_order_id == parsed.platform_order_id,
            )
        )
        if order is None:
            order = SalesOrder(
                platform=platform,
                platform_order_id=parsed.platform_order_id,
                order_batch_id=batch.id,
                shop_code=shop.code,
                ordered_at=parsed.ordered_at,
                status=states.NEW,
                review_note=review_note,
            )
            session.add(order)
            _set_items(order, parsed)
            session.flush()
            states.log_event(
                session,
                actor,
                "order_imported",
                platform=platform,
                platform_order_id=order.platform_order_id,
                detail={"import_batch_id": import_batch.id if import_batch else None},
            )
            evaluate_order(session, order, actor)
            result.new += 1
        elif order.status not in states.OPEN_STATUSES:
            result.unchanged += 1  # SO already linked, delivered or cancelled: keep as is
            if (
                _item_signature(order.items) != _item_signature(parsed.items)
                or order.ordered_at != parsed.ordered_at
            ):
                _report_change_after_so(session, order, actor, import_batch, result)
        elif (
            _item_signature(order.items) == _item_signature(parsed.items)
            and order.ordered_at == parsed.ordered_at
            and order.review_note == review_note
        ):
            result.unchanged += 1
        else:
            order.ordered_at = parsed.ordered_at
            order.review_note = review_note
            _set_items(order, parsed)
            session.flush()
            states.log_event(
                session,
                actor,
                "order_updated",
                platform=platform,
                platform_order_id=order.platform_order_id,
                detail={"import_batch_id": import_batch.id if import_batch else None},
            )
            evaluate_order(session, order, actor)
            result.updated += 1

        if order.status in (states.MAPPING_ERROR, states.NEED_REVIEW):
            result.problem_orders.append(order)
        if order.order_batch_id != batch.id:
            result.in_other_batch.append((order, session.get(OrderBatch, order.order_batch_id)))
        if order.shop_code != shop.code:
            result.in_other_shop.append(order)
        _ensure_customer(session, platform, parsed)

    if import_batch is not None:
        import_batch.new_count = result.new
        import_batch.updated_count = result.updated
        import_batch.unchanged_count = result.unchanged
    states.log_event(
        session,
        actor,
        "file_imported",
        platform=platform,
        detail={
            "processing_date": processing_date.isoformat(),
            "new": result.new,
            "updated": result.updated,
            "unchanged": result.unchanged,
            "changed_after_so": len(result.changed_after_so),
            "in_other_batch": len(result.in_other_batch),
            "in_other_shop": len(result.in_other_shop),
            "shop": shop.code,
        },
    )
    session.flush()
    return result


def _report_change_after_so(
    session: Session,
    order: SalesOrder,
    actor: str,
    import_batch: ImportBatch | None,
    result: ImportResult,
) -> None:
    """The platform now says something else about an order that already has an SO, a DO or was
    cancelled. The order is not changed; an event is written and the batch report lists it."""
    result.changed_after_so.append(order)
    states.log_event(
        session,
        actor,
        "order_changed_after_so",
        platform=order.platform,
        platform_order_id=order.platform_order_id,
        detail={
            "status": order.status,
            "import_batch_id": import_batch.id if import_batch else None,
        },
    )


def _ensure_customer(session: Session, platform: str, parsed: ParsedOrder) -> None:
    """Create the customer row from the file; only fill blanks, never overwrite admin edits."""
    existing = session.scalar(
        select(CustomerInfo).where(
            CustomerInfo.platform == platform,
            CustomerInfo.platform_order_id == parsed.platform_order_id,
        )
    )
    if existing is None:
        session.add(
            CustomerInfo(
                platform=platform,
                platform_order_id=parsed.platform_order_id,
                customer_name=parsed.customer_name,
                address=parsed.default_address,
                province=province_of(parsed.default_address),
                place_key=place_key(parsed.default_address),
                address_source="file" if parsed.default_address else None,
            )
        )
        return
    if not existing.address:
        existing.address = parsed.default_address
        existing.province = province_of(parsed.default_address)
        existing.place_key = place_key(parsed.default_address)
        existing.address_source = "file" if parsed.default_address else None
    if not existing.customer_name and parsed.customer_name:
        existing.customer_name = parsed.customer_name
