"""Task C tests: LLM providers (mocked HTTP), read-only guard, secret API keys."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dbvisual.app.ai.provider import (
    AnthropicProvider,
    DeepSeekProvider,
    GeminiProvider,
    OpenAIProvider,
    clean_sql,
    format_schema,
    get_provider,
)
from dbvisual.app.ai.settings import (
    AIConfig,
    api_key_secret_key,
    get_ai_config,
    get_api_key,
    save_api_key,
    set_ai_config,
)
from dbvisual.app.report_service import ensure_readonly
from dbvisual.meta.secrets import SecretStore

_SCHEMA = {"orders": ["id", "customer_id", "amount"], "customers": ["id", "name"]}


class _Capture:
    """A fake HTTP client that records the request and returns a canned response."""

    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.url = ""
        self.headers: dict[str, str] = {}
        self.payload: dict[str, Any] = {}

    def __call__(self, url, headers, payload):  # type: ignore[no-untyped-def]
        self.url, self.headers, self.payload = url, headers, payload
        return self.response


# --- request construction per provider -------------------------------------


def test_anthropic_request_and_extract() -> None:
    http = _Capture({"content": [{"text": "SELECT 1"}]})
    p = AnthropicProvider(api_key="KEY", model="claude-x", http=http)
    sql = p.generate_sql("count orders", _SCHEMA)
    assert http.url == "https://api.anthropic.com/v1/messages"
    assert http.headers["x-api-key"] == "KEY"
    assert http.payload["model"] == "claude-x"
    assert "orders(id, customer_id, amount)" in http.payload["messages"][0]["content"]
    assert sql == "SELECT 1"


def test_openai_request_and_extract() -> None:
    http = _Capture({"choices": [{"message": {"content": "SELECT 2"}}]})
    p = OpenAIProvider(api_key="KEY", model="gpt", http=http)
    sql = p.generate_sql("x", _SCHEMA)
    assert http.url.endswith("/v1/chat/completions")
    assert http.headers["Authorization"] == "Bearer KEY"
    assert sql == "SELECT 2"


def test_deepseek_uses_own_endpoint() -> None:
    http = _Capture({"choices": [{"message": {"content": "SELECT 3"}}]})
    p = DeepSeekProvider(api_key="KEY", model="deepseek-chat", http=http)
    p.generate_sql("x", _SCHEMA)
    assert http.url == "https://api.deepseek.com/chat/completions"
    assert http.headers["Authorization"] == "Bearer KEY"


def test_gemini_request_and_extract() -> None:
    http = _Capture({"candidates": [{"content": {"parts": [{"text": "SELECT 4"}]}}]})
    p = GeminiProvider(api_key="KEY", model="gemini-x", http=http)
    sql = p.generate_sql("x", _SCHEMA)
    assert "gemini-x:generateContent?key=KEY" in http.url
    assert sql == "SELECT 4"


def test_get_provider_factory() -> None:
    assert isinstance(get_provider("openai", "k", "m"), OpenAIProvider)
    with pytest.raises(ValueError):
        get_provider("unknown", "k", "m")


# --- output cleaning & read-only guard -------------------------------------


def test_clean_sql_strips_fences() -> None:
    assert clean_sql("```sql\nSELECT 1\n```") == "SELECT 1"
    assert clean_sql("  SELECT 2  ") == "SELECT 2"


def test_generated_sql_must_pass_readonly() -> None:
    http = _Capture({"choices": [{"message": {"content": "SELECT * FROM orders"}}]})
    sql = OpenAIProvider("k", "m", http=http).generate_sql("all orders", _SCHEMA)
    ensure_readonly(sql)  # SELECT -> ok


def test_generated_write_is_rejected() -> None:
    http = _Capture({"choices": [{"message": {"content": "DELETE FROM orders"}}]})
    sql = OpenAIProvider("k", "m", http=http).generate_sql("wipe", _SCHEMA)
    with pytest.raises(ValueError):
        ensure_readonly(sql)


def test_format_schema() -> None:
    assert "orders(id, customer_id, amount)" in format_schema(_SCHEMA)


# --- config: off by default, API key is a secret ---------------------------


def test_ai_disabled_by_default(tmp_path: Path) -> None:
    cfg = get_ai_config(tmp_path)
    assert cfg.enabled is False
    assert cfg.provider == "anthropic"


def test_ai_config_roundtrip(tmp_path: Path) -> None:
    set_ai_config(AIConfig(enabled=True, provider="openai", model="gpt"), tmp_path)
    cfg = get_ai_config(tmp_path)
    assert cfg.enabled is True and cfg.provider == "openai" and cfg.model == "gpt"


def test_api_key_is_secret_not_in_settings(tmp_path: Path) -> None:
    secrets = SecretStore(use_keyring=False, data_dir=tmp_path)
    set_ai_config(AIConfig(enabled=True, provider="openai", model="gpt"), tmp_path)
    save_api_key(secrets, "openai", "sk-SECRET-KEY")

    assert get_api_key(secrets, "openai") == "sk-SECRET-KEY"
    assert api_key_secret_key("openai") == "ai:openai"
    # The key must not appear in the plaintext settings file.
    settings_text = (tmp_path / "settings.json").read_text(encoding="utf-8")
    assert "sk-SECRET-KEY" not in settings_text
    # Nor in the encrypted secrets vault as plaintext.
    assert b"sk-SECRET-KEY" not in (tmp_path / "secrets.enc").read_bytes()
