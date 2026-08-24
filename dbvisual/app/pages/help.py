"""Help page: a self-contained, navigable HTML manual served at /help.

First-time-user oriented: explains installation, DB configuration and every app
page button by button. Rendered as one HTML document with a sticky sidebar table
of contents and anchored sections, so it is fully navigable without JavaScript.
"""

from __future__ import annotations

from nicegui import ui

_STYLE = """
<style>
.hlp { font-family: system-ui, Segoe UI, Arial, sans-serif; color: #1f2937; }
.hlp-top { position: sticky; top: 0; z-index: 5; display: flex; align-items: center;
  justify-content: space-between; gap: 12px; background: #2563eb; color: #fff;
  padding: 10px 18px; }
.hlp-top a.back { color: #fff; text-decoration: none; font-weight: 600;
  border: 1px solid rgba(255,255,255,.5); padding: 4px 10px; border-radius: 6px; }
.hlp-top a.back:hover { background: rgba(255,255,255,.15); }
.hlp-body { display: flex; align-items: flex-start; gap: 0; }
.hlp-nav { flex: 0 0 280px; position: sticky; top: 52px; align-self: flex-start;
  max-height: calc(100vh - 52px); overflow: auto; background: #f8fafc;
  border-right: 1px solid #e5e7eb; padding: 16px 14px; font-size: 14px; }
.hlp-nav h4 { margin: 14px 0 6px; font-size: 12px; text-transform: uppercase;
  letter-spacing: .04em; color: #6b7280; }
.hlp-nav a { display: block; padding: 4px 8px; color: #1f2937; text-decoration: none;
  border-radius: 6px; }
.hlp-nav a:hover { background: #e5edff; color: #1d4ed8; }
.hlp-main { flex: 1; padding: 24px 34px; max-width: 980px; }
.hlp-main h1 { font-size: 26px; margin: 0 0 6px; }
.hlp-main h2 { font-size: 20px; margin: 32px 0 8px; padding-top: 8px;
  border-top: 1px solid #eef2f7; }
.hlp-main h3 { font-size: 16px; margin: 18px 0 6px; color: #111827; }
.hlp-main p, .hlp-main li { line-height: 1.55; }
.hlp-main code { background: #f3f4f6; padding: 1px 5px; border-radius: 4px;
  font-family: ui-monospace, Consolas, monospace; font-size: 13px; }
.hlp-main pre { background: #0f172a; color: #e2e8f0; padding: 12px 14px;
  border-radius: 8px; overflow: auto; }
.hlp-main pre code { background: none; color: inherit; padding: 0; }
.hlp-main table { border-collapse: collapse; width: 100%; font-size: 13px;
  margin: 8px 0; }
.hlp-main th, .hlp-main td { border: 1px solid #e5e7eb; padding: 6px 8px;
  text-align: left; vertical-align: top; }
.hlp-main th { background: #f3f4f6; }
.hlp-btn { font-weight: 600; }
.hlp-note { background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px;
  padding: 10px 12px; margin: 10px 0; font-size: 14px; }
.hlp-tip { background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 8px;
  padding: 10px 12px; margin: 10px 0; font-size: 14px; }
.hlp-main section { scroll-margin-top: 64px; }
</style>
"""

_NAV = """
<nav class="hlp-nav">
  <h4>Getting started</h4>
  <a href="#overview">Overview</a>
  <a href="#install">Installation</a>
  <a href="#run">Running the app</a>
  <a href="#firststeps">First steps</a>
  <a href="#concepts">Key concepts</a>
  <h4>Pages</h4>
  <a href="#connections">Connections</a>
  <a href="#dbconfig">Database configuration</a>
  <a href="#database">Database (schema)</a>
  <a href="#sheets">Sheets</a>
  <a href="#forms">Forms</a>
  <a href="#reports">Reports</a>
  <a href="#masterdetail">Master-detail</a>
  <a href="#applications">Applications</a>
  <a href="#settings">Settings</a>
  <a href="#about">About</a>
  <h4>Features</h4>
  <a href="#views">Saved views</a>
  <a href="#snapshots">Snapshots</a>
  <a href="#webhooks">Webhooks</a>
  <a href="#rls">Row-level security</a>
  <a href="#ai">AI assistant</a>
  <a href="#security">Security &amp; data folder</a>
  <a href="#packaging">Packaging</a>
  <a href="#faq">Troubleshooting / FAQ</a>
</nav>
"""

_CONTENT = """
<div class="hlp-main">
<h1>dbvisual - User guide</h1>
<p>dbvisual is a <strong>local</strong>, self-contained application to build
<strong>forms, sheets (grids) and reports</strong> over your existing databases.
Everything runs on this machine as a native desktop window or a local web app on
<code>127.0.0.1</code> - no cloud, no remote account. This guide explains, page by
page and button by button, how to use it. If this is your first time, read
<a href="#firststeps">First steps</a> after installing.</p>

<section id="overview">
<h2>Overview</h2>
<p>Everything is generated from a single <strong>query-spec</strong> (a JSON
specification of a main table, its columns and related tables). Forms, sheets and
reports are just different <em>renders</em> of that spec:</p>
<ul>
  <li><strong>Connection</strong> - how to reach a target database (credentials are
  stored as secrets, never in clear text).</li>
  <li><strong>Application</strong> - a logical group of definitions.</li>
  <li><strong>Definition</strong> - one saved form, sheet or report bound to a
  connection.</li>
</ul>
<p>Golden rule: writes happen <strong>only</strong> on the main table; related
(lookup) columns are read-only.</p>
</section>

<section id="install">
<h2>Installation</h2>
<p>You need Python 3.11 or later. A virtual environment is recommended.</p>
<pre><code>python -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install -e .</code></pre>
<p>Database drivers are <strong>optional extras</strong> - install only what you
need:</p>
<pre><code># one driver
.\\.venv\\Scripts\\python.exe -m pip install -e ".[postgresql]"
# or every driver at once
.\\.venv\\Scripts\\python.exe -m pip install -e ".[all-drivers]"</code></pre>
<p>Available extras: <code>postgresql</code>, <code>mysql</code>,
<code>mssql</code>, <code>oracle</code>, <code>duckdb</code>,
<code>all-drivers</code>. SQLite ships with Python.</p>
</section>

<section id="run">
<h2>Running the app</h2>
<pre><code>python main.py --mode desktop      # native desktop window (default)
python main.py --mode web          # web app at http://127.0.0.1:8080</code></pre>
<p>Or, once installed, the <code>dbvisual</code> command:</p>
<pre><code>dbvisual --mode desktop
dbvisual --mode web --host 127.0.0.1 --port 8080</code></pre>
<p>In web mode the app stays bound to <code>127.0.0.1</code> (local only). You can
set the preferred startup mode from the <a href="#settings">Settings</a> page.</p>
</section>

<section id="firststeps">
<h2>First steps (start here)</h2>
<ol>
  <li>Open <a href="#connections">Connections</a> and click
  <span class="hlp-btn">New connection</span>. Pick your database dialect, fill in
  the details, click <span class="hlp-btn">Test</span>, then
  <span class="hlp-btn">Save</span>. See
  <a href="#dbconfig">Database configuration</a> for per-database fields.</li>
  <li>Click <span class="hlp-btn">Browse schema</span> to confirm the app can read
  your tables.</li>
  <li>Go to <a href="#sheets">Sheets</a> (or Forms/Reports) and click
  <span class="hlp-btn">New sheet</span>. Choose the connection, load the schema,
  pick the main table and columns, then <span class="hlp-btn">Save</span>.</li>
  <li>Open the new sheet and start editing, or build a report and try
  <a href="#views">saved views</a> and <a href="#snapshots">snapshots</a>.</li>
</ol>
<div class="hlp-tip">Tip: the left navigation drawer switches between pages
(Connections, Database, Sheet, Form, Report, Master-Detail, Applications,
Settings, About). This Help opens in its own view; use <em>Back to app</em> at the
top to return.</div>
</section>

<section id="concepts">
<h2>Key concepts</h2>
<ul>
  <li><strong>Main table</strong>: the only writable table of a definition.</li>
  <li><strong>Related tables</strong>: read-only lookups joined for display.</li>
  <li><strong>Optimistic locking</strong>: if a record changed since you loaded it,
  the save is refused and the data reloaded - retry.</li>
  <li><strong>Identity</strong>: an email used for PostgreSQL row-level security and
  to scope private saved views.</li>
</ul>
</section>

<section id="connections">
<h2>Connections page</h2>
<p>Route <code>/connections</code>. Create and manage the databases dbvisual talks
to.</p>
<h3>Buttons and controls</h3>
<ul>
  <li><span class="hlp-btn">New connection</span> - opens the connection dialog
  (see below).</li>
  <li><strong>Current identity (email for PostgreSQL RLS)</strong> - the email
  passed to Postgres as <code>app.current_user_email</code>. Leave empty to disable
  RLS. Click <span class="hlp-btn">Save identity</span> to store it.</li>
  <li>Per saved connection card:
    <ul>
      <li><span class="hlp-btn">Browse schema</span> - lists tables, columns
      (type/nullable/PK) and foreign keys.</li>
      <li><span class="hlp-btn">Delete</span> (trash icon) - removes the connection
      and its stored password.</li>
    </ul>
  </li>
</ul>
<h3>New / edit connection dialog</h3>
<ul>
  <li><strong>Name</strong> - a label for the connection.</li>
  <li><strong>Dialect</strong> - PostgreSQL, MySQL/MariaDB, SQL Server, Oracle,
  SQLite, DuckDB, or SQLite encrypted (SQLCipher).</li>
  <li><strong>Host</strong>, <strong>Port</strong> - server address (not used for
  SQLite/DuckDB file databases).</li>
  <li><strong>Database / file path</strong> - the database name, or a file path for
  SQLite/DuckDB.</li>
  <li><strong>Username</strong>, <strong>Password</strong> - credentials; the
  password is stored as a secret.</li>
  <li><strong>Encrypted file passphrase (SQLCipher / DuckDB)</strong> - only for
  encrypted file databases; also stored as a secret.</li>
  <li><span class="hlp-btn">Test</span> - tries to connect and reports success or
  the error.</li>
  <li><span class="hlp-btn">Save</span> - stores the connection.</li>
  <li><span class="hlp-btn">Cancel</span> - closes without saving.</li>
</ul>
<div class="hlp-note">The RLS connection must use a role that is <strong>not</strong>
superuser and <strong>not</strong> the table owner, otherwise PostgreSQL bypasses
row-level security.</div>
</section>

<section id="dbconfig">
<h2>Database configuration (per dialect)</h2>
<p>Fields to fill in the connection dialog, and the driver extra to install.</p>
<table>
  <tr><th>Dialect</th><th>Typical fields</th><th>Driver extra</th></tr>
  <tr><td>PostgreSQL</td><td>host, port 5432, database, username, password</td>
    <td><code>pip install -e ".[postgresql]"</code></td></tr>
  <tr><td>MySQL / MariaDB</td><td>host, port 3306, database, username, password</td>
    <td><code>pip install -e ".[mysql]"</code></td></tr>
  <tr><td>SQL Server</td><td>host, port 1433, database, username, password (an ODBC
    driver must be installed on the OS)</td>
    <td><code>pip install -e ".[mssql]"</code></td></tr>
  <tr><td>Oracle</td><td>host, port 1521, service/database, username, password</td>
    <td><code>pip install -e ".[oracle]"</code></td></tr>
  <tr><td>SQLite</td><td>Database / file path only (no host/port/user)</td>
    <td>built in</td></tr>
  <tr><td>DuckDB</td><td>Database / file path, or <code>:memory:</code></td>
    <td><code>pip install -e ".[duckdb]"</code></td></tr>
  <tr><td>SQLite encrypted (SQLCipher)</td><td>file path + passphrase</td>
    <td>needs <code>pysqlcipher3</code> or <code>sqlcipher3</code></td></tr>
</table>
<div class="hlp-tip">Always click <span class="hlp-btn">Test</span> before
<span class="hlp-btn">Save</span>. If a driver is missing, Test reports a clear
error telling you which package to install.</div>
</section>

<section id="database">
<h2>Database page (schema / DDL)</h2>
<p>Route <code>/schema</code>. Browse and change the schema of a connection. Every
change composes SQL and shows it for review; nothing runs automatically.</p>
<h3>Top controls</h3>
<ul>
  <li><strong>Connection</strong> select - pick which database to inspect.</li>
  <li><span class="hlp-btn">Create table</span> - opens the create-table dialog.</li>
  <li><span class="hlp-btn">Import CSV</span> - create a table from a CSV file.</li>
  <li><span class="hlp-btn">Relationship diagram</span> - a Mermaid diagram of
  foreign keys.</li>
</ul>
<h3>Per table (expand a table)</h3>
<ul>
  <li>Grid of columns: Column, Type, Nullable, PK.</li>
  <li><span class="hlp-btn">Add column</span> - opens the add-column dialog.</li>
  <li><span class="hlp-btn">Delete column</span> - opens the drop-column dialog
  (destructive).</li>
  <li><span class="hlp-btn">Export CSV</span> - downloads the table as CSV.</li>
  <li><span class="hlp-btn">Delete table</span> - drops the table (destructive).</li>
</ul>
<h3>Review and execute dialog</h3>
<p>Shows the exact SQL. Destructive operations show a warning and require ticking
<strong>I confirm I have read the SQL</strong>.</p>
<ul>
  <li><span class="hlp-btn">Execute</span> / <span class="hlp-btn">Execute
  (confirm)</span> - runs the statement in a transaction.</li>
  <li><span class="hlp-btn">Cancel</span> - discards it.</li>
</ul>
<h3>Create table dialog</h3>
<ul>
  <li><strong>Table name</strong>, then one row per column: <strong>Column</strong>,
  type, <strong>PK</strong>, <strong>NOT NULL</strong>.</li>
  <li><span class="hlp-btn">Add column</span> - adds a column row.</li>
  <li><span class="hlp-btn">Generate with AI</span> - describe the table and let the
  AI propose the DDL (optional; needs the AI assistant enabled).</li>
  <li><span class="hlp-btn">Review DDL</span> - shows the SQL to confirm.</li>
  <li><span class="hlp-btn">Cancel</span> - closes.</li>
</ul>
<div class="hlp-note">You need a database user with DDL privileges. SQLite cannot
add or drop a foreign key via ALTER.</div>
</section>

<section id="sheets">
<h2>Sheets (editable Excel-like grid)</h2>
<p>Route <code>/sheets</code>. List of saved sheets.</p>
<h3>List page</h3>
<ul>
  <li><span class="hlp-btn">New sheet</span> - opens the create dialog.</li>
  <li>Per sheet: <span class="hlp-btn">Open</span>, rename (pencil), delete
  (trash).</li>
</ul>
<h3>New sheet dialog</h3>
<ul>
  <li><strong>Sheet name</strong>, <strong>Application</strong> (or
  <strong>...or new application</strong>), <strong>Connection</strong>.</li>
  <li><strong>Row-level security</strong> checkbox (PostgreSQL only).</li>
  <li><strong>Main table</strong>, <strong>Columns</strong>, <strong>Related tables
  (read-only)</strong>.</li>
  <li><span class="hlp-btn">Save</span> / <span class="hlp-btn">Cancel</span>.</li>
</ul>
<h3>Sheet editor - top bar</h3>
<ul>
  <li><span class="hlp-btn">Save</span> - saves all edits in one transaction.</li>
  <li><span class="hlp-btn">Views</span> - save/load/delete
  <a href="#views">saved views</a>.</li>
  <li><span class="hlp-btn">Webhook</span> - configure
  <a href="#webhooks">webhooks</a>.</li>
  <li><span class="hlp-btn">Back</span> - returns to the sheet list.</li>
</ul>
<h3>Grid toolbar</h3>
<ul>
  <li><strong>Search</strong> - quick filter across rows.</li>
  <li><span class="hlp-btn">Add row</span> (plus) - inserts a new empty row.</li>
  <li><span class="hlp-btn">Delete selected</span> (trash) - removes selected
  rows (attachments cascade).</li>
  <li><span class="hlp-btn">Copy (TSV)</span> - copies the grid as tab-separated
  values for Excel.</li>
  <li><span class="hlp-btn">Paste from Excel (TSV)</span> - opens a dialog to paste
  cells; tick <em>First row is a header</em> if needed, then
  <span class="hlp-btn">Import</span>.</li>
  <li><span class="hlp-btn">Export CSV</span> - downloads the grid.</li>
  <li><span class="hlp-btn">Attachments</span> - manage files for the selected row
  (upload/download/delete) when the sheet has an attachment column.</li>
  <li><strong>Group by</strong> - group rows by one or more columns.</li>
</ul>
<div class="hlp-note">Only main-table columns are editable; related columns are
read-only. If someone else changed a row, the save is refused and the grid
reloaded - just retry.</div>
</section>

<section id="forms">
<h2>Forms (single-record data entry)</h2>
<p>Route <code>/forms</code>. One record at a time with navigation.</p>
<h3>List page</h3>
<ul>
  <li><span class="hlp-btn">New form</span>, then per form
  <span class="hlp-btn">Open</span> and delete.</li>
</ul>
<h3>Form editor toolbar</h3>
<ul>
  <li>Chevrons (&lt; &gt;) - previous / next record. The counter shows
  <em>Record N of M</em> (or <em>(new)</em>).</li>
  <li><span class="hlp-btn">New</span> - start a blank record.</li>
  <li><span class="hlp-btn">Save</span> - validates and saves (optimistic
  locking).</li>
  <li><span class="hlp-btn">Delete</span> - deletes the current record
  (attachments cascade).</li>
  <li><span class="hlp-btn">Webhook</span> - configure webhooks.</li>
  <li><span class="hlp-btn">Back</span> - returns to the form list.</li>
</ul>
<p>Fields honor defaults, typed inputs, <em>available values</em> (label differs
from stored value), per-field validation, cross-field submit rules and conditional
form rules (show/hide/enable). Attachment fields upload/download files.</p>
</section>

<section id="reports">
<h2>Reports (read-only)</h2>
<p>Route <code>/reports</code>. Reports never write to the database.</p>
<h3>List page</h3>
<ul>
  <li><span class="hlp-btn">New report</span>, then <span class="hlp-btn">Open</span>
  and delete per report.</li>
</ul>
<h3>New report dialog</h3>
<ul>
  <li><strong>Report name</strong>, <strong>Application</strong>,
  <strong>Connection</strong>.</li>
  <li>Source toggle: <strong>Query builder</strong> or <strong>Custom SQL
  (read-only)</strong>.</li>
  <li>For custom SQL: a textarea (only <code>SELECT</code>/<code>WITH</code>),
  <span class="hlp-btn">Generate with AI</span> and
  <span class="hlp-btn">AI settings</span>.</li>
  <li>For the builder: <strong>Main table</strong>, <strong>Columns</strong>,
  <strong>Related tables</strong>.</li>
  <li><span class="hlp-btn">Save</span> / <span class="hlp-btn">Cancel</span>.</li>
</ul>
<h3>Report viewer</h3>
<ul>
  <li><strong>Parameter</strong> inputs (if the report declares any).</li>
  <li><strong>Search</strong> - full-text filter over the loaded rows.</li>
  <li><strong>Grouping and subtotals</strong> panel: <strong>Group by (levels)</strong>,
  <strong>Subtotal field</strong>, <strong>Aggregate</strong> (sum/avg/count/min/max),
  <strong>Sort groups by</strong> (Caption or Subtotal), <strong>Descending</strong>,
  then <span class="hlp-btn">Apply grouping</span> or <span class="hlp-btn">Clear</span>.</li>
  <li><span class="hlp-btn">Load data</span> - runs the report.</li>
  <li><span class="hlp-btn">Views</span> - <a href="#views">saved views</a>.</li>
  <li><span class="hlp-btn">Snapshot HTML</span> / <span class="hlp-btn">Snapshot
  Excel</span> - export a <a href="#snapshots">point-in-time snapshot</a>.</li>
  <li><span class="hlp-btn">Back</span> - returns to the report list.</li>
  <li><span class="hlp-btn">Export CSV</span> - on the results grid.</li>
  <li>Chart builder: <strong>Type</strong> (Column/Line/Pie),
  <strong>Category</strong>, <strong>Series</strong>, <strong>Value</strong>,
  <strong>Aggregate</strong>, then <span class="hlp-btn">Generate</span>.</li>
</ul>
</section>

<section id="masterdetail">
<h2>Master-detail</h2>
<p>Route <code>/master-detail</code>. A master form plus linked detail grids, saved
atomically.</p>
<h3>List and create</h3>
<ul>
  <li><span class="hlp-btn">New</span> - dialog with <strong>Name</strong>,
  <strong>Application</strong>, <strong>Connection</strong>, <strong>Master
  table</strong> and one or more <strong>Detail table</strong>s.</li>
  <li>Per item: <span class="hlp-btn">Open</span>, delete.</li>
</ul>
<h3>Editor toolbar</h3>
<ul>
  <li>Chevrons - previous / next master record.</li>
  <li><span class="hlp-btn">New master</span> - blank master.</li>
  <li><span class="hlp-btn">Save all</span> - commits master and all details in one
  transaction; a new master PK propagates to new detail rows.</li>
  <li><span class="hlp-btn">Back</span> - returns to the list.</li>
</ul>
</section>

<section id="applications">
<h2>Applications</h2>
<p>Route <code>/applications</code>. A placeholder overview of your logical groups;
applications are created inline when you save a sheet/form/report.</p>
</section>

<section id="settings">
<h2>Settings</h2>
<p>Route <code>/settings</code>. The single place for configuration.</p>
<h3>AI</h3>
<ul>
  <li><strong>Enable AI</strong> (off by default), <strong>Provider</strong>,
  <strong>Model</strong>, <strong>New API key</strong> (stored only as a secret;
  shown as <em>set / not set</em>, never the value).</li>
  <li><span class="hlp-btn">Save AI</span>, <span class="hlp-btn">Test</span>,
  <span class="hlp-btn">Delete key</span>.</li>
</ul>
<h3>Identity / RLS</h3>
<ul>
  <li><strong>Current identity (email)</strong> and
  <span class="hlp-btn">Save identity</span>. Empty = RLS inactive.</li>
</ul>
<h3>General</h3>
<ul>
  <li><strong>Preferred startup mode</strong> (Desktop / Web) and
  <span class="hlp-btn">Save</span>.</li>
  <li>The <strong>user data folder</strong> is shown read-only (where the metadata
  store, attachments, secrets vault and snapshots live).</li>
</ul>
</section>

<section id="about">
<h2>About</h2>
<p>Route <code>/about</code>. Product description, author, credits, license and
links to the ST-LINE site, the online manual and the source code.</p>
</section>

<section id="views">
<h2>Saved views</h2>
<p>Sheets and reports can save named <strong>views</strong> (search, grouping and
column configuration) from the <span class="hlp-btn">Views</span> dialog:</p>
<ul>
  <li><strong>Private</strong> - visible only to the current identity.</li>
  <li><strong>Shared</strong> - visible to everyone.</li>
  <li><strong>Locked</strong> - immutable until unlocked.</li>
  <li><span class="hlp-btn">Save current</span> stores the current configuration;
  <span class="hlp-btn">Load</span> applies a view; the trash icon deletes it.</li>
</ul>
</section>

<section id="snapshots">
<h2>Snapshots (point-in-time)</h2>
<p>From a report, <span class="hlp-btn">Snapshot HTML</span> and
<span class="hlp-btn">Snapshot Excel</span> freeze the current (filtered/grouped)
rows into portable files saved in the <code>snapshots/</code> folder of the user
data directory:</p>
<ul>
  <li><strong>HTML</strong> - a single self-contained file (no database needed),
  including group subtotals.</li>
  <li><strong>Excel</strong> - an <code>.xlsx</code> with detail rows and, when
  grouping is active, group header and subtotal rows.</li>
</ul>
</section>

<section id="webhooks">
<h2>Webhooks</h2>
<p>From a sheet or form, the <span class="hlp-btn">Webhook</span> button configures
non-blocking HTTP POST (JSON) calls on create/update/delete.</p>
<ul>
  <li><span class="hlp-btn">Add webhook</span>, then per webhook edit/delete;
  <span class="hlp-btn">Close</span>.</li>
  <li>Editor: <strong>Name</strong>, <strong>URL (secret)</strong>,
  <strong>Events</strong> (created/updated/deleted), body mode (default/custom) and
  a template with placeholders <code>{{field}}</code>,
  <code>{{field:formatted}}</code>, <code>{{field:bare}}</code>.</li>
  <li><span class="hlp-btn">Test</span> sends a sample; <span class="hlp-btn">Save</span>
  stores it; the URL is kept as a secret.</li>
</ul>
</section>

<section id="rls">
<h2>Row-level security (PostgreSQL)</h2>
<p>RLS is delegated to PostgreSQL policies. dbvisual only passes the current
identity via <code>SET app.current_user_email</code>. Enable it per definition
(Postgres only) and set the identity email in Connections or Settings.</p>
<div class="hlp-note">The connection role must be non-superuser and not the table
owner, or PostgreSQL bypasses RLS.</div>
</section>

<section id="ai">
<h2>AI assistant (optional, off by default)</h2>
<p>Turns natural language into <strong>read-only</strong> SQL for reports, using a
provider you choose (Claude / OpenAI / Gemini / DeepSeek) with your own API key
(stored as a secret). The generated SQL is always shown for review and validated as
read-only; it is never executed automatically.</p>
<div class="hlp-note">When using the AI, the database structure (table and column
names) and your request are sent to the chosen cloud provider. Per-token cost is on
you.</div>
</section>

<section id="security">
<h2>Security &amp; data folder</h2>
<ul>
  <li>All queries use bound parameters (no SQL injection); writes only on the main
  table; lookup columns are read-only.</li>
  <li>Secrets (passwords, passphrases, API keys, webhook URLs) are never stored in
  clear text - they live in the OS keyring or an encrypted fallback vault.</li>
  <li>The metadata store, attachments, secrets vault and <code>snapshots/</code>
  folder live in the user data directory shown in Settings.</li>
</ul>
</section>

<section id="packaging">
<h2>Packaging (standalone executable)</h2>
<p>Build a standalone executable with <code>nicegui-pack</code> (a PyInstaller
wrapper):</p>
<pre><code>nicegui-pack --onefile --name dbvisual main.py</code></pre>
<p>See <code>docs/packaging.md</code> in the repository for the required hidden
imports and an 8-item acceptance checklist. User data always resolves via the OS
user directory, never inside the temporary bundle folder.</p>
</section>

<section id="faq">
<h2>Troubleshooting / FAQ</h2>
<ul>
  <li><strong>Test connection fails with a missing driver</strong> - install the
  matching extra (see <a href="#dbconfig">Database configuration</a>).</li>
  <li><strong>Save is refused with a concurrency message</strong> - someone changed
  the record; the data was reloaded, just retry.</li>
  <li><strong>RLS does not filter anything</strong> - set the identity email and make
  sure the Postgres role is non-superuser / non-owner.</li>
  <li><strong>Encrypted SQLite is unavailable</strong> - install
  <code>pysqlcipher3</code> or <code>sqlcipher3</code>; DuckDB encryption works out
  of the box.</li>
  <li><strong>The native window shows a blank page after an upgrade</strong> - pin a
  known-good NiceGUI 3.x version.</li>
  <li><strong>Where is my data?</strong> - the user data folder is shown on the
  Settings page.</li>
</ul>
</section>

</div>
"""

_HELP_HTML = (
    _STYLE
    + '<div class="hlp">'
    + '<div class="hlp-top">'
    + "<strong>dbvisual - Help</strong>"
    + '<a class="back" href="/connections">Back to app</a>'
    + "</div>"
    + '<div class="hlp-body">'
    + _NAV
    + _CONTENT
    + "</div></div>"
)


@ui.page("/help")
def help_page() -> None:
    """Render the self-contained, navigable HTML help document."""
    ui.query(".nicegui-content").classes("p-0 gap-0")
    ui.html(_HELP_HTML).classes("w-full")
