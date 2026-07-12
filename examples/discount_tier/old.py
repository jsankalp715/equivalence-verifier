"""Loyalty tier lookup by purchase count -- reference implementation."""

from __future__ import annotations


def tier_for_count(purchase_count: int) -> str:
    if purchase_count < 5:
        return "bronze"
    if purchase_count < 10:
        return "silver"
    if purchase_count < 25:
        return "gold"
    return "platinum"
