"""Multi-dialect SQLAlchemy engine creation.

Abstracts away the URL differences between the supported database dialects and
provides a lightweight connection test. Credentials are expected to arrive
already resolved (encrypted-credential handling lives in ``meta/secrets`` in a
later phase).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL

Dialect = Literal["postgresql", "mysql", "mssql", "oracle", "sqlite"]

# Mapping of logical dialect -> SQLAlchemy ``dialect+driver`` string.
_DRIVERS: dict[Dialect, str] = {
    "postgresql": "postgresql+psycopg",
    "mysql": "mysql+pymysql",
    "mssql": "mssql+pyodbc",
    "oracle": "oracle+oracledb",
    "sqlite": "sqlite",
}


@dataclass(slots=True)
class ConnectionConfig:
    """Resolved connection parameters for a single database.

    ``credentials`` are assumed to be already decrypted by the caller.
    For SQLite use ``database`` as the file path (or ``":memory:"``).
    """

    dialect: Dialect
    host: str | None = None
    port: int | None = None
    database: str | None = None
    username: str | None = None
    password: str | None = None
    # Extra dialect-specific URL query args, e.g. {"driver": "ODBC Driver 18 for SQL Server"}.
    query: dict[str, str] = field(default_factory=dict)
    # Extra kwargs forwarded to ``create_engine`` (pool sizing, echo, ...).
    engine_kwargs: dict[str, Any] = field(default_factory=dict)


def _build_url(config: ConnectionConfig) -> URL:
    """Translate a :class:`ConnectionConfig` into a SQLAlchemy ``URL``."""
    if config.dialect not in _DRIVERS:
        raise ValueError(f"Unsupported dialect: {config.dialect!r}")

    drivername = _DRIVERS[config.dialect]

    if config.dialect == "sqlite":
        # SQLite has no host/user; ``database`` is the file path (empty => in-memory).
        database = config.database or ":memory:"
        return URL.create(drivername=drivername, database=database)

    return URL.create(
        drivername=drivername,
        username=config.username,
        password=config.password,
        host=config.host,
        port=config.port,
        database=config.database,
        query=config.query,
    )


def build_engine(config: ConnectionConfig) -> Engine:
    """Build a SQLAlchemy :class:`Engine` from resolved connection parameters.

    Pool pre-ping is enabled by default so stale connections are detected and
    recycled transparently. Callers may override any ``create_engine`` option
    through ``config.engine_kwargs``.
    """
    url = _build_url(config)
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    kwargs.update(config.engine_kwargs)
    return create_engine(url, **kwargs)


def test_connection(engine: Engine) -> bool:
    """Return ``True`` if a trivial ``SELECT 1`` succeeds against ``engine``."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
