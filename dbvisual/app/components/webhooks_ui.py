"""Webhook management dialog (Phase 7), used from the sheet/form design panels.

Lists, creates, edits, tests and deletes the webhooks of a definition. The URL
is stored as a secret (never in the metadata DB).
"""

from __future__ import annotations

import threading
from typing import Any

from nicegui import ui

from dbvisual.app.state import get_state
from dbvisual.app.webhooks import http_post, render_body, webhook_secret_key

_EVENTS = ["created", "updated", "deleted"]


def open_webhooks_dialog(definition_id: int, table_name: str) -> None:
    """Open the webhook manager for a definition targeting ``table_name``."""
    state = get_state()

    with ui.dialog() as dialog, ui.card().classes("w-[640px] gap-3"):
        ui.label("Webhook").classes("text-lg font-semibold")
        ui.label(
            "Invio HTTP POST (JSON) su create/update/delete verso un URL esterno. "
            "L'URL è trattato come segreto e non è salvato in chiaro."
        ).classes("text-sm text-gray-500")
        listing = ui.column().classes("w-full gap-2")

        def refresh() -> None:
            listing.clear()
            hooks = state.store.list_webhooks(definition_id)
            with listing:
                if not hooks:
                    ui.label("Nessun webhook.").classes("text-gray-500")
                for wh in hooks:
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label(f"{wh['name']} · {', '.join(wh['events'])}").classes(
                            "text-sm"
                        )
                        with ui.row().classes("gap-1"):
                            ui.button(
                                icon="edit", on_click=lambda wh=wh: _edit(wh)
                            ).props("flat dense size=sm")
                            ui.button(
                                icon="delete", on_click=lambda wh=wh: _delete(wh)
                            ).props("flat dense color=negative size=sm")

        def _delete(wh: dict[str, Any]) -> None:
            state.secrets.delete_secret(webhook_secret_key(wh["id"]))
            state.store.delete_webhook(wh["id"])
            refresh()

        def _edit(wh: dict[str, Any] | None) -> None:
            _editor(definition_id, table_name, wh, refresh)

        with ui.row().classes("w-full justify-between"):
            ui.button(
                "Aggiungi webhook", icon="add", on_click=lambda: _edit(None)
            ).props("color=primary")
            ui.button("Chiudi", on_click=dialog.close).props("flat")
        refresh()
    dialog.open()


def _editor(
    definition_id: int, table_name: str, wh: dict[str, Any] | None, on_saved
) -> None:
    """New/edit webhook editor dialog."""
    state = get_state()
    existing_url = state.secrets.get_secret(webhook_secret_key(wh["id"])) if wh else ""

    with ui.dialog() as dlg, ui.card().classes("w-[560px] gap-3"):
        ui.label("Nuovo webhook" if wh is None else "Modifica webhook").classes(
            "text-lg font-semibold"
        )
        name = ui.input("Nome", value=(wh or {}).get("name", "")).classes("w-full")
        url = ui.input(
            "URL (segreto)", value=existing_url or "", password=True
        ).classes("w-full")
        ui.label("Eventi").classes("text-sm font-medium")
        selected = set((wh or {}).get("events", ["created"]))
        boxes = {e: ui.checkbox(e, value=e in selected) for e in _EVENTS}
        mode = ui.toggle(
            {"default": "Body default", "custom": "Body custom"},
            value=(wh or {}).get("body_mode", "default"),
        )
        template = ui.textarea(
            "Template body (placeholder {{campo}}, {{campo:formatted}}, {{campo:bare}})",
            value=(wh or {}).get("body_template", "") or "",
        ).classes("w-full")

        def _events() -> list[str]:
            return [e for e, b in boxes.items() if b.value]

        def test() -> None:
            sample = {"id": 1, "example": "valore", table_name: "esempio"}
            body = render_body(sample, mode.value, template.value or None)
            if not url.value:
                ui.notify("Inserisci un URL da testare.", type="warning")
                return
            threading.Thread(
                target=lambda: _safe_post(url.value, body), daemon=True
            ).start()
            ui.notify("Invio di prova avviato.", type="info")

        def save() -> None:
            if not name.value or not _events():
                ui.notify("Nome ed almeno un evento sono obbligatori.", type="negative")
                return
            if wh is None:
                new_id = state.store.create_webhook(
                    definition_id,
                    table_name,
                    name.value,
                    _events(),
                    mode.value,
                    template.value or None,
                )
                if url.value:
                    state.secrets.set_secret(webhook_secret_key(new_id), url.value)
            else:
                state.store.update_webhook(
                    wh["id"],
                    name=name.value,
                    events=_events(),
                    body_mode=mode.value,
                    body_template=template.value or None,
                )
                if url.value:
                    state.secrets.set_secret(webhook_secret_key(wh["id"]), url.value)
            dlg.close()
            on_saved()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Testa", on_click=test).props("outline")
            ui.button("Salva", on_click=save).props("color=primary")
            ui.button("Annulla", on_click=dlg.close).props("flat")
    dlg.open()


def _safe_post(url: str, body: str) -> None:
    try:
        http_post(url, body)
    except Exception:
        pass  # test send failures are non-fatal
