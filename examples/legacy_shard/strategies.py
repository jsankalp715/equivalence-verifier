"""Phase 1 domain: a large realistic user_id range.

The trigger value for the hidden branch is exactly one point in this range;
random sampling is not expected to hit it.
"""

from hypothesis import strategies as st

strategies = {
    "user_id": st.integers(min_value=0, max_value=10_000_000),
}
