# PIANO MVP — primo programma girabile (draft v0.1)

> Ordine concreto di costruzione del codice, dal repo vuoto al primo
> MVP funzionante.
>
> **Definizione di "MVP girabile"**: una persona può accedere all'app
> via browser, vedere l'elenco delle corse commerciali importate dal
> PdE, e navigare le 5 dashboard (anche se solo "scaffolding" per le
> prime 4). È il **primo punto di valore concreto** del progetto.
>
> Documento di riferimento: questo non è un'estensione di tutto, è
> il **minimo onesto** che dimostra che la macchina funziona.

---

## 1. Definizione di MVP

### Cosa fa l'MVP v1

| Feature | Stato MVP | Note |
|---------|-----------|------|
| Login / logout | ✅ | JWT, 2 utenti seed (admin + 1 pianificatore) |
| Schema DB completo (31 tabelle) | ✅ | Migrazione Alembic 0001 applicata |
| Seed Trenord (azienda, 7 località manutenzione, 25 depot) | ✅ | Migrazione 0002 |
| Importer PdE da CLI | ✅ | Importa il file Numbers reale 14/12/25 → 12/12/26 |
| Vista corse (PIANIFICATORE_GIRO) | ✅ | Tabella paginata + filtri base |
| Vista depositi manutenzione (MANUTENZIONE) | ✅ | Lista + dettaglio inventario |
| Scaffolding 3 dashboard rimanenti | ⏸️ | Pagina vuota con menu funzionante |
| Tutto il resto | ❌ | Builder, editor giri, persone, revisioni, ecc. → v1.x |

### Cosa NON fa l'MVP v1

- **Builder giro materiale**: nessuna generazione automatica. Le tabelle `giro_*` sono vuote.
- **Builder turno PdC**: idem
- **Editor giri/turni**: nessun editor
- **Anagrafica persone**: tabella vuota, nessuna UI
- **Revisioni provvisorie**: nessuna UI
- **Notifiche**: nessuna
- **Multi-azienda reale**: solo Trenord
- **Mobile responsive**: layout desktop only
- **Deploy in produzione**: solo dev locale via Docker compose

**Filosofia**: l'MVP v1 dimostra che la pipeline `PdE Numbers → DB →
UI` funziona end-to-end. Da lì in poi, ogni feature ulteriore è
addizione, non riscrittura.

---

## 2. Ordine costruzione (passi atomici)

Ogni passo = **1 commit + 1 verifica**. Niente big bang.

### Sprint 0 — Setup repo (1-2 giorni)

| # | Cosa | Verifica |
|---|------|----------|
| 0.1 | Crea `backend/` + `pyproject.toml` + `Dockerfile` + struttura cartelle vuote | `uv sync` non errore |
| 0.2 | Crea `frontend/` + `package.json` + `vite.config.ts` + Tailwind config | `pnpm dev` apre pagina vuota |
| 0.3 | Crea `docker-compose.yml` (db + backend + frontend) | `docker compose up db` parte Postgres |
| 0.4 | Setup CI GitHub Actions: `backend-ci.yml`, `frontend-ci.yml` | CI verde su PR di prova |
| 0.5 | Crea `README.md` con quick start + link a `docs/` | leggibile |

**Output Sprint 0**: repo clonable, dev può fare `docker compose up`
e ottenere 3 container che dialogano (anche se backend e frontend
mostrano "Hello world").

### Sprint 1 — Backend skeleton (2-3 giorni)

| # | Cosa | Verifica |
|---|------|----------|
| 1.1 | `colazione/main.py` FastAPI app + `/health` endpoint | `curl localhost:8000/health` → 200 |
| 1.2 | `colazione/config.py` Pydantic Settings da env | settings caricano da `.env.local` |
| 1.3 | `colazione/db.py` async engine + session manager | connessione Postgres OK |
| 1.4 | Setup Alembic + `alembic.ini` + env.py async | `alembic upgrade head` no-op funziona |
| 1.5 | Migrazione `0001_initial_schema.py` → 31 tabelle (vedi `SCHEMA-DATI-NATIVO.md`) | `\dt` in psql mostra le 31 tabelle |
| 1.6 | Migrazione `0002_seed_trenord.py` → azienda, depots, località | conteggio righe corretto |
| 1.7 | Modelli SQLAlchemy ORM in `models/` (1 file per entità) | import senza errori |
| 1.8 | Modelli Pydantic in `schemas/` (CorsaRead, GiroRead, ecc.) | parsing test dati fixture |

**Output Sprint 1**: backend FastAPI parte, DB ha schema + seed, ORM
e schemas Pydantic pronti.

### Sprint 2 — Auth + utenti (2 giorni)

| # | Cosa | Verifica |
|---|------|----------|
| 2.1 | `colazione/auth/` (hash, JWT encode/decode, dependencies) | unit test passa |
| 2.2 | Endpoint `POST /api/auth/login` | `curl` con admin/password ritorna JWT |
| 2.3 | Endpoint `POST /api/auth/refresh` | refresh token funziona |
| 2.4 | Dependency `get_current_user` + `require_role` | endpoint protetto risponde 401/403 |
| 2.5 | Migrazione `0003_seed_users.py` → admin + pianificatore_giro_demo | login funziona via curl |

**Output Sprint 2**: auth completo lato backend.

### Sprint 3 — Importer PdE (3-4 giorni)

| # | Cosa | Verifica |
|---|------|----------|
| 3.1 | `importers/pde.py` skeleton + lettura file Numbers | apre file, conta righe |
| 3.2 | Parser singola riga → `CorsaCommercialeCreate` | unit test con fixture 1 riga |
| 3.3 | Parser composizione 9 combinazioni → `CorsaComposizioneCreate[]` | unit test |
| 3.4 | Parser periodicità testuale → `intervalli_skip`, `date_singole`, `date_extra` | unit test 5+ casi |
| 3.5 | Calcolo `valido_in_date_json` denormalizzato | unit test con totale annuo verificato |
| 3.6 | Bulk insert + transazione unica + tracking `corsa_import_run` | full import file di test (50 righe) |
| 3.7 | Idempotenza: re-import → 0 nuovi insert | test integrazione |
| 3.8 | CLI: `uv run python -m colazione.importers.pde --file ... --azienda trenord` | importa file reale 10580 corse < 30s |

**Output Sprint 3**: il file Numbers reale è importato. Conta righe DB:
`corsa_commerciale = 10580`, `corsa_composizione = 95220`,
`corsa_import_run = 1`.

### Sprint 4 — API base corse + depositi (2 giorni)

| # | Cosa | Verifica |
|---|------|----------|
| 4.1 | `api/corse.py` GET list paginato (filter: linea, direttrice, validità data) | curl ritorna JSON |
| 4.2 | `api/corse.py` GET singola corsa con composizione | dettagli OK |
| 4.3 | `api/depositi.py` GET list località manutenzione + dotazione | 7 depositi seed |
| 4.4 | `api/depositi.py` GET dettaglio deposito (inventario) | inventario corretto |
| 4.5 | OpenAPI auto-generato visibile su `/docs` | tutti gli endpoint documentati |

**Output Sprint 4**: backend espone le rotte minime. Frontend può
consumare.

### Sprint 5 — Frontend skeleton (3-4 giorni)

| # | Cosa | Verifica |
|---|------|----------|
| 5.1 | Setup React + Tailwind + shadcn/ui (componenti base: button, card, dialog, table) | `pnpm dev` mostra demo |
| 5.2 | `lib/api.ts` client typed (genera tipi da OpenAPI con `openapi-typescript`) | autocomplete API in IDE |
| 5.3 | Routing react-router-dom + auth guard | route protette |
| 5.4 | Pagina Login + form + chiamata API | login funzionante |
| 5.5 | Layout principale: sidebar + header + content area | layout OK |
| 5.6 | Sidebar dinamica per ruolo utente loggato | mostra solo voci pertinenti |
| 5.7 | Pagine "scaffolding" per tutti e 5 i ruoli (vuote ma navigabili) | navigazione fluida |

**Output Sprint 5**: app React naviga, login funziona, sidebar adatta
al ruolo.

### Sprint 6 — Dashboard MVP (3-4 giorni)

| # | Cosa | Verifica |
|---|------|----------|
| 6.1 | Dashboard PIANIFICATORE_GIRO: home con contatori | mostra n. corse, n. giri (zero) |
| 6.2 | Dashboard PIANIFICATORE_GIRO: vista PdE con tabella corse | tabella paginata + filtri funzionanti |
| 6.3 | Dashboard PIANIFICATORE_GIRO: drawer dettaglio corsa | apertura/chiusura, dati corretti |
| 6.4 | Dashboard MANUTENZIONE: home con cards per deposito | 7 cards visibili |
| 6.5 | Dashboard MANUTENZIONE: dettaglio deposito + inventario | inventario corretto da seed |

**Output Sprint 6**: 2 dashboard funzionanti su dati reali. Le altre 3
restano scaffolding "Funzionalità in arrivo".

### Sprint 7 — Test end-to-end + documentazione (1-2 giorni)

| # | Cosa | Verifica |
|---|------|----------|
| 7.1 | Test E2E con Playwright: login + visualizza corse + filtra | green su CI |
| 7.2 | Aggiorna `README.md` con istruzioni dev + screenshot | leggibile, video di 30s |
| 7.3 | Quick fix issue residue dei sprint precedenti | issue list = [] |

**Output Sprint 7**: MVP v1 completato.

---

## 3. Stima effort

| Sprint | Effort stimato | Note |
|--------|----------------|------|
| Sprint 0 — Setup | 1-2 giorni | Setup tooling |
| Sprint 1 — Backend skeleton | 2-3 giorni | Schema 31 tabelle è il pezzo grosso |
| Sprint 2 — Auth | 2 giorni | Pattern noto |
| Sprint 3 — Importer PdE | 3-4 giorni | Parser periodicità è fragile, serve attenzione |
| Sprint 4 — API base | 2 giorni | Standard CRUD |
| Sprint 5 — Frontend skeleton | 3-4 giorni | Setup + auth + navigazione |
| Sprint 6 — Dashboard MVP | 3-4 giorni | 2 dashboard reali |
| Sprint 7 — Test + docs | 1-2 giorni | |
| **TOTALE** | **17-23 giorni lavorativi** | ~3-4 settimane di lavoro full time |

**ATTENZIONE**: stime al ribasso, includono sviluppo ma non
imprevisti. Aggiungere 30% di buffer per debug e refinement = **22-30
giorni reali**, ovvero **~5-6 settimane**.

---

## 4. Cosa è in v1.x (subito dopo MVP)

In ordine di priorità, le feature da aggiungere nelle settimane post-
MVP:

### v1.1 — Builder giro materiale (Algoritmo A)
- Implementazione `domain/builder_giro/` (vedi `LOGICA-COSTRUZIONE.md` §3)
- Endpoint `POST /api/giri/build-from-pde`
- UI: bottone "Genera giri" nella dashboard PIANIFICATORE_GIRO

### v1.2 — Editor giro materiale (lettura)
- Editor con Gantt orizzontale (vedi `RUOLI-E-DASHBOARD.md` §3.4)
- Solo visualizzazione, niente edit ancora

### v1.3 — Anagrafica persone (modulo nuovo)
- Tabelle popolate da CSV import o UI
- Dashboard GESTIONE_PERSONALE attivata

### v1.4 — Builder turno PdC (Algoritmo B)
- Implementazione `domain/builder_pdc/` (vedi `LOGICA-COSTRUZIONE.md` §4)
- Endpoint `POST /api/turni-pdc/build-from-giri`
- Dashboard PIANIFICATORE_PDC attivata

### v1.5 — Editor giro/turno (scrittura)
- Drag & drop blocchi
- Validatore live
- Salvataggio modifiche

### v1.6 — Assegnazioni persone
- Calendario assegnazioni
- Logica indisponibilità → conflitti

### v1.7 — Revisioni provvisorie (Algoritmo C)
- UI nuova revisione
- Cascading PdC automatico

### v1.x — Resto (notifiche, dashboard PERSONALE, deploy prod, ecc.)

---

## 5. Definizione di "MVP completato"

L'MVP è considerato completato quando **tutte queste affermazioni sono vere**:

1. ✅ `docker compose up` parte 3 container funzionanti senza errori
2. ✅ `alembic upgrade head` applica le migrazioni 0001-0003 a DB pulito
3. ✅ `uv run python -m colazione.importers.pde --file ...` importa il file reale Trenord (10580 corse) in < 60s
4. ✅ Login da browser con admin/password funziona, ritorna JWT, e l'utente vede la dashboard appropriata
5. ✅ La dashboard PIANIFICATORE_GIRO mostra la lista delle 10580 corse importate, paginata e filtrabile per linea/direttrice
6. ✅ La dashboard MANUTENZIONE mostra i 7 depositi seed con il loro inventario (POOL_TILO incluso)
7. ✅ Tutte le altre 3 dashboard (PIANIFICATORE_PDC, GESTIONE_PERSONALE, PERSONALE_PDC) sono navigabili (anche vuote)
8. ✅ I test backend (`uv run pytest`) sono verdi: > 50 test, copertura > 70% sui moduli `importers/`, `auth/`
9. ✅ I test frontend (`pnpm test`) sono verdi: smoke test su login + 1 dashboard
10. ✅ La CI GitHub Actions è verde su `master`
11. ✅ Il `README.md` mostra come clonare, avviare, e arrivare alla schermata di login in < 5 comandi
12. ✅ Test E2E Playwright: login → vedi corse → filtra → vedi dettagli funziona end-to-end

Quando tutti i 12 sono verdi, **MVP v1 è released**. Si tagga `v0.1.0`
in git e si parte con v1.1 (builder giro).

---

## 6. Rischi noti e mitigazione

| Rischio | Probabilità | Impatto | Mitigazione |
|---------|-------------|---------|-------------|
| Parser periodicità Numbers troppo fragile | Alta | Medio | Coverage > 90% su unit test del parser. Casi reali da PdE come fixture. |
| Bulk insert lento su Postgres | Bassa | Medio | Usare `INSERT ... VALUES (...)` batch 1000, transazione unica. |
| Schema DB cambia in v1.1+ | Alta | Alto | Alembic migrazioni reversibili. Mai DROP TABLE. |
| Frontend complesso (Gantt) → ritardo | Alta | Medio | MVP v1 NON include Gantt. Solo tabella corse. Gantt arriva v1.2. |
| Numero ruoli multi → confusione | Media | Basso | Solo 2 ruoli attivi in MVP (PIANIF_GIRO + MANUTENZIONE). Altri 3 vuoti. |
| Stack tecnologico nuovo a chi lavora | Media | Medio | Stack scelto vicino al vecchio progetto (Python+FastAPI+React). Curva minimale. |

---

## 7. Decisioni rinviate (non bloccanti per MVP)

Cose che **non** servono per il MVP ma che vanno scelte prima di v1.x:

1. **Gestione file uploads** (PDF allegati a revisioni provvisorie):
   storage locale, S3 compatibile, o blob Postgres?
2. **Real-time push** (notifiche): Server-Sent Events, WebSocket, o
   polling?
3. **Audit log retention**: quanto tenere? Compressione vecchie righe?
4. **Backup DB**: pg_dump cron + S3, oppure servizio gestito?
5. **Logging strutturato**: stdout JSON + log aggregator (Loki?), o file?
6. **Hosting produzione**: VPS Hetzner / Railway / Fly.io? Decisione
   al momento del primo deploy reale.

Queste decisioni si prendono durante v1.x in `TN-UPDATE.md`.

---

## 8. Riepilogo: dove inizia FASE D

Dopo aver letto e validato questo documento, **FASE D** parte da:

> **Sprint 0, passo 0.1**: creare `backend/` + `pyproject.toml`.

Ogni passo è un commit. Ogni commit ha verifica esplicita. Aggiornare
`TN-UPDATE.md` ad ogni passo.

Quando l'utente legge "ok parti con FASE D", inizio dal passo 0.1.

---

## 9. Riferimenti

- `docs/VISIONE.md` — perché stiamo facendo questo
- `docs/STACK-TECNICO.md` — con cosa lo facciamo
- `docs/RUOLI-E-DASHBOARD.md` — quali UI servono (priorità in §6)
- `docs/LOGICA-COSTRUZIONE.md` — algoritmi da implementare in v1.1+
- `docs/SCHEMA-DATI-NATIVO.md` — DDL per migrazione 0001
- `docs/IMPORT-PDE.md` — spec Sprint 3
- `docs/MODELLO-DATI.md` v0.5 — modello concettuale
- `docs/NORMATIVA-PDC.md` — fonte verità Trenord
- `docs/METODO-DI-LAVORO.md` — come lavorare
- `TN-UPDATE.md` — diario

---

**Fine draft v0.1**. **FASE C completa**. Aspetto OK utente per
iniziare FASE D Sprint 0.
