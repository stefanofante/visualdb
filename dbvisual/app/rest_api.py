"""Local versioned API for exporting and maintaining application definitions."""

import hashlib
import hmac
import json
import secrets
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.exc import IntegrityError

from dbvisual.app.form_service import FormSpec
from dbvisual.app.master_detail_service import MasterDetailSpec
from dbvisual.app.report_service import ReportSpec
from dbvisual.app.sheet_service import SheetSpec
from dbvisual.app.state import get_state

MODELS = {
    "sheet": SheetSpec,
    "form": FormSpec,
    "report": ReportSpec,
    "master_detail": MasterDetailSpec,
}
Kind = Literal["sheet", "form", "report", "master_detail"]
bearer = HTTPBearer(auto_error=False)


def token_key(app_id: int) -> str:
    return f"rest:v1:{app_id}"


def issue_token(app_id: int) -> str:
    token = secrets.token_urlsafe(32)
    get_state().secrets.set_secret(
        token_key(app_id), hashlib.sha256(token.encode()).hexdigest()
    )
    return token


def authorize(
    app_id: int,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    expected = get_state().secrets.get_secret(token_key(app_id))
    supplied = (
        hashlib.sha256(credentials.credentials.encode()).hexdigest()
        if credentials
        else ""
    )
    if not expected or not hmac.compare_digest(expected, supplied):
        raise HTTPException(
            401,
            "A valid application token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )


router = APIRouter(
    prefix="/api/v1/apps/{app_id}",
    dependencies=[Depends(authorize)],
    tags=["Definitions"],
)


class DefinitionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Kind
    name: str = Field(min_length=1, max_length=200)
    specification: dict


def representation(row):
    return {
        "id": row["id"],
        "app_id": row["app_id"],
        "name": row["name"],
        "kind": row["kind"],
        "specification": json.loads(row["queryspec_json"]),
    }


def etag(row):
    data = json.dumps(
        representation(row), sort_keys=True, separators=(",", ":")
    ).encode()
    return '"' + hashlib.sha256(data).hexdigest() + '"'


def lookup(app_id, definition_id):
    row = get_state().store.get_definition(definition_id)
    if row is None or row["app_id"] != app_id:
        raise HTTPException(404, "Definition not found.")
    return row


def validated(body):
    try:
        model = MODELS[body.kind].model_validate(body.specification)
    except ValidationError:
        raise HTTPException(
            422, "Invalid specification for the requested kind."
        ) from None
    if get_state().store.get_connection(model.connection_id) is None:
        raise HTTPException(422, "Choose an existing local connection.")
    return model.model_dump_json()


def check_version(row, match):
    if match is None:
        raise HTTPException(428, "Supply the ETag from GET in If-Match.")
    if match != etag(row):
        raise HTTPException(412, "The stored definition changed.")


@router.get("/definitions")
def list_definitions(app_id: int):
    rows = get_state().store.list_definitions(app_id)
    return [{k: r[k] for k in ("id", "name", "kind")} for r in rows]


@router.get("/definitions/{definition_id}")
def get_definition(app_id: int, definition_id: int, response: Response):
    row = lookup(app_id, definition_id)
    response.headers["ETag"] = etag(row)
    response.headers["Cache-Control"] = "no-store"
    return representation(row)


@router.post("/definitions", status_code=201)
def create_definition(app_id: int, body: DefinitionInput, response: Response):
    store = get_state().store
    if store.get_application(app_id) is None:
        raise HTTPException(404, "Application not found.")
    spec = validated(body)
    try:
        did = store.create_definition(app_id, body.kind, body.name, spec)
    except IntegrityError:
        raise HTTPException(
            409, "The application or definition name changed."
        ) from None
    response.headers["Location"] = f"/api/v1/apps/{app_id}/definitions/{did}"
    return get_definition(app_id, did, response)


@router.put("/definitions/{definition_id}")
def replace_definition(
    app_id: int,
    definition_id: int,
    body: DefinitionInput,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
):
    row = lookup(app_id, definition_id)
    check_version(row, if_match)
    if row["kind"] != body.kind:
        raise HTTPException(422, "A definition keeps its original kind.")
    try:
        changed = get_state().store.change_definition_if_current(
            row, name=body.name, spec=validated(body)
        )
    except IntegrityError:
        raise HTTPException(409, "That definition name is already in use.") from None
    if not changed:
        raise HTTPException(412, "The stored definition changed.")
    return get_definition(app_id, definition_id, response)


@router.delete("/definitions/{definition_id}", status_code=204)
def remove_definition(
    app_id: int, definition_id: int, if_match: Annotated[str | None, Header()] = None
):
    row = lookup(app_id, definition_id)
    check_version(row, if_match)
    if not get_state().store.change_definition_if_current(row):
        raise HTTPException(412, "The stored definition changed.")
    return Response(status_code=204)
