"""Gated multi-dialect integration tests (Task 5).

These exercise the real core stack (schema DDL -> CRUD with optimistic locking ->
introspection -> compiled SELECT) against actual database servers. They are
**skipped unless** the corresponding environment variable holds a SQLAlchemy URL:

* ``DBVISUAL_TEST_POSTGRES_URL``  e.g. ``postgresql+psycopg://user:pw@host/db``
* ``DBVISUAL_TEST_MYSQL_URL``     e.g. ``mysql+pymysql://user:pw@host/db``
* ``DBVISUAL_TEST_MSSQL_URL``     e.g. ``mssql+pyodbc://user:pw@host/db?driver=...``
* ``DBVISUAL_TEST_ORACLE_URL``    e.g. ``oracle+oracledb://user:pw@host/?service_name=...``

Each test creates a throwaway table, round-trips a row and drops the table, so a
throwaway schema/user is expected. Nothing runs in CI unless the URLs are set.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine

from dbvisual.core.compiler import compile_select
from dbvisual.core.crud import (
    ConflictError,
    delete_record,
    insert_record,
    update_record,
)
from dbvisual.core.introspect import get_columns, list_tables, reflect_schema
from dbvisual.core.queryspec import Column, QuerySpec
from dbvisual.core.schema_ddl import (
    ColumnSpec,
    TableSpec,
    compose_create_table,
    compose_drop_table,
    execute_ddl,
)

_DIALECTS = [
    ("postgres", "DBVISUAL_TEST_POSTGRES_URL"),
    ("mysql", "DBVISUAL_TEST_MYSQL_URL"),
    ("mssql", "DBVISUAL_TEST_MSSQL_URL"),
    ("oracle", "DBVISUAL_TEST_ORACLE_URL"),
]

_TABLE = "dbvisual_it_roundtrip"


def _find_table(metadata, name: str) -> str:
    """Return the reflected table name, tolerating dialect case folding."""
    for t in list_tables(metadata):
        if t.lower() == name.lower():
            return t
    raise AssertionError(f"table {name} not found after create")


def _roundtrip(url: str) -> None:
    engine = create_engine(url)
    dialect = engine.dialect
    # Best-effort clean slate.
    try:
        execute_ddl(engine, compose_drop_table(dialect, _TABLE))
    except Exception:
        pass

    spec = TableSpec(
        _TABLE,
        [
            ColumnSpec("id", "integer", primary_key=True, nullable=False),
            ColumnSpec("name", "text", length=50),
            ColumnSpec("qty", "integer"),
        ],
    )
    execute_ddl(engine, compose_create_table(dialect, spec))
    try:
        metadata = reflect_schema(engine)
        table_name = _find_table(metadata, _TABLE)
        table = metadata.tables[table_name]

        assert {c.name.lower() for c in get_columns(metadata, table_name)} == {
            "id",
            "name",
            "qty",
        }

        insert_record(engine, table, {"id": 1, "name": "Pen", "qty": 3})
        insert_record(engine, table, {"id": 2, "name": "Book", "qty": 7})

        # optimistic locking: stale expected value must raise
        with pytest.raises(ConflictError):
            update_record(
                engine, table, {"id": 1}, {"qty": 99}, expected={"qty": 999}
            )
        # correct expected value updates the row
        affected = update_record(
            engine, table, {"id": 1}, {"qty": 42}, expected={"qty": 3}
        )
        assert affected == 1

        # compiled SELECT reads back the updated data
        query = QuerySpec(
            main_table=table_name,
            columns=[
                Column(table=table_name, name="id", alias="id"),
                Column(table=table_name, name="qty", alias="qty"),
            ],
        )
        stmt = compile_select(query, metadata, {})
        with engine.connect() as conn:
            data = {r["id"]: r["qty"] for r in conn.execute(stmt).mappings()}
        assert data == {1: 42, 2: 7}

        assert delete_record(engine, table, {"id": 2}) == 1
    finally:
        execute_ddl(engine, compose_drop_table(dialect, _TABLE))
        engine.dispose()


@pytest.mark.parametrize("name,env", _DIALECTS, ids=[d[0] for d in _DIALECTS])
def test_dialect_end_to_end(name: str, env: str) -> None:
    url = os.environ.get(env)
    if not url:
        pytest.skip(f"{env} not set; skipping {name} integration test")
    _roundtrip(url)
