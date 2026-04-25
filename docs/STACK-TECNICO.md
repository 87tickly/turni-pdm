# STACK TECNICO — scelte tecnologiche del nuovo progetto (v1.0)

> Decisioni prese il 2026-04-25 dopo discussione con l'utente.
> Tutte le scelte sono **"consigliate"** e l'utente ha confermato in
> blocco. Modifiche future devono passare da una nuova entry in
> `TN-UPDATE.md` con motivazione.
>
> Questo documento è **operativo**: chi clona il repo legge qui cosa
> installare, come avviare, come deployare.

---

## 1. Le 6 scelte fondamentali

| # | Layer | Scelta | Motivo |
|---|-------|--------|--------|
| 1 | Linguaggio backend | **Python 3.12+** | Esperienza pregressa, ecosistema maturo per data manipulation (Pandas, openpyxl, numbers-parser), Pydantic per validazione tipi |
| 2 | Framework backend | **FastAPI** | Async, OpenAPI auto-generato, Pydantic-native, ecosystem maturo |
| 3 | Database | **PostgreSQL 16+** | JSONB nativo per `valido_in_date`, tipi temporali decenti, schema robusto, multi-tenant pronto. Stesso DB dev e prod (no SQLite/PG dual-mode come prima — fonte di bug) |
| 4 | Frontend | **React 18 + TypeScript + Vite** | Ecosistema dominante, esperienza pregressa, build velocissima |
| 5 | UI Kit | **shadcn/ui** (Radix + Tailwind CSS) | Componenti leggibili (codice nostro), accessibility da Radix, design system coerente |
| 6 | Auth | **JWT custom + bcrypt** | Zero dipendenze esterne, controllo totale, già fatto nel vecchio (logica trasferibile come riferimento) |

### Hosting / Deploy

**Decisione differita.** Sviluppo locale via `docker compose` per ora.
Quando arriva il primo deploy reale, valutiamo VPS self-host (Hetzner
~5€/mese) vs Railway/Fly.io. La struttura del codice è hosting-agnostic
(immagini Docker standard).

---

## 2. Struttura repo (monorepo)

Un solo repository, due cartelle principali per backend e frontend:

```
COLAZIONE/                          (questo repo)
├── .github/                        CI/CD GitHub Actions
├── .claude/                        config harness Claude Code
├── .gitignore
├── CLAUDE.md                       istruzioni Claude (FASE B ✅)
├── TN-UPDATE.md                    diario operativo
├── README.md                       da scrivere — quick start
├── docker-compose.yml              dev: backend + db + frontend
├── data/
│   └── depositi_manutenzione_trenord_seed.json
│
├── backend/                        applicazione FastAPI
│   ├── pyproject.toml              dipendenze + tooling Python
│   ├── Dockerfile
│   ├── .python-version             "3.12"
│   ├── alembic.ini                 migrazioni DB
│   ├── alembic/                    migrazioni versionate
│   │   └── versions/
│   ├── src/
│   │   └── colazione/              package principale
│   │       ├── __init__.py
│   │       ├── main.py             entry point FastAPI app
│   │       ├── config.py           settings da env (Pydantic Settings)
│   │       ├── db.py               session manager SQLAlchemy
│   │       ├── auth/               JWT, hashing, dependencies
│   │       ├── models/             SQLAlchemy ORM (1 file per entità)
│   │       ├── schemas/            Pydantic schemas (request/response)
│   │       ├── api/                router FastAPI (1 file per dominio)
│   │       │   ├── corse.py        LIV 1 corse commerciali
│   │       │   ├── giri.py         LIV 2 giro materiale
│   │       │   ├── turni_pdc.py    LIV 3 turno PdC
│   │       │   ├── persone.py      LIV 4 anagrafica
│   │       │   ├── revisioni.py    revisioni provvisorie
│   │       │   ├── depositi.py     anagrafica località manutenzione
│   │       │   └── auth.py         login/refresh
│   │       ├── domain/             logica di business (no DB)
│   │       │   ├── builder_giro/   algoritmo costruzione giro materiale
│   │       │   ├── builder_pdc/    algoritmo costruzione turno PdC
│   │       │   ├── normativa/      validatore regole Trenord
│   │       │   └── revisioni/      cascading revisioni
│   │       └── importers/
│   │           └── pde.py          import PdE Numbers/Excel
│   └── tests/                      pytest, mirror di src/
│
└── frontend/                       applicazione React
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    ├── tailwind.config.ts
    ├── Dockerfile
    ├── public/
    └── src/
        ├── main.tsx                entry React
        ├── App.tsx                 router top-level + auth guard
        ├── lib/
        │   ├── api.ts              client API typed
        │   ├── auth.ts             gestione token
        │   └── utils.ts
        ├── components/             componenti shadcn-style + custom
        │   ├── ui/                 shadcn (button, card, dialog, ecc.)
        │   └── domain/             componenti dominio (GiroGantt, ecc.)
        ├── routes/                 una cartella per ruolo (vedi RUOLI-E-DASHBOARD.md)
        │   ├── pianificatore-giro/
        │   ├── pianificatore-pdc/
        │   ├── manutenzione/
        │   ├── gestione-personale/
        │   └── personale/
        └── hooks/                  React Query hooks
```

**Principi**:
- Backend e frontend **indipendenti** (build separati, container separati). Comunicano via API REST + JSON.
- `domain/` nel backend è **DB-agnostic**: contiene la logica pura (builder, validatori, normativa). I modelli SQLAlchemy stanno in `models/`, le API in `api/`. Test unitari vivono in `tests/domain/` senza toccare DB.
- Frontend organizzato **per ruolo** (cartella per dashboard), non per tipo (no `pages/`, `components/all-mixed-up/`).

---

## 3. Tooling di sviluppo

### Backend (Python)

| Tool | Versione min | Scopo |
|------|--------------|-------|
| `python` | 3.12 | Runtime |
| `uv` | latest | Package manager (sostituisce pip + virtualenv) |
| `ruff` | latest | Linter + formatter (sostituisce flake8 + black + isort) |
| `mypy` | latest | Type checker statico |
| `pytest` | latest | Test runner |
| `pytest-cov` | latest | Code coverage |
| `pytest-asyncio` | latest | Test async |

**Comandi standard** (definiti in `backend/pyproject.toml`):

```bash
cd backend
uv sync                  # installa dipendenze
uv run uvicorn colazione.main:app --reload   # dev server
uv run ruff check .      # lint
uv run ruff format .     # format
uv run mypy src/         # type check
uv run pytest            # test
```

### Frontend (React)

| Tool | Versione min | Scopo |
|------|--------------|-------|
| `node` | 20 LTS | Runtime |
| `pnpm` | 9+ | Package manager (più veloce di npm, store condiviso) |
| `vite` | 5+ | Build tool |
| `typescript` | 5.4+ | Type checker |
| `eslint` | 9+ | Linter |
| `prettier` | 3+ | Formatter |
| `vitest` | latest | Test runner (Vite-native) |
| `@testing-library/react` | latest | Component testing |

**Comandi standard** (definiti in `frontend/package.json`):

```bash
cd frontend
pnpm install
pnpm dev                 # dev server con HMR
pnpm build               # build produzione
pnpm lint
pnpm format
pnpm typecheck
pnpm test
```

### Database

| Tool | Versione min | Scopo |
|------|--------------|-------|
| `postgresql` | 16+ | DB |
| `alembic` | latest | Migrazioni schema (Python-side) |

In dev, Postgres gira via Docker (vedi `docker-compose.yml` più sotto).

---

## 4. Dipendenze Python principali

Da scrivere in `backend/pyproject.toml`:

```toml
[project]
name = "colazione"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    # Web framework
    "fastapi[standard]>=0.115",
    "uvicorn[standard]>=0.30",

    # DB
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "psycopg[binary]>=3.2",      # driver Postgres async-compatible

    # Validation / config
    "pydantic>=2.7",
    "pydantic-settings>=2.3",

    # Auth
    "bcrypt>=4.1",
    "pyjwt>=2.9",

    # Data manipulation
    "openpyxl>=3.1",              # lettura .xlsx
    "numbers-parser>=4.10",       # lettura .numbers
    "pandas>=2.2",                # opzionale, per analisi PdE
]

[project.optional-dependencies]
dev = [
    "ruff>=0.5",
    "mypy>=1.10",
    "pytest>=8.2",
    "pytest-cov>=5.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",                # client HTTP per test API
]
```

---

## 5. Dipendenze frontend principali

Da scrivere in `frontend/package.json`:

```json
{
  "name": "colazione-frontend",
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "lint": "eslint .",
    "format": "prettier --write .",
    "typecheck": "tsc --noEmit",
    "test": "vitest"
  },
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.26.0",
    "@tanstack/react-query": "^5.50.0",

    "tailwindcss": "^3.4.0",
    "tailwind-merge": "^2.4.0",
    "class-variance-authority": "^0.7.0",
    "clsx": "^2.1.0",
    "lucide-react": "^0.408.0",

    "@radix-ui/react-dialog": "^1.1.0",
    "@radix-ui/react-dropdown-menu": "^2.1.0",
    "@radix-ui/react-toast": "^1.2.0",
    "@radix-ui/react-popover": "^1.1.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "vite": "^5.4.0",
    "typescript": "^5.5.0",
    "eslint": "^9.7.0",
    "@typescript-eslint/parser": "^7.16.0",
    "@typescript-eslint/eslint-plugin": "^7.16.0",
    "prettier": "^3.3.0",
    "vitest": "^2.0.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.4.0"
  }
}
```

I componenti shadcn/ui si aggiungono **on-demand** con `pnpm dlx
shadcn-ui@latest add <componente>` — non sono una dipendenza, sono
codice copiato in `src/components/ui/`.

---

## 6. Configurazione runtime

### Variabili d'ambiente (backend)

File `.env.local` (mai committato), modello in `.env.example`:

```ini
# Database
DATABASE_URL=postgresql+psycopg://colazione:colazione@localhost:5432/colazione

# Auth
JWT_SECRET=change-me-in-prod-min-32-chars
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MIN=4320           # 72h
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30

# Admin bootstrap
ADMIN_DEFAULT_USERNAME=admin
ADMIN_DEFAULT_PASSWORD=                     # auto-generata se vuota

# CORS (dev)
CORS_ALLOW_ORIGINS=http://localhost:5173

# Logging
LOG_LEVEL=INFO

# Multi-tenant default
DEFAULT_AZIENDA=trenord
```

Caricate via `pydantic-settings` in `backend/src/colazione/config.py`.

### Variabili d'ambiente (frontend)

File `frontend/.env.local`:

```ini
VITE_API_BASE_URL=http://localhost:8000
```

---

## 7. `docker-compose.yml` per dev

Da scrivere alla root del repo:

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: colazione
      POSTGRES_PASSWORD: colazione
      POSTGRES_DB: colazione
    ports:
      - "5432:5432"
    volumes:
      - colazione_pgdata:/var/lib/postgresql/data

  backend:
    build: ./backend
    environment:
      DATABASE_URL: postgresql+psycopg://colazione:colazione@db:5432/colazione
      JWT_SECRET: dev-secret-change-me-min-32-characters-long
    ports:
      - "8000:8000"
    depends_on:
      - db
    volumes:
      - ./backend/src:/app/src                # hot reload in dev
      - ./data:/app/data:ro

  frontend:
    build: ./frontend
    environment:
      VITE_API_BASE_URL: http://localhost:8000
    ports:
      - "5173:5173"
    volumes:
      - ./frontend/src:/app/src

volumes:
  colazione_pgdata:
```

Avvio dev:

```bash
docker compose up -d db   # solo DB se sviluppi backend/frontend nativamente
docker compose up         # tutto containerizzato
```

---

## 8. Strategia migrazioni DB

### Tool: **Alembic**

- Schema gestito da SQLAlchemy ORM in `backend/src/colazione/models/`
- Migrazioni autogenerate da Alembic, **revisionate a mano** prima di committare
- Naming: `alembic/versions/0001_initial_schema.py`,
  `0002_add_revisione_provvisoria.py`, ecc.
- Apply automatico al boot del backend in dev (cfr. `main.py`):
  `alembic upgrade head` come startup hook
- In prod, apply manuale via job/cmd dedicato

### Vincoli

- **Niente schema ad-hoc nel codice runtime**. Solo Alembic crea/modifica tabelle.
- **Idempotenza obbligatoria**: ogni migrazione deve poter girare due volte senza errori (importante per ambiente CI/test).

---

## 9. Convenzioni di codice

### Backend (Python)

- **Naming**: snake_case per funzioni/variabili, PascalCase per classi (Pydantic + SQLAlchemy)
- **Type hints**: obbligatori ovunque, mypy `strict` mode
- **Docstring**: Google style (`"""Description.\n\n  Args:\n    x: ...`)
- **Async**: tutte le route `async def`. SQLAlchemy 2.0 async session.
- **Test**: ogni modulo `domain/` ha test unitari. API endpoint → test integrazione con httpx + TestClient.

### Frontend (React)

- **Naming**: camelCase per variabili/funzioni, PascalCase per componenti, kebab-case per file di route
- **Tipi**: stretti, no `any`
- **Componenti**: function components, niente class components
- **Stato server**: TanStack Query (React Query). Niente Redux/Zustand per dati API.
- **Stato UI locale**: `useState` o `useReducer`, custom hooks per logica condivisa.
- **CSS**: solo Tailwind. Niente CSS Modules, niente styled-components.

### Commit (entrambi)

Conventional Commits: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`,
`test:`. Italiano nel corpo del commit accettabile (parla la persona,
non il linter).

---

## 10. Versioning Python / Node / Postgres

```
Python:     3.12 (specifico in .python-version, pyproject requires-python)
Node:       20 LTS (specifico in .nvmrc)
Postgres:   16 (image docker postgres:16-alpine)
pnpm:       9+
uv:         latest stabile
```

Quando esce Python 3.13/3.14, valutiamo bump in TN-UPDATE.md.

---

## 11. CI/CD (GitHub Actions, primo MVP)

In `.github/workflows/`:

| Workflow | Trigger | Cosa fa |
|----------|---------|---------|
| `backend-ci.yml` | push/PR su backend/** | uv sync + ruff check + mypy + pytest |
| `frontend-ci.yml` | push/PR su frontend/** | pnpm install + lint + typecheck + build + test |
| `db-migration-check.yml` | push/PR | apply migrazioni a DB temporaneo + rollback (verifica reversibilità) |

Deploy CD: differito quando si decide hosting.

---

## 12. Cosa NON useremo (esplicito)

- **Tauri** (desktop app): il progetto vecchio l'aveva pianificato, ora differito. Web-only.
- **GraphQL**: REST è sufficiente, OpenAPI auto-generato da FastAPI è abbastanza per il frontend.
- **Redis** in primo MVP: cache in-memory dentro FastAPI (lru_cache) basta. Redis arriva quando serve session storage o pub/sub.
- **Celery / job queue**: niente background job pesanti nel MVP. Le revisioni provvisorie sono operazioni sincrone "sufficienti".
- **Microservizi**: monolite modulare. Boundaries chiare via `domain/`, ma deploy unico.
- **Container orchestration (k8s)**: docker-compose basta per dev e per VPS singolo. K8s solo se domani arriva scala enterprise.
- **Server-Side Rendering (SSR/SSG)**: app interna B2B, SPA classica va bene.
- **Internationalization (i18n)**: italiano-only per Trenord. Quando arriva SAD, valutiamo.

---

## 13. Riferimenti

- `docs/VISIONE.md` — cosa stiamo costruendo
- `docs/MODELLO-DATI.md` v0.5 — modello concettuale
- `docs/RUOLI-E-DASHBOARD.md` — 5 dashboard (FASE C doc 3, prossimo)
- `docs/SCHEMA-DATI-NATIVO.md` — schema SQL eseguibile (FASE C doc 5)
- `docs/PIANO-MVP.md` — roadmap costruzione (FASE C doc 7)

---

**Fine v1.0**. Modifiche future tracciate in TN-UPDATE.md.
