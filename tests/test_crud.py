"""Tests for the generic CRUD helpers."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, MetaData, func, select

from dbvisual.core.crud import (
    Operation,
    delete_record,
    insert_record,
    save_master_detail,
    update_record,
)


def _count(engine: Engine, table) -> int:
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(table)).scalar_one()


def test_insert_record(engine: Engine, metadata: MetaData) -> None:
    customers = metadata.tables["customers"]
    before = _count(engine, customers)
    pk = insert_record(engine, customers, {"id": 4, "name": "Dan", "city": "Turin"})
    assert _count(engine, customers) == before + 1
    assert pk[0] == 4


def test_update_record(engine: Engine, metadata: MetaData) -> None:
    customers = metadata.tables["customers"]
    affected = update_record(engine, customers, {"id": 1}, {"city": "Naples"})
    assert affected == 1
    with engine.connect() as conn:
        city = conn.execute(
            select(customers.c.city).where(customers.c.id == 1)
        ).scalar_one()
    assert city == "Naples"


def test_delete_record(engine: Engine, metadata: MetaData) -> None:
    orders = metadata.tables["orders"]
    before = _count(engine, orders)
    affected = delete_record(engine, orders, {"id": 12})
    assert affected == 1
    assert _count(engine, orders) == before - 1


def test_save_master_detail_commits(engine: Engine, metadata: MetaData) -> None:
    customers = metadata.tables["customers"]
    orders = metadata.tables["orders"]
    master = Operation(
        kind="insert",
        table=customers,
        values={"id": 5, "name": "Eve", "city": "Genoa"},
    )
    details = [
        Operation(
            kind="insert",
            table=orders,
            values={"id": 20, "customer_id": 5, "amount": 42},
        ),
        Operation(
            kind="insert",
            table=orders,
            values={"id": 21, "customer_id": 5, "amount": 99},
        ),
    ]
    results = save_master_detail(engine, master, details)
    assert len(results) == 3
    with engine.connect() as conn:
        n = conn.execute(
            select(func.count()).select_from(orders).where(orders.c.customer_id == 5)
        ).scalar_one()
    assert n == 2


def test_save_master_detail_rolls_back(engine: Engine, metadata: MetaData) -> None:
    customers = metadata.tables["customers"]
    orders = metadata.tables["orders"]
    before_customers = _count(engine, customers)
    before_orders = _count(engine, orders)

    master = Operation(
        kind="insert",
        table=customers,
        values={"id": 6, "name": "Frank", "city": "Bari"},
    )
    details = [
        Operation(
            kind="insert",
            table=orders,
            values={"id": 30, "customer_id": 6, "amount": 10},
        ),
        # Duplicate primary key -> integrity error -> whole tx rolls back.
        Operation(
            kind="insert",
            table=orders,
            values={"id": 30, "customer_id": 6, "amount": 20},
        ),
    ]

    with pytest.raises(Exception):
        save_master_detail(engine, master, details)

    # Nothing must have been persisted.
    assert _count(engine, customers) == before_customers
    assert _count(engine, orders) == before_orders
