"""Local current-user identity (Phase 8, minimal — no accounts/login).

A single email declared by the user, persisted in a local JSON settings file
under the app data directory. An empty identity means Row-Level Security stays
inactive (nothing is passed to the database).
"""

from __future__ import annotations

import json
from pathlib import Path

from platformdirs import user_data_dir

_APP_NAME = "dbvisual"


def _settings_path(data_dir: str | Path | None = None) -> Path:
    base = (
        Path(data_dir)
        if data_dir is not None
        else Path(user_data_dir(_APP_NAME, appauthor=False))
    )
    base.mkdir(parents=True, exist_ok=True)
    return base / "settings.json"


def _load(data_dir: str | Path | None = None) -> dict[str, str]:
    path = _settings_path(data_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def get_identity(data_dir: str | Path | None = None) -> str:
    """Return the current user email, or ``""`` when unset."""
    return str(_load(data_dir).get("current_user_email", "") or "")


def set_identity(email: str, data_dir: str | Path | None = None) -> None:
    """Persist the current user email (empty string clears it)."""
    data = _load(data_dir)
    data["current_user_email"] = email or ""
    _settings_path(data_dir).write_text(json.dumps(data), encoding="utf-8")
