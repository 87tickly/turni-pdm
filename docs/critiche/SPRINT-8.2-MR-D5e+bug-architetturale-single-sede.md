# Critica SEVERO — MR-D5e (fix FK MISTO) + 2° bug architetturale single-sede vs multi-sede

**Data**: 2026-05-09
**Commit / range**: `ff2873d` (MR-D5e, builder.py +52 -9) + diagnosi
2° bug architetturale a `builder.py:1252-1254` (preesistente, scoperto
dal retry e2e post-fix)
**Entry TN-UPDATE**: 270
**Motore usato**: AMILCARE V4 Flash via `mcp__amilcare__code` (brief
~1KB, output ~500 parole) come fallback dichiarato dopo **3 timeout
consecutivi** di V4 Pro su `mcp__amilcare__reason` con brief 3-3.5KB
e poi 1KB. Output filtrato da NINO: corretto un falso positivo
("`_materiale_da_regola[0]` IndexError" — è una funzione, non
indicizzazione di lista, e gestisce composizione vuota a
builder.py:825-828); orchestrazione SEVERO eseguita manualmente da
NINO seguendo `.claude/agents/severo.md` e dichiarata come fallback
operativo (pattern entry 248, voto provvisorio se motore non
operativo).

---

## Sintesi (3 righe)

Il fix MR-D5e chiude correttamente la FK violation MISTO ma è
chirurgico, non corregge la causa a monte (segmenti `_tronco_X` non
mappati) e introduce uno scarto silenzioso di giri senza test sul
ramo nuovo. Il retry e2e ha smascherato un 2° bug architetturale
preesistente (builder.py:1252-1254 single-sede) che produce il calo
catastrofico 2450→52 corse processate (98% perdita) e dimostra che
la raccomandazione SEVERO #2 originale ("HARD no ciclo aperto fuori
area Milano") era corretta solo nell'ipotesi multi-sede mai resa
esplicita nel piano. **Voto: 4/10 provvisorio fallback** — strutturale
sul 2° bug, debito sul fix.

---

## Cosa funziona

- **Diagnosi del bug FK** è corretta e ben motivata in commit message
  + entry TN-UPDATE 270: cascata segmento `_tronco_X` → fallback
    `MISTO` → propagazione su `BloccoAssegnato.composizione` →
    `MaterialeThread.tipo_materiale_codice` (NOT NULL + FK RESTRICT) →
    500. Ricostruita con stack trace e file:riga.
- **Lookup `materiale_per_regola[regola_id]` è autoritativo**: non
  dipende dalla classificazione segmenti, quindi è robusto rispetto
  a tronchi/varianti future. È un miglioramento strutturale rispetto
  al loop `for seg_codice, r_id in regola_per_segmento.items()` del
  pre-fix (O(n) per giro vs O(1) lookup).
- **mypy --strict + ruff clean + 53 test pure-domain green**: il fix
  non rompe nulla di esistente, e il branch è pulito.
- **Onestà sul mancato sblocco e2e**: l'entry TN-UPDATE 270 dichiara
  esplicitamente "Plan-D NON chiuso", "2° bug architetturale
  preesistente", "decisione utente su (a)/(b)/(c)". Niente
  auto-compiacenza di "fix MR-D5e funziona, sblocco completo": NINO
  ha visto il calo 2450→52 e non l'ha mascherato.
- **Validazione funzionale honesty**: HTTP 200 ottenuto è dichiarato
  come "no più 500 FK MISTO", non come "e2e funzionante".

---

## Cosa si poteva fare meglio

### S1 — HIGH — Scarto silenzioso giro: warning loss-of-data invisibile al pianificatore

- **Severità**: HIGH
- **Dove**: `backend/src/colazione/domain/builder_giro/builder.py:1346-1369`
- **Cosa**: il fix scarta il giro con `warnings.append(...)` se
  `regola_id_giro` non risolve a un materiale, ma il warning finisce
  in `BuilderRun.warnings_json`. La response API `/genera-giri`
  ritorna HTTP 200 con `n_giri_creati`, `n_corse_processate` e
  warnings — ma se il pianificatore guarda solo "200 OK" o solo i
  numeri creati senza scrollare i warning, **non si accorge** che N
  giri sono stati silenziosamente persi. Nel retry e2e prog 17 il
  warning è 1 su 43, perso nel rumore.
- **Perché è un problema**: viola in modo sottile il principio
  "metriche non bugiarde" che hai applicato in altre critiche
  (es. SPRINT-8.1-MR-A7 voto 3/10: "trade-off mascherato da metriche
  favorevoli"). HTTP 200 + n_giri_creati=0 con 1 warning di scarto
  fa sembrare il sistema "ok ma vuoto" mentre invece è un fallimento
  silenzioso. Inoltre la regola §7 NIENTE PIGRIZIA è violata: lo
  scarto è ancora "metà-job" — andrebbe ESPOSTO nel response payload
  come `n_giri_scartati: int` con motivo dedicato, non sepolto in
  warnings testuali.
- **Fix proposto**: aggiungi al return di `_genera_giri_linea_centrica`
  una contabilizzazione esplicita `n_giri_scartati` (insieme a
  `n_giri_creati`), e quando >0 nel persister fai sì che il
  `BuilderRun` espliciti `n_eventi_composizione=giri_skippati` o
  un nuovo campo `n_giri_scartati_pre_persist`. La response API
  della route esponga il valore. Frontend aggiunge un toast warning
  visibile se `n_giri_scartati > 0`.
- **Costo del fix**: <2h. Modifica MR-D5e-bis o agganciato a MR-D5g.

### S2 — HIGH — Manca test sul ramo `regola_id=None → scarto giro`

- **Severità**: HIGH
- **Dove**: `backend/tests/test_builder_linea_centrica_adapter.py`
  (nessun test che esercita il branch nuovo); il test esistente
  `test_adapter_blocchi_assegnati_regola_id_none_fallback_a_zero`
  copre solo il caso `regola_id=0`, non `None`.
- **Cosa**: il fix MR-D5e introduce un branch (riga 1358-1369)
  significativo (= "scarta + warning + counter") senza UNA singola
  riga di test. La verifica "53 test pure-domain green" è
  ingannevole: tutti i test esistenti coprono il caso felice
  `regola_id_giro` valido in `materiale_per_regola`. Il caso
  patologico che ha causato la 500 in produzione **non è coperto**.
- **Perché è un problema**: regola §5 METODO violata in modo silente
  (verifica prima del commit). Inoltre la regola §7 NIENTE PIGRIZIA:
  scrivere un test parametrico per il branch è <30 min, ben sotto
  la soglia "<2h" di chiusura obbligata. Il pattern esatto è già
  presente in `test_traduce_turno_senza_regola_id_default_none`
  (linea_centrica/aggregazione), basta replicarlo a livello di
  adapter `_genera_giri_linea_centrica`. Non c'è alcuna motivazione
  oggettiva per ometterlo.
- **Fix proposto**: aggiungi `test_genera_giri_linea_centrica_scarta_giro_se_regola_id_none`
  che mocka `result.giri` con `Giro(giornate=(GiornataGiro(...
  catena_posizionata=CatenaPosizionata(... regola_id=None ...))))`
  e verifica: (a) `BuilderRun.warnings_json` contiene il pattern
  "Giro linea-centrica scartato", (b) il giro NON viene persistito
  (DB vuoto post-call), (c) `n_giri_creati == 0` se quello è
  l'unico giro.
- **Costo del fix**: <30 min.

### S3 — HIGH — Bug architetturale single-sede: la racc SEVERO #2 era condizionata a un'ipotesi multi-sede mai esplicitata

- **Severità**: HIGH (in realtà il blocking del retry e2e — voto
  alzato a HIGH non CRITICAL solo perché il fix è ben definito)
- **Dove**: `backend/src/colazione/domain/builder_giro/builder.py:1252-1254`
  (`sedi_disponibili = {localita.codice: localita.stazione_collegata_codice}`)
  combinato con `assegna_convogli_linea.py:197-229` (`_e_compatibile`)
- **Cosa**: il design MR-D2 applica come HARD constraint il vincolo
  "sede compatibile sse `stazione_collegata in
  segmento.stazioni_sosta_notturna` OR `area(sede) ==
  area(capolinee)`". Era la mia raccomandazione SEVERO #2 sul piano
  ("no ciclo aperto fuori area Milano", voto 7/10). MA: il piano
  Plan-D non ha mai esplicitato che MR-D2 richiede il pool COMPLETO
  delle sedi attive del programma. Il modello cumulativo legacy
  (decisione utente 2026-05-01: 1 chiamata genera-giri = 1 sede)
  porta avanti l'invariante "1 sede in input" → MR-D5b applica
  letteralmente questa invariante → MR-D2 con sola FIO scarta TUTTI
  i 26 segmenti con capolinee non-Milano (Brescia/Bergamo/Tirano/
  Cremona/Lecco) come `errore='no_sede_compatibile'`. Risultato:
  98% delle corse perse (2450 → 52).
- **Perché è un problema**:
  - **Regressione operativa pura**: il legacy esplorativo, sulla
    stessa sede FIO, produce 51 giri / 2450 corse perché non applica
    il vincolo HARD multi-sede di MR-D2. Plan-D introduce una
    feature di robustezza ("no ciclo aperto fuori area") ma in
    single-sede si trasforma in una mannaia che taglia il 98% del
    perimetro operativo.
  - **Errore di mio giudizio nella raccomandazione SEVERO #2**:
    quando ho approvato il PIANO Plan-D 7/10 chiedendo "HARD non
    SOFT" non ho controllato se il design downstream presupponeva
    un input multi-sede. Era una raccomandazione corretta in
    astratto ma incompleta. Andava aggiunta una postilla:
    "ASSUNZIONE: MR-D2 riceve TUTTE le sedi attive del programma;
    in caso single-sede il vincolo HARD va rilassato a SOFT con
    proxy 'rientro sede via vuoto'".
  - **NINO ha applicato la raccomandazione letteralmente** senza
    notare il mismatch al MR-D5b (= primo cambio in builder.py).
    Questo è il bug. Vedi S5 sotto.
- **Fix proposto** — analisi delle 3 strade:
  - **(a) MR-D5f minimal — Caricare TUTTE le sedi attive in
    `sedi_disponibili`**: pragmatico, 4-6h. Il loader carica
    `LocalitaManutenzione` filtrato per `azienda_id` (e magari per
    sedi che hanno almeno 1 regola del programma). Persistenza
    resta scoping per `localita.codice` corrente (= solo i giri
    creati da quella chiamata sono attribuiti alla sede del run).
    Mantiene l'invariante "1 chiamata = 1 sede persistita" del
    modello cumulativo. **MA**: l'algoritmo MR-D2 most-constrained-
    first sceglierà la sede ottimale per ogni segmento, non
    necessariamente la sede del run. Quindi i giri creati per la
    sede del run includeranno SOLO i segmenti che MR-D2 ha
    assegnato a `localita.codice`. Per gli altri segmenti il
    pianificatore dovrà fare le altre N-1 chiamate
    (genera-giri per ALES, BG, BS, ecc.). Modello cumulativo
    preservato ma rallentato (richiede 6 chiamate frontend invece
    di 1 per coprire le 6 sedi attive). **Possibile artefatto**: se
    MR-D2 assegna un segmento a una sede X e l'utente NON chiama
    mai `genera-giri` per X, quei giri non vengono mai creati.
    Devi mostrare in UI "segmenti assegnati a sedi non ancora
    eseguite".
  - **(b) Revisione architetturale completa — Modello multi-sede
    atomico**: 2-3 settimane. 1 chiamata genera-giri per programma
    = tutte le sedi processate insieme. Breaking change della
    decisione utente 2026-05-01. Richiede redesign del lock
    builder, della response, della UI. È la strada "pulita" ma
    cambia un contratto consolidato.
  - **(c) Sospendere Plan-D, riconsolidare esplorativo come
    default**: rollback per il momento. Plan-D resta in `master`
    come modalità opt-in (`builder_mode='linea_centrica'`)
    sperimentale. Nessun pianificatore reale lo usa fino a che
    (a) o (b) non chiudono il single-sede.
  - **Mia raccomandazione**: **(c) immediato + (a) come MR-D5f
    nello sprint 8.3**. Procedere subito con (a) senza fermare
    significa accumulare debito (manca anche S2 test, S1 loss-of-
    data, MR-D5g per `regola_id=None`, MED 'pipeline mock-only'
    di MR-D4+D5+D5b ancora non chiuso). Meglio: rollback prog 17
    a `esplorativo` (già fatto da NINO, OK), riapertura del piano
    Plan-D nello sprint successivo con SEVERO sul piano rivisitato
    (3a iterazione, dopo voti 6/10 e 7/10), con esplicitazione
    forte del modello multi-sede.
- **Costo del fix**: (a) 4-6h, (b) 2-3 settimane, (c) 0h immediato +
  riapertura sprint 8.3.

### S4 — MED — `_materiale_da_regola` ritorna sempre il primo elemento di composizione_json: limitazione amplificata dal fix

- **Severità**: MED
- **Dove**: `backend/src/colazione/domain/builder_giro/builder.py:813-828`
  (helper) + `:1357` (uso post-MR-D5e)
- **Cosa**: per regole con composizione mista (es.
  `[ETR526×1, ETR425×1]`), `_materiale_da_regola` ritorna SOLO
  ETR526. La limitazione è documentata in docstring "regole con
  composizione di 1+ pezzi dello STESSO materiale". MA il fix
  MR-D5e ora rende **sempre** il `MaterialeThread.tipo_materiale_codice`
  derivato da `materiale_per_regola[regola_id]` — prima, via
  `materiale_per_segmento[segmento_codice]`, c'era almeno la
  possibilità teorica di una mappatura più fine se segmenti
  rappresentassero varianti material-specific.
- **Perché è un problema**: nel codice prog 17 produzione le
  regole monomateriali sono OK, ma per regole future (e per
  programmi diversi che abbiano regole multimateriale) il fix
  introduce una "regressione di optionality": prima il sistema
  poteva (con un mapping segmento più fine) produrre composizioni
  diversificate per giro; ora il giro è marchiato monomateriale al
  primo elemento per costruzione.
- **Fix proposto**: nel medio termine `_materiale_da_regola` va
  rifattorizzato per restituire una lista di materiali ammessi (o
  un `ComposizioneItem` strutturato), e `materiale_per_regola`
  diventa `dict[int, tuple[str, ...]]` con il primo come "primario".
  Lo `MaterialeThread.tipo_materiale_codice` resta il primario
  (vincolo NOT NULL FK), ma il fix adapter espone gli altri come
  metadata composizione.
- **Costo del fix**: 4-8h, scope MR-D7 o successivo (legato al
  refactor segmenti `_tronco_X` già pianificato MR-D7).

### S5 — MED — Falla sistemica nel processo SEVERO post-MR strangler: 4 voti 7+ ma e2e fallimento al primo run reale

- **Severità**: MED (di processo, non di codice)
- **Dove**: critiche `PLAN-D-riscrittura-linea-centrica.md` (7/10),
  `SPRINT-8.2-MR-D0-D3-codice-committato.md` (8.5/10),
  `SPRINT-8.2-MR-D4-D5-D5b-codice-committato.md` (9.0/10), e
  questo MR-D5e
- **Cosa**: 4 voti SEVERO consecutivi tutti ≥7/10, tutti su codice
  green pure-domain con mock, **mai** un voto fondato su run e2e
  reale. Il primo retry e2e (post-MR-D5e) ha smascherato il 2° bug
  single-sede. La raccomandazione MED 9.0/10 ("pipeline solo
  mock-tested, mitigare PRIMA di MR-D7 con run su 2-3 linee
  reali") è stata **ignorata** da NINO che ha proceduto direttamente
  con MR-D5e+e2e completo prog 17 (52 linee). Il MED è risultato
  giusto.
- **Perché è un problema**:
  - **Conferma la raccomandazione MED**: era prevedibile. Non
    l'avresti dovuta marcare come "MED non bloccante" se sapevi
    che l'integration testing era assente — andava marcata HIGH
    BLOCKING in MR-D5b (= primo cambio strangler in builder.py).
  - **SEVERO ha mancato il single-sede al MR-D5b**: builder.py:
    1252-1254 era già committato e visibile nel diff D5b
    (4a54023). La critica D4+D5+D5b 9.0/10 ha rilevato il
    "blocchi_assegnati=()" empty (HIGH-1), ma NON il
    `sedi_disponibili={1 sede only}` che era a 4 righe di distanza.
    Significa che il giudizio AMILCARE è stato superficiale sul
    cambio architetturale per concentrarsi su altri punti più
    visibili.
  - **Memoria utente "SEVERO sempre sui piani"**: applicata, ma
    incompleta — la critica sul piano ha approvato "HARD" senza
    chiedere "HARD assumendo cosa sull'input?".
- **Fix proposto** — raccomandazione di processo:
  - **R-PROC-1**: SEVERO obbligatorio sul **primo cambio
    architetturale strangler che tocca builder.py** con verifica
    e2e empirica su prog reale PRIMA di assegnare il voto. Se
    l'e2e non gira (solo mock), il voto massimo è 6/10 con flag
    "test integration BLOCKING".
  - **R-PROC-2**: ogni raccomandazione SEVERO che impone un
    constraint HARD deve esplicitare le **assunzioni
    sull'input/contesto** (= "questo HARD è corretto SE..."). La
    racc #2 originale doveva contenere "...assumendo che MR-D2
    riceva tutte le sedi attive del programma". Senza, l'utente o
    NINO può applicare il constraint in un contesto degenere.
  - **R-PROC-3**: una raccomandazione MED può diventare HIGH
    BLOCKING quando il MR successivo è "il primo che tocca codice
    già toccato dal MR mock-only". Cioè: "mock-only è MED se sei
    al MR-D4 (greenfield), diventa HIGH al MR-D5b (= primo cambio
    in produzione)".
- **Costo del fix**: 1h aggiornamento `.claude/agents/severo.md`
  + `docs/AUSILI-CODICE.md` con le 3 R-PROC.

### S6 — LOW — Codice zombie `materiale_per_giro` info-only

- **Severità**: LOW
- **Dove**: `backend/src/colazione/domain/builder_giro/builder.py:1335-1342`
- **Cosa**: il dict `materiale_per_giro` viene popolato per
  `result.turni` con cascata `materiale_per_segmento → materiale_per_regola
  → "MISTO"`, ma il commit message dichiara "questo dict è solo
  informativo e non finisce nel DB". Cercando nel codice, non viene
  letto altrove dopo la riga 1342. Né per logging, né per debug,
  né per metriche del `BuilderRun`.
- **Perché è un problema**: codice morto. Il commit message dice
  "non persiste in DB" ma non spiega "a cosa serve allora?". Se
  era pensato per future log/diagnostiche è OK lasciarlo, ma con
  un commento esplicito; altrimenti va rimosso.
- **Fix proposto**: rimuovere il loop `for turno in result.turni:
  materiale_per_giro[id(turno)] = ...`. Se serve per diagnostica
  futura, aggiungere un commento `# TODO MR-D7: usare per metrica
  per-turno` con motivazione.
- **Costo del fix**: <15 min.

---

## Debito tecnico segnalato

- **Residuo S1 (loss-of-data invisibile)**: NON giustificato
  oggettivamente. Fix scrivibile in <2h. → ❌ pigrizia §7 violata.
- **Residuo S2 (test ramo nuovo)**: NON giustificato oggettivamente.
  Fix scrivibile in <30 min. → ❌ pigrizia §7 violata, esattamente
  il tipo di residuo che CLAUDE.md vieta ("se la formula esatta è
  scrivibile in 1h, scrivila adesso").
- **Residuo S4 (composizioni multimateriali)**: ✅ legittimo —
  refactor segmenti `_tronco_X` mapping è scope MR-D7 dichiarato,
  con motivazione oggettiva (richiede gestione strutturata di
  `ComposizioneItem` cross-modulo).
- **Residuo S6 (zombie code)**: NON giustificato. Fix scrivibile
  in <15 min. → ❌ pigrizia §7 violata (residuo low ma evitabile
  sull'orlo del commit).
- **Residuo MED 9.0/10 ignorato**: ❌ pigrizia §7 violata
  retroattivamente. La raccomandazione "pipeline solo mock-tested,
  mitigare prima MR-D7" era esplicita, NINO ha proceduto comunque
  saltando lo smoke su 2-3 linee reali. È costato il retry e2e
  fallito.

---

## Aderenza al METODO-DI-LAVORO

1. **Diagnosi prima di azione**: ✅ entry TN-UPDATE 270 ha stack
   trace completo, ricostruzione causa-effetto a 5 step, file:riga.
   NINO ha diagnosticato bene PRIMA del fix.
2. **Numeri non ipotesi**: ✅ tutto numerato (52 vs 2450 corse, 26
   segmenti scartati, 51 giri esplorativo vs 0 linea_centrica, 43
   warning categorizzati).
3. **Un passo alla volta**: ⚠️ il fix MR-D5e è un solo passo
   (corretto), ma NINO ha proceduto con e2e completo prog 17
   (52 linee, 2450 corse) senza fare prima lo smoke parziale (2-3
   linee, 1 settimana) raccomandato dal MED. Mezzo punto.
4. **Ammettere l'errore**: ✅ entry 270 dichiara apertamente "2°
   bug architetturale preesistente", "Plan-D NON chiuso", senza
   colorature.
5. **Verifica prima del commit**: ❌ test sul ramo nuovo NON
   scritto (S2). Il "53 test pure-domain green" copre il vecchio
   codice, non il nuovo branch. Regola violata.
6. **Preservare non distruggere**: ✅ rollback prog 17 a
   `esplorativo` eseguito; 11 giri G-CRE-XXX preservati. I 51 giri
   FIO sono stati cancellati dal `force=True` (limite del modello
   cumulativo, non del fix), e NINO lo dichiara nel campo "Stato
   safety attuale" dell'entry.
7. **Costanza nel tempo**: N/A (single-task).

---

## Voto complessivo

**4 / 10 (provvisorio fallback)** — strutturale: il MR-D5e fix è
chirurgicamente OK ma 2 residui §7 violati (S1+S2) + il 2° bug
architetturale (S3) che invalida l'intero retry e2e Plan-D. La
falla di processo SEVERO (S5) è la goccia.

Scala (rif. severo.md):
- 4 = problemi strutturali, da rivedere

Voto provvisorio perché motore AMILCARE V4 Pro non operativo
(3 timeout in fila); fallback V4 Flash via `mcp__amilcare__code` con
output filtrato da NINO. Da rifare con AMILCARE V4 Pro operativo se
l'utente richiede revisione. Pattern entry 248: critica fallback ha
margine di errore in eccesso (= NINO può essere stato troppo
indulgente sul fix, troppo severo sul processo).

---

## Raccomandazione concreta — MR-D5f scope + revisione raccomandazione SEVERO #2 + processo

### Per il codice

**Decisione utente richiesta** fra 3 strade S3 — analisi sopra.
Mia raccomandazione: **(c) immediato + (a) MR-D5f sprint 8.3**.

Se l'utente sceglie procedere subito con (a) MR-D5f:

1. **MR-D5f**: caricare TUTTE le sedi attive del programma in
   `sedi_disponibili` (filtra per `LocalitaManutenzione` con
   almeno 1 `ProgrammaRegolaAssegnazione` per il programma
   corrente). Persistenza resta scoping per `localita.codice` del
   run. Test integration con prog 17 (sede FIO) deve produrre
   ≥40 giri (vs 0 attuale).
2. **MR-D5g**: gestire `regola_id=None` nei giri prodotti da
   `costruisci_turno_linea`. Indagare se è caso degenerato
   legittimo (= warn + skip) o bug strutturale (= fix monte). Test
   coverage del ramo (chiude S2).
3. **MR-D5h** (opzionale, può essere combinato): chiude S1 (response
   `n_giri_scartati` esposto), S6 (rimuovi `materiale_per_giro`
   zombie).

**Sequenza MR rispetta principio §7 NIENTE PIGRIZIA**:
MR-D5f+g+h vanno in cascata stretta (3-4 giorni totali), non
spalmati su sprint diversi. Lo smoke parziale 2-3 linee reali
(MED 9.0/10) va eseguito DOPO MR-D5f e PRIMA di MR-D6, come da
raccomandazione originale.

### Per la raccomandazione SEVERO #2 originale

**Revisione obbligatoria**: la raccomandazione "no ciclo aperto
fuori area Milano come HARD constraint" va riscritta nel piano
Plan-D come:

> "HARD assumendo che MR-D2 riceva il pool COMPLETO delle sedi
> attive del programma. Se l'input è degenere a una sola sede, il
> constraint diventa SOFT con proxy 'rientro sede via vuoto
> serale' per i segmenti con capolinee fuori area sede ma con
> almeno 1 corsa passante per la whitelist sede."

Questa revisione va riflessa anche in `assegna_convogli_linea.py`
con un parametro `params.modalita_single_sede: bool`: se True, il
vincolo HARD #1 viene rilassato come sopra.

### Per il processo SEVERO

3 raccomandazioni di processo da aggiungere a `.claude/agents/severo.md`:

- **R-PROC-1**: SEVERO obbligatorio sul primo cambio architetturale
  strangler che tocca un file di produzione (es. builder.py) richiede
  **verifica e2e empirica su prog reale** prima del voto. Se solo
  mock, voto MAX 6/10 con flag "test integration BLOCKING".
- **R-PROC-2**: ogni raccomandazione SEVERO che impone un constraint
  HARD deve esplicitare le **assunzioni sull'input/contesto**
  (formato: "HARD assumendo X. Se non X, il constraint va
  rilassato a Y").
- **R-PROC-3**: una raccomandazione MED non bloccante diventa
  HIGH BLOCKING quando il MR successivo tocca codice già toccato
  dal MR mock-only. Caso concreto: "mock-only è MED al MR-D4
  greenfield, diventa HIGH al MR-D5b primo cambio in produzione".

---

## Cosa NON ho controllato

- **Run test pytest completo locale** sul fix MR-D5e: ho verificato
  solo che il file di test sul ramo `regola_id=None→scarto` NON
  esiste (`grep` in `backend/tests/`), confermando S2. Non ho
  rieseguito i 53 test green dichiarati nel commit.
- **Build/deploy Railway post-fix**: l'utente dichiara "✅ railway up
  --service backend" + "startup confermato post-call API HTTP 200"
  in entry 270; non ho verificato i log Railway nativamente.
- **Profiling MR-D2 con N>1 sedi reali**: non ho stimato la
  complessità computazionale di `assegna_convogli_segmenti` con il
  pool completo (potrebbe essere O(s × m × c) dove s=sedi, m=
  segmenti, c=candidati — accettabile per Trenord 6-7 sedi e 30
  segmenti, ma da verificare in MR-D5f).
- **Critica AMILCARE V4 Pro**: 3 timeout su `mcp__amilcare__reason`
  + 1 timeout su `mcp__amilcare__code` con brief 3.5KB. Output
  finale ottenuto solo con brief 1KB su V4 Flash via `code`. La
  qualità del giudizio AMILCARE qui è inferiore a quella delle
  critiche precedenti dove V4 Pro ha risposto. Voto provvisorio
  fallback.
- **Decisione utente fra strade (a)/(b)/(c)**: lasciata aperta in
  TN-UPDATE 270; questa critica fornisce raccomandazione (c+a) ma
  la decisione finale resta dell'utente + NINO.

---

## Tracciabilità

- Brief AMILCARE V4 Pro tentato 3× con `mcp__amilcare__reason`
  (3.5KB, 2.5KB, 1KB → tutti timeout `-32001`). Brief V4 Flash via
  `mcp__amilcare__code` 1KB → output ricevuto in pochi secondi
  (~500 parole, 4 finding). Output filtrato da NINO: rimosso falso
  positivo "`_materiale_da_regola[0]` IndexError" (è una funzione,
  builder.py:813-828, gestisce composizione vuota con `if not mat:
  continue` a riga 1273).
- Pattern entry 248 applicato: voto provvisorio fallback + dichiarazione
  motore + nota di rifare con AMILCARE V4 Pro operativo.
- Critiche precedenti rilevanti citate:
  `docs/critiche/PLAN-D-riscrittura-linea-centrica.md` (7/10
  raccomandazioni #1+#2), `docs/critiche/SPRINT-8.2-MR-D4-D5-D5b-
  codice-committato.md` (9.0/10 MED ignorato).
