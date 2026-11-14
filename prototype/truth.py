"""PROTOTYPE — independent ground truth: plain pandas on the raw seed rows. Shares no code with BSL or the API logic."""
import numpy as np
import pandas as pd

CITY = {"JFK": "New York", "LAX": "Los Angeles", "ORD": "Chicago", "SFO": "San Francisco"}


def _metrics(g: pd.DataFrame, grand_distance: float) -> dict:
    n = len(g)
    dist = g.distance.sum(min_count=1)  # all-NULL -> NaN, like SQL SUM (U-19)
    delayed = int((g.delay > 30).sum())
    return {
        "flight_count": n, "total_distance": dist, "distance_per_flight": dist / n,
        "avg_distance": g.distance.mean(), "unique_carriers": g.carrier.nunique(dropna=True),
        "delayed_flights": delayed, "on_time_rate": 1 - delayed / n, "median_delay": g.delay.median(),
        "pct_of_total": dist / grand_distance, "max_delay": g.delay.max(),
        "unique_carriers (fixed grain)": g.carrier.nunique(dropna=True),
        "total_delay": g.delay.sum(), "min_delay": g.delay.min(), "avg_delay": g.delay.mean(),
        "max_distance": g.distance.max(), "min_distance": g.distance.min(),
        # SQL semantics: NULL > c is NULL, SUM over only NULLs is NULL (an all-NULL group shows null, not 0)
        "long_haul_flights": (g.distance > 2000).where(g.distance.notna()).sum(min_count=1),
        "short_haul_flights": (g.distance < 500).where(g.distance.notna()).sum(min_count=1),
        "early_flights": int((g.delay < 5).sum()),
    }


DIMS = {"origin", "carrier", "airports.city", "airports.country", "airports.code", "dep_date"}
_key = lambda k: "null" if (k is None or (isinstance(k, float) and np.isnan(k))) else str(k)


def truth(df: pd.DataFrame, dim, date_range: dict, keep=None) -> dict:
    """{dim value (or 'v1 | v2' for several dims) or 'Grand total': {metric: value}}; keep = row filter."""
    d = df[(df.dep_date >= date_range["startDate"]) & (df.dep_date <= date_range["endDate"])].copy()
    if keep is not None:
        d = d[keep(d)]
    d["airports.city"] = d.origin.map(CITY)
    d["airports.code"], d["airports.country"] = d.origin, "United States"
    grand = d.distance.sum(min_count=1)
    out = {"Grand total": _metrics(d, grand)}
    dims = [dim] if isinstance(dim, str) else list(dim or [])
    for k, g in (d.groupby(dims, dropna=False) if dims else []):
        k = k if isinstance(k, tuple) else (k,)
        out[" | ".join(_key(x) for x in k)] = _metrics(g, grand)
    return out
