# Changelog

Record user-visible changes under **Unreleased** as they land. When tagging a
release, move those entries under its version and date and start a fresh
Unreleased section. Dates refer to releases of this repository.

## [Unreleased]

### Security and data integrity

- Dispatch post-commit webhooks only for the originating definition. Two sheets
  connected to identically named tables can now have independent recipients.
- Apply the same single-query validation to reports, AI query previews and
  lookup lists. Use database read-only transactions on PostgreSQL, MySQL and
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
  when their target or credentials change.
- Preserve rows with empty lookups and use every component of a composite
  foreign key when joining a related table.
- Quote schema identifiers using the target dialect, validate CSV headers and
  record lengths, preserve leading zeroes and roll back a failed SQLite table
  import including creation of the table.
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

[Unreleased]: https://github.com/stefanofante/visualdb/compare/v1.1.0.0...master
[1.1.0.0]: https://github.com/stefanofante/visualdb/compare/v1.0.0.0...v1.1.0.0
[1.0.0.0]: https://github.com/stefanofante/visualdb/tree/v1.0.0.0
