# DB Visual Builder — Specifiche

Applicazione **locale** in Python per costruire *form di data-entry, sheet (griglie) e report*
su database esistenti, in stile Visual DB, ma **self-contained**: si installa e gira sulla
macchina dell'utente. Nessun cloud, nessun account remoto, nessun multi-tenant.

---

## 1. Obiettivi

- Software installabile e **eseguito in locale** su una singola macchina (Windows / Linux / macOS).
- **BYOD (Bring Your Own Database)**: si connette a DB *già esistenti* dell'utente.
- Copre i tre pilastri di Visual DB: **Form**, **Sheet**, **Report**.
- **Architettura aperta e multi-DB**: PostgreSQL, MySQL/MariaDB, SQL Server, Oracle, SQLite.
- Concetto centrale: tutto è generato da una **query-spec** (JSON). Form/Sheet/Report sono
  soltanto *render* diversi della stessa spec.
- **Layout moderno**: interfaccia pulita, griglie **Excel-like**, **grafici embedded**, e
  copia/incolla di tabelle, grafici e query (vedi sezione 6).

## 2. Non-obiettivi (esplicito)

- Prodotto cloud / SaaS.
- Multi-tenant, fatturazione, account remoti.
- Sincronizzazione o storage in cloud dei dati utente.
- Sostituire lo strumento di amministrazione del DB.

> Nota: i *database target* possono risiedere in remoto (es. un Postgres su un altro server),
> ma **l'applicazione** e i suoi metadati stanno sempre in locale.

## 3. Modello concettuale

Non esistono "form" e "report" come entità dati distinte. Esiste una **query-spec**:

- `main_table` — tabella principale (l'unica aggiornabile in form/sheet)
- `related[]` — tabelle correlate via foreign key (sola lettura)
- `columns[]` — colonne selezionate con alias
- `filters[]` — condizioni parametrizzate
- `params[]` — parametri (con supporto valori multipli e cascata)

Un **unico compilatore** trasforma la query-spec in `sqlalchemy.select()`. Tutto il resto è UI.

## 4. Architettura & moduli

```
dbvisual/
  core/
    connections.py   # crea Engine SQLAlchemy per dialetto; pool; test connessione
    introspect.py    # reflect di tabelle/colonne/tipi; rilevamento FK
    queryspec.py     # modelli Pydantic della query-spec (JSON serializzabile)
    compiler.py      # query-spec -> sqlalchemy.select()   [CUORE del sistema]
    crud.py          # insert/update/delete generico; transazioni (master-detail)
  meta/
    store.py         # persistenza locale (SQLite) di connessioni + definizioni
    models.py        # schema del metadata store
    secrets.py       # cifratura credenziali DB (keyring o Fernet)
  api/
    main.py          # FastAPI su 127.0.0.1
    routers/         # /connections /schema /query /records /apps
  ui/                # front-end web servito in locale (React) — fase successiva
  cli.py             # entrypoint: avvia il server locale e apre il browser
```

## 5. Stack tecnico (deciso)

- **Python** ≥ 3.11
- **Astrazione DB**: SQLAlchemy Core **2.0** (non l'ORM) — introspezione via `inspect()` /
  `MetaData.reflect()`. È il layer che rende il tutto DB-agnostico.
- **Backend**: FastAPI + Uvicorn, in ascolto **solo su `127.0.0.1`** (non esposto in rete).
- **Validazione**: Pydantic v2 (anche per la query-spec).
- **Metadata store**: SQLite locale, file in cartella utente
  (`~/.dbvisual/metadata.db` o equivalente `platformdirs`).
- **Credenziali DB**: `keyring` (portachiavi OS) con fallback a file cifrato `cryptography.Fernet`.
- **Front-end**: web UI servita in locale da FastAPI (browser su `localhost`), **React + TypeScript**.
  - **Griglia Excel-like**: Glide Data Grid (licenza MIT, editing inline, selezione a range,
    copia/incolla stile Excel, alte prestazioni su molte righe). Alternativa: AG Grid Community
    (attenzione: fill-handle e range-selection avanzati sono Enterprise).
  - **Grafici embedded**: Apache ECharts (Apache-2.0): colonne/barre, torta/ciambella, treemap,
    scatter/bubble, linea, choropleth, time-series con finestra scorrevole. Export come PNG/SVG.
  - **Layout/UI**: componentistica moderna (es. shadcn/ui + Tailwind) per interfacce pulite.
- **Packaging**: eseguibile via `pip install .` + comando `dbvisual`; opzionale bundle
  PyInstaller per distribuzione senza Python.

### Driver per DB (URL SQLAlchemy)

| DB | Driver | URL |
|---|---|---|
| PostgreSQL | `psycopg` (v3) | `postgresql+psycopg://` |
| MySQL/MariaDB | `PyMySQL` | `mysql+pymysql://` |
| SQL Server | `pyodbc` | `mssql+pyodbc://` |
| Oracle | `oracledb` | `oracle+oracledb://` |
| SQLite | built-in | `sqlite:///path` |

## 6. Requisiti UI/UX

Layout moderno, pensato per l'uso quotidiano da parte di utenti non tecnici.

**Griglie Excel-like (Sheet)**
- Editing inline delle celle con validazione al volo.
- Selezione a range, navigazione da tastiera, fill-handle dove possibile.
- Raggruppamento, ordinamento, filtro e ricerca full-text as-you-type.
- Styling condizionale (colora la cella in base al valore).
- Salvataggio a lotti (batch) delle modifiche in transazione.

**Grafici embedded (Report)**
- Grafici incorporati direttamente nella pagina del report (non finestre separate).
- Tipi: colonna/barra, torta/ciambella, treemap, scatter/bubble, linea, choropleth, time-series.
- Interazione: filtro, pivot, zoom; time-series con finestra temporale scorrevole.

**Copia / incolla (interoperabilità)**
- **Tabelle**: copiare una selezione dalla griglia verso Excel/foglio (formato TSV) e
  incollare dati tabellari da Excel dentro la griglia.
- **Grafici**: copiare/esportare il grafico come immagine (PNG/SVG).
- **Query**: copiare/esportare la query (SQL generato) e re-importare una query-spec.

**Layout generale**
- Interfaccia pulita e responsive; navigazione tra Connessioni, Applicazioni, Form, Sheet, Report.
- Editor visuale della query-spec (query builder) con join automatici da FK.

## 7. Sicurezza (contesto locale)

- Server in bind esclusivo su `127.0.0.1`; nessuna porta esposta all'esterno.
- Credenziali dei DB **mai in chiaro** su disco: usare il portachiavi di sistema.
- Tutte le query parametrizzate con bind-param (no string concatenation → no SQL injection).

## 8. Funzionalità per fasi

- **Fase 1 — Core**: connections, introspect, queryspec, compiler, crud + smoke test.
- **Fase 2 — API**: FastAPI con endpoint schema/query/records + metadata store + cifratura credenziali.
- **Fase 3 — Sheet**: griglia Excel-like (editing, batch-save, copia/incolla, styling condizionale).
- **Fase 4 — Form**: record singolo, tipi di input, validazione, campi condizionali (hide/disable).
- **Fase 5 — Report**: tabellare + grafici ECharts embedded (raggruppa/ordina/filtra, export immagine).
- **Fase 6 — Master-detail**: aggiornamento multi-tabella in transazione.

## 9. Requisiti non funzionali

- Nessuna dipendenza da servizi esterni per funzionare.
- Deve avviarsi con un singolo comando e aprire l'interfaccia nel browser.
- Codice tipizzato (type hints), testabile in isolamento (SQLite in-memory per i test del core).