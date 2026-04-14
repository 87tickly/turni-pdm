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

---

## 2026-04-14 — Pagina Cerca Treni (prima pagina operativa)

### Funzionalità implementate
- **Ricerca per numero treno**: cerca nel DB locale, mostra segmenti (stazione A → B, orari)
- **Dettaglio real-time espandibile**: pannello "Dati real-time (ARTURO Live)" con stato treno, operatore, ritardo, 14 fermate con orari arr/dep/binario/ritardo
- **Giro materiale**: se il treno ha un giro materiale nel DB, mostra la catena con posizione evidenziata
- **Ricerca per stazione**: autocomplete via ARTURO Live (nome stazione → suggerimenti con codice)
- **Partenze/Arrivi**: tabellone con numero treno, categoria, destinazione, operatore, orario, ritardo

### File
- `frontend/src/pages/TrainSearchPage.tsx` — ~450 righe, pagina completa
- `frontend/src/lib/api.ts` — aggiunte API: queryTrain, queryStation, listStations, getGiroChain, vtAutocompleteStation, vtDepartures, vtArrivals, vtTrainInfo
- `frontend/src/App.tsx` — route /treni punta a TrainSearchPage

### Note tecniche
- Due fonti dati separate: DB locale (dati PDF statici) e ARTURO Live (real-time)
- Nessuna "allucinazione": mostra solo dati dalle API, non inventa nulla
- Autocomplete stazione supporta nodi aggregati (node:milano = tutte le stazioni di Milano)

---

## 2026-04-14 — Pagina Turni salvati con timeline visiva

### Funzionalità implementate
- **Lista turni salvati** con filtro per tipo giorno (Tutti/LV/SAB/DOM)
- **Card turno espandibile**: nome, deposito, tipo giorno, numero treni, badge FR, conteggio violazioni
- **Stats in card**: prestazione (ore:min), condotta, orario inizio/fine
- **Timeline visiva**: barra colorata proporzionale con blocchi (treno, vettura, refezione, accessori, extra, spostamento, giro materiale)
- **Dettaglio timeline**: lista blocchi con tipo, label, orari, durata
- **Legenda colori**: 7 tipi blocco con colori distinti
- **Violazioni**: lista con icona e messaggio
- **Eliminazione**: conferma prima di cancellare
- **Stato vuoto**: placeholder quando non ci sono turni

### File
- `frontend/src/pages/ShiftsPage.tsx` — ~400 righe
- `frontend/src/lib/api.ts` — aggiunte API: getSavedShifts, deleteSavedShift, getShiftTimeline, getWeeklyShifts, deleteWeeklyShift + tutti i types
- `frontend/src/App.tsx` — route /turni punta a ShiftsPage

---

## 2026-04-14 — Pagina Builder Turno manuale (cuore del software)

### Funzionalità implementate
- **Configurazione**: selezione deposito (25 depositi), tipo giorno (LV/SAB/DOM), tipo accessori (Standard/Maggiorato/CVL), toggle FR
- **Ricerca treni**: per numero (DB locale) con risultati cliccabili per aggiunta
- **Connessioni intelligenti**: tab "Connessioni da [ultima stazione]" appare automaticamente dopo il primo treno
- **Lista treni nel turno**: con orari, stazioni, bottone VET (vettura/deadhead), bottone rimuovi
- **Validazione real-time**: si aggiorna automaticamente (300ms debounce) ad ogni modifica
  - Prestazione con limite max (8h30)
  - Condotta con limite max (5h30)
  - Refezione, Accessori
  - Violazioni con messaggi dettagliati
  - Badge "Valido" verde o "N violazioni" rosso
- **Timeline visiva**: barra colorata + lista blocchi dettagliata (Extra, Accessori, Treno, Refezione, Spostamento, Giro materiale) con orari e durate
- **Rientro deposito**: segnala automaticamente se manca il treno di rientro
- **Salvataggio**: campo nome + bottone "Salva turno" con feedback (spinner, "Salvato" verde)
- **Layout**: due colonne — builder a sinistra, pannello validazione sticky a destra

### File
- `frontend/src/pages/BuilderPage.tsx` — ~500 righe, pagina completa
- `frontend/src/lib/api.ts` — aggiunte: validateDayWithTimeline, getConnections, saveShift, AppConstants type
- `frontend/src/App.tsx` — route /builder
- `frontend/src/components/Sidebar.tsx` — aggiunta voce "Nuovo turno" con icona PlusCircle
