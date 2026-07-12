"""Rewritten discount pricing — with a seeded rounding bug.

The rewrite was supposed to "avoid banker's rounding surprises" by explicitly
truncating to two decimal places. In practice this is not equivalent: for
values that should round UP (e.g. 0.995 -> 1.00), truncation gives 0.99.
"""

from __future__ import annotations

import math


def discount_price(
    price: float,
    discount_pct: float,
    loyalty_multiplier: float,
) -> float:
    discounted = price * (1.0 - discount_pct / 100.0)
    final = discounted * loyalty_multiplier
    # BUG: truncation instead of rounding.
    return math.floor(final * 100.0) / 100.0
