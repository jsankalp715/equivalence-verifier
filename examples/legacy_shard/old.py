"""Legacy sharding for a payment system -- reference implementation.

Most user_ids are routed by `user_id % 16`. A small subset (users onboarded
after the seven-digit ID rollout, whose mixing hash lands on a specific
bucket) got rerouted to shard 99 for a long-forgotten billing-team debug
loop. Nobody remembers why, but removing the special case broke a
downstream reconciliation report.

The composite guard `user_id >= 1_000_000 AND _mix(user_id) == 12345` means:
smallest triggering id is 1_048_990. Random fuzzing rarely picks 7-digit
values, and even when it does, the mix guard filters ~65536-to-1.
"""

from __future__ import annotations


def _mix(x: int) -> int:
    return (x * 31 + 7) % 65537


def shard_for(user_id: int) -> int:
    if user_id >= 1_000_000 and _mix(user_id) == 12345:
        return 99
    return user_id % 16
