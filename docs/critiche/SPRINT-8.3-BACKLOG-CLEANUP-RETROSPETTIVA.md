# Critica SEVERO — Retrospettiva Sprint 8.3 backlog cleanup post-piano α

**Data**: 2026-05-10
**Commit / range**: `6606492..4d83dce` (7 commit, entry 287-293)
**Entry TN-UPDATE**: 287, 288, 289, 290, 291, 292, 293
**Motore usato**: AMILCARE V4 Pro via `mcp__amilcare__reason` — **SÌ**, brief
~600 byte al 3° tentativo (i primi 2 timeout `-32001`, server saturo cronico).
Orchestratore SEVERO eseguito **manualmente da NINO** (subagent custom non
bootato in sessione corrente — pattern entry 248).

## Sintesi

Lo Sprint 8.3 chiude **tutti i 7 finding aperti dello Sprint 8.2** (S3, S4,
S5, S6, S7, S8, S9, S10) + smoke prod end-to-end con turno 119 persistito.
+96 test PdC (53 → 149) + 5 nuovi S8 = 154 test, mypy/ruff clean, zero
regressioni introdotte. Ma **AMILCARE conferma 1 finding HIGH-CRITICAL
nascosto dietro un commento fuorviante** (S4 from_db wild-card operatore =
0 esclusioni effettive sul filtro live_arturo). Voto **3/10** AMILCARE
(vs 5/10 fallback NINO Sprint 8.2 ⇒ 4/10 AMILCARE: stessa traiettoria
"NINO si auto-compiace, AMILCARE smaschera").

## Cosa funziona

- **Backlog precedente realmente chiuso**: nessun finding HIGH/MED/LOW
  dello Sprint 8.2 lasciato aperto. SEVERO 8.2 entry 285 → tutti
  riconducibili a un commit Sprint 8.3 con riferimento esplicito (S3
  → entry 287, S4 → 288, ecc.). Tracciabilità S2-S10 → commit-message →
  entry TN-UPDATE è impeccabile.
- **S7 ha trovato un bug critico PRIMA del prod** (entry 289): la sintassi
  `TurnoPdc.generation_metadata_json["giro_materiale_id"].astext` di S4
  generava `ProgrammingError` Postgres. S7 l'ha esercitata in test
  integration → fix `func.jsonb_extract_path_text` applicato. Senza S7,
  primo run reale `genera_turni_pdc_deposito_first` in prod sarebbe
  fallito con ProgrammingError. **Esattamente il valore previsto da
  SEVERO 8.2 entry 285** ("la copertura unitaria è coperta, l'integrazione
  è scoperta"). Pattern positivo da consolidare: ogni MR backend con SQL
  custom va con ≥1 test integration su DB reale.
- **S3 anti-ricorsione meta**: il check `check_alembic_revisions.py`
  copre l'incidente entry 283 + 3 check generici (down dangling, single
  head, no cycle). 13 test + smoke 45 migration reali. È il prototipo
  del pattern "lezione meta diventa script eseguibile" — vale per tutti
  i futuri incidenti.
- **S8 refactor strisce**: il nuovo formato `striscia_consecutiva_da_G{i}_a_G{j}:{L}_giornate`
  preserva semantica (substring `no_in_7gg` mantenuto = test backward-compat
  passano). 5 nuovi test in `TestStrisceContinue` coprono i 4 scenari
  chiave (21gg, 14gg, 8gg, 2 strisce, sotto-soglia 6gg). È il refactor
  esemplare di questo Sprint.
- **S9 parser DSL**: 28 test + 7 classi + integration con
  `enumera_date_giornata`. Risolve il problema "fallback sovra-include
  > 50% giornate Trenord reali" sollevato da SEVERO 8.2 S9. Documenta
  esplicitamente i pattern non coperti (entry 290 §Limitazioni) =
  onesto su debito futuro.
- **Numerazione TN-UPDATE coerente**: 287 → 288 → ... → 293 senza salti
  (modulo "implicit" entry 293 da 1bb200d, vedi S5 sotto).

## Cosa si poteva fare meglio

### S1 — Bug semantico cross-modulo `from_db` wild-card operatore = 0 esclusioni effettive

- **Severità**: HIGH-CRITICAL
- **Dove**:
  - `backend/src/colazione/domain/builder_pdc/registro_vetture.py:230-241`
    (popolamento `assegna(operatore=None)` in loop `from_db`)
  - `backend/src/colazione/integrations/live_arturo.py:301` (filtro
    `if (cand.numero, cand.operatore) in esclusi: continue`)
- **Cosa**: il match registro→filtro è una **tupla stretta**:
  ```python
  # registro_vetture.py:237-241 (from_db):
  registro.assegna(
      numero_treno=numero,
      operatore=None,  # wild card S4 TODO
      data_operativa=None,
  )
  # live_arturo.py:301:
  if esclusi is not None and (cand.numero, cand.operatore) in esclusi:
      continue
  ```
  `cand.operatore` reale è `"TN"` o `"TILO"` (popolato da
  `_estrai_candidato`); `esclusi` arriva da `numeri_da_escludere` =
  `frozenset[(numero, None)]`. **Tupla `(n, "TN")` non matcha mai
  `(n, None)`**. Risultato: `from_db` carica N vetture nel registro,
  ma il filtro a valle ne esclude **0**. Il commento `registro_vetture.py:11-12`
  dichiara "match strict (None matcha solo None)" — coerente con
  il comportamento `is_assegnata` quando il chiamante PASSA operatore
  reale, ma **nel caso `from_db` il registro è popolato con `None` e
  i candidati reali hanno operatore reale → asimmetria silente**.
- **Perché è un problema** (AMILCARE conferma HIGH-CRITICAL):
  1. **L'invariante semantica del registro è violata**. Il commit message
     entry 288 dice "Sprint 8.3 S4 chiude pigrizia §7 — query reale
     filtra programma_id". È vero solo per il `programma_id`. Ma sul
     match cross-PdC §15 (= la ragione d'essere del registro vetture),
     `from_db` è funzionalmente un no-op.
  2. **Smoke prod entry 293 NON l'ha esercitato**. Il giro 2094 chiude
     a S01640=FIORENZA=deposito → Caso A short-circuit, `risolvi_rientro`
     mai chiamato → registro mai consultato → bug invisibile. Il prossimo
     turno reale con chiusura ≠ deposito attiverà il filtro a vuoto e
     nessuno se ne accorgerà finché non emergerà un doppione cross-PdC
     in produzione (= debug di settimane).
  3. **Falsificazione del commento doc**: `registro_vetture.py:148-163`
     dichiara "MVP wild card... sovra-strict ma sicuro (no doppioni)".
     **È falso**: con operatore=None la wild-card su data NON compensa
     l'asimmetria operatore. La sicurezza promessa non c'è. Il commento
     induce in errore qualsiasi senior che leggesse il codice.
  4. **Test del residuo §7 CLAUDE.md violato**: il fix è scrivibile
     in <1h (vedi sotto) → era pigrizia mascherata da "scope MR-PD7+".
- **Fix proposto**: 2 strade, scelta utente:
  - (a) **Allineare la wild-card su operatore**: in `live_arturo.py:301`
    cambiare match in:
    ```python
    if esclusi is not None and any(
        cand.numero == num and (op is None or op == cand.operatore)
        for num, op in esclusi
    ):
        continue
    ```
    Coerente col comportamento dichiarato `is_assegnata` (None matcha
    None). Costo: 4 righe + 2 test.
  - (b) **Recuperare operatore da DB in from_db**: aggiungere colonna
    `operatore_treno_vettura` alla migration 0046 (o a una nuova
    migration 0047) + popolarla nel `_inserisci_blocco_rientro` +
    leggerla in `from_db`. Più pulito ma migration grossa = MR a sé.
  - (c) **Documentare onestamente il bug** + cambiare commento riga
    158-163 da "sovra-strict ma sicuro" a "MVP funzionalmente no-op
    finché operatore non è recuperato". Almeno l'onesta semantica.
    Solo cosmetico — il bug resta.
- **Costo del fix**: (a) <1h. (b) MR a sé 4-6h. (c) 5 min ma falsa
  soluzione.

### S2 — Test integration S7 #4 PASSA VACUAMENTE (loop su 0 righe)

- **Severità**: HIGH
- **Dove**: `backend/tests/test_piano_alpha_integration.py:226-285`
  (`test_piano_alpha_blocco_vettura_numero_treno_persistito`).
- **Cosa**: il test è dichiaratamente "vacuo" se `chiusura == deposito`.
  Commento riga 226-234 (testuale):
  > "il giro chiude in staz_a (= partenza giornata 1, dopo blocco 2 che
  > torna a staz_a). Quindi rientro vettura non serve (chiusura ==
  > deposito = no-op). Per forzare path VETTURA, devo mockare con
  > stazione_chiusura ≠ depot. Soluzione: uso il giro così com'è,
  > vediamo se trigger VETTURA. Se chiusura == deposito → SceltaVOCTAXI
  > durata 0 (no-op), no blocco. In quel caso il test verifica solo il
  > path NORMAL: nessun blocco VETTURA dovrebbe essere stato creato."
  Il loop `for tipo, numero in rows: assert ...` itera su 0 righe →
  **nessuna assert eseguita**. Test verde, copertura zero.
- **Perché è un problema**:
  1. **R5 METODO violata**: il test dichiara di verificare la persistenza
     `numero_treno_vettura` (= la migration 0046 + builder entry 279)
     ma in realtà non la verifica mai. Il bug S4 nascosto sopra (S1 di
     questa critica) sarebbe sopravvissuto a questo test perché il
     test non esercita mai il filtro registro → resolver vettura.
  2. **R-PROC-1 SEVERO post-Sprint 8.2 entry 270**: "E2E empirico al
     primo cambio strangler". Il bug fix S4 è cambio in produzione su
     codice che oggi gira in opt-in. R-PROC-1 richiede E2E empirico
     SUL PATH ESERCITATO — non un test che PASSA VACUAMENTE.
  3. **Self-aware ma non risolto**: NINO ha SCRITTO il commento "test
     verifica solo il path NORMAL" SAPENDO che è inadeguato — è
     pigrizia mascherata da "scope MR-PD7+ con fixture programma reale".
     Ma il fix è scrivibile in 1-2h con seed sintetico.
- **Fix proposto**: 1 nuova fixture `_crea_giro_chiusura_diversa_dal_deposito`
  che costruisce blocchi giro con `staz_a → staz_b → staz_c` (3 stazioni
  diverse, chiusura in staz_c ≠ deposito). Il test mock `treno_mock`
  rientro vettura `staz_c → deposito`. Verifica che 1 blocco VETTURA
  persistito + `numero_treno_vettura == "9999"`.
- **Costo del fix**: 2-3h (fixture + 1 test integration aggiuntivo).

### S3 — `S3 hook` non integrato in pre-commit framework / CI (regressione possibile)

- **Severità**: MEDIUM
- **Dove**: `backend/scripts/check_alembic_revisions.py` + assenza di
  `.pre-commit-config.yaml` e `.github/workflows/`.
- **Cosa**: lo script è eseguibile a mano ma:
  - nessun hook git automatico l'invoca,
  - nessuna CI lo blocca su PR,
  - dipende dalla disciplina dello sviluppatore (= NINO che si ricorda
    di lanciarlo).
  Limitazione dichiarata in entry 287 §Limitazioni 1-2.
- **Perché è un problema**: l'origine di S3 era proprio "incidente
  migration 0046 = 0029 in deploy prod 502". Lo script è il "mai più",
  ma se lo si dimentica di lanciare al prossimo MR alembic, lo stesso
  incidente può ricapitarci. R5 METODO "verifica prima del commit"
  rimane manuale.
- **Fix proposto**: 2 strade complementari:
  - (a) Aggiungere `.pre-commit-config.yaml` minimale con hook
    `check-alembic-revisions` (~10 righe yaml + setup `pre-commit
    install`).
  - (b) Aggiungere step in `.github/workflows/backend-ci.yml` (anche
    minimal: ruff + mypy + check_alembic). Manca interamente la CI
    backend.
- **Costo del fix**: (a) <1h. (b) 2-3h per workflow CI minimale.

### S4 — Smoke prod entry 293 esercita SOLO Caso A (chiusura=deposito), Caso B mai

- **Severità**: MEDIUM (con cap da R-PROC-3 sul prossimo cambio)
- **Dove**: TN-UPDATE entry 293 §Coverage smoke (riga 84-96).
- **Cosa**: il giro 2094 chiude a S01640=FIORENZA=deposito. La tabella
  coverage smoke dichiara onestamente: `risolvi_rientro` ❌, `_inserisci_blocco_rientro`
  ❌. Il bug fix S4 JSONB query è esercitato in prod **ma su `from_db`
  che ritorna registro vuoto** (0 turni `deposito_first` esistenti
  pre-smoke). Il branch "registro popolato + filtro vetture cross-turno"
  rimane mock-only.
- **Perché è un problema**: combinato con S1 di questa critica, il bug
  semantico operatore=None **non è stato esercitato in prod**. Domani
  quando un giro reale chiuderà ≠ deposito + un secondo turno proverà
  a usare la stessa vettura, scopriamo il bug a danno fatto. R-PROC-1
  applicabile: questo era il primo cambio strangler in `from_db` e
  l'E2E empirico è incompleto.
- **Fix proposto**: smoke prod follow-up con giro che chiude ≠ deposito
  (selezione query: `WHERE giro_blocco.stazione_a_codice != depot.stazione_principale_codice
  ON ULTIMA giornata`). Esempio realistico: giro Mi.Centrale↔Tirano
  che chiude a TIRANO o LECCO. Cleanup turno 119 + nuovo turno 120 con
  vettura/MM/VOCTAXI persistita.
- **Costo del fix**: 1-2h (selezione giro + run + verifica DB).

### S5 — Numerazione TN-UPDATE "implicita" `1bb200d` rompe la convenzione

- **Severità**: LOW-MEDIUM
- **Dove**: commit `1bb200d` "docs(claude.md) ... (entry 293 implicit)".
- **Cosa**: il commit aggiorna solo CLAUDE.md (tabella stato Sprint),
  ma il messaggio scrive "(entry 293 implicit)" senza incrementare il
  contatore TN-UPDATE. Il successivo entry 293 reale (smoke prod) ha
  preso lo stesso numero. Numerazione fragile in scenari con commit
  parallelo (Plan-D side branch ha usato gli stessi numeri).
- **Perché è un problema**:
  1. **Test del residuo §7 CLAUDE.md**: incrementare 293→294 era
     scrivibile in 30 secondi. Pigrizia mascherata da "è solo doc".
  2. **Convenzione TN-UPDATE rotta**: ogni commit ha la sua entry.
     "Implicit" è un'eccezione che apre a futuro caos: ogni doc-only
     commit potrebbe pretendere di "non contare". Slippery slope.
  3. **Tracciabilità persa**: se domani un MR cita "entry 293", quale
     dei due intende? Lo smoke prod o il bump CLAUDE.md?
- **Fix proposto**: convenzione retroattiva: anche i doc-only commit
  hanno la loro entry. Nello specifico, riassegnare nelle prossime
  entry: `1bb200d` = "entry 293 — bump CLAUDE.md tabella stato Sprint",
  smoke prod = entry 294, SEVERO retrospettiva = entry 295.
- **Costo del fix**: <30 min (rinumerazione TN-UPDATE già scritto +
  riferimenti incrociati). Ma decisione utente: "vale la pena
  rinumerare retroattivamente?". Se no, scrivere convenzione esplicita
  in METODO o CLAUDE.md "doc-only commit non hanno entry separata".

### S6 — Smoke prod bypass JWT (admin password env stale, non risolto)

- **Severità**: LOW-MEDIUM
- **Dove**: TN-UPDATE entry 293 §Coverage smoke + §Limitazioni 2.
- **Cosa**: `genera_turni_pdc_deposito_first` chiamata direttamente su
  `Session(engine_prod)` perché credenziali admin DB env Railway
  (`ADMIN_DEFAULT_PASSWORD`) non corrispondono al DB. Equivalente lato
  builder+DB ma non valida il dispatch FastAPI + JWT check + role
  admin in prod.
- **Perché è un problema**:
  1. **Coerenza endpoint REST**: il path `POST /api/giri/{id}/genera-turno-pdc?builder_strategy=deposito_first`
     è quello che la dashboard frontend userà davvero. Se c'è un
     middleware buggato (es. CORS, JWT scope, rate-limit) lo scopri
     in prod, non con questo smoke.
  2. **Test integration TestClient copre l'endpoint** (entry 289 S7),
     OK. Ma TestClient è in-process: non valida il deploy reale Railway
     con uvicorn workers / proxy / TLS termination.
  3. **R5 METODO "verifica prima del commit"**: la verifica c'è, ma
     non è integrale (manca lo strato HTTP).
- **Fix proposto**: 2 strade:
  - (a) Risolvere la password admin (`railway env set ADMIN_DEFAULT_PASSWORD=...`
    + trigger reset in db_init o re-bootstrap). 30 min.
  - (b) Endpoint dedicato di smoke con auth alternativa (token interno
    per CI/cron). Più lavoro, MR a sé.
- **Costo del fix**: (a) 30 min. Manca azione utente per scegliere.

### S7 — Parser DSL `dsl_varianti_calendariali.py` non gestisce range continuo né "Misto"

- **Severità**: LOW
- **Dove**: `backend/src/colazione/domain/dsl_varianti_calendariali.py`
  (limitazioni dichiarate entry 290 §Limitazioni 1).
- **Cosa**: il parser copre 7-8 sintassi (LV, F, Si eff., Solo, GG,
  Circola Sabato Festivo). Manca:
  - `"Dal 22/3 al 12/4"` (range continuo) — comune nei PDF Trenord per
    finestre di validità (es. orario estivo).
  - `"Misto: Lv+F (N date)"` — etichetta generata da
    `calcola_etichetta_variante` legacy = self-referenziale (il parser
    non parsa il proprio output).
  - Etichette PDF con typo o spazi anomali (es. doppia spazio,
    accentazione).
- **Perché è un problema**: limitazione documentata onestamente, ma
  scope MR-PD7+ NON aperto come ticket. Sprint 8.3 chiude S9 SEVERO 8.2
  con un parser **utile ma incompleto**. Il fallback sovra-include
  resta attivo per i pattern non coperti = ancora scenari "tutte le
  candidate" sui PDF reali Trenord 2026 (anche se in % minore di
  pre-S9).
- **Fix proposto**: aggiungere 2-3 regex:
  - `r"DAL\s+(\d+/\d+)\s+AL\s+(\d+/\d+)"` per range continuo.
  - Per "Misto: Lv+F (N date)" il parser deve ricomporre i sub-token
    LV+F separati (richiede refactor maggiore = legitime MR a sé).
- **Costo del fix**: range continuo <1h. "Misto" 4-6h MR a sé.

### S8 — S8 nuovo formato `striscia_consecutiva` mai persistito DB prod

- **Severità**: LOW
- **Dove**: TN-UPDATE entry 293 §Risultato persistito (turno 119 ha solo
  `numero_insufficiente`, no `striscia_consecutiva`).
- **Cosa**: il refactor S8 introduce un nuovo formato messaggio
  violazione (`striscia_consecutiva_da_G{i}_a_G{j}:{L}_giornate`) ma
  lo smoke prod su giro 1gg non lo triggers (serve striscia ≥7gg
  consecutivi). 5 test unit lo coprono ma 0 persistenze DB prod.
- **Perché è un problema**: R-PROC-1 SEVERO entry 270 "E2E empirico"
  = anche il nuovo formato output va visto in prod almeno 1 volta. Se
  il consumatore frontend cerca substring `"no_in_7gg"` (= mantenuto)
  funziona; se cerca `"contatore_raggiunto_7"` (= rimosso) si rompe.
  Backward-compat nominale OK ma da verificare in prod.
- **Fix proposto**: smoke prod su giro multi-giornata con violazione
  forzata striscia ≥7gg. Combinabile con S4 (smoke Caso B). Verifica
  output `riposo_settimanale_violazioni` contiene
  `"striscia_consecutiva"`.
- **Costo del fix**: 1h (subset del fix S4).

### S9 — S10 ha rimosso parametro pubblico `cache=` senza entry breaking-change esplicita

- **Severità**: LOW
- **Dove**: `backend/src/colazione/domain/builder_pdc/deposito_first.py:269-274`
  (signature `costruisci_giornata_deposito_first`).
- **Cosa**: parametro `cache: PartenzeCache | None = None` rimosso
  dalla signature pubblica. Verificato dal commit message entry 291:
  "Verificato che NESSUN chiamante (test unit, endpoint API, builder
  interno) passa `cache=` esplicitamente". È vero, ma è breaking
  change minore della signature pubblica.
- **Perché è un problema**:
  1. Convenzione "breaking change esplicito" persa: nessuna entry di
     "BREAKING" nel commit message né nota in TN-UPDATE.
  2. Codice greenfield, multi-tenant futuro: domani altre aziende
     potrebbero chiamare la funzione `cache=` (= public API del package
     `colazione.domain`). Senza CHANGELOG/breaking-flag il refactor è
     silenzioso.
- **Fix proposto**: aggiungere nota nel commit message (post-fact: in
  TN-UPDATE entry 291 chiarire "BREAKING signature minor: param `cache`
  rimosso"). Da Sprint 8.4 in poi, convenzione: ogni signature change
  pubblica ha tag `BREAKING:` nel body commit.
- **Costo del fix**: 5 min (post-edit TN-UPDATE) + decisione policy.

## Debito tecnico segnalato

NINO ha lasciato 4 residui dichiarati nei commit Sprint 8.3. Verifica
test del residuo §7 CLAUDE.md per ognuno:

1. **Helper `enumera_date_giornata` integrato per turni storici**
   (`registro_vetture.py:240` "wild card S4 TODO"): scope MR-PD7+.
   ❌ **Pigrizia mascherata** se inteso come "operatore=None forever".
   Il vero fix è S1 di questa critica = filtro `live_arturo` deve
   gestire wild-card OPPURE migration 0047 aggiunge operatore. Il
   commit message entry 288 dichiara "Wild card per data_operativa
   rimane" senza menzionare il problema operatore.

2. **Path Caso B rientro VETTURA non esercitato in prod** (entry 293
   §Limitazioni 1): scope "fixture programma reale Trenord". ✅
   **Legittimo MA**: la prossima azione concreta deve essere "smoke
   prod follow-up giro chiusura ≠ deposito" — non aspettare MR-PD7
   intero.

3. **JWT auth admin prod** (entry 293 §Limitazioni 2): "scope MR-PD7+
   con fixture programma reale Trenord". ❌ **Pigrizia mascherata**:
   reset password admin = `railway env set` + restart = 30 min. Test
   del residuo §7: scrivibile <2h → CHIUDILO.

4. **Cleanup turno 119 in prod** (entry 293 §Limitazioni 3): "lasciato
   come marker storico". ✅ **Legittimo** se utente concorda;
   altrimenti pulire prima di Sprint 8.4 per ripartire da DB pulito.

## Aderenza al METODO-DI-LAVORO

1. **R1 Diagnosi prima di azione**: ✅ rispettato. Ogni Sprint 8.3 entry
   parte dal finding SEVERO 8.2 corrispondente con riferimento esplicito.
   La diagnosi del bug JSONB di S4 è ottima (entry 289: "DB locale era a
   `alembic_version=a6b7c8d9e0f1`" — root cause concreto).

2. **R2 Numeri non ipotesi**: ✅ rispettato sui validatori (ciclo 21gg
   = 1 violazione 21gg, calcolato e testato). ⚠️ Sul `_conta_giorni_solari_per_riposo`
   `gap_min // (24*60)` resta proxy stimato (documentato come "sotto-stima"
   = onesto). OK.

3. **R3 Un passo alla volta**: ✅ rispettato. 7 commit, ognuno con scope
   chiaro (S3 → S4 → S5+S6+S10 → S7 → S8 → S9 → smoke). Niente MR
   monolitico. Combina S5+S6+S10 in un commit unico ma sono 3 LOW
   omogenei = giustificato.

4. **R4 Ammettere l'errore**: ✅ entry 289 onestamente dichiara "S7 ha
   trovato il bug JSONB ProgrammingError che sarebbe arrivato in prod".
   Auto-critica positiva: "DB locale non aveva applicato migration 0046
   ... `alembic upgrade head` applicato". Niente difesa cieca. Buono.

5. **R5 Verifica prima del commit**: ⚠️ **PARZIALE**. mypy/ruff/test
   verdi su tutti i commit. Ma:
   - S4 `from_db` operatore=None bug (S1 di questa critica) non
     verificato cross-modulo (= mancanza di test integration filter
     end-to-end).
   - Smoke prod entry 293 verifica Caso A ma non Caso B (= S4 di questa
     critica).
   La verifica c'è ma non è integrale, esattamente come Sprint 8.2.

6. **R6 Preservare non distruggere**: ✅ tutti i refactor sono backward-compat
   (substring `no_in_7gg` mantenuto in S8, signature `cache=` rimossa
   solo dopo verifica chiamanti in S10). Nessuna distruzione attiva.

7. **R7 Costanza nel tempo**: N/A.

## Aderenza R-PROC SEVERO post-Sprint 8.2

- **R-PROC-1 (E2E empirico al primo cambio strangler)**: ⚠️ **VIOLATA
  parzialmente**. S4 from_db è cambio in produzione su un modulo critico
  (registro vetture cross-PdC). Smoke prod l'ha esercitato ma su path
  Caso A (registro vuoto) = non è E2E completo. Cap voto applicabile:
  MAX 6/10. Combinato con il bug semantico S1 di questa critica → cap
  più aggressivo.

- **R-PROC-2 (assunzioni esplicite per HARD constraint)**: N/A questo
  Sprint (no nuovi HARD constraint introdotti).

- **R-PROC-3 (MED diventa HIGH BLOCKING al cambio successivo)**: ⚠️
  applicabile a S2 di questa critica (test S7 vacuo). Era LOW se Sprint
  8.3 fosse "solo cleanup", ma essendo il primo cambio in produzione
  che esercita la logica integrata (smoke prod), il debito mock-only
  diventa HIGH BLOCKING per Sprint 8.4.

## Voto complessivo

**3/10** (AMILCARE V4 Pro confermato).

Motivazione in 1 riga: backlog precedente chiuso pedissequamente MA con
1 bug HIGH-CRITICAL nascosto dietro commento fuorviante (S1 from_db wild-card
operatore = filtro inoperante) + 1 test integration vacuo che non
intercetta il bug + smoke prod incompleto su Caso B = il "fai bene tutto"
opzione Z dello Sprint 8.2 si è trasformato in "chiudo i ticket nominalmente
ma il debito vero resta nascosto".

Scala: 3-4 = problemi strutturali, da rivedere. Sprint 8.3 chiude 7
finding SEVERO 8.2 ma ne lascia 9 nuovi (di cui 1 HIGH-CRITICAL) =
trasferimento del debito, non riduzione.

**Confronto vs Sprint 8.2**:
- Sprint 8.2 fallback NINO 5/10 → AMILCARE 4/10 (delta -1).
- Sprint 8.3 AMILCARE 3/10 (motore disponibile al 3° tentativo).

La traiettoria è preoccupante: ogni Sprint cleanup introduce nuovi
finding mentre chiude i precedenti. Il pattern "S7 trova bug fix S4 PRIMA
del prod" è positivo, ma S2 di questa critica dimostra che il test
integration può anche **passare vacuamente** = falso positivo del
positivo.

## Cosa NON ho controllato

- **AMILCARE risposta breve 300 parole** (3° retry post-2 timeout). Brief
  più ridotto ⇒ giudizio meno articolato vs Sprint 8.2 (che aveva 1000+
  parole quando AMILCARE rispondeva). Voto AMILCARE potrebbe oscillare
  3-5 con brief più ricco. Da rifare con AMILCARE operativo a contesto
  pieno se l'utente vuole conferma.
- **Test runtime non eseguiti**. Non ho lanciato `pytest backend/tests/test_piano_alpha_integration.py`
  per verificare i 5 test S7. Mi fido dei commit message "5 passed" e
  del DB cleanup autouse.
- **Deploy verifica visiva**. Non ho controllato `railway logs --service
  backend` post-deploy 7 commit Sprint 8.3. Mi fido dell'utente che
  vede verde + entry 293 §Stato deploy "cea72791 ultimo".
- **Frontend test Vitest**. Sprint 8.3 non ha toccato frontend (solo
  backend). 53 test frontend pre-Sprint 8.3 non verificati post.
- **Migration 0046 schema reale prod**. Non ho ispezionato `\d
  turno_pdc_blocco` in prod per verificare presenza colonna
  `numero_treno_vettura` nullable. Mi fido di entry 293 che ha
  persistito 119 senza errori.
- **Coverage cross-modulo dei test**. Non ho misurato copertura effettiva
  dei nuovi moduli `dsl_varianti_calendariali.py`, `riposo_settimanale.py`
  refactor S8. Gli unit test sì, ma % di branch coverage no.
- **Performance del registro `from_db`**. Caricare TUTTE le vetture del
  programma (S4) è ora lineare nel numero di blocchi VETTURA del
  programma = al momento trascurabile (programma 17 ha 0 turni
  `deposito_first`), ma non misurato.

---

## Tracciabilità

- Brief AMILCARE: target 600 byte al 3° retry (2 timeout `-32001` con
  brief 3KB e 1.5KB). Pattern entry 248/270/278/Sprint 8.2 confermato:
  server saturo cronico questa settimana (5+ critiche consecutive
  finiscono in fallback).
- Modalità ufficiale per questa critica: **AMILCARE V4 Pro via
  `mcp__amilcare__reason`; orchestratore SEVERO eseguito manualmente da
  NINO (subagent custom non bootato in sessione corrente)**, come da
  pattern entry 246/248. Voto **non asteriscato** (giudizio AMILCARE
  esplicito).
- Bug semantico S1 verificato cross-modulo da NINO PRIMA della
  delega ad AMILCARE (lettura `live_arturo.py:301` + `registro_vetture.py:230-241`).
  AMILCARE ha confermato HIGH-CRITICAL.
- Sprint 8.4 prossimo: trigger linguistici "fai criticare" attivi,
  SEVERO retro automatico. Da chiudere PRIMA: S1 (fix `live_arturo`
  match wild-card) + S2 (fixture giro chiusura ≠ deposito).
