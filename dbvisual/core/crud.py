"""Generic, parametrized CRUD helpers.

Only the ``main_table`` of a query-spec is updatable; these helpers operate on a
single :class:`~sqlalchemy.Table` at a time. All statements use bound
parameters. ``save_master_detail`` runs a set of operations inside a single
transaction and rolls back on any error.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from sqlalchemy import Connection, Engine, Table, and_, delete, insert, update

from dbvisual.core.events import CrudEvent, emit

OpKind = Literal["insert", "update", "delete"]


class ConflictError(RuntimeError):
    """Raised when an optimistic-locking guarded update matches 0 rows.

    Signals that the record changed (or was removed) after it was loaded, so the
    caller should reload and retry.
    """


@dataclass(slots=True)
class Operation:
    """A single write operation to be executed within a transaction.

    * ``insert``: ``values`` holds the row to add.
    * ``update``: ``pk_values`` locates the row, ``values`` holds the changes.
    * ``delete``: ``pk_values`` locates the row to remove.

    ``expected`` (update only, optional) adds original-value guard conditions to
    the WHERE clause for optimistic locking; if the guarded update matches no
    rows a :class:`ConflictError` is raised.
    """

    kind: OpKind
    table: Table
    values: dict[str, Any] | None = None
    pk_values: dict[str, Any] | None = None
    expected: dict[str, Any] | None = None


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
    conn: Connection,
    table: Table,
    pk_values: dict[str, Any],
    values: dict[str, Any],
    expected: dict[str, Any] | None = None,
) -> int:
    """Update the row identified by ``pk_values``; return affected row count.

    When ``expected`` is given, its column/value pairs are added to the WHERE
    clause (optimistic locking guard).
    """
    conditions = [_pk_where(table, pk_values)]
    if expected:
        conditions.append(and_(*(table.c[col] == val for col, val in expected.items())))
    result = conn.execute(update(table).where(and_(*conditions)).values(**values))
    return result.rowcount


def _exec_delete(conn: Connection, table: Table, pk_values: dict[str, Any]) -> int:
    """Delete the row identified by ``pk_values``; return affected row count."""
    result = conn.execute(delete(table).where(_pk_where(table, pk_values)))
    return result.rowcount


def insert_record(engine: Engine, table: Table, values: dict[str, Any]) -> Any:
    """Insert a single row and return its primary key (if the driver reports one)."""
    with engine.begin() as conn:
        result = _exec_insert(conn, table, values)
    emit(CrudEvent("created", table.name, dict(values)))
    return result


def update_record(
    engine: Engine,
    table: Table,
    pk_values: dict[str, Any],
    values: dict[str, Any],
    expected: dict[str, Any] | None = None,
) -> int:
    """Update the row matching ``pk_values`` and return the affected row count.

    ``expected`` (optional) enables optimistic locking: the update also matches
    on the supplied original values and raises :class:`ConflictError` if no row
    is affected (the record changed since it was loaded).
    """
    with engine.begin() as conn:
        affected = _exec_update(conn, table, pk_values, values, expected)
        if expected is not None and affected == 0:
            raise ConflictError(
                "Il record è stato modificato da altri: ricarica e riprova."
            )
    emit(CrudEvent("updated", table.name, {**pk_values, **values}))
    return affected


def delete_record(engine: Engine, table: Table, pk_values: dict[str, Any]) -> int:
    """Delete the row matching ``pk_values`` and return the affected row count."""
    with engine.begin() as conn:
        affected = _exec_delete(conn, table, pk_values)
    emit(CrudEvent("deleted", table.name, dict(pk_values)))
    return affected


def _apply(conn: Connection, op: Operation) -> Any:
    """Dispatch a single :class:`Operation` on an open connection."""
    if op.kind == "insert":
        if op.values is None:
            raise ValueError("insert operation requires 'values'")
        return _exec_insert(conn, op.table, op.values)
    if op.kind == "update":
        if op.pk_values is None or op.values is None:
            raise ValueError("update operation requires 'pk_values' and 'values'")
        affected = _exec_update(conn, op.table, op.pk_values, op.values, op.expected)
        if op.expected is not None and affected == 0:
            raise ConflictError(
                "Il record è stato modificato da altri: ricarica e riprova."
            )
        return affected
    if op.kind == "delete":
        if op.pk_values is None:
            raise ValueError("delete operation requires 'pk_values'")
        return _exec_delete(conn, op.table, op.pk_values)
    raise ValueError(f"Unknown operation kind: {op.kind!r}")  # pragma: no cover


def save_master_detail(
    engine: Engine,
    master_op: Operation,
    detail_ops: list[Operation],
    *,
    link: "Callable[[Any, list[Operation]], None] | None" = None,
) -> list[Any]:
    """Execute the master and detail operations in a single transaction.

    The master operation runs first, then each detail operation, all inside one
    ``engine.begin()`` block. Any exception rolls back the entire transaction so
    the database is never left in a partially updated state.

    ``link`` (optional) is called with ``(master_result, detail_ops)`` after the
    master runs but before the details, letting the caller propagate a freshly
    generated master primary key into the detail operations (e.g. FK values on
    new detail rows). It runs inside the same transaction.

    Returns the list of per-operation results (master first, then details).
    """
    results: list[Any] = []
    with engine.begin() as conn:
        master_result = _apply(conn, master_op)
        results.append(master_result)
        if link is not None:
            link(master_result, detail_ops)
        for op in detail_ops:
            results.append(_apply(conn, op))
    # Emit events only after the whole transaction commits successfully.
    for op in (master_op, *detail_ops):
        emit(_event_for_op(op))
    return results


def _event_for_op(op: Operation) -> CrudEvent:
    """Map an :class:`Operation` to its post-commit :class:`CrudEvent`."""
    if op.kind == "insert":
        return CrudEvent("created", op.table.name, dict(op.values or {}))
    if op.kind == "update":
        return CrudEvent(
            "updated", op.table.name, {**(op.pk_values or {}), **(op.values or {})}
        )
    return CrudEvent("deleted", op.table.name, dict(op.pk_values or {}))
