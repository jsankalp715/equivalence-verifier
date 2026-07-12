"""Legacy discount pricing — the reference implementation.

Applies a percentage discount, then a loyalty-tier multiplier, then rounds
the final result to two decimal places using standard round-half-to-even.
"""

from __future__ import annotations


def discount_price(
    price: float,
    discount_pct: float,
    loyalty_multiplier: float,
) -> float:
    discounted = price * (1.0 - discount_pct / 100.0)
    final = discounted * loyalty_multiplier
    return round(final, 2)
