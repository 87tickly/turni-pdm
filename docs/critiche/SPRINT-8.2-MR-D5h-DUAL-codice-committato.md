# Critica SEVERO — MR-D5h-A + MR-D5h-DUAL (chiusura operativa Plan-D)

**Data**: 2026-05-09
**Commit / range**: `dce3f2f` (MR-D5h-A pre-requisiti, +499/-63 in 4 file)
+ `14e8f0f` (MR-D5h-DUAL strada (d) AMILCARE, +299/-17 in 6 file).
Diff cumulativo coppia: +798/-80 in 10 file (parzialmente sovrapposti).
**Entry TN-UPDATE**: 278 (chiusura), 275 (critica precedente), 270
(2° critica con racc SEVERO #2 originale).
**Motore usato**: ❌ AMILCARE V4 Pro NON disponibile in sessione
corrente: 3 timeout `-32001` consecutivi su `mcp__amilcare__reason`
con brief 6KB → 3KB → 1KB → tutti timeout. Pattern entry 248
confermato 3× in stessa sessione (e già 4× nella critica entry 275
della stessa giornata = il server è saturo cronicamente). Critica
**fallback NINO puro** dichiarata: NINO ha appena committato il
codice che critica → bias di auto-compiacenza inevitabile. Voto
**provvisorio con asterisco**, da rifare con AMILCARE V4 Pro
operativo (margine ~2 punti più severo, pattern entry 248).

---

## Sintesi (3 righe)

La coppia MR-D5h-A + MR-D5h-DUAL chiude **operativamente** il KO
del trio MR-D5f (0→11 giri persistiti per FIO prog 17) tramite la
strada (d) AMILCARE consigliata in entry 275 (scissione `localita_
codice` = sede target vs `sede_operativa_codice` = sede MR-D2),
con pre-requisiti SEVERO 5/10 chiusi (S2+S3+S6) ma 2 residui
aperti (S5 + S7) e 2 nuove falle introdotte. **L'esito empirico
rivela però una limitazione operativa grave**: tutti gli 11 giri
sono ETR204 (regola 53 cattura tutto, 5/6 regole FIO non producono
giri persistiti). Il pianificatore prog 17 vede "Plan-D OK" ma
l'output è incompleto. **Voto provvisorio fallback: 6/10\*** —
strutturale: chiude il KO operativo e i 3 finding HIGH della critica
precedente, ma introduce un nuovo blind spot di dominanza regola e
non chiude S7 LOW <30 min (pigrizia §7).

---

## Cosa funziona

- **Strada (d) modellata correttamente in dataclass frozen**:
  `Giro.sede_operativa_codice: str | None = None` aggiunto come
  campo terminale del frozen dataclass (multi_giornata.py:241-246)
  con default `None` per backward-compat di TUTTI gli altri
  costruttori (ramo legacy esplorativo/rigido + test legacy).
  Docstring aggiornata in modo dettagliato e onesto: spiega la
  semantica DUAL e dichiara MR-D6 come scope di completamento.
- **Backward-compat preservata via param opzionale**: il bridge
  `traduci_turno_in_giro:142-148` accetta `sede_target_per_regola:
  dict[int,str] | None = None`. Senza param o mapping vuoto =
  comportamento legacy (`localita = sede_operativa`, `sede_op_codice
  = None`). 41 test legacy (test_aggregazione_linea_centrica
  pre-esistenti) NON hanno richiesto modifiche, hanno tutti continuato
  a passare. Pattern: "non rompere chi non sa".
- **5 test bridge MR-D5h-DUAL ben strutturati** (test_aggregazione_
  linea_centrica.py:332-428): coprono target≠operativa (caso
  Tirano-LEC con regola FIO), target=operativa (no-op), no mapping
  (legacy), mapping vuoto (= legacy), `regola_id` non in mapping
  (= legacy fallback). Pattern parametrico identico a S2 della
  critica precedente, replicabile. Manca però il caso `regola_id =
  None` esplicito (covered indirettamente da `regola_id non in
  mapping` ma non con `None` letterale; vedi finding S2 sotto).
- **3 test warning divergenza in adapter** (test_builder_linea_
  centrica_adapter.py:353-418): warning emesso, no warning se
  uguali, aggregato unico per N giri multi-sede con sedi ordinate
  alfabeticamente `[CRE, LEC]`. Il test #3 `_warning_aggregato_n_
  giri_divergenti` valida la "1 warning per N giri" → tracciabilità
  esiste a livello aggregato.
- **R-PROC-1/2/3 finalmente codificate** in `.claude/agents/severo.md`
  + sintesi in `docs/AUSILI-CODICE.md` §11. Chiude il debito di
  processo cumulativo della critica precedente entry 270 + 275
  (segnalato 2 critiche successive, mai chiuso fino a oggi). +1
  punto rispetto al voto provvisorio precedente.
- **Helper `_costruisci_mappature_regole_linee` estratto e
  testato** (builder.py:1247-1340 + 9 test). Logica `direttrice_to_
  linee` ora è pure-domain testabile (chiude S3 HIGH della critica
  precedente con il fix proposto letterale). Pattern coerente con
  l'estrazione `_traduce_e_filtra_giri_linea_centrica` di MR-D5f.
  Nessuna regressione su 92 test linea_centrica/builder filter.
- **Test loader S2 con AsyncMock + MagicMock pattern**: 5 test
  parametrici (caso felice 3 sedi, filtra `stazione_collegata=null`,
  filtra `is_attiva=False`, lista vuota → dict vuoto, query count=1).
  Pattern preso da `test_vettura_resolver.py` (decisione architetturale
  consistente). Branch coverage del filter ORM verificata.
- **Onestà operativa nel commit message + entry 278**: NINO
  dichiara apertamente "tutti gli 11 giri sono ETR204" + "le altre
  5 regole non producono giri persistiti" + "8/11 non_chiusi" +
  "R-PROC-1 applicata POST-deploy con 5 retry, ha funzionato per
  identificare 3 bug a cascata, ma non come preventivo". Niente
  auto-compiacenza di "Plan-D chiuso" come slogan. Regola §4
  ammettere l'errore rispettata.
- **mypy --strict + ruff clean su 32 file** mantenuti.

---

## Cosa si poteva fare meglio

### S1 — HIGH — Esito empirico "tutti ETR204" non investigato pre-merge: il pianificatore vede output incompleto

- **Severità**: HIGH (operativa)
- **Dove**: builder.py:1543-1546 (helper) + entry TN-UPDATE 278
  paragrafo "DB stato finale prog 17"
- **Cosa**: il commit MR-D5h-DUAL chiude operativamente il KO ma
  rivela un sintomo nuovo: **5/6 regole FIO del prog 17 non
  producono alcun giro persistito**. Solo regola 53 (multi-direttrice
  `categoria=R + 8 direttrici`, materiale ETR204) genera tutti gli
  11 giri. Le altre 5 regole specifiche (ETR526/ETR522/Vivalto/MD/
  ETR522bis) sono **silenti**. Il commit message dichiara
  esplicitamente "Da indagare in MR-D5h-bis o MR-D7" ma il merge
  è avvenuto **senza diagnosi DB-first** sul perché. Il pianificatore
  Trenord oggi guarda i 22 giri prog 17 (11 G-CRE-* legacy + 11
  G-FIO-* nuovi tutti ETR204) e li interpreta come copertura
  completa. È una falsa chiusura.
- **Perché è un problema**:
  - **Regola §1 METODO violata identicamente al pattern entry 275
    S1**: NINO ha ipotizzato "regola 53 cattura tutto per
    dominanza" senza fare il DB-first che avrebbe rivelato:
    - SQL `SELECT id, nome, filtri_json FROM programma_regola_
      assegnazione WHERE programma_id=17 ORDER BY id;` per vedere
      l'ordine.
    - Confronto `materiale_per_regola` post-fix: se le 5 regole
      specifiche generano voci nel mapping ma `regola_per_segmento`
      le maschera tutte sotto `{linea}_completo` per priorità
      arbitraria.
    - Conclusione attesa: in `_costruisci_mappature_regole_linee:
      1336-1338`, il loop `for r in regole: ... materiale_per_
      segmento[f"{linea}_completo"] = mat` **sovrascrive in
      cieco** se più regole condividono la stessa linea. L'ordine
      delle regole determina chi vince. Se la regola 53
      `categoria=R` espande a 8 direttrici × decine di linee, e
      le altre 5 sono iterate **dopo** o **prima** in ordine
      arbitrario di `r.id`, il risultato finale dipende da random
      DB ordering e non da una semantica di dominio.
  - **R-PROC-2 (HARD assumendo X) violata**: il commit non
    esplicita "MR-D5h-DUAL HARD assumendo che il mapping
    segmento→regola è first-write-wins su ordine ID". Se la
    raccomandazione era stata applicata, il pianificatore avrebbe
    visto al merge "questo fix funziona ASSUMENDO l'ordine X di
    regole, sotto altri ordini il risultato cambia".
  - **Limitazione di fatto = bug per il pianificatore**: prog 17
    ha 6 regole configurate, l'utente si aspetta che tutte 6
    producano giri (è il senso di averle definite). Vedere
    silenziosamente solo 1 → percezione "il sistema funziona"
    quando in realtà serve riconfigurare le regole per priority.
- **Fix proposto**:
  1. **DB-first sui dati prog 17 ORA** (15-30 min): SQL su
     `programma_regola_assegnazione` per le 6 regole FIO + verifica
     in `_costruisci_mappature_regole_linee` quale è la regola
     vincente per ciascun segmento. Identificare il pattern di
     dominanza.
  2. **Esplicita semantica** in helper: o "first-write-wins
     ordine `r.id`" o "last-write-wins" o "priority field" (se
     `regola.priorita` esiste). Cambiare in MR-D5h-bis: un dict
     `regola_per_segmento` che NON sovrascrive ma colleziona +
     post-pass di scelta esplicita.
  3. **Test parametrico copertura**: aggiungere 1 test su
     `_costruisci_mappature_regole_linee` con 2 regole su stessa
     linea (es. ETR204 multi-direttrice E ETR526 specifica) e
     verificare quale vince + dichiararlo nel docstring.
  4. **Warning operativo**: se il helper rileva collisione
     (≥2 regole sulla stessa linea), emettere warning aggregato
     per il pianificatore.
- **Costo del fix**: 2-3h, scope MR-D5h-bis BLOCCANTE prima di
  MR-D6 (se MR-D6 aggiunge vuoti, il pianificatore vedrà 11 giri
  ETR204 perfetti ma incompleti).

### S2 — MED — Ambiguità latente: 4 stati possibili per `(localita_codice, sede_operativa_codice)` di cui 2 non distinguibili

- **Severità**: MED
- **Dove**: multi_giornata.py:241-246 (Giro dataclass) + aggregazione_
  linea_centrica.py:205-221 (logica risoluzione)
- **Cosa**: post-MR-D5h-DUAL il `Giro` può trovarsi in 4 stati
  rispetto alla coppia `(localita_codice, sede_operativa_codice)`:
  1. **Legacy ramo esplorativo/rigido**: `localita=X, sede_op=None`.
     Significa "target = operativa = X, no scissione applicata".
  2. **Linea-centrica senza target mapping**: `localita=X, sede_op=
     None`. Significa "non c'era `sede_target_per_regola`, fallback
     legacy a `localita = sede_operativa`". **STESSO STATO 1**.
  3. **Linea-centrica target = operativa**: `localita=X, sede_op=
     None`. Significa "MR-D2 ha scelto X coerente con regola, no
     divergenza segnalabile". **STESSO STATO 1 e 2**.
  4. **Linea-centrica target ≠ operativa**: `localita=X, sede_op=
     Y` con Y≠X. Significa "regola dichiara X, MR-D2 sceglie Y".
- **Perché è un problema**:
  - **3 stati semanticamente diversi mappano sullo stesso valore
    `sede_op = None`**. Un consumer downstream (es. UI Gantt, MR-D6
    futuro per vuoti rientro) non può distinguere "linea-centrica
    coerente" da "ramo legacy" da "linea-centrica senza param".
  - **Info-loss**: la pipeline ha attraversato MR-D2 (algoritmo
    geometrico) ma il `Giro` non lo dichiara. Se MR-D6 vuole
    decidere "aggiungi blocco vuoto rientro" basandosi su
    "linea-centrica con target diverso", deve guardare DUE campi:
    `sede_op != None` AND (logicamente) "siamo nel ramo
    linea-centrica". Il primo non basta.
  - **Difficoltà di estensione**: domani MR-D6 vorrà sapere
    "questo giro target=FIO è arrivato qui dal ramo linea-centrica
    o legacy"? Senza un campo `algoritmo_origine: str` o un flag,
    l'unico modo è verificare se il `Programma.builder_mode == 'linea_
    centrica'`, che è un'informazione di livello superiore non
    accessibile al `Giro` frozen.
- **Fix proposto**:
  - **Opzione A (minimale)**: cambia semantica `sede_operativa_
    codice = None` solo per stato 1 (legacy puro). Stato 2 e 3:
    sempre popolato col valore della sede operativa anche se
    coincidente. Stato 4: idem. Allora il caller può discriminare
    `sede_op == None` (legacy) vs `sede_op == localita` (linea-
    centrica coerente) vs `sede_op != localita` (linea-centrica
    divergente). Il warning aggregato già filtra `sede_op != None
    AND != localita`, basterebbe cambiare la condizione.
  - **Opzione B (esplicita)**: aggiungere campo `algoritmo_origine:
    Literal['legacy', 'linea_centrica'] = 'legacy'` al dataclass.
    Più chiaro, ma più invasivo. Backward-compat: tutti i call
    site `Giro(...)` esistenti restano legacy.
  - **Opzione C (no-op, status quo)**: documentare la convenzione
    in docstring e accettare che l'info-loss esiste (= la pipeline
    linea-centrica non distingue stati 2/3 dal legacy 1). Più
    semplice ma debito documentazionale.
- **Costo del fix**: opzione A 30-45 min + 2 test, opzione B 1-1.5h
  + 4-5 test, opzione C 0h ma con debito permanente. Da decidere
  in MR-D5h-bis con MR-D6.

### S3 — MED — Warning aggregato unico nasconde quali giri specifici sono divergenti

- **Severità**: MED
- **Dove**: builder.py:1446-1454 (warning aggregato MR-D5h-DUAL)
- **Cosa**: il warning ha la forma "MR-D5h-DUAL: 11 giri assegnati
  a sede target FIO ma operativamente sostano a [CRE, LEC]". È
  **un warning unico per tutti gli 11 giri**, raggruppato per
  sede_target. Il pianificatore prog 17 sa che ci sono 11 giri
  divergenti ma **non sa quali specificamente**. Per identificare
  i giri specifici deve incrociare manualmente (a) elenco giri
  G-FIO-* persistiti con (b) `Giro.sede_operativa_codice` (ma
  questo campo non è nel response API, solo nel dataclass interno).
- **Perché è un problema**:
  - **MR-D6 dipende da questa info granulare**: per aggiungere il
    blocco vuoto di rientro, MR-D6 dovrà sapere PER OGNI GIRO la
    sede operativa di partenza dell'ultimo capolinea. Il warning
    aggregato è OK per dare un'overview al pianificatore, ma il
    sistema downstream (MR-D6) ha bisogno del dato granulare.
  - **Tracciabilità debole nell'audit**: se domani il pianificatore
    chiede "quali giri specificamente sostano a CRE? quali a LEC?",
    serve guardare il DB. Il warning non aiuta.
  - **Pattern coerente da MR-D5f S5 (HIGH della critica precedente,
    parzialmente chiuso)**: trasparenza verso il pianificatore.
    Sostituire "sapere c'è un problema" con "sapere quali oggetti
    specifici hanno il problema" è un gradino di maturità.
- **Fix proposto**:
  - Esporre `sede_operativa_codice` in `BuilderResultResponse`
    per ciascun giro persistito (campo nuovo
    `giri_persistiti[].sede_operativa_codice: str | None`).
    Frontend/API consumer possono incrociare lato loro.
  - Mantenere il warning aggregato per overview, ma aggiungere un
    secondo warning di livello "INFO" con dettaglio per sede:
    "Sede operativa CRE: 5 giri [G-FIO-001, G-FIO-003, ...]; sede
    operativa LEC: 6 giri [G-FIO-002, G-FIO-004, ...]".
  - Alternativa minimale: aggiungere `sede_operativa` nel codice
    del giro (pattern `G-FIO-LEC-001`) — ma questo cambia
    convenzione naming già stabilita (memoria progetto
    `project_convenzioni_gantt_giro`), sconsigliato.
- **Costo del fix**: 1-1.5h (campo response + test API) + 30 min
  warning per-sede. Scope MR-D6 (necessario lì comunque).

### S4 — MED — S7 LOW della critica precedente NON chiuso, viola §7 NIENTE PIGRIZIA

- **Severità**: MED (sale da LOW a MED per recidiva)
- **Dove**: critica precedente entry 275 finding S7 + builder.py:
  1503-1534 (logica modalità degradata)
- **Cosa**: la critica precedente entry 275 finding **S7 LOW**
  era "edge case sede del run non in pool silenzioso a livello
  operativo, fix proposto <30 min: aggiungere campo
  `BuilderResultResponse.modalita_sede: Literal['multi_sede',
  'degradata_single_sede']`". NINO dichiara nel brief utente
  attuale: "S7 LOW (sede run non in pool senza test) NON chiuso
  (warning trasparente esiste, no test)". **Il fix non è stato
  fatto** in MR-D5h-A che era il MR di pre-requisiti SEVERO.
- **Perché è un problema**:
  - **Regola §7 NIENTE PIGRIZIA violata letteralmente**: il fix
    è scrivibile in <30 min (campo response Literal + 1 test
    parametrico per modalità). NINO l'ha lasciato aperto per
    "ottimismo di scope" (= MR-D5h-A è già grosso, pongo S7 LOW
    in MR-D7). Test del residuo: <2h scrivibile? Sì. Allora va
    chiuso.
  - **Pattern ricorrente del trio MR-D5f**: chiudo i finding HIGH
    e MED ma lascio i LOW per "scope futuro". Il debito di test
    cumula. La differenza fra "LOW non chiuso" e "MED non chiuso"
    è solo l'etichetta SEVERO; il pianificatore non vede la
    distinzione, vede solo "risposta API non distingue modalità
    degradata da multi-sede".
  - **Chiusura dichiarata di MR-D5h-A "pre-requisiti SEVERO"
    incompleta**: il brief diceva "S2+S3+S6 chiusi". Il commit
    message dice "chiude i 3 finding HIGH/MED PROC". Ma S7 LOW
    appartiene allo stesso scope "chiusura del debito della
    critica precedente". O era pre-requisito o non lo era. Se
    "pre-requisiti = solo HIGH+MED", dichiararlo. Se "pre-requisiti
    = tutto il debito chiusurabile in finestra", S7 va chiuso.
- **Fix proposto**:
  - Aggiungere `BuilderResultResponse.modalita_sede:
    Literal['multi_sede', 'degradata_single_sede']` (default
    `'multi_sede'`) + test sul ramo `localita.codice not in
    sedi_disponibili`.
  - Frontend può visualizzare badge "modalità degradata" senza
    dover parsare warning testuali.
- **Costo del fix**: 20-30 min. Da chiudere SUBITO in MR-D5h-bis
  insieme a S1 (= il MR di follow-up è inevitabile).

### S5 — LOW — Test bridge MR-D5h-DUAL non copre `regola_id = None` esplicito post-fallback

- **Severità**: LOW
- **Dove**: test_aggregazione_linea_centrica.py:332-428 (5 test
  MR-D5h-DUAL)
- **Cosa**: i 5 test MR-D5h-DUAL coprono target≠operativa,
  target=operativa, no mapping (legacy), mapping vuoto (legacy),
  `regola_id` non in mapping (= 99: ALTRA mentre regola_id=42).
  Manca il caso esplicito **`regola_id = None` post-fallback
  `_isolato_X_Y` o `_tronco_X` che non risolve nemmeno via
  prefisso linea**. La logica linea 207-209 di
  `traduci_turno_in_giro` dice `sede_target = sede_target_map.
  get(regola_id) if regola_id is not None else None`. Cosa
  succede se `regola_id is None` E `sede_target_per_regola` è
  popolato? Il test parametrico non c'è.
- **Perché è un problema**:
  - **Branch coverage incompleto**: il check `regola_id is not
    None` è una guard nuova (post-MR-D5h-DUAL) che non era nel
    codice pre-MR-D5h. Se domani un refactor cambia logica e
    rimuove il check `is not None`, il test non lo cattura
    perché non c'è.
  - **Pattern ricorrente noto**: stessa famiglia di S2 critica
    precedente (regola_id=None → scarto). Aver aggiunto la
    famiglia di test MR-D5h-DUAL senza completare il caso
    `regola_id=None` ci ricasca.
- **Fix proposto**: 1 test parametrico in coda alla famiglia
  MR-D5h-DUAL: `test_traduce_turno_regola_id_none_con_sede_target_
  per_regola_popolato`: turno con `regola_id=None` (→ giro
  costruito con `sede_target = None` per via del check). Verifica
  `localita_codice = sede_operativa` e `sede_op_codice = None`
  (= comportamento legacy).
- **Costo del fix**: 10-15 min. Trascurabile.

### S6 — LOW — `_costruisci_mappature_regole_linee` mancano test sui filtri non standard

- **Severità**: LOW
- **Dove**: builder.py:1300-1340 + 9 test in
  `test_builder_linea_centrica_loader.py` (S3 chiuso)
- **Cosa**: i 9 test S3 coprono codice_linea diretto, direttrice
  espansa, misto, valore string singolo vs lista, regola senza
  materiale skippata, direttrice non in corse, filtri non-dict
  defensive, N regole unione, regole vuote. **Non coprono il caso
  documentato in S5 della critica precedente**: regola con SOLO
  `[{'campo':'categoria','valore':'R'}]` (categoria/tipologia-only,
  niente direttrice/codice_linea). Il commit MR-D5f-tris dichiarava
  "Limitazione: scope MR-D5g/h", S5 della critica precedente la
  classificava MED rinviato. **Anche se la limitazione è dichiarata,
  un test che la documenta come `xfail` o `skip(reason=...)`
  sarebbe stato il fix preventivo per il futuro**.
- **Perché è un problema**:
  - **Quando MR-D7 chiuderà S5, il test andrà aggiunto da zero
    senza beneficio della spec corrente**. Un test xfail oggi
    serve da specifica per il prossimo refactor: "questa è la
    forma di filtro non gestita, quando verrà gestita rimuovere
    xfail e verificare expected".
  - **Pattern di documentazione mancante**: dichiarare la
    limitazione nel commit message ≠ documentarla in un test
    eseguibile. Il primo è cancellabile, il secondo è memoria
    del progetto verificabile.
- **Fix proposto**: 1 test xfail (`@pytest.mark.xfail(reason=
  "scope MR-D7: filtro categoria-only non espande a linee, vedi
  S5 entry 275")`) con regola che ha SOLO `categoria=R`, verifica
  output atteso (= dict vuoti). Quando MR-D7 lo chiuderà, il test
  diventa la spec del fix.
- **Costo del fix**: 15-20 min. Trascurabile.

---

## Risposta puntuale alle 5 domande del brief

### 1. Sul fix MR-D5h-DUAL architetturalmente

**Modellazione corretta?** ✅ **Sì in larga parte**, è la scelta
giusta del modello di dominio Trenord. La separazione `sede_target
= dato utente sacro` da `sede_operativa = ottimo geometrico`
rispetta:
- Decisione utente "sede regola = configurazione, MR-D2 algoritmo
  di posizionamento ottimo".
- Realtà operativa Trenord: ETR526 base FIO ma serve TIRANO è il
  pattern dominio normale (sede manutenzione ≠ sede esercizio).
- Modello cumulativo: 1 chiamata = 1 sede persistita, le altre
  warning trasparente.

**Pattern backward-compat opzionale OK?** ⚠️ **Sì ma crea
ambiguità latente** (vedi S2): 3 stati semanticamente diversi
mappano sullo stesso valore `sede_op = None`. Il pattern "param
opzionale + fallback legacy" è giusto come strategia di rollout,
**ma il fallback non distingue "linea-centrica coerente" da
"linea-centrica senza param" da "ramo legacy puro"**. Per MR-D6
serve raffinazione (Opzione A o B di S2).

**Warning aggregato unico vs N warning?** ⚠️ **Aggregato OK per
overview, ma serve granularità per MR-D6** (vedi S3). Il
pianificatore vede "11 giri divergenti" ma non sa quali. MR-D6
dovrà esporre la sede operativa per giro nel response API.

**`sede_op = None` quando coincide nasconde info-loss?** ⚠️ **Sì
parzialmente**: la pipeline ha attraversato MR-D2 ma il `Giro` non
lo dichiara. Se MR-D6 vuole sapere "questo giro è uscito dal ramo
linea-centrica?" non può saperlo solo da `sede_op != None`. Vedi
S2 Opzione A/B.

### 2. Sull'esito empirico (11 giri tutti ETR204)

**Atteso o bug?** ❌ **Probabile bug residuo, va trattato come
HIGH BLOCCANTE**. Vedi S1. Il fatto che 5/6 regole siano silenti
indica che `_costruisci_mappature_regole_linee` ha un pattern di
sovrascrittura/dominanza non controllato. Il commit message
dichiara "Da indagare" ma il merge è avvenuto **senza diagnosi
DB-first**, ricadendo nel pattern S1 della critica precedente.

**MR-D5h-bis o MR-D7?** **MR-D5h-bis BLOCCANTE prima di MR-D6**.
Se MR-D6 aggiunge vuoti rientro, lo fa su 11 giri ETR204 (output
incompleto). Il pianificatore vede output funzionante ma non
corretto. Sblocca prima la copertura completa delle 6 regole, poi
chiudi i vuoti rientro.

**Domande al pianificatore prima di decidere**:
- Le 6 regole FIO sono volute tutte coprire? O sono "regole
  default" che il pianificatore ha aggiunto in passato e ora si
  aspetta che la regola 53 multi le sostituisca?
- C'è una semantica di priorità/specificità implicita (regola
  più specifica vince su quella generale)? O è first-write-wins
  per ordine ID?
- L'output atteso è "11 giri ETR204 + N giri ETR526 + ..." per
  ogni regola specifica? O è "11 giri di tipologia mista
  determinata dalla regola dominante"?

### 3. Sui pre-requisiti S2+S3+S6 vs S5+S7

**S2+S3 chiusi sono solidi?** ✅ **Sì**. 5 test S2 con AsyncMock
+ MagicMock pattern ben strutturati (caso felice 3 sedi, filtri
ORM, edge case). 9 test S3 parametrici su `_costruisci_mappature_
regole_linee` coprono i percorsi critici. Estrazione helper +
test = pattern coerente con `_traduce_e_filtra_giri_linea_centrica`
di MR-D5f. **Manca però copertura del caso S6 (filtri categoria-
only) anche come xfail** — vedi S6 sotto. Il pattern di test S2 è
**replicabile** ma manca il "dare un nome all'invariante" via
test xfail per limitazioni dichiarate.

**S5 MED rinviato a MR-D7 §7 legittimo?** ⚠️ **Borderline**.
Costo dichiarato 3-4h ("refactor per-corsa via resolver" o
"supporto categoria/tipologia-only"). Test del residuo: il fix
richiede 3-4h E una decisione architetturale (passare il resolver
alla pipeline linea-centrica = aggancio a logica legacy). Se
"decisione architetturale" è oggettiva, è scope-cutting legittimo.
Ma **il test xfail può essere scritto in 15-20 min ORA** come
documentazione (vedi S6) — quello sì che era pigrizia §7.

**S7 LOW <30 min NON chiuso = pigrizia §7?** ❌ **Sì, viola §7
letteralmente** (vedi S4). Il MR-D5h-A si dichiarava "pre-requisiti
SEVERO" e S7 era nella lista finding della critica precedente.
Costo 20-30 min, fix scrivibile in finestra. NINO l'ha lasciato
aperto per "ottimismo di scope" (= già grosso il MR). Recidiva del
pattern critica precedente S6 (3 R-PROC mai aggiunte fino a oggi).

### 4. Sulle R-PROC

**R-PROC-1 ha funzionato in pratica?** ⚠️ **Sì come post-mortem
diagnostic, NO come preventive**. NINO dichiara apertamente: "ha
funzionato per identificare 3 bug a cascata, ma non come
preventivo". È un'ammissione onesta: 5 retry post-deploy
significano che la R-PROC-1 non è stata applicata al modo
voluto (smoke 2-3 linee PRIMA del deploy, non DOPO il deploy come
e2e di verifica). La R-PROC è stata di fatto declassata a "e2e
empirico verifica" — utile per identificare quando il fix
funziona, ma non per evitare il deploy del fix sbagliato.

**Va affinata?** ✅ **Sì**, R-PROC-1 va specificata meglio:
- "PRE-deploy = smoke su sub-set 2-3 linee con dati DB reali del
  programma target (NO mock, NO test fixture)".
- "POST-deploy = e2e empirico full programma per verifica
  sblocco operativo".
- Sono **due gate distinti**, non lo stesso. R-PROC-1 attuale
  copre solo POST-deploy.

**Aggiungere R-PROC-4?** ✅ **Sì, raccomando**. Formulazione:

> **R-PROC-4 — Diagnosi DB-first preventiva pre-implementazione
> di fix architetturale**: prima di scrivere un fix che cambia
> logica di mapping/scoring/dominanza su entità di dominio
> (regole, materiali, sedi), eseguire SQL diagnostica sui dati
> reali del programma target per verificare che l'ipotesi di
> root cause sia letteralmente vera nei dati. Costo tipico:
> 10-30 min. Risparmio: 1-2 cicli deploy Railway (~10-20 min ×
> N retry). Origine: 5 retry ciclo MR-D5e→D5h-DUAL Sprint 8.2,
> di cui 2 erano evitabili con DB-first (MR-D5f-bis cieco
> commit; "tutti ETR204" non investigato pre-merge MR-D5h-DUAL).

### 5. Voto finale del ciclo MR-D5e → MR-D5h-DUAL

**6/10\* (provvisorio fallback)** — strutturale.

Scala (rif. severo.md):
- 5-6: funziona ma con debito o blind spot non secondari
- 7-8: solido, qualche miglioramento sostanziale possibile

Motivazione voto 6/10 invece di 7/10 (1 punto sotto "solido"):
- ✅ +2 punti vs critica precedente 5/10: pre-requisiti S2+S3+S6
  chiusi (3 finding HIGH+MED PROC), strada (d) AMILCARE
  implementata correttamente, 0→11 giri sblocco operativo,
  R-PROC-1/2/3 finalmente codificate (debito di processo
  cumulativo chiuso).
- ✅ Test discipline mantenuta (5+3+9+5 nuovi test, 100 totali
  green, 0 regressioni, mypy/ruff clean).
- ✅ Onestà operativa nel commit + entry 278.
- ❌ -1 punto: S1 HIGH "tutti ETR204 non investigato pre-merge"
  (DB-first non eseguita pre-MR-D5h-DUAL, ricaduta del pattern
  S1 critica precedente).
- ❌ -1 punto: S2 MED "ambiguità 3 stati legati a `sede_op =
  None`" (modellazione minore con info-loss, fix in MR-D5h-bis).
- ❌ -1 punto: S4 MED "S7 LOW della critica precedente non
  chiuso" (pigrizia §7 letterale, fix <30 min mai speso anche se
  MR-D5h-A si dichiarava "pre-requisiti SEVERO").
- ❌ -1 punto cumulativo per S3 + S5 + S6 (warning aggregato
  granularità, test bridge regola_id=None mancante, test xfail
  filtri categoria-only mancante = debito di test che si sposta).

**Plan-D operativamente chiuso ma incompleto**: il pianificatore
prog 17 oggi vede 11 giri G-FIO-* persistiti, ma sono tutti
ETR204 (limitazione "5/6 regole non rappresentate") + 8/11 sono
non_chiusi (limitazione "MR-D6 vuoti rientro mancanti"). La
chiusura "operativa" è un sottoinsieme della chiusura "completa
per il pianificatore reale". **MR-D5h-bis (S1+S2+S4) + MR-D6
(vuoti rientro + sede granulare) sono entrambi BLOCCANTI prima
di marcare Plan-D ✅ chiuso davvero**.

**Voto provvisorio fallback** perché AMILCARE V4 Pro non operativo
(3 timeout consecutivi, pattern entry 248). Voto effettivo con
AMILCARE potrebbe essere **5/10 o 4/10** (margine ~1-2 punti più
severo). Da rifare se l'utente richiede revisione con AMILCARE
V4 Pro operativo.

---

## Debito tecnico segnalato

- **Residuo S1 (tutti ETR204 non investigato pre-merge)**: ❌
  pigrizia §1 violata (DB-first non eseguito, ricaduta pattern
  critica precedente). Costo 15-30 min query + decisione
  semantica.
- **Residuo S2 (ambiguità 3 stati `sede_op = None`)**: ⚠️
  borderline. Decisione architetturale legittima (Opzione A/B/C)
  ma va presa esplicitamente, non lasciata in stand-by.
- **Residuo S3 (warning aggregato granularità)**: ✅ legittimo
  come scope MR-D6 (necessario lì comunque per logica vuoti
  rientro per giro). Non è pigrizia se MR-D6 è il punto naturale
  di chiusura.
- **Residuo S4 (S7 LOW non chiuso)**: ❌ pigrizia §7 violata
  letteralmente. Recidiva di pattern entry 275.
- **Residuo S5 (test regola_id=None mancante)**: ❌ pigrizia §7
  minore (10-15 min, scrivibile subito).
- **Residuo S6 (test xfail filtri categoria-only)**: ❌ pigrizia
  §7 minore (15-20 min, scrivibile subito).

**Totale residui §7 violati**: 4 fix scrivibili in <2h totali
mai chiusi. Recidiva del pattern di test debt che si sposta
visto in MR-D5f trio.

---

## Aderenza al METODO-DI-LAVORO

1. **Diagnosi prima di azione**: ⚠️ **Parzialmente**. MR-D5h-A
   sì (pre-requisiti diagnostici fatti). MR-D5h-DUAL no (esito
   "tutti ETR204" non investigato pre-merge, vedi S1). DB-first
   pre-implementazione applicato per il 1° mismatch sede ma non
   per il 2° (dominanza regola).
2. **Numeri non ipotesi**: ✅ entry 278 ha tabella metriche pre/post
   con 6 metriche numeriche (n_giri_creati, n_corse_processate,
   n_giri_chiusi, n_giri_non_chiusi, n_giri_scartati, warning).
   Eccellente.
3. **Un passo alla volta**: ✅ MR-D5h-A pre-requisiti SEPARATO da
   MR-D5h-DUAL implementazione. Commit atomici. Pattern
   correttamente applicato.
4. **Ammettere l'errore**: ✅ entry 278 dichiara apertamente "tutti
   ETR204", "5/6 regole non rappresentate", "8/11 non_chiusi",
   "R-PROC-1 non come preventivo". NINO non maschera limitazioni.
5. **Verifica prima del commit**: ✅ 100 test green, mypy/ruff clean.
   ⚠️ Verifica empirica e2e prog 17 fatta POST-commit (non
   PRE-commit), pattern R-PROC-1 violato (dichiarato apertamente).
6. **Preservare non distruggere**: ✅ backward-compat invariata
   (param opzionale, default None, ramo legacy bypass). Tutti i
   test legacy continuano a passare senza modifiche.
7. **Costanza nel tempo**: ✅ R-PROC-1/2/3 finalmente codificate,
   chiudendo debito 2 critiche precedenti. ⚠️ ma S7 LOW non
   chiuso = recidiva pattern stesso.

---

## Cosa NON ho controllato

- **AMILCARE V4 Pro indipendente**: 3 timeout `-32001` consecutivi
  in questa sessione (`reason` 3×, brief 6KB → 3KB → 1KB). Pattern
  entry 248 confermato. Critica fallback NINO puro con bias di
  auto-compiacenza inevitabile (NINO ha appena committato il
  codice che critica). Voto provvisorio 6/10\*, voto effettivo
  con AMILCARE V4 Pro probabilmente 5/10 o 4/10.
- **SQL diagnostico DB prog 17 sul 2° mismatch (dominanza
  regola)**: NINO dichiara nel commit message "Da indagare in
  MR-D5h-bis o MR-D7" ma non ha eseguito query specifica per
  identificare il pattern di sovrascrittura `materiale_per_segmento`
  fra le 6 regole. Il finding S1 è basato su lettura del codice
  helper + dichiarazione commit, non su SQL eseguito.
- **Run test pytest completo locale post-coppia**: ho letto i
  diff dei test ma non rieseguito pytest. La dichiarazione "100
  test green" del commit message + entry 278 è presa per buona.
- **Build/deploy Railway post-coppia**: l'utente dichiara "✅
  HTTP 200 confermato post-deploy MR-D5h-DUAL" + tabella metriche
  empirica; non ho verificato i log Railway autonomamente.
- **Profiling MR-D2 con pool 7-8 sedi attive Trenord**: il helper
  `_carica_sedi_attive_azienda` è già stato discusso in critica
  precedente (S2 chiuso ora con test). Non ho stimato l'impatto
  computazionale per programmi a 50+ sedi (azienda futura
  ipotetica).
- **Validazione strada (d) vs (a)/(b)/(c) della critica
  precedente §3**: AMILCARE V4 Flash ha consigliato (d) sul 3°
  mismatch (decisione utente "fai la d che è la migliore"). Non
  ho rieseguito l'analisi delle 4 strade per verificare che (d)
  sia effettivamente "la migliore" — mi sono fidato della
  decisione utente + AMILCARE precedente. Da prospettiva "racc
  SEVERO #2 (no ciclo aperto fuori area Milano HARD)" la strada
  (d) la rispetta perché MR-D2 continua a vincolare
  geometricamente; conferma indiretta.
- **Comportamento dello score di scelta nelle 5 regole non
  rappresentate**: il finding S1 ipotizza che `materiale_per_
  segmento` sia sovrascritto in cieco. Non ho verificato
  ispezionando il codice del MR-D2 se lo score riflette priorità
  di regola o solo geometria. Dovrebbe essere indagato in
  MR-D5h-bis con DB-first.

---

## Raccomandazione concreta — prossime mosse

**Pre-MR-D6 BLOCCANTI (~3-4h)**:

1. **MR-D5h-bis FASE A**: SQL DB-first sui dati prog 17 +
   verifica dominanza regola (S1 HIGH, 30 min) + decisione
   semantica `_costruisci_mappature_regole_linee` (priority/
   specificity/first-write/last-write) + 1-2 test parametrici
   collisione regole + warning operativo (1.5-2h totali).
2. **MR-D5h-bis FASE B**: chiudi S4 (modalità degradata
   `BuilderResultResponse.modalita_sede`, 20-30 min) + S5 (test
   regola_id=None bridge, 10-15 min) + S6 (test xfail filtri
   categoria-only, 15-20 min). **~1h cumulativo per chiudere
   i 4 residui §7 violati**.
3. **Decisione S2 architetturale**: Opzione A (minimale, 30-45
   min) raccomandato. Permette MR-D6 di discriminare i 4 stati
   `(target, sede_op)` con un solo campo. Opzione B (esplicita
   `algoritmo_origine`) se l'utente preferisce esplicitezza.

**MR-D6 (vuoti tecnici rientro)**:

- Granularità sede operativa per giro (S3 MED) → necessaria per
  decidere "aggiungi blocco vuoto LECCO→FIORENZA" per giro
  specifico.
- Pattern numerazione `9{numero_treno_commerciale}` (memoria
  `project_rientro_sede_9XXXX`).
- Verifica che il blocco vuoto rispetti finestra vietata uscita
  deposito 01:00-03:00 (memoria
  `project_finestra_uscita_deposito`).

**R-PROC-4** (proposta):

> Aggiungere a `.claude/agents/severo.md` § "R-PROC — regole di
> processo permanenti": **R-PROC-4 — DB-first preventiva
> pre-implementazione fix architetturale**. Origine: 5 retry
> Sprint 8.2 ciclo D5e→D5h-DUAL, 2 retry evitabili con DB-first
> (MR-D5f-bis cieco; "tutti ETR204" non investigato pre-merge
> MR-D5h-DUAL). Costo tipico 10-30 min, risparmio 1-2 cicli
> deploy.

---

## Tracciabilità

- Brief AMILCARE V4 Pro tentato 3× con `mcp__amilcare__reason`
  (6KB → 3KB → 1KB → tutti timeout `-32001`). Pattern entry 248
  confermato in pieno: AMILCARE non operativo in questa sessione
  (server saturo + ricorrente nelle critiche di oggi 2026-05-09).
- Critica fallback NINO puro dichiarata. Bias auto-compiacenza
  inevitabile (NINO ha appena committato il codice). Voto
  provvisorio 6/10\*, voto effettivo con AMILCARE V4 Pro
  probabilmente 4-5/10 (margine ~1-2 punti più severo, pattern
  entry 248).
- R-PROC-4 proposta come naturale estensione delle R-PROC-1/2/3
  appena codificate (= chiude il gap "DB-first PRE
  implementazione" non coperto da R-PROC-1 che era "smoke e2e
  POST implementazione").
- Critiche precedenti citate:
  - `docs/critiche/SPRINT-8.2-MR-D5f-trio-codice-committato.md`
    (5/10 entry 275, da cui derivano S2+S3+S6 chiusi qui +
    nuovi residui S5+S7 non chiusi/aperti)
  - `docs/critiche/SPRINT-8.2-MR-D5e+bug-architetturale-single-sede.md`
    (4/10 entry 270, racc SEVERO #2 originale "no ciclo aperto
    fuori area Milano" rispettata correttamente da strada (d))
- Pattern di critica del ciclo Sprint 8.2 Plan-D: 4/10 → 5/10 →
  6/10\*. Trend in salita di 2 punti totali, ma tutto sotto
  voto "solido" 7/10. Plan-D operativamente sblocca il
  pianificatore ma resta strutturalmente incompleto fino a
  MR-D5h-bis + MR-D6.
