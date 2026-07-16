"""Shared application state.

Holds the singletons the UI pages depend on: the local metadata store and the
secret store. Kept tiny and importable so pages and tests can inject their own
temporary instances.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dbvisual.meta.secrets import SecretStore
from dbvisual.meta.store import MetadataStore


@dataclass(slots=True)
class AppState:
    """Container for the app-wide service singletons."""

    store: MetadataStore
    secrets: SecretStore


_state: AppState | None = None


def init_state(
    db_path: str | Path | None = None,
    *,
    use_keyring: bool = True,
    data_dir: str | Path | None = None,
) -> AppState:
    """Create and register the global :class:`AppState`."""
    global _state
    _state = AppState(
        store=MetadataStore(db_path),
        secrets=SecretStore(use_keyring=use_keyring, data_dir=data_dir),
    )
    return _state


def get_state() -> AppState:
    """Return the initialised :class:`AppState` (initialising defaults if needed)."""
    global _state
    if _state is None:
        _state = init_state()
    return _state


def set_state(state: AppState) -> None:
    """Override the global state (used by tests)."""
    global _state
    _state = state
