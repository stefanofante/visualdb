"""Placeholder Applications page (fleshed out in later phases)."""

from __future__ import annotations

from nicegui import ui

from dbvisual.app.shell import frame


@ui.page("/applications")
def applications_page() -> None:
    """Show a placeholder until the applications feature lands (Phase 3+)."""
    with frame(active="/applications"):
        ui.label("Applicazioni").classes("text-2xl font-bold")
        ui.label(
            "Sezione in arrivo: qui creerai form, sheet e report a partire dalle "
            "connessioni salvate."
        ).classes("text-gray-500")
