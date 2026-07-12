"""Phase 2 domain guard for the tier lookup."""

from __future__ import annotations

from crosshair import IgnoreAttempt

from . import new, old


def _in_domain(purchase_count: int) -> bool:
    return 0 <= purchase_count <= 1000


def old_bounded(purchase_count: int) -> str:
    if not _in_domain(purchase_count):
        raise IgnoreAttempt
    return old.tier_for_count(purchase_count)


def new_bounded(purchase_count: int) -> str:
    if not _in_domain(purchase_count):
        raise IgnoreAttempt
    return new.tier_for_count(purchase_count)
