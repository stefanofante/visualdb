"""Tests for Phase 5: report service (params, filters, aggregation, read-only SQL)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, MetaData

from dbvisual.app.form_service import AvailableValues
from dbvisual.app.report_service import (
    FilterCondition,
    FilterGroup,
    ReportParam,
    ReportSpec,
    aggregate_summary,
    column_totals,
    ensure_readonly,
    filter_rows,
    full_text_filter,
    load_report_rows,
    resolve_param_options,
    run_custom_sql,
)
from dbvisual.core.queryspec import Column, Filter, Param, QuerySpec
from dbvisual.meta.store import MetadataStore


def _builder_spec_with_multi() -> QuerySpec:
    """orders filtered by a multi-value IN on customer_id."""
    return QuerySpec(
        main_table="orders",
        columns=[
            Column(table="orders", name="id", alias="id"),
            Column(table="orders", name="customer_id", alias="customer_id"),
            Column(table="orders", name="amount", alias="amount"),
        ],
        filters=[
            Filter(
                column=Column(table="orders", name="customer_id"),
                op="in",
                param="customers",
            )
        ],
        params=[Param(name="customers", type="integer", multi=True)],
    )


# --- definition round-trip -------------------------------------------------


def test_report_roundtrip_builder(tmp_path: Path) -> None:
    store = MetadataStore(tmp_path / "m.db")
    app_id = store.create_application("Rep")
    report = ReportSpec(
        connection_id=1, source="builder", spec=_builder_spec_with_multi()
    )
    did = store.create_definition(app_id, "report", "R1", report.to_json())
    got = store.get_definition(did)
    assert got is not None and got["kind"] == "report"
    assert ReportSpec.from_json(got["queryspec_json"]).source == "builder"


def test_report_roundtrip_custom() -> None:
    report = ReportSpec(connection_id=1, source="custom", custom_sql="SELECT 1 AS x")
    assert ReportSpec.from_json(report.to_json()).custom_sql == "SELECT 1 AS x"


# --- multi-value parameter -> WHERE IN -------------------------------------


def test_multi_value_param_where_in(engine: Engine, metadata: MetaData) -> None:
    report = ReportSpec(
        connection_id=1, source="builder", spec=_builder_spec_with_multi()
    )
    _f, rows = load_report_rows(engine, metadata, report, {"customers": [1, 2]})
    assert {r["customer_id"] for r in rows} == {1, 2}
    # Customer 1 has orders 10,11; customer 2 has order 12 -> 3 rows.
    assert len(rows) == 3


# --- cascade parameter -----------------------------------------------------


def test_cascade_param_options_depend_on_parent(
    engine: Engine, metadata: MetaData
) -> None:
    # Second param lists orders of the customer chosen in the first.
    param = ReportParam(
        name="order_id",
        depends_on="customer_id",
        available=AvailableValues(
            source="query",
            query="SELECT id, id FROM orders WHERE customer_id = :customer_id",
        ),
    )
    opts_c1 = resolve_param_options(
        engine, metadata, param, parent_values={"customer_id": 1}
    )
    opts_c2 = resolve_param_options(
        engine, metadata, param, parent_values={"customer_id": 2}
    )
    assert {o["value"] for o in opts_c1} == {10, 11}
    assert {o["value"] for o in opts_c2} == {12}


# --- nested AND/OR filters -------------------------------------------------


def test_nested_and_or_filter() -> None:
    rows = [
        {"city": "Rome", "amount": 100},
        {"city": "Rome", "amount": 10},
        {"city": "Milan", "amount": 100},
        {"city": "Turin", "amount": 5},
    ]
    # (city = Rome AND amount >= 50) OR (city = Milan)
    tree = FilterGroup(
        op="or",
        children=[
            FilterGroup(
                op="and",
                children=[
                    FilterCondition(field="city", op="eq", value="Rome"),
                    FilterCondition(field="amount", op="ge", value=50),
                ],
            ),
            FilterCondition(field="city", op="eq", value="Milan"),
        ],
    )
    out = filter_rows(rows, tree)
    assert out == [
        {"city": "Rome", "amount": 100},
        {"city": "Milan", "amount": 100},
    ]


# --- aggregation (summary / pivot) -----------------------------------------


def test_aggregate_summary_pivot() -> None:
    rows = [
        {"product": "A", "region": "N", "sales": 10},
        {"product": "A", "region": "S", "sales": 5},
        {"product": "B", "region": "N", "sales": 7},
        {"product": "A", "region": "N", "sales": 3},
    ]
    summary = aggregate_summary(
        rows, category="product", series="region", value="sales", agg="sum"
    )
    assert summary["categories"] == ["A", "B"]
    by_series = {s["name"]: s["data"] for s in summary["series"]}
    # Region N: A=13, B=7 ; Region S: A=5, B=0
    assert by_series["N"] == [13.0, 7.0]
    assert by_series["S"] == [5.0, 0.0]


def test_column_totals_and_fulltext_recompute() -> None:
    rows = [
        {"city": "Rome", "amount": 100},
        {"city": "Milan", "amount": 50},
        {"city": "Rome", "amount": 20},
    ]
    assert column_totals(rows, {"amount": "sum"}) == {"amount": 170.0}
    filtered = full_text_filter(rows, "rome", ["city"])
    assert column_totals(filtered, {"amount": "sum"}) == {"amount": 120.0}


# --- read-only custom SQL --------------------------------------------------


def test_custom_sql_readonly_bind_param(engine: Engine) -> None:
    fields, rows = run_custom_sql(
        engine,
        "SELECT id, amount FROM orders WHERE customer_id = :cid",
        {"cid": 1},
    )
    assert set(fields) == {"id", "amount"}
    assert {r["id"] for r in rows} == {10, 11}


def test_custom_sql_rejects_writes() -> None:
    for bad in (
        "DELETE FROM orders",
        "UPDATE orders SET amount = 0",
        "INSERT INTO orders VALUES (1)",
        "DROP TABLE orders",
        "SELECT 1; DELETE FROM orders",
    ):
        with pytest.raises(ValueError):
            ensure_readonly(bad)


def test_custom_sql_run_rejects_write(engine: Engine) -> None:
    with pytest.raises(ValueError):
        run_custom_sql(engine, "DELETE FROM orders WHERE id = 10")


# --- smoke -----------------------------------------------------------------


def test_reports_routes_registered() -> None:
    from nicegui import Client

    import dbvisual.app.main  # noqa: F401

    routes = set(Client.page_routes.values())
    assert "/reports" in routes
    assert "/reports/{definition_id}" in routes
