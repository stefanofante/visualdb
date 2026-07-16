"""Database tab (Phase 9): visual schema browser and editor with reviewed DDL.

Every schema change composes DDL, shows the exact SQL in a **review dialog** and
runs it only after explicit confirmation (double confirmation for destructive
operations). The DDL channel is separate from the report read-only guard.
"""

from __future__ import annotations

from typing import Any, Callable

from nicegui import ui

from dbvisual.app.ai.settings import get_ai_config, get_api_key
from dbvisual.app.schema_service import (
    csv_create_table_ddl,
    generate_ddl_via_ai,
    rows_from_csv,
    table_to_csv,
)
from dbvisual.app.sheet_service import get_table, resolve_engine
from dbvisual.app.shell import frame
from dbvisual.app.state import get_state
from dbvisual.core.introspect import (
    detect_foreign_keys,
    get_columns,
    list_tables,
    reflect_schema,
)
from dbvisual.core.schema_ddl import (
    ColumnSpec,
    DDLNotSupported,
    ForeignKeySpec,
    TableSpec,
    compose_add_column,
    compose_create_table,
    compose_drop_column,
    compose_drop_table,
    execute_ddl,
    logical_types,
)


def _review_and_execute(
    engine: Any, sql: str, *, destructive: bool, on_done: Callable[[], None]
) -> None:
    """Show the exact SQL and execute only after (double) confirmation."""
    with ui.dialog() as dialog, ui.card().classes("w-[620px] gap-3"):
        ui.label("Rivedi ed esegui").classes("text-lg font-semibold")
        if destructive:
            ui.label(
                "⚠ Operazione DISTRUTTIVA: perdita di dati/struttura irreversibile."
            ).classes("text-red-600 font-semibold")
        ui.code(sql, language="sql").classes("w-full")
        confirm = ui.checkbox("Confermo di aver letto l'SQL") if destructive else None

        def run() -> None:
            if destructive and not (confirm and confirm.value):
                ui.notify("Conferma richiesta per un'operazione distruttiva.", type="warning")
                return
            try:
                execute_ddl(engine, sql)
            except Exception as exc:
                ui.notify(str(exc), type="negative")
                return
            dialog.close()
            on_done()
            ui.notify("DDL eseguito.", type="positive")

        with ui.row().classes("w-full justify-end gap-2"):
            label = "Esegui (conferma)" if destructive else "Esegui"
            ui.button(label, on_click=run).props(
                "color=negative" if destructive else "color=primary"
            )
            ui.button("Annulla", on_click=dialog.close).props("flat")
    dialog.open()


@ui.page("/schema")
def schema_page() -> None:
    """The Database tab: pick a connection, browse and edit its schema."""
    state = get_state()
    conns = state.store.list_connections()

    with frame(active="/schema"):
        ui.label("Database (schema)").classes("text-2xl font-bold")
        ui.label(
            "Il DDL viene sempre mostrato e richiede conferma esplicita; le operazioni "
            "distruttive richiedono doppia conferma. Serve un utente con privilegi DDL."
        ).classes("text-sm text-gray-500")

        conn_select = ui.select(
            {c["id"]: c["name"] for c in conns}, label="Connessione"
        ).classes("w-96")
        body = ui.column().classes("w-full gap-3")
        ctx: dict[str, Any] = {}

        def load() -> None:
            body.clear()
            cid = conn_select.value
            if cid is None:
                return
            conn = state.store.get_connection(int(cid))
            password = state.secrets.get_password(int(cid))
            if conn is None:
                return
            try:
                engine, metadata = resolve_engine(conn, password, refresh=True)
                tables = list_tables(metadata)
            except Exception as exc:
                with body:
                    ui.label(f"Errore schema: {exc}").classes("text-red-600")
                return
            ctx.update(engine=engine, metadata=metadata, dialect=engine.dialect,
                       conn=conn, tables=tables)
            _render(engine, metadata, tables)

        def refresh() -> None:
            load()

        def _render(engine: Any, metadata: Any, tables: list[str]) -> None:
            body.clear()
            with body:
                with ui.row().classes("gap-2"):
                    ui.button("Crea tabella", icon="add_box",
                              on_click=lambda: _create_table_dialog(refresh)).props(
                        "color=primary"
                    )
                    ui.button("Importa CSV", icon="upload_file",
                              on_click=lambda: _import_csv_dialog(refresh)).props("outline")
                    ui.button("Diagramma relazioni", icon="account_tree",
                              on_click=lambda: _diagram_dialog()).props("outline")
                if not tables:
                    ui.label("Nessuna tabella.").classes("text-gray-500")
                for table in tables:
                    columns = get_columns(metadata, table)
                    fks = detect_foreign_keys(metadata, table)
                    with ui.expansion(table, icon="table_chart").classes("w-full"):
                        ui.aggrid({
                            "columnDefs": [
                                {"headerName": "Colonna", "field": "name"},
                                {"headerName": "Tipo", "field": "type"},
                                {"headerName": "Nullable", "field": "nullable"},
                                {"headerName": "PK", "field": "pk"},
                            ],
                            "rowData": [
                                {"name": c.name, "type": c.type,
                                 "nullable": c.nullable, "pk": c.primary_key}
                                for c in columns
                            ],
                        }).classes("h-48")
                        for fk in fks:
                            ui.label(
                                f"FK: {fk.local_col} → {fk.remote_table}.{fk.remote_col}"
                            ).classes("text-sm font-mono")
                        with ui.row().classes("gap-2"):
                            ui.button("Aggiungi colonna", icon="add",
                                      on_click=lambda t=table: _add_column_dialog(t, refresh)
                                      ).props("flat size=sm")
                            ui.button("Elimina colonna", icon="remove",
                                      on_click=lambda t=table, cols=columns:
                                      _drop_column_dialog(t, cols, refresh)
                                      ).props("flat size=sm color=negative")
                            ui.button("Esporta CSV", icon="download",
                                      on_click=lambda t=table: _export_csv(t)).props(
                                "flat size=sm")
                            ui.button("Elimina tabella", icon="delete",
                                      on_click=lambda t=table: _drop_table(t, refresh)
                                      ).props("flat size=sm color=negative")

        # -- operations -----------------------------------------------------

        def _create_table_dialog(on_done: Callable[[], None]) -> None:
            engine, dialect = ctx["engine"], ctx["dialect"]
            with ui.dialog() as dlg, ui.card().classes("w-[680px] gap-2"):
                ui.label("Crea tabella").classes("text-lg font-semibold")
                name = ui.input("Nome tabella").classes("w-full")
                rows_box = ui.column().classes("w-full gap-1")
                col_rows: list[dict[str, Any]] = []

                def add_row(cname: str = "", ctype: str = "text") -> None:
                    with rows_box:
                        with ui.row().classes("items-center gap-2") as row:
                            n = ui.input("Colonna", value=cname).classes("w-40")
                            t = ui.select(logical_types(), value=ctype).classes("w-32")
                            pk = ui.checkbox("PK")
                            nn = ui.checkbox("NOT NULL")
                            entry = {"n": n, "t": t, "pk": pk, "nn": nn, "row": row}
                            ui.button(icon="close", on_click=lambda e=entry: _remove(e)
                                      ).props("flat dense")
                            col_rows.append(entry)

                def _remove(entry: dict[str, Any]) -> None:
                    rows_box.remove(entry["row"])
                    col_rows.remove(entry)

                add_row("id", "integer")
                ui.button("Aggiungi colonna", icon="add", on_click=lambda: add_row()
                          ).props("flat size=sm")

                def compose_and_review() -> None:
                    specs = [
                        ColumnSpec(name=e["n"].value, type=e["t"].value,
                                   primary_key=bool(e["pk"].value),
                                   nullable=not e["nn"].value)
                        for e in col_rows if e["n"].value
                    ]
                    if not name.value or not specs:
                        ui.notify("Nome e almeno una colonna richiesti.", type="warning")
                        return
                    sql = compose_create_table(dialect, TableSpec(name.value, specs))
                    dlg.close()
                    _review_and_execute(engine, sql, destructive=False, on_done=on_done)

                with ui.row().classes("w-full justify-between"):
                    ui.button("Genera con AI", icon="auto_awesome",
                              on_click=lambda: _ai_ddl(name, on_done, dlg)).props("outline")
                    with ui.row().classes("gap-2"):
                        ui.button("Rivedi DDL", on_click=compose_and_review).props(
                            "color=primary")
                        ui.button("Annulla", on_click=dlg.close).props("flat")
            dlg.open()

        def _ai_ddl(name_input: Any, on_done: Callable[[], None], parent: Any) -> None:
            cfg = get_ai_config()
            key = get_api_key(state.secrets, cfg.provider)
            if not cfg.enabled or not key:
                ui.notify("Assistente AI disattivato o senza API key (Impostazioni).",
                          type="warning")
                return
            with ui.dialog() as dlg, ui.card().classes("w-[560px] gap-2"):
                ui.label("Genera DDL con AI").classes("text-lg font-semibold")
                ui.label(
                    "La descrizione viene inviata al provider cloud scelto."
                ).classes("text-xs text-amber-700")
                prompt = ui.textarea("Descrivi la tabella").classes("w-full")

                def go() -> None:
                    engine, metadata = ctx["engine"], ctx["metadata"]
                    schema = {t: [c.name for c in get_columns(metadata, t)]
                              for t in list_tables(metadata)}
                    try:
                        sql = generate_ddl_via_ai(cfg.provider, key, cfg.model,
                                                  prompt.value or "", schema,
                                                  ctx["dialect"].name)
                    except Exception as exc:
                        ui.notify(f"Errore AI: {exc}", type="negative")
                        return
                    dlg.close()
                    parent.close()
                    _review_and_execute(engine, sql, destructive=False, on_done=on_done)

                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("Genera", on_click=go).props("color=primary")
                    ui.button("Annulla", on_click=dlg.close).props("flat")
            dlg.open()

        def _add_column_dialog(table: str, on_done: Callable[[], None]) -> None:
            engine, dialect = ctx["engine"], ctx["dialect"]
            with ui.dialog() as dlg, ui.card().classes("w-[480px] gap-2"):
                ui.label(f"Aggiungi colonna — {table}").classes("text-lg font-semibold")
                cname = ui.input("Nome colonna").classes("w-full")
                ctype = ui.select(logical_types(), value="text").classes("w-full")
                nn = ui.checkbox("NOT NULL")

                def go() -> None:
                    if not cname.value:
                        return
                    sql = compose_add_column(
                        dialect, table,
                        ColumnSpec(cname.value, ctype.value, nullable=not nn.value))
                    dlg.close()
                    _review_and_execute(engine, sql, destructive=False, on_done=on_done)

                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("Rivedi DDL", on_click=go).props("color=primary")
                    ui.button("Annulla", on_click=dlg.close).props("flat")
            dlg.open()

        def _drop_column_dialog(table: str, columns: Any, on_done) -> None:
            engine, dialect = ctx["engine"], ctx["dialect"]
            with ui.dialog() as dlg, ui.card().classes("w-[420px] gap-2"):
                ui.label(f"Elimina colonna — {table}").classes("text-lg font-semibold")
                col = ui.select([c.name for c in columns], label="Colonna").classes("w-full")

                def go() -> None:
                    if not col.value:
                        return
                    sql = compose_drop_column(dialect, table, col.value)
                    dlg.close()
                    _review_and_execute(engine, sql, destructive=True, on_done=on_done)

                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("Rivedi DDL", on_click=go).props("color=negative")
                    ui.button("Annulla", on_click=dlg.close).props("flat")
            dlg.open()

        def _drop_table(table: str, on_done) -> None:
            sql = compose_drop_table(ctx["dialect"], table)
            _review_and_execute(ctx["engine"], sql, destructive=True, on_done=on_done)

        def _export_csv(table: str) -> None:
            tbl = get_table(ctx["metadata"], table)
            csv_text = table_to_csv(ctx["engine"], tbl)
            ui.download(csv_text.encode("utf-8"), f"{table}.csv")

        def _import_csv_dialog(on_done) -> None:
            engine, dialect = ctx["engine"], ctx["dialect"]
            with ui.dialog() as dlg, ui.card().classes("w-[560px] gap-2"):
                ui.label("Importa CSV").classes("text-lg font-semibold")
                tname = ui.input("Nome nuova tabella").classes("w-full")
                holder: dict[str, str] = {}

                def _on_upload(e: Any) -> None:
                    holder["text"] = e.content.read().decode("utf-8")
                    ui.notify(f"CSV caricato: {e.name}", type="info")

                ui.upload(on_upload=_on_upload, auto_upload=True).classes("w-full")

                def go() -> None:
                    if not tname.value or "text" not in holder:
                        ui.notify("Nome tabella e CSV richiesti.", type="warning")
                        return
                    sql, header = csv_create_table_ddl(dialect, tname.value, holder["text"])
                    dlg.close()

                    def after_create() -> None:
                        _fill_csv(engine, tname.value, header, holder["text"])
                        on_done()

                    _review_and_execute(engine, sql, destructive=False, on_done=after_create)

                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("Rivedi DDL", on_click=go).props("color=primary")
                    ui.button("Annulla", on_click=dlg.close).props("flat")
            dlg.open()

        def _fill_csv(engine: Any, table: str, header: list[str], text: str) -> None:
            from sqlalchemy import text as sa_text

            _h, rows = rows_from_csv(text)
            if not rows:
                return
            cols = ", ".join(header)
            binds = ", ".join(f":{h}" for h in header)
            stmt = sa_text(f"INSERT INTO {table} ({cols}) VALUES ({binds})")
            with engine.begin() as conn:
                for r in rows:
                    conn.execute(stmt, {h: (r[i] if i < len(r) else None)
                                        for i, h in enumerate(header)})

        def _diagram_dialog() -> None:
            metadata, tables = ctx["metadata"], ctx["tables"]
            lines = ["graph LR"]
            for t in tables:
                for fk in detect_foreign_keys(metadata, t):
                    lines.append(f"  {t} --> {fk.remote_table}")
            diagram = "\n".join(lines) if len(lines) > 1 else "graph LR\n  (nessuna FK)"
            with ui.dialog() as dlg, ui.card().classes("w-[640px] gap-2"):
                ui.label("Diagramma relazioni").classes("text-lg font-semibold")
                ui.mermaid(diagram)
                ui.button("Chiudi", on_click=dlg.close).props("flat")
            dlg.open()

        conn_select.on_value_change(lambda _e: load())
