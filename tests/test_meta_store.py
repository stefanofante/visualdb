"""Tests for the local metadata store (SQLite Core CRUD)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dbvisual.meta.store import MetadataStore


@pytest.fixture()
def store(tmp_path: Path) -> MetadataStore:
    return MetadataStore(tmp_path / "metadata.db")


def test_connection_crud(store: MetadataStore) -> None:
    cid = store.create_connection(
        name="local-pg",
        dialect="postgresql",
        host="localhost",
        port=5432,
        database="app",
        username="admin",
        options={"sslmode": "require"},
    )
    assert isinstance(cid, int)

    got = store.get_connection(cid)
    assert got is not None
    assert got["name"] == "local-pg"
    assert got["port"] == 5432
    assert got["options"] == {"sslmode": "require"}

    assert len(store.list_connections()) == 1

    affected = store.update_connection(cid, host="db.internal", port=6543)
    assert affected == 1
    assert store.get_connection(cid)["host"] == "db.internal"

    assert store.delete_connection(cid) == 1
    assert store.get_connection(cid) is None
    assert store.list_connections() == []


def test_application_and_definition_crud(store: MetadataStore) -> None:
    app_id = store.create_application("Sales")
    assert store.get_application(app_id)["name"] == "Sales"

    spec = json.dumps({"main_table": "orders", "columns": []})
    def_id = store.create_definition(app_id, "sheet", "Orders grid", spec)

    defs = store.list_definitions(app_id)
    assert len(defs) == 1
    assert defs[0]["kind"] == "sheet"
    assert defs[0]["queryspec_json"] == spec

    store.update_definition(def_id, name="All orders")
    assert store.get_definition(def_id)["name"] == "All orders"

    assert store.delete_definition(def_id) == 1
    assert store.list_definitions(app_id) == []


def test_delete_application_cascades_definitions(store: MetadataStore) -> None:
    app_id = store.create_application("Temp")
    store.create_definition(app_id, "form", "f1", "{}")
    store.create_definition(app_id, "report", "r1", "{}")
    assert len(store.list_definitions(app_id)) == 2

    store.delete_application(app_id)
    assert store.get_application(app_id) is None
    assert store.list_definitions(app_id) == []


def test_persistence_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "metadata.db"
    store_a = MetadataStore(path)
    store_a.create_connection(name="c1", dialect="sqlite", database="/tmp/x.db")

    store_b = MetadataStore(path)
    names = [c["name"] for c in store_b.list_connections()]
    assert names == ["c1"]


# --- saved views -----------------------------------------------------------


def _view_def(store: MetadataStore) -> int:
    app_id = store.create_application("ViewsApp")
    return store.create_definition(app_id, "report", "R", "{}")


def test_view_crud_and_config_roundtrip(store: MetadataStore) -> None:
    def_id = _view_def(store)
    config = {"group_by": ["region"], "value": "amount", "agg": "sum", "desc": True}
    vid = store.create_view(def_id, "By region", config, owner_identity="a@x.io")

    got = store.get_view(vid)
    assert got is not None
    assert got["name"] == "By region"
    assert got["scope"] == "private"
    assert got["locked"] is False
    assert got["config"] == config

    assert store.update_view(vid, name="Regions", scope="shared") == 1
    updated = store.get_view(vid)
    assert updated["name"] == "Regions"
    assert updated["scope"] == "shared"

    new_config = {"group_by": ["region", "product"], "value": "amount", "agg": "avg"}
    assert store.update_view(vid, config=new_config) == 1
    assert store.get_view(vid)["config"] == new_config

    assert store.delete_view(vid) == 1
    assert store.get_view(vid) is None


def test_view_scope_filtering_by_identity(store: MetadataStore) -> None:
    def_id = _view_def(store)
    store.create_view(def_id, "Mine", {}, scope="private", owner_identity="me@x.io")
    store.create_view(def_id, "Theirs", {}, scope="private", owner_identity="you@x.io")
    store.create_view(def_id, "Public", {}, scope="shared", owner_identity="me@x.io")

    mine = {v["name"] for v in store.list_views(def_id, "me@x.io")}
    assert mine == {"Mine", "Public"}

    theirs = {v["name"] for v in store.list_views(def_id, "you@x.io")}
    assert theirs == {"Theirs", "Public"}

    anon = {v["name"] for v in store.list_views(def_id, None)}
    assert anon == {"Public"}


def test_locked_view_is_immutable(store: MetadataStore) -> None:
    def_id = _view_def(store)
    vid = store.create_view(def_id, "Locked", {"a": 1}, locked=True)

    assert store.get_view(vid)["locked"] is True
    # A locked view cannot be modified.
    assert store.update_view(vid, name="Renamed") == 0
    assert store.get_view(vid)["name"] == "Locked"
    # ...but it can be unlocked, then edited.
    assert store.update_view(vid, locked=False) == 1
    assert store.update_view(vid, name="Renamed") == 1
    assert store.get_view(vid)["name"] == "Renamed"


def test_delete_definition_cascades_views(store: MetadataStore) -> None:
    def_id = _view_def(store)
    store.create_view(def_id, "V1", {}, scope="shared")
    assert len(store.list_views(def_id)) == 1
    store.delete_definition(def_id)
    assert store.list_views(def_id) == []
