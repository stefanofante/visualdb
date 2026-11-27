"""Application shell: header + side navigation, shared by every page."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from nicegui import ui

from dbvisual.app.pages.help import help_dialog

# (label, icon, route) for each primary navigation entry.
_NAV: list[tuple[str, str, str]] = [
    ("Connections", "storage", "/connections"),
    ("Database", "schema", "/schema"),
    ("Sheet", "grid_on", "/sheets"),
    ("Form", "dynamic_form", "/forms"),
    ("Report", "insights", "/reports"),
    ("Master-Detail", "account_tree", "/master-detail"),
    ("Applications", "apps", "/applications"),
    ("Settings", "settings", "/settings"),
    ("About", "info", "/about"),
]


@contextmanager
def frame(active: str = "") -> Iterator[None]:
    """Wrap page content in the standard header + left navigation drawer.

    ``active`` is the route of the current page, used to highlight the entry.
    """
    ui.colors(primary="#2563eb")

    ui.add_css("""
        .dbv-page { overflow-wrap: anywhere; }
        .dbv-page .q-field, .q-dialog .q-field { min-width: 0; max-width: 100%; }
        @media (max-width: 480px) {
            .dbv-page .text-2xl { font-size: 20px; line-height: 1.35; }
        }
    """)
    guide = help_dialog()
    with ui.header().classes("items-center justify-between bg-primary text-white"):
        with ui.row().classes("items-center gap-2"):
            ui.button(icon="menu", on_click=lambda: drawer.toggle()).props(
                'flat round color=white aria-label="Navigation"'
            )
            ui.label("dbvisual").classes("text-xl font-bold")
        with ui.row().classes("items-center gap-3"):
            ui.label("Local visual DB builder").classes(
                "hidden sm:block text-sm opacity-80"
            )
            ui.button("Help", icon="help", on_click=guide.open).props(
                "flat color=white"
            ).classes("text-white")

    with ui.left_drawer(value=None, bordered=True).classes("bg-gray-50 p-2") as drawer:
        drawer.props("width=220")
        for label, icon, route in _NAV:
            classes = "w-full justify-start rounded"
            if route == active:
                classes += " bg-blue-100 text-primary font-semibold"
            ui.button(
                label, icon=icon, on_click=lambda r=route: ui.navigate.to(r)
            ).props("flat align=left").classes(classes)

    with ui.column().classes("dbv-page w-full min-w-0 p-2 gap-3 sm:p-6 sm:gap-4"):
        yield
