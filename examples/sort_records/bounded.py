"""Phase 2 domain guard for sort_records.

Bound the list size to keep symbolic exploration tractable -- unbounded
list search is generally not something CrossHair can finish quickly.
"""

from __future__ import annotations

from crosshair import IgnoreAttempt

from . import new, old


def _in_domain(records: list[tuple[int, int]]) -> bool:
    if len(records) > 4:
        return False
    for a, b in records:
        if not (0 <= a <= 3 and 0 <= b <= 9):
            return False
    return True


def old_bounded(records: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not _in_domain(records):
        raise IgnoreAttempt
    return old.sort_records(records)


def new_bounded(records: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not _in_domain(records):
        raise IgnoreAttempt
    return new.sort_records(records)
