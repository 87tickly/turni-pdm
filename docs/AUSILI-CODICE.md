# AUSILI ALLO SVILUPPO CODICE — NINO con FAUSTO, AMILCARE e SEVERO

> **Decisione 2026-05-08**: da oggi ogni riga di codice del programma
> COLAZIONE è scritta da **NINO** con l'ausilio di **FAUSTO** e
> **AMILCARE**. NINO da solo è ammesso solo per task triviali (rename,
> typo, una riga di config); per qualunque altra cosa l'ausilio è la
> norma, non l'eccezione.
>
> **Decisione 2026-05-08 (sera)**: aggiunto **SEVERO**, quarto attore.
> SEVERO non scrive né esegue codice — è il **critico permanente** che
> giudica i commit a fine Sprint o dopo MR significativo, partendo dal
> presupposto che si poteva fare meglio. Motore di ragionamento =
> AMILCARE (no bias auto-compiacenza). Definizione subagent in
> `.claude/agents/severo.md`.
>
> Questo documento sostituisce ed estende la sezione 9 di
> `CLAUDE.md` (vecchia "Ausilio Grok Code"), che ora copriva solo
> FAUSTO. Da ora il framework è **a quattro attori**: tre coder
> (NINO, FAUSTO, AMILCARE) + un critico (SEVERO).

---

## 1. Chi è chi

### NINO — il driver principale

- **Identità**: Claude Code (CLI Anthropic) — l'AI che dialoga con
  l'utente nella sessione corrente.
- **Ruolo**: orchestratore, decisore, autore finale del codice che
  finisce nel repo. È l'unico ad avere il **contesto pieno della
  sessione** e la memoria viva del progetto.
- **Possiede**:
  - Lettura di `TN-UPDATE.md` e `docs/METODO-DI-LAVORO.md` a inizio
    sessione (regole 1 e 4 di CLAUDE.md)
  - Memoria delle decisioni utente storiche (es. "A1 strict",
    "stazione_collegata FIO=Certosa", "9XXXX numerazione vuoti",
    cap-per-regola, varianti per giornata, ecc.)
  - Conoscenza di normativa PdC, modello dati, schema SQL nativo
- **Mai delega**: architettura, scope, piano MR, scelta della
  sintesi finale.

### FAUSTO — il coder veloce

- **Identità**: Grok Code (`grok-code-fast-1` via xAI API)
- **MCP server**: `~/.claude/mcp-servers/grok/` (user-level)
- **Tool namespace**: `mcp__grok__*`
  (`code_review`, `ask`, `brainstorm`, `chat`, `run_code`, ecc.)
- **Variabili**: `XAI_API_KEY` in `~/.zshrc` + `~/.claude/settings.json`
- **Forte di**:
  - Velocità di risposta (è "fast" by design)
  - Code review indipendenti post-refactor (occhi freschi)
  - Stesura di funzioni con specifica precisa
  - Cleanup di pattern ripetitivi (rename, typing, fix mypy)
  - Second opinion su scelte di design
- **Costo**: token xAI per chiamata; review tipica = qualche centesimo.

### AMILCARE — il coder profondo

- **Identità**: DeepSeek V4 Pro (`deepseek/deepseek-v4-pro` via
  OpenRouter)
- **MCP server**: `~/Developer/deepseek-claude-MCP-server/`
- **Tool namespace**: `mcp__amilcare__*` (al momento espone
  `reason`, ma è un proxy generico: il prompt viene mandato così
  com'è al modello e la risposta torna a NINO)
- **Variabili**: `OPENROUTER_API_KEY` + `DEEPSEEK_MODEL` +
  `OPENROUTER_BASE_URL` nel blocco `amilcare` di
  `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Modello scelto**: **V4 Pro**, non V4 Flash. Decisione utente
  2026-05-08: "usa il migliore". Benchmark di riferimento:
  SWE-bench Verified 80.6%, LiveCodeBench 93.5%, Codeforces 3206,
  Terminal-Bench 2.0 67.9%. Architettura MoE 1.6T parametri totali
  / 49B attivati, context window 1M token.
- **Forte di**:
  - Ragionamento esteso su problemi complessi
  - Context da 1M token: digerisce MR multi-file interi
  - Edge case e blind spot che FAUSTO può perdere
  - Refactor architetturali con valutazione di trade-off
- **Costo**: $0.435/M input + $0.87/M output. Su task brevi
  comparabile a FAUSTO; su context grandi pesa di più — monitorare
  bolletta OpenRouter.

### SEVERO — il critico permanente

- **Identità**: subagent Claude Code con system prompt critico.
  Non è un modello esterno autonomo: è una **istanza di Claude
  Code** definita in `.claude/agents/severo.md`, ma il giudizio
  sostanziale lo delega ad **AMILCARE** via `mcp__amilcare__reason`
  (no bias di auto-compiacenza verso codice scritto da NINO).
- **Invocazione**: tramite `Agent` tool con `subagent_type=severo`,
  oppure trigger linguistici utente (vedi §10).
- **Ruolo**: criticare i commit. Mai scrivere codice. Mai committare.
  Mai modificare `TN-UPDATE.md` o i file del MR criticato.
- **Forte di**:
  - Indipendenza dal codice appena scritto da NINO
  - Indipendenza dalle decisioni dell'utente (non è "dalla sua parte")
  - Format canonico in `docs/critiche/` (file:riga, severità, fix
    proposto, costo del fix, voto)
  - Aderenza ai documenti operativi (CLAUDE.md §7 NIENTE PIGRIZIA,
    METODO 7 regole)
- **Quando invocarlo**:
  - **Obbligatorio**: a fine Sprint, dopo MR significativo (multi-file,
    cambio architetturale, refactor di dominio)
  - **On-demand**: quando l'utente lo chiede
  - **Non invocare**: micro-commit (typo, doc, rename triviale,
    una riga di config)
- **Costo**: il subagent stesso è gratuito (è Claude); il giudizio
  delegato ad AMILCARE costa quanto una review AMILCARE classica.

---

## 2. Quando usare cosa — matrice di decisione

| Tipo di task | NINO | FAUSTO | AMILCARE | SEVERO |
|---|---|---|---|---|
| Architettura, scope, piano MR | ✅ unico decisore | ❌ | ❌ | ❌ |
| Decisione utente / dominio (normativa, modello dati) | ✅ unico decisore | ❌ | ❌ | ❌ |
| Codice routine (CRUD, schema Pydantic, migration semplice) | ✅ esegue | ☑️ second opinion se serve | ❌ overkill | ❌ overkill |
| Refactor cross-file di logica di dominio | ✅ esegue + sintesi | ☑️ review post | ✅ ragionamento iniziale | ✅ critica post-commit |
| Algoritmo non-banale (builder, validazione PdC) | ✅ esegue | ☑️ stesura blocchi circoscritti | ✅ review esteso + edge case | ✅ critica post-commit |
| Code review post-MR (file principale) | ✅ orchestra | ✅ review veloce | ✅ review profondo se MR grosso | ☑️ se MR significativo |
| Bug oscuro che non si sblocca | ✅ esegue fix | ☑️ second pair eyes | ✅ ragionamento alternativo | ❌ inutile prima del fix |
| Cleanup pattern uniforme su N file | ✅ orchestra | ✅ esegue tutto | ❌ overkill | ❌ micro-commit |
| Test edge case su codice stabilizzato | ✅ orchestra | ✅ stesura | ☑️ se vincoli sottili | ❌ |
| Stesura funzione X con firma + vincoli noti | ☑️ supervisiona | ✅ scrive | ❌ overkill | ❌ |
| Verifica indipendente di un calcolo / formula | ✅ pone domanda | ✅ controprova | ✅ controprova | ❌ controprova non è critica |
| Chiusura Sprint (giudizio complessivo sul lavoro fatto) | ☑️ orchestra | ❌ | ❌ | ✅ obbligatorio |
| Critica di un MR significativo già committato | ☑️ orchestra | ❌ | ❌ via SEVERO | ✅ obbligatorio |

Legenda: ✅ usalo, ☑️ valutalo (opzionale), ❌ non serve / spreco.

**Differenza review vs critica**:

- **Review** (FAUSTO/AMILCARE) = giudizio di qualità tecnica
  *prima del commit*, per migliorare il codice prima di chiuderlo.
- **Critica** (SEVERO) = giudizio post-commit, *retrospettivo*,
  che valuta il lavoro come un tutto contro le regole del progetto
  (NIENTE PIGRIZIA, METODO 7 regole, debito tecnico segnalato in
  modo coerente). Non sostituisce le review, le segue.

---

## 3. Workflow standard — "codice con ausilio"

Sequenza canonica per un task di sviluppo non triviale:

1. **NINO comprende il task** — legge TN-UPDATE recenti, documenti
   di dominio rilevanti, guarda lo stato del repo.
2. **NINO progetta la soluzione** — file da toccare, ordine, vincoli,
   test plan. Questa parte non si delega mai.
3. **Decisione di pre-stesura**: NINO valuta se aprire con un ausilio.
   - Task circoscritto + spec chiara → **FAUSTO scrive il blocco**,
     NINO integra.
   - Task complesso che NINO scriverà → **AMILCARE ragiona prima**
     (es. "qui ci sono 3 approcci A/B/C, quale si adatta meglio a
     vincolo Y?"), NINO sceglie e scrive.
4. **NINO scrive** (o supervisiona la scrittura altrui).
5. **Build + test locali** — regola 5 METODO. Niente commit prima.
6. **Decisione di post-stesura**: NINO chiama un ausilio per review.
   - Review veloce su file singolo → **FAUSTO**.
   - Review profondo su MR multi-file / cambio architetturale
     → **AMILCARE** (sfrutta il context 1M).
7. **NINO filtra i finding** — applica solo quelli che comprende e
   accetta. False positive vanno annotati nell'entry TN-UPDATE.
8. **Entry TN-UPDATE + commit + push** (regola 2 CLAUDE.md).
9. **(Solo MR significativo o fine Sprint) — SEVERO critica**:
   NINO invoca SEVERO via `Agent` tool con `subagent_type=severo`.
   SEVERO legge il diff, delega ad AMILCARE il giudizio sostanziale,
   scrive critica in `docs/critiche/SPRINT-X.Y-MR-Z-titolo.md`,
   aggiorna `docs/critiche/README.md`. **NINO + utente** decidono
   se accettare/rimandare/ignorare i finding. Eventuali fix
   diventano nuovi MR (mai correzioni in-place del MR criticato).

Per task triviali (rename, typo, fix banale di un'ora) è ammesso
saltare 3, 6 e 9. **Mai** saltarli per task non banali.

---

## 4. Come briefare un ausilio — vale per entrambi

Né FAUSTO né AMILCARE vedono la sessione di NINO. Il brief deve
essere **autosufficiente**:

- **File e righe specifiche** (non descrizioni vaghe)
- **Decisioni utente storiche rilevanti** (es. "A1 strict del refactor
  bug 5", "varianti per giornata MR 7.7.5", "FIO=Certosa MR2")
- **Output atteso** (review, fix, test, suggerimento di design,
  controprova di un numero)
- **Vincoli**: stack (Python 3.12, FastAPI async, SQLAlchemy 2.x;
  React 18 + TanStack Query; Postgres 16); naming (italiano per
  dominio, inglese per struttura); regole METODO; privacy.

**Domanda secca, non aperta**. ❌ "che ne pensi?" → ✅ "review file X
per regressioni dopo refactor Y, focalizzati su edge case Z".

---

## 5. Verifica prima di applicare

L'output di un ausilio = una PR review esterna. **Mai accettare
patch alla cieca**:

- Filtra falsi positivi (FAUSTO e AMILCARE possono dire cose sbagliate
  perché non vedono il contesto pieno)
- Build + test locali prima del commit (regola 5 METODO)
- Solo fix che NINO comprende e accetta
- Se due ausili disagree, vince la sintesi di NINO (non la "media")

---

## 6. Tracciabilità in TN-UPDATE

Ogni intervento di FAUSTO o AMILCARE va **citato esplicitamente**
nell'entry, con il finding che hanno trovato e cosa è stato fatto:

```
### Review Fausto — code_review su catena.py
- F1 HIGH (riga 412): off-by-one nel loop di chiusura giornata
  → applicato fix.
- F3 LOW (riga 78): naming variabile — false positive, era una
  scelta voluta del refactor 7.7.5.

### Ragionamento Amilcare — reason su trade-off A/B/C
- Proposto pattern A (state machine esplicita).
- Adottato pattern B perché stack qui usa pydantic discriminated
  union (vincolo non noto ad Amilcare).
```

Niente intervento "fantasma": se hanno detto qualcosa, deve
essere ricostruibile da chi legge TN-UPDATE in futuro.

---

## 7. Costi — monitoraggio

| Ausilio | Costo tipico per chiamata | Quando preoccuparsi |
|---|---|---|
| FAUSTO (`grok-code-fast-1`) | qualche centesimo | Loop di review massivi senza ragione, review preventivi su file invariati |
| AMILCARE (`deepseek-v4-pro`) | 1-3 centesimi su review medie; cresce con context grande (1M tok = ~$0.43 input + output) | Stessa cosa di FAUSTO, **più**: invio di interi MR multi-file ripetuto, "dialoghi" lunghi senza necessità |

In dubbio: chiedi all'utente prima di chiamare l'ausilio. Le bollette
si vedono lato xAI (FAUSTO) e OpenRouter (AMILCARE).

---

## 8. Privacy — cosa NON mandare

Vale per **entrambi gli ausili**:

- Chiavi API, password, credenziali DB
- Dati personali reali (matricole macchinisti, nomi PdC, anagrafica
  reale anche di test)
- Contenuto integrale di `CLAUDE.md`, `TN-UPDATE.md`, o memorie
  operative — se non strettamente necessari per il task

**Nota specifica AMILCARE**: il traffico passa via **OpenRouter**,
che è un router-broker tra provider. Per default usa DeepSeek
nativo, ma il routing può cambiare nel tempo. Per COLAZIONE
(greenfield, no segreti dichiarati) non è un blocker, ma vale come
awareness permanente. Se un giorno il progetto avesse contenuti
sensibili, riconsiderare.

---

## 9. Regola guida

> **FAUSTO** e **AMILCARE** aiutano a **eseguire** o **verificare**,
> non a **decidere**.
>
> **SEVERO** aiuta a **criticare**, non a eseguire né a decidere.
> SEVERO scrive critiche, non codice; non committa, non aggiorna
> TN-UPDATE; le sue critiche sono input per NINO + utente, non
> direttive da applicare alla cieca.
>
> La sintesi architetturale, il piano dei MR, le scelte di scope
> e le decisioni di dominio restano di **NINO**. Anche dopo una
> critica di SEVERO, è NINO + utente a decidere quali finding
> accettare e quali rimandare.
>
> Se NINO si accorge di aver delegato il pensare — non l'esecuzione,
> proprio il pensare — si ferma e riprende in mano. È sintomo di
> stanchezza o di scope poco chiaro, non un legittimo risparmio di
> tempo. **Stesso vale per SEVERO**: se NINO accetta acriticamente
> i finding di SEVERO ("AMILCARE ha detto X, applico X"), ha
> abdicato. Filtra sempre.

---

## 10. Trigger linguistici dell'utente

Quando l'utente dice frasi tipo:

- *"chiedi a Fausto"*, *"fatti aiutare da Fausto"*, *"delega Fausto"*
  → NINO usa `mcp__grok__*`
- *"chiedi ad Amilcare"*, *"fatti aiutare da Amilcare"*,
  *"chiedi a deepseek"*
  → NINO usa `mcp__amilcare__*`
- *"chiedi a SEVERO"*, *"fai criticare"*, *"review severa"*,
  *"che ne dice SEVERO?"*, *"giudica l'ultimo commit"*
  → NINO invoca il subagent `severo` via `Agent` tool con
  `subagent_type=severo`. NON chiama AMILCARE direttamente:
  è SEVERO che internamente delega.
- *"second opinion"* / *"controprova"* senza specifica → NINO sceglie
  l'ausilio in base al task (vedi matrice §2)
- *"review"* di un MR / file → NINO sceglie l'ausilio in base alla
  taglia (file singolo → FAUSTO; MR multi-file → AMILCARE).
  Se l'utente specifica *"review severa"* o *"critica"* → SEVERO,
  non FAUSTO/AMILCARE.

Quando l'utente non specifica e il task lo richiede, NINO può
proporre: *"questa cosa la faccio io oppure la passo a FAUSTO/AMILCARE,
preferisci?"*. Non chiedere conferma su ogni minuzia, però — vale
solo per chiamate non triviali.

**Differenza importante review vs critica**: l'utente che dice
"review" intende di solito *review tecnica* (FAUSTO/AMILCARE,
pre-commit). L'utente che dice *critica*, *giudica*, *severa* o
nomina *SEVERO* intende il critico permanente (post-commit,
retrospettivo). Se ambiguo, chiedere.

---

## Riferimenti

- `CLAUDE.md` — regole operative del progetto (sezione 9 ora rimanda
  qui)
- `docs/METODO-DI-LAVORO.md` — framework comportamentale (regola 5:
  build + test prima del commit, vale anche per patch da ausili)
- `TN-UPDATE.md` — diario operativo (entry 241 e successive citano
  esplicitamente FAUSTO/AMILCARE/SEVERO quando coinvolti)
- `~/Library/Application Support/Claude/claude_desktop_config.json`
  — config MCP che registra `grok` (FAUSTO) e `amilcare` (AMILCARE)
- `.claude/agents/severo.md` — definizione del subagent SEVERO
  (system prompt critico, format canonico critica)
- `docs/critiche/` — output canonico delle critiche di SEVERO
  (un file per critica + `README.md` indice)
