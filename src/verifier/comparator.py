"""Compare two implementations' outputs -- values or raised exceptions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Outcome:
    """The result of calling an implementation once.

    Either `kind == "value"` (with `value` populated) or `kind == "exception"`
    (with `exc_type` and `exc_message`). Behavioural equivalence must account
    for both -- a rewrite that swallows an exception is a real behavior change.
    """
    kind: str  # "value" | "exception"
    value: Any = None
    exc_type: str | None = None
    exc_message: str | None = None

    def render(self) -> str:
        if self.kind == "value":
            return f"returned {self.value!r}"
        return f"raised {self.exc_type}({self.exc_message!r})"


def run_once(fn: Callable, kwargs: dict[str, Any]) -> Outcome:
    """Call `fn(**kwargs)` and wrap the result or exception in an Outcome."""
    try:
        return Outcome(kind="value", value=fn(**kwargs))
    except Exception as e:
        return Outcome(kind="exception", exc_type=type(e).__name__, exc_message=str(e))


Comparator = Callable[[Outcome, Outcome], bool]
"""(old_outcome, new_outcome) -> True if considered equivalent."""


def exact_equality(old: Outcome, new: Outcome) -> bool:
    """Both must be values that == each other, OR both same exception type.

    Exception messages are ignored -- a rename or wording change shouldn't
    trip the verifier, but a change in exception TYPE is a real behavior change.
    """
    if old.kind != new.kind:
        return False
    if old.kind == "exception":
        return old.exc_type == new.exc_type
    # value comparison
    try:
        return bool(old.value == new.value)
    except Exception:
        return False


def float_tolerance(rel_tol: float, abs_tol: float) -> Comparator:
    """Comparator that tolerates small float differences.

    Falls back to exact_equality for non-float values and for exceptions.
    NaN == NaN is treated as True (both diverged the same way).
    """
    def cmp(old: Outcome, new: Outcome) -> bool:
        if old.kind != new.kind:
            return False
        if old.kind == "exception":
            return old.exc_type == new.exc_type
        a, b = old.value, new.value
        if isinstance(a, float) and isinstance(b, float):
            if math.isnan(a) and math.isnan(b):
                return True
            return math.isclose(a, b, rel_tol=rel_tol, abs_tol=abs_tol)
        return exact_equality(old, new)
    return cmp
