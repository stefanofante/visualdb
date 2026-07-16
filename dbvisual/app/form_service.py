"""Form orchestration — the testable, UI-agnostic logic behind a Form.

A *Form* is a saved definition (``kind='form'``) whose ``queryspec_json`` holds a
:class:`FormSpec` (query-spec + connection id + per-field config + rules). Records
are loaded with the core compiler and shown one at a time; only the main table is
writable. All DB access delegates to the Phase 1 core.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import Engine, MetaData, Table, select, text

from dbvisual.app.formula import FormulaError, evaluate
from dbvisual.app.sheet_service import (  # reused Phase 3 helpers
    ConflictError,
    SheetView,
    build_view,
    get_table,
    load_rows,
    resolve_engine,
)
from dbvisual.app.validation import FieldRule, validate_field
from dbvisual.core.crud import delete_record, insert_record, update_record
from dbvisual.core.queryspec import QuerySpec

__all__ = [
    "AvailableValues",
    "FieldConfig",
    "SubmitRule",
    "FormRule",
    "FormSpec",
    "ConflictError",
    "SheetView",
    "build_view",
    "get_table",
    "load_rows",
    "resolve_engine",
    "apply_defaults",
    "validate_record",
    "check_submit_rules",
    "evaluate_form_rules",
    "resolve_available_values",
    "save_record",
    "delete_form_record",
]

InputType = Literal[
    "auto", "text", "multiline", "number", "date", "checkbox", "dropdown", "attachment"
]


class AvailableValues(BaseModel):
    """Source of allowed values for a dropdown field (label may differ from value)."""

    source: Literal["none", "column", "table", "query", "manual"] = "none"
    table: str | None = None
    value_col: str | None = None
    label_col: str | None = None
    query: str | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)  # {"value","label"}
    allow_new: bool = False


class FieldConfig(BaseModel):
    """Per-field presentation, default, allowed values and validation rule."""

    field: str  # grid field key (alias or column name)
    label: str = ""
    input: InputType = "auto"
    default: Any = None
    available: AvailableValues = Field(default_factory=AvailableValues)
    rule: FieldRule = Field(default_factory=FieldRule)


class SubmitRule(BaseModel):
    """Cross-field rule evaluated on the whole record before saving."""

    kind: Literal["at_least_one", "all_or_none", "expression"]
    fields: list[str] = Field(default_factory=list)
    expression: str | None = None
    message: str = "Regola di submit non soddisfatta."


class FormRule(BaseModel):
    """Conditional rule: when ``when_field`` matches, act on ``target``."""

    when_field: str
    op: Literal["eq", "ne", "empty", "not_empty", "truthy", "falsy"]
    value: Any = None
    action: Literal["hide", "show", "enable", "disable"]
    target: str


class FormSpec(BaseModel):
    """Persisted shape of a form definition."""

    connection_id: int
    spec: QuerySpec
    fields: list[FieldConfig] = Field(default_factory=list)
    submit_rules: list[SubmitRule] = Field(default_factory=list)
    form_rules: list[FormRule] = Field(default_factory=list)
    rls: bool = False  # Postgres row-level security (Phase 8); ignored otherwise.

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, raw: str) -> "FormSpec":
        return cls.model_validate_json(raw)


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


# -- defaults & validation --------------------------------------------------


def apply_defaults(fields: list[FieldConfig], record: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``record`` with configured defaults filling empty fields."""
    out = dict(record)
    for fc in fields:
        if fc.default is not None and _is_empty(out.get(fc.field)):
            out[fc.field] = fc.default
    return out


def validate_record(
    fields: list[FieldConfig], record: dict[str, Any]
) -> dict[str, list[str]]:
    """Validate each configured field; return ``{field: [messages]}`` (only errors)."""
    errors: dict[str, list[str]] = {}
    for fc in fields:
        msgs = validate_field(fc.rule, record.get(fc.field))
        if msgs:
            errors[fc.field] = msgs
    return errors


def check_submit_rules(rules: list[SubmitRule], record: dict[str, Any]) -> list[str]:
    """Return the messages of any violated cross-field submit rules."""
    violations: list[str] = []
    for rule in rules:
        if rule.kind == "at_least_one":
            if not any(not _is_empty(record.get(f)) for f in rule.fields):
                violations.append(rule.message)
        elif rule.kind == "all_or_none":
            filled = [not _is_empty(record.get(f)) for f in rule.fields]
            if any(filled) and not all(filled):
                violations.append(rule.message)
        elif rule.kind == "expression" and rule.expression:
            try:
                if not evaluate(rule.expression, record):
                    violations.append(rule.message)
            except FormulaError:
                violations.append(rule.message)
    return violations


def _match(op: str, actual: Any, value: Any) -> bool:
    if op == "eq":
        return actual == value
    if op == "ne":
        return actual != value
    if op == "empty":
        return _is_empty(actual)
    if op == "not_empty":
        return not _is_empty(actual)
    if op == "truthy":
        return bool(actual)
    if op == "falsy":
        return not bool(actual)
    return False


def evaluate_form_rules(
    rules: list[FormRule], record: dict[str, Any]
) -> dict[str, dict[str, bool]]:
    """Return per-field UI state ``{field: {"hidden": bool, "disabled": bool}}``."""
    state: dict[str, dict[str, bool]] = {}
    for rule in rules:
        if not _match(rule.op, record.get(rule.when_field), rule.value):
            continue
        entry = state.setdefault(rule.target, {"hidden": False, "disabled": False})
        if rule.action == "hide":
            entry["hidden"] = True
        elif rule.action == "show":
            entry["hidden"] = False
        elif rule.action == "disable":
            entry["disabled"] = True
        elif rule.action == "enable":
            entry["disabled"] = False
    return state


# -- available values -------------------------------------------------------


def resolve_available_values(
    engine: Engine,
    metadata: MetaData,
    available: AvailableValues,
    *,
    main_table: str,
    column: str,
) -> list[dict[str, Any]]:
    """Resolve the ``{value,label}`` options for a dropdown field.

    Supports distinct column values, a lookup table, a custom read-only query or
    a manual list. Label may differ from value (the value is what gets saved).
    """
    av = available
    if av.source == "manual":
        return list(av.items)
    if av.source == "none":
        return []
    if av.source == "column":
        tbl = get_table(metadata, main_table)
        with engine.connect() as conn:
            rows = conn.execute(select(tbl.c[column]).distinct()).scalars().all()
        return [{"value": v, "label": str(v)} for v in rows if v is not None]
    if av.source == "table" and av.table and av.value_col:
        tbl = get_table(metadata, av.table)
        label_col = av.label_col or av.value_col
        with engine.connect() as conn:
            rows = conn.execute(
                select(tbl.c[av.value_col], tbl.c[label_col]).distinct()
            ).all()
        return [{"value": r[0], "label": str(r[1])} for r in rows]
    if av.source == "query" and av.query:
        with engine.connect() as conn:
            result = conn.execute(text(av.query))
            out: list[dict[str, Any]] = []
            for row in result:
                value = row[0]
                label = row[1] if len(row) > 1 else row[0]
                out.append({"value": value, "label": str(label)})
        return out
    return []


# -- persistence ------------------------------------------------------------


def _editable_values(view: SheetView, record: dict[str, Any]) -> dict[str, Any]:
    field_to_col = view.field_to_column
    return {field_to_col[f]: record[f] for f in view.editable_fields if f in record}


def _pk_values(view: SheetView, record: dict[str, Any]) -> dict[str, Any]:
    field_to_col = view.field_to_column
    return {field_to_col[f]: record[f] for f in view.pk_fields}


def save_record(
    engine: Engine,
    view: SheetView,
    table: Table,
    record: dict[str, Any],
    *,
    is_new: bool,
    original: dict[str, Any] | None = None,
) -> Any:
    """Insert or update a single record (main-table columns only).

    On update, ``original`` (if given) enables optimistic locking; a concurrent
    change raises :class:`ConflictError` and writes nothing. Related lookup
    columns are never written.
    """
    values = _editable_values(view, record)
    if is_new:
        return insert_record(engine, table, values)
    pk = _pk_values(view, record)
    expected: dict[str, Any] | None = None
    if original is not None:
        field_to_col = view.field_to_column
        expected = {
            field_to_col[f]: original[f]
            for f in view.editable_fields
            if f in record and f in original
        }
    return update_record(engine, table, pk, values, expected=expected)


def delete_form_record(
    engine: Engine, view: SheetView, table: Table, record: dict[str, Any]
) -> int:
    """Delete the record identified by its primary-key fields."""
    return delete_record(engine, table, _pk_values(view, record))
