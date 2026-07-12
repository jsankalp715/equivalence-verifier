"""Phase 1 engine: property-based differential fuzzing with Hypothesis.

The core trick: build a Hypothesis property dynamically from a strategies dict,
run both implementations on the same input, and use Hypothesis's built-in
shrinking to minimize any counterexample to the smallest form that still
triggers disagreement.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from hypothesis import HealthCheck, Phase, given, settings
from hypothesis import strategies as st

from .comparator import Comparator, Outcome, exact_equality, run_once
from .report import Counterexample


@dataclass
class FuzzResult:
    examples_tried: int
    counterexample: Counterexample | None
    elapsed_seconds: float = 0.0


class _Divergence(AssertionError):
    """Raised inside the Hypothesis property to trigger shrinking on divergence."""


def run_differential_fuzz(
    old_impl: Callable,
    new_impl: Callable,
    strategies: dict[str, st.SearchStrategy],
    *,
    max_examples: int = 500,
    comparator: Comparator = exact_equality,
    seed: int | None = None,
) -> FuzzResult:
    """Fuzz two implementations against each other; return a FuzzResult.

    Hypothesis shrinks by re-running the property on progressively simpler
    inputs; each shrink attempt calls both impls again, so `examples_tried`
    counts every invocation (shrink attempts included).
    """
    # Mutable state captured by closure. We track:
    #   - total invocations (for the report's "inputs tried" number)
    #   - the most recently seen divergence (Hypothesis's shrinking will keep
    #     narrowing this until it can't shrink further)
    state: dict[str, Any] = {
        "count": 0,
        "last_divergence": None,  # (inputs, old_outcome, new_outcome)
    }

    hypothesis_settings = settings(
        max_examples=max_examples,
        deadline=None,  # legacy code can be slow; don't fail on timeouts
        derandomize=seed is not None,
        database=None,  # portfolio tool: reproducible runs, no ~/.hypothesis dir
        suppress_health_check=[
            HealthCheck.too_slow,
            HealthCheck.data_too_large,
            HealthCheck.function_scoped_fixture,
        ],
        phases=[Phase.generate, Phase.shrink],
    )

    @hypothesis_settings
    @given(**strategies)
    def _property(**kwargs):
        state["count"] += 1
        old_outcome = run_once(old_impl, kwargs)
        new_outcome = run_once(new_impl, kwargs)
        if not comparator(old_outcome, new_outcome):
            state["last_divergence"] = (dict(kwargs), old_outcome, new_outcome)
            raise _Divergence(
                f"old {old_outcome.render()} vs new {new_outcome.render()}"
            )

    start = time.perf_counter()
    try:
        _property()
    except _Divergence:
        pass
    except Exception as e:
        # Anything else (e.g. Hypothesis internal Flaky) -- surface it as a note
        # rather than crashing the CLI. The last observed divergence, if any,
        # is still the useful signal.
        if state["last_divergence"] is None:
            raise
    elapsed = time.perf_counter() - start

    counterexample: Counterexample | None = None
    if state["last_divergence"] is not None:
        inputs, old_outcome, new_outcome = state["last_divergence"]
        counterexample = Counterexample(
            inputs=inputs,
            old_outcome=old_outcome,
            new_outcome=new_outcome,
        )

    return FuzzResult(
        examples_tried=state["count"],
        counterexample=counterexample,
        elapsed_seconds=elapsed,
    )
