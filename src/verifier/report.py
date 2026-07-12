"""Report structure and pretty-printer.

The framing here is deliberate: we never report "proven equivalent". The best
these techniques can honestly say is "no counterexample found under the
following coverage" -- that's evidence, not proof.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .comparator import Outcome
from .symbolic import SymbolicResult

REPORT_SCHEMA_VERSION = 1


@dataclass
class Counterexample:
    inputs: dict[str, Any]
    old_outcome: Outcome
    new_outcome: Outcome


@dataclass
class FuzzReport:
    old_name: str
    new_name: str
    examples_tried: int
    counterexample: Counterexample | None
    strategy_source: str
    elapsed_seconds: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def diverged(self) -> bool:
        return self.counterexample is not None


@dataclass
class CombinedReport:
    fuzz: FuzzReport
    symbolic: SymbolicResult | None  # None when Phase 2 was skipped

    @property
    def any_divergence(self) -> bool:
        return self.fuzz.diverged or (self.symbolic is not None and self.symbolic.diverged)


def _render_fuzz_section(report: FuzzReport) -> list[str]:
    lines = []
    lines.append("-" * 72)
    lines.append("PHASE 1 -- Property-Based Fuzzing (Hypothesis)")
    lines.append("-" * 72)
    lines.append(f"  strategies: {report.strategy_source}")
    lines.append(f"  inputs tried: {report.examples_tried}")
    lines.append(f"  elapsed: {report.elapsed_seconds:.2f}s")

    if report.diverged:
        ce = report.counterexample
        assert ce is not None
        lines.append("  verdict: DIVERGENCE FOUND")
        lines.append("")
        lines.append("  Minimized counterexample:")
        for k, v in ce.inputs.items():
            lines.append(f"    {k} = {v!r}")
        lines.append("")
        lines.append(f"    old {ce.old_outcome.render()}")
        lines.append(f"    new {ce.new_outcome.render()}")
    else:
        lines.append("  verdict: no counterexample found within budget")
    return lines


def _render_symbolic_section(result: SymbolicResult) -> list[str]:
    lines = []
    lines.append("-" * 72)
    lines.append("PHASE 2 -- Symbolic Execution (CrossHair)")
    lines.append("-" * 72)

    if result.exit_status == "not_installed":
        lines.append("  skipped: crosshair-tool not installed")
        for n in result.notes:
            lines.append(f"  note: {n}")
        return lines

    lines.append(f"  status: {result.exit_status}")
    lines.append(f"  elapsed: {result.elapsed_seconds:.2f}s")
    if result.diverged:
        lines.append(f"  verdict: {len(result.divergences)} divergence(s) found")
        lines.append("")
        for i, d in enumerate(result.divergences, 1):
            lines.append(f"  Divergence #{i}:")
            for k, v in d.inputs_repr.items():
                lines.append(f"    {k} = {v}")
            lines.append(f"    old {d.old_behavior}")
            lines.append(f"    new {d.new_behavior}")
            lines.append("")
    else:
        lines.append("  verdict: no counterexample found within budget")

    for n in result.notes:
        lines.append(f"  note: {n}")
    return lines


def _render_honesty_footer(combined: CombinedReport) -> list[str]:
    lines = []
    lines.append("-" * 72)
    lines.append("WHAT THIS REPORT DOES AND DOES NOT SAY")
    lines.append("-" * 72)

    if combined.any_divergence:
        lines.append(
            "  A divergence was found. The counterexample above is a concrete input\n"
            "  on which the two implementations disagree. That is direct evidence\n"
            "  of a behavior difference -- the rewrite is NOT equivalent."
        )
    else:
        parts = ["No divergence was surfaced by"]
        techniques = ["property-based fuzzing"]
        if combined.symbolic is not None and combined.symbolic.exit_status not in ("not_installed",):
            techniques.append("bounded symbolic execution")
        parts.append(" or ".join(techniques) + ".")
        lines.append("  " + " ".join(parts))
        lines.append("")
        lines.append(
            "  This is NOT a proof of equivalence. It means: within the input\n"
            "  domain(s) declared, the example budget for Phase 1, and the time\n"
            "  budget for Phase 2, no disagreement was observed. Bugs on rare\n"
            "  branches outside the explored paths, inputs outside the declared\n"
            "  domain, or behavior depending on non-input state (I/O, time, RNG,\n"
            "  external services) can still exist."
        )
        if combined.symbolic is not None and combined.symbolic.exit_status == "timeout":
            lines.append(
                "\n  NOTE: Phase 2 timed out before finishing exploration. The\n"
                "  'no counterexample' verdict here is weaker than an exhaustive run."
            )
    return lines


def render_report(combined: CombinedReport) -> str:
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("BEHAVIORAL EQUIVALENCE REPORT")
    lines.append("=" * 72)
    lines.append(f"  old: {combined.fuzz.old_name}")
    lines.append(f"  new: {combined.fuzz.new_name}")
    lines.append("")
    lines.extend(_render_fuzz_section(combined.fuzz))
    lines.append("")
    if combined.symbolic is not None:
        lines.extend(_render_symbolic_section(combined.symbolic))
        lines.append("")
    lines.extend(_render_honesty_footer(combined))
    lines.append("=" * 72)
    return "\n".join(lines)


def _outcome_to_dict(o: Outcome) -> dict[str, Any]:
    """Serialize an Outcome for JSON. Values are stringified via repr() so
    consumers don't rely on JSON round-tripping arbitrary Python objects."""
    if o.kind == "value":
        return {"kind": "value", "value_repr": repr(o.value)}
    return {
        "kind": "exception",
        "exc_type": o.exc_type,
        "exc_message": o.exc_message,
    }


def _counterexample_to_dict(ce: Counterexample) -> dict[str, Any]:
    return {
        "inputs_repr": {k: repr(v) for k, v in ce.inputs.items()},
        "old_outcome": _outcome_to_dict(ce.old_outcome),
        "new_outcome": _outcome_to_dict(ce.new_outcome),
    }


def report_to_dict(combined: CombinedReport) -> dict[str, Any]:
    """Convert a CombinedReport into a JSON-serializable dict.

    Contract for CI consumers: this schema is versioned via
    `schema_version`. Bump the constant on any breaking change; additive
    changes (new keys, new optional fields) keep the version.
    """
    fuzz = combined.fuzz
    fuzz_section: dict[str, Any] = {
        "old_name": fuzz.old_name,
        "new_name": fuzz.new_name,
        "strategy_source": fuzz.strategy_source,
        "examples_tried": fuzz.examples_tried,
        "elapsed_seconds": fuzz.elapsed_seconds,
        "diverged": fuzz.diverged,
        "counterexample": (
            _counterexample_to_dict(fuzz.counterexample) if fuzz.counterexample else None
        ),
    }

    sym_section: dict[str, Any] | None = None
    if combined.symbolic is not None:
        s = combined.symbolic
        sym_section = {
            "status": s.exit_status,
            "elapsed_seconds": s.elapsed_seconds,
            "diverged": s.diverged,
            "divergences": [
                {
                    "inputs_repr": d.inputs_repr,
                    "old_behavior": d.old_behavior,
                    "new_behavior": d.new_behavior,
                }
                for d in s.divergences
            ],
            "notes": s.notes,
            "invocation": s.invocation,
        }

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "any_divergence": combined.any_divergence,
        "phase1_fuzz": fuzz_section,
        "phase2_symbolic": sym_section,
    }


def render_report_json(combined: CombinedReport, *, indent: int = 2) -> str:
    return json.dumps(report_to_dict(combined), indent=indent, default=str)
