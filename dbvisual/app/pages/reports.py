"""Reports page: read-only data views with params, filters, grouping and charts.

A report is a ``kind='report'`` definition (:class:`ReportSpec`). It never writes
to the target database. Data comes from the query builder or a read-only custom
SQL string; results render in a read-only ``ui.aggrid`` plus an embedded
``ui.echart`` for summary/pivot and time-series charts.
"""

from __future__ import annotations

from typing import Any

from nicegui import ui

from dbvisual.app.ai.ui import ai_generate_dialog, ai_settings_dialog
from dbvisual.app.query_builder import build_queryspec
from dbvisual.app.report_service import (
    ReportSpec,
    aggregate_summary,
    ensure_readonly,
    flatten_group_rows,
    full_text_filter,
    group_with_subtotals,
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
        ui.label("New report").classes("text-lg font-semibold")
        name = ui.input("Report name").classes("w-full")
        app_select = ui.select(
            {a["id"]: a["name"] for a in apps},
            label="Application",
            value=apps[0]["id"] if apps else None,
        ).classes("w-full")
        new_app = ui.input("...or new application").classes("w-full")
        conn_select = ui.select(
            {c["id"]: c["name"] for c in conns}, label="Connection"
        ).classes("w-full")
        source = ui.toggle(
            {"builder": "Query builder", "custom": "Custom SQL (read-only)"},
            value="builder",
        )

        builder_box = ui.column().classes("w-full gap-3")
        custom_box = ui.column().classes("w-full gap-2")
        result = ui.label("").classes("text-sm")
        ctx: dict[str, Any] = {"metadata": None}

        with custom_box:
            custom_sql = ui.textarea(
                placeholder="SELECT ... (read-only, bind with :param)"
            ).classes("w-full")

            def _apply_ai_sql(sql: str) -> None:
                custom_sql.set_value(sql)

            def _open_ai() -> None:
                if conn_select.value is None:
                    ui.notify("Choose a connection first.", type="warning")
                    return
                ai_generate_dialog(int(conn_select.value), _apply_ai_sql)

            with ui.row().classes("gap-2"):
                ui.button(
                    "Generate with AI", icon="auto_awesome", on_click=_open_ai
                ).props("outline size=sm")
                ui.button(
                    "AI settings", icon="settings", on_click=ai_settings_dialog
                ).props("flat size=sm")

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
                result.set_text(f"Schema error: {exc}")
                result.classes(replace="text-sm text-red-600")
                return
            ctx["metadata"] = metadata
            with builder_box:
                main_select = ui.select(tables, label="Main table").classes("w-full")
                cols_select = ui.select([], label="Columns", multiple=True).classes(
                    "w-full"
                )
                rel_select = ui.select(
                    [], label="Related tables", multiple=True
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
                result.set_text("Name and connection are required.")
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
                    result.set_text("Load the schema and choose the main table.")
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
            ui.button("Save", on_click=save).props("color=primary")
            ui.button("Cancel", on_click=dialog.close).props("flat")
        _toggle_source()
    dialog.open()


@ui.page("/reports")
def reports_page() -> None:
    """List saved reports with create / open / delete actions."""
    state = get_state()

    with frame(active="/reports"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Reports").classes("text-2xl font-bold")
            ui.button(
                "New report", icon="add", on_click=lambda: _create_dialog(refresh)
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
                    ui.label("No saved reports.").classes("text-gray-500")
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
            ui.label("Report not found.").classes("text-red-600")
            return
        report = ReportSpec.from_json(definition["queryspec_json"])
        conn = state.store.get_connection(report.connection_id)
        if conn is None:
            ui.label("Connection not available.").classes("text-red-600")
            return
        password = state.secrets.get_password(conn["id"])
        try:
            engine, metadata = resolve_engine(conn, password)
        except Exception as exc:
            ui.label(f"Unable to open the report: {exc}").classes("text-red-600")
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
            ui.input(placeholder="Search in the report...")
            .props("dense clearable")
            .classes("w-72")
        )
        with ui.expansion("Grouping and subtotals", icon="table_rows").classes(
            "w-full"
        ):
            with ui.row().classes("items-end gap-2 flex-wrap"):
                group_sel = ui.select(
                    [], label="Group by (levels)", multiple=True
                ).classes("w-64")
                gval_sel = ui.select([], label="Subtotal field").classes("w-40")
                gagg_sel = ui.select(
                    ["sum", "avg", "count", "min", "max"], value="sum", label="Aggregate"
                ).classes("w-32")
                gsort_sel = ui.select(
                    {"caption": "Caption", "total": "Subtotal"},
                    value="caption",
                    label="Sort groups by",
                ).classes("w-40")
                gdesc = ui.switch("Descending")
                ui.button(
                    "Apply grouping",
                    icon="playlist_add_check",
                    on_click=lambda: apply_grouping(),
                ).props("color=primary")
                ui.button("Clear", icon="clear", on_click=lambda: clear_grouping()).props(
                    "flat"
                )

        grid_box = ui.column().classes("w-full")
        chart_box = ui.column().classes("w-full")

        def _refresh_group_fields(fields: list[str]) -> None:
            group_sel.options = fields
            gval_sel.options = fields
            group_sel.update()
            gval_sel.update()

        def _param_values() -> dict[str, Any]:
            values: dict[str, Any] = {}
            for name, inp in param_inputs.items():
                val = inp.value
                param = next(p for p in report.params if p.name == name)
                if param.multi and isinstance(val, str):
                    val = [v.strip() for v in val.split(",") if v.strip()]
                values[name] = val
            return values

        def _current_rows() -> list[dict[str, Any]]:
            return full_text_filter(
                state_holder["rows"], search.value or "", state_holder["fields"]
            )

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
                        "Export CSV",
                        icon="download",
                        on_click=lambda: grid.run_grid_method("exportDataAsCsv"),
                    ).props("outline size=sm")

        def render_grouped(rows: list[dict[str, Any]]) -> None:
            grid_box.clear()
            detail_fields = state_holder["fields"]
            value_aggs = {gval_sel.value: gagg_sel.value} if gval_sel.value else {}
            tree = group_with_subtotals(
                rows,
                list(group_sel.value or []),
                value_aggs,
                sort_by=gsort_sel.value,
                descending=bool(gdesc.value),
            )
            flat = flatten_group_rows(tree, detail_fields)
            for r in flat:
                if "_group" in r:
                    r["_group"] = ("\u2003" * int(r["_level"])) + r["_group"]
            col_defs: list[dict[str, Any]] = [
                {"headerName": "Group", "field": "_group", "minWidth": 260}
            ]
            col_defs += [{"field": f, "resizable": True} for f in detail_fields]
            col_defs.append({"headerName": "Count", "field": "_count", "maxWidth": 110})
            with grid_box:
                grid = ui.aggrid(
                    {
                        "columnDefs": col_defs,
                        "rowData": flat,
                        "defaultColDef": {"flex": 1, "minWidth": 110},
                        ":getRowStyle": (
                            "params => !params.data ? null : "
                            "(params.data._type === 'subtotal' "
                            "? {fontWeight:'700', background:'#eef2f7'} : "
                            "(params.data._type === 'group' "
                            "? {fontWeight:'700'} : null))"
                        ),
                    }
                ).classes("w-full h-[55vh]")
                state_holder["grid"] = grid
                with ui.row().classes("gap-2 mt-2"):
                    ui.button(
                        "Export CSV",
                        icon="download",
                        on_click=lambda: grid.run_grid_method("exportDataAsCsv"),
                    ).props("outline size=sm")

        def render(rows: list[dict[str, Any]]) -> None:
            if group_sel.value:
                render_grouped(rows)
            else:
                render_grid(rows)

        def apply_grouping() -> None:
            if not state_holder["rows"]:
                ui.notify("Load the data first.", type="warning")
                return
            render(_current_rows())

        def clear_grouping() -> None:
            group_sel.value = []
            render(_current_rows())

        def load() -> None:
            try:
                fields, rows = load_report_rows(
                    engine, metadata, report, _param_values()
                )
            except Exception as exc:
                ui.notify(f"Query error: {exc}", type="negative")
                return
            state_holder["fields"] = fields
            state_holder["rows"] = rows
            _refresh_group_fields(fields)
            render(rows)
            _refresh_chart_fields(fields)

        def apply_search(text_value: str | None) -> None:
            render(_current_rows())

        search.on_value_change(lambda e: apply_search(e.value))

        with ui.row().classes("gap-2"):
            ui.button("Load data", icon="play_arrow", on_click=load).props(
                "color=primary"
            )
            ui.button(
                "Back",
                icon="arrow_back",
                on_click=lambda: ui.navigate.to("/reports"),
            ).props("flat")

        # --- chart builder -------------------------------------------------
        ui.separator()
        ui.label("Chart (summary / pivot)").classes("text-lg font-semibold")
        with ui.row().classes("items-end gap-2 flex-wrap"):
            chart_type = ui.select(
                {"bar": "Column", "line": "Line / time-series", "pie": "Pie"},
                value="bar",
                label="Type",
            ).classes("w-40")
            cat_sel = ui.select([], label="Category").classes("w-40")
            ser_sel = ui.select([], label="Series (opt.)").classes("w-40")
            val_sel = ui.select([], label="Value").classes("w-40")
            agg_sel = ui.select(
                ["sum", "avg", "count", "min", "max"], value="sum", label="Aggreg."
            ).classes("w-32")
            ui.button(
                "Generate", icon="insights", on_click=lambda: build_chart()
            ).props("color=primary")

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
                    "Choose a category and a value, then load the data.", type="warning"
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
