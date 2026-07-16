"""Multi-dialect SQLAlchemy engine creation.

Abstracts away the URL differences between the supported database dialects and
provides a lightweight connection test. Credentials are expected to arrive
already resolved (encrypted-credential handling lives in ``meta/secrets`` in a
later phase).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import Engine, create_engine, event, text
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

# Dialects that understand ``SET <name> = <value>`` for session settings.
_SET_DIALECTS = {"postgresql", "mysql", "mssql", "oracle"}


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
    # Session settings applied via ``SET`` on every new connection (e.g. timezone,
    # search_path, statement_timeout, app.current_user_email for Postgres RLS).
    session_settings: dict[str, str] = field(default_factory=dict)
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


def _session_statement(dialect: str, key: str, value: str) -> str | None:
    """Build a ``SET`` statement for ``key``/``value`` on ``dialect`` (or ``None``).

    Only dialects in :data:`_SET_DIALECTS` support session ``SET``; others (e.g.
    SQLite) return ``None`` so the setting is silently skipped. ``key`` must be a
    trusted setting name; ``value`` is single-quote escaped.
    """
    if dialect not in _SET_DIALECTS:
        return None
    safe = str(value).replace("'", "''")
    return f"SET {key} = '{safe}'"


def build_engine(config: ConnectionConfig) -> Engine:
    """Build a SQLAlchemy :class:`Engine` from resolved connection parameters.

    Pool pre-ping is enabled by default so stale connections are detected and
    recycled transparently. Callers may override any ``create_engine`` option
    through ``config.engine_kwargs``. When ``config.session_settings`` is given,
    the corresponding ``SET`` statements run on every new connection.
    """
    url = _build_url(config)
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    kwargs.update(config.engine_kwargs)
    engine = create_engine(url, **kwargs)
    _register_session_settings(engine, config)
    return engine


def _register_session_settings(engine: Engine, config: ConnectionConfig) -> None:
    """Attach a connect listener that applies ``config.session_settings``."""
    if not config.session_settings:
        return
    settings = dict(config.session_settings)
    dialect = config.dialect

    @event.listens_for(engine, "connect")
    def _apply_session_settings(dbapi_connection: Any, _record: Any) -> None:
        statements = [
            stmt
            for stmt in (_session_statement(dialect, k, v) for k, v in settings.items())
            if stmt
        ]
        if not statements:
            return
        cursor = dbapi_connection.cursor()
        try:
            for stmt in statements:
                cursor.execute(stmt)
        finally:
            cursor.close()


def test_connection(engine: Engine) -> bool:
    """Return ``True`` if a trivial ``SELECT 1`` succeeds against ``engine``."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
