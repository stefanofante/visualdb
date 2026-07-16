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


def load_metadata(text: str | None) -> list[dict[str, Any]]:
    """Parse the JSON metadata array stored in the DB text column."""
    if not text:
        return []
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


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
        path = self.base / f"app_{app_id}" / f"rec_{_safe(record_key)}"
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

    def read(self, app_id: int, record_key: str, att_id: str) -> bytes:
        """Return the bytes of a stored attachment."""
        return (self._dir(app_id, record_key, create=False) / att_id).read_bytes()

    def delete(self, app_id: int, record_key: str, att_id: str) -> None:
        """Delete a single attachment file (no-op if missing)."""
        path = self._dir(app_id, record_key, create=False) / att_id
        if path.exists():
            path.unlink()

    def delete_record(self, app_id: int, record_key: str) -> None:
        """Delete all attachment files for a record (cascade on record delete)."""
        path = self._dir(app_id, record_key, create=False)
        if path.exists():
            shutil.rmtree(path)
