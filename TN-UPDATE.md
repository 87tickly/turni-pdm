# TN-UPDATE — Diario del nuovo programma (greenfield)

> Questo file viene aggiornato dopo **ogni modifica** al progetto.
> È il diario operativo del nuovo programma, costruito da zero.
>
> **Predecessore archiviato**: `docs/_archivio/LIVE-COLAZIONE-storico.md`
> contiene il diario del progetto vecchio (eliminato il 2026-04-25).
> Lì si trova la storia di come ci siamo arrivati al modello dati e
> all'architettura, in caso serva un riferimento.

---

## 2026-04-25 (8) — FASE C doc 6: IMPORT-PDE.md

### Contesto

Specifica del primo importer del programma. Legge PdE Numbers/Excel
e popola corsa_commerciale + corsa_composizione. È il punto di ingresso
del sistema: senza questo, il resto della piramide non si popola.

### Modifiche

**Nuovo `docs/IMPORT-PDE.md` v0.1** (~470 righe):

- §1 Input: formati supportati (.numbers prio, .xlsx alt), 3 sheet
  Trenord (PdE RL = 10580 righe da importare; NOTE Treno e NOTE BUS
  per dopo)
- §2 Mapping completo 124 colonne PdE → schema DB:
  - identificativi (numero treno, rete, categoria, linea, direttrice)
  - geografia (origine/destinazione + CdS, orari, km, durate)
  - periodicità (testuale + flag garantito feriale/festivo)
  - 9 combinazioni stagione × giorno-tipo → corsa_composizione (95K
    record per Trenord)
  - calendario annuale (Gg_gen, Gg_feb, ..., Gg_anno)
  - aggregati (totale km, postikm, velocità commerciale)
- §3 **Algoritmo calcolo valido_in_date_json denormalizzato**:
  - parsing testo "Periodicità" (intervalli skip, date singole skip,
    date extra)
  - validazione incrociata con Gg_* per mese
  - retorna lista date ISO YYYY-MM-DD
- §4 Idempotenza:
  - chiave logica `(azienda_id, numero_treno, valido_da)` → upsert
  - SHA-256 file → skip se già importato
  - tracking corsa_import_run con n_create / n_update / warnings
- §5 Pseudo-codice top-level (transazione unica + bulk insert)
- §6 8 edge case noti (numero treno come float, date all'italiana,
  caratteri Unicode, sheet ordering, ecc.)
- §7 Performance: 10580 × 9 = 95K insert, target < 30s con bulk insert
  + transazione unica
- §8 Test (smoke + idempotenza + modifica + calcolo periodicità)
- §9 CLI: `uv run python -m colazione.importers.pde --file ... --azienda trenord`

### Stato

- Spec pronta per implementazione `backend/src/colazione/importers/pde.py`
- Anche pronta per la fixture di test (50 righe del file reale)

### Prossimo step

`docs/PIANO-MVP.md` (FASE C doc 7, ULTIMO): primo MVP girabile +
ordine costruzione codice + definizione "MVP completato". Dopo
questo, FASE C chiusa e si passa a FASE D (codice).

---

## 2026-04-25 (7) — FASE C doc 5: SCHEMA-DATI-NATIVO.md (DDL eseguibile)

### Contesto

Materializzazione di MODELLO-DATI v0.5 in DDL SQL eseguibile per
Postgres 16. Specifica per la prima migrazione Alembic
(0001_initial_schema.py).

### Modifiche

**Nuovo `docs/SCHEMA-DATI-NATIVO.md` v0.1** (~700 righe):

- §1 Convenzioni (naming, tipi, FK, indici)
- §2 Estensioni Postgres (pg_trgm)
- §3-§9 Schema in 7 strati con CREATE TABLE eseguibili:
  - Strato 0 anagrafica: azienda, stazione, materiale_tipo,
    localita_manutenzione, dotazione, depot, depot_linea_abilitata,
    depot_materiale_abilitato (8 tabelle)
  - Strato 1 corse LIV 1: corsa_commerciale, corsa_composizione,
    corsa_materiale_vuoto, corsa_import_run (4 tabelle)
  - Strato 2 giro LIV 2: giro_materiale, versione_base_giro,
    giro_finestra_validita, giro_giornata, giro_variante,
    giro_blocco (6 tabelle)
  - Strato 2bis revisioni: revisione_provvisoria,
    revisione_provvisoria_blocco, revisione_provvisoria_pdc (3 tabelle)
  - Strato 3 turno PdC LIV 3: turno_pdc, turno_pdc_giornata,
    turno_pdc_blocco (3 tabelle)
  - Strato 4 personale LIV 4: persona, assegnazione_giornata,
    indisponibilita_persona (3 tabelle)
  - Strato 5 auth/audit: app_user, app_user_ruolo, notifica,
    audit_log (4 tabelle)

Totale **31 tabelle**.

- §10 Indici secondari (FK, query frequenti, GIN su JSONB e trigram
  per cognome/nome persona)
- §11 5 vincoli consistenza come query SQL eseguibili (per test
  integrazione)
- §12 Seed iniziale Trenord:
  - 1 azienda Trenord con normativa_pdc_json completa
  - 7 localita_manutenzione (FIORENZA, NOVATE, CAMNAGO, LECCO,
    CREMONA, ISEO, POOL_TILO_SVIZZERA)
  - 25 depot Trenord (NORMATIVA §2.1)
- §13 Riepilogo numerico (record stimati: ~256k record totali in
  produzione Trenord)

### Stato

- DDL pronto per migrazione Alembic.
- 5 vincoli consistenza pronti per test integrazione.
- Seed Trenord pronti per popolamento iniziale.

### Prossimo step

`docs/IMPORT-PDE.md` (doc 6): come si legge PdE Numbers/Excel,
mapping colonne, calcolo valido_in_date denormalizzato, idempotenza.

---

## 2026-04-25 (6) — FASE C doc 4: LOGICA-COSTRUZIONE.md

### Contesto

Documento centrale degli algoritmi nativi. Tre algoritmi descritti in
modo formale + pseudo-codice + mapping a moduli Python.

### Modifiche

**Nuovo `docs/LOGICA-COSTRUZIONE.md` v0.1** (~600 righe):

**Algoritmo A — PdE → Giro Materiale**:
- Input: corse, localita_manutenzione, dotazione, giorno_tipo
- Greedy: per ogni località, costruisci catene di corse rispettando
  continuità geografica + tempo manovra + composizione coerente +
  ciclo chiuso
- Genera `corsa_materiale_vuoto` per posizionamento e rientro
- Multi-giornata + varianti calendario derivate da PdE periodicità

**Algoritmo B — Giro Materiale → Turno PdC**:
- Architettura "centrata sulla condotta" (riferimento ARCHITETTURA-
  BUILDER-V4 storico): seed produttivo (1-2 corse, 2-3h condotta) +
  posizionamento + gap handling + rientro
- 5 step: A scelta seed, B posizionamento, C gap (REFEZ in finestra),
  D rientro, E validazione
- Validazione vincoli singolo turno (NORMATIVA §11.8, §4.1, §9.2,
  §3, §6) + ciclo settimanale (§11.4, §11.5)

**Algoritmo C — Revisione provvisoria + cascading**:
- Crea `revisione_provvisoria` con causa esterna esplicita
- Modifica `giro_blocco` impattati (modifica/cancella/aggiungi)
- **Cascading**: per ogni giro modificato, crea
  `revisione_provvisoria_pdc` con stessa finestra
- Re-build automatico turni PdC nella finestra (Algoritmo B su giri-rev)
- Notifiche cross-ruolo
- Resolver query "cosa succede il giorno D?": base + override rev

**Validazione + scoring**:
- ValidatorePdC unificato in `domain/normativa/validator.py`
- Score per ranking soluzioni (n_pdc, prestazione_sotto_sfruttata,
  violazioni preferenziali §11.7)

**Mapping moduli Python**:
- `domain/builder_giro/`, `domain/builder_pdc/`, `domain/normativa/`,
  `domain/revisioni/` — tutti DB-agnostic
- Test puri in `tests/domain/`, fixtures con seed reali

**Edge case noti** (7 casi):
- Materiale pernotta fuori deposito
- Partenza senza U-numero
- CV Tirano (capolinea inversione)
- Cap 7h notturno
- MI.PG ↔ FIOz taxi obbligatorio
- Composizione mista
- POOL_TILO_SVIZZERA

### Stato

- Documento draft v0.1, ~600 righe.
- Pronto per implementazione (FASE D) ma 3 punti aperti:
  multi-giornata schema-tica, scoring seed con pesi placeholder,
  cascading re-build a maglie larghe.

### Prossimo step

`docs/SCHEMA-DATI-NATIVO.md` (FASE C doc 5): DDL SQL eseguibile.
Materializza `MODELLO-DATI.md` v0.5 in CREATE TABLE + indici + FK +
seed iniziali per Postgres 16.

---

## 2026-04-25 (5) — FASE C doc 3: RUOLI-E-DASHBOARD.md

### Contesto

Specifica dettagliata delle 5 dashboard per ruolo. Ogni ruolo ha
schermate, azioni, dati visualizzati, permessi. Documento operativo
per costruire frontend e backend coerenti.

### Modifiche

**Nuovo `docs/RUOLI-E-DASHBOARD.md` v0.1** (~530 righe):

- §1 Tabella riepilogativa 5 ruoli + ADMIN con privilegi
- §2 Schermate condivise (login, profilo, settings)
- §3 **Dashboard PIANIFICATORE_GIRO** (6 schermate):
  home, vista PdE, lista giri, editor giro (centrale, con Gantt
  orizzontale + drag&drop + valida live), revisioni, nuova revisione
- §4 **Dashboard PIANIFICATORE_PDC** (5 schermate):
  home, vista giri readonly, lista turni, editor turno PdC (centrale,
  Gantt giornaliero + validazione normativa live + pannello vincoli
  ciclo), revisioni cascading
- §5 **Dashboard MANUTENZIONE** (5 schermate):
  home, lista depositi, dettaglio deposito (inventario), spostamenti
  tra depositi, manutenzioni programmate
- §6 **Dashboard GESTIONE_PERSONALE** (6 schermate):
  home, anagrafica, scheda persona (calendario annuale + ore/sett),
  calendario assegnazioni (centrale, persone × date), indisponibilita,
  sostituzioni
- §7 **Dashboard PERSONALE_PDC** (5 schermate):
  oggi (banner + Gantt giornaliero), calendario, dettaglio turno data,
  ferie/assenze, segnalazioni
- §8 Matrix permessi cross-ruolo per 11 entita
- §9 Notifiche cross-ruolo (8 eventi tracciati)
- §10 Settings admin
- §11 Cosa NON e in v1 (dark mode, mobile native, PDF export ricco,
  WebSocket/SSE, drill-down KPI, conversazioni in-app)

### Stato

- Documento draft v0.1, ~30 schermate descritte.
- Pronto per priorizzazione in PIANO-MVP.md (doc 7).

### Prossimo step

`docs/LOGICA-COSTRUZIONE.md` (doc 4): algoritmo nativo PdE → giro
materiale → turno PdC. Riformula ALGORITMO-BUILDER.md + ARCHITETTURA-
BUILDER-V4.md in chiave nativa, senza riferimenti al codice vecchio.

---

## 2026-04-25 (4) — FASE C doc 2: STACK-TECNICO.md (scelte confermate)

### Contesto

Utente ha confermato in blocco le 6 scelte consigliate. Stack tecnico
definito.

### Modifiche

**Nuovo `docs/STACK-TECNICO.md` v1.0** (~390 righe):

Le 6 scelte:
1. Backend: **Python 3.12+**
2. Framework: **FastAPI** (async, OpenAPI auto-gen, Pydantic-native)
3. DB: **PostgreSQL 16+** (anche dev, no più SQLite-PG dual-mode)
4. Frontend: **React 18 + TypeScript + Vite**
5. UI Kit: **shadcn/ui** (Radix + Tailwind CSS)
6. Auth: **JWT custom + bcrypt**

Hosting differito (probabile VPS self-host quando arriva il momento).

**Struttura repo monorepo**:
- `backend/` (FastAPI con `src/colazione/` + `domain/` per business
  logic DB-agnostic)
- `frontend/` (Vite con routes per ruolo, non per tipo)
- `data/` (seed JSON gia presente)
- `docker-compose.yml` per dev (db + backend + frontend)
- Alembic per migrazioni schema versionate

**Tooling**:
- Backend: `uv` (package manager) + `ruff` (lint+format) + `mypy` + `pytest`
- Frontend: `pnpm` + `eslint` + `prettier` + `vitest` + `@testing-library/react`

**Convenzioni**:
- Python: type hints obbligatori, mypy strict, async ovunque
- React: function components, TanStack Query per stato server,
  Tailwind only (no CSS modules/styled-components)
- Commit: Conventional Commits in italiano

**Cosa NON useremo** (esplicito):
- Tauri (web-only per ora)
- GraphQL (REST sufficiente)
- Redis/Celery (non serve in MVP)
- Microservizi/k8s (monolite modulare)
- SSR/SSG (SPA classica)
- i18n (italiano-only)

### Stato

- Documento v1.0, completo per costruzione MVP.
- Modifiche future tracciate qui in TN-UPDATE.md.

### Prossimo step

`docs/RUOLI-E-DASHBOARD.md` (FASE C doc 3): dettaglio delle 5
dashboard, schermate per ruolo, azioni, permessi, mockup testuale.

---

## 2026-04-25 (3) — FASE C doc 1: VISIONE.md scritta

### Contesto

Primo documento architetturale del nuovo progetto. Scopo: chiarire
in modo permanente cosa stiamo costruendo, per chi, e perché. Punto
di riferimento per qualsiasi domanda di scope ("c'è dentro X?" → si
controlla qui).

### Modifiche

**Nuovo `docs/VISIONE.md` (draft v0.1)**:
- §1 Frase manifesto: sistema operativo per pianificazione
  ferroviaria nativa, dal contratto commerciale al singolo
  macchinista
- §2 Il problema reale: 3 silos disconnessi (PdE, turno materiale,
  turno PdC) cuciti con parser fragili
- §3 Cosa fa il programma: 4 funzioni primarie (importa PdE, genera
  giro, genera PdC, assegna persone) + 5a (revisioni provvisorie con
  cascading)
- §4 5 ruoli destinatari: pianificatore giro / pianificatore PdC /
  manutenzione / gestione personale / personale finale (PdC)
- §5 Cosa NON e': 6 esclusioni esplicite (no biglietteria, no real-
  time da zero, no manutenzione predittiva, no payroll, no RFI, no
  solo Trenord)
- §6 7 principi guida: costruzione non importazione, no parser
  fragili come ingresso primario, modello a piramide, multi-tenant
  giorno 1, 5 dashboard 1 modello, revisioni provvisorie tracciate,
  sviluppo iterativo
- §7 Definizione di successo (uomo davanti al monitor + scala
  industriale)
- §8 Ambito rilascio: MVP v1 → v1.0 → v1.x → v2.0 → v2.x (no date)
- §9 Riferimenti incrociati a documenti gia esistenti e in coda

### Stato

- Documento draft v0.1, ~250 righe.
- Pronto per revisione utente.

### Prossimo step

**MI FERMO QUI.** Il prossimo documento (`STACK-TECNICO.md`) richiede
decisioni dell'utente su:
- Linguaggio backend (Python? Node? Go? Rust?)
- Framework backend (FastAPI? Express? Fastify? altro?)
- Frontend (React? Vue? Svelte? Next/Remix?)
- DB primario (SQLite locale + Postgres prod come prima?)
- Hosting (Railway? Vercel? Fly.io? Cloudflare? self-host?)
- Auth (JWT? sessions? OAuth? Clerk/Auth0?)

Aspetto input dell'utente prima di scrivere STACK-TECNICO.md.

---

## 2026-04-25 (2) — FASE B completata: nuovo CLAUDE.md + .gitignore

### Contesto

CLAUDE.md vecchio era pieno di riferimenti al codice eliminato in
FASE A (server.py, FastAPI, Tauri, parser PDF, train_segment, builder
genetico, ecc.). Riscrittura completa per il nuovo progetto greenfield.

### Modifiche

**`CLAUDE.md`** completamente riscritto:
- Stato del progetto: greenfield, in scrittura specifiche
- 7 regole operative obbligatorie (lettura TN-UPDATE.md, aggiornamento
  TN-UPDATE.md dopo ogni task, METODO-DI-LAVORO.md, lettura dominio,
  manifesto greenfield, sviluppo per ruoli)
- Mappa dei documenti di dominio con "quando leggerli"
- Stato fasi A/B/C/D + lista 7 documenti FASE C
- Stack tecnologico: TBD in `docs/STACK-TECNICO.md` (FASE C doc 2)
- Glossario dominio essenziale (PdE, giro materiale, turno PdC, CV,
  PK, ACCp/ACCa, vettura, materiale vuoto, FR, S.COMP, ciclo 5+2)
- Convenzioni naming + riferimenti a tutti i .md

**`.gitignore`** aggiornato:
- Rimosse voci specifiche al vecchio (turni.db, server.log, uploads/
  hardcoded, ecc.)
- Aggiunte sezioni separate per Python e Node.js (entrambi ignorati
  finche non scegliamo lo stack)
- Strutturato per essere stack-agnostic e estendibile in FASE C

### Stato

- CLAUDE.md ora rispecchia il progetto attuale (greenfield)
- .gitignore agnostic per qualsiasi stack
- Repo pronto per FASE C (scrittura specifiche architetturali)

### Prossimo step

FASE C documento 1: `docs/VISIONE.md`. Cos'e' il programma, per chi,
cosa risolve, scope esplicito.

---

## 2026-04-25 — Greenfield reset (FASE A completata)

### Decisione

Il progetto vecchio (parser PDF Gantt centrato su `train_segment`,
backend FastAPI 60+ file Python, frontend React 1GB) è stato dichiarato
inutile dall'utente. Si parte da zero col nuovo programma nativo,
basato su:

- Logica di costruzione **PdE → giro materiale → turno PdC → personale**
- 5 dashboard separate per ruolo (pianificatori, manutenzione,
  gestione personale, personale finale)
- Modello dati a piramide v0.5 (vedi `docs/MODELLO-DATI.md`)
- Manifesto "non copiamo Trenord" — usano il loro sistema come
  ispirazione, non come template

### Cancellato in questo commit

| Categoria | Cosa | Motivo |
|-----------|------|--------|
| Backend | `server.py`, `app.py`, `api/` (18 file), `services/`, `src/` (1.2 MB di codice) | Logica vecchia centrata su parser PDF |
| Frontend | `frontend/` (~1 GB con node_modules), `static/`, `mockups/` | UI vecchia da riscrivere |
| Test | `tests/` (808 KB) | Test del codice vecchio |
| Dati runtime | `turni.db` (20 MB), `turni_backup_*.db`, `turno_materiale_treni.json`, `uploads/` (5.2 MB), `fr_stations.txt` | DB locale + dati vecchi |
| Config deploy | `Procfile`, `railway.toml`, `runtime.txt`, `.dockerignore`, `.railwayignore`, `requirements.txt`, `.env.example` | Deploy vecchio Railway |
| Script ad-hoc | `parse_turno_materiale.py`, `import_turno_materiale.py`, `debug_digits.py`, `scripts/enrich_db_*.py` | Tool 1-shot del vecchio |
| Junk | `nul`, `server.log`, `__pycache__/`, `.pytest_cache/`, `.venv/` | Cache + log |
| Config app | `config/` | Config app vecchia |

**Spazio liberato**: ~1.05 GB.

### Archiviato in `docs/_archivio/`

| Cosa | Motivo |
|------|--------|
| `LIVE-COLAZIONE-storico.md` (370 KB) | Memoria storica del progetto vecchio |
| `MIGRAZIONE-DATI.md` | Piano di migrazione DB (rinnegato — questo era progetto greenfield, non migrazione) |
| `GANTT-GUIDE.md`, `HANDOFF-*.md` (×5), `PROMPT-claude-design-*.md` (×5), `REFERENCE-*.css/.html` (×5), `PLAN-parser-refactor.md`, `claude-design-bundles/`, `stitch-mockups/` | UI vecchia (mockup, prompt, riferimenti) |
| `scripts/extract_depositi_manutenzione.py` | Utility 1-shot per estrarre depositi dal PDF (riutilizzabile se serve) |

### Tenuto (dominio + base nuovo progetto)

| Cosa | Motivo |
|------|--------|
| `docs/NORMATIVA-PDC.md` (1292 righe) | **Fonte verità** dominio Trenord |
| `docs/METODO-DI-LAVORO.md` | Framework comportamentale (vale sempre) |
| `docs/MODELLO-DATI.md` v0.5 | Modello concettuale (12 entità + manifesto) |
| `docs/ALGORITMO-BUILDER.md` | Spec algoritmo (riferimento, da riscrivere in chiave nativa) |
| `docs/ARCHITETTURA-BUILDER-V4.md` | Idea "centrata sulla condotta" (riferimento) |
| `docs/schema-pdc.md` | Schema dati turno PdC (riferimento) |
| `data/depositi_manutenzione_trenord_seed.json` | Anagrafica reale 7 depositi + 1884 pezzi |
| `CLAUDE.md` | Da **riscrivere** in FASE B per nuovo progetto |
| `.gitignore` | Da aggiornare per nuovo stack |
| `.claude/` | Config harness Claude Code |

### Stato repo dopo FASE A

```
COLAZIONE/
├── .claude/
├── .git/
├── .gitignore
├── CLAUDE.md                ← da riscrivere (FASE B)
├── TN-UPDATE.md             ← questo diario (nuovo)
├── data/
│   └── depositi_manutenzione_trenord_seed.json
└── docs/
    ├── ALGORITMO-BUILDER.md       ← riferimento
    ├── ARCHITETTURA-BUILDER-V4.md ← riferimento
    ├── METODO-DI-LAVORO.md        ← framework
    ├── MODELLO-DATI.md            ← v0.5
    ├── NORMATIVA-PDC.md           ← dominio
    ├── schema-pdc.md              ← riferimento
    └── _archivio/                 ← memoria progetto vecchio
```

### Prossimi step

- **FASE B**: riscrivere `CLAUDE.md` per il nuovo progetto
- **FASE C** (multi-commit): scrivere documentazione architetturale
  nativa, un documento per volta:
  1. `docs/VISIONE.md`
  2. `docs/STACK-TECNICO.md`
  3. `docs/RUOLI-E-DASHBOARD.md`
  4. `docs/LOGICA-COSTRUZIONE.md`
  5. `docs/SCHEMA-DATI-NATIVO.md`
  6. `docs/IMPORT-PDE.md`
  7. `docs/PIANO-MVP.md`
- **FASE D**: inizio costruzione codice (solo dopo che A+B+C sono
  chiusi e validati dall'utente)
