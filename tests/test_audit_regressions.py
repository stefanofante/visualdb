"""Regressions for editor isolation, transaction boundaries and legacy data."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from openpyxl import load_workbook
from sqlalchemy import (
    Column,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    Table,
    select,
)

from dbvisual.app.app_settings import load_settings, set_setting
from dbvisual.app.query_builder import build_queryspec
from dbvisual.app.schema_service import (
    csv_create_table_ddl,
    insert_csv_rows,
    rows_from_csv,
)
from dbvisual.app.sheet_attachments import inserted_record_key
from dbvisual.app.sheet_service import build_view, load_rows
from dbvisual.app.snapshot_service import write_xlsx_snapshot
from dbvisual.core.crud import (
    ConflictError,
    delete_record,
    insert_record,
)
from dbvisual.core.readonly import ensure_readonly, readonly_result
from dbvisual.core.schema_ddl import DDLPermissionError, execute_ddl
from dbvisual.meta.attachments import (
    AttachmentDraft,
    AttachmentStore,
    dump_metadata,
    load_metadata,
)


def test_sql_mode_restored_after_error_and_on_success(engine):
    with pytest.raises(RuntimeError):
        with readonly_result(
            engine, "WITH c AS (SELECT :n AS value) SELECT value FROM c", {"n": 8}
        ) as result:
            assert result.scalar_one() == 8
            raise RuntimeError("consumer failed")
    with engine.begin() as conn:
        assert conn.exec_driver_sql("PRAGMA query_only").scalar_one() == 0
        conn.exec_driver_sql("PRAGMA query_only = ON")
    try:
        with readonly_result(engine, "SELECT 'update; delete'") as result:
            assert result.scalar_one() == "update; delete"
        with engine.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA query_only").scalar_one() == 1
    finally:
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA query_only = OFF")


@pytest.mark.parametrize(
    "sql", ["SELECT 7; SELECT 8", "CREATE TABLE example (id INTEGER)"]
)
def test_reporting_requires_one_query(sql):
    with pytest.raises(ValueError):
        ensure_readonly(sql, "sqlite")


def test_composite_lookup_and_nullable_row(engine):
    md = MetaData()
    regions = Table(
        "regions",
        md,
        Column("region", Integer, primary_key=True),
        Column("code", Integer, primary_key=True),
        Column("name", String),
    )
    branches = Table(
        "branches",
        md,
        Column("id", Integer, primary_key=True),
        Column("region", Integer),
        Column("code", Integer),
        ForeignKeyConstraint(["region", "code"], ["regions.region", "regions.code"]),
    )
    md.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            regions.insert(),
            [
                {"region": 1, "code": 1, "name": "A"},
                {"region": 1, "code": 2, "name": "B"},
            ],
        )
        conn.execute(
            branches.insert(),
            [
                {"id": 1, "region": 1, "code": 2},
                {"id": 2, "region": None, "code": None},
            ],
        )
    _, rows = load_rows(
        engine, md, build_queryspec(md, "branches", ["id"], ["regions"])
    )
    assert {r["id"]: r["regions_name"] for r in rows} == {1: "B", 2: None}
    with pytest.raises(ValueError, match="complete primary key"):
        delete_record(engine, regions, {"region": 1})
    with pytest.raises(ConflictError):
        delete_record(engine, regions, {"region": 1, "code": 2}, {"name": "previous"})
    with engine.connect() as conn:
        assert len(conn.execute(select(regions)).all()) == 2


def test_attachment_rollback_and_retry_with_generated_key(tmp_path, engine, metadata):
    table = Table("uploads", metadata, Column("id", Integer, primary_key=True), Column("note", String))
    table.create(engine)
    spec = build_queryspec(metadata, "uploads", ["note"], [])
    view = build_view(spec, metadata)
    store = AttachmentStore(tmp_path)
    draft = AttachmentDraft(store, 1)
    item = draft.upload("invoice.txt", b"invoice", "text/plain")
    value = dump_metadata([item])
    seen = []

    def install(pk):
        key = inserted_record_key(view, pk)
        seen.append(key)
        draft.install(key, [value])
        assert store.read(1, key, item["id"]) == b"invoice"

    def abort(pk):
        install(pk)
        raise ValueError("cancel save")

    record = {"note": value}
    try:
        with pytest.raises(ValueError, match="cancel save"):
            insert_record(engine, table, record, before_commit=abort)
        draft.finish(False)
        with pytest.raises(FileNotFoundError):
            store.read(1, seen[-1], item["id"])
        with engine.connect() as conn:
            assert (
                conn.execute(select(table.c.id).where(table.c.note == value)).first()
                is None
            )
        insert_record(engine, table, record, before_commit=install)
        draft.finish(True)
        draft.discard_removed(seen[-1], [value], [value])
        assert store.read(1, seen[-1], item["id"]) == b"invoice"
        draft.discard_removed(seen[-1], [value], [])
        with pytest.raises(FileNotFoundError):
            store.read(1, seen[-1], item["id"])
    finally:
        draft.close()


def test_reads_legacy_attachment_by_its_stored_id(tmp_path):
    store = AttachmentStore(tmp_path)
    item = store.save(1, "new", "legacy.txt", b"legacy")
    assert store.read(1, "42", item["id"]) == b"legacy"
    assert load_metadata(dump_metadata([dict(item, id="invalid")])) == []
    with pytest.raises(ValueError):
        store.read(1, "42", "invalid")


def test_csv_identifier_and_atomicity(engine):
    data = '"select",postal\n5,00123\n'
    name = "order lines"
    ddl, _ = csv_create_table_ddl(engine.dialect, name, data)

    def abort(conn):
        insert_csv_rows(conn, name, data)
        raise ValueError("cancel import")

    with pytest.raises(DDLPermissionError):
        execute_ddl(engine, ddl, after_ddl=abort)
    execute_ddl(engine, ddl, after_ddl=lambda conn: insert_csv_rows(conn, name, data))
    with engine.connect() as conn:
        assert conn.exec_driver_sql('SELECT * FROM "order lines"').one() == (5, "00123")
    with pytest.raises(ValueError):
        rows_from_csv("name,name\nA,B")
    with pytest.raises(ValueError):
        rows_from_csv("name,code\nA")


def test_snapshots_preserve_literal_text_and_previous_exports(tmp_path):
    def save():
        return write_xlsx_snapshot(
            "Invoices",
            ["label", "qty"],
            [{"label": "=1+1", "qty": 4}],
            dir_override=tmp_path,
        )

    first, second = save(), save()
    assert first != second
    sheet = load_workbook(first).active
    assert sheet["A2"].data_type == "s" and sheet["A2"].value == "=1+1"
    assert sheet["B2"].data_type == "n"


def test_settings_preserve_independent_writers(tmp_path):
    with ThreadPoolExecutor(6) as pool:
        list(pool.map(lambda i: set_setting(str(i), i, tmp_path), range(15)))
    assert load_settings(tmp_path) == {str(i): i for i in range(15)}
