"""Phase 9 tests: schema service (CSV import/export, AI DDL) + route smoke."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, MetaData

from dbvisual.app.schema_service import (
    csv_create_table_ddl,
    generate_ddl_via_ai,
    infer_columns,
    rows_from_csv,
    table_to_csv,
)
from dbvisual.core.connections import ConnectionConfig, build_engine
from dbvisual.core.introspect import list_tables, reflect_schema
from dbvisual.core.schema_ddl import execute_ddl


def _sqlite() -> Engine:
    return build_engine(ConnectionConfig(dialect="sqlite", database=":memory:"))


# --- CSV import/export ------------------------------------------------------


def test_infer_columns_int_vs_text() -> None:
    header = ["id", "name"]
    rows = [["1", "Alice"], ["2", "Bob"]]
    specs = {c.name: c.type for c in infer_columns(header, rows)}
    assert specs == {"id": "integer", "name": "text"}


def test_csv_create_and_export_roundtrip() -> None:
    from dbvisual.app.sheet_service import get_table as gt

    engine = _sqlite()
    csv_text = "id,name\n1,Alice\n2,Bob\n"
    sql, header = csv_create_table_ddl(engine.dialect, "people", csv_text)
    assert "CREATE TABLE people" in sql
    execute_ddl(engine, sql)

    # Fill the table then export back to CSV.
    from sqlalchemy import text as sa_text

    with engine.begin() as conn:
        for row in rows_from_csv(csv_text)[1]:
            conn.execute(
                sa_text("INSERT INTO people (id, name) VALUES (:id, :name)"),
                {"id": row[0], "name": row[1]},
            )
    metadata = reflect_schema(engine)
    assert "people" in list_tables(metadata)
    out = table_to_csv(engine, gt(metadata, "people"))
    assert "Alice" in out and "Bob" in out and out.splitlines()[0].startswith("id")


# --- AI DDL generation (mock HTTP) -----------------------------------------


def test_generate_ddl_via_ai_mock() -> None:
    captured: dict[str, Any] = {}

    def fake_http(url, headers, payload):  # type: ignore[no-untyped-def]
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "CREATE TABLE t(a INT)"}}]}

    ddl = generate_ddl_via_ai(
        "openai", "KEY", "gpt", "a table t with column a",
        {"existing": ["x"]}, "sqlite", http=fake_http,
    )
    assert ddl == "CREATE TABLE t(a INT)"
    # DDL system prompt must permit DDL (not the read-only SELECT prompt).
    assert "DDL" in captured["payload"]["messages"][0]["content"]


# --- smoke -----------------------------------------------------------------


def test_schema_route_registered() -> None:
    from nicegui import Client

    import dbvisual.app.main  # noqa: F401

    assert "/schema" in set(Client.page_routes.values())
