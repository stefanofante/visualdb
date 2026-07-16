"""Tests for the centralized Settings page modules (single source of truth)."""

from __future__ import annotations

from pathlib import Path

from dbvisual.app.ai.settings import (
    AIConfig,
    get_ai_config,
    get_api_key,
    has_api_key,
    delete_api_key,
    save_api_key,
    set_ai_config,
    test_provider as run_provider_test,
)
from dbvisual.app.app_settings import get_startup_mode, set_startup_mode
from dbvisual.app.identity import get_identity, set_identity
from dbvisual.meta.secrets import SecretStore


# --- one source of truth: settings + secrets shared ------------------------


def test_ai_config_shared_source(tmp_path: Path) -> None:
    set_ai_config(AIConfig(enabled=True, provider="openai", model="gpt"), tmp_path)
    # Whatever reads ai.settings (page or contextual dialog) sees the same values.
    cfg = get_ai_config(tmp_path)
    assert cfg.enabled and cfg.provider == "openai" and cfg.model == "gpt"


def test_api_key_saved_via_settings_available_to_provider(tmp_path: Path) -> None:
    secrets = SecretStore(use_keyring=False, data_dir=tmp_path)
    save_api_key(secrets, "openai", "sk-XYZ")
    # The provider reads the same secret store.
    assert get_api_key(secrets, "openai") == "sk-XYZ"
    assert has_api_key(secrets, "openai") is True
    delete_api_key(secrets, "openai")
    assert has_api_key(secrets, "openai") is False


def test_api_key_never_exposed_as_status() -> None:
    # has_api_key only reveals presence, never the value.
    secrets = SecretStore(use_keyring=False)
    assert has_api_key(secrets, "nonexistent-xyz") is False


def test_test_provider_uses_mock_http() -> None:
    def fake_http(url, headers, payload):  # type: ignore[no-untyped-def]
        return {"choices": [{"message": {"content": "SELECT 1"}}]}

    assert run_provider_test("openai", "k", "m", http=fake_http) is True

    def boom(url, headers, payload):  # type: ignore[no-untyped-def]
        raise RuntimeError("bad key")

    assert run_provider_test("openai", "k", "m", http=boom) is False


# --- identity round-trip ---------------------------------------------------


def test_identity_roundtrip(tmp_path: Path) -> None:
    assert get_identity(tmp_path) == ""
    set_identity("me@example.com", tmp_path)
    assert get_identity(tmp_path) == "me@example.com"
    set_identity("", tmp_path)
    assert get_identity(tmp_path) == ""


# --- general settings ------------------------------------------------------


def test_startup_mode_roundtrip(tmp_path: Path) -> None:
    assert get_startup_mode(tmp_path) == "desktop"  # default
    set_startup_mode("web", tmp_path)
    assert get_startup_mode(tmp_path) == "web"
    set_startup_mode("bogus", tmp_path)  # invalid -> falls back to desktop
    assert get_startup_mode(tmp_path) == "desktop"


# --- smoke -----------------------------------------------------------------


def test_settings_route_registered() -> None:
    from nicegui import Client

    import dbvisual.app.main  # noqa: F401

    assert "/settings" in set(Client.page_routes.values())
