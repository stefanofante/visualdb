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

from pydantic import BaseModel, Field
from sqlalchemy import Engine, MetaData, Table

from dbvisual.core.compiler import compile_select
from dbvisual.core.connections import ConnectionConfig, build_engine
from dbvisual.core.crud import ConflictError, Operation, save_master_detail
from dbvisual.core.introspect import get_primary_key, reflect_schema
from dbvisual.core.introspect import resolve_table as get_table
from dbvisual.core.queryspec import QuerySpec

__all__ = [
    "ConflictError",
    "SheetColumn",
    "SheetSpec",
    "SheetView",
    "apply_batch",
    "build_operations",
    "build_view",
    "clear_engine_cache",
    "config_from_connection",
    "get_table",
    "load_rows",
    "resolve_engine",
]


class SheetSpec(BaseModel):
    """Persisted shape of a sheet definition: a query-spec bound to a connection."""

    connection_id: int
    spec: QuerySpec
    rls: bool = False  # Postgres row-level security (Phase 8); ignored otherwise.
    attachment_fields: list[str] = Field(
        default_factory=list
    )  # Task 1: attachment columns

    def to_json(self) -> str:
        """Serialize to the JSON string stored in ``definitions.queryspec_json``."""
        return self.model_dump_json()

    @classmethod
    def from_json(cls, raw: str) -> SheetSpec:
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
    encryption_key: str | None = None,
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
        encryption_key=encryption_key,
    )


# Keep credentials out of cache keys and invalidate entries when a saved target changes.
_engine_cache: dict[tuple[int, tuple], tuple[bytes, Engine, MetaData]] = {}


def resolve_engine(
    connection, password, *, refresh=False, session_settings=None, encryption_key=None
):
    key = (int(connection["id"]), tuple(sorted((session_settings or {}).items())))
    config = config_from_connection(
        connection, password, session_settings, encryption_key
    )
    import json
    from hashlib import sha256

    signature = sha256(
        json.dumps([connection, password, encryption_key], sort_keys=True).encode()
    ).digest()
    cached = _engine_cache.get(key)
    if cached and not refresh and cached[0] == signature:
        return cached[1], cached[2]
    engine = build_engine(config)
    try:
        metadata = reflect_schema(engine)
    except Exception:
        engine.dispose()
        raise
    if cached:
        cached[1].dispose()
    _engine_cache[key] = signature, engine, metadata
    return engine, metadata


def resolve_saved_engine(connection, secrets, **options):
    cid = connection["id"]
    return resolve_engine(
        connection,
        secrets.get_password(cid),
        encryption_key=secrets.get_secret(f"enckey:{cid}"),
        **options,
    )


def clear_engine_cache() -> None:
    for _, engine, _ in _engine_cache.values():
        engine.dispose()
    _engine_cache.clear()


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

    if update_originals is not None and len(update_originals) != len(updates):
        raise ValueError("Each updated row requires its original values.")
    ops: list[Operation] = []
    for row in deletes:
        ops.append(
            Operation(
                kind="delete",
                table=table,
                pk_values=pk_of(row),
                expected=values_of(row),
            )
        )
    for idx, row in enumerate(updates):
        values = values_of(row)
        expected: dict[str, Any] | None = None
        if update_originals is not None:
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
                pk_values=pk_of(
                    update_originals[idx] if update_originals is not None else row
                ),
                values=values,
                expected=expected,
            )
        )
    for row in inserts:
        ops.append(Operation(kind="insert", table=table, values=values_of(row)))
    return ops


def apply_batch(engine: Engine, ops: list[Operation], *, before_commit=None) -> None:
    """Apply all operations in a single transaction (rollback on any error)."""
    if not ops:
        return
    save_master_detail(engine, ops[0], ops[1:], before_commit=before_commit)
