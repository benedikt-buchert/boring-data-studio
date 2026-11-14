"""PROTOTYPE — compare numbers read from the Data Studio dashboard DOM with BSL truth from the API.

Usage: .venv/bin/python verify_dashboard.py dashboard_text.json
dashboard_text.json = {"dateRange": {...}, "components": ["<innerText of each component>", ...]} dumped from the browser.
Every check is an assert; prints a table of DS value vs BSL value.
"""
import json, re, sys, urllib.request

API = "http://localhost:8799/data"
doc = json.load(open(sys.argv[1]))
dr = doc["dateRange"]

def q(fields, **extra):
    body = {"fields": [{"name": f} for f in fields], "dateRange": dr, **extra}
    r = urllib.request.urlopen(urllib.request.Request(API, json.dumps(body).encode(), {"content-type": "application/json"}))
    rows = json.load(r)["rows"]
    return [dict(zip(fields, x["values"])) for x in rows]

num = lambda s: None if s in ("null", "-", "") else (float(s.replace(",", "")[:-1]) / 100 if s.endswith("%") else float(s.replace(",", "")))
close = lambda a, b: (a is None and b is None) or (a is not None and b is not None and abs(a - b) <= max(0.011, abs(b) * 5e-3))

checks = []
# totals (scorecards + grand totals)
tot = q(["flight_count", "total_distance", "avg_distance__sum", "avg_distance__count", "delayed_flights", "unique_carriers__bsl", "median_delay", "pct_of_total"])[0]
truth_tot = {"flight_count": tot["flight_count"], "distance_per_flight": tot["total_distance"] / tot["flight_count"],
             "avg_distance": tot["avg_distance__sum"] / tot["avg_distance__count"], "unique_carriers": tot["unique_carriers__bsl"],
             "on_time_rate": 1 - tot["delayed_flights"] / tot["flight_count"], "median_delay": tot["median_delay"], "pct_of_total": tot["pct_of_total"]}
for c in doc["components"]:
    m = re.fullmatch(r"(\w+)\s+([\d,.]+%?|null)", c.strip())
    if m and m.group(1) in truth_tot:
        checks.append(("scorecard " + m.group(1), num(m.group(2)), truth_tot[m.group(1)]))

# tables: header line then numbered rows; identify by first header token
def table_rows(text):
    lines = [l for l in text.split("\n") if l.strip()]
    hdr = []
    i = 0
    while i < len(lines) and not re.fullmatch(r"\d+\.", lines[i]):
        if lines[i] not in ("▼", "▲"): hdr.append(lines[i])
        i += 1
    rows = []
    while i < len(lines):
        if re.fullmatch(r"\d+\.", lines[i]) or lines[i] == "Grand total":
            name = "Grand total" if lines[i] == "Grand total" else None
            vals = lines[i + 1:i + 1 + len(hdr) - (1 if name else 0)]
            if name: vals = [name] + vals
            rows.append(dict(zip(hdr, vals))); i += len(vals) + (0 if name else 1)
        else:
            i += 1
    return hdr, rows

FORMULA = {"distance_per_flight": lambda r: r["total_distance"] / r["flight_count"] if r["total_distance"] is not None else None,
           "avg_distance": lambda r: r["avg_distance__sum"] / r["avg_distance__count"] if r["avg_distance__sum"] is not None else None,
           "on_time_rate": lambda r: 1 - r["delayed_flights"] / r["flight_count"],
           "unique_carriers": None, "pct_of_total": None, "median_delay": None, "delayed_flights": None, "flight_count": None, "total_distance": None}  # COUNT_DISTINCT over raw rows: compared via unique_carriers__bsl at the same grain
BASES = {"pct_of_total": ["pct_of_total"], "median_delay": ["median_delay"], "distance_per_flight": ["total_distance", "flight_count"], "avg_distance": ["avg_distance__sum", "avg_distance__count"],
         "on_time_rate": ["delayed_flights", "flight_count"], "unique_carriers": ["unique_carriers__bsl"]}
DIM_IDS = {"origin": "origin", "carrier": "carrier", "airports.city": "airports__city", "airports.country": "airports__country", "dep_date": "dep_date"}
LABEL = {"unique_carriers (fixed grain)": "unique_carriers__bsl"}

for c in doc["components"]:
    if not re.search(r"\n1\.\n", c): continue
    hdr, rows = table_rows(c)
    dim, metrics = DIM_IDS.get(hdr[0]), [LABEL.get(h, h) for h in hdr[1:]]
    if not dim: continue
    fields = [dim] + sorted({b for m in metrics for b in BASES.get(m, [m])})
    truth = {("null" if r[dim] is None else r[dim]): r for r in q(fields)}
    truth_all = q(fields[1:])[0]
    for r in rows:
        key = r[hdr[0]]
        t = truth_all if key == "Grand total" else truth.get(key)
        if t is None: checks.append((f"table {hdr[0]} row {key}", "missing in BSL", None)); continue
        for h, m in zip(hdr[1:], metrics):
            tv = FORMULA[m](t) if FORMULA.get(m) else t[BASES.get(m, [m])[0]]
            checks.append((f"table {hdr[0]} {key} {h}", num(r[h]), tv))

bad = 0
for name, ds, tv in checks:
    ok = close(ds, tv) if not isinstance(ds, str) else False
    bad += not ok
    print(("OK  " if ok else "FAIL") + f" {name}: dashboard={ds} bsl={tv}")
print(f"\n{len(checks) - bad}/{len(checks)} values match BSL")
assert bad == 0
