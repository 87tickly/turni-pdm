# LIVE-COLAZIONE — Registro modifiche in tempo reale

Questo file viene aggiornato ad ogni modifica. Leggilo sempre per avere il contesto completo.

---

## 2026-04-14 — Sessione A: CLAUDE.md + Sicurezza

### CLAUDE.md creato
- Documentato scopo, stack, glossario dominio, regole operative, convenzioni, roadmap

### Fix sicurezza
- `src/database/db.py`: rimossa password admin hardcoded `"Manu1982!"` → env var `ADMIN_DEFAULT_PASSWORD` o generazione random
- `server.py`: `JWT_SECRET` obbligatorio in produzione (se `DATABASE_URL` impostato)
- Creato `.env.example` con tutte le variabili ambiente
- Aggiunto `.env` a `.gitignore`

---

## 2026-04-14 — Sessione B: Ristrutturazione server.py

### server.py spezzato (2834 → 62 righe)
Struttura creata:
- `api/deps.py` — dipendenze condivise (DB, JWT auth, password utils)
- `api/auth.py` — 6 endpoint (register, login, me, admin/*)
- `api/health.py` — 3 endpoint (/, health, info)
- `api/upload.py` — 2 endpoint (upload PDF, delete DB)
- `api/trains.py` — 12 endpoint (query treni/stazioni, giro materiale, connections)
- `api/validation.py` — 4 endpoint (constants, validate-day, check-validity)
- `api/builder.py` — 4 endpoint (build-auto, build-auto-all, calendar, weekly)
- `api/shifts.py` — 9 endpoint (CRUD turni salvati/settimanali, timeline, used-trains)
- `api/importers.py` — 5 endpoint (turno personale, PdC, train-check)
- `api/viaggiatreno.py` — 8 endpoint (dati real-time)

### Service layer estratto
- `services/segments.py` — dedup_segments, serialize_segments, seg_get
- `services/timeline.py` — build_timeline_blocks (~280 righe di logica timeline)

---

## 2026-04-14 — Switch VT → ARTURO Live

### API ViaggiaTreno sostituite con ARTURO Live
- `services/arturo_client.py` — NUOVO: client API live.arturo.travel (httpx sincrono, nessuna auth)
- `api/viaggiatreno.py` — riscritto da 735 a 320 righe, usa arturo_client
- `api/importers.py` — train-check ora usa ARTURO Live (era VT diretto)
- URL `/vt/*` mantenuti per retrocompatibilità frontend legacy

### Mapping endpoint
| COLAZIONE `/vt/*` | ARTURO Live |
|---|---|
| autocomplete-station | `GET /api/cerca/stazione?q=` |
| departures | `GET /api/partenze/{id}` |
| arrivals | `GET /api/arrivi/{id}` |
| train-info | `GET /api/treno/{numero}` |
| solutions | `GET /api/cerca/tratta?da=&a=` |
| find-return | Combinazione partenze + arrivi |

---

## 2026-04-14 — Sessione C: Configurazione multi-azienda

### Sistema config/ creato
- `config/schema.py` — dataclass `CompanyConfig` con 40+ campi e default normativi italiani
- `config/trenord.py` — override specifici Trenord (25 depositi, 19 FR, CVL, tempi fissi)
- `config/loader.py` — `get_active_config()`, selezione via env var `COLAZIONE_COMPANY`

### src/constants.py → wrapper retrocompatibile
- Non contiene più valori hardcoded
- Legge tutto da `config/loader.get_active_config()`
- Esporta gli stessi nomi di prima → zero modifiche a validator/builder/consumer

### Multi-deposito nel DB
- Tabella `depot` (code, display_name, company, active) aggiunta a `db.py`
- `depot_id` nullable aggiunto a `material_turn`, `saved_shift`, `weekly_shift`
- Auto-seed depositi dalla configurazione attiva all'avvio
- Migrazioni idempotenti via `_run_migration()`

### Per aggiungere nuova azienda
1. Creare `config/nuovaazienda.py` con `CompanyConfig(...)`
2. Registrarlo in `config/loader.py` dict `configs`
3. Settare `COLAZIONE_COMPANY=nuovaazienda`

---

## 2026-04-14 — Sessione D: Setup frontend React + TypeScript

### Scaffold progetto
- `frontend/` creato con Vite + React + TypeScript
- Tailwind CSS 4 configurato via `@tailwindcss/vite` plugin
- Path alias `@/` → `src/` configurato in vite.config.ts + tsconfig
- Proxy API configurato in Vite dev server (tutte le route backend proxied a :8002)

### Dipendenze installate
- `tailwindcss`, `@tailwindcss/vite` — CSS utility framework
- `react-router-dom` — routing client-side
- `lucide-react` — icone (stile minimale)
- `clsx`, `tailwind-merge` — utility per classi CSS condizionali

### Design system
- Palette colori custom in `index.css` via `@theme` (background, foreground, primary blu ARTURO, sidebar scura)
- Font: SF Pro Display/Text con fallback a Segoe UI/Roboto
- Sidebar scura (171717) con navigazione attiva evidenziata

### Struttura frontend
```
frontend/src/
├── main.tsx              — entry point
├── App.tsx               — routing (BrowserRouter + Routes)
├── index.css             — Tailwind + design tokens
├── lib/
│   ├── api.ts            — client API con JWT auth (get/post/delete + login/register/getMe/getHealth/getDbInfo)
│   └── utils.ts          — cn(), fmtMin(), timeToMin()
├── hooks/
│   └── useAuth.ts        — hook autenticazione (user state, loading, logout)
├── components/
│   ├── Layout.tsx         — layout con sidebar + Outlet (redirect a /login se non autenticato)
│   └── Sidebar.tsx        — sidebar navigazione (Dashboard, Treni, Turni, Calendario, Import, Impostazioni)
└── pages/
    ├── LoginPage.tsx      — login/register con form
    ├── DashboardPage.tsx  — stats DB (segmenti, treni, turni materiale, day indices)
    └── PlaceholderPage.tsx — placeholder per sezioni in costruzione
```

### Route
- `/login` — pagina login/registrazione (pubblica)
- `/` — Dashboard (protetta)
- `/treni` — Ricerca Treni (placeholder)
- `/turni` — Gestione Turni (placeholder)
- `/calendario` — Calendario (placeholder)
- `/import` — Import PDF (placeholder)
- `/impostazioni` — Impostazioni (placeholder)

### Build verificata
- `tsc --noEmit` → 0 errori
- `npm run build` → 272KB JS + 15KB CSS

---

## 2026-04-14 — Redesign frontend: dark theme professionale

### Problema
Il primo design (sfondo grigio chiaro, card bianche) era troppo generico/template. Bocciato dall'utente.

### Nuovo design system
- **Palette scura** ispirata a Linear/Raycast: background #0a0a0b, card #131316, border #27272a
- **Accent blu elettrico** ARTURO (#3b82f6) con varianti hover/muted
- **Colori semantici** con varianti muted (success, warning, info, destructive)
- **Font**: Inter con font-features cv02/cv03/cv04/cv11
- **Scrollbar minimale** custom
- **Glow effect** su login page

### Componenti rifatti
- **Sidebar**: più compatta (w-56), icona brand con badge blu, sezioni Menu/Sistema, shortcut keyboard visibili on hover, avatar utente con iniziale
- **Layout**: spinner di caricamento animato, max-w-6xl centrato
- **Dashboard**: stat cards con accent colorati (blu/verde/giallo), badge "Operativo" pill, turni materiale con hover effect
- **Login**: sfondo scuro con glow blu diffuso, icona treno in contenitore con bordo primary, input scuri con focus ring blu, spinner nel bottone durante loading
- **Placeholder**: icona in contenitore muted, testo minimale
