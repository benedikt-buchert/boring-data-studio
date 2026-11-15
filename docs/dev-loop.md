# Dev loop

- API: `make api` (uvicorn, port 8799, reload; uv builds the env from `prototype/api/requirements.txt`). Every getData body lands in `prototype/fixtures/<ms>.json`.
- Public URL: `make tunnel` (ngrok static domain, O-08). One-time: create an ngrok account, run `ngrok config add-authtoken <token>`, claim the free static domain and write it to `prototype/api/NGROK_DOMAIN` (git-ignored). The URL never changes, so Data Studio needs no re-entry. Fallback: `make tunnel-serveo` (stable only for the ssh session). Do not use localhost.run (rotates domains).
- Auth: the connector uses PATH_KEY. The API enforces `X-API-Key` when `prototype/api/API_KEY` exists (git-ignored, create with any random string).
- After a new tunnel URL: in the Apps Script editor run `resetAuth` once, then reload the report. Data Studio shows the Path / Key form; enter the new URL and the key. All data sources and reports of that user follow; no per-data-source edit.
- Offline check: `make check` (also runs in CI on every PR and push to main) runs the schema self-check and replays every fixture against the API in-process (no Google needed). Run it before pushing connector or model changes.
- Dashboard numbers: dump the components (see `datastudio-driving.md`) and run `prototype/verify_dashboard.py <dump.json>`.
