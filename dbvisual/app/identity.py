"""Local current-user identity (Phase 8, minimal — no accounts/login).

A single email declared by the user, persisted in a local JSON settings file
under the app data directory. An empty identity means Row-Level Security stays
inactive (nothing is passed to the database).
"""

from __future__ import annotations

from pathlib import Path

from dbvisual.app.app_settings import get_setting, set_setting


def get_identity(data_dir: str | Path | None = None) -> str:
    """Return the current user email, or ``""`` when unset."""
    return str(get_setting("current_user_email", "", data_dir) or "")


def set_identity(email: str, data_dir: str | Path | None = None) -> None:
    """Persist the current user email (empty string clears it)."""
    set_setting("current_user_email", email or "", data_dir)
