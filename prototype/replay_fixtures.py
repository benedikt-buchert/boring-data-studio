"""Replay every captured getData body through the API in-process. Fails on any non-2xx except the R-09 guard (400)."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "api"))
from fastapi.testclient import TestClient
import app

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
print(f"{bad} failures")
sys.exit(1 if bad else 0)
