"""Replay every captured getData body through the API in-process. Fails on any non-2xx except the R-09 guard (400)."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "api"))
from fastapi.testclient import TestClient
import app
sys.path.insert(0, str(Path(__file__).parent))
from truth import truth

client = TestClient(app.app)
known = {f["id"] for f in app.SCHEMA}
bad = 0
for f in sorted((Path(__file__).parent / "fixtures").glob("*.json")):
    body = json.load(open(f))
    ids = {x["name"] for x in body["fields"]}
    if not ids <= known:
        continue  # fixture from an older schema
    r = client.post("/data", json=body)
    ok = r.status_code == 200 or (r.status_code == 400 and "fixed-grain" in r.text)
    bad += not ok
    print(("ok  " if ok else "FAIL"), f.name, sorted(ids), r.status_code)
# LS-16: applied filters drop forFilterOnly fields and filter the rows
flt = {"fields": [{"name": "origin"}, {"name": "flight_count"}, {"name": "carrier", "forFilterOnly": True}],
       "dimensionsFilters": [[{"fieldName": "carrier", "values": ["AA"], "type": "INCLUDE", "operator": "IN_LIST"}]]}
r = client.post("/data", json=flt).json()
expected = app.MODEL.query(dimensions=["origin"], measures=["flight_count"], filters=[{"field": "carrier", "operator": "in", "values": ["AA"]}]).execute()
assert r["filtersApplied"] is True and [f["id"] for f in r["schema"]] == ["origin", "flight_count"], r["schema"]
assert sorted((x["values"][0], x["values"][1]) for x in r["rows"]) == sorted(zip(expected.origin, expected.flight_count.astype(float))), r["rows"]
print("ok   synthetic forFilterOnly + IN_LIST")
# regression: helper measures must group by non-join-key dims on a joined model (with_measures broadcast totals)
dr = {"startDate": "2000-01-01", "endDate": "2100-01-01"}
r = client.post("/data", json={"fields": [{"name": "carrier"}, {"name": "avg_distance__sum"}, {"name": "avg_distance__count"}], "dateRange": dr}).json()
t = truth(app.df, "carrier", dr)
for row in r["rows"]:
    k, s_, n_ = row["values"][0] or "null", row["values"][1], row["values"][2]
    assert n_ and abs(s_ / n_ - t[k]["avg_distance"]) < 1e-6, (k, s_, n_, t[k]["avg_distance"])
print("ok   synthetic avg_distance helpers grouped by carrier")
# Data Studio's real "exclude AA" filter: EXCLUDE IN_LIST [AA] OR INCLUDE IS_NULL (from a live fixture)
excl = [[{"fieldName": "carrier", "values": ["AA"], "type": "EXCLUDE", "operator": "IN_LIST"},
         {"fieldName": "carrier", "values": [], "type": "INCLUDE", "operator": "IS_NULL"}]]
r = client.post("/data", json={"fields": [{"name": "carrier"}, {"name": "flight_count"}], "dateRange": dr, "dimensionsFilters": excl}).json()
t = truth(app.df, "carrier", dr, lambda d: (d.carrier != "AA") | d.carrier.isna())
assert r["filtersApplied"] and {(x["values"][0] or "null") for x in r["rows"]} == set(t) - {"Grand total"}, r["rows"]
assert all(x["values"][1] == t[x["values"][0] or "null"]["flight_count"] for x in r["rows"]), r["rows"]
print("ok   synthetic EXCLUDE IN_LIST + IS_NULL")
print(f"{bad} failures")
sys.exit(1 if bad else 0)
