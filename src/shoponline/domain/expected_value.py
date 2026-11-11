"""Expected SO value incl. VAT, computed from the platform file."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol


class _Line(Protocol):
    quantity: int
    unit_price: int
    unit_subsidy: int


def expected_so_value(items: Iterable[_Line]) -> int:
    """Σ (original price − subsidy per unit) × quantity."""
    return sum((item.unit_price - item.unit_subsidy) * item.quantity for item in items)
