"""Tests for Phase 3 Sheet enrichments: optimistic locking, formulas, validation."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, MetaData, select

from dbvisual.app.formula import FormulaError, evaluate
from dbvisual.app.sheet_service import (
    ConflictError,
    apply_batch,
    build_operations,
    build_view,
    get_table,
    load_rows,
)
from dbvisual.app.validation import FieldRule, validate_field
from dbvisual.core.crud import update_record
from dbvisual.core.queryspec import Column, QuerySpec


def _orders_spec() -> QuerySpec:
    return QuerySpec(
        main_table="orders",
        columns=[
            Column(table="orders", name="id", alias="id"),
            Column(table="orders", name="customer_id", alias="customer_id"),
            Column(table="orders", name="amount", alias="amount"),
        ],
    )


# --- optimistic locking (core + service) -----------------------------------


def test_update_record_locking_conflict(engine: Engine, metadata: MetaData) -> None:
    orders = metadata.tables["orders"]
    # Expected original amount is wrong -> guarded update matches 0 rows.
    with pytest.raises(ConflictError):
        update_record(
            engine, orders, {"id": 10}, {"amount": 1}, expected={"amount": 999}
        )
    # The row is unchanged.
    with engine.connect() as conn:
        amt = conn.execute(
            select(orders.c.amount).where(orders.c.id == 10)
        ).scalar_one()
    assert amt == 100


def test_update_record_locking_success(engine: Engine, metadata: MetaData) -> None:
    orders = metadata.tables["orders"]
    affected = update_record(
        engine, orders, {"id": 10}, {"amount": 150}, expected={"amount": 100}
    )
    assert affected == 1


def test_update_record_without_expected_unchanged_api(
    engine: Engine, metadata: MetaData
) -> None:
    # Existing API (no expected) keeps returning the row count, never raises.
    orders = metadata.tables["orders"]
    assert update_record(engine, orders, {"id": 11}, {"amount": 7}) == 1


def test_batch_optimistic_locking_conflict(engine: Engine, metadata: MetaData) -> None:
    view = build_view(_orders_spec(), metadata)
    table = get_table(metadata, "orders")
    _f, rows = load_rows(engine, metadata, _orders_spec())
    original = next(r for r in rows if r["id"] == 10)

    # Simulate a concurrent change after load.
    with engine.begin() as conn:
        conn.execute(table.update().where(table.c.id == 10).values(amount=42))

    updated = dict(original)
    updated["amount"] = 500
    ops = build_operations(
        view,
        table,
        inserts=[],
        updates=[updated],
        deletes=[],
        update_originals=[original],
    )
    with pytest.raises(ConflictError):
        apply_batch(engine, ops)

    # The concurrent value (42) is preserved; our 500 was rolled back.
    with engine.connect() as conn:
        amt = conn.execute(select(table.c.amount).where(table.c.id == 10)).scalar_one()
    assert amt == 42


# --- safe formula evaluator ------------------------------------------------


def test_formula_arithmetic() -> None:
    assert evaluate("qty * price", {"qty": 3, "price": 4}) == 12
    assert evaluate("(a + b) / 2", {"a": 10, "b": 20}) == 15


def test_formula_functions() -> None:
    assert evaluate("round(x, 1)", {"x": 3.14159}) == 3.1
    assert evaluate("max(a, b, c)", {"a": 1, "b": 9, "c": 5}) == 9


def test_formula_coerces_numeric_strings() -> None:
    assert evaluate("a + b", {"a": "2", "b": "3"}) == 5


def test_formula_rejects_unknown_column() -> None:
    with pytest.raises(FormulaError):
        evaluate("missing + 1", {"a": 1})


def test_formula_rejects_arbitrary_code() -> None:
    for expr in ("__import__('os')", "obj.attr", "open('x')", "().__class__"):
        with pytest.raises(FormulaError):
            evaluate(expr, {})


# --- field validation ------------------------------------------------------


def test_validate_required() -> None:
    assert validate_field(FieldRule(required=True), None)
    assert validate_field(FieldRule(required=True), "")
    assert validate_field(FieldRule(required=True), "x") == []


def test_validate_numeric_range() -> None:
    rule = FieldRule(min=1, max=10)
    assert validate_field(rule, 5) == []
    assert validate_field(rule, 0)
    assert validate_field(rule, 11)


def test_validate_email_and_length() -> None:
    assert validate_field(FieldRule(fmt="email"), "not-an-email")
    assert validate_field(FieldRule(fmt="email"), "a@b.co") == []
    assert validate_field(FieldRule(max_len=3), "toolong")


def test_validate_regex_and_custom_message() -> None:
    rule = FieldRule(regex=r"[A-Z]{3}", message="Codice a 3 lettere maiuscole.")
    assert validate_field(rule, "AB") == ["Codice a 3 lettere maiuscole."]
    assert validate_field(rule, "ABC") == []


def test_validate_credit_card_luhn() -> None:
    assert validate_field(FieldRule(fmt="credit_card"), "4111111111111111") == []
    assert validate_field(FieldRule(fmt="credit_card"), "1234567890123456")
