"""Shared validation and execution for user-defined reporting and lookup queries."""

from contextlib import contextmanager
from typing import Any

import sqlglot
from sqlalchemy import Engine, text
from sqlglot import exp
from sqlglot.errors import SqlglotError

_DIALECT = {"postgresql": "postgres", "mssql": "tsql", "mariadb": "mysql"}


def ensure_readonly(sql: str, dialect: str | None = None) -> None:
    """Accept one SELECT, including set operations and read-only CTEs."""
    try:
        trees = sqlglot.parse(sql, read=_DIALECT.get(dialect, dialect))
    except SqlglotError as exc:
        raise ValueError("Invalid report SQL.") from exc
    if len(trees) != 1 or not isinstance(trees[0], exp.Query):
        raise ValueError("Only a single SELECT query is allowed.")
    if trees[0].find(exp.DML, exp.DDL, exp.Into, exp.Lock, exp.Command, exp.Copy):
        raise ValueError("The query must be read-only.")


@contextmanager
def readonly_result(engine: Engine, sql: str, params: dict[str, Any] | None = None):
    """Keep the result and any database read-only settings within one checkout."""
    dialect = engine.dialect.name
    ensure_readonly(sql, dialect)
    with engine.connect() as conn:
        sqlite = dialect == "sqlite"
        if sqlite:
            prior = conn.exec_driver_sql("PRAGMA query_only").scalar_one()
            conn.exec_driver_sql("PRAGMA query_only = ON")
        elif dialect == "duckdb":
            # duckdb-engine starts an ordinary native transaction on autobegin.
            # This private checkout has no work yet. Replace its transaction mode.
            conn.begin()
            conn.exec_driver_sql("ROLLBACK")
            conn.exec_driver_sql("BEGIN TRANSACTION READ ONLY")
        elif dialect in {"postgresql", "oracle"}:
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")
        elif dialect in {"mysql", "mariadb"}:
            conn.exec_driver_sql("START TRANSACTION READ ONLY")
        try:
            with conn.execute(text(sql), params or {}) as result:
                yield result
        finally:
            if sqlite:
                try:
                    conn.exec_driver_sql(f"PRAGMA query_only = {int(prior)}")
                except Exception:
                    conn.invalidate()
                    raise
