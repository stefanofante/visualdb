"""Multi-dialect DDL composition and execution (Phase 9).

Schema mutation is a **deliberate write channel**, separate from the read-only
report path (``ensure_readonly``). Every helper here follows a two-step model:

1. ``compose_*`` returns the exact SQL text for the user to review.
2. ``execute_ddl`` runs a reviewed statement inside a transaction.

Composition never executes anything; the UI must obtain explicit confirmation
(double confirmation for destructive operations) before calling ``execute_ddl``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
)
from sqlalchemy.engine import Engine
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.schema import CreateTable
from sqlalchemy.types import TypeEngine

# Logical type -> factory producing a SQLAlchemy generic type (compiles per dialect).
_LOGICAL_TYPES: dict[str, Any] = {
    "text": lambda length: String(length) if length else String(),
    "integer": lambda length: Integer(),
    "bigint": lambda length: BigInteger(),
    "decimal": lambda length: Numeric(),
    "float": lambda length: Float(),
    "boolean": lambda length: Boolean(),
    "date": lambda length: Date(),
    "timestamp": lambda length: DateTime(),
}

# Dialects whose ALTER TABLE cannot ADD/DROP a foreign key constraint.
_NO_ALTER_FK = {"sqlite"}


class DDLNotSupported(RuntimeError):
    """Raised when an operation is not supported on the target dialect."""


class DDLPermissionError(RuntimeError):
    """Raised when a DDL statement fails (often missing DDL privileges)."""


@dataclass(slots=True)
class ColumnSpec:
    """A column definition for DDL composition."""

    name: str
    type: str = "text"          # a key of _LOGICAL_TYPES
    length: int | None = None
    nullable: bool = True
    primary_key: bool = False


@dataclass(slots=True)
class ForeignKeySpec:
    """A foreign-key relation for DDL composition."""

    column: str
    ref_table: str
    ref_column: str
    name: str | None = None


@dataclass(slots=True)
class TableSpec:
    """A table definition for ``compose_create_table``."""

    name: str
    columns: list[ColumnSpec] = field(default_factory=list)
    foreign_keys: list[ForeignKeySpec] = field(default_factory=list)


def logical_types() -> list[str]:
    """Return the supported logical type names."""
    return list(_LOGICAL_TYPES)


def _sa_type(spec: ColumnSpec) -> TypeEngine[Any]:
    try:
        factory = _LOGICAL_TYPES[spec.type]
    except KeyError as exc:
        raise DDLNotSupported(f"Tipo logico sconosciuto: {spec.type!r}") from exc
    return factory(spec.length)


def _compile_type(dialect: Dialect, spec: ColumnSpec) -> str:
    return dialect.type_compiler_instance.process(_sa_type(spec))


def compose_create_table(dialect: Dialect, table: TableSpec) -> str:
    """Compose a ``CREATE TABLE`` statement (with inline PK and FKs)."""
    from sqlalchemy import ForeignKey

    fk_by_col = {fk.column: fk for fk in table.foreign_keys}
    md = MetaData()
    # Stub referenced tables so ForeignKey targets resolve at compile time.
    for fk in table.foreign_keys:
        if fk.ref_table not in md.tables:
            Table(fk.ref_table, md, Column(fk.ref_column, Integer, primary_key=True))
    cols: list[Column[Any]] = []
    for c in table.columns:
        args: list[Any] = [c.name, _sa_type(c)]
        if c.name in fk_by_col:
            fk = fk_by_col[c.name]
            args.append(ForeignKey(f"{fk.ref_table}.{fk.ref_column}"))
        cols.append(
            Column(*args, primary_key=c.primary_key, nullable=c.nullable)
        )
    tbl = Table(table.name, md, *cols)
    return str(CreateTable(tbl).compile(dialect=dialect)).strip()


def compose_drop_table(dialect: Dialect, table: str) -> str:
    """Compose a ``DROP TABLE`` statement (destructive)."""
    return f"DROP TABLE {table}"


def compose_add_column(dialect: Dialect, table: str, column: ColumnSpec) -> str:
    """Compose an ``ALTER TABLE ... ADD COLUMN`` statement."""
    coltype = _compile_type(dialect, column)
    null = "" if column.nullable else " NOT NULL"
    return f"ALTER TABLE {table} ADD COLUMN {column.name} {coltype}{null}"


def compose_drop_column(dialect: Dialect, table: str, column: str) -> str:
    """Compose an ``ALTER TABLE ... DROP COLUMN`` statement (destructive).

    Note: very old SQLite (< 3.35) lacks native DROP COLUMN and needs a
    table-rebuild; modern SQLite and DuckDB support it directly.
    """
    return f"ALTER TABLE {table} DROP COLUMN {column}"


def compose_add_foreign_key(dialect: Dialect, table: str, fk: ForeignKeySpec) -> str:
    """Compose an ``ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY`` statement."""
    if dialect.name in _NO_ALTER_FK:
        raise DDLNotSupported(
            f"{dialect.name}: aggiunta di una FK via ALTER non supportata "
            "(ricrea la tabella con la FK inline)."
        )
    name = fk.name or f"fk_{table}_{fk.column}"
    return (
        f"ALTER TABLE {table} ADD CONSTRAINT {name} "
        f"FOREIGN KEY ({fk.column}) REFERENCES {fk.ref_table}({fk.ref_column})"
    )


def compose_drop_foreign_key(dialect: Dialect, table: str, constraint: str) -> str:
    """Compose an ``ALTER TABLE ... DROP CONSTRAINT`` statement (destructive)."""
    if dialect.name in _NO_ALTER_FK:
        raise DDLNotSupported(
            f"{dialect.name}: rimozione di una FK via ALTER non supportata."
        )
    return f"ALTER TABLE {table} DROP CONSTRAINT {constraint}"


def compose_rename_table(dialect: Dialect, table: str, new_name: str) -> str:
    """Compose a rename-table statement (dialect dependent)."""
    return f"ALTER TABLE {table} RENAME TO {new_name}"


# Operations considered destructive -> require double confirmation in the UI.
DESTRUCTIVE = {"drop_table", "drop_column", "drop_foreign_key"}


def execute_ddl(engine: Engine, sql: str) -> None:
    """Execute a reviewed DDL statement in a transaction.

    This is the deliberate write channel; it does **not** go through
    ``ensure_readonly``. A failure (e.g. missing DDL privileges) is surfaced as
    :class:`DDLPermissionError` with a clear message rather than crashing.
    """
    from sqlalchemy import text

    try:
        with engine.begin() as conn:
            conn.execute(text(sql))
    except Exception as exc:  # includes permission / syntax errors
        raise DDLPermissionError(
            f"Esecuzione DDL fallita (verifica i privilegi DDL): {exc}"
        ) from exc
