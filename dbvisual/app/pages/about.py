"""About page: app info and links to ST-LINE and the online user manual (wiki)."""

from __future__ import annotations

from nicegui import ui

from dbvisual.app.shell import frame

_SITE_URL = "https://www.stline.it"
_WIKI_URL = "https://www.stline.it/wiki/visualdb/"
_REPO_URL = "https://github.com/stefanofante/visualdb"
_VERSION = "1.0.0.0"


@ui.page("/about")
def about_page() -> None:
    """Render the About page with product info and external links."""
    with frame(active="/about"):
        ui.label("About dbvisual").classes("text-2xl font-bold")

        with ui.card().classes("w-full max-w-3xl gap-2"):
            ui.label(
                "Local, self-contained visual builder for forms, sheets and reports "
                "over existing databases. Everything runs on this machine; no cloud."
            ).classes("text-sm text-gray-600")
            ui.label(f"Version {_VERSION} - MIT License").classes(
                "text-xs text-gray-500"
            )

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

        ui.label("© STLine - Stefano Fante").classes("text-xs text-gray-400")
