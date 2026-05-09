# Critica preventiva SEVERO — PIANO Sprint 8.2 MR-PD7b §11.4 riposo settimanale

**Data**: 2026-05-09
**Commit / range**: N/A (critica PRE-implementazione del piano)
**Entry TN-UPDATE**: futura (post-3a entry 277, post-3b entry 279)
**Piano criticato**: `docs/piani/SPRINT-8.2-MR-PD7b-piano.md` (186 righe)
**Motore usato**: **NINO puro (fallback dichiarato)** — AMILCARE V4 Pro
**3 timeout consecutivi** su brief 3.5KB → 1.8KB → 1KB. Pattern entry 248
non ha sbloccato la situazione: il servizio MCP DeepSeek risulta saturo
in questa giornata (4° critica di seguito senza AMILCARE; vedi anche
critica 3b PIANO sopra in indice). **VOTO PROVVISORIO, da rifare con
AMILCARE operativo** (entry 248 documenta margine ~1-2 punti più severo
con motore esterno indipendente). Bias auto-compiacenza dichiarato e
parzialmente compensato dalla disciplina di trovare almeno 5 finding
HIGH/CRITICAL e dal tono ipersevero compensativo.

---

## Sintesi (3 righe max)

Il piano §11.4 è **decorativo**: il validatore strutturale senza date
concrete, su cicli reali Trenord 1-17gg con varianti calendariali
F/L/V interleaved, non catturerà mai violazioni vere — produrrà 0
errori per costruzione e darà falsa sicurezza che §11.4 sia rispettata.
Inoltre **§11.5 (riposo intraturno 11/14/16h, RIGIDA pari a §11.4)
è prerequisito logico saltato**, e la formula wrap-around inventa una
variabile fantasma `n_giornate_attive_nella_settimana_corrente`. Voto
**3/10** — bocciato per riapertura piano.

## Cosa funziona

- Decisione di criticare il piano PRIMA del codice (rispetto regola
  memoria `feedback_severo_sempre_su_piani.md`). ✅
- Riconoscimento esplicito che la validazione persona-specifica è
  out-of-scope (modello `AssegnazionePersonaTurnoData` davvero non
  esiste, scope MR-PD7+). Scope cut **legittimo**. ✅
- Auto-domande del piano (5 punti per SEVERO) corrette per copertura:
  NINO ha già dubitato di sé sui 5 punti chiave, è la cosa giusta
  da fare PRIMA di codare. ✅
- Stima 4h plausibile **se il piano fosse fattibile**, ma il problema
  qui non è il costo — è la sostanza.

## Cosa si poteva fare meglio

### S1 — CRITICAL — Validatore decorativo: 0 violazioni catturate per costruzione

- **Severità**: **CRITICAL**
- **Dove**: piano §"In scope MVP — opzione γ" + §"Architettura proposta"
  (riposo_settimanale.py funzione `valida_riposo_settimanale`)
- **Cosa**: il validatore opera su `drafts: list[GiornataPdcDraft]`
  che NON ha date concrete, e usa proxy `≥48h interi` invece di
  enumerare i giorni solari veri (perché `enumera_date_giornata`
  manca, S4 TODO documentato in `registro_vetture.py:17/45/156`
  e `deposito_first.py:541`). Sui 54 turni reali Trenord 2026
  (`data/turni_materiale_2026_dump.json`), distribuzione cicli:
  7×10gg, 6×7gg, 6×5gg, 5×9gg, 5×12gg, fino a 17gg, mediana ~8gg.
  Le N giornate del TurnoPdc sono giornate-LOGICHE (variante F vs LV
  vs Si eff. specifiche date — vedi modello PDF Trenord 1134
  citato in `project_refactor_varianti_giri_separati_TODO.md`),
  NON giornate calendariali consecutive. Quindi:
  - Per ciclo 10gg con varianti `LV 1:5 + F + LV 6 escl. + Si eff. 21-28/3`,
    le 10 "giornate" del TurnoPdc rappresentano DECINE di date concrete
    diverse a seconda del periodo del calendario.
  - Calcolare un wrap-around `(ciclo_giorni - n_giornate_attive)*24*60`
    presupponendo che le 10 giornate seguono in 14 giorni solari
    (5+2+5+2) è **un'astrazione che non corrisponde mai alla realtà**.
  - Le coppie consecutive (G1,G2)...(G10,G1') che il validatore itera
    NON sono sempre adiacenti calendarialmente (giornata 6 può cadere
    su F e venire saltata; giornata 10 può cadere su Si eff. specifica
    fuori sequenza).
- **Perché è un problema**: il validatore produrrà 0 violazioni perché
  la "logica strutturale" trova sempre una sequenza valida nei drafts
  (gap orari coerenti per costruzione del builder). Il test verde
  diventa **falso positivo silenzioso**: §11.4 è formalmente
  "implementata" ma di fatto NON viene mai violata né rispettata —
  perché non viene mai testata sui dati che contano (le date concrete
  per variante). Pattern già visto in critica MR-PD3 RE-CRITICA AMILCARE
  (3/10 finding A1: regole "implementate" senza universo applicabile
  reale = peggio di non implementarle, perché chiudono il TODO ma
  lasciano il bug latente).
- **Fix proposto**: due alternative. (α) **Rimandare MR-PD7b** dopo
  helper `enumera_date_giornata` (S4 SEVERO) — il vero validatore va
  su date concrete enumerate per variante, non su drafts logici. Costo
  helper enumera_date stimato 3-4h + validatore §11.4 vero su date 2-3h
  = totale 5-7h. (β) Riscrivere il piano come **"validatore minimale
  preliminare + log di violazioni potenziali su date NON ancora note"**
  — emette warning "RIPOSO_SETTIMANALE_INDETERMINATO: gap 60h tra G7
  e G1' del ciclo 10gg, verificabile solo con date concrete" invece di
  dare verdetto verde/rosso. Costo simile, ma onesto sul perimetro.
- **Costo del fix**: α = 5-7h, β = 3-4h. Entrambi superano la stima 4h
  del piano corrente, ma producono valore reale. **Lo status quo (4h
  di codice decorativo) è negativo**, non neutro.

### S2 — CRITICAL — §11.5 (riposo intraturno 11/14/16h) è prerequisito logico saltato

- **Severità**: **CRITICAL**
- **Dove**: piano §"In scope MVP" non menziona §11.5; codice
  `builder.py:1074` ha solo `riposo_min=0` placeholder; NORMATIVA-PDC
  §11.7 elenca §11.5 fra le 2 regole RIGIDE del ciclo (insieme a §11.4).
- **Cosa**: §11.4 (settimanale 62h+2gg) e §11.5 (intraturno 11/14/16h)
  sono **entrambe RIGIDE** e nascono dalla stessa famiglia "Ciclo
  settimanale e contesto turno" (NORMATIVA-PDC §11). Il piano implementa
  la seconda (settimanale) saltando la prima (intraturno). È
  **logicamente invertito**: per validare che ci siano 62h tra fine
  giornata 7 e inizio giornata 1 della settimana dopo, devo prima
  garantire che ci siano 11/14/16h tra giornata 1→2, 2→3, ..., 6→7.
  Senza §11.5 il validatore §11.4 dice "ok ciclo settimanale rispettato"
  mentre il PdC potrebbe avere violazioni intraturno **inammissibili**
  e mai segnalate. Esempio concreto: ciclo 5gg con G3 fine 23:00 e G4
  inizio 06:00 = 7h (≪14h richieste post-fine 00:01-01:00) —
  validatore §11.4 lo trova "compatibile" perché c'è poi un wrap finale
  di 62h, ma il turno è illegale per §11.5.
- **Perché è un problema**: NINO sta proponendo MR-PD7b come "ULTIMO MR
  del piano α" e dichiara `chiude tutto il piano non fermarti mai`.
  Chiudere il piano α mentre §11.5 RIGIDA è ancora `riposo_min=0`
  placeholder = piano α NON CHIUSO con fanfara. La memoria `feedback_no_errori.md`
  ("correttezza > velocità") si applica letteralmente: §11.5 è una
  regola di correttezza primaria del dominio, non un nice-to-have.
- **Fix proposto**: o (γ) MR-PD7b implementa **prima** §11.5 (più
  semplice meccanicamente: confronta `fine_prestazione[i]` vs
  `inizio_prestazione[i+1]` con discriminante `is_notturno` e `is_cap_notturno`,
  costo ~2h con 6-8 test, sblocca il `riposo_min=0` placeholder), poi
  §11.4; o (δ) MR-PD7b implementa **solo** §11.5 e §11.4 va in MR-PD7c
  separato dopo `enumera_date_giornata` (vedi S1 fix α). La δ rispetta
  il "chiudi un MR alla volta" di METODO-DI-LAVORO regola 3.
- **Costo del fix**: γ = 2h §11.5 + 4h §11.4 originale = 6h ma
  inverte priorità. δ = 2h §11.5 in MR-PD7b + rimando MR-PD7c. Nessuna
  delle due chiude completamente il piano α come da promessa
  "non fermarti mai", ma entrambe rispettano la regola §7 NIENTE PIGRIZIA
  (residui solo se motivazione oggettiva = manca helper date concrete).

### S3 — HIGH — Variabile fantasma `n_giornate_attive_nella_settimana_corrente`

- **Severità**: HIGH
- **Dove**: piano riga 134 e §"Cose da decidere prima del codice" punto 1.
- **Cosa**: la formula wrap-around proposta è
  `(ciclo_giorni - n_giornate_attive_nella_settimana_corrente)*24*60 -
  fine_prestazione_G_N + inizio_prestazione_G_1 (settimana dopo)`.
  Ma `n_giornate_attive_nella_settimana_corrente` **non esiste** nel
  modello dati (`grep` su `backend/src/colazione/domain/builder_pdc/`
  conferma 0 risultati per `n_giornate_attive`, `giornate_attive`).
  Il concetto stesso "giornate attive nella settimana" presuppone di
  sapere su quali date solari ricadano le N giornate, che è il problema
  del S1. NINO ha **inventato un campo che il validatore deve calcolare
  da solo** ma senza specificare come.
- **Perché è un problema**: il piano dichiara "verificato" il modello
  dati al §"Cose verificate" punti 2-4, ma il punto 4 dice "calcolo gap
  usa modulo 24h e somma `(ciclo_giorni - giornate_lavorative_nella_settimana_corrente)*24*60`"
  rinviando di fatto la specifica al codice futuro. È **wishful planning**:
  scrivo "verificato" su un punto che è in realtà la maggior incognita
  del progetto. Pattern già visto in critica MR-PD3 PRE-FIX (4.5/10
  finding S5: "scope dichiarato verificato ma in realtà non testato").
- **Fix proposto**: il piano deve specificare **algoritmicamente** come
  si calcola questa variabile per cicli arbitrari (esempio per ciclo
  9gg: `n_giornate_attive_settimana = ciclo_giorni % 7 = 2`?
  `min(ciclo_giorni, 5)`? `5` fisso assumendo 5+2 weekly?). Per ciclo
  10gg: `10 % 7 = 3`? Oppure `5+5+0`? La risposta varia il wrap-around
  da 12h a 96h. Senza specifica, il validatore può essere scritto in 5
  modi diversi e tutti "passano i test" del piano (perché i test sono
  scritti senza vincoli su questa variabile).
- **Costo del fix**: 1h decisione utente + algoritmica esplicita nel
  piano. Imprescindibile prima di qualsiasi codice.

### S4 — HIGH — Heuristic `ciclo_giorni // 7` sotto-protettivo per cicli lunghi

- **Severità**: HIGH
- **Dove**: piano §"Architettura proposta" e §"Cose da decidere"
  punto 2.
- **Cosa**: per ciclo 10gg → `10 // 7 = 1` riposo settimanale richiesto
  in 10 giornate. Per ciclo 12gg → 1. Per ciclo 14gg → 2. Per ciclo
  17gg → 2. Significa che un ciclo di 12 giornate consecutive con UN
  solo riposo di 62h verrebbe accettato. Realistico? NORMATIVA-PDC §11
  non specifica il numero esatto di riposi per ciclo lungo, ma "settimanale"
  in italiano operativo Trenord significa **"almeno uno ogni 7 giorni
  solari"** non "ogni ciclo solo 1 se il ciclo è lungo". Se il ciclo
  ha 12 giornate spalmate su 14 giorni solari (= 12 lavoro + 2 riposo),
  il PdC fa 12 giornate consecutive = 12 giorni di lavoro effettivo
  senza riposo settimanale → **violazione palese di "settimanale"**.
- **Perché è un problema**: la heuristic `// 7` può autorizzare turni
  che la normativa rifiuterebbe in audit umano. È falso negativo
  garantito sui cicli lunghi (5×12gg + 5×9gg + 3×11gg + 2×17gg + 1×16gg
  + 1×13gg = 17 turni Trenord 2026 con cicli >7gg). Almeno **31% del
  catalogo** rischia false-OK con questa heuristic.
- **Fix proposto**: regola corretta richiede "almeno 1 riposo settimanale
  ogni 7 giornate consecutive senza riposo". Algoritmo: scorri il ciclo
  contando giornate consecutive senza gap ≥62h; se conta > 7, violazione
  "manca riposo settimanale". Costo ~30 min in più del `// 7`. Aggiungere
  test esplicito ciclo 12gg con un solo riposo a metà.
- **Costo del fix**: 30 min algoritmica + 1 test scenario = 1h totale.

### S5 — HIGH — Le 10 scenari di test mancano i casi reali Trenord

- **Severità**: HIGH
- **Dove**: piano §"Test" lista 10 scenari (5gg, 7gg, 14gg, edge case).
- **Cosa**: i 10 test coprono cicli 5/7/14gg ok/ko + helper. **Manca**:
  - Ciclo 10gg (7 turni Trenord, distribuzione massima)
  - Ciclo 12gg (5 turni)
  - Ciclo 9gg (5 turni)
  - Ciclo 17gg (2 turni — caso di stress massimo)
  - Test con FR (`fr_giornate` aggiunte da `aggiungi_dormite_fr` in
    `deposito_first.py:581`): le dormite FR aggiunte modificano la
    sequenza dei drafts? Il validatore ne tiene conto? Non chiaro
    dal piano.
  - Test con turni-RAMO-SPLIT (`builder.py:920`): TurnoPdc-ramo-split
    ha 1 sola giornata, niente FR — come si applica §11.4 a un turno
    di 1 giornata? `1 // 7 = 0` riposi richiesti = test verde fasullo,
    perché un PdC che lavora 1 giornata e basta NON ha turno settimanale,
    deve essere skippato esplicitamente.
- **Perché è un problema**: i test passano sui casi "didattici" 5/7/14
  ma sono casi di laboratorio. Il vero test è "lanci builder su prog 17
  reale Trenord 2026 e vedi cosa succede sui 54 turni con cicli misti".
  Non c'è nemmeno un integration test su dati reali nel piano. Pattern
  ricorrente § criticato (entry 270 root cause "pipeline solo
  mock-tested" → bug latenti al primo run reale).
- **Fix proposto**: aggiungere 4-6 test su cicli realistici (10/12/17/9gg)
  + 2 test FR + 1 test ramo-split skip + 1 integration test su prog 17
  reale (o fixture estratta).
- **Costo del fix**: 1.5h test aggiuntivi + 30 min integration = 2h.

### S6 — MED — Definizione "giorno solare intero" 00:00-23:59 vs interpretazione normativa

- **Severità**: MED
- **Dove**: piano §"Architettura proposta" helper
  `_giorni_solari_interi_in_finestra`.
- **Cosa**: NORMATIVA-PDC §11.4 dice "almeno 2 giorni solari interi"
  ma non specifica COME si misurano. Il piano assume "00:00-23:59
  consecutivi dentro la finestra di riposo". Interpretazione
  alternativa: "2 calendar days inclusi nella finestra" (anche se
  non sono interi 00:00-23:59 ma il PdC è sostanzialmente fermo in
  quel giorno). Esempio normativa: "ultimo turno termina sabato 14:00,
  riposo fino martedì ~04:00, include domenica e lunedì interi". Qui
  domenica e lunedì SONO interi 00:00-23:59 nel riposo (sabato 14:00-24:00
  + dom 24:00 + lun 24:00 + mar 04:00 = 62h, dom e lun interi). Ma
  esempio ambiguo: "se l'ultimo turno finisse domenica 10:00, le 62h
  si chiuderebbero mercoledì ~00:00, ma i due giorni solari interi
  (lunedì e martedì) ci stanno dentro — regola rispettata". Qui
  domenica 10:00-24:00 + lun 24:00 + mar 24:00 + mer 00:00 = 62h, lun
  e mar interi. Ok la lettura strict 00:00-23:59 funziona — in entrambi
  gli esempi.
- **Perché è un problema**: la lettura strict è la più severa, va bene.
  Ma il piano la dichiara senza riferimento normativo esplicito. Va
  citata in commento di codice.
- **Fix proposto**: aggiungere docstring esplicita "interpretazione strict:
  giorno solare intero = 00:00:00 a 23:59:59 nella timezone locale del
  PdC, secondo §11.4 esempi normativa". Risolto in 5 min.
- **Costo del fix**: 5 min.

### S7 — MED — Persistenza in `violazioni_ciclo_extra` vs nuovo campo dedicato

- **Severità**: MED
- **Dove**: piano §"In scope MVP" punto finale + §"File modificati"
  `deposito_first.py` riga ~590 (riga corretta del piano: il piano
  cita 579 ma la chiamata vera a `_verifica_unicita_intra_turno` è
  alla riga **590**, refuso).
- **Cosa**: il piano dice "propaga come `violazioni_ciclo_extra` al
  persister + finisce in `generation_metadata_json.riposo_settimanale_violazioni`".
  Il campo `violazioni_ciclo_extra` è già un cestino misto (FR cap +
  unicità intra-turno §15 dal MR-PD7a entry 274 + ora §11.4). Il
  consumer downstream (UI Pianificatore PdC, MR-PD7c?) deve poter
  filtrare per categoria. Mescolare 3 famiglie di violazioni nello
  stesso array porta a string-parsing fragile a valle (anti-pattern
  S1 critica MR-PD-FIX-SEVERO 3b).
- **Perché è un problema**: non blocca MVP, ma pagamento tecnico è
  sicuro al 100% (=NEXT MR farà refactor). Meglio chiudere subito.
- **Fix proposto**: o categorizzare le violazioni come tuple
  `(categoria: str, descrizione: str)` invece di solo `str`, oppure
  separare 3 array distinti in extra_metadata: `fr_cap_violazioni`,
  `unicita_violazioni`, `riposo_settimanale_violazioni` (gli ultimi
  due già esistono come chiavi separate in `extra_metadata`,
  vedi `deposito_first.py:608-610`). Coerente con pattern attuale.
- **Costo del fix**: 30 min.

### S8 — LOW — Refuso riga 579 vs 590

- **Severità**: LOW
- **Dove**: piano §"File modificati" `deposito_first.py` riga 579.
- **Cosa**: la riga 579 del file attuale è in mezzo a `GiroVuotoError`
  raise. La chiamata vera a `_verifica_unicita_intra_turno` è alla riga
  590. Refuso minore ma indica lettura imprecisa del file (NINO ha
  citato a memoria invece di rileggere).
- **Fix proposto**: aggiornare riferimento a riga 590.
- **Costo del fix**: 1 min.

## Debito tecnico segnalato

Il piano §"Out of scope (residui legittimi)" elenca 4 residui:
1. ✅ Validazione persona-specifica (modello mancante = legittimo §7)
2. ✅ Validazione aggregata cross-turno per PdC (stesso modello = legittimo)
3. ❌ §11.2 primo giorno post-riposo non mattino (PREFERENZIALE §11.7)
4. ❌ §11.3 ultimo giorno pre-riposo finisce ≤ 15:00 (PREFERENZIALE §11.7)

**Punti 3 e 4** sono PREFERENZIALI per §11.7, scope futuro legittimo.
✅ Marcatura corretta.

**Residuo non dichiarato dal piano ma critico (= pigrizia §7)**:
- ❌ §11.5 riposo intraturno 11/14/16h: **RIGIDA** per §11.7, non
  implementata (`riposo_min=0` placeholder), e il piano la SALTA senza
  spiegare perché. Vedi S2.
- ❌ Helper `enumera_date_giornata`: dichiarato S4 SEVERO TODO da MR-PD3
  (entry 276), e il piano §11.4 lo aggira con proxy '≥48h' senza
  motivazione oggettiva. La motivazione "lo aggiriamo per MVP" non basta
  perché senza date concrete il validatore §11.4 non funziona (S1).
  Helper costo stimato 3-4h, scrivibile ora. Non è una migration
  invasiva, è un puro modulo di logica calendariale che lo Sprint 8.2
  ha ripetutamente rimandato.

## Aderenza al METODO-DI-LAVORO

1. **Diagnosi prima di azione** — ❌ NO. Il piano salta la diagnosi
   sulla distribuzione cicli reali Trenord (54 turni, mediana 8gg,
   max 17gg) — le scelte (heuristic `//7`, ciclo 5+2 esemplificativo)
   sono fatte sul caso didattico non sul caso reale. Vedi S4.
2. **Numeri non ipotesi** — ❌ NO. Il piano non cita numeri reali
   (distribuzione cicli, conteggio turni con cicli >7gg). Vedi S4-S5.
3. **Un passo alla volta** — ❌ NO. Il piano vuole chiudere "tutto
   il piano α" in un MR senza affrontare §11.5 prerequisito. Vedi S2.
4. **Ammettere l'errore** — N/A (pre-implementazione).
5. **Verifica prima del commit** — N/A (pre-implementazione). Ma il
   piano non prevede integration test su dati reali. Vedi S5.
6. **Preservare non distruggere** — N/A.
7. **Costanza nel tempo** — ⚠️ il pattern "validatore strutturale
   senza dati reali" è già stato criticato in entry 270 (pipeline solo
   mock-tested → bug al primo run reale), entry 275/276 (DB-first non
   eseguita) e MR-PD3 RE-CRITICA. La R-PROC-1 (smoke 2-3 entità
   reali pre-deploy 1° strangler) **andrebbe applicata anche a
   validatori normativi**, non solo a builder.

## Voto complessivo

**3 / 10** — bocciato per riapertura. Validatore decorativo (S1) +
prerequisito saltato (S2) + variabile fantasma (S3) = piano non
producibile in stato attuale.

**Voto target post-modifiche per arrivare a 7/10**:

Modifiche obbligatorie:
1. Decidere fra fix S1-α (rimanda MR-PD7b dopo `enumera_date_giornata`)
   o S1-β (riscrivi come "warning indeterminato"). NINO + utente.
2. Decidere fra S2-γ (§11.5 prima di §11.4 in MR-PD7b) o S2-δ
   (§11.5 only in MR-PD7b, §11.4 in MR-PD7c separato). NINO + utente.
3. S3: specificare algoritmica `n_giornate_attive` per cicli arbitrari
   con esempi numerici 5/7/9/10/12gg.
4. S4: sostituire `// 7` con conteggio "giornate consecutive senza
   gap ≥62h" + test ciclo 12gg con 1 riposo a metà.
5. S5: aggiungere 4-6 test cicli reali (10/12/17/9gg) + 2 FR + 1
   ramo-split skip + 1 integration su fixture reale.

Modifiche raccomandate:
6. S7: separare violazioni in 3 array distinti, no cestino misto.
7. S8: refuso riga 579 → 590.

## Cosa NON ho controllato

- ❌ AMILCARE V4 Pro **non disponibile**: 3 timeout `-32001` su
  `mcp__amilcare__reason` con brief 3.5KB → 1.8KB → 1KB. Pattern entry 248
  brief snello NON ha funzionato in questa sessione (server saturo,
  4° critica consecutiva senza AMILCARE — vedi indice).
- ❌ Voto effettivo con AMILCARE probabilmente 2-3/10 (margine
  ~1 punto più severo, storico entry 248). NINO sta proponendo il
  piano = bias auto-compiacenza inevitabile, parzialmente compensato
  dalla disciplina di trovare 5 finding HIGH/CRITICAL e dal tono
  ipersevero.
- ❌ Non ho verificato se la riformulazione "warning indeterminato"
  (S1-β) sia compatibile con UI Pianificatore PdC esistente (MR-PD6
  parte 1 entry 268 e parte 2 entry 272 hanno introdotto banda
  notturna + label stazioni acronimi, ma non ho controllato come
  consumano `violazioni_ciclo_extra` dal frontend).
- ❌ Non ho consultato un giuslavorista o esperto Trenord sulla
  lettura precisa di "settimanale" per cicli >7gg (S4). La mia lettura
  "almeno 1 ogni 7 giornate consecutive" è la più severa
  ragionevolmente; potrebbe essere meno o più rigida.
- ❌ Non ho letto in profondità `aggiungi_dormite_fr` per capire come
  le dormite FR modifichino la sequenza dei drafts e l'effetto su
  `valida_riposo_settimanale`. S5 segnala il dubbio ma non ha verifica.
- ❌ Non ho verificato il comportamento del validatore su TurnoPdc-
  ramo-split (1 sola giornata): `1 // 7 = 0` ma serve skip esplicito
  con motivazione documentata (S5).

---

**Raccomandazione operativa per NINO + utente**:

Bocciatura del piano corrente. Decisione utente richiesta su:

1. **Sequenza MR**: §11.5 prima di §11.4 (path γ in S2) o solo §11.5
   in MR-PD7b + §11.4 dopo `enumera_date_giornata` in MR-PD7c (path δ)?
   Path δ è più rigoroso ma non chiude il piano α come da promessa
   "non fermarti mai". Path γ chiude metà del piano (§11.5) e lascia
   §11.4 a MR-PD7c.
2. **Helper `enumera_date_giornata`**: scope MR-PD7b? MR-PD7c separato?
   Se separato, MR-PD7b non può fare §11.4 vera (solo proxy decorativo
   = bocciato S1).
3. **Cicli >7gg**: il modello "1 riposo per ciclo se ciclo <14gg"
   è accettabile per Trenord o serve "1 riposo ogni 7 giornate
   consecutive"? Decisione di dominio.

Costo realistico totale per fare bene §11.4 + §11.5: **8-12h**, non
4h del piano. È accettabile alla luce della promessa "chiudi tutto il
piano α" o serve splittarlo in MR-PD7b (§11.5 only) + MR-PD7c
(`enumera_date_giornata` + §11.4 vera) + MR-PD7d (integration su prog
17 reale)?

Fino a decisione utente sui 3 punti sopra: **MR-PD7b sospeso**.
