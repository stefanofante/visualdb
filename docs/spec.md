# DB Visual Builder - Specification

A **local** Python application to build *data-entry forms, sheets (grids) and reports*
over existing databases, in the spirit of Visual DB, but **self-contained**: it installs and
runs on the user's machine. No cloud, no remote account, no multi-tenancy.

---

## 1. Goals

- Software installable and **run locally** on a single machine (Windows / Linux / macOS).
- **BYOD (Bring Your Own Database)**: connects to the user's *existing* databases.
- Covers the three pillars of Visual DB: **Form**, **Sheet**, **Report**.
- **Open, multi-DB architecture**: PostgreSQL, MySQL/MariaDB, SQL Server, Oracle, SQLite, DuckDB.
- Central concept: everything is generated from a **query-spec** (JSON). Form/Sheet/Report are
  just different *renders* of the same spec.
- **Modern layout**: clean interface, **Excel-like** grids, **embedded charts**, and
  copy/paste of tables, charts and queries (see section 6).

## 2. Non-goals (explicit)

- Cloud / SaaS product.
- Multi-tenant, billing, remote accounts.
- Cloud sync or cloud storage of user data.
- Replacing the DB administration tool.

> Note: the *target databases* may be remote (e.g. a Postgres on another server), but **the
> application** and its metadata always stay local.

## 3. Conceptual model

There are no distinct "form" and "report" data entities. There is a **query-spec**:

- `main_table` - the main table (the only one updatable in form/sheet)
- `related[]` - related tables via foreign key (read-only)
- `columns[]` - selected columns with aliases
- `filters[]` - parametrized conditions
- `params[]` - parameters (with multi-value and cascade support)

A **single compiler** turns the query-spec into `sqlalchemy.select()`. Everything else is UI.

## 4. Architecture & modules

**Monolithic application**: a single Python codebase, a single process, a single executable.
No frontend/backend separation, no JS build, no HTTP API to maintain. The UI is written in
**NiceGUI** (pure Python) and the same code runs both as a **native desktop window**
(`ui.run(native=True)`) and as a local **web app** (`ui.run()`, bound to `127.0.0.1`).

```
dbvisual/
  core/                # DB-agnostic layer (Phase 1)
    connections.py     # creates a SQLAlchemy Engine per dialect; pool; connection test
    introspect.py      # reflection of tables/columns/types; FK detection
    queryspec.py       # Pydantic query-spec models (JSON serializable)
    compiler.py        # query-spec -> sqlalchemy.select()   [CORE of the system]
    crud.py            # generic insert/update/delete; transactions (master-detail)
  meta/                # local persistence (Phase 2)
    store.py           # local persistence (SQLite) of connections + definitions
    models.py          # metadata store schema (SQLAlchemy Core)
    secrets.py         # DB credential encryption (keyring or Fernet)
  app/                 # monolithic NiceGUI UI (Phase 2+)
    shell.py           # layout: header + side navigation
    main.py            # app assembly + ui.run (desktop/web)
    pages/             # one page per section (connections, applications, ...)
    components/        # reusable widgets
    cli.py             # `dbvisual` command: starts the app
main.py                # entrypoint (--mode desktop | web)
```

## 5. Technical stack (decided)

- **Python** >= 3.11
- **DB abstraction**: SQLAlchemy Core **2.0** (not the ORM) - introspection via `inspect()` /
  `MetaData.reflect()`. This is the layer that makes everything DB-agnostic.
- **UI = NiceGUI** (pure Python): monolithic application, no separate frontend/backend, no JS
  build. The same code runs **native desktop** (`ui.run(native=True)`, via pywebview) or local
  **web** (`ui.run()`, bound exclusively to `127.0.0.1`).
  - **Excel-like grid**: `ui.aggrid` (AG Grid) - inline editing, sorting, filtering, range
    selection.
  - **Embedded charts**: `ui.echart` (Apache ECharts, Apache-2.0): columns/bars, pie/donut,
    treemap, scatter/bubble, line, choropleth, time-series with a sliding window. Export as
    PNG/SVG.
  - **Layout/UI**: NiceGUI components with Tailwind classes for clean, responsive interfaces.
- **Validation**: Pydantic v2 (also for the query-spec).
- **Metadata store**: local SQLite, file in the user directory
  (`~/.dbvisual/metadata.db` or the `platformdirs` equivalent).
- **DB credentials**: `keyring` (OS keychain) with a `cryptography.Fernet` encrypted-file fallback.
- **Packaging**: portable executable with **`nicegui-pack`** (based on PyInstaller); also
  installable via `pip install .` + the `dbvisual` command.

### DB drivers (SQLAlchemy URL)

| DB | Driver | URL |
|---|---|---|
| PostgreSQL | `psycopg` (v3) | `postgresql+psycopg://` |
| MySQL/MariaDB | `PyMySQL` | `mysql+pymysql://` |
| SQL Server | `pyodbc` | `mssql+pyodbc://` |
| Oracle | `oracledb` | `oracle+oracledb://` |
| SQLite | built-in | `sqlite:///path` |
| DuckDB | `duckdb_engine` | `duckdb:///path` , `duckdb:///:memory:` |

## 6. UI/UX requirements

Modern layout, designed for daily use by non-technical users.

**Excel-like grids (Sheet)** - `ui.aggrid`
- Inline cell editing with on-the-fly validation.
- Range selection, keyboard navigation, fill-handle where possible.
- Grouping, sorting, filtering and as-you-type full-text search.
- Conditional styling (color the cell based on the value).
- Batch save of changes in a transaction.

**Embedded charts (Report)** - `ui.echart`
- Charts embedded directly in the report page (not separate windows).
- Types: column/bar, pie/donut, treemap, scatter/bubble, line, choropleth, time-series.
- Interaction: filter, pivot, zoom; time-series with a sliding time window.

**Copy / paste (interoperability)**
- **Tables**: copy a grid selection to Excel/spreadsheet (TSV format) and paste tabular data
  from Excel into the grid.
- **Charts**: copy/export the chart as an image (PNG/SVG).
- **Query**: copy/export the query (generated SQL) and re-import a query-spec.

**General layout**
- Clean, responsive interface; navigation across Connections, Applications, Form, Sheet, Report.
- Visual query-spec editor (query builder) with automatic joins from FKs.

## 7. Security (local context)

- In web mode, exclusive bind on `127.0.0.1`; no port exposed externally.
- DB credentials **never in clear text** on disk: use the system keychain (fallback to a file
  encrypted with `cryptography.Fernet`).
- **Generic secrets** (passwords, encrypted-file passphrases, LLM API keys) via the same
  `meta/secrets` (`set_secret`/`get_secret`), never in clear text in the metadata store or logs.
- **Encrypted local file databases** (optional): SQLite via **SQLCipher** (`PRAGMA key`; requires
  the `pysqlcipher3`/`sqlcipher3` driver, otherwise the option is disabled with a message) and
  **DuckDB** via native encryption (`ATTACH ... (ENCRYPTION_KEY ...)`, DuckDB >= 1.4; verified on
  1.5.x). The passphrase is a secret in `meta/secrets`.
- **AI assistant** (optional, off by default): generated SQL passes through `ensure_readonly`
  (only `SELECT`/`WITH`) and is shown for review before execution; API key stored as a secret.
- All queries parametrized with bind-params (no string concatenation -> no SQL injection).

## 8. Features by phase

- **Phase 1 - Core** *(DONE, 16 green tests)*: connections, introspect, queryspec, compiler, crud.
- **Phase 2 - Shell + Connections + Schema** *(DONE, 28 green tests)*: NiceGUI shell, metadata
  store, credential encryption, connection management and schema browser.
- **Phase 3 - Sheet** *(DONE, 51 green tests)*: editable Excel-like `ui.aggrid` grid from a saved
  sheet (definition `kind='sheet'`); editing only on `main_table`, related columns read-only,
  transactional batch save, TSV copy/paste and CSV export. Enhancements: optimistic locking,
  cell validation and computed/total columns; query builder with validated "many -> one" joins
  (see section 10).
- **Phase 4 - Form** *(DONE, 64 green tests)*: single record with prev/next navigation, input
  types and *available values* (label != value), defaults, per-field validation, cross-field
  *submit rules*, conditional *form rules* and **attachment fields** (see section 10).
- **Phase 5 - Report** *(DONE, 78 green tests)*: tabular + embedded `ui.echart` charts
  (group/sort/filter, image export); multi-value and cascading parameters, nested AND/OR filters,
  summary/pivot chart and time-series with zoom; read-only custom SQL queries (see section 10).
- **Phase 6 - Master-detail** *(DONE, 88 green tests)*: master (form) + detail (grid) linked by
  the master PK, atomic commit; covers one-to-many and many-to-many (see section 10).
- **Phase 7 - Automation / Webhooks** *(DONE, 96 green tests)*: on create/update/delete, sends an
  HTTP POST (JSON) webhook to configured URLs (Zapier/Slack/Discord/custom endpoint); optional
  dispatch from the core, non-blocking send; config per sheet/form in the metadata store;
  placeholders `{{field}}` / `:formatted` / `:bare`; URLs treated as secrets (see section 10).
- **Phase 8 - Row-Level Security (PostgreSQL)** *(DONE, 103 green tests)*: RLS delegated to
  Postgres (the user's SQL policies); dbvisual passes the identity via
  `SET app.current_user_email`; local identity, RLS flag on form/sheet (Postgres only) via
  `session_settings` (see section 10).
- **Phase 9 - Schema management / Database tab (DDL)** *(DONE, 143 green tests)*: **write**
  operations on the schema (create/drop tables, add/remove columns, FK, diagram, CSV
  import/export, AI-generated DDL) with review and **manual** execution, never automatic (see
  section 10).
- **Settings** *(DONE)*: `/settings` page as the **single source** of configuration - AI
  (provider/model/API key via `meta/secrets`), RLS identity (`app/identity`) and general options;
  it orchestrates the existing modules without duplicating them.
- **Post-phase enhancements** *(DONE, 177 green tests + 5 gated skips)*: sheet attachment column,
  report **grouping with multi-level subtotals**, **saved views** (private/shared/locked),
  point-in-time **snapshots** (self-contained HTML + Excel), **gated multi-dialect integration
  tests**, and **packaging** with `nicegui-pack` (see section 10).

## 9. Non-functional requirements

- No dependency on external services to work.
- Must start with a single command, as a native desktop window or a local web app.
- Typed code (type hints), testable in isolation (in-memory SQLite for the core tests).

## 10. Functional details by phase

### Query builder (shared - Phases 3/4/5)

**Join direction: "many -> one"**
- The **main table** always sits on the **"many"** side; related tables are added **only** by
  following FKs toward the **"one"** side. A related table is allowed **only if** it is on the
  "one" side of a relation with a table **already present** in the query.
- Guarantees **a single row per main record** (no duplicates; correct `count` and aggregations).
- The query builder **validates** the direction using `core.introspect.detect_foreign_keys` and
  **blocks** adding a related table that would sit on the "many" side.
- Only the **main table is updatable**; related tables are **read-only**.

**PostgreSQL troubleshooting - "table has no primary keys"**
- To detect PK and constraints, the connection user must have the **`REFERENCES`** privilege
  (besides `SELECT`). Example:
  `GRANT SELECT, REFERENCES ON ALL TABLES IN SCHEMA <schema> TO <user>;`
- The **"table has no primary keys"** message is typically a **permissions** problem, not a
  schema problem: check the grant above.

### Phase 3 - Sheet: enhancements

**Optimistic locking (concurrency)**
- On save, changes made by others in the meantime must not be overwritten: a record update must
  **fail signaling a conflict** if the record changed after it was loaded.
- BYOD schema: a version column cannot be assumed. Default strategy:
  `UPDATE ... WHERE PK = :pk AND <changed_columns> = <original_values>`. If the update affects
  **0 rows** -> **conflict**: the user reloads the record and retries.
- If the schema exposes a version / `updated_at` column, use it as the guard instead of comparing
  the original values.
- **Core impact** (backward compatible with the existing API): `crud.update_record` takes an
  **optional** parameter (guard conditions / expected values) to add the `WHERE` clauses above;
  without the parameter the behavior is unchanged.

**Cell-level validation**
- Configurable per-column rules: required, numeric min/max, email, phone, regex, length.
- Invalid cells are marked visually (red border/underline) with a message.
- **Save is blocked** until all errors are fixed.

**Computed columns and totals**
- Excel-style **formula** columns: an expression referencing other columns of the same row,
  recomputed on the fly when dependencies change.
- **Column totals** (sum/avg/count) in a **fixed row**, updated instantly on each change and
  consistent with the active search/filter.
- **Limited and safe** formula engine (no arbitrary `eval`).
- Computed columns are **display-only** if not mapped to a real column.

### Phase 3 - Sheet: backlog (documented, NOT in this phase)
- **Private / shared / locked** views (per-user vs global sort/filter/group).
- **Snapshots** point-in-time exportable as self-contained HTML or Excel.

> **Row-level security** is now tracked separately as **Phase 8** (see below).

### Phase 4 - Form

**Record navigation**
- A form shows the records of a query **one at a time** (navigate **prev/next**).
- Main table **updatable**, lookup columns **read-only**.
- **Query parameter** to select which record to load.

**Input types by data type**
- **Text**: single-line, multiline, formatted, radio.
- **Number**: numeric textbox.
- **Date**: date picker.
- **Boolean**: checkbox / radio.
- **Dropdown**: when the column has *available values*.

**Available values (allowed values)**
- Sources: **existing** column values, from a **table**, from a **query**, **manual list**.
- **LABEL != VALUE** support: the dropdown shows a readable label (e.g. an employee name) but
  **saves the ID** in the DB.
- **"allow new values"** option (the user may enter a value not in the list).

**Default value**
- Per-field default value, applied if the user leaves it empty.

**Per-field validation** (reuses the Sheet validation engine, Phase 3)
- required, numeric min/max, min/max length, allowed/forbidden characters, regex, email, phone,
  zip, URL, credit card, and **date** constraints (not before/after, today or after, date of
  birth, etc.).

**Submit rules (cross-field validation)**
- Rules at the **whole-form** level (e.g. "at least one of two fields filled"), **distinct** from
  single-field validation. They block the **submit** if not satisfied.

**Form rules (conditional logic)**
- Enable / disable / hide fields based on the value of other fields.

### Phase 4 - Attachment fields (architectural decision)

> Introduced in **Forms** (Phase 4) and **back-applied to Sheets** (Phase 3).

- The **file does not go into the database**. Only a **TEXT** field is stored in the DB with the
  attachment **metadata** (`id`, `filename`, `content_type`, `size`) as **JSON**.
- The file **content** lives on **local disk** (local app, no cloud), in a dedicated app
  **attachments folder** (via `platformdirs`), organized per **application/record**.
- Operations: **upload, download, delete**.
- On **record deletion**, the related attachment files are removed (**cascade**).
- An **existing text field** can be **marked as "attachment"**.

### Phase 5 - Report: details

**Query parameters**
- **Multi-value** (e.g. several states at once) and **cascading** (the choice in one dropdown
  determines the values available in the next).
- **Prompting UI**: a parameters panel shown before/with the report; each parameter has its own
  input (e.g. a multi-select); cascading parameters update when the parent parameter changes.

**Composite filters**
- **Nested AND/OR** conditions, shown in **hierarchical** form (tree/groups) to avoid
  interpretation ambiguity.

**Charts**
- **Summary / pivot chart**: charts that **aggregate** the data and plot the aggregates (e.g.
  sales by Product on the category axis and Region on the series), distinct from "raw" per-row
  charts.
- **Time-series** with **zoom** and a sliding time window (confirmed, already planned in section 6).

### Phase 6 - Master-detail (mechanism)

- **Two queries**: one for the **MASTER** (a normal form) and one for the **DETAIL** (grid).
- The **detail** query has **exactly one parameter**, set to the **master PK**: it loads **only**
  the details of the current master.
- On details: **insert / update / delete**.
- **Commit** of master + details in **ONE atomic transaction** (via `crud.save_master_detail`).
- Covers **one-to-many** (FK on the "many" side) and **many-to-many** (a **junction** table with
  two FKs; workable from both perspectives).

### Phase 7 - Automation / Webhooks

**Purpose**
- When a record is **created / updated / deleted**, send an **HTTP POST webhook** (JSON) to a
  configured URL (Zapier, Slack, Discord, or a custom endpoint).
- **Local context**: webhooks originate from the machine running dbvisual, which must have
  **outbound** network access to the target services. **No inbound server**: outbound POST only.

**Event hook**
- Events are generated by the **`core.crud`** layer (insert/update/delete). A **dispatch**
  mechanism with **optional registrable** hooks/callbacks, without breaking existing core
  API/tests.
- HTTP sending is **non-blocking** and must not fail the save if the webhook fails (error logged,
  **optional retry**).

**Configuration (per sheet or form)**
- Name, URL, one or more events (`created` / `updated` / `deleted`), body format.
- Persisted in the **metadata store**, bound to the definition. **"Test"** button.

**JSON body with placeholders** (handlebars over the query fields), three "flavors":
- `{{field}}` -> a **valid JSON** value (numbers, booleans, quoted strings).
- `{{field:formatted}}` -> a readable **formatted string**, always quoted (fallback = raw).
- `{{field:bare}}` -> **raw text without quotes** (for insertion inside strings, e.g.
  Slack/Discord).
- **Default** body (auto-includes all query fields, adapts if they change) + **custom** body.
  Custom examples for Slack (`{"text": "..."}`) and Discord (`{"content": "..."}`) using `:bare`
  to stay valid JSON.

**Security**
- Webhook URLs may contain tokens: treat them as **secrets** (do not log them in clear text,
  consider encrypted storage like the passwords).

### Phase 8 - Row-Level Security (PostgreSQL)

**Model**
- RLS is **not implemented by the application**: it is **delegated to PostgreSQL**. The user
  creates the policies in SQL (`CREATE POLICY ... USING / WITH CHECK`) and enables RLS on the
  table (`ALTER TABLE ... ENABLE ROW LEVEL SECURITY`). dbvisual only **passes the identity** of
  the current user to the database.
- Available **for PostgreSQL only**. Other databases are not supported for RLS.

**Mechanism**
- Postgres filters the rows based on `current_setting('app.current_user_email')`.
- dbvisual, on each session/connection, runs `SET app.current_user_email = <email>`.

**Prerequisites**
- **User identity**: the app is local **single-user, without login**. RLS requires an identity
  (email) to pass to the DB, declared by the user and persisted locally (`app/identity.py`, via
  `platformdirs`). Until there is an identity, RLS stays **inactive** (no `SET`).
- **Connection**: must use a Postgres role that is **NOT superuser** and **NOT the table owner**
  (superuser/owner **bypass** RLS). A security requirement, flagged in the UI.

**Implementation (additive, does not break existing API/tests)**
- `core/connections.py`: an **optional** `session_settings` parameter (key->value map) that, on
  each connection open, runs the corresponding `SET` (`timezone`, `search_path`,
  `statement_timeout`, and `app.current_user_email`). Default: none; no-op on non-SET dialects.
- `app/identity.py`: the **current identity** (email) persisted locally, settable from the UI
  (Connections page). Empty = RLS inactive.
- `app/rls.py`: `rls_session_settings(connection, rls_enabled, identity)` returns
  `{app.current_user_email: <email>}` **only** if the flag is enabled, the connection is Postgres
  and the identity is present; otherwise `{}` (flag ignored on other dialects).
- **RLS** flag per definition (`SheetSpec.rls` / `FormSpec.rls`, default `False`): a checkbox in
  the design panel, visible only for Postgres connections. On open, the engine is built with the
  RLS `session_settings`.

### AI assistant (NL -> SQL) - Report only

> **Optional feature, disabled by default**. LLM provider of choice (Claude / OpenAI / Gemini /
> DeepSeek) via the **user's API key** (treated as a secret in `meta/secrets`, never in clear text).

- **Current scope**: the assistant generates **READ-ONLY SQL (SELECT)** for **Reports**, from a
  natural-language description + the reflected schema (table/column names).
- The generated SQL is **always shown to the user for review** before execution and passes
  through `ensure_readonly` (Phase 5): **no automatic execution** of write statements.
- It **does NOT generate DDL** or modify the schema in this scope (for schema management see
  Phase 9).
- **Transparency / privacy** (mandatory in the UI): enabling the AI sends the DB structure
  (table/column names) and the request text to the chosen **cloud provider**, at a per-token cost
  borne by the user. Off by default; explicit opt-in.
- **Integration**: a "Generate with AI" button **only** in the **Reports** query builder (where
  custom queries are allowed), not in the form/sheet builders (which stay structured query
  builders).

### Phase 9 - Schema management / Database tab (DDL)

- **Purpose**: create and manage the DB schema without external tools (like Visual DB's "Database
  tab"). Until now dbvisual did read-only **introspection**; this phase introduces schema
  **write** operations.
- **Functions**: create/drop tables, add/remove columns, define relations (FK), view a table's
  data, relationship diagram, CSV import/export.
- **AI assistant for the schema** (reuses the LLM provider): generates **DDL** from a
  natural-language description (e.g. "a table to track employee training with completion dates and
  certification status") -> `CREATE TABLE` with columns, types and relations.
- **Security (mandatory)**: composed/generated DDL is **never executed automatically**; it is
  always **shown for review** and requires **explicit confirmation**. Destructive operations
  (`DROP`, data-losing `ALTER`) require **double confirmation** and a warning. DDL is a **separate**
  path from read-only queries: it does **not** pass through `ensure_readonly` (which stays for
  SELECTs).
- **Dialect**: DDL is dialect-dependent (Postgres / MySQL / SQL Server / Oracle / SQLite /
  DuckDB): use SQLAlchemy where possible or per-dialect generation; document the limits.
- **Permission prerequisite**: the connection user must have **DDL** privileges on the database.

**Implementation**
- `core/schema_ddl.py`: `compose_*` (create/drop table, add/drop column, add/drop FK, rename)
  returns the **SQL text**; `execute_ddl` runs it in a transaction = two distinct steps. Logical
  type mapping -> per-dialect SQLAlchemy types; `DDLNotSupported`/`DDLPermissionError`.
  **Known limit**: SQLite does not support ADD/DROP FK via `ALTER` (use inline FKs in create).
- `app/pages/schema.py`: browser + editor with a **"Review and execute"** dialog (SQL shown,
  **double confirmation** for destructive operations), CSV import/export, FK diagram (`ui.mermaid`).
- `app/schema_service.py`: CSV helpers (infer columns, `csv_create_table_ddl`, `table_to_csv`)
  and `generate_ddl_via_ai` (reuses the LLM provider with a DDL system prompt; always for review).

### Settings (`/settings` page)

- **Single source** of app configuration; orchestrates the existing modules without duplicating
  them.
- **AI**: `app/ai/settings` + `meta/secrets`. Enable/disable (off by default), provider, model,
  **API key** saved **only** as a secret (`ai:<provider>`); shown as *set/not set* (never the
  value), with replace/delete and **Test** (mockable).
- **Identity / RLS**: `app/identity` - `app.current_user_email` email (empty = RLS inactive).
- **General**: preferred startup mode (`app/app_settings`) and the **user data directory**
  (`platformdirs`) shown read-only for transparency (metadata store, attachments, secrets vault).
- The contextual AI dialogs (`app/ai/ui.py`) read/write the **same** config and the same secrets
  as the Settings page.

### Report grouping with subtotals

- `report_service.group_with_subtotals(rows, group_by, value_aggs, sort_by, descending)` builds a
  multi-level group tree over already filtered rows (so it stays consistent with
  `full_text_filter`/`filter_rows`); per-group subtotals use sum/avg/count/min/max.
- Groups are ordered by **caption** or by the **subtotal** of a chosen field.
- `flatten_group_rows(tree, detail_fields)` produces aggrid-ready rows tagged with `_type`
  (`group`/`detail`/`subtotal`) and `_level` for indentation; the report page renders group header,
  detail and bold subtotal rows in a community `ui.aggrid`.

### Saved views (Sheet & Report)

- New `views` table in the metadata store: `definition_id`, `name`, `scope` (`private`/`shared`),
  `locked`, `config_json`, `owner_identity`.
- **Private** views are filtered by the current identity (match / non-match / empty); **shared**
  views are visible to everyone. A **locked** view is immutable (updates are refused until it is
  unlocked). `config_json` round-trips arbitrary view config (filters, grouping, columns, search).
- A generic `components/views_ui.py` dialog captures the current config and applies a chosen one;
  the Sheet grid persists search + group-by, the Report persists search + grouping settings.

### Snapshots (point-in-time)

- `app/snapshot_service.py` freezes the current rows into portable artifacts under the
  `snapshots/` folder in the user data dir:
  - **HTML** - a single self-contained file (inline style and data, no external assets, no DB),
    reflecting exactly what is on screen including group subtotals;
  - **Excel** - an `.xlsx` workbook (openpyxl) with detail rows and, when grouping is active,
    group header and subtotal rows.

### Multi-dialect integration tests (gated)

- `tests/test_integration_dialects.py` runs an end-to-end round-trip (DDL create -> CRUD with
  optimistic locking -> introspection -> compiled SELECT -> drop) against real servers.
- Enabled only when the matching env var holds a SQLAlchemy URL, otherwise **skipped**:
  `DBVISUAL_TEST_POSTGRES_URL`, `DBVISUAL_TEST_MYSQL_URL`, `DBVISUAL_TEST_MSSQL_URL`,
  `DBVISUAL_TEST_ORACLE_URL`.

### Packaging

- `docs/packaging.md` documents the `nicegui-pack` build (entrypoint `main.py`), the required
  **hidden imports** (DB drivers, `duckdb`, `keyring`, `cryptography`, `openpyxl`, AI modules) and
  an 8-item manual acceptance checklist.
- User data resolves via `platformdirs`, **independent of** the PyInstaller bundle dir
  (`sys._MEIPASS`); SQLCipher degrades gracefully when absent. Guarded by
  `tests/test_packaging_smoke.py`.

