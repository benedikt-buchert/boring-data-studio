"""Spike: evidence for docs/research.md section 7.7 (claims E-18 to E-20).

Compares two compute locations for a distinct count:
  data_studio: COUNT_DISTINCT($user__value); the API returns raw user values (grouped mode).
  bsl:         the API returns the finished distinct count for each requested group.
Run:  pip install "boring-semantic-layer==0.3.19" duckdb pandas pyarrow pyarrow_hotfix
      python spike_compute_location.py
"""
import boring_semantic_layer as bsl
import ibis
import numpy as np
import pandas as pd

rng = np.random.default_rng(7)
days = pd.date_range("2026-01-20", periods=28, freq="D")          # crosses a month boundary
# 2,000 users each day; a user can use more than one channel on a day.
rows = [(d, f"u{u}", c) for d in days
        for u in rng.choice(5000, 2000, replace=False)
        for c in rng.choice(["web", "ios", "android"], rng.integers(1, 4), replace=False)]
t = ibis.memtable(pd.DataFrame(rows, columns=["day", "user", "channel"]))
m = bsl.to_semantic_table(t, name="e").with_dimensions(
    day=lambda x: x.day, user=lambda x: x.user, channel=lambda x: x.channel,
    month=lambda x: x.day.truncate("M"),
).with_measures(users=lambda x: x.user.nunique())

truth_day = m.group_by("day").aggregate("users").execute().set_index("day").users

# E-18: compute=bsl returns one row per group. compute=data_studio returns one row per (group, user).
ds_rows = m.group_by("day", "user").aggregate().execute()
bsl_rows = m.group_by("day").aggregate("users").execute()
assert len(bsl_rows) == 28 and len(ds_rows) == 28 * 2000  # one row per (day, user)
assert ds_rows.groupby("day").user.nunique().to_dict() == truth_day.to_dict()   # both correct per day
print(f"rows returned: data_studio={len(ds_rows):,}  bsl={len(bsl_rows):,}")

# E-19: compute=bsl is wrong when Data Studio aggregates the rows again (day -> month).
truth_month = m.group_by("month").aggregate("users").execute().set_index("month").users
summed = bsl_rows.assign(month=bsl_rows.day.dt.to_period("M")).groupby("month").users.sum()
assert (summed.values > truth_month.sort_index().values).all()      # sums overcount
# ... and the summary row (total distinct users) cannot come from the per-day values.
total = m.aggregate("users").execute().iloc[0, 0]
assert bsl_rows.users.sum() > total and bsl_rows.users.max() < total
# compute=data_studio stays correct for month and total, because the raw values are in the rows.
ds_month = ds_rows.assign(month=ds_rows.day.dt.to_period("M")).groupby("month").user.nunique()
assert ds_month.tolist() == truth_month.sort_index().tolist() and ds_rows.user.nunique() == total

# E-20: compute=bsl is wrong when the request also contains extra grouping fields.
# Chart: users by day. Another metric in the same chart adds `channel__value` to the request.
mixed = m.group_by("day", "channel").aggregate("users").execute()
assert (mixed.groupby("day").users.sum() > truth_day).all()          # overcount
print("All spike checks passed.")
