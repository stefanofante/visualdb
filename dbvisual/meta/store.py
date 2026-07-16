"""Local metadata store — CRUD over the SQLite metadata database.

Uses SQLAlchemy Core (no ORM). The store owns its own :class:`Engine` pointed at
a SQLite file inside the user's data directory (resolved with ``platformdirs``),
or at any path supplied by tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir
from sqlalchemy import Engine, create_engine, delete, insert, select, update

from dbvisual.meta.models import (
    applications,
    connections,
    definitions,
    metadata,
    webhooks,
)

_APP_NAME = "dbvisual"


def default_db_path() -> Path:
    """Return the default metadata DB path (``<user data dir>/metadata.db``)."""
    data_dir = Path(user_data_dir(_APP_NAME, appauthor=False))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "metadata.db"


class MetadataStore:
    """CRUD facade over the local metadata database."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        """Open (and create if needed) the metadata store at ``db_path``.

        When ``db_path`` is ``None`` the default user-data location is used.
        """
        path = Path(db_path) if db_path is not None else default_db_path()
        self.engine: Engine = create_engine(f"sqlite:///{path}")
        self.create_all()

    def create_all(self) -> None:
        """Create the metadata tables if they do not exist yet."""
        metadata.create_all(self.engine)

    # -- connections --------------------------------------------------------

    def create_connection(
        self,
        name: str,
        dialect: str,
        host: str | None = None,
        port: int | None = None,
        database: str | None = None,
        username: str | None = None,
        options: dict[str, str] | None = None,
    ) -> int:
        """Insert a connection and return its new id."""
        with self.engine.begin() as conn:
            result = conn.execute(
                insert(connections).values(
                    name=name,
                    dialect=dialect,
                    host=host,
                    port=port,
                    database=database,
                    username=username,
                    options=json.dumps(options) if options else None,
                )
            )
            return int(result.inserted_primary_key[0])

    def list_connections(self) -> list[dict[str, Any]]:
        """Return all saved connections as dicts (ordered by name)."""
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(connections).order_by(connections.c.name)
            ).mappings()
            return [self._decode_connection(r) for r in rows]

    def get_connection(self, connection_id: int) -> dict[str, Any] | None:
        """Return a single connection by id, or ``None`` if not found."""
        with self.engine.connect() as conn:
            row = (
                conn.execute(
                    select(connections).where(connections.c.id == connection_id)
                )
                .mappings()
                .first()
            )
            return self._decode_connection(row) if row else None

    def update_connection(self, connection_id: int, **values: Any) -> int:
        """Update fields of a connection; return the affected row count.

        ``options`` (if present) is JSON-encoded automatically.
        """
        if "options" in values and isinstance(values["options"], dict):
            values["options"] = json.dumps(values["options"])
        with self.engine.begin() as conn:
            result = conn.execute(
                update(connections)
                .where(connections.c.id == connection_id)
                .values(**values)
            )
            return result.rowcount

    def delete_connection(self, connection_id: int) -> int:
        """Delete a connection by id; return the affected row count."""
        with self.engine.begin() as conn:
            result = conn.execute(
                delete(connections).where(connections.c.id == connection_id)
            )
            return result.rowcount

    # -- applications -------------------------------------------------------

    def create_application(self, name: str) -> int:
        """Insert an application and return its new id."""
        with self.engine.begin() as conn:
            result = conn.execute(insert(applications).values(name=name))
            return int(result.inserted_primary_key[0])

    def list_applications(self) -> list[dict[str, Any]]:
        """Return all applications as dicts (ordered by name)."""
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(applications).order_by(applications.c.name)
            ).mappings()
            return [dict(r) for r in rows]

    def get_application(self, app_id: int) -> dict[str, Any] | None:
        """Return a single application by id, or ``None`` if not found."""
        with self.engine.connect() as conn:
            row = (
                conn.execute(select(applications).where(applications.c.id == app_id))
                .mappings()
                .first()
            )
            return dict(row) if row else None

    def update_application(self, app_id: int, **values: Any) -> int:
        """Update fields of an application; return the affected row count."""
        with self.engine.begin() as conn:
            result = conn.execute(
                update(applications).where(applications.c.id == app_id).values(**values)
            )
            return result.rowcount

    def delete_application(self, app_id: int) -> int:
        """Delete an application (and its definitions) by id."""
        with self.engine.begin() as conn:
            # Explicit cascade: SQLite does not enforce FK cascade by default.
            conn.execute(delete(definitions).where(definitions.c.app_id == app_id))
            result = conn.execute(
                delete(applications).where(applications.c.id == app_id)
            )
            return result.rowcount

    # -- definitions --------------------------------------------------------

    def create_definition(
        self, app_id: int, kind: str, name: str, queryspec_json: str
    ) -> int:
        """Insert a definition (form/sheet/report) and return its new id."""
        with self.engine.begin() as conn:
            result = conn.execute(
                insert(definitions).values(
                    app_id=app_id,
                    kind=kind,
                    name=name,
                    queryspec_json=queryspec_json,
                )
            )
            return int(result.inserted_primary_key[0])

    def list_definitions(self, app_id: int | None = None) -> list[dict[str, Any]]:
        """Return definitions, optionally filtered by ``app_id``."""
        stmt = select(definitions).order_by(definitions.c.name)
        if app_id is not None:
            stmt = stmt.where(definitions.c.app_id == app_id)
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(stmt).mappings()]

    def get_definition(self, definition_id: int) -> dict[str, Any] | None:
        """Return a single definition by id, or ``None`` if not found."""
        with self.engine.connect() as conn:
            row = (
                conn.execute(
                    select(definitions).where(definitions.c.id == definition_id)
                )
                .mappings()
                .first()
            )
            return dict(row) if row else None

    def update_definition(self, definition_id: int, **values: Any) -> int:
        """Update fields of a definition; return the affected row count."""
        with self.engine.begin() as conn:
            result = conn.execute(
                update(definitions)
                .where(definitions.c.id == definition_id)
                .values(**values)
            )
            return result.rowcount

    def delete_definition(self, definition_id: int) -> int:
        """Delete a definition by id; return the affected row count."""
        with self.engine.begin() as conn:
            conn.execute(
                delete(webhooks).where(webhooks.c.definition_id == definition_id)
            )
            result = conn.execute(
                delete(definitions).where(definitions.c.id == definition_id)
            )
            return result.rowcount

    # -- webhooks -----------------------------------------------------------

    def create_webhook(
        self,
        definition_id: int,
        table_name: str,
        name: str,
        events: list[str],
        body_mode: str = "default",
        body_template: str | None = None,
    ) -> int:
        """Insert a webhook config (URL is stored separately as a secret)."""
        with self.engine.begin() as conn:
            result = conn.execute(
                insert(webhooks).values(
                    definition_id=definition_id,
                    table_name=table_name,
                    name=name,
                    events=json.dumps(events),
                    body_mode=body_mode,
                    body_template=body_template,
                )
            )
            return int(result.inserted_primary_key[0])

    def list_webhooks(self, definition_id: int | None = None) -> list[dict[str, Any]]:
        """Return webhook configs, optionally filtered by ``definition_id``."""
        stmt = select(webhooks)
        if definition_id is not None:
            stmt = stmt.where(webhooks.c.definition_id == definition_id)
        with self.engine.connect() as conn:
            return [self._decode_webhook(r) for r in conn.execute(stmt).mappings()]

    def get_webhook(self, webhook_id: int) -> dict[str, Any] | None:
        """Return a single webhook config by id, or ``None``."""
        with self.engine.connect() as conn:
            row = (
                conn.execute(select(webhooks).where(webhooks.c.id == webhook_id))
                .mappings()
                .first()
            )
            return self._decode_webhook(row) if row else None

    def update_webhook(self, webhook_id: int, **values: Any) -> int:
        """Update webhook fields; ``events`` (list) is JSON-encoded automatically."""
        if "events" in values and isinstance(values["events"], list):
            values["events"] = json.dumps(values["events"])
        with self.engine.begin() as conn:
            result = conn.execute(
                update(webhooks).where(webhooks.c.id == webhook_id).values(**values)
            )
            return result.rowcount

    def delete_webhook(self, webhook_id: int) -> int:
        """Delete a webhook config by id; return the affected row count."""
        with self.engine.begin() as conn:
            result = conn.execute(delete(webhooks).where(webhooks.c.id == webhook_id))
            return result.rowcount

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _decode_connection(row: Any) -> dict[str, Any]:
        """Convert a connection row mapping into a dict with parsed ``options``."""
        data = dict(row)
        raw = data.get("options")
        data["options"] = json.loads(raw) if raw else {}
        return data

    @staticmethod
    def _decode_webhook(row: Any) -> dict[str, Any]:
        """Convert a webhook row mapping into a dict with parsed ``events``."""
        data = dict(row)
        raw = data.get("events")
        data["events"] = json.loads(raw) if raw else []
        return data
