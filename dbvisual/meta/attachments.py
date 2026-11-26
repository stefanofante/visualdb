"""Local attachment storage (Phase 4, reusable by Sheets and Forms).

Files never touch the database. The DB text column holds only a JSON array of
attachment *metadata* (``id``, ``filename``, ``content_type``, ``size``); the
file bytes live on local disk under the app data directory, organised per
application and record. Deleting a record cascades to its files.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from platformdirs import user_data_dir

_APP_NAME = "dbvisual"
_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def _safe(text: str) -> str:
    """Make ``text`` safe to use as a folder name."""
    return _SAFE.sub("_", str(text)) or "_"


def _attachment_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise ValueError("Invalid attachment identifier.")
    return value


def load_metadata(text: str | None) -> list[dict[str, Any]]:
    """Parse the JSON metadata array stored in the DB text column."""
    if not text:
        return []
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [
        item
        for item in data
        if isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and re.fullmatch(r"[0-9a-f]{32}", item["id"])
        and isinstance(item.get("filename"), str)
        and isinstance(item.get("size"), int)
    ]


def dump_metadata(items: list[dict[str, Any]]) -> str:
    """Serialize an attachment metadata array for the DB text column."""
    return json.dumps(items)


class AttachmentStore:
    """Store attachment bytes on disk, keyed by application id and record key."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        if base_dir is not None:
            self.base = Path(base_dir)
        else:
            self.base = Path(user_data_dir(_APP_NAME, appauthor=False)) / "attachments"
        self.base.mkdir(parents=True, exist_ok=True)

    def _dir(self, app_id: int, record_key: str, create: bool = True) -> Path:
        path = self.base / f"app_{int(app_id)}" / f"rec_{_safe(record_key)}"
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def save(
        self,
        app_id: int,
        record_key: str,
        filename: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        """Persist ``content`` and return its metadata dict."""
        att_id = uuid4().hex
        (self._dir(app_id, record_key) / att_id).write_bytes(content)
        return {
            "id": att_id,
            "filename": filename,
            "content_type": content_type,
            "size": len(content),
        }

    def _stored_file(self, app_id: int, record_key: str, att_id: str) -> Path:
        att_id = _attachment_id(att_id)
        path = self._dir(app_id, record_key, create=False) / att_id
        # Older releases uploaded under a placeholder before an insert got its key.
        for legacy in ("new", "None"):
            if path.is_file():
                break
            candidate = self._dir(app_id, legacy, create=False) / att_id
            if candidate.is_file():
                return candidate
        return path

    def read(self, app_id: int, record_key: str, att_id: str) -> bytes:
        """Return the bytes of a stored attachment."""
        return self._stored_file(app_id, record_key, att_id).read_bytes()

    def delete(self, app_id: int, record_key: str, att_id: str) -> None:
        """Delete a single attachment file (no-op if missing)."""
        path = self._stored_file(app_id, record_key, att_id)
        if path.exists():
            path.unlink()

    def delete_record(self, app_id: int, record_key: str) -> None:
        """Delete all attachment files for a record (cascade on record delete)."""
        path = self._dir(app_id, record_key, create=False)
        if path.exists():
            shutil.rmtree(path)


class AttachmentDraft:
    """Unsaved uploads belong to one editor. Install bytes before committing row metadata."""

    def __init__(self, store: AttachmentStore, app_id: int):
        from tempfile import TemporaryDirectory

        self.store = store
        self.app_id = app_id
        self._installed = []
        self._temp = TemporaryDirectory(prefix="dbvisual-attachments-")

    def upload(self, filename, content, content_type):
        att_id = uuid4().hex
        (Path(self._temp.name) / att_id).write_bytes(content)
        return {
            "id": att_id,
            "filename": filename,
            "size": len(content),
            "content_type": content_type,
        }

    def read(self, key, att_id):
        path = Path(self._temp.name) / _attachment_id(att_id)
        return (
            path.read_bytes()
            if path.exists()
            else self.store.read(self.app_id, key, att_id)
        )

    def install(self, key, fields):
        for value in fields:
            for item in load_metadata(value):
                att_id = item["id"]
                src = Path(self._temp.name) / att_id
                if src.exists():
                    dest = self.store._dir(self.app_id, key) / att_id
                    # UUIDs are unique; retries can reinstall the same draft.
                    if not dest.exists():
                        self._installed.append(dest)
                        shutil.copyfile(src, dest)

    def finish(self, committed: bool):
        if not committed:
            for path in self._installed:
                path.unlink(missing_ok=True)
        self._installed.clear()

    def discard_removed(self, key, old_fields, new_fields):
        retained = {item["id"] for value in new_fields for item in load_metadata(value)}
        for value in old_fields:
            for item in load_metadata(value):
                if item["id"] not in retained:
                    self.store.delete(self.app_id, key, item["id"])

    def close(self):
        self._temp.cleanup()
