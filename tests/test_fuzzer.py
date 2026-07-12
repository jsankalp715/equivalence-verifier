"""Smoke tests for the Phase 1 engine."""

from __future__ import annotations

import math

from hypothesis import strategies as st

from verifier.comparator import exact_equality, float_tolerance, run_once
from verifier.fuzzer import run_differential_fuzz


def _identical_add(a: int, b: int) -> int:
    return a + b


def _buggy_add(a: int, b: int) -> int:
    # A boundary bug — findable by fuzzing, shrinks to a=51, b=0.
    if a > 50:
        return 999
    return a + b


def test_no_divergence_when_impls_agree():
    result = run_differential_fuzz(
        old_impl=_identical_add,
        new_impl=_identical_add,
        strategies={
            "a": st.integers(min_value=-100, max_value=100),
            "b": st.integers(min_value=-100, max_value=100),
        },
        max_examples=200,
    )
    assert result.counterexample is None
    assert result.examples_tried > 0


def test_finds_and_shrinks_seeded_bug():
    result = run_differential_fuzz(
        old_impl=_identical_add,
        new_impl=_buggy_add,
        strategies={
            "a": st.integers(min_value=0, max_value=100),
            "b": st.integers(min_value=0, max_value=100),
        },
        max_examples=500,
    )
    assert result.counterexample is not None
    # Shrinking should land at the boundary (a=51, b=0).
    assert result.counterexample.inputs["a"] == 51
    assert result.counterexample.inputs["b"] == 0
    assert result.counterexample.new_outcome.value == 999


def test_exception_vs_value_is_a_divergence():
    def raises(a: int) -> int:
        raise ValueError("nope")

    def returns(a: int) -> int:
        return 0

    result = run_differential_fuzz(
        old_impl=raises,
        new_impl=returns,
        strategies={"a": st.integers(min_value=0, max_value=5)},
        max_examples=50,
    )
    assert result.counterexample is not None
    assert result.counterexample.old_outcome.kind == "exception"
    assert result.counterexample.new_outcome.kind == "value"


def test_float_tolerance_masks_small_diffs():
    def f1(x: float) -> float:
        return x * 3.0

    def f2(x: float) -> float:
        return x + x + x  # subtly different due to FP

    exact = run_differential_fuzz(
        old_impl=f1, new_impl=f2,
        strategies={"x": st.floats(min_value=0.1, max_value=1e6, allow_nan=False, allow_infinity=False)},
        max_examples=200,
        comparator=exact_equality,
    )
    tolerant = run_differential_fuzz(
        old_impl=f1, new_impl=f2,
        strategies={"x": st.floats(min_value=0.1, max_value=1e6, allow_nan=False, allow_infinity=False)},
        max_examples=200,
        comparator=float_tolerance(rel_tol=1e-9, abs_tol=1e-12),
    )
    # Exact mode may or may not find a diff depending on FP luck; tolerant mode
    # should never find one for this pair.
    assert tolerant.counterexample is None
