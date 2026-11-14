# BSL 0.3.19 gotchas (cost us 4 debug cycles)

- Filter dicts go through `model.query(dimensions=..., measures=..., filters=[{"operator": "AND", "conditions": [...]}])`. `model.filter(x)` takes only a callable; a dict or list raises `SignatureValidationError ... is not a Callable`.
- `time_range` needs the time dimension in the query. Send the Data Studio date range as two `>=`/`<=` conditions on the time dimension instead.
- After a `joins:` block every name is prefixed: dimensions `flights.origin`, `airports.city`; measures `flights.flight_count`. `query()` accepts the plain own-model names (`flight_count`, `origin`) and returns plain columns for them; joined dims must be requested as `airports.city` and come back under that column name. Strip the own-model prefix for IDs; map `.` to `__` for Data Studio IDs (LS-02).
- Measures of joined models (`airports.airport_count`) appear in `get_measures()`; skip them unless the model exposes them on purpose.
- `Measure.expr` is a Deferred or a callable: `expr.resolve(table) if hasattr(expr, "resolve") else expr(table)`. The resolved Ibis op type (`Sum`, `Mean`, `CountDistinct`, `Median`, `CountStar`) is the classifier input.
- A calculated measure is a function of a scope. Classify it by calling it with a recording scope (see `prototype/api/app.py`, `RecordingScope`); the same trick renders the Data Studio formula (`FormulaScope`). Give the scope every reversed operator (`__rsub__`, `__rtruediv__`): `1 - _.x / _.y` fails without them.
- A `.all()` calculated measure cannot become a formula; expose it only with `compute: bsl` (fixed grain). Its value must be a fraction when the Data Studio semantic type is PERCENT (Data Studio multiplies by 100).
- Requesting `x` and the hidden raw dimension `x__value` in one request maps to the same column: dedupe before `query()` or Ibis raises `Duplicate column name`.
