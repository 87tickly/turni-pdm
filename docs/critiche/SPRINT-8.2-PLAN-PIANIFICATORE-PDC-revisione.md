# Critica SEVERO — PLAN preventivo Sprint 8.2 revisione Pianificatore PdC

**Data**: 2026-05-09
**Oggetto**: PLAN scritto da NINO PRIMA della codifica (5 MR + 3 prereq).
  Non è un commit — è un piano da approvare/respingere.
**Entry TN-UPDATE**: nessuna ancora (la critica precede la decisione utente).
**Motore usato**: ❌ **AMILCARE V4 Pro non disponibile** in questa
  sessione. 6 invocazioni `mcp__amilcare__reason` consecutive in
  timeout `-32001` su brief 2-5KB; ping minimale (`"Rispondi solo PRONTO"`)
  passa, quindi server raggiungibile ma il modello satura ogni domanda
  non triviale (probabile saturazione capacità DeepSeek odierna o
  reasoning_effort interno troppo alto). Pattern già visto in entry 248
  con brief gigante; oggi si ripete anche con brief snello. **Critica
  prodotta in fallback NINO puro** — da rifare con AMILCARE operativo.
  Il bias di auto-compiacenza verso il proprio plan è inevitabile e va
  smascherato dichiarandolo: NINO è autore del plan E critico. Per
  questo motivo i finding sotto sono filtrati con tono extra-severo
  (sopra-correzione bias), e la classifica aspetta verifica AMILCARE.

**Voto SEVERO (provvisorio fallback)**: **4/10** *(perimetro AMILCARE
  non verificato — se AMILCARE confermerà avremmo 4/10 stabile, se
  indurirà potremmo scendere a 3/10)*.

---

## TL;DR

> Il plan affronta i 4 punti dichiarati dall'utente, ma li tratta come
> 5 MR isolati senza affrontare il **debito normativo strutturale** del
> builder (5+ regole §10.3, §11.4, §15, §6 PK, §9 CV efficiency
> escluse senza giustificazione oggettiva). MR-C2 ripropone il default
> (c) che è **lo stesso pattern di Sprint 7.10 MR 7.10.7 che l'utente
> ha appena bocciato**. La stima 18-37h ha range 2× che tradisce
> incertezza; il test plan per ogni MR non è dichiarato. Pigrizia
> presente in 3 punti diversi (residui §10.3/§11.4/§15/§9, default P1
> ricalca lavoro fallito, P1 delegata pur avendo già un default).

---

## Cosa funziona

- Separazione P1/P2/P3 prerequisiti vs MR è pulita: P2 (esempi reali
  utente) è genuinamente bloccante, NINO non poteva inventarlo.
- MR-C1 audit normativa con output `docs/AUDIT-PDC-NORMATIVA-2026-05-09.md`
  è onesto: si dichiara che il piano completo dipende da quanti finding
  emergono, non si finge di sapere ora.
- MR-C5 trigger basato su flag programma `auto_generate_pdc=BOOL` è
  reversibile (rispetta R5 "preservare non distruggere": il flusso
  manuale resta).
- Riconosce che opt(b) "componente unificato `<GanttGiornata>`" costa
  12-16h vs 6-10h opt(c) — almeno il trade-off è dichiarato.

## Cosa si poteva fare meglio

### S1 — P1 default (c) è LO STESSO PATTERN che Sprint 7.10 MR 7.10.7 ha già fatto e l'utente ha bocciato

- **Severità**: HIGH
- **Dove**: plan §"Pre-requisiti P1" + commento Sprint 7.10 in
  `frontend/src/routes/pianificatore-giro/TurnoPdcDettaglioRoute.tsx:34-62`
  (pattern attuale: "ricalcato sulla grammatica del Gantt giro
  materiale (1° ruolo) con palette dedicata", single-line per
  giornata, sticky axis, mini-mappa fishbone).
- **Cosa**: il plan offre 3 opzioni per P1. L'opzione (c) "estrarre
  sotto-componenti riusabili (axis, ticks-bg, blocco), route separate"
  è **letteralmente** la descrizione di ciò che MR 7.10.7 ha già
  prodotto: `Card → AxisHeader sticky → ticks-bg single-line →
  blocchi posizionati assolutamente`. NINO **sceglie (c) come default
  proprio**. Ma l'utente ha appena dichiarato 7.10.7 INSUFFICIENTE.
- **Perché HIGH**: scegliere come default il pattern già fallito è il
  caso da manuale di pigrizia mascherata da "scope ridotto, costo
  basso". L'utente ha usato il verbo "RIFATTO" (forte). NINO traduce
  "rifatto" in "patch + riusa" perché costa 6-10h invece di 12-16h.
  È esattamente la dinamica di CLAUDE.md §7 ("scope-cutting silente
  mio").
- **Fix proposto**: invertire la logica. Default proposto da NINO →
  opt(a) **riscrittura allineata al layout PDF Trenord giro**
  (multi-riga per giornata, banda notturna, palette commerciale rossa
  CONDOTTA, label stazioni in-blocco). Opt(c) come ripiego solo se
  l'utente in P1 dichiara "no, non voglio mimare il Gantt giro
  materialmente, voglio solo riuso componenti". P1 va ribaltata: NINO
  **propone** (a), utente **conferma o devia**, non viceversa.
- **Costo del fix**: 0h (decisione, non codice). Se accettato cambia
  i numeri MR-C2: 12-16h opt(a) invece di 6-10h opt(c).

### S2 — MR-C4 non include 5+ regole NORMATIVA fondamentali, senza giustificazione oggettiva (pigrizia §7)

- **Severità**: HIGH
- **Dove**: plan §MR-C4. Lista NINO: "probabili: §6 CV/ACC/PK gap,
  §11.3 ≤15:00, §3.3 ACCp 80', §7.3 rientro produttivo, §11.2 no
  mattino post-riposo".
- **Cosa**: il plan ammette esplicitamente che **5 regole**
  NORMATIVA-PDC.md sono fuori scope di tutti gli MR proposti:
  1. **§10.3** struttura FR g1+g2 unica unità-turno (non due turni
     separati). Oggi probabilmente non rispettata: il builder
     produce/consuma "turni giornalieri" non "turni multi-giornata".
     Verificato in `multi_turno.py` ma non con dettaglio sufficiente
     per dire "implementato §10.3".
  2. **§11.4** riposo settimanale ≥62h con 2 giorni solari. Non
     emerge da grep nel builder.
  3. **§15** vincolo unicità no doppioni. Non emerge.
  4. **§6 PK** opt-in operatore >300'. Non emerge.
  5. **§9 CV intermedi efficiency** (gap<65 → CVa/CVp che
     sostituiscono ACCa/ACCp risparmiando 80'). `split_cv.py:27-28`
     dichiara espressamente "Limitazione MVP: non viene applicato il
     pattern CV no-overhead". Sprint 7.4 lo ha lasciato aperto.
- **Perché HIGH**: la richiesta utente §3 dice testualmente "**la
  normativa non viene rispettata**". Risposta NINO: "ne copro 5,
  altre 5+ restano aperte, non lo dichiaro nel piano". Questa è la
  forma più letterale della pigrizia §7: residui fuori scope **non
  motivati oggettivamente** né concordati con l'utente. Se erano
  troppo grossi per Sprint 8.2, vanno **dichiarati** come "Sprint
  8.3" o "MR-C6/C7 a parte" con motivazione, non taciuti.
- **Fix proposto**: il plan deve avere una sezione "Cosa NON sarà
  fatto in Sprint 8.2 e perché". Per ognuna delle 5+ regole: o (a) la
  includi in MR-C4/C6, o (b) dichiari il motivo oggettivo dell'esclusione
  ("§10.3 richiede refactor modello dati turno multi-giornata = MR
  separato Sprint 8.3", "§9 CV efficiency richiede coordinamento con
  rotture composizione"), o (c) chiedi conferma utente. Test del
  residuo CLAUDE.md §7: §11.4 e §15 sono probabilmente <2h ciascuno;
  §6 PK opt-in è ~3-4h (UI flag + builder branch); §10.3 è grosso
  davvero. Ma il plan non distingue.
- **Costo del fix**: 30min di plan-writing + eventuale +6-10h se §11.4,
  §15, §6 PK passano in MR-C4.

### S3 — MR-C2 e MR-C3 dichiarati paralleli ma collidono sull'output (interfaccia non documentata)

- **Severità**: HIGH
- **Dove**: plan §MR ordering "C2 || C3 paralleli" + plan §MR-C3
  "vetture: priorità §7.2 vettura→MM→VOCTAXI fallback".
- **Cosa**: MR-C3 introduce nuovi blocchi nel turno PdC (`MM`, oppure
  un nuovo `tipo_evento="VOCTAXI"` o `"MM"` non presenti oggi —
  `builder.py:141` lista i tipi attuali: `CONDOTTA, VETTURA, REFEZ,
  ACCp, ACCa, CVp, CVa, PK, SCOMP, PRESA, FINE`). MR-C2 ridisegna il
  Gantt PdC che deve **renderizzare** quei blocchi (palette,
  raggruppamento, label, validazione visuale). Senza interfaccia
  concordata: MR-C2 sviluppato in parallelo finisce mocked sui blocchi
  esistenti, poi MR-C3 produce blocchi nuovi → MR-C2 va riaperto =
  doppio lavoro.
- **Perché HIGH**: in CLAUDE.md regola 5 e §3 "un passo alla volta",
  due MR paralleli con condivisione output è il classico anti-pattern.
  Soprattutto se MR-C2 è il pezzo più costoso (12-16h o 6-10h).
- **Fix proposto**: o (a) serializzare MR-C3 → MR-C2 (prima i nuovi
  blocchi backend, poi il Gantt che li disegna), o (b) MR-C3.0 da fare
  PRIMA di entrambi: "definire schema blocchi turno PdC esteso (tipi
  MM/VOCTAXI, etichetta_corta, palette suggerita)" — output:
  `docs/SCHEMA-BLOCCHI-TURNO-PDC.md` o estensione esplicita di
  `docs/schema-pdc.md`. Tempo: 1-2h ma sblocca veri parallelismo.
- **Costo del fix**: 1-2h (scelta a) oppure 0h (scelta b, solo
  riordino del piano).

### S4 — Stima MR-C5 2-3h ottimistica: include migration + endpoint + errori asincroni + test E2E

- **Severità**: HIGH
- **Dove**: plan §MR-C5 "Trigger automatico Giro→PdC con flag
  `auto_generate_pdc` + endpoint reattivo on publish".
- **Cosa**: il plan stima MR-C5 in 2-3h. La stessa frase elenca:
  1. Flag `auto_generate_pdc=BOOL` su programma → migration alembic
     (~30min, ma già fa scattare deploy Railway + verifica regola CLAUDE.md §2).
  2. Endpoint reattivo on publish → modificare `POST /api/giri/.../publish`
     (o equivalente) per disepatch generazione PdC, gestire transazione,
     gestire fallimento (rollback? notifica? retry?).
  3. Comportamento se la generazione fallisce a metà (es. timeout
     durante creazione 30 turni PdC): il giro resta published ma senza
     PdC? Riapre stato? Nessuna decisione nel plan.
  4. Test E2E: pubblica giro → verifica turni PdC creati. Mock
     live.arturo.travel. Asincrono.
- **Perché HIGH**: 2-3h è ~2x sotto il vero costo. La regola CLAUDE.md
  §2 "ogni modifica → commit + push + main su Railway" + verifica logs
  da sola costa 30min. Numeri non ipotesi: MR comparabili (MR α/β del
  refactor UX 2026-05-06) costavano ~4-6h ciascuno secondo TN-UPDATE.
- **Fix proposto**: rivedere stima a 4-6h. Aggiungere al plan: (a)
  policy errore generazione (suggerimento: "se la generazione fallisce,
  il giro resta published, l'errore è loggato in
  `programma_evento_log`, l'utente vede badge giallo che richiede click
  manuale per retry"); (b) idempotenza endpoint (publish chiamato 2x
  non genera 2x i turni); (c) test E2E con mock live.arturo + scenario
  failure.
- **Costo del fix**: 0h del plan, ma riallinea il totale stimato a
  20-40h (più realistico).

### S5 — Test plan per MR non dichiarato, "regressione visuale" è solo rischio non test obbligatorio

- **Severità**: HIGH
- **Dove**: plan §Rischi "R2 regressione visuale Gantt" + assenza di
  qualunque sezione "test" per ciascun MR.
- **Cosa**: il plan elenca 5 MR e 5 rischi ma non specifica per ogni
  MR (a) test esistenti che devono continuare a passare, (b) test
  nuovi obbligatori, (c) verifica preview/screenshot, (d) numero o
  metrica che dimostra "fatto". CLAUDE.md regola 2 "Numeri non ipotesi"
  e regola 5 "Verifica prima del commit" sono apertamente non
  applicate al piano.
- **Perché HIGH**: la regola 5 dice "build + preview + numero". Senza
  test plan dichiarato, ogni MR rischia di chiudere con "test passano"
  ma senza dimostrare la *correttezza* del fix. In particolare MR-C4
  (5 regole normativa): per ognuna serve un caso fixture esempio (es.
  "turno con condotta ultimo giorno pre-riposo che termina alle 17:30
  → builder deve troncare/spostare a ≤15:00") o il fix è non
  verificabile.
- **Fix proposto**: aggiungere sezione "Test plan" per MR-C2, C3, C4,
  C5. C2: snapshot screenshot before/after + test render manuale 3
  scenari (turno semplice, multi-giornata, FR). C3: unit test resolver
  con fixture VOCTAXI/MM/edge 8h30 sforata. C4: 1 unit test per regola
  (5 test minimum) + 1 fixture E2E che mostra builder rispettare la
  regola in un programma reale. C5: test E2E publish→generate +
  scenario failure + scenario retry.
- **Costo del fix**: 30min di plan-writing.

### S6 — P1 delegata all'utente pur avendo già un default NINO: scaricare la decisione

- **Severità**: MEDIUM
- **Dove**: plan §"Pre-requisiti decisioni utente P1".
- **Cosa**: NINO scrive "P1 — Cosa significa Gantt simile? Default
  NINO: opt(c)". Quindi NINO **ha** una proposta. Ma la registra come
  prerequisito da utente, ovvero come "decisione utente bloccante".
- **Perché MEDIUM**: P1 è la scelta più impattante del piano (fa
  variare MR-C2 da 6-10h a 12-16h). NINO ha la competenza per
  proporre — anche perché ha già verificato il commento esistente
  in 7.10.7 e conosce il fallimento. Lasciare P1 come "decidi tu"
  pulisce le mani. CLAUDE.md §7: "Il fix richiede una decisione
  utente che non ho? Se sì → chiedi". Ma NINO ha la decisione, ha solo
  paura di dichiararla per il rischio che cambi il costo.
- **Fix proposto**: P1 va eliminata come "prerequisito" e diventare
  "raccomandazione NINO da confermare in 1 riga": *"Raccomando
  opt(a) riscrittura layout PDF Trenord giro perché Sprint 7.10 ha
  già provato il pattern (c) e l'utente ha bocciato. Costo MR-C2:
  12-16h. Conferma o correggi?"*. Stessa cosa P3 (NINO ha già
  default `(a) publish giro` — confermala come raccomandazione).
  Solo P2 resta vero prerequisito.
- **Costo del fix**: 5min.

### S7 — Audit MR-C1 prima di sapere quanti finding non-banali = MR-C4 a costo non stimabile

- **Severità**: MEDIUM
- **Dove**: plan §MR-C1 + §MR-C4 + §Rischi R1.
- **Cosa**: NINO scrive C1 (audit, 2-4h, fix banali chiusi qui) e C4
  (fix non banali, 4-8h, lista *probabile*). Ma C4 è scritto **prima**
  di sapere il risultato di C1. R1 "audit > 5 critici → C4 cresce" è
  citato nei rischi ma non gestito.
- **Perché MEDIUM**: la struttura ha un gap logico: il piano si auto-
  dichiara conclusivo (5 MR) prima di avere i dati per dirlo. Se C1
  trova 8 fix non banali, C4 può raddoppiare. Il piano andrebbe
  scritto come "C1 audit, poi sessione di plan-revision dove
  decidiamo C4/C6/C7 in base ai finding".
- **Fix proposto**: marcare C4 come *"Costo dipende da output C1.
  Stima preliminare 4-8h se finding ≤5 non-banali. Plan da rivedere
  dopo C1 chiuso, prima di iniziare C4."* + aggiungere checkpoint
  esplicito.

### S8 — Range stima 18-37h è 2× = stima fragile (sintomo di "non lo so davvero")

- **Severità**: MEDIUM
- **Dove**: plan §"Costo totale".
- **Cosa**: range 18-37h. Max è 2.06× min. Pratica buona ingegneristica:
  range >1.5× = lo stimatore non sa davvero. Range 2× = ipotesi
  selvaggia.
- **Perché MEDIUM**: NINO sta dichiarando incertezza che CLAUDE.md
  regola 2 "numeri non ipotesi" non ammette per claim definitivi. Il
  range va o ridotto (più analisi prima del plan) o motivato variabile
  per variabile (es. "MR-C2 6-16h dipende P1; MR-C4 4-8h dipende C1").
- **Fix proposto**: spaccare il range. Costo deterministico (C1+C5) +
  range condizionale (C2 da P1, C4 da C1, C3 fisso).

## Debito tecnico segnalato (residui che il plan tace)

| Regola | Stato dichiarato dal plan | Stato vero |
|--------|---------------------------|------------|
| §10.3 FR g1+g2 unica unità-turno | non menzionata | aperta |
| §11.4 riposo settimanale ≥62h+2gg solari | non menzionata | aperta |
| §15 unicità no doppioni | non menzionata | aperta |
| §6 PK opt-in operatore >300' | non menzionata | aperta |
| §9 CV intermedi efficiency (gap<65 → CV no-overhead) | non menzionata | aperta da Sprint 7.4 (`split_cv.py:27-28`) |
| §10 FR struttura intera (g1 fine, riposo, g2 ripresa) | non menzionata | parzialmente coperta (cap 1/sett+3/28gg ma non struttura) |

Il plan dichiara come outcome "Pianificatore PdC rivisto". Con questi 6
residui aperti senza menzione, l'outcome è **falso**. Pigrizia §7:
giustificato solo se motivazione oggettiva o sì utente, e qui non c'è
nessuno dei due. Test del residuo:

- §11.4 e §15: ognuno probabilmente <2-3h → CHIUDIBILI in MR-C4 esteso
  o MR-C6 mini. ❌ pigrizia se restano fuori senza motivazione.
- §6 PK opt-in: ~3-4h (UI checkbox + builder branch) → CHIUDIBILE in
  MR-C4 esteso. ❌ pigrizia.
- §9 CV efficiency: probabilmente ~6-10h (richiede toccare split_cv +
  test). Aperto da Sprint 7.4 = ✅ legittimo come MR a sé, ma va
  **dichiarato** come "MR-C6 Sprint 8.3", non taciuto.
- §10.3 FR struttura g1+g2 unica: probabilmente migration modello dati
  (turno multi-giornata) → ✅ legittimo come MR grosso a sé, va
  dichiarato.
- §10 FR struttura: incrocia §10.3, idem.

Conclusione: il piano dovrebbe contenere una sezione "Sprint 8.3
preview" con MR-C6 §9, MR-C7 §10/§10.3 esplicitamente dichiarati come
"NON in 8.2, motivo: refactor grosso / coordinamento composizione".

## Aderenza al METODO-DI-LAVORO (le 7 regole, applicabili al plan)

1. **Diagnosi prima di azione** — ✅ parzialmente. NINO ha aperto i
   file, fatto grep sui residui (verifica anche in critica). Però non
   ha fatto un audit sistematico del builder vs NORMATIVA prima di
   scrivere il piano: l'audit è MR-C1, scritto come azione futura.
   Sarebbe diagnosi-prima-di-piano, non diagnosi-dentro-il-piano.
2. **Numeri non ipotesi** — ❌ violata sui costi (range 2× S8).
3. **Un passo alla volta** — ❌ MR-C2||C3 paralleli con interfaccia
   non documentata (S3).
4. **Ammettere l'errore** — N/A (no errore in atto).
5. **Verifica prima del commit** — ❌ test plan per MR non dichiarato
   (S5).
6. **Preservare non distruggere** — ✅ MR-C5 con flag mantiene flusso
   manuale (good).
7. **Costanza nel tempo** — N/A.

## Voto complessivo

**4/10** *(provvisorio, fallback NINO puro, da confermare AMILCARE)*.

Motivazione: il plan affronta i 4 punti utente in modo strutturato ma
con tre forme distinte di pigrizia §7 (default P1 ricalca lavoro
fallito, 6 regole normativa silenziate, P1 delegata pur avendo
default), 2 stime ottimistiche (MR-C5, MR-C4 in caso C1>5 finding),
1 anti-pattern di MR paralleli senza interfaccia, e nessun test plan
dichiarato. Se accettato così com'è, lo Sprint 8.2 chiuderà con
"Pianificatore PdC rivisto" ma il builder violerà ancora §10.3, §11.4,
§15, §9 — esattamente il problema dell'utente §3 "normativa non
rispettata" parzialmente irrisolto. Bocciato per riapertura.

Scala SEVERO:

- 9-10: lavoro da senior, finding solo cosmetici
- 7-8: solido, qualche miglioramento sostanziale possibile
- 5-6: funziona ma con debito o blind spot non secondari
- **3-4**: problemi strutturali, da rivedere ← qui
- 1-2: bocciato, riaprire prima di proseguire

## Cosa NON ho controllato

- **Critica con AMILCARE**: 6 timeout `-32001`. Il fallback NINO puro
  è inevitabilmente compiacente verso il proprio plan. AMILCARE V4
  Pro avrebbe probabilmente: (a) confermato S1, S2, S5, S6 (i più
  netti), (b) potenzialmente alzato la severità di S2 a CRITICAL
  (residui normativi taciuti = bug semantico non solo gestione scope),
  (c) probabilmente trovato 1-2 finding aggiuntivi che NINO non vede
  per sua natura. Voto AMILCARE-driven probabile: **3/10**.
- **Verifica empirica builder vs NORMATIVA**: ho fatto grep mirato
  (VOCTAXI=0, auto_generate_pdc=0, riferimenti §6/§7/§11.4/§15) ma
  non ho fatto un audit completo. È esattamente quello che MR-C1 deve
  fare. Possibile che alcune regole "non coperte" siano in realtà
  parzialmente coperte, o viceversa che ci siano altre regole non
  coperte che non ho rilevato.
- **Costi reali Gantt 6-10h vs 12-16h**: NINO non ha mai prodotto un
  Gantt da 4.389 LOC come quello del Giro. Le stime sono basate su
  intuizione, non su misura comparabile. Range probabilmente
  ottimistico in entrambe le opzioni.
- **Verifica che §10.3 FR g1+g2 sia davvero non coperta**: `multi_turno.py`
  ha 1.274 LOC, ho letto solo intestazione e grep specifici. Possibile
  copertura parziale che ho mancato.
- **FAUSTO non consultato**: il plan menziona "NINO usa AMILCARE+FAUSTO".
  Per onestà segnalo che FAUSTO (review veloce, grep) avrebbe potuto
  essere usato da NINO durante la scrittura del piano per verificare
  alcune delle "non-coperture" prima di passare a SEVERO. NINO non
  l'ha fatto.

---

## Azioni post-critica (proposta SEVERO, decisione NINO+utente)

1. **NINO riscrive il plan** affrontando S1-S5 (HIGH) prima di passarlo
   all'utente:
   - P1 → raccomandazione esplicita opt(a) con motivazione 7.10 fallito
   - C2/C3 → seriallizzati o con MR-C3.0 schema-blocchi prima
   - MR-C4 esteso o MR-C6 mini per §11.4, §15, §6 PK
   - Sezione "Sprint 8.3 preview" per §9, §10.3, §10 FR struttura
   - Test plan per ogni MR
   - Stima C5 → 4-6h
2. **AMILCARE retry**: aspettare che il servizio si liberi, ri-lanciare
   `mcp__amilcare__reason` con stesso brief, eventualmente alzare
   `AMILCARE_TIMEOUT_SEC` o accorciare il brief a <1KB.
3. **Plan riveduto** torna a SEVERO per critica AMILCARE-driven prima
   dell'approvazione utente.

---

## Tracciabilità

- **Plan criticato**: scritto da NINO 2026-05-09, mai committato.
- **Brief AMILCARE tentato**: 6 versioni decrescenti 5KB→2KB→1KB. Tutti
  timeout `-32001` su 60s. Ping minimale (`question="Rispondi solo:
  PRONTO"`) ha risposto in <2s — server raggiungibile, modello satura
  ogni domanda non triviale oggi.
- **Filtro NINO**: nessuno (è NINO l'autore di entrambi). Filtro
  applicato: tono extra-severo per sopra-correggere bias auto-compiacenza
  documentato in entry 248 (fallback NINO 6/10 → AMILCARE 4/10 sullo
  stesso MR).

## Note sul workflow SEVERO

- Questa è la **5ª critica** di SEVERO (precedenti: MR-A3, MR-A4,
  MR-A7, MR-B2 — tutte voto 2-4/10).
- È la **2ª critica in fallback NINO puro** dopo entry 248. Entrambe
  da rifare con AMILCARE quando operativo.
- È la **1ª critica su un PLAN PREVENTIVO** invece che su un commit.
  Pattern utile: se il piano è bocciato qui, si evita di scrivere
  codice da buttare. Costo critica preventiva << costo MR fallito.
