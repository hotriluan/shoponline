"""Order status machine. Every status change goes through transition()."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from shoponline.db.models import EventLog, SalesOrder

NEW = "NEW"
READY = "READY"
SO_LINKED = "SO_LINKED"
DELIVERED = "DELIVERED"
MAPPING_ERROR = "MAPPING_ERROR"
NEED_REVIEW = "NEED_REVIEW"
CANCELLED = "CANCELLED"

# Statuses where the order content may still change (re-import, mapping re-check).
OPEN_STATUSES = frozenset({NEW, READY, MAPPING_ERROR, NEED_REVIEW})

ALLOWED: dict[str, frozenset[str]] = {
    NEW: frozenset({READY, MAPPING_ERROR, NEED_REVIEW, CANCELLED}),
    READY: frozenset({MAPPING_ERROR, NEED_REVIEW, SO_LINKED, CANCELLED}),
    MAPPING_ERROR: frozenset({READY, NEED_REVIEW, SO_LINKED, CANCELLED}),
    NEED_REVIEW: frozenset({READY, MAPPING_ERROR, SO_LINKED, CANCELLED}),
    SO_LINKED: frozenset({DELIVERED, CANCELLED}),
    DELIVERED: frozenset(),
    CANCELLED: frozenset(),
}

LABELS = {
    NEW: "Mới",
    READY: "Sẵn sàng",
    SO_LINKED: "Đã có SO",
    DELIVERED: "Đã có DO",
    MAPPING_ERROR: "Thiếu ánh xạ",
    NEED_REVIEW: "Cần kiểm tra",
    CANCELLED: "Đã hủy",
}


class InvalidTransition(ValueError):
    pass


def log_event(
    session: Session,
    actor: str,
    kind: str,
    *,
    platform: str | None = None,
    platform_order_id: str | None = None,
    detail: dict | None = None,
) -> None:
    session.add(
        EventLog(
            actor=actor,
            kind=kind,
            platform=platform,
            platform_order_id=platform_order_id,
            detail=json.dumps(detail, ensure_ascii=False) if detail else None,
        )
    )


def transition(
    session: Session, order: SalesOrder, new_status: str, actor: str, reason: str | None = None
) -> bool:
    """Move order to new_status. Returns False when the status is unchanged."""
    old = order.status
    if old == new_status:
        order.status_reason = reason
        return False
    if new_status not in ALLOWED.get(old, frozenset()):
        raise InvalidTransition(
            f"Không chuyển được đơn {order.platform_order_id} từ {old} sang {new_status}"
        )
    order.status = new_status
    order.status_reason = reason
    log_event(
        session,
        actor,
        "status_change",
        platform=order.platform,
        platform_order_id=order.platform_order_id,
        detail={"from": old, "to": new_status, "reason": reason},
    )
    return True
