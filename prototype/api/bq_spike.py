"""PROTOTYPE - Wayfinder #21 live spike: BigQuery advanced services with the BSL schema.

Adds two routes to the prototype API (app.py) for connector/CodeBigQuery.gs:
  GET  /bq/schema         the normal schema, minus fields that shape A cannot serve (compute: bsl)
  POST /bq/sql?shape=A|B  BigQuery SQL for a getData request. Every body is logged to
                          ../fixtures/bq/<ms>.json, so the fixtures show which requests reach getData.

Run:   BQ_DATASET=my-project.bsl_spike .venv/bin/uvicorn bq_spike:app --port 8799
       BQ_DATE_AS_STRING=1 returns dep_date as 'YYYYMMDD' (the current contract) in place of DATE.
Data:  .venv/bin/python bq_spike.py export <dir>   writes flights.csv / airports.csv + the bq load commands.
       .venv/bin/python bq_spike.py sql-a          prints the shape A SQL (native-connector baseline view).
"""
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path

import boring_semantic_layer as bsl
import ibis
from fastapi import Request

import app as proto
from app import BY_ID, CFG, FIX, MEASURE_MAP, RAW_DIMS, BSL_NAME, SCHEMA, app, translate_filters
from bq_sql import base_relation

FLIGHTS = {"origin": "string", "carrier": "string", "dep_date": "date", "distance": "float64", "delay": "int64"}
AIRPORTS = {"code": "string", "city": "string", "country": "string", "state": "string"}
DATASET = os.environ.get("BQ_DATASET", "my-project.bsl_spike")
DATE_AS_STRING = os.environ.get("BQ_DATE_AS_STRING") == "1"
project, dataset = DATASET.split(".", 1)
# CFG already holds the helper measures (app.py adds HELPERS before its second from_config).
M_BQ = bsl.from_config(CFG, tables={
    "flights_tbl": ibis.table(FLIGHTS, name="flights", catalog=project, database=dataset),
    "airports_tbl": ibis.table(AIRPORTS, name="airports", catalog=project, database=dataset)})["flights"]
BASE, AGG, FORMULAS, EXCLUDED = base_relation(M_BQ, date_as_string=DATE_AS_STRING)
BASE_SQL = ibis.to_sql(BASE, dialect="bigquery")
BASE_COLS = set(BASE.columns)
ref_ok = lambda f: all(r in BASE_COLS for r in re.findall(r"\$(\w+)", f.get("formula", "")))
BQ_SCHEMA = [f for f in SCHEMA if (f["id"] in BASE_COLS or "formula" in f) and ref_ok(f)]


@app.get("/bq/schema")
def bq_schema():
    return {"schema": BQ_SCHEMA, "excluded": [f["id"] for f in SCHEMA if f not in BQ_SCHEMA]}


def per_request_sql(body):
    """Shape B: the BSL query for this request; output columns renamed to the field IDs."""
    filters = translate_filters(body.get("dimensionsFilters"))
    ids = [f["name"] for f in body["fields"] if not (filters is not None and f.get("forFilterOnly"))]
    dims = [i for i in ids if BY_ID[i]["type"] == "DIMENSION"]
    bsl_dims = list(dict.fromkeys(RAW_DIMS.get(i, BSL_NAME.get(i, i)) for i in dims))
    measures = list(dict.fromkeys(MEASURE_MAP[i] for i in ids if BY_ID[i]["type"] == "METRIC" and i in MEASURE_MAP))
    conds = list(filters or [])
    dr = body.get("dateRange")
    if dr:  # date objects, not strings: a string becomes DATETIME('...') against a DATE column
        d = lambda s: dt.date.fromisoformat(s)
        conds += [{"field": "dep_date", "operator": ">=", "value": d(dr["startDate"])},
                  {"field": "dep_date", "operator": "<=", "value": d(dr["endDate"])}]
    q = M_BQ.query(dimensions=bsl_dims, measures=measures, filters=[{"operator": "AND", "conditions": conds}] if conds else None)
    inner = q.to_sql(dialect="bigquery")
    col = lambda i: (RAW_DIMS.get(i, BSL_NAME.get(i, i)) if BY_ID[i]["type"] == "DIMENSION" else MEASURE_MAP.get(i, i)).replace(".", "_")
    sel = []
    for i in dict.fromkeys(ids):
        if i in MEASURE_MAP or BY_ID[i]["type"] == "DIMENSION":
            c = f"`{col(i)}`"
            if i == "dep_date" and DATE_AS_STRING: c = f"FORMAT_DATE('%Y%m%d', {c})"
            sel.append(f"{c} AS `{i}`")
    return f"SELECT {', '.join(sel)} FROM (\n{inner}\n)", filters is not None


@app.post("/bq/sql")
async def bq_sql(req: Request, shape: str = "A"):
    body = await req.json()
    (FIX / "bq").mkdir(parents=True, exist_ok=True)
    (FIX / "bq" / f"{int(time.time() * 1000)}.json").write_text(json.dumps({"shape": shape, **body}, indent=1))
    if shape == "A":
        return {"sql": BASE_SQL, "shape": "A"}
    sql, applied = per_request_sql(body)
    return {"sql": sql, "shape": "B", "filtersApplied": applied}


if __name__ == "__main__":
    if sys.argv[1:2] == ["export"]:
        out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
        proto.df.assign(dep_date=proto.df.dep_date.dt.date).to_csv(out / "flights.csv", index=False)
        proto.airports.execute().to_csv(out / "airports.csv", index=False)
        sch = lambda s: ",".join(f"{k}:{v.replace('string', 'STRING').replace('float64', 'FLOAT').replace('int64', 'INTEGER').replace('date', 'DATE')}" for k, v in s.items())
        print(f"bq mk --dataset {project}:{dataset}")
        print(f"bq load --skip_leading_rows=1 --replace {project}:{dataset}.flights {out / 'flights.csv'} {sch(FLIGHTS)}")
        print(f"bq load --skip_leading_rows=1 --replace {project}:{dataset}.airports {out / 'airports.csv'} {sch(AIRPORTS)}")
    elif sys.argv[1:2] == ["sql-a"]:  # shape A only, e.g. for the native-connector baseline view
        print(BASE_SQL)
    else:  # self-check: print the SQL of both shapes
        print("-- excluded from shape A:", EXCLUDED)
        print("-- /bq/schema fields:", [f["id"] for f in BQ_SCHEMA])
        print(BASE_SQL)
        sample = {"fields": [{"name": "airports__city"}, {"name": "unique_carriers"}, {"name": "carrier__value"}, {"name": "avg_distance__sum"}],
                  "dateRange": {"startDate": "2026-09-01", "endDate": "2026-09-30"},
                  "dimensionsFilters": [[{"fieldName": "origin", "type": "INCLUDE", "operator": "IN_LIST", "values": ["JFK", "SFO"]}]]}
        print(per_request_sql(sample)[0])
