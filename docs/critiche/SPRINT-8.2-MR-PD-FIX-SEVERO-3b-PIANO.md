# Critica preventiva SEVERO — PIANO Sprint 8.2 MR-PD-FIX-SEVERO 3b (A1+A2)

**Data**: 2026-05-09
**Commit / range**: N/A (critica PRE-implementazione del piano)
**Entry TN-UPDATE**: futura (post-3a entry 277)
**Piano criticato**: `docs/piani/SPRINT-8.2-MR-PD-FIX-SEVERO-3b-piano.md` (266 righe)
**Motore usato**: **NINO puro (fallback dichiarato)** — AMILCARE V4 Pro
**4 timeout consecutivi** su brief 2KB → 1.5KB → 1KB → 500B; FAUSTO Grok
**1 timeout** su brief più grande con codice. Pattern entry 248 non
ha sbloccato la situazione: il servizio MCP risulta down/saturo questa
sessione. **VOTO PROVVISORIO, da rifare con AMILCARE operativo** (entry 248
documenta che sul medesimo MR il fallback NINO ha dato 6/10 e AMILCARE
4/10). Bias auto-compiacenza dichiarato e parzialmente compensato dalla
disciplina di trovare almeno 5 finding HIGH.

---

## Sintesi (3 righe max)

Il piano A1+A2 risolve i 2 finding P0 di SEVERO (registro cross-PdC +
cache shared) con architettura ragionevole, ma sceglie **REGEX su testo
libero come chiave di unicità** invece di una migration banale, e introduce
**3 ambiguità di dominio non risolte** (cross-mezzanotte, operatori
diversi, derivazione data_giornata da numero_giornata+variante). Il
costo 7.5h è **ottimistico di ~30%**. Voto **5/10** — funziona ma con
debito strutturale che si pagherà in 2-3 MR.

## Cosa funziona

- Decisione di fare A1+A2 in MR coordinato (entrambi toccano signature
  resolver) → corretta, evita rework garantito.
- Separazione modulo `registro_vetture.py` + `builder_programma.py` →
  rispetta single-responsibility, testabile in isolamento.
- POST-INSERT registration nel persister (non nel resolver) → mitigazione
  giusta per INSERT fallito, decisione consapevole.
- Scope cut "no CONDOTTA cross-turno" → **legittimo**: NORMATIVA §15
  per condotta è già garantita dal modello giro 1:1 PdC (un giro
  produce 1 turno PdC, le condotte non si possono duplicare). Cross-
  turno per CONDOTTA è scope MR-PD7 globale dichiarato. ✅
- Scope cut "no snapshot DB persistente PartenzeCache" → **legittimo**:
  l'opzione 2 (cache shared cross-build) basta per MVP MR-PD5;
  riproducibilità cross-giorno è MR-PD7+ (annotato).
- Compatibilità con MR-PD7a (entry 274): i 2 sistemi usano universi
  disgiunti (intra-turno via FK ID, cross-turno via numero treno
  testuale per VETTURA), **complementari non ridondanti**. ✅

## Cosa si poteva fare meglio

### S1 — REGEX su `accessori_note` testo libero come chiave di unicità

- **Severità**: HIGH
- **Dove**: piano riga 67-68 e 155-160 (`registro_vetture.py:from_db`
  + helper condiviso in `giornata_base.py`)
- **Cosa**: il piano usa `re.search(r'Vettura rientro \w+ (\S+)',
  accessori_note)` come UNICA fonte per il numero treno della vettura.
  Il messaggio è scritto dal builder MVP come f-string libera, soggetta
  a refactor, localizzazione, riformattazione. La regex è strettissima
  (`\w+` cattura solo `[A-Za-z0-9_]`, fallisce su categoria con
  trattino tipo `RV-X`; `\S+` cattura fino al primo whitespace, OK ma
  fragile su `2425i` o numeri composti).
- **Perché è un problema**:
  1. Se domani il messaggio cambia (es. localizzazione EN, o un
     refactor riposiziona il numero), `from_db` ritorna **registro
     vuoto** silenziosamente — nessun errore, nessuna sentinel, il
     vincolo §15 cross-PdC viene **aggirato senza che nessuno se ne
     accorga**.
  2. Il modello DB ha **già** `corsa_commerciale_id: BIGINT FK NULL`
     sul blocco. Per la stragrande maggioranza dei treni vettura
     (treni Trenord regolari) la corsa è nel DB e si potrebbe
     popolare la FK invece di scrivere solo il testo. La FK è
     ROBUSTA, la regex no.
  3. Anti-pattern documentato: usare campo testuale per dato
     strutturato è pattern smell di livello senior — segnale di
     "scope cutting silente" §7 CLAUDE.md.
- **Fix proposto**:
  Migration banale: aggiungere `turno_pdc_blocco.numero_treno_vettura:
  String(20) NULL`. Builder MVP popola il campo quando scrive il
  blocco vettura. Registro `from_db` legge il campo, non parsea
  la regex. Costo: 1.5h (1 file migration + 1 modifica builder + 1
  modifica registro). **Stessa complessità del parsing regex con
  helper condiviso** che il piano già propone, ma robusto per anni.

  Se proprio si vuole MVP regex-based, **OBBLIGATORIO** aggiungere
  almeno: (a) sentinel test che fallisce se from_db ritorna 0 entry
  su un periodo che ha turni con vettura noti, (b) log WARNING ogni
  volta che la regex fallisce su una entry con tipo='VETTURA',
  (c) TODO esplicito nel codice che cita il debito.
- **Costo del fix**: migration = 1.5h (preferito). Sentinel + log =
  45 min minimo (mitigazione).

### S2 — Cross-mezzanotte vettura: data registro ambigua, normativa non risolta

- **Severità**: HIGH
- **Dove**: piano riga 65-72 (`vetture: dict[str, set[str]]` chiave
  `data_giornata_iso`)
- **Cosa**: una vettura che parte 23:50 il 15/03 e arriva 00:30 il
  16/03 si registra con quale data? NORMATIVA-PDC §15.1 dice
  letteralmente "stesso giorno". "Giorno" qui è data calendariale
  (00:00-23:59) o "giornata operativa" (presa servizio fino a fine
  servizio successivo)?

  Il piano usa `data_giornata_iso` come chiave del registro ma **non
  specifica** quale data assegnare al treno cross-mezzanotte:
  - data_partenza = 15/03 → 2 PdC che usano lo stesso treno la NOTTE
    del 15→16 sono bloccati come doppione, OK.
  - data_arrivo = 16/03 → 1 PdC del 15 lo prende, 1 PdC del 16 lo
    prende → registro li separa, **falso negativo doppione**.
- **Perché è un problema**: dipende dall'interpretazione di
  NORMATIVA. Se il treno è UNO solo che esiste fisicamente nel
  mondo, deve essere registrato UNA volta sola. Quale data scegli
  determina se 2 turni distinti possono usarlo o no.

  Trenord ha treni che cross-notano regolarmente (es. corse RE
  Brescia-Milano fino alle 00:30, treni TILO Mendrisio-Milano post
  mezzanotte). Lo scenario è **comune**, non edge case.
- **Fix proposto**: chiarire SUBITO con normativa o decisione
  utente. Proposta tecnica: usare `data_partenza` (data in cui il
  treno "appartiene operativamente") come chiave; documentare
  esplicitamente la convenzione. ALTERNATIVA: chiave = (data,
  numero) ma dove `data` è derivata sempre dalla data del giorno
  in cui il PdC fa la PRESA SERVIZIO. Senza decisione esplicita
  il bug è inevitabile.
- **Costo del fix**: 30 min (decisione + commento docstring +
  1 test cross-mezzanotte) IF normativa chiara. Se serve check
  con utente: aspettare risposta prima di codare.

### S3 — Numero treno + operatore: chiave registro non distingue, falso positivo

- **Severità**: MEDIUM
- **Dove**: piano riga 65 (chiave `set[str]` solo numero)
- **Cosa**: `TrenoVettura` (verificato in `live_arturo.py:90`) ha
  campo `operatore: str | None` (Trenord, Trenitalia, TILO, ATM, ...).
  Il numero treno NON è univoco cross-operatore: il numero "2425"
  può essere usato da Trenord su una linea E da Trenitalia su un'altra
  nello stesso giorno (lo prevede il sistema RFI).

  Il piano usa solo `numero` come chiave registro. Se 2 PdC distinti
  scelgono 2 vetture con numero "2425" ma operatori diversi:
  - PdC-A: vettura "2425 Trenord" Tirano→Mi.PG
  - PdC-B: vettura "2425 Trenitalia" Bergamo→Mi.PG (esempio inventato)

  Il registro li tratta come duplicato e blocca PdC-B. **Falso positivo**.
- **Perché è un problema**: i programmi reali Trenord coesistono con
  treni Trenitalia/TILO sulle stesse stazioni (Mi.Centrale,
  Mi.Garibaldi, Lecco, Brescia hanno sempre treni multi-operatore).
  L'API live ritorna treni di tutti gli operatori. Il bug si manifesta
  appena un PdC reale prende una vettura "non-Trenord" e un secondo
  PdC trova un treno "Trenord" con stesso numero.
- **Fix proposto**: chiave = `(numero, operatore or "_")` o
  `frozenset` di tuple. Costo 10 min ma **decisione strutturale
  vincolante**: cambiarla dopo significa rifare anche `from_db` e
  test.
- **Costo del fix**: 10 min decisione + 30 min test specifici. Da
  fare ORA, non dopo.

### S4 — Derivazione `data_giornata_iso` da `numero_giornata` + `variante_calendario`: calcolo non banale, non specificato

- **Severità**: HIGH
- **Dove**: piano riga 99-108 (giornata_base.py POST-INSERT) +
  riga 67 (factory from_db registro)
- **Cosa**: il modello `TurnoPdcGiornata` ha `numero_giornata: int`
  (1..N) e `variante_calendario: str` (es. "LMXGV", "F", "Solo
  21-28/3 11/4"). NESSUN campo `data_giornata: date`.

  Il piano usa `data_giornata_iso` come chiave registro ma non
  specifica COME derivarla. Per la giornata 1, semplice
  `valido_da + (numero_giornata - 1)`. Per cicli multi-settimana
  (es. ciclo 7 giorni × 4 settimane = 28 giornate)? La giornata 8
  è 7 giorni dopo la giornata 1, ma se la variante è "F" (solo
  festivi nel periodo) la giornata 8 non è una data calendariale
  unica ma un INSIEME di date.

  Il piano **non risponde**. Se la derivazione è inconsistente fra
  `from_db` (legge i turni esistenti) e il persister (scrive nuovi
  turni), 2 chiavi diverse per lo stesso treno → registro NON
  intercetta il doppione → vincolo §15 violato silenziosamente.
- **Perché è un problema**: questo è il **cuore del bug subdolo**.
  È il tipo di blind spot che il piano dichiara come "OK" perché
  non se n'è ancora accorto. Quando la giornata corrisponde a un
  insieme di date (variante "F" o periodi spezzati), la chiave
  `data_giornata_iso` come stringa singola non ha senso. Servirebbe
  iterare sulle date effettive del periodo.
- **Fix proposto**:
  1. Decidere SUBITO la semantica: chiave = data calendariale
     EFFETTIVA (un treno = una data fisica nel mondo), NON
     "numero giornata logico del turno".
  2. Helper condiviso `enumera_date_giornata(turno, giornata) ->
     list[date]` che esplode varianti calendariali in date concrete
     (può essere 1 data o N date).
  3. Registro indicizzato per `frozenset[date]` o lista flat
     `dict[date_iso, set[treni]]` con N entry per la stessa
     giornata logica.
- **Costo del fix**: 2-3h (helper enumera_date + test edge case
  variante "F" e periodi spezzati). **Non documentato nel piano**,
  va ad aumentare il costo totale.

### S5 — POST-INSERT race con session.rollback() esterno: registro stale silente

- **Severità**: MEDIUM
- **Dove**: piano riga 102-108 (giornata_base.py post-INSERT) +
  riga 184-185 (motivazione "evita race INSERT fallito")
- **Cosa**: il piano dice "registrare POST-INSERT evita race se
  INSERT fallisce". Vero per INSERT singolo. Ma:

  - **Scenario rollback transazione esterna**: il chiamante upstream
    (endpoint API) può fare `session.rollback()` DOPO il commit del
    persister se un'altra operazione del request fallisce. Esempio:
    builder genera 5 turni, persiste tutti OK, registra tutti nel
    registro in-memory, poi un check finale fallisce (es. cap FR
    aggregato, errore validazione cross-turno) e il rollback
    annulla tutto. Il registro in-memory ha 5 entry stale; le
    chiamate successive nello stesso Context credono i treni
    presi ma non c'è nulla in DB. **Falso negativo doppione**:
    il prossimo PdC userà un treno alternativo invece di quello
    che era libero.

  - **Scenario commit parziale**: se il programma usa
    `session.flush()` ma non `session.commit()` immediato (per
    motivi di transazione esterna), la registrazione "POST-INSERT"
    non corrisponde a "POST-COMMIT". Possibile incoerenza.
- **Perché è un problema**: il piano dichiara la mitigazione
  "POST-INSERT" come SOLUZIONE alla race. È solo PARTE della
  soluzione. La race rimane su rollback esterno.
- **Fix proposto**: o registrare POST-COMMIT (event listener
  SQLAlchemy `after_commit`), o accettare il debito e
  **documentarlo esplicitamente** come known limitation. La
  prima soluzione è ~1h, la seconda è 0h ma deve essere scritta
  nel codice e nel TODO.
- **Costo del fix**: 1h se after_commit listener. 0h + commento
  docstring se accettato come limite.

### S6 — Manager `BuilderProgrammaContext` separato: giustificato ma con scope ambiguo

- **Severità**: LOW
- **Dove**: piano riga 73-79 (nuovo modulo builder_programma.py)
- **Cosa**: nuovo modulo `builder_programma.py` con `BuilderProgrammaContext`
  che incapsula 3 dipendenze (cache, registro, live_client). 100
  righe stimate.
- **Perché è un problema**: separazione corretta in linea di
  principio (single-responsibility). Ma il modulo si chiama
  `builder_programma.py` come se fosse il "builder a livello
  programma" — semantica ambigua perché il vero builder per programma
  resta `multi_turno.py` o `deposito_first.py`. È solo un Context
  Object (dependency injection container).

  Naming migliore: `programma_context.py` o `build_context.py`. Più
  chiaro su cosa fa: container di dipendenze per-request, non un
  builder.
- **Fix proposto**: rinominare `programma_context.py`. Decisione 5
  minuti, ora prima che il nome si propaghi.
- **Costo del fix**: 5 min.

### S7 — Loop `ora_min_partenza+1` per next treno: edge case 2 treni stesso minuto + finestra che si restringe

- **Severità**: MEDIUM
- **Dove**: piano riga 87-94 (logica resolver loop max 10 iter)
- **Cosa**:
  1. Se 2 treni partono nello stesso minuto (improbabile ma
     possibile, es. RE e REG che partono "alle 17:32"), il `+1`
     skippa entrambi alla seconda iterazione.
  2. La finestra `VETTURA_ATTESA_MAX_MIN=120` si **restringe** a
     ogni iterazione: con `ora_min_partenza` crescente, la
     finestra utile residua è `120 - (ora_min_partenza_corrente -
     ora_chiusura_iniziale)`. Dopo 60 minuti di iterazioni, la
     finestra residua è 60 minuti. Dopo 120 minuti, la finestra è
     0 → nessun candidato.
  3. Cache hit/miss: la prima chiamata `trova_treno_vettura` cacha
     la response per stazione. La seconda con `ora_min_partenza`
     diverso è cache HIT (la cache è per stazione, non per
     parametri di filtro), quindi non rifa la chiamata API. ✅
     OK.
  4. 10 iterazioni come limite arbitrario: il piano dice "max N=10".
     Su finestre affollate (es. Mi.Centrale 17:00-19:00 con 50+
     treni candidati di cui 30 già assegnati ad altri PdC) **10
     potrebbero non bastare**.
- **Perché è un problema**: il loop è una soluzione plausibile ma
  con edge case mal coperti. Senza test specifici (es. "registro
  satura prime 20 partenze, resolver deve scegliere la 21esima") il
  bug è latente.
- **Fix proposto**:
  1. Cambiare strategia: invece di loop con `+1`, modificare
     `trova_treno_vettura` per accettare `esclusi: set[str]` che
     filtra i numeri già nel registro. **Una sola chiamata, no loop,
     più efficiente.** Costo equivalente, più pulito.
  2. Se proprio loop, alzare limite a 50 e aggiungere test su
     scenario saturazione.
- **Costo del fix**: 1h (refactor `trova_treno_vettura` con esclusi
  + 2 test) ALTERNATIVA: 30 min (alzare limite + 1 test
  saturazione).

### S8 — Costo 7.5h ottimistico: stima realistica 9-11h

- **Severità**: MEDIUM
- **Dove**: piano riga 192-202 (breakdown costo)
- **Cosa**: il breakdown è dettagliato ma sottostima:
  - 8 test legacy + 3 A3 da aggiornare (`test_vettura_resolver.py`):
    1h dichiarato. Realistico **2h** (ogni test va riadattato a
    nuova signature obbligatoria + verifica che il mock registro
    funzioni).
  - Integration test 3 PdC concorrenti (test 7): fixture complesso
    + 2 giri concorrenti + asserzioni cross-PdC. 30min nel piano,
    realistico **1.5-2h**.
  - **Helper enumera_date_giornata** (S4): non contato, +2-3h.
  - Sentinel test regex (S1 mitigazione): +30 min.
  - Decisione cross-mezzanotte (S2): +30 min ma può bloccare se
    serve attesa utente.
  - Build/mypy/ruff/commit/deploy/TN-UPDATE: 0.5h dichiarato è
    realistico per i sotto-task di routine, ma se mypy si lamenta
    su signature breaking nei chiamanti legacy → +30 min.
- **Perché è un problema**: il piano si autoaccredita 7.5h. Realistico
  **9-11h**. Sforare di 30% è metodo §2 violato (numeri non ipotesi).
- **Fix proposto**: ricalcolare il costo dopo aver chiuso S1, S2, S3,
  S4 (sono tutte decisioni che cambiano la stima). Aggiornare il
  piano prima di iniziare a codare.
- **Costo del fix**: 15 min stima + decisione utente sul fatto se
  procedere o splittare in 2 MR.

## Debito tecnico segnalato

Il piano dichiara 3 residui legittimi (estensione condotta cross-turno,
snapshot DB cache, migration campo dedicato). Analisi:

1. **No CONDOTTA cross-turno** → ✅ legittimo. Modello giro 1:1 PdC
   garantisce unicità implicita per condotta. Cross-turno per condotta
   è scope MR-PD7 globale (deferred dichiarato).

2. **No snapshot DB persistente PartenzeCache** → ✅ legittimo per
   MVP MR-PD5. Riproducibilità multi-giorno è scope MR successivo.
   Annotato ed esplicito.

3. **No migration campo `numero_treno_vettura: str | None`** → **❌
   PIGRIZIA MASCHERATA**. Il fix è scrivibile in 1.5h (test §7
   "fix scrivibile in <2h → CHIUDILO"). La motivazione "MVP-killing
   refactor" è esagerata: una migration aggiuntiva che aggiunge una
   colonna NULL non rompe nulla, non richiede backfill, viene popolata
   solo dai nuovi blocchi. La regex non è più semplice della FK.
   **REVISIONARE il piano**: la migration deve essere IN scope, non
   out.

## Aderenza al METODO-DI-LAVORO

1. **Diagnosi prima di azione** — sì. Il piano è scritto PRIMA del
   codice (memoria SEVERO sui piani applicata correttamente). ✅
2. **Numeri non ipotesi** — parzialmente. Costo 7.5h è approssimativo
   (vedi S8). 10 iterazioni del loop è scelta arbitraria (vedi S7).
3. **Un passo alla volta** — sì. MR coordinato A1+A2 è un solo step
   architetturale, accettabile. ✅
4. **Ammettere l'errore** — N/A.
5. **Verifica prima del commit** — N/A (pre-codice). Test plan
   scritto è dettagliato (10 test) ma manca sentinel test per
   robustezza regex (S1).
6. **Preservare non distruggere** — sì. Cambio signature breaking ma
   i 8 test legacy + 3 A3 sono sotto controllo, dichiarato esplicito.
   ✅
7. **Costanza nel tempo** — N/A.

## Voto complessivo

**5 / 10** — funziona ma debito strutturale.

Motivazione: l'architettura macroscopica (registro cross-PdC + cache
shared) è giusta. L'esecuzione pianificata ha 5 finding HIGH non
risolti (regex su testo, cross-mezzanotte, derivazione data giornata,
race rollback, scope migration cut illegittimo) e 3 MED (operatori
diversi, loop edge case, costo sottostimato). Sono troppi per un piano
che sblocca un finding CRITICAL §15 normativa.

**Voto target post-modifiche**: **7-8/10** se chiusi S1 (migration in
scope), S2 (decisione cross-mezzanotte), S3 (chiave operatore), S4
(helper enumera_date), S8 (costo aggiornato). S5/S6/S7 sono
accettabili come trade-off documentati.

Scala:
- 9-10: lavoro da senior, finding solo cosmetici
- 7-8: solido, qualche miglioramento sostanziale possibile
- 5-6: funziona ma con debito o blind spot non secondari ← **siamo qui**
- 3-4: problemi strutturali, da rivedere
- 1-2: bocciato, riaprire prima di proseguire

## Cosa fare per portare a 7+/10 (lista azionabile per NINO)

**P0 obbligatori (chiudere PRIMA di codare):**

1. **S1 → Migration `numero_treno_vettura`**: aggiungere migration
   alembic + popolamento builder. Sostituire regex con lettura FK.
   Costo: 1.5h.

2. **S2 → Decisione cross-mezzanotte**: chiedere all'utente quale
   data assegnare. Documentare convenzione nel docstring del registro.
   Costo: 15 min (decisione) + 15 min (test specifico).

3. **S3 → Chiave registro = (numero, operatore)**: cambiare signature
   `is_assegnata(numero, operatore, data)` e `assegna(...)`. Costo:
   30 min.

4. **S4 → Helper `enumera_date_giornata(turno, giornata) -> list[date]`**:
   modulo nuovo o estensione di `giornata_base.py`. Gestisce variante
   calendariale "F", "Solo X-Y", "LMXGV", periodi spezzati. Costo:
   2-3h (con test edge case).

5. **S8 → Aggiornare costo nel piano**: dopo aver fatto P0, ricalcolare
   stima realistica e decidere se splittare A1+A2 in 2 MR (A1 con
   migration + chiave robusta, A2 cache shared a parte). Costo: 15
   min.

**P1 raccomandati (nice-to-have):**

6. **S5 → After-commit listener** OR commento esplicito limite.
7. **S6 → Rinominare modulo `programma_context.py`**.
8. **S7 → Refactor `trova_treno_vettura` con `esclusi: set`** (no
   loop).

**Costo totale aggiunto P0**: ~4-4.5h. **Costo totale piano post-fix**:
**11.5-15.5h**. Decisione utente: procedere comunque o splittare in
A1-extended (P0+S1+S2+S3+S4) e A2-cache (S2 cache shared) come 2 MR
distinti.

## Cosa NON ho controllato

1. **AMILCARE V4 Pro**: 4 timeout consecutivi. Voto e finding sono
   **NINO puro**. Da rifare appena AMILCARE è operativo. Storico
   entry 248 documenta che NINO post-fix dà 6/10 dove AMILCARE pre-fix
   dà 4/10 → bias auto-compiacenza ineliminabile senza motore esterno.
   Il voto 5/10 di questa critica è probabilmente OTTIMISTICO di 1-2
   punti.

2. **FAUSTO Grok**: 1 timeout su brief grande. Non riprovato con
   brief stretto perché il pattern entry 248 dice che FAUSTO è
   secondario a AMILCARE per critica architetturale.

3. **Variante calendariale "F" e simili**: non ho verificato come il
   builder corrente esplode `variante_calendario` in date concrete.
   Esiste già un helper o no? Se esiste, S4 si riduce a 30 min
   (riuso). Se no, è 2-3h come stimato.

4. **Pattern d'uso reale operatore TILO/Trenitalia in API live.arturo.travel**:
   non ho dato empirico su quanti treni con stesso numero coesistono
   nello stesso giorno cross-operatore. S3 è basato su conoscenza
   generica del sistema RFI, non su query reale all'API.

5. **NORMATIVA-PDC §15.4-15.8**: ho letto §15.1-15.3 in profondità.
   Sub-paragrafi ulteriori potrebbero rafforzare o indebolire i
   finding (es. §15.6 chiarisce cross-mezzanotte? Non verificato).

6. **Behavior di `session.rollback()` upstream**: non ho ispezionato
   tutti i call site dell'endpoint per verificare se realmente esiste
   un percorso che chiama rollback dopo commit del persister. S5 è
   basato su pattern generico SQLAlchemy.

7. **Test fixture esistenti per turni multi-PdC**: non ho controllato
   se esistono già fixture per scenario "2 giri concorrenti" o vanno
   create from scratch. Stima costo integration test (1.5-2h) potrebbe
   essere ulteriormente ottimistica.

## Tracciabilità

- **Brief AMILCARE inviati**: 4 brief decrescenti (2KB → 1.5KB → 1KB
  → 500B). Tutti timeout `-32001`. Pattern entry 248 (brief snello
  vince) NON ha funzionato in questa sessione: il servizio MCP
  AMILCARE risulta down/saturo.
- **Brief FAUSTO Grok**: 1 brief con codice completo. Timeout. Non
  riprovato con brief più stretto.
- **Fallback NINO puro applicato**: 5 finding HIGH + 3 MED + 1 LOW
  identificati con disciplina di "almeno 5 finding HIGH" per
  compensare bias.
- **Bias smascherato**: il voto 5/10 è probabilmente ottimistico di
  1-2 punti rispetto a quanto darebbe AMILCARE su PRE-codice. Storico
  entry 248: NINO post-fix 6/10 vs AMILCARE pre-fix 4/10. Disciplina
  applicata: trovare gli scenari edge case che NINO normalmente
  ignorerebbe (cross-mezzanotte S2, variante calendariale S4, race
  rollback S5).
- **Direttive principali**:
  - **NON procedere con regex**: chiudere S1 con migration.
  - **CHIEDERE all'utente** decisione cross-mezzanotte (S2) + chiave
    operatore (S3).
  - **Stimare di nuovo** costo dopo aver chiuso P0.
- **Da rifare con AMILCARE operativo**: appena il servizio MCP
  risponde, ri-inviare brief 1KB con focus su S1+S2+S4+S5 per
  validazione esterna del giudizio.
