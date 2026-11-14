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
    }


def truth(df: pd.DataFrame, dim: str | None, date_range: dict, keep=None) -> dict:
    """{dimension value or 'Grand total': {metric: value}}; keep = row predicate for dimension filters."""
    d = df[(df.dep_date >= date_range["startDate"]) & (df.dep_date <= date_range["endDate"])].copy()
    if keep is not None:
        d = d[keep(d)]
    d["airports.city"] = d.origin.map(CITY)
    grand = d.distance.sum(min_count=1)
    out = {"Grand total": _metrics(d, grand)}
    if dim:
        for k, g in d.groupby(dim, dropna=False):
            out["null" if (k is None or (isinstance(k, float) and np.isnan(k))) else k] = _metrics(g, grand)
    return out
