# COLAZIONE — Sistema Gestionale Personale di Macchina

## Regole operative OBBLIGATORIE

1. **Leggi sempre `LIVE-COLAZIONE.md`** all'inizio di ogni conversazione per avere il contesto aggiornato di tutte le modifiche fatte
2. **Dopo ogni task completato** (feature, fix, refactoring, qualsiasi modifica):
   - Aggiorna `LIVE-COLAZIONE.md` con le modifiche fatte
   - Fai `git add` dei file modificati
   - Fai `git commit` con messaggio descrittivo
   - Fai `git push`
3. **Mai lavorare senza contesto**: se non hai letto LIVE-COLAZIONE.md, leggilo prima di fare qualsiasi cosa
4. **Leggi `docs/METODO-DI-LAVORO.md`** all'inizio di ogni sessione (subito dopo `LIVE-COLAZIONE.md`). È il framework di comportamento ispirato all'affidabilità lavorativa giapponese — fiducia attraverso i fatti, diagnosi prima di azione, un passo alla volta completato bene, ammettere l'errore, verifica prima del commit, preservare non distruggere, costanza nel tempo. NON È opzionale. Nei momenti di fretta o frustrazione è proprio quando serve fermarsi e ri-consultarlo.
5. **Design UX/UI → SEMPRE via Claude Design** (claude.ai/design, by Anthropic Labs): quando la conversazione riguarda aspetto visivo, layout, interazioni, design system, nuove schermate, restyle di componenti, mockup, wireframe → NON iniziare a generare CSS/Tailwind inline o proporre markup a mano.

   **PRECONDIZIONE — Claude Design conosce GIÀ questa cartella.** L'utente ha collegato su claude.ai/design sia il repo GitHub `87tickly/turni-pdm` sia la cartella locale `COLAZIONE` come contesto filesystem diretto. Claude Design può leggere componenti sorgente, token CSS (`frontend/src/index.css`), reference (`docs/REFERENCE-*.html`, `docs/HANDOFF-claude-design.md`), screenshot già salvati. **NON serve preparare bundle di upload** (zip, copie, cartelle materiale). Serve solo un **prompt mirato**.

   **Workflow quando l'utente chiede "redesign X"**:
   1. NON scrivere CSS/JSX
   2. Scrivere un prompt mirato in `docs/PROMPT-claude-design-{feature}.md` che specifichi:
      - **Cosa redesignare**: path file + nome componente (es. `frontend/src/components/PdcGanttV2.tsx`)
      - **Cosa non va oggi**: riferimento a screenshot o descrizione del pain point
      - **Vincoli funzionali da preservare**: props, interazioni (drag/resize/click), API consumate, callback
      - **Principi DS applicabili**: link a `docs/HANDOFF-claude-design.md` (Claude Design lo legge da sé)
      - **Deliverable atteso**: hi-fi mockup + handoff markdown pronto per Claude Code
   3. L'utente copia il prompt su claude.ai/design, riceve l'handoff, me lo mostra
   4. SOLO POI implemento il React

   **Motivo**: Claude Design ha Claude Opus 4.7 vision + lettura codebase, produce risultati migliori del disegnare ad-hoc in chat. Un prompt mirato (30 sec) + 10 min in Claude Design = risparmio di 5-10h di iterazioni CSS frustranti.

## STRUTTURA VERA di un turno PdC (memorizzato 21/04/2026)

Referenza: **turno ALOR_C [65046]** impianto ALESSANDRIA, profilo Condotta,
valido 23/02/2026 - 12/12/2026 (PDF "Turni PdC rete RFI dal 23 Febbraio 2026",
pagine 386-387). Da studiare **prima di toccare l'algoritmo del builder**.

### Un turno ha N giornate × M varianti calendario

Il turno ALOR_C ha **5 giornate lavorative (1-5) + 2 riposi** (ciclo 5+2).
Ogni giornata ha varianti per giorno settimana:
- **LMXGV** = feriale (Lun Mar Mer Gio Ven)
- **S** = Sabato
- **D** = Domenica
- **SD** = Sab/Dom combinata (quando uguali)
- **F** = Festivo infrasettimanale (variante specifica)

Stesse giornate ma **sequenze di treni COMPLETAMENTE DIVERSE** tra LMXGV e S
e D. Domenica (D) spesso è `S.COMP AL` = disponibilita' a riposo.

### Cct (condotta) reale: 2-3h, NON 4-5h

Numeri letti dalle 5 giornate LMXGV del turno ALOR_C:
- G1: Cct 02:28 (148 min), Lav 05:13 — **ratio 47%**
- G2: Cct 02:53 (173 min), Lav 08:17 — **ratio 35%**
- G3: Cct 03:33 (213 min), Lav 08:30 — **ratio 42%**
- G4: Cct 02:16 (136 min), Lav 08:05 — **ratio 28%**
- G5: Cct 01:45 (105 min), Lav 06:07 — **ratio 29%**

**Media condotta: ~2h30-3h. Media prestazione: ~7h. Ratio medio: 35%.**

Il mio scoring pre-esistente puntava a ratio 60-70% → **SBAGLIATO**.

### Uso massiccio di VETTURA (posizionamento + rientro)

Giornata 2 LMXGV (il caso da analizzare a fondo):
```
AL → (11055 VOGH)  [VETTURA 49' + 4']  Vogh
   → 2316 Mlce     [CONDOTTA 55']      Milano Centrale
   → U316 FlOz     [CONDOTTA 16' + 6'] Fiorenza
   → (59AS Mlba)   [VETTURA 38' + 55'] Milano Bovisa
   → (24135 Mlro)  [VETTURA 6' + 33']  Milano Rogoredo
   → REFEZ Mlro    [PAUSA 30']         Mlro
   → 10045 AL      [CONDOTTA 56' + 41'] Alessandria
   → CVa 10062 AL  [CAMBIO VOLANTE ARRIVO] AL
```

**7 segmenti**: 4 VETTURA + 2 CONDOTTA + 1 REFEZIONE + 1 CVa. Solo 2
treni guidati, gli altri tutti passivi per posizionarsi o rientrare.

### Simboli nel PDF turno PdC

- `(NUMERO STAZ` = treno in **vettura** (PdC passeggero)
- `NUMERO STAZ` (barra continua nera) = treno in **condotta** (PdC guida)
- `●NUMERO` = **preriscaldamento** (tempi maggiorati per preparare il mezzo)
- `CVp NUMERO` = **Cambio Volante in Produzione** (PdC cambia treno guidando)
- `CVa NUMERO` = **Cambio Volante in Arrivo** (altro tipo di cambio in arrivo)
- `REFEZ STAZ` = **refezione** (pausa pasto) in stazione specifica
- `(VOCTAXI` = **vettura occasionale in TAXI** (quando non c'e' treno)
- `●10020 Tr 10020 tempi maggiorati per preriscaldo` = nota operativa

### Pattern algoritmico corretto (per prossima iterazione builder)

Il builder attuale cerca **catene di treni-condotta dal deposito**. Sbagliato.
Il builder giusto deve partire dal **punto di condotta** e costruire:

1. **STEP 1 - Seleziona il/i treno/i produttivo/i**: 1-2 treni che il PdC
   guida, condotta totale target **2-3h** (non 4-5h)
2. **STEP 2 - Posizionamento iniziale**: dal deposito alla stazione di
   inizio condotta, tipicamente in **vettura** su 1-3 treni passivi
3. **STEP 3 - Refezione**: 30 min in stazione compatibile, durante il gap
   tra treni condotta o prima/dopo
4. **STEP 4 - Rientro**: dal punto di fine condotta al deposito, in
   vettura o condotta
5. **STEP 5 - Valida**: prestazione ≤ 8h30, condotta ≤ 5h30, refezione in
   finestra, riposo dopo turno

**Il turno vero e' CENTRATO SULLA CONDOTTA, non sulla catena dal deposito.**

### Non fossilizzarsi e NON gettare la spugna

L'utente ha pazienza limitata (giustamente) per:
- Risposte tipo "funziona cosi e cosi"
- "Dataset povero quindi impossibile"
- "E' un problema architetturale da fare in sessione futura"

Tutti questi sono modi di gettare la spugna. Prima di dare una di queste
risposte, rileggere `docs/METODO-DI-LAVORO.md` (regole 1, 3, 7):
- **Diagnosi prima di azione**: quando il builder sceglie sempre Pavia,
  verifica davvero qual e' lo score delle alternative, perche' vengono
  scartate, cosa cambia aggiungendo bonus
- **Un passo alla volta**: ogni fix testato con numeri, non "dovrebbe
  funzionare"
- **Costanza nel tempo**: il problema di Alessandria non si risolve "dopo"
  o "in sessione dedicata" — si risolve ora con 2-3 ore di riprogettazione
  algoritmica se serve

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
