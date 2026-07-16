"""Lightweight smoke test for the NiceGUI app wiring.

Verifies that importing the app registers the expected page routes and that the
shared state can be bootstrapped against a temporary metadata store, without
launching a UI window or an event loop.
"""

from __future__ import annotations

from pathlib import Path

from nicegui import Client

from dbvisual.app import main as app_main
from dbvisual.app import state as app_state


def test_pages_are_registered() -> None:
    routes = set(Client.page_routes.values())
    assert {"/", "/connections", "/applications"} <= routes


def test_bootstrap_uses_temp_store(tmp_path: Path) -> None:
    app_main.bootstrap(tmp_path / "metadata.db", use_keyring=False, data_dir=tmp_path)
    state = app_state.get_state()
    # A round-trip through the store confirms the wiring is functional.
    cid = state.store.create_connection(name="smoke", dialect="sqlite")
    state.secrets.save_password(cid, "pw")
    assert state.secrets.get_password(cid) == "pw"
    assert [c["name"] for c in state.store.list_connections()] == ["smoke"]
