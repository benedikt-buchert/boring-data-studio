# PROTOTYPE — throwaway feasibility spike

Question: can a BSL model reach a real Data Studio report with locked formulas, hidden helpers,
descriptions and correct ratio totals, and what do the real getData requests look like (U-01…U-19)?

Neither prototype branch (logic/UI) fits; this is an end-to-end spike. Nothing here is production code.

## Run

```
cd prototype/api && uv venv -p 3.12 .venv && uv pip install -p .venv/bin/python "boring-semantic-layer==0.3.19" "ibis-framework[duckdb]==11.0.0" fastapi uvicorn pandas pyarrow pyarrow_hotfix
.venv/bin/python app.py            # self-check: prints the generated Data Studio schema
.venv/bin/uvicorn app:app --port 8799 --reload
```

1. Expose port 8799 publicly (ngrok / cloudflared / `ssh -R 80:localhost:8799 nokey@localhost.run`).
2. script.google.com → new project → paste `connector/Code.gs`, enable "Show appsscript.json" and paste `connector/appsscript.json` → Deploy → New deployment → type "Library"/head is enough.
3. Open `https://lookerstudio.google.com/datasources/create?connectorId=<DEPLOYMENT_ID>`, enter the public URL.
4. Build: table (origin × metrics, summary row on), scorecard, monthly time series on dep_date, filtered table.
5. Every getData body lands in `fixtures/*.json` — those are the golden fixtures for section 9.4.

## What the API already proves locally

- Classifier: Sum/Count → SUM metric; Mean → 2 hidden helpers + `SUM($x__sum)/SUM($x__count)`;
  CountDistinct → hidden raw dim + `COUNT_DISTINCT($carrier__value)`; calc measure → `$`-formula;
  `.all()` and Median → excluded; `compute: both` → extra `__bsl` field with `isReaggregatable=false`.
- `/data` translates fields, EQUALS/IN_LIST filters, date range; raw dims group by the source column;
  dates come back as `YYYYMMDD`; NULL stays NULL.

## Checks to record once a report exists

U-01 base fields only? · U-02 summary row from summed bases? · U-03 `__bsl` in summary row · U-05 scorecard request
· U-06 month series requests day? · U-14 hidden raw dim requested? · U-15 NULL in COUNT_DISTINCT · U-19 SUM over all-NULL (SFO).

## Findings from the real report (2026-11-14, head deployment AKfycbwVDI6M0Uddi3U99-RIH8yKVHSQrTuRs3iNxbjJih9y)

| ID | Result | Evidence |
|---|---|---|
| Builder rule (new) | `setAggregation` on a field with `isReaggregatable=false` throws in `getSchema` ("Cannot set aggregation type ... not reaggregatable"). Omit aggregation for `compute: bsl` fields. | Data Studio error dialog, Error ID f6b07b34 |
| LS-35 | Direct link with `connectorConfig` prefilled the API URL. | Data source create page |
| LS-08 | Hidden helpers (`avg_distance__sum/__count`, `carrier__value`) do not appear in the field list (10/10 fields shown). | Data source field list |
| LS-17 | Default `dateRange` = last 28 days excluding today. | fixtures/1794637700526.json |
| U-01 | **Yes.** For formula metrics Data Studio requests only base fields: `total_distance, flight_count, avg_distance__sum, avg_distance__count` — never the formula field itself. | fixtures/1794637762742.json |
| U-02 | **Yes.** Summary row = a separate getData without dimensions (fields: helpers + raw dim). Grand total `distance_per_flight` 1,200.41 = BSL 1200.41; `avg_distance` 1,614.84 = BSL 1614.84; `unique_carriers` 3 = BSL nunique 3 (not 12). | fixtures/1794637792498.json vs table |
| U-14 | **Yes.** `COUNT_DISTINCT($carrier__value)` makes Data Studio request the hidden dimension `carrier__value`. | fixtures/1794637792619.json |
| U-15 | NULL is **not** counted by `COUNT_DISTINCT`: rows with NULL carrier show 0. Same as BSL `nunique` (E-10). | table rows 5–8 |
| U-19 | `SUM` over all-NULL rows shows `null` (SFO), and `null / n` stays `null`. | table row SFO |
| U-03 / E-20 / R-09 | Mixing `unique_carriers__bsl` (isReaggregatable=false) with a raw-field metric in one table: Data Studio cannot merge rows with different values of the fixed metric → origin rows duplicate (8 rows for 4 origins), grand total collapses to one slice (flight_count 46 instead of 904, ratio 1,266 instead of 1,200) and Data Studio shows "Data aggregation issue: the data response has a bad reaggregation". API must reject this combination (R-09). | table + warning dialog |
| Requests per chart | Table with summary row = 2 getData (body + summary). Every getData = 1 URL Fetch after dropping the extra `/schema` call. | fixtures |
| Tunnel | localhost.run free tunnels rotate domains and drop; "Address unavailable" errors are transport, not connector. Use a stable host for golden-fixture runs. | error IDs 3a63f606, 221e7eae |
| U-03 | **Correct when alone.** Table origin × flight_count × `unique_carriers__bsl` (no raw fields): 4 rows, 3 each, grand total 3. The summary row is its own dimension-less getData, so BSL computes the true total; Data Studio does not sum the rows. `compute: bsl` is safe for summary rows; E-19's "sum of rows" concern applies only to client-side re-bucketing (U-06). | fixtures/1794638193916.json (summary) + 1794638193116.json (body) |
| U-05 | **Yes.** Scorecard sends getData with metrics only, no dimensions (`fields: [flight_count]`, dateRange present). Shows 904 = BSL. | fixtures/1794638511759.json |
| LS-29 | Data Studio caches per query incl. failures: after a tunnel drop the metrics-only query kept returning the cached error (new Error ID 8dbb1c0c) until the data source config changed. | scorecard |
| U-06 | **Yes, Data Studio buckets itself.** Switching the time series dimension to "Year Month" sent a new getData still asking for day-grain `dep_date`; the chart then shows 2 points (Oct ≈469, Nov ≈435 = BSL day rows summed per month). So a `compute: bsl` metric on a month series is re-aggregated by Data Studio (E-19 holds here, unlike the summary row). | fixtures/1794638628861.json + chart |
| Skipped | U-04 (>20 fields), U-07 (metric filters), U-16 (timeout), dimension filters (`dimensionsFilters` never appeared in any request; no filter control was added). | — |

## Verdict

Feasible. The whole chain works in the real product: BSL YAML → classifier → `/schema` with `$`-formulas, hidden helpers, descriptions → Apps Script builder → Data Studio field list → correct per-row and summary-row values for ratio, mean and distinct-count metrics, with totals equal to BSL. Two hard rules fall out of the live run: never `setAggregation` on `isReaggregatable=false` fields, and never let a `compute: bsl` metric share a request with raw fields (R-09) — Data Studio shows a "bad reaggregation" warning and corrupts every column. `compute: bsl` is safe for tables with summary rows (separate total query) but not for client-side date re-bucketing.

Report: https://datastudio.google.com/reporting/9559732f-1452-4c24-bab8-761cf8ab67e0 · Data source: https://datastudio.google.com/datasources/a12eede9-6afc-465f-86a5-0c5a6984acba · Apps Script: https://script.google.com/home/projects/1mwH_cLLtqaEKPttW8ZDTK66vX_YmQQQM1pq5le7ihtYxdlp-pnQZoYdr

## Showcase dashboard (report page 2, theme "Constellation")

Built live on 2026-11-14 to show every research case on one page:

| Component | Research case |
|---|---|
| Title text | — |
| Scorecards `flight_count`, `distance_per_flight`, `avg_distance`, `unique_carriers` | U-05 metrics-only requests; formula metrics on totals (E-23) |
| Table origin × flight_count, distance_per_flight, avg_distance, unique_carriers, summary row | E-22/E-23 base-field requests, summary row from a separate query; U-19 all-NULL SFO row |
| Time series `dep_date` (Year Month) × avg_distance, distance_per_flight | E-28 client-side month bucketing of day rows; ratios still correct because the bases are additive |
| Table origin × total_distance, `unique_carriers (fixed grain)`, summary row | E-26 `compute: bsl` safe without raw fields; R-09 guard in the API rejects the mixed case |
| Bar chart carrier × avg_distance | mean via hidden helpers at a second grain |
| Date range control + carrier drop-down | `dateRange` translation; `dimensionsFilters` translation (IN_LIST → BSL `in`) |

Caveat: the free localhost.run tunnel drops every few minutes; Data Studio caches each failed query ("Address unavailable", LS-52) until the chart or the data source config changes. For a stable demo run the API behind ngrok/cloudflared and update the data source URL once.

## Page 3 — "what only a semantic layer gives Data Studio"

Model additions (`api/flights.yml`): `airports` model + `joins: airports` (left, one) → dimensions `airports.city/country` exposed as `airports__city/__country` (LS-02 `__` mapping); conditional measure `delayed_flights = (_.delay > 30).sum()` → plain SUM metric; `on_time_rate = 1 - delayed_flights / flight_count` → formula `(1 - (SUM($delayed_flights) / SUM($flight_count)))`; `pct_of_total` (uses `.all()`) and `median_delay` with `compute: bsl` → fixed-grain fields, PERCENT semantic type on the share.

| Component | Shows |
|---|---|
| Table airports.city × flight_count, delayed_flights, on_time_rate, pct_of_total, median_delay + summary | joined dimension, conditional ratio, share-of-total and median per city with correct totals (100 %, 61.5) |
| Bar airports.city × on_time_rate | ratio at a joined grain |
| Table carrier × flight_count, on_time_rate, median_delay, pct_of_total + summary | same metrics at another grain; NULL carrier row |
| Scorecards median_delay 61.5, on_time_rate 0.25 | fixed-grain and formula metrics as totals |

## Verification

`verify_dashboard.py` reads every number from the dashboard DOM dump (`verification/*.json`, dumped from the report via the browser) and compares it with BSL truth from `/data` for the same date range (2026-10-17..2026-11-13):

- page 2 (dashboard): **34/34 values match**
- page 3 (semantic layer): **47/47 values match**

Run: `api/.venv/bin/python verify_dashboard.py verification/page3_semantic_layer.json`.

Stable tunnel used for the final run: serveo.net via `ssh -R 80:localhost:8799 serveo.net` (random subdomain, stable for the ssh session, no interstitial for non-browser clients).
