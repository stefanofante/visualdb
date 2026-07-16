"""Pydantic v2 models describing a query-spec.

A query-spec is the single source of truth from which forms, sheets and reports
are rendered. It is fully JSON-serializable so it can be stored in the local
metadata store and shipped to the UI.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Supported comparison operators for filters.
FilterOp = Literal["eq", "ne", "lt", "le", "gt", "ge", "like", "in"]

# Logical parameter types (used by the UI for input rendering / coercion).
ParamType = Literal["string", "integer", "float", "boolean", "date", "datetime"]


class Column(BaseModel):
    """A selected column, optionally aliased in the result set."""

    table: str
    name: str
    alias: str | None = None


class Related(BaseModel):
    """A related table joined via a foreign key (read-only in form/sheet)."""

    table: str
    local_col: str
    remote_col: str


class Filter(BaseModel):
    """A parametrized filter condition: ``column <op> :param``."""

    column: Column
    op: FilterOp
    param: str


class Param(BaseModel):
    """A named query parameter.

    When ``multi`` is ``True`` the parameter accepts a list of values (used by
    the ``in`` operator and cascading multi-value filters).
    """

    name: str
    type: ParamType = "string"
    multi: bool = False


class QuerySpec(BaseModel):
    """The complete specification of a query.

    ``main_table`` is the only updatable table in form/sheet renders; entries in
    ``related`` are joined read-only.
    """

    main_table: str
    columns: list[Column] = Field(default_factory=list)
    related: list[Related] = Field(default_factory=list)
    filters: list[Filter] = Field(default_factory=list)
    params: list[Param] = Field(default_factory=list)
