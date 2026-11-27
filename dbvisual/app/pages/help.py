"""In-app manual shared by the Help dialog and the standalone /help page."""

from __future__ import annotations

from collections.abc import Callable

from nicegui import ui

_STYLE = """
.hlp { --help-top: 0px; color: #1f2937; font-size: 16px; line-height: 1.55; }
.hlp.standalone { --help-top: 56px; }
.hlp-shell { display: grid; grid-template-columns: 216px minmax(0, 1fr);
  max-width: 1200px; margin: 0 auto; }
.hlp-sidebar { position: sticky; top: var(--help-top); align-self: start;
  max-height: calc(100vh - var(--help-top)); overflow-y: auto;
  padding: 16px; background: #f8fafc; border-right: 1px solid #dbe2eb; }
.hlp-nav h4 { color: #334155; font-size: 14px; line-height: 1.4;
  font-weight: 700; letter-spacing: normal; margin: 16px 0 4px; }
.hlp-nav h4:first-child { margin-top: 0; }
.hlp-nav a { display: block; padding: 3px 0; font-size: 14px; }
.hlp a { color: #1d4ed8; text-decoration: underline; text-underline-offset: 2px; }
.hlp a:focus-visible, .hlp summary:focus-visible { outline: 2px solid #2563eb;
  outline-offset: 2px; }
.hlp-mobile-index { display: none; }
.hlp-main { min-width: 0; max-width: 88ch; padding: 20px 32px 48px; }
.hlp-main h1, .hlp-main h2, .hlp-main h3 { color: #172033;
  font-weight: 650; line-height: 1.3; letter-spacing: normal; }
.hlp-main h1 { font-size: 26px; margin: 0 0 8px; }
.hlp-main h2 { font-size: 21px; margin: 26px 0 8px;
  padding-top: 14px; border-top: 1px solid #dbe2eb; }
.hlp-main h3 { font-size: 17px; margin: 16px 0 5px; }
.hlp-main p { margin: 0 0 10px; }
.hlp-main ul, .hlp-main ol { padding-left: 1.5em; margin: 6px 0 12px; }
.hlp-main ul { list-style: disc; }
.hlp-main ol { list-style: decimal; }
.hlp-main li { margin: 0 0 4px; }
.hlp-main code { background: #f1f5f9; border-radius: 3px; padding: 1px 4px;
  font-family: ui-monospace, Consolas, monospace; font-size: .9em; overflow-wrap: anywhere; }
.hlp-main table { border-collapse: collapse; width: 100%; font-size: 14px; }
.hlp-main th, .hlp-main td { border: 1px solid #dbe2eb; padding: 6px;
  text-align: left; vertical-align: top; overflow-wrap: anywhere; }
.hlp-main th { background: #f1f5f9; }
.hlp-btn { font-weight: 600; }
.hlp-note, .hlp-tip { border-left: 3px solid #2563eb; background: #eff6ff;
  padding: 8px 12px; margin: 12px 0; }
.hlp-main section, .hlp-main h3[id] { scroll-margin-top: calc(var(--help-top) + 10px); }
@media (max-width: 840px) {
  .hlp-shell { display: block; }
  .hlp-sidebar { display: none; }
  .hlp-mobile-index { display: block; background: #f8fafc; padding: 8px 16px;
    border-bottom: 1px solid #dbe2eb; }
  .hlp-mobile-index summary { cursor: pointer; color: #1d4ed8; font-weight: 600; }
  .hlp-mobile-index nav { padding: 12px 6px 0; }
  .hlp-main { padding: 16px 16px 40px; }
}
@media (max-width: 480px) {
  .hlp-main h1 { font-size: 22px; }
  .hlp-main h2 { font-size: 19px; }
}
"""

_NAV = """
<nav class="hlp-nav">
  <h4>Getting started</h4>
  <a href="#firststeps">First steps</a>
  <a href="#install">Install DBVisual</a>
  <a href="#run">Open the app</a>
  <a href="#create-db">Create a database</a>
  <a href="#sqlite">Open a SQLite file</a>
  <a href="#csv">Import a CSV file</a>
  <a href="#overview">Overview</a>
  <a href="#concepts">Key concepts</a>
  <h4>Pages</h4>
  <a href="#connections">Connections</a>
  <a href="#dbconfig">Database configuration</a>
  <a href="#database">Database (schema)</a>
  <a href="#sheets">Sheets</a>
  <a href="#form-editor">Forms</a>
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
<section id="firststeps">
<h1>First steps</h1>
<p>Begin with a database file on your computer. Once connected, you can browse
its tables, build an editable sheet or create a report.</p>

<h3 id="run">Open the app</h3>
<p><strong>Windows:</strong> open Start, type <strong>DBVisual</strong> and select
the app. The installer creates the shortcut in the Start menu.
<strong>Mac:</strong> open DBVisual in Applications.</p>
<p>The first screen is <strong>Connections</strong>. “No saved connections”
means you are ready to add your first database.</p>

<h3 id="create-db">Create a database</h3>
<ol>
  <li>In <strong>Connections</strong>, click <strong>Create database</strong>.
  Choose <strong>SQLite</strong> or <strong>DuckDB</strong>.</li>
  <li>Enter a <strong>File name</strong> such as <em>Practice</em>. Keep the
  suggested folder, enter another folder path or use <strong>Choose folder</strong>
  in the desktop app. DBVisual adds the file extension if you omit it.</li>
  <li>Click <strong>Create</strong>. Your new connection appears in the list.
  From <strong>Database</strong> you can create a table or import a CSV.</li>
</ol>
<h3 id="sqlite">Open a SQLite file</h3>
<ol>
  <li>Save the database in a folder you can write to, such as a DBVisual folder
  under Documents. Extract the file first if it came in a ZIP archive.</li>
  <li>In <strong>Connections</strong>, choose <strong>New connection</strong>.
  Enter a <strong>Name</strong> such as <em>Practice</em> and change
  <strong>Dialect</strong> to <strong>SQLite</strong>.</li>
  <li>Paste the full path of the database file into <strong>Database / file path</strong>.
  Leave Host, Port, Username and Password empty.</li>
  <li>Click <strong>Test</strong>, then <strong>Save</strong>. On the saved connection,
  click <strong>Browse schema</strong> to see the tables. If you expected tables
  and see none, check the filename: SQLite can create an empty file at a new path.</li>
</ol>

<h3 id="csv">Import a CSV file</h3>
<ol>
  <li>Save the CSV anywhere convenient. Use a UTF-8, comma-separated file
  with column names in the first row.</li>
  <li>Choose a destination database. If this is your first import,
  <a href="#create-db">create a database</a> first.</li>
  <li>Open the navigation menu, choose <strong>Database</strong>, select the
  saved connection and click <strong>Import CSV</strong>.</li>
  <li>Enter a <strong>New table name</strong> and choose your CSV file. Click
  <strong>Review DDL</strong>, then <strong>Execute</strong>. The new table
  appears in the database. The original CSV stays in its folder.</li>
</ol>
<h3>Work with the data</h3>
<p>To view imported rows, create a <a href="#reports">report</a>. To edit an existing
table that has a primary key, open <a href="#sheets">Sheet</a> and choose
<strong>New sheet</strong>. Choose or name an application, select the connection,
table and columns, then save and open your sheet.</p>
</section>

<section id="install">
<h2>Install DBVisual</h2>
<p><strong>Windows 10 or 11 (64-bit):</strong> run the setup file and accept the
suggested folder. It installs for your Windows user. If Windows shows “Access
denied” for Program Files, run setup again and keep the suggested location.</p>
<p><strong>Mac with Apple Silicon:</strong> open the disk image, drag DBVisual to
Applications and open it from there. Both desktop packages include Python.</p>
</section>

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

<section id="concepts">
<h2>Key concepts</h2>
<ul>
  <li><strong>Main table</strong>: the only writable table of a definition.</li>
  <li><strong>Related tables</strong>: read-only lookups joined for display.</li>
  <li><strong>Optimistic locking</strong>: if a record changed since you loaded it,
  saving stops. Review the conflicting fields and choose which values to keep.</li>
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
  <li><a href="#create-db">Create database</a> creates an empty SQLite or DuckDB file
  and saves its connection.</li>
  <li><span class="hlp-btn">New connection</span> - opens the connection dialog
  (see below).</li>
  <li><strong>Current identity (email for PostgreSQL RLS)</strong> - the email
  passed to Postgres as <code>app.current_user_email</code>. An identity is required
  for definitions that use RLS. SQLite connections can leave this field empty. Click <span class="hlp-btn">Save identity</span> to store it.</li>
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
<p>Select the dialect in <strong>New connection</strong>, then enter the corresponding details.</p>
<table>
  <tr><th>Dialect</th><th>Connection details</th></tr>
  <tr><td>SQLite</td><td>Full path to the database file.</td></tr>
  <tr><td>DuckDB</td><td>Full path to the database file; enter the passphrase for an encrypted database.</td></tr>
  <tr><td>PostgreSQL</td><td>Host, port (usually 5432), database, username and password.</td></tr>
  <tr><td>MySQL / MariaDB</td><td>Host, port (usually 3306), database, username and password.</td></tr>
  <tr><td>SQL Server</td><td>Host, port (usually 1433), database, username and password.
  Install a compatible ODBC driver on the computer.</td></tr>
  <tr><td>Oracle</td><td>Host, port (usually 1521), service or database, username and password.</td></tr>
  <tr><td>SQLite encrypted (SQLCipher)</td><td>File path and passphrase. Requires a source
  installation with a SQLCipher driver; the standard installers omit this optional driver.</td></tr>
</table>
<p>Click <strong>Test</strong> to check the details, then <strong>Save</strong>.</p>
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
read-only. If someone else changed a row, the save is refused. Review the original, local and database values. Choose which edits to keep, then click <strong>Apply choices and retry</strong>.</div>
</section>

<section id="form-editor">
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
  <span class="hlp-btn">Save identity</span>. RLS-enabled forms and sheets require an identity.</li>
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
identity in the session setting <code>app.current_user_email</code>. Enable it per definition
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
<p>For the Windows installer and macOS disk image, see <a href="#install">Install
DBVisual</a>. If you are running from the Python source distribution, follow the
installation and launch instructions in the repository README.</p>
</section>

<section id="faq">
<h2>Troubleshooting / FAQ</h2>
<ul>
  <li><strong>Test connection fails with a missing driver</strong> - install the
  driver required for your database (see <a href="#dbconfig">Database configuration</a>).</li>
  <li><strong>Another user changed a row.</strong> Compare the original value, your edit
  and the current database value. Choose which value to keep, then retry the save.</li>
  <li><strong>RLS does not filter anything</strong> - set the identity email and make
  sure the Postgres role is non-superuser / non-owner.</li>
  <li><strong>Encrypted SQLite is unavailable.</strong> The standard installer supports
  ordinary SQLite files. See <a href="#dbconfig">Database configuration</a> for SQLCipher.</li>
  <li><strong>Where are my files?</strong> Your SQLite database stays at the path in
  its connection. CSV imports create a table in the selected database. Settings shows
  the separate folder for DBVisual settings, attachments and snapshots.</li>
</ul>
</section>

</div>
"""


def _toolbar(on_back: Callable[[], None]) -> None:
    with ui.row().classes(
        "w-full shrink-0 flex-nowrap items-center justify-between gap-2 bg-primary "
        "px-4 text-white h-14"
    ):
        ui.label("DBVisual Help").classes("text-xl font-bold")
        ui.button("Back to app", icon="arrow_back", on_click=on_back).props(
            "outline no-caps color=white"
        )


def help_dialog() -> ui.dialog:
    """Keep the current editor and its unsaved values mounted beneath the manual."""
    with (
        ui.dialog().props('maximized aria-label="DBVisual Help"') as dialog,
        ui.card().classes(
            "w-full h-full flex flex-col flex-nowrap p-0 gap-0 overflow-hidden"
        ),
    ):
        _toolbar(dialog.close)
        ui.element("iframe").props(
            'src="/help?embedded=true" title="User guide"'
        ).classes("w-full grow min-h-0 border-0")
    return dialog


@ui.page("/help")
def help_page(embedded: bool = False) -> None:
    """Render the same guide in the app or at its bookmarked URL."""
    ui.add_css(_STYLE)
    ui.query(".nicegui-content").classes("p-0 gap-0")
    if not embedded:
        ui.colors(primary="#2563eb")
        with ui.header().classes("p-0"):
            _toolbar(lambda: ui.navigate.to("/connections"))
    layout = "hlp" if embedded else "hlp standalone"
    ui.html(
        f'<div class="{layout}"><div class="hlp-shell">'
        f'<aside class="hlp-sidebar">{_NAV}</aside>'
        f'<details class="hlp-mobile-index"><summary>Guide topics</summary>{_NAV}</details>'
        f"{_CONTENT}</div></div>"
    ).classes("w-full")
