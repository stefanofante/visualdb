"""Shared pytest fixtures.

Provides an in-memory SQLite database with two FK-related tables
(``customers`` and ``orders``) plus a reflected :class:`MetaData`.
"""

from __future__ import annotations

import pytest
from sqlalchemy import (
    Column as SAColumn,
)
from sqlalchemy import (
    Engine,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    insert,
)

from dbvisual.core.connections import ConnectionConfig, build_engine
from dbvisual.core.introspect import reflect_schema


@pytest.fixture()
def engine() -> Engine:
    """A fresh in-memory SQLite engine with a seeded two-table schema.

    A ``StaticPool`` keeps the single in-memory database alive across the
    connections opened during a test.
    """
    config = ConnectionConfig(
        dialect="sqlite",
        database=":memory:",
        engine_kwargs={
            "connect_args": {"check_same_thread": False},
            "poolclass": _static_pool(),
        },
    )
    eng = build_engine(config)
    _create_schema(eng)
    _seed(eng)
    return eng


@pytest.fixture()
def metadata(engine: Engine) -> MetaData:
    """The reflected schema for the seeded engine."""
    return reflect_schema(engine)


def _static_pool():
    from sqlalchemy.pool import StaticPool

    return StaticPool


# --- helpers ---------------------------------------------------------------

_meta = MetaData()

customers = Table(
    "customers",
    _meta,
    SAColumn("id", Integer, primary_key=True),
    SAColumn("name", String(100), nullable=False),
    SAColumn("city", String(100), nullable=True),
)

orders = Table(
    "orders",
    _meta,
    SAColumn("id", Integer, primary_key=True),
    SAColumn("customer_id", Integer, ForeignKey("customers.id"), nullable=False),
    SAColumn("amount", Numeric(10, 2), nullable=False),
)


def _create_schema(engine: Engine) -> None:
    _meta.create_all(engine)


def _seed(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            insert(customers),
            [
                {"id": 1, "name": "Alice", "city": "Rome"},
                {"id": 2, "name": "Bob", "city": "Milan"},
                {"id": 3, "name": "Carol", "city": "Rome"},
            ],
        )
        conn.execute(
            insert(orders),
            [
                {"id": 10, "customer_id": 1, "amount": 100},
                {"id": 11, "customer_id": 1, "amount": 250},
                {"id": 12, "customer_id": 2, "amount": 75},
            ],
        )
