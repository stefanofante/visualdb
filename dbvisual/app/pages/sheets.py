"""Sheets page: list, create and open editable Excel-like sheets.

A sheet is a ``kind='sheet'`` definition holding a :class:`SheetSpec`
(query-spec + connection id). Opening a sheet compiles the query with the core,
executes it and renders an editable :class:`SheetGrid`; saving applies all edits
in a single transaction via the core CRUD helpers.
"""

from __future__ import annotations

from typing import Any

from nicegui import ui

from dbvisual.app.components.grid import SheetGrid
from dbvisual.app.query_builder import build_queryspec
from dbvisual.app.sheet_service import (
    ConflictError,
    SheetSpec,
    apply_batch,
    build_operations,
    build_view,
    get_table,
    load_rows,
    resolve_engine,
)
from dbvisual.app.shell import frame
from dbvisual.app.state import get_state
from dbvisual.core.introspect import (
    detect_foreign_keys,
    get_columns,
    list_tables,
)


def _build_queryspec(
    metadata: Any,
    main_table: str,
    main_cols: list[str],
    related_tables: list[str],
) -> QuerySpec:
    """Backward-compatible wrapper around the shared query builder."""
    return build_queryspec(metadata, main_table, main_cols, related_tables)


def _create_dialog(on_saved) -> None:
    """Open the minimal query-builder dialog to create a new sheet."""
    state = get_state()
    apps = state.store.list_applications()
    conns = state.store.list_connections()

    with ui.dialog() as dialog, ui.card().classes("w-[620px] gap-3"):
        ui.label("Nuovo sheet").classes("text-lg font-semibold")

        name = ui.input("Nome sheet").classes("w-full")
        app_select = ui.select(
            {a["id"]: a["name"] for a in apps},
            label="Applicazione",
            value=apps[0]["id"] if apps else None,
        ).classes("w-full")
        new_app = ui.input("…oppure nuova applicazione").classes("w-full")

        conn_select = ui.select(
            {c["id"]: c["name"] for c in conns}, label="Connessione"
        ).classes("w-full")

        schema_box = ui.column().classes("w-full gap-3")
        result = ui.label("").classes("text-sm")
        # Mutable holder shared with the reflect closure.
        ctx: dict[str, Any] = {"metadata": None}

        def load_schema() -> None:
            schema_box.clear()
            cid = conn_select.value
            if cid is None:
                result.set_text("Seleziona una connessione.")
                result.classes(replace="text-sm text-red-600")
                return
            conn = state.store.get_connection(int(cid))
            password = state.secrets.get_password(int(cid))
            if conn is None:
                result.set_text("Connessione non trovata.")
                result.classes(replace="text-sm text-red-600")
                return
            try:
                _engine, metadata = resolve_engine(conn, password, refresh=True)
                tables = list_tables(metadata)
            except Exception as exc:
                result.set_text(f"Errore schema: {exc}")
                result.classes(replace="text-sm text-red-600")
                return
            ctx["metadata"] = metadata
            result.set_text("")
            with schema_box:
                main_select = ui.select(tables, label="Tabella principale").classes(
                    "w-full"
                )
                cols_select = ui.select([], label="Colonne", multiple=True).classes(
                    "w-full"
                )
                rel_select = ui.select(
                    [], label="Tabelle correlate (sola lettura)", multiple=True
                ).classes("w-full")
                ctx.update(main=main_select, cols=cols_select, rel=rel_select)

                def on_main_change() -> None:
                    table = main_select.value
                    if not table:
                        return
                    cols_select.options = [c.name for c in get_columns(metadata, table)]
                    cols_select.value = list(cols_select.options)
                    cols_select.update()
                    rel_select.options = [
                        fk.remote_table for fk in detect_foreign_keys(metadata, table)
                    ]
                    rel_select.value = []
                    rel_select.update()

                main_select.on_value_change(lambda _e: on_main_change())

        conn_select.on_value_change(lambda _e: load_schema())

        def save() -> None:
            metadata = ctx.get("metadata")
            main = ctx.get("main")
            if not name.value:
                result.set_text("Il nome è obbligatorio.")
                result.classes(replace="text-sm text-red-600")
                return
            if metadata is None or main is None or not main.value:
                result.set_text("Carica lo schema e scegli la tabella principale.")
                result.classes(replace="text-sm text-red-600")
                return
            # Resolve target application (existing selection or a new one).
            app_id = int(app_select.value) if app_select.value else None
            if new_app.value:
                app_id = state.store.create_application(new_app.value)
            if app_id is None:
                app_id = state.store.create_application("Default")

            spec = _build_queryspec(
                metadata,
                main.value,
                list(ctx["cols"].value or []),
                list(ctx["rel"].value or []),
            )
            sheet_spec = SheetSpec(connection_id=int(conn_select.value), spec=spec)
            state.store.create_definition(
                app_id=app_id,
                kind="sheet",
                name=name.value,
                queryspec_json=sheet_spec.to_json(),
            )
            dialog.close()
            on_saved()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Salva", on_click=save).props("color=primary")
            ui.button("Annulla", on_click=dialog.close).props("flat")

    dialog.open()


@ui.page("/sheets")
def sheets_page() -> None:
    """List saved sheets with create / open / rename / delete actions."""
    state = get_state()

    with frame(active="/sheets"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Sheet").classes("text-2xl font-bold")
            ui.button(
                "Nuovo sheet", icon="add", on_click=lambda: _create_dialog(refresh)
            ).props("color=primary")

        container = ui.column().classes("w-full gap-2")

        def refresh() -> None:
            container.clear()
            apps = {a["id"]: a["name"] for a in state.store.list_applications()}
            sheets = [d for d in state.store.list_definitions() if d["kind"] == "sheet"]
            with container:
                if not sheets:
                    ui.label("Nessuno sheet salvato.").classes("text-gray-500")
                    return
                for d in sheets:
                    with ui.card().classes("w-full"):
                        with ui.row().classes("w-full items-center justify-between"):
                            with ui.column().classes("gap-0"):
                                ui.label(d["name"]).classes("font-semibold")
                                ui.label(apps.get(d["app_id"], "—")).classes(
                                    "text-sm text-gray-500"
                                )
                            with ui.row().classes("gap-1"):
                                ui.button(
                                    "Apri",
                                    icon="open_in_new",
                                    on_click=lambda d=d: ui.navigate.to(
                                        f"/sheets/{d['id']}"
                                    ),
                                ).props("outline size=sm")
                                ui.button(
                                    icon="edit",
                                    on_click=lambda d=d: _rename(d),
                                ).props("flat size=sm")
                                ui.button(
                                    icon="delete",
                                    on_click=lambda d=d: _delete(d),
                                ).props("flat color=negative size=sm")

        def _rename(d: dict[str, Any]) -> None:
            with ui.dialog() as dlg, ui.card().classes("w-96 gap-3"):
                ui.label("Rinomina sheet").classes("text-lg font-semibold")
                field = ui.input("Nome", value=d["name"]).classes("w-full")

                def apply() -> None:
                    if field.value:
                        state.store.update_definition(d["id"], name=field.value)
                    dlg.close()
                    refresh()

                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("Salva", on_click=apply).props("color=primary")
                    ui.button("Annulla", on_click=dlg.close).props("flat")
            dlg.open()

        def _delete(d: dict[str, Any]) -> None:
            state.store.delete_definition(d["id"])
            refresh()

        refresh()


@ui.page("/sheets/{definition_id}")
def sheet_editor(definition_id: int) -> None:
    """Open a saved sheet as an editable grid with transactional save."""
    state = get_state()

    with frame(active="/sheets"):
        definition = state.store.get_definition(definition_id)
        if definition is None or definition["kind"] != "sheet":
            ui.label("Sheet non trovato.").classes("text-red-600")
            return

        sheet_spec = SheetSpec.from_json(definition["queryspec_json"])
        conn = state.store.get_connection(sheet_spec.connection_id)
        if conn is None:
            ui.label("Connessione dello sheet non disponibile.").classes("text-red-600")
            return

        password = state.secrets.get_password(conn["id"])
        try:
            engine, metadata = resolve_engine(conn, password)
            view = build_view(sheet_spec.spec, metadata)
            _fields, rows = load_rows(engine, metadata, sheet_spec.spec)
        except Exception as exc:
            ui.label(f"Impossibile aprire lo sheet: {exc}").classes("text-red-600")
            return

        with ui.row().classes("w-full items-center justify-between"):
            ui.label(definition["name"]).classes("text-2xl font-bold")
            with ui.row().classes("gap-2"):
                save_btn = ui.button("Salva", icon="save").props("color=primary")
                ui.button(
                    "Indietro",
                    icon="arrow_back",
                    on_click=lambda: ui.navigate.to("/sheets"),
                ).props("flat")

        grid = SheetGrid(view, rows)

        def save() -> None:
            if grid.has_errors():
                ui.notify(
                    "Correggi gli errori di validazione prima di salvare.",
                    type="negative",
                )
                return
            inserts, updates, deletes, originals = grid.collect_changes_with_originals()
            table = get_table(metadata, sheet_spec.spec.main_table)
            ops = build_operations(
                view,
                table,
                inserts=inserts,
                updates=updates,
                deletes=deletes,
                update_originals=originals,
            )
            if not ops:
                ui.notify("Nessuna modifica da salvare.", type="info")
                return
            try:
                apply_batch(engine, ops)
            except ConflictError:
                _f, fresh = load_rows(engine, metadata, sheet_spec.spec)
                grid.reload(fresh)
                ui.notify(
                    "Il record è stato modificato da altri: griglia ricaricata, riprova.",
                    type="warning",
                )
                return
            except Exception as exc:
                ui.notify(f"Salvataggio annullato (rollback): {exc}", type="negative")
                return
            _f, fresh = load_rows(engine, metadata, sheet_spec.spec)
            grid.reload(fresh)
            ui.notify("Modifiche salvate.", type="positive")

        save_btn.on_click(lambda: save())
