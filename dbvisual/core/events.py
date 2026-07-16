"""Optional CRUD event dispatch (Phase 7).

A lightweight, decoupled registry: after a successful insert/update/delete the
core emits a :class:`CrudEvent` to every registered dispatcher. When no
dispatcher is registered nothing happens, so the core's behaviour and existing
tests are unchanged. Dispatchers are fire-and-forget: an exception in one never
propagates back into the CRUD operation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

logger = logging.getLogger("dbvisual.events")

EventKind = Literal["created", "updated", "deleted"]


@dataclass(slots=True)
class CrudEvent:
    """A successful CRUD mutation: its kind, target table and record values."""

    kind: EventKind
    table: str
    values: dict[str, Any] = field(default_factory=dict)


_dispatchers: list[Callable[[CrudEvent], None]] = []


def register_dispatcher(fn: Callable[[CrudEvent], None]) -> Callable[[CrudEvent], None]:
    """Register a dispatcher callback (idempotent)."""
    if fn not in _dispatchers:
        _dispatchers.append(fn)
    return fn


def unregister_dispatcher(fn: Callable[[CrudEvent], None]) -> None:
    """Remove a previously registered dispatcher (no-op if absent)."""
    if fn in _dispatchers:
        _dispatchers.remove(fn)


def clear_dispatchers() -> None:
    """Remove all dispatchers (used by tests)."""
    _dispatchers.clear()


def has_dispatchers() -> bool:
    """Return ``True`` if at least one dispatcher is registered."""
    return bool(_dispatchers)


def emit(event: CrudEvent) -> None:
    """Deliver ``event`` to all dispatchers, swallowing their exceptions."""
    for dispatcher in list(_dispatchers):
        try:
            dispatcher(event)
        except Exception:  # fire-and-forget: never break the caller
            logger.exception("CRUD event dispatcher failed for %s", event.kind)
