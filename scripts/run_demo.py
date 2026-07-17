"""Walk through the demo cases in sequence.

Run from repo root:

    python scripts/run_demo.py           # all 5 cases (~1 min end-to-end)
    python scripts/run_demo.py --quick   # only legacy_shard (the headline case)

Prints each case's full text report, then a summary table matching the
README's headline result. Uses --json under the hood to capture the
verdicts programmatically for the summary.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Case:
    dir: str
    func: str
    label: str
    bug_class: str


CASES: list[Case] = [
    Case("discount",      "discount_price", "discount",      "FP rounding"),
    Case("discount_tier", "tier_for_count", "discount_tier", "Off-by-one at loyalty boundary"),
    Case("http_class",    "http_class",     "http_class",    "Rare-branch elif (dropped teapot)"),
    Case("sort_records",  "sort_records",   "sort_records",  "Sort-stability tiebreak lost"),
    Case("legacy_shard",  "shard_for",      "legacy_shard",  "Hash-mix carve-out"),
]


def run_case(case: Case, *, json_only: bool) -> dict:
    """Invoke the CLI on one case. Returns the parsed JSON report.

    When json_only is False, we run twice: once for the text report (shown
    live to the viewer) and once for JSON (parsed for the summary table).
    That double-run keeps the demo output honest -- what the viewer sees
    IS what the verifier reports.
    """
    ex = REPO_ROOT / "examples" / case.dir
    args = [
        sys.executable, "-m", "verifier.cli",
        f"{ex / 'old.py'}:{case.func}",
        f"{ex / 'new.py'}:{case.func}",
        "--strategies", str(ex / "strategies.py"),
        "--symbolic-old", f"{ex / 'bounded.py'}:old_bounded",
        "--symbolic-new", f"{ex / 'bounded.py'}:new_bounded",
        "--symbolic-timeout", "20",
        "--symbolic-wall-timeout", "90",
        "--max-examples", "500" if case.dir != "legacy_shard" else "2000",
        "--seed", "1",
    ]
    if not json_only:
        subprocess.run(args, cwd=REPO_ROOT, check=False)
    proc = subprocess.run(
        args + ["--json"],
        capture_output=True, text=True, cwd=REPO_ROOT, check=False,
    )
    return json.loads(proc.stdout)


def print_banner(title: str) -> None:
    bar = "#" * 72
    # flush=True so banners land in transcript order when stdout is a pipe
    # (subprocess.run inherits fd 1 and writes unbuffered, our print is
    # block-buffered on a pipe -- without flush the banners bunch at the end).
    print(f"\n{bar}\n# {title}\n{bar}\n", flush=True)


def _verdict(section: dict | None) -> str:
    if section is None:
        return "skipped"
    if section.get("diverged"):
        return "found"
    return "not found"


def summarize(results: list[tuple[Case, dict]]) -> None:
    print("\n" + "=" * 100)
    print("DEMO SUMMARY")
    print("=" * 100)
    header = f"{'Case':<16} {'Bug class':<38} {'P1':<12} {'P1 time':<10} {'P2':<12} {'P2 time':<10}"
    print(header)
    print("-" * len(header))
    for case, report in results:
        p1 = report["phase1_fuzz"]
        p2 = report["phase2_symbolic"]
        p1_verdict = _verdict(p1)
        p2_verdict = _verdict(p2)
        p1_time = f"{p1['elapsed_seconds']:.2f}s"
        p2_time = f"{p2['elapsed_seconds']:.2f}s" if p2 else "-"
        print(
            f"{case.label:<16} {case.bug_class:<38} "
            f"{p1_verdict:<12} {p1_time:<10} {p2_verdict:<12} {p2_time:<10}"
        )
    print("=" * 100)
    print(
        "\nHeadline: cases 1-4 are caught by property-based fuzzing (Hypothesis's\n"
        "bytecode branch-coverage feedback is powerful). Case 5 -- the hash-mix\n"
        "carve-out -- is where symbolic execution earns its place: Z3 inverts the\n"
        "modular guard in one iteration; random testing effectively cannot.\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quick", action="store_true",
        help="Run only the headline case (legacy_shard) for a fast demo.",
    )
    args = parser.parse_args()

    cases = [c for c in CASES if c.dir == "legacy_shard"] if args.quick else CASES

    results: list[tuple[Case, dict]] = []
    for case in cases:
        print_banner(f"CASE: {case.label}  --  {case.bug_class}")
        report = run_case(case, json_only=False)
        results.append((case, report))
    summarize(results)


if __name__ == "__main__":
    main()
