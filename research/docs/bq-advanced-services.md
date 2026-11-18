# Wayfinder #21: BigQuery advanced services: offline findings and live runbook

Question: can the connector use BigQuery advanced services to get native BigQuery speed and keep the BSL descriptions and formulas? ([#21](https://github.com/benedikt-buchert/boring-data-studio/issues/21))

Status (2026-11-18): the parts that need no Google account are complete. This covers the docs, the SQL from BSL/Ibis, correctness against a simulated Data Studio wrapper, and the auth analysis. The live parts are in the runbook below: timing, the real SQL that Data Studio sends, and the schema behaviour in a report. This file is evidence and recommendations. **It contains no decisions.** Decisions go into the ticket. The IDs LS-65..LS-69, E-44..E-46 and U-21..U-28 continue the numbering of `research.md`, and they move there after review.

## 1. Short answer

- **Probably yes, for most measures, in a specific shape.** The API gives one *base relation* SQL for each model ("shape A"). This relation is row-level. It has one column for each dimension, each hidden raw dimension and each metric input, and the column names are the Data Studio field IDs. The normal `getSchema` stays as it is (descriptions, `$` formulas, hidden helpers), and Data Studio aggregates in BigQuery. Offline, this matches BSL at every grain we tested, the summary row and month buckets included (E-45).
- **What is lost in this mode:** `compute: bsl` measures (median, `.all()`, approx distinct), BSL's `auth_hook`/row-level control (BigQuery IAM decides instead), and the API guards. The guards are not necessary for the row cap, but AD-36 (one-to-many) needs a new rule.
- **Not proven:** that Data Studio wraps the SQL as a custom query and binds formula fields to it. The docs strongly suggest it (LS-67, LS-68). The speed gain is not measured yet. The runbook answers both in about 30 minutes.
- **Recommendation:** make it an optional, BigQuery-only data mode next to the v1 path. Do not change v1 before U-21..U-23 pass. If they pass, the same `/schema` contract feeds both modes.

## 2. Evidence from the docs

| ID | Claim | Source |
|---|---|---|
| LS-65 | With advanced services, `getSchema` and/or `getData` return a query configuration, and Data Studio "will directly fetch the schema and/or data based on the query configuration provided". Manifest: `dataStudio.advancedServices.schema` / `.data`. Leave `schema` false when the schema cannot come from one BigQuery query. `getSchema` then returns a normal schema. `useQueryConfig` is deprecated. | [Advanced Services](https://developers.google.com/looker-studio/connector/advanced-services) |
| LS-66 | `newBigQueryConfig()` has only these setters: billing project, query, standard SQL, access token, and `addQueryParameter`. Parameter types are only `BOOL`, `FLOAT64`, `INT64` and `STRING`, and each value is passed as a string. There is **no** setter for `maximumBytesBilled`, labels or job settings, and no `DATE` parameter type. | [BigQueryConfig](https://developers.google.com/apps-script/reference/data-studio/big-query-config) |
| LS-67 | For advanced services: "Filters are automatically pushed down". Calculated fields are supported through `getSchema`. The Apps Script BigQuery service and the REST API do not push filters down. Advanced services cannot do custom caching or transform data in `getData`, and the fetched data never reaches Apps Script. | [Connect to BigQuery](https://developers.google.com/looker-studio/connector/connect-to-bigquery) |
| LS-68 | Google's row-level-security example builds SQL in `getData` from the effective user's email, returns it with a service-account token, and ignores `request.fields`. Its schema declares `sales` as a SUM metric, so Data Studio aggregates the returned relation. It uses `forceViewersCredentials`, and each viewer authorises once. | [BigQuery RLS with Advanced Services](https://developers.google.com/looker-studio/connector/bigquery-row-level-security) |
| LS-69 | A user token needs `https://www.googleapis.com/auth/bigquery.readonly` in `oauthScopes`. A service-account token needs no manifest scope. Whether `bigquery.readonly` counts as a *sensitive* scope for OAuth verification (#3) is **not confirmed**. | LS-65 page; [OAuth verification FAQ](https://support.google.com/cloud/answer/13463817) |

**Not documented anywhere:**

- Is `getData` called once for each chart in this mode, or once for each data source?
- Which SQL does Data Studio generate?
- Do `$` formulas, `isReaggregatable` and date fields bind to the BigQuery columns?
- Can `getData` return rows for some requests and a config for others?

These are U-21..U-28.

## 3. Offline evidence

Spike: `research/spikes/spike_bq_advanced_services.py` (prototype model with join, NULL carriers, all-NULL SFO distance). Shared code: `prototype/api/bq_sql.py`.

| ID | Test | Result |
|---|---|---|
| E-44 | Generate shape A from the BSL model through the AD-26 translation rows: `CountStar` → `1`, `Sum` → arg (bool cast to INT64), `Count` → `arg IS NOT NULL`, `Min`/`Max` → arg, `Mean` → `__sum`/`__count` helpers, `CountDistinct` → `<col>__value`. Compile it with `ibis.to_sql(dialect="bigquery")`. | Valid BigQuery SQL (parsed by sqlglot): one `SELECT` over the `LEFT JOIN`. Column names equal the Data Studio field IDs, `airports__city` included. `median_delay` and `pct_of_total` (`compute: bsl`) are excluded. No credentials are needed. |
| E-45 | Run shape A in DuckDB, wrapped the way we assume Data Studio does it (`SELECT dims, SUM(col)…, COUNT(DISTINCT raw), formulas FROM (<A>) [WHERE …] GROUP BY dims`). Compare with BSL. | **128/128 values equal**: 16 metrics × 8 requests. The requests are 6 grains including the summary row (no dimensions), a month grain bucketed by the wrapper, and an `IN` filter plus a date range. The means, the distinct count and the calculated measures (`distance_per_flight`, `on_time_rate`) are included. |
| E-46 | Shape B: compile `SemanticAggregate.to_sql(dialect="bigquery")` for a request. | It works. **Gotcha:** a date range given as strings (as Data Studio sends it) compiles to `dep_date >= DATETIME('2026-09-01T00:00:00')` against a DATE column. Date objects give `DATE(2026, 9, 1)`. When the wrapper re-aggregates at the same grain, the result is exact. At a coarser grain, distinct counts overcount again (as in E-19). |

The `ds_wrapper` in E-45 is our assumption of the Data Studio SQL. U-22 checks it against the real SQL.

## 4. The six questions

**1. Overhead.**

- What stays: `getData` still runs in Apps Script, at about 0.7–1.5 s per call (E-40). If Data Studio calls it once per chart (U-21), that cost stays per chart, and the calls run in parallel.
- What goes away:
  - the URL Fetch round trip to the API (mode `A_CACHED` keeps the SQL in `CacheService`);
  - BSL execution in the API;
  - JSON serialisation of the rows, and the rows passing through Apps Script.
- When the BSL backend is BigQuery, today's path already runs one BigQuery job per chart, so the BigQuery time is equal in both paths.
- Expected gap to the native connector: the Apps Script hop only, about 1 s.
- Expected gain over today: largest for large responses, which today are capped by R-02 and by the URL Fetch size, and for distinct counts, whose raw rows (AD-35) never leave BigQuery.
- Measurement: U-26.

**2. Query shape.**

- The docs point to wrapping: filters are "pushed down" (LS-67), and the RLS example ignores `request.fields` and declares `SUM` (LS-68).
- Shape A does not depend on per-chart calls, so it is the safer shape. If Data Studio wraps it, distinct counts are correct at every grain (E-45).
- Shape B (per-request SQL) works only if `getData` runs per chart. It brings back the fixed-grain problem (E-46).
- Live checks: U-21, U-22, U-27.

**3. Schema.**

- The docs say calculated fields from `getSchema` work with advanced services (LS-67).
- The base-relation column names are the field IDs, so `$id` formulas can bind by name.
- Unknown: whether descriptions, hidden helpers and `isReaggregatable` survive, and the date type. The relation gives a BigQuery `DATE`, but the schema says `YEAR_MONTH_DAY`. `BQ_DATE_AS_STRING=1` gives `'YYYYMMDD'` instead. Live checks: U-23, U-24.

**4. SQL source and what it changes.**

The API can give both shapes from BSL/Ibis (E-44, E-46). In BigQuery mode:

| Item | Change |
|---|---|
| API cache (D-19) | Out of the data path. Shape A SQL changes only with the model version. BigQuery result cache and Data Studio cache take over (U-28). |
| Row guard (R-01, R-02) | Rows no longer pass through Apps Script or the API, so the cap is not needed. Cost becomes the risk: the config has no `maximumBytesBilled` (LS-66). Cost control must come from BigQuery custom quotas on the billing project, and from partitioned tables plus the date range. |
| Fixed-grain guard (R-09) | No `compute: bsl` in shape A, so there is nothing to guard. |
| Filter translation (§8.2) | Not needed. Data Studio pushes every operator down (LS-67). |
| One-to-many (AD-36) | A row-level join fans out the measures of the "one" side. The API cannot reject the request, because shape A never sees it. Rule needed: exclude one-side measures in this mode, or pre-aggregate them. |
| `compute: bsl` / `both` | Only the `data_studio` field exists. Median, quantiles, `.all()` and approx distinct need a normal (ROWS) data source. U-25 checks whether one connector can mix both. |
| `auth_hook`, RLS (D-13) | BSL is not in the data path. BigQuery IAM of the token holder decides, or an SQL `WHERE` on the verified email (LS-68 pattern). |
| Injection | Shape A contains no request input. Shape B contains filter literals that Ibis escapes. BigQuery parameters would be cleaner, but there is no `DATE` type (LS-66). |

**5. Auth.**

| Option | Who queries BigQuery | Effect on #12, A-3, #3 |
|---|---|---|
| User token (`ScriptApp.getOAuthToken()`) | The viewer (AD-04 viewer's credentials). Each viewer needs `bigquery.dataViewer` on the tables and `bigquery.jobUser` on the billing project, as with the native connector. | Fits AD-04. A-3 still protects `/schema` and `/bq/sql`. Adds `bigquery.readonly` to the consent screen and possibly to the Gallery verification (LS-69, unconfirmed). |
| Service-account key in `ScriptProperties` (LS-59) | One service account | Conflicts with #12 (no shared key in the connector; script editors can read it, LS-57). **Not recommended.** |
| API-minted token | The API verifies the A-3 identity token and mints a short-lived token for a service account through IAM Credentials `generateAccessToken`. The API itself runs with workload identity. It returns the SQL and the token, and the connector puts both in the config. | No key in Apps Script. Viewers need no BigQuery IAM. `auth_hook` decides who gets a token. Row-level control is possible with the LS-68 `WHERE`. Cost: one URL Fetch per `getData`, which can be cached in `UserCache` while the token lives (≤ 1 h). Risk: Data Studio holds a 1 h bearer token for the service account. Recommended for a shared or Gallery deployment. Needs a check (T-7). |

**6. Scope.**

- This mode is BigQuery-only. D-02 says all Ibis backends.
- Recommendation: an optional per-deployment mode ("BigQuery direct") on top of v1, not a change of v1.
- What stays shared: the `/schema` contract, the classifier (AD-24..AD-38) and the field spec (#6). The mode needs:
  - one extra endpoint (`/bq/sql` or a config endpoint);
  - a `getData` branch;
  - a manifest with `advancedServices.data`;
  - the rules for AD-36 and `compute: bsl` above.
- Revisit this if U-26 shows that the current path is too slow for typical pages even with caching. Then BigQuery direct becomes the default for BigQuery deployments.

## 5. Live runbook (U-21..U-28)

Needs: a Google account with a BigQuery project (you need `bigquery.jobUser` on it, plus dataset create), and the Chrome MCP set-up from `docs/datastudio-driving.md`. Takes about 30 minutes.

**Set-up**

1. Load the data:
   ```
   cd prototype/api && .venv/bin/python bq_spike.py export /tmp/bq21
   ```
   Then run the three printed `bq` commands with your project in place of `my-project`. Use the same location for every dataset (e.g. `--location=EU` on `bq mk`).
2. Start the API with BigQuery SQL:
   ```
   BQ_DATASET=<project>.bsl_spike .venv/bin/uvicorn bq_spike:app --port 8799
   ```
   Then run `make tunnel` (see `docs/dev-loop.md`). `bq_spike:app` is the prototype app plus `/bq/*`, so `/data` still works.
3. New Apps Script project: paste `prototype/connector/CodeBigQuery.gs` and the manifest `appsscript.bigquery.json`. Use the head deployment ID as the `connectorId`.
4. Create four data sources from the same connector, one for each mode: `A`, `A_CACHED`, `B` and `ROWS`. Use the billing project = your project.
5. Native baseline: `BQ_DATASET=<project>.bsl_spike .venv/bin/python bq_spike.py sql-a > /tmp/bq21/a.sql`, then `bq mk --use_legacy_sql=false --view "$(cat /tmp/bq21/a.sql)" <project>:bsl_spike.base_relation`. Connect the native BigQuery connector to that view.
6. One report page per data source, with the same charts as the prototype report:
   - a table origin × (flight_count, avg_distance, unique_carriers, on_time_rate) with a summary row;
   - a scorecard;
   - a monthly time series on dep_date;
   - a table filtered to carrier IN (AA, DL);
   - a date range control.

**Checks**

| ID | Question | How to read it |
|---|---|---|
| U-21 | Does Data Studio call `getData` once per chart in this mode? Does the request have `fields`, `dimensionsFilters` and `dateRange`? | Executions page: count the `BQ21 {...}` log lines per page load. Also look at `prototype/fixtures/bq/*.json`. |
| U-22 | Which SQL does BigQuery receive for the table, the summary row, the scorecard, the month series, the filter and the date range? Does it match `ds_wrapper` (E-45)? | `SELECT creation_time, TIMESTAMP_DIFF(end_time, start_time, MILLISECOND) AS ms, cache_hit, total_bytes_processed, query FROM \`region-eu\`.INFORMATION_SCHEMA.JOBS_BY_USER WHERE creation_time > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR) AND query LIKE '%bsl_spike%' ORDER BY creation_time` (change the region to match the dataset). |
| U-23 | Do the formula fields, the hidden helpers, the descriptions and `isReaggregatable` work? | Data source field list (descriptions, hidden). Then the chart values and the formulas in the U-22 SQL. |
| U-24 | Does dep_date work as a BigQuery `DATE`, or only as `'YYYYMMDD'`? | Run the month series once with each `BQ_DATE_AS_STRING` setting. |
| U-25 | Can `getData` return rows (mode `ROWS`) when `advancedServices.data` is true? | Page for ROWS: values, or an error. |
| U-26 | Page-load time, first load and reload: ROWS vs A vs A_CACHED vs native. | Time from navigation until no chart shows a spinner (`evaluate_script` poll). Use a fresh date range for each "first load", so that the Data Studio cache misses. Also record the Executions durations. |
| U-27 | Are the distinct counts and means correct in the real report? | Dump the components and run `prototype/verify_dashboard.py` (same data as the prototype). |
| U-28 | On reload, does Data Studio skip `getData`, as in E-41? Does BigQuery report `cache_hit`? | Executions page and the `cache_hit` column from U-22. |
| T-7 | Does an API-minted service-account token work in the config? Does it ever reach the browser? | Put a token from `gcloud auth print-access-token --impersonate-service-account=…` in the config temporarily. Search the browser network log for `ya29.`. |

**Rules for the decision**

- If U-21 shows one call per data source, shape B is dead and shape A is the only option.
- If U-22 shows no wrapping (Data Studio runs our SQL as-is), only shape B can work, and the fixed-grain limits of §7.7 apply to everything.
- If U-23 shows that formulas do not bind, the mode loses its reason to exist, because the native connector on a view gives the same result.

## 6. Files

- `research/spikes/spike_bq_advanced_services.py`: the offline proof (E-44..E-46). Run with `prototype/api/.venv/bin/python`.
- `prototype/api/bq_sql.py`: shape A builder, shared by the spike and the API.
- `prototype/api/bq_spike.py`: `/bq/schema` and `/bq/sql` on top of the prototype API, plus `export` for the BigQuery data.
- `prototype/connector/CodeBigQuery.gs` and `appsscript.bigquery.json`: connector with modes A, A_CACHED, B and ROWS.
- Venv: the README venv plus `ibis-framework[bigquery]==11.0.0` (for the BigQuery dialect).
