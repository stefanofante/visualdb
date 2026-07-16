# dbvisual

Applicazione **locale** e self-contained per costruire **form, sheet (griglie) e report**
su database esistenti, in stile Visual DB. Gira interamente sulla macchina di installazione:
nessun cloud, nessun account remoto, nessun multi-tenant. I database *target* possono
essere locali o remoti, ma l'app e i suoi metadati restano sempre in locale.

Concetto centrale: tutto è generato da una **query-spec** (JSON). Form, sheet e report
sono soltanto *render* diversi della stessa specifica.

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

## Esecuzione dei test

I test del core usano **SQLite in-memory**, quindi non richiedono alcun database esterno
né credenziali.

```powershell
pytest
```

Output atteso: tutti i test **verdi**.

I test coprono:

- reflection dello schema, `list_tables` e `detect_foreign_keys` su tabelle in relazione FK;
- `compile_select` con join automatico + filtro parametrico (incluso `in` multi-valore)
  e verifica che i valori siano *bound* (no SQL injection);
- `insert` / `update` / `delete` sulla `main_table`;
- `save_master_detail` con **rollback** corretto quando una detail-op fallisce.

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

- **Fase 1 — Core** ✅ (questo pacchetto)
- **Fase 2 — API**: FastAPI su `127.0.0.1`, metadata store SQLite, cifratura credenziali.
- **Fase 3 — Sheet**: griglia CRUD.
- **Fase 4 — Form**: record singolo, validazione, campi condizionali.
- **Fase 5 — Report**: tabellare + grafici.
- **Fase 6 — Master-detail**: aggiornamento multi-tabella in transazione (UI).
