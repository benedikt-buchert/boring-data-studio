"""Spike: evidence for docs/research.md claims E-13 to E-17.

Run:  pip install "boring-semantic-layer==0.3.19" duckdb pandas pyarrow pyarrow_hotfix
      python spike_function_semantics.py
"""
import math

import boring_semantic_layer as bsl
import ibis
from ibis.expr import operations as ops

# Data Studio documentation examples use the input 95, 100, 92.
# PERCENTILE(x, 30.5) = 93.83, STDDEV = 3.3, VARIANCE = 10.89.
t = ibis.memtable({"x": [95.0, 100.0, 92.0]})
con = ibis.duckdb.connect()

# E-13: Data Studio STDDEV and VARIANCE are POPULATION statistics.
pop_sd = con.execute(t.x.std(how="pop"))
samp_sd = con.execute(t.x.std(how="sample"))
pop_var = con.execute(t.x.var(how="pop"))
assert round(pop_sd, 1) == 3.3 and round(pop_var, 2) == 10.89
assert round(samp_sd, 1) != 3.3  # 4.0 -> Ibis default (sample) does NOT match
# A sample std in BSL needs the formula STDDEV(x) * SQRT(n / (n - 1)).
assert math.isclose(pop_sd * math.sqrt(3 / 2), samp_sd)

# E-14: Data Studio PERCENTILE uses linear interpolation (numpy "linear", DuckDB quantile_cont).
p = con.execute(t.x.quantile(0.305))
assert round(p, 2) == 93.83, p
sql = str(ibis.to_sql(t.x.quantile(0.305), dialect="duckdb")).lower()
assert "quantile_cont" in sql, sql

# E-15: conditional aggregations keep the condition in the Ibis node (`where`).
f = ibis.memtable({"origin": ["JFK", "JFK", "LAX", "LAX"], "carrier": ["AA", "DL", "AA", "UA"],
                   "delay": [1, 5, 2, 8], "distance": [100.0, 200.0, 300.0, 400.0]})
m = bsl.to_semantic_table(f, name="f").with_measures(
    late_distance=lambda x: x.distance.sum(where=x.delay > 2),
    late_carriers=lambda x: x.carrier.nunique(where=x.delay > 2),
)
meas = m.get_measures()
def node(name):
    e = meas[name].expr
    return (e.resolve(f) if hasattr(e, "resolve") else e(f)).op()
assert isinstance(node("late_distance"), ops.Sum) and node("late_distance").where is not None
assert isinstance(node("late_carriers"), ops.CountDistinct) and node("late_carriers").where is not None
# A conditional SUM still decomposes: re-aggregate from (origin, carrier) to (origin).
truth = m.group_by("origin").aggregate("late_distance").execute().set_index("origin").late_distance
fine = m.group_by("origin", "carrier").aggregate("late_distance").execute()
assert fine.groupby("origin").late_distance.sum(min_count=1).fillna(0).to_dict() == truth.fillna(0).to_dict()

# E-16: Data Studio uses RE2; DuckDB uses RE2. Ibis compiles re_search to regexp_matches on DuckDB.
r = ibis.memtable({"c": ["USA", "ROK", "RU", "CA"]})
sql = str(ibis.to_sql(r.filter(r.c.re_search("^R[A-Z]*K$")), dialect="duckdb")).lower()
assert "regexp_matches" in sql, sql
# Data Studio reference examples: PARTIAL '(?i)R[A-Z]*' -> ROK, RU ; EXACT '^R[A-Z]*K$' -> ROK
partial = con.execute(r.filter(r.c.re_search("(?i)R[A-Z]*")).c).tolist()
exact = con.execute(r.filter(r.c.re_search("^(?:^R[A-Z]*K$)$")).c).tolist()
assert sorted(partial) == ["ROK", "RU"], partial
assert exact == ["ROK"], exact

# E-17: the documented filter semantics (inner OR, outer AND, EXCLUDE) map to BSL filter dicts.
fm = bsl.to_semantic_table(f, name="g").with_dimensions(
    origin=lambda x: x.origin, carrier=lambda x: x.carrier).with_measures(n=lambda x: x.count())
# Data Studio: [[origin IN (JFK)] OR [carrier = UA]] AND [[carrier EXCLUDE EQUALS DL]]
res = fm.query(dimensions=["origin", "carrier"], measures=["n"], filters=[{"operator": "AND", "conditions": [
    {"operator": "OR", "conditions": [
        {"field": "origin", "operator": "in", "values": ["JFK"]},
        {"field": "carrier", "operator": "=", "value": "UA"}]},
    {"field": "carrier", "operator": "!=", "value": "DL"}]}]).execute()
assert sorted(zip(res.origin, res.carrier)) == [("JFK", "AA"), ("LAX", "UA")]

print("All spike checks passed.")
