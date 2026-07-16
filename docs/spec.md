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

**Applicazione monolitica**: un solo codebase Python, un solo processo, un solo
eseguibile. Nessuna separazione frontend/backend, nessun build JS, nessuna API HTTP
da mantenere. La UI è scritta in **NiceGUI** (Python puro) e lo stesso codice gira sia
come finestra **desktop nativa** (`ui.run(native=True)`) sia come **web app** locale
(`ui.run()`, bind su `127.0.0.1`).

```
dbvisual/
  core/                # layer DB-agnostico (Fase 1)
    connections.py     # crea Engine SQLAlchemy per dialetto; pool; test connessione
    introspect.py      # reflect di tabelle/colonne/tipi; rilevamento FK
    queryspec.py       # modelli Pydantic della query-spec (JSON serializzabile)
    compiler.py        # query-spec -> sqlalchemy.select()   [CUORE del sistema]
    crud.py            # insert/update/delete generico; transazioni (master-detail)
  meta/                # persistenza locale (Fase 2)
    store.py           # persistenza locale (SQLite) di connessioni + definizioni
    models.py          # schema del metadata store (SQLAlchemy Core)
    secrets.py         # cifratura credenziali DB (keyring o Fernet)
  app/                 # UI monolitica NiceGUI (Fase 2+)
    shell.py           # layout: header + navigazione laterale
    main.py            # costruzione app + ui.run (desktop/web)
    pages/             # una pagina per sezione (connections, applications, ...)
    components/        # widget riutilizzabili
    cli.py             # comando `dbvisual`: avvia l'app
main.py                # entrypoint (--mode desktop | web)
```

## 5. Stack tecnico (deciso)

- **Python** ≥ 3.11
- **Astrazione DB**: SQLAlchemy Core **2.0** (non l'ORM) — introspezione via `inspect()` /
  `MetaData.reflect()`. È il layer che rende il tutto DB-agnostico.
- **UI = NiceGUI** (Python puro): applicazione monolitica, nessun frontend/backend separato,
  nessun build JS. Lo stesso codice gira **desktop nativo** (`ui.run(native=True)`, via
  pywebview) o **web** locale (`ui.run()`, bind esclusivo su `127.0.0.1`).
  - **Griglia Excel-like**: `ui.aggrid` (AG Grid) — editing inline, ordinamento, filtro,
    selezione a range.
  - **Grafici embedded**: `ui.echart` (Apache ECharts, Apache-2.0): colonne/barre,
    torta/ciambella, treemap, scatter/bubble, linea, choropleth, time-series con finestra
    scorrevole. Export come PNG/SVG.
  - **Layout/UI**: componenti NiceGUI con classi Tailwind per interfacce pulite e responsive.
- **Validazione**: Pydantic v2 (anche per la query-spec).
- **Metadata store**: SQLite locale, file in cartella utente
  (`~/.dbvisual/metadata.db` o equivalente `platformdirs`).
- **Credenziali DB**: `keyring` (portachiavi OS) con fallback a file cifrato `cryptography.Fernet`.
- **Packaging**: eseguibile portabile con **`nicegui-pack`** (basato su PyInstaller);
  installabile anche via `pip install .` + comando `dbvisual`.

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

**Griglie Excel-like (Sheet)** — `ui.aggrid`
- Editing inline delle celle con validazione al volo.
- Selezione a range, navigazione da tastiera, fill-handle dove possibile.
- Raggruppamento, ordinamento, filtro e ricerca full-text as-you-type.
- Styling condizionale (colora la cella in base al valore).
- Salvataggio a lotti (batch) delle modifiche in transazione.

**Grafici embedded (Report)** — `ui.echart`
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

- In modalità web, bind esclusivo su `127.0.0.1`; nessuna porta esposta all'esterno.
- Credenziali dei DB **mai in chiaro** su disco: usare il portachiavi di sistema
  (fallback a file cifrato con `cryptography.Fernet`).
- Tutte le query parametrizzate con bind-param (no string concatenation → no SQL injection).

## 8. Funzionalità per fasi

- **Fase 1 — Core** *(FATTA, 16 test verdi)*: connections, introspect, queryspec, compiler, crud.
- **Fase 2 — Shell + Connessioni + Schema** *(FATTA, 28 test verdi)*: guscio NiceGUI, metadata store,
  cifratura credenziali, gestione connessioni e browser dello schema.
- **Fase 3 — Sheet** *(FATTA, 51 test verdi)*: griglia Excel-like `ui.aggrid` editabile a partire
  da uno sheet salvato (definition `kind='sheet'`); editing solo sulla `main_table`, colonne related
  in sola lettura, salvataggio batch transazionale, copia/incolla TSV ed export CSV. Arricchimenti:
  optimistic locking, validazione di cella e campi calcolati/totali; query builder con join
  "molti → uno" validati (vedi §10).
- **Fase 4 — Form** *(FATTA, 64 test verdi)*: record singolo con navigazione prev/next, tipi di input e *available values*
  (label ≠ value), default, validazione per campo, *submit rules* cross-field, *form rules*
  condizionali e **attachment fields** (vedi §10).
- **Fase 5 — Report**: tabellare + grafici `ui.echart` embedded (raggruppa/ordina/filtra, export immagine);
  parametri multi-valore e a cascata, filtri AND/OR annidati, summary/pivot chart e time-series con zoom (vedi §10).
- **Fase 6 — Master-detail**: master (form) + detail (grid) legati dalla PK del master, commit
  atomico; copre one-to-many e many-to-many (vedi §10).
- **Fase 7 — Automation / Webhooks**: su create/update/delete invia un webhook HTTP POST (JSON)
  a URL configurati (Zapier/Slack/Discord/endpoint proprio); dispatch opzionale dal core, invio
  non bloccante; config per sheet/form nel metadata store; placeholder `{{campo}}` / `:formatted`
  / `:bare`; URL trattati come segreti (vedi §10).
- **Fase 8 — Row-Level Security (PostgreSQL)** *(predisposta, non implementata)*: RLS delegata a
  Postgres (policy SQL dell'utente); dbvisual passa l'identità via `SET app.current_user_email`;
  predisposizione additiva `session_settings` su `core/connections.py` (vedi §10).

## 9. Requisiti non funzionali

- Nessuna dipendenza da servizi esterni per funzionare.
- Deve avviarsi con un singolo comando, come finestra desktop nativa o come web app locale.
- Codice tipizzato (type hints), testabile in isolamento (SQLite in-memory per i test del core).

## 10. Dettagli funzionali per fase

### Query builder (condiviso — Fasi 3/4/5)

**Direzione dei join: "molti → uno"**
- La **main table** sta sempre sul lato **"molti"**; le tabelle related si aggiungono **solo**
  seguendo le FK verso il lato **"uno"**. Una related è ammessa **solo se** è sul lato "uno" di
  una relazione con una tabella **già presente** nella query.
- Garantisce **una sola riga per record della main** (niente duplicati; `count` e aggregazioni
  corretti).
- Il query builder **valida** la direzione usando `core.introspect.detect_foreign_keys` e
  **blocca** l'aggiunta di una related che starebbe sul lato "molti".
- Solo la **main table è aggiornabile**; le related sono **read-only**.
- *(Impatto potenziale sul core: eventuale helper di validazione della direzione FK; le
  informazioni necessarie sono già esposte da `detect_foreign_keys`.)*

**Troubleshooting PostgreSQL — "table has no primary keys"**
- Per rilevare PK e constraint, l'utente di connessione deve avere il privilegio **`REFERENCES`**
  (oltre a `SELECT`). Esempio:
  `GRANT SELECT, REFERENCES ON ALL TABLES IN SCHEMA <schema> TO <utente>;`
- Il messaggio **"table has no primary keys"** è tipicamente un problema di **permessi**, non di
  schema: verificare il grant sopra.

### Fase 3 — Sheet: arricchimenti

**Optimistic locking (concorrenza)**
- Al salvataggio non si devono sovrascrivere modifiche fatte da altri nel frattempo:
  l'update di un record deve **fallire segnalando un conflitto** se il record è cambiato
  dopo il caricamento.
- Schema BYOD: non si può assumere una colonna di versione. Strategia di default:
  `UPDATE ... WHERE PK = :pk AND <colonne_modificate> = <valori_originali>`. Se l'update
  interessa **0 righe** → **conflitto**: l'utente ricarica il record e riprova.
- Se lo schema espone una colonna di versione / `updated_at`, usarla come guardia al posto
  del confronto sui valori originali.
- **Impatto sul core** (retro-compatibile con l'API esistente): `crud.update_record` riceve
  un parametro **opzionale** (es. condizioni di guardia / valori attesi) per aggiungere le
  clausole `WHERE` sopra; senza il parametro il comportamento resta invariato.

**Validazione a livello cella**
- Regole configurabili per colonna: obbligatorio, min/max numerico, email, telefono,
  regex, lunghezza.
- Le celle non valide sono marcate visivamente (bordo/sottolineatura rossa) con messaggio.
- Il **salvataggio è bloccato** finché tutti gli errori non sono corretti.

**Campi calcolati e totali**
- Colonne **formula** in stile Excel: espressione che referenzia altre colonne della stessa
  riga, ricalcolata al volo quando cambiano le dipendenze.
- **Totali di colonna** (somma/media/conteggio) in **riga fissa**, aggiornati istantaneamente
  a ogni modifica e coerenti con la ricerca/filtro attivi.
- Motore di formule **limitato e sicuro** (nessun `eval` arbitrario).
- I campi calcolati sono di **sola visualizzazione** se non mappati a una colonna reale.

### Fase 3 — Sheet: backlog (documentato, NON in questa fase)
- Viste **private / condivise / bloccate** (sort/filter/group per utente vs globali).
- **Snapshot** moment-in-time esportabili come HTML autocontenuto o Excel.

> La **row-level security** è ora tracciata a parte come **Fase 8** (vedi sotto).

### Fase 4 — Form

**Navigazione record**
- Un form mostra i record di una query **uno alla volta** (naviga **prev/next**).
- Main table **aggiornabile**, colonne lookup **read-only**.
- **Query parameter** per selezionare quale record caricare.

**Tipi di input per tipo dato**
- **Testo**: single-line, multiline, formatted, radio.
- **Numero**: textbox numerico.
- **Data**: date picker.
- **Booleano**: checkbox / radio.
- **Dropdown**: quando la colonna ha *available values*.

**Available values (valori ammessi)**
- Sorgenti: valori **esistenti** della colonna, da **tabella**, da **query**, **lista manuale**.
- Supporto **LABEL ≠ VALUE**: il dropdown mostra un'etichetta leggibile (es. nome dipendente)
  ma **salva l'ID** nel DB.
- Opzione **"consenti nuovi valori"** (l'utente può inserire un valore non in lista).

**Default value**
- Valore predefinito per campo, applicato se l'utente non compila.

**Validazione per campo** (riusa il motore di validazione dello Sheet, §Fase 3)
- required, min/max numerico, min/max lunghezza, caratteri ammessi/vietati, regex, email,
  telefono, zip, URL, carta di credito, e vincoli su **date** (non prima/dopo, oggi o dopo,
  data di nascita, ecc.).

**Submit rules (validazione cross-field)**
- Regole a livello di **intero form** (es. "almeno uno tra due campi compilato"), **distinte**
  dalla validazione del singolo campo. Bloccano il **submit** se non soddisfatte.

**Form rules (logica condizionale)**
- Abilita / disabilita / nascondi campi in base al valore di altri campi.

### Fase 4 — Attachment fields (decisione architetturale)

> Introdotti nei **Form** (Fase 4) e **retro-applicati agli Sheet** (Fase 3).

- Il **file non va nel database**. Nel DB si salva **solo un campo TESTO** con i **metadati**
  dell'allegato (`id`, `filename`, `content_type`, `size`) come **JSON**.
- Il **contenuto** del file sta su **disco locale** (app locale, nessun cloud), in una
  **cartella allegati dedicata** dell'app (via `platformdirs`), organizzata per
  **applicazione/record**.
- Operazioni: **upload, download, delete**.
- Alla **cancellazione di un record** i relativi file allegati vengono eliminati (**cascade**).
- Un **campo testo esistente** può essere **marcato come "attachment"**.

### Fase 5 — Report: precisazioni

**Parametri di query**
- **Multi-valore** (es. più stati contemporaneamente) e **a cascata** (la scelta di un
  dropdown determina i valori disponibili nel successivo).
- **UI di prompting**: pannello parametri mostrato prima/insieme al report; ogni parametro
  ha il proprio input (es. select multipla); i parametri a cascata si aggiornano al cambio
  del parametro padre.

**Filtri compositi**
- Condizioni **AND/OR annidate**, mostrate in forma **gerarchica** (albero/gruppi) per
  evitare ambiguità di interpretazione.

**Grafici**
- **Summary / pivot chart**: grafici che **aggregano** i dati e plottano gli aggregati
  (es. vendite per Prodotto sull'asse categorie e Regione sulle serie), distinti dai grafici
  "grezzi" sui valori riga-per-riga.
- **Time-series** con **zoom** e finestra temporale scorrevole (confermato, già previsto in §6).

### Fase 6 — Master-detail (meccanismo)

- **Due query**: una per il **MASTER** (form normale) e una per i **DETAIL** (grid).
- La query **detail** ha **esattamente un parametro**, valorizzato con la **PK del master**:
  carica **solo** i detail del master corrente.
- Sui detail: **insert / update / delete**.
- **Commit** di master + detail in **UNA transazione atomica** (via `crud.save_master_detail`).
- Copre **one-to-many** (FK nel lato "molti") e **many-to-many** (tabella di **giunzione** con
  due FK; gestibile da entrambe le prospettive).

### Fase 7 — Automation / Webhooks

**Scopo**
- Quando un record viene **creato / aggiornato / eliminato**, inviare un **webhook HTTP POST**
  (JSON) a un URL configurato (Zapier, Slack, Discord, o endpoint proprio).
- **Contesto locale**: i webhook partono dalla macchina dove gira dbvisual, che deve avere rete
  in **uscita** verso i servizi target. **Nessun server in ingresso**: solo POST in uscita.

**Aggancio agli eventi**
- Gli eventi si generano dal layer **`core.crud`** (insert/update/delete). Meccanismo di
  **dispatch** con hook/callback **opzionali registrabili**, senza rompere API/test esistenti
  del core.
- L'invio HTTP è **non bloccante** e non deve far fallire il salvataggio se il webhook fallisce
  (log dell'errore, **retry opzionale**).

**Configurazione (per sheet o form)**
- Nome, URL, uno o più eventi (`created` / `updated` / `deleted`), formato body.
- Persistita nel **metadata store**, legata alla definition. Bottone **"Test"**.

**Body JSON con placeholder** (handlebars sui campi della query), tre "flavor":
- `{{campo}}` → valore **JSON valido** (numeri, booleani, stringhe tra virgolette).
- `{{campo:formatted}}` → **stringa formattata** leggibile, sempre tra virgolette (fallback = raw).
- `{{campo:bare}}` → **testo puro senza virgolette** (per inserimento dentro stringhe, es.
  Slack/Discord).
- Body di **default** (auto-include tutti i campi della query, si adatta se cambiano) + body
  **custom**. Esempi custom per Slack (`{"text": "…"}`) e Discord (`{"content": "…"}`) usando
  `:bare` per restare JSON valido.

**Sicurezza**
- Gli URL webhook possono contenere token: trattarli come **segreti** (non loggarli in chiaro,
  valutare storage cifrato come per le password).

### Fase 8 — Row-Level Security (PostgreSQL) [predisposta, non implementata]

**Modello**
- La RLS **non è implementata dall'applicazione**: è **delegata a PostgreSQL**. L'utente crea le
  policy con SQL (`CREATE POLICY ... USING / WITH CHECK`) e abilita la RLS sulla tabella
  (`ALTER TABLE ... ENABLE ROW LEVEL SECURITY`). dbvisual si limita a **passare l'identità**
  dell'utente corrente al database.
- Disponibile **solo per PostgreSQL**. Altri database non supportati per la RLS.

**Meccanismo**
- Postgres filtra le righe in base a `current_setting('app.current_user_email')`.
- dbvisual, a ogni sessione/connessione, esegue `SET app.current_user_email = <email>`.

**Prerequisiti**
- **Identità utente**: oggi l'app è locale **single-user, senza login**. La RLS richiede
  un'identità (email) da passare al DB. Decisione **rimandata**: eventuale login locale in cui
  l'utente dichiara la propria email. Finché non c'è identità, la RLS resta **inattiva**.
- **Connessione**: deve usare un ruolo Postgres **NON superuser** e **NON owner** della tabella
  (superuser/owner **bypassano** la RLS). Requisito di sicurezza.

**Predisposizione additiva (da fare ora, non rompe API/test esistenti)**
- `core/connections.py`: parametro **opzionale** `session_settings` (mappa chiave→valore) che, a
  ogni apertura di connessione, esegue i corrispondenti `SET` (utile in generale: `timezone`,
  `search_path`, `statement_timeout`, e in futuro `app.current_user_email`). Default: nessuno.
- Livello applicativo: concetto astratto e **opzionale** di **"identità corrente"** (per ora
  sempre vuota = single-user); se valorizzata, verrebbe passata come session-setting
  `app.current_user_email` sulle connessioni Postgres.

**Non in questa fase**: schermata di login, gestione utenti, checkbox RLS su form/sheet,
enforcement lato app.