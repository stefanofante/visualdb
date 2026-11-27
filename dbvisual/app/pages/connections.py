"""Connections page: list, create/edit, test, save, and browse schema.

Relies entirely on the Phase 1 core (``dbvisual.core``) for engine building,
connection testing and schema reflection — no DB logic is duplicated here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nicegui import app, ui
from platformdirs import user_documents_path
from sqlalchemy.exc import SQLAlchemyError

from dbvisual.app.database_files import create_database_file
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
    "DuckDB": "duckdb",
    "SQLite encrypted (SQLCipher)": "sqlcipher",
}

# Dialects that use a file passphrase (encryption at rest).
_ENCRYPTED_DIALECTS = {"sqlcipher", "duckdb"}


def _enc_secret_key(connection_id: int) -> str:
    """SecretStore key holding a connection's file encryption passphrase."""
    return f"enckey:{connection_id}"


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
        encryption_key=data.get("passphrase") or None,
    )


def _create_database_dialog(on_saved) -> None:
    store = get_state().store
    documents = user_documents_path()
    with ui.dialog() as dialog, ui.card().classes("w-[520px] max-w-full gap-3"):
        ui.label("Create database").classes("text-lg font-semibold")
        dialect = ui.select(
            {"sqlite": "SQLite", "duckdb": "DuckDB"},
            value="sqlite",
            label="Database type",
        ).classes("w-full")
        filename = ui.input("File name", placeholder="Practice").classes("w-full")
        folder = ui.input(
            "Folder", value=str(documents if documents.is_dir() else Path.home())
        ).classes("w-full")
        window = app.native.main_window
        if window is not None:

            async def browse() -> None:
                import webview

                folder_mode = (
                    webview.FileDialog.FOLDER
                    if hasattr(webview, "FileDialog")
                    else webview.FOLDER_DIALOG
                )
                selected = await window.create_file_dialog(
                    folder_mode, directory=folder.value
                )
                if selected:
                    folder.set_value(
                        selected if isinstance(selected, str) else selected[0]
                    )

            ui.button("Choose folder", icon="folder_open", on_click=browse).props(
                "outline"
            )

        result = ui.label("").classes("text-sm text-red-700")

        def create() -> None:
            try:
                path = create_database_file(dialect.value, folder.value, filename.value)
            except (OSError, ValueError, ImportError, SQLAlchemyError) as exc:
                result.set_text(str(exc))
                return
            try:
                store.create_connection(
                    name=path.stem, dialect=dialect.value, database=str(path)
                )
            except SQLAlchemyError as exc:
                result.set_text(
                    f"Database created at {path}. The connection could not be saved: {exc}. "
                    "Use New connection to open this file."
                )
                return
            dialog.close()
            on_saved()
            ui.notify(f"Database created: {path.name}", type="positive")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button("Create", on_click=create).props("color=primary")
    dialog.open()


def _connection_dialog(on_saved) -> None:
    """Open the new/edit connection dialog. ``on_saved`` refreshes the list."""
    state = get_state()
    fields: dict[str, Any] = {}

    with ui.dialog() as dialog, ui.card().classes("w-[520px] gap-3"):
        ui.label("New connection").classes("text-lg font-semibold")

        fields["name"] = ui.input("Name").classes("w-full")
        fields["dialect"] = ui.select(
            {v: k for k, v in _DIALECTS.items()}, label="Dialect", value="postgresql"
        ).classes("w-full")
        fields["host"] = ui.input("Host").classes("w-full")
        fields["port"] = ui.number("Port", format="%d").classes("w-full")
        fields["database"] = ui.input("Database / file path").classes("w-full")
        fields["username"] = ui.input("Username").classes("w-full")
        fields["password"] = ui.input("Password", password=True).classes("w-full")
        fields["passphrase"] = ui.input(
            "Encrypted file passphrase (SQLCipher / DuckDB)", password=True
        ).classes("w-full")
        enc_note = ui.label(
            "Passphrase used only for encrypted DB files at rest; stored as a secret."
        ).classes("text-xs text-gray-500")

        def _toggle_enc() -> None:
            show = fields["dialect"].value in _ENCRYPTED_DIALECTS
            fields["passphrase"].set_visibility(show)
            enc_note.set_visibility(show)

        fields["dialect"].on_value_change(lambda _e: _toggle_enc())
        _toggle_enc()

        result = ui.label("").classes("text-sm")

        def collect() -> tuple[dict[str, Any], str]:
            data = {
                "name": fields["name"].value,
                "dialect": fields["dialect"].value,
                "host": fields["host"].value,
                "port": fields["port"].value,
                "database": fields["database"].value,
                "username": fields["username"].value,
                "passphrase": fields["passphrase"].value,
            }
            return data, fields["password"].value or ""

        def on_test() -> None:
            data, password = collect()
            try:
                engine = build_engine(_to_config(data, password))
                try:
                    ok = test_connection(engine)
                finally:
                    engine.dispose()
            except Exception as exc:  # driver missing / bad params
                result.set_text(f"Error: {exc}")
                result.classes(replace="text-sm text-red-600")
                return
            if ok:
                result.set_text("Connection succeeded.")
                result.classes(replace="text-sm text-green-600")
            else:
                result.set_text("Connection failed.")
                result.classes(replace="text-sm text-red-600")

        def on_save() -> None:
            data, password = collect()
            if not data["name"]:
                result.set_text("Name is required.")
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
            if data.get("passphrase") and data["dialect"] in _ENCRYPTED_DIALECTS:
                state.secrets.set_secret(_enc_secret_key(conn_id), data["passphrase"])
            dialog.close()
            on_saved()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Test", on_click=on_test).props("outline")
            ui.button("Save", on_click=on_save).props("color=primary")
            ui.button("Cancel", on_click=dialog.close).props("flat")

    dialog.open()


def _schema_dialog(connection: dict[str, Any]) -> None:
    """Connect using ``connection`` and show tables, columns and FKs."""
    state = get_state()
    password = state.secrets.get_password(connection["id"])
    encryption_key = state.secrets.get_secret(_enc_secret_key(connection["id"]))
    config = ConnectionConfig(
        dialect=connection["dialect"],
        host=connection.get("host"),
        port=connection.get("port"),
        database=connection.get("database"),
        username=connection.get("username"),
        password=password,
        query=connection.get("options") or {},
        encryption_key=encryption_key,
    )

    with ui.dialog() as dialog, ui.card().classes("w-[720px] h-[560px] gap-3"):
        ui.label(f"Schema — {connection['name']}").classes("text-lg font-semibold")
        body = ui.column().classes("w-full grow overflow-auto")

        try:
            engine = build_engine(config)
            try:
                metadata = reflect_schema(engine)
                tables = list_tables(metadata)
            finally:
                engine.dispose()
        except Exception as exc:
            with body:
                ui.label(f"Unable to read the schema: {exc}").classes("text-red-600")
            with ui.row().classes("w-full justify-end"):
                ui.button("Close", on_click=dialog.close).props("flat")
            dialog.open()
            return

        with body:
            if not tables:
                ui.label("No tables found.")
            for table in tables:
                columns = get_columns(metadata, table)
                fks = detect_foreign_keys(metadata, table)
                with ui.expansion(table, icon="table_chart").classes("w-full"):
                    ui.aggrid(
                        {
                            "columnDefs": [
                                {"headerName": "Column", "field": "name"},
                                {"headerName": "Type", "field": "type"},
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
            ui.button("Close", on_click=dialog.close).props("flat")

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
            ui.label("Connections").classes("text-2xl font-bold")
            with ui.row().classes("items-center gap-2"):
                ui.button(
                    "Create database",
                    icon="create_new_folder",
                    on_click=lambda: _create_database_dialog(refresh),
                ).props("outline")
                ui.button(
                    "New connection",
                    icon="add",
                    on_click=lambda: _connection_dialog(refresh),
                ).props("color=primary")

        # Local identity (Phase 8): email passed to Postgres RLS as
        # app.current_user_email. Empty = RLS inactive.
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-center gap-2"):
                ui.icon("badge")
                email = ui.input(
                    "Current identity (email for PostgreSQL RLS)",
                    value=get_identity(),
                ).classes("grow")

                def _save_identity() -> None:
                    set_identity(email.value or "")
                    ui.notify("Identity updated.", type="positive")

                ui.button("Save identity", on_click=_save_identity).props("outline")
            ui.label(
                "RLS is delegated to PostgreSQL (the user's SQL policies). The connection "
                "must use a role that is NOT superuser and NOT the table owner, otherwise "
                "RLS is bypassed."
            ).classes("text-xs text-amber-700")

        container = ui.column().classes("w-full gap-2")

        def refresh() -> None:
            container.clear()
            rows = state.store.list_connections()
            with container:
                if not rows:
                    ui.label("No saved connections.").classes("text-gray-500")
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
                                ui.label(detail).classes(
                                    "text-sm text-gray-500 break-all"
                                )
                            with ui.row().classes("gap-1"):
                                ui.button(
                                    "Browse schema",
                                    icon="account_tree",
                                    on_click=lambda c=conn: _schema_dialog(c),
                                ).props("outline size=sm")
                                ui.button(
                                    icon="delete",
                                    on_click=lambda c=conn: _delete(c),
                                ).props("flat color=negative size=sm")

        def _delete(conn: dict[str, Any]) -> None:
            state.secrets.delete_password(conn["id"])
            state.secrets.delete_secret(_enc_secret_key(conn["id"]))
            state.store.delete_connection(conn["id"])
            from dbvisual.app.sheet_service import clear_engine_cache

            clear_engine_cache()
            refresh()

        refresh()
