# dbvisual

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![UI: NiceGUI](https://img.shields.io/badge/UI-NiceGUI%203.x-0b7285.svg)](https://nicegui.io/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-c72e49.svg)](https://www.sqlalchemy.org/)
[![Tests](https://img.shields.io/badge/tests-177%20passing-brightgreen.svg)](#running-the-tests)

A **local**, self-contained application to build **forms, sheets (grids) and reports**
over existing databases, in the spirit of Visual DB. It runs entirely on the installation
machine: no cloud, no remote account, no multi-tenancy. The *target* databases may be local
or remote, but the app and its metadata always stay local.

Central concept: everything is generated from a **query-spec** (JSON). Forms, sheets and
reports are just different *renders* of the same specification.

**Monolithic application**: a single Python codebase (UI = [NiceGUI](https://nicegui.io/)),
a single process, a single executable. The same code runs as a **native desktop window** or
as a local **web app** on `127.0.0.1`. No separate frontend/backend, no JS build.

<!-- Add a screenshot to showcase the app, e.g. the Report page with grouping + subtotals:
<p align="center">
  <img src="docs/screenshot.png" alt="dbvisual report with grouping and subtotals" width="820">
</p>
-->

---

## Running the application

After installation (see below), start the app from the entrypoint:

```powershell
python main.py --mode desktop      # default: native desktop window (pywebview)
python main.py --mode web          # local web app at http://127.0.0.1:8080
```

Or via the installed command:

```powershell
dbvisual --mode desktop
dbvisual --mode web --host 127.0.0.1 --port 8080
```

> **Note on NiceGUI and native mode.** NiceGUI is pinned to `>=3,<4` in `pyproject.toml`:
> with this series `ui.echart` (charts) and `ui.aggrid` (grids) also render correctly in
> native desktop mode. If, after an upgrade, the native window shows a blank page, pin a
> known-good NiceGUI 3.x version and update this note.

---

## Installation (venv)

Requirements: **Python >= 3.11**.

```powershell
# from the project folder
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows PowerShell
# source .venv/bin/activate         # Linux / macOS

# install the core + test tools (SQLite is built-in, no external driver required)
pip install -e ".[dev]"
```

Database drivers are **optional** and installed only for the DB you need:

```powershell
pip install -e ".[postgresql]"      # or mysql / mssql / oracle / duckdb
pip install -e ".[all-drivers]"     # all drivers at once
```

### Supported dialects and drivers

| DB | Driver | SQLAlchemy URL |
| --- | --- | --- |
| PostgreSQL | `psycopg` (v3) | `postgresql+psycopg://` |
| MySQL/MariaDB | `PyMySQL` | `mysql+pymysql://` |
| SQL Server | `pyodbc` | `mssql+pyodbc://` |
| Oracle | `oracledb` | `oracle+oracledb://` |
| SQLite | built-in | `sqlite:///path` |
| DuckDB | `duckdb_engine` | `duckdb:///path` , `duckdb:///:memory:` |

---

## Architecture

Monolithic NiceGUI app. Layers:

```mermaid
flowchart TD
    UI["dbvisual/app<br/>NiceGUI UI: shell, pages, components, services"]
    META["dbvisual/meta<br/>metadata store (SQLite) - secrets (keyring/Fernet) - attachments"]
    CORE["dbvisual/core<br/>connections - introspect - queryspec - compiler - crud - schema_ddl"]
    DB[("Target databases<br/>PostgreSQL - MySQL - SQL Server - Oracle - SQLite - DuckDB")]

    UI --> META
    UI --> CORE
    CORE --> DB
```

- `dbvisual/core/` - DB-agnostic engine (SQLAlchemy Core 2.0):
  - `connections.py` - multi-dialect `Engine` creation + connection test; optional
    `session_settings` (Postgres RLS) and file `encryption_key` (SQLCipher / DuckDB).
  - `introspect.py` - schema reflection: tables, columns (type/nullable/pk), foreign keys.
  - `queryspec.py` - Pydantic v2 query-spec models (JSON serializable).
  - `compiler.py` - compiles a `QuerySpec` into a `sqlalchemy.select()` with bound parameters.
  - `crud.py` - generic insert/update/delete + transactional master-detail, optimistic
    locking, and an optional CRUD event dispatch (`events.py`) for webhooks.
  - `schema_ddl.py` - multi-dialect DDL composition and execution (Database tab).
- `dbvisual/meta/` - local persistence: metadata store (SQLite via `platformdirs`),
  encrypted secrets (`keyring` + `cryptography.Fernet` fallback), local attachment storage.
- `dbvisual/app/` - NiceGUI UI (shell, pages, components) and app services.
- `main.py` - entrypoint (`--mode desktop | web`).

Principles: bound parameters everywhere (no SQL injection); only the `main_table` of a
query-spec is writable; related (lookup) columns are read-only; secrets never in clear text
in the metadata store or logs.

---

## Features

### Connections and schema
Manage saved connections (dialect, host, port, database, user, passphrase for encrypted
files). "Test" and "Browse schema" use the core (`build_engine`, `test_connection`,
`reflect_schema`, `list_tables`, `get_columns`, `detect_foreign_keys`).

### Sheet (editable Excel-like grid)
`ui.aggrid` grid rendered from a saved sheet definition. Only `main_table` columns are
editable; related columns are read-only. Batch save in a single transaction with
**optimistic locking**; cell validation; computed (formula) columns and live totals;
TSV copy/paste and CSV export. A text column can be marked as an **attachment** column
(files on disk via the local attachment store, metadata JSON in the cell; row delete
cascades the files).

### Form (single-record data entry)
Prev/next record navigation, typed inputs, **available values** (label != value), defaults,
per-field validation, cross-field submit rules, conditional form rules, and attachment
fields. Transactional save with optimistic locking.

### Report (read-only)
Query builder or read-only custom SQL (`ensure_readonly`). Multi-value and cascading
parameters, nested AND/OR filters, summary/pivot aggregation, and **multi-level grouping with
subtotals** (sum/avg/count/min/max, groups sortable by caption or subtotal), full-text search,
and embedded `ui.echart` charts (bar, line/time-series with zoom, pie). CSV export plus
point-in-time **snapshots** (self-contained HTML and Excel, including group subtotals).

### Saved views
Sheets and reports can save named **views** (search, grouping and column config) as
`private` (visible only to the current identity), `shared` (visible to everyone), or `locked`
(immutable). Stored in the local metadata store; reload or delete them from the *Views* dialog.

### Master-detail
A master form plus one or more linked detail grids. The detail query has exactly one
parameter bound to the master PK. Master + all detail edits commit in a single transaction
(`crud.save_master_detail`); a new master PK is propagated to new detail FKs.

### Database tab (schema / DDL)
Visual schema browser and editor. Every change composes DDL and shows the exact SQL in a
"Review and execute" dialog; execution only after explicit confirmation (double confirmation
for destructive operations). CSV import/export, FK relationship diagram (`ui.mermaid`), and
optional AI-generated DDL. The DDL channel is separate from `ensure_readonly`.

### Automation / Webhooks
On create/update/delete, an optional non-blocking HTTP POST (JSON) is sent to configured
URLs (Zapier/Slack/Discord/custom). Body placeholders `{{field}}` / `{{field:formatted}}` /
`{{field:bare}}`. Webhook URLs are stored as secrets.

### Row-Level Security (PostgreSQL)
RLS is delegated to Postgres policies; dbvisual only passes the current identity via
`SET app.current_user_email`. Enabled per definition (Postgres only) with a local identity
email.

### AI assistant (optional, off by default)
Natural-language to read-only SQL for Reports via a chosen LLM provider (Claude / OpenAI /
Gemini / DeepSeek) with a user API key stored as a secret. Generated SQL is always shown for
review and validated by `ensure_readonly`; it is never executed automatically.

### Settings page (`/settings`)
Single source of truth: AI (provider/model/API key status), identity/RLS email, and general
options (preferred startup mode, user data directory shown read-only).

---

## Encrypted local file databases

Optional passphrase-encrypted local file DBs:

- **SQLite (SQLCipher)**: dialect `sqlcipher`; the key is applied with `PRAGMA key`. Requires
  a separate SQLCipher driver (`pysqlcipher3` or `sqlcipher3`); if missing, the option is
  disabled with a clear message (no crash).
- **DuckDB**: native encryption (DuckDB >= 1.4) via `ATTACH '<file>' (ENCRYPTION_KEY '<pass>')`
  applied over a single `StaticPool` connection.
- The passphrase is a **secret** (`enckey:<id>`), never in clear text in the metadata store.

> Packaging note: SQLCipher is not the standard SQLite; it must be installed separately and
> bundled with `nicegui-pack`. DuckDB encryption needs no extra driver.

---

## Running the tests

Core tests use **in-memory SQLite/DuckDB**, so they require no external database or
credentials.

```powershell
pytest
```

Server dialect integration tests (PostgreSQL, MySQL/MariaDB, SQL Server, Oracle) are
**opt-in** and run only when the matching environment variables point at a real database;
otherwise they are skipped. See "Integration tests" below.

---

## Integration tests (real servers, opt-in)

Set any of these environment variables to a SQLAlchemy URL to enable the corresponding
end-to-end test; unset variables are skipped:

```powershell
$env:DBVISUAL_TEST_POSTGRES_URL = "postgresql+psycopg://user:pass@localhost/dbname"
$env:DBVISUAL_TEST_MYSQL_URL    = "mysql+pymysql://user:pass@localhost/dbname"
$env:DBVISUAL_TEST_MSSQL_URL    = "mssql+pyodbc://user:pass@localhost/db?driver=ODBC+Driver+18+for+SQL+Server"
$env:DBVISUAL_TEST_ORACLE_URL   = "oracle+oracledb://user:pass@localhost/?service_name=XEPDB1"
pytest tests/test_integration_dialects.py
```

Each test exercises only existing APIs end-to-end: a create table via `schema_ddl`
(`compose_create_table` + `execute_ddl`), reflection (`reflect_schema` / `get_columns`), CRUD
with **optimistic locking** (`insert_record` / `update_record` / `delete_record`), a
`compile_select` read-back, and a final drop table.

---

## Packaging (standalone executable)

Build a standalone executable with `nicegui-pack` (a PyInstaller wrapper):

```powershell
nicegui-pack --onefile --name dbvisual main.py
```

See `docs/packaging.md` for the required hidden imports, bundled assets,
and a manual acceptance checklist to run on the target OS. Metadata, attachments, secrets and
snapshots always resolve via `platformdirs` (the user data directory), never inside the
PyInstaller temporary folder.

---

## Full specification

The authoritative specification lives in [docs/spec.md](docs/spec.md).

---

## License

Released under the [MIT License](LICENSE).
