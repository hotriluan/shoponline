"""Store zrsd001 SO numbers, link them to platform orders, and report discrepancies."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.db.models import (
    ImportBatch,
    OrderBatch,
    PlatformSetting,
    SalesOrder,
    SapSoRef,
    SapSoRefItem,
)
from shoponline.domain import states
from shoponline.domain.expected_value import expected_so_value
from shoponline.importers.sap_reports import DeliveryRow, SoReport


def platform_by_customer(session: Session) -> dict[str, str]:
    return {s.sap_customer: s.platform for s in session.scalars(select(PlatformSetting))}


def is_main_line(item_no: int) -> bool:
    """Kit components are added by SAP as sub-lines (11, 12, …) under the kit line (10)."""
    return item_no % 10 == 0


# ---------------------------------------------------------------- zrsd001 import


@dataclass
class SoImportResult:
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    linked: list[SalesOrder] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _signature(po_no, sold_to, doc_date, lines) -> tuple:
    return (
        po_no,
        sold_to,
        doc_date,
        tuple(
            (
                int(i.item_no),
                i.material_number,
                Decimal(i.quantity).normalize(),
                int(i.net_value_incl),
            )
            for i in sorted(lines, key=lambda x: x.item_no)
        ),
    )


def store_so_reports(
    session: Session,
    reports: list[SoReport],
    actor: str,
    import_batch: ImportBatch | None = None,
    expect_batch: OrderBatch | None = None,
) -> SoImportResult:
    result = SoImportResult()
    for report in reports:
        ref = session.get(SapSoRef, report.so_number)
        new_sig = _signature(report.po_no, report.sold_to, report.doc_date, report.lines)
        if (
            ref is not None
            and _signature(ref.po_no, ref.sold_to, ref.doc_date, ref.items) == new_sig
        ):
            result.unchanged += 1
            continue
        if ref is None:
            ref = SapSoRef(so_number=report.so_number)
            session.add(ref)
            result.new += 1
        else:
            result.updated += 1
        ref.po_no = report.po_no
        ref.sold_to = report.sold_to
        ref.doc_date = report.doc_date
        ref.net_value_incl = report.net_value_incl
        ref.import_batch_id = import_batch.id if import_batch else None
        ref.items = [
            SapSoRefItem(
                item_no=line.item_no,
                material_number=line.material_number,
                quantity=line.quantity,
                net_value_incl=line.net_value_incl,
            )
            for line in report.lines
        ]
    session.flush()
    result.linked = link_orders(session, actor)

    if import_batch is not None:
        import_batch.new_count = result.new
        import_batch.updated_count = result.updated
        import_batch.unchanged_count = result.unchanged
    if expect_batch is not None:
        customer = session.get(PlatformSetting, expect_batch.platform).sap_customer
        if not any(
            r.sold_to == customer and r.doc_date == expect_batch.processing_date for r in reports
        ):
            result.warnings.append(
                f"File không có SO nào của khách hàng {customer} ngày "
                f"{expect_batch.processing_date:%d/%m/%Y}. Kiểm tra lại bộ lọc khi chạy zrsd001."
            )
    states.log_event(
        session,
        actor,
        "zrsd001_imported",
        detail={
            "new": result.new,
            "updated": result.updated,
            "unchanged": result.unchanged,
            "linked": len(result.linked),
        },
    )
    session.flush()
    return result


def link_orders(session: Session, actor: str) -> list[SalesOrder]:
    """Link every open order without SO to the single SO whose PO No equals its order id."""
    customers = platform_by_customer(session)
    refs_by_key: dict[tuple[str, str], list[SapSoRef]] = defaultdict(list)
    for ref in session.scalars(select(SapSoRef)):
        platform = customers.get(ref.sold_to)
        if platform:
            refs_by_key[(platform, ref.po_no)].append(ref)
    taken = set(
        session.scalars(select(SalesOrder.so_number).where(SalesOrder.so_number.is_not(None)))
    )
    linked: list[SalesOrder] = []
    candidates = session.scalars(
        select(SalesOrder).where(
            SalesOrder.so_number.is_(None), SalesOrder.status.in_(states.OPEN_STATUSES)
        )
    )
    for order in candidates:
        refs = refs_by_key.get((order.platform, order.platform_order_id), [])
        if len(refs) != 1 or refs[0].so_number in taken:
            continue  # none, or a duplicate that a person must resolve
        order.so_number = refs[0].so_number
        taken.add(order.so_number)
        states.transition(session, order, states.SO_LINKED, actor, f"SO {order.so_number}")
        linked.append(order)
    session.flush()
    return linked


class LinkError(ValueError):
    pass


def link_manually(session: Session, order: SalesOrder, so_number: str, actor: str) -> None:
    """Admin links an SO whose PO No was mistyped to the right order."""
    ref = session.get(SapSoRef, so_number)
    if ref is None:
        raise LinkError(f"Chưa có SO {so_number} trong dữ liệu zrsd001")
    if order.so_number:
        raise LinkError(f"Đơn {order.platform_order_id} đã có SO {order.so_number}")
    if order.status not in states.OPEN_STATUSES:
        raise LinkError(f"Đơn {order.platform_order_id} đang ở trạng thái {order.status}")
    holder = session.scalar(select(SalesOrder).where(SalesOrder.so_number == so_number))
    if holder is not None:
        raise LinkError(f"SO {so_number} đã nối với đơn {holder.platform_order_id}")
    order.so_number = so_number
    states.transition(
        session, order, states.SO_LINKED, actor, f"Nối tay SO {so_number} (PO No {ref.po_no})"
    )
    states.log_event(
        session,
        actor,
        "so_linked_manually",
        platform=order.platform,
        platform_order_id=order.platform_order_id,
        detail={"so_number": so_number, "po_no": ref.po_no},
    )
    session.flush()


# ---------------------------------------------------------------- discrepancy report


@dataclass
class ValueMismatch:
    order: SalesOrder
    so_number: str
    expected: int
    actual: int
    detail: str


@dataclass
class BatchReport:
    missing_so: list[SalesOrder] = field(default_factory=list)
    unmatched_sos: list[SapSoRef] = field(default_factory=list)
    duplicate_po: list[tuple[str, list[str]]] = field(default_factory=list)
    value_mismatch: list[ValueMismatch] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not (
            self.missing_so or self.unmatched_sos or self.duplicate_po or self.value_mismatch
        )


def _material_quantities(pairs) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for material, quantity in pairs:
        totals[material] += Decimal(quantity)
    return {k: v.normalize() for k, v in totals.items()}


def batch_report(session: Session, batch: OrderBatch) -> BatchReport:
    report = BatchReport()
    customer = session.get(PlatformSetting, batch.platform).sap_customer
    orders = list(session.scalars(select(SalesOrder).where(SalesOrder.order_batch_id == batch.id)))
    order_ids = {o.platform_order_id for o in orders}
    platform_order_ids = set(
        session.scalars(
            select(SalesOrder.platform_order_id).where(SalesOrder.platform == batch.platform)
        )
    )
    linked_sos = set(
        session.scalars(select(SalesOrder.so_number).where(SalesOrder.so_number.is_not(None)))
    )
    refs = list(
        session.scalars(
            select(SapSoRef).where(
                SapSoRef.sold_to == customer,
                (SapSoRef.doc_date == batch.processing_date) | SapSoRef.po_no.in_(order_ids),
            )
        )
    )

    # 1. READY orders without SO
    report.missing_so = sorted(
        (o for o in orders if o.status == states.READY and not o.so_number),
        key=lambda o: o.ordered_at,
    )
    # 2. SOs of the day whose PO No matches no order of the platform
    report.unmatched_sos = sorted(
        (
            r
            for r in refs
            if r.doc_date == batch.processing_date
            and r.po_no not in platform_order_ids
            and r.so_number not in linked_sos
        ),
        key=lambda r: r.so_number,
    )
    # 3. one PO No, several SOs
    by_po: dict[str, list[str]] = defaultdict(list)
    for ref in refs:
        by_po[ref.po_no].append(ref.so_number)
    report.duplicate_po = sorted((po, sorted(sos)) for po, sos in by_po.items() if len(sos) > 1)
    # 4. value or material/quantity differs from the platform file
    for order in orders:
        if not order.so_number or order.status == states.CANCELLED:
            continue
        ref = session.get(SapSoRef, order.so_number)
        if ref is None:
            continue
        expected = expected_so_value(order.items)
        problems = []
        if ref.net_value_incl != expected:
            problems.append(f"giá trị SO {ref.net_value_incl:,} khác {expected:,}")
        so_lines = _material_quantities(
            (i.material_number, i.quantity) for i in ref.items if is_main_line(i.item_no)
        )
        order_lines = _material_quantities(
            (i.material_number or "?", i.quantity) for i in order.items
        )
        if so_lines != order_lines:
            problems.append(
                "vật tư/số lượng SO "
                + ", ".join(f"{m}×{q}" for m, q in sorted(so_lines.items()))
                + " khác đơn "
                + ", ".join(f"{m}×{q}" for m, q in sorted(order_lines.items()))
            )
        if problems:
            report.value_mismatch.append(
                ValueMismatch(
                    order, ref.so_number, expected, ref.net_value_incl, "; ".join(problems)
                )
            )
    return report


# ---------------------------------------------------------------- zrsd004 deliveries


def mark_delivered(session: Session, rows: list[DeliveryRow], actor: str) -> int:
    first_delivery: dict[str, str] = {}
    for row in rows:
        first_delivery.setdefault(row.so_number, row.delivery)
    count = 0
    orders = session.scalars(
        select(SalesOrder).where(
            SalesOrder.so_number.in_(list(first_delivery)), SalesOrder.status == states.SO_LINKED
        )
    )
    for order in orders:
        order.do_number = first_delivery[order.so_number]
        states.transition(session, order, states.DELIVERED, actor, f"DO {order.do_number}")
        count += 1
    session.flush()
    return count
