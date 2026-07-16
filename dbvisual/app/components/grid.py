"""Reusable editable AG Grid component for Sheets.

Wraps ``ui.aggrid`` and tracks edits so the owning page can persist them through
the core CRUD helpers. Only columns flagged editable in the :class:`SheetView`
(main-table, non-PK) can be modified; related lookup columns are read-only.

AG Grid *community* features used here: inline editing, per-column sort & filter,
quick-filter search, and CSV export. Range-based clipboard copy is an Enterprise
feature, so a reliable TSV copy button and a paste dialog are provided instead.
"""

from __future__ import annotations

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
    ) -> None:
        self.view = view
        self.rules = rules or {}
        self.formulas = formulas or {}
        self.totals = totals or {}
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
            editable = col.editable and not is_formula
            class_rules: dict[str, str] = {}
            if editable:
                class_rules["dbv-negative"] = "typeof x === 'number' && x < 0"
            if col.field in self.rules:
                # Mark the cell when its field is listed in the row's error array.
                class_rules["dbv-invalid"] = (
                    "params.data && params.data.__err__ && "
                    f"params.data.__err__.indexOf('{col.field}') >= 0"
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
        return defs

    def _build(self) -> None:
        ui.html(_STYLE)
        with ui.row().classes("w-full items-center gap-2"):
            self._search = (
                ui.input(placeholder="Cerca…").props("dense clearable").classes("w-64")
            )
            self._search.on_value_change(lambda e: self._on_search(e.value))
            ui.button(icon="add", on_click=self.add_row).props("flat dense").tooltip(
                "Aggiungi riga"
            )
            ui.button(icon="delete", on_click=self.delete_selected).props(
                "flat dense color=negative"
            ).tooltip("Elimina selezionate")
            ui.button(icon="content_copy", on_click=self.copy_tsv).props(
                "flat dense"
            ).tooltip("Copia (TSV)")
            ui.button(icon="content_paste", on_click=self._paste_dialog).props(
                "flat dense"
            ).tooltip("Incolla da Excel (TSV)")
            ui.button(icon="download", on_click=self.export_csv).props(
                "flat dense"
            ).tooltip("Esporta CSV")
            groupable = {c.field: c.header for c in self.view.columns}
            self._group = (
                ui.select(groupable, label="Raggruppa per", multiple=True)
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

    # -- editing state ------------------------------------------------------

    def _on_cell_changed(self, event: Any) -> None:
        data = event.args.get("data") if isinstance(event.args, dict) else None
        if not data or "__id__" not in data:
            return
        rid = data["__id__"]
        self._apply_formulas(data)
        self._validate_row(data)
        self._by_id[rid] = data
        for i, row in enumerate(self.rows):
            if row.get("__id__") == rid:
                self.rows[i] = data
                break
        if rid in self._existing_ids:
            self._dirty_ids.add(rid)
        self._recompute_totals()
        self.grid.update()

    def add_row(self) -> None:
        """Append a blank editable row (persisted as an insert on save)."""
        row: dict[str, Any] = {c.field: None for c in self.view.columns}
        self._prepare(row)
        self.rows.append(row)
        self._by_id[row["__id__"]] = row
        self._recompute_totals()
        self.grid.update()

    async def delete_selected(self) -> None:
        """Remove the selected rows; existing rows are queued for deletion."""
        selected = await self.grid.get_selected_rows()
        ids = {r["__id__"] for r in selected if "__id__" in r}
        if not ids:
            ui.notify("Nessuna riga selezionata.", type="warning")
            return
        for rid in ids:
            if rid in self._existing_ids:
                self._deleted.append(self._by_id[rid])
            self._dirty_ids.discard(rid)
        self.rows = [r for r in self.rows if r.get("__id__") not in ids]
        self._by_id = {r["__id__"]: r for r in self.rows}
        self.grid.update()

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
                    value = len(nums)
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
        ui.notify("Copiato negli appunti (TSV).", type="positive")

    def to_tsv(self) -> str:
        """Serialize the visible columns and rows as tab-separated values."""
        fields = self._visible_fields()
        headers = [c.header for c in self.view.columns]
        lines = ["\t".join(headers)]
        for row in self.rows:
            lines.append(
                "\t".join("" if row.get(f) is None else str(row.get(f)) for f in fields)
            )
        return "\n".join(lines)

    def import_tsv(self, text: str, has_header: bool = True) -> int:
        """Append rows parsed from ``text`` (TSV). Returns the number added.

        Values map onto the editable fields, in column order. Non-editable
        (lookup/PK) columns are left empty so they are never written on save.
        """
        editable = [c.field for c in self.view.columns if c.editable]
        lines = [ln for ln in text.replace("\r\n", "\n").split("\n") if ln.strip()]
        if has_header and lines:
            lines = lines[1:]
        added = 0
        for line in lines:
            cells = line.split("\t")
            row: dict[str, Any] = {c.field: None for c in self.view.columns}
            for field, value in zip(editable, cells):
                row[field] = value
            self._tag(row)
            self.rows.append(row)
            self._by_id[row["__id__"]] = row
            added += 1
        if added:
            self.grid.update()
        return added

    def _paste_dialog(self) -> None:
        with ui.dialog() as dialog, ui.card().classes("w-[560px] gap-3"):
            ui.label("Incolla da Excel (TSV)").classes("text-lg font-semibold")
            ui.label(
                "Incolla le celle copiate da Excel. Le colonne editabili vengono "
                "riempite in ordine; le nuove righe saranno inserite al salvataggio."
            ).classes("text-sm text-gray-500")
            area = ui.textarea(placeholder="col1\tcol2\t…").classes("w-full h-40")
            header = ui.checkbox("La prima riga è un'intestazione", value=True)

            def do_import() -> None:
                n = self.import_tsv(area.value or "", has_header=header.value)
                dialog.close()
                ui.notify(f"Aggiunte {n} righe.", type="positive")

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Importa", on_click=do_import).props("color=primary")
                ui.button("Annulla", on_click=dialog.close).props("flat")
        dialog.open()
