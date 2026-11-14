"""Spike: evidence for docs/research.md section 7.6 and section 12 (claims E-09 to E-12).

Run:  pip install "boring-semantic-layer==0.3.19" duckdb pandas pyarrow pyarrow_hotfix
      python spike_distinct_and_limits.py
The script simulates how Data Studio evaluates a formula on the rows that the
connector returns. Every check is an assert.
"""
import json

import boring_semantic_layer as bsl
import ibis

t = ibis.memtable({
    "origin":  ["JFK", "JFK", "JFK", "JFK", "LAX", "LAX", "ORD"],
    "carrier": ["AA",  "AA",  "DL",  None,  "AA",  "UA",  "UA"],
    "delay":   [1,     1,     1,     5,     2,     8,     4],
})
m = bsl.to_semantic_table(t, name="f").with_dimensions(
    origin=lambda x: x.origin, carrier=lambda x: x.carrier, delay=lambda x: x.delay,
).with_measures(
    carriers=lambda x: x.carrier.nunique(),
    median_delay=lambda x: x.delay.median(),
)

truth = m.group_by("origin").aggregate("carriers", "median_delay").execute().set_index("origin")
total = m.aggregate("carriers", "median_delay").execute().iloc[0]

# E-09: COUNT_DISTINCT($carrier) is correct on GROUPED rows.
# Data Studio requests [origin, carrier]. The connector groups by both fields.
grouped = m.group_by("origin", "carrier").aggregate().execute()
ds_cd = grouped.dropna(subset=["carrier"]).groupby("origin").carrier.nunique()
assert ds_cd.to_dict() == truth.carriers.to_dict(), (ds_cd, truth.carriers)
assert grouped.carrier.dropna().nunique() == total.carriers == 3  # summary row / scorecard

# E-10: BSL nunique ignores NULL. Data Studio NULL handling is not known (U-15).
assert truth.carriers["JFK"] == 2  # AA, DL; the NULL row does not count

# E-11: MEDIAN($delay) is WRONG on grouped rows, because grouping removes duplicates.
grouped_d = m.group_by("origin", "delay").aggregate().execute()
ds_med_grouped = grouped_d.groupby("origin").delay.median()
assert truth.median_delay["JFK"] == 1.0          # 1, 1, 1, 5
assert ds_med_grouped["JFK"] == 3.0              # 1, 5 -> wrong
# Raw rows (no grouping) give the correct median.
raw = t.select("origin", "delay").execute()
assert raw.groupby("origin").delay.median().to_dict() == truth.median_delay.to_dict()

# E-12: response size per row in the Data Studio getData format.
def bytes_per_row(values, n=10_000):
    body = {"schema": [{"name": f"f{i}", "dataType": "STRING"} for i in range(len(values))],
            "rows": [{"values": values} for _ in range(n)], "filtersApplied": True}
    return len(json.dumps(body, separators=(",", ":"))) / n

narrow = bytes_per_row(["20260101", "JFK", 1234.5])                          # date, dim, metric
id_row = bytes_per_row(["20260101", "3f2b8c1e-9a4d-4c2e-b7f1-0d6e5a9c8b7a"])   # date, UUID
wide = bytes_per_row(["20260101", "Some campaign name", "Germany", "Mobile",
                      12345.67, 890, 0.1234, 456])
for label, b in [("narrow", narrow), ("date+uuid", id_row), ("wide", wide)]:
    print(f"{label:10s} {b:6.1f} bytes/row -> {int(50 * 1024**2 // b):>9,d} rows per 50 MB")
assert narrow < 50 and id_row < 70 and wide < 110
print("All spike checks passed.")
