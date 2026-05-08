# Critica SEVERO — MR-A3 vincolo soft tier-based in risolvi_corsa (12399ef)

> **Data**: 2026-05-08
> **Commit criticato**: `12399ef` (MR-A3 Sprint 8.1)
> **TN-UPDATE entry**: 244
> **Motore sostanziale**: AMILCARE DeepSeek V4 Pro via `mcp__amilcare__reason`
> **Orchestratore**: SEVERO (subagent custom non ancora registrato come `subagent_type` di sistema → workflow eseguito manualmente da NINO seguendo `.claude/agents/severo.md`)
> **Voto SEVERO**: **4/10**

---

## TL;DR — SEVERO

> MR-A3 introduce un fallback Tier 1 senza averne validato l'effetto né
> misurato l'impatto trasversale. Il claim "sblocca il sintomo R11" è
> infondato, la modalità esplorativa elabora l'intero parco corse
> (~6500) senza filtro di perimetro, e il tie-break al Tier 1 si basa
> su metadati ignorati. Il voto di NINO (6/10 in fallback) è
> auto-compiacente; il MR non supererebbe un code review rigoroso.

---

## 4 Finding HIGH/CRITICAL (verbatim AMILCARE + filtro NINO)

### HIGH-1: Nessuna validazione end-to-end, claim "sblocca sintomo" falso

**Perché HIGH** (AMILCARE):

> La entry 244 dichiara di aver sbloccato il blocco "linea=R11 sede FIO
> → 0 giri", ma l'unico test E2E è rimandato a MR-A7. Senza un test
> integrato su fixture reale (o mini-fixture) non sappiamo se il Tier 1
> genera effettivamente giri concatenati per le altre linee, né se il
> risultato globale del programma è corretto. Un MR che si auto-accredita
> una soluzione senza prova empirica viola R5 (verifica prima del commit)
> e mina la fiducia nell'intero strangler.

**Fix concreto** (AMILCARE):

> Aggiungere almeno un test di accettazione con un dataset ridotto
> (poche corse R11+R8, programmazione esplorativa) che verifichi la
> generazione di giri >0 e l'assenza di corse orfane, prima di mergiare.

**Filtro NINO**: ✅ **ACCETTATO HIGH**. Combacia col mio finding S1
fallback. La gravità è confermata: il MR si autoaccredita "sblocca
sintomo R11" senza dimostrarlo. Costo del fix mini-fixture: 2-4h, sotto
la soglia <2h estesa di CLAUDE.md §7. Pigrizia mascherata da "scope
MR-A7". MR-A7 è prerequisito per dichiarare A3 "chiuso" davvero.

---

### HIGH-2: `corse_perimetro = list(corse)` senza filtro — rischio performance e semantico

**Perché HIGH** (AMILCARE):

> Nel builder esplorativo, `genera_giri` carica *tutte* le ~6500 corse
> invece di applicare il filtro di perimetro legacy
> (`_corsa_in_perimetro`). Ciò significa che la modalità esplorativa
> allarga silenziosamente il dominio di programmazione a corse che non
> appartengono alla sede, consumando risorse e potenzialmente
> producendo assegnazioni per materiale fuori perimetro. Non c'è alcun
> benchmark né analisi R2 (numeri non ipotesi); il rischio di
> regressione prestazionale è concreto e il comportamento potrebbe
> generare giri spuri. La delega dichiarata "ai vincoli inviolabili"
> non giustifica la rimozione del filtro.

**Fix concreto** (AMILCARE):

> Reintrodurre un filtro di perimetro anche in modalità esplorativa,
> magari meno stringente ma documentato (es. corse con almeno una
> stazione nel perimetro), accompagnato da un test di performance
> comparativa.

**Filtro NINO**: ✅ **ACCETTATO HIGH** (AMILCARE l'ha alzato di livello
rispetto al mio fallback MED — giustamente). NINO sotto-stimato. La
mia analisi assumeva che il secondo filtro implicito
`risolutore_dominante(c, regole_della_sede)` ritorni `None` per corse
fuori sede e quindi escluda. AMILCARE ha ragione nel sottolineare:
1. Il loop sulle 6500 corse + sort O(R log R) per ogni corsa avviene
   COMUNQUE → costo computazionale reale anche se l'output finale
   esclude le corse fuori sede.
2. Più subdolo: una corsa fuori sede potrebbe matchare al Tier 1 una
   regola della sede (filtri ignorati) e generare un assegnamento
   "spurio". Va a finire in `corse_per_materiale` della sede sbagliata.
   Il vincolo di sede è perso.

Fix urgente, MR-A3-bis pre-A7.

---

### HIGH-3: Tie-break al Tier 1 basato su `len(filtri_json)` (specificità) mentre i filtri sono ignorati

**Perché HIGH** (AMILCARE):

> La funzione `_trova_regola_dominante_esplorativa` ordina le regole
> per `(-priorita, -len(filtri_json), id)`, ma al Tier 1 i filtri
> vengono volontariamente ignorati. Quindi il tie-break premia la
> regola con più filtri, anche se quei filtri non verranno applicati,
> creando una selezione che non riflette né la pertinenza effettiva
> né la qualità del matching. In pratica, si introduce una dipendenza
> da un metadato irrilevante, che può dare risultati non deterministici
> o controintuitivi in caso di parità di priorità, e mina la
> riproducibilità.

**Fix concreto** (AMILCARE):

> Rimuovere `len(filtri_json)` dalla chiave di ordinamento al Tier 1
> e sostituirlo con, ad esempio, il numero di composizioni ammesse o
> la data dell'ultima modifica della regola, oppure usare un
> ordinamento stabile esplicito (es. id cronologico).

**Filtro NINO**: ✅ **ACCETTATO HIGH**. Concorda col mio finding S5
fallback. Confermo: una regola con 5 filtri specifici batte una regola
generica con 1 filtro al Tier 1, ma al Tier 1 nessuno dei filtri è
valutato → la regola "stretta" (pensata per casi marginali) vince come
dominante anche per casi fuori scope. Fix preferenza NINO: in modo Tier 1
usare solo `(-r.priorita, r.id)`. Costo: 30min + 1-2 test edge case.

---

### CRITICAL-1: `TIER_1_PENALTY=50` contraddice la matrice dichiarata e non è spiegabile

**Perché CRITICAL** (AMILCARE):

> Il commento spiega il valore 50 derivandolo da una tabella che
> assegna pesi 20/40/70 ai vari livelli, ma 50 non è nessuno di
> questi. Il numero magico introdotto senza giustificazione analitica
> crea un costo arbitrario che si propaga nel calcolo del ranking
> complessivo. Un domani chi rivedrà le penalità dovrà indovinare
> perché 50; la mancanza di tracciabilità rispetto ai requisiti
> (vincolo soft tier-based) rende la manutenzione fragile.

**Fix concreto** (AMILCARE):

> Allineare la penalty a uno dei valori della matrice (es.
> `TIER_1_PENALTY=20` per minimo impatto) oppure documentare
> esattamente la formula decisionale che ha prodotto 50 (es. media
> pesata, vincolo temporaneo).

**Filtro NINO**: ✅ **ACCETTATO** (AMILCARE l'ha classificato CRITICAL,
io fallback MED — AMILCARE più severo). Concordo con la severità: è il
caso più netto di pigrizia mascherata da commento giustificativo. Il
commento "deriva da matrice tier" è una bugia: 50 ∉ {20, 40, 70}. Fix
NINO preferisce: `TIER_1_PENALTY = 20` (allineato peso LINEA tier 1
della matrice citata) + commento veritiero. Costo: 30min.

---

## 2 Finding MEDIUM (verbatim AMILCARE + filtro NINO)

### MEDIUM-1: Asimmetria delle firme tra `_trova_regola_dominante_esplorativa` e `risolvi_corsa_esplorativo`

**Perché MEDIUM** (AMILCARE):

> Il builder chiama `_trova_regola_dominante_esplorativa(prima_corsa,
> regole)` senza il parametro `data`, e senza passare
> `vincoli_inviolabili`. Il commento "delegato a composizione.py" non è
> verificato nel codice: la funzione non applica alcun filtro, quindi
> può restituire una regola che successivamente fallirà l'accoppiamento
> o genererà eccezioni altrove. Il disallineamento produce un contratto
> fragile, anche se al momento mascherato da catch esterni. Va
> armonizzato.

**Filtro NINO**: ✅ **ACCETTATO MED**. AMILCARE ha unificato i miei
finding S7 (naming `prima_corsa` vs `corsa`) e S2 (pre-pool senza
vincoli) in un unico MED — interpretazione più rigorosa della mia. Il
"disallineamento contrattuale" è il punto giusto: una funzione che
"delega" ma non documenta la pre-condizione che il chiamante DEVE poi
filtrare = bug latente nel design.

---

### MEDIUM-2: "Strangler 100%" non verificato sui consumer di `AssegnazioneRisolta`

**Perché MEDIUM** (AMILCARE):

> L'aggiunta dei campi `tier_applicato` e `penalty` modifica la struct
> restituita ai moduli a valle (programma, ranking). Senza grep sui
> consumer non si può garantire che il legacy sia intatto
> "byte-per-byte"; eventuali confronti di uguaglianza o serializzazioni
> potrebbero rompersi silenziosamente. Una rapida analisi statica (es.
> `rg "AssegnazioneRisolta"` escludendo i test) rivelerebbe i punti di
> impatto.

**Filtro NINO**: ✅ **ACCETTATO MED**. Concorda col mio finding S8
fallback. Fix: `rg AssegnazioneRisolta backend/src/` per enumerare
consumer + verifica per ognuno (Pydantic? JSON dump? entità DB?).
Costo: 1h.

---

## Cosa SEVERO non ha rilevato (ma NINO segnala dal fallback)

AMILCARE non ha esplicitamente toccato questi punti. NINO li mantiene
come MED dal fallback iniziale, in attesa di conferma in revisione
futura:

### MED-NINO-1: Pre-pool `_trova_regola_dominante_esplorativa` senza vincoli inviolabili

(Distinto da MEDIUM-1 di AMILCARE che era sull'asimmetria firme; qui
parlo dello spreco computazionale.)

In pre-processing pool, una corsa viene assegnata a un materiale
basato solo sulla priorità → entra in `corse_per_materiale[ETR421]`
→ catene/giri costruiti → al final pass `composizione.assegna_materiali`
scopre l'incompatibilità → corsa orfana. Lavoro buttato + diagnostica
ingannevole (catene "buone" che producono residue). Severità: MED.
Fix: filtrare vincoli inviolabili anche nel pre-pool (1-2h).

### MED-NINO-2: `is_composizione_manuale=True` al Tier 1: regola fuori scope vince

Il check legacy `if not top.is_composizione_manuale` salta validazione
accoppiamento ANCHE al Tier 1. Conseguenza: una regola manuale con
filtri specifici (pensata per scope mirato) può vincere come dominante
per corse out-of-scope al Tier 1 → composizione applicata a corse non
target + bypass accoppiamento. Severità: MED. Fix: al Tier 1 escludere
regole con `is_composizione_manuale=True` (30min + 1 test).

### LOW-NINO-1: Filtro `all()` su composizione doppia poco autodocumentato

`all(corsa_ammessa_per_materiale(...) for item in r.composizione_json)`
scarta intera regola se UN materiale è incompatibile (no fallback
parziale). Concettualmente corretto (composizione doppia = unità) ma
nessun commento + nessun test edge case. Severità: LOW. Fix: 2 righe
di commento + 1 test (30min).

---

## Cosa NON è stato fatto e si poteva fare

1. **Validazione E2E con fixture mini** (HIGH-1): scrivibile in 2-4h,
   sotto la soglia di chiusura.
2. **Benchmark performance rigido vs esplorativo** (HIGH-2): nessuna
   misura R2 in entry 244.
3. **Grep sui consumer di `AssegnazioneRisolta`** (MEDIUM-2): 5 minuti.
4. **Documentazione invariant del modulo esplorativo**: pre-condizioni
   / post-condizioni / invariant del Tier 1 esplicite.
5. **Allineamento `TIER_1_PENALTY` alla matrice** (CRITICAL-1): 30min.

---

## Voto finale: **4/10**

Motivazione AMILCARE:

> Il MR risolve un problema reale con un'idea promettente, ma lo fa
> senza verifica empirica, con un'espansione ingiustificata del
> perimetro e scelte arbitrarie non tracciate. La qualità del codice è
> sufficiente per un prototipo, ma la pretesa di produzione ("sblocca
> sintomo") è ingannevole. Il voto di 6/10 [fallback NINO] è troppo
> generoso; per come è presentato, non si può accettare senza fix
> almeno per HIGH-1, 2, 3.

**NINO concorda col downgrade**: il mio voto fallback 6/10 era
auto-compiacente (AMILCARE l'ha colto correttamente). 4/10 è la lettura
giusta una volta misurato l'impatto del CRITICAL-1 (penalty arbitraria),
del HIGH-2 (perimetro non solo performance ma anche semantico), e del
fatto che il claim principale del MR non è dimostrato (HIGH-1).

Scala SEVERO:
- 9-10: lavoro da senior, finding solo cosmetici
- 7-8: solido, qualche miglioramento sostanziale possibile
- 5-6: funziona ma con debito o blind spot non secondari
- **3-4**: problemi strutturali, da rivedere ← qui
- 1-2: bocciato, riaprire prima di proseguire

---

## Azioni post-critica

1. **MR-A3-bis** (M effort, da fare PRIMA di A7) — priorità simile
   a MR-A4-bis ma indipendente:
   - **HIGH-1 fix**: test E2E con fixture mini (programma minimal,
     1 sede FIO, regola unica `linea=R11`, ~10 corse miste) →
     `genera_giri` rigido produce 0 giri, esplorativo produce ≥1.
     Costo: 2-4h.
   - **HIGH-2 fix**: reintrodurre filtro perimetro anche in
     esplorativo (versione "morbida": almeno una stazione nel
     perimetro sede). Costo: 1-2h.
   - **HIGH-3 fix**: rimuovere `len(filtri_json)` dalla chiave Tier 1.
     Costo: 30min + 2 test.
   - **CRITICAL-1 fix**: `TIER_1_PENALTY=20` (allineato matrice) +
     commento veritiero. Costo: 30min.
   - **MEDIUM-1 fix**: armonizzare firma `_trova_regola_dominante_esplorativa`
     (`corsa` invece di `prima_corsa`, accettare `data` per coerenza).
     Costo: 15min.
   - **MEDIUM-2 fix**: `rg AssegnazioneRisolta backend/src/` +
     verifica consumer. Costo: 1h.
   - **MED-NINO-1 fix** (pre-pool vincoli): 1-2h.
   - **MED-NINO-2 fix** (manual al Tier 1): 30min + 1 test.

   **Total stimato MR-A3-bis**: ~7-12h.

2. **MR-A3 NON modificato in-place** (regola 9 CLAUDE.md aggiornata
   entry 245: "Eventuali fix → nuovi MR, mai correzioni in-place del
   MR criticato").

3. **Priorità MR-A3-bis vs MR-A4-bis**: sono indipendenti, possono
   essere fatti in parallelo o in serie. Decisione utente.

---

## Tracciabilità

- **Commit criticato**: `12399efeaf2d7c7da1ddbf14ffcb104c1112e659`
- **Branch**: `master`
- **Brief AMILCARE V4 Pro**: contesto MR-A3 + diff sintesi (~3KB) + 10
  zone grigie pre-identificate da NINO + format request → output ~700
  parole strutturato HIGH×3 + CRITICAL×1 + MEDIUM×2.
- **Filtro NINO**: 4 HIGH/CRITICAL confermati integralmente, 2 MEDIUM
  confermati integralmente; AMILCARE ha alzato 2 finding di severità
  rispetto al fallback NINO (perimetro: MED→HIGH, penalty: MED→CRITICAL),
  giustamente.
- **Finding aggiunti da NINO** (non rilevati da AMILCARE): MED pre-pool
  vincoli, MED manual al Tier 1, LOW filtro `all()` composizione doppia.

---

## Note sul workflow SEVERO

Questa è la **seconda critica** prodotta da SEVERO (la prima è MR-A4,
voto 2/10). Differenze metodologiche rispetto al primo tentativo
(fallback NINO, AMILCARE timeout):

1. **AMILCARE V4 Pro operativo** via DeepSeek API diretta (setup
   risolto durante MR-A4 dall'utente, vedi entry 246).
2. **Brief più snello** (~3KB invece di ~30KB) — il primo tentativo
   è andato in timeout MCP `-32001` con brief gigante. Lezione:
   condensare diff sintesi + zone grigie pre-identificate, non
   incollare diff verbatim.
3. **Pattern verbatim AMILCARE + filtro NINO** allineato al file
   MR-A4 — output ricostruibile dal lettore (chi ha detto cosa,
   chi ha confermato/aggiunto/declassato).

Il fallback NINO che ho scritto al primo tentativo è stato sostituito
da questa versione (AMILCARE-driven).
