"""Application shell: header + side navigation, shared by every page."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from nicegui import ui

# (label, icon, route) for each primary navigation entry.
_NAV: list[tuple[str, str, str]] = [
    ("Connessioni", "storage", "/connections"),
    ("Sheet", "grid_on", "/sheets"),
    ("Form", "dynamic_form", "/forms"),
    ("Applicazioni", "apps", "/applications"),
]


@contextmanager
def frame(active: str = "") -> Iterator[None]:
    """Wrap page content in the standard header + left navigation drawer.

    ``active`` is the route of the current page, used to highlight the entry.
    """
    ui.colors(primary="#2563eb")

    with ui.header().classes("items-center justify-between bg-primary text-white"):
        with ui.row().classes("items-center gap-2"):
            ui.icon("grid_view").classes("text-2xl")
            ui.label("dbvisual").classes("text-xl font-bold")
        ui.label("Local visual DB builder").classes("text-sm opacity-80")

    with ui.left_drawer(value=True, bordered=True).classes("bg-gray-50 p-2") as drawer:
        drawer.props("width=220")
        for label, icon, route in _NAV:
            classes = "w-full justify-start rounded"
            if route == active:
                classes += " bg-blue-100 text-primary font-semibold"
            ui.button(
                label, icon=icon, on_click=lambda r=route: ui.navigate.to(r)
            ).props("flat align=left").classes(classes)

    with ui.column().classes("w-full p-6 gap-4"):
        yield
