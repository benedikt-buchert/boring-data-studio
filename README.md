# Boring Data Studio

A Data Studio (Looker Studio) community connector for the [Boring Semantic Layer](https://github.com/boringdata/boring-semantic-layer) (BSL).
You define metrics once in a BSL YAML model. Data Studio then gets them as fields with locked formulas, hidden helpers and descriptions, and ratios, means and distinct counts come out right in every total.

> **Status: feasibility spike.** The code in `prototype/` is throwaway. The live findings are in [`prototype/README.md`](prototype/README.md) and the full research is in [`research/docs/research.md`](research/docs/research.md) (section 7.8 = live evidence).

## How it works

```
BSL YAML model ──► FastAPI (/schema, /data) ──► public URL ──► Apps Script connector ──► Data Studio
prototype/api/flights.yml   prototype/api/app.py      tunnel        prototype/connector/Code.gs
```

- `/schema` classifies each BSL measure. Sums and counts become plain metrics. Means become hidden `__sum`/`__count` helpers plus a formula. Calculated measures become `$`-formulas. Measures that can't be re-aggregated become fixed-grain fields.
- `/data` translates Data Studio getData requests (fields, filters, date range) into BSL queries.
- The connector uses `PATH_KEY` auth. Each user enters the API URL and an API key once.

## Requirements

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- A Google account, for Apps Script and Data Studio
- A way to expose a local port publicly (`ssh` to serveo.net, ngrok or cloudflared)

## Setup

### 1. Run the API

```sh
cd prototype/api
uv venv -p 3.12 .venv
uv pip install -p .venv/bin/python "boring-semantic-layer==0.3.19" "ibis-framework[duckdb]==11.0.0" \
  fastapi uvicorn pandas pyarrow pyarrow_hotfix
openssl rand -hex 16 > API_KEY      # git-ignored; the API requires X-API-Key while this file exists
cd ../..
make check                          # offline gate: schema self-check + replay of every fixture
make api                            # uvicorn on port 8799, with reload
```

The API serves a built-in synthetic flights dataset (90 days, with NULLs on purpose), so you don't need a database.

### 2. Expose it publicly

```sh
make tunnel     # ssh -R to serveo.net; the printed URL stays the same for the whole ssh session
```

Don't use localhost.run, because its domain changes every few minutes. Data Studio also caches failed queries until the chart or data source config changes.

### 3. Deploy the connector

1. Go to [script.google.com](https://script.google.com) and create a new project. Paste in `prototype/connector/Code.gs`.
2. Under Project Settings, enable "Show appsscript.json manifest" and paste in `prototype/connector/appsscript.json`.
3. Go to Deploy → Test deployments and copy the head deployment ID. This ID is the `connectorId`. Code changes to the head deployment go live immediately, without a redeploy.

### 4. Connect Data Studio

1. Open `https://lookerstudio.google.com/datasources/create?connectorId=<DEPLOYMENT_ID>`.
2. Authorize the connector. In the Path / Key form, enter the tunnel URL as the path and the contents of `API_KEY` as the key.
3. Create the data source and build a report.

Each getData request body is saved to `prototype/fixtures/<ms>.json`. These files are the golden fixtures that `make check` replays.

**When the tunnel URL changes:** run `resetAuth` once in the Apps Script editor, then reload the report and enter the new URL. All of that user's data sources follow.

## Repo layout

| Path | What |
|---|---|
| `prototype/api/` | FastAPI app and BSL model (`flights.yml`) |
| `prototype/connector/` | Apps Script community connector |
| `prototype/fixtures/` | Recorded getData requests, replayed by `make check` |
| `prototype/verify_dashboard.py`, `truth.py` | Compare dashboard numbers against independent pandas truth |
| `docs/` | Dev loop, BSL gotchas, and notes on driving Data Studio from a browser |
| `research/` | Research document and spikes |
