"""Tests for Phase 7: CRUD event dispatch, webhook config, body rendering, sending."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import Engine, MetaData

from dbvisual.app.webhooks import (
    WebhookService,
    render_body,
    webhook_secret_key,
)
from dbvisual.core import events
from dbvisual.core.crud import delete_record, insert_record, update_record
from dbvisual.core.events import CrudEvent
from dbvisual.meta.secrets import SecretStore
from dbvisual.meta.store import MetadataStore

# --- core event dispatch ---------------------------------------------------


def test_no_dispatcher_is_noop(engine: Engine, metadata: MetaData) -> None:
    events.clear_dispatchers()
    assert events.has_dispatchers() is False
    # CRUD works exactly as before with no dispatcher registered.
    customers = metadata.tables["customers"]
    insert_record(engine, customers, {"id": 9, "name": "Zoe", "city": "Pisa"})


def test_dispatcher_receives_crud_events(engine: Engine, metadata: MetaData) -> None:
    events.clear_dispatchers()
    received: list[CrudEvent] = []
    events.register_dispatcher(received.append)
    try:
        customers = metadata.tables["customers"]
        insert_record(engine, customers, {"id": 7, "name": "Ivo", "city": "Lecce"})
        update_record(engine, customers, {"id": 7}, {"city": "Como"})
        delete_record(engine, customers, {"id": 7})
    finally:
        events.clear_dispatchers()
    kinds = [(e.kind, e.table) for e in received]
    assert kinds == [
        ("created", "customers"),
        ("updated", "customers"),
        ("deleted", "customers"),
    ]


# --- webhook config CRUD + URL as secret -----------------------------------


def test_webhook_crud_url_is_secret(tmp_path: Path) -> None:
    store = MetadataStore(tmp_path / "m.db")
    secrets = SecretStore(use_keyring=False, data_dir=tmp_path)
    app_id = store.create_application("A")
    def_id = store.create_definition(app_id, "sheet", "S", "{}")

    wid = store.create_webhook(
        def_id, "orders", "notify", ["created", "updated"], "default", None
    )
    secrets.set_secret(webhook_secret_key(wid), "https://hooks.example/T0KEN")

    got = store.get_webhook(wid)
    assert got is not None and got["events"] == ["created", "updated"]
    # The URL/token must not be stored in the metadata DB.
    dump = (tmp_path / "m.db").read_bytes()
    assert b"T0KEN" not in dump
    assert secrets.get_secret(webhook_secret_key(wid)) == "https://hooks.example/T0KEN"

    store.delete_webhook(wid)
    assert store.get_webhook(wid) is None


# --- body rendering (three flavors) ----------------------------------------


def test_default_body_includes_all_fields() -> None:
    body = render_body({"a": 1, "b": "x", "c": None}, "default")
    assert json.loads(body) == {"a": 1, "b": "x", "c": None}


def test_flavors() -> None:
    values = {"n": 5, "s": "hi", "d": None}
    # {{field}} -> valid JSON token
    assert render_body({"n": 5}, "custom", "{{n}}") == "5"
    assert render_body({"s": "hi"}, "custom", "{{s}}") == '"hi"'
    # {{field:bare}} -> raw text, no quotes
    assert render_body(values, "custom", "X {{s:bare}} Y") == "X hi Y"
    # {{field:formatted}} -> always quoted string
    assert render_body(values, "custom", "{{n:formatted}}") == '"5"'
    assert render_body(values, "custom", "{{d:formatted}}") == '""'


def test_slack_and_discord_templates_are_valid_json() -> None:
    values = {"customer_name": "Alice", "product": "Book"}
    discord = render_body(
        values,
        "custom",
        '{"content": "Customer {{customer_name:bare}} ordered {{product:bare}}."}',
    )
    slack = render_body(
        values,
        "custom",
        '{"text": "Customer {{customer_name:bare}} ordered {{product:bare}}."}',
    )
    assert json.loads(discord)["content"] == "Customer Alice ordered Book."
    assert json.loads(slack)["text"] == "Customer Alice ordered Book."


# --- sending (mock poster, no real network) --------------------------------


def _service(
    tmp_path: Path, poster
) -> tuple[WebhookService, MetadataStore, SecretStore]:
    store = MetadataStore(tmp_path / "m.db")
    secrets = SecretStore(use_keyring=False, data_dir=tmp_path)
    svc = WebhookService(store, secrets, poster=poster, threaded=False)
    return svc, store, secrets


def test_send_posts_body_and_filters_events(tmp_path: Path) -> None:
    calls: list[tuple[str, str]] = []
    svc, store, secrets = _service(
        tmp_path, lambda url, body: calls.append((url, body))
    )
    app_id = store.create_application("A")
    def_id = store.create_definition(app_id, "sheet", "S", "{}")
    wid = store.create_webhook(def_id, "orders", "hook", ["created"], "default", None)
    secrets.set_secret(webhook_secret_key(wid), "https://hook.example/x")

    # A 'created' event fires; an 'updated' event does not (filtered out).
    svc.handle_event(CrudEvent("created", "orders", {"id": 1, "amount": 9}))
    svc.handle_event(CrudEvent("updated", "orders", {"id": 1, "amount": 9}))

    assert len(calls) == 1
    url, body = calls[0]
    assert url == "https://hook.example/x"
    assert json.loads(body) == {"id": 1, "amount": 9}


def test_failing_webhook_does_not_raise(tmp_path: Path) -> None:
    def boom(url: str, body: str) -> None:
        raise RuntimeError("network down")

    svc, store, secrets = _service(tmp_path, boom)
    app_id = store.create_application("A")
    def_id = store.create_definition(app_id, "sheet", "S", "{}")
    wid = store.create_webhook(def_id, "orders", "hook", ["created"], "default", None)
    secrets.set_secret(webhook_secret_key(wid), "https://hook.example/x")

    # Must not raise even though the poster fails -> the save is never broken.
    svc.handle_event(CrudEvent("created", "orders", {"id": 1}))
