"""Saved-views dialog — save/load/delete named view configs for a definition.

A *view* is a JSON config blob (filters, grouping, columns, search, ...) bound to
a ``definition_id``. Views are ``private`` (visible only to the current identity)
or ``shared`` (visible to everyone), and may be ``locked`` (immutable). The dialog
is generic: the caller supplies a ``capture`` callback (returns the current config)
and an ``apply_config`` callback (applies a chosen config).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from dbvisual.app.identity import get_identity
from dbvisual.app.state import get_state

__all__ = ["open_views_dialog"]


def open_views_dialog(
    definition_id: int,
    capture: Callable[[], dict[str, Any]],
    apply_config: Callable[[dict[str, Any]], None],
) -> None:
    """Open the saved-views manager for ``definition_id``."""
    state = get_state()
    identity = get_identity() or None

    with ui.dialog() as dialog, ui.card().classes("w-[620px] gap-3"):
        ui.label("Saved views").classes("text-lg font-semibold")
        ui.label(
            "Private views are visible only to the current identity; shared views to "
            "everyone. A locked view cannot be modified."
        ).classes("text-xs text-gray-500")
        listing = ui.column().classes("w-full gap-2")

        def refresh() -> None:
            listing.clear()
            rows = state.store.list_views(definition_id, identity)
            with listing:
                if not rows:
                    ui.label("No saved views.").classes("text-gray-500")
                for v in rows:
                    with ui.row().classes("w-full items-center justify-between"):
                        tags = v["scope"] + (" - locked" if v["locked"] else "")
                        ui.label(f"{v['name']} ({tags})").classes("text-sm")
                        with ui.row().classes("gap-1"):
                            ui.button(
                                "Load",
                                icon="open_in_new",
                                on_click=lambda v=v: _load(v),
                            ).props("flat dense size=sm")
                            ui.button(
                                icon="delete", on_click=lambda v=v: _delete(v)
                            ).props("flat dense color=negative size=sm")

        def _load(v: dict[str, Any]) -> None:
            apply_config(v["config"])
            dialog.close()
            ui.notify(f"View '{v['name']}' loaded.", type="positive")

        def _delete(v: dict[str, Any]) -> None:
            state.store.delete_view(v["id"])
            refresh()

        ui.separator()
        with ui.row().classes("w-full items-end gap-2"):
            name = ui.input("New view name").classes("grow")
            scope = ui.select(
                {"private": "Private", "shared": "Shared"},
                value="private",
                label="Scope",
            ).classes("w-32")
            locked = ui.checkbox("Locked")

            def _save() -> None:
                if not name.value:
                    ui.notify("Enter a name.", type="warning")
                    return
                state.store.create_view(
                    definition_id,
                    name.value,
                    capture(),
                    scope=scope.value,
                    locked=bool(locked.value),
                    owner_identity=identity,
                )
                name.value = ""
                refresh()
                ui.notify("View saved.", type="positive")

            ui.button("Save current", icon="save", on_click=_save).props(
                "color=primary"
            )

        with ui.row().classes("w-full justify-end"):
            ui.button("Close", on_click=dialog.close).props("flat")
        refresh()
    dialog.open()
