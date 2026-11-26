"""Query filters, parameter prompts and page navigation shared by forms and sheets."""

from nicegui import ui

from dbvisual.app.editor_query import QueryPage, fetch_page
from dbvisual.app.report_service import resolve_param_options
from dbvisual.app.state import get_state
from dbvisual.core.introspect import resolve_table
from dbvisual.core.queryspec import Column, Filter, Param


class EditorPager:
    def __init__(self, engine, metadata, definition, model, dirty, show):
        self.engine, self.metadata, self.spec = engine, metadata, model.spec
        self.dirty, self.show = dirty, show
        self.values = {p.name: p.default for p in self.spec.params}
        self.page = QueryPage([])
        self.size = 50
        self.ready = False
        self.inputs = {}
        with ui.row().classes("items-end gap-2 flex-wrap"):
            for prompt in sorted(self.spec.params, key=lambda p: p.order):
                label = (prompt.label or prompt.name) + (
                    " *" if prompt.required else ""
                )
                if prompt.available.source != "none":
                    widget = ui.select({}, label=label, multiple=prompt.multi)
                else:
                    default = self.values[prompt.name]
                    text = (
                        ", ".join(map(str, default))
                        if isinstance(default, list)
                        else default
                    )
                    widget = ui.input(label, value=None if text is None else str(text))
                self.inputs[prompt.name] = widget
            for prompt in self.spec.params:
                if prompt.available.source != "none":
                    self.options(prompt)
                    if prompt.default is not None:
                        self.inputs[prompt.name].value = prompt.default
                    if prompt.depends_on in self.inputs:
                        self.inputs[prompt.depends_on].on_value_change(
                            lambda _, p=prompt: self.options(p)
                        )
            ui.button("Apply filters", on_click=lambda: self.load(0, apply=True))
            ui.button("Discard edits", on_click=self.discard).props("flat")
            self.previous = ui.button(
                icon="chevron_left", on_click=lambda: self.load(self.page.index - 1)
            ).tooltip("Previous page")
            self.next = ui.button(
                icon="chevron_right", on_click=lambda: self.load(self.page.index + 1)
            ).tooltip("Next page")
            self.limit = ui.select(
                [25, 50, 100, 250], value=self.size, label="Rows per page"
            )
            ui.button(
                "Query settings",
                icon="tune",
                on_click=lambda: self.configure(definition, model),
            ).props("flat")
        self.status = ui.label("").classes("text-sm")
        self.previous.disable()
        self.next.disable()

    async def discard(self):
        if not self.ready or not self.dirty():
            return
        with ui.dialog() as dialog, ui.card():
            ui.label("Discard unsaved edits on this page?")
            with ui.row():
                ui.button("Discard", on_click=lambda: dialog.submit(True))
                ui.button("Keep editing", on_click=lambda: dialog.submit(False)).props(
                    "flat"
                )
        if await dialog:
            self.refresh()

    def options(self, prompt):
        values = {name: w.value for name, w in self.inputs.items()}
        widget = self.inputs[prompt.name]
        opts = resolve_param_options(
            self.engine,
            self.metadata,
            prompt,
            main_table=self.spec.main_table,
            parent_values=values,
        )
        widget.set_options(
            {o["value"]: o["label"] for o in opts}, value=[] if prompt.multi else None
        )

    def allow_navigation(self):
        if self.dirty():
            ui.notify(
                "Save or discard your edits before changing the selection.",
                type="warning",
            )
            return False
        return True

    def load(self, index=0, *, apply=False, force=False):
        if not force and not self.allow_navigation():
            return
        values = {n: w.value for n, w in self.inputs.items()} if apply else self.values
        size = self.limit.value if apply else self.size
        try:
            page = fetch_page(
                self.engine, self.metadata, self.spec, values, index, size
            )
            if not page.rows and index:
                page = fetch_page(
                    self.engine, self.metadata, self.spec, values, 0, size
                )
        except Exception as exc:
            self.status.set_text(str(exc))
            return
        self.page, self.values, self.size, self.ready = page, values, size, True
        self.previous.set_enabled(page.index > 0)
        self.next.set_enabled(page.has_next)
        scope = "Page totals, search and exports use the loaded rows."
        if not list(resolve_table(self.metadata, self.spec.main_table).primary_key):
            scope = "Preview only. This table has no primary key for paging."
        self.status.set_text(f"Page {page.index + 1} · {len(page.rows)} rows. {scope}")
        self.show(page.rows)

    def refresh(self):
        self.load(self.page.index, force=True)

    def configure(self, definition, model):
        if not self.allow_navigation():
            return
        with ui.dialog() as dlg, ui.card().classes("w-[750px] max-w-full"):
            ui.label("Query settings").classes("text-xl font-bold")
            draft = model.model_copy(deep=True)
            listing = ui.column().classes("w-full")

            def render():
                listing.clear()
                with listing:
                    for flt in draft.spec.filters:
                        with ui.row():
                            ui.label(
                                f"{flt.column.table}.{flt.column.name} {flt.op} · {flt.param}"
                            )
                            ui.button(
                                icon="delete", on_click=lambda f=flt: remove(f)
                            ).props("flat dense")

            def remove(flt):
                draft.spec.filters.remove(flt)
                if not any(f.param == flt.param for f in draft.spec.filters):
                    draft.spec.params = [
                        p for p in draft.spec.params if p.name != flt.param
                    ]
                render()

            render()
            cols = {c.alias or c.name: c for c in draft.spec.columns}
            column = ui.select(list(cols), label="Field")
            with ui.row():
                op = ui.select(
                    ["eq", "ne", "lt", "le", "gt", "ge", "like", "in"],
                    value="eq",
                    label="Comparison",
                )
                kind = ui.select(
                    ["string", "integer", "float", "boolean", "date", "datetime"],
                    value="string",
                    label="Value type",
                )
                caption = ui.input("Prompt label")
                required = ui.checkbox("Required", value=True)

            def add():
                if not column.value:
                    ui.notify("Choose a field.")
                    return
                col = cols[column.value]
                name = col.name
                n = 1
                while any(p.name == name for p in draft.spec.params):
                    n += 1
                    name = f"{col.name}_{n}"
                draft.spec.params.append(
                    Param(
                        name=name,
                        type=kind.value,
                        multi=op.value == "in",
                        label=caption.value or name,
                        required=required.value,
                    )
                )
                draft.spec.filters.append(
                    Filter(
                        column=Column(table=col.table, name=col.name),
                        op=op.value,
                        param=name,
                    )
                )
                render()

            ui.button("Add filter", on_click=add)

            def save():
                ok = get_state().store.replace_definition_spec(
                    definition["id"], definition["queryspec_json"], draft.to_json()
                )
                if not ok:
                    ui.notify(
                        "The definition changed. Reopen it before saving.",
                        type="warning",
                    )
                    return
                dlg.close()
                ui.navigate.reload()

            with ui.row():
                ui.button("Save query settings", on_click=save)
                ui.button("Cancel", on_click=dlg.close).props("flat")
        dlg.open()
