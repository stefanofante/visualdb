"""About page: app info, description, author, credits, license and links."""

from __future__ import annotations

from nicegui import ui

from dbvisual.app.shell import frame

_SITE_URL = "https://www.stline.it"
_WIKI_URL = "https://www.stline.it/wiki/visualdb/"
_REPO_URL = "https://github.com/stefanofante/visualdb"
_VERSION = "1.0.0.0"

# (name, purpose, url) for the third-party libraries the app is built on.
_CREDITS: list[tuple[str, str, str]] = [
    ("NiceGUI", "user interface", "https://nicegui.io/"),
    ("SQLAlchemy", "database engine (Core 2.0)", "https://www.sqlalchemy.org/"),
    ("Pydantic", "query-spec models", "https://docs.pydantic.dev/"),
    ("keyring", "OS secret storage", "https://github.com/jaraco/keyring"),
    ("cryptography", "encrypted secrets fallback", "https://cryptography.io/"),
    ("platformdirs", "user data locations", "https://github.com/tox-dev/platformdirs"),
    ("openpyxl", "Excel snapshots", "https://openpyxl.readthedocs.io/"),
]


@ui.page("/about")
def about_page() -> None:
    """Render the About page with description, author, credits, license and links."""
    with frame(active="/about"):
        ui.label("About dbvisual").classes("text-2xl font-bold")

        # --- description ---------------------------------------------------
        with ui.card().classes("w-full max-w-3xl gap-2"):
            ui.label("What it does").classes("text-lg font-semibold")
            ui.label(
                "dbvisual is a local, self-contained visual builder for forms, "
                "sheets (Excel-like grids) and reports over existing databases, in "
                "the spirit of Visual DB. It runs entirely on this machine as a "
                "native desktop window or a local web app; no cloud, no remote "
                "account. Everything is generated from a single JSON query-spec: "
                "forms, sheets and reports are just different renders of it."
            ).classes("text-sm text-gray-600")
            ui.label(
                "Supports PostgreSQL, MySQL/MariaDB, SQL Server, Oracle, SQLite and "
                "DuckDB. Features include editable grids with optimistic locking, "
                "validation and computed columns, data-entry forms, read-only "
                "reports with grouping and subtotals, saved views, point-in-time "
                "HTML/Excel snapshots, atomic master-detail, schema/DDL management, "
                "webhooks, PostgreSQL row-level security and an optional read-only "
                "AI query assistant."
            ).classes("text-sm text-gray-600")
            ui.label(f"Version {_VERSION}").classes("text-xs text-gray-500")

        # --- author & license ----------------------------------------------
        with ui.card().classes("w-full max-w-3xl gap-2"):
            ui.label("Author and license").classes("text-lg font-semibold")
            with ui.row().classes("items-center gap-2"):
                ui.icon("person")
                ui.label("Author: Stefano Fante - ST-LINE").classes("text-sm")
            with ui.row().classes("items-center gap-2"):
                ui.icon("balance")
                ui.label(
                    "Released under the MIT License. Copyright (c) 2026 Stefano Fante."
                ).classes("text-sm")

        # --- credits -------------------------------------------------------
        with ui.card().classes("w-full max-w-3xl gap-2"):
            ui.label("Credits").classes("text-lg font-semibold")
            ui.label(
                "Built on open-source software, with thanks to their authors:"
            ).classes("text-sm text-gray-600")
            for name, purpose, url in _CREDITS:
                with ui.row().classes("items-center gap-2"):
                    ui.icon("check").classes("text-gray-400")
                    ui.link(name, url, new_tab=True)
                    ui.label(f"- {purpose}").classes("text-sm text-gray-500")

        # --- links ---------------------------------------------------------
        with ui.card().classes("w-full max-w-3xl gap-3"):
            ui.label("Links").classes("text-lg font-semibold")
            with ui.row().classes("items-center gap-2"):
                ui.icon("public")
                ui.link("ST-LINE - www.stline.it", _SITE_URL, new_tab=True)
            with ui.row().classes("items-center gap-2"):
                ui.icon("menu_book")
                ui.link("User manual (online wiki)", _WIKI_URL, new_tab=True)
            with ui.row().classes("items-center gap-2"):
                ui.icon("code")
                ui.link("Source code on GitHub", _REPO_URL, new_tab=True)

        ui.label("© 2026 Stefano Fante - ST-LINE").classes("text-xs text-gray-400")
