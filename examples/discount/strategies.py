"""Strategies for the discount example.

Constrains inputs to realistic money-shaped values so that counterexamples
Hypothesis surfaces are intelligible (not 1e-308 float weirdness).
"""

from hypothesis import strategies as st

strategies = {
    "price": st.floats(
        min_value=0.01, max_value=10_000.0,
        allow_nan=False, allow_infinity=False,
    ),
    "discount_pct": st.floats(
        min_value=0.0, max_value=100.0,
        allow_nan=False, allow_infinity=False,
    ),
    "loyalty_multiplier": st.floats(
        min_value=0.5, max_value=1.5,
        allow_nan=False, allow_infinity=False,
    ),
}
