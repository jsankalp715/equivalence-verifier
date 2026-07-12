"""Phase 1 domain: purchase counts up to 50."""

from hypothesis import strategies as st

strategies = {
    "purchase_count": st.integers(min_value=0, max_value=50),
}
