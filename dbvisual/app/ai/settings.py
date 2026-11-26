"""AI assistant configuration (Task C).

Non-secret settings (enabled flag, provider, model) are persisted in the local
settings file; the **API key is a secret** stored via :class:`SecretStore` under
``ai:<provider>`` — reusing the Phase 7 generic secret mechanism, not a second
secrets system. The feature is **off by default**.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dbvisual.app.ai.provider import DEFAULT_MODELS
from dbvisual.app.app_settings import load_settings, update_settings
from dbvisual.meta.secrets import SecretStore


@dataclass(slots=True)
class AIConfig:
    """Resolved AI settings (non-secret)."""

    enabled: bool = False
    provider: str = "anthropic"
    model: str = ""


def get_ai_config(data_dir: str | Path | None = None) -> AIConfig:
    """Return the persisted AI config (disabled by default)."""
    data = load_settings(data_dir)
    provider = str(data.get("ai_provider", "anthropic"))
    return AIConfig(
        enabled=bool(data.get("ai_enabled", False)),
        provider=provider,
        model=str(data.get("ai_model") or DEFAULT_MODELS.get(provider, "")),
    )


def set_ai_config(config: AIConfig, data_dir: str | Path | None = None) -> None:
    """Persist the non-secret AI settings."""
    update_settings(
        {
            "ai_enabled": config.enabled,
            "ai_provider": config.provider,
            "ai_model": config.model,
        },
        data_dir,
    )


def api_key_secret_key(provider: str) -> str:
    """SecretStore key holding a provider's API key."""
    return f"ai:{provider}"


def save_api_key(secrets: SecretStore, provider: str, api_key: str) -> None:
    """Store a provider API key as a secret (never in the settings/metadata)."""
    secrets.set_secret(api_key_secret_key(provider), api_key)


def get_api_key(secrets: SecretStore, provider: str) -> str | None:
    """Return the stored API key for ``provider`` (or ``None``)."""
    return secrets.get_secret(api_key_secret_key(provider))


def has_api_key(secrets: SecretStore, provider: str) -> bool:
    """Return ``True`` if an API key is stored for ``provider`` (never the value)."""
    return bool(get_api_key(secrets, provider))


def delete_api_key(secrets: SecretStore, provider: str) -> None:
    """Remove the stored API key for ``provider`` (no-op if absent)."""
    secrets.delete_secret(api_key_secret_key(provider))


def test_provider(provider: str, api_key: str, model: str, http: Any = None) -> bool:
    """Make a minimal provider call; return ``True`` on success (never logs the key)."""
    from dbvisual.app.ai.provider import get_provider

    try:
        get_provider(provider, api_key, model, http=http).generate_sql(
            "SELECT 1", {"t": ["a"]}
        )
        return True
    except Exception:
        return False
