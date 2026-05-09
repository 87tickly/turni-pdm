# Critica SEVERO — MR-D5f trio (MR-D5f + MR-D5f-bis + MR-D5f-tris)

**Data**: 2026-05-09
**Commit / range**: `f6b7992` (MR-D5f, +340/-65 in 5 file) + `1105a0b`
(MR-D5f-bis, +67/-0 in 2 file) + `d4200bd` (MR-D5f-tris, +36/-6 in 1
file). Diff cumulativo trio: 575 insertions / 65 deletions, 5 file.
**Entry TN-UPDATE**: 275 (e 270 per contesto critica precedente)
**Motore usato**: ❌ AMILCARE V4 Pro NON disponibile in sessione
corrente: 3 timeout `-32001` su `mcp__amilcare__reason` (brief 6KB,
3.5KB, 1.5KB) + 1 timeout su `mcp__amilcare__code` (brief 1KB) →
pattern entry 248 confermato 4× consecutive in stessa sessione.
**Fallback**: critica NINO puro dichiarata, voto provvisorio con
asterisco. NINO ha appena committato il codice che critica → bias di
auto-compiacenza inevitabile. Da rifare con AMILCARE V4 Pro operativo
(margine ~2 punti: il pattern entry 248 mostra che fallback NINO è
~2 punti più indulgente di AMILCARE V4 Pro).

---

## Sintesi (3 righe)

Il trio MR-D5f chiude correttamente i 6 finding della critica
precedente 4/10 e fa funzionare la pipeline linea-centrica
(2450→1302 corse processate, +25× rispetto a single-sede), ma **il
KO operativo per il pianificatore Trenord prog 17 non è chiuso**
(0 giri persistiti su 11 prodotti, sede [CRE,LEC] vs sede regola
FIO). La sequenza f→f-bis→f-tris è 1 commit utile, 1 commit cieco
(D5f-bis non sblocca nulla), 1 commit decisivo (D5f-tris):
diagnosi DB-first prima di scrivere f-bis avrebbe risparmiato un
ciclo retry-deploy. **Voto provvisorio fallback: 5/10\*** —
strutturale: chiude il debito ma non chiude l'obiettivo, e
introduce una nuova superficie senza test che pagherà domani.

---

## Cosa funziona

- **MR-D5f S1+S2+S6 chiusura tutta**: `n_giri_scartati` esposto in
  `BuilderResult` + `BuilderResultResponse` con descrizione
  esplicita e default a 0 per backward-compat (chiude S1 HIGH).
  Funzione pura `_traduce_e_filtra_giri_linea_centrica` con 6 test
  parametrici copre il ramo regola_id=None (chiude S2 HIGH).
  Rimosso loop zombie `materiale_per_giro` (chiude S6 LOW). I 3
  finding sono stati chiusi con un fix ben fatto ognuno — niente
  half-job §7.
- **Helper `_carica_sedi_attive_azienda` ben strutturato**: filtro
  `is_attiva=True AND stazione_collegata_codice IS NOT NULL`
  difensivo, edge case "sede del run non nel pool" gestito con
  warning + fallback include forzato. Modalità degradata
  trasparente al pianificatore.
- **Onestà operativa nel commit message + entry 275**: NINO ha
  dichiarato apertamente "Plan-D bloccato sul 3° mismatch
  sede-regola", "0 giri persistiti", "decisione utente richiesta".
  Niente auto-compiacenza di "fix funziona" mentre il KO non è
  chiuso. È rispettata regola §4 ammettere l'errore.
- **Filtro persistenza `g.localita_codice == localita_codice_run`
  preserva modello cumulativo**: la decisione utente 2026-05-01
  (1 chiamata = 1 sede persistita) è rispettata letteralmente.
  Le sedi altre sono visibilizzate come warning specifici, non
  silenziate.
- **Test S2 ben fatti**: pattern parametrico (caso felice,
  regola_id=None, regola non in dict, altra sede, misti, vuoti) è
  idiomatico e replicabile. La factory `_giro(localita=, regola_id=)`
  rende i test leggibili.
- **mypy --strict + ruff clean** mantenuti su tutti e 3 i file
  modificati.

---

## Cosa si poteva fare meglio

### S1 — HIGH — Diagnosi DB-first non eseguita prima di scrivere MR-D5f-bis: 1 commit cieco evitabile

- **Severità**: HIGH (di processo, non di codice)
- **Dove**: sequenza commit `f6b7992` → `1105a0b` → `d4200bd`
  (cronologia retry 2 → retry 3 entry 275 tabella)
- **Cosa**: post-deploy MR-D5f, l'e2e prog 17 ritorna 1302 corse
  processate, 11 giri tutti con regola_id=None scartati. NINO
  ipotizza causa = "segmenti `_tronco_X` non in `regola_per_segmento`
  perché il chiamante mappa solo `_completo`, MR-D1 produce anche
  tronchi/isolati", scrive MR-D5f-bis (3 test, deploy). Retry post
  deploy: **identico** retry 2 (1302/0/11/114 warnings
  letteralmente uguali). Significa che il fallback `_tronco_X →
  _completo` non era mai invocato perché `regola_per_segmento`
  era **vuoto a monte** (nessun mapping linea→regola). Diagnosi
  DB-first prima di scrivere f-bis avrebbe rivelato:
  - SQL banale: `SELECT id, nome, filtri_json FROM
    programma_regola_assegnazione WHERE programma_id=17;`
  - Output atteso (visibile retroattivamente in commit message
    f-tris): "7 regole, tutte con
    `[{'campo':'direttrice','valore':[...]}]`, 0 con
    `codice_linea`".
  - Conclusione: `regola_per_segmento` è vuoto perché il loop
    estrae solo `campo='codice_linea'` mentre tutte le regole
    filtrano per `direttrice` → root cause vera in builder.py
    pre-MR-D5f-tris.
- **Perché è un problema**: viola regola §1 METODO ("Diagnosi prima
  di azione: estraggo dati reali (DB query) per vedere COSA sta
  succedendo, non cosa immagino sta succedendo"). NINO ha applicato
  un fix basato su un'ipotesi plausibile (i tronchi sono noti come
  superficie problematica da MR-D1) senza prima querying il DB
  reale. Il fix MR-D5f-bis è di per sé corretto come **rete di
  sicurezza difensiva** (è giusto che il fallback ci sia per
  programmi futuri con regole `codice_linea`-only e segmenti
  `_tronco_X`), ma in **questa pipeline reale prog 17 non è
  invocato**. È costato 1 ciclo deploy Railway (~5-10 min) +
  cognitive overhead di un commit ininfluente.
- **Fix proposto**: prima del prossimo cambio in builder
  linea-centrica, **diagnosi DB obbligatoria sui dati di prog 17
  reale**: SQL su `programma_regola_assegnazione`, su `corsa` per
  vedere quali campi popolati (direttrice/codice_linea/categoria/
  tipologia/etc), poi ipotesi e fix. Pattern entry 270 ricorda:
  "i dati DB sono stati ignorati al MR-D5b" — qui ricapita.
- **Costo del fix**: 0h retroattivo (commit fatto). Costo
  preventivo per il futuro: 10-20 min di SQL prima di ogni MR
  che tocca mapping. Trascurabile.

### S2 — HIGH — `_carica_sedi_attive_azienda` introdotto in produzione senza test unitario

- **Severità**: HIGH
- **Dove**: `backend/src/colazione/domain/builder_giro/builder.py:357-396`
  (definizione helper) — verificato `grep -r 'carica_sedi_attive_azienda'
  backend/tests/` ritorna 0 risultati.
- **Cosa**: il fix S3 della critica precedente (= 2° bug
  architetturale single-sede, finding HIGH) è risolto introducendo
  `_carica_sedi_attive_azienda(session, azienda_id) -> dict[str, str]`.
  La funzione è **caricata in produzione senza un singolo test
  unitario**. Branch coverage 0%: filter `is_attiva=True` non
  testato, filter `stazione_collegata_codice IS NOT NULL` non
  testato, build del dict non testato, edge case "0 sedi attive"
  non testato. La verifica è solo via integration e2e prog 17
  (che è il caso felice +25× corse).
- **Perché è un problema**: regola §5 METODO violata in modo
  identico a S2 della critica precedente. Il pattern è
  ricorrente: NINO chiude un finding di test mancante (S2 ramo
  regola_id=None) introducendo una funzione pura ben testata, MA
  nello stesso MR introduce **un'altra funzione pura non
  testata**. Il debito di test si sposta, non si chiude. Inoltre
  regola §7 NIENTE PIGRIZIA è violata: scrivere 4-5 test parametrici
  su un helper così piccolo con dipendenza solo da
  `LocalitaManutenzione` ORM model è <30 min con `AsyncSession`
  in-memory o mock. Esiste già un pattern di test su
  `_carica_localita` ma non è stato replicato qui.
- **Fix proposto**: aggiungere `test_carica_sedi_attive_azienda_*`
  (4-5 test): (a) caso felice 3 sedi attive con stazione
  collegata, (b) sede inattiva esclusa, (c) sede senza
  stazione_collegata esclusa, (d) azienda con 0 sedi → dict vuoto,
  (e) azienda mismatch (sedi di altra azienda non incluse). Usare
  `db_session` fixture esistente.
- **Costo del fix**: <45 min. Da fare PRIMA del prossimo MR-D5*
  che tocchi questa pipeline.

### S3 — HIGH — `direttrice_to_linee` MR-D5f-tris zero test sul mapping

- **Severità**: HIGH
- **Dove**: `backend/src/colazione/domain/builder_giro/builder.py:1438-1473`
  (pre-calcolo + espansione filtro) — verificato `grep -rn
  'direttrice_to_linee' backend/tests/` ritorna 0 risultati.
- **Cosa**: il fix MR-D5f-tris (root cause finale, "espande filtri
  direttrice → linee") aggiunge 35 righe di logica nuova in builder.py:
  pre-calcolo mappa, gestione `campo='codice_linea'` + `campo='direttrice'`,
  estrazione lista vs stringa, dedup via set. È la modifica con
  **maggiore impatto operativo** del trio (sblocca da 0 corse a
  1302 con regola_id valida) eppure non ha **un singolo test**.
  Il commit message dichiara "42 test linea-centrica green" ma
  questi sono test pre-esistenti su altri moduli; non c'è test
  specifico per questa logica.
- **Perché è un problema**:
  - **Regola §5 METODO violata**: il fix è in produzione ma non
    è coperto da test. Se domani NINO o un altro contributor
    rinomina `direttrice` in `direzione` (refactor naming) o
    cambia il formato `valore` (lista vs string), il fix si rompe
    silenziosamente in produzione e il pianificatore vede regredire
    a 0 giri (= condizione pre-fix che ha causato il KO).
  - **Regola §7 NIENTE PIGRIZIA violata**: scrivere 4-6 test
    parametrici puri su questa logica è triviale. Si costruisce
    un `Programma` finto + `regole` finte + `corse` finte, si
    chiama la sezione di estrazione (che però è inline al chiamante
    `_genera_giri_linea_centrica` — vedi S4 sotto), si verifica
    `materiale_per_segmento` e `regola_per_segmento` popolati
    correttamente. <1h se la logica fosse estratta in helper.
  - **Pattern ricorrente che sintetizza tutto il trio**: ogni
    helper introdotto è messo in produzione senza test (Sprint 8.2
    pattern: D5e ramo nuovo no test, D5f `_carica_sedi_attive_azienda`
    no test, D5f-tris `direttrice_to_linee` no test). I test ci
    sono solo sulla **ultima** estrazione (`_traduce_e_filtra`).
- **Fix proposto**: estrarre la logica in helper puro
  `_costruisci_mappature_regole_linee(corse, regole) -> tuple[
  dict[str, str], dict[str, int]]` che ritorna
  `(materiale_per_segmento, regola_per_segmento)`, e scrivere 4-6
  test su questa funzione: (a) regola con filtro `codice_linea`
  list, (b) filtro `codice_linea` string, (c) filtro `direttrice`
  con espansione, (d) regola misto (entrambi i campi), (e) regola
  con filtro non riconosciuto (`categoria`/`tipologia` → segment
  vuoto, vedi S5 sotto), (f) corsa senza direttrice/codice_linea
  (skip). Pattern di test pure-domain identico ai 6 test S2 di
  MR-D5f.
- **Costo del fix**: 1.5-2h. Da fare PRIMA di MR-D5h/D6.

### S4 — MED — Logica MR-D5f-tris inline al chiamante invece che helper estratto

- **Severità**: MED
- **Dove**: `backend/src/colazione/domain/builder_giro/builder.py:1429-1477`
  (35 righe inline a `_genera_giri_linea_centrica`)
- **Cosa**: la logica `direttrice_to_linee` + loop estrazione filtri
  è scritta **inline** al chiamante async che ha già ~200 righe.
  Pattern incoerente: nello stesso commit MR-D5f, NINO ha
  correttamente estratto `_traduce_e_filtra_giri_linea_centrica`
  in funzione pura testabile (chiudendo S2 critica precedente);
  qui non lo fa.
- **Perché è un problema**:
  - **Inconsistenza interna del MR**: la stessa motivazione che
    giustifica l'estrazione `_traduce_e_filtra` (testabilità del
    ramo nuovo) si applica identicamente a `direttrice_to_linee`.
    NINO sceglie due strategie diverse per due fix dello stesso MR.
    Indica fretta ("ho già fatto l'estrazione difficile, questa
    butto inline").
  - **Sinergia negativa con S3**: senza estrazione, scrivere i
    test richiesti da S3 è più costoso (devi mockare tutta la
    chiamata a `_genera_giri_linea_centrica` con session DB) e
    NINO non lo fa.
- **Fix proposto**: insieme a S3, estrarre la logica in helper
  puro `_costruisci_mappature_regole_linee`. Allinea il pattern
  con `_traduce_e_filtra_giri_linea_centrica`. Funzione testabile
  in pure-domain.
- **Costo del fix**: 1-1.5h (stesso costo di S3).

### S5 — MED — Logica espansione filtri non chiude completamente il caso `categoria`/`tipologia`-only

- **Severità**: MED
- **Dove**: `backend/src/colazione/domain/builder_giro/builder.py:1455-1473`
  (loop `for f in r.filtri_json or []:`)
- **Cosa**: il loop estrae linee SOLO da `campo='codice_linea'` e
  `campo='direttrice'`. Se in futuro una regola ha `filtri_json`
  con SOLO `[{'campo':'categoria','valore':'R'}]` (tutti i regionali)
  o `[{'campo':'tipologia','valore':'METROPOLITANA'}]` senza
  `direttrice`/`codice_linea`, la regola sarà ignorata: `linee_regola`
  resta vuoto → nessun mapping segmento → giri orfani regola_id=None
  → scartati. Il commit message MR-D5f-tris dichiara questa limitazione
  esplicitamente ("regola 53 usa anche `categoria=R` ma il filtro è
  AND, quindi `direttrice` da sola basta per matchare i suoi
  segmenti. Se in futuro c'è una regola che filtra ESCLUSIVAMENTE
  per `categoria`/`tipologia` senza `direttrice`, il mapping
  resterà vuoto → log `n_giri_scartati` trasparente").
- **Perché è un problema**: tecnicamente è giusto dichiarare il
  residuo, MA viola §7 NIENTE PIGRIZIA test: la logica generica
  che funziona per QUALSIASI tipo di filtro esisterebbe già nel
  resolver/builder esplorativo legacy (filtra le corse per regola,
  estrae i loro `codice_linea`, costruisce `regola_per_segmento`
  per intersection corsa→regola). Il MR-D5f-tris ha scelto
  l'approccio per-filtro (matching sui campi del filtro) invece
  di per-corsa (matching sull'output del resolver). Per-corsa
  sarebbe robusto a qualsiasi filtro futuro:
  ```
  for corsa in corse:
      regola = resolver.applica(corsa)  # logica già in builder esplorativo
      if regola:
          mat = _materiale_da_regola(regola)
          if mat:
              materiale_per_segmento[f"{corsa.codice_linea}_completo"] = mat
              regola_per_segmento[f"{corsa.codice_linea}_completo"] = regola.id
  ```
- **Fix proposto**: refactor MR-D5f-quater (o scope MR-D5g): usare
  il resolver per costruire `materiale_per_segmento`/`regola_per_segmento`
  invece di parsing manuale dei filtri. Vantaggi: (a) supporta
  qualsiasi filtro futuro, (b) coerente con resolver esplorativo,
  (c) elimina il bug latente. Svantaggi: richiede di passare la
  resolver alla pipeline linea-centrica (= aggancio a logica
  legacy).
- **Costo del fix**: 3-4h, scope MR-D5g/h.

### S6 — MED PROCESSO — R-PROC-1 della critica precedente NON aggiunta a `.claude/agents/severo.md` né a `docs/AUSILI-CODICE.md`

- **Severità**: MED PROCESSO
- **Dove**: `.claude/agents/severo.md` (verificato: 0 occorrenze
  "R-PROC"), `docs/AUSILI-CODICE.md` (verificato: 0 occorrenze
  "R-PROC")
- **Cosa**: la critica precedente entry 270 ha raccomandato 3
  R-PROC con dettaglio (R-PROC-1 e2e empirico al 1° strangler,
  R-PROC-2 esplicitazione assunzioni HARD, R-PROC-3 escalation
  MED→HIGH al 1° MR su codice mock-only). Costo del fix dichiarato
  "1h aggiornamento `.claude/agents/severo.md` + `docs/AUSILI-CODICE.md`".
  Verifica grep: NESSUNA delle 3 R-PROC è stata aggiunta. Il trio
  MR-D5f trae direttamente l'esperienza dal mancato R-PROC-1
  (deploy MR-D5f senza smoke 2-3 linee → 5 retry post-deploy):
  l'esperienza è in TN-UPDATE 275 ma non è codificata.
- **Perché è un problema**:
  - **Regola §7 NIENTE PIGRIZIA violata retroattivamente**: il
    finding S5 della critica precedente era "MED PROCESSO" con
    fix dichiarato 1h. NINO ha proceduto con 3 commit di codice
    senza chiudere il fix di processo che era proprio la lezione
    appresa. Test del residuo: <2h scrivibile, scrivilo subito.
  - **Falla sistemica documentata empiricamente**: post-MR-D5f
    sono serviti 3 retry (D5f-bis identico a D5f, D5f-tris vero
    fix). Se la R-PROC-1 fosse stata operativa (smoke 2-3 linee
    pre-deploy MR-D5f richiede di selezionare 2-3 linee reali e
    girare la pipeline su un sottoinsieme), il pianificatore
    avrebbe visto pre-deploy che `regola_per_segmento` è vuoto e
    avrebbe diagnosticato il problema direttrice → linee al
    Day-1, prima del primo deploy MR-D5f. Avrebbe risparmiato 2
    cicli deploy Railway + cognitive overhead.
  - **Pattern ricorrente entro Sprint 8.2**: MR-D5b voto 9.0/10
    aveva MED 'pipeline mock-only', MR-D5e ha avuto KO al primo
    e2e (entry 270 voto 4/10), MR-D5f trio ha 5 retry. Tre eventi
    successivi sulla stessa lezione, mai codificata.
- **Fix proposto**: aggiungere a `.claude/agents/severo.md` una
  nuova sezione "## R-PROC — raccomandazioni di processo persistenti"
  con le 3 R-PROC (testo già scritto in entry 270/critica
  precedente). Aggiornare anche `docs/AUSILI-CODICE.md` §10 trigger
  linguistici con riferimento.
- **Costo del fix**: 1h (lo stesso del finding precedente, mai
  speso). Da fare PRIMA del prossimo MR-D5h/D6.

### S7 — LOW — Edge case "sede del run non nel pool" silenzioso a livello operativo

- **Severità**: LOW
- **Dove**: `backend/src/colazione/domain/builder_giro/builder.py:1405-1413`
  (`if localita.codice not in sedi_disponibili: ... warnings.append(...)`)
- **Cosa**: NINO ha gestito difensivamente il caso "sede del run
  non risulta attiva nel pool azienda" (= forse `is_attiva=False`
  o senza stazione collegata) con un warning + forzatura
  inclusione. Il warning è informativo ma il pianificatore può
  non vederlo nel mare di altri 100+ warning.
- **Perché è un problema**: minore. Il caso è gestito ma non
  esposto in un campo response distinto. Se il pianificatore
  prog X ha sede del run senza `stazione_collegata_codice` o
  `is_attiva=False`, si ritrova in modalità degradata single-sede
  identica al pre-MR-D5f con i suoi rischi (98% perdita corse) e
  vede solo il warning testuale. Tracciabilità debole.
- **Fix proposto**: aggiungere campo `BuilderResultResponse.modalita_sede:
  Literal['multi_sede', 'degradata_single_sede']` per esplicitare lo
  stato operativo. Frontend può mostrare badge "modalità degradata"
  al posto del solo conteggio warning.
- **Costo del fix**: <30 min, scope MR-D5h o nice-to-have MR-D7.

---

## Risposta puntuale alle 5 domande del brief

### 1. Sui 3 commit del ciclo

**MR-D5f-tris chirurgicamente corretto**: ✅ in larga parte sì.
L'espansione `direttrice → linee` è la cosa giusta da fare per
sbloccare prog 17. Il pre-calcolo lineare via `direttrice_to_linee`
è efficiente. La backward-compat per `codice_linea` è preservata.
Set invece di list per dedup è giusto. ⚠️ Limite: la logica resta
inline (S4) e senza test (S3), e non chiude il caso
`categoria`/`tipologia`-only (S5).

**Sequenza f→f-bis→f-tris**: **falla del processo**, non
iterazione naturale. La diagnosi DB-first prima di scrivere f-bis
avrebbe rivelato che `regola_per_segmento` era vuoto a monte (root
cause MR-D5f-tris). NINO ha applicato il pattern "ho un'ipotesi
plausibile, scrivo il fix, deploy, vedo se funziona" tre volte: la
prima (D5f) era giusta in parallelo (multi-sede), la seconda (D5f-bis)
è stata cieca (fallback non invocato), la terza (D5f-tris) è stata
quella vera. Il D5f-bis di per sé non è un fix sbagliato (è una
rete di sicurezza utile per programmi futuri), ma è stato motivato
da una diagnosi non verificata sul caso reale prog 17 e ha
consumato un ciclo deploy. Vedi S1.

**Mancano test**: ✅ sì, due nuovi helper introdotti senza test
(S2 `_carica_sedi_attive_azienda` HIGH, S3 `direttrice_to_linee`
HIGH).

**Split f/f-bis/f-tris vs bundle in 1 MR**: lo split è
**giustificato come iterazione di scoperta diagnostica**: ogni
commit chiude una causa diversa scoperta in retry successivo.
Bundle in 1 MR avrebbe richiesto di aspettare di scoprire la
root cause vera prima di committare nulla, ma quella scoperta è
arrivata al 4° retry (post deploy D5f-bis). Lo split atomico
permette in teoria di rollback granulare (= se domani scopriamo
che `_carica_sedi_attive_azienda` introduce regressione, posso
rollback solo MR-D5f). **Tuttavia**, dato che MR-D5f-bis non era
necessario per prog 17, sarebbe stato più pulito **diagnosticare
DB-first** e committare 1 MR-D5f bundle (multi-sede + direttrice→
linee insieme + helper testati), tenendo MR-D5f-bis come "rete di
sicurezza opzionale" da aggiungere DOPO con motivazione
"programmi futuri con regole `codice_linea`-only e segmenti tronco".

### 2. Sulla R-PROC-1 (smoke 2-3 linee pre-deploy 1° strangler)

**Confermata 100%**, e va aggiunta tassativamente a
`.claude/agents/severo.md` + `docs/AUSILI-CODICE.md`. Lezione
empirica: se R-PROC-1 fosse stata operativa, il deploy MR-D5f
sarebbe stato preceduto da uno smoke su 2-3 linee selezionate (es.
una linea con direttrice TIRANO, una con CARNATE, una breve test).
Lo smoke avrebbe rivelato pre-deploy:
- `n_corse_processate=1302` (multi-sede ✅)
- `n_giri_creati=0` (regola_id=None tutti)
- `regola_per_segmento` vuoto (debug log)

→ NINO avrebbe diagnosticato il problema direttrice → linee al
Day-1, prima di MR-D5f-bis e MR-D5f-tris. Avrebbe consolidato in
1 MR-D5f con tutti i fix necessari. **5 retry → 1 retry**. Ho
classificato il finding S6 come MED PROCESSO con costo 1h e
rinvio MAX al prossimo MR. R-PROC-1 + R-PROC-2 + R-PROC-3 vanno
scritte in `.claude/agents/severo.md` SENZA passare allo Sprint
successivo.

### 3. Sul 3° mismatch sede-regola

**Strada consigliata**: **(c) Configurazione utente**, integrata
con un fix codice di chiarezza UI. Motivazione:

- **(a) Override sede-regola in MR-D2 = rilassa la racc SEVERO #2
  originale**: pessima idea operativamente. La racc #2 ("HARD no
  ciclo aperto fuori area Milano") è geometricamente fondamentale
  per il dominio: un convoglio non può tornare in deposito FIO
  partendo da Tirano la sera tardi. La pipeline MR-D2 ottimizza
  geometricamente per buona ragione. Rilassare = produrre giri
  letteralmente impossibili da eseguire (= il convoglio non torna a
  deposito → giro aperto in stazione fuori sede). Il prog 17
  pianificatore avrebbe giri persistiti, ma non operabili.
- **(b) Modello cumulativo multi-sede**: breaking change della
  decisione utente 2026-05-01. Non è un fix di bug ma riapertura
  di una decisione architetturale. Va fatto solo se arrivasse una
  nuova decisione utente di superare il modello cumulativo. **Non
  raccomandato come prima mossa**.
- **(c) Configurazione utente**: il pianificatore prog 17 deve
  riassegnare le 7 regole con `localita_codice` coerente con la
  geometria del segmento (es. regola Tirano-Milano con sede LEC
  invece di FIO). Questa è l'azione corretta nel modello dato:
  la regola dichiara "questi treni sono guidati da convogli della
  sede X" — se il segmento finisce a Tirano, la sede operativa
  ottimale è LEC (Lecco). Non è un mismatch architetturale, è una
  **configurazione di dato sbagliata** del pianificatore prog 17
  che usava FIO come default per tutto perché legacy esplorativo
  non rilevava il problema. Cambiare la sede regola = aggiornamento
  configurazione. Costo: 0h codice + 30 min pianificatore via UI
  (assumendo UI esiste).

**Fix codice complementare a (c)**: aggiungere validazione
pre-build che mostri al pianificatore "regola con sede X ha treni
che finiscono in stazioni Y dove la sede ottimale geometrica è Z;
considera di riassegnare". Warning informativo, non bloccante. È
1-2h di fix UI + endpoint diagnostica.

**Era un terzo errore retroattivo della racc #2 originale?** **Sì,
parzialmente**. La racc #2 era corretta in astratto (HARD
geometrico = fondamentale) ma incompleta su un punto: non ha
predetto la collisione col modello cumulativo `regola.localita_codice`
quando il pianificatore configura le regole con sede FIO mentre i
segmenti commerciali finiscono altrove. SEVERO precedente avrebbe
dovuto raccomandare in MR-D2 design: "MR-D2 SHALL emettere warning
se la sede geometricamente ottima diverge da `regola.localita_codice`".
Con il senno di poi, è una raccomandazione 4 (non 2): "validazione
allineamento sede-regola vs sede-geometrica con avviso al
pianificatore". Lo aggiungo come finding implicito a questa critica.

### 4. Sui 3 retry consecutivi pre-deploy con stessi numeri

**3 retry post-deploy non pre-deploy**: la cronologia entry 275
mostra che ogni commit è stato deployato e l'e2e è stato eseguito
DOPO il deploy. I retry sono stati: deploy MR-D5f → e2e mostra
1302/0/11 → ipotesi tronchi → scrivi MR-D5f-bis → deploy → e2e
mostra **identico** 1302/0/11 → diagnosi vera (DB-first finalmente)
→ scrivi MR-D5f-tris → deploy → e2e 1302/0/11 [CRE,LEC] sblocco
parziale.

**Indica che il polling deploy era inaccurato?** No, il deploy è
stato verificato HTTP 200 ogni volta. Il problema è che NINO ha
**ripetuto la stessa chiamata e2e** dopo MR-D5f-bis senza prima
verificare con SQL/log se il fallback era effettivamente invocato.
Se l'e2e ha mostrato `n_giri_scartati=11` identico, era un segnale
forte che il fix non aveva sbloccato nulla. La diagnosi di "perché
è identico" doveva essere fatta PRIMA di considerare MR-D5f-tris.

**Era inevitabile diagnosi-fix-retest in produzione?** No. Era
"diagnosticabile a tavolino" via:
- SQL su `programma_regola_assegnazione` per vedere i `filtri_json`
  reali (12 secondi).
- Verifica `regola_per_segmento` populated dopo MR-D5f deploy via
  log temporaneo o breakpoint local (5 min se l'env locale gira).
- Domanda secca: "perché regola_id=None? il `regola_per_segmento`
  ha mappature?" prima di assumere "tronchi".

**3 retry sono spreco di processo**, attribuibili a S1+S6 (manca
diagnosi DB-first + R-PROC-1 non operativa).

### 5. Voto finale

**5/10\* (provvisorio fallback)** — strutturale.

Scala (rif. severo.md):
- 5-6: funziona ma con debito o blind spot non secondari

Motivazione:
- ✅ +2 punti vs critica precedente 4/10: i 6 finding chiusi
  (S1+S2+S6 chiusi tutti, S3 chiuso con multi-sede, S4 dichiarato
  scope MR-D7, S5 PROCESSO parzialmente chiuso ma R-PROC-1 ancora
  aperta).
- ✅ Multi-sede sblocca 25× corse processate (52→1302).
- ✅ Trasparenza n_giri_scartati con sede esplicita.
- ✅ Pattern di test S2 ben fatto, riproducibile.
- ❌ -2 punti: 2 nuovi helper introdotti senza test (S2+S3 in
  questa critica, HIGH), pattern ricorrente di test debt che si
  sposta non si chiude.
- ❌ -1 punto: MR-D5f-bis cieco evitabile con DB-first (S1
  HIGH), 1 ciclo deploy sprecato.
- ❌ -1 punto: R-PROC-1 della critica precedente NON aggiunta
  (S6 MED PROCESSO), debito di processo cumulativo.
- ❌ KO operativo NON chiuso: 0 giri persistiti per pianificatore
  prog 17 in linea_centrica. La modalità è ancora opt-in
  sperimentale, non ha sostituito esplorativo. Da una prospettiva
  di "il sistema in produzione fa quello che deve" (= il
  pianificatore Trenord vede giri creati), Plan-D è ancora
  bloccato. Il voto deve riflettere questa realtà.

**Voto provvisorio fallback** perché AMILCARE V4 Pro non
operativo (4 timeout consecutivi). Pattern entry 248 indica
fallback NINO è ~2 punti più indulgente di V4 Pro: voto effettivo
con AMILCARE potrebbe essere **3/10**. Da rifare se l'utente
richiede revisione con AMILCARE V4 Pro operativo.

---

## Debito tecnico segnalato

- **Residuo S1 (DB-first non eseguito retroattivo)**: ✅ legittimo
  da imparare per il futuro, non è "pigrizia §7" ma "regola §1
  non applicata in pieno". Riapertura via R-PROC.
- **Residuo S2 (`_carica_sedi_attive_azienda` no test)**: ❌
  pigrizia §7 violata. Fix scrivibile in <45 min.
- **Residuo S3 (`direttrice_to_linee` no test)**: ❌ pigrizia §7
  violata. Fix scrivibile in 1.5-2h.
- **Residuo S4 (logica inline)**: ❌ pigrizia §7 violata,
  inconsistente col pattern S2 di MR-D5f. Costo combinato con S3
  ~2h totali.
- **Residuo S5 (categoria/tipologia-only)**: ✅ legittimo come
  scope MR-D5g/h dichiarato in commit message MR-D5f-tris.
- **Residuo S6 (R-PROC mai aggiunte)**: ❌ pigrizia §7 violata
  retroattivamente, costo 1h dichiarato critica precedente, mai
  speso.
- **Residuo S7 (modalità degradata silente)**: ✅ legittimo
  come nice-to-have MR-D5h.

---

## Aderenza al METODO-DI-LAVORO

1. **Diagnosi prima di azione**: ⚠️ MR-D5f-bis NON ha rispettato
   questa regola (vedi S1). MR-D5f sì. MR-D5f-tris sì
   (esplicitamente dichiarato nel commit message "Diagnosi finale
   post deploy MR-D5f+f-bis").
2. **Numeri non ipotesi**: ✅ entry 275 ha tabella retry numerata
   con numeri reali (corse_proc, giri_creati, scartati, warnings,
   tipo_warning_dominante). Eccellente.
3. **Un passo alla volta**: ✅ commit atomici, ognuno chiude un
   sotto-fix. Lo split f/f-bis/f-tris rispetta la regola, anche se
   con efficienza migliorabile (vedi S1).
4. **Ammettere l'errore**: ✅ entry 275 dichiara apertamente "Plan-D
   bloccato sul 3° mismatch sede-regola", "decisione utente
   richiesta su (a)/(b)/(c)". NINO non ha mascherato il KO
   operativo.
5. **Verifica prima del commit**: ⚠️ test pytest 197 green
   (caso felice + funzioni pure ben coperte) ma 2 nuovi helper
   introdotti senza test propri (S2+S3). Mezzo punto. Smoke 2-3
   linee reali pre-deploy non eseguito (R-PROC-1 non operativa).
6. **Preservare non distruggere**: ✅ filtro persistenza preserva
   modello cumulativo (decisione utente 2026-05-01). Backward-compat
   builder_mode `'esplorativo'/'rigido'` invariato.
7. **Costanza nel tempo**: ⚠️ R-PROC della critica precedente
   non aggiunte (S6). Lezione appresa ma non codificata.

---

## Cosa NON ho controllato

- **AMILCARE V4 Pro indipendente**: 4 timeout consecutivi in
  questa sessione (`reason` 3×, `code` 1×, brief 6KB→3.5KB→1.5KB→
  1KB). Pattern entry 248 confermato. Critica fallback NINO puro
  con bias di auto-compiacenza inevitabile (NINO ha appena
  committato il codice che critica). Il voto effettivo con
  AMILCARE V4 Pro è probabilmente 1-2 punti più severo.
- **SQL diagnostico DB prog 17 verificato post-fatto**: NINO ha
  dichiarato in commit message MR-D5f-tris i risultati ("7 regole
  tutte con `[{'campo':'direttrice','valore':[...]}]`, 0 con
  `codice_linea`, 62 codici_linea distinti nelle corse del periodo")
  ma non ho rieseguito le query localmente per verificare. Mi sono
  fidato della dichiarazione del commit message.
- **Run test pytest completo locale post-trio**: ho verificato
  via grep che i nuovi helper non hanno test, non ho eseguito
  pytest. La dichiarazione "197 test green" del commit message
  MR-D5f è presa per buona.
- **Build/deploy Railway post-trio**: l'utente dichiara "✅ HTTP
  200 confermato su tutte le rigenerazioni" + "deploy + redeploy
  forzato"; non ho verificato i log Railway.
- **Profiling MR-D2 con pool di 7-8 sedi attive Trenord**: il
  helper `_carica_sedi_attive_azienda` carica TUTTE le sedi attive
  azienda (per Trenord ~7-8). MR-D2 itera su questo pool per
  scegliere la sede ottima per ogni segmento. Non ho stimato
  l'impatto computazionale per programmi a 50+ sedi (azienda
  futura ipotetica). Probabilmente OK ma da verificare in MR-D7.
- **Validazione racc #2 originale**: dichiarata "geometricamente
  corretta" in §3 della risposta domande, ma non ho riletto
  letteralmente il diff MR-D2 originale per verificare che il
  vincolo HARD sia implementato come dichiarato. Mi sono fidato
  delle critiche precedenti.

---

## Raccomandazione concreta — prossime mosse

**Pre-MR-D5h obbligatori (~3-4h)**:

1. **Aggiungi test su `_carica_sedi_attive_azienda`** (S2 HIGH,
   <45 min) — 4-5 test parametrici.
2. **Estrai `_costruisci_mappature_regole_linee` + test** (S3+S4
   HIGH+MED, ~2h) — funzione pura testabile + 4-6 test.
3. **Aggiungi 3 R-PROC a `.claude/agents/severo.md`** (S6 MED
   PROCESSO, 1h) — chiude debito di processo entry 270.

**Decisione utente per il 3° mismatch sede-regola**:

Mia raccomandazione **(c) Configurazione utente** + fix codice
complementare warning UI. Vedi §3 risposta domande. Costo: 0h
codice critico + 30 min pianificatore + 1-2h UI nice-to-have
(scope MR-D5h diagnostico).

**Sequenza MR**:
- MR-D5h-A (test debt): fix S2+S3+S4+S6 (~4h)
- MR-D5h-B (UI diagnostica + warning sede vs regola): scope se
  utente conferma strada (c) (~2h)
- Configurazione prog 17: pianificatore riassegna sede regole
  Tirano/Bergamo via UI (out of scope codice)
- E2E re-test prog 17 post-configurazione: verificare giri
  persistiti > 0

**Se utente conferma le mosse sopra**: MR-D5h trio chiude tutto
il debito strutturale del trio MR-D5f con voto target 7/10
(buono, qualche miglioramento sostanziale possibile).

---

## Tracciabilità

- Brief AMILCARE V4 Pro tentato 3× con `mcp__amilcare__reason`
  (6KB → 3.5KB → 1.5KB → tutti timeout `-32001`). Brief V4 Flash
  via `mcp__amilcare__code` 1KB → timeout. Pattern entry 248
  confermato in pieno: AMILCARE non operativo in questa sessione.
- Critica fallback NINO puro dichiarata. Bias auto-compiacenza
  inevitabile (NINO ha appena committato il codice). Voto
  provvisorio 5/10\*, da rifare con AMILCARE V4 Pro operativo
  (margine ~2 punti più severo, voto effettivo ipotetico 3-4/10).
- R-PROC-1 aggiunge una raccomandazione concreta a `.claude/agents/
  severo.md` rispetto a critica precedente entry 270 (mai chiusa)
  + lezione empirica del trio MR-D5f.
- Critiche precedenti rilevanti citate:
  `docs/critiche/SPRINT-8.2-MR-D5e+bug-architetturale-single-sede.md`
  (4/10 entry 270 fallback, da cui derivano S1-S6 della critica
  attuale).
