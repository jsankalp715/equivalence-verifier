"""Tests for report rendering (text + JSON) and elapsed-time capture."""

from __future__ import annotations

import json

from hypothesis import strategies as st

from verifier.comparator import Outcome
from verifier.fuzzer import run_differential_fuzz
from verifier.report import (
    REPORT_SCHEMA_VERSION,
    CombinedReport,
    Counterexample,
    FuzzReport,
    render_report_json,
    report_to_dict,
)
from verifier.symbolic import SymbolicDivergence, SymbolicResult


def test_fuzz_result_captures_elapsed_seconds():
    def f(x: int) -> int:
        return x

    result = run_differential_fuzz(
        old_impl=f,
        new_impl=f,
        strategies={"x": st.integers(min_value=0, max_value=10)},
        max_examples=20,
    )
    assert result.elapsed_seconds > 0.0


def _build_no_divergence_report() -> CombinedReport:
    return CombinedReport(
        fuzz=FuzzReport(
            old_name="a.py:f",
            new_name="b.py:f",
            examples_tried=100,
            counterexample=None,
            strategy_source="type-hint inference",
            elapsed_seconds=0.12,
        ),
        symbolic=SymbolicResult(
            divergences=[],
            exit_status="completed",
            elapsed_seconds=3.4,
        ),
    )


def _build_divergence_report() -> CombinedReport:
    return CombinedReport(
        fuzz=FuzzReport(
            old_name="a.py:f",
            new_name="b.py:f",
            examples_tried=10,
            counterexample=Counterexample(
                inputs={"x": 42, "xs": [1, 2, 3]},
                old_outcome=Outcome(kind="value", value=99),
                new_outcome=Outcome(kind="exception", exc_type="ValueError", exc_message="bad"),
            ),
            strategy_source="spec file: strategies.py",
            elapsed_seconds=0.05,
        ),
        symbolic=SymbolicResult(
            divergences=[
                SymbolicDivergence(
                    inputs_repr={"x": "1048990"},
                    old_behavior="returns 99",
                    new_behavior="returns 14",
                )
            ],
            exit_status="completed",
            elapsed_seconds=12.7,
            notes=["some note"],
        ),
    )


class TestReportToDict:
    def test_schema_version_present(self):
        d = report_to_dict(_build_no_divergence_report())
        assert d["schema_version"] == REPORT_SCHEMA_VERSION

    def test_no_divergence_shape(self):
        d = report_to_dict(_build_no_divergence_report())
        assert d["any_divergence"] is False
        assert d["phase1_fuzz"]["diverged"] is False
        assert d["phase1_fuzz"]["counterexample"] is None
        assert d["phase1_fuzz"]["elapsed_seconds"] == 0.12
        assert d["phase2_symbolic"]["diverged"] is False
        assert d["phase2_symbolic"]["divergences"] == []
        assert d["phase2_symbolic"]["elapsed_seconds"] == 3.4

    def test_divergence_shape(self):
        d = report_to_dict(_build_divergence_report())
        assert d["any_divergence"] is True
        p1 = d["phase1_fuzz"]
        assert p1["diverged"] is True
        # Counterexample inputs are stringified via repr.
        assert p1["counterexample"]["inputs_repr"] == {"x": "42", "xs": "[1, 2, 3]"}
        assert p1["counterexample"]["old_outcome"] == {"kind": "value", "value_repr": "99"}
        assert p1["counterexample"]["new_outcome"] == {
            "kind": "exception", "exc_type": "ValueError", "exc_message": "bad",
        }

        p2 = d["phase2_symbolic"]
        assert p2["diverged"] is True
        assert len(p2["divergences"]) == 1
        assert p2["divergences"][0]["inputs_repr"] == {"x": "1048990"}
        assert p2["divergences"][0]["old_behavior"] == "returns 99"

    def test_phase2_omitted_when_not_run(self):
        r = _build_no_divergence_report()
        r.symbolic = None
        d = report_to_dict(r)
        assert d["phase2_symbolic"] is None


class TestJsonSerializesCleanly:
    def test_no_divergence(self):
        s = render_report_json(_build_no_divergence_report())
        parsed = json.loads(s)  # must round-trip
        assert parsed["any_divergence"] is False

    def test_with_divergence(self):
        s = render_report_json(_build_divergence_report())
        parsed = json.loads(s)
        assert parsed["any_divergence"] is True
        assert parsed["phase2_symbolic"]["elapsed_seconds"] == 12.7
