"""Spike: property-based equivalence test with Hypothesis (claim E-21).

Hypothesis generates random tables (with NULLs and duplicates) and random
coarse grains. For each case, the decomposable metrics re-aggregated from the
finest grain must equal the BSL result. This is the core simulator check.
Run:  pip install "boring-semantic-layer==0.3.19" duckdb pandas pyarrow pyarrow_hotfix hypothesis
      python spike_property_based.py
"""
import boring_semantic_layer as bsl
import ibis
import numpy as np
import pandas as pd
from hypothesis import given, settings, HealthCheck, strategies as st

DIMS = ["a", "b", "c"]
row = st.tuples(st.sampled_from(["x", "y", "z"]), st.sampled_from(["p", "q"]), st.sampled_from(["k", "l", "m"]),
                st.one_of(st.none(), st.floats(min_value=-1e3, max_value=1e3, allow_nan=False)))

@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(rows=st.lists(row, min_size=1, max_size=40),
       grain=st.lists(st.sampled_from(DIMS), unique=True, max_size=2))
def test_reaggregation_equals_bsl(rows, grain):
    df = pd.DataFrame(rows, columns=["a", "b", "c", "v"]).astype({"v": "float64"})
    t = ibis.memtable(df)
    m = (bsl.to_semantic_table(t, name="t")
         .with_dimensions(a=lambda x: x.a, b=lambda x: x.b, c=lambda x: x.c)
         .with_measures(n=lambda x: x.count(), s=lambda x: x.v.sum(), mx=lambda x: x.v.max(),
                        v_sum=lambda x: x.v.sum(), v_cnt=lambda x: x.v.count(),
                        avg_v=lambda x: x.v.mean()))
    # finest grain = what the connector returns when Data Studio asks for all dims
    fine = m.group_by(*DIMS).aggregate("n", "s", "mx", "v_sum", "v_cnt").execute()
    if grain:
        truth = m.group_by(*grain).aggregate("n", "s", "mx", "avg_v").execute().set_index(grain).sort_index()
        g = fine.groupby(grain).agg(n=("n", "sum"), s=("s", lambda x: x.sum(min_count=1)),
                                    mx=("mx", "max"), vs=("v_sum", lambda x: x.sum(min_count=1)),
                                    vc=("v_cnt", "sum")).sort_index()
    else:  # scorecard / summary row
        truth = m.aggregate("n", "s", "mx", "avg_v").execute()
        g = pd.DataFrame({"n": [fine.n.sum()], "s": [fine.s.sum(min_count=1)], "mx": [fine.mx.max()],
                          "vs": [fine.v_sum.sum(min_count=1)], "vc": [fine.v_cnt.sum()]})
    sim_avg = np.where(g.vc.values > 0, g.vs.values / np.maximum(g.vc.values, 1), np.nan)
    for col in ["n", "s", "mx"]:
        assert np.allclose(truth[col].astype(float).values, g[col].astype(float).values, equal_nan=True, atol=1e-6), col
    assert np.allclose(truth["avg_v"].astype(float).values, sim_avg.astype(float), equal_nan=True, atol=1e-6)

if __name__ == "__main__":
    test_reaggregation_equals_bsl()
    print("All spike checks passed (60 generated cases).")
