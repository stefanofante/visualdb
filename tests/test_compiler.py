"""Tests for the query-spec models and the compiler."""

from __future__ import annotations

import json

from sqlalchemy import Engine, MetaData

from dbvisual.core.compiler import compile_select
from dbvisual.core.queryspec import Column, Filter, Param, QuerySpec, Related


def test_queryspec_json_roundtrip() -> None:
    spec = QuerySpec(
        main_table="orders",
        columns=[Column(table="orders", name="id", alias="order_id")],
        related=[Related(table="customers", local_col="customer_id", remote_col="id")],
        filters=[
            Filter(
                column=Column(table="customers", name="city"),
                op="eq",
                param="city",
            )
        ],
        params=[Param(name="city", type="string")],
    )
    payload = spec.model_dump_json()
    restored = QuerySpec.model_validate(json.loads(payload))
    assert restored == spec


def test_compile_select_join_and_filter(engine: Engine, metadata: MetaData) -> None:
    spec = QuerySpec(
        main_table="orders",
        columns=[
            Column(table="orders", name="id", alias="order_id"),
            Column(table="orders", name="amount"),
            Column(table="customers", name="name", alias="customer"),
        ],
        related=[Related(table="customers", local_col="customer_id", remote_col="id")],
        filters=[
            Filter(column=Column(table="customers", name="city"), op="eq", param="city")
        ],
        params=[Param(name="city", type="string")],
    )
    stmt = compile_select(spec, metadata, {"city": "Rome"})
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()

    # Alice (Rome) has orders 10 & 11; Bob (Milan) is filtered out.
    assert {r["order_id"] for r in rows} == {10, 11}
    assert all(r["customer"] == "Alice" for r in rows)


def test_compile_select_in_filter(engine: Engine, metadata: MetaData) -> None:
    spec = QuerySpec(
        main_table="orders",
        columns=[Column(table="orders", name="id", alias="order_id")],
        filters=[
            Filter(column=Column(table="orders", name="id"), op="in", param="ids")
        ],
        params=[Param(name="ids", type="integer", multi=True)],
    )
    stmt = compile_select(spec, metadata, {"ids": [10, 12]})
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()
    assert {r["order_id"] for r in rows} == {10, 12}


def test_compile_select_optional_filter_skipped(
    engine: Engine, metadata: MetaData
) -> None:
    spec = QuerySpec(
        main_table="orders",
        columns=[Column(table="orders", name="id", alias="order_id")],
        filters=[Filter(column=Column(table="orders", name="id"), op="eq", param="id")],
        params=[Param(name="id", type="integer")],
    )
    # No value supplied -> filter is skipped -> all rows returned.
    stmt = compile_select(spec, metadata, {})
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()
    assert {r["order_id"] for r in rows} == {10, 11, 12}


def test_compile_select_uses_bound_params(metadata: MetaData) -> None:
    spec = QuerySpec(
        main_table="customers",
        columns=[Column(table="customers", name="id")],
        filters=[
            Filter(column=Column(table="customers", name="city"), op="eq", param="c")
        ],
        params=[Param(name="c", type="string")],
    )
    stmt = compile_select(spec, metadata, {"c": "Rome'; DROP TABLE customers; --"})
    compiled = str(stmt)
    # The raw value must NOT appear inline in the SQL text: it is bound.
    assert "DROP TABLE" not in compiled
    assert ":city" in compiled or ":city_1" in compiled
