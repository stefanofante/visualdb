"""Schema introspection helpers built on SQLAlchemy reflection.

Reflect an existing database into a :class:`~sqlalchemy.MetaData` object and
expose convenient accessors for tables, columns and foreign-key relations. The
foreign-key information feeds the query compiler's automatic joins.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, MetaData, inspect


@dataclass(slots=True, frozen=True)
class ColumnInfo:
    """Lightweight description of a single column."""

    name: str
    type: str
    nullable: bool
    primary_key: bool


@dataclass(slots=True, frozen=True)
class ForeignKeyInfo:
    """A foreign-key relation: ``local_col`` -> ``remote_table.remote_col``."""

    local_col: str
    remote_table: str
    remote_col: str


def reflect_schema(engine: Engine, schema: str | None = None) -> MetaData:
    """Reflect the full schema of ``engine`` into a fresh :class:`MetaData`.

    ``schema`` may be provided for dialects that namespace tables.
    """
    metadata = MetaData(schema=schema)
    metadata.reflect(bind=engine)
    return metadata


def list_tables(metadata: MetaData) -> list[str]:
    """Return the names of all reflected tables, sorted alphabetically."""
    return sorted(metadata.tables.keys())


def _resolve_table(metadata: MetaData, table: str):
    """Return the reflected ``Table`` for ``table`` (raw or schema-qualified)."""
    tbl = metadata.tables.get(table)
    if tbl is None:
        # Try matching by bare name when a schema prefix is present.
        for key, value in metadata.tables.items():
            if key == table or key.split(".")[-1] == table:
                return value
        raise KeyError(f"Table not found in metadata: {table!r}")
    return tbl


def get_columns(metadata: MetaData, table: str) -> list[ColumnInfo]:
    """Return column metadata (name, type, nullable, pk) for ``table``."""
    tbl = _resolve_table(metadata, table)
    return [
        ColumnInfo(
            name=col.name,
            type=str(col.type),
            nullable=bool(col.nullable),
            primary_key=bool(col.primary_key),
        )
        for col in tbl.columns
    ]


def detect_foreign_keys(metadata: MetaData, table: str) -> list[ForeignKeyInfo]:
    """Return the foreign-key relations declared on ``table``.

    Each entry maps a local column to a remote ``table.column`` pair, which the
    compiler uses to build automatic joins for related tables.
    """
    tbl = _resolve_table(metadata, table)
    relations: list[ForeignKeyInfo] = []
    for fk in tbl.foreign_keys:
        target = fk.column  # remote Column object
        relations.append(
            ForeignKeyInfo(
                local_col=fk.parent.name,
                remote_table=target.table.name,
                remote_col=target.name,
            )
        )
    return relations


def get_primary_key(metadata: MetaData, table: str) -> list[str]:
    """Return the ordered list of primary-key column names for ``table``."""
    tbl = _resolve_table(metadata, table)
    return [col.name for col in tbl.primary_key.columns]


def _inspect_tables(engine: Engine, schema: str | None = None) -> list[str]:
    """Return table names directly from the inspector (without reflection)."""
    return sorted(inspect(engine).get_table_names(schema=schema))
