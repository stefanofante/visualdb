# Packaging dbvisual

dbvisual ships as a single local application. This guide covers producing a
standalone, self-contained build with **nicegui-pack** (a thin wrapper over
PyInstaller) and the manual acceptance checklist to run before shipping a build.

## Prerequisites

- A clean virtual environment with the app and its runtime drivers installed:

  ```powershell
  python -m venv .venv
  .\.venv\Scripts\python.exe -m pip install -e ".[all-drivers]"
  .\.venv\Scripts\python.exe -m pip install nicegui[pack]
  ```

- Optional AI providers use plain HTTP (`requests`/`httpx` as configured) and no
  extra native dependencies.

## Build command

`main.py` is the entrypoint (native desktop window by default). Build with:

```powershell
nicegui-pack --onefile --name dbvisual main.py `
  --add-data "dbvisual;dbvisual"
```

Because some dependencies are imported dynamically (SQLAlchemy dialects, the AI
provider modules, keyring backends), pass them explicitly as hidden imports:

```powershell
nicegui-pack --onefile --name dbvisual main.py `
  --hidden-import psycopg `
  --hidden-import pymysql `
  --hidden-import pyodbc `
  --hidden-import oracledb `
  --hidden-import duckdb `
  --hidden-import duckdb_engine `
  --hidden-import keyring.backends.Windows `
  --hidden-import keyring.backends.macOS `
  --hidden-import keyring.backends.SecretService `
  --hidden-import cryptography `
  --hidden-import openpyxl `
  --hidden-import dbvisual.app.ai.provider `
  --hidden-import dbvisual.app.ai.settings `
  --hidden-import dbvisual.app.ai.ui
```

Notes:

- Include only the DB drivers you intend to ship; each adds size.
- **SQLCipher** (`pysqlcipher3` / `sqlcipher3`) is optional and often has no
  prebuilt wheel. If it is absent, encrypted-SQLite connections degrade
  gracefully: `encryption_supported("sqlcipher")` returns `False` and attempting
  such a connection raises a clear error instead of crashing. DuckDB native
  encryption is unaffected.
- User data (metadata DB, attachments, the secrets vault and snapshots) is
  resolved via `platformdirs`, **not** the PyInstaller bundle dir (`sys._MEIPASS`).
  This keeps writes in a stable, writable per-user location across runs. The
  `tests/test_packaging_smoke.py` suite guards this property.

## User data locations

Everything the app persists lives under the platform user-data directory
(shown in Settings): the metadata SQLite DB, uploaded attachments, the encrypted
secrets vault fallback, and the `snapshots/` folder. The bundle itself stays
read-only.

## Manual acceptance checklist

Run the produced executable and confirm each item:

1. **Launch** — the desktop window opens (or `--mode web` serves on
   `127.0.0.1:8080`) with no console errors.
2. **Connections** — create a connection, run *Test*, *Save*, and *Browse schema*
   against a real database.
3. **Sheet** — open a sheet, edit cells, add/delete a row, save; verify optimistic
   locking (a stale edit is rejected) and attachments upload/download.
4. **Form** — navigate records, edit and save, delete a record (attachments
   cascade), confirm validation and form rules fire.
5. **Report** — load data, apply **grouping with subtotals**, sort groups by
   caption and by subtotal, and confirm the full-text search stays consistent.
6. **Saved views** — save a private and a shared view, reload them, and confirm a
   locked view cannot be modified.
7. **Snapshots** — export an HTML snapshot (opens standalone, shows subtotals) and
   an Excel snapshot (detail rows + subtotal rows) into the snapshots folder.
8. **Security & data dir** — confirm secrets are never written in clear text, the
   user-data directory shown in Settings is writable and persists across restarts,
   and (if built without SQLCipher) encrypted-SQLite fails with a clear message
   while everything else keeps working.
