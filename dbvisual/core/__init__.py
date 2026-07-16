"""Core, DB-agnostic layer of dbvisual.

Exposes connections, schema introspection, the query-spec models,
the query-spec compiler and generic CRUD helpers.
"""

from dbvisual.core.compiler import compile_select
from dbvisual.core.connections import ConnectionConfig, build_engine, test_connection
from dbvisual.core.crud import (
    delete_record,
    insert_record,
    save_master_detail,
    update_record,
)
from dbvisual.core.introspect import (
    ColumnInfo,
    ForeignKeyInfo,
    detect_foreign_keys,
    get_columns,
    list_tables,
    reflect_schema,
)
from dbvisual.core.queryspec import Column, Filter, Param, QuerySpec, Related

__all__ = [
    # connections
    "ConnectionConfig",
    "build_engine",
    "test_connection",
    # introspect
    "ColumnInfo",
    "ForeignKeyInfo",
    "reflect_schema",
    "list_tables",
    "get_columns",
    "detect_foreign_keys",
    # queryspec
    "Column",
    "Related",
    "Filter",
    "Param",
    "QuerySpec",
    # compiler
    "compile_select",
    # crud
    "insert_record",
    "update_record",
    "delete_record",
    "save_master_detail",
]
