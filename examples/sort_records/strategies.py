"""Phase 1 domain: small lists with a small key-space so tie collisions happen.

If we let each primary key be any int, ties would be vanishingly rare and
Hypothesis would burn its budget on lists without collisions. Bounded ranges
make the interesting case likely.
"""

from hypothesis import strategies as st

strategies = {
    "records": st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=3),
            st.integers(min_value=0, max_value=9),
        ),
        min_size=0, max_size=6,
    ),
}
