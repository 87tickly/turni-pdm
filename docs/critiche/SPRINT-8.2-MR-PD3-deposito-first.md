# Critica SEVERO — Sprint 8.2 MR-PD3a + MR-PD3b+PD4 deposito-first builder

**Data**: 2026-05-09
**Commit / range**: `053b1f2` (MR-PD3a vettura_resolver) + `90ed424`
(MR-PD3b+PD4 deposito_first + 9 test green)
**Entry TN-UPDATE**: 264, 265
**Motore usato**:
- AMILCARE V4 Pro via `mcp__amilcare__reason` — **NON disponibile** (4
  invocazioni timeout `-32001` consecutive su brief 1.5–5KB; stesso
  pattern stamattina, server raggiungibile ma modello satura).
- **Fallback dichiarato**: FAUSTO (Grok Code Fast) via `mcp__grok__chat`
  con system prompt "FAUSTO equivalente AMILCARE motore SEVERO". Output
  filtrato da NINO.
- Brief: 13 bug-points pre-identificati da NINO con verifica codice +
  domanda secca voto + ranking severità + costo fix. ~3KB.
- **Riserva metodologica**: critica con motore secondario non-AMILCARE,
  voto provvisorio. Da rifare con AMILCARE V4 Pro operativo se il
  collegamento endpoint MR-PD5 cambia il quadro.

---

## Sintesi (3 righe max)

Builder deposito-first chiude le Violazioni A/C/D dichiarate, ma porta
con sé un **bug semantico critico** (cap notturno applicato a turni
non-notturni, B1) e un **coupling fragile su API privata** di
`builder.py` (B5) che si romperà al prossimo refactor MR-PD5+. Test
green numerosi ma quasi tutti mockati: zero integration. Voto
**4.5/10 provvisorio**: il cuore architetturale è corretto, l'esecuzione
ha 3-4 falle che vanno chiuse PRIMA di collegare l'endpoint.

## Cosa funziona

- **Decomposizione resolver/builder corretta**: separazione `vettura_resolver`
  (priorità §7.2 pure-function) da `deposito_first` (assemblaggio giornata)
  è la scelta giusta. Il resolver è testabile in isolamento, il builder
  orchestra.
- **HARD scarto su cap condotta** in `deposito_first.py:245-249`:
  promosso da soft-violation a return None — comportamento corretto vs
  builder MVP che annotava soltanto. Coerente con plan Strada B.
- **Pipeline post-rientro**: `replace(draft, blocchi=..., stazione_fine=
  deposito_stazione, fine_prestazione=..., prestazione_min=...)` (linee
  308-317) è immutabile e atomica — buon pattern Python.
- **Caso degenere chiusura == deposito** gestito sia nel resolver
  (`vettura_resolver.py:192-197`) che nel builder
  (`deposito_first.py:252-254`) con short-circuit. Resolver NON chiamato
  inutilmente (verificato nel test
  `test_chiusura_uguale_deposito_no_rientro_extra`).

## Cosa si poteva fare meglio

### S1 — `is_notturno` superinclusivo applicato come discriminante cap

- **Severità**: CRITICAL
- **Dove**: `backend/src/colazione/domain/builder_pdc/builder.py:331` +
  `backend/src/colazione/domain/builder_pdc/deposito_first.py:296-298`
  + `backend/src/colazione/domain/builder_pdc/vettura_resolver.py:160`
- **Cosa**:
  ```python
  # builder.py:331 (calcolo flag draft)
  is_notturno = ora_presa < 5*60 or ora_fine_servizio > 22*60 or ora_fine_servizio < ora_presa

  # builder.py:336 (cap nello stesso file, criterio DIVERSO)
  cap_prestazione = PRESTAZIONE_MAX_NOTTURNO if 60 <= ora_presa < 5*60 else PRESTAZIONE_MAX_STANDARD
  ```
  La flag `is_notturno` salvata sul `_GiornataPdcDraft` è
  **superinclusiva**: True per qualunque turno con presa < 05:00 OR
  fine > 22:00 OR wrap mezzanotte. Ma il cap normativo è 420 min SOLO
  se presa fra 01:00 e 04:59 (NORMATIVA-PDC §3). Quando
  `deposito_first.py:296-298` legge `draft.is_notturno` per scegliere
  `cap_prestazione = PRESTAZIONE_MAX_NOTTURNO_MIN if draft.is_notturno
  else PRESTAZIONE_MAX_STANDARD_MIN`, applica 420 min anche a turni che
  hanno presa 22-23 e fine 05-06 (= NON notturni per cap).
- **Perché è un problema**: turni con presa serale (22:00-00:59) o
  fine post-22 vengono **falsamente scartati** come "prestazione_max_hard"
  con soglia 420 invece di 510. Sul programma Tirano-Mi.PG questi turni
  esistono (S30 sera, ETR526 ultime corse). Il resolver subisce lo
  stesso problema: `ScelzaVettura.prestazione_finale_min <= cap` viene
  valutato con cap 420 errato → tornano `ScelzaMM` o `ScelzaVOCTAXI`
  quando la vettura sarebbe valida.
- **Fix proposto**: introdurre un metodo/property
  `_GiornataPdcDraft.is_cap_notturno` che applichi **lo stesso
  predicato** del cap (`60 <= ora_presa < 300`). Smettere di esporre
  la flag superinclusiva come boolean ambiguo. Il consumatore
  `deposito_first` deve leggere la nuova property; il `vettura_resolver`
  deve ricevere `is_cap_notturno` (rinominare il parametro per onestà).
- **Costo del fix**: <2h (rinomina semantica + 3 test border 22:00,
  23:00, 00:30, 02:30, 04:00 nel resolver e nel builder).

### S2 — Coupling cross-module su API privata di `builder.py`

- **Severità**: HIGH
- **Dove**: `backend/src/colazione/domain/builder_pdc/deposito_first.py:42-51`
- **Cosa**:
  ```python
  from colazione.domain.builder_pdc.builder import (
      ACCESSORI_MIN_STANDARD, CONDOTTA_MAX_MIN, FINE_SERVIZIO_MIN,
      _BloccoPdcDraft, _build_giornata_pdc, _from_min,
      _GiornataPdcDraft, _t,
  )
  ```
  Cinque simboli con underscore (`_BloccoPdcDraft`, `_build_giornata_pdc`,
  `_from_min`, `_GiornataPdcDraft`, `_t`) sono **API privata** di
  `builder.py`. Convenzione Python: i privati possono cambiare senza
  preavviso. `deposito_first` ne dipende per il proprio funzionamento
  base.
- **Perché è un problema**: la roadmap Strada B prevede MR-PD5
  (collegamento endpoint) e MR-PD6+ (sostituzione progressiva del
  builder MVP). Quando builder.py viene rifattorizzato/rimosso, il
  `deposito_first.py` si rompe in punti **non protetti da test**
  (l'import fallisce a collection time pytest). Il
  refactor del builder diventa "chirurgico-coordinato" invece di
  isolato.
- **Fix proposto**: due opzioni equivalenti, scelta NINO:
  1. **Promuovere a pubblico**: rinominare i 5 simboli togliendo
     underscore + dichiararli in `__all__` di `builder.py`. Costo: 1h
     (rename + update consumatori).
  2. **Estrarre modulo helper condiviso** `builder_pdc/giornata_base.py`
     con `BloccoPdcDraft, GiornataPdcDraft, build_giornata_pdc, t,
     from_min, ACCESSORI_MIN_STANDARD, CONDOTTA_MAX_MIN, FINE_SERVIZIO_MIN`.
     Sia `builder.py` (legacy) sia `deposito_first.py` (nuovo) lo
     importano. Costo: 2-3h (move + import update + 1 test sanity).
  
  Opzione 2 è la corretta perché anticipa MR-PD5+: il modulo helper
  sopravvive al rimpiazzo di builder.py.
- **Costo del fix**: 2-3h (opzione 2 raccomandata).

### S3 — §7.3 condotta produttiva ignorata, scope-cutting silente

- **Severità**: HIGH-LATENT (bug attivo SOLO se giro contiene treni
  post-ACCa)
- **Dove**: `backend/src/colazione/domain/builder_pdc/deposito_first.py:262-277`
- **Cosa**: NORMATIVA-PDC §7.3 letterale: *"se nel turno materiale un
  treno di condotta transita dalla stazione di fine produzione fino al
  deposito del PdC, il PdC conduce quel treno invece di muoversi in
  modo passivo […] il principio produttivo ha precedenza"*. Il builder
  invoca `risolvi_rientro` direttamente senza valutare se il
  `blocchi_giro` contiene già un treno verso il deposito **dopo
  l'ACCa**. Docstring (linee 26-28) dichiara: *"§7.3 condotta come
  rientro produttivo (richiede ranking sui treni candidati al rientro:
  prima condotta produttiva, poi vettura passiva, poi MM/VOCTAXI).
  Sprint 8.3 MR-C7"*.
- **Perché è un problema**: scope-cutting parzialmente giustificato.
  Sul builder MVP attuale `_build_giornata_pdc` chiude alla
  `ultimo.ora_fine` del giro (l'ultimo blocco condotta), quindi per
  costruzione i blocchi del giro che NON sono già nel turno PdC base
  sono assenti — il bug è LATENTE. Ma quando MR-C7/MR-C8 introdurranno
  ranking multi-blocco (split CV, FR g1+g2), il bug diventa attivo: il
  builder mette VETTURA invece di CONDOTTA produttiva → turno legittimo
  ma sub-ottimale (paga vettura passiva quando poteva guidare). Il fix
  in MR-C7 dovrà toccare deposito_first, NON estenderlo.
- **Fix proposto**: documentare il limite con TODO esplicito in
  `deposito_first.py` linea 262 (subito prima della chiamata a
  `risolvi_rientro`):
  ```python
  # TODO MR-C7: prima di invocare risolvi_rientro, scansiona blocchi_giro
  # per treni di condotta verso deposito post-ACCa (NORMATIVA §7.3
  # condotta produttiva precedenza). Vincolato dal builder MVP che
  # chiude su ultimo.ora_fine; bug latente finché split CV non entra.
  ```
- **Costo del fix**: 15 min (TODO con riferimento §7.3 e MR-C7); il fix
  vero resta MR-C7 com'era previsto.

### S4 — Test cap-eccede ambivalente: green-phase compromesso

- **Severità**: HIGH
- **Dove**: `backend/tests/test_deposito_first.py:418-434`
  (`test_prestazione_post_rientro_eccede_cap_scartata`)
- **Cosa**:
  ```python
  if draft is None:
      assert any("prestazione_max_hard" in v for v in violazioni)
  else:
      assert draft.stazione_fine == "CREMONA"
  ```
  L'assert ha **branch alternativo**: se `draft is None` allora
  controlla violazione, altrimenti controlla solo che la stazione_fine
  sia il deposito. Cioè il test accetta entrambi gli esiti — se il
  builder NON applica il cap e fa passare un turno 9h → il test passa
  comunque.
- **Perché è un problema**: il test si autodichiara
  "Caso pathological: VOCTAXI con durata che porta prestazione finale
  oltre 8h30 standard. Builder hard-fail." Ma l'assert non FORZA il
  fail. Se domani un bug nasconde il check `nuova_prestazione_min >
  cap_prestazione` (es. cap viene valutato a None), il test continua a
  essere green. Test green-phase **rotto by design** per non rischiare
  fail su numeri arbitrari (presa 06:00 + condotta 8h+ + voctaxi 2h è
  difficile da centrare con calcolo "a mano"). Pigrizia.
- **Fix proposto**: tarare gli orari del giro in modo che la prestazione
  finale sia ESATTAMENTE > 510 (es. presa 04:00 + ultima ACCa 13:00 →
  9h00 base + voctaxi 30 = 9h30 + 15 fine = 9h45 = 585 min > 510). Poi
  assert SECCO `assert draft is None and any("prestazione_max_hard" in v
  for v in violazioni)`. Niente branch.
- **Costo del fix**: 30 min (ricalibrare orari blocchi + togliere
  branch).

### S5 — Zero test integration: rischio bug latenti pre-endpoint

- **Severità**: HIGH
- **Dove**: 17 test totali (`test_vettura_resolver.py` 8 +
  `test_deposito_first.py` 9), TUTTI mockano `risolvi_rientro` o
  `trova_treno_vettura`.
- **Cosa**: nessun test verifica il flusso completo
  `risolvi_rientro` (con `live.arturo.travel` reale o stub HTTP) →
  `costruisci_giornata_deposito_first` → persister → endpoint. Le
  asserzioni esistenti coprono unit pure-function ma non
  l'integrazione.
- **Perché è un problema**: prossimo passo MR-PD5 collega endpoint
  `/api/turni-pdc/genera`. Se `risolvi_rientro` ritorna un
  `TrenoVettura` con campi inattesi (es. `arrivo_min` None per treni
  che cambiano numero, `categoria` lowercase, `operatore` vuoto), il
  builder lo persiste o crasha solo a runtime. Il MR-PD5 verrebbe
  "verde su unit, rosso al primo run reale".
- **Fix proposto**: 3 test sentinel pre-endpoint, in
  `test_deposito_first_integration.py`:
  1. `test_risolvi_rientro_con_stub_http_partenze` (stub `httpx.MockTransport`
     che ritorna 1 risposta `/api/partenze/TIRANO` realistica → builder
     produce VETTURA).
  2. `test_giornata_full_pipeline_persister_in_memory` (giro reale 2
     blocchi + Depot reale FIORENZA + builder + persister salva in DB
     in-memoria → check `deposito_pdc_id` valorizzato + `stazione_fine
     == 'MILANO_CERTOSA'`).
  3. `test_resolver_to_builder_treno_vettura_campi_attesi`
     (TrenoVettura con `arrivo_min=None` → resolver non crasha, builder
     scarta con violazione coerente).
- **Costo del fix**: 2-3h (setup MockTransport + helper persister
  in-memory + 3 test).

### S6 — `DEPOT_MILANO_MM` hardcoded in modulo invece che in DB

- **Severità**: MED
- **Dove**: `backend/src/colazione/domain/builder_pdc/vettura_resolver.py:75-84`
- **Cosa**:
  ```python
  DEPOT_MILANO_MM: frozenset[str] = frozenset({
      "GARIBALDI_ALE", "GARIBALDI_CADETTI", "GARIBALDI_TE",
      "GRECO_TE", "GRECO_S9", "FIORENZA",
  })
  ```
  6 voci hardcoded in modulo Python. Modello `Depot` (anagrafica.py:119-135)
  ha 8 colonne ma niente flag MM.
- **Perché è un problema**: viola CLAUDE.md regola "tutte le regole
  operative configurate via DATO, mai cablate". Se Trenord aggiunge
  domani un deposito MI servito da MM (ipotesi: nuovo M5 esteso),
  serve modifica codice + deploy + restart backend. Inoltre quando il
  programma supporterà SAD/TILO/Trenitalia (CLAUDE.md regola 6
  manifesto greenfield) il frozenset Trenord-specifico diventa zavorra.
- **Fix proposto**:
  1. Migration alembic: `Depot.is_servito_da_mm BOOLEAN NOT NULL DEFAULT FALSE`.
  2. Seed `data/depositi_manutenzione_trenord_seed.json` (o seed Depot
     PdC equivalente): impostare True per i 6 codici attuali.
  3. `vettura_resolver` riceve `depot.is_servito_da_mm` invece di
     consultare il frozenset.
  4. Cancellare `DEPOT_MILANO_MM` dal modulo + `__all__`.
- **Costo del fix**: 1-1.5h (migration + seed + signature update +
  test). Va fatto PRIMA di MR-PD5 perché poi l'endpoint legge il
  Depot da DB e il fix diventa un secondo MR coordinato.

### S7 — Refuso "Scelza" propagato 50+ occorrenze

- **Severità**: LOW (irritante, memetic)
- **Dove**: `vettura_resolver.py` (definizioni 4 dataclass +
  `__all__` + docstring), `deposito_first.py` (5 import + isinstance),
  `test_vettura_resolver.py` (8 ref), `test_deposito_first.py` (10 ref)
- **Cosa**: `ScelzaVettura`, `ScelzaMM`, `ScelzaVOCTAXI`, `ScelzaRientro`
  e l'uso "scelza_vettura" nei test. **Scelza** non è italiano:
  l'ortografia corretta è **scelta** (con T). Refuso ripetuto.
- **Perché è un problema**: anti-pattern professionale. Memetic spread:
  altri MR (MR-PD5+) lo riusano e cementano. Codice ufficiale
  greenfield deve avere naming corretto. Il fix ora è 5 minuti
  (replace_all globale). Fra 6 mesi con 10+ consumatori esterni
  (frontend type, Pydantic schema, OpenAPI doc) costa 2-3h coordinati.
- **Fix proposto**: `replace_all` su 4 file:
  ```
  ScelzaVettura → SceltaVettura
  ScelzaMM → SceltaMM
  ScelzaVOCTAXI → SceltaVOCTAXI
  ScelzaRientro → SceltaRientro
  scelza_vettura → scelta_vettura  (test naming)
  ```
- **Costo del fix**: 5 min (Edit replace_all su 4 file + run pytest +
  ruff).

### S8 — Costanti cap duplicate in 2 moduli con 2 nomi diversi

- **Severità**: MED
- **Dove**: `builder.py:58-59` + `vettura_resolver.py:50-53`
- **Cosa**:
  ```python
  # builder.py
  PRESTAZIONE_MAX_STANDARD = 510      # 8h30
  PRESTAZIONE_MAX_NOTTURNO = 420      # 7h se presa 01:00-04:59
  
  # vettura_resolver.py (stesso valore, nome diverso)
  PRESTAZIONE_MAX_STANDARD_MIN: int = 510
  PRESTAZIONE_MAX_NOTTURNO_MIN: int = 420
  ```
- **Perché è un problema**: single-source-of-truth violato. Se domani
  un nuovo accordo sindacale alza il cap (es. 540 min in casi
  particolari), serve modifica coordinata in 2 moduli. È esattamente
  il pattern §10.6 cap FR di NORMATIVA che il progetto ha sempre voluto
  evitare ("regole = dato, mai hardcoded").
- **Fix proposto**: estrarre in modulo `builder_pdc/normativa_const.py`
  o aggiungere a `giornata_base.py` (vedi S2 fix opzione 2). Importare
  una sola volta. Eliminare la copia.
- **Costo del fix**: 30 min (estrazione + update import 2 moduli).

### S9 — Helper `_inserisci_blocco_rientro` cerca "primo FINE"

- **Severità**: MED-LOW (latente)
- **Dove**: `backend/src/colazione/domain/builder_pdc/deposito_first.py:103-107`
- **Cosa**:
  ```python
  fine_idx = -1
  for i, b in enumerate(blocchi):
      if b.tipo_evento == "FINE":
          fine_idx = i
          break
  ```
  Cerca il **primo** blocco FINE. Builder MVP garantisce sempre 1 FINE
  come ultimo blocco — funziona oggi.
- **Perché è un problema**: quando MR-C7 (split CV intermedi) entra,
  una giornata può avere FINE intermedi (rami). La logica preserva il
  primo, ignora i successivi → blocco rientro inserito nel ramo
  sbagliato, FINE intermedio mai aggiornato → giornata corrotta. Bug
  latente ma garantito al prossimo MR.
- **Fix proposto**: documentare l'assunzione con assert esplicito
  + commento (basta cambiare `break` con
  `# Builder MVP: 1 solo FINE, è l'ultimo. Quando entra split CV (MR-C7)
  questa logica deve gestire FINE multipli per ramo.` + assert
  `assert sum(1 for b in blocchi if b.tipo_evento == "FINE") == 1, ...`).
  Il fix vero resta MR-C7.
- **Costo del fix**: 10 min (commento + assert + test che verifica
  l'assunzione).

### S10 — Gap ACCa→VETTURA senza blocco esplicito

- **Severità**: MED
- **Dove**: `backend/src/colazione/domain/builder_pdc/deposito_first.py:120-136`
- **Cosa**: per VETTURA il blocco usa
  `ora_inizio = treno.partenza_min`. Fra `ora_fine_acca_min` e
  `treno.partenza_min` c'è un gap `[5, 120]` minuti (vincoli del
  resolver `VETTURA_GAP_PRE_MIN=5`, `VETTURA_ATTESA_MAX_MIN=120`). Il
  PdC durante quel gap è in attesa della vettura. Il resolver lo
  include nel calcolo prestazione (corretto: il PdC è in servizio), ma
  il builder NON emette un blocco esplicito per quell'attesa.
- **Perché è un problema**: il Gantt UI (Pianificatore Turno PdC,
  ruolo 2) avrà un buco visibile fra ACCa e VETTURA. Operativo che
  guarda il turno non capisce dove sta il PdC. NORMATIVA §6 dice PK è
  "materiale parcheggiato col PdC che lo guida" — qui il PdC è in
  attesa di vettura passeggero, non sta col mezzo. Manca
  concettualmente un blocco `ATTESA` esplicito (oppure si dichiara che
  il PK qui è degenere → "parking del macchinista, non del materiale").
- **Fix proposto**: due opzioni:
  1. Emettere blocco `PK` con stazione = `stazione_chiusura`,
     ora_inizio = ora_fine_acca, ora_fine = treno.partenza_min,
     accessori_note = "Attesa vettura {treno.numero}".
  2. Introdurre nuovo `tipo_evento = "ATTESA"` (richiede migration
     enum schema).
  Opzione 1 più pragmatica per ora. La distinzione operativa
  PK-materiale vs ATTESA-passeggero è una decisione utente che va
  posta esplicitamente.
- **Costo del fix**: 1h (opzione 1) + 30 min decisione utente sulla
  semantica.

### S11 — `+15` post MM/VOCTAXI: estrapolazione della §3.2

- **Severità**: LOW
- **Dove**: `backend/src/colazione/domain/builder_pdc/deposito_first.py:159-170`
- **Cosa**: NORMATIVA §3.2 letterale: *"se l'ultimo segmento è una
  vettura → fine servizio è 15 minuti dopo l'arrivo vettura"*. Il
  builder applica `+15` anche dopo MM/VOCTAXI (non vettura per la
  §7.1: "VOCTAXI è vettura in taxi non è un treno"; MM è metropolitana
  non vettura).
- **Perché è un problema**: piccolo gap di documentazione. Il `+15` è
  ragionevole come "tempo di rientro al binario / firma fine turno"
  ma non è documentato esplicitamente in §3.2 come "post-MM/VOCTAXI".
  Decisione operativa che andrebbe sancita.
- **Fix proposto**: 2 opzioni:
  1. Chiedere conferma utente: "applichiamo +15 anche dopo MM/VOCTAXI?
     Se sì aggiorniamo NORMATIVA-PDC §3.2."
  2. Rimuovere il +15 per MM/VOCTAXI (fine servizio = ora_fine_rientro).
  Decisione utente + aggiornamento NORMATIVA in entrambi i casi.
- **Costo del fix**: 15 min (decisione + 2 righe NORMATIVA).

## Debito tecnico segnalato

### Residui legittimi

- **§7.3 condotta produttiva** (S3) → ✅ legittimo, motivazione
  oggettiva: il fix richiede ranking multi-blocco e tocca anche
  `_build_giornata_pdc` che è builder MVP destinato a sostituzione.
  Sprint 8.3 MR-C7 dichiarato. Fix-now = TODO esplicito.
- **§9 split CV intermedi, §10.3 FR g1+g2 multi-day, §11.2-§11.4
  ciclo settimanale** → ✅ legittimi, sono refactor architetturali che
  toccano modello dati (FR g1+g2 = 1 unità multi-giornata, schema PdC
  va esteso). MR-C8 + MR-PD7 dichiarati.

### Residui pigri (mascherati)

- **B12 / S5 minore — 2 test pre-esistenti rotti 403 cross-role
  lasciati senza indagine in MR-PD2** → ❌ **pigrizia leggera**. Sono
  test di permessi RBAC, fix scrivibile in <1h se è davvero un bug
  (oppure 30 min se è solo aggiornamento fixture per MR-PD2 schema
  esteso). Lasciati come "fuori scope MR-PD2" è scope-cutting silente.
  Riapri test_giri_turni_pdc_list_api.py:247 e :370, indaga.
  ⚠️ Non blocca MR-PD5 ma va fatto.

- **S1 cap notturno** non è scope-cutting: è bug attivo. È pigrizia
  perché il fix è <2h e tocca riusabile.
- **S2 coupling API privata** non è scope-cutting: è anti-pattern. È
  pigrizia perché va sistemato proprio prima di MR-PD5+ (il refactor
  che il coupling ostacola).

## Aderenza al METODO-DI-LAVORO

1. **Diagnosi prima di azione** — sì. MR-PD3a + MR-PD3b separati
   correttamente (TDD red-phase MR-PD1 → resolver MR-PD3a → builder
   MR-PD3b). Audit MR-PD1 letto.
2. **Numeri non ipotesi** — sì sul cap (510, 420, 330 verificati con
   NORMATIVA). NO sui forfait MM/VOCTAXI (entrambi a 30 min senza
   citazione fonte).
3. **Un passo alla volta** — sì. MR-PD3 splittato per ridurre rischio
   perdita lavoro (entry 264).
4. **Ammettere l'errore** — N/A (nessun errore in corso di sviluppo
   dichiarato).
5. **Verifica prima del commit** — parzialmente. pytest verde (incluso
   2 test pre-esistenti rotti FUORI SCOPE), mypy/ruff verde. NO smoke
   end-to-end (deploy NON eseguito per dichiarazione esplicita —
   l'endpoint non è collegato, scelta corretta). Ma anche zero test
   integration unit-level (S5).
6. **Preservare non distruggere** — sì. Builder MVP intatto,
   `deposito_first` modulo nuovo. Migration MR-PD2 (deposito_pdc_id
   NOT NULL) deployata e verificata 0 orfani.
7. **Costanza nel tempo** — N/A.

## Voto complessivo

**4.5 / 10** — provvisorio, motore secondario.

Cuore architetturale corretto (resolver/builder separati, HARD scarti,
caso degenere chiusura==deposito) ma 4 falle che richiedono chiusura
**prima** del collegamento endpoint MR-PD5: bug semantico cap notturno
(S1), coupling fragile (S2), test ambivalente (S4), zero integration
(S5). +S6 hardcoded MM va fatto adesso o sarà debito. +S7 refuso ora
o si propaga. +S8 single-source.

Scala:
- 9-10: lavoro da senior, finding solo cosmetici
- 7-8: solido, qualche miglioramento sostanziale possibile
- 5-6: funziona ma con debito o blind spot non secondari
- 3-4: problemi strutturali, da rivedere ← **siamo qui**
- 1-2: bocciato, riaprire prima di proseguire

## Cosa fixare PRIMA di MR-PD5 (collegamento endpoint)

**Obbligatori** (~6-8h totali):

1. **S1** cap notturno: `is_cap_notturno` property + signature update
   resolver. ~2h.
2. **S2** estrarre `giornata_base.py` modulo helper condiviso. ~2-3h.
3. **S4** test cap-eccede senza branch. ~30 min.
4. **S5** 3 test integration sentinel. ~2-3h.
5. **S7** replace_all `Scelza → Scelta`. ~5 min.

**Raccomandati** (~2-3h):

6. **S6** migration `Depot.is_servito_da_mm` + seed. ~1.5h.
7. **S8** estrarre cap in modulo unico. ~30 min.
8. **S9** assert + commento "1 solo FINE". ~10 min.
9. **B12** indaga 2 test 403 rotti. ~30 min.

**Decisioni utente** (no-op, ma da chiarire):

10. **S10** semantica gap ATTESA vs PK degenere.
11. **S11** `+15` post MM/VOCTAXI documentato in NORMATIVA o rimosso.

## Cosa NON ho controllato

- **Build/deploy reale**: non ho eseguito `pytest`, `mypy`, `ruff`. Mi
  sono basato sul commit message che dichiara green. Affidabilità del
  commit storico.
- **Programma reale Tirano**: non ho verificato quanti turni "border"
  (presa 22-01 o fine 22-02) esistono nel programma 6536 corse. Stima
  S1 impatto è qualitativa, non numerica.
- **Builder MVP `_build_giornata_pdc` completo**: ho letto le prime
  ~400 righe ma non `_inserisci_refezione`, `_inserisci_refezione_ai_bordi`,
  e i 7 sotto-helper. Possono esserci ulteriori dipendenze cross-module
  oltre le 5 dichiarate.
- **`live.arturo.travel` API behavior reale**: la signature `TrenoVettura`
  è stata letta ma non testata su risposta reale. Eventuali campi None
  o NaN non sono nel mio perimetro.
- **CODE-REVIEW-2026-05-01.md**: 24 finding precedenti, non incrociati
  con MR-PD3 (alcuni potrebbero essere stati risolti, altri no).
- **Critica con AMILCARE V4 Pro**: 4 timeout consecutivi su brief 1.5–5KB
  hanno impedito la critica con motore primario. Questa critica usa
  FAUSTO come fallback motore — il bias di FAUSTO è verso "voto severo
  rapido" piuttosto che "ragionamento lungo edge case", quindi
  potrebbero esserci finding strutturali profondi che né NINO né FAUSTO
  hanno colto. Da rifare con AMILCARE operativo se quadro cambia.
