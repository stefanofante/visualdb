"""Schema-tab helpers (Phase 9): CSV import/export and AI DDL generation.

UI-agnostic and testable. CSV import infers simple column types; export renders a
table to CSV text. AI DDL reuses the existing LLM provider with a DDL-oriented
system prompt — the result is always returned for human review, never executed.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from sqlalchemy import Column, Engine, MetaData, Table, select

from dbvisual.app.ai.provider import HttpClient, ddl_system_prompt, get_provider
from dbvisual.core.schema_ddl import ColumnSpec, TableSpec, compose_create_table


def rows_from_csv(text: str) -> tuple[list[str], list[list[str]]]:
    """Parse CSV ``text`` into ``(header, rows)``."""
    reader = csv.reader(io.StringIO(text))
    data = list(reader)
    if not data:
        return [], []
    header = [name or f"col{i + 1}" for i, name in enumerate(data[0])]
    if not header or len(set(header)) != len(header):
        raise ValueError("CSV column names must be unique.")
    for line, row in enumerate(data[1:], 2):
        if len(row) != len(header):
            raise ValueError(
                f"CSV row {line} has {len(row)} fields; expected {len(header)}."
            )
    return header, data[1:]


def _looks_int(values: list[str]) -> bool:
    seen = False
    for v in values:
        if v == "":
            continue
        seen = True
        try:
            n = int(v)
            if str(n) != v.strip() or not -(2**31) <= n < 2**31:
                return False
        except ValueError:
            return False
    return seen


def infer_columns(header: list[str], rows: list[list[str]]) -> list[ColumnSpec]:
    """Infer column specs from a CSV header + sample rows (integer or text)."""
    specs: list[ColumnSpec] = []
    for i, name in enumerate(header):
        column_values = [r[i] for r in rows if i < len(r)]
        ctype = "integer" if _looks_int(column_values) else "text"
        specs.append(ColumnSpec(name=name or f"col{i + 1}", type=ctype))
    return specs


def csv_create_table_ddl(dialect: Any, table: str, text: str) -> tuple[str, list[str]]:
    """Compose the CREATE TABLE DDL inferred from a CSV; return ``(sql, header)``."""
    header, rows = rows_from_csv(text)
    if not header:
        raise ValueError("CSV is empty.")
    spec = TableSpec(name=table, columns=infer_columns(header, rows))
    return compose_create_table(dialect, spec), header


def insert_csv_rows(conn, name: str, csv_text: str) -> None:
    header, rows = rows_from_csv(csv_text)
    specs = infer_columns(header, rows)
    table = Table(name, MetaData(), *(Column(h) for h in header))
    if rows:
        records = [
            {
                col.name: (int(v) if v else None) if col.type == "integer" else v
                for col, v in zip(specs, row, strict=True)
            }
            for row in rows
        ]
        conn.execute(table.insert(), records)


def table_to_csv(engine: Engine, table: Table) -> str:
    """Render every row of ``table`` to CSV text."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    with engine.connect() as conn:
        result = conn.execute(select(table))
        writer.writerow(list(result.keys()))
        writer.writerows(result.all())
    return buffer.getvalue()


def generate_ddl_via_ai(
    provider: str,
    api_key: str,
    model: str,
    prompt: str,
    schema: dict[str, list[str]],
    dialect: str,
    http: HttpClient | None = None,
) -> str:
    """Ask the LLM to propose DDL for review (never executed here)."""
    llm = get_provider(
        provider, api_key, model, http=http, system=ddl_system_prompt(dialect)
    )
    return llm.generate_sql(prompt, schema)
