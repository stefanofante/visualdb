"""Row-Level Security wiring (Phase 8) — PostgreSQL only.

dbvisual does not implement RLS itself: policies live in PostgreSQL. Here we only
decide the session settings to pass on each connection. When a definition has RLS
enabled, the connection is Postgres and a current identity is set, we schedule
``SET app.current_user_email = <email>`` via ``ConnectionConfig.session_settings``.
For non-Postgres dialects the flag is ignored.
"""

from __future__ import annotations

from typing import Any

RLS_SETTING = "app.current_user_email"


def is_postgres(connection: dict[str, Any]) -> bool:
    """Return ``True`` if the connection targets PostgreSQL."""
    return connection.get("dialect") == "postgresql"


def rls_available(connection: dict[str, Any]) -> bool:
    """RLS may only be enabled on PostgreSQL connections."""
    return is_postgres(connection)


def rls_session_settings(
    connection: dict[str, Any], rls_enabled: bool, identity: str
) -> dict[str, str]:
    """Return the session settings for RLS, or ``{}`` when not applicable.

    RLS applies only when enabled, on a Postgres connection, with a non-empty
    identity. Otherwise nothing is scheduled (RLS stays inactive / ignored).
    """
    if rls_enabled and is_postgres(connection) and identity:
        return {RLS_SETTING: identity}
    return {}
