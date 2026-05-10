# Critica SEVERO — PIANO MR-Sprint8.3-S2 (durata vuoto rientro data-driven)

**Data**: 2026-05-10
**Commit / range**: nessuno (critica **PRE-implementazione** del PIANO)
**Entry TN-UPDATE**: backlog post-Sprint 8.2 (entry 286 chiusa S1+S2,
entry 287 S3 alembic check, entry 288 S4 `from_db` programma_id) →
prossimo finding S2 HIGH critica entry 284
(`docs/critiche/SPRINT-8.2-MR-D5h-bis+MR-D6-codice-committato.md`).
**Motore usato**: ⚠️ AMILCARE V4 Pro NON disponibile in sessione
corrente. 3 timeout `-32001` consecutivi su `mcp__amilcare__reason`
con brief 4KB → 2KB → 1KB → tutti timeout (pattern entry 248 confermato
6× consecutive in 3 giorni: critiche entry 270/275/278/284/285 + questa).
Server V4 Pro saturo cronicamente. Fallback motore V4 Flash
(`mcp__amilcare__code`, V3-chat) operativo: 1 invocazione riuscita
con brief ~700 byte, output ~500 parole strutturato in ~10s. Output
V4 Flash filtrato (3 falsi positivi/over-prescription identificati e
dichiarati: F1 "fallback geometrico obbligatorio" pre-validato come
finding nuovo NON come over-prescription, F4 "≥10 test" gold-plating,
F5 "dict[tuple[str,str],int] non JSON-serializzabile" tecnicamente
vero ma `ParamPipelineLineaCentrica` è dataclass pure-domain non
risposta API). Voto **provvisorio con asterisco** perché V4 Flash
non equivale a V4 Pro in profondità (margine atteso ~0.5-1 punto
più severo con V4 Pro, storico).

---

## Sintesi (3 righe max)

Il piano **risolve correttamente la diagnosi** (60 min hardcoded
sottostimato per scenari distanti) e **adotta una strategia data-driven
elegante** (CorsaCommerciale del programma stesso = fonte di verità
per durate operative reali, niente tabella distanze duplicata) con
**blast radius ben contenuto** (signature opzionale `| None`, fallback
backward-compat). Ma rimane **un buco strutturale**: il fallback 60
quando coppia non in lookup è **lo stesso bug originale rimasto in
piedi** per scenari distanti senza corsa speculare nel programma —
il piano risolve l'80% dei casi e ne lascia il 20% identico al
pre-fix. **Voto provvisorio: 6/10\*** — solido come architettura ma
NON ancora "implementa così" senza ritocco al fallback (vedi
finding S1 nuovo).

---

## Cosa funziona

- **Strategia data-driven CorsaCommerciale = scelta giusta**. Il
  PdE è la fonte unica autorevole (CLAUDE.md §6 manifesto greenfield
  + memoria `feedback_no_inventare_dati`). Usare le durate reali
  del programma stesso = aderenza massima a "numeri non ipotesi"
  (METODO §2). Niente tabella distanze duplicata = niente sync
  problem domani quando cambia l'orario PdE 2027. Niente velocità
  materiale ipotetica = niente assunzione "il vuoto va come il
  commerciale" o "va più veloce di X%" = niente magic constant
  da giustificare.
- **Lookup diretto + speculare = pragmatismo corretto**. Una corsa
  X→Y commerciale dà una stima ragionevole del tempo Y→X vuoto
  (stessa infrastruttura, stessa pendenza, stesse fermate principali).
  Errore tipico < 15-20%, accettabile per stima vuoto rientro.
- **Signature `dict | None = None` = backward-compat preservata**
  (METODO §6 preservare non distruggere). I 5 test MR-D6 esistenti
  in `test_aggregazione_linea_centrica.py:436-562` continuano a
  passare senza modifica (= attivano il fallback 60 = comportamento
  pre-piano).
- **Out-of-scope onesti e ben argomentati**: parking notte intermedio
  (S3 entry 284) è **strutturalmente diverso** (logica ortogonale
  rientro coda vs sosta intermedia) → MR-D7 dedicato. Tabella
  distanze cablata in `data/*.json` = over-engineering reale per
  fix 1.5-2h. Il framing è onesto, NON il pattern "raffinabile MR-D7"
  ingannevole della critica entry 284.
- **Side-fix S1 MED gratis incluso = pattern accettabile**. La
  costante `SPECIFICITY_WILDCARD: Final[int] = 2**31 - 1` è un fix
  banale (5 min, zero blast radius, già discusso in critica entry
  284). Includerlo nello stesso MR di S2 HIGH è coerente — vedi
  domanda 7 sotto. Buona occasione per saldare un debito senza
  costo di context-switching.

---

## Risposta puntuale alle 7 domande

### 1. Strategia data-driven (CorsaCommerciale) vs geometrico (km/velocità + sosta)

**Data-driven è la scelta giusta**, ma NON deve essere l'unica.

Il calcolo geometrico ha 3 problemi reali:
- **Velocità materiale ≠ velocità reale di percorrenza commerciale**:
  ETR526 ha `velocita_max_kmh=160`, ma su Mi.Cle-Tirano la velocità
  commerciale media è ~75-80 km/h (passaggi a livello, gallerie,
  pendenze Stelvio). Velocità max è un'astrazione tecnica, non
  operativa.
- **5 min sosta = magic constant**: stessa pigrizia §7 del 60
  hardcoded, solo spostata di livello.
- **Vuoti effettivamente più veloci dei commerciali, ma di quanto?**
  Niente fermate intermedie ⇒ stima -10/-20% sul tempo, ma il
  "quanto" dipende dalla tratta (n. fermate skippate). Ipotizzare
  un fattore fisso = magic constant n.2.

Data-driven elimina questi 3 magic. **MA** non copre il caso
"coppia non in programma" (es. SONDRIO→CADORNA quando il programma
ha solo Mi.Cle-Tirano, non Cadorna-Tirano). Per quei casi il
fallback 60 è esattamente il bug originale rimasto in piedi —
è il **finding nuovo S1** sotto.

**Verdetto domanda 1**: data-driven primario ✅, geometrico come
**fallback secondario** prima di scendere a 60. Il piano attuale
salta il livello intermedio.

### 2. Where piazzare il pre-calcolo: builder.py vs modulo dedicato

**Modulo dedicato `domain/builder_giro/durata_vuoto.py`**.

Tre motivi:
- `builder.py` è già **1.700 righe** e cresce ogni MR. Aggiungere
  un nuovo helper di 30-50 righe + query DB peggiora il bloat.
- **L'I/O DB sta GIÀ FUORI dal pure-domain**. `genera_giri()` (~riga
  1500-1700) fa async DB calls, poi costruisce `ParamPipelineLineaCentrica`
  (dataclass pure-domain in `pipeline_linea_centrica.py:129`) che
  riceve solo dict pre-calcolati. Il pattern è già: **I/O DB nel
  caller, dati statici al pure-domain via dataclass**. Il pre-calcolo
  durata segue lo stesso pattern.
- **Testabilità**: un modulo dedicato ha unit test propri puri (input
  query mock → output dict atteso). Mescolato in `builder.py` finisce
  in test integration grossi.

V4 Flash dice la stessa cosa, e ha ragione su questo specifico punto.

**Verdetto domanda 2**: modulo dedicato `durata_vuoto.py`, helper
async che riceve `session: AsyncSession` + `programma_id: int` +
`coppie_target: set[tuple[str, str]]` e ritorna
`dict[tuple[str, str], int]`. Importato da `builder.py` come
chiamata fra `_costruisci_mappature_regole_linee` e `ParamPipelineLineaCentrica(...)`.

### 3. Cambio signature: param keyword vs `TurnoConvoglio` vs `ParamPipelineLineaCentrica`

**`ParamPipelineLineaCentrica`** (l'opzione 3 del brief).

- **`TurnoConvoglio` è output di `costruisci_turno_linea` (MR-D3),
  non input del builder**. Iniettare il dict lì = aggiungere un
  campo "viaggio backward" che non corrisponde alla semantica del
  modello (TurnoConvoglio = sequenza giornate, non parametro di
  costruzione). Bocciato.
- **Param keyword in `traduci_turno_in_giro` e `traduci_turni_in_giri`
  (= il piano attuale)**: funziona, ma propaga il dict in 2 funzioni
  invece che 1. Inoltre `traduci_turni_in_giri` è chiamata DOPO
  `esegui_pipeline_linea_centrica`, il che vuol dire che il dict
  viaggia **fuori** dalla pipeline, in un secondo step. Asimmetria
  gestionale.
- **`ParamPipelineLineaCentrica`**: il dataclass è già **il punto
  unico** dove il caller passa configurazione al pure-domain. Aggiungere
  `durata_vuoto_per_coppia: dict[tuple[str, str], int] | None = None`
  lì = 1 punto di iniezione, simmetrico a `sede_target_per_regola`,
  `regola_per_segmento`, `materiale_per_segmento`. Il dict viaggia
  con la pipeline e finisce in `traduci_turni_in_giri` come parte
  del context. Blast radius **minore** del piano attuale.

**Caveat mypy strict**: `dict[tuple[str, str], int]` è hashable
e dataclass-compatible (tuple immutabile + int primitivo). Niente
problema serialization perché `ParamPipelineLineaCentrica` è
pure-domain, non DTO API. F5 V4 Flash ("non JSON-serializable per
BuilderResultResponse") = falso positivo: il dict NON entra in
response.

**Verdetto domanda 3**: aggiungere il campo a
`ParamPipelineLineaCentrica`, propagarlo dentro la pipeline a
`traduci_turni_in_giri` via `params.durata_vuoto_per_coppia`. UNA
firma cambia (`pipeline_linea_centrica.py:225` `esegui_pipeline_linea_centrica`
e/o `traduci_turni_in_giri` interni). Eliminare la modifica
signature di `traduci_turno_in_giro/i` se possibile.

### 4. N corse X→Y a orari diversi: min/mediana/media/percentile

**Mediana, NON minimo**.

V4 Flash concorda. Ragionamento:
- **Min ignora outlier corretti**: la corsa più veloce X→Y può
  essere un treno ad alta velocità (categoria FR, RegioExpress) che
  salta tutte le fermate. Il vuoto materiale invece percorre tutta
  la tratta a velocità tecnica intermedia. Min sottostima.
- **Media è sensibile a outlier opposti**: una corsa lenta
  (regionale, tutte le fermate) gonfia la media. Risultato simile
  al 60 hardcoded ma in eccesso.
- **Mediana è robusta**: stima centrale stabile anche con N piccolo
  (3-5 corse, tipico di tratte secondarie nel PdE).

**Filtro pre-mediana** (importante, NON nel piano attuale):
- Escludere `is_cancellata=True` (memoria `feedback_no_inventare_dati`:
  niente dati invalidi).
- Considerare se filtrare per `categoria` (es. solo "R" regionali
  per omogeneità con vuoto): NO, il piano sarebbe over-engineered.
  Mediana su tutte le categorie va bene.
- Soglia minima N≥1 (NON 3 come dice V4 Flash): se ho 1 sola corsa
  X→Y, la sua durata è comunque meglio del 60 hardcoded. V4 Flash
  over-prescrive. Falso positivo dichiarato.

**Verdetto domanda 4**: mediana di `(ora_arrivo - ora_partenza)`
in minuti, su corse non cancellate, soglia minima N≥1 (no soglia
artificiale che ricade su fallback inutilmente). Ordinamento
deterministico: ordinare per `(ora_partenza, numero_treno)` prima
del calcolo mediana = output stabile cross-run.

### 5. Fallback 60 hardcoded vs geometrico se km_tratta+velocità disponibili

**Geometrico OBBLIGATORIO come fallback secondario** (= NUOVO
finding del piano, vedi S1 sotto).

V4 Flash su questo ha ragione (= NON falso positivo, finding
sostanziale che il piano non considera). Ragionamento:
- **TIRANO→FIO scenario**: probabilmente il programma 17 ha corse
  TIRANO→Mi.Cle e ritorno, ma NON ha corse TIRANO→CERTOSA (lookup
  diretto fallisce). Speculare CERTOSA→TIRANO **probabilmente
  manca pure** (nessuno fa una corsa commerciale verso il deposito).
  Risultato: lookup miss → fallback 60 → bug originale RIMASTO.
- **Soluzione cumulativa**: dato `corse` già in scope a livello
  `genera_giri`, posso aggregare `km_tratta` su path X→Y derivato
  da `(codice_origine, codice_destinazione)` + `min_tratta` o
  velocità inferita. Costo: ~30 min in più al piano.
- **Alternativa minimal**: per ogni stazione_target nel programma,
  cerco la corsa più lunga X→stazione_target nel programma e uso
  la sua durata come "tetto pessimistico". Non perfetto ma sopra
  60 = già un miglioramento di 80% dei casi distanti.

**Verdetto domanda 5**: il piano va MODIFICATO per includere
fallback geometrico. Senza, il finding S2 HIGH entry 284 resta
chiuso solo per coppie con corsa nel programma — cioè il sintomo
SI sposta ma non sparisce.

**Costo extra**: 30-45 min sulla stima 1.5-2h = totale 2-2.5h.
Ancora dentro la soglia §7 (<2h è morbida; >2h è dura).
**MA**: se il piano accetta il fallback 60, l'etichetta "MR-D7
raffina" è la stessa pigrizia §7 dichiarata in critica entry 284.

### 6. Test cases: 5 sufficienti?

**No, 7-8 sono il minimo onesto**. Ma NON 10 come dice V4 Flash
(over-prescription, gold-plating).

I 5 nel piano:
1. ✅ Hit diretto
2. ✅ Hit speculare
3. ✅ Miss → fallback
4. ✅ Dict vuoto → fallback ovunque
5. ✅ Plausibili LECCO→CERTOSA + TIRANO→CERTOSA

**Edge che mancano (priorità ordinata)**:

- **6.A — `is_cancellata=True` filtrata**: corsa X→Y cancellata
  NON deve entrare nella mediana. Test: 2 corse X→Y attive (60min,
  70min) + 1 cancellata (30min) → mediana = 65, NON 60. **PRIORITÀ
  ALTA**: il piano non specifica filtro cancellate, è un buco
  reale.
- **6.B — Solo speculare presente**: la coppia X→Y non esiste ma
  Y→X sì. Lookup deve trovare il valore via fallback speculare.
  Test del piano (test 2 "hit speculare") già copre, ma NON è
  ovvio che speculare = unica direzione presente. **PRIORITÀ MEDIA**:
  rinforzare il test 2 con assertion esplicita "diretto miss,
  speculare hit, valore = X".
- **6.C — Fallback geometrico (se accetti finding S1 nuovo)**:
  miss completo + km_tratta presente nel programma → calcolo
  geometrico kicks in. Test: tratta 200km → fallback ≥ 60min ma
  < 200min. **PRIORITÀ ALTA** se si chiude S1 nuovo.

**Edge che V4 Flash propone ma sono falsi positivi**:

- **Corse 'i' (treno-suffisso-i)**: V4 Flash dice "filtra solo
  corse 'i'". Falso: il treno "i" è un commerciale Trenord con
  materiale vuoto in posizionamento (memoria `feedback_pde_periodicita_verita`).
  È **già nel PdE** come corsa commerciale, va trattato come tutte
  le altre. Bocciato.
- **Multi-hop X→Y inesistente ma X→Z + Z→Y sì**: V4 Flash dice
  "calcolo concatenato". Sbagliato: il vuoto rientro è una **singola
  corsa materiale** non spezzettata su 2 treni commerciali. Multi-hop
  = scope MR-D7+. Bocciato.
- **Sede_target == operativa**: già gestito nel codice corrente
  (riga 314: `if sede_target is not None and sede_target != sede_operativa:`).
  Pre-calcolo skippa questi casi naturalmente. Test ridondante.
  Bocciato.

**Verdetto domanda 6**: 5 → 7 test (aggiunti 6.A `is_cancellata`
+ 6.C fallback geometrico se accetti S1 nuovo). 6.B = rinforzo
assertion del test 2 esistente. 7 totali, NON 10.

### 7. Side-fix S1 MED gratis nello stesso MR vs §3 "un passo alla volta"

**OK includerlo, NON è violazione di §3**.

§3 METODO "un passo alla volta" è scritto contro **i salti
architetturali concorrenti** (es. "rifaccio l'algoritmo + cambio
schema DB + aggiungo endpoint, tutto in 1 commit"). NON contro i
fix banali raggruppabili.

Test del raggruppamento:
- I due fix toccano file **diversi** (S1 in `builder.py`, S2 in
  `aggregazione_linea_centrica.py` + `pipeline_linea_centrica.py`)?
  Sì → niente conflict di logica intrecciata.
- I due fix possono essere **revertati indipendentemente** se uno
  rompe? Sì → granularità ok.
- L'inclusione **gonfia il diff oltre il leggibile** (>500 righe)?
  No, S1 è ~10 righe + 2 occorrenze + docstring. Trascurabile.

Pattern accettabile per fix banali co-located in stesso MR-cleanup:
- Estrazione costante magica
- Refactoring rename triviale (1-2 punti)
- Fix typo

Pattern NON accettabile (separare in MR distinti):
- Modifiche a logica di dominio in moduli ortogonali
- Refactor strutturali (cambio signature multiple)
- Modifiche schema DB

**Verdetto domanda 7**: includere S1 nello stesso MR, **ma in commit
git separato** dentro il MR (= 2 commit logici: commit 1 "extract
SPECIFICITY_WILDCARD constant", commit 2 "data-driven durata vuoto
rientro"). Reviewer può guardare ognuno isolato. Nessuna violazione
§3.

---

## Cosa si poteva fare meglio (finding NUOVI sul piano)

### S1 — HIGH — Fallback 60 quando coppia non nel programma è il bug originale rimasto in piedi

- **Severità**: HIGH (sale di nuovo a HIGH come nella critica entry 284)
- **Dove**: piano step 1 + step 3 (`fallback=60` nel helper +
  "skip se non trovata" nel pre-calcolo)
- **Cosa**: il piano risolve il bug per **coppie X→Y presenti come
  corse commerciali nel programma**. Per coppie NON presenti
  (esempio canonico: TIRANO→CERTOSA = stazione collegata FIO ≠
  stazione commerciale, **NESSUNA corsa commerciale viaggia verso
  un deposito materiale**), il lookup miss e ricade su 60 min.
  Risultato: il bug originale è RIMASTO IDENTICO per il caso più
  importante (rientro materiale a sede operativa lontana).
- **Perché è un problema**:
  - Il finding S2 HIGH entry 284 era proprio "TIRANO→FIO
    drasticamente sotto" — e FIO=FIORENZA, depositato materiale,
    **non è una stazione commerciale** del PdE. Il lookup diretto
    su CorsaCommerciale fallirà sempre per stazione collegata =
    proxy commerciale.
  - Il proxy commerciale è la *stazione COLLEGATA* (memoria
    `project_stazione_collegata_localita`): FIO→CERTOSA, NOV→Cadorna,
    CRE→omonima, etc. CERTOSA, Cadorna sono stazioni commerciali,
    ma non sono i capolinea naturali delle corse di linea.
    Esempio: corse TIRANO→Mi.Cle ci sono, TIRANO→CERTOSA NO. Il
    piano non lo riconosce.
  - Fallback 60 = bug originale rimasto = pigrizia §7 LETTERALE
    se non si chiude.
- **Fix proposto**: 
  - **Opzione A (raccomandata)**: fallback geometrico se km_tratta
    è derivabile dal programma. Quando coppia (X, Y) non è in
    lookup, trova la corsa commerciale che parte da Y (o termina
    a X) verso/da una stazione vicina alla destinazione/origine
    target, e usa la sua velocità commerciale come stima per il
    tratto restante. È un'approssimazione, ma sopra 60.
  - **Opzione B (più semplice)**: per ogni stazione_target nel
    programma, cerca la corsa più lunga (in min_tratta o km_tratta)
    che termina a una stazione "vicina" (= stessa direttrice della
    target). Usa quella come baseline pessimistica per qualunque
    miss verso quella target. Costo: ~30 min in più, ricicla
    `direttrice` campo già esistente.
  - **Opzione C (peggio)**: dichiarare il limite + warning runtime
    quando si usa fallback 60 + corse coppia non disponibili. Almeno
    è onesto, non risolve. Costo: 10 min.
- **Costo del fix**: opzione A 30-45 min in più al piano (totale
  2-2.5h, dentro soglia §7 morbida). Opzione B 30 min. Opzione C
  10 min ma è un palliativo.
- **Verdetto SEVERO**: **opzione A o B BLOCCANTE** prima di marcare
  S2 HIGH entry 284 chiuso davvero. Opzione C è solo "mi salvo la
  faccia" per spostare il bug a MR-D7. Pattern recidiva critica
  entry 284 ("raffinabile MR-D7" framing ingannevole).

### S2 — MED — Pre-calcolo NON cachato fra run consecutivi del builder

- **Severità**: MED
- **Dove**: piano step 3, helper `_costruisci_durata_vuoto_per_coppia`
  presumibilmente eseguito ad ogni `genera_giri()` invocation
- **Cosa**: il helper fa N query CorsaCommerciale (una per coppia
  X→Y plausibile), o 1 query bulk + filter in-memory. Per programmi
  grandi (PdE 2026 ~6.500 corse) la query bulk è leggera (~200ms),
  ma se il pianificatore rilancia `genera_giri()` 10 volte per
  tweak di regole, sono 10×200ms sprecati.
- **Perché è un problema**:
  - Il pre-calcolo è **deterministicamente derivato** da
    `(programma_id, sedi_target_codici)` (dipende solo da dati
    statici del programma + lista sedi). Cachable.
  - Pattern già usato per `dotazione_per_materiale` (cached nello
    scope sessione). Asimmetria con `durata_vuoto_per_coppia`.
- **Fix proposto**: documentare nel docstring del helper "chiamare
  una sola volta per run di `genera_giri`". OPPURE caching a livello
  di `BuilderProgrammaContext` (nuova astrazione MR-PD7b1, entry
  280-281). NON OBBLIGATORIO per chiudere S2 HIGH, ma da NON
  dimenticare.
- **Costo del fix**: 0 min (solo documentazione) per non-cache;
  20-30 min per integrare in BuilderProgrammaContext.

### S3 — LOW — Test #5 "valori plausibili" è asserzione fragile su numeri reali

- **Severità**: LOW
- **Dove**: piano step 5, test 5 "valori plausibili LECCO→CERTOSA
  ~60min OK, TIRANO→CERTOSA ~150min via lookup"
- **Cosa**: il test asserisce numeri specifici (60, 150) che
  dipendono dai **dati reali del programma di test** (es. prog 17
  o fixture). Se l'orario PdE 2026 cambia (es. RFI ricarica un
  treno con +5min su Lecco-Mi.Cle), il test si rompe per nessuna
  ragione di logica.
- **Perché è un problema**:
  - Test fragile = test rumoroso = test ignorato.
  - L'asserzione "via lookup vs fallback" è la cosa importante,
    NON il numero esatto.
- **Fix proposto**: asserzione su **range** (`60 <= durata <= 80`
  per LECCO, `120 <= durata <= 180` per TIRANO) + assert "valore
  != fallback 60" per TIRANO (= dimostra che il lookup ha funzionato).
  In alternativa, fixture sintetica con corse fittizie a durata
  prevedibile (LECCO→CERTOSA 60min hardcoded nella fixture, asserisce
  60 esatto).
- **Costo del fix**: 5-10 min, refactoring asserzioni.

### S4 — LOW — Edge case mancante: `ora_arrivo < ora_partenza` (corsa cross-mezzanotte)

- **Severità**: LOW
- **Dove**: piano step 3, calcolo `(ora_arrivo - ora_partenza) in
  minuti`
- **Cosa**: alcune corse Trenord viaggiano cross-mezzanotte
  (parte 23:50, arriva 00:30 K+1). `ora_arrivo (time)` < `ora_partenza
  (time)` per `time` plain. Se il calcolo è `(ora_arrivo - ora_partenza)`
  diretto in minuti, esce un valore negativo o overflow modulo
  24h.
- **Perché è un problema**:
  - In progetto `feedback_giro_materiale_no_pdc_no_gap` la giornata
    chiude a mezzanotte, quindi corse cross-notte sono rare ma
    esistono (rif. memoria `project_finestra_uscita_deposito`
    "vuoto uscita 01:00-03:00 vietato").
  - Il helper deve gestire questo edge: se `ora_arrivo < ora_partenza`,
    durata = `(24*60 - ora_partenza) + ora_arrivo` in minuti.
- **Fix proposto**: helper interno `_durata_min_tra(ora_p, ora_a)
  -> int` con check cross-notte. Test parametrico con 1 corsa
  cross-mezzanotte (es. partenza 23:30, arrivo 00:15, atteso
  45 min).
- **Costo del fix**: 10-15 min (helper + 1 test).

### S5 — LOW — Pre-calcolo non considera la dotazione materiale per stima velocità tipica

- **Severità**: LOW (potenzialmente downgrade a INFO)
- **Dove**: piano step 3, query CorsaCommerciale senza filtro
  materiale
- **Cosa**: la durata X→Y commerciale può essere fatta da ETR526
  (160 km/h max) o ATR125 (90 km/h max) — corse miste sulla stessa
  tratta. Il vuoto rientro userà uno specifico materiale (quello
  del giro). Se la tratta è coperta solo da ATR125 nel programma
  ma il vuoto è ETR526, sottostimo la velocità del vuoto = SOVRA-stimo
  durata = sovra-vincolo prestazione PdC futura (= eccesso di
  cautela, NON bug operativo).
- **Perché è un problema**:
  - Trade-off: aggiungere filtro materiale al lookup = lookup più
    sparse = più miss = più fallback. Probabilmente peggiora il
    risultato netto.
  - Non è un blind spot critico se la mediana è già su tutte le
    corse della tratta.
- **Fix proposto**: NON fixare adesso. Documentare in docstring
  del helper: "lookup mediano su tutte le categorie/materiali della
  tratta; sovra-stima per vuoti su materiali veloci, accettabile
  come margine di sicurezza".
- **Costo del fix**: 0 min (solo doc).

---

## Voto del PIANO

**6/10\* (provvisorio fallback V4 Flash)** — solido come architettura
ma con UN buco strutturale (S1 HIGH nuovo: fallback 60 = bug
originale rimasto per coppie non in PdE).

Scala (rif. severo.md):
- 5-6: funziona ma con debito o blind spot non secondari
- 7-8: solido, qualche miglioramento sostanziale possibile

Motivazione voto 6/10\*:

✅ **Cosa eleva il piano sopra 5/10**:
- Strategia data-driven CorsaCommerciale = scelta architetturalmente
  corretta (+1 punto)
- Lookup diretto + speculare = pragmatismo aderente a vincolo §7
  (+0.5 punto)
- Out-of-scope onesti (parking notte ortogonale, tabella distanze
  over-engineering) = framing corretto NON pattern "raffinabile
  MR-D7" ingannevole entry 284 (+0.5 punto)
- Backward-compat preservata via `dict | None = None` (+0.5 punto)
- Side-fix S1 MED gratis incluso correttamente (+0.5 punto)

❌ **Cosa blocca il salto a 7/10**:
- **-1 punto** S1 HIGH nuovo: fallback 60 quando coppia non in
  PdE = bug originale rimasto in piedi per scenario canonico
  TIRANO→FIO (= proprio quello citato nel finding S2 HIGH entry
  284). Senza fallback geometrico o pessimistico, il piano risolve
  l'80% e lascia il 20% identico al pre-fix. Pigrizia §7 letterale
  se non chiuso.
- **-0.5 punto** S2 MED non-caching → lavoro ridondante per tweak
  iterativi del pianificatore.
- **-0.5 punto** S3 LOW test fragili su numeri reali invece di
  range/fixture sintetica.
- **-0.3 punto** S4 LOW cross-mezzanotte non gestito.

Voto target post-modifica:
- **7/10** se chiudi S1 HIGH (fallback geometrico opzione A o B):
  fix solido, S2 HIGH entry 284 chiuso davvero per tutti i casi.
- **8/10** se chiudi S1 + S2 + S3: piano polished.
- **5/10** se procedi con piano attuale senza modificare fallback:
  finding S2 HIGH entry 284 RIMANE in stato "parzialmente chiuso"
  per coppie non in PdE. Sintomo si sposta ma non sparisce.

**Voto provvisorio** perché AMILCARE V4 Pro non operativo (3
timeout consecutivi confermano pattern entry 248 cronico). Voto
effettivo con V4 Pro probabilmente 5-6/10 (margine ~0.5-1 punto
più severo per profondità).

---

## Raccomandazione concreta

**Modifica il piano: aggiungi fallback geometrico/pessimistico
prima di rilasciare a 60**.

3 modifiche P0 (BLOCCANTI prima di "implementa così"):

**X. Fallback geometrico/pessimistico per miss completo (S1 HIGH)**:
   - Opzione A o B (vedi finding S1 sopra). Preferenza opzione B
     ("corsa più lunga verso direttrice") perché più semplice e
     ricicla `direttrice` campo già esistente.
   - +30-45 min al piano = totale 2-2.5h, dentro soglia §7 morbida.
   - Test #6 nuovo: miss completo → fallback geometrico produce
     valore > 60.

**Y. Modulo dedicato `domain/builder_giro/durata_vuoto.py` invece
di builder.py (domanda 2)**:
   - Helper `costruisci_durata_vuoto_per_coppia(session, programma_id,
     coppie_target) -> dict[tuple[str, str], int]` async, riceve
     `AsyncSession`.
   - Builder.py importa e chiama 1 volta in `genera_giri`.
   - Coerente con pattern già usato per `_carica_sedi_attive_azienda`,
     `carica_dotazione_per_azienda`, `carica_festivita_periodo`.

**Z. Iniezione via `ParamPipelineLineaCentrica` (domanda 3)**:
   - Aggiungi campo `durata_vuoto_per_coppia: dict[tuple[str, str],
     int] | None = None` al dataclass.
   - `traduci_turni_in_giri` legge da `params.durata_vuoto_per_coppia`
     invece che param keyword duplicato.
   - 1 punto di iniezione, simmetrico a `sede_target_per_regola`.

3 modifiche P1 (raccomandate, non bloccanti):

**W. Mediana NON minimo + filtro `is_cancellata=True` (domanda 4)**.
**V. Test 7 invece di 5**: aggiungere edge `is_cancellata` (6.A) +
   fallback geometrico se accetti X (6.C).
**U. Asserzioni range invece di numeri esatti (S3)**.

Side-fix S1 MED (estrarre `SPECIFICITY_WILDCARD: Final[int]`):
include nel MR, **commit separato** dentro il MR per granularità
review.

**Costo realistico totale post-modifiche**: 2-2.5h (= entro soglia
§7 morbida, sopra dura). Se eccede 2.5h → piano sbagliato, semplificare
fallback geometrico a opzione C (warning runtime + dichiarare
limite onestamente) e accettare voto 6/10.

---

## Cosa NON ho controllato

- **AMILCARE V4 Pro indipendente**: 3 timeout `-32001` consecutivi
  in questa sessione (`reason` 3×, brief 4KB → 2KB → 1KB → tutti
  timeout). Pattern entry 248 confermato 6× consecutivi in 3
  giorni: critiche entry 270/275/278/284/285 + questa. Server V4
  Pro saturo cronicamente. Critica fallback V4 Flash dichiarata,
  voto provvisorio con asterisco.
- **Output AMILCARE V4 Flash filtrato**: 3 falsi positivi/over-
  prescription identificati e dichiarati:
  - **F1 V4 Flash "fallback geometrico obbligatorio"**: NON falso
    positivo, valido come finding S1 nuovo HIGH (V4 Flash ha visto
    correttamente, IO non avevo notato pre-AMILCARE).
  - **F4 V4 Flash "≥10 test"**: gold-plating, ridotto a 7 (5
    originali + 6.A `is_cancellata` + 6.C fallback geometrico se
    accetti S1).
  - **F5 V4 Flash "dict[tuple[str,str],int] non JSON-serializable
    per BuilderResultResponse"**: tecnicamente vero ma irrilevante
    perché `ParamPipelineLineaCentrica` è dataclass pure-domain
    NON DTO API. Falso positivo per il caso d'uso.
  - **F-altri V4 Flash "corse 'i' filtra"**: falso positivo, le
    corse 'i' sono già nel PdE come commerciali (memoria
    `feedback_pde_periodicita_verita`), non vanno filtrate.
  - **F-altri V4 Flash "multi-hop X→Z+Z→Y"**: falso positivo,
    vuoto rientro è singola corsa materiale non spezzettata, scope
    MR-D7+.
- **Verifica empirica TIRANO→FIO durata reale**: ho stimato ~150min
  da memoria progetto (~190km × velocità tecnica vuoto ~75 km/h
  + sosta 10min). NON ho fatto query DB su prog 17 per cercare
  corse TIRANO→Mi.Cle e calcolare durata mediana (== il punto del
  piano). Se il dato reale diverge da 150min significativamente
  (>20%), il finding S3 LOW va riformulato. Per il finding S1 HIGH
  l'argomento regge a prescindere dal numero esatto perché TIRANO→CERTOSA
  (proxy commerciale FIO) probabilmente non esiste nel programma
  → lookup miss → fallback 60 invariato.
- **Stima costo helper geometrico opzione B**: ho stimato 30 min
  ma non ho profilato (es. la query "corsa più lunga verso
  direttrice" potrebbe richiedere subquery, non così banale). Se
  in implementazione esce 1h, totale piano = 3h → fuori soglia
  §7 dura → o opzione C (warning) o piano andrà splittato in MR-S2
  + MR-S2-bis.
- **Verifica `BuilderProgrammaContext` cache surface (S2 MED)**:
  ho citato BuilderProgrammaContext da memoria entry 280-281 (MR-PD7b1)
  ma NON ho verificato se ha già una struttura per cache durate.
  La modifica W al piano (cache) può essere più o meno banale a
  seconda dello stato attuale di BuilderProgrammaContext.
- **Lista coppie target plausibili per pre-calcolo**: il piano
  step 3 dice "per ogni coppia (X, Y) plausibile rientro" ma non
  specifica come si calcola la lista. Probabilmente: `set((corsa.codice_destinazione,
  stazione_collegata_per_sede[regola.localita_codice]) for ...)`.
  NON ho verificato la cardinalità, potrebbe essere 50-200 coppie
  per programma grande, gestibili.

---

## Aderenza al METODO-DI-LAVORO

1. **Diagnosi prima di azione**: ✅ il brief PIANO ha pre-verificato
   i pre-requisiti dati (km_tratta + min_tratta + velocita_max_kmh
   esistono nel modello), entry 284 dichiara apertamente la
   diagnosi del bug, fonte univoca CorsaCommerciale identificata.
   Pattern R-PROC-4 (DB-first) applicato preventivamente al piano
   stesso. Buona aderenza.
2. **Numeri non ipotesi**: ✅ il brief cita LECCO→CERTOSA ~80km
   (60min plausibile), TIRANO→CERTOSA ~190km (150min realtà).
   Numeri stimati da memoria, non query DB diretta = ⚠️ sub-aderenza
   (non da query DB ma da memoria progetto, comunque concrete).
3. **Un passo alla volta**: ⚠️ il piano include side-fix S1 MED
   gratis. Pattern accettabile (vedi domanda 7 sopra) ma vincolo:
   commit git separato dentro MR per granularità.
4. **Ammettere l'errore**: N/A (piano nuovo, non correzione di
   precedente).
5. **Verifica prima del commit**: N/A pre-impl, ma test plan ben
   strutturato (5 → raccomandato 7).
6. **Preservare non distruggere**: ✅ signature `dict | None = None`
   preserva backward-compat completa per i 5 test MR-D6 esistenti.
   Buona aderenza.
7. **Costanza nel tempo**: ⚠️ MISTO. Il piano CHIUDE finalmente
   S2 HIGH entry 284, MA solo parzialmente (vedi finding S1 nuovo
   "fallback 60 = bug originale rimasto"). Pattern ricorrente:
   "chiudo l'80% del finding e lascio il 20% per MR-X+1". Stesso
   pattern critica entry 284 sui 4/11 residui multi-giornata (si
   spostano da MR-D6 a MR-D7) e xfail strict che si spostano di
   MR in MR.

---

## Tracciabilità

- **Brief AMILCARE V4 Pro tentato 3× con `mcp__amilcare__reason`**
  (4KB → 2KB → 1KB → tutti timeout `-32001`). Pattern entry 248
  confermato 6× consecutive in 3 giorni: critiche entry
  270/275/278/284/285 + questa. Server V4 Pro saturo cronicamente.
- **Fallback su AMILCARE V4 Flash** (`mcp__amilcare__code`,
  V3-chat) operativo: 1 invocazione riuscita con brief ~700 byte,
  output ~500 parole strutturato + reasoning trace. Tempo risposta
  ~10s.
- **Output V4 Flash filtrato**:
  - F1 (data-driven vs geometrico) → adottato come finding S1 HIGH
    nuovo "fallback geometrico obbligatorio". V4 Flash ha visto
    correttamente.
  - F2 (modulo dedicato `durata_vuoto.py`) → adottato come
    raccomandazione Y.
  - F3 (`ParamPipelineLineaCentrica`) → adottato come raccomandazione Z.
  - F4 (mediana) → adottato come raccomandazione W (mediana, non
    minimo).
  - F5 (≥10 test) → over-prescription, ridotto a 7.
  - F-altri (corse 'i', multi-hop) → falso positivi dichiarati.
  - F-altri ("dict non JSON-serializable") → falso positivo per
    il caso d'uso (dataclass pure-domain non DTO).
- **Voto V4 Flash 5/10** vs **mio voto fallback 6/10\***: mio
  voto +1 vs V4 Flash perché V4 Flash punisce il fallback 60 con
  -2 (= bocciato come "criminale"), io riconosco che il piano è
  comunque architetturalmente corretto e il fallback è una
  decisione discutibile NON un bug strutturale. Margine atteso V4
  Pro: ulteriori -0.5/-1 punto per profondità.
- **Critiche precedenti citate**:
  - `docs/critiche/SPRINT-8.2-MR-D5h-bis+MR-D6-codice-committato.md`
    (5/10\* entry 284, finding S2 HIGH "60 min hardcoded fragile"
    è proprio l'origine di questo piano)
  - `docs/critiche/SPRINT-8.2-PIANO-ALPHA-RETROSPETTIVA.md`
    (5/10\* entry 285, pattern recidiva "lezione presa, non chiusa")
  - `docs/critiche/SPRINT-8.2-MR-D5h-DUAL-codice-committato.md`
    (6/10\* entry 278, R-PROC-4 origine)
- **Pattern di critica del ciclo Sprint 8.2 → 8.3**:
  4/10 → 5/10 → 6/10\* → 5/10\* → 5/10\* → 6/10\* (questa). Dopo
  6 critiche, voto medio resta sotto "solido" 7/10. NINO sta
  migliorando il pattern di chiusura ma non abbastanza per saltare
  il tetto strutturale 6/10. La modifica raccomandata X (fallback
  geometrico) è il primo punto in cui il salto a 7/10 sarebbe
  realistico.
