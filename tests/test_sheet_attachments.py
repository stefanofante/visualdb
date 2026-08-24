"""Task 1 tests: Sheet attachment column wiring (metadata JSON + files on disk)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import MetaData

from dbvisual.app.sheet_attachments import (
    add_attachment,
    attachment_summary,
    cascade_delete_row,
    record_key,
    remove_attachment,
)
from dbvisual.app.sheet_service import SheetSpec, build_view
from dbvisual.core.queryspec import Column, QuerySpec
from dbvisual.meta.attachments import AttachmentStore, load_metadata


def _view(metadata: MetaData):
    spec = QuerySpec(
        main_table="orders",
        columns=[
            Column(table="orders", name="id", alias="id"),
            Column(table="orders", name="amount", alias="amount"),
            Column(table="orders", name="note", alias="note"),  # attachment column
        ],
    )
    return build_view(spec, metadata)


def test_attachment_field_persisted_in_spec() -> None:
    spec = SheetSpec(
        connection_id=1,
        spec=QuerySpec(main_table="orders"),
        attachment_fields=["note"],
    )
    assert SheetSpec.from_json(spec.to_json()).attachment_fields == ["note"]


def test_upload_stores_metadata_and_file(tmp_path: Path) -> None:
    store = AttachmentStore(base_dir=tmp_path)
    new_json = add_attachment(store, 1, "10", None, "a.txt", b"hello", "text/plain")

    meta = load_metadata(new_json)
    assert len(meta) == 1 and meta[0]["filename"] == "a.txt"
    # The file exists on disk with the expected bytes.
    assert store.read(1, "10", meta[0]["id"]) == b"hello"
    assert attachment_summary(new_json) == "1 file"


def test_remove_attachment(tmp_path: Path) -> None:
    store = AttachmentStore(base_dir=tmp_path)
    j1 = add_attachment(store, 1, "10", None, "a.txt", b"x")
    att_id = load_metadata(j1)[0]["id"]
    j2 = remove_attachment(store, 1, "10", j1, att_id)
    assert load_metadata(j2) == []


def test_row_delete_cascades_files(tmp_path: Path, metadata: MetaData) -> None:
    store = AttachmentStore(base_dir=tmp_path)
    view = _view(metadata)
    row = {"id": 10, "amount": 5, "note": None}
    key = record_key(view, row)
    row["note"] = add_attachment(store, 1, key, None, "a.txt", b"data")
    att_id = load_metadata(row["note"])[0]["id"]
    assert store.read(1, key, att_id) == b"data"

    cascade_delete_row(store, 1, key)
    import pytest

    with pytest.raises(FileNotFoundError):
        store.read(1, key, att_id)


def test_record_key_from_pk(metadata: MetaData) -> None:
    view = _view(metadata)
    assert record_key(view, {"id": 42, "amount": 1, "note": None}) == "42"
