"""Configurable form field widget (Phase 4).

Renders the appropriate NiceGUI input for a :class:`FieldConfig` and the column's
data type, supports available-value dropdowns (label may differ from the saved
value), per-field validation with visual marking, conditional hide/disable, and
an attachment field type backed by :class:`AttachmentStore`.
"""

from __future__ import annotations

from typing import Any, Callable

from nicegui import ui

from dbvisual.app.form_service import FieldConfig
from dbvisual.app.validation import validate_field
from dbvisual.meta.attachments import (
    AttachmentStore,
    dump_metadata,
    load_metadata,
)


def _resolve_input(config: FieldConfig, col_type: str, has_options: bool) -> str:
    """Pick the concrete input kind from config, column type and options."""
    if config.input != "auto":
        return config.input
    if has_options:
        return "dropdown"
    t = col_type.lower()
    if any(k in t for k in ("int", "numeric", "decimal", "float", "double", "real")):
        return "number"
    if "date" in t or "time" in t:
        return "date"
    if "bool" in t:
        return "checkbox"
    return "text"


class FormField:
    """A single bound, validated form field."""

    def __init__(
        self,
        config: FieldConfig,
        *,
        editable: bool = True,
        col_type: str = "",
        options: list[dict[str, Any]] | None = None,
        on_change: Callable[[], None] | None = None,
        attachments: AttachmentStore | None = None,
        record_key: str = "",
        app_id: int = 0,
    ) -> None:
        self.config = config
        self.editable = editable
        self.options = options or []
        self._on_change = on_change
        self._attachments = attachments
        self._record_key = record_key
        self._app_id = app_id
        self._kind = _resolve_input(config, col_type, bool(self.options))
        self._widget: Any = None
        self._build()

    # -- construction -------------------------------------------------------

    def _build(self) -> None:
        with ui.column().classes("gap-0 w-full") as self.container:
            label = self.config.label or self.config.field
            if self._kind == "attachment":
                self._build_attachment(label)
            elif self._kind == "dropdown":
                mapping = {o["value"]: o["label"] for o in self.options}
                self._widget = ui.select(
                    mapping,
                    label=label,
                    with_input=self.config.available.allow_new,
                ).classes("w-full")
            elif self._kind == "multiline":
                self._widget = ui.textarea(label=label).classes("w-full")
            elif self._kind == "number":
                self._widget = ui.number(label=label).classes("w-full")
            elif self._kind == "date":
                with ui.input(label).classes("w-full") as self._widget:
                    with ui.menu().props("no-parent-event") as menu:
                        ui.date().bind_value(self._widget)
                    with self._widget.add_slot("append"):
                        ui.icon("event").on("click", menu.open).classes(
                            "cursor-pointer"
                        )
            elif self._kind == "checkbox":
                self._widget = ui.checkbox(label)
            else:
                self._widget = ui.input(label=label).classes("w-full")

            if not self.editable and self._widget is not None:
                self._widget.props("readonly")
            self._error = ui.label("").classes("text-xs text-red-600")

        if self._widget is not None and self._kind != "attachment":
            self._widget.on_value_change(lambda _e: self._changed())

    def _build_attachment(self, label: str) -> None:
        ui.label(label).classes("text-sm font-medium")
        self._att_value = ""  # JSON metadata string mirrored to the DB column
        self._att_list = ui.column().classes("gap-1")
        self._render_attachments()
        if self.editable and self._attachments is not None:
            ui.upload(on_upload=self._on_upload, auto_upload=True).props(
                "flat dense"
            ).classes("w-full")

    # -- attachment handling ------------------------------------------------

    def _render_attachments(self) -> None:
        self._att_list.clear()
        with self._att_list:
            for meta in load_metadata(self._att_value):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("attach_file")
                    ui.label(f"{meta['filename']} ({meta['size']} B)").classes(
                        "text-sm"
                    )
                    ui.button(
                        icon="delete",
                        on_click=lambda m=meta: self._remove_attachment(m),
                    ).props("flat dense color=negative size=sm")

    def _on_upload(self, event: Any) -> None:
        if self._attachments is None:
            return
        content = event.content.read()
        meta = self._attachments.save(
            self._app_id,
            self._record_key,
            event.name,
            content,
            getattr(event, "type", "application/octet-stream"),
        )
        items = load_metadata(self._att_value)
        items.append(meta)
        self._att_value = dump_metadata(items)
        self._render_attachments()
        self._changed()

    def _remove_attachment(self, meta: dict[str, Any]) -> None:
        if self._attachments is not None:
            self._attachments.delete(self._app_id, self._record_key, meta["id"])
        items = [m for m in load_metadata(self._att_value) if m["id"] != meta["id"]]
        self._att_value = dump_metadata(items)
        self._render_attachments()
        self._changed()

    # -- value & state ------------------------------------------------------

    @property
    def value(self) -> Any:
        if self._kind == "attachment":
            return self._att_value
        return self._widget.value if self._widget is not None else None

    @value.setter
    def value(self, new: Any) -> None:
        if self._kind == "attachment":
            self._att_value = new or ""
            self._render_attachments()
        elif self._widget is not None:
            self._widget.value = new

    def _changed(self) -> None:
        self.validate()
        if self._on_change:
            self._on_change()

    def validate(self) -> list[str]:
        """Validate the current value; mark the field and return error messages."""
        msgs = validate_field(self.config.rule, self.value)
        self._error.set_text("; ".join(msgs))
        if self._widget is not None:
            if msgs:
                self._widget.props("error")
            else:
                self._widget.props(remove="error")
        return msgs

    def set_state(self, hidden: bool = False, disabled: bool = False) -> None:
        """Apply conditional visibility / enabled state (from form rules)."""
        self.container.set_visibility(not hidden)
        if self._widget is not None:
            self._widget.set_enabled(not disabled)
