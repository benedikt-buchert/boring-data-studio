"""Spike: evidence for docs/research.md (claims E-01 to E-06).

Run:  pip install "boring-semantic-layer==0.3.19" duckdb pandas pyarrow pyarrow_hotfix
      python spike_bsl_data_studio.py
Every check is an assert. The script exits non-zero if a claim fails.
"""
from pathlib import Path

import boring_semantic_layer as bsl
import ibis
import numpy as np
import pandas as pd
from ibis.expr import operations as ops

HERE = Path(__file__).parent

t = ibis.memtable({
    "origin": ["JFK", "LAX", "JFK", "ORD", "LAX", "JFK"],
    "carrier": ["AA", "UA", "AA", "UA", "AA", "DL"],
    "dep_date": ["2026-01-01", "2026-01-01", "2026-01-02", "2026-01-02", "2026-01-03", "2026-01-03"],
    "distance": [100.0, 200.0, None, 400.0, 500.0, 600.0],  # one NULL on purpose
    "delay": [1, 2, 3, 4, 5, 6],
})
t = t.mutate(dep_date=t.dep_date.cast("date"))
m = bsl.from_yaml(str(HERE / "flights.yml"), tables={"flights_tbl": t})["flights"]

# E-01: descriptions and free-form metadata survive YAML loading.
dims, meas, calcs = m.get_dimensions(), m.get_measures(), m.get_calculated_measures()
assert dims["origin"].description == "Origin airport code"
assert dims["origin"].metadata == {"looker_studio": {"group": "Route"}}
assert meas["total_distance"].metadata == {"looker_studio": {"semantic_type": "NUMBER"}}
assert dims["dep_date"].is_time_dimension and dims["dep_date"].smallest_time_grain == "TIME_GRAIN_DAY"

# E-02: base measures resolve to inspectable Ibis reduction ops.
def resolve(expr, table):
    # Measure.expr is a Deferred or a callable, depending on how it was built.
    return expr.resolve(table) if hasattr(expr, "resolve") else expr(table)

op_of = {k: type(resolve(v.expr, t).op()).__name__ for k, v in meas.items()}
assert op_of == {"flight_count": "CountStar", "total_distance": "Sum", "avg_distance": "Mean",
                 "max_delay": "Max", "unique_carriers": "CountDistinct", "median_delay": "Median"}, op_of

# E-03: calculated measures can be classified with a recording scope.
vt = ibis.table({k: "float64" for k in [*meas, *calcs]}, name="agg")
SAFE = (ops.Field, ops.Add, ops.Subtract, ops.Multiply, ops.Divide, ops.Literal,
        ops.Negate, ops.Cast, ops.UnboundTable)

class RecordingScope:
    def __init__(self):
        self.used_all = False
    def __getattr__(self, name):
        return vt[name]
    def all(self, x):
        self.used_all = True
        return x

def classify_calc(fn):
    scope = RecordingScope()
    node = fn(scope).op()
    deps = {f.name for f in node.find(ops.Field)}
    safe = not scope.used_all and all(isinstance(n, SAFE) for n in node.find(ops.Node))
    return safe, deps

assert classify_calc(calcs["distance_per_flight"].expr) == (True, {"total_distance", "flight_count"})
assert classify_calc(calcs["pct_of_total"].expr)[0] is False  # uses .all() -> exclude

# E-04: re-aggregating decomposable bases from a finer grain equals BSL truth.
m2 = m.with_measures(avg_distance__sum=lambda x: x.distance.sum(),
                     avg_distance__count=lambda x: x.distance.count())  # non-NULL count
cols = ["total_distance", "flight_count", "avg_distance", "distance_per_flight", "max_delay"]
truth = m2.group_by("origin").aggregate(*cols).execute().set_index("origin").sort_index()
fine = m2.group_by("origin", "dep_date").aggregate(
    "total_distance", "flight_count", "avg_distance__sum", "avg_distance__count", "max_delay").execute()
g = fine.groupby("origin").agg({"total_distance": "sum", "flight_count": "sum",
                                "avg_distance__sum": "sum", "avg_distance__count": "sum",
                                "max_delay": "max"}).sort_index()
sim = pd.DataFrame({
    "total_distance": g.total_distance, "flight_count": g.flight_count,
    "avg_distance": g.avg_distance__sum / g.avg_distance__count,
    "distance_per_flight": g.total_distance / g.flight_count, "max_delay": g.max_delay})
assert np.allclose(truth[cols].astype(float), sim[cols].astype(float), equal_nan=True)

# E-05: summary row. Formula on summed bases is correct; summing ratios is not.
tot = m2.aggregate("distance_per_flight", "avg_distance").execute().iloc[0]
assert tot.distance_per_flight == 300.0 and tot.avg_distance == 360.0
assert g.total_distance.sum() / g.flight_count.sum() == 300.0
assert g.avg_distance__sum.sum() / g.avg_distance__count.sum() == 360.0
assert round(truth.distance_per_flight.sum(), 2) == 983.33  # the wrong number
# mean != total/count when NULLs exist -> helper count must be the non-NULL count
assert tot.avg_distance != tot.distance_per_flight

# E-06: distinct count does not decompose.
assert m.aggregate("unique_carriers").execute().iloc[0, 0] == 3
assert m.group_by("origin").aggregate("unique_carriers").execute().unique_carriers.sum() == 5

# E-07: BSL filter dicts cover IN / NOT IN / range; regex needs a callable filter.
r = m.query(dimensions=["origin"], measures=["flight_count"], filters=[{"operator": "AND", "conditions": [
    {"field": "carrier", "operator": "in", "values": ["AA", "UA"]},
    {"field": "origin", "operator": "not in", "values": ["ORD"]},
    {"field": "dep_date", "operator": ">=", "value": "2026-01-01"},
    {"field": "dep_date", "operator": "<=", "value": "2026-01-02"}]}]).execute()
assert dict(zip(r.origin, r.flight_count)) == {"JFK": 2, "LAX": 1}
rx = m.filter(lambda x: x.origin.re_search("^J")).group_by("origin").aggregate("flight_count").execute()
assert list(rx.origin) == ["JFK"]

# E-08: time_range needs the time dimension in the query -> send date range as a filter.
try:
    m.query(dimensions=["origin"], measures=["flight_count"],
            time_range={"start": "2026-01-01", "end": "2026-01-02"}).execute()
    raise AssertionError("expected ValueError")
except ValueError:
    pass

from importlib.metadata import version
print("All spike checks passed. boring-semantic-layer", version("boring-semantic-layer"), "ibis", ibis.__version__)
