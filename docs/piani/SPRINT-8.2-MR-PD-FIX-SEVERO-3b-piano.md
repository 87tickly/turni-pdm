# PIANO MR-PD-FIX-SEVERO 3b — A1 (RegistroVettureAssegnate) + A2 (PartenzeCache shared)

> Piano scritto da NINO il 2026-05-09 prima del codice. Va criticato
> da SEVERO (motore AMILCARE V4 Pro) prima dell'implementazione,
> come da memoria `feedback_severo_sempre_su_piani.md`.

## Contesto

Re-critica SEVERO MR-PD3 entry 276 ha aperto 3 finding HIGH/CRITICAL
P0 prima dell'uso reale del path `builder_strategy=deposito_first`:

- **A3** chiuso entry 277 (MR-PD-FIX-SEVERO 3a, A3-extended).
- **A1 CRITICAL** §15 cross-PdC: 2 PdC indipendenti possono prenotare
  la stessa vettura per il rientro = output illegale per definizione
  NORMATIVA-PDC §15.1-§15.2.
- **A2 HIGH** idempotenza: `PartenzeCache` opzionale + API non-deterministica
  → re-build stesso input produce turni diversi.

Decisione utente + FAUSTO: **MR unico coordinato A1+A2** perché entrambi
toccano la signature di `risolvi_rientro` (rework garantito se separati).

## Scope

### In scope MVP

1. `RegistroVettureAssegnate`: classe stateful che traccia i numeri treno
   già usati come VETTURA rientro. Inizializzata da DB (legge `turno_pdc_blocco`
   tipo='VETTURA' del periodo programma) + aggiornata in-memory ad ogni
   nuovo turno costruito nel run.
2. `PartenzeCache` promossa a **dipendenza obbligatoria** del resolver
   (signature change, breaking per chi non passa cache).
3. `BuilderProgrammaContext`: classe context che incapsula `cache`,
   `registro`, `live_client` per il run di costruzione. Iniettata
   nell'endpoint MR-PD5.
4. Resolver: `risolvi_rientro` accetta `registro`. Quando `trova_treno_vettura`
   ritorna un treno già nel registro → **loop con `ora_min_partenza` aggiornato**
   per cercare il prossimo treno non escluso. Esaurita la finestra → fallback
   MM/VOCTAXI.
5. Endpoint `POST /api/giri/{id}/genera-turno-pdc?builder_strategy=deposito_first`:
   istanzia `BuilderProgrammaContext` per request, popola registro da DB
   (turni PdC esistenti del programma per giorno+stazione coerenti).
6. Tracciamento numero treno vettura nel blocco DB: **soluzione MVP =
   parsing regex** dell'`accessori_note` quando si legge il registro
   (è scritto come `"Vettura rientro {categoria} {numero} ({operatore})..."`).
   Migration con campo dedicato è scope creep, lasciata aperta in TODO.

### Out of scope (residui legittimi)

- Estensione registro a corse commerciali / materiale vuoto: l'unicità
  CONDOTTA è già garantita dal modello giro 1:1 PdC; cross-turno per
  CONDOTTA è scope §15 cross-turno (MR-PD7 globale, futuro).
- Snapshot DB persistente del PartenzeCache (opzione 1 di AMILCARE):
  scope creep, MVP cache shared cross-build (opzione 2) basta.
- Migration `turno_pdc_blocco.numero_treno_vettura: str | None` campo
  dedicato: refactor MVP-killing. Parsing regex in MVP, migration in
  MR successivo se necessario.

## Architettura proposta

### File nuovi

- `backend/src/colazione/domain/builder_pdc/registro_vetture.py` (~80 righe)
  - `class RegistroVettureAssegnate` (stateful, dataclass non-frozen)
    - campo `vetture: dict[str, set[str]]` chiave `data_giornata_iso` →
      set numeri treno
    - metodo `is_assegnata(numero, data_giornata) -> bool`
    - metodo `assegna(numero, data_giornata)` (idempotente)
    - factory `from_db(db_session, programma_id, data_inizio, data_fine)`
      async che esegue 1 query SELECT `turno_pdc_blocco` join
      `turno_pdc_giornata` con `tipo='VETTURA'`, parsea `accessori_note`
      via regex, popola le entry
    - metodo `numeri_per_giornata(data_giornata) -> frozenset[str]`
- `backend/src/colazione/domain/builder_pdc/builder_programma.py` (~100 righe)
  - `@dataclass class BuilderProgrammaContext`
    - `cache: PartenzeCache`
    - `registro: RegistroVettureAssegnate`
    - `live_client: httpx.AsyncClient`
    - factory async `crea_per_programma(db_session, programma_id) -> BuilderProgrammaContext`
      che istanzia tutto e popola registro da DB

### File modificati

- `backend/src/colazione/domain/builder_pdc/vettura_resolver.py`:
  - signature `risolvi_rientro` aggiunge `registro: RegistroVettureAssegnate`,
    `data_giornata_iso: str` (per chiave registro)
  - `cache: PartenzeCache` non più `| None` (obbligatoria)
  - logica step 1: chiama `trova_treno_vettura`. Se `treno is not None`
    AND `registro.is_assegnata(treno.numero, data_giornata)` → log info
    "vettura X già assegnata, cerco successiva". Loop con
    `ora_min_partenza_corrente = treno.partenza_min + 1` (skip avanti).
    Max iterazioni = N (es. 10) per evitare loop infiniti su finestra
    affollata. Esaurito → `treno = None`.
  - quando si sceglie SceltaVettura, NON registrare ancora (lo fa il
    persister dopo INSERT successo, evita race condition se INSERT
    fallisce).
- `backend/src/colazione/domain/builder_pdc/deposito_first.py`:
  - signature `costruisci_giornata_deposito_first` aggiunge `context:
    BuilderProgrammaContext`, `data_giornata_iso: str`
  - propaga a `risolvi_rientro` (cache+registro+data)
  - dopo persistenza turno (in `persisti_un_turno_pdc` via
    `giornata_base.py` facade), chiama `context.registro.assegna(...)`
    per le vetture appena create
- `backend/src/colazione/domain/builder_pdc/giornata_base.py`:
  - facade `persisti_un_turno_pdc` riceve `context` opt-in (non breaking
    per chiamanti legacy che non lo usano)
  - dopo INSERT successo, scansiona blocchi `tipo='VETTURA'`, estrae
    numero treno (helper condiviso con `RegistroVettureAssegnate.from_db`),
    chiama `context.registro.assegna`
- `backend/src/colazione/api/routes/giri.py` (o equivalente endpoint):
  - `POST /api/giri/{id}/genera-turno-pdc?builder_strategy=deposito_first`:
    crea `BuilderProgrammaContext.crea_per_programma(db, giro.programma_id)`
    PRIMA di chiamare `costruisci_giornata_deposito_first`.

### Test

`backend/tests/test_registro_vetture.py` (nuovo, ~120 righe):
1. `test_registro_vuoto_nessuna_vettura_assegnata`
2. `test_registro_assegna_e_query`
3. `test_registro_from_db_legge_turni_esistenti` (fixture turno PdC con
   blocco VETTURA, legge regex)
4. `test_registro_data_giornata_isolation` (vettura 12345 il 2026-03-15
   non collide con vettura 12345 il 2026-03-16)

`backend/tests/test_vettura_resolver.py` (esteso):
5. `test_a1_vettura_in_registro_cerca_successiva`: mock `trova_treno_vettura`
   con side_effect che ritorna treno1, poi treno2 (orari distinti).
   Registro ha treno1. Resolver chiama 2 volte → ritorna SceltaVettura(treno2).
6. `test_a1_finestra_esaurita_fallback_mm`: registro ha tutti i candidati,
   resolver esaurisce finestra → fallback SceltaMM.

`backend/tests/test_a1_a2_integration.py` (nuovo, ~150 righe):
7. `test_a1_2_pdc_concorrenti_no_doppione_vettura`: integration end-to-end.
   Crea 2 giri concorrenti che chiudono a TIRANO stessa fascia oraria.
   Un solo treno vettura disponibile. Genera turno PdC per primo giro
   → SceltaVettura(2425). Genera turno PdC per secondo giro nello stesso
   `BuilderProgrammaContext` → registro impedisce → SceltaMM o
   SceltaVettura(treno_alternativo se disponibile).
8. `test_a2_cache_shared_2_pdc_riusa_response`: 2 chiamate `risolvi_rientro`
   stessa stazione → cache miss + cache hit; verifica `cache.misses==1`,
   `cache.hits==1`, mock fetch chiamato 1 volta sola.
9. `test_a2_idempotenza_rebuild_stesso_input_stessa_output`: 1° run con
   cache+registro fresh produce turno T1. 2° run con stessa cache+registro
   (stato dopo 1° run) NON deve assegnare la stessa vettura (registro la
   blocca) → output diverso o uguale a seconda della finestra. Verifica
   determinismo: 2 chiamate consecutive con context fresh identico
   producono output identico (idempotenza per signature).

`backend/tests/test_api_programmi_conferma.py` (esteso):
10. `test_genera_turno_pdc_endpoint_usa_builder_programma_context`:
    integration smoke. POST endpoint, verifica che il manager venga
    istanziato (mock con spy) e che context sia passato giù.

## Cose verificate

1. ✅ Modello DB: `turno_pdc_blocco.tipo_evento` = "VETTURA" + `accessori_note`
   contiene il numero treno come testo. Verificato in `models/turni_pdc.py:97-118`.
2. ✅ Builder MVP scrive il blocco con `accessori_note=f"Vettura rientro
   {treno.categoria} {treno.numero} ({treno.operatore or '—'}) → {deposito_stazione}"`.
   Regex parsing target: `r"Vettura rientro \w+ (\S+)"` (cattura numero
   treno come secondo token).
3. ✅ `_fetch_partenze` di `live_arturo.py` cacha già le response per
   stazione (esiste struttura `PartenzeCache.by_stazione`). Promuovere
   a obbligatoria significa solo signature change, non inventare
   meccanismo.
4. ✅ Manager `BuilderProgrammaContext` resta semplice (3 campi + 1
   factory). Non sostituisce il builder, lo wrappa per dependency injection.

## Cosa NON ho ancora deciso

1. **Signature change breaking**: `risolvi_rientro(registro=..., data_giornata_iso=...)`
   è breaking per chi chiama oggi senza. Quanti chiamanti ci sono?
   Verificato: SOLO `deposito_first.py` chiama `risolvi_rientro` direttamente
   + 8 test in `test_vettura_resolver.py` + 3 nuovi A3. Tutti sotto controllo
   nostro. Nessun consumatore esterno. → breaking accettabile.
2. **Posizione del manager**: nuovo modulo `builder_programma.py` (proposto)
   vs estendere `multi_turno.py` legacy vs inline endpoint. Proposto:
   nuovo modulo. SEVERO valuti.
3. **Strategia "vettura successiva"**: loop con `ora_min_partenza` incrementato
   funziona se i candidati sono ordinati per partenza. `trova_treno_vettura`
   già ordina così (`candidati.sort(key=lambda t: t.partenza_min)` riga 300).
   OK.
4. **Race condition INSERT fallito**: se persistenza fallisce dopo che
   il resolver ha "prenotato" la vettura, il registro contiene una entry
   stale. Mitigazione: registrare solo POST-INSERT (nel persister, non
   nel resolver). Corretto, da implementare.
5. **Concorrenza**: il MVP è single-request (1 endpoint = 1 request = 1
   contesto). Multi-worker non garantito (FastAPI worker pool). Per ora
   assumo single-process; race condition cross-process è scope §15 globale
   futuro.

## Costo stimato

- `registro_vetture.py` + test: 1.5h
- `builder_programma.py` + test: 1h
- Modifiche `vettura_resolver.py` (signature + loop): 1h
- Modifiche `deposito_first.py` + `giornata_base.py` (propagation): 1h
- Modifiche endpoint + integration test: 1.5h
- Update test esistenti `test_vettura_resolver.py` (8 test legacy + 3 A3
  → cache obbligatoria): 1h
- Build/mypy/ruff/commit/deploy/TN-UPDATE: 0.5h

**Totale: 7.5h netti**. AMILCARE aveva stimato 6-8h, in linea.

## Domande per SEVERO

1. **Scope MVP del registro (solo VETTURA, no CONDOTTA)** è scope-cutting
   legittimo o pigrizia mascherata?
2. **Parsing regex su `accessori_note`** vs migration campo dedicato:
   pragmatismo accettabile o anti-pattern strutturale? Quanto durerà
   prima di rompersi?
3. **Manager `BuilderProgrammaContext` come nuovo modulo separato**
   vs integrazione in `multi_turno.py` o `deposito_first.py`: la separazione
   è giustificata o overengineering?
4. **Race condition INSERT fallito**: registrare POST-INSERT è la
   mitigazione giusta, o ci sono altri scenari da coprire (es.
   transazione DB rollback dopo registrazione in-memory)?
5. **Test integration end-to-end** scopre bug latenti come MR-PD-FIX-SEVERO 2
   (entry 271, S5 → bug DB CHECK constraint)? Se sì quali sono le
   probabili zone grigie?

## Output atteso da SEVERO

Critica preventiva su questo piano. Se voto ≥ 7/10 procediamo
all'implementazione. Se voto < 7/10 modifichiamo il piano (iterazione
1-2 max). Format canonico SEVERO + file in `docs/critiche/`.

---

## POST-CRITICA SEVERO (voto 5/10 fallback NINO, AMILCARE 4 timeout)

Critica in `docs/critiche/SPRINT-8.2-MR-PD-FIX-SEVERO-3b-PIANO.md`. 5
finding HIGH + 3 MED/LOW. Modifiche obbligatorie integrate nel piano:

### S1 (HIGH) — Migration `numero_treno_vettura` invece di regex

**Accettato**. Aggiungo allo scope:
- Migration alembic 0046: `turno_pdc_blocco.numero_treno_vettura: String(20) NULL`
- Modello `TurnoPdcBlocco`: campo nuovo nullable
- Builder `deposito_first.py:147-159`: popola il campo quando scrive
  blocco VETTURA
- `RegistroVettureAssegnate.from_db`: SELECT `numero_treno_vettura`
  invece di parsare `accessori_note`
- Costo: 1.5h aggiunti

### S2 (HIGH) — Cross-mezzanotte: decisione utente

**Decisione NINO conservativa per non bloccare il flusso (utente ha
detto "chiudi tutto il piano non fermarti")**:

> La chiave registro per la data è la **data operativa del turno PdC**
> (= `data_giornata` derivata dal numero giornata + variante calendariale
> del turno), NON la data calendariale di partenza/arrivo della vettura.

Razionale:
- Il vincolo §15 "ogni segmento si assegna a UN solo PdC, sempre" è
  scritto dal punto di vista del PdC: 2 PdC distinti che lavorano lo
  STESSO giorno operativo non possono usare la stessa vettura.
- Se vettura cross-mezzanotte: PdC X chiude turno il 15 marzo usando
  vettura che parte 23:30/15 e arriva 00:30/16. PdC Y chiude turno il
  16 marzo non può usare la stessa vettura → ma la stessa vettura è
  già "consumata fisicamente" alla mezzanotte, quindi PdC Y vorrebbe
  un treno DIVERSO. Quindi conviene registrare con la data operativa
  di chi USA la vettura (15 marzo per X, 16 marzo per Y se Y volesse
  un'altra vettura).
- Conservativa: meglio falso positivo doppione (= scarto vettura legittima)
  che falso negativo (= turno illegale).

L'utente può rifinire/correggere in MR successivo se l'interpretazione
non è quella voluta dalle operazioni Trenord.

### S3 (MED) — Chiave registro `(numero, operatore)`

**Accettato**. La chiave è `(numero, operatore, data_operativa)` invece
di `(numero, data_operativa)`. `TrenoVettura.operatore: str | None` è
già nel modello (`live_arturo.py:90`). Costo: trascurabile (è una
modifica di chiave dataclass).

### S4 (HIGH) — Helper `enumera_date_giornata` mancante

**Accettato**. `TurnoPdcGiornata` rappresenta una giornata logica (numero +
variante calendariale) che si materializza in N date concrete. Per il
registro, ad ogni `assegna()` serve la data operativa CONCRETA (non la
giornata logica). Costo: 2-3h aggiunti per:
- Helper `enumera_date_giornata(giornata, programma) -> list[date]`
  in `domain/calendario.py` o nuovo modulo `domain/giornate_concrete.py`
- Logica: prende `numero_giornata` + `variante.tipo` (LV/F/Misto/Solo)
  + `programma.calendario_inizio/fine` → genera lista date concrete
- Test: 4-5 scenari (LV pieno, F pieno, LV+escl, Solo X-Y, misto)

Nota: per il MVP del MR-PD-FIX-SEVERO 3b l'endpoint MR-PD5 processa
**1 giro per request** → 1 giornata operativa per chiamata `costruisci_giornata_deposito_first`.
Il "data_giornata_iso" passato al resolver è la data CONCRETA del
turno appena costruito (che il chiamante endpoint conosce dal contesto
HTTP request: il pianificatore sceglie data calendar specifica).

Per il MVP NON SERVE l'helper completo `enumera_date_giornata` perché
l'endpoint sa già la data. Però SERVE per il `from_db` del registro:
quando carica turni esistenti dal DB, il `TurnoPdcGiornata` ha solo
numero+variante e va materializzato in date concrete per il registro.

**Compromesso pragmatico**: per MR-PD-FIX-SEVERO 3b MVP, il
`from_db` carica le entry con `data_operativa = NULL` come "wild card
match" (collide con qualunque data) finché l'helper non è scritto.
Quando MR successivo introduce `enumera_date_giornata` lo
rifattorizzazione del registro è banale.

Costo: ridotto a 30 min per il "wild card match" + nota TODO esplicita
nel codice. L'helper `enumera_date_giornata` sale a MR-PD7c o MR-PD7d
quando serve effettivamente per validazione cross-turno completa.

### S8 — Stima realistica

Stima aggiornata: **9.5-10h netti** (vs 7.5h originale):
- 1.5h migration + modello + builder
- 30 min wild card match (vs 2-3h helper completo)
- 1h registro_vetture.py + test
- 1h builder_programma.py + test
- 1h modifiche vettura_resolver.py (signature + loop con esclusioni
  via operatore tuple)
- 1h modifiche deposito_first.py + giornata_base.py
- 1.5h modifiche endpoint + integration test
- 1h update test esistenti (cache obbligatoria propagation)
- 1h build/mypy/ruff/commit/deploy/TN-UPDATE

Possibile split: solo se >12h, mantieni MR unico (utente "chiudi tutto
non fermarti"). MVP single MR confermato.

### S5/S6/S7 (MED-HIGH/LOW)

- **S5** race rollback transazione esterna: documentato come limite
  noto nel codice + TODO. After-commit listener è MR-PD7+ (richiede
  refactor del flow async/transaction).
- **S6** rinomina modulo `programma_context.py` invece di `builder_programma.py`:
  **accettato**, naming meno ambiguo.
- **S7** loop `ora_min_partenza+1` edge case 2 treni stesso minuto:
  **accettato parzialmente**. Uso il pattern proposto da SEVERO:
  `trova_treno_vettura(esclusi: set[tuple[str, str]])` opt-in (default
  `None` non rompe legacy). L'esclusione opera nel filtro candidati
  prima dell'ordinamento, no loop esterno. Costo trascurabile (10 min
  per signature + 5 min per filtro).

## Implementazione effettiva (post integrazione)

Ordine:
1. Migration alembic 0046 + modello TurnoPdcBlocco campo nuovo
2. Builder MVP popola campo + test sanity
3. `domain/builder_pdc/programma_context.py` (rinominato da builder_programma.py)
4. `domain/builder_pdc/registro_vetture.py` con wild card match
5. Modifica `live_arturo.trova_treno_vettura(esclusi)` opt-in
6. Modifica `vettura_resolver.risolvi_rientro` (cache obbligatoria,
   registro, esclusi via tuple chiave)
7. Modifica `deposito_first.costruisci_giornata_deposito_first` (propaga
   context)
8. Modifica `giornata_base.persisti_un_turno_pdc` (POST-INSERT registra
   nel context.registro)
9. Endpoint update
10. Test integration end-to-end
11. Build/commit/push/deploy

Procedo.
