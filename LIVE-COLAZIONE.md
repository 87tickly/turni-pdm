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

---

## 2026-04-15 — Rebrand ARTURO + Timeline Gantt

### Brand ARTURO applicato
- **Font Exo 2** (variable, weight 100-900) — self-hosted da /public/fonts/
- **Colori brand**: #0062CC (primario), #0070B5 (secondario), #30D158 (dot verde), #38BDF8 (accent)
- **Palette dark**: background #0A0F1A, card #111827, text #F1F5F9, muted #94A3B8
- **Logo COLAZIONE**: componente React con font Exo 2 black + dot verde pulsante (stile ARTURO Live/Business)
- Animazione `pulse-dot` per il pallino verde

### Timeline Gantt orizzontale (stile PDF Trenord)
- Componente SVG `GanttTimeline` con griglia oraria 3→24→3
- Barre proporzionali per durata blocchi
- Testo verticale sopra le barre (numero treno + stazione)
- Linee tratteggiate per attese/spostamenti/refezione
- Colonne totali a destra: Lav, Cct, Km, Not, Rip
- Label giornata a sinistra (LV, SAB, DOM) con orari [inizio][fine]
- Deposito mostrato come label
- Wrapper `GanttFromValidation` per conversione dati validazione → Gantt

### File creati/modificati
- `frontend/public/fonts/Exo2-Variable.ttf`, `Exo2-Italic-Variable.ttf` — font self-hosted
- `frontend/src/index.css` — palette brand ARTURO + @font-face Exo 2
- `frontend/src/components/Logo.tsx` — NUOVO: logo COLAZIONE stile ARTURO
- `frontend/src/components/GanttTimeline.tsx` — NUOVO: timeline Gantt SVG
- `frontend/src/components/Sidebar.tsx` — usa Logo component
- `frontend/src/pages/LoginPage.tsx` — usa Logo component
- `frontend/src/pages/BuilderPage.tsx` — usa GanttFromValidation al posto delle barre colorate

---

## 2026-04-15 — Gantt dinamico v2 + unificazione Gantt in ShiftsPage

### Miglioramenti Gantt
- **Scala DINAMICA**: mostra solo le ore rilevanti (1h prima e 1h dopo il turno), non più 24h fisse
- **Barre più grandi**: BAR_H=18px (era 14), min 55px/ora (era ~37.5)
- **Testo più leggibile**: font size aumentati, stazione fino a 8 char (era 6)
- **Deposito duplice**: label deposito sia a inizio che a fine riga (come PDF)
- **Totali verticali**: Lav/Cct/Km/Not/Rip in colonna verticale a destra (era orizzontale)
- **Orari treno**: orario partenza sotto le barre dei treni se c'è spazio
- **SVG responsive**: width="100%" con viewBox, scrollabile orizzontalmente

### ShiftsPage unificata
- Rimossi componenti vecchi (TimelineBar, TimelineDetail, TimelineLegend)
- Usa GanttFromValidation come il BuilderPage — stesso stile ovunque

### Nota FR
- L'utente richiede Gantt a doppia riga per dormite FR (giorno 1 sera + giorno 2 mattina)
- Richiede supporto backend per blocchi multi-giorno — segnato per prossima iterazione

---

## 2026-04-15 — Tauri desktop app (macOS)

### Setup completato
- Rust 1.94.1 installato via rustup
- Tauri v2 configurato in `frontend/src-tauri/`
- Build produce `COLAZIONE.app` + `COLAZIONE_0.1.0_aarch64.dmg`
- Finestra 1280x800, min 900x600, resizable
- Identifier: `com.arturo.colazione`

### File creati
- `frontend/src-tauri/Cargo.toml` — dipendenze Rust (tauri v2, serde)
- `frontend/src-tauri/tauri.conf.json` — config app (titolo, dimensioni, bundle)
- `frontend/src-tauri/src/main.rs` — entry point Rust
- `frontend/src-tauri/build.rs` — build script
- `frontend/src-tauri/icons/` — icone placeholder (PNG blu #0062CC)

### Nota
- L'app desktop wrappa il frontend React — al momento richiede backend Python avviato separatamente
- Per Windows serve cross-compile o build su macchina Windows
- Le icone sono placeholder — da sostituire con logo COLAZIONE vero

---

## 2026-04-15 — Deploy Railway configurato per nuovo frontend

### Configurazione
- `railway.toml`: buildCommand aggiunto per buildare frontend React prima del deploy
- `nixpacks.toml`: NUOVO — configura nodejs_22 + python312 + gcc per build ibrida
- `server.py`: serve `frontend/dist/` (React build) in produzione, `static/` come fallback
- `api/health.py`: rimossa route `/` redirect (il frontend è servito dal mount statico)

### Come funziona in produzione
1. Railway esegue `cd frontend && npm install && npm run build`
2. Output in `frontend/dist/` (HTML + JS + CSS + assets)
3. FastAPI monta `frontend/dist/` su `/` come StaticFiles con `html=True`
4. Le API hanno priorità (router inclusi PRIMA del mount statico)
5. `railway up` per deployare

### Testato localmente
- `/api/health` → JSON ok
- `/` → serve index.html del frontend React
- Le due cose funzionano insieme senza conflitti

---

## 2026-04-15 — Palette slate più chiara + fix Tauri

### Palette v3 (slate chiaro)
- Background: `#1E293B` (era #0A0F1A — molto più chiaro)
- Card: `#273549` (era #111827)
- Sidebar: `#182336`
- Border: `#3D5472` (visibili)
- Muted: `#334B68`
- Card e sfondo ora distinguibili, bordi visibili, non più "buco nero"

### Fix Tauri
- API client rileva Tauri via `__TAURI__` window property → punta a `http://localhost:8002`
- CSP aggiornato per permettere `connect-src localhost:*`
- Il DMG funziona ma richiede backend avviato separatamente (sidecar non ancora integrato)

### Nota operativa
- Ogni modifica frontend richiede: `npm run build` per aggiornare `frontend/dist/`
- Per aggiornare il DMG: `npx tauri build`
- Per uso quotidiano: `uvicorn server:app --port 8002` + browser su `localhost:8002`

---

## 2026-04-15 — Redesign tema bianco + nuova Dashboard

### Palette light (bianca, pulita)
- Background: `#F7F8FA` (quasi bianco)
- Card: `#FFFFFF` (bianco puro)
- Foreground: `#0F172A` (testo scuro)
- Muted: `#F1F5F9` (grigio chiarissimo)
- Border: `#E2E8F0` (bordi leggeri)
- Sidebar: `#FFFFFF` (bianco con bordo destro)
- Primary: `#0062CC` (brand ARTURO blu) — era `#38BDF8` (cyan)
- Active sidebar: `bg-brand/8 text-brand` (sfumatura blu leggera)
- Scrollbar: grigio chiaro (#CBD5E1)

### Dashboard ridisegnata
- **Rimossi** i 4 stat cards tecnici (Segmenti, Treni unici, Turni materiale, Varianti giorno)
- **Saluto** personalizzato: "Buongiorno/Buon pomeriggio/Buonasera, [username]"
- **Quick actions**: 4 card con icone gradient colorate (Nuovo turno, Cerca treni, Turni salvati, Importa dati)
- **Turni recenti**: lista ultimi 5 turni salvati con deposito, tipo giorno, numero treni
- **Empty state**: messaggio + CTA "Crea turno" quando non ci sono turni

### SettingsPage creata (Impostazioni)
- Stats DB spostati qui (Segmenti, Treni unici, Turni materiale, Varianti giorno)
- Lista turni materiale importati
- Badge "Operativo" per stato sistema
- Route `/impostazioni` punta a `SettingsPage` (era `PlaceholderPage`)

### GanttTimeline adattato a tema chiaro
- Colori SVG hardcoded aggiornati per sfondo bianco
- text: `#0F172A` (era #F1F5F9)
- grid: `#CBD5E1` (era #475569)
- Barre treno: `#0062CC` brand blu (era #F1F5F9 bianco)
- Accessori/extra: grigi chiari (#CBD5E1, #E2E8F0)

### LoginPage
- Sfondo: gradiente bianco/azzurro sfumato (`from-slate-50 via-blue-50/30`)
- Card: bianca con ombra leggera
- Focus input: ring brand blu

### File modificati
- `frontend/src/index.css` — palette completa da dark a light
- `frontend/src/pages/DashboardPage.tsx` — riscritto: welcome + quick actions + turni recenti
- `frontend/src/pages/SettingsPage.tsx` — NUOVO: info sistema + stats DB
- `frontend/src/pages/LoginPage.tsx` — adattato a tema chiaro
- `frontend/src/components/Sidebar.tsx` — sidebar bianca, active state brand blu
- `frontend/src/components/GanttTimeline.tsx` — colori SVG per sfondo chiaro
- `frontend/src/App.tsx` — route impostazioni → SettingsPage

---

## 2026-04-15 — GanttTimeline v3: colori saturi + scala fissa

### Modifiche Gantt
- **Scala fissa 0-24**: griglia completa dalle 0 alle 24 ore (era dinamica)
- **Sfondo grigio chiaro**: wrapper `bg-[#F1F5F9]` con `rounded-lg p-3` per staccare dalla pagina bianca
- **Altezze differenziate per tipo blocco**:
  - Treno: 22px (barra grande, dominante)
  - Deadhead/spostamento/giro_return: 14px (media)
  - Accessori/extra: 10px (piccoli, secondari)
  - Tutte centrate verticalmente sullo stesso asse
- **Colori saturi e distinti**:
  - Treno: `#0062CC` (blu brand)
  - Deadhead/giro_return: `#7C3AED` (viola)
  - Accessori: `#F59E0B` (ambra)
  - Extra: `#FB923C` (arancione)
  - Spostamento: `#0891B2` (ciano)
- **Anti-sovrapposizione**: sistema di rilevamento collisioni tra label verticali, label shiftate verso l'alto se troppo vicine
- **Testo più grande e grassetto**: fontSize 11, fontWeight 900 per label treni
- **Durata** mostrata solo per blocchi treno (non accessori/extra)
- **Rimossi orari duplicati** sotto l'asse per evitare sovrapposizioni con numeri griglia

---

## 2026-04-15 — Deploy Railway risolto

### Problemi risolti
1. **`pip: command not found`**: `nixPkgs` custom sovrascriveva i default di nixpacks, rimuovendo Python
2. **`No module named pip`**: `python312Full` non bastava, il problema era nelle `cmds` custom
3. **Upload timeout CLI**: repo troppo grande (1.2GB per `src-tauri/target/`)
4. **`self.conn.execute()` su psycopg2**: PostgreSQL richiede `cursor().execute()`, fix in `db.py`

### Soluzione finale
- **Rimosso `nixpacks.toml`** completamente — nixpacks auto-rileva Python da `requirements.txt`
- **`railway.toml`** minimale: solo `startCommand` per uvicorn
- **`frontend/dist/`** committato nel repo (rimosso da `.gitignore` e `frontend/.gitignore`)
- **`.dockerignore`** creato: esclude `src-tauri/target/` (863MB), `node_modules/`, `frontend/src/`
- **Fix `db.py`**: `self.conn.cursor().execute()` in `_run_migration()` per compatibilità psycopg2

### Stato deploy
- Servizio: **Arturo-Turni** su Railway (progetto `affectionate-embrace` era sbagliato)
- URL: **web-production-0e9b9b.up.railway.app**
- Auto-deploy da GitHub attivo
- DB: PostgreSQL su Railway (separato da SQLite locale)

### Workflow aggiornato
1. Modifica codice frontend
2. `cd frontend && npm run build` per aggiornare `frontend/dist/`
3. `git add frontend/dist/ ...` + commit + push
4. Railway auto-deploya da GitHub

---

## 2026-04-15 — Pagina Calendario + Import PDF

### CalendarPage (`/calendario`)
- **Lista turni settimanali** con card espandibili (pattern ShiftsPage)
- Card header: nome, deposito, numero giorni, ore settimanali medie, note
- Card expanded: griglia giorni con varianti (LMXGV/SAB/DOM)
- Ogni variante mostra: treni, prestazione, condotta, badge FR/SCOMP, violazioni
- Eliminazione con conferma
- Empty state quando non ci sono turni settimanali

### ImportPage (`/import`)
- **3 sezioni upload** (una per tipo import):
  - **Turno Materiale** (primario): drag & drop PDF, mostra segmenti/treni/confidenza/warnings
  - **Turno Personale**: upload PDF, solo visualizzazione (non salva nel DB)
  - **Turno PdC (RFI)**: upload PDF, mostra turni importati
- Stato upload: idle → uploading (spinner) → success/error
- Stats correnti del DB in fondo (segmenti, treni, turni materiale, varianti giorno)
- Drop zone con drag & drop support

### Modifiche collaterali
- `api.ts`: tipi `DayVariant`, `WeeklyDay` tipizzati (era `Record<string, unknown>[]`)
- `api.ts`: funzioni `uploadTurnoMateriale()`, `uploadTurnoPersonale()`, `uploadTurnoPdc()`, `getPdcStats()` + helper `uploadFile()` per multipart FormData
- `api.ts`: tipi `UploadResult`, `TurnoPersonaleResult`, `TurnoPdcResult`, `PdcStats`
- `App.tsx`: route aggiornate, rimosso import `PlaceholderPage` (non più usato)

### File
- `frontend/src/pages/CalendarPage.tsx` — NUOVO (~300 righe)
- `frontend/src/pages/ImportPage.tsx` — NUOVO (~310 righe)
- `frontend/src/App.tsx` — modificato
- `frontend/src/lib/api.ts` — modificato

### Build
- `tsc --noEmit` → 0 errori
- `npm run build` → 335KB JS + 48KB CSS

---

## 2026-04-16 — Parser turno materiale: estrazione tipo locomotiva

### Contesto
Nell'intestazione di ogni turno materiale (prima pagina, prima del Gantt) c'e' una tabella "Impegno del materiale (n.pezzi)" che elenca i pezzi del convoglio:
```
Pezzo        Numero
npBDL        2
nBC-clim     10
E464N        2
```
Le righe lowercase (`npBDL`, `nBC-clim`) sono carrozze, la riga UPPERCASE (`E464N`) e' la locomotiva. Il parser prima non estraeva questo dato.

### Modifiche
- **`src/database/db.py`**:
  - Colonna `material_type TEXT DEFAULT ''` aggiunta a `material_turn`
  - Migrazione idempotente: `ALTER TABLE material_turn ADD COLUMN material_type TEXT DEFAULT ''`
  - `insert_material_turn()` accetta parametro opzionale `material_type`
- **`src/importer/pdf_parser.py`**:
  - Nuova regex `RE_LOCO` per codici locomotiva Trenord (E464, E464N, E484, ETR*, ALn*, ALe*, TAF, TSR)
  - Nuova funzione `extract_material_type(words)` con 2 strategie:
    1. Anchor su "Impegno" + scansione della zona sottostante (tabella)
    2. Fallback: scansione di tutta l'header area (top < 110 pt)
  - `parse_pdf()` costruisce `turno_material_types: dict[turn_number, str]` registrando il primo match per turno
  - Il dict `material_turns` ritornato include `material_type`
  - `PDFImporter.run_import()` passa `material_type` a `insert_material_turn()`
- **`.claude/skills/turno-materiale-reader.md`**:
  - Nuova sezione "Tabella Impegno del materiale" con convenzione lowercase/uppercase
  - Elenco codici locomotiva riconosciuti dalla regex
  - Schema JSON aggiornato con campo `material_type`

### Test
- Regex: verificata su E464/E464N/E484/ETR425/TAF/TSR/ALn668 (match) + npBDL/nBC-clim/10606 (no match)
- extract_material_type: 5 casi di test (tabella standard, fallback header, nessuna loco, lista vuota, ETR)
- `tests/test_database.py` e `tests/test_builder.py`: tutti passanti

### Impatto
- Import PDF futuri registreranno `material_type` nel DB
- I turni gia' importati avranno `material_type=''` — si popoleranno al prossimo re-import del PDF
- `GET /material-turns` (via SELECT *) ritorna automaticamente il nuovo campo senza modifiche API

### File modificati
- `src/database/db.py` — schema + migrazione + insert_material_turn
- `src/importer/pdf_parser.py` — regex + extract_material_type + parse_pdf + run_import
- `.claude/skills/turno-materiale-reader.md` — documentazione

---

## 2026-04-16 — Fix import PDF su PostgreSQL (FK violation)

### Problema
In produzione (PostgreSQL su Railway) l'import di un PDF turno materiale falliva con:
```
update or delete on table "material_turn" violates foreign key constraint
"day_variant_material_turn_id_fkey" on table "day_variant"
DETAIL: Key (id)=(1) is still referenced from table "day_variant".
```
In locale (SQLite) il problema non si manifestava perché SQLite non applica le FK per default.

### Causa
In `src/database/db.py::clear_all()` l'ordine dei DELETE cancellava `material_turn` PRIMA di `day_variant`, che però ha una FK verso `material_turn`. PostgreSQL (che applica sempre le FK) rifiutava l'operazione.

### Fix
Riordinati i DELETE in modo che i figli (che hanno FK verso `material_turn`) vengano cancellati per primi, poi il padre:
1. `non_train_event` (nessuna FK)
2. `train_segment` (figlio)
3. `day_variant` (figlio) ← spostato qui prima di material_turn
4. `material_turn` (padre) ← ora per ultimo

Nessuna migrazione DB necessaria: è solo un riordino di statement.

### File modificato
- `src/database/db.py::clear_all()` — ordine DELETE corretto

---

## 2026-04-16 — Fix routing SPA su Railway (404 su /login)

### Problema
Aprendo `web-production-0e9b9b.up.railway.app/login` (o qualsiasi altra route React Router come `/treni`, `/turni`, ecc.) il server rispondeva `{"detail":"Not Found"}` invece di servire il frontend.

### Causa
`StaticFiles(html=True)` di Starlette serve `index.html` solo per la root `/`. Per qualsiasi altro path che non corrisponde a un file statico esistente ritorna 404. Le route SPA gestite lato client da React Router non sono file fisici sotto `frontend/dist/`, quindi cadevano nel 404.

### Fix
- `server.py`: nuova classe `SPAStaticFiles(StaticFiles)` che cattura il 404 e fa fallback a `index.html`, così React Router può gestire la route lato client.
- Eccezione: i path che iniziano con `api/` o `vt/` mantengono il 404 originale (i client API ricevono JSON 404 coerente, non HTML).
- Mount `/` aggiornato per usare `SPAStaticFiles` al posto di `StaticFiles`.

### Verifica locale
| Route | Prima | Dopo |
|---|---|---|
| `/` | 200 (index.html) | 200 (index.html) |
| `/login` | 404 JSON | 200 (index.html → React Router) |
| `/treni` | 404 JSON | 200 (index.html → React Router) |
| `/api/health` | 200 JSON | 200 JSON |
| `/api/nonexistent` | 404 JSON | 404 JSON (immutato) |
| `/favicon.svg` | 200 | 200 |

### File modificato
- `server.py` — aggiunta classe `SPAStaticFiles`, mount `/` aggiornato

---

## 2026-04-15 — Skill turno materiale reader

### Contesto appreso (insegnato dall'utente con screenshot PDF)
Il PDF turno materiale Trenord ha struttura Gantt orizzontale:
- **Asse X**: ore 0-23
- **Colonna sinistra**: periodicita (LV 1:5, 6, F, Effettuato 6F) + numero giro
- **Segmenti**: stazione origine (verde) → numero treno (blu) → stazione arrivo (verde)
- **Barra rossa**: durata viaggio, numeri sotto = minuti partenza/arrivo
- **Suffisso "i"**: materiale vuoto (senza passeggeri), destinazione tipica Fiorenza
- **DISPONIBILE**: materiale fermo, nessun servizio
- **Colonna "Per"**: sequenza giornate + Km

### Skill creata
- `.claude/skills/turno-materiale-reader.md` — skill completa con:
  - Struttura documento PDF
  - Come leggere la griglia Gantt
  - Codici periodicita (LV, 6, F, 6F)
  - Tipologie segmenti (commerciale, vuoto, disponibile)
  - Schema JSON per estrazione dati strutturati
  - Relazione turno materiale → turno personale
  - Note per implementazione parser

### Memory aggiornata
- `reference_turno_materiale.md` — puntatore rapido alla skill
