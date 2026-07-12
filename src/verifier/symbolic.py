"""Phase 2: symbolic execution via CrossHair.

Shells out to `python -m crosshair diffbehavior`, parses its structured
output, and returns a `SymbolicResult`. Subprocess (not programmatic) because
CrossHair's internal APIs are unstable across versions and the CLI is the
supported contract; also gives us a hard wall-clock kill switch.

Path-coverage honesty: CrossHair does not expose an exact count of paths
explored via its CLI. What we CAN report is (a) whether the search
exhausted the code paths (crosshair prints an "exhaustion" debug line
only in verbose mode) or ran out of budget, and (b) how many distinct
divergences it surfaced. The tool always tells the user which of those
happened -- we never say "N of M paths explored" unless we can back it up.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SymbolicDivergence:
    """One counterexample surfaced by CrossHair.

    We keep the raw string forms as CrossHair reports them -- attempting to
    re-eval the reprs into Python objects would introduce another surface
    for bugs and is unnecessary for the report.
    """
    inputs_repr: dict[str, str]
    old_behavior: str  # e.g. "returns 0.25" or "raises ValueError(...)"
    new_behavior: str


@dataclass
class SymbolicResult:
    divergences: list[SymbolicDivergence]
    exit_status: str  # "completed" | "timeout" | "crosshair_error" | "not_installed"
    elapsed_seconds: float = 0.0
    stderr_tail: str = ""
    invocation: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def diverged(self) -> bool:
        return len(self.divergences) > 0


class SymbolicSetupError(Exception):
    """Raised for pre-flight problems (crosshair missing, bad path, etc.)."""


def _to_dotted_module(path: Path) -> tuple[str, Path]:
    """Convert file path to a `pkg.sub.mod` dotted name + PYTHONPATH root.

    Walks upward while `__init__.py` exists; the first ancestor WITHOUT one
    is the root that must be on `sys.path` for the dotted name to resolve.
    """
    path = path.resolve()
    if path.suffix != ".py":
        raise SymbolicSetupError(f"Not a .py file: {path}")

    parts: list[str] = [path.stem]
    parent = path.parent
    while (parent / "__init__.py").exists():
        parts.append(parent.name)
        parent = parent.parent
    dotted = ".".join(reversed(parts))
    return dotted, parent


def _parse_crosshair_output(stdout: str) -> list[SymbolicDivergence]:
    """Parse crosshair diffbehavior's textual output into divergences.

    Format per divergence (from crosshair.diff_behavior.diff_summary):

        Given: (name1=repr1, name2=repr2, ...),
          <fully.qualified.fn1> : returns <repr> | raises <exc>
          <fully.qualified.fn2> : returns <repr> | raises <exc>
    """
    divergences: list[SymbolicDivergence] = []
    # Non-greedy match; stops at next "Given:" or EOF.
    pattern = re.compile(
        r"Given:\s*\((?P<args>.*?)\),\s*\n"
        r"\s+\S+\s*:\s*(?P<b1>[^\n]+)\n"
        r"\s+\S+\s*:\s*(?P<b2>[^\n]+)",
        re.DOTALL,
    )
    for m in pattern.finditer(stdout):
        args_str = m.group("args")
        inputs_repr = _parse_kwargs_repr(args_str)
        divergences.append(SymbolicDivergence(
            inputs_repr=inputs_repr,
            old_behavior=m.group("b1").strip(),
            new_behavior=m.group("b2").strip(),
        ))
    return divergences


def _parse_kwargs_repr(args_str: str) -> dict[str, str]:
    """Turn `name1=repr1, name2=repr2` into a dict.

    Not a full Python parser -- argument reprs can contain commas
    (e.g. `[1, 2]`). Walk char-by-char tracking bracket depth to split.
    """
    result: dict[str, str] = {}
    depth = 0
    key_end = -1
    start = 0
    i = 0
    key: str | None = None
    while i < len(args_str):
        c = args_str[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif depth == 0:
            if c == "=" and key is None:
                key = args_str[start:i].strip()
                start = i + 1
            elif c == "," and key is not None:
                result[key] = args_str[start:i].strip()
                key = None
                start = i + 1
        i += 1
    if key is not None:
        result[key] = args_str[start:].strip()
    return result


def run_symbolic_diff(
    old_path: Path,
    old_func: str,
    new_path: Path,
    new_func: str,
    *,
    per_condition_timeout: float = 15.0,
    wall_timeout: float = 60.0,
    max_uninteresting_iterations: int | None = None,
    exception_equivalence: str = "SAME_TYPE",
) -> SymbolicResult:
    """Run `crosshair diffbehavior` on the two targets and return structured result.

    Both targets must be importable -- i.e. their containing directories
    (walking up to the first non-package) must be on `sys.path`. This function
    sets `PYTHONPATH` to the appropriate roots so the user doesn't have to.
    """
    if not shutil.which("crosshair") and not _crosshair_module_available():
        return SymbolicResult(
            divergences=[],
            exit_status="not_installed",
            notes=["crosshair-tool is not installed. `pip install crosshair-tool`."],
        )

    old_dotted, old_root = _to_dotted_module(old_path)
    new_dotted, new_root = _to_dotted_module(new_path)

    old_qualified = f"{old_dotted}.{old_func}"
    new_qualified = f"{new_dotted}.{new_func}"

    env = os.environ.copy()
    roots = os.pathsep.join(sorted({str(old_root), str(new_root)}))
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = roots + (os.pathsep + existing if existing else "")

    cmd: list[str] = [
        sys.executable, "-m", "crosshair", "diffbehavior",
        old_qualified, new_qualified,
        f"--per_condition_timeout={per_condition_timeout}",
        f"--exception_equivalence={exception_equivalence}",
    ]
    if max_uninteresting_iterations is not None:
        cmd.append(f"--max_uninteresting_iterations={max_uninteresting_iterations}")

    invocation = " ".join(cmd)
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=wall_timeout,
        )
    except subprocess.TimeoutExpired as e:
        elapsed = time.perf_counter() - start
        # Wall-clock kill. Anything already printed to stdout is still useful.
        partial = (e.stdout or "").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        divergences = _parse_crosshair_output(partial)
        return SymbolicResult(
            divergences=divergences,
            exit_status="timeout",
            elapsed_seconds=elapsed,
            invocation=invocation,
            notes=[
                f"crosshair killed after {wall_timeout}s wall clock. "
                f"Any divergences above are still valid; absence of more "
                f"divergences below is NOT evidence they don't exist."
            ],
        )
    elapsed = time.perf_counter() - start

    divergences = _parse_crosshair_output(proc.stdout)
    status = "completed"
    notes: list[str] = []
    if proc.returncode != 0:
        # crosshair exits nonzero when it FINDS a divergence -- that's success
        # for us. Only treat other returncodes as errors.
        if not divergences:
            status = "crosshair_error"
            notes.append(f"crosshair exited {proc.returncode} without finding divergences.")

    return SymbolicResult(
        divergences=divergences,
        exit_status=status,
        elapsed_seconds=elapsed,
        stderr_tail=proc.stderr[-500:] if proc.stderr else "",
        invocation=invocation,
        notes=notes,
    )


def _crosshair_module_available() -> bool:
    try:
        import crosshair  # noqa: F401
        return True
    except ImportError:
        return False
