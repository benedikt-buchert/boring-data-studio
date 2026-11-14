"""PROTOTYPE — compare numbers read from the Data Studio dashboard with independent pandas truth (truth.py).

Usage: api/.venv/bin/python verify_dashboard.py dump.json
dump.json = {"dateRange": {...}, "filter": "carrier_not_AA" | null, "components": ["<innerText of each component>", ...]}
Exits non-zero on any mismatch.
"""
import json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "api"))
import app  # only for the raw seed rows (app.df)
from truth import truth

FILTERS = {None: None, "carrier_not_AA": lambda d: (d.carrier != "AA") | d.carrier.isna()}
doc = json.load(open(sys.argv[1]))
keep = FILTERS[doc.get("filter")]

def num(s):
    s = s.replace(",", "")
    return None if s in ("null", "-", "") else (float(s[:-1]) / 100 if s.endswith("%") else float(s))

def close(a, b):
    b = None if b != b else b  # NaN -> None
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= max(0.011, abs(b) * 5e-3)  # dashboard rounds to 2 decimals / 2 significant % digits

def table(text):
    lines = [l for l in text.split("\n") if l.strip() and l not in ("▼", "▲")]
    i = next(k for k, l in enumerate(lines) if re.fullmatch(r"\d+\.", l) or l == "Grand total")
    hdr, rows = lines[:i], []
    while i < len(lines):
        if re.fullmatch(r"\d+\.", lines[i]):
            rows.append(lines[i + 1:i + 1 + len(hdr)]); i += 1 + len(hdr)
        elif lines[i] == "Grand total":
            rows.append(["Grand total"] + lines[i + 1:i + len(hdr)]); i += len(hdr)
        else:
            i += 1
    return hdr, rows

checks = []
for c in doc["components"]:
    m = re.fullmatch(r"(\S+)\n([\d,.]+%?|null)", c.strip())
    if m:  # scorecard
        t = truth(app.df, None, doc["dateRange"], keep)["Grand total"]
        if m.group(1) in t:
            checks.append((f"scorecard {m.group(1)}", num(m.group(2)), t[m.group(1)]))
    elif re.search(r"\n1\.\n", c):
        hdr, rows = table(c)
        t = truth(app.df, hdr[0], doc["dateRange"], keep)
        for r in rows:
            for h, v in zip(hdr[1:], r[1:]):
                if r[0] not in t:
                    checks.append((f"{hdr[0]}={r[0]} {h}", num(v), "missing")); continue
                checks.append((f"{hdr[0]}={r[0]} {h}", num(v), t[r[0]][h]))

bad = 0
for name, ds, tv in checks:
    ok = tv != "missing" and close(ds, tv)
    bad += not ok
    print(("OK  " if ok else "FAIL") + f" {name}: dashboard={ds} truth={tv}")
print(f"\n{len(checks) - bad}/{len(checks)} values match independent truth")
sys.exit(1 if bad else 0)
