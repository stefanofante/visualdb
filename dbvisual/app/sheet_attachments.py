"""Sheet attachment helpers (Task 1): wire the generic attachment store to Sheets.

A Sheet column can be marked as an *attachment* column: its cell value is the
JSON metadata array (``load_metadata``/``dump_metadata``), while the file bytes
live on disk via :class:`AttachmentStore`, keyed by application id + record key.
Deleting a row cascades to its files. Related (lookup) columns are never touched.
"""

from __future__ import annotations

from typing import Any

from dbvisual.app.sheet_service import SheetView
from dbvisual.meta.attachments import AttachmentStore, dump_metadata, load_metadata


def record_key(view: SheetView, row: dict[str, Any]) -> str:
    """Build a stable record key from the row's primary-key fields."""
    parts = [str(row.get(f)) for f in view.pk_fields]
    return "_".join(parts) if parts else "row"


def inserted_record_key(view: SheetView, primary_key) -> str:
    """Project the database key into the same field order used by the saved view."""
    if primary_key is None or not view.pk_fields:
        raise ValueError("An attachment needs a complete record key.")
    columns = view.field_to_column
    keys = primary_key._mapping
    projected = {field: keys.get(columns[field]) for field in view.pk_fields}
    if len(projected) != len(primary_key) or None in projected.values():
        raise ValueError("An attachment needs a complete record key.")
    return record_key(view, projected)


def add_attachment(
    store: AttachmentStore,
    app_id: int,
    key: str,
    current_json: str | None,
    filename: str,
    content: bytes,
    content_type: str = "application/octet-stream",
) -> str:
    """Save a file and return the updated JSON metadata for the cell."""
    meta = store.save(app_id, key, filename, content, content_type)
    items = load_metadata(current_json)
    items.append(meta)
    return dump_metadata(items)


def remove_attachment(
    store: AttachmentStore,
    app_id: int,
    key: str,
    current_json: str | None,
    att_id: str,
) -> str:
    """Delete a single file and return the updated JSON metadata for the cell."""
    store.delete(app_id, key, att_id)
    items = [m for m in load_metadata(current_json) if m.get("id") != att_id]
    return dump_metadata(items)


def cascade_delete_row(store: AttachmentStore, app_id: int, key: str) -> None:
    """Remove all attachment files of a deleted row."""
    store.delete_record(app_id, key)


def attachment_summary(current_json: str | None) -> str:
    """Return a short cell summary, e.g. ``"2 file"`` or ``""``."""
    n = len(load_metadata(current_json))
    return f"{n} file" if n else ""
