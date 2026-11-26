"""Group fields in reading order and edit the persisted twelve-column form layout."""

from nicegui import ui

from dbvisual.app.state import get_state


def layout_rows(fields):
    rows = {}
    for index, field in enumerate(fields, 1):
        rows.setdefault(field.layout_row or index, []).append(field)
    return [rows[key] for key in sorted(rows)]


def edit_layout(definition, model):
    with ui.dialog() as dlg, ui.card().classes("w-[630px] max-w-full"):
        ui.label("Form layout").classes("text-xl font-bold")
        ui.label(
            "Place fields on the same row using up to 12 columns. Narrow windows stack fields in reading order."
        )
        inputs = []
        with ui.column().classes("w-full max-h-[60vh] overflow-auto"):
            for i, field in enumerate(model.fields, 1):
                with ui.row().classes("items-center"):
                    ui.label(field.label or field.field).classes("w-36")
                    row = ui.number(
                        "Row", value=field.layout_row or i, min=1, precision=0
                    ).classes("w-24")
                    width = ui.select(
                        list(range(1, 13)), label="Width", value=field.width
                    ).classes("w-24")
                    inputs.append((row, width))

        def save():
            draft = model.model_copy(deep=True)
            for field, (row, width) in zip(draft.fields, inputs, strict=True):
                if row.value is None or row.value < 1 or row.value != int(row.value):
                    ui.notify(
                        "Row numbers must be positive whole numbers.", type="warning"
                    )
                    return
                field.layout_row, field.width = int(row.value), width.value
            if any(
                sum(f.width for f in group) > 12 for group in layout_rows(draft.fields)
            ):
                ui.notify(
                    "A row exceeds 12 columns. Reduce a width or move a field.",
                    type="warning",
                )
                return
            if not get_state().store.replace_definition_spec(
                definition["id"], definition["queryspec_json"], draft.to_json()
            ):
                ui.notify(
                    "The definition changed. Reopen it before saving.", type="warning"
                )
                return
            dlg.close()
            ui.navigate.reload()

        with ui.row():
            ui.button("Save layout", on_click=save)
            ui.button("Cancel", on_click=dlg.close).props("flat")
    dlg.open()
