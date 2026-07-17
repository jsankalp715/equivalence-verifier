# Legacy Code Behavioral-Equivalence Verifier

Given two implementations of the same Python function, find a concrete input
on which they disagree -- or report, honestly, how much was actually checked.

## Why

When teams rewrite legacy code, the usual "proof" the rewrite is safe is: the
existing tests still pass. Existing tests cover known behavior, not unknown
edge cases the original happened to get right. This tool differential-fuzzes
and symbolically explores the pair to hunt for inputs where old and new disagree.

## How it works

Two independent techniques, run in sequence and reported together:

**Phase 1 -- property-based fuzzing.** [Hypothesis][hyp] generates random
inputs matching the function's type signature (or a user-supplied strategy
spec), runs both implementations, and compares outputs. On disagreement it
shrinks the input to the smallest form that still triggers the difference.

**Phase 2 -- symbolic execution.** Shells out to [CrossHair's][ch] `diffbehavior`
command, which uses Z3 under the hood to search execution paths of both
functions and solve for input values that make one path diverge from the
other. Catches boundary/edge-case bugs random fuzzing rarely stumbles into.

Both techniques catching the same bug is a strong signal. Only one catching
it -- particularly when Phase 2 catches something Phase 1 didn't -- is
exactly the value proposition of adding symbolic execution.

[hyp]: https://hypothesis.readthedocs.io/
[ch]: https://crosshair.readthedocs.io/

## Install

```
pip install -e .
pip install crosshair-tool   # Phase 2, optional
```

## Use

```
verify-equivalence examples/discount/old.py:discount_price \
                   examples/discount/new.py:discount_price \
                   --strategies examples/discount/strategies.py \
                   --symbolic-old examples/discount/bounded.py:old_bounded \
                   --symbolic-new examples/discount/bounded.py:new_bounded
```

Options:

| Flag | Purpose |
|---|---|
| `--strategies FILE` | Python file defining a Hypothesis `strategies` dict. Optional if all parameters have type hints. |
| `--max-examples N` | Hypothesis example budget (default 500). |
| `--rel-tol / --abs-tol` | Float comparison tolerance (default: exact). |
| `--seed N` | Derandomize Hypothesis for reproducible runs. |
| `--symbolic-old / --symbolic-new` | Enable Phase 2. Point at domain-bounded wrappers (see `bounded.py` pattern). |
| `--symbolic-timeout` | Per-condition CPU-time budget for crosshair (default 30s). |
| `--symbolic-wall-timeout` | Hard wall-clock kill for the subprocess (default 90s). |
| `--json` | Emit a machine-readable JSON report on stdout (schema versioned) instead of the text report. |

Exit code is 1 if any divergence is found, 0 otherwise -- usable in CI.

The text report shows per-phase elapsed time; the JSON report includes it in
`phase1_fuzz.elapsed_seconds` / `phase2_symbolic.elapsed_seconds`. The JSON
schema is versioned via `schema_version` at the top level -- additive changes
(new keys) keep the version, breaking changes bump it.

## The `bounded.py` pattern (Phase 2 domain guard)

CrossHair explores the *unconstrained* input domain by default -- so vanilla
crosshair on the discount example will happily surface counterexamples at
`price=-inf` or `NaN`, which aren't inputs your code will ever see in
production. `strategies.py` solves this for Phase 1; for Phase 2 we use a
domain-guarded wrapper:

```python
# examples/discount/bounded.py
from crosshair import IgnoreAttempt
from . import old, new

def old_bounded(price, discount_pct, loyalty_multiplier):
    if not _in_domain(price, discount_pct, loyalty_multiplier):
        raise IgnoreAttempt  # crosshair discards this path silently
    return old.discount_price(price, discount_pct, loyalty_multiplier)

# ...identical wrapper for new_bounded
```

CrossHair's `diffbehavior` command does **not** honor PEP316 docstring
preconditions (verified against 0.0.108: `run_iteration` never consults
the condition parser); `IgnoreAttempt` is the mechanism it does honor.
Both wrappers rejecting the same out-of-domain inputs means the engine
sees "equivalent behavior" there and moves on.

## Honesty in reporting

Phases 1 and 2 can find bugs but cannot prove their absence. The report
never says "equivalent". When both phases come up clean it says:

> No divergence was surfaced by property-based fuzzing or bounded symbolic
> execution. This is NOT a proof of equivalence. It means: within the input
> domain(s) declared, the example budget for Phase 1, and the time budget
> for Phase 2, no disagreement was observed.

And when Phase 2 hits the wall-clock timeout, the report calls that out
explicitly -- the negative verdict is weaker in that case than after a
clean run.

We do NOT report "N of M paths explored" -- CrossHair's CLI doesn't expose
that count, and inventing a fake one would be exactly the overclaiming this
project is trying to avoid.

## What this can't catch

- External state: files, network, environment variables, time, RNG without
  a fixed seed
- Inputs outside the declared domain (Phase 1's strategies or Phase 2's
  bounded wrapper)
- Extremely rare code paths that neither fuzzing nor symbolic exploration
  reach within budget
- Non-deterministic implementations (concurrency, GC-order dependence)

## Live demo

Walk through the whole set with one command:

```
python scripts/run_demo.py           # all 5 cases, ~1 min end-to-end
python scripts/run_demo.py --quick   # just the headline case, ~5 sec
```

Each case prints its full report, then a summary table lands at the bottom
showing which phase caught which bug and how long each took.

## Demo results -- five seeded bug pairs

Each example directory has `old.py`, `new.py`, `strategies.py`, `bounded.py`,
and an `__init__.py`. Run the tool against each pair and record which phase
caught which bug -- the headline finding of the project.

| # | Case | Bug class | Phase 1 (Hypothesis) | Phase 2 (CrossHair) |
|---|---|---|---|---|
| 1 | `discount` | FP rounding | found after 34 inputs: `price=1.546875, discount=0, loyalty=1.0` -> old `1.55`, new `1.54` | found: `price=0.4975, discount=0, loyalty=0.5` -> old `0.25`, new `0.24` |
| 2 | `discount_tier` | Off-by-one at loyalty boundary | found after 20 inputs: `purchase_count=10` -> old `'gold'`, new `'silver'` | found: `purchase_count=10` |
| 3 | `http_class` | Rare-branch elif (dropped teapot case) | found after 62 inputs: `code=418` -> old `'teapot'`, new `'client_error'` | found: `code=418` |
| 4 | `sort_records` | Lost tiebreak in `sorted(key=...)` rewrite | found after 45 inputs: `[(0,1), (0,0)]` -> stability inverted | found: `[(0,1),(0,1),(0,1),(0,0)]` |
| 5 | `legacy_shard` | Hash-mix carve-out (dropped `user_id >= 1M and _mix(x)==12345` branch) | **not found after 2000 inputs (~0.3s)** | found in `~0.4s`: `user_id=1048990` -> old `99`, new `14` |

### Where each phase shines

Cases 1-4 are all caught by Hypothesis alone. That may surprise -- even the
seemingly-rare "HTTP 418 teapot" branch is found in 62 tries because Hypothesis
6+ uses bytecode branch-coverage feedback: when it sees an unexplored branch it
biases mutations toward taking it. Shrinking then delivers a minimal, readable
counterexample.

**Case 5 is where symbolic execution earns its place.** The rewritten
`shard_for` looks safe -- the removed branch fires only when
`user_id >= 1_000_000 and (user_id * 31 + 7) % 65537 == 12345`. Random
testing cannot invert modular arithmetic; you would need to both pick a
seven-digit user_id (Hypothesis's size-biased integer distribution favors
small values) and hit the right one-in-65537 modular residue. Hypothesis
has no way to bias toward the combination because coverage feedback can
only observe that the branch *hasn't* been taken, not compute what would
take it. CrossHair hands the composite guard to Z3, which returns
`user_id = 1_048_990` immediately -- the smallest solution to the
combined system.

This is the archetypal "legacy hack" the tool is designed to catch: an
undocumented rewrite-time deletion that survives every existing test
because no existing test knows the magic value.

### Rerun any case

```
verify-equivalence examples/legacy_shard/old.py:shard_for \
                   examples/legacy_shard/new.py:shard_for \
                   --strategies examples/legacy_shard/strategies.py \
                   --symbolic-old examples/legacy_shard/bounded.py:old_bounded \
                   --symbolic-new examples/legacy_shard/bounded.py:new_bounded
```

## Layout

```
src/verifier/
  loader.py       Parse path:func spec, import, check signatures match
  strategies.py   Infer Hypothesis strategies from type hints; load spec file
  comparator.py   exact / float-tolerance; treats exceptions as first-class
  fuzzer.py       Phase 1 -- differential fuzz engine with shrinking
  symbolic.py     Phase 2 -- crosshair subprocess wrapper & output parser
  report.py       Combined report with honest confidence framing
  cli.py          Click CLI entry point

examples/
  discount/       FP rounding bug: round vs truncate
  discount_tier/  Off-by-one at a loyalty tier boundary
  http_class/     Rare-branch bug: dropped HTTP 418 teapot case
  sort_records/   Sort-stability bug: lost tiebreak rule
  legacy_shard/   Hash-mix carve-out (Phase 1 misses; Phase 2 catches)

Each example directory contains:
  old.py          Reference "legacy" implementation
  new.py          Rewrite with a seeded bug
  strategies.py   Phase 1 domain spec (Hypothesis)
  bounded.py      Phase 2 domain guards (IgnoreAttempt wrappers)

tests/
  test_fuzzer.py    Phase 1 engine smoke tests
  test_symbolic.py  Phase 2 parser + E2E (E2E opt-in via RUN_CROSSHAIR_E2E=1)
```
