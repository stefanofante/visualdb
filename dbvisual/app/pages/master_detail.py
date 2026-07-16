"""Master-detail page: a master form with linked editable detail grids.

Reuses the Form field widgets (master), the Sheet grid component (details) and
the core transactional save. Master + all detail edits commit atomically.
"""

from __future__ import annotations

from typing import Any

from nicegui import ui

from dbvisual.app.components.form_field import FormField
from dbvisual.app.components.grid import SheetGrid
from dbvisual.app.form_service import FieldConfig
from dbvisual.app.master_detail_service import (
    ConflictError,
    DetailChange,
    DetailQuery,
    MasterDetailSpec,
    build_save_plan,
    execute_save,
    load_details,
    suggest_detail_fk,
)
from dbvisual.app.query_builder import build_queryspec
from dbvisual.app.sheet_service import build_view, get_table, load_rows, resolve_engine
from dbvisual.app.shell import frame
from dbvisual.app.state import get_state
from dbvisual.core.introspect import get_columns, list_tables
from dbvisual.core.queryspec import Column, Filter, Param


def build_detail_query(
    metadata: Any,
    master_table: str,
    detail_table: str,
    cols: list[str],
    related: list[str],
) -> DetailQuery:
    """Build a detail query-spec with a single FK parameter to the master."""
    suggestion = suggest_detail_fk(metadata, master_table, detail_table)
    if suggestion is None:
        raise ValueError(f"Nessuna foreign key da {detail_table} verso {master_table}.")
    fk_column, _remote = suggestion
    spec = build_queryspec(metadata, detail_table, cols, related)
    param_name = f"master_{fk_column}"
    spec.filters.append(
        Filter(
            column=Column(table=detail_table, name=fk_column),
            op="eq",
            param=param_name,
        )
    )
    spec.params.append(Param(name=param_name, type="integer"))
    return DetailQuery(
        title=detail_table, spec=spec, param_name=param_name, fk_column=fk_column
    )


def _create_dialog(on_saved) -> None:
    """Create a master-detail: master query + one or more detail queries."""
    state = get_state()
    apps = state.store.list_applications()
    conns = state.store.list_connections()

    with ui.dialog() as dialog, ui.card().classes("w-[680px] gap-3"):
        ui.label("Nuovo master-detail").classes("text-lg font-semibold")
        name = ui.input("Nome").classes("w-full")
        app_select = ui.select(
            {a["id"]: a["name"] for a in apps},
            label="Applicazione",
            value=apps[0]["id"] if apps else None,
        ).classes("w-full")
        conn_select = ui.select(
            {c["id"]: c["name"] for c in conns}, label="Connessione"
        ).classes("w-full")
        box = ui.column().classes("w-full gap-3")
        result = ui.label("").classes("text-sm")
        ctx: dict[str, Any] = {"metadata": None, "details": []}

        def load_schema() -> None:
            box.clear()
            cid = conn_select.value
            if cid is None:
                return
            conn = state.store.get_connection(int(cid))
            password = state.secrets.get_password(int(cid))
            if conn is None:
                return
            try:
                _e, metadata = resolve_engine(conn, password, refresh=True)
                tables = list_tables(metadata)
            except Exception as exc:
                result.set_text(f"Errore schema: {exc}")
                result.classes(replace="text-sm text-red-600")
                return
            ctx["metadata"] = metadata
            with box:
                master_sel = ui.select(tables, label="Tabella master").classes("w-full")
                detail_sel = ui.select(
                    tables, label="Tabella detail", multiple=True
                ).classes("w-full")
                ctx.update(master=master_sel, details_sel=detail_sel)

        conn_select.on_value_change(lambda _e: load_schema())

        def save() -> None:
            metadata = ctx.get("metadata")
            master = ctx.get("master")
            details_sel = ctx.get("details_sel")
            if not name.value or metadata is None or master is None or not master.value:
                result.set_text("Compila nome, schema e tabella master.")
                result.classes(replace="text-sm text-red-600")
                return
            app_id = int(app_select.value) if app_select.value else None
            if app_id is None:
                app_id = state.store.create_application("Default")
            master_cols = [c.name for c in get_columns(metadata, master.value)]
            master_spec = build_queryspec(metadata, master.value, master_cols, [])
            details: list[DetailQuery] = []
            selected_details = details_sel.value if details_sel else []
            for dtable in selected_details or []:
                dcols = [c.name for c in get_columns(metadata, dtable)]
                try:
                    details.append(
                        build_detail_query(metadata, master.value, dtable, dcols, [])
                    )
                except ValueError as exc:
                    result.set_text(str(exc))
                    result.classes(replace="text-sm text-red-600")
                    return
            md = MasterDetailSpec(
                connection_id=int(conn_select.value),
                master_spec=master_spec,
                details=details,
            )
            state.store.create_definition(
                app_id=app_id,
                kind="master_detail",
                name=name.value,
                queryspec_json=md.to_json(),
            )
            dialog.close()
            on_saved()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Salva", on_click=save).props("color=primary")
            ui.button("Annulla", on_click=dialog.close).props("flat")
    dialog.open()


@ui.page("/master-detail")
def master_detail_page() -> None:
    """List saved master-detail definitions."""
    state = get_state()

    with frame(active="/master-detail"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Master-Detail").classes("text-2xl font-bold")
            ui.button(
                "Nuovo", icon="add", on_click=lambda: _create_dialog(refresh)
            ).props("color=primary")

        container = ui.column().classes("w-full gap-2")

        def refresh() -> None:
            container.clear()
            apps = {a["id"]: a["name"] for a in state.store.list_applications()}
            items = [
                d
                for d in state.store.list_definitions()
                if d["kind"] == "master_detail"
            ]
            with container:
                if not items:
                    ui.label("Nessun master-detail salvato.").classes("text-gray-500")
                    return
                for d in items:
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
                                        f"/master-detail/{d['id']}"
                                    ),
                                ).props("outline size=sm")
                                ui.button(
                                    icon="delete", on_click=lambda d=d: _delete(d)
                                ).props("flat color=negative size=sm")

        def _delete(d: dict[str, Any]) -> None:
            state.store.delete_definition(d["id"])
            refresh()

        refresh()


@ui.page("/master-detail/{definition_id}")
def master_detail_editor(definition_id: int) -> None:
    """Open a master-detail: master form + linked detail grids, atomic save."""
    state = get_state()

    with frame(active="/master-detail"):
        definition = state.store.get_definition(definition_id)
        if definition is None or definition["kind"] != "master_detail":
            ui.label("Master-detail non trovato.").classes("text-red-600")
            return
        md = MasterDetailSpec.from_json(definition["queryspec_json"])
        conn = state.store.get_connection(md.connection_id)
        if conn is None:
            ui.label("Connessione non disponibile.").classes("text-red-600")
            return
        password = state.secrets.get_password(conn["id"])
        try:
            engine, metadata = resolve_engine(conn, password)
            master_view = build_view(md.master_spec, metadata)
            master_table = get_table(metadata, md.master_spec.main_table)
            _f, masters = load_rows(engine, metadata, md.master_spec)
        except Exception as exc:
            ui.label(f"Impossibile aprire: {exc}").classes("text-red-600")
            return

        master_types = {
            c.field: t
            for c in master_view.columns
            for t in [
                {gc.name: gc.type for gc in get_columns(metadata, c.table)}.get(
                    c.column, ""
                )
            ]
        }
        st: dict[str, Any] = {"index": 0, "is_new": not masters}
        master_fields: dict[str, FormField] = {}
        detail_grids: list[tuple[DetailQuery, Any, Any, SheetGrid]] = []

        ui.label(definition["name"]).classes("text-2xl font-bold")
        pos = ui.label("").classes("text-sm text-gray-500")
        master_box = ui.column().classes("w-full max-w-2xl gap-2")
        details_box = ui.column().classes("w-full gap-4")

        def current_master() -> dict[str, Any]:
            if st["is_new"] or not masters:
                return {}
            return masters[st["index"]]

        def master_pk_value(record: dict[str, Any]) -> Any:
            if not master_view.pk_fields:
                return None
            return record.get(master_view.pk_fields[0])

        def render() -> None:
            master_box.clear()
            details_box.clear()
            master_fields.clear()
            detail_grids.clear()
            record = current_master()
            st["original"] = None if st["is_new"] else dict(record)
            total = len(masters)
            shown = 0 if st["is_new"] else st["index"] + 1
            pos.set_text(
                f"Master {shown} di {total}" + (" (nuovo)" if st["is_new"] else "")
            )
            with master_box:
                for c in master_view.columns:
                    fc = FieldConfig(field=c.field, label=c.header)
                    fw = FormField(
                        fc,
                        editable=c.field in master_view.editable_fields,
                        col_type=master_types.get(c.field, ""),
                    )
                    fw.value = record.get(c.field)
                    master_fields[c.field] = fw

            pk_val = master_pk_value(record)
            with details_box:
                for dq in md.details:
                    ui.label(dq.title or dq.spec.main_table).classes(
                        "text-lg font-semibold"
                    )
                    dview = build_view(dq.spec, metadata)
                    dtable = get_table(metadata, dq.spec.main_table)
                    rows: list[dict[str, Any]] = []
                    if pk_val is not None:
                        _df, rows = load_details(engine, metadata, dq, pk_val)
                    grid = SheetGrid(dview, rows)
                    detail_grids.append((dq, dview, dtable, grid))

        def go(delta: int) -> None:
            if not masters:
                return
            st["is_new"] = False
            st["index"] = max(0, min(len(masters) - 1, st["index"] + delta))
            render()

        def new_master() -> None:
            st["is_new"] = True
            render()

        def reload() -> None:
            nonlocal masters
            _f2, masters = load_rows(engine, metadata, md.master_spec)
            st["is_new"] = not masters
            st["index"] = min(st["index"], max(0, len(masters) - 1))
            render()

        def save() -> None:
            master_record = {f: fw.value for f, fw in master_fields.items()}
            errs = [m for fw in master_fields.values() for m in fw.validate()]
            details: list[DetailChange] = []
            for dq, dview, dtable, grid in detail_grids:
                if grid.has_errors():
                    errs.append("detail")
                ins, upd, dele, orig = grid.collect_changes_with_originals()
                details.append(
                    DetailChange(
                        view=dview,
                        table=dtable,
                        fk_column=dq.fk_column,
                        inserts=ins,
                        updates=upd,
                        deletes=dele,
                        update_originals=orig,
                    )
                )
            if errs:
                ui.notify("Correggi gli errori di validazione.", type="negative")
                return
            record = current_master()
            plan = build_save_plan(
                master_view=master_view,
                master_table=master_table,
                master_record=master_record,
                master_is_new=st["is_new"],
                master_original=st.get("original"),
                details=details,
                master_pk_value=None if st["is_new"] else master_pk_value(record),
            )
            try:
                execute_save(engine, plan)
            except ConflictError:
                reload()
                ui.notify(
                    "Conflitto di concorrenza: ricaricato, riprova.", type="warning"
                )
                return
            except Exception as exc:
                ui.notify(f"Salvataggio annullato (rollback): {exc}", type="negative")
                return
            reload()
            ui.notify("Master e detail salvati.", type="positive")

        with ui.row().classes("items-center gap-2"):
            ui.button(icon="chevron_left", on_click=lambda: go(-1)).props("flat")
            ui.button(icon="chevron_right", on_click=lambda: go(1)).props("flat")
            ui.button("Nuovo master", icon="add", on_click=new_master).props("outline")
            ui.button("Salva tutto", icon="save", on_click=save).props("color=primary")
            ui.button(
                "Indietro",
                icon="arrow_back",
                on_click=lambda: ui.navigate.to("/master-detail"),
            ).props("flat")

        render()
