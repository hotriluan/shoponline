"""Platform-independent order shape produced by every platform reader."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class ParsedItem:
    product_name: str
    variation_name: str
    quantity: int
    unit_price: int
    unit_subsidy: int = 0


@dataclass(frozen=True)
class ParsedOrder:
    platform: str
    platform_order_id: str
    ordered_at: datetime
    items: tuple[ParsedItem, ...]
    default_address: str
    review_reasons: tuple[str, ...] = field(default=())
    # Only platforms whose export shows the real buyer name (Lazada) fill this.
    customer_name: str | None = None

    @property
    def has_subsidy(self) -> bool:
        return any(item.unit_subsidy > 0 for item in self.items)


def default_address(*parts: str) -> str:
    """Join district/province parts the way admins write them in the customer note."""
    kept = [p.strip() for p in parts if p and p.strip()]
    return ", ".join([*kept, "Việt Nam"])
