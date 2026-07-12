"""Rewrite -- forgot the tiebreak rule.

The rewriter noticed `sorted` is stable and thought "just sort by primary".
For records that share a primary key, old orders them by secondary ascending,
new preserves input order. Divergence for any input with a primary-key tie
whose secondary keys are out of order.
"""

from __future__ import annotations


def sort_records(records: list[tuple[int, int]]) -> list[tuple[int, int]]:
    return sorted(records, key=lambda r: r[0])  # BUG: no tiebreak
