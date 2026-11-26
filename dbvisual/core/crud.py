"""Generic, parametrized CRUD helpers.

Only the ``main_table`` of a query-spec is updatable; these helpers operate on a
single :class:`~sqlalchemy.Table` at a time. All statements use bound
parameters. ``save_master_detail`` runs a set of operations inside a single
transaction and rolls back on any error.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Literal

from sqlalchemy import (
    Connection,
    Date,
    DateTime,
    Engine,
    Table,
    Time,
    and_,
    delete,
    insert,
    update,
)

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


def _typed_values(table: Table, values: dict[str, Any]):
    """Native date/time bind processors expect Python objects from browser text."""
    result = dict(values)
    for key, value in values.items():
        if not isinstance(value, str):
            continue
        kind = table.c[key].type
        for sql_type, convert in ((DateTime, datetime), (Date, date), (Time, time)):
            if isinstance(kind, sql_type):
                result[key] = convert.fromisoformat(value) if value else None
                break
    return result


def _pk_where(table: Table, pk_values: dict[str, Any]):
    """Build a WHERE clause matching ``pk_values`` on ``table``."""
    if not pk_values:
        raise ValueError("pk_values must not be empty")
    if (
        set(pk_values) != {column.key for column in table.primary_key}
        or None in pk_values.values()
    ):
        raise ValueError("A complete primary key is required for a record write.")
    return and_(
        *(table.c[col] == val for col, val in _typed_values(table, pk_values).items())
    )


def _exec_insert(conn: Connection, table: Table, values: dict[str, Any]) -> Any:
    """Insert ``values`` into ``table``; return the primary key when available."""
    fields = {
        k: v
        for k, v in _typed_values(table, values).items()
        if v is not None
        or (table.c[k].default is None and table.c[k].server_default is None)
    }
    stmt = insert(table).values(**fields)
    if conn.dialect.name == "duckdb" and len(table.primary_key):
        return conn.execute(stmt.returning(*table.primary_key)).one()
    result = conn.execute(stmt)
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
        conditions.append(
            and_(
                *(
                    table.c[col] == val
                    for col, val in _typed_values(table, expected).items()
                )
            )
        )
    stmt = update(table).where(and_(*conditions)).values(**_typed_values(table, values))
    if conn.dialect.name == "duckdb":
        return len(conn.execute(stmt.returning(*table.primary_key)).all())
    result = conn.execute(stmt)
    return result.rowcount


def _exec_delete(
    conn: Connection, table: Table, pk_values: dict[str, Any], expected=None
) -> int:
    """Delete the row identified by ``pk_values``; return affected row count."""
    stmt = delete(table).where(_pk_where(table, pk_values))
    for name, value in _typed_values(table, expected or {}).items():
        stmt = stmt.where(table.c[name] == value)
    if conn.dialect.name == "duckdb":
        return len(conn.execute(stmt.returning(*table.primary_key)).all())
    result = conn.execute(stmt)
    return result.rowcount


def insert_record(
    engine: Engine, table: Table, values: dict[str, Any], *, before_commit=None
) -> Any:
    """Insert a single row and return its primary key (if the driver reports one)."""
    with engine.begin() as conn:
        result = _exec_insert(conn, table, values)
        if before_commit:
            before_commit(result)
    emit(
        CrudEvent(
            "created",
            table.name,
            dict(values),
            engine.get_execution_options().get("dbvisual_definition_id"),
        )
    )
    return result


def update_record(
    engine: Engine,
    table: Table,
    pk_values: dict[str, Any],
    values: dict[str, Any],
    expected: dict[str, Any] | None = None,
    *,
    before_commit=None,
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
                "The record was modified by someone else: reload and retry."
            )
        if before_commit and affected != 0:
            before_commit(None)
    if affected != 0:
        emit(
            CrudEvent(
                "updated",
                table.name,
                {**pk_values, **values},
                engine.get_execution_options().get("dbvisual_definition_id"),
            )
        )
    return affected


def delete_record(
    engine: Engine, table: Table, pk_values: dict[str, Any], expected=None
) -> int:
    """Delete the row matching ``pk_values`` and return the affected row count."""
    with engine.begin() as conn:
        affected = _exec_delete(conn, table, pk_values, expected)
        if expected is not None and affected == 0:
            raise ConflictError("Record changed or already removed.")
    if affected != 0:
        emit(
            CrudEvent(
                "deleted",
                table.name,
                dict(pk_values),
                engine.get_execution_options().get("dbvisual_definition_id"),
            )
        )
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
        if not op.values:
            conditions = [_pk_where(op.table, op.pk_values)]
            conditions.extend(
                op.table.c[k] == v for k, v in (op.expected or {}).items()
            )
            from sqlalchemy import select

            if (
                conn.execute(select(*op.table.primary_key).where(*conditions)).first()
                is None
            ):
                raise ConflictError("Master record is no longer available.")
            return 0
        affected = _exec_update(conn, op.table, op.pk_values, op.values, op.expected)
        if op.expected is not None and affected == 0:
            raise ConflictError(
                "The record was modified by someone else: reload and retry."
            )
        return affected
    if op.kind == "delete":
        if op.pk_values is None:
            raise ValueError("delete operation requires 'pk_values'")
        affected = _exec_delete(conn, op.table, op.pk_values, op.expected)
        if affected == 0:
            raise ConflictError("Record changed or already removed.")
        return affected
    raise ValueError(f"Unknown operation kind: {op.kind!r}")  # pragma: no cover


def save_master_detail(
    engine: Engine,
    master_op: Operation,
    detail_ops: list[Operation],
    *,
    link: Callable[[Any, list[Operation]], None] | None = None,
    before_commit: Callable[[list[Any]], None] | None = None,
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
        if before_commit:
            before_commit(results)
    # Emit events only after the whole transaction commits successfully.
    for op, result in zip((master_op, *detail_ops), results, strict=True):
        if op.kind == "insert" or result != 0:
            event = _event_for_op(op)
            event.definition_id = engine.get_execution_options().get(
                "dbvisual_definition_id"
            )
            emit(event)
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
