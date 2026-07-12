"""CLI: verify-equivalence old.py:func new.py:func [options]."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from .comparator import exact_equality, float_tolerance
from .fuzzer import run_differential_fuzz
from .loader import check_signatures_compatible, load_function, parse_spec
from .report import CombinedReport, FuzzReport, render_report, render_report_json
from .strategies import resolve_strategies
from .symbolic import run_symbolic_diff


@click.command(
    help=(
        "Find inputs where OLD_SPEC and NEW_SPEC behave differently.\n\n"
        "Each SPEC is `path/to/file.py:function_name`.\n\n"
        "Runs Phase 1 (property-based fuzzing) always, and Phase 2 (symbolic\n"
        "execution via CrossHair) if --symbolic-old / --symbolic-new are given."
    )
)
@click.argument("old_spec")
@click.argument("new_spec")
@click.option(
    "--strategies", "strategies_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Python file defining a Hypothesis `strategies` dict.",
)
@click.option(
    "--max-examples", type=int, default=500, show_default=True,
    help="Hypothesis example budget (excluding shrink attempts).",
)
@click.option(
    "--rel-tol", type=float, default=0.0, show_default=True,
    help="Relative tolerance for float comparison (0 = exact).",
)
@click.option(
    "--abs-tol", type=float, default=0.0, show_default=True,
    help="Absolute tolerance for float comparison (0 = exact).",
)
@click.option(
    "--seed", type=int, default=None,
    help="Derandomize Hypothesis with this seed for reproducible runs.",
)
@click.option(
    "--symbolic-old", "symbolic_old", default=None,
    help="Domain-bounded wrapper for Phase 2, form path/to/file.py:func_name. "
         "See examples/discount/bounded.py for the pattern.",
)
@click.option(
    "--symbolic-new", "symbolic_new", default=None,
    help="Domain-bounded wrapper for Phase 2 (the new impl's wrapper).",
)
@click.option(
    "--symbolic-timeout", type=float, default=30.0, show_default=True,
    help="Per-condition timeout for crosshair (seconds of CPU time).",
)
@click.option(
    "--symbolic-wall-timeout", type=float, default=90.0, show_default=True,
    help="Hard wall-clock timeout for the crosshair subprocess.",
)
@click.option(
    "--json", "json_output", is_flag=True, default=False,
    help="Emit a machine-readable JSON report on stdout instead of the text report.",
)
def main(
    old_spec: str,
    new_spec: str,
    strategies_file: Path | None,
    max_examples: int,
    rel_tol: float,
    abs_tol: float,
    seed: int | None,
    symbolic_old: str | None,
    symbolic_new: str | None,
    symbolic_timeout: float,
    symbolic_wall_timeout: float,
    json_output: bool,
) -> None:
    # --- load & signature check --------------------------------------------
    try:
        old = load_function(old_spec)
        new = load_function(new_spec)
        check_signatures_compatible(old, new)
    except (ValueError, FileNotFoundError, AttributeError, ImportError, TypeError) as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(2)

    # --- Phase 1: fuzzing ---------------------------------------------------
    try:
        strategy_dict = resolve_strategies(old.signature, strategies_file)
    except Exception as e:
        click.echo(f"error resolving strategies: {e}", err=True)
        sys.exit(2)

    comparator = exact_equality
    if rel_tol > 0 or abs_tol > 0:
        comparator = float_tolerance(rel_tol=rel_tol, abs_tol=abs_tol)

    fuzz_result = run_differential_fuzz(
        old_impl=old.func,
        new_impl=new.func,
        strategies=strategy_dict,
        max_examples=max_examples,
        comparator=comparator,
        seed=seed,
    )
    fuzz_report = FuzzReport(
        old_name=old.qualified_name,
        new_name=new.qualified_name,
        examples_tried=fuzz_result.examples_tried,
        counterexample=fuzz_result.counterexample,
        strategy_source=(
            f"spec file: {strategies_file}" if strategies_file
            else "type-hint inference"
        ),
        elapsed_seconds=fuzz_result.elapsed_seconds,
    )

    # --- Phase 2: symbolic (optional) ---------------------------------------
    symbolic_result = None
    if symbolic_old or symbolic_new:
        if not (symbolic_old and symbolic_new):
            click.echo(
                "error: --symbolic-old and --symbolic-new must be given together.",
                err=True,
            )
            sys.exit(2)
        try:
            sym_old_path, sym_old_fn = parse_spec(symbolic_old)
            sym_new_path, sym_new_fn = parse_spec(symbolic_new)
        except (ValueError, FileNotFoundError) as e:
            click.echo(f"error parsing symbolic target: {e}", err=True)
            sys.exit(2)

        symbolic_result = run_symbolic_diff(
            old_path=sym_old_path,
            old_func=sym_old_fn,
            new_path=sym_new_path,
            new_func=sym_new_fn,
            per_condition_timeout=symbolic_timeout,
            wall_timeout=symbolic_wall_timeout,
        )

    combined = CombinedReport(fuzz=fuzz_report, symbolic=symbolic_result)
    if json_output:
        click.echo(render_report_json(combined))
    else:
        click.echo(render_report(combined))
    sys.exit(1 if combined.any_divergence else 0)


if __name__ == "__main__":
    main()
