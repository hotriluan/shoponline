"""Write what the shipping labels say into `customer_info`.

Rules per order (a name or address the label agrees with is kept as it is):

- blank name or address: written (an address written here is marked `label`)
- name differs: the admin decides
- address differs: overwritten when the file or an earlier label wrote the current one, the admin
  decides when an admin typed it or nobody knows who did (NULL)
- the pages of one order disagree: the admin decides, nothing is written
- an order the admin confirmed gets the label's name and address

The function does not commit and never logs or returns more than what the confirmation page
needs: names and addresses stay out of messages and events.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass, field

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from shoponline.db.models import CustomerInfo, PlatformSetting, SalesOrder
from shoponline.domain.provinces import place_key
from shoponline.domain.report_names import province_of
from shoponline.importers.shipping_label_pdf import Label, merge_labels

# The sources whose address a label may replace without asking.
_REPLACEABLE_SOURCES = {"file", "label"}


@dataclass(frozen=True)
class PendingLabel:
    """An order whose label differs from what is stored and waits for the admin."""

    platform: str
    order_id: str
    label_name: str
    label_address: str
    current_name: str | None
    current_address: str | None
    name_differs: bool
    address_differs: bool
    conflicting: bool


@dataclass
class LabelApplyResult:
    written: int = 0  # orders with at least one field written
    unchanged: int = 0  # orders the label agrees with
    skipped: int = 0  # labels of a platform the system does not know
    without_order: int = 0  # labelled orders that have no sales order yet
    pending: list[PendingLabel] = field(default_factory=list)


def _same(a: str | None, b: str | None) -> bool:
    return re.sub(r"\s+", " ", a or "").strip() == re.sub(r"\s+", " ", b or "").strip()


def _set_address(info: CustomerInfo, address: str) -> None:
    info.address = address
    info.address_source = "label"
    info.province = province_of(address)
    info.place_key = place_key(address)


def apply_labels(
    session: Session,
    labels: Collection[Label],
    *,
    confirmed: Collection[tuple[str, str]] = frozenset(),
) -> LabelApplyResult:
    result = LabelApplyResult()
    known = set(session.scalars(select(PlatformSetting.platform)))
    merged = merge_labels([(0, label) for label in labels])
    wanted = [(m.platform, m.order_id) for m in merged if m.platform in known]
    existing: dict[tuple[str, str], CustomerInfo] = {}
    with_order: set[tuple[str, str]] = set()
    if wanted:
        for info in session.scalars(
            select(CustomerInfo).where(
                tuple_(CustomerInfo.platform, CustomerInfo.platform_order_id).in_(wanted)
            )
        ):
            existing[(info.platform, info.platform_order_id)] = info
        with_order = {
            (platform, order_id)
            for platform, order_id in session.execute(
                select(SalesOrder.platform, SalesOrder.platform_order_id).where(
                    tuple_(SalesOrder.platform, SalesOrder.platform_order_id).in_(wanted)
                )
            )
        }
    for label in merged:
        key = (label.platform, label.order_id)
        if label.platform not in known:
            result.skipped += 1
            continue
        if key not in with_order:
            result.without_order += 1
        info = existing.get(key)
        is_new = info is None
        if info is None:
            info = CustomerInfo(platform=label.platform, platform_order_id=label.order_id)
        wrote, waiting = _apply_one(info, label, key in confirmed)
        if is_new and wrote:  # an order that only waits for the admin gets no empty row
            session.add(info)
        if waiting is not None:
            result.pending.append(waiting)
        if wrote:
            result.written += 1
        elif waiting is None:
            result.unchanged += 1
    session.flush()
    return result


def _apply_one(
    info: CustomerInfo, label: Label, confirmed: bool
) -> tuple[bool, PendingLabel | None]:
    """Returns (something was written, the part that waits for the admin)."""
    if label.conflicting and not confirmed:
        return False, _pending(info, label, name=True, address=True)
    wrote = False
    name_waits = address_waits = False
    if not _same(info.customer_name, label.name):
        if not info.customer_name or confirmed:
            info.customer_name = label.name
            wrote = True
        else:
            name_waits = True
    if not _same(info.address, label.address):
        replaceable = info.address_source in _REPLACEABLE_SOURCES
        if not info.address or replaceable or confirmed:
            _set_address(info, label.address)
            wrote = True
        else:
            address_waits = True
    if name_waits or address_waits:
        return wrote, _pending(info, label, name=name_waits, address=address_waits)
    return wrote, None


def _pending(info: CustomerInfo, label: Label, *, name: bool, address: bool) -> PendingLabel:
    return PendingLabel(
        platform=label.platform,
        order_id=label.order_id,
        label_name=label.name,
        label_address=label.address,
        current_name=info.customer_name,
        current_address=info.address,
        name_differs=name,
        address_differs=address,
        conflicting=label.conflicting,
    )
