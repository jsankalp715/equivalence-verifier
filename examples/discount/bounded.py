"""Domain-constrained wrappers for symbolic analysis.

`old.py` and `new.py` are the legacy code and its rewrite as-found — kept
free of tool-specific annotations. This module wraps them with an explicit
domain guard so CrossHair's symbolic search stays within the real input
domain (positive prices, valid percentages, sensible loyalty tiers) rather
than exploring `-inf` and `NaN`.

Why `IgnoreAttempt` rather than docstring preconditions: crosshair's
`diffbehavior` command does *not* enforce PEP316 `pre:` conditions during
input generation (verified against crosshair 0.0.108 source). Raising
`IgnoreAttempt` on out-of-domain inputs tells the engine to discard the
path — the two wrappers behave identically on rejected inputs, so no
false divergence is recorded.

This is the Phase 2 analogue of `strategies.py` (Phase 1's domain spec).
"""

from __future__ import annotations

from crosshair import IgnoreAttempt

from . import new, old


def _in_domain(price: float, discount_pct: float, loyalty_multiplier: float) -> bool:
    return (
        0.01 <= price <= 10000.0
        and 0.0 <= discount_pct <= 100.0
        and 0.5 <= loyalty_multiplier <= 1.5
    )


def old_bounded(
    price: float,
    discount_pct: float,
    loyalty_multiplier: float,
) -> float:
    if not _in_domain(price, discount_pct, loyalty_multiplier):
        raise IgnoreAttempt
    return old.discount_price(price, discount_pct, loyalty_multiplier)


def new_bounded(
    price: float,
    discount_pct: float,
    loyalty_multiplier: float,
) -> float:
    if not _in_domain(price, discount_pct, loyalty_multiplier):
        raise IgnoreAttempt
    return new.discount_price(price, discount_pct, loyalty_multiplier)
