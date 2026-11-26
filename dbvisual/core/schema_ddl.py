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
_NO_ALTER_FK = {"sqlite", "duckdb"}


class DDLNotSupported(RuntimeError):
    """Raised when an operation is not supported on the target dialect."""


class DDLPermissionError(RuntimeError):
    """Raised when a DDL statement fails (often missing DDL privileges)."""


@dataclass(slots=True)
class ColumnSpec:
    """A column definition for DDL composition."""

    name: str
    type: str = "text"  # a key of _LOGICAL_TYPES
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
        raise DDLNotSupported(f"Unknown logical type: {spec.type!r}") from exc
    return factory(spec.length)


def _compile_type(dialect: Dialect, spec: ColumnSpec) -> str:
    return dialect.type_compiler_instance.process(_sa_type(spec))


def compose_create_table(dialect: Dialect, table: TableSpec) -> str:
    """Compose a ``CREATE TABLE`` statement (with inline PK and FKs)."""
    from sqlalchemy import ForeignKeyConstraint

    md = MetaData()
    tbl = Table(
        table.name,
        md,
        *(
            Column(
                c.name,
                _sa_type(c),
                primary_key=c.primary_key,
                nullable=c.nullable and not c.primary_key,
                autoincrement=False if dialect.name == "duckdb" else "auto",
            )
            for c in table.columns
        ),
    )
    for fk in table.foreign_keys:
        remote = md.tables.get(fk.ref_table)
        if remote is None:
            remote = Table(fk.ref_table, md)
        if fk.ref_column not in remote.c and remote is not tbl:
            remote.append_column(Column(fk.ref_column, Integer))
        tbl.append_constraint(
            ForeignKeyConstraint([fk.column], [remote.c[fk.ref_column]], name=fk.name)
        )
    return str(CreateTable(tbl).compile(dialect=dialect)).strip()


def compose_drop_table(dialect: Dialect, table: str) -> str:
    """Compose a ``DROP TABLE`` statement (destructive)."""
    return f"DROP TABLE {dialect.identifier_preparer.quote(table)}"


def compose_add_column(dialect: Dialect, table: str, column: ColumnSpec) -> str:
    """Compose an ``ALTER TABLE ... ADD COLUMN`` statement."""
    coltype = _compile_type(dialect, column)
    null = "" if column.nullable else " NOT NULL"
    quote = dialect.identifier_preparer.quote
    add = "ADD" if dialect.name in {"oracle", "mssql"} else "ADD COLUMN"
    return f"ALTER TABLE {quote(table)} {add} {quote(column.name)} {coltype}{null}"


def compose_drop_column(dialect: Dialect, table: str, column: str) -> str:
    """Compose an ``ALTER TABLE ... DROP COLUMN`` statement (destructive).

    Note: very old SQLite (< 3.35) lacks native DROP COLUMN and needs a
    table-rebuild; modern SQLite and DuckDB support it directly.
    """
    quote = dialect.identifier_preparer.quote
    return f"ALTER TABLE {quote(table)} DROP COLUMN {quote(column)}"


def compose_add_foreign_key(dialect: Dialect, table: str, fk: ForeignKeySpec) -> str:
    """Compose an ``ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY`` statement."""
    if dialect.name in _NO_ALTER_FK:
        raise DDLNotSupported(
            f"{dialect.name}: adding a FK via ALTER is not supported "
            "(recreate the table with an inline FK)."
        )
    name = fk.name or f"fk_{table}_{fk.column}"
    q = dialect.identifier_preparer.quote
    return (
        f"ALTER TABLE {q(table)} ADD CONSTRAINT {q(name)} "
        f"FOREIGN KEY ({q(fk.column)}) REFERENCES {q(fk.ref_table)}({q(fk.ref_column)})"
    )


def compose_drop_foreign_key(dialect: Dialect, table: str, constraint: str) -> str:
    """Compose an ``ALTER TABLE ... DROP CONSTRAINT`` statement (destructive)."""
    if dialect.name in _NO_ALTER_FK:
        raise DDLNotSupported(
            f"{dialect.name}: removing a FK via ALTER is not supported."
        )
    q = dialect.identifier_preparer.quote
    kind = "FOREIGN KEY" if dialect.name in {"mysql", "mariadb"} else "CONSTRAINT"
    return f"ALTER TABLE {q(table)} DROP {kind} {q(constraint)}"


def compose_rename_table(dialect: Dialect, table: str, new_name: str) -> str:
    """Compose a rename-table statement (dialect dependent)."""
    q = dialect.identifier_preparer.quote
    if dialect.name == "mssql":
        table_literal = q(table).replace("'", "''")
        name_literal = new_name.replace("'", "''")
        return f"EXEC sp_rename N'{table_literal}', N'{name_literal}', 'OBJECT'"
    return f"ALTER TABLE {q(table)} RENAME TO {q(new_name)}"


# Operations considered destructive -> require double confirmation in the UI.
DESTRUCTIVE = {"drop_table", "drop_column", "drop_foreign_key"}


def execute_ddl(engine: Engine, sql: str, *, after_ddl=None) -> None:
    """Execute a reviewed DDL statement in a transaction.

    This is the deliberate write channel; it does **not** go through
    ``ensure_readonly``. A failure (e.g. missing DDL privileges) is surfaced as
    :class:`DDLPermissionError` with a clear message rather than crashing.
    """
    try:
        with engine.begin() as conn:
            if (
                conn.dialect.name == "sqlite"
                and not conn.connection.driver_connection.in_transaction
            ):
                conn.exec_driver_sql("BEGIN")
            conn.exec_driver_sql(sql)
            if after_ddl:
                after_ddl(conn)
    except Exception as exc:  # includes permission / syntax errors
        raise DDLPermissionError(
            f"DDL execution failed (check DDL privileges): {exc}"
        ) from exc
