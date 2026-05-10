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
- `git push` su `origin/master`
- **Deploy Railway**: dopo il push, rilanciare il deploy dei servizi
  toccati così la produzione resta allineata con `master`. Decisione
  utente 2026-05-04: "ogni modifica → commit + push + main su Railway".
  Comandi tipici (CLI già linkato a progetto `Arturo-Turni`):
  ```
  # Backend (backend/, models, migrations, schemas, domain logic)
  railway link --service backend --project Arturo-Turni \
              --environment production
  railway up --detach --service backend
  ```
  ```
  # Frontend (frontend/, route, hook, lib)
  railway link --service frontend --project Arturo-Turni \
              --environment production
  railway up --detach --service frontend
  ```
  Se la modifica è solo backend → solo `railway up --service backend`,
  e simmetricamente per frontend. Se la modifica tocca SOLO `*.md` o
  `docs/`, salta il deploy (commit+push bastano). Migration Alembic
  vengono applicate automaticamente al boot del backend (CMD =
  `alembic upgrade head && uvicorn ...`).
  Verifica post-deploy: `railway logs --service <name>` per build/runtime.

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

### 9. Codice scritto SEMPRE con ausilio — NINO + FAUSTO + AMILCARE + SEVERO

**Decisione 2026-05-08**: ogni riga di codice del programma COLAZIONE
è scritta da **NINO** (Claude Code, driver principale) con l'ausilio
di **FAUSTO** e **AMILCARE**. NINO da solo è ammesso solo per task
triviali (rename, typo, una riga di config). Per qualunque altra cosa
l'ausilio è **la norma, non l'eccezione**.

**Decisione 2026-05-08 (sera)**: aggiunto **SEVERO**, quarto attore.
SEVERO non scrive né esegue codice — è il **critico permanente** che
giudica i commit a fine Sprint o dopo MR significativo, partendo dal
presupposto che si poteva fare meglio. Motore di ragionamento
sostanziale = AMILCARE (no bias auto-compiacenza). Definizione
subagent in `.claude/agents/severo.md`.

**Il framework completo (matrice di decisione, workflow, brief,
costi, privacy, trigger linguistici) sta in
`docs/AUSILI-CODICE.md`** — leggilo a inizio sessione insieme a
TN-UPDATE e METODO.

**Riassunto attori (il dettaglio è nel doc):**

- **NINO** = Claude Code. Driver principale. Possiede contesto della
  sessione, memoria del progetto, decisioni utente storiche. Non
  delega mai: architettura, scope, sintesi finale, decisioni di
  dominio.
- **FAUSTO** = Grok Code (`grok-code-fast-1` via xAI). MCP server
  `grok` user-level (`~/.claude/mcp-servers/grok/`), tool namespace
  `mcp__grok__*`. Forte di velocità, review veloci, stesura di
  codice circoscritto, cleanup ripetitivi.
- **AMILCARE** = DeepSeek V4 Pro (`deepseek/deepseek-v4-pro` via
  OpenRouter). MCP server `~/Developer/deepseek-claude-MCP-server/`,
  tool namespace `mcp__amilcare__*`. Forte di ragionamento esteso,
  context 1M token, edge case profondi, refactor architetturali.
  Modello scelto = il top (V4 Pro, non Flash) per qualità del
  ragionamento. SWE-bench 80.6%, LiveCodeBench 93.5%.
- **SEVERO** = subagent Claude Code definito in
  `.claude/agents/severo.md`. Critico permanente post-commit,
  giudica con tono partendo dal presupposto che si poteva fare
  meglio. Non è dalla parte dell'utente né di NINO. Motore di
  giudizio sostanziale = AMILCARE (delegato dal subagent). Output
  canonico in `docs/critiche/`. Mai scrive codice, mai committa.

**Trigger linguistici**:
- *"chiedi a Fausto"* / *"delega Fausto"* → `mcp__grok__*`
- *"chiedi ad Amilcare"* / *"chiedi a deepseek"* → `mcp__amilcare__*`
- *"chiedi a SEVERO"* / *"fai criticare"* / *"review severa"* /
  *"giudica l'ultimo commit"* → `Agent` tool con
  `subagent_type=severo` (NON chiamare AMILCARE direttamente:
  è SEVERO che internamente delega)
- Quando l'utente non specifica, NINO sceglie in base alla taglia
  e natura del task (vedi matrice §2 di `docs/AUSILI-CODICE.md`).

**Regola guida**: FAUSTO e AMILCARE aiutano a **eseguire** o
**verificare**; SEVERO aiuta a **criticare**; nessuno dei tre
**decide**. La sintesi architetturale, le scelte di scope e le
decisioni di dominio restano sempre di NINO + utente. Ogni
intervento di FAUSTO/AMILCARE/SEVERO va **tracciato in TN-UPDATE**
con finding e azione presa (false positive inclusi).

**Invocazione SEVERO — quando è obbligatorio**:

SEVERO va invocato in modo sistematico (non opzionale) nei seguenti
casi:

1. **A fine Sprint** (es. Sprint 7.3, 8.1, ecc.) — prima di marcare
   lo Sprint come ✅ chiuso in CLAUDE.md o nell'entry TN-UPDATE
   conclusiva.
2. **Dopo un MR significativo** — multi-file, refactor di logica
   di dominio, cambio architetturale, nuovo algoritmo, nuova
   entità nel modello dati, nuovo endpoint API non triviale.
3. **Quando l'utente lo chiede esplicitamente** — vedi trigger
   linguistici sopra.

SEVERO **NON** va invocato per:
- Micro-commit (typo, doc, rename triviale, una riga di config)
- Hotfix urgenti (riprendere dopo)
- Quando NINO o l'utente sono incerti sull'esito ma vogliono
  procedere comunque (la critica è retrospettiva, non blocca)

L'output di SEVERO (file in `docs/critiche/`) **non è una direttiva**
da applicare alla cieca: è input per la decisione successiva di
NINO + utente. Eventuali fix accettati diventano nuovi MR (mai
correzioni in-place del MR criticato).

---

## Stato attuale del progetto

| Fase | Stato | Output |
|------|-------|--------|
| **A — Greenfield reset** | ✅ chiusa (2026-04-25) | Repo pulito, solo dominio + 1 seed |
| **B — CLAUDE.md** | ✅ chiusa (aggiornato 2026-05-10) | Questo file |
| **C — Documentazione architetturale** | ✅ chiusa | 7 documenti scritti, vedi sotto |
| **D — Costruzione codice** | 🔄 in corso | Sprint 8.3 backlog cleanup (Sprint 7 e 8.0/8.1/8.2 chiusi) |

### Documenti FASE C (tutti presenti in `docs/`)

1. `docs/VISIONE.md` — cos'è il programma, per chi, cosa risolve
2. `docs/STACK-TECNICO.md` — stack scelto + env vars
3. `docs/RUOLI-E-DASHBOARD.md` — 5 dashboard, schermate, permessi
4. `docs/LOGICA-COSTRUZIONE.md` — algoritmo nativo PdE → giro → PdC
5. `docs/SCHEMA-DATI-NATIVO.md` — schema SQL concreto (eseguibile)
6. `docs/IMPORT-PDE.md` — parser PdE Trenord (testo Periodicità = verità)
7. `docs/PIANO-MVP.md` — primo MVP girabile, ordine costruzione

### Stato sviluppo (FASE D)

| Sprint | Scope | Stato |
|---|---|---|
| 7.0-7.5 | Builder turno PdC MVP + split CV + dashboard pianificatore giro (1° ruolo) | ✅ chiuso |
| 7.6-7.9 | Refactor bug 5 + clustering A1 + km_cap per regola + varianti per giornata + festività ufficiali | ✅ chiuso |
| 8.0 | Concatenazione fra ruoli (6 MR Fase A+B+C + dashboard admin pipeline trasversale, entry 164-175) | ✅ chiuso 2026-05-05 |
| 8.1 | Backtracking esplorativo giri lunghi + cross-rule contamination fix (MR-B1/B2/B3) | ✅ chiuso 2026-05-09 |
| 8.2 | **Piano α Pianificatore Turno PdC** (deposito-first, vettura_resolver, registro vetture cross-PdC, §11.4/§11.5/§15) + **Plan-D builder giro linea-centrica** (parallelo, MR-D5e→MR-D6) | ✅ chiuso 2026-05-10 |
| 8.3 | Backlog cleanup post Sprint 8.2 (S3 hook alembic + S4 from_db JOIN + S5/S6/S10 cleanup + S7 integration test + S8 §11.4 strisce + S9 parser DSL etichette parlanti) | 🔄 **in corso** |

Il 1° ruolo (Pianificatore Giro Materiale) è operativo e testato su
PdE reale Trenord 2025-2026 (6.536 corse importate). Sprint 8.2 ha
chiuso il **piano α del 2° ruolo** (Pianificatore Turno PdC con builder
deposito-first opt-in, validatori §11.4/§11.5/§15) — il MVP è
generabile via API `POST /api/giri/{id}/genera-turno-pdc?builder_strategy=deposito_first`.
Restano poi i ruoli Manutenzione, Gestione Personale, PdC finale.

### Code review post Sprint 7.4

`docs/CODE-REVIEW-2026-05-01.md` — 6 critici, 11 importanti, 7 minori
con `file:riga`/motivo/impatto/fix/costo. Review separata dallo
sviluppo (riferimento storico, parte dei finding già coperti negli
Sprint 7.6+ e 8.0).

### Critiche SEVERO (post-Sprint)

`docs/critiche/` — output canonico delle critiche di SEVERO post-MR
significativi e fine-Sprint. Vedi `docs/critiche/README.md` per
l'indice. Critica chiave Sprint 8.2:
`SPRINT-8.2-PIANO-ALPHA-RETROSPETTIVA.md` — voto 5/10 fallback NINO,
10 finding (HIGH S1+S2 chiusi entry 286, MED+LOW chiusi nello
Sprint 8.3 corrente).

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
- `docs/AUSILI-CODICE.md` — NINO + FAUSTO + AMILCARE + SEVERO (regola §9)
- `.claude/agents/severo.md` — definizione subagent SEVERO (critico)
- `docs/critiche/` — output canonico critiche di SEVERO + indice
- `docs/NORMATIVA-PDC.md` — fonte verità dominio
- `docs/MODELLO-DATI.md` v0.5 — modello concettuale
- `docs/CODE-REVIEW-2026-05-01.md` — review post Sprint 7.4 (24 finding)
- `backend/.env.example` — template variabili d'ambiente
- `data/depositi_manutenzione_trenord_seed.json` — anagrafica reale 7 depositi + 1884 pezzi
- `docs/_archivio/LIVE-COLAZIONE-storico.md` — diario progetto vecchio (memoria storica)
