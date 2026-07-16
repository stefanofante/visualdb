"""Phase 9 tests: DDL composition/execution on SQLite and DuckDB."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine

from dbvisual.core.connections import ConnectionConfig, build_engine
from dbvisual.core.introspect import (
    detect_foreign_keys,
    get_columns,
    list_tables,
    reflect_schema,
)
from dbvisual.core.schema_ddl import (
    DDLNotSupported,
    ColumnSpec,
    ForeignKeySpec,
    TableSpec,
    compose_add_column,
    compose_add_foreign_key,
    compose_create_table,
    compose_drop_column,
    compose_drop_table,
    execute_ddl,
    logical_types,
)


def _sqlite() -> Engine:
    return build_engine(ConnectionConfig(dialect="sqlite", database=":memory:"))


def _duckdb() -> Engine:
    pytest.importorskip("duckdb_engine")
    return build_engine(ConnectionConfig(dialect="duckdb", database=":memory:"))


# --- composition -----------------------------------------------------------


def test_logical_types_available() -> None:
    assert {"text", "integer", "decimal", "boolean", "date", "timestamp"} <= set(
        logical_types()
    )


def test_compose_create_table_text() -> None:
    engine = _sqlite()
    spec = TableSpec(
        name="people",
        columns=[
            ColumnSpec("id", "integer", primary_key=True, nullable=False),
            ColumnSpec("name", "text", length=100, nullable=False),
        ],
    )
    sql = compose_create_table(engine.dialect, spec)
    assert "CREATE TABLE people" in sql
    assert "PRIMARY KEY" in sql
    assert "name" in sql


def test_compose_add_column_text() -> None:
    engine = _sqlite()
    sql = compose_add_column(
        engine.dialect, "people", ColumnSpec("age", "integer", nullable=False)
    )
    assert sql.startswith("ALTER TABLE people ADD COLUMN age")
    assert "NOT NULL" in sql


def test_add_fk_unsupported_on_sqlite() -> None:
    engine = _sqlite()
    with pytest.raises(DDLNotSupported):
        compose_add_foreign_key(
            engine.dialect, "orders", ForeignKeySpec("cid", "customers", "id")
        )


# --- execution round-trips (SQLite) ----------------------------------------


def test_create_add_drop_roundtrip_sqlite() -> None:
    engine = _sqlite()
    execute_ddl(
        engine,
        compose_create_table(
            engine.dialect,
            TableSpec("t", [ColumnSpec("id", "integer", primary_key=True)]),
        ),
    )
    assert "t" in list_tables(reflect_schema(engine))

    execute_ddl(engine, compose_add_column(engine.dialect, "t", ColumnSpec("qty", "integer")))
    assert "qty" in {c.name for c in get_columns(reflect_schema(engine), "t")}

    execute_ddl(engine, compose_drop_column(engine.dialect, "t", "qty"))
    assert "qty" not in {c.name for c in get_columns(reflect_schema(engine), "t")}

    execute_ddl(engine, compose_drop_table(engine.dialect, "t"))
    assert "t" not in list_tables(reflect_schema(engine))


def test_create_with_fk_detected_sqlite() -> None:
    engine = _sqlite()
    execute_ddl(
        engine,
        compose_create_table(
            engine.dialect,
            TableSpec("customers", [ColumnSpec("id", "integer", primary_key=True)]),
        ),
    )
    execute_ddl(
        engine,
        compose_create_table(
            engine.dialect,
            TableSpec(
                "orders",
                columns=[
                    ColumnSpec("id", "integer", primary_key=True),
                    ColumnSpec("customer_id", "integer"),
                ],
                foreign_keys=[ForeignKeySpec("customer_id", "customers", "id")],
            ),
        ),
    )
    fks = detect_foreign_keys(reflect_schema(engine), "orders")
    assert any(fk.remote_table == "customers" and fk.local_col == "customer_id" for fk in fks)


# --- execution round-trip (DuckDB) -----------------------------------------


def test_create_add_roundtrip_duckdb() -> None:
    engine = _duckdb()
    execute_ddl(
        engine,
        compose_create_table(
            engine.dialect,
            TableSpec("d", [ColumnSpec("id", "integer"), ColumnSpec("label", "text")]),
        ),
    )
    assert "d" in list_tables(reflect_schema(engine))
    execute_ddl(engine, compose_add_column(engine.dialect, "d", ColumnSpec("n", "integer")))
    assert "n" in {c.name for c in get_columns(reflect_schema(engine), "d")}


# --- DDL channel is separate from ensure_readonly --------------------------


def test_ddl_does_not_pass_ensure_readonly() -> None:
    from dbvisual.app.report_service import ensure_readonly

    engine = _sqlite()
    sql = compose_create_table(
        engine.dialect, TableSpec("x", [ColumnSpec("id", "integer")])
    )
    # The report read-only guard would reject DDL; the DDL channel must not use it.
    with pytest.raises(ValueError):
        ensure_readonly(sql)
    # But executing via the dedicated channel works.
    execute_ddl(engine, sql)
    assert "x" in list_tables(reflect_schema(engine))
