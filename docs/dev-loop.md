# Dev loop

- API: `make api` (uvicorn, port 8799, reload). Every getData body lands in `prototype/fixtures/<ms>.json`.
- Public URL: `make tunnel` (serveo; the URL is stable for the ssh session and serves JSON to non-browser clients). localhost.run rotates its domain every few minutes: do not use it. `npx cloudflared`/`ngrok` need the user to run or allow them.
- Auth: the connector uses PATH_KEY. The API enforces `X-API-Key` when `prototype/api/API_KEY` exists (git-ignored, create with any random string).
- After a new tunnel URL: in the Apps Script editor run `resetAuth` once, then reload the report. Data Studio shows the Path / Key form; enter the new URL and the key. All data sources and reports of that user follow; no per-data-source edit.
- Offline check: `make check` runs the schema self-check and replays every fixture against the API in-process (no Google needed). Run it before pushing connector or model changes.
- Dashboard numbers: dump the components (see `datastudio-driving.md`) and run `prototype/verify_dashboard.py <dump.json>`.
