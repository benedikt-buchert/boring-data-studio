"""PROTOTYPE - Wayfinder #21. BigQuery SQL for the advanced-services connector (CodeBigQuery.gs).

Shape A (base relation): one row-level SQL per model, independent of the request. One column per
dimension, hidden raw dimension and metric input; column names are the Data Studio field IDs, so the
normal getSchema fields (formulas, hidden helpers, descriptions) bind to them by name.
Shape B (per request): the BSL query for one getData request, compiled to BigQuery SQL.

Used by bq_spike.py (live spike) and research/spikes/spike_bq_advanced_services.py (offline proof).
"""
import ibis

short = lambda n: n[8:] if n.startswith("flights.") else n
DS_ID = lambda n: short(n).replace(".", "__")


def resolve(expr, table):
    return expr.resolve(table) if hasattr(expr, "resolve") else expr(table)


def _compute(obj):
    return ((obj.metadata or {}).get("looker_studio") or {}).get("compute", "auto")


def base_relation(M, date_as_string=False):
    """Row-level relation + the Data Studio aggregation for each generated column.

    Returns (ibis table, {column: SUM|MIN|MAX}, {metric: SQL formula over columns}, excluded).
    Only the AD-26 translation rows. compute: bsl is excluded: a request-independent relation has
    no requested grain.
    """
    J = M.to_untagged()
    cols, agg, formulas, excluded = {}, {}, {}, []
    for name, d in M.get_dimensions().items():
        e = resolve(d.expr, J)
        if date_as_string and d.is_time_dimension:
            e = e.strftime("%Y%m%d")  # matches the current contract: YEAR_MONTH_DAY as STRING
        cols[DS_ID(name)] = e
    for name, m in M.get_measures().items():
        if "." in short(name):
            continue  # joined-model measures: not exposed (AD-37)
        name = short(name)
        if _compute(m) == "bsl":
            excluded.append((name, "compute: bsl - needs the requested grain"))
            continue
        node = resolve(m.expr, J).op()
        kind = type(node).__name__
        where = getattr(node, "where", None)
        arg = node.arg.to_expr() if kind != "CountStar" else None  # CountStar.arg is the table
        if arg is not None and arg.type().is_boolean():
            arg = arg.cast("int64")  # SUM(bool) is not valid BigQuery
        cond = (lambda e: ibis.ifelse(where.to_expr(), e, ibis.null())) if where is not None else (lambda e: e)
        if kind == "CountStar":
            cols[name], agg[name] = cond(ibis.literal(1, "int64")), "SUM"
        elif kind == "Count":
            cols[name], agg[name] = cond(arg.notnull().cast("int64")), "SUM"
        elif kind in ("Sum", "Min", "Max"):
            cols[name], agg[name] = cond(arg), kind.upper()
        elif kind == "Mean":
            cols[f"{name}__sum"], agg[f"{name}__sum"] = cond(arg), "SUM"
            cols[f"{name}__count"], agg[f"{name}__count"] = cond(arg.notnull().cast("int64")), "SUM"
            formulas[name] = f"SUM({name}__sum) / SUM({name}__count)"
        elif kind == "CountDistinct" and where is None:
            raw = f"{node.arg.name}__value"
            cols.setdefault(raw, arg)
            formulas[name] = f"COUNT(DISTINCT {raw})"
        else:
            excluded.append((name, f"{kind}: no translation row"))
    for name, c in M.get_calculated_measures().items():
        name = short(name)
        if _compute(c) == "bsl":
            excluded.append((name, "compute: bsl - needs the requested grain"))
            continue
        formulas[name] = c.expr(_FormulaScope(agg, formulas)).s
    return J.select(**cols), agg, formulas, excluded


class _FormulaScope:  # expands a reference to a mean into its helper formula (AD-33)
    def __init__(self, agg, formulas): self.agg, self.formulas = agg, formulas
    def __getattr__(self, n):
        return _F(f"({self.formulas[n]})" if n in self.formulas else f"{self.agg[n]}({n})")


class _F:
    def __init__(self, s): self.s = s
    def _op(self, o, other, rev=False):
        b = other.s if isinstance(other, _F) else repr(other)
        return _F(f"({b} {o} {self.s})" if rev else f"({self.s} {o} {b})")
    __add__ = lambda s, o: s._op("+", o); __sub__ = lambda s, o: s._op("-", o)
    __mul__ = lambda s, o: s._op("*", o); __truediv__ = lambda s, o: s._op("/", o)
    __radd__ = lambda s, o: s._op("+", o, True); __rmul__ = lambda s, o: s._op("*", o, True)
    __rsub__ = lambda s, o: s._op("-", o, True); __rtruediv__ = lambda s, o: s._op("/", o, True)
