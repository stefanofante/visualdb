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
    and_,
    select,
)

from dbvisual.core.introspect import resolve_table
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


def _resolve_column(metadata: MetaData, ref: Column) -> ColumnElement[Any]:
    """Return the SQLAlchemy column referenced by a query-spec :class:`Column`."""
    tbl = resolve_table(metadata, ref.table)
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
    main = resolve_table(metadata, spec.main_table)

    joined = {spec.main_table, *(rel.table for rel in spec.related)}
    if any(
        ref.table not in joined
        for ref in [*spec.columns, *(flt.column for flt in spec.filters)]
    ):
        raise ValueError("A query column refers to a table without a join.")

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
        remote = resolve_table(metadata, rel.table)
        matching = [
            fk
            for fk in main.foreign_key_constraints
            if any(
                e.parent.name == rel.local_col and e.column is remote.c[rel.remote_col]
                for e in fk.elements
            )
        ]
        if len(matching) > 1:
            raise ValueError("Ambiguous lookup foreign key.")
        onclause = (
            and_(*(e.parent == e.column for e in matching[0].elements))
            if matching
            else main.c[rel.local_col] == remote.c[rel.remote_col]
        )
        from_clause = from_clause.outerjoin(remote, onclause)
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
