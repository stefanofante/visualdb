"""Webhook service (Phase 7): render bodies and POST on CRUD events.

Listens to core CRUD events, finds the webhooks configured for the affected
table and POSTs a JSON body to each configured URL. Sending is non-blocking and
resilient: a failing webhook never breaks the record save (the error is logged).
URLs are treated as secrets (stored in :class:`SecretStore`, never in the DB).
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.request
from typing import Any, Callable

from dbvisual.core.events import CrudEvent
from dbvisual.meta.secrets import SecretStore
from dbvisual.meta.store import MetadataStore

logger = logging.getLogger("dbvisual.webhooks")

# Poster signature: (url, json_body) -> None. Default posts over HTTP.
Poster = Callable[[str, str], None]

_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9_]+)(?::(formatted|bare))?\s*\}\}")


def webhook_secret_key(webhook_id: int) -> str:
    """Return the SecretStore key holding a webhook's URL."""
    return f"webhook:{webhook_id}"


# -- body rendering ---------------------------------------------------------


def _json_value(value: Any) -> str:
    """Render a value as a valid JSON token (quoted string, number, bool, null)."""
    return json.dumps(value, default=str)


def _bare(value: Any) -> str:
    """Render a value as raw text with JSON string-internals escaped, no quotes."""
    if value is None:
        return ""
    dumped = json.dumps(str(value))
    return dumped[1:-1]  # strip the surrounding quotes


def _formatted(value: Any) -> str:
    """Render a value as an always-quoted human-readable string."""
    return json.dumps("" if value is None else str(value))


def render_body(
    values: dict[str, Any],
    body_mode: str = "default",
    body_template: str | None = None,
) -> str:
    """Render the webhook JSON body from ``values``.

    * ``default``: a JSON object with all query fields (adapts if fields change).
    * ``custom``: ``body_template`` with ``{{field}}`` / ``{{field:formatted}}`` /
      ``{{field:bare}}`` placeholders substituted.
    """
    if body_mode == "custom" and body_template is not None:

        def _sub(match: re.Match[str]) -> str:
            field, flavor = match.group(1), match.group(2)
            value = values.get(field)
            if flavor == "bare":
                return _bare(value)
            if flavor == "formatted":
                return _formatted(value)
            return _json_value(value)

        return _PLACEHOLDER.sub(_sub, body_template)
    # Default: full record as a JSON object.
    return json.dumps(values, default=str)


# -- HTTP posting -----------------------------------------------------------


def http_post(url: str, body: str, timeout: float = 10.0) -> None:
    """POST ``body`` as JSON to ``url`` (used as the default poster)."""
    request = urllib.request.Request(
        url,
        data=body.encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout):  # noqa: S310 (local app)
        pass


# -- service ----------------------------------------------------------------


class WebhookService:
    """Dispatches CRUD events to configured webhooks (non-blocking)."""

    def __init__(
        self,
        store: MetadataStore,
        secrets: SecretStore,
        poster: Poster | None = None,
        *,
        threaded: bool = True,
        retries: int = 1,
        backoff: float = 0.5,
    ) -> None:
        self._store = store
        self._secrets = secrets
        self._poster = poster or http_post
        self._threaded = threaded
        self._retries = max(1, retries)
        self._backoff = backoff

    def handle_event(self, event: CrudEvent) -> None:
        """Find matching webhooks for ``event`` and dispatch each (never raises)."""
        try:
            hooks = [
                wh
                for wh in self._store.list_webhooks()
                if wh["table_name"] == event.table and event.kind in wh["events"]
            ]
        except Exception:  # store failure must not break the save
            logger.exception("Failed to load webhooks for %s", event.table)
            return
        for wh in hooks:
            url = self._secrets.get_secret(webhook_secret_key(wh["id"]))
            if not url:
                continue
            body = render_body(event.values, wh["body_mode"], wh.get("body_template"))
            self._send(url, body)

    def _send(self, url: str, body: str) -> None:
        if self._threaded:
            threading.Thread(
                target=self._send_now, args=(url, body), daemon=True
            ).start()
        else:
            self._send_now(url, body)

    def _send_now(self, url: str, body: str) -> None:
        for attempt in range(1, self._retries + 1):
            try:
                self._poster(url, body)
                return
            except Exception:
                # Never log the raw URL (it may contain a token).
                logger.warning("Webhook POST failed (attempt %d)", attempt)
                if attempt < self._retries:
                    time.sleep(self._backoff * attempt)
        logger.error("Webhook delivery gave up after %d attempts", self._retries)
