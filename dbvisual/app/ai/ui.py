"""AI assistant UI (Task C): settings dialog and NL→SQL generation dialog.

Both are opt-in. The generation dialog shows the privacy notice, calls the chosen
provider, validates the result with ``ensure_readonly`` and hands the SQL back for
human review — it is never executed automatically.
"""

from __future__ import annotations

from typing import Callable

from nicegui import ui

from dbvisual.app.ai.provider import (
    DEFAULT_MODELS,
    PROVIDER_LABELS,
    get_provider,
)
from dbvisual.app.ai.settings import (
    AIConfig,
    get_ai_config,
    get_api_key,
    save_api_key,
    set_ai_config,
)
from dbvisual.app.report_service import ensure_readonly, resolve_engine
from dbvisual.app.state import get_state
from dbvisual.core.introspect import get_columns, list_tables

_PRIVACY = (
    "Usando l'AI, la struttura del DB (nomi di tabelle e colonne) e il testo della "
    "richiesta vengono inviati al provider cloud scelto. Costo per token a carico "
    "dell'utente. Funzione disattivata di default."
)


def ai_settings_dialog() -> None:
    """Configure provider, model, API key and the enabled flag."""
    state = get_state()
    cfg = get_ai_config()

    with ui.dialog() as dialog, ui.card().classes("w-[560px] gap-3"):
        ui.label("Impostazioni assistente AI").classes("text-lg font-semibold")
        ui.label(_PRIVACY).classes("text-xs text-amber-700")
        enabled = ui.switch("Abilita assistente AI", value=cfg.enabled)
        provider = ui.select(
            PROVIDER_LABELS, label="Provider", value=cfg.provider
        ).classes("w-full")
        model = ui.input(
            "Modello", value=cfg.model or DEFAULT_MODELS.get(cfg.provider, "")
        ).classes("w-full")
        api_key = ui.input(
            "API key (segreta)",
            value=get_api_key(state.secrets, cfg.provider) or "",
            password=True,
        ).classes("w-full")

        def _on_provider() -> None:
            model.value = DEFAULT_MODELS.get(provider.value, "")
            api_key.value = get_api_key(state.secrets, provider.value) or ""

        provider.on_value_change(lambda _e: _on_provider())

        def save() -> None:
            set_ai_config(
                AIConfig(
                    enabled=bool(enabled.value),
                    provider=provider.value,
                    model=model.value,
                )
            )
            if api_key.value:
                save_api_key(state.secrets, provider.value, api_key.value)
            dialog.close()
            ui.notify("Impostazioni AI salvate.", type="positive")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Salva", on_click=save).props("color=primary")
            ui.button("Annulla", on_click=dialog.close).props("flat")
    dialog.open()


def ai_generate_dialog(connection_id: int, on_sql: Callable[[str], None]) -> None:
    """Prompt for a natural-language request and produce a read-only SQL query."""
    state = get_state()
    cfg = get_ai_config()
    if not cfg.enabled:
        ui.notify("Assistente AI disattivato (Impostazioni AI).", type="warning")
        return
    key = get_api_key(state.secrets, cfg.provider)
    if not key:
        ui.notify("Nessuna API key configurata per il provider.", type="warning")
        return

    with ui.dialog() as dialog, ui.card().classes("w-[560px] gap-3"):
        ui.label("Genera SQL con AI").classes("text-lg font-semibold")
        ui.label(_PRIVACY).classes("text-xs text-amber-700")
        prompt = ui.textarea(
            "Descrivi in linguaggio naturale cosa vuoi estrarre"
        ).classes("w-full")
        preview = ui.label("").classes("text-xs text-red-600")

        def generate() -> None:
            conn = state.store.get_connection(connection_id)
            if conn is None:
                preview.set_text("Connessione non trovata.")
                return
            password = state.secrets.get_password(connection_id)
            try:
                engine, metadata = resolve_engine(conn, password)
                schema = {
                    t: [c.name for c in get_columns(metadata, t)]
                    for t in list_tables(metadata)
                }
                provider = get_provider(cfg.provider, key, cfg.model)
                sql = provider.generate_sql(prompt.value or "", schema)
                ensure_readonly(sql)  # reject any non-SELECT before review
            except Exception as exc:
                preview.set_text(f"Errore: {exc}")
                return
            on_sql(sql)
            dialog.close()
            ui.notify("SQL generato: rivedilo prima di eseguire.", type="positive")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Genera", icon="auto_awesome", on_click=generate).props(
                "color=primary"
            )
            ui.button("Annulla", on_click=dialog.close).props("flat")
    dialog.open()
