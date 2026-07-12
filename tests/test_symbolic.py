"""Tests for the Phase 2 subprocess/parser layer.

We test the output parser directly (fast, deterministic) and gate the
end-to-end crosshair invocation behind an env var to keep CI fast.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from verifier.symbolic import (
    SymbolicDivergence,
    _parse_crosshair_output,
    _parse_kwargs_repr,
    _to_dotted_module,
    run_symbolic_diff,
)


class TestKwargsParser:
    def test_simple(self):
        assert _parse_kwargs_repr("a=1, b=2") == {"a": "1", "b": "2"}

    def test_reprs_with_commas(self):
        # Lists/tuples/dicts in args must not be split at their internal commas.
        assert _parse_kwargs_repr("xs=[1, 2, 3], y=4") == {"xs": "[1, 2, 3]", "y": "4"}

    def test_nested(self):
        assert _parse_kwargs_repr("d={'a': [1, 2]}, n=7") == {
            "d": "{'a': [1, 2]}",
            "n": "7",
        }

    def test_float_repr(self):
        assert _parse_kwargs_repr("price=1.546875, discount_pct=0.0") == {
            "price": "1.546875",
            "discount_pct": "0.0",
        }


class TestCrosshairOutputParser:
    def test_single_divergence(self):
        stdout = (
            "Given: (price=0.4975, discount_pct=0.0, loyalty_multiplier=0.5),\n"
            "  examples.discount.bounded.old_bounded : returns 0.25\n"
            "  examples.discount.bounded.new_bounded : returns 0.24\n"
        )
        divs = _parse_crosshair_output(stdout)
        assert len(divs) == 1
        d = divs[0]
        assert d.inputs_repr == {
            "price": "0.4975",
            "discount_pct": "0.0",
            "loyalty_multiplier": "0.5",
        }
        assert "returns 0.25" in d.old_behavior
        assert "returns 0.24" in d.new_behavior

    def test_multiple_divergences(self):
        stdout = (
            "Given: (x=1),\n"
            "  m.a : returns 1\n"
            "  m.b : returns 2\n"
            "Given: (x=3),\n"
            "  m.a : returns 3\n"
            "  m.b : raises ValueError('bad')\n"
        )
        divs = _parse_crosshair_output(stdout)
        assert len(divs) == 2
        assert divs[1].inputs_repr == {"x": "3"}
        assert "raises" in divs[1].new_behavior

    def test_no_divergence_output(self):
        # Empty or purely-noise output returns no divergences.
        assert _parse_crosshair_output("") == []
        assert _parse_crosshair_output("some debug line\n") == []


class TestToDottedModule:
    def test_walks_up_through_init(self, tmp_path: Path):
        # Set up  root/pkg/sub/mod.py with __init__.py at each level.
        root = tmp_path
        (root / "pkg").mkdir()
        (root / "pkg" / "__init__.py").write_text("")
        (root / "pkg" / "sub").mkdir()
        (root / "pkg" / "sub" / "__init__.py").write_text("")
        modfile = root / "pkg" / "sub" / "mod.py"
        modfile.write_text("")

        dotted, sys_root = _to_dotted_module(modfile)
        assert dotted == "pkg.sub.mod"
        assert sys_root == root

    def test_bare_module_no_init(self, tmp_path: Path):
        modfile = tmp_path / "loose.py"
        modfile.write_text("")
        dotted, sys_root = _to_dotted_module(modfile)
        assert dotted == "loose"
        assert sys_root == tmp_path


@pytest.mark.skipif(
    os.environ.get("RUN_CROSSHAIR_E2E") != "1",
    reason="Set RUN_CROSSHAIR_E2E=1 to run the end-to-end crosshair test (slow).",
)
def test_e2e_finds_discount_bug():
    """End-to-end: crosshair should find the discount rounding divergence."""
    repo_root = Path(__file__).resolve().parents[1]
    old_p = repo_root / "examples" / "discount" / "bounded.py"
    new_p = repo_root / "examples" / "discount" / "bounded.py"
    result = run_symbolic_diff(
        old_path=old_p, old_func="old_bounded",
        new_path=new_p, new_func="new_bounded",
        per_condition_timeout=15.0,
        wall_timeout=60.0,
    )
    assert result.exit_status in ("completed", "timeout")
    assert result.diverged, f"expected a divergence; stderr: {result.stderr_tail}"
