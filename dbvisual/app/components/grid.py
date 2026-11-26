"""Reusable editable AG Grid component for Sheets.

Wraps ``ui.aggrid`` and tracks edits so the owning page can persist them through
the core CRUD helpers. Only columns flagged editable in the :class:`SheetView`
(main-table, non-PK) can be modified; related lookup columns are read-only.

AG Grid *community* features used here: inline editing, per-column sort & filter,
quick-filter search, and CSV export. Range-based clipboard copy is an Enterprise
feature, so a reliable TSV copy button and a paste dialog are provided instead.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from nicegui import ui

from dbvisual.app.formula import FormulaError, evaluate
from dbvisual.app.sheet_service import SheetView
from dbvisual.app.validation import FieldRule, validate_field

# Client-side conditional styling: negative numbers red; invalid cells underlined.
_STYLE = (
    "<style>"
    ".dbv-negative{color:#dc2626;font-weight:600;}"
    ".dbv-invalid{border-bottom:2px solid #dc2626 !important;background:#fef2f2;}"
    "</style>"
)


def _to_num(value: Any) -> float | None:
    """Coerce a value to float, or return ``None`` when not numeric."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class SheetGrid:
    """An editable grid bound to a :class:`SheetView` and its row data.

    Optional ``rules`` (field -> :class:`FieldRule`) enable per-cell validation,
    ``formulas`` (field -> expression) enable computed columns, and ``totals``
    (field -> ``"sum"|"avg"|"count"``) render a live pinned bottom row that
    respects the active quick filter.
    """

    def __init__(
        self,
        view: SheetView,
        rows: list[dict[str, Any]],
        *,
        rules: dict[str, FieldRule] | None = None,
        formulas: dict[str, str] | None = None,
        totals: dict[str, str] | None = None,
        attachment_fields: list[str] | None = None,
        attachments: Any | None = None,
        app_id: int = 0,
    ) -> None:
        self.view = view
        self.rules = rules or {}
        self.formulas = formulas or {}
        self.totals = totals or {}
        self.attachment_fields = attachment_fields or []
        from dbvisual.meta.attachments import AttachmentDraft

        self._attachments = (
            AttachmentDraft(attachments, app_id) if attachments is not None else None
        )
        self._app_id = app_id
        self._id_seq = 0
        self.rows: list[dict[str, Any]] = [self._prepare(dict(r)) for r in rows]
        self._by_id: dict[str, dict[str, Any]] = {r["__id__"]: r for r in self.rows}
        self._existing_ids: set[str] = set(self._by_id)
        self._orig_by_id: dict[str, dict[str, Any]] = {
            r["__id__"]: self._snapshot(r) for r in self.rows
        }
        self._dirty_ids: set[str] = set()
        self._deleted: list[dict[str, Any]] = []
        self._build()

    # -- row identity -------------------------------------------------------

    def _tag(self, row: dict[str, Any]) -> dict[str, Any]:
        """Attach a stable client id used by AG Grid's ``getRowId``."""
        row["__id__"] = str(self._id_seq)
        self._id_seq += 1
        return row

    def _prepare(self, row: dict[str, Any]) -> dict[str, Any]:
        """Tag a row, evaluate its formulas and initialise its error marker."""
        self._tag(row)
        self._apply_formulas(row)
        row["__err__"] = []
        return row

    def _snapshot(self, row: dict[str, Any]) -> dict[str, Any]:
        """Copy the original field values of ``row`` (for optimistic locking)."""
        return {c.field: row.get(c.field) for c in self.view.columns}

    # -- formulas & validation ---------------------------------------------

    def _apply_formulas(self, row: dict[str, Any]) -> None:
        for field, expr in self.formulas.items():
            try:
                row[field] = evaluate(expr, row)
            except FormulaError:
                row[field] = None

    def _validate_row(self, row: dict[str, Any]) -> dict[str, list[str]]:
        errs: dict[str, list[str]] = {}
        for field, rule in self.rules.items():
            msgs = validate_field(rule, row.get(field))
            if msgs:
                errs[field] = msgs
        row["__err__"] = list(errs.keys())
        return errs

    def validate_all(self) -> dict[str, dict[str, list[str]]]:
        """Validate every row; return ``{row_id: {field: [messages]}}``."""
        all_errs: dict[str, dict[str, list[str]]] = {}
        for row in self.rows:
            errs = self._validate_row(row)
            if errs:
                all_errs[row["__id__"]] = errs
        self.grid.update()
        return all_errs

    def has_errors(self) -> bool:
        """True if any row currently fails validation."""
        return any(self._validate_row(r) for r in self.rows)

    # -- UI -----------------------------------------------------------------

    def _column_defs(self) -> list[dict[str, Any]]:
        defs: list[dict[str, Any]] = [{"field": "__id__", "hide": True}]
        for col in self.view.columns:
            is_formula = col.field in self.formulas
            editable = (
                col.editable
                and not is_formula
                and col.field not in self.attachment_fields
            )
            class_rules: dict[str, str] = {}
            if editable:
                class_rules["dbv-negative"] = "typeof x === 'number' && x < 0"
            if col.field in self.rules:
                # Mark the cell when its field is listed in the row's error array.
                class_rules["dbv-invalid"] = (
                    "params.data && params.data.__err__ && "
                    f"params.data.__err__.indexOf({json.dumps(col.field)}) >= 0"
                )
            defs.append(
                {
                    "field": col.field,
                    "headerName": col.header + (" ƒ" if is_formula else ""),
                    "editable": editable,
                    "sortable": True,
                    "filter": True,
                    "resizable": True,
                    "cellClassRules": class_rules,
                }
            )
            if col.field in self.view.assigned_keys and not is_formula:
                defs[-1].pop("editable")
                defs[-1][":editable"] = "p => p.data?.__newRow === true"
        return defs

    def _build(self) -> None:
        ui.add_head_html(_STYLE)
        with ui.row().classes("w-full items-center gap-2"):
            self._search = (
                ui.input(placeholder="Search...")
                .props("dense clearable")
                .classes("w-64")
            )
            self._search.on_value_change(lambda e: self._on_search(e.value))
            ui.button(icon="add", on_click=self.add_row).props("flat dense").tooltip(
                "Add row"
            )
            ui.button(icon="delete", on_click=self.delete_selected).props(
                "flat dense color=negative"
            ).tooltip("Delete selected")
            ui.button(icon="content_copy", on_click=self.copy_tsv).props(
                "flat dense"
            ).tooltip("Copy (TSV)")
            ui.button(icon="content_paste", on_click=self._paste_dialog).props(
                "flat dense"
            ).tooltip("Paste from Excel (TSV)")
            ui.button(icon="download", on_click=self.export_csv).props(
                "flat dense"
            ).tooltip("Export CSV")
            if self.attachment_fields and self._attachments is not None:
                ui.button(icon="attach_file", on_click=self._attachments_dialog).props(
                    "flat dense"
                ).tooltip("Attachments (selected row)")
            groupable = {c.field: c.header for c in self.view.columns}
            self._group = (
                ui.select(groupable, label="Group by", multiple=True)
                .props("dense outlined")
                .classes("w-56")
            )
            self._group.on_value_change(lambda e: self._apply_grouping(e.value or []))

        self.grid = ui.aggrid(
            {
                "columnDefs": self._column_defs(),
                "rowData": self.rows,
                "rowSelection": "multiple",
                "defaultColDef": {"flex": 1, "minWidth": 100},
                "stopEditingWhenCellsLoseFocus": True,
                "pinnedBottomRowData": [],
                ":getRowId": "(params) => params.data.__id__",
            }
        ).classes("w-full h-[60vh]")
        self.grid.on("cellValueChanged", self._on_cell_changed)
        self._recompute_totals()

    def _on_search(self, text: str | None) -> None:
        """React to the quick-filter input: filter rows and refresh totals."""
        self._set_quick_filter(text)
        self._recompute_totals()

    def capture_view(self) -> dict[str, Any]:
        """Return the current view config (search text and group-by fields)."""
        return {
            "search": self._search.value or "",
            "group_by": list(self._group.value or []),
        }

    def apply_view(self, config: dict[str, Any]) -> None:
        """Apply a saved view config (search text and group-by fields)."""
        self._search.value = config.get("search", "")
        group_by = config.get("group_by", [])
        self._group.value = group_by
        self._set_quick_filter(self._search.value)
        self._apply_grouping(group_by)
        self._recompute_totals()

    # -- editing state ------------------------------------------------------

    def _on_cell_changed(self, event: Any) -> None:
        data = event.args.get("data") if isinstance(event.args, dict) else None
        if not data or "__id__" not in data:
            return
        rid = data["__id__"]
        row = self._by_id.get(rid)
        field = event.args.get("colId")
        if (
            row is None
            or field not in self.view.writable_fields(rid not in self._existing_ids)
            or field in self.formulas
            or field in self.attachment_fields
        ):
            return
        row[field] = data.get(field)
        self._apply_formulas(row)
        self._validate_row(row)
        if rid in self._existing_ids:
            self._dirty_ids.add(rid)
        self._recompute_totals()
        self.grid.update()

    def add_row(self) -> None:
        """Append a blank editable row (persisted as an insert on save)."""
        row: dict[str, Any] = {c.field: None for c in self.view.columns}
        self._prepare(row)
        row["__newRow"] = True
        self.rows.append(row)
        self._by_id[row["__id__"]] = row
        self._recompute_totals()
        self.grid.update()

    async def delete_selected(self) -> None:
        """Remove the selected rows; existing rows are queued for deletion."""
        selected = await self.grid.get_selected_rows()
        ids = {r["__id__"] for r in selected if "__id__" in r}
        if not ids:
            ui.notify("No row selected.", type="warning")
            return
        for rid in ids:
            if rid in self._existing_ids:
                self._deleted.append(self._orig_by_id[rid])
            self._dirty_ids.discard(rid)
        self.rows = [r for r in self.rows if r.get("__id__") not in ids]
        self._by_id = {r["__id__"]: r for r in self.rows}
        self.grid.options["rowData"] = self.rows
        self._recompute_totals()
        self.grid.update()

    # -- attachments --------------------------------------------------------

    @property
    def attachment_draft(self):
        return self._attachments

    async def _attachments_dialog(self) -> None:
        """Manage attachments of the selected row's first attachment field."""
        from dbvisual.app.sheet_attachments import (
            record_key,
        )
        from dbvisual.meta.attachments import dump_metadata, load_metadata

        selected = await self.grid.get_selected_rows()
        if len(selected) != 1:
            ui.notify("Select exactly one row.", type="warning")
            return
        row = self._by_id.get(selected[0]["__id__"])
        if row is None:
            return
        choices = [f for f in self.attachment_fields if f in self.view.editable_fields]
        if not choices:
            return
        key = record_key(self.view, row)

        with ui.dialog() as dialog, ui.card().classes("w-[520px] gap-2"):
            selector = ui.select(choices, value=choices[0], label="Attachment field")
            listing = ui.column().classes("w-full gap-1")

            def render() -> None:
                field = selector.value
                listing.clear()
                with listing:
                    for meta in load_metadata(row.get(field)):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("attach_file")
                            ui.label(f"{meta['filename']} ({meta['size']} B)").classes(
                                "text-sm"
                            )
                            ui.button(
                                icon="download",
                                on_click=lambda m=meta: ui.download(
                                    self._attachments.read(key, m["id"]), m["filename"]
                                ),
                            ).props("flat dense")
                            ui.button(
                                icon="delete", on_click=lambda m=meta: _remove(m)
                            ).props("flat dense color=negative size=sm")

            def _remove(meta: dict[str, Any]) -> None:
                field = selector.value
                row[field] = dump_metadata(
                    [m for m in load_metadata(row.get(field)) if m["id"] != meta["id"]]
                )
                if row["__id__"] in self._existing_ids:
                    self._dirty_ids.add(row["__id__"])
                self.grid.update()
                render()

            async def _on_upload(event: Any) -> None:
                field = selector.value
                item = self._attachments.upload(
                    event.file.name, await event.file.read(), event.file.content_type
                )
                row[field] = dump_metadata([*load_metadata(row.get(field)), item])
                if row["__id__"] in self._existing_ids:
                    self._dirty_ids.add(row["__id__"])
                self.grid.update()
                render()

            render()
            ui.upload(on_upload=_on_upload, auto_upload=True).classes("w-full")
            selector.on_value_change(lambda _: render())
            ui.button("Close", on_click=dialog.close).props("flat")
        dialog.open()

    def collect_changes(
        self,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        """Return ``(inserts, updates, deletes)`` as field-keyed row dicts."""
        inserts = [r for r in self.rows if r["__id__"] not in self._existing_ids]
        updates = [self._by_id[i] for i in self._dirty_ids if i in self._by_id]
        return inserts, updates, list(self._deleted)

    def collect_changes_with_originals(
        self,
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
    ]:
        """Like :meth:`collect_changes` plus the original values of updated rows.

        The originals (parallel to ``updates``) let the caller build optimistic-
        locking guards.
        """
        inserts, updates, deletes = self.collect_changes()
        originals = [self._orig_by_id.get(r["__id__"], {}) for r in updates]
        return inserts, updates, deletes, originals

    def reload(self, rows: list[dict[str, Any]]) -> None:
        """Replace all data with freshly loaded rows and reset edit tracking."""
        self._id_seq = 0
        self.rows = [self._prepare(dict(r)) for r in rows]
        self._by_id = {r["__id__"]: r for r in self.rows}
        self._existing_ids = set(self._by_id)
        self._orig_by_id = {r["__id__"]: self._snapshot(r) for r in self.rows}
        self._dirty_ids = set()
        self._deleted = []
        self.grid.options["rowData"] = self.rows
        self._recompute_totals()
        self.grid.update()

    # -- totals -------------------------------------------------------------

    def _filtered_rows(self) -> list[dict[str, Any]]:
        """Rows matching the active quick-filter text (case-insensitive)."""
        text = (self._search.value or "").strip().lower()
        if not text:
            return self.rows
        fields = self._visible_fields()
        matches = []
        for r in self.rows:
            hay = " ".join(
                "" if r.get(f) is None else str(r.get(f)) for f in fields
            ).lower()
            if text in hay:
                matches.append(r)
        return matches

    def _recompute_totals(self) -> None:
        """Rebuild the pinned bottom row of column totals over filtered rows."""
        if not self.totals:
            return
        rows = self._filtered_rows()
        pinned: dict[str, Any] = {"__id__": "__totals__"}
        label_placed = False
        for col in self.view.columns:
            f = col.field
            if f in self.totals:
                nums = [n for n in (_to_num(r.get(f)) for r in rows) if n is not None]
                agg = self.totals[f]
                if agg == "sum":
                    value: Any = sum(nums)
                elif agg == "avg":
                    value = round(sum(nums) / len(nums), 4) if nums else 0
                else:  # count
                    value = sum(row.get(f) is not None for row in rows)
                pinned[f] = value
            elif not label_placed:
                pinned[f] = "Σ"
                label_placed = True
        self.grid.options["pinnedBottomRowData"] = [pinned]
        self.grid.update()

    # -- grid actions -------------------------------------------------------

    def _set_quick_filter(self, text: str | None) -> None:
        self.grid.run_grid_method("setGridOption", "quickFilterText", text or "")

    def _apply_grouping(self, fields: list[str]) -> None:
        """Toggle row-group flags on the chosen columns (Enterprise for display)."""
        chosen = set(fields)
        for col in self.grid.options["columnDefs"]:
            if col.get("field") in {c.field for c in self.view.columns}:
                col["rowGroup"] = col["field"] in chosen
        self.grid.update()

    def _visible_fields(self) -> list[str]:
        return [c.field for c in self.view.columns]

    def export_csv(self) -> None:
        """Trigger a client-side CSV download of the grid content."""
        self.grid.run_grid_method(
            "exportDataAsCsv", {"columnKeys": self._visible_fields()}
        )

    async def copy_tsv(self) -> None:
        """Copy the whole grid to the clipboard as Excel-friendly TSV."""
        await ui.clipboard.write(self.to_tsv())
        ui.notify("Copied to clipboard (TSV).", type="positive")

    def to_tsv(self) -> str:
        """Serialize the visible columns and rows as tab-separated values."""
        fields = self._visible_fields()
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, dialect="excel-tab")
        writer.writerow(c.header for c in self.view.columns)
        writer.writerows([row.get(f) for f in fields] for row in self.rows)
        return stream.getvalue()

    def import_tsv(self, text: str, has_header: bool = True) -> int:
        """Map labelled columns by name so skipped keys never shift cell values."""
        writable = (
            self.view.writable_fields(True)
            - set(self.attachment_fields)
            - self.formulas.keys()
        )
        editable = [col.field for col in self.view.columns if col.field in writable]
        records = csv.reader(io.StringIO(text, newline=""), dialect="excel-tab")
        if has_header:
            headers = next(records, [])
            known = {col.header: col.field for col in self.view.columns}
            if any(h in known for h in headers):
                editable = [known.get(h) for h in headers]
        added = 0
        for cells in records:
            if not cells:
                continue
            row: dict[str, Any] = {c.field: None for c in self.view.columns}
            for field, value in zip(editable, cells):
                if field in writable:
                    row[field] = value
            self._prepare(row)
            row["__newRow"] = True
            self.rows.append(row)
            self._by_id[row["__id__"]] = row
            added += 1
        if added:
            self._recompute_totals()
            self.grid.update()
        return added

    def _paste_dialog(self) -> None:
        with ui.dialog() as dialog, ui.card().classes("w-[560px] gap-3"):
            ui.label("Paste from Excel (TSV)").classes("text-lg font-semibold")
            ui.label(
                "Paste the cells copied from Excel. Editable columns are filled in "
                "order; new rows will be inserted on save."
            ).classes("text-sm text-gray-500")
            area = ui.textarea(placeholder="col1\tcol2\t...").classes("w-full h-40")
            header = ui.checkbox("First row is a header", value=True)

            def do_import() -> None:
                n = self.import_tsv(area.value or "", has_header=header.value)
                dialog.close()
                ui.notify(f"Added {n} rows.", type="positive")

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Import", on_click=do_import).props("color=primary")
                ui.button("Cancel", on_click=dialog.close).props("flat")
        dialog.open()
