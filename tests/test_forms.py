"""Tests for Phase 4: form service, rules, available values and attachments."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, MetaData, select

from dbvisual.app.form_service import (
    AvailableValues,
    ConflictError,
    FieldConfig,
    FormRule,
    FormSpec,
    SubmitRule,
    apply_defaults,
    build_view,
    check_submit_rules,
    delete_form_record,
    evaluate_form_rules,
    get_table,
    load_rows,
    resolve_available_values,
    save_record,
    validate_record,
)
from dbvisual.app.validation import FieldRule
from dbvisual.core.queryspec import Column, QuerySpec, Related
from dbvisual.meta.attachments import AttachmentStore, load_metadata
from dbvisual.meta.store import MetadataStore


def _orders_spec() -> QuerySpec:
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


def _form_spec() -> FormSpec:
    return FormSpec(
        connection_id=1,
        spec=_orders_spec(),
        fields=[
            FieldConfig(field="id", label="ID"),
            FieldConfig(field="customer_id", label="Cliente"),
            FieldConfig(
                field="amount", label="Importo", rule=FieldRule(required=True, min=0)
            ),
            FieldConfig(field="customer", label="Nome cliente"),
        ],
    )


# --- definition round-trip -------------------------------------------------


def test_formspec_definition_roundtrip(tmp_path: Path) -> None:
    store = MetadataStore(tmp_path / "m.db")
    app_id = store.create_application("Sales")
    def_id = store.create_definition(app_id, "form", "Orders", _form_spec().to_json())
    got = store.get_definition(def_id)
    assert got is not None and got["kind"] == "form"
    assert FormSpec.from_json(got["queryspec_json"]).spec.main_table == "orders"


# --- defaults, validation, rules -------------------------------------------


def test_apply_defaults_fills_new_record() -> None:
    fields = [FieldConfig(field="amount", default=10)]
    assert apply_defaults(fields, {})["amount"] == 10
    assert apply_defaults(fields, {"amount": 5})["amount"] == 5


def test_validate_record_blocks_invalid() -> None:
    fields = [FieldConfig(field="amount", rule=FieldRule(required=True, min=0))]
    assert validate_record(fields, {"amount": None})  # required -> error
    assert validate_record(fields, {"amount": -1})  # below min -> error
    assert validate_record(fields, {"amount": 5}) == {}


def test_submit_rule_at_least_one() -> None:
    rule = SubmitRule(kind="at_least_one", fields=["a", "b"], message="Serve A o B.")
    assert check_submit_rules([rule], {"a": None, "b": None}) == ["Serve A o B."]
    assert check_submit_rules([rule], {"a": "x", "b": None}) == []


def test_form_rule_toggles_state() -> None:
    rules = [
        FormRule(
            when_field="kind", op="eq", value="other", action="hide", target="note"
        )
    ]
    hidden = evaluate_form_rules(rules, {"kind": "other"})
    assert hidden["note"]["hidden"] is True
    assert evaluate_form_rules(rules, {"kind": "std"}) == {}


# --- available values (label != value) -------------------------------------


def test_available_values_table_label_differs_from_value(
    engine: Engine, metadata: MetaData
) -> None:
    av = AvailableValues(
        source="table", table="customers", value_col="id", label_col="name"
    )
    options = resolve_available_values(
        engine, metadata, av, main_table="orders", column="customer_id"
    )
    by_value = {o["value"]: o["label"] for o in options}
    # Value stored is the id (1), label shown is the name (Alice).
    assert by_value[1] == "Alice"
    assert 1 in by_value and "Alice" not in by_value


def test_available_values_manual() -> None:
    av = AvailableValues(source="manual", items=[{"value": 1, "label": "One"}])
    # Manual source needs no DB access.
    assert resolve_available_values(
        None,
        None,
        av,
        main_table="orders",
        column="x",  # type: ignore[arg-type]
    ) == [{"value": 1, "label": "One"}]


# --- persistence: save writes value not label, respects locking ------------


def test_save_new_record_writes_editable_only(
    engine: Engine, metadata: MetaData
) -> None:
    view = build_view(_orders_spec(), metadata)
    table = get_table(metadata, "orders")
    # 'customer' is a related lookup -> must never be written.
    record = {"customer_id": 2, "amount": 77, "customer": "IGNORED"}
    save_record(engine, view, table, record, is_new=True)
    with engine.connect() as conn:
        row = conn.execute(
            select(table.c.customer_id, table.c.amount).where(table.c.amount == 77)
        ).first()
    assert row == (2, 77)


def test_save_dropdown_value_is_id(engine: Engine, metadata: MetaData) -> None:
    view = build_view(_orders_spec(), metadata)
    table = get_table(metadata, "orders")
    # The form would show "Bob" but the bound value is the id 2.
    save_record(engine, view, table, {"customer_id": 2, "amount": 5}, is_new=True)
    with engine.connect() as conn:
        cid = conn.execute(
            select(table.c.customer_id).where(table.c.amount == 5)
        ).scalar_one()
    assert cid == 2


def test_update_optimistic_locking_conflict(engine: Engine, metadata: MetaData) -> None:
    view = build_view(_orders_spec(), metadata)
    table = get_table(metadata, "orders")
    _f, records = load_rows(engine, metadata, _orders_spec())
    original = next(r for r in records if r["id"] == 10)

    with engine.begin() as conn:  # concurrent change
        conn.execute(table.update().where(table.c.id == 10).values(amount=1))

    changed = dict(original)
    changed["amount"] = 999
    with pytest.raises(ConflictError):
        save_record(engine, view, table, changed, is_new=False, original=original)
    with engine.connect() as conn:
        assert (
            conn.execute(select(table.c.amount).where(table.c.id == 10)).scalar_one()
            == 1
        )


def test_delete_record(engine: Engine, metadata: MetaData) -> None:
    view = build_view(_orders_spec(), metadata)
    table = get_table(metadata, "orders")
    _f, records = load_rows(engine, metadata, _orders_spec())
    assert delete_form_record(engine, view, table, records[0]) == 1


# --- attachments -----------------------------------------------------------


def test_attachment_upload_and_cascade(tmp_path: Path) -> None:
    store = AttachmentStore(base_dir=tmp_path)
    meta = store.save(1, "rec42", "note.txt", b"hello", "text/plain")
    assert meta["filename"] == "note.txt"
    assert meta["size"] == 5
    assert store.read(1, "rec42", meta["id"]) == b"hello"

    # Simulate the DB text column holding the metadata JSON array.
    from dbvisual.meta.attachments import dump_metadata

    column_text = dump_metadata([meta])
    assert load_metadata(column_text)[0]["filename"] == "note.txt"

    # Cascade delete removes the record's files.
    store.delete_record(1, "rec42")
    with pytest.raises(FileNotFoundError):
        store.read(1, "rec42", meta["id"])


# --- smoke -----------------------------------------------------------------


def test_forms_routes_registered() -> None:
    from nicegui import Client

    import dbvisual.app.main  # noqa: F401

    routes = set(Client.page_routes.values())
    assert "/forms" in routes
    assert "/forms/{definition_id}" in routes
