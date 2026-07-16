"""Local metadata store — SQLAlchemy Core schema definitions.

Three tables persist the user's local configuration:

* ``connections``  — saved database connections (credentials live in ``secrets``).
* ``applications`` — logical groupings of definitions.
* ``definitions``  — form/sheet/report query-specs (JSON) bound to an application.

No ORM is used: everything is declared with :class:`sqlalchemy.Table`.
"""

from __future__ import annotations

from sqlalchemy import (
    Column as SAColumn,
)
from sqlalchemy import (
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

# Dedicated MetaData for the local store (kept separate from reflected target DBs).
metadata = MetaData()

connections = Table(
    "connections",
    metadata,
    SAColumn("id", Integer, primary_key=True, autoincrement=True),
    SAColumn("name", String(200), nullable=False, unique=True),
    SAColumn("dialect", String(50), nullable=False),
    SAColumn("host", String(255), nullable=True),
    SAColumn("port", Integer, nullable=True),
    SAColumn("database", String(500), nullable=True),
    SAColumn("username", String(255), nullable=True),
    # JSON-encoded dict of extra dialect-specific URL options.
    SAColumn("options", Text, nullable=True),
)

applications = Table(
    "applications",
    metadata,
    SAColumn("id", Integer, primary_key=True, autoincrement=True),
    SAColumn("name", String(200), nullable=False, unique=True),
)

definitions = Table(
    "definitions",
    metadata,
    SAColumn("id", Integer, primary_key=True, autoincrement=True),
    SAColumn(
        "app_id",
        Integer,
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    ),
    # One of: "form", "sheet", "report".
    SAColumn("kind", String(20), nullable=False),
    SAColumn("name", String(200), nullable=False),
    # Serialized dbvisual.core.queryspec.QuerySpec.
    SAColumn("queryspec_json", Text, nullable=False),
    UniqueConstraint("app_id", "name", name="uq_definition_app_name"),
)

webhooks = Table(
    "webhooks",
    metadata,
    SAColumn("id", Integer, primary_key=True, autoincrement=True),
    SAColumn(
        "definition_id",
        Integer,
        ForeignKey("definitions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    # Denormalized target table (matched against emitted CRUD events).
    SAColumn("table_name", String(200), nullable=False),
    SAColumn("name", String(200), nullable=False),
    # JSON list among "created" / "updated" / "deleted".
    SAColumn("events", Text, nullable=False),
    # "default" (auto body with all fields) or "custom" (body_template).
    SAColumn("body_mode", String(20), nullable=False, default="default"),
    SAColumn("body_template", Text, nullable=True),
    # NOTE: the URL is a secret and is NOT stored here; it lives in SecretStore
    # under the key ``webhook:<id>`` (may contain tokens).
)
