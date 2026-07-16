"""Tests for the Sheet layer (service orchestration + app wiring).

The service tests reuse the in-memory ``customers``/``orders`` schema from
``conftest`` and exercise only the core-backed logic (no NiceGUI runtime).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, MetaData, func, select

from dbvisual.app.sheet_service import (
    SheetSpec,
    apply_batch,
    build_operations,
    build_view,
    get_table,
    load_rows,
)
from dbvisual.core.queryspec import Column, QuerySpec, Related
from dbvisual.meta.store import MetadataStore


def _orders_spec() -> QuerySpec:
    """A sheet spec over ``orders`` with a read-only ``customers.name`` lookup."""
    return QuerySpec(
        main_table="orders",
        columns=[
            Column(table="orders", name="id", alias="id"),
            Column(table="orders", name="customer_id", alias="customer_id"),
            Column(table="orders", name="amount", alias="amount"),
            Column(table="customers", name="name", alias="customer"),
        ],
        related=[Related(table="customers", local_col="customer_id", remote_col="id")],
    )


def test_sheetspec_json_roundtrip() -> None:
    spec = SheetSpec(connection_id=7, spec=_orders_spec())
    restored = SheetSpec.from_json(spec.to_json())
    assert restored == spec


def test_definition_roundtrip(tmp_path: Path) -> None:
    store = MetadataStore(tmp_path / "metadata.db")
    app_id = store.create_application("Sales")
    payload = SheetSpec(connection_id=1, spec=_orders_spec()).to_json()
    def_id = store.create_definition(app_id, "sheet", "Orders", payload)

    got = store.get_definition(def_id)
    assert got is not None
    assert got["kind"] == "sheet"
    restored = SheetSpec.from_json(got["queryspec_json"])
    assert restored.spec.main_table == "orders"


def test_build_view_editability(metadata: MetaData) -> None:
    view = build_view(_orders_spec(), metadata)
    editable = {c.field: c.editable for c in view.columns}
    assert editable["id"] is False  # primary key: never editable
    assert editable["customer_id"] is True  # main-table column: editable
    assert editable["amount"] is True
    assert editable["customer"] is False  # related lookup: read-only
    assert view.pk_fields == ["id"]


def test_load_rows_join(engine: Engine, metadata: MetaData) -> None:
    fields, rows = load_rows(engine, metadata, _orders_spec())
    assert set(fields) == {"id", "customer_id", "amount", "customer"}
    by_id = {r["id"]: r for r in rows}
    assert by_id[10]["customer"] == "Alice"
    assert by_id[12]["customer"] == "Bob"


def test_build_operations_ignores_related(metadata: MetaData) -> None:
    view = build_view(_orders_spec(), metadata)
    table = get_table(metadata, "orders")
    # A dirty row that also changes the read-only lookup field.
    updates = [{"id": 10, "amount": 500, "customer": "HACKED"}]
    ops = build_operations(view, table, inserts=[], updates=updates, deletes=[])
    assert len(ops) == 1
    values = ops[0].values
    assert values == {"amount": 500}  # only the editable main column
    assert "customer" not in values and "name" not in values


def test_batch_save_commits(engine: Engine, metadata: MetaData) -> None:
    view = build_view(_orders_spec(), metadata)
    table = get_table(metadata, "orders")
    orders = metadata.tables["orders"]

    ops = build_operations(
        view,
        table,
        inserts=[{"customer_id": 1, "amount": 5}],
        updates=[{"id": 10, "amount": 999}],
        deletes=[{"id": 12}],
    )
    apply_batch(engine, ops)

    with engine.connect() as conn:
        rows = list(conn.execute(select(orders.c.id, orders.c.amount)))
    amounts = {r.id: r.amount for r in rows}
    values = [r.amount for r in rows]
    assert amounts[10] == 999  # updated
    assert all(a != 75 for a in values)  # order 12 (amount 75) was deleted
    assert any(a == 5 for a in values)  # new row inserted
    assert len(rows) == 3  # 3 - 1 delete + 1 insert


def test_batch_save_rolls_back(engine: Engine, metadata: MetaData) -> None:
    view = build_view(_orders_spec(), metadata)
    table = get_table(metadata, "orders")
    orders = metadata.tables["orders"]

    with engine.connect() as conn:
        before = conn.execute(select(func.count()).select_from(orders)).scalar_one()

    # A row missing the NOT NULL ``customer_id`` triggers an integrity error,
    # so the whole batch (including the valid update) must roll back.
    ops = build_operations(
        view,
        table,
        inserts=[
            {"customer_id": 1, "amount": 1},
            {"amount": 2},  # customer_id missing -> NOT NULL violation
        ],
        updates=[{"id": 11, "amount": 888}],
        deletes=[],
    )
    with pytest.raises(Exception):
        apply_batch(engine, ops)

    with engine.connect() as conn:
        after = conn.execute(select(func.count()).select_from(orders)).scalar_one()
        amount_11 = conn.execute(
            select(orders.c.amount).where(orders.c.id == 11)
        ).scalar_one()
    assert after == before  # no inserts persisted
    assert amount_11 == 250  # update rolled back to seeded value


def test_apply_batch_noop(engine: Engine) -> None:
    # Empty op list must not raise.
    apply_batch(engine, [])


def test_sheets_routes_registered() -> None:
    from nicegui import Client

    import dbvisual.app.main  # noqa: F401  (registers routes on import)

    routes = set(Client.page_routes.values())
    assert "/sheets" in routes
    assert "/sheets/{definition_id}" in routes
