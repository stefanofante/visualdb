"""Reflect DuckDB using its own catalog rather than PostgreSQL compatibility views."""

from sqlalchemy import (
    Column,
    ForeignKeyConstraint,
    MetaData,
    PrimaryKeyConstraint,
    Table,
    text,
)
from sqlalchemy.types import Numeric, UserDefinedType


class DuckType(UserDefinedType):
    """Retain the DuckDB spelling of nested and extension types."""

    cache_ok = True

    def __init__(self, name):
        self.name = name

    def get_col_spec(self, **kw):
        return self.name


def reflect_duckdb(engine, schema):
    metadata = MetaData(schema=schema)
    scope = "database_name = current_database() AND schema_name = coalesce(:schema, current_schema())"
    columns = text("""
        SELECT c.table_name, c.column_name, c.data_type, c.is_nullable,
               c.numeric_precision, c.numeric_scale
        FROM duckdb_columns() AS c JOIN duckdb_tables() AS t USING (database_oid, schema_oid, table_oid)
        WHERE c.database_name = current_database()
          AND c.schema_name = coalesce(:schema, current_schema()) AND NOT t.internal
        ORDER BY c.table_name, c.column_index
    """)
    with engine.connect() as conn:
        tables = {}
        for name, field, dtype, nullable, precision, scale in conn.execute(
            columns, {"schema": schema}
        ):
            if name not in tables:
                tables[name] = Table(name, metadata)
            cls = engine.dialect.ischema_names.get(dtype.lower())
            if dtype.startswith("DECIMAL"):
                sa_type = Numeric(precision, scale)
            else:
                sa_type = cls() if cls else DuckType(dtype)
            tables[name].append_column(Column(field, sa_type, nullable=nullable))
        keys = text(f"""
            SELECT table_name, constraint_type, constraint_column_names, referenced_table, referenced_column_names
            FROM duckdb_constraints() WHERE {scope} AND constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY')
        """)
        for name, kind, fields, target, remote in conn.execute(
            keys, {"schema": schema}
        ):
            if kind == "PRIMARY KEY":
                tables[name].append_constraint(PrimaryKeyConstraint(*fields))
            else:
                tables[name].append_constraint(
                    ForeignKeyConstraint(fields, [tables[target].c[f] for f in remote])
                )
    return metadata
