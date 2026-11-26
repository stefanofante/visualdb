"""Bound parameters and bounded database pages for editable definitions."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import Engine, MetaData

from dbvisual.core.compiler import compile_select
from dbvisual.core.introspect import resolve_table
from dbvisual.core.queryspec import Param, QuerySpec


def collect_params(prompts: list[Param], inputs: dict[str, Any]) -> dict[str, Any]:
    values = {}

    def boolean(value):
        names = {"true": True, "1": True, "false": False, "0": False}
        return names[str(value).strip().lower()]

    convert = {
        "integer": int,
        "float": float,
        "boolean": boolean,
        "date": date.fromisoformat,
        "datetime": datetime.fromisoformat,
    }
    for prompt in prompts:
        raw = inputs.get(prompt.name, prompt.default)
        if raw is None or raw == "" or raw == []:
            if prompt.required:
                raise ValueError(f"Enter a value for {prompt.label or prompt.name}.")
            continue
        if prompt.multi and not isinstance(raw, list):
            raw = [v.strip() for v in str(raw).split(",") if v.strip()]
        items = raw if prompt.multi else [raw]
        try:
            cast = convert.get(prompt.type, str)
            items = [cast(str(v)) for v in items]
        except (KeyError, ValueError) as exc:
            raise ValueError(
                f"Invalid {prompt.type} for {prompt.label or prompt.name}."
            ) from exc
        if prompt.required and not items:
            raise ValueError(f"Enter a value for {prompt.label or prompt.name}.")
        values[prompt.name] = items if prompt.multi else items[0]
    return values


@dataclass
class QueryPage:
    rows: list[dict[str, Any]]
    index: int = 0
    has_next: bool = False


def fetch_page(
    engine: Engine, metadata: MetaData, spec: QuerySpec, inputs, index=0, size=50
) -> QueryPage:
    if not 1 <= size <= 500 or index < 0:
        raise ValueError("Invalid database page.")
    values = collect_params(spec.params, inputs)
    table = resolve_table(metadata, spec.main_table)
    keys = list(table.primary_key)
    stmt = compile_select(spec, metadata, values)
    if not keys:
        # A keyless table can be previewed, but rows have no stable identity for paging.
        if index:
            raise ValueError("Paging requires a primary key.")
        stmt = stmt.limit(size)
    else:
        stmt = stmt.order_by(*keys).limit(size + 1).offset(index * size)
    with engine.connect() as conn:
        rows = [dict(r) for r in conn.execute(stmt).mappings()]
    return QueryPage(rows[:size], index, len(rows) > size)
