"""Sort records by primary key ascending, tiebreak by secondary key ascending.

Each record is a (primary, secondary) pair. Reference implementation.
"""

from __future__ import annotations


def sort_records(records: list[tuple[int, int]]) -> list[tuple[int, int]]:
    return sorted(records, key=lambda r: (r[0], r[1]))
