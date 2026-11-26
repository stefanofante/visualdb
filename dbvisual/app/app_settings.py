"""Generic local app settings (Phase: Settings page).

Small key/value helpers over the same local ``settings.json`` used by the AI and
identity modules — a single settings file, not a parallel config system. Secrets
never live here (they stay in :class:`SecretStore`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from filelock import FileLock
from platformdirs import user_data_dir

from dbvisual.meta.local_files import atomic_write

_APP_NAME = "dbvisual"


def data_dir(data_dir: str | Path | None = None) -> Path:
    """Return the user data directory (where metadata, attachments, vault live)."""
    base = (
        Path(data_dir)
        if data_dir is not None
        else Path(user_data_dir(_APP_NAME, appauthor=False))
    )
    base.mkdir(parents=True, exist_ok=True)
    return base


def _settings_path(dir_override: str | Path | None = None) -> Path:
    return data_dir(dir_override) / "settings.json"


def load_settings(dir_override: str | Path | None = None) -> dict[str, Any]:
    path = _settings_path(dir_override)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Invalid settings file.")
    return data


def get_setting(
    key: str, default: Any = None, dir_override: str | Path | None = None
) -> Any:
    """Return a persisted setting value (or ``default``)."""
    return load_settings(dir_override).get(key, default)


def set_setting(key: str, value: Any, dir_override: str | Path | None = None) -> None:
    """Persist a single setting value."""
    update_settings({key: value}, dir_override)


def update_settings(values, dir_override=None):
    path = _settings_path(dir_override)
    with FileLock(str(path) + ".lock", timeout=10):
        data = load_settings(dir_override)
        data.update(values)
        atomic_write(path, json.dumps(data).encode("utf-8"))


def get_startup_mode(dir_override: str | Path | None = None) -> str:
    """Preferred startup mode: ``"desktop"`` (default) or ``"web"``."""
    mode = get_setting("startup_mode", "desktop", dir_override)
    return mode if mode in ("desktop", "web") else "desktop"


def set_startup_mode(mode: str, dir_override: str | Path | None = None) -> None:
    """Persist the preferred startup mode."""
    set_setting(
        "startup_mode", mode if mode in ("desktop", "web") else "desktop", dir_override
    )
