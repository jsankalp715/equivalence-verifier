"""Integration tests that lock in the demo-set headline results.

These run Phase 1 (fuzzing) against each demo pair and assert that the
expected bug IS or IS NOT found within the declared budget. Phase 2
crosshair E2E runs are opt-in via env var (slow).

The point of these tests is not to test Hypothesis or CrossHair -- it's to
guard against a demo-example file being edited in a way that quietly breaks
the story the README tells. If the `legacy_shard` phase-1 assertion starts
failing (Phase 1 unexpectedly finds it), that's a signal to bump the trigger
difficulty; if `discount_tier` starts failing (Phase 1 misses it), the
strategy spec probably got too loose.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from verifier.fuzzer import run_differential_fuzz
from verifier.strategies import load_spec_file


def _fuzz(example_dir: str, func_name: str, max_examples: int):
    root = REPO_ROOT / "examples" / example_dir
    old_mod = importlib.import_module(f"examples.{example_dir}.old")
    new_mod = importlib.import_module(f"examples.{example_dir}.new")
    strategies = load_spec_file(root / "strategies.py")
    return run_differential_fuzz(
        old_impl=getattr(old_mod, func_name),
        new_impl=getattr(new_mod, func_name),
        strategies=strategies,
        max_examples=max_examples,
    )


def test_discount_phase1_catches_rounding_bug():
    r = _fuzz("discount", "discount_price", max_examples=200)
    assert r.counterexample is not None


def test_discount_tier_phase1_catches_offbyone():
    r = _fuzz("discount_tier", "tier_for_count", max_examples=200)
    assert r.counterexample is not None
    # Off-by-one lives at exactly count=10.
    assert r.counterexample.inputs == {"purchase_count": 10}


def test_http_class_phase1_catches_dropped_teapot():
    r = _fuzz("http_class", "http_class", max_examples=500)
    assert r.counterexample is not None
    assert r.counterexample.inputs == {"code": 418}


def test_sort_records_phase1_catches_lost_tiebreak():
    r = _fuzz("sort_records", "sort_records", max_examples=300)
    assert r.counterexample is not None


def test_legacy_shard_phase1_does_NOT_find_hash_carveout():
    """Portfolio's headline result: Phase 1 alone cannot find this bug.

    If this test starts failing, either Hypothesis got smarter or the demo
    strategy inadvertently narrowed the search space. Both cases should be
    investigated -- the README claim depends on this.
    """
    r = _fuzz("legacy_shard", "shard_for", max_examples=2000)
    assert r.counterexample is None, (
        f"Phase 1 unexpectedly found the hash carve-out at {r.counterexample.inputs}. "
        "The README's headline finding is invalidated -- rework the trigger."
    )
