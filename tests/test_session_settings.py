"""Tests for the core session_settings hook (RLS predisposition)."""

from __future__ import annotations

from dbvisual.core import connections
from dbvisual.core.connections import ConnectionConfig, build_engine


def test_session_settings_empty_is_noop() -> None:
    engine = build_engine(
        ConnectionConfig(dialect="sqlite", database=":memory:", session_settings={})
    )
    assert connections.test_connection(engine) is True


def test_session_settings_populated_does_not_break_connection() -> None:
    # On SQLite the SET statements are skipped; the connect hook must still run
    # without raising when a settings map is provided.
    engine = build_engine(
        ConnectionConfig(
            dialect="sqlite",
            database=":memory:",
            session_settings={
                "app.current_user_email": "user@example.com",
                "timezone": "UTC",
            },
        )
    )
    assert connections.test_connection(engine) is True


def test_session_statement_builder() -> None:
    from dbvisual.core.connections import _session_statement

    assert _session_statement("sqlite", "timezone", "UTC") is None
    stmt = _session_statement("postgresql", "app.current_user_email", "a@b.co")
    assert stmt == "SET app.current_user_email = 'a@b.co'"
    # Values are single-quote escaped to avoid breaking the statement.
    assert _session_statement("postgresql", "k", "O'Brien") == "SET k = 'O''Brien'"
