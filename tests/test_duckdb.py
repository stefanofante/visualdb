"""Task A tests: DuckDB dialect works with the core (introspect/compiler/crud)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import (
    Column as SACol,
)
from sqlalchemy import (
    Engine,
    Integer,
    MetaData,
    String,
    Table,
    insert,
    select,
)

from dbvisual.core import connections
from dbvisual.core.compiler import compile_select
from dbvisual.core.connections import ConnectionConfig, build_engine
from dbvisual.core.crud import delete_record, insert_record, update_record
from dbvisual.core.introspect import get_columns, list_tables, reflect_schema
from dbvisual.core.queryspec import Column, QuerySpec

duckdb_engine = pytest.importorskip("duckdb_engine")


def _seed(engine: Engine) -> MetaData:
    meta = MetaData()
    items = Table(
        "items",
        meta,
        SACol("id", Integer, primary_key=True, autoincrement=False),
        SACol("name", String(50)),
        SACol("qty", Integer),
    )
    meta.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            insert(items),
            [{"id": 1, "name": "Pen", "qty": 3}, {"id": 2, "name": "Book", "qty": 7}],
        )
    return reflect_schema(engine)


def test_duckdb_memory_connection() -> None:
    engine = build_engine(ConnectionConfig(dialect="duckdb", database=":memory:"))
    assert connections.test_connection(engine) is True


def test_duckdb_file_reflect_and_query(tmp_path: Path) -> None:
    db_file = str(tmp_path / "data.duckdb")
    engine = build_engine(ConnectionConfig(dialect="duckdb", database=db_file))
    metadata = _seed(engine)

    assert "items" in list_tables(metadata)
    assert {c.name for c in get_columns(metadata, "items")} == {"id", "name", "qty"}

    spec = QuerySpec(
        main_table="items",
        columns=[
            Column(table="items", name="name", alias="name"),
            Column(table="items", name="qty", alias="qty"),
        ],
    )
    stmt = compile_select(spec, metadata, {})
    with engine.connect() as conn:
        rows = {r["name"]: r["qty"] for r in conn.execute(stmt).mappings()}
    assert rows == {"Pen": 3, "Book": 7}


def test_duckdb_basic_crud(tmp_path: Path) -> None:
    db_file = str(tmp_path / "crud.duckdb")
    engine = build_engine(ConnectionConfig(dialect="duckdb", database=db_file))
    metadata = _seed(engine)
    items = metadata.tables["items"]

    insert_record(engine, items, {"id": 3, "name": "Lamp", "qty": 1})
    update_record(engine, items, {"id": 3}, {"qty": 5})
    with engine.connect() as conn:
        qty = conn.execute(select(items.c.qty).where(items.c.id == 3)).scalar_one()
    assert qty == 5

    delete_record(engine, items, {"id": 3})
    # DuckDB does not always report DELETE rowcount, so verify by querying.
    with engine.connect() as conn:
        remaining = conn.execute(select(items.c.id).where(items.c.id == 3)).all()
    assert remaining == []
