"""The query-spec compiler: turns a :class:`QuerySpec` into a SQLAlchemy ``Select``.

This is the heart of dbvisual. The produced :class:`~sqlalchemy.Select` object is
dialect-independent: the same spec yields the same statement regardless of the
target database. All filter values are bound as parameters — never concatenated
into SQL — which prevents SQL injection.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    ColumnElement,
    MetaData,
    Select,
    Table,
    and_,
    select,
)

from dbvisual.core.queryspec import Column, Filter, QuerySpec

# Map query-spec operators to the corresponding SQLAlchemy column operations.
_SIMPLE_OPS = {
    "eq": lambda col, val: col == val,
    "ne": lambda col, val: col != val,
    "lt": lambda col, val: col < val,
    "le": lambda col, val: col <= val,
    "gt": lambda col, val: col > val,
    "ge": lambda col, val: col >= val,
    "like": lambda col, val: col.like(val),
}


def _resolve_table(metadata: MetaData, name: str) -> Table:
    """Return the reflected :class:`Table` for ``name`` (raw or schema-qualified)."""
    tbl = metadata.tables.get(name)
    if tbl is not None:
        return tbl
    for key, value in metadata.tables.items():
        if key.split(".")[-1] == name:
            return value
    raise KeyError(f"Table not found in metadata: {name!r}")


def _resolve_column(metadata: MetaData, ref: Column) -> ColumnElement[Any]:
    """Return the SQLAlchemy column referenced by a query-spec :class:`Column`."""
    tbl = _resolve_table(metadata, ref.table)
    try:
        return tbl.c[ref.name]
    except KeyError as exc:  # pragma: no cover - defensive
        raise KeyError(f"Column {ref.name!r} not found in table {ref.table!r}") from exc


def _build_condition(
    column: ColumnElement[Any], flt: Filter, value: Any
) -> ColumnElement[bool]:
    """Build a single bound filter condition for ``flt`` given its ``value``."""
    if flt.op == "in":
        values = value if isinstance(value, (list, tuple, set)) else [value]
        return column.in_(list(values))
    try:
        factory = _SIMPLE_OPS[flt.op]
    except KeyError as exc:  # pragma: no cover - guarded by Literal type
        raise ValueError(f"Unsupported filter op: {flt.op!r}") from exc
    return factory(column, value)


def compile_select(
    spec: QuerySpec, metadata: MetaData, params: dict[str, Any]
) -> Select:
    """Compile ``spec`` into a SQLAlchemy :class:`Select`.

    * Selects the spec's columns (applying aliases).
    * Joins each related table via its foreign-key columns.
    * Applies every filter as a bound-parameter condition.
    * Supports multi-value ``in`` filters.

    ``params`` maps parameter names to their runtime values. A filter whose
    parameter is absent from ``params`` is skipped, allowing optional filters.
    """
    main = _resolve_table(metadata, spec.main_table)

    # --- SELECT list -------------------------------------------------------
    selected: list[ColumnElement[Any]] = []
    for col in spec.columns:
        element = _resolve_column(metadata, col)
        if col.alias:
            element = element.label(col.alias)
        selected.append(element)
    # Fall back to the whole main table when no columns are specified.
    stmt = select(*selected) if selected else select(main)

    # --- JOINs for related tables -----------------------------------------
    from_clause: Any = main
    for rel in spec.related:
        remote = _resolve_table(metadata, rel.table)
        onclause = main.c[rel.local_col] == remote.c[rel.remote_col]
        from_clause = from_clause.join(remote, onclause)
    if spec.related:
        stmt = stmt.select_from(from_clause)

    # --- WHERE conditions --------------------------------------------------
    conditions: list[ColumnElement[bool]] = []
    for flt in spec.filters:
        if flt.param not in params:
            continue  # optional filter with no supplied value
        column = _resolve_column(metadata, flt.column)
        conditions.append(_build_condition(column, flt, params[flt.param]))
    if conditions:
        stmt = stmt.where(and_(*conditions))

    return stmt
