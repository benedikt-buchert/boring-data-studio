"""PROTOTYPE — throwaway. Feasibility spike for research.md: BSL model -> Data Studio getSchema/getData.

Run:  .venv/bin/uvicorn app:app --port 8787
Every getData request body is logged to ../fixtures/<n>.json (golden fixtures, section 9.4).
"""
import asyncio, json, time
from pathlib import Path

import boring_semantic_layer as bsl
import yaml
import ibis
import numpy as np
import pandas as pd
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from ibis.expr import operations as ops

HERE = Path(__file__).parent
FIX = HERE.parent / "fixtures"

# --- data: 90 days, 4 origins, 3 carriers, NULLs on purpose (U-15, U-19) ---
rng = np.random.default_rng(1)
n = 3000
df = pd.DataFrame({
    "origin": rng.choice(["JFK", "LAX", "ORD", "SFO"], n),
    "carrier": rng.choice(["AA", "UA", "DL", None], n, p=[0.4, 0.3, 0.25, 0.05]),
    "dep_date": pd.Timestamp.today().normalize() - pd.to_timedelta(rng.integers(1, 90, n), "D"),
    "distance": rng.integers(100, 3000, n).astype(float),
    "delay": rng.integers(0, 120, n),
})
df.loc[df.origin == "SFO", "distance"] = None  # all-NULL group -> U-19
t = ibis.memtable(df).mutate(dep_date=ibis._.dep_date.cast("date"))
airports = ibis.memtable(pd.DataFrame({"code": ["JFK", "LAX", "ORD", "SFO"], "city": ["New York", "Los Angeles", "Chicago", "San Francisco"],
                                       "country": ["United States"] * 4, "state": ["New York", "California", "Illinois", "California"]}))
CFG = yaml.safe_load(open(HERE / "flights.yml"))
TABLES = {"flights_tbl": t, "airports_tbl": airports}
MODEL = bsl.from_config(CFG, tables=TABLES)["flights"]  # rebuilt below with helper measures declared
HELPERS = {}  # helper id -> BSL expression; declared in the config, never added with with_measures (breaks GROUP BY on joined models)
short = lambda name: name[8:] if name.startswith("flights.") else name  # own-model names stay plain
DS_ID = lambda name: short(name).replace(".", "__")  # LS-02: join dims are "airports.city" in BSL, ids must be [A-Za-z0-9_]
BSL_NAME = {}
VERSION = "proto-" + time.strftime("%Y%m%d")

# --- classifier (section 7.2) ---------------------------------------------
def resolve(expr, table):
    return expr.resolve(table) if hasattr(expr, "resolve") else expr(table)

def ls_meta(obj):
    return (obj.metadata or {}).get("looker_studio", {})

def field(id, name, kind, dtype, agg=None, formula=None, hidden=False, desc="", semantic=None, reagg=True):
    f = {"id": id, "name": name, "type": kind, "dataType": dtype, "description": f"{desc} [{VERSION}]".strip()}
    if agg: f["aggregation"] = agg
    if formula: f["formula"] = formula
    if hidden: f["isHidden"] = True
    if semantic: f["semanticType"] = semantic
    if not reagg: f["isReaggregatable"] = False
    return f

def build_schema():
    fields, measure_map, raw_dims = [], {}, {}
    for name, d in MODEL.get_dimensions().items():
        BSL_NAME[DS_ID(name)] = short(name); name = short(name)
        if d.is_time_dimension:
            fields.append(field(DS_ID(name), name, "DIMENSION", "STRING", semantic="YEAR_MONTH_DAY", desc=d.description or ""))
        else:
            fields.append(field(DS_ID(name), name, "DIMENSION", "STRING", desc=d.description or ""))
    for name, m in MODEL.get_measures().items():
        if "." in short(name): continue  # measures of joined models are out of scope
        name = short(name)
        node = resolve(m.expr, t).op()
        kind = type(node).__name__
        meta = ls_meta(m)
        desc = m.description or ""
        compute = meta.get("compute", "auto")
        if compute == "bsl":
            fields.append(field(name, name, "METRIC", "NUMBER", desc=desc + " (fixed grain: correct only at the shown grain)", reagg=False))
            measure_map[name] = name
            continue
        if kind in ("CountStar", "Sum"):
            fields.append(field(name, name, "METRIC", "NUMBER", agg="SUM", desc=desc)); measure_map[name] = name
        elif kind in ("Max", "Min"):
            fields.append(field(name, name, "METRIC", "NUMBER", agg=kind.upper(), desc=desc)); measure_map[name] = name
        elif kind == "Mean":
            col = node.arg.name
            fields.append(field(f"{name}__sum", f"{name} sum", "METRIC", "NUMBER", agg="SUM", hidden=True))
            fields.append(field(f"{name}__count", f"{name} count", "METRIC", "NUMBER", agg="SUM", hidden=True))
            HELPERS[f"{name}__sum"], HELPERS[f"{name}__count"] = f"_.{col}.sum()", f"_.{col}.count()"
            measure_map[f"{name}__sum"], measure_map[f"{name}__count"] = f"{name}__sum", f"{name}__count"
            fields.append(field(name, name, "METRIC", "NUMBER", agg="AUTO", formula=f"SUM(${name}__sum) / SUM(${name}__count)", desc=desc))
        elif kind == "CountDistinct":
            col = node.arg.name
            raw = f"{col}__value"
            if raw not in raw_dims:
                fields.append(field(raw, raw, "DIMENSION", "STRING", hidden=True)); raw_dims[raw] = col
            fields.append(field(name, name, "METRIC", "NUMBER", agg="AUTO", formula=f"COUNT_DISTINCT(${raw})", desc=desc))
            if compute == "both":
                fields.append(field(f"{name}__bsl", f"{name} (fixed grain)", "METRIC", "NUMBER", reagg=False,
                                    desc=desc + " (fixed grain: correct only at the shown grain, wrong in totals)"))
                measure_map[f"{name}__bsl"] = name
        # Median etc.: excluded (no allow_raw_mode in this prototype)
    for name, c in MODEL.get_calculated_measures().items():
        name = short(name)
        if ls_meta(c).get("compute") == "bsl":
            fields.append(field(name, name, "METRIC", "NUMBER", desc=(c.description or "") + " (fixed grain)", reagg=False, semantic=ls_meta(c).get("semantic_type")))
            measure_map[name] = name
            continue
        deps, safe = classify_calc(c.expr)
        if safe and all(d in {f["id"] for f in fields} for d in deps):
            formula = c.expr  # re-render with $ refs via recording scope
            fields.append(field(name, name, "METRIC", "NUMBER", agg="AUTO", formula=render_calc(c.expr), desc=c.description or ""))
    return fields, measure_map, raw_dims

SAFE = (ops.Field, ops.Add, ops.Subtract, ops.Multiply, ops.Divide, ops.Literal, ops.Negate, ops.Cast, ops.UnboundTable)
vt = ibis.table({k: "float64" for n in [*MODEL.get_measures(), *MODEL.get_calculated_measures()] for k in (n, short(n))}, name="agg")

class RecordingScope:
    def __init__(self): self.used_all = False
    def __getattr__(self, name): return vt[name]
    def all(self, x): self.used_all = True; return x

def classify_calc(fn):
    s = RecordingScope(); node = fn(s).op()
    deps = {f.name for f in node.find(ops.Field)}
    return deps, (not s.used_all and all(isinstance(n, SAFE) for n in node.find(ops.Node)))

class FormulaScope:
    # shortcut: only + - * / over base metrics; wraps each ref in SUM($id) which is right for SUM-aggregated bases only
    def __getattr__(self, name): return F(f"SUM(${name})")
class F:
    def __init__(self, s): self.s = s
    def _op(self, o, other, rev=False):
        b = other.s if isinstance(other, F) else repr(other)
        return F(f"({b} {o} {self.s})" if rev else f"({self.s} {o} {b})")
    __add__ = lambda s, o: s._op("+", o); __sub__ = lambda s, o: s._op("-", o)
    __mul__ = lambda s, o: s._op("*", o); __truediv__ = lambda s, o: s._op("/", o)
    __radd__ = lambda s, o: s._op("+", o, True); __rmul__ = lambda s, o: s._op("*", o, True)
    __rsub__ = lambda s, o: s._op("-", o, True); __rtruediv__ = lambda s, o: s._op("/", o, True)
def render_calc(fn): return fn(FormulaScope()).s

SCHEMA, MEASURE_MAP, RAW_DIMS = build_schema()
CFG["flights"]["measures"].update(HELPERS)
MODEL = bsl.from_config(CFG, tables=TABLES)["flights"]
BY_ID = {f["id"]: f for f in SCHEMA}

# --- request translation (section 8) ---------------------------------------
# Data Studio operator -> (INCLUDE, EXCLUDE) BSL operator. Anything else -> filtersApplied false (LS-16 fallback).
OPS = {"EQUALS": ("=", "!="), "IN_LIST": ("in", "not in"), "IS_NULL": ("is null", "is not null")}
def translate_filters(groups):
    out = []
    for group in groups or []:
        ors = []
        for c in group:
            if c["operator"] not in OPS: return None
            op = OPS[c["operator"]][c["type"] == "EXCLUDE"]
            fname = RAW_DIMS.get(c["fieldName"], BSL_NAME.get(c["fieldName"], c["fieldName"]))
            if op in ("in", "not in"): ors.append({"field": fname, "operator": op, "values": c["values"]})
            elif op.startswith("is "): ors.append({"field": fname, "operator": op})
            else: ors.append({"field": fname, "operator": op, "value": c["values"][0]})
        out.append({"operator": "OR", "conditions": ors} if len(ors) > 1 else ors[0])
    return out

app = FastAPI()

@app.get("/schema")
def schema(): return {"schema": SCHEMA}

@app.post("/data")
async def data(req: Request):
    body = await req.json()
    FIX.mkdir(exist_ok=True)
    (FIX / f"{int(time.time()*1000)}.json").write_text(json.dumps(body, indent=1))
    # shortcut: test switches as flag files (U-07, U-16); delete the files to turn them off
    if any(f["name"] == "max_delay" for f in body["fields"]) and (HERE / "DELAY_SECONDS").exists():
        await asyncio.sleep(float((HERE / "DELAY_SECONDS").read_text()))
    filters = None if (HERE / "FORCE_NO_PUSHDOWN").exists() else translate_filters(body.get("dimensionsFilters"))
    applied = filters is not None
    # LS-16: filters applied -> drop forFilterOnly fields; not applied -> return them so Data Studio filters
    ids = [f["name"] for f in body["fields"] if not (applied and f.get("forFilterOnly"))]
    dims = [i for i in ids if BY_ID[i]["type"] == "DIMENSION"]
    bsl_dims = list(dict.fromkeys(RAW_DIMS.get(i, BSL_NAME.get(i, i)) for i in dims))  # x and x__value share one column
    metrics = [i for i in ids if BY_ID[i]["type"] == "METRIC"]
    m = MODEL
    measures = [MEASURE_MAP[i] for i in metrics]
    # R-09 / E-25: a fixed-grain metric must not share a request with raw fields of other measures
    if any(BY_ID[i].get("isReaggregatable") is False for i in metrics) and any(i in RAW_DIMS for i in dims):
        return JSONResponse(status_code=400, content={"error": "fixed-grain metric cannot be combined with distinct-count metrics in one chart"})
    conds = list(filters or [])
    dr = body.get("dateRange")
    if dr:
        conds += [{"field": "dep_date", "operator": ">=", "value": dr["startDate"]},
                  {"field": "dep_date", "operator": "<=", "value": dr["endDate"]}]
    res = m.query(dimensions=bsl_dims, measures=list(dict.fromkeys(measures)),
                  filters=[{"operator": "AND", "conditions": conds}] if conds else None).execute()
    rows = []
    for _, r in res.iterrows():
        vals = []
        for i in ids:
            col = RAW_DIMS.get(i, BSL_NAME.get(i, i)) if BY_ID[i]["type"] == "DIMENSION" else MEASURE_MAP[i]
            v = r[col] if col in r.index else r[col.replace(".", "_")]
            if v is None or (isinstance(v, float) and np.isnan(v)): vals.append(None)
            elif i == "dep_date": vals.append(pd.Timestamp(v).strftime("%Y%m%d"))
            elif BY_ID[i]["type"] == "METRIC": vals.append(float(v))
            else: vals.append(str(v))
        rows.append({"values": vals})
    return {"schema": [BY_ID[i] for i in ids], "rows": rows, "filtersApplied": applied}

if __name__ == "__main__":  # self-check
    print(json.dumps(SCHEMA, indent=1))
    assert BY_ID["distance_per_flight"]["formula"] == "(SUM($total_distance) / SUM($flight_count))"
    assert BY_ID["unique_carriers"]["formula"] == "COUNT_DISTINCT($carrier__value)"
    assert BY_ID["pct_of_total"]["isReaggregatable"] is False and BY_ID["median_delay"]["isReaggregatable"] is False  # compute: bsl
    assert BY_ID["unique_carriers__bsl"]["isReaggregatable"] is False and "aggregation" not in BY_ID["unique_carriers__bsl"]  # LS-49
    assert BY_ID["on_time_rate"]["formula"] == "(1 - (SUM($delayed_flights) / SUM($flight_count)))"
