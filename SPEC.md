# dbvisual — Specifica di architettura (SPEC)

Applicazione **locale** e self-contained per costruire **form, sheet (griglie) e report**
su database esistenti dell'utente, in stile Visual DB. Gira interamente sulla macchina di
installazione. I database *target* possono essere locali o remoti, ma l'app e i suoi
metadati restano sempre in locale. Nessun cloud, nessun account remoto, nessun multi-tenant.

---

## 1. Architettura: applicazione monolitica

- **Un solo codebase Python, un solo processo, un solo eseguibile.** Niente separazione
  frontend/backend, niente build JS, nessuna API HTTP da mantenere.
- **UI = [NiceGUI](https://nicegui.io/).** Lo stesso codice gira come:
  - **desktop nativo** — `ui.run(native=True)` (finestra pywebview);
  - **web** — `ui.run()` con bind esclusivo su `127.0.0.1`.
- **Griglie Excel-like** con `ui.aggrid` (AG Grid).
- **Grafici embedded** con `ui.echart` (Apache ECharts).
- **DB-agnostico** tramite **SQLAlchemy Core 2.0** (già implementato nel layer `core`,
  fase 1). DB supportati: **PostgreSQL, MySQL/MariaDB, SQL Server, Oracle, SQLite**.

## 2. Concetto centrale: la query-spec

Non esistono "form" e "report" come entità dati distinte: esiste una **query-spec** (JSON).
Un unico compilatore (`dbvisual.core.compiler.compile_select`) la trasforma in un
`sqlalchemy.select()`. **Form, Sheet e Report sono solo render diversi della stessa spec.**

## 3. Persistenza locale

- **Metadata store**: SQLite locale (percorso via `platformdirs`, cartella dati utente).
  Contiene connessioni, applicazioni e definizioni (query-spec serializzate).
- **Credenziali DB**: mai in chiaro. Backend primario **keyring** (portachiavi OS);
  fallback **file cifrato con `cryptography.Fernet`**, chiave nella cartella dati utente
  con permessi ristretti.

## 4. Packaging

- Eseguibile portabile con **`nicegui-pack`** (basato su PyInstaller).
- Su Windows: `multiprocessing.freeze_support()` nell'entrypoint.

## 5. Struttura del progetto

```
dbvisual/
  core/                     # FASE 1 — layer DB-agnostico (NON modificare l'API pubblica)
    connections.py          # build_engine / test_connection
    introspect.py           # reflect_schema / list_tables / get_columns / detect_foreign_keys
    queryspec.py            # modelli Pydantic della query-spec
    compiler.py             # query-spec -> sqlalchemy.select()  [cuore]
    crud.py                 # insert/update/delete + master-detail transazionale
  meta/                     # FASE 2 — persistenza locale
    models.py               # schema SQLAlchemy Core del metadata store
    store.py                # CRUD connections/applications/definitions
    secrets.py              # cifratura credenziali (keyring + fallback Fernet)
  app/                      # FASE 2 — UI NiceGUI
    shell.py                # layout: header + navigazione laterale
    main.py                 # costruzione app + ui.run
    pages/                  # una pagina per sezione (connections, ...)
    components/             # widget riutilizzabili
main.py                     # entrypoint (--mode desktop | web)
```

## 6. Fasi del progetto

| Fase | Contenuto | Stato |
| --- | --- | --- |
| 1 | **Core**: connections, introspect, queryspec, compiler, crud | ✅ FATTA |
| 2 | **Shell + Connessioni + Schema**: metadata store, secrets, UI guscio, browser schema | 🔨 QUESTA |
| 3 | **Sheet**: griglia CRUD (`ui.aggrid`) | ⬜ |
| 4 | **Form**: record singolo, validazione, campi condizionali | ⬜ |
| 5 | **Report**: tabellare + grafici (`ui.echart`) | ⬜ |
| 6 | **Master-detail**: aggiornamento multi-tabella in transazione | ⬜ |

## 7. Sicurezza (contesto locale)

- In modalità web, bind esclusivo su `127.0.0.1`: nessuna porta esposta in rete.
- Credenziali dei DB mai in chiaro su disco (keyring / Fernet).
- Tutte le query parametrizzate con bind-param (nessuna concatenazione di stringhe).
