"""Reports page: read-only data views with params, filters, grouping and charts.

A report is a ``kind='report'`` definition (:class:`ReportSpec`). It never writes
to the target database. Data comes from the query builder or a read-only custom
SQL string; results render in a read-only ``ui.aggrid`` plus an embedded
``ui.echart`` for summary/pivot and time-series charts.
"""

from __future__ import annotations

from typing import Any

from nicegui import ui

from dbvisual.app.query_builder import build_queryspec
from dbvisual.app.report_service import (
    ReportSpec,
    aggregate_summary,
    ensure_readonly,
    full_text_filter,
    load_report_rows,
    resolve_engine,
)
from dbvisual.app.shell import frame
from dbvisual.app.state import get_state
from dbvisual.core.introspect import detect_foreign_keys, get_columns, list_tables


def _create_dialog(on_saved) -> None:
    """Create a report from the query builder or a read-only custom SQL string."""
    state = get_state()
    apps = state.store.list_applications()
    conns = state.store.list_connections()

    with ui.dialog() as dialog, ui.card().classes("w-[640px] gap-3"):
        ui.label("Nuovo report").classes("text-lg font-semibold")
        name = ui.input("Nome report").classes("w-full")
        app_select = ui.select(
            {a["id"]: a["name"] for a in apps},
            label="Applicazione",
            value=apps[0]["id"] if apps else None,
        ).classes("w-full")
        new_app = ui.input("…oppure nuova applicazione").classes("w-full")
        conn_select = ui.select(
            {c["id"]: c["name"] for c in conns}, label="Connessione"
        ).classes("w-full")
        source = ui.toggle(
            {"builder": "Query builder", "custom": "SQL custom (sola lettura)"},
            value="builder",
        )

        builder_box = ui.column().classes("w-full gap-3")
        custom_box = ui.column().classes("w-full gap-2")
        result = ui.label("").classes("text-sm")
        ctx: dict[str, Any] = {"metadata": None}

        with custom_box:
            custom_sql = ui.textarea(
                placeholder="SELECT ... (solo lettura, bind con :param)"
            ).classes("w-full")

        def _toggle_source() -> None:
            builder_box.set_visibility(source.value == "builder")
            custom_box.set_visibility(source.value == "custom")

        source.on_value_change(lambda _e: _toggle_source())

        def load_schema() -> None:
            builder_box.clear()
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
            with builder_box:
                main_select = ui.select(tables, label="Tabella principale").classes(
                    "w-full"
                )
                cols_select = ui.select([], label="Colonne", multiple=True).classes(
                    "w-full"
                )
                rel_select = ui.select(
                    [], label="Tabelle correlate", multiple=True
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
            if not name.value or conn_select.value is None:
                result.set_text("Nome e connessione sono obbligatori.")
                result.classes(replace="text-sm text-red-600")
                return
            app_id = int(app_select.value) if app_select.value else None
            if new_app.value:
                app_id = state.store.create_application(new_app.value)
            if app_id is None:
                app_id = state.store.create_application("Default")

            if source.value == "custom":
                try:
                    ensure_readonly(custom_sql.value or "")
                except ValueError as exc:
                    result.set_text(str(exc))
                    result.classes(replace="text-sm text-red-600")
                    return
                report = ReportSpec(
                    connection_id=int(conn_select.value),
                    source="custom",
                    custom_sql=custom_sql.value,
                )
            else:
                metadata = ctx.get("metadata")
                main = ctx.get("main")
                if metadata is None or main is None or not main.value:
                    result.set_text("Carica lo schema e scegli la tabella principale.")
                    result.classes(replace="text-sm text-red-600")
                    return
                spec = build_queryspec(
                    metadata,
                    main.value,
                    list(ctx["cols"].value or []),
                    list(ctx["rel"].value or []),
                )
                report = ReportSpec(
                    connection_id=int(conn_select.value), source="builder", spec=spec
                )
            state.store.create_definition(
                app_id=app_id,
                kind="report",
                name=name.value,
                queryspec_json=report.to_json(),
            )
            dialog.close()
            on_saved()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Salva", on_click=save).props("color=primary")
            ui.button("Annulla", on_click=dialog.close).props("flat")
        _toggle_source()
    dialog.open()


@ui.page("/reports")
def reports_page() -> None:
    """List saved reports with create / open / delete actions."""
    state = get_state()

    with frame(active="/reports"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Report").classes("text-2xl font-bold")
            ui.button(
                "Nuovo report", icon="add", on_click=lambda: _create_dialog(refresh)
            ).props("color=primary")

        container = ui.column().classes("w-full gap-2")

        def refresh() -> None:
            container.clear()
            apps = {a["id"]: a["name"] for a in state.store.list_applications()}
            reports = [
                d for d in state.store.list_definitions() if d["kind"] == "report"
            ]
            with container:
                if not reports:
                    ui.label("Nessun report salvato.").classes("text-gray-500")
                    return
                for d in reports:
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
                                        f"/reports/{d['id']}"
                                    ),
                                ).props("outline size=sm")
                                ui.button(
                                    icon="delete", on_click=lambda d=d: _delete(d)
                                ).props("flat color=negative size=sm")

        def _delete(d: dict[str, Any]) -> None:
            state.store.delete_definition(d["id"])
            refresh()

        refresh()


@ui.page("/reports/{definition_id}")
def report_viewer(definition_id: int) -> None:
    """Open a report: prompt params, load data, show table + chart, export."""
    state = get_state()

    with frame(active="/reports"):
        definition = state.store.get_definition(definition_id)
        if definition is None or definition["kind"] != "report":
            ui.label("Report non trovato.").classes("text-red-600")
            return
        report = ReportSpec.from_json(definition["queryspec_json"])
        conn = state.store.get_connection(report.connection_id)
        if conn is None:
            ui.label("Connessione non disponibile.").classes("text-red-600")
            return
        password = state.secrets.get_password(conn["id"])
        try:
            engine, metadata = resolve_engine(conn, password)
        except Exception as exc:
            ui.label(f"Impossibile aprire il report: {exc}").classes("text-red-600")
            return

        ui.label(definition["name"]).classes("text-2xl font-bold")
        state_holder: dict[str, Any] = {"fields": [], "rows": [], "grid": None}

        # --- parameter prompts (before loading data) -----------------------
        param_inputs: dict[str, Any] = {}
        if report.params:
            with ui.row().classes("w-full items-end gap-2 flex-wrap"):
                for p in sorted(report.params, key=lambda x: x.order):
                    inp = ui.input(p.label or p.name).classes("w-48")
                    param_inputs[p.name] = inp

        search = (
            ui.input(placeholder="Cerca nel report…")
            .props("dense clearable")
            .classes("w-72")
        )
        grid_box = ui.column().classes("w-full")
        chart_box = ui.column().classes("w-full")

        def _param_values() -> dict[str, Any]:
            values: dict[str, Any] = {}
            for name, inp in param_inputs.items():
                val = inp.value
                param = next(p for p in report.params if p.name == name)
                if param.multi and isinstance(val, str):
                    val = [v.strip() for v in val.split(",") if v.strip()]
                values[name] = val
            return values

        def render_grid(rows: list[dict[str, Any]]) -> None:
            grid_box.clear()
            fields = state_holder["fields"]
            with grid_box:
                grid = ui.aggrid(
                    {
                        "columnDefs": [
                            {
                                "field": f,
                                "sortable": True,
                                "filter": True,
                                "resizable": True,
                                "enableRowGroup": True,
                            }
                            for f in fields
                        ],
                        "rowData": rows,
                        "defaultColDef": {"flex": 1, "minWidth": 110},
                    }
                ).classes("w-full h-[55vh]")
                state_holder["grid"] = grid
                with ui.row().classes("gap-2 mt-2"):
                    ui.button(
                        "Esporta CSV",
                        icon="download",
                        on_click=lambda: grid.run_grid_method("exportDataAsCsv"),
                    ).props("outline size=sm")

        def load() -> None:
            try:
                fields, rows = load_report_rows(
                    engine, metadata, report, _param_values()
                )
            except Exception as exc:
                ui.notify(f"Errore query: {exc}", type="negative")
                return
            state_holder["fields"] = fields
            state_holder["rows"] = rows
            render_grid(rows)
            _refresh_chart_fields(fields)

        def apply_search(text_value: str | None) -> None:
            rows = full_text_filter(
                state_holder["rows"], text_value or "", state_holder["fields"]
            )
            render_grid(rows)

        search.on_value_change(lambda e: apply_search(e.value))

        with ui.row().classes("gap-2"):
            ui.button("Carica dati", icon="play_arrow", on_click=load).props(
                "color=primary"
            )
            ui.button(
                "Indietro",
                icon="arrow_back",
                on_click=lambda: ui.navigate.to("/reports"),
            ).props("flat")

        # --- chart builder -------------------------------------------------
        ui.separator()
        ui.label("Grafico (summary / pivot)").classes("text-lg font-semibold")
        with ui.row().classes("items-end gap-2 flex-wrap"):
            chart_type = ui.select(
                {"bar": "Colonna", "line": "Linea / time-series", "pie": "Torta"},
                value="bar",
                label="Tipo",
            ).classes("w-40")
            cat_sel = ui.select([], label="Categoria").classes("w-40")
            ser_sel = ui.select([], label="Serie (opz.)").classes("w-40")
            val_sel = ui.select([], label="Valore").classes("w-40")
            agg_sel = ui.select(
                ["sum", "avg", "count", "min", "max"], value="sum", label="Aggreg."
            ).classes("w-32")
            ui.button("Genera", icon="insights", on_click=lambda: build_chart()).props(
                "color=primary"
            )

        def _refresh_chart_fields(fields: list[str]) -> None:
            for sel in (cat_sel, ser_sel, val_sel):
                sel.options = fields
                sel.update()

        def build_chart() -> None:
            rows = full_text_filter(
                state_holder["rows"], search.value or "", state_holder["fields"]
            )
            if not rows or not cat_sel.value or not val_sel.value:
                ui.notify(
                    "Scegli categoria e valore, poi carica i dati.", type="warning"
                )
                return
            summary = aggregate_summary(
                rows,
                category=cat_sel.value,
                value=val_sel.value,
                series=ser_sel.value or None,
                agg=agg_sel.value,
            )
            chart_box.clear()
            with chart_box:
                ui.echart(_echart_option(chart_type.value, summary)).classes(
                    "w-full h-[40vh]"
                )

        load()


def _echart_option(chart_type: str, summary: dict[str, Any]) -> dict[str, Any]:
    """Build an ECharts option from an aggregated summary."""
    categories = summary["categories"]
    series = summary["series"]
    if chart_type == "pie":
        data = (
            [
                {"name": c, "value": series[0]["data"][i]}
                for i, c in enumerate(categories)
            ]
            if series
            else []
        )
        return {
            "tooltip": {"trigger": "item"},
            "legend": {"top": "bottom"},
            "series": [{"type": "pie", "radius": "60%", "data": data}],
        }
    option: dict[str, Any] = {
        "tooltip": {"trigger": "axis"},
        "legend": {"top": "bottom"},
        "xAxis": {"type": "category", "data": categories},
        "yAxis": {"type": "value"},
        "series": [
            {"name": s["name"], "type": chart_type, "data": s["data"]} for s in series
        ],
    }
    if chart_type == "line":
        # Time-series: zoom + sliding window.
        option["dataZoom"] = [
            {"type": "inside"},
            {"type": "slider"},
        ]
    return option
