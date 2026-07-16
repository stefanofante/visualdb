"""Sheet orchestration — the DB-facing logic behind an editable Sheet.

This module is intentionally UI-agnostic (no NiceGUI imports) so it can be unit
tested in isolation. Every database operation is delegated to the Phase 1 core
(``dbvisual.core``): nothing here re-implements SQL building or execution.

A *Sheet* is a saved definition (``kind='sheet'``) whose ``queryspec_json`` holds
a :class:`SheetSpec` — a query-spec plus the id of the connection it runs on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Engine, MetaData, Table

from dbvisual.core.compiler import compile_select
from dbvisual.core.connections import ConnectionConfig, build_engine
from dbvisual.core.crud import ConflictError, Operation, save_master_detail
from dbvisual.core.introspect import get_primary_key, reflect_schema
from dbvisual.core.queryspec import QuerySpec

__all__ = [
    "SheetSpec",
    "SheetColumn",
    "SheetView",
    "ConflictError",
    "config_from_connection",
    "resolve_engine",
    "clear_engine_cache",
    "get_table",
    "build_view",
    "load_rows",
    "build_operations",
    "apply_batch",
]


class SheetSpec(BaseModel):
    """Persisted shape of a sheet definition: a query-spec bound to a connection."""

    connection_id: int
    spec: QuerySpec
    rls: bool = False  # Postgres row-level security (Phase 8); ignored otherwise.

    def to_json(self) -> str:
        """Serialize to the JSON string stored in ``definitions.queryspec_json``."""
        return self.model_dump_json()

    @classmethod
    def from_json(cls, raw: str) -> "SheetSpec":
        """Rebuild a :class:`SheetSpec` from its stored JSON."""
        return cls.model_validate_json(raw)


@dataclass(slots=True, frozen=True)
class SheetColumn:
    """A single grid column resolved from the query-spec."""

    field: str  # key used in row data (alias or column name)
    header: str  # display header
    table: str  # source table
    column: str  # actual column name in ``table``
    editable: bool  # True only for writable main-table, non-PK columns


@dataclass(slots=True)
class SheetView:
    """Resolved presentation of a sheet: columns, PK fields and main table."""

    main_table: str
    columns: list[SheetColumn] = field(default_factory=list)
    pk_fields: list[str] = field(default_factory=list)

    @property
    def field_to_column(self) -> dict[str, str]:
        """Map field key -> main-table column name (main-table columns only)."""
        return {c.field: c.column for c in self.columns if c.table == self.main_table}

    @property
    def editable_fields(self) -> set[str]:
        """Set of field keys that may be written back to the database."""
        return {c.field for c in self.columns if c.editable}


def config_from_connection(
    connection: dict[str, Any],
    password: str | None,
    session_settings: dict[str, str] | None = None,
) -> ConnectionConfig:
    """Build a :class:`ConnectionConfig` from a stored connection row + password."""
    return ConnectionConfig(
        dialect=connection["dialect"],
        host=connection.get("host"),
        port=connection.get("port"),
        database=connection.get("database"),
        username=connection.get("username"),
        password=password,
        query=connection.get("options") or {},
        session_settings=session_settings or {},
    )


# Cache of (engine, reflected metadata) keyed by (connection id, session settings).
_engine_cache: dict[
    tuple[int, tuple[tuple[str, str], ...]], tuple[Engine, MetaData]
] = {}


def resolve_engine(
    connection: dict[str, Any],
    password: str | None,
    *,
    refresh: bool = False,
    session_settings: dict[str, str] | None = None,
) -> tuple[Engine, MetaData]:
    """Return a cached ``(engine, metadata)`` for ``connection`` (reflecting once).

    ``session_settings`` (e.g. ``app.current_user_email`` for Postgres RLS) are
    applied on each connection and are part of the cache key.
    """
    key = (int(connection["id"]), tuple(sorted((session_settings or {}).items())))
    if not refresh and key in _engine_cache:
        return _engine_cache[key]
    engine = build_engine(
        config_from_connection(connection, password, session_settings)
    )
    metadata = reflect_schema(engine)
    _engine_cache[key] = (engine, metadata)
    return engine, metadata


def clear_engine_cache() -> None:
    """Drop all cached engines/metadata (e.g. after editing a connection)."""
    _engine_cache.clear()


def get_table(metadata: MetaData, name: str) -> Table:
    """Return the reflected :class:`Table` for ``name`` (raw or schema-qualified)."""
    tbl = metadata.tables.get(name)
    if tbl is not None:
        return tbl
    for key, value in metadata.tables.items():
        if key.split(".")[-1] == name:
            return value
    raise KeyError(f"Table not found in metadata: {name!r}")


def build_view(spec: QuerySpec, metadata: MetaData) -> SheetView:
    """Resolve a :class:`SheetView` from a query-spec and reflected metadata.

    Main-table columns are editable except primary-key columns (needed to locate
    rows but never edited). Columns coming from related tables are read-only.
    """
    pk_cols = set(get_primary_key(metadata, spec.main_table))
    columns: list[SheetColumn] = []
    pk_fields: list[str] = []
    for col in spec.columns:
        field_key = col.alias or col.name
        is_main = col.table == spec.main_table
        is_pk = is_main and col.name in pk_cols
        columns.append(
            SheetColumn(
                field=field_key,
                header=col.alias or col.name,
                table=col.table,
                column=col.name,
                editable=is_main and not is_pk,
            )
        )
        if is_pk:
            pk_fields.append(field_key)
    return SheetView(main_table=spec.main_table, columns=columns, pk_fields=pk_fields)


def load_rows(
    engine: Engine, metadata: MetaData, spec: QuerySpec
) -> tuple[list[str], list[dict[str, Any]]]:
    """Compile + execute the query-spec and return ``(field_keys, rows)``."""
    stmt = compile_select(spec, metadata, {})
    with engine.connect() as conn:
        result = conn.execute(stmt)
        fields = list(result.keys())
        rows = [dict(r) for r in result.mappings()]
    return fields, rows


def build_operations(
    view: SheetView,
    table: Table,
    *,
    inserts: list[dict[str, Any]],
    updates: list[dict[str, Any]],
    deletes: list[dict[str, Any]],
    update_originals: list[dict[str, Any]] | None = None,
) -> list[Operation]:
    """Translate dirty grid rows into ordered core :class:`Operation` objects.

    Rows are keyed by grid *field*. Only editable main-table fields are written;
    related (lookup) fields are always ignored. Order is deletes → updates →
    inserts so re-used primary keys do not collide.

    When ``update_originals`` is given (parallel to ``updates``), each update
    carries an ``expected`` guard built from the original values of the changed
    columns, enabling optimistic locking in the core.
    """
    field_to_col = view.field_to_column
    editable = view.editable_fields
    pk_fields = view.pk_fields

    def pk_of(row: dict[str, Any]) -> dict[str, Any]:
        return {field_to_col[f]: row[f] for f in pk_fields}

    def values_of(row: dict[str, Any]) -> dict[str, Any]:
        return {field_to_col[f]: row[f] for f in editable if f in row}

    ops: list[Operation] = []
    for row in deletes:
        ops.append(Operation(kind="delete", table=table, pk_values=pk_of(row)))
    for idx, row in enumerate(updates):
        values = values_of(row)
        expected: dict[str, Any] | None = None
        if update_originals is not None and idx < len(update_originals):
            original = update_originals[idx]
            # Guard on the original values of the changed editable columns.
            expected = {
                field_to_col[f]: original[f]
                for f in editable
                if f in row and f in original
            }
        ops.append(
            Operation(
                kind="update",
                table=table,
                pk_values=pk_of(row),
                values=values,
                expected=expected,
            )
        )
    for row in inserts:
        ops.append(Operation(kind="insert", table=table, values=values_of(row)))
    return ops


def apply_batch(engine: Engine, ops: list[Operation]) -> None:
    """Apply all operations in a single transaction (rollback on any error)."""
    if not ops:
        return
    save_master_detail(engine, ops[0], ops[1:])
