# dbvisual

Applicazione **locale** e self-contained per costruire **form, sheet (griglie) e report**
su database esistenti, in stile Visual DB. Gira interamente sulla macchina di installazione:
nessun cloud, nessun account remoto, nessun multi-tenant. I database *target* possono
essere locali o remoti, ma l'app e i suoi metadati restano sempre in locale.

Concetto centrale: tutto è generato da una **query-spec** (JSON). Form, sheet e report
sono soltanto *render* diversi della stessa specifica.

**Applicazione monolitica**: un solo codebase Python (UI = [NiceGUI](https://nicegui.io/)),
un solo processo, un solo eseguibile. Lo stesso codice gira come **finestra desktop nativa**
o come **web app** locale su `127.0.0.1`. Nessun frontend/backend separato, nessun build JS.

---

## Avvio dell'applicazione

Dopo l'installazione (vedi sotto), avvia l'app dall'entrypoint:

```powershell
python main.py --mode desktop      # default: finestra desktop nativa (pywebview)
python main.py --mode web          # web app locale su http://127.0.0.1:8080
```

In alternativa, tramite il comando installato:

```powershell
dbvisual --mode desktop
dbvisual --mode web --host 127.0.0.1 --port 8080
```

> **Nota su NiceGUI e native mode.** NiceGUI è fissato a `>=3,<4` in `pyproject.toml`:
> con questa serie `ui.echart` (grafici) ed `ui.aggrid` (griglie) renderizzano
> correttamente anche in modalità desktop nativa. Se dopo un aggiornamento la finestra
> nativa mostra una pagina bianca, ripristina una versione nota di NiceGUI (3.x) e
> aggiorna questa nota.

---

## Fase 1 — Core (questo pacchetto)

Questa fase implementa **solo** il layer `core` DB-agnostico, senza UI e senza API HTTP:

| Modulo | Responsabilità |
| --- | --- |
| `dbvisual/core/connections.py` | Creazione di un `Engine` SQLAlchemy multi-dialetto + test di connessione. |
| `dbvisual/core/introspect.py` | Reflection dello schema: tabelle, colonne (tipo/nullable/pk), foreign key. |
| `dbvisual/core/queryspec.py` | Modelli Pydantic v2 della query-spec, serializzabili in JSON. |
| `dbvisual/core/compiler.py` | **Cuore del sistema**: compila una `QuerySpec` in un `sqlalchemy.select()`. |
| `dbvisual/core/crud.py` | CRUD generico su `main_table` + salvataggio master-detail transazionale. |

### Principi

- **SQLAlchemy Core 2.0** (non l'ORM): `Engine`, `MetaData.reflect()`, `inspect()`,
  costruzione query con `select()/insert()/update()/delete()`.
- **DB-agnostico**: la stessa query-spec produce lo stesso `Select` su qualunque dialetto.
- **Sicurezza**: tutti i valori dei filtri sono passati come **bind-parameter**, mai
  concatenati nella stringa SQL (niente SQL injection).
- **Tipizzazione**: type hints ovunque, docstring brevi.

### Dialetti e driver supportati

| DB | Driver | URL SQLAlchemy |
| --- | --- | --- |
| PostgreSQL | `psycopg` (v3) | `postgresql+psycopg://` |
| MySQL/MariaDB | `PyMySQL` | `mysql+pymysql://` |
| SQL Server | `pyodbc` | `mssql+pyodbc://` |
| Oracle | `oracledb` | `oracle+oracledb://` |
| SQLite | built-in | `sqlite:///path` |

---

## Installazione (venv)

Requisiti: **Python ≥ 3.11**.

```powershell
# dalla cartella del progetto
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows PowerShell
# source .venv/bin/activate         # Linux / macOS

# installa il core + strumenti di test (SQLite è built-in, nessun driver esterno richiesto)
pip install -e ".[dev]"
```

I driver dei database sono **opzionali** e si installano solo per il DB che serve:

```powershell
pip install -e ".[postgresql]"      # oppure mysql / mssql / oracle
pip install -e ".[all-drivers]"     # tutti i driver insieme
```

---

## Fase 2 — Shell + Connessioni + Schema

La Fase 2 aggiunge il guscio dell'app NiceGUI, la persistenza locale e la gestione
delle connessioni con browser dello schema.

| Modulo | Responsabilità |
| --- | --- |
| `dbvisual/meta/models.py` | Schema SQLAlchemy Core del metadata store (`connections`, `applications`, `definitions`). |
| `dbvisual/meta/store.py` | CRUD su connessioni/applicazioni/definizioni (SQLite locale via `platformdirs`). |
| `dbvisual/meta/secrets.py` | Password DB cifrate: **keyring** (portachiavi OS) con fallback a file **Fernet**. |
| `dbvisual/app/shell.py` | Layout: header + navigazione laterale. |
| `dbvisual/app/pages/connections.py` | Lista connessioni, form nuova/modifica, **Testa**, **Salva**, **Sfoglia schema**. |
| `dbvisual/app/main.py` · `main.py` | Bootstrap dello stato + `ui.run` (desktop/web) ed entrypoint CLI. |

- **Metadata store**: file SQLite nella cartella dati utente (`platformdirs`).
- **Credenziali**: mai in chiaro nel metadata store; keyring o file cifrato Fernet
  con permessi ristretti.
- La pagina *Connessioni* usa direttamente il core (`build_engine`, `test_connection`,
  `reflect_schema`, `list_tables`, `get_columns`, `detect_foreign_keys`): nessuna logica DB
  duplicata.

### Packaging (eseguibile portabile)

Bundle standalone con **`nicegui-pack`** (basato su PyInstaller):

```powershell
nicegui-pack --onefile --name dbvisual main.py
```

L'eseguibile risultante avvia l'app in modalità desktop senza richiedere Python installato.

---

## Fase 3 — Sheet (griglia Excel-like editabile)

Uno **Sheet** è una *definition* (`kind='sheet'`) nel metadata store: contiene una
query-spec e l'id della connessione su cui gira. Aprirlo compila la query col core,
la esegue e popola una `ui.aggrid` editabile.

| Modulo | Responsabilità |
| --- | --- |
| `dbvisual/app/sheet_service.py` | Orchestrazione DB (solo core): risoluzione engine+metadata con cache, `compile_select`, costruzione delle operazioni e salvataggio batch transazionale. |
| `dbvisual/app/components/grid.py` | Componente `SheetGrid`: `ui.aggrid` editabile, tracking delle modifiche, ricerca, copia/incolla TSV, export CSV. |
| `dbvisual/app/pages/sheets.py` | Lista sheet, creazione (query-builder minimale) e editor con salvataggio. |

### Creare uno sheet

1. Vai in **Sheet → Nuovo sheet**.
2. Dai un nome, scegli l'**applicazione** (o creane una nuova) e la **connessione**.
3. Alla selezione della connessione lo schema viene riflesso: scegli la **tabella
   principale**, le **colonne** da mostrare e, opzionalmente, le **tabelle correlate**
   (rilevate via foreign key, aggiunte in **sola lettura**).
4. **Salva**: lo sheet è persistito come definition `kind='sheet'`.

> Le colonne di primary key della tabella principale sono incluse automaticamente
> (servono per aggiornare/eliminare le righe) e non sono editabili.

### Usare uno sheet

- **Apri** lo sheet: solo le colonne della `main_table` sono editabili; le colonne
  delle tabelle correlate (lookup) sono di sola lettura.
- **Ordinamento / filtro** per colonna e **ricerca full-text** (quick filter) sono nativi.
- **Aggiungi riga** / **Elimina selezionate** preparano insert/delete.
- **Salva**: tutte le modifiche (insert/update/delete) sono applicate in **una singola
  transazione** tramite il core (`crud`); in caso di errore viene fatto **rollback
  completo** e la griglia è ricaricata dai dati reali. Le colonne related non vengono
  mai scritte.

### Validazione, campi calcolati e totali

- **Validazione di cella**: si configurano regole per colonna (`FieldRule`: required,
  min/max, lunghezza, caratteri ammessi/vietati, regex, email, telefono, zip, url, carta
  di credito, vincoli su date). Le celle non valide sono **sottolineate in rosso** e il
  **Salva è bloccato** finché restano errori. Il motore (`dbvisual/app/validation.py`) è
  riutilizzabile anche dai Form (Fase 4).
- **Campi calcolati (formula)**: colonne in sola lettura la cui espressione referenzia altre
  colonne della stessa riga (es. `qty * price`), ricalcolate a ogni edit. Il valutatore
  (`dbvisual/app/formula.py`) è **limitato e sicuro**: whitelist di operatori/funzioni,
  nessun `eval` di codice arbitrario.
- **Totali di colonna**: riga fissa in fondo (pinned bottom row) con somma/media/conteggio,
  aggiornata istantaneamente a ogni modifica e **coerente con il quick filter attivo**.

### Optimistic locking (concorrenza)

Gli update usano il locking ottimistico: la griglia conserva i **valori originali** di ogni
riga caricata e l'`UPDATE` include un guard `WHERE PK AND valori-originali`. Se un record è
stato modificato da altri nel frattempo l'update tocca **0 righe** → il core solleva
`ConflictError`, l'intera transazione fa **rollback** e la griglia viene ricaricata con un
messaggio "il record è stato modificato da altri, riprova". Il parametro è **opzionale** e
additivo su `crud.update_record` (l'API e i test esistenti restano invariati).

### Copia / incolla ed export

- **Copia (TSV)**: copia l'intera griglia negli appunti in formato compatibile con Excel.
- **Incolla da Excel (TSV)**: apre un dialog dove incollare celle da Excel; le colonne
  editabili vengono riempite in ordine e le righe aggiunte come insert al salvataggio.
- **Esporta CSV**: scarica il contenuto dello sheet (funzione community di AG Grid).

> **Nota su AG Grid Community.** La selezione a range e la clipboard nativa sono funzioni
> *Enterprise*; per questo copia/incolla usano un percorso TSV affidabile e l'export è in
> CSV. Anche il *row grouping* visuale richiede Enterprise: il selettore "Raggruppa per"
> imposta i flag ma la resa a gruppi è disponibile solo con AG Grid Enterprise; ordinamento,
> filtro e quick-filter (community) funzionano pienamente.

---

## Fase 4 — Form (data entry su un record alla volta)

Un **Form** è una definition (`kind='form'`) con un `FormSpec` (query-spec + connessione +
config dei campi + regole). Mostra i record **uno alla volta**; solo la `main_table` è
scrivibile, le colonne related sono in sola lettura.

| Modulo | Responsabilità |
| --- | --- |
| `dbvisual/app/form_service.py` | `FormSpec`, default, validazione, submit/form rules, available values, save/delete con optimistic locking (solo core). |
| `dbvisual/app/components/form_field.py` | Campo configurabile: input per tipo dato, dropdown label≠value, validazione visiva, hide/disable, attachment. |
| `dbvisual/app/pages/forms.py` | Lista form, creazione (query builder) e editor con navigazione record. |
| `dbvisual/meta/attachments.py` | Storage locale dei file (metadati JSON nel DB, byte su disco via `platformdirs`). |

### Creare e usare un form

1. **Form → Nuovo form**: nome, applicazione, connessione; scegli tabella principale,
   colonne ed eventuali tabelle correlate (read-only). Si salva come definition `kind='form'`.
2. **Apri** il form: naviga i record con **‹ ›** e l'indicatore *"Record N di M"*; usa
   **Nuovo / Salva / Elimina**.

### Input, available values, default e validazione

- **Tipi di input** derivati dal tipo dato: testo (single/multiline), numero, data
  (date picker), booleano (checkbox), dropdown se ci sono *available values*.
- **Available values** con sorgenti: valori esistenti della colonna, da **tabella**, da
  **query**, **lista manuale**. Supporto **LABEL ≠ VALUE**: il dropdown mostra l'etichetta
  (es. nome cliente) ma **salva il value** (es. l'id). Opzione *"consenti nuovi valori"*.
- **Default value** applicato ai nuovi record.
- **Validazione per campo** (stesso motore dello Sheet): required, min/max, lunghezza,
  caratteri ammessi/vietati, regex, email/telefono/zip/url, carta di credito, vincoli data.
  I campi non validi sono evidenziati e il **salvataggio è bloccato** finché restano errori.

### Regole di form e attachment

- **Submit rules** (cross-field): regole sull'intero record prima del salvataggio (es.
  "almeno uno tra A e B compilato"); se violate, il submit è bloccato con messaggio.
- **Form rules**: nascondi / disabilita / abilita un campo in base ai valori di altri campi,
  rivalutate a ogni modifica.
- **Attachment**: un campo può essere di tipo *attachment*. Il **file non entra nel DB**: nel
  campo testo si salvano solo i **metadati JSON** (`id`, `filename`, `content_type`, `size`),
  mentre i byte stanno su **disco locale** (cartella app per applicazione/record). Upload,
  download e delete supportati; alla **cancellazione del record** i file vengono rimossi
  (cascade).
- Il **salvataggio** usa il core in transazione con **optimistic locking** (come lo Sheet):
  un conflitto ricarica il record senza scrivere.

---

## Fase 5 — Report (sola lettura: parametri, filtri e grafici)

Un **Report** è una definition (`kind='report'`) con un `ReportSpec`. È **sola lettura**: non
aggiorna mai i dati. La sorgente può essere il **query builder** oppure una **query custom
SQL in sola lettura** (bind-param). I risultati vanno in una `ui.aggrid` read-only con grafici
`ui.echart` embedded.

| Modulo | Responsabilità |
| --- | --- |
| `dbvisual/app/report_service.py` | Caricamento dati (builder/custom), parametri (multi + cascata), filtri AND/OR annidati, aggregazione summary/pivot, SQL read-only. |
| `dbvisual/app/pages/reports.py` | Lista/crea/apri report; prompt parametri, tabella, ricerca, chart builder ed export. |

### Creare e usare un report

1. **Report → Nuovo report**: nome, applicazione, connessione; scegli **Query builder**
   (tabella + colonne + correlate) **oppure** **SQL custom** (solo `SELECT`/`WITH`).
2. **Apri** il report: compila gli eventuali **parametri**, premi **Carica dati**; usa la
   **ricerca** full-text, l'**ordinamento/raggruppamento** di colonna e **Esporta CSV**.

### Parametri

- **Multi-valore**: es. filtrare per più clienti/stati → `WHERE ... IN (:param)` con bind-param.
- **A cascata**: il valore scelto in un dropdown popola le opzioni del successivo (query
  dipendente dal parametro padre). Le liste riusano `resolve_available_values`
  (colonna/tabella/query/manuale).

### Filtri end-user

- Condizioni semplici, combinazioni **AND/OR** e condizioni **composte annidate** valutate in
  forma gerarchica (`FilterGroup`/`FilterCondition`). Applicati lato griglia sui risultati
  già caricati; i parametri di query (WHERE lato DB) si impostano invece nei prompt.

### Grafici (`ui.echart`)

- **Summary / pivot chart**: aggregano i dati (`aggregate_summary`, es. somma vendite per
  Prodotto × Regione) e plottano gli **aggregati**, distinti dai grafici grezzi.
- Tipi: colonna, linea/**time-series** (con **zoom** e finestra scorrevole via `dataZoom`),
  torta. Grafici **incorporati** nella pagina, esportabili come immagine (PNG/SVG di ECharts).

### Query custom SQL (sola lettura)

Le query custom sono validate da `ensure_readonly`: sono ammesse **solo** istruzioni singole
`SELECT`/`WITH`; qualunque `INSERT/UPDATE/DELETE/DROP/...` o statement multiplo è **rifiutato**.
I valori passano sempre come **bind-param** (`:param`), mai per concatenazione.

### Predisposizione RLS (session settings)

`ConnectionConfig` accetta ora un parametro opzionale `session_settings` (mappa chiave→valore):
a ogni nuova connessione esegue i relativi `SET` (es. `timezone`, `search_path`,
`statement_timeout`, e in futuro `app.current_user_email` per la RLS PostgreSQL della Fase 8).
Additivo e retro-compatibile; su SQLite è un no-op.

---

## Fase 6 — Master-Detail (salvataggio atomico)

Un **master-detail** è una definition (`kind='master_detail'`) con un `MasterDetailSpec`: una
query **master** (record singolo, riusa il Form) e una o più **detail** (grid, riusa lo Sheet).
Ogni detail ha **esattamente un parametro**, valorizzato con la **PK del master** corrente.
Master + tutti i detail vengono salvati in **una sola transazione**.

| Modulo | Responsabilità |
| --- | --- |
| `dbvisual/app/master_detail_service.py` | `MasterDetailSpec`, validazione (un solo parametro), rilevamento FK, caricamento detail, piano di salvataggio atomico con propagazione PK. |
| `dbvisual/app/pages/master_detail.py` | Lista/crea/apri; form master (prev/next) + grid detail editabili, salvataggio "Salva tutto". |

### Creare e usare un master-detail

1. **Master-Detail → Nuovo**: nome, connessione, **tabella master** e una o più **tabelle
   detail**. La FK detail→master è rilevata automaticamente (`detect_foreign_keys`) e usata
   come parametro unico della detail query.
2. **Apri**: naviga i master con **‹ ›**; per il master corrente ogni detail mostra solo le
   righe collegate. Modifica master e detail, poi **Salva tutto**.

### Casi supportati

- **One-to-many**: FK nel lato "molti" (es. `Orders` master → `LineItems` via `order_id`).
- **Many-to-many**: la **tabella di giunzione** è la main table del detail; la FK verso il
  master è il parametro e la seconda entità è una tabella **related read-only** per l'etichetta.

### Salvataggio atomico

- Tutte le modifiche (master + insert/update/delete su ogni detail) sono applicate in **una
  transazione** via `core.crud.save_master_detail`; un errore su un qualunque detail fa
  **rollback anche del master**.
- **Master nuovo**: la PK auto-generata viene **propagata come FK** ai detail nuovi *dentro la
  stessa transazione* (parametro additivo `link` di `save_master_detail`).
- **Optimistic locking** su master e detail: un conflitto annulla tutto e ricarica.
- Le colonne di tabelle **related non vengono mai scritte**.

---

## Fase 7 — Automation / Webhooks

Quando un record viene **creato / aggiornato / eliminato** in uno sheet o form, dbvisual può
inviare un **webhook HTTP POST (JSON)** a un URL configurato (Zapier, Slack, Discord, endpoint
proprio). I POST partono in **uscita** dalla macchina locale; nessun server in ingresso.

| Modulo | Responsabilità |
| --- | --- |
| `dbvisual/core/events.py` | Dispatch **opzionale** di eventi CRUD. Senza dispatcher registrato il core è invariato. |
| `dbvisual/app/webhooks.py` | Servizio: trova i webhook della tabella, rende il body e fa il POST (non bloccante, con retry opzionale). |
| `dbvisual/meta` | Tabella `webhooks` (config) + URL salvato come **segreto** in `SecretStore` (mai in chiaro nel DB). |

- **Configurazione** (dal pannello Webhook di sheet/form): nome, URL, eventi
  (`created`/`updated`/`deleted`), `body_mode` (default/custom) e template, con bottone **Testa**.
- **Body di default**: include automaticamente tutti i campi del record (si adatta se cambiano).
- **Body custom** con placeholder handlebars, tre *flavor*:
  - `{{campo}}` → valore **JSON valido** (numero/booleano/stringa quotata, `null`);
  - `{{campo:formatted}}` → stringa **sempre tra virgolette** (fallback a raw);
  - `{{campo:bare}}` → **testo puro senza virgolette** (per inserimento dentro stringhe).
  Esempi validi: Slack `{"text": "... {{customer_name:bare}} ..."}`, Discord
  `{"content": "... {{product:bare}} ..."}`.
- **Resilienza**: un webhook che fallisce **non** fa fallire il salvataggio (errore loggato, mai
  l'URL in chiaro); invio in background.

---

## Fase 8 — Row-Level Security (PostgreSQL)

La RLS **non è implementata dall'app**: è **delegata a PostgreSQL** (l'utente crea le policy con
`CREATE POLICY ... USING/WITH CHECK` e abilita la RLS sulla tabella). dbvisual si limita a
**passare l'identità** dell'utente corrente al DB.

- **Identità locale** (`app/identity.py`): una singola **email** dichiarata dall'utente e
  persistita in locale (impostabile dalla pagina **Connessioni**). Vuota = RLS **inattiva**.
- **Flag RLS per definition**: checkbox nel design panel di sheet/form, **visibile solo se la
  connessione è Postgres**; salvato in `SheetSpec.rls` / `FormSpec.rls`.
- **Wiring**: quando una definition ha RLS attiva su Postgres e l'identità è impostata, l'engine
  esegue `SET app.current_user_email = <email>` a ogni connessione (via `session_settings`); le
  policy Postgres usano `current_setting('app.current_user_email')`. Su dialetti non-Postgres il
  flag è **ignorato**.
- **Sicurezza (setup Postgres)**: la connessione deve usare un ruolo **NON superuser** e **NON
  owner** della tabella, altrimenti la RLS viene **bypassata**. L'avviso è mostrato in UI.
- Il filtraggio effettivo delle righe è responsabilità delle **policy Postgres** e non è
  unit-testabile senza un Postgres reale.

---

## Esecuzione dei test

I test del core usano **SQLite in-memory**, quindi non richiedono alcun database esterno
né credenziali.

```powershell
pytest
```

Output atteso: tutti i test **verdi** (103 test).

I test coprono:

- reflection dello schema, `list_tables` e `detect_foreign_keys` su tabelle in relazione FK;
- `compile_select` con join automatico + filtro parametrico (incluso `in` multi-valore)
  e verifica che i valori siano *bound* (no SQL injection);
- `insert` / `update` / `delete` sulla `main_table`;
- `save_master_detail` con **rollback** corretto quando una detail-op fallisce;
- CRUD del metadata store (connessioni/applicazioni/definizioni) su SQLite temporaneo;
- round-trip delle password col backend di fallback **Fernet** (il keyring reale non
  viene toccato nei test) e verifica che il vault su disco sia cifrato;
- Sheet: round-trip della definition `kind='sheet'`, `compile_select` da query-spec salvata
  (join + lookup read-only), salvataggio batch (insert/update/delete) in transazione con
  **rollback** su errore, e verifica che le colonne related **non** vengano scritte;
- **optimistic locking**: conflitto rilevato (core + batch) con rollback e nessuna scrittura;
- **valutatore di formule**: calcolo corretto e rifiuto di espressioni non ammesse;
- **validazione di cella**: regole per colonna (required, range, email, regex, Luhn, ecc.);
- Form: round-trip definition `kind='form'`, default sui nuovi record, validazione che blocca
  il salvataggio, submit rule cross-field, form rule (hide/disable), available values con
  **label ≠ value** (salva l'id), salvataggio con **optimistic locking**, e attachment
  (upload → metadati nel campo testo + file su disco, delete del record con **cascade**);
- Report: round-trip definition `kind='report'` (builder e custom SQL), parametro multi-valore
  → `WHERE IN` con bind, parametro **a cascata** (opzioni dipendenti dal padre), filtri
  **AND/OR annidati**, aggregazione **summary/pivot** corretta, full-text che ricalcola i totali,
  **SQL custom read-only** (scritture rifiutate) con bind-param; `session_settings` sul core;
- Master-detail: round-trip `kind='master_detail'`, la detail query deve avere **un solo**
  parametro, rilevamento FK detail→master, caricamento dei soli detail collegati, **salvataggio
  atomico** one-to-many (errore su un detail → rollback del master), **PK del master nuovo
  propagata** alle FK dei detail, many-to-many via giunzione (related non scritta), e
  **optimistic locking** con rollback totale;
- Webhooks: dispatch eventi CRUD (no-op senza dispatcher; created/updated/deleted col dispatcher),
  CRUD config con **URL come segreto** (non nel DB), rendering dei tre *flavor* del body
  (`{{x}}`/`:formatted`/`:bare`) e template Slack/Discord JSON-validi, invio col body/eventi
  giusti, filtro eventi e **webhook che fallisce senza propagare eccezioni**;
- RLS: persistenza dell'identità locale, `session_settings` per `app.current_user_email` solo su
  Postgres con identità (ignorato altrove), flag `rls` su Sheet/Form con round-trip;
- smoke test dell'app NiceGUI: registrazione delle route e bootstrap dello stato.

---

## Esempio d'uso del core

```python
from dbvisual.core import (
    ConnectionConfig, build_engine,
    reflect_schema,
    Column, Related, Filter, Param, QuerySpec,
    compile_select,
)

engine = build_engine(ConnectionConfig(dialect="sqlite", database="app.db"))
metadata = reflect_schema(engine)

spec = QuerySpec(
    main_table="orders",
    columns=[
        Column(table="orders", name="id", alias="order_id"),
        Column(table="customers", name="name", alias="customer"),
    ],
    related=[Related(table="customers", local_col="customer_id", remote_col="id")],
    filters=[Filter(column=Column(table="customers", name="city"), op="eq", param="city")],
    params=[Param(name="city", type="string")],
)

stmt = compile_select(spec, metadata, {"city": "Rome"})
with engine.connect() as conn:
    rows = conn.execute(stmt).mappings().all()
```

---

## Roadmap

- **Fase 1 — Core** ✅ connections, introspect, queryspec, compiler, crud.
- **Fase 2 — Shell + Connessioni + Schema** ✅ metadata store, cifratura credenziali,
  guscio NiceGUI, gestione connessioni e browser schema.
- **Fase 3 — Sheet** ✅ griglia Excel-like (`ui.aggrid`) editabile, salvataggio batch
  transazionale con **optimistic locking**, validazione di cella, campi calcolati/totali,
  copia/incolla TSV ed export CSV.
- **Fase 4 — Form** ✅ record singolo (prev/next), input tipizzati, available values
  (label ≠ value), default, validazione, submit/form rules, attachment, optimistic locking.
- **Fase 5 — Report** ✅ sola lettura: parametri multi-valore/cascata, filtri AND/OR annidati,
  grafici summary/pivot e time-series (`ui.echart`), query custom SQL read-only, export CSV.
- **Fase 6 — Master-detail** ✅ master (form) + detail (grid) legati dalla PK, salvataggio
  **atomico** one-to-many e many-to-many con propagazione PK e optimistic locking.
- **Fase 7 — Automation / Webhooks** ✅ dispatch eventi CRUD dal core, webhook HTTP POST non
  bloccanti, body default/custom (flavor `{{x}}`/`:formatted`/`:bare`), URL come segreto.
- **Fase 8 — Row-Level Security (PostgreSQL)** ✅ identità locale + flag RLS su form/sheet
  (solo Postgres) via `app.current_user_email`; policy delegate a Postgres.

Dettagli architetturali completi in [docs/spec.md](docs/spec.md).
