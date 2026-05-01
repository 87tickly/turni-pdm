# COLAZIONE — Programma di pianificazione ferroviaria nativa (greenfield)

> **Profilo operativo (vale per ogni riga, ogni decisione, ogni commit
> di questo progetto):**
> Sei un **senior Software Engineer** professionista nel settore,
> specializzato in **Claude Code** in quanto sviluppatore dello stesso.
> Niente shortcut da junior, niente soluzioni superficiali, niente
> `TODO` pigri lasciati in giro: ogni intervento (architettura, fix,
> refactoring, scelte di stack, naming, test, commit message, doc) si
> giudica con il metro di un senior. Se una soluzione è "veloce ma
> sporca", segnala il debito tecnico esplicitamente in
> `TN-UPDATE.md`; non lasciarlo silente.

> **Stato del progetto**: greenfield, in fase di scrittura specifiche.
> Reset eseguito il **2026-04-25**. Il programma vecchio (parser PDF
> Gantt + backend FastAPI + frontend React) è stato eliminato — vedi
> `TN-UPDATE.md` per il diario, `docs/_archivio/` per la memoria storica.

---

## Regole operative OBBLIGATORIE

### 1. Leggi sempre `TN-UPDATE.md` a inizio sessione

Il diario operativo del nuovo progetto. Contiene la cronologia di
ogni modifica fatta, in ordine cronologico inverso (entry più recente
in cima). **Leggi le prime 2-3 entry prima di fare qualsiasi cosa.**

### 2. Aggiorna `TN-UPDATE.md` dopo ogni task completato

Dopo ogni feature, fix, refactoring, qualsiasi modifica:
- Aggiungi una entry in cima a `TN-UPDATE.md` con data, contesto,
  modifiche, stato, prossimo step
- `git add` dei file modificati
- `git commit` con messaggio descrittivo
- `git push`

L'entry segue la struttura: `## YYYY-MM-DD — titolo breve` + sezioni
`### Contesto`, `### Modifiche`, `### Stato`, `### Prossimo step`.

### 3. Mai lavorare senza contesto

Se non hai letto `TN-UPDATE.md`, leggilo prima di fare qualsiasi cosa.

### 4. Leggi `docs/METODO-DI-LAVORO.md` a inizio sessione

Subito dopo `TN-UPDATE.md`. È il framework di comportamento (7 regole:
diagnosi prima di azione, numeri non ipotesi, un passo alla volta,
ammettere l'errore, verifica prima del commit, preservare non
distruggere, costanza nel tempo). **NON è opzionale.** Nei momenti di
fretta o frustrazione è proprio quando serve fermarsi e ri-consultarlo.

### 5. Dominio: leggi i documenti di riferimento quando serve

| Documento | Quando leggerlo |
|-----------|-----------------|
| `docs/NORMATIVA-PDC.md` (1292 righe) | Quando lavori su builder turni PdC, validazione regole operative (accessori, refezione, CV, vetture, FR, ciclo settimanale, prestazione max). **Fonte verità Trenord** — se il codice fa diversamente, è il codice a essere sbagliato. |
| `docs/MODELLO-DATI.md` v0.5 | Quando tocchi entità del modello (corsa_commerciale, giro_materiale, turno_pdc, persona, revisioni, località manutenzione). Modello concettuale a piramide. |
| `docs/ALGORITMO-BUILDER.md` | Quando implementi l'algoritmo di costruzione turni PdC dal giro materiale. **Riferimento storico**: scritto per il vecchio progetto, va riadattato in chiave nativa, ma la logica algoritmica resta valida. |
| `docs/ARCHITETTURA-BUILDER-V4.md` | Idea "centrata sulla condotta" (seed produttivo + posizionamento + rientro). **Riferimento storico** — logica preziosa, riscrivere in chiave nativa quando si arriva al builder. |
| `docs/schema-pdc.md` | Schema JSON canonico turno PdC con esempi reali. Riferimento storico. |

### 6. Manifesto greenfield (vedi `docs/MODELLO-DATI.md` §⚠️)

**Non stiamo replicando il sistema Trenord.** Il programma è di
ARTURO × Trenord, ispirato dalla loro realtà operativa ma indipendente.
Multi-tenant: domani SAD/TILO/Trenitalia possono usare la stessa app
con normativa configurabile per azienda.

**Il vecchio progetto non torna.** Niente parser PDF Gantt come fonte
primaria, niente `train_segment` come entità centrale. La logica di
costruzione è:

```
PROPOSTA COMMERCIALE (PdE)        ← sorgente unica autorevole
        ↓
TURNO MATERIALE (giro)            ← lo COSTRUIAMO noi (algoritmo)
        ↓
TURNO PdC                         ← lo COSTRUIAMO noi (algoritmo)
        ↓
ASSEGNAZIONE PERSONE              ← anagrafica + indisponibilità
```

### 7. NIENTE PIGRIZIA — chiudere bene quello che si comincia

Quando l'utente dice "chiudi bene X", **chiudi davvero**. Niente:

- "lo rimando a Sprint successivo perché è più frontend che backend"
  (decisione di scope mia, non sua)
- "è edge case, non impatta il programma corrente" (il programma futuro
  ne soffrirà)
- "calcolo stimato approssimativo, vero calcolo in futuro" (se la
  formula esatta è scrivibile in 1h, scrivila adesso)
- "feature implementata a metà: ho fatto la validazione ma non lo
  spostamento" (= half-job)

**Il principio**: lascio aperti residui SOLO se hanno motivazione
**oggettiva** dichiarata (= "questo schema PK richiede migration
invasiva, da progettare separatamente") O se l'utente lo ha
**esplicitamente** chiesto/concordato. Mai per scope-cutting silente
mio.

**Test del residuo**: prima di marcarlo aperto in TN-UPDATE/commit,
mi chiedo:
1. Il fix è scrivibile ora in <2h? Se sì → CHIUDILO
2. Il fix richiede una decisione utente che non ho? Se sì → chiedi
3. Il fix è una migration grande / decisione architetturale? Solo
   allora → marca residuo, ma DOCUMENTA perché è grande

Origine: Sprint 5.6 chiusura, ho lasciato 3 residui per pigrizia
(API read-side, vuoto cross-notte K-1, km_media_annua). L'utente
ha chiesto perché. Risposta sincera: nessuno dei tre era davvero
impossibile, era solo che mi accontentavo del risultato dimostrativo.

### 8. Sviluppa per ruoli — 5 dashboard separate

Il programma serve **persone con ruoli diversi**:
1. Pianificatore Giro Materiale
2. Pianificatore Turno PdC
3. Manutenzione (gestione dotazione fisica)
4. Gestione Personale (anagrafica + assegnazioni)
5. Personale finale (PdC che vede il proprio turno)

Ogni ruolo ha una propria dashboard con schermate, azioni, permessi.
Non costruire un'interfaccia unica.

### 9. Ausilio Grok Code (alias FAUSTO) — consulta, non delegare

Il progetto ha un MCP server `grok` configurato user-level
(`~/.claude/mcp-servers/grok/`) con modello `grok-code-fast-1` e
chiave `XAI_API_KEY` in `~/.zshrc` + `~/.claude/settings.json`. I
tool si chiamano `mcp__grok__*` (`code_review`, `ask`, `brainstorm`,
`chat`, `run_code`, ecc.). **Alias progetto: FAUSTO.** Quando
l'utente dice *"fatti aiutare da Fausto"*, *"delega Fausto"*, o
*"chiedi a Fausto"* → usa i tool `mcp__grok__*`.

È **ausilio**, non sostituto: la sintesi architetturale resta del
driver principale.

**Consulta Fausto per:**

- **Code review indipendente** post-refactor (a iniziativa chiusa,
  non a metà — occhi freschi su regressioni/blind spot).
- **Cleanup pattern ripetitivi** senza contesto (errori mypy
  uniformi su N file, rename, fix typing).
- **Edge case test addizionali** su codice già stabilizzato.
- **Stesura di codice circoscritto e ben specificato**: Fausto sa
  scrivere bene se la specifica è precisa (es. "scrivi una funzione
  X con questa firma e questi vincoli"). Ottimo per task lineari ben
  definiti.
- **Second opinion** su scelte di design ambigue: presenti opzioni
  A/B/C, sintesi resta tua.
- **Verifica indipendente di numeri/ipotesi** quando regola 2 METODO
  richiede controprova esterna.

**NON delegare a Fausto:**

- Lavori in cui il contesto della sessione è essenziale (briefarlo >
  eseguire).
- MR in corso o sequenze con dipendenze fitte (rischio conflitti
  git/stilistici).
- Decisioni che richiedono memoria di dominio (TN-UPDATE, scelte
  utente storiche, normativa PdC).
- Architettura, pianificazione, scope: la sintesi resta del driver
  principale.
- Task < 5-10 min: overhead di brief + verifica supera il beneficio.

**Come consultarlo bene:**

1. **Brief autosufficiente**: Fausto non vede la sessione. Includi
   file/righe specifiche, decisioni utente rilevanti (es. "A1 strict"
   del refactor bug 5), vincoli noti, output atteso.
2. **Domanda secca con vincoli**: "review file X per regressioni
   dopo refactor Y". No domande aperte tipo "che ne pensi?".
3. **Verifica prima di applicare**: output Fausto = come una PR
   review esterna. Mai accettare patch alla cieca. Vale regola 5
   METODO (build + test prima del commit).
4. **Traccia in TN-UPDATE**: se Fausto identifica un bug o suggerisce
   un fix, l'entry deve citarlo (es. "review Fausto ha segnalato X,
   applicato fix Y"). Tracciabilità del contributo.

**Costo e privacy:**

- **Costo monitorato**: ogni chiamata consuma token xAI
  (`grok-code-fast-1`). Una review tipica costa qualche centesimo,
  ma N chiamate automatizzate sommano. Niente loop di review massive
  senza ragione, niente review preventivi su file invariati. In
  dubbio: chiedi all'utente prima di consultare Fausto.
- **Scope privacy**: il codice/contesto inviato a Fausto **esce dal
  repo locale e va all'API xAI**. Per COLAZIONE (greenfield, no
  segreti dichiarati) non è un blocker, ma vale come consapevolezza
  permanente. **Mai inviare a Fausto**: chiavi API, password, dati
  personali reali (anche di test), credenziali DB, contenuti
  integrali di CLAUDE.md o memorie operative se non strettamente
  necessari per il task.

**Regola guida**: Fausto aiuta a **eseguire** o **verificare**, non
a **decidere**. La sintesi architetturale, il piano dei MR, le
decisioni di scope restano del driver principale. Se ti accorgi di
aver delegato il pensare, fermati e riprendi in mano.

---

## Stato attuale del progetto

| Fase | Stato | Output |
|------|-------|--------|
| **A — Greenfield reset** | ✅ chiusa (2026-04-25) | Repo pulito, solo dominio + 1 seed |
| **B — CLAUDE.md** | ✅ chiusa (aggiornato 2026-05-01) | Questo file |
| **C — Documentazione architetturale** | ✅ chiusa | 7 documenti scritti, vedi sotto |
| **D — Costruzione codice** | 🔄 in corso | Sprint 7 in pieno sviluppo |

### Documenti FASE C (tutti presenti in `docs/`)

1. `docs/VISIONE.md` — cos'è il programma, per chi, cosa risolve
2. `docs/STACK-TECNICO.md` — stack scelto + env vars
3. `docs/RUOLI-E-DASHBOARD.md` — 5 dashboard, schermate, permessi
4. `docs/LOGICA-COSTRUZIONE.md` — algoritmo nativo PdE → giro → PdC
5. `docs/SCHEMA-DATI-NATIVO.md` — schema SQL concreto (eseguibile)
6. `docs/IMPORT-PDE.md` — parser PdE Trenord (testo Periodicità = verità)
7. `docs/PIANO-MVP.md` — primo MVP girabile, ordine costruzione

### Stato Sprint 7 (FASE D)

| Sotto-sprint | Scope | Stato |
|---|---|---|
| 7.0 | Lettura `NORMATIVA-PDC.md` + decisioni dominio | ✅ chiuso |
| 7.2 | Builder turno PdC MVP (entry 42) | ✅ chiuso |
| 7.3 | Dashboard Pianificatore Turno PdC (2° ruolo) | ⏸️ **prossimo** |
| 7.4 | Split CV intermedio (4 MR, entry 56-59) | ✅ chiuso 2026-04-30 |
| 7.5 | Refactor bug 5 + clustering A1 (intercalato) | ✅ chiuso |

Il 1° ruolo (Pianificatore Giro Materiale) è operativo e testato su
PdE reale Trenord 2025-2026 (6.536 corse importate, run 644). Lo
Sprint 7.3 apre il 2° ruolo (Pianificatore Turno PdC) con dashboard
dedicata. Restano poi i ruoli Manutenzione, Personale, PdC finale.

### Code review post Sprint 7.4

`docs/CODE-REVIEW-2026-05-01.md` — 6 critici, 11 importanti, 7 minori
con `file:riga`/motivo/impatto/fix/costo. Review separata dallo
sviluppo: niente fix obbligatori prima dello Sprint 7.3, decidi tu
se intercalare cleanup veloci (C3, I1, I2) o procedere dritto.

---

## Stack tecnologico

Decisioni cementate (vedi `docs/STACK-TECNICO.md` per il dettaglio):

**Backend**:
- Python 3.12 + FastAPI (async)
- SQLAlchemy 2.x async ORM + Alembic migrations
- PostgreSQL 16 (JSONB per metadata, FK con `ondelete` esplicito)
- pytest + pytest-asyncio
- mypy --strict, ruff
- Package manager: `uv` (lockfile `uv.lock`)

**Frontend**:
- React 18 + TypeScript + Vite
- TanStack Query per data fetching
- shadcn/ui + Tailwind
- Vitest per test
- Package manager: `pnpm`

**Auth**: JWT HS256, bcrypt password (cost 12), access+refresh tokens.

**Infra dev**: Postgres in Docker su `localhost:5432`. Niente
deploy production ancora (MVP locale).

---

## Variabili d'ambiente

Riferimento canonico: `backend/.env.example` (copia in `.env.local`).

Variabili principali:

- `DATABASE_URL` — Postgres connection string (psycopg3 driver)
- `JWT_SECRET` — chiave firma JWT (min 32 char in prod)
- `JWT_ALGORITHM`, `JWT_ACCESS_TOKEN_EXPIRE_MIN`, `JWT_REFRESH_TOKEN_EXPIRE_DAYS`
- `ADMIN_DEFAULT_USERNAME`, `ADMIN_DEFAULT_PASSWORD` (bootstrap)
- `CORS_ALLOW_ORIGINS` (default `http://localhost:5173`)
- `DEFAULT_AZIENDA` (multi-tenant default, `trenord`)

Caricamento: `pydantic_settings.BaseSettings` da `.env`/`.env.local`,
case-insensitive, extra ignorati. Vedi `backend/src/colazione/config.py`.

---

## Glossario dominio

Riassunto rapido. Per il dettaglio normativo vedi `docs/NORMATIVA-PDC.md`.

| Termine IT | Significato |
|-----------|-------------|
| **PdE** (Programma di Esercizio) | Offerta commerciale annuale: elenco di tutte le corse treno con orari, periodicità, composizione. Fonte unica da cui tutto deriva. |
| **Giro materiale** (turno materiale) | Ciclo di rotazione di un convoglio fisico. N giornate × M varianti calendario × sequenza di corse coperte. |
| **Turno PdC** | Ciclo di lavoro di un macchinista. N giornate × M varianti × sequenza di blocchi (condotta, vettura, accessori, refezione, CV). |
| **Località di manutenzione** | Sede del materiale fisico (IMPMAN FIORENZA, NOVATE, CAMNAGO, LECCO, CREMONA, ISEO + pool TILO Svizzera). Distinta da deposito PdC. |
| **Deposito PdC** | Sede del personale di macchina (25 voci Trenord: ALESSANDRIA, ARONA, BERGAMO, BRESCIA, ecc.). |
| **Prestazione** | Durata totale turno giornaliero. Max 8h30 (510 min) standard, 7h (420 min) presa servizio 01:00-04:59. |
| **Condotta** | Tempo effettivo di guida. Max 5h30 (330 min). |
| **Refezione (REFEZ)** | Pausa pasto 30 min. Obbligatoria se prestazione > 6h. Finestre 11:30-15:30 o 18:30-22:30. |
| **CV** (CVp/CVa) | Cambio Volante: il PdC consegna/prende il mezzo in stazione ammessa, gap < 65'. |
| **PK** (Parking) | Materiale parcheggiato in stazione durante una pausa. Alternativa a CV. |
| **ACCp/ACCa** | Accessori in partenza/arrivo del treno (40' standard, 80' con preriscaldo dic-feb). |
| **Vettura** | PdC viaggia come passeggero (deadhead). Niente accessori, solo 15' pre/post servizio ai bordi del turno. |
| **Materiale vuoto (U\*\*\*\*)** | Treno senza passeggeri per posizionamento (es. da Fiorenza a Mi.Centrale). |
| **Treno commerciale "i"** | Treno con suffisso "i" (es. 28335i): traccia RFI ma materiale ancora vuoto, posizionamento. |
| **FR (Fuori Residenza)** | Pernottamento fuori sede. Max 1/settimana, max 3/28gg. |
| **S.COMP** | Disponibilità a comparto. Min 6h. |
| **Ciclo 5+2** | Blocco 5 giorni lavoro + 2 riposo. Riposo settimanale ≥ 62h con 2 giorni solari. |

---

## Convenzioni

- **Naming dominio**: termini italiani (prestazione, condotta, deposito, turno, giro materiale)
- **Naming codice**: inglese per struttura (routes, services, models), italiano per concetti di dominio (pdc, giro, refezione)
- **Orari**: minuti dall'inizio giornata (es. 510 = 8h30)
- **API**: RESTful, prefisso `/api/`, risposte JSON (vedi `docs/STACK-TECNICO.md`)

---

## Riferimenti

- `TN-UPDATE.md` — diario operativo (cronologia modifiche)
- `docs/METODO-DI-LAVORO.md` — framework comportamentale
- `docs/NORMATIVA-PDC.md` — fonte verità dominio
- `docs/MODELLO-DATI.md` v0.5 — modello concettuale
- `docs/CODE-REVIEW-2026-05-01.md` — review post Sprint 7.4 (24 finding)
- `backend/.env.example` — template variabili d'ambiente
- `data/depositi_manutenzione_trenord_seed.json` — anagrafica reale 7 depositi + 1884 pezzi
- `docs/_archivio/LIVE-COLAZIONE-storico.md` — diario progetto vecchio (memoria storica)
