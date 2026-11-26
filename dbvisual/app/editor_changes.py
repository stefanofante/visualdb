"""Review and reconcile record edits while retaining the transaction's version guards."""

from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy import Engine, select

from dbvisual.app.sheet_attachments import inserted_record_key, record_key
from dbvisual.app.sheet_service import SheetView, apply_batch
from dbvisual.core.crud import Operation
from dbvisual.meta.attachments import AttachmentDraft, load_metadata


@dataclass
class RowConflict:
    index: int
    op: Operation
    current: dict[str, Any] | None


def read_conflicts(engine: Engine, operations: list[Operation]) -> list[RowConflict]:
    conflicts = []
    with engine.connect() as conn:
        for index, op in enumerate(operations):
            if op.kind == "insert" or op.expected is None:
                continue
            keys = op.pk_values or {}
            if set(keys) != {c.key for c in op.table.primary_key} or not keys:
                raise ValueError("Resolving a conflict requires the complete key.")
            columns = [op.table.c[name] for name in op.expected] or list(
                op.table.primary_key
            )
            row = (
                conn.execute(
                    select(*columns).where(
                        *(op.table.c[k] == v for k, v in keys.items())
                    )
                )
                .mappings()
                .one_or_none()
            )
            current = dict(row) if row is not None else None
            if current is None or any(current[k] != v for k, v in op.expected.items()):
                conflicts.append(RowConflict(index, op, current))
    return conflicts


def reconcile(
    conflict: RowConflict, keep_local: set[str], *, delete: bool = False
) -> Operation | None:
    op, current = conflict.op, conflict.current
    if current is None or (op.kind == "delete" and not delete):
        return None
    if op.kind == "delete":
        return replace(op, expected=current)
    values = dict(op.values or {})
    for field, original in (op.expected or {}).items():
        if field in values and current[field] != original and field not in keep_local:
            values[field] = current[field]
    if all(
        field in current and current[field] == value for field, value in values.items()
    ):
        return None
    return replace(op, values=values, expected=current)


def save_reviewed(
    engine: Engine,
    ops: list[Operation],
    view: SheetView,
    draft: AttachmentDraft | None,
    fields: list[str],
) -> bool:
    """Commit exactly the reviewed rows and files, including a reconciled retry."""
    if draft is None or not fields:
        apply_batch(engine, ops)
        return True
    mapping = view.field_to_column
    names = [mapping[field] for field in fields if field in view.editable_fields]

    def key_for(op):
        return record_key(
            view, {field: op.pk_values[mapping[field]] for field in view.pk_fields}
        )

    def install(results):
        for op, result in zip(ops, results, strict=True):
            values = [(op.values or {}).get(name) for name in names]
            if any(load_metadata(v) for v in values):
                key = (
                    inserted_record_key(view, result)
                    if op.kind == "insert"
                    else key_for(op)
                )
                draft.install(key, values)

    try:
        apply_batch(engine, ops, before_commit=install)
    except Exception:
        draft.finish(False)
        raise
    draft.finish(True)
    cleaned = True
    for op in ops:
        if op.kind != "insert":
            old = op.expected or {}
            new = {} if op.kind == "delete" else {**old, **(op.values or {})}
            try:
                draft.discard_removed(
                    key_for(op),
                    [old.get(n) for n in names],
                    [new.get(n) for n in names],
                )
            except OSError:
                cleaned = False
    return cleaned
