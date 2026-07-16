"""Generic, parametrized CRUD helpers.

Only the ``main_table`` of a query-spec is updatable; these helpers operate on a
single :class:`~sqlalchemy.Table` at a time. All statements use bound
parameters. ``save_master_detail`` runs a set of operations inside a single
transaction and rolls back on any error.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import Connection, Engine, Table, and_, delete, insert, update

OpKind = Literal["insert", "update", "delete"]


@dataclass(slots=True)
class Operation:
    """A single write operation to be executed within a transaction.

    * ``insert``: ``values`` holds the row to add.
    * ``update``: ``pk_values`` locates the row, ``values`` holds the changes.
    * ``delete``: ``pk_values`` locates the row to remove.
    """

    kind: OpKind
    table: Table
    values: dict[str, Any] | None = None
    pk_values: dict[str, Any] | None = None


def _pk_where(table: Table, pk_values: dict[str, Any]):
    """Build a WHERE clause matching ``pk_values`` on ``table``."""
    if not pk_values:
        raise ValueError("pk_values must not be empty")
    return and_(*(table.c[col] == val for col, val in pk_values.items()))


def _exec_insert(conn: Connection, table: Table, values: dict[str, Any]) -> Any:
    """Insert ``values`` into ``table``; return the primary key when available."""
    result = conn.execute(insert(table).values(**values))
    try:
        return result.inserted_primary_key
    except Exception:  # pragma: no cover - driver dependent
        return None


def _exec_update(
    conn: Connection, table: Table, pk_values: dict[str, Any], values: dict[str, Any]
) -> int:
    """Update the row identified by ``pk_values``; return affected row count."""
    result = conn.execute(
        update(table).where(_pk_where(table, pk_values)).values(**values)
    )
    return result.rowcount


def _exec_delete(conn: Connection, table: Table, pk_values: dict[str, Any]) -> int:
    """Delete the row identified by ``pk_values``; return affected row count."""
    result = conn.execute(delete(table).where(_pk_where(table, pk_values)))
    return result.rowcount


def insert_record(engine: Engine, table: Table, values: dict[str, Any]) -> Any:
    """Insert a single row and return its primary key (if the driver reports one)."""
    with engine.begin() as conn:
        return _exec_insert(conn, table, values)


def update_record(
    engine: Engine, table: Table, pk_values: dict[str, Any], values: dict[str, Any]
) -> int:
    """Update the row matching ``pk_values`` and return the affected row count."""
    with engine.begin() as conn:
        return _exec_update(conn, table, pk_values, values)


def delete_record(engine: Engine, table: Table, pk_values: dict[str, Any]) -> int:
    """Delete the row matching ``pk_values`` and return the affected row count."""
    with engine.begin() as conn:
        return _exec_delete(conn, table, pk_values)


def _apply(conn: Connection, op: Operation) -> Any:
    """Dispatch a single :class:`Operation` on an open connection."""
    if op.kind == "insert":
        if op.values is None:
            raise ValueError("insert operation requires 'values'")
        return _exec_insert(conn, op.table, op.values)
    if op.kind == "update":
        if op.pk_values is None or op.values is None:
            raise ValueError("update operation requires 'pk_values' and 'values'")
        return _exec_update(conn, op.table, op.pk_values, op.values)
    if op.kind == "delete":
        if op.pk_values is None:
            raise ValueError("delete operation requires 'pk_values'")
        return _exec_delete(conn, op.table, op.pk_values)
    raise ValueError(f"Unknown operation kind: {op.kind!r}")  # pragma: no cover


def save_master_detail(
    engine: Engine, master_op: Operation, detail_ops: list[Operation]
) -> list[Any]:
    """Execute the master and detail operations in a single transaction.

    The master operation runs first, then each detail operation, all inside one
    ``engine.begin()`` block. Any exception rolls back the entire transaction so
    the database is never left in a partially updated state.

    Returns the list of per-operation results (master first, then details).
    """
    results: list[Any] = []
    with engine.begin() as conn:
        results.append(_apply(conn, master_op))
        for op in detail_ops:
            results.append(_apply(conn, op))
    return results
