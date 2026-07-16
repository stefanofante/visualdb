"""Tests for Phase 8: local identity, RLS session settings and spec flags."""

from __future__ import annotations

from pathlib import Path

from dbvisual.app.form_service import FormSpec
from dbvisual.app.identity import get_identity, set_identity
from dbvisual.app.rls import RLS_SETTING, rls_available, rls_session_settings
from dbvisual.app.sheet_service import SheetSpec
from dbvisual.core.queryspec import QuerySpec


def _spec() -> QuerySpec:
    return QuerySpec(main_table="orders")


# --- local identity persistence --------------------------------------------


def test_identity_roundtrip(tmp_path: Path) -> None:
    assert get_identity(tmp_path) == ""  # empty by default
    set_identity("user@example.com", tmp_path)
    assert get_identity(tmp_path) == "user@example.com"
    set_identity("", tmp_path)  # clearing
    assert get_identity(tmp_path) == ""


# --- RLS session settings gating -------------------------------------------


def test_rls_only_on_postgres() -> None:
    pg = {"dialect": "postgresql"}
    sqlite = {"dialect": "sqlite"}
    assert rls_available(pg) is True
    assert rls_available(sqlite) is False


def test_rls_session_settings_scheduled_when_enabled() -> None:
    pg = {"dialect": "postgresql"}
    settings = rls_session_settings(pg, rls_enabled=True, identity="a@b.co")
    assert settings == {RLS_SETTING: "a@b.co"}


def test_rls_ignored_without_identity_or_flag() -> None:
    pg = {"dialect": "postgresql"}
    assert rls_session_settings(pg, rls_enabled=True, identity="") == {}
    assert rls_session_settings(pg, rls_enabled=False, identity="a@b.co") == {}


def test_rls_ignored_on_non_postgres() -> None:
    sqlite = {"dialect": "sqlite"}
    assert rls_session_settings(sqlite, rls_enabled=True, identity="a@b.co") == {}


# --- spec flag round-trip --------------------------------------------------


def test_sheet_and_form_rls_flag_roundtrip() -> None:
    s = SheetSpec(connection_id=1, spec=_spec(), rls=True)
    assert SheetSpec.from_json(s.to_json()).rls is True
    # Default stays False and old JSON (without the field) still loads.
    assert (
        SheetSpec.from_json('{"connection_id":1,"spec":{"main_table":"orders"}}').rls
        is False
    )

    f = FormSpec(connection_id=1, spec=_spec(), rls=True)
    assert FormSpec.from_json(f.to_json()).rls is True


def test_session_settings_reach_connection_config() -> None:
    from dbvisual.app.sheet_service import config_from_connection

    cfg = config_from_connection(
        {"dialect": "postgresql", "id": 1}, "pw", {RLS_SETTING: "a@b.co"}
    )
    assert cfg.session_settings == {RLS_SETTING: "a@b.co"}
