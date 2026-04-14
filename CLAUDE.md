# COLAZIONE — Sistema Gestionale Personale di Macchina

## Regole operative OBBLIGATORIE

1. **Leggi sempre `LIVE-COLAZIONE.md`** all'inizio di ogni conversazione per avere il contesto aggiornato di tutte le modifiche fatte
2. **Dopo ogni task completato** (feature, fix, refactoring, qualsiasi modifica):
   - Aggiorna `LIVE-COLAZIONE.md` con le modifiche fatte
   - Fai `git add` dei file modificati
   - Fai `git commit` con messaggio descrittivo
   - Fai `git push`
3. **Mai lavorare senza contesto**: se non hai letto LIVE-COLAZIONE.md, leggilo prima di fare qualsiasi cosa

## Scopo

Software gestionale per la pianificazione turni del personale di macchina ferroviario.
Partito come tool specifico Trenord, sta diventando un sistema ibrido utilizzabile da qualsiasi azienda di trasporto ferroviario.

## Stack tecnologico

| Layer | Tecnologia | Note |
|-------|-----------|------|
| Backend | Python 3.12 + FastAPI | API REST, logica di business |
| Frontend | React + TypeScript (in migrazione) | Sostituisce il vecchio vanilla HTML |
| UI Kit | shadcn/ui (Radix + Tailwind) | Design moderno, minimale, alta densità dati |
| Desktop | Tauri (pianificato) | macOS + Windows |
| Database | SQLite (locale) / PostgreSQL (produzione) | Dual-mode via `DATABASE_URL` env var |
| Deploy | Railway CLI | `railway up` per staging/produzione |
| Dati real-time | ARTURO Live API (live.arturo.travel) | Sostituisce ViaggiaTreno diretto |
| Auth | JWT (python-jose) + bcrypt | Token 72h |

## Come avviare

```bash
# Backend (dev)
uvicorn server:app --reload --port 8002

# Test
python -m pytest tests/ -v

# CLI
python app.py info              # statistiche DB
python app.py train 10603       # cerca treno
python app.py station "MILANO CENTRALE"
python app.py build-auto --deposito MILANO --days 5
```

## Variabili d'ambiente

| Variabile | Obbligatoria | Default | Descrizione |
|-----------|-------------|---------|-------------|
| `DATABASE_URL` | No | SQLite `turni.db` | Connection string PostgreSQL per produzione |
| `JWT_SECRET` | Si in prod | `dev-secret-...` | Chiave firma JWT |
| `ADMIN_DEFAULT_PASSWORD` | No | random generata | Password iniziale admin |

## Struttura directory

```
COLAZIONE/
├── server.py                  # FastAPI app shell (62 righe: CORS + router includes)
├── app.py                     # CLI entry point
│
├── api/                       # Router FastAPI modulari
│   ├── deps.py                # Dipendenze condivise (DB, JWT auth)
│   ├── auth.py                # Register, login, admin
│   ├── health.py              # Health check, info DB
│   ├── upload.py              # Upload PDF
│   ├── trains.py              # Query treni, stazioni, giro materiale
│   ├── validation.py          # Validazione giornata, costanti
│   ├── builder.py             # Auto-builder, calendar
│   ├── shifts.py              # CRUD turni salvati/settimanali
│   ├── importers.py           # Import turno personale/PdC
│   └── viaggiatreno.py        # Dati real-time via ARTURO Live API
│
├── services/                  # Logica di business
│   ├── arturo_client.py       # Client API ARTURO Live (live.arturo.travel)
│   ├── segments.py            # Dedup, serializzazione segmenti
│   └── timeline.py            # Costruzione timeline visiva giornata
├── requirements.txt
├── turni.db                   # Database SQLite locale
├── turno_materiale_treni.json # Dati turni materiale estratti da PDF
├── fr_stations.txt            # Stazioni fuori residenza
│
│
├── src/
│   ├── constants.py           # Regole operative (da astrarre in config/)
│   ├── database/db.py         # Abstraction layer DB (SQLite/PostgreSQL)
│   ├── validator/rules.py     # Engine validazione turni
│   ├── turn_builder/
│   │   ├── auto_builder.py    # AI builder (genetico + simulated annealing)
│   │   └── manual_builder.py  # Builder interattivo CLI
│   ├── importer/
│   │   ├── pdf_parser.py      # Parser PDF Gantt Trenord
│   │   ├── turno_personale_parser.py
│   │   └── turno_pdc_parser.py
│   └── cli/main.py            # Comandi CLI
│
├── tests/                     # pytest
├── static/index.html          # Frontend legacy (da sostituire con frontend/)
└── uploads/                   # PDF caricati
```

## Glossario dominio

| Termine IT | Significato | Dettaglio |
|-----------|-------------|-----------|
| Turno materiale | Ciclo rotazione treni | Sequenza treni assegnati a un convoglio |
| Turno personale | Ciclo lavoro macchinista | Sequenza giornate lavorative + riposi |
| Segmento | Singola tratta treno | Da stazione A a B con orari |
| Prestazione | Durata totale turno giornaliero | Include condotta + pause + accessori. Max 8h30 (510 min) |
| Condotta | Tempo effettivo di guida | Max 5h30 (330 min) |
| Refezione | Pausa pasto | 30 min, finestre 11:30-15:30 o 18:30-22:30 |
| FR (Fuori Residenza) | Pernottamento fuori sede | Max 1/settimana, 3/28 giorni |
| Dormita | Notte in FR | Riposo minimo 6h fuori dal deposito base |
| Deposito | Sede operativa macchinista | Es. Milano Garibaldi, Brescia, Lecco |
| S.COMP | Disponibilità (a disposizione) | Min 6h (360 min) |
| Notturno | Turno tra 00:01-01:00 | Max 7h (420 min) |
| LV/SAB/DOM | Tipo giornata | Feriale / Sabato / Domenica |
| Ciclo 5+2 | Blocco lavoro-riposo | 5 giorni lavoro + 2 riposo |

## Regole operative chiave

- **Prestazione**: max 510 min (8h30) con accessori inclusi
- **Condotta**: max 330 min (5h30)
- **Refezione**: 30 min obbligatori in finestra 11:30-15:30 o 18:30-22:30
- **Riposo tra turni**: 11h standard, 14h dopo fine 00:01-01:00, 16h dopo notturno
- **Riposo settimanale**: min 62h
- **Ore settimanali**: target 35h30, min 33h, max 38h
- **FR**: max 1/settimana, max 3 in 28 giorni, riposo min 6h

## Convenzioni

- **Naming dominio**: termini italiani (prestazione, condotta, deposito, turno)
- **Naming codice**: inglese per struttura (routes, services, models), italiano per concetti di dominio
- **Orari**: sempre in minuti dall'inizio giornata (es. 510 = 8:30)
- **Database**: migrazioni idempotenti via `_run_migration()` in db.py
- **API**: RESTful, prefisso `/api/`, risposte JSON
- **Frontend**: React + TypeScript, componenti shadcn/ui, Tailwind CSS

## Roadmap

| Phase | Stato | Descrizione |
|-------|-------|-------------|
| Phase 0 | In corso | Ristrutturazione backend: split server.py, config multi-azienda, sicurezza |
| Phase 1 | Pianificato | Nuovo frontend React + Tauri desktop shell |
| Phase 2 | Futuro | Multi-azienda completo, gestionale personale esteso |

## AI Builder (auto_builder.py)

Algoritmo a 4 fasi per costruzione automatica turni:
1. **POOL**: genera catene treni candidati via DFS (depth=10, branch=4)
2. **BUILD**: scheduling greedy multi-restart (25 tentativi)
3. **EVOLVE**: crossover genetico sui migliori 8 candidati (15 round)
4. **REFINE**: simulated annealing (40 iterazioni, T: 300→10)

Non toccare questo modulo in Phase 0 — è già ben strutturato.

## Note importanti

- `pdf_parser.py` contiene costanti geometriche specifiche per i PDF Gantt Trenord — è specifico per natura
- Il vecchio `static/index.html` (5441 righe) verrà sostituito completamente dal nuovo frontend React
- Il deploy è sempre via Railway CLI (`railway up`)
- SQLite è il DB primario per uso desktop; PostgreSQL solo per deploy web
