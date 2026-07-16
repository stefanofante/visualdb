"""Forms page: list, create and open single-record data-entry forms.

A form is a ``kind='form'`` definition holding a :class:`FormSpec`. The editor
shows one record at a time (prev/next), applies per-field validation, cross-field
submit rules and conditional form rules, saves through the core with optimistic
locking, and supports attachment fields.
"""

from __future__ import annotations

from typing import Any

from nicegui import ui

from dbvisual.app.components.form_field import FormField
from dbvisual.app.form_service import (
    ConflictError,
    FieldConfig,
    FormSpec,
    apply_defaults,
    build_view,
    check_submit_rules,
    delete_form_record,
    evaluate_form_rules,
    get_table,
    load_rows,
    resolve_available_values,
    resolve_engine,
    save_record,
)
from dbvisual.app.query_builder import build_queryspec
from dbvisual.app.shell import frame
from dbvisual.app.state import get_state
from dbvisual.core.introspect import detect_foreign_keys, get_columns, list_tables
from dbvisual.meta.attachments import AttachmentStore


def _auto_fields(spec_columns: list[Any], main_table: str) -> list[FieldConfig]:
    """Create default field configs from the query columns."""
    return [
        FieldConfig(field=c.alias or c.name, label=c.alias or c.name)
        for c in spec_columns
    ]


def _create_dialog(on_saved) -> None:
    """Open the query-builder dialog to create a new form."""
    state = get_state()
    apps = state.store.list_applications()
    conns = state.store.list_connections()

    with ui.dialog() as dialog, ui.card().classes("w-[620px] gap-3"):
        ui.label("Nuovo form").classes("text-lg font-semibold")
        name = ui.input("Nome form").classes("w-full")
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
        ctx: dict[str, Any] = {"metadata": None}

        def load_schema() -> None:
            schema_box.clear()
            cid = conn_select.value
            if cid is None:
                return
            conn = state.store.get_connection(int(cid))
            password = state.secrets.get_password(int(cid))
            if conn is None:
                return
            try:
                _engine, metadata = resolve_engine(conn, password, refresh=True)
                tables = list_tables(metadata)
            except Exception as exc:
                result.set_text(f"Errore schema: {exc}")
                result.classes(replace="text-sm text-red-600")
                return
            ctx["metadata"] = metadata
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
            if not name.value or metadata is None or main is None or not main.value:
                result.set_text("Compila nome, schema e tabella principale.")
                result.classes(replace="text-sm text-red-600")
                return
            app_id = int(app_select.value) if app_select.value else None
            if new_app.value:
                app_id = state.store.create_application(new_app.value)
            if app_id is None:
                app_id = state.store.create_application("Default")
            spec = build_queryspec(
                metadata,
                main.value,
                list(ctx["cols"].value or []),
                list(ctx["rel"].value or []),
            )
            form_spec = FormSpec(
                connection_id=int(conn_select.value),
                spec=spec,
                fields=_auto_fields(spec.columns, main.value),
            )
            state.store.create_definition(
                app_id=app_id,
                kind="form",
                name=name.value,
                queryspec_json=form_spec.to_json(),
            )
            dialog.close()
            on_saved()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Salva", on_click=save).props("color=primary")
            ui.button("Annulla", on_click=dialog.close).props("flat")
    dialog.open()


@ui.page("/forms")
def forms_page() -> None:
    """List saved forms with create / open / rename / delete actions."""
    state = get_state()

    with frame(active="/forms"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Form").classes("text-2xl font-bold")
            ui.button(
                "Nuovo form", icon="add", on_click=lambda: _create_dialog(refresh)
            ).props("color=primary")

        container = ui.column().classes("w-full gap-2")

        def refresh() -> None:
            container.clear()
            apps = {a["id"]: a["name"] for a in state.store.list_applications()}
            forms = [d for d in state.store.list_definitions() if d["kind"] == "form"]
            with container:
                if not forms:
                    ui.label("Nessun form salvato.").classes("text-gray-500")
                    return
                for d in forms:
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
                                        f"/forms/{d['id']}"
                                    ),
                                ).props("outline size=sm")
                                ui.button(
                                    icon="delete", on_click=lambda d=d: _delete(d)
                                ).props("flat color=negative size=sm")

        def _delete(d: dict[str, Any]) -> None:
            state.store.delete_definition(d["id"])
            refresh()

        refresh()


@ui.page("/forms/{definition_id}")
def form_editor(definition_id: int) -> None:
    """Open a saved form: navigate records, edit, save and delete."""
    state = get_state()

    with frame(active="/forms"):
        definition = state.store.get_definition(definition_id)
        if definition is None or definition["kind"] != "form":
            ui.label("Form non trovato.").classes("text-red-600")
            return
        form_spec = FormSpec.from_json(definition["queryspec_json"])
        conn = state.store.get_connection(form_spec.connection_id)
        if conn is None:
            ui.label("Connessione non disponibile.").classes("text-red-600")
            return

        password = state.secrets.get_password(conn["id"])
        try:
            engine, metadata = resolve_engine(conn, password)
            view = build_view(form_spec.spec, metadata)
            _f, records = load_rows(engine, metadata, form_spec.spec)
        except Exception as exc:
            ui.label(f"Impossibile aprire il form: {exc}").classes("text-red-600")
            return

        table = get_table(metadata, form_spec.spec.main_table)
        attachments = AttachmentStore()
        col_types = _column_types(metadata, view)

        st: dict[str, Any] = {"index": 0, "is_new": not records, "original": None}
        fields: dict[str, FormField] = {}

        ui.label(definition["name"]).classes("text-2xl font-bold")
        pos = ui.label("").classes("text-sm text-gray-500")
        fields_box = ui.column().classes("w-full max-w-2xl gap-2")

        def current_record() -> dict[str, Any]:
            if st["is_new"] or not records:
                return apply_defaults(form_spec.fields, {})
            return records[st["index"]]

        def gather() -> dict[str, Any]:
            return {f: fw.value for f, fw in fields.items()}

        def apply_rules() -> None:
            state_map = evaluate_form_rules(form_spec.form_rules, gather())
            for f, fw in fields.items():
                s = state_map.get(f, {})
                fw.set_state(
                    hidden=s.get("hidden", False), disabled=s.get("disabled", False)
                )

        def render() -> None:
            fields_box.clear()
            fields.clear()
            record = current_record()
            pk_val = "new" if st["is_new"] else _record_key(view, record)
            st["original"] = None if st["is_new"] else dict(record)
            total = len(records)
            shown = 0 if st["is_new"] else st["index"] + 1
            pos.set_text(
                f"Record {shown} di {total}" + (" (nuovo)" if st["is_new"] else "")
            )
            with fields_box:
                for fc in form_spec.fields:
                    editable = fc.field in view.editable_fields
                    options = _options_for(engine, metadata, form_spec, fc, view)
                    fw = FormField(
                        fc,
                        editable=editable,
                        col_type=col_types.get(fc.field, ""),
                        options=options,
                        on_change=apply_rules,
                        attachments=attachments,
                        record_key=str(pk_val),
                        app_id=definition["app_id"],
                    )
                    fw.value = record.get(fc.field)
                    fields[fc.field] = fw
            apply_rules()

        def go(delta: int) -> None:
            if not records:
                return
            st["is_new"] = False
            st["index"] = max(0, min(len(records) - 1, st["index"] + delta))
            render()

        def new_record() -> None:
            st["is_new"] = True
            render()

        def reload() -> None:
            nonlocal records
            _f2, records = load_rows(engine, metadata, form_spec.spec)
            st["is_new"] = not records
            st["index"] = min(st["index"], max(0, len(records) - 1))
            render()

        def save() -> None:
            record = gather()
            errs = [m for fw in fields.values() for m in fw.validate()]
            if errs:
                ui.notify("Correggi gli errori evidenziati.", type="negative")
                return
            violations = check_submit_rules(form_spec.submit_rules, record)
            if violations:
                ui.notify("; ".join(violations), type="negative")
                return
            try:
                save_record(
                    engine,
                    view,
                    table,
                    record,
                    is_new=st["is_new"],
                    original=st["original"],
                )
            except ConflictError:
                reload()
                ui.notify(
                    "Il record è stato modificato da altri: ricaricato, riprova.",
                    type="warning",
                )
                return
            except Exception as exc:
                ui.notify(f"Salvataggio fallito: {exc}", type="negative")
                return
            reload()
            ui.notify("Record salvato.", type="positive")

        def delete() -> None:
            if st["is_new"] or not records:
                return
            record = records[st["index"]]
            delete_form_record(engine, view, table, record)
            attachments.delete_record(definition["app_id"], _record_key(view, record))
            reload()
            ui.notify("Record eliminato.", type="positive")

        with ui.row().classes("items-center gap-2"):
            ui.button(icon="chevron_left", on_click=lambda: go(-1)).props("flat")
            ui.button(icon="chevron_right", on_click=lambda: go(1)).props("flat")
            ui.button("Nuovo", icon="add", on_click=new_record).props("outline")
            ui.button("Salva", icon="save", on_click=save).props("color=primary")
            ui.button("Elimina", icon="delete", on_click=delete).props(
                "flat color=negative"
            )
            ui.button(
                "Indietro", icon="arrow_back", on_click=lambda: ui.navigate.to("/forms")
            ).props("flat")

        render()


# -- helpers ----------------------------------------------------------------


def _column_types(metadata: Any, view: Any) -> dict[str, str]:
    """Map each view field to its SQL column type string."""
    types: dict[str, str] = {}
    by_table: dict[str, dict[str, str]] = {}
    for col in view.columns:
        if col.table not in by_table:
            by_table[col.table] = {
                c.name: c.type for c in get_columns(metadata, col.table)
            }
        types[col.field] = by_table[col.table].get(col.column, "")
    return types


def _record_key(view: Any, record: dict[str, Any]) -> str:
    """Build a stable string key from the record's primary-key fields."""
    return "_".join(str(record.get(f)) for f in view.pk_fields) or "row"


def _options_for(engine, metadata, form_spec, fc, view) -> list[dict[str, Any]]:
    """Resolve available-value options for a field, or an empty list."""
    if fc.available.source == "none":
        return []
    field_to_col = view.field_to_column
    column = field_to_col.get(fc.field, fc.field)
    try:
        return resolve_available_values(
            engine,
            metadata,
            fc.available,
            main_table=form_spec.spec.main_table,
            column=column,
        )
    except Exception:
        return []
