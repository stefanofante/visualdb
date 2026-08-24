"""Packaging smoke tests (Task 6).

Verify the properties a frozen (nicegui-pack / PyInstaller) build relies on:

* user data (metadata DB, attachments, secrets vault, snapshots) resolves via
  ``platformdirs`` and is **independent of** the PyInstaller bundle dir
  (``sys._MEIPASS``), so writes go to a stable, writable location;
* the modules that must be listed as PyInstaller hidden imports are importable;
* encrypted SQLite (SQLCipher) degrades gracefully when the driver is absent.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from dbvisual.app.app_settings import data_dir
from dbvisual.app.snapshot_service import snapshot_dir
from dbvisual.core.connections import (
    ConnectionConfig,
    build_engine,
    encryption_supported,
)
from dbvisual.core.connections import (
    test_connection as check_connection,
)
from dbvisual.meta.store import default_db_path


def test_data_dir_independent_of_meipass(monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulate a frozen bundle whose temp extraction dir is _MEIPASS.
    fake_meipass = Path.cwd() / "_fake_meipass"
    monkeypatch.setattr(sys, "_MEIPASS", str(fake_meipass), raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    resolved = data_dir()
    # The writable data dir must NOT live inside the read-only bundle dir.
    assert not str(resolved).startswith(str(fake_meipass))
    assert not str(default_db_path()).startswith(str(fake_meipass))
    assert not str(snapshot_dir()).startswith(str(fake_meipass))


def test_data_dir_override_is_used(tmp_path: Path) -> None:
    assert data_dir(tmp_path) == tmp_path
    assert snapshot_dir(tmp_path).parent == tmp_path


@pytest.mark.parametrize(
    "module",
    [
        "keyring",
        "cryptography.fernet",
        "openpyxl",
        "platformdirs",
        "dbvisual.app.ai.provider",
        "dbvisual.app.ai.settings",
        "dbvisual.app.ai.ui",
        "dbvisual.app.snapshot_service",
        "dbvisual.app.main",
    ],
)
def test_hidden_import_modules_importable(module: str) -> None:
    assert importlib.import_module(module) is not None


def test_sqlcipher_degrades_gracefully() -> None:
    # Whether or not the driver is installed, the query must return a bool and
    # never raise at import/probe time.
    assert isinstance(encryption_supported("sqlcipher"), bool)


def test_plain_sqlite_engine_still_works(tmp_path: Path) -> None:
    # A non-encrypted local engine must work without any optional driver.
    engine = build_engine(
        ConnectionConfig(dialect="sqlite", database=str(tmp_path / "plain.db"))
    )
    assert check_connection(engine) is True
