"""Phase 1 domain: valid HTTP status code range."""

from hypothesis import strategies as st

strategies = {
    "code": st.integers(min_value=100, max_value=599),
}
