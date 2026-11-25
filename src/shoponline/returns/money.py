"""Exact money arithmetic for the return documents.

Python's `round()` rounds halves to even and `/` returns floats; an invoice rounds halves up. Every
rounding of money under `returns/` goes through `round_half_up`.
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction


def round_half_up(numerator: int | Decimal, denominator: int | Decimal) -> int:
    """numerator / denominator rounded to a whole number, halves away from zero."""
    if not denominator:
        raise ZeroDivisionError("denominator is zero")
    ratio = Fraction(numerator) / Fraction(denominator)
    # floor(|ratio| + 1/2) with the fraction kept exact, then the sign put back.
    magnitude = (2 * abs(ratio.numerator) + ratio.denominator) // (2 * ratio.denominator)
    return -magnitude if ratio < 0 else magnitude


def format_vnd(amount: int) -> str:
    """111111 -> '111.111', -8889 -> '-8.889'."""
    text = f"{abs(amount):,}".replace(",", ".")
    return f"-{text}" if amount < 0 else text
