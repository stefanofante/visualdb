"""Centralized Settings page (single source of truth for app configuration).

Orchestrates the existing modules — it does not reimplement them:
* AI: ``app/ai/settings`` + ``meta/secrets`` (API keys under ``ai:<provider>``).
* Identity / RLS: ``app/identity``.
* General: ``app/app_settings`` (startup mode) + the user data directory path.

Secrets are never shown in clear text: API keys display as *set / not set*.
"""

from __future__ import annotations

from dbvisual.app.ai.provider import DEFAULT_MODELS, PROVIDER_LABELS
from dbvisual.app.ai.settings import (
    AIConfig,
    delete_api_key,
    get_ai_config,
    has_api_key,
    save_api_key,
    set_ai_config,
    test_provider,
)
from dbvisual.app.app_settings import data_dir, get_startup_mode, set_startup_mode
from dbvisual.app.identity import get_identity, set_identity
from dbvisual.app.shell import frame
from dbvisual.app.state import get_state
from nicegui import ui


@ui.page("/settings")
def settings_page() -> None:
    """Render the centralized settings page."""
    state = get_state()

    with frame(active="/settings"):
        ui.label("Impostazioni").classes("text-2xl font-bold")

        # --- AI ------------------------------------------------------------
        with ui.card().classes("w-full max-w-3xl gap-2"):
            ui.label("Assistente AI").classes("text-lg font-semibold")
            ui.label(
                "Off di default. Usando l'AI, schema (nomi tabelle/colonne) e richieste "
                "vengono inviati al provider cloud scelto (costo per token a tuo carico)."
            ).classes("text-xs text-amber-700")
            cfg = get_ai_config()
            enabled = ui.switch("Abilita AI", value=cfg.enabled)
            provider = ui.select(
                PROVIDER_LABELS, label="Provider", value=cfg.provider
            ).classes("w-full")
            model = ui.input(
                "Modello", value=cfg.model or DEFAULT_MODELS.get(cfg.provider, "")
            ).classes("w-full")

            key_status = ui.label("").classes("text-sm")
            new_key = ui.input("Nuova API key (sostituisce)", password=True).classes(
                "w-full"
            )

            def _refresh_status() -> None:
                present = has_api_key(state.secrets, provider.value)
                key_status.set_text(
                    f"API key: {'impostata' if present else 'non impostata'}"
                )
                key_status.classes(
                    replace="text-sm "
                    + ("text-green-600" if present else "text-gray-500")
                )

            def _on_provider() -> None:
                model.value = DEFAULT_MODELS.get(provider.value, "")
                new_key.value = ""
                _refresh_status()

            provider.on_value_change(lambda _e: _on_provider())
            _refresh_status()

            def save_ai() -> None:
                set_ai_config(
                    AIConfig(enabled=bool(enabled.value), provider=provider.value,
                             model=model.value)
                )
                if new_key.value:
                    save_api_key(state.secrets, provider.value, new_key.value)
                    new_key.value = ""
                _refresh_status()
                ui.notify("Impostazioni AI salvate.", type="positive")

            def delete_key() -> None:
                delete_api_key(state.secrets, provider.value)
                _refresh_status()
                ui.notify("API key eliminata.", type="info")

            def test_key() -> None:
                from dbvisual.app.ai.settings import get_api_key

                key = new_key.value or get_api_key(state.secrets, provider.value)
                if not key:
                    ui.notify("Nessuna API key da testare.", type="warning")
                    return
                ok = test_provider(provider.value, key, model.value)
                ui.notify("Test riuscito." if ok else "Test fallito.",
                          type="positive" if ok else "negative")

            with ui.row().classes("gap-2"):
                ui.button("Salva AI", on_click=save_ai).props("color=primary")
                ui.button("Testa", on_click=test_key).props("outline")
                ui.button("Elimina key", on_click=delete_key).props(
                    "flat color=negative")

        # --- Identity / RLS ------------------------------------------------
        with ui.card().classes("w-full max-w-3xl gap-2"):
            ui.label("Identità / Row-Level Security").classes("text-lg font-semibold")
            ui.label(
                "Email usata come app.current_user_email per la RLS PostgreSQL. Vuota = "
                "RLS inattiva. La RLS effettiva dipende dalle policy Postgres e da una "
                "connessione con ruolo NON superuser/owner."
            ).classes("text-xs text-gray-500")
            email = ui.input("Identità corrente (email)", value=get_identity()).classes(
                "w-full"
            )

            def save_identity() -> None:
                set_identity(email.value or "")
                ui.notify("Identità aggiornata.", type="positive")

            ui.button("Salva identità", on_click=save_identity).props("outline")

        # --- General -------------------------------------------------------
        with ui.card().classes("w-full max-w-3xl gap-2"):
            ui.label("Generale").classes("text-lg font-semibold")
            mode = ui.select(
                {"desktop": "Desktop (nativo)", "web": "Web (127.0.0.1)"},
                label="Modalità di avvio preferita",
                value=get_startup_mode(),
            ).classes("w-full")

            def save_mode() -> None:
                set_startup_mode(mode.value)
                ui.notify("Preferenza salvata.", type="positive")

            ui.button("Salva", on_click=save_mode).props("outline")
            ui.label(f"Cartella dati utente: {data_dir()}").classes(
                "text-xs text-gray-500"
            )
            ui.label(
                "Qui risiedono metadata store, allegati e vault dei segreti (mai in chiaro)."
            ).classes("text-xs text-gray-500")
