"""Tests for schema introspection."""

from __future__ import annotations

from sqlalchemy import MetaData

from dbvisual.core import connections
from dbvisual.core.connections import ConnectionConfig, build_engine
from dbvisual.core.introspect import (
    detect_foreign_keys,
    get_columns,
    get_primary_key,
    list_tables,
)


def test_build_engine_and_connection() -> None:
    engine = build_engine(ConnectionConfig(dialect="sqlite", database=":memory:"))
    assert connections.test_connection(engine) is True


def test_list_tables(metadata: MetaData) -> None:
    assert list_tables(metadata) == ["customers", "orders"]


def test_get_columns(metadata: MetaData) -> None:
    cols = {c.name: c for c in get_columns(metadata, "customers")}
    assert set(cols) == {"id", "name", "city"}
    assert cols["id"].primary_key is True
    assert cols["name"].nullable is False
    assert cols["city"].nullable is True


def test_get_primary_key(metadata: MetaData) -> None:
    assert get_primary_key(metadata, "orders") == ["id"]


def test_detect_foreign_keys(metadata: MetaData) -> None:
    fks = detect_foreign_keys(metadata, "orders")
    assert len(fks) == 1
    fk = fks[0]
    assert fk.local_col == "customer_id"
    assert fk.remote_table == "customers"
    assert fk.remote_col == "id"


def test_no_foreign_keys_on_parent(metadata: MetaData) -> None:
    assert detect_foreign_keys(metadata, "customers") == []
