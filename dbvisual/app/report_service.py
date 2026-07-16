"""Report orchestration — read-only data retrieval, params, filters, aggregation.

UI-agnostic and testable. A *Report* is a ``kind='report'`` definition holding a
:class:`ReportSpec`. Unlike sheets/forms it is **read-only** and may run either a
query-spec (via the core compiler) or a custom **read-only** SQL string executed
with bound parameters. Nothing here writes to the target database.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import Engine, MetaData, text

from dbvisual.app.form_service import AvailableValues, resolve_available_values
from dbvisual.app.sheet_service import (
    resolve_engine,
)
from dbvisual.core.compiler import compile_select
from dbvisual.core.queryspec import QuerySpec

__all__ = [
    "ReportParam",
    "FilterCondition",
    "FilterGroup",
    "ReportSpec",
    "resolve_engine",
    "load_report_rows",
    "run_custom_sql",
    "ensure_readonly",
    "resolve_param_options",
    "evaluate_filter",
    "filter_rows",
    "full_text_filter",
    "aggregate_summary",
    "column_totals",
]

Agg = Literal["sum", "avg", "count", "min", "max"]

# Leading keywords allowed for custom report SQL (read-only).
_READONLY_START = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
# Statement-starting keywords that indicate a write / DDL.
_WRITE = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|"
    r"merge|replace|call|do)\b",
    re.IGNORECASE,
)


class ReportParam(BaseModel):
    """A runtime prompt parameter for a report."""

    name: str
    label: str = ""
    type: str = "string"
    multi: bool = False
    default: Any = None
    width: int = 200
    available: AvailableValues = Field(default_factory=AvailableValues)
    depends_on: str | None = None  # cascade: parent parameter name
    order: int = 0


class FilterCondition(BaseModel):
    """A single end-user filter condition on a result column."""

    kind: Literal["condition"] = "condition"
    field: str
    op: Literal["eq", "ne", "lt", "le", "gt", "ge", "contains", "in"]
    value: Any = None


class FilterGroup(BaseModel):
    """A nested AND/OR group of conditions/sub-groups (hierarchical)."""

    kind: Literal["group"] = "group"
    op: Literal["and", "or"] = "and"
    children: list["FilterCondition | FilterGroup"] = Field(default_factory=list)


FilterGroup.model_rebuild()


class ReportSpec(BaseModel):
    """Persisted shape of a report definition."""

    connection_id: int
    source: Literal["builder", "custom"] = "builder"
    spec: QuerySpec | None = None
    custom_sql: str | None = None
    params: list[ReportParam] = Field(default_factory=list)

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, raw: str) -> "ReportSpec":
        return cls.model_validate_json(raw)


# -- read-only custom SQL ---------------------------------------------------


def ensure_readonly(sql: str) -> None:
    """Raise ``ValueError`` if ``sql`` is not a single read-only statement."""
    stripped = sql.strip().rstrip(";")
    if ";" in stripped:
        raise ValueError("Solo una singola istruzione SELECT è ammessa.")
    if not _READONLY_START.match(stripped):
        raise ValueError("La query del report deve iniziare con SELECT o WITH.")
    if _WRITE.search(stripped):
        raise ValueError(
            "La query del report non può contenere istruzioni di scrittura."
        )


def run_custom_sql(
    engine: Engine, sql: str, params: dict[str, Any] | None = None
) -> tuple[list[str], list[dict[str, Any]]]:
    """Execute a read-only custom SQL string with bound parameters."""
    ensure_readonly(sql)
    with engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        fields = list(result.keys())
        rows = [dict(r) for r in result.mappings()]
    return fields, rows


def load_report_rows(
    engine: Engine,
    metadata: MetaData,
    report: ReportSpec,
    param_values: dict[str, Any] | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Load report rows from either the query-spec or the custom SQL."""
    params = param_values or {}
    if report.source == "custom":
        if not report.custom_sql:
            return [], []
        return run_custom_sql(engine, report.custom_sql, params)
    if report.spec is None:
        return [], []
    stmt = compile_select(report.spec, metadata, params)
    with engine.connect() as conn:
        result = conn.execute(stmt)
        fields = list(result.keys())
        rows = [dict(r) for r in result.mappings()]
    return fields, rows


# -- parameter options (incl. cascade) --------------------------------------


def resolve_param_options(
    engine: Engine,
    metadata: MetaData,
    param: ReportParam,
    *,
    main_table: str = "",
    parent_values: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Resolve a parameter's ``{value,label}`` options.

    For a cascade parameter (``depends_on`` + a ``query`` source), the parent's
    value is bound into the dependent query; otherwise the shared Phase 4
    resolver is used.
    """
    av = param.available
    if param.depends_on and av.source == "query" and av.query:
        parent = (parent_values or {}).get(param.depends_on)
        with engine.connect() as conn:
            result = conn.execute(text(av.query), {param.depends_on: parent})
            return [
                {"value": r[0], "label": str(r[1] if len(r) > 1 else r[0])}
                for r in result
            ]
    return resolve_available_values(
        engine, metadata, av, main_table=main_table, column=param.name
    )


# -- end-user filters (nested AND/OR) ---------------------------------------


def _match_condition(cond: FilterCondition, row: dict[str, Any]) -> bool:
    actual = row.get(cond.field)
    op = cond.op
    if op == "in":
        values = (
            cond.value if isinstance(cond.value, (list, tuple, set)) else [cond.value]
        )
        return actual in values
    if op == "contains":
        return actual is not None and str(cond.value).lower() in str(actual).lower()
    if actual is None or cond.value is None:
        return op == "ne" and actual != cond.value
    if op == "eq":
        return actual == cond.value
    if op == "ne":
        return actual != cond.value
    if op == "lt":
        return actual < cond.value
    if op == "le":
        return actual <= cond.value
    if op == "gt":
        return actual > cond.value
    if op == "ge":
        return actual >= cond.value
    return False


def evaluate_filter(node: "FilterCondition | FilterGroup", row: dict[str, Any]) -> bool:
    """Evaluate a (possibly nested) filter node against a row."""
    if isinstance(node, FilterGroup):
        results = [evaluate_filter(child, row) for child in node.children]
        if not results:
            return True
        return all(results) if node.op == "and" else any(results)
    return _match_condition(node, row)


def filter_rows(
    rows: list[dict[str, Any]], node: "FilterCondition | FilterGroup | None"
) -> list[dict[str, Any]]:
    """Return only the rows satisfying the filter tree (grid-side filtering)."""
    if node is None:
        return rows
    return [r for r in rows if evaluate_filter(node, r)]


def full_text_filter(
    rows: list[dict[str, Any]], text_query: str, fields: list[str]
) -> list[dict[str, Any]]:
    """Filter rows whose any listed field contains ``text_query`` (case-insensitive)."""
    q = (text_query or "").strip().lower()
    if not q:
        return rows
    out = []
    for r in rows:
        hay = " ".join(
            "" if r.get(f) is None else str(r.get(f)) for f in fields
        ).lower()
        if q in hay:
            out.append(r)
    return out


# -- aggregation ------------------------------------------------------------


def _to_num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _aggregate(values: list[float], agg: Agg) -> float:
    if agg == "count":
        return float(len(values))
    if not values:
        return 0.0
    if agg == "sum":
        return sum(values)
    if agg == "avg":
        return sum(values) / len(values)
    if agg == "min":
        return min(values)
    return max(values)


def aggregate_summary(
    rows: list[dict[str, Any]],
    *,
    category: str,
    value: str,
    series: str | None = None,
    agg: Agg = "sum",
) -> dict[str, Any]:
    """Aggregate ``value`` by ``category`` (and optional ``series``).

    Returns ``{"categories": [...], "series": [{"name", "data": [...]}], "matrix"}``
    suitable for an ECharts bar/line option. This is the *summary/pivot* result:
    the aggregated numbers, independent of the chart rendering.
    """
    categories = sorted(
        {r.get(category) for r in rows if r.get(category) is not None},
        key=lambda x: str(x),
    )
    series_names = (
        sorted(
            {r.get(series) for r in rows if r.get(series) is not None},
            key=lambda x: str(x),
        )
        if series
        else [None]
    )
    matrix: dict[Any, dict[Any, float]] = {}
    for sname in series_names:
        buckets: dict[Any, list[float]] = {c: [] for c in categories}
        for r in rows:
            if series is not None and r.get(series) != sname:
                continue
            cat = r.get(category)
            if cat not in buckets:
                continue
            num = _to_num(r.get(value))
            if num is not None or agg == "count":
                buckets[cat].append(num if num is not None else 0.0)
        matrix[sname] = {c: _aggregate(v, agg) for c, v in buckets.items()}

    series_out = [
        {
            "name": "" if sname is None else str(sname),
            "data": [matrix[sname][c] for c in categories],
        }
        for sname in series_names
    ]
    return {
        "categories": [str(c) for c in categories],
        "series": series_out,
        "matrix": matrix,
    }


def column_totals(rows: list[dict[str, Any]], aggs: dict[str, Agg]) -> dict[str, float]:
    """Compute per-column aggregates over ``rows`` (used for report totals)."""
    totals: dict[str, float] = {}
    for field_name, agg in aggs.items():
        nums = [n for n in (_to_num(r.get(field_name)) for r in rows) if n is not None]
        totals[field_name] = _aggregate(nums, agg)
    return totals
