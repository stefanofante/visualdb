"""Master-detail orchestration (Phase 6) — atomic master + details save.

UI-agnostic and testable. A *master-detail* is a ``kind='master_detail'``
definition holding a :class:`MasterDetailSpec`: a master query plus one or more
detail queries, each having exactly one parameter bound to the master's primary
key. Master and all detail changes commit in a single transaction via the core
``save_master_detail`` (with optimistic locking); on any error everything rolls
back. Only each query's main table is writable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import Engine, MetaData, Table

from dbvisual.app.sheet_service import (
    ConflictError,
    SheetView,
    build_operations,
)
from dbvisual.core.compiler import compile_select
from dbvisual.core.crud import Operation, save_master_detail
from dbvisual.core.introspect import detect_foreign_keys
from dbvisual.core.queryspec import QuerySpec

__all__ = [
    "DetailQuery",
    "MasterDetailSpec",
    "ConflictError",
    "validate_detail_query",
    "suggest_detail_fk",
    "load_details",
    "DetailChange",
    "build_save_plan",
    "execute_save",
]


class DetailQuery(BaseModel):
    """A detail query: a query-spec with exactly one FK parameter to the master."""

    title: str = ""
    spec: QuerySpec
    param_name: str  # the single parameter (bound to the master PK)
    fk_column: str  # detail main-table column referencing the master PK

    def validate_single_param(self) -> None:
        validate_detail_query(self)


class MasterDetailSpec(BaseModel):
    """Persisted shape: a master query-spec plus its detail queries."""

    connection_id: int
    master_spec: QuerySpec
    master_pk_field: str = ""  # master field carrying the PK (auto if empty)
    details: list[DetailQuery] = Field(default_factory=list)

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, raw: str) -> "MasterDetailSpec":
        return cls.model_validate_json(raw)


# -- validation & FK detection ----------------------------------------------


def validate_detail_query(detail: DetailQuery) -> None:
    """Raise ``ValueError`` unless the detail query has exactly one parameter."""
    n = len(detail.spec.params)
    if n != 1:
        raise ValueError(
            f"La detail query deve avere esattamente un parametro (trovati {n})."
        )
    if detail.spec.params[0].name != detail.param_name:
        raise ValueError("Il nome del parametro non corrisponde a quello dichiarato.")


def suggest_detail_fk(
    metadata: MetaData, master_table: str, detail_table: str
) -> tuple[str, str] | None:
    """Return ``(fk_column, master_remote_col)`` linking detail → master, if any.

    Uses ``detect_foreign_keys`` on the detail table to find the FK whose remote
    table is the master's main table.
    """
    for fk in detect_foreign_keys(metadata, detail_table):
        if fk.remote_table == master_table:
            return fk.local_col, fk.remote_col
    return None


# -- loading ----------------------------------------------------------------


def load_details(
    engine: Engine,
    metadata: MetaData,
    detail: DetailQuery,
    master_pk_value: Any,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Load the detail rows for a given master PK (bound to the single param)."""
    stmt = compile_select(detail.spec, metadata, {detail.param_name: master_pk_value})
    with engine.connect() as conn:
        result = conn.execute(stmt)
        fields = list(result.keys())
        rows = [dict(r) for r in result.mappings()]
    return fields, rows


# -- saving -----------------------------------------------------------------


@dataclass(slots=True)
class DetailChange:
    """Collected edits for one detail grid, plus its resolved view/table/FK."""

    view: SheetView
    table: Table
    fk_column: str
    inserts: list[dict[str, Any]] = field(default_factory=list)
    updates: list[dict[str, Any]] = field(default_factory=list)
    deletes: list[dict[str, Any]] = field(default_factory=list)
    update_originals: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class SavePlan:
    """A ready-to-execute atomic plan: master op + detail ops + FK injections."""

    master_op: Operation
    detail_ops: list[Operation]
    fk_injections: list[tuple[Operation, str]]
    master_is_new: bool


def _editable_values(view: SheetView, record: dict[str, Any]) -> dict[str, Any]:
    f2c = view.field_to_column
    return {f2c[f]: record[f] for f in view.editable_fields if f in record}


def _pk_values(view: SheetView, record: dict[str, Any]) -> dict[str, Any]:
    f2c = view.field_to_column
    return {f2c[f]: record[f] for f in view.pk_fields}


def build_save_plan(
    *,
    master_view: SheetView,
    master_table: Table,
    master_record: dict[str, Any],
    master_is_new: bool,
    master_original: dict[str, Any] | None,
    details: list[DetailChange],
    master_pk_value: Any | None,
) -> SavePlan:
    """Assemble the master op, all detail ops and FK injections for new details.

    For an existing master the known ``master_pk_value`` is written directly into
    new detail rows' FK column. For a new master the FK is injected after insert
    (via the returned ``fk_injections``) using the generated primary key.
    """
    if master_is_new:
        master_op = Operation(
            kind="insert",
            table=master_table,
            values=_editable_values(master_view, master_record),
        )
    else:
        expected: dict[str, Any] | None = None
        if master_original is not None:
            f2c = master_view.field_to_column
            expected = {
                f2c[f]: master_original[f]
                for f in master_view.editable_fields
                if f in master_record and f in master_original
            }
        master_op = Operation(
            kind="update",
            table=master_table,
            pk_values=_pk_values(master_view, master_record),
            values=_editable_values(master_view, master_record),
            expected=expected,
        )

    detail_ops: list[Operation] = []
    fk_injections: list[tuple[Operation, str]] = []
    for dc in details:
        ops = build_operations(
            dc.view,
            dc.table,
            inserts=dc.inserts,
            updates=dc.updates,
            deletes=dc.deletes,
            update_originals=dc.update_originals or None,
        )
        for op in ops:
            if op.kind == "insert" and op.values is not None:
                if master_is_new:
                    fk_injections.append((op, dc.fk_column))
                elif master_pk_value is not None:
                    op.values[dc.fk_column] = master_pk_value
            detail_ops.append(op)

    return SavePlan(
        master_op=master_op,
        detail_ops=detail_ops,
        fk_injections=fk_injections,
        master_is_new=master_is_new,
    )


def execute_save(engine: Engine, plan: SavePlan) -> list[Any]:
    """Execute the plan atomically, propagating a new master PK into detail FKs."""

    def _link(master_result: Any, _detail_ops: list[Operation]) -> None:
        if not plan.master_is_new or not plan.fk_injections:
            return
        new_pk = master_result[0] if master_result else None
        for op, fk_column in plan.fk_injections:
            if op.values is not None:
                op.values[fk_column] = new_pk

    return save_master_detail(engine, plan.master_op, plan.detail_ops, link=_link)
