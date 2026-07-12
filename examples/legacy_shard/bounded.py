"""Phase 2 domain guard for the sharding function."""

from __future__ import annotations

from crosshair import IgnoreAttempt

from . import new, old


def _in_domain(user_id: int) -> bool:
    return 0 <= user_id <= 10_000_000


def old_bounded(user_id: int) -> int:
    if not _in_domain(user_id):
        raise IgnoreAttempt
    return old.shard_for(user_id)


def new_bounded(user_id: int) -> int:
    if not _in_domain(user_id):
        raise IgnoreAttempt
    return new.shard_for(user_id)
