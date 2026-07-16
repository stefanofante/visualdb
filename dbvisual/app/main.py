"""Application bootstrap and launcher.

Imports the page modules (which register their ``@ui.page`` routes as a side
effect), wires up the shared state, and exposes :func:`run` to start NiceGUI in
either desktop (native window) or web (127.0.0.1) mode.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from nicegui import ui

from dbvisual.app import state as app_state

# Importing the page modules registers their routes with NiceGUI.
from dbvisual.app.pages import applications as _applications  # noqa: F401
from dbvisual.app.pages import connections as _connections  # noqa: F401
from dbvisual.app.pages import forms as _forms  # noqa: F401
from dbvisual.app.pages import reports as _reports  # noqa: F401
from dbvisual.app.pages import sheets as _sheets  # noqa: F401

Mode = Literal["desktop", "web"]

# NiceGUI 3.x pinned in pyproject: ui.echart renders correctly in native mode
# with this line; see README note if a blank page appears after an upgrade.


def bootstrap(
    db_path: str | Path | None = None,
    *,
    use_keyring: bool = True,
    data_dir: str | Path | None = None,
) -> None:
    """Initialise the shared app state (metadata store + secrets)."""
    app_state.init_state(db_path, use_keyring=use_keyring, data_dir=data_dir)


def run(
    mode: Mode = "desktop",
    host: str = "127.0.0.1",
    port: int = 8080,
    reload: bool = False,
) -> None:
    """Start the NiceGUI event loop.

    * ``desktop`` -> native window via pywebview.
    * ``web``     -> browser UI bound to ``host`` (default 127.0.0.1 only).
    """
    bootstrap()
    common = {
        "title": "dbvisual",
        "reload": reload,
        "storage_secret": "dbvisual-local",
    }
    if mode == "desktop":
        ui.run(native=True, **common)
    else:
        ui.run(host=host, port=port, show=True, **common)
