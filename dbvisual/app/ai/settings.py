"""AI assistant configuration (Task C).

Non-secret settings (enabled flag, provider, model) are persisted in the local
settings file; the **API key is a secret** stored via :class:`SecretStore` under
``ai:<provider>`` — reusing the Phase 7 generic secret mechanism, not a second
secrets system. The feature is **off by default**.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_dir

from dbvisual.app.ai.provider import DEFAULT_MODELS
from dbvisual.meta.secrets import SecretStore

_APP_NAME = "dbvisual"


def _settings_path(data_dir: str | Path | None = None) -> Path:
    base = Path(data_dir) if data_dir is not None else Path(
        user_data_dir(_APP_NAME, appauthor=False)
    )
    base.mkdir(parents=True, exist_ok=True)
    return base / "settings.json"


def _load(data_dir: str | Path | None = None) -> dict:
    path = _settings_path(data_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(data: dict, data_dir: str | Path | None = None) -> None:
    _settings_path(data_dir).write_text(json.dumps(data), encoding="utf-8")


@dataclass(slots=True)
class AIConfig:
    """Resolved AI settings (non-secret)."""

    enabled: bool = False
    provider: str = "anthropic"
    model: str = ""


def get_ai_config(data_dir: str | Path | None = None) -> AIConfig:
    """Return the persisted AI config (disabled by default)."""
    data = _load(data_dir)
    provider = str(data.get("ai_provider", "anthropic"))
    return AIConfig(
        enabled=bool(data.get("ai_enabled", False)),
        provider=provider,
        model=str(data.get("ai_model") or DEFAULT_MODELS.get(provider, "")),
    )


def set_ai_config(
    config: AIConfig, data_dir: str | Path | None = None
) -> None:
    """Persist the non-secret AI settings."""
    data = _load(data_dir)
    data["ai_enabled"] = config.enabled
    data["ai_provider"] = config.provider
    data["ai_model"] = config.model
    _save(data, data_dir)


def api_key_secret_key(provider: str) -> str:
    """SecretStore key holding a provider's API key."""
    return f"ai:{provider}"


def save_api_key(secrets: SecretStore, provider: str, api_key: str) -> None:
    """Store a provider API key as a secret (never in the settings/metadata)."""
    secrets.set_secret(api_key_secret_key(provider), api_key)


def get_api_key(secrets: SecretStore, provider: str) -> str | None:
    """Return the stored API key for ``provider`` (or ``None``)."""
    return secrets.get_secret(api_key_secret_key(provider))
