"""Placeholder Applications page (fleshed out in later phases)."""

from __future__ import annotations

from nicegui import ui

from dbvisual.app.shell import frame


@ui.page("/applications")
def applications_page() -> None:
    """Show a placeholder until the applications feature lands (Phase 3+)."""
    with frame(active="/applications"):
        ui.label("Applications").classes("text-2xl font-bold")
        ui.label(
            "Coming soon: here you will create forms, sheets and reports from the "
            "saved connections."
        ).classes("text-gray-500")
