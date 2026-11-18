"""Spike: offline part of Wayfinder #21 (BigQuery advanced services with BSL descriptions).

With advanced services, getData returns newBigQueryConfig() (SQL + billing project + token) and
Data Studio queries BigQuery itself. Google says "Filters are automatically pushed down" for this
mode, which means Data Studio generates its own SQL around the connector's SQL, like a custom
query. Whether Data Studio also calls getData per chart (so the SQL can change per request) is not
documented; the live runbook checks it.

This spike tests the two SQL shapes the API could hand to the connector:

  A  base relation  one SQL per model, independent of the request. Row-level: one column per
                    dimension, per hidden raw dimension (distinct counts) and per metric input
                    (Sum -> arg, CountStar -> 1, Mean -> two helpers). Data Studio aggregates
                    it with the existing field formulas.
  B  per request    the BSL query for the request's fields, filters and date range, compiled with
                    SemanticAggregate.to_sql(dialect="bigquery"). Needs a getData call per chart.

Checks:
  1. Both shapes compile to BigQuery SQL from the prototype model (with a join) - no credentials.
  2. Shape A under a simulated Data Studio wrapper (GROUP BY + SUM/MIN/MAX/COUNT(DISTINCT) +
     formulas, run in DuckDB) equals BSL at every grain, the summary row, a month grain and a filter.
  3. Shape B wrapped again at the same grain equals BSL; re-aggregated to a coarser grain it is
     wrong for distinct counts, as today (E-19).
  4. Gotchas in the generated SQL (date literal type, collisions, compute: bsl measures).
  5. Median (E-47): holistic; raw mode over shape A; Ibis cannot compile an exact median for BigQuery.

Run:  prototype/api/.venv/bin/python research/spikes/spike_bq_advanced_services.py
      (venv from prototype/README.md, plus "ibis-framework[bigquery]==11.0.0" for the dialect)
"""
import datetime as dt
import sys
from pathlib import Path

import boring_semantic_layer as bsl
import ibis
import numpy as np
import pandas as pd
import sqlglot
import yaml

CFG_PATH = Path(__file__).resolve().parents[2] / "prototype" / "api" / "flights.yml"
CFG = yaml.safe_load(CFG_PATH.read_text())
sys.path.insert(0, str(CFG_PATH.parent))
from bq_sql import DS_ID, base_relation, short  # noqa: E402  shared with the live spike (prototype/api/bq_spike.py)
FLIGHTS = {"origin": "string", "carrier": "string", "dep_date": "date", "distance": "float64", "delay": "int64"}
AIRPORTS = {"code": "string", "city": "string", "country": "string", "state": "string"}


def model(tables):
    return bsl.from_config(CFG, tables=tables)["flights"]


def ds_wrapper(inner_sql, dims, metrics, agg, formulas, where=None):
    """What we assume Data Studio sends to BigQuery around a custom query (to verify live)."""
    sel = list(dims) + [f"{formulas[m] if m in formulas else agg[m] + '(' + m + ')'} AS {m}" for m in metrics]
    sql = f"SELECT {', '.join(sel)} FROM ({inner_sql}) AS ds"
    if where: sql += f" WHERE {where}"
    if dims: sql += " GROUP BY " + ", ".join(str(i + 1) for i in range(len(dims)))
    return sql


# --- data: same generator as prototype/api/app.py (NULL carriers, all-NULL SFO distance) -------
rng = np.random.default_rng(1)
n = 3000
df = pd.DataFrame({
    "origin": rng.choice(["JFK", "LAX", "ORD", "SFO"], n),
    "carrier": rng.choice(["AA", "UA", "DL", None], n, p=[0.4, 0.3, 0.25, 0.05]),
    "dep_date": pd.Timestamp("2026-11-01") - pd.to_timedelta(rng.integers(1, 90, n), "D"),
    "distance": rng.integers(100, 3000, n).astype(float),
    "delay": rng.integers(0, 120, n),
})
df.loc[df.origin == "SFO", "distance"] = None
ap_df = pd.DataFrame({"code": ["JFK", "LAX", "ORD", "SFO"], "city": ["New York", "Los Angeles", "Chicago", "San Francisco"],
                      "country": ["United States"] * 4, "state": ["New York", "California", "Illinois", "California"]})
con = ibis.duckdb.connect()
con.create_table("flights", df.assign(dep_date=df.dep_date.dt.date), schema=ibis.schema(FLIGHTS))
con.create_table("airports", ap_df, schema=ibis.schema(AIRPORTS))
M_duck = model({"flights_tbl": con.table("flights"), "airports_tbl": con.table("airports")})
M_bq = model({"flights_tbl": ibis.table(FLIGHTS, name="flights", catalog="my-project", database="analytics"),
              "airports_tbl": ibis.table(AIRPORTS, name="airports", catalog="my-project", database="analytics")})

# 1. Both shapes compile to BigQuery SQL without credentials.
base_bq, agg, formulas, excluded = base_relation(M_bq)
base_bq_sql = ibis.to_sql(base_bq, dialect="bigquery")
sqlglot.parse_one(str(base_bq_sql), read="bigquery")
print("== shape A: base relation, BigQuery SQL ==\n", base_bq_sql, sep="")
print("excluded from shape A:", excluded)

req = dict(dimensions=["origin", "airports.city"], measures=["flight_count", "avg_distance", "unique_carriers"])
date_conds = lambda a, b: [{"field": "dep_date", "operator": ">=", "value": a}, {"field": "dep_date", "operator": "<=", "value": b}]
q_str = M_bq.query(**req, filters=[{"operator": "AND", "conditions": date_conds("2026-09-01", "2026-09-30")}])
q_date = M_bq.query(**req, filters=[{"operator": "AND", "conditions": date_conds(dt.date(2026, 9, 1), dt.date(2026, 9, 30))}])
sql_str, sql_date = q_str.to_sql(dialect="bigquery"), q_date.to_sql(dialect="bigquery")
for s in (sql_str, sql_date): sqlglot.parse_one(s, read="bigquery")
print("\n== shape B: per-request BSL query, BigQuery SQL (date range as date objects) ==\n", sql_date, sep="")
# 4a. A string date range becomes DATETIME('2026-09-01T00:00:00') against a DATE column; date objects stay DATE.
assert "DATETIME('2026-09-01T00:00:00')" in sql_str and "DATE(2026, 9, 1)" in sql_date
print("\ngotcha: string date range ->", [l.strip() for l in sql_str.splitlines() if "DATETIME" in l][0])

# 2. Shape A + simulated Data Studio wrapper == BSL at every grain.
base_duck, agg_d, formulas_d, _ = base_relation(M_duck)
inner = ibis.to_sql(base_duck, dialect="duckdb")
metrics = [m for m in [*agg_d, *formulas_d] if "__" not in m]  # visible metrics only
truth_ms = [m for m in metrics if m in {short(k) for k in [*M_duck.get_measures(), *M_duck.get_calculated_measures()]}]
grains = [[], ["origin"], ["carrier"], ["airports.city"], ["origin", "carrier"], ["airports.country", "carrier"]]
checked = 0


def compare(got, want, dims, label):
    global checked
    key = [DS_ID(d) for d in dims]
    want = want.rename(columns=lambda c: DS_ID(c.replace("airports_", "airports.")) if c.startswith("airports") else c)
    if key:
        got, want = got.sort_values(key, na_position="first").reset_index(drop=True), want.sort_values(key, na_position="first").reset_index(drop=True)
    for m in truth_ms:
        np.testing.assert_allclose(got[m].astype(float).to_numpy(), want[m].astype(float).to_numpy(), rtol=1e-9, equal_nan=True, err_msg=f"{label} {m}")
        checked += 1


for g in grains:
    got = con.raw_sql(ds_wrapper(inner, [DS_ID(d) for d in g], truth_ms, agg_d, formulas_d)).df()
    compare(got, M_duck.query(dimensions=g, measures=truth_ms).execute(), g, f"grain {g}")
# month grain: Data Studio buckets the day field itself (E-28); shape A has the raw date, so it can.
got = con.raw_sql(ds_wrapper(inner, ["date_trunc('month', dep_date) AS m"], truth_ms, agg_d, formulas_d)).df().sort_values("m")
want = M_duck.query(dimensions=["dep_date"], measures=truth_ms).execute()  # BSL truth at month grain:
want = model({"flights_tbl": con.table("flights").mutate(dep_date=ibis._.dep_date.truncate("M")), "airports_tbl": con.table("airports")}
             ).query(dimensions=["dep_date"], measures=truth_ms).execute().sort_values("dep_date")
for m in truth_ms:
    np.testing.assert_allclose(got[m].astype(float).to_numpy(), want[m].astype(float).to_numpy(), rtol=1e-9, equal_nan=True, err_msg=f"month {m}")
    checked += 1
# filter + date range pushed down by Data Studio as WHERE on the wrapper
got = con.raw_sql(ds_wrapper(inner, ["origin"], truth_ms, agg_d, formulas_d,
                             where="carrier IN ('AA', 'DL') AND dep_date BETWEEN DATE '2026-09-01' AND DATE '2026-09-30'")).df()
want = M_duck.query(dimensions=["origin"], measures=truth_ms, filters=[{"operator": "AND", "conditions": [
    {"field": "carrier", "operator": "in", "values": ["AA", "DL"]}, *date_conds(dt.date(2026, 9, 1), dt.date(2026, 9, 30))]}]).execute()
compare(got, want, ["origin"], "filter")
print(f"\nshape A: {checked} metric columns equal to BSL ({len(truth_ms)} metrics x {len(grains) + 2} requests: {len(grains)} grains incl. summary row, month grain, filter + date range)")

# 3. Shape B: wrapping at the same grain is exact; re-aggregation to a coarser grain breaks distinct counts.
qB = M_duck.query(dimensions=["origin", "dep_date"], measures=["flight_count", "unique_carriers"])
inner_B = qB.to_sql(dialect="duckdb")
same = con.raw_sql(f"SELECT origin, dep_date, SUM(flight_count) AS flight_count, SUM(unique_carriers) AS unique_carriers FROM ({inner_B}) GROUP BY 1, 2").df()
assert len(same) == len(qB.execute())
coarse = con.raw_sql(f"SELECT origin, SUM(flight_count) fc, SUM(unique_carriers) uc FROM ({inner_B}) GROUP BY 1 ORDER BY 1").df()
truth = M_duck.query(dimensions=["origin"], measures=["flight_count", "unique_carriers"]).execute().sort_values("origin")
assert (coarse.fc.to_numpy() == truth.flight_count.to_numpy()).all()
assert (coarse.uc.to_numpy() > truth.unique_carriers.to_numpy()).all()  # per-day distinct counts summed per origin -> wrong, like E-19
print("shape B: same-grain wrap exact; coarser re-aggregation overcounts distinct counts (E-19 again)")

# 4b. Column-name collisions in the joined relation: BSL dims resolve on plain names of the join.
J = M_bq.to_untagged()
assert len(J.columns) == len(set(J.columns))
print("\nrow counts: shape A returns no rows to Apps Script; BigQuery returns only the aggregated result to Data Studio")

# 5. Median (E-47, U-29). Holistic: no per-group summary combines to the total median.
d = con.table("flights").delay
tiny = ibis.memtable({"g": [1, 1, 1, 2, 2], "x": [1, 2, 3, 10, 20]})
per_group = con.execute(tiny.group_by("g").aggregate(m=tiny.x.median())).sort_values("g").m.tolist()
total = con.execute(tiny.aggregate(m=tiny.x.median())).m[0]
assert per_group == [2, 15] and total == 3  # 3 cannot be built from 2 and 15 (mean 8.5, median-of-medians 8.5)
# Raw mode in shape A: MEDIAN over the raw column equals BSL at every grain (DuckDB: exact median).
for g in [[], ["origin"], ["carrier"]]:
    got = con.raw_sql(ds_wrapper(inner, [DS_ID(x) for x in g], ["median_delay__raw"], agg_d,
                                 {**formulas_d, "median_delay__raw": "MEDIAN(delay__value)"})).df()
    want = M_duck.query(dimensions=g, measures=["median_delay"]).execute()
    key = [DS_ID(x) for x in g]
    if key: got, want = got.sort_values(key, na_position="first"), want.sort_values(key, na_position="first")
    np.testing.assert_allclose(got.median_delay__raw.to_numpy(float), want.median_delay.to_numpy(float))
# Ibis 11 has no BigQuery rule for exact Median/Quantile; only approximate APPROX_QUANTILES compiles.
for e in (d.median(), d.quantile(0.5)):
    try:
        ibis.to_sql(con.table("flights").aggregate(m=e), dialect="bigquery"); raise AssertionError("compiled")
    except ibis.common.exceptions.OperationNotDefinedError:
        pass
assert "APPROX_QUANTILES" in ibis.to_sql(con.table("flights").aggregate(m=d.approx_median()), dialect="bigquery")
print("median: holistic (2, 15 -> 3); raw-mode MEDIAN over shape A equals BSL in DuckDB; "
      "Ibis cannot compile exact median/quantile for BigQuery, only APPROX_QUANTILES")
