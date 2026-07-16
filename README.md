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

## Esecuzione dei test

I test del core usano **SQLite in-memory**, quindi non richiedono alcun database esterno
né credenziali.

```powershell
pytest
```

Output atteso: tutti i test **verdi** (28 test).

I test coprono:

- reflection dello schema, `list_tables` e `detect_foreign_keys` su tabelle in relazione FK;
- `compile_select` con join automatico + filtro parametrico (incluso `in` multi-valore)
  e verifica che i valori siano *bound* (no SQL injection);
- `insert` / `update` / `delete` sulla `main_table`;
- `save_master_detail` con **rollback** corretto quando una detail-op fallisce;
- CRUD del metadata store (connessioni/applicazioni/definizioni) su SQLite temporaneo;
- round-trip delle password col backend di fallback **Fernet** (il keyring reale non
  viene toccato nei test) e verifica che il vault su disco sia cifrato;
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
- **Fase 3 — Sheet**: griglia Excel-like (`ui.aggrid`).
- **Fase 4 — Form**: record singolo, validazione, campi condizionali.
- **Fase 5 — Report**: tabellare + grafici (`ui.echart`).
- **Fase 6 — Master-detail**: aggiornamento multi-tabella in transazione.

Dettagli architetturali completi in [docs/spec.md](docs/spec.md).
