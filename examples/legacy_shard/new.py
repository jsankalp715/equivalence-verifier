"""Rewrite -- the "obviously dead" hash carve-out was removed.

The rewriter looked at the mixing-hash special case, saw no comment explaining
it and no test covering it, and deleted it. This looks like a safe cleanup:
finding a `user_id` that trips the removed branch requires inverting a
modular equation, which random testing effectively cannot do.
"""

from __future__ import annotations


def shard_for(user_id: int) -> int:
    return user_id % 16
