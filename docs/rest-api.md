# DBVisual REST API v1

The local API exports and imports application definitions for version control,
backup and transfer between DBVisual installations. A bearer token authorizes
a local client to list, read, create, replace and delete definitions in **one**
application. These operations change the local metadata database. The API
does not execute report SQL, edit business records, or return passwords, file
contents or webhook addresses.

## Start and authorize a client

1. Start DBVisual in web mode on a known port. From source, run
   `dbvisual --mode web --port 8080`. An installed Windows copy accepts the
   same arguments through `DBVisual.exe`. On the Mac use
   `open -n -a DBVisual --args --mode web --port 8080`.
2. In **Settings → Local REST API**, choose an existing application and select
   **Issue or rotate token**. Copy the token and the numeric application ID.
   A new token revokes the previous one. **Revoke token** disables that
   application's API immediately. A fresh installation has no active tokens.
3. Use `http://127.0.0.1:8080/api/v1/apps/{app_id}` as the base URL.
   Supply the token in the HTTP `Authorization` header as `Bearer <token>`.
   Set `Content-Type: application/json` for requests with a body. Desktop mode
   selects its own port, so use a fixed web-mode port for scripts.

The token grants write access to that application's definitions. Grant it to
trusted local tools. The secret store retains its SHA-256 digest. An exported
specification includes SQL, defaults, parameters and labels authored by the
builder. Review those contents before sharing an export.

## Endpoints

All paths below are relative to the application base URL.

| Method | Path | Request | Success |
| --- | --- | --- | --- |
| GET | `/definitions` | No body | 200, JSON array of `id`, `name`, `kind`, ordered by name |
| GET | `/definitions/{id}` | No body | 200, definition and an `ETag` header |
| POST | `/definitions` | New definition | 201, saved definition, `Location` and `ETag` |
| PUT | `/definitions/{id}` | Complete replacement, with `If-Match` | 200, saved definition and its new `ETag` |
| DELETE | `/definitions/{id}` | `If-Match`, no body | 204, empty body |

A write body has three fields. `kind` is one of `form`, `sheet`, `report`,
or `master_detail`. `name` is unique within the application (1–200 characters).
`specification` is the JSON object used by that kind of editor. Typed models
are defined in `form_service.py`, `sheet_service.py`, `report_service.py` and
`master_detail_service.py`. The connection ID must identify an existing local
connection. When moving a definition to another installation, select its
connection ID on that machine. Related definitions, views, webhooks and
attachment files have independent lifecycles. Back those up separately.

For example, a new sheet referencing the local connection numbered 3 can be
created with this body:

```json
{
  "kind": "sheet",
  "name": "Customer directory",
  "specification": {
    "connection_id": 3,
    "spec": {
      "main_table": "customers",
      "columns": [
        {"table": "customers", "name": "id"},
        {"table": "customers", "name": "name"}
      ]
    }
  }
}
```

GET, POST and PUT return the representation with its assigned `id`, `app_id`,
`name`, `kind` and normalized `specification`. For imports, send just `kind`,
`name` and `specification`. Replacing a definition can rename it and update
its specification. Its kind and application remain fixed. Deleting it also
removes its dependent view and webhook metadata.

## PowerShell example

Set `DBVISUAL_API_TOKEN` in the calling process, then replace the example
application ID. The following exports a definition, changes its display name
and writes back only if the version you read is still current.

```powershell
$base = 'http://127.0.0.1:8080/api/v1/apps/42'
$auth = @{ Authorization = "Bearer $env:DBVISUAL_API_TOKEN" }
$definitions = Invoke-RestMethod -Uri "$base/definitions" -Headers $auth
$id = $definitions[0].id
$response = Invoke-WebRequest -Uri "$base/definitions/$id" -Headers $auth -UseBasicParsing
$definition = $response.Content | ConvertFrom-Json
$body = [ordered]@{ kind = $definition.kind; name = $definition.name; specification = $definition.specification }
$body | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 definition.json
$body.name = 'Customer directory (reviewed)'
$headers = $auth.Clone()
$headers['If-Match'] = [string]$response.Headers['ETag']
Invoke-RestMethod -Method Put -Uri "$base/definitions/$id" -Headers $headers -ContentType 'application/json' -Body ($body | ConvertTo-Json -Depth 100)
```

## Errors and concurrency

| Status | Meaning | Client action |
| --- | --- | --- |
| 401 | Absent, invalid, revoked or wrong application's bearer token | Check the ID and token |
| 404 | Resource absent or outside the authenticated application | List definitions again |
| 409 | Duplicate definition name or conflicting application state | Choose another name or refresh |
| 412 | Stored content changed since the supplied ETag | GET again, review the new contents, then send its ETag |
| 422 | Invalid body, kind, specification, connection ID or path parameter | Correct the request |
| 428 | PUT or DELETE omitted `If-Match` | GET the resource and pass its quoted ETag verbatim |

## Comparison with Visual DB

The third-party product exposes its own application-token API under
`/public/api/apps/{appId}`. Its resources cover users and roles, connections,
queries, forms, sheets and reports. It can reassign queries and upload a
previously exported artifact. DBVisual v1 uses local application IDs and JSON
definitions, with the query embedded in the definition and conditional writes
using HTTP ETags. The formats and authentication tokens are product-specific.

[Visual DB REST reference](https://visualdb.com/docs/rest-api.html)
