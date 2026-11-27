# Changelog

Before creating a tag, give its changes their published version and release date.
Use that entry as the GitHub release notes. Published changelogs contain versioned entries only.

## [1.2.1.0] – 2026-11-27

- Create an empty SQLite or DuckDB database from Connections. Choose a name and
  folder; the new file is registered as a connection and existing files are protected.
- Open Help over the current page and return to the same draft. The guide uses
  the app's blue header, a persistent Back to app button, a compact topic index
  on narrow screens and step-by-step instructions for opening databases and importing CSV.
- Keep inputs within the available width and reduce page headings and padding
  in small windows. Desktop builds check the guide layout and navigation in Chromium
  on Windows and WebKit on macOS.
- Fix the success notification after importing a CSV or changing a database schema.
- Remove the unused sample file `test.duckdb` from the source tree.

## [1.2.0.0] – 2026-11-26

### Added

- Added native build scripts for a per-user Windows x64 installer and a macOS
  Apple Silicon disk image. Both include the Python runtime. The Windows installer
  includes the offline WebView2 runtime.
- Read the version shown in About from the package metadata.
- Preview pending inserts, updates and deletes in sheets and forms. Resolve a
  concurrent edit against the original, local and current value of each field.
  Retrying checks the displayed database version again and keeps unrelated edits.
- Configure typed, optional or required query filters on saved forms and sheets.
  Fetch a bounded page ordered by the complete primary key. The page selector
  identifies the scope of grid search, totals and export.
- Arrange form fields on shared rows with widths from one to twelve columns.
  Narrow windows stack the fields in reading order. Existing forms retain their layout.
  The navigation drawer now opens on demand in a narrow desktop window.
- Added the local REST API for exporting and managing application definitions.
  Tokens are scoped to one application. Updates and deletes require an ETag.
  See the REST API reference in the repository.
- Versioned release commits publish both native installers after their builds and
  tests succeed. The release notes come from the dated changelog for that commit.
- Run `python scripts/download_installers.py` from a source checkout to download
  both release packages into its `installers` directory.

### Security and data integrity

- Dispatch post-commit webhooks only for the originating definition. Two sheets
  connected to identically named tables can now have independent recipients.
- Apply the same single-query validation to reports, AI query previews and
  lookup lists. Use database read-only transactions on PostgreSQL, MySQL, DuckDB and
  Oracle and restore SQLite's read-only setting before returning a connection.
- Limit the local web UI to loopback. Require a local identity when opening an
  RLS-enabled PostgreSQL sheet or form. Pass the identity as a bound value.
- Validate attachment IDs and stage edits until save. Cancelling or rolling
  back a database write preserves the existing files. New uploads use the
  inserted record's primary key. Older uploads saved under a placeholder
  remain readable by their recorded ID.
- Require the complete primary key for record writes. Detect stale deletes,
  constrain detail writes to their parent and preserve unsaved edits when an
  optimistic concurrency check fails.
- Enforce metadata foreign keys, protect locked views and prevent a deleted
  connection's stored credentials from being inherited by a newly created one.
  Concurrent settings and encrypted-vault writes now preserve unrelated keys.

### Fixed

- Reflect DuckDB tables and ordered keys using its native catalog. Detect
  stale DuckDB writes from the rows actually affected. Reopen saved encrypted
  database connections with their stored key and refresh cached connections
  when their target or credentials change. The DuckDB extra requires 1.5.3 or
  newer for the tested reflection, CRUD and encrypted-file paths.
- Accept manually assigned record keys on insert and keep saved keys immutable.
  Save date and time inputs using the reflected database type and preserve
  generated DuckDB keys and defaults.
- Preserve rows with empty lookups and use every component of a composite
  foreign key when joining a related table.
- Quote schema identifiers using the target dialect, validate CSV headers and
  record lengths, preserve leading zeroes and roll back a failed SQLite table
  import including creation of the table.
- Paste labelled spreadsheet columns by name, preserving quoted tabs and newlines
  and keeping generated keys and lookup columns out of the insert.
- Preserve text as literal text in Excel snapshots and keep successive exports
  with the same title. Fix NULL counts and formula short-circuit evaluation.
- Honour the saved launch mode from both entry points and send Gemini API
  credentials in the request header.

## [1.1.0.0] – 2026-08-24

- Added navigable in-app help with page-by-page instructions and database setup.
- Added the About page with project, author, credits and licence information.

## [1.0.0.0] – 2026-08-24

- First tagged release of the local Python application. Included the query
  builder, editable sheets, forms, master-detail editing, reports, schema tools,
  saved views, snapshots, webhooks and optional AI assistance.

[1.2.1.0]: https://github.com/stefanofante/visualdb/compare/v1.2.0.0...v1.2.1.0
[1.2.0.0]: https://github.com/stefanofante/visualdb/compare/v1.1.0.0...v1.2.0.0
[1.1.0.0]: https://github.com/stefanofante/visualdb/compare/v1.0.0.0...v1.1.0.0
[1.0.0.0]: https://github.com/stefanofante/visualdb/tree/v1.0.0.0
