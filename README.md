# Colazione

> **Programma di pianificazione ferroviaria nativa** — gestisce
> l'intero ciclo dall'offerta commerciale al singolo macchinista, in
> un unico ecosistema multi-ruolo. Sviluppo iniziato il 25/04/2026
> (greenfield reset).

[![backend-ci](https://github.com/87tickly/turni-pdm/actions/workflows/backend-ci.yml/badge.svg)](https://github.com/87tickly/turni-pdm/actions/workflows/backend-ci.yml)
[![frontend-ci](https://github.com/87tickly/turni-pdm/actions/workflows/frontend-ci.yml/badge.svg)](https://github.com/87tickly/turni-pdm/actions/workflows/frontend-ci.yml)

---

## Cosa è (in 30 secondi)

```
PROPOSTA COMMERCIALE (PdE)        ← sorgente unica autorevole
        ↓
TURNO MATERIALE                   ← lo COSTRUIAMO noi (algoritmo)
        ↓
TURNO PdC                         ← lo COSTRUIAMO noi (algoritmo)
        ↓
ASSEGNAZIONE PERSONE              ← anagrafica + indisponibilità
```

Cinque dashboard separate per ruolo (Pianificatore Giro Materiale,
Pianificatore Turno PdC, Manutenzione, Gestione Personale, Personale
finale), un unico modello dati condiviso, multi-tenant
fin dal giorno 1.

Per i dettagli completi vedi [`docs/VISIONE.md`](docs/VISIONE.md).

---

## Stato attuale

**FASE D — Sprint 0: Setup repo (in corso).**

| Sprint | Stato |
|--------|-------|
| 0.1 Backend skeleton | ✅ |
| 0.2 Frontend skeleton | ✅ |
| 0.3 docker-compose.yml | ✅ |
| 0.4 GitHub Actions CI | ✅ |
| 0.5 README (questo file) | ✅ |
| 1.x Backend reale (Alembic + 31 tabelle) | ⏸️ |

Diario completo in [`TN-UPDATE.md`](TN-UPDATE.md).

---

## Quick start (sviluppo locale)

### Prerequisiti

- **macOS / Linux** (Windows: WSL2 consigliato, non testato)
- **Python 3.12** (su macOS: `brew install python@3.12`)
- **Node 20+** (su macOS: `brew install node@20`)
- **uv** (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **pnpm** (`npm install -g pnpm`)
- **Docker Desktop** o **OrbStack** (per Postgres dev)

### Setup in 5 comandi

```bash
# 1. Clona il repo
git clone https://github.com/87tickly/turni-pdm.git colazione
cd colazione

# 2. Avvia Postgres
docker compose up -d db

# 3. Backend (in un terminale)
cd backend && uv sync --extra dev
PYTHONPATH=src uv run uvicorn colazione.main:app --reload

# 4. Frontend (in un altro terminale)
cd frontend && pnpm install && pnpm dev

# 5. Apri il browser
# → http://localhost:5173 (frontend)
# → http://localhost:8000/docs (OpenAPI Swagger)
# → http://localhost:8000/health (health check)
```

### Alternativa: tutto in Docker

```bash
docker compose up
# Aspetta che i 3 container siano "healthy"
# Apri http://localhost:5173
```

### Stop

```bash
# Ferma container ma preserva dati DB
docker compose down

# Ferma container + cancella volume DB (RESET completo)
docker compose down -v
```

---

## Comandi sviluppo

### Backend

```bash
cd backend

uv sync --extra dev           # installa deps
uv run pytest                 # esegui test
uv run ruff check .           # lint
uv run ruff format .          # format
uv run mypy src/colazione     # type check
```

### Frontend

```bash
cd frontend

pnpm install         # installa deps
pnpm dev             # dev server (HMR)
pnpm test            # vitest
pnpm lint            # eslint
pnpm format          # prettier
pnpm typecheck       # tsc --noEmit
pnpm build           # build prod (dist/)
```

---

## Struttura repo

```
colazione/
├── .github/workflows/             CI GitHub Actions
├── backend/                       FastAPI + SQLAlchemy + Alembic
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── alembic/                   migrazioni DB versionate
│   ├── src/colazione/             package principale
│   │   ├── main.py                FastAPI app
│   │   ├── config.py              Pydantic Settings
│   │   ├── auth/                  JWT + dependencies
│   │   ├── models/                ORM
│   │   ├── schemas/               Pydantic request/response
│   │   ├── api/                   route per dominio
│   │   ├── domain/                logica business (DB-agnostic)
│   │   │   ├── builder_giro/      algoritmo PdE → giro materiale
│   │   │   ├── builder_pdc/       algoritmo giro → turno PdC
│   │   │   ├── normativa/         validatore Trenord
│   │   │   └── revisioni/         cascading revisioni
│   │   └── importers/             import PdE
│   └── tests/
├── frontend/                      React 18 + Vite + TS + Tailwind
│   ├── package.json
│   ├── Dockerfile
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── ui/                shadcn/ui (on-demand)
│   │   │   └── domain/            componenti dominio (Gantt, ecc.)
│   │   ├── routes/                1 cartella per ruolo
│   │   ├── lib/                   api client + utils
│   │   └── hooks/                 TanStack Query hooks
│   └── ...
├── data/
│   └── depositi_manutenzione_trenord_seed.json   anagrafica reale
├── docs/                          specifiche architetturali
│   ├── VISIONE.md                 cosa stiamo costruendo
│   ├── STACK-TECNICO.md           scelte tecniche
│   ├── RUOLI-E-DASHBOARD.md       5 dashboard per ruolo
│   ├── LOGICA-COSTRUZIONE.md      algoritmi nativi
│   ├── SCHEMA-DATI-NATIVO.md      DDL Postgres eseguibile
│   ├── IMPORT-PDE.md              importer PdE Numbers/Excel
│   ├── PIANO-MVP.md               primo MVP girabile
│   ├── MODELLO-DATI.md            modello concettuale (v0.5)
│   ├── NORMATIVA-PDC.md           fonte verità Trenord
│   ├── METODO-DI-LAVORO.md        framework comportamentale
│   └── _archivio/                 memoria progetto vecchio
├── docker-compose.yml             dev locale (db + backend + frontend)
├── CLAUDE.md                      istruzioni Claude Code
├── TN-UPDATE.md                   diario operativo
└── README.md                      questo file
```

---

## Documentazione

Tutto il progetto è documentato in `docs/`. **Leggi prima di scrivere
codice**:

1. **[VISIONE.md](docs/VISIONE.md)** — cosa stiamo costruendo, perché, per chi
2. **[STACK-TECNICO.md](docs/STACK-TECNICO.md)** — Python, FastAPI, Postgres, React, ecc.
3. **[RUOLI-E-DASHBOARD.md](docs/RUOLI-E-DASHBOARD.md)** — 5 dashboard, 30+ schermate, permessi
4. **[LOGICA-COSTRUZIONE.md](docs/LOGICA-COSTRUZIONE.md)** — algoritmi PdE → giro → PdC
5. **[SCHEMA-DATI-NATIVO.md](docs/SCHEMA-DATI-NATIVO.md)** — DDL Postgres 31 tabelle
6. **[IMPORT-PDE.md](docs/IMPORT-PDE.md)** — lettura PdE Numbers/Excel
7. **[PIANO-MVP.md](docs/PIANO-MVP.md)** — roadmap costruzione MVP

Riferimenti normativi e di metodo:

- **[NORMATIVA-PDC.md](docs/NORMATIVA-PDC.md)** — fonte verità dominio Trenord (1292 righe)
- **[MODELLO-DATI.md](docs/MODELLO-DATI.md)** — modello concettuale a piramide (v0.5)
- **[METODO-DI-LAVORO.md](docs/METODO-DI-LAVORO.md)** — framework comportamentale

---

## Contribuire

Non c'è ancora un team formalizzato. Per ora:

1. Ogni modifica = **1 commit + 1 verifica** + aggiornamento `TN-UPDATE.md`
2. Naming commit: Conventional Commits (`feat:`, `fix:`, `refactor:`, ecc.)
3. CI deve essere verde prima del merge in master
4. Niente DROP/TRUNCATE/operazioni distruttive senza autorizzazione esplicita

Il framework di lavoro completo è in
[`docs/METODO-DI-LAVORO.md`](docs/METODO-DI-LAVORO.md).

---

## Licenza

Proprietary — uso interno. Codice ispirato dall'esperienza Trenord ma
indipendente dal loro sistema (vedi
[`docs/MODELLO-DATI.md` §⚠️ Manifesto](docs/MODELLO-DATI.md)).
