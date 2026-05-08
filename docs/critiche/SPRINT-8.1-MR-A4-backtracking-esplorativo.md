# Critica SEVERO — MR-A4 backtracking esplorativo (b3ddc57)

> **Data**: 2026-05-08
> **Commit criticato**: `b3ddc57` (MR-A4)
> **TN-UPDATE entry**: 246
> **Motore sostanziale**: AMILCARE DeepSeek V4 Pro via `mcp__amilcare__reason`
> **Orchestratore**: SEVERO (subagent custom non ancora registrato come `subagent_type` di sistema → workflow eseguito manualmente da NINO seguendo `.claude/agents/severo.md`)
> **Voto SEVERO**: **2/10**

---

## TL;DR — SEVERO

> Si poteva fare meglio.
>
> La peggior scelta è aver varato un modulo backtracking con beam=8 e
> depth fino a 11 **senza alcuna analisi di complessità né misure di
> contenimento**: 8^11 nodi possibili, nemmeno un benchmark
> worst-case. A questo si aggiunge una grave regressione rispetto al
> greedy sui vincoli di servizio e un ordine di esecuzione che
> trasforma il modulo in una fabbrica di doppi conteggi. **Voto 2/10.**
>
> Il modulo introduce un meccanismo potenzialmente utile ma lo fa
> senza controlli di sostenibilità, ignorando vincoli già consolidati
> e addirittura innescando elaborazioni duplicate – un rilascio che,
> allo stato, è un rischio più che un avanzamento.

---

## 3 Finding HIGH (verbatim da SEVERO)

### HIGH-1: Beam × depth non misurato (zona grigia 5)

**Perché HIGH** (SEVERO):

> Un fattore di ramificazione 8 e profondità dinamica fino a 11 danno
> uno spazio di ricerca fino a 8^11 nodi senza valutazione empirica
> né tetto computazionale. In produzione può congelare il sistema o
> far esplodere la latenza senza alcuna segnalazione, vanificando
> l'affidabilità del builder.

**Fix concreto per MR successivo** (SEVERO):

> Imporre un limite rigido al numero di nodi visitati (es. 10^6),
> misurare tempo e consumo in scenari worst-case documentati dal
> V4 Pro, e aggiungere una soglia di abort con log strutturato. Solo
> dopo l'analisi si può approvare beam>3.

**Filtro NINO**: ✅ **ACCETTATO HIGH**. Il pruning km_cap che ho ipotizzato
contenitivo NON è quantificato. Il timeout del builder è gestito a
runtime senza limite esplicito sul backtracking. Bug latente.

---

### HIGH-2: Vincoli MR-4 non replicati nel backtracking (zona grigia 7)

**Perché HIGH** (SEVERO):

> Il backtracking esplora soluzioni ignorando `max_sosta_diurna` e
> `min_servizio_giornata`, che il greedy rispetta. Ciò introduce
> *regressione* dove la nuova logica può proporre soluzioni illegali
> o peggiori di quelle esistenti, rompendo la validazione già
> verificata. Equivale a consegnare un percorso che il sistema
> operazionale rifiuterebbe, senza che l'utente lo sappia.

**Fix concreto per MR successivo** (SEVERO):

> Replicare i controlli greedy nel modulo backtracking, inserendoli
> nel calcolo dello score e nella fase di pruning, con test di non
> regressione che confrontano greedy e backtracking sui medesimi casi
> reali.

**Filtro NINO**: ✅ **ACCETTATO HIGH**. Verificato:
`backtracking_esplorativo.py:_estendi_ricorsivo` salta i controlli su
`max_sosta_diurna_min` e `min_servizio_giornata_pct` che
`multi_giornata.py:601-623` applica. **REGRESSIONE REALE**: in modo
esplorativo il backtracking può estendere giri che violano vincoli
configurati dal pianificatore. Bug critico, fix urgente in MR-A4-bis
prima di A7 reale.

---

### HIGH-3: Backtracking eseguito prima di A2 closure (zona grigia 9)

**Perché HIGH** (SEVERO):

> Eseguire l'esplorazione su un `ciclo_aperto_irrisolto` (pre-A2)
> produce uno stato inconsistente e, alla successiva chiusura, forza
> un doppio processing sullo stesso ciclo. Oltre allo spreco di CPU,
> genera soluzioni duplicate e potenziali race condition sui dati
> intermedi, minando la coerenza del piano finale.

**Fix concreto per MR successivo** (SEVERO):

> Spostare l'invocazione del backtracking dopo la chiusura A2, o
> comunque garantire che operi solo su cicli già stabilizzati.
> Aggiungere un guard-clause che scarti mosse su cicli ancora aperti,
> documentandolo nella pre-condizione del modulo.

**Filtro NINO**: ⚠️ **ACCETTATO PARZIALMENTE — MED**. SEVERO sta leggendo
una semantica errata del flusso:

- A4 backtracking opera su giri con motivo `non_chiuso` o `sotto_min`
  (NON `ciclo_aperto_irrisolto`, che è il marker prodotto da A2).
- L'ordine corretto è A4→A2: A4 estende cicli aperti che POTEVANO
  raggiungere n_min via beam search, A2 prende i residui e tenta
  chiusura via vuoto intra-area.
- Niente doppio processing: A4 e A2 sono pure functions sequenziali,
  ognuna riceve nuovo stato.

Tuttavia c'è un **kernel di verità**: se A4 estende un giro a 4
giornate ma resta `non_chiuso`, A2 lo prende e prova chiusura
intra-area. Sequenza corretta funzionalmente ma potenzialmente
**dispendiosa** se gran parte dei giri estesi finiscono comunque in
A2. Fix proposto: aggiungere telemetria nel logging A7 per misurare
overlap A4∩A2 (giri estesi da A4 che poi cadono in A2). Se overlap
alto, valutare riordino. **Severità rivista a MED**, non HIGH.

---

## Cosa SEVERO non ha rilevato (ma NINO segnala)

### MED-NINO-1: Score function arbitraria (zona grigia 3)

I pesi `_score_stato` (km×0.5, n_corse×1, +50 chiude, +30 raggiunge_min,
-0.5 n_giornate) sono scelte mie senza validazione utente. SEVERO non
li ha contestati ma:

- Bilanciamento km/corse arbitrario: 1 km vale 0.5, 1 corsa vale 1
  ⇒ una catena di 2 corse pesa quanto 4 km. Senza fondamento.
- Bonus +50/+30 non scalati con dimensioni del giro.
- Nessun parametro per programma per tweak empirico.

**Fix MR-A4-bis**: parametrizzare i pesi in `ParamBacktracking` con
default attuali; documentare in commento che sono "default empirici da
calibrare in A7".

### MED-NINO-2: Test no-DB max 4 catene (zona grigia 2)

13 test sintetici con max 4 catene, niente test su volume reale
(200+ catene per giorno-materiale). Coverage insufficiente per L
effort. **Fix**: aggiungere test parametrizzati con N=20, N=100, N=200
catene + benchmark di runtime (assertable < soglia).

### MED-NINO-3: Regola 9 CLAUDE.md violata (zona grigia 8)

NINO ha scritto il modulo da solo senza coinvolgere FAUSTO/AMILCARE.code
per la stesura. Solo validation pre-design con AMILCARE.reason. Regola
9 CLAUDE.md aggiornata oggi: "ogni codice scritto con ausilio". MR-A4
viola la regola appena introdotta. **Fix**: per MR-A4-bis, coinvolgere
AMILCARE.code (V4 Flash) per stesura della fix dei vincoli MR-4 +
review FAUSTO finale.

---

## Cosa NON è stato fatto e si poteva fare

1. **Benchmark empirico worst-case**: simulare beam=8/depth=11 su pool
   sintetico di 200 catene + misurare tempo/nodi. Non fatto, sebbene
   sia il primo controllo a cui SEVERO punta.

2. **Test di non-regressione greedy vs backtracking**: stesso input
   PdE → confronto output (n_giri, motivo distribuzione, vincoli MR-4
   rispettati). Avrebbe smascherato HIGH-2 prima del commit.

3. **Documentazione invariant del modulo**: nessun blocco "Pre-condizioni
   / Post-condizioni / Invariant" esplicito sul modulo. Pure function
   sì, ma quali invariant assicura sulle giornate output? (es. "le
   giornate output rispettano i vincoli del programma_materiale" è
   un'asserzione che HIGH-2 dimostra essere FALSA).

---

## Voto finale: **2/10**

Motivazione SEVERO:

> Il modulo introduce un meccanismo potenzialmente utile ma lo fa
> senza controlli di sostenibilità, ignorando vincoli già consolidati
> e addirittura innescando elaborazioni duplicate – un rilascio che,
> allo stato, è un rischio più che un avanzamento.

**NINO concorda con la severità del voto**: 2 finding HIGH genuini
(complessità non misurata + regressione vincoli MR-4) sono blocking
per A7 produzione. MR-A4-bis è priorità #1 prima di MR-A5/A6/A7.

---

## Azioni post-critica

1. **MR-A4-bis** (M effort, da fare PRIMA di A7):
   - HIGH-1 fix: limite hard `n_branches_max` (default 100k) +
     abort + log
   - HIGH-2 fix: replicare check `max_sosta_diurna_min` e
     `min_servizio_giornata_pct` in `_estendi_ricorsivo`
   - MED-NINO-1 fix: pesi score parametrizzati in `ParamBacktracking`
   - MED-NINO-2 fix: 3 test volume parametrizzati N=20/100/200
   - **Coinvolgere AMILCARE.code per stesura della fix** (regola 9)
2. **MR-A4 NON modificato in-place** (regola 9 CLAUDE.md aggiornata
   entry 245: "Eventuali fix → nuovi MR, mai correzioni in-place del
   MR criticato").
3. Telemetria HIGH-3 in MR-A7 per misurare overlap A4∩A2.

---

## Tracciabilità

- **Commit criticato**: `b3ddc57`
- **Branch**: `master`
- **Brief AMILCARE V4 Pro**: contesto + 10 zone grigie + format request
  → output 700 parole strutturato HIGH×3 + voto.
- **Filtro NINO**: 2 HIGH confermati, 1 HIGH ridotto a MED (kernel di
  verità ma SEVERO ha letto male il flusso A4→A2 sequenziale).
- **3 MED aggiunti da NINO** non rilevati da SEVERO: score arbitraria,
  test volume, regola 9 violata.
