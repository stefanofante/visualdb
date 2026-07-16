"""Connections page: list, create/edit, test, save, and browse schema.

Relies entirely on the Phase 1 core (``dbvisual.core``) for engine building,
connection testing and schema reflection — no DB logic is duplicated here.
"""

from __future__ import annotations

from typing import Any

from nicegui import ui

from dbvisual.app.identity import get_identity, set_identity
from dbvisual.app.shell import frame
from dbvisual.app.state import get_state
from dbvisual.core.connections import ConnectionConfig, build_engine, test_connection
from dbvisual.core.introspect import (
    detect_foreign_keys,
    get_columns,
    list_tables,
    reflect_schema,
)

# Dialects offered in the UI (label -> value expected by the core).
_DIALECTS = {
    "PostgreSQL": "postgresql",
    "MySQL / MariaDB": "mysql",
    "SQL Server": "mssql",
    "Oracle": "oracle",
    "SQLite": "sqlite",
}


def _to_config(data: dict[str, Any], password: str | None) -> ConnectionConfig:
    """Build a :class:`ConnectionConfig` from raw form ``data``."""
    port = data.get("port")
    return ConnectionConfig(
        dialect=data["dialect"],
        host=data.get("host") or None,
        port=int(port) if port else None,
        database=data.get("database") or None,
        username=data.get("username") or None,
        password=password or None,
        query=data.get("options") or {},
    )


def _connection_dialog(on_saved) -> None:
    """Open the new/edit connection dialog. ``on_saved`` refreshes the list."""
    state = get_state()
    fields: dict[str, Any] = {}

    with ui.dialog() as dialog, ui.card().classes("w-[520px] gap-3"):
        ui.label("Nuova connessione").classes("text-lg font-semibold")

        fields["name"] = ui.input("Nome").classes("w-full")
        fields["dialect"] = ui.select(
            {v: k for k, v in _DIALECTS.items()}, label="Dialetto", value="postgresql"
        ).classes("w-full")
        fields["host"] = ui.input("Host").classes("w-full")
        fields["port"] = ui.number("Port", format="%d").classes("w-full")
        fields["database"] = ui.input("Database / file path").classes("w-full")
        fields["username"] = ui.input("Username").classes("w-full")
        fields["password"] = ui.input("Password", password=True).classes("w-full")

        result = ui.label("").classes("text-sm")

        def collect() -> tuple[dict[str, Any], str]:
            data = {
                "name": fields["name"].value,
                "dialect": fields["dialect"].value,
                "host": fields["host"].value,
                "port": fields["port"].value,
                "database": fields["database"].value,
                "username": fields["username"].value,
            }
            return data, fields["password"].value or ""

        def on_test() -> None:
            data, password = collect()
            try:
                engine = build_engine(_to_config(data, password))
                ok = test_connection(engine)
            except Exception as exc:  # driver missing / bad params
                result.set_text(f"Errore: {exc}")
                result.classes(replace="text-sm text-red-600")
                return
            if ok:
                result.set_text("Connessione riuscita.")
                result.classes(replace="text-sm text-green-600")
            else:
                result.set_text("Connessione fallita.")
                result.classes(replace="text-sm text-red-600")

        def on_save() -> None:
            data, password = collect()
            if not data["name"]:
                result.set_text("Il nome è obbligatorio.")
                result.classes(replace="text-sm text-red-600")
                return
            conn_id = state.store.create_connection(
                name=data["name"],
                dialect=data["dialect"],
                host=data["host"] or None,
                port=int(data["port"]) if data["port"] else None,
                database=data["database"] or None,
                username=data["username"] or None,
            )
            if password:
                state.secrets.save_password(conn_id, password)
            dialog.close()
            on_saved()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Testa", on_click=on_test).props("outline")
            ui.button("Salva", on_click=on_save).props("color=primary")
            ui.button("Annulla", on_click=dialog.close).props("flat")

    dialog.open()


def _schema_dialog(connection: dict[str, Any]) -> None:
    """Connect using ``connection`` and show tables, columns and FKs."""
    state = get_state()
    password = state.secrets.get_password(connection["id"])
    config = ConnectionConfig(
        dialect=connection["dialect"],
        host=connection.get("host"),
        port=connection.get("port"),
        database=connection.get("database"),
        username=connection.get("username"),
        password=password,
        query=connection.get("options") or {},
    )

    with ui.dialog() as dialog, ui.card().classes("w-[720px] h-[560px] gap-3"):
        ui.label(f"Schema — {connection['name']}").classes("text-lg font-semibold")
        body = ui.column().classes("w-full grow overflow-auto")

        try:
            engine = build_engine(config)
            metadata = reflect_schema(engine)
            tables = list_tables(metadata)
        except Exception as exc:
            with body:
                ui.label(f"Impossibile leggere lo schema: {exc}").classes(
                    "text-red-600"
                )
            with ui.row().classes("w-full justify-end"):
                ui.button("Chiudi", on_click=dialog.close).props("flat")
            dialog.open()
            return

        with body:
            if not tables:
                ui.label("Nessuna tabella trovata.")
            for table in tables:
                columns = get_columns(metadata, table)
                fks = detect_foreign_keys(metadata, table)
                with ui.expansion(table, icon="table_chart").classes("w-full"):
                    ui.aggrid(
                        {
                            "columnDefs": [
                                {"headerName": "Colonna", "field": "name"},
                                {"headerName": "Tipo", "field": "type"},
                                {"headerName": "Nullable", "field": "nullable"},
                                {"headerName": "PK", "field": "pk"},
                            ],
                            "rowData": [
                                {
                                    "name": c.name,
                                    "type": c.type,
                                    "nullable": c.nullable,
                                    "pk": c.primary_key,
                                }
                                for c in columns
                            ],
                        }
                    ).classes("h-48")
                    if fks:
                        ui.label("Foreign keys").classes("text-sm font-semibold mt-2")
                        for fk in fks:
                            ui.label(
                                f"{fk.local_col} → {fk.remote_table}.{fk.remote_col}"
                            ).classes("text-sm font-mono")

        with ui.row().classes("w-full justify-end"):
            ui.button("Chiudi", on_click=dialog.close).props("flat")

    dialog.open()


@ui.page("/")
def index() -> None:
    """Redirect the root to the connections page."""
    ui.navigate.to("/connections")


@ui.page("/connections")
def connections_page() -> None:
    """Render the saved-connections list with actions."""
    state = get_state()

    with frame(active="/connections"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Connessioni").classes("text-2xl font-bold")
            ui.button(
                "Nuova connessione",
                icon="add",
                on_click=lambda: _connection_dialog(refresh),
            ).props("color=primary")

        # Local identity (Phase 8): email passed to Postgres RLS as
        # app.current_user_email. Empty = RLS inactive.
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-center gap-2"):
                ui.icon("badge")
                email = ui.input(
                    "Identità corrente (email per RLS PostgreSQL)",
                    value=get_identity(),
                ).classes("grow")

                def _save_identity() -> None:
                    set_identity(email.value or "")
                    ui.notify("Identità aggiornata.", type="positive")

                ui.button("Salva identità", on_click=_save_identity).props("outline")
            ui.label(
                "La RLS è delegata a PostgreSQL (policy SQL dell'utente). La connessione "
                "deve usare un ruolo NON superuser e NON owner della tabella, altrimenti "
                "la RLS viene bypassata."
            ).classes("text-xs text-amber-700")

        container = ui.column().classes("w-full gap-2")

        def refresh() -> None:
            container.clear()
            rows = state.store.list_connections()
            with container:
                if not rows:
                    ui.label("Nessuna connessione salvata.").classes("text-gray-500")
                    return
                for conn in rows:
                    with ui.card().classes("w-full"):
                        with ui.row().classes("w-full items-center justify-between"):
                            with ui.column().classes("gap-0"):
                                ui.label(conn["name"]).classes("font-semibold")
                                detail = f"{conn['dialect']}"
                                if conn.get("host"):
                                    detail += f" · {conn['host']}"
                                if conn.get("database"):
                                    detail += f" / {conn['database']}"
                                ui.label(detail).classes("text-sm text-gray-500")
                            with ui.row().classes("gap-1"):
                                ui.button(
                                    "Sfoglia schema",
                                    icon="account_tree",
                                    on_click=lambda c=conn: _schema_dialog(c),
                                ).props("outline size=sm")
                                ui.button(
                                    icon="delete",
                                    on_click=lambda c=conn: _delete(c),
                                ).props("flat color=negative size=sm")

        def _delete(conn: dict[str, Any]) -> None:
            state.store.delete_connection(conn["id"])
            state.secrets.delete_password(conn["id"])
            refresh()

        refresh()
