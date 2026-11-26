import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dbvisual.app import state
from dbvisual.app.rest_api import issue_token, router, token_key


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "_state", None)
    service = state.init_state(
        tmp_path / "metadata.db", use_keyring=False, data_dir=tmp_path
    )
    store = service.store
    aid = store.create_application("Sales")
    other = store.create_application("Other")
    cid = store.create_connection("Source", "sqlite", database=":memory:")
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        yield client, service, aid, other, cid


def test_scoped_token_and_conditional_writes(api):
    client, service, aid, other, cid = api
    path = f"/api/v1/apps/{aid}/definitions"

    def auth(app_id):
        return {"Authorization": f"Bearer {issue_token(app_id)}"}

    assert client.get(path).status_code == 401
    headers = auth(aid)
    assert (
        client.get(f"/api/v1/apps/{other}/definitions", headers=headers).status_code
        == 401
    )
    payload = {
        "kind": "sheet",
        "name": "Sales",
        "specification": {"connection_id": cid, "spec": {"main_table": "orders"}},
    }
    response = client.post(path, headers=headers, json=payload)
    assert response.status_code == 201
    uri = response.headers["location"]
    assert client.post(path, headers=headers, json=payload).status_code == 409
    assert (
        client.get(
            uri.replace(f"/{aid}/", f"/{other}/"), headers=auth(other)
        ).status_code
        == 404
    )
    assert client.get(path, headers=headers).json() == [
        {"id": response.json()["id"], "kind": "sheet", "name": "Sales"}
    ]
    assert client.put(uri, headers=headers, json=payload).status_code == 428
    tag = response.headers["etag"]
    payload["name"] = "Archived"
    saved = client.put(uri, headers={**headers, "If-Match": tag}, json=payload)
    assert saved.status_code == 200 and saved.headers["etag"] != tag
    assert client.delete(uri, headers={**headers, "If-Match": tag}).status_code == 412
    assert client.get(uri, headers=headers).json()["name"] == "Archived"
    assert (
        client.delete(
            uri, headers={**headers, "If-Match": saved.headers["etag"]}
        ).status_code
        == 204
    )
    rotated = auth(aid)
    assert client.get(path, headers=headers).status_code == 401
    assert client.get(path, headers=rotated).json() == []
    service.secrets.delete_secret(token_key(aid))
    assert client.get(path, headers=rotated).status_code == 401


def test_rejects_invalid_import(api):
    client, _, aid, _, cid = api
    uri = f"/api/v1/apps/{aid}/definitions"
    headers = {"Authorization": f"Bearer {issue_token(aid)}"}
    for specification in (
        {},
        {"connection_id": cid + 1, "spec": {"main_table": "orders"}},
    ):
        assert (
            client.post(
                uri,
                headers=headers,
                json={"kind": "sheet", "name": "Bad", "specification": specification},
            ).status_code
            == 422
        )
    assert client.get(uri, headers=headers).json() == []
