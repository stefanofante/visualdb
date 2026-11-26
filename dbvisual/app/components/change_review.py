"""Preview a transaction, then resolve concurrent edits using current database values."""

from nicegui import ui

from dbvisual.app.editor_changes import read_conflicts, reconcile
from dbvisual.core.crud import ConflictError


def display(value):
    return "NULL" if value is None else str(value)


async def review_changes(engine, operations, commit):
    if not operations:
        ui.notify("No changes to save.")
        return False
    with (
        ui.dialog().props("persistent") as dialog,
        ui.card().classes("w-[760px] max-w-full"),
    ):
        ui.label("Review pending changes").classes("text-xl font-bold")
        with ui.column().classes("max-h-[65vh] w-full overflow-auto"):
            for op in operations:
                key = ", ".join(f"{k}={v}" for k, v in (op.pk_values or {}).items())
                ui.label(f"{op.kind.title()} · {op.table.name} {key}").classes(
                    "font-semibold"
                )
                original, local = op.expected or {}, op.values or {}
                for name in dict.fromkeys([*original, *local]):
                    if op.kind == "update" and local.get(name) == original.get(name):
                        continue
                    if op.kind == "update":
                        ui.label(
                            f"{name}   {display(original.get(name))} → {display(local.get(name))}"
                        )
                    else:
                        ui.label(
                            f"{name}   {display((original if op.kind == 'delete' else local).get(name))}"
                        )
        with ui.row():
            ui.button("Save changes", on_click=lambda: dialog.submit(True))
            ui.button("Keep editing", on_click=lambda: dialog.submit(False)).props(
                "flat"
            )
    if not await dialog:
        return False
    pending = list(operations)
    while pending:
        try:
            commit(pending)
            return True
        except ConflictError:
            conflicts = read_conflicts(engine, pending)
            if not conflicts:
                ui.notify(
                    "The database changed. Review and save again.", type="warning"
                )
                return False
        with (
            ui.dialog().props("persistent") as dlg,
            ui.card().classes("w-[900px] max-w-full"),
        ):
            ui.label("Resolve changes made by another user").classes(
                "text-xl font-bold"
            )
            choices, deletes = {}, {}
            with ui.column().classes("max-h-[65vh] w-full overflow-auto"):
                for conflict in conflicts:
                    op, current = conflict.op, conflict.current
                    ui.label(f"{op.table.name} · {op.pk_values}").classes(
                        "font-semibold"
                    )
                    if current is None:
                        ui.label("This record was deleted. Continuing omits this edit.")
                        continue
                    if op.kind == "delete":
                        deletes[conflict.index] = ui.checkbox(
                            "Delete the displayed database version"
                        )
                    with ui.grid(columns=5).classes("w-full items-center"):
                        for label in [
                            "Field",
                            "Originally loaded",
                            "Your edit",
                            "Database now",
                            "Keep",
                        ]:
                            ui.label(label).classes("font-semibold")
                        for field, old in (op.expected or {}).items():
                            local = (op.values or {}).get(field, old)
                            db = current[field]
                            if old == db and old == local:
                                continue
                            for value in (field, old, local, db):
                                ui.label(display(value)).classes("break-all")
                            if op.kind == "update" and db != old and local != db:
                                choices[conflict.index, field] = ui.select(
                                    ["Database", "Local"], value="Database"
                                )
                            else:
                                ui.label("Local" if local != old else "Database")
            with ui.row():
                ui.button("Apply choices and retry", on_click=lambda: dlg.submit(True))
                ui.button("Keep editing", on_click=lambda: dlg.submit(False)).props(
                    "flat"
                )
        if not await dlg:
            return False
        resolved = dict(enumerate(pending))
        for conflict in conflicts:
            index = conflict.index
            local = {
                field
                for (i, field), widget in choices.items()
                if i == index and widget.value == "Local"
            }
            resolved[index] = reconcile(
                conflict, local, delete=index in deletes and deletes[index].value
            )
        pending = [op for op in resolved.values() if op is not None]
    return True
