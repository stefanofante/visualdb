"""Multi-dialect SQLAlchemy engine creation.

Abstracts away the URL differences between the supported database dialects and
provides a lightweight connection test. Credentials are expected to arrive
already resolved (encrypted-credential handling lives in ``meta/secrets`` in a
later phase).
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import URL
from sqlalchemy.pool import StaticPool

Dialect = Literal[
    "postgresql", "mysql", "mssql", "oracle", "sqlite", "duckdb", "sqlcipher"
]

# Mapping of logical dialect -> SQLAlchemy ``dialect+driver`` string.
_DRIVERS: dict[Dialect, str] = {
    "postgresql": "postgresql+psycopg",
    "mysql": "mysql+pymysql",
    "mssql": "mssql+pyodbc",
    "oracle": "oracle+oracledb",
    "sqlite": "sqlite",
    "duckdb": "duckdb",  # provided by the duckdb_engine package
    "sqlcipher": "sqlite+pysqlcipher",  # encrypted SQLite (SQLCipher)
}

# File-based / embedded dialects: ``database`` is a file path (or in-memory).
_FILE_DIALECTS = {"sqlite", "duckdb", "sqlcipher"}

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
    # Passphrase for an encrypted local file DB (SQLCipher / encrypted DuckDB).
    # Assumed already decrypted by the caller; absent = no file encryption.
    encryption_key: str | None = None
    # Extra kwargs forwarded to ``create_engine`` (pool sizing, echo, ...).
    engine_kwargs: dict[str, Any] = field(default_factory=dict)


def _build_url(config: ConnectionConfig) -> URL:
    """Translate a :class:`ConnectionConfig` into a SQLAlchemy ``URL``."""
    if config.dialect not in _DRIVERS:
        raise ValueError(f"Unsupported dialect: {config.dialect!r}")

    drivername = _DRIVERS[config.dialect]

    if config.dialect in _FILE_DIALECTS:
        # No host/user; ``database`` is the file path (empty => in-memory).
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


def encryption_supported(dialect: str) -> bool:
    """Return ``True`` if the driver needed for encrypted files is installed.

    * ``sqlcipher`` requires ``pysqlcipher3`` or ``sqlcipher3``.
    * ``duckdb`` uses native encryption (via the ``duckdb_engine`` package).
    """
    if dialect == "sqlcipher":
        return bool(
            importlib.util.find_spec("pysqlcipher3")
            or importlib.util.find_spec("sqlcipher3")
        )
    if dialect == "duckdb":
        return bool(importlib.util.find_spec("duckdb_engine"))
    return False


def build_engine(config: ConnectionConfig) -> Engine:
    """Build a SQLAlchemy :class:`Engine` from resolved connection parameters.

    Pool pre-ping is enabled by default so stale connections are detected and
    recycled transparently. Callers may override any ``create_engine`` option
    through ``config.engine_kwargs``. When ``config.session_settings`` is given,
    the corresponding ``SET`` statements run on every new connection. When
    ``config.encryption_key`` is set, the encrypted file (SQLCipher or DuckDB) is
    opened with that passphrase.
    """
    if config.dialect == "duckdb" and config.encryption_key:
        return _build_encrypted_duckdb(config)

    if config.dialect == "sqlcipher" and not encryption_supported("sqlcipher"):
        raise RuntimeError(
            "SQLite cifrato non disponibile: installa il driver SQLCipher "
            "(pysqlcipher3 o sqlcipher3)."
        )

    url = _build_url(config)
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    kwargs.update(config.engine_kwargs)
    engine = create_engine(url, **kwargs)
    _register_session_settings(engine, config)
    _register_encryption_key(engine, config)
    return engine


def _register_encryption_key(engine: Engine, config: ConnectionConfig) -> None:
    """For SQLCipher, apply ``PRAGMA key`` on every new connection."""
    if config.dialect != "sqlcipher" or not config.encryption_key:
        return
    safe = config.encryption_key.replace("'", "''")

    @event.listens_for(engine, "connect")
    def _apply_key(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"PRAGMA key = '{safe}'")
        finally:
            cursor.close()


def _build_encrypted_duckdb(config: ConnectionConfig) -> Engine:
    """Open an encrypted DuckDB file via ``ATTACH ... (ENCRYPTION_KEY ...)``.

    A single-connection ``StaticPool`` is used so the encrypted file is attached
    exactly once; the attached database is made the default catalog with ``USE``
    so table names resolve unqualified.
    """
    path = (config.database or "").replace("\\", "/").replace("'", "''")
    if not path or path == ":memory:":
        raise ValueError("Un DuckDB cifrato richiede un percorso file.")
    key = (config.encryption_key or "").replace("'", "''")
    kwargs: dict[str, Any] = {"poolclass": StaticPool}
    kwargs.update(config.engine_kwargs)
    engine = create_engine("duckdb:///:memory:", **kwargs)

    @event.listens_for(engine, "connect")
    def _attach(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"ATTACH '{path}' AS encdb (ENCRYPTION_KEY '{key}')")
            cursor.execute("USE encdb")
        finally:
            cursor.close()

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
