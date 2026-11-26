"""Acceptance cases for paged editing, conflict reconciliation and form layout."""

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, event, select

from dbvisual.app.components.form_layout import layout_rows
from dbvisual.app.editor_changes import read_conflicts, reconcile, save_reviewed
from dbvisual.app.editor_query import fetch_page
from dbvisual.app.form_service import FieldConfig, FormSpec
from dbvisual.app.query_builder import build_queryspec
from dbvisual.app.sheet_service import build_operations, build_view
from dbvisual.core.crud import ConflictError, Operation, update_record
from dbvisual.core.queryspec import Filter, Param
from dbvisual.meta.attachments import AttachmentDraft, AttachmentStore, dump_metadata


def test_paging_filters_at_database_and_orders_by_whole_key(engine):
    md = MetaData()
    table = Table(
        "invoice_lines",
        md,
        Column("group_id", Integer, primary_key=True),
        Column("line", Integer, primary_key=True),
        Column("label", String),
    )
    md.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            table.insert(),
            [
                {"group_id": grp, "line": n, "label": "item"}
                for n in reversed(range(1500))
                for grp in (2, 1)
            ],
        )
    spec = build_queryspec(md, table.name, ["label"], [])
    spec.params = [Param(name="start", type="integer", required=True)]
    spec.filters = [Filter(column=spec.columns[1], op="ge", param="start")]
    calls = []
    event.listen(
        engine,
        "before_cursor_execute",
        lambda conn, cursor, statement, parameters, context, executemany: calls.append(
            (statement, parameters)
        ),
    )
    with pytest.raises(ValueError, match="Enter a value"):
        fetch_page(engine, md, spec, {}, 0, 25)
    assert calls == []
    first = fetch_page(engine, md, spec, {"start": "1470"}, 0, 25)
    second = fetch_page(engine, md, spec, {"start": "1470"}, 1, 25)
    assert first.has_next and second.has_next
    assert [(r["group_id"], r["line"]) for r in second.rows[:6]] == [
        (1, i) for i in range(1495, 1500)
    ] + [(2, 1470)]
    assert calls[-1][1] == (1470, 26, 25)
    assert "ORDER BY invoice_lines.group_id, invoice_lines.line" in calls[-1][0]


def test_repeated_conflict_keeps_unrelated_upload_and_batch_atomic(engine, tmp_path):
    md = MetaData()
    table = Table(
        "invoices",
        md,
        Column("id", Integer, primary_key=True),
        Column("city", String),
        Column("note", String),
    )
    md.create_all(engine)
    view = build_view(build_queryspec(md, "invoices", ["city", "note"], []), md)
    rows = [
        {"id": 1, "city": "Milan", "note": None},
        {"id": 2, "city": "Turin", "note": None},
    ]
    with engine.begin() as conn:
        conn.execute(table.insert(), rows)
    store = AttachmentStore(tmp_path)
    draft = AttachmentDraft(store, 1)
    item = draft.upload("invoice.txt", b"invoice", "text/plain")
    upload = dump_metadata([item])
    ops = build_operations(
        view,
        table,
        inserts=[],
        deletes=[],
        updates=[dict(rows[0], city="Genoa"), dict(rows[1], note=upload)],
        update_originals=rows,
    )

    def submit():
        save_reviewed(engine, ops, view, draft, ["note"])

    try:
        update_record(engine, table, {"id": 1}, {"city": "Rome"})
        with pytest.raises(ConflictError):
            submit()
        (conflict,) = read_conflicts(engine, ops)
        assert conflict.current["city"] == "Rome"
        ops[0] = reconcile(conflict, {"city"})
        update_record(engine, table, {"id": 1}, {"city": "Pisa"})
        with pytest.raises(ConflictError):
            submit()
        with engine.connect() as conn:
            assert (
                conn.execute(select(table.c.note).where(table.c.id == 2)).scalar_one()
                is None
            )
        (conflict,) = read_conflicts(engine, ops)
        ops[0] = reconcile(conflict, {"city"})
        submit()
        assert store.read(1, "2", item["id"]) == b"invoice"
        with engine.connect() as conn:
            assert (
                conn.execute(select(table.c.city).where(table.c.id == 1)).scalar_one()
                == "Genoa"
            )
    finally:
        draft.close()


def test_deleted_record_requires_explicit_reconfirmation(engine, metadata):
    table = metadata.tables["customers"]
    op = Operation("delete", table, pk_values={"id": 1}, expected={"name": "old name"})
    (conflict,) = read_conflicts(engine, [op])
    assert reconcile(conflict, set()) is None
    assert (
        reconcile(conflict, set(), delete=True).expected["name"]
        == conflict.current["name"]
    )
    op.pk_values = {"id": 999999}
    (missing,) = read_conflicts(engine, [op])
    assert reconcile(missing, set(), delete=True) is None


def test_form_layout_legacy_and_round_trip():
    raw = '{"connection_id":1,"spec":{"main_table":"t"},"fields":[{"field":"city"},{"field":"zip"}]}'
    form = FormSpec.from_json(raw)
    assert [[f.field for f in row] for row in layout_rows(form.fields)] == [
        ["city"],
        ["zip"],
    ]
    form.fields = [
        FieldConfig(field="city", layout_row=1, width=8),
        FieldConfig(field="zip", layout_row=1, width=4),
    ]
    restored = FormSpec.from_json(form.to_json())
    assert [[f.width for f in row] for row in layout_rows(restored.fields)] == [[8, 4]]
