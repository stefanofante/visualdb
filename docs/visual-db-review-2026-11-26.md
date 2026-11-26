# Visual DB review for the next DBVisual release

Reviewed on 26 November 2026 against DBVisual v1.1.0.0 and the changes in
Unreleased. Visual DB is the separate product at visualdb.com.

## What changed since our August release

The publisher's x64 and ARM64 container repositories both list v556 on
17 November, v557 on 18 November, v558 on 21 November, v560 on 23 November and
v561 on 24 November (UTC update dates). On both architectures the latest tag
pointed to v561 at review time. The self-hosting guide and official blog do
not identify the individual features introduced in each image. In particular,
the publisher described its record conflict workflow in December 2024.
A new image date alone cannot date a product feature.

[Windows/Linux x64 registry history](https://hub.docker.com/v2/repositories/visualdb/visualdb-x64/tags?page_size=20) ·
[ARM64 registry history](https://hub.docker.com/v2/repositories/visualdb/visualdb-arm64/tags?page_size=20) ·
[Self-hosting guide](https://visualdb.com/docs/self-hosting.html) ·
[Publisher's articles](https://visualdb.com/blog/) ·
[Data integrity article, December 2024](https://blog.visualdb.com/2024/12/23/how-visual-db-protects-data-integrity/)

## Candidates for our next release

| Priority | Visual DB capability | What DBVisual already does | Proposed next increment and acceptance |
| --- | --- | --- | --- |
| 1 | Review inserted, changed and deleted records before saving. Resolve conflicting values side by side. | Sheets queue a batch. Forms and sheets detect stale writes. The audit now keeps the draft on screen after a conflict. | Build the preview from the grid originals and pending values. For a conflict, read the current record by its complete key and show original, local and database values. Retry against the version displayed. A second concurrent change must be detected again. An unrelated pending row and its attachments must survive. |
| 2 | Ask for query parameters before loading records. | Reports accept parameters. The common compiler supports filters and bound values. Form and sheet loaders currently pass an empty parameter map and materialize the result. | Reuse the report parameter definitions in forms and sheets. Defer the query until required inputs are set, and bind the filter at the database. Add deterministic paging by complete key. Verify with a large table that initial load and changing pages fetch only the records needed. Define the scope of totals and exports explicitly. |
| 3 | Put related fields on one form row and adjust their widths. | The form definition already persists ordered field configurations. The editor renders them in one vertical column. | Add optional row and width settings with the current layout as the default. Verify reopening old definitions, resizing a narrow window, keyboard order and conditional visibility. A first release can use a grid editor with explicit widths. |

[Sheets and conflict handling](https://visualdb.com/docs/sheets.html) ·
[Query parameters](https://visualdb.com/docs/queries.html) ·
[Form layout](https://visualdb.com/docs/forms.html)

Visual DB also documents a remotely accessible REST API. That would change the
local application's access model and requires a separate decision on identity,
authorisation and deployment. Paradox interoperability remains a separate
database-adapter decision. The releases inspected provide no evidence that
would change the effort estimate for that adapter.

[Visual DB REST API](https://visualdb.com/docs/rest-api.html)
