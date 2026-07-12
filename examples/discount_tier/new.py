"""Rewrite -- off-by-one at the silver/gold boundary.

The rewrite "cleaned up" the middle condition to `<=` but did not shift the
constant, silently changing behavior at purchase_count == 10:
  old(10) = "gold"
  new(10) = "silver"
"""

from __future__ import annotations


def tier_for_count(purchase_count: int) -> str:
    if purchase_count < 5:
        return "bronze"
    if purchase_count <= 10:  # BUG: should be `<`
        return "silver"
    if purchase_count < 25:
        return "gold"
    return "platinum"
