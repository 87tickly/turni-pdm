# TN-UPDATE — Diario del nuovo programma (greenfield)

> Questo file viene aggiornato dopo **ogni modifica** al progetto.
> È il diario operativo del nuovo programma, costruito da zero.
>
> **Predecessore archiviato**: `docs/_archivio/LIVE-COLAZIONE-storico.md`
> contiene il diario del progetto vecchio (eliminato il 2026-04-25).
> Lì si trova la storia di come ci siamo arrivati al modello dati e
> all'architettura, in caso serva un riferimento.

---

## 2026-04-26 (24) — Sprint 4.4.5a: persister (dominio → ORM)

### Contesto

Sprint 4.4.5 originario (orchestrator + persistenza + endpoint API)
spezzato in **4.4.5a** (persister stupido, solo bridge dataclass→ORM)
e **4.4.5b** (loader + endpoint + strict mode + migration codice_breve).
Motivazione: due responsabilità diverse, due commit più digeribili e
isolati. Decisioni di rigenerazione/finestra/numero_turno tutte in
4.4.5b; il persister non sa nulla di convenzioni.

### Modifiche

**Nuovo `backend/src/colazione/domain/builder_giro/persister.py`** (~380 righe):

Funzione async `persisti_giri(giri, session, programma_id, azienda_id)
→ list[int]`. Mapping completo:

- `GiroAssegnato` → `GiroMateriale` (con `tipo_materiale` denormalizzato
  dal primo blocco assegnato, fallback `"MISTO"`; metadata di
  tracciabilità in `generation_metadata_json`)
- `GiornataAssegnata` → `GiroGiornata` + `GiroVariante` con
  `validita_dates_apply_json=[data]` (istanze 1:1)
- Sequenza blocchi: `vuoto_testa? → [evento_composizione? → corsa]* →
  vuoto_coda?`
- `BloccoMaterialeVuoto` testa/coda → `CorsaMaterialeVuoto`
  (`numero_treno_vuoto = "V-{numero_turno}-{NNN}"`,
  `origine="generato_da_giro_materiale"`) + `GiroBlocco materiale_vuoto`
- `EventoComposizione` → `GiroBlocco aggancio`/`sgancio` con
  `is_validato_utente=False` e `metadata_json` (pezzi_delta,
  note_builder, stazione_proposta_originale, stazione_finale)
- Corse → `GiroBlocco corsa_commerciale` (FK su corsa.id) con
  `metadata_json` (materiale_tipo, numero_pezzi, regola_id)

Errore esplicito `LocalitaNonTrovataError` se `localita_codice` non
in anagrafica per l'azienda.

**Modifica `__init__.py`**: re-export `PERSISTER_VERSION`,
`GiroDaPersistere`, `LocalitaNonTrovataError`, `persisti_giri`.

### Decisioni di design

- **Solo INSERT, no commit**: il persister usa `session.add` +
  `session.flush()` ma non committa. Il caller (4.4.5b) controlla la
  transazione (rollback su errore complessivo).
- **`numero_turno` parametro**: il persister non genera nomi. Riceve
  `GiroDaPersistere(numero_turno, giro)`. La convenzione
  `G-{LOC_BREVE}-{SEQ:03d}` la applica 4.4.5b.
- **`tipo_materiale="MISTO"` placeholder**: se il giro è tutto in
  `corse_residue` (zero blocchi assegnati) il TEXT NOT NULL deve
  comunque avere un valore. Onesto: segnala anomalia senza fallire.
- **Vuoto numerato per giro intero** (non per giornata): `seq_vuoto`
  cresce attraverso le giornate. Es. giro 2-giornate con vuoto coda
  G1 + vuoto testa G2 → `V-G-FIO-001-000` e `V-G-FIO-001-001`.
- **`is_validato_utente=False` SOLO per aggancio/sgancio**: corse e
  vuoti sono "dati", non proposte. Lo flag serve solo agli eventi
  composizione che richiedono validazione manuale del pianificatore.
- **`seq` blocco parte da 1**: vincolo schema `seq >= 1`.
- **`generation_metadata_json` ricco**: `persister_version`,
  `generato_at`, motivo_chiusura, n_corse_residue, ecc. Permette
  audit/debug.

### Test

**`backend/tests/test_persister.py`** (12 test integration, 0.48s):

- 2 casi base (lista vuota, 1 giro 1 corsa con verifica completa
  ORM)
- 1 errore `LocalitaNonTrovataError`
- 2 vuoti (testa + coda separati, verifica `numero_treno_vuoto`
  formato `V-...-NNN`)
- 2 eventi composizione (aggancio +3, sequenza 3→6→3 con aggancio
  + sgancio in ordine corretto)
- 1 multi-giornata (2 giornate con dataset distinte)
- 1 multi-giri (2 giri persistiti, ids distinti, numero_turno
  preservato)
- 1 edge case (giro senza blocchi assegnati → `tipo_materiale="MISTO"`)
- 2 smoke (PERSISTER_VERSION, GiroDaPersistere dataclass)

Setup test: stazioni `S99NNN` (formato vincolo `^S\d+$`), località
`TEST_LOC_*`, corse `TEST_*`. Wipe autouse. Fixture `azienda_id`
recupera dinamicamente l'id Trenord dal seed (sequence può variare).

### Verifiche

- `pytest` con DB: **293 passed** (era 231 puri + 50 skip; ora 12
  nuovi DB attivi → 231+62 quando SKIP_DB_TESTS=1)
- `ruff check` + `format` ✓ (auto-format applicato)
- `mypy strict`: no issues in **45 source files** (era 44, +1
  persister.py)

### Stato

Sub 4.4.5a chiuso. Persister bridge dataclass dominio → ORM testato
end-to-end con DB reale. Pipeline pure → ORM ora invocabile in 4.4.5b.

### Prossimo step

Sub 4.4.5b: orchestrator + endpoint API.

1. Migration 0006: aggiungi `LocalitaManutenzione.codice_breve
   VARCHAR(8) NOT NULL` + backfill per le 7 località Trenord (FIO,
   NOV, CAM, LEC, CRE, ISE, TILO).
2. Loader: dato `programma_id` + `data_inizio` + `n_giornate`, carica
   corse/dotazione/regole dal DB → dataclass dominio.
3. Orchestrator: pipeline pure (catene → posiziona → multi-giornata
   → assegna+eventi) + chiama `persisti_giri()`.
4. Generazione `numero_turno`: `G-{LOC_BREVE}-{SEQ:03d}` con seq
   per (programma_id, località).
5. Endpoint `POST /api/programmi/{id}/genera-giri?data_inizio=...&n_giornate=...`.
6. Strict mode handling: 409 se programma ha già giri (no `?force=true`),
   400 se `no_corse_residue=true` violato, ecc.

---

## 2026-04-26 (23) — Sprint 4.4.4: assegnazione regole + eventi composizione

### Contesto

Sub 4.4.3 produce `Giro` multi-giornata fatti di catene posizionate.
Manca: ad ogni blocco corsa va assegnato un materiale tramite
`risolvi_corsa()` (Sprint 4.2), e i delta `numero_pezzi` vanno
materializzati in eventi `aggancio`/`sgancio` (`PROGRAMMA-MATERIALE.md`
§5).

### Modifiche

**Nuovo `backend/src/colazione/domain/builder_giro/composizione.py`**:

Tre funzioni pure + 6 dataclass frozen:

- `assegna_materiali(giro, regole) → GiroAssegnato`: per ogni corsa
  chiama `risolvi_corsa()`. `None` → corsa va in `corse_residue`.
  `RegolaAmbiguaError` → bubble up (caller decide). Se una giornata
  usa > 1 `materiale_tipo` → registra `IncompatibilitaMateriale`
  (warning, vìola `LOGICA-COSTRUZIONE.md` §3.3 punto 3).
- `rileva_eventi_composizione(giro_assegnato) → GiroAssegnato`:
  scorre `blocchi_assegnati` di ogni giornata, calcola delta
  `numero_pezzi`. Se delta != 0: crea `EventoComposizione` (tipo
  aggancio/sgancio, stazione_proposta = origine blocco corrente,
  `is_validato_utente=False`). Usa `dataclasses.replace` per
  rispettare frozen.
- `assegna_e_rileva_eventi(giri, regole) → list[GiroAssegnato]`:
  orchestrator pipeline.

**Output dataclass**:

- `BloccoAssegnato`: corsa + assegnazione.
- `EventoComposizione`: tipo, pezzi_delta, stazione_proposta,
  posizione_dopo_blocco, note_builder, is_validato_utente.
- `CorsaResidua`: data + corsa senza regola.
- `IncompatibilitaMateriale`: data + frozenset dei tipi visti.
- `GiornataAssegnata`: data + catena_posizionata + blocchi_assegnati
  + eventi_composizione + materiali_tipo_giornata.
- `GiroAssegnato`: localita + giornate + chiuso + motivo + residue
  + incompatibilità.

**Modifica `__init__.py`**: re-export 10 nuovi simboli + aggiornati
docstring sub-moduli e `__all__`.

### Decisioni di design

- **Eventi solo intra-giornata**: i delta cross-notte tra giornate
  consecutive del giro (es. G1 chiude con 6 pezzi, G2 inizia con 3)
  NON generano eventi qui. Sono concettualmente "durante la notte"
  e li gestirà 4.4.5 orchestrator se servono. 4.4.4 fa un solo
  passo: composizione **dentro** ogni giornata.
- **`RegolaAmbiguaError` bubble up**: 4.4.4 pure non sa cosa fare
  (l'utente deve disambiguare); il caller business logic decide
  (es. abort builder, segnala UI).
- **Stazione proposta = origine blocco corrente**: euristica semplice
  e deterministica. L'utente sposta in editor giro UI (campo
  `is_validato_utente=False`).
- **`dataclasses.replace` per "modificare" frozen**: pythonic e
  type-safe. `rileva_eventi_composizione` ricrea giornate e giro
  preservando immutabilità.
- **`IncompatibilitaMateriale` come warning, non errore**: la
  decisione strict mode spetta al builder. Per ora la sola
  registrazione dell'anomalia è sufficiente.

### Test

**`backend/tests/test_composizione.py`** (20 test puri, 0.03s):

- 7 `assegna_materiali` (1 corsa+1 regola, residua, no incompat,
  incompat 2 tipi, RegolaAmbigua bubble, pass-through metadata,
  multi-giornata)
- 5 `rileva_eventi_composizione` (costante = 0 eventi, aggancio
  3→6, sgancio 6→3, sequenza 3→6→3, eventi solo intra-giornata)
- 2 orchestrator (pipeline + giri vuoti)
- 6 frozen dataclass + dataclass smoke (BloccoAssegnato,
  EventoComposizione, GiornataAssegnata, GiroAssegnato,
  CorsaResidua, IncompatibilitaMateriale)
- 1 determinismo

### Verifiche

- `pytest` (no DB): **231 passed + 50 skipped** (era 211+50; +20 nuovi)
- `ruff check` + `format` ✓ (auto-fix organize imports)
- `mypy strict`: no issues in **44 source files** (era 43, +1
  composizione.py)

### Stato

Sub 4.4.4 chiuso. Builder pure ha ora 5 moduli e 4 funzioni
top-level che compongono la pipeline:

```
costruisci_catene → posiziona_su_localita → costruisci_giri_multigiornata
                 → assegna_e_rileva_eventi → list[GiroAssegnato]
```

Tutto DB-agnostic. Pronto per 4.4.5 che farà il bridge ORM
(loader DB → pipeline pure → persister DB) + endpoint REST.

### Prossimo step

Sub 4.4.5: orchestrator builder + persistenza DB.

- Loader: dato `programma_id` + finestra temporale, carica corse
  + dotazione + regole dal DB → dataclass dominio.
- Esegue pipeline pure 4.4.1→4.4.4.
- Persister: traduce `list[GiroAssegnato]` in ORM
  (`GiroMateriale + GiroGiornata + GiroVariante + GiroBlocco` +
  `CorsaMaterialeVuoto`). Eventi composizione → blocchi
  `aggancio`/`sgancio` con `metadata_json`.
- Endpoint `POST /api/programmi/{id}/genera-giri` sincrono.
- Strict mode handling: `no_corse_residue`, `no_giro_non_chiuso_a_localita`
  → 400 se violati.

---

## 2026-04-26 (22) — Sprint 4.4.3: multi-giornata cross-notte

### Contesto

Sub 4.4.2 produce `CatenaPosizionata` chiuse o aperte
(`chiusa_a_localita=True/False`). Sub 4.4.3 le concatena in **giri
multi-giornata** che attraversano la mezzanotte senza tornare in
deposito (decisione utente "B subito" su PROGRAMMA-MATERIALE.md
§6.7).

### Modifiche

**Nuovo `backend/src/colazione/domain/builder_giro/multi_giornata.py`**:

- `MotivoChiusura` (`Literal['naturale', 'max_giornate', 'non_chiuso']`).
- `ParamMultiGiornata` (frozen): `n_giornate_max=5` (default ciclo
  Trenord 5+2). Singleton `_DEFAULT_PARAM`.
- `GiornataGiro` (frozen): `data + catena_posizionata`.
- `Giro` (frozen): `localita_codice + giornate (tuple) + chiuso +
  motivo_chiusura`. Output dominio (DB-agnostic). Mapperà su ORM
  `GiroMateriale + GiroGiornata + GiroVariante + GiroBlocco` in 4.4.5.
- `costruisci_giri_multigiornata(catene_per_data, params) → list[Giro]`:
  itera date in ordine, per ogni catena non visitata avvia un giro,
  estende cross-notte cercando catene nella data successiva (stessa
  località + prima corsa parte da staz_arrivo dell'ultima corsa).

**Algoritmo**:

1. Iterazione date crono.
2. Per ogni catena non visitata → nuovo giro.
3. Estensione: continua finché ultima giornata non chiude E sotto
   `n_giornate_max` E esiste catena in data+1 con stessa località e
   prima corsa origine = arrivo precedente.
4. Tie-break continuazioni: prima per `ora_partenza`.
5. Determina `motivo_chiusura`: naturale | max_giornate | non_chiuso.

**Modifica `__init__.py`**: re-export 5 nuovi simboli (Giro,
GiornataGiro, MotivoChiusura, ParamMultiGiornata,
costruisci_giri_multigiornata).

### Decisioni di design

- **Naming `Giro` (non `GiroMateriale`)**: evita collisione con ORM
  `models.giri.GiroMateriale`. Nel dominio è la dataclass pure;
  4.4.5 farà la traduzione esplicita.
- **Vincolo "stessa località" rigido per la continuazione**: lo
  stesso convoglio fisico non passa di mano tra località diverse
  cross-notte. Anche se geografia matcha, località diversa = giri
  separati.
- **Niente check km_max_giornaliero**: il dato non è ancora cablato
  nelle dataclass dominio (le `FakeCorsa` di test non hanno km).
  Sarà aggiunto in 4.4.4/4.4.5 quando il builder lavorerà sui
  metadati ORM. Onesto: meglio non check parziale.
- **Niente normativa-aware**: non leggiamo `holidays.py` qui per
  determinare `giorno_tipo`. Quel lavoro è in 4.4.4
  (assegnazione regole) — la `data` di una `GiornataGiro` è
  sufficiente per derivare il giorno_tipo on-demand.
- **Sort delle catene per ora di prima partenza**: determinismo +
  euristica FIFO (i convogli che entrano in servizio prima vengono
  processati prima).

### Test

**`backend/tests/test_multi_giornata.py`** (17 test puri, 0.02s):

- 3 casi base (mappa vuota, 1 catena chiusa, 1 catena non chiusa)
- 4 cross-notte (legate, mancante = appeso, località diverse,
  3-giornate)
- 2 forza chiusura (cap=2 con 3 giornate, cap=1)
- 2 tie-break + determinismo
- 1 date non contigue (salto giorno → appeso)
- 4 frozen dataclass + default param
- 1 esempio realistico (ciclo 5 giornate Lun-Ven Trenord)

### Verifiche

- `pytest` (no DB): **211 passed + 50 skipped** (era 194+50; +17 nuovi)
- `ruff check` + `format` ✓ (ruff ha auto-fixato organize imports)
- `mypy strict`: no issues in **43 source files** (era 42, +1
  multi_giornata.py)

### Stato

Sub 4.4.3 chiuso. Builder pure ha ora 4 moduli: `risolvi_corsa`,
`catena`, `posizionamento`, `multi_giornata`. La pipeline completa
pure è: `costruisci_catene` → `posiziona_su_localita` (per ogni
catena) → `costruisci_giri_multigiornata` (concatenazione cross-notte)
→ `Giro` finale.

### Prossimo step

Sub 4.4.4: assegnazione regole + rilevamento eventi composizione.
Per ogni blocco corsa nel `Giro`, chiama `risolvi_corsa()` per
assegnare materiale_tipo + numero_pezzi. Verifica compatibilità
materiale per giornata. Rileva delta composizione (+3 / -3 alle
soglie fascia oraria) e inserisce blocchi `aggancio`/`sgancio` con
`is_validato_utente=False`.

---

## 2026-04-26 (21) — Sprint 4.4.2: posizionamento catena su località

### Contesto

Sub 4.4.1 produce catene "nude" (solo corse incatenate). Per
trasformare una catena in un giro vero serve **chiuderla a una
località manutenzione**: se la prima corsa non parte dalla stazione
collegata alla località, serve un materiale vuoto di posizionamento
(testa); analogo per il rientro (coda).

### Modifiche

**Nuovo `backend/src/colazione/domain/builder_giro/posizionamento.py`**:

- `_LocalitaLike` (Protocol): `codice` + `stazione_collegata_codice`.
- `ParamPosizionamento` (frozen): `durata_vuoto_default_min=30`,
  `gap_min=5`. Singleton `_DEFAULT_PARAM`.
- `BloccoMaterialeVuoto` (frozen): origine, destinazione, partenza,
  arrivo, motivo (`'testa'`|`'coda'`).
- `CatenaPosizionata` (frozen): codice località + stazione collegata,
  vuoto_testa | None, catena originale, vuoto_coda | None,
  `chiusa_a_localita: bool`.
- `LocalitaSenzaStazioneError`, `PosizionamentoImpossibileError`.
- `posiziona_su_localita(catena, localita, params) → CatenaPosizionata`.

**Algoritmo**:

1. Vuoto di testa se `prima.codice_origine != stazione_localita`.
   Orari: `arrivo = prima.partenza - gap_min`, `partenza = arrivo -
   durata_vuoto`. Se partenza < 00:00 → `PosizionamentoImpossibileError`
   (caso "prima corsa molto presto al mattino").
2. Vuoto di coda se NON cross-notte e `ultima.codice_destinazione !=
   stazione_localita`. Orari simmetrici. Se l'arrivo supera 23:59 →
   no vuoto generato, `chiusa_a_localita=False` (4.4.3 lo riprende).
3. `chiusa_a_localita` finale: `True` se la giornata si chiude in
   stazione collegata (naturalmente o via vuoto coda).

**Modifica `__init__.py`**: re-export 6 nuovi simboli + aggiornati
docstring sub-moduli e `__all__`.

### Decisioni di design

- **Durata vuoto stimata costante** (30' default). Niente matrice
  km/velocità reale qui — raffinamento futuro quando avremo dati
  geografici. Stima conservativa.
- **Cross-notte → no vuoto coda**: se la catena chiude cross-notte
  (4.4.1), non possiamo materializzare una coda con `time` puro.
  Marca `chiusa_a_localita=False` e demanda a 4.4.3.
- **`PosizionamentoImpossibileError` esplicito**: se la prima corsa
  parte alle 00:10 con vuoto stimato 30'+5', il vuoto sarebbe alle
  23:35 del giorno prima. Errore esplicito invece di clip silenzioso.
- **`BloccoMaterialeVuoto.motivo`**: `'testa'`|`'coda'` per
  tracciabilità in `metadata_json` quando 4.4.5 persisterà.
- **Validazione input rigorosa**: catena vuota o località senza
  stazione → eccezioni esplicite. Niente `Optional` opachi.

### Test

**`backend/tests/test_posizionamento.py`** (18 test puri, 0.02s):

- 2 validazione (catena vuota, località senza stazione)
- 4 casi base (no vuoti, solo testa, solo coda, entrambi)
- 2 calcolo orari (testa, coda)
- 3 cross-notte / mezzanotte (cross-notte chiude, vuoto testa
  pre-mezzanotte raises, vuoto coda post-mezzanotte non chiude)
- 1 prima corsa presto in stazione (no testa, no errore)
- 4 determinismo + frozen (3 dataclass + default param)
- 1 esempio realistico Trenord (giro S5 Cadorna ↔ Varese, Fiorenza
  manutenzione → 2 vuoti)
- 1 default param

### Verifiche

- `pytest` (no DB): **194 passed + 50 skipped** (era 176+50; +18 nuovi)
- `ruff check` + `format` ✓
- `mypy strict`: no issues in **42 source files** (era 41, +1
  posizionamento.py)

### Stato

Sub 4.4.2 chiuso. Ora una catena può essere chiusa a località con
materiali vuoti. Pronta per 4.4.3 che concatenerà più
`CatenaPosizionata` (o catene grezze) in giri multi-giornata
cross-notte.

### Prossimo step

Sub 4.4.3: multi-giornata cross-notte. Dato un pool di corse di più
giornate, costruisce `GiroMateriale` (G1...Gn) che possono attraversare
la mezzanotte. Determinazione `giorno_tipo` via data partenza (§6.7).
Chiusura: torna a località OR raggiunge `n_giornate_default` OR
supera `km_max_giornaliero`.

---

## 2026-04-26 (20) — Sprint 4.4.1: catena single-day greedy chain

### Contesto

Sprint 4.4 builder giro materiale è il pezzo più complesso del
progetto. Spezzato in 6 sub-sprint (vedi piano in chat). Sub 4.4.1
copre il primo step pure-function: dato un pool di corse single-day,
produrre catene massimali rispettando continuità geografica + gap
minimo. Niente località manutenzione, niente regole, niente DB.

### Modifiche

**Nuovo `backend/src/colazione/domain/builder_giro/catena.py`**:

- `_CorsaLike` (Protocol): 4 attributi minimi (codice_origine,
  codice_destinazione, ora_partenza, ora_arrivo).
- `ParamCatena` (frozen dataclass): `gap_min: int = 5`. Singleton
  `_DEFAULT_PARAM` come default arg (B008-safe).
- `Catena` (frozen dataclass): `corse: tuple[Any, ...]` con invariante
  documentata (continuità geo + gap rispettati).
- `costruisci_catene(corse, params) → list[Catena]`: greedy
  multi-iterazione. Sort per partenza, prendi prima libera, estendi
  con `_trova_prossima` (origine match + soglia inclusiva), chiudi
  su no-match o cross-notte.
- Chiusura cross-notte: se `ora_arrivo < ora_partenza`, la catena
  chiude lì. La concatenazione cross-notte è in Sprint 4.4.3.

**Modifica `backend/src/colazione/domain/builder_giro/__init__.py`**:
re-export di `Catena`, `ParamCatena`, `costruisci_catene`. Aggiornati
`__all__` e docstring sub-moduli.

### Decisioni di design

- **`gap_min` unico** (non triplo 5'/15'/20' come spec §3.3). I
  raffinamenti per tipo stazione richiedono metadati su `Stazione`
  (capolinea sì/no) che oggi non abbiamo. Onesto: sviluppo quando
  serve, non prima.
- **Single-day rigido**: le corse cross-notte chiudono la catena.
  Multi-giornata è 4.4.3, vogliamo 4.4.1 testabile in `time` puro
  senza confusione su date.
- **Tie-break deterministico**: a parità di matching geografico, vince
  la corsa con partenza più precoce. A parità ulteriore, l'ordine
  stable del pool sortato decide. Output = funzione pura degli input.
- **`id()` per visitate**: le corse in input non sono hashable di
  default (dataclass non frozen) e non vogliamo forzare `frozen=True`
  sui modelli ORM. `id()` Python è univoco per oggetto in memoria,
  perfetto per "questo oggetto è già in una catena".

### Test

**`backend/tests/test_catena.py`** (18 test puri, 0.02s):

- 2 casi base (lista vuota, singola corsa)
- 4 concatenamento (compatibili, geografia incomp., gap troppo corto,
  gap esatto = soglia, gap=0)
- 2 ordinamento (input non ordinato, ordine catene per prima partenza)
- 2 cross-notte (corsa attraversa mezzanotte chiude, normale +
  cross-notte attaccata)
- 2 tie-break + determinismo
- 2 esempi realistici (S5 mattina 4 corse 1 catena, due rotabili
  indipendenti 2 catene)
- 4 misc (default 5', frozen `ParamCatena`/`Catena`)

### Verifiche

- `pytest` (no DB): **176 passed + 50 skipped** (era 158+50; +18 nuovi)
- `ruff check` + `format` ✓ (dopo fix B008 → singleton)
- `mypy strict`: no issues in **41 source files** (era 40, +1 catena.py)

### Stato

Sub 4.4.1 chiuso. Catena pura testata in profondità. Pronta per
4.4.2 che la posizionerà su località manutenzione (materiali vuoti
apertura/chiusura).

### Prossimo step

Sub 4.4.2: `posiziona_su_localita(catena, localita, params) →
CatenaPosizionata`. Genera blocchi `materiale_vuoto` testa/coda se
necessario per chiudere il giro a una località manutenzione.

---

## 2026-04-26 (19) — Sprint 4.3: API REST CRUD programma materiale

### Contesto

Sub 4.2 ha chiuso la funzione pura `risolvi_corsa`. Ora il
pianificatore deve poter creare/leggere/modificare programmi via
API REST. È il bridge tra UI futura (frontend) e modello dati.

### Modifiche

**Nuovo `backend/src/colazione/api/programmi.py`** (~340 righe):

8 endpoint protetti da `require_role("PIANIFICATORE_GIRO")`
(admin bypassa). Tutti filtrano per `user.azienda_id` dal JWT (multi-
tenant rigorosa).

| Endpoint | Cosa |
|---|---|
| `POST /api/programmi` | Crea programma (stato `bozza`), regole nested opzionali |
| `GET /api/programmi` | Lista azienda corrente con filtri `?stato=`, `?stagione=` |
| `GET /api/programmi/{id}` | Dettaglio + regole (ordinate per priorità DESC) |
| `PATCH /api/programmi/{id}` | Aggiorna intestazione (no stato, no regole) |
| `POST /api/programmi/{id}/regole` | Aggiungi regola (solo bozza) |
| `DELETE /api/programmi/{id}/regole/{rid}` | Rimuovi regola (solo bozza) |
| `POST /api/programmi/{id}/pubblica` | Bozza → attivo con validazione |
| `POST /api/programmi/{id}/archivia` | Attivo → archiviato |

**Validazione pubblicazione** (`_validate_pubblicabile`):
1. Stato corrente = `bozza` (no doppia pubblicazione)
2. Almeno 1 regola (no programma vuoto)
3. Nessun programma attivo della stessa azienda+stagione si
   sovrappone su `[valido_da, valido_a]` (constraint applicativo,
   non SQL)

Errori → 400 (validazione) o 409 (conflitto sovrapposizione).
404 per programma di altra azienda (security: non rivelare l'esistenza).

**Modifica registrazione**:
`backend/src/colazione/main.py`: include `programmi_routes.router`.

### Test

**`backend/tests/test_programmi_api.py`** (23 test integration, DB
required, skipif `SKIP_DB_TESTS=1`):

- 4 auth (401 senza token, admin/pianificatore_giro_demo OK)
- 4 POST (minimo, regole nested, validità invertita 422, filtro
  invalido 422)
- 4 GET (lista vuota, lista con filtri, dettaglio 404, regole
  ordinate per priorità DESC)
- 2 PATCH (aggiorna intestazione, 404 inesistente)
- 3 regole (add bozza OK, delete bozza OK, add su attivo blocca 400)
- 4 pubblica (bozza+regole OK, senza regole 400, già attivo 400,
  sovrapposizione 409)
- 2 archivia (attivo OK, già archiviato 400)

Cleanup `_wipe_programmi` autouse: ogni test parte da DB pulito.
Login via helper `_login(client, username, password)` per riuso.

### Verifiche

- `pytest`: **208/208 verdi** (era 185, +23 nuovi)
- `ruff check` + `format` ✓
- `mypy strict`: **40 source files** (era 39, +1 api/programmi.py)

### Stato

Sub 4.3 chiuso. Il pianificatore ha API complete per gestire i
programmi materiale via REST. Frontend potrà collegarsi quando
arriva.

### Prossimo step

Sub 4.4: builder algoritmico vero. Usa `risolvi_corsa` (Sub 4.2) +
le regole del programma attivo (via API o ORM diretta) per
costruire i giri materiali multi-giornata cross-notte (decisione
utente: B subito).

---

## 2026-04-26 (18) — Sprint 4.2: risolvi_corsa (funzione pura)

### Contesto

Sub 4.1 ha definito schema + modelli + validation Pydantic dei
filtri. Ora il pezzo algoritmico centrale: una funzione **pura**
(no DB, no I/O) che data una corsa + le regole di un programma +
una data, ritorna l'assegnazione vincente. È il cuore del builder
giro materiale di Sub 4.4.

### Modifiche

**Nuovo `backend/src/colazione/domain/builder_giro/risolvi_corsa.py`**:

- `AssegnazioneRisolta` (frozen dataclass): `regola_id`,
  `materiale_tipo_codice`, `numero_pezzi`.
- `RegolaAmbiguaError`: con `corsa_id` + `regole_ids`, sollevato se
  top-2 regole hanno stesse priorità + specificità.
- `determina_giorno_tipo(d: date) → str`: festività italiane via
  `holidays.italian_holidays`, weekend, feriale.
- `estrai_valore_corsa(campo, corsa, giorno_tipo)`: dispatch sui
  campi (giorno_tipo, fascia_oraria, getattr per gli altri).
- `_parse_time_str`: HH:MM o HH:MM:SS → `time`.
- `matches_filtro(filtro, corsa, giorno_tipo)`: dispatcher per i 5
  operatori (eq, in, between, gte, lte). Per `fascia_oraria` parsa
  i valori filtro (stringhe) in `time` per il confronto.
- `matches_all(filtri, corsa, giorno_tipo)`: AND su tutti i filtri.
  Lista vuota → matcha tutto (regola fallback).
- `risolvi_corsa(corsa, regole, data)`: orchestrator. Filtra,
  ordina per `(priorita DESC, specificita DESC)`, detect ambiguità
  top-2, ritorna `AssegnazioneRisolta` o `None`.

**Nuovo `backend/src/colazione/domain/builder_giro/__init__.py`**:
re-export delle 7 funzioni/classi pubbliche.

### Decisioni di design

- **Tipo del parametro `corsa`**: `Any` (lazy duck-typing). I campi
  richiesti dipendono dai filtri usati nelle regole. Il chiamante
  passa ORM o dataclass, l'importante è che abbia gli attributi
  giusti (vedi `CAMPI_AMMESSI` in `schemas/programmi.py`).
- **Tipo del parametro `regole`**: `list[_RegolaLike]` con Protocol.
  Niente lazy-load ORM: il builder carica le regole una volta per
  programma, poi le passa.
- **Specificità = `len(filtri_json)`**: numero di condizioni AND.
  Tie-break naturale tra regole con stessa priorità.
- **`fascia_oraria` con stringhe**: i valori filtro arrivano come
  stringhe `"HH:MM"` da JSONB; `corsa.ora_partenza` è `time`.
  Parsa solo per `fascia_oraria` per restare type-safe sugli altri
  campi.
- **`bool` cast esplicito** sui ritorni di `matches_filtro` per non
  far indurre mypy a `bool | Any`.

### Test

**`backend/tests/test_risolvi_corsa.py`** (41 test puri, 0.03s):

- 9 test `determina_giorno_tipo` (capodanno, Natale, 25 aprile,
  Pasqua/Pasquetta, sabato/domenica/lunedì/venerdì normali)
- 4 test `estrai_valore_corsa` (giorno_tipo, fascia_oraria,
  codice_linea, bool)
- 3 test `matches_filtro eq` (string match, no-match, bool)
- 3 test `matches_filtro in` (categoria match/no-match, giorno_tipo)
- 5 test `matches_filtro` con `fascia_oraria` (between dentro range,
  estremi inclusi, fuori, gte, lte)
- 1 test op sconosciuto raises
- 3 test `matches_all` (lista vuota, tutti match, uno falso)
- 13 test `risolvi_corsa`: nessuna regola, una regola match/no,
  fallback vuoti, priorità più alta vince, specificità tie-break,
  ambiguità (raises), ambiguità ignora terza, priorità diverse no
  ambiguità, esempi Trenord realistici (S5 mattina/pomeriggio/
  weekend, treno specifico vince su linea)

Le 3 fixture dataclass `FakeCorsa` e `FakeRegola` simulano gli ORM
con i campi minimi.

### Verifiche

- `pytest`: **185/185 verdi** (era 144, +41 nuovi)
- `ruff check` + `format`: tutti verdi
- `mypy strict`: no issues in **39 source files** (era 38, +1
  risolvi_corsa.py)

### Stato

Sub 4.2 chiuso. Algoritmo di risoluzione corsa pronto, isolato dal
DB, testato in profondità. Pronto per essere usato dal builder
multi-giornata di Sub 4.4.

### Prossimo step

Sub 4.3: API REST CRUD per `programma_materiale` + regole. Il
pianificatore deve poter creare/modificare programmi via UI (quando
arriva).

---

## 2026-04-26 (17) — Sprint 4.1: schema DB + modelli SQLAlchemy + Pydantic

### Contesto

Doc PROGRAMMA-MATERIALE.md v0.2 validato dall'utente ("iniziamo con
questo schema per ora poi vediamo se modificare qualcosa"). Procedo
con l'implementazione del modello dati: migration 0005 + modelli
ORM + schemi Pydantic con validazione robusta dei filtri.

### Modifiche

**`backend/alembic/versions/0005_programma_materiale.py`** (nuova):
- `CREATE TABLE programma_materiale` (14 colonne, 5 check constraint,
  3 indici)
- `CREATE TABLE programma_regola_assegnazione` (8 colonne, 2 check,
  3 indici inclusi GIN su `filtri_json`)
- ALTER `giro_blocco`: aggiunti `is_validato_utente BOOLEAN` e
  `metadata_json JSONB`. Estesi i constraint
  `giro_blocco_tipo_check` e `giro_blocco_link_coerente` per
  ammettere `'aggancio'` e `'sgancio'` (pre-condizione per Sprint
  4.4 builder che li produrrà).

**`backend/src/colazione/models/programmi.py`** (nuovo):
- `ProgrammaMateriale` (14 campi mappati)
- `ProgrammaRegolaAssegnazione` (con `filtri_json` JSONB)

**`backend/src/colazione/models/giri.py`**: aggiunti `is_validato_utente`
e `metadata_json` su `GiroBlocco` (import `Boolean` da SQLAlchemy).

**`backend/src/colazione/schemas/programmi.py`** (nuovo, ~250 righe):

Validazione robusta dei filtri tramite la classe `FiltroRegola`:
- 11 campi ammessi (`CAMPI_AMMESSI`): codice_linea, direttrice,
  categoria, numero_treno, rete, codice_origine, codice_destinazione,
  is_treno_garantito_feriale/festivo, fascia_oraria, giorno_tipo
- 5 operatori (`OP_AMMESSI`): eq, in, between, gte, lte
- Compatibilità campo×op (`_CAMPO_OP_COMPATIBILI`):
  - bool: solo `eq`
  - fascia_oraria: solo between/gte/lte
  - stringhe: eq/in
- Shape valore coerente con op:
  - `eq/gte/lte` → scalare
  - `in` → lista non vuota
  - `between` → lista di esattamente 2
- Validazione semantica:
  - `giorno_tipo` valori in {feriale, sabato, festivo}
  - `fascia_oraria` parsabile come HH:MM o HH:MM:SS

`StrictOptions` (6 flag bool default false). `ProgrammaMaterialeCreate`
(con regole nested), `ProgrammaMaterialeUpdate`, schemi `Read` ORM-
ready.

### Test

**`backend/tests/test_programmi.py`** (nuovo, 31 test):

- 6 casi positivi `FiltroRegola` (linea, categoria, fascia,
  giorno_tipo, bool)
- 9 casi negativi (campo non ammesso, op non ammesso, op
  incompatibile, eq con lista, in vuoto, between con 1 solo
  elemento, giorno_tipo "domenica", fascia formato errato, extra
  field)
- 3 test `StrictOptions` (default, personalizzata, extra field)
- 5 test `ProgrammaMaterialeCreate` (minimo, validità invertita,
  stagione invalida, regole nested, propagazione errori filtri)
- 2 test `ProgrammaRegolaAssegnazioneCreate` (numero_pezzi=0,
  priorita>100)
- 6 test ORM smoke (registrazione metadata, columns attese,
  istanziabilità, GiroBlocco ha nuovi campi)

**`backend/tests/test_models.py`**: `EXPECTED_TABLE_COUNT` 31 → 33.
**`backend/tests/test_schemas.py`**: `EXPECTED_SCHEMA_COUNT` 31 → 38.

### Verifiche

- `alembic upgrade head` applicato OK (migration `c4f7a92b1e30 →
  a8e2f57d4c91`)
- `pytest`: **144/144 verdi** (era 113, +31 test programmi)
- `ruff check` + `ruff format`: tutti verdi
- `mypy strict`: no issues in **38 source files** (era 36, +2:
  models/programmi + schemas/programmi)

### Stato

Sub 4.1 chiuso. Schema dati + ORM + validazione filtri pronti per
l'algoritmo `risolvi_corsa` di Sub 4.2.

### Prossimo step

Sub 4.2: funzione pura `risolvi_corsa(corsa, programma, data) →
AssegnazioneRisolta | None` in `domain/builder_giro/`. Tests puri,
no DB.

---

## 2026-04-26 (16) — Sprint 4.0 v0.2: refinement post-feedback utente

### Contesto

L'utente ha letto v0.1 e dato 5 risposte mirate che richiedono
modifiche significative al modello dati prima di procedere a SQL.

### Risposte utente → modifiche al doc

1. *"Metti più info possibili"* (scope estesi)
   → §2.3: il modello passa da `scope_tipo` enum a **lista di filtri
   AND** estendibile su 12+ campi (codice_linea, direttrice,
   categoria, numero_treno, rete, codice_origine, codice_destinazione,
   is_treno_garantito_feriale/festivo, fascia_oraria, giorno_tipo,
   valido_in_data). Schema SQL: `filtri_json JSONB` con index GIN.

3. *"Aggancio/sgancio: la decisione deve avvenire manualmente, il
   sistema può dire 'questo dovrebbe agganciare'"*
   → §5.2: il builder PROPONE stazione candidata, l'utente DECIDE.
   Aggiunto campo `is_validato_utente` su `giro_blocco`. Strict
   flag `no_aggancio_non_validato` blocca pubblicazione se ci sono
   eventi non confermati.

4. *"La fascia oraria è indicativa, non rigida"*
   → §2.4: il modello tiene fasce esatte, ma il builder ragiona
   morbido sulle borderline. Parametro `fascia_oraria_tolerance_min`
   sul programma (default 30 min). Corse entro tolleranza generano
   note "borderline" che il pianificatore valuta.

5. *"Voglio molto più granularità per strict mode"*
   → §2.7 + §6.8: passa da flag globale a JSONB `strict_options_json`
   con 6 flag indipendenti (no_corse_residue, no_overcapacity,
   no_aggancio_non_validato, no_orphan_blocks,
   no_giro_non_chiuso_a_localita, no_km_eccesso). Editing tutto
   false (tolerant), pre-pubblicazione tutto true (strict).

6. *"Multi-giornata cross-notte: B (subito), inutile fare A poi
   lavorare per B"*
   → §6.7: il builder gestisce da subito giri che attraversano la
   notte. `n_giornate_default` sul programma + 3 criteri di
   chiusura giro (rientro a località, n giornate raggiunte, km
   superati).

### Modifiche al doc PROGRAMMA-MATERIALE.md

Versione v0.2 — riscrittura sezioni:
- §2.2-2.3 nuova ontologia "regola = lista di filtri AND"
- §2.4 fasce indicative + tolerance
- §2.7 strict_options_json granulare (sostituisce strict_mode bool)
- §3.1 nuovo schema SQL con filtri_json + tolerance + JSONB strict
- §3.2 schema dei filtri (Pydantic-validable)
- §4.1 algoritmo risolvi_corsa con matches_all + RegolaAmbiguaError
- §5 aggancio/sgancio con stazione_proposta + is_validato_utente
- §6.7 multi-giornata cross-notte come prima cittadina
- §7 6 esempi reali (era 4)

### Stato

- [x] Doc v0.2 scritto
- [ ] Validazione utente sulle 5 modifiche (in corso)
- [ ] Sub 4.1: migration 0005 + modello SQLAlchemy

### Prossimo step

Conferma utente che il v0.2 è coerente con la sua visione →
parte 4.1.

---

## 2026-04-26 (15) — Sprint 4.0: disegno PROGRAMMA-MATERIALE

### Contesto

Diagnosi pre-Sprint 4 (builder giro materiale). Letti documenti
storici `ALGORITMO-BUILDER.md` e `ARCHITETTURA-BUILDER-V4.md`:
risultano essere sul **builder PdC**, non giro materiale. Il
documento corretto per Sprint 4 è `LOGICA-COSTRUZIONE.md` §3
(Algoritmo A: PdE → Giro Materiale).

**Trovato bloccante critico**: il vincolo §3.3.4 dell'algoritmo dice
"tutti i blocchi del giro condividono lo stesso tipo materiale".
Per applicarlo serve il mapping `corsa → tipo_materiale`. Verifica
empirica sul file Trenord 2025-2026 reale: **27 colonne** del PdE
relative al tipo rotabile (`Tipologia Treno × 9`,
`CATEGORIA POSTI × 9`, `VINCOLO × 9`) sono **completamente vuote**
(0 righe popolate su 10579). Il PdE Trenord non specifica il
rotabile.

### Decisione architetturale (utente, esplicita)

> *"Prendere dal turno materiale solo il materiale rotabile che oggi
> Trenord utilizza, e in fase di programmazione inserire noi i dati,
> ovvero quanti km, che tipo di materiale per quella tratta. Questo
> genera un algoritmo tutto nostro, non siamo vittime di copia e
> incolla."*

Il paradigma cambia da **"PdE → Algoritmo → Giri"** a **"PdE +
Programma Materiale (input umano) → Algoritmo → Giri"**. COLAZIONE
diventa lo strumento di programmazione vero, non un parser dei
sistemi Trenord. Multi-tenant: ogni azienda compila il suo
programma.

### Modifiche

**Nuovo `docs/PROGRAMMA-MATERIALE.md`** (draft v0.1, ~600 righe):

- **Visione**: programma materiale come registro autorevole delle
  scelte di programmazione del pianificatore. Versione fungibile
  prima (quantità per tipo), individuale poi (matricola per pezzo,
  obbligatoria in futuro per integrazione manutenzione).
- **Concetti**: programma + regola_assegnazione con scope
  (direttrice/codice_linea/categoria_linea/corsa_specifica) +
  filtri (fascia oraria, giorno_tipo) + assegnazione (tipo,
  numero_pezzi).
- **Modello dati v0.1**: 2 tabelle nuove (`programma_materiale`,
  `programma_regola_assegnazione`), DDL completo con check
  constraint e indici.
- **Risoluzione corsa**: funzione pura `risolvi_corsa(corsa, prog,
  data) → AssegnazioneRisolta | None` con priorità + tie-break per
  specificità.
- **Composizione dinamica** (cit. utente: "ALe711 in singola fino
  alle 16, poi aggancia 3 pezzi per fascia pendolare"): emerge
  naturalmente dalla sovrapposizione di regole con fasce orarie
  diverse. Algoritmo di rilevamento delta `+N`/`-N` → eventi
  `aggancio`/`sgancio` come `tipo_blocco`.
- **Edge case**: sovrapposizione regole, strict_mode, capacità
  dotazione, programmi sovrapposti, materiale non in dotazione.
- **Esempi reali Trenord**: 4 casi (S5 cambio fascia, TILO
  Svizzera, treno specifico, default categoria).
- **Versione individuale** (futura): anticipo modello `rotabile_individuale`
  + tabella di link, migrazione graduale fungibile→individuale via
  campo opzionale `assegnazione_individuale_json` su `giro_blocco`.

### Decisioni architetturali prese in questo doc (da validare)

1. **Scope tipo enum** con 4 valori: `direttrice`, `codice_linea`,
   `categoria_linea`, `corsa_specifica`.
2. **Priorità numerica** (0-100) con default suggeriti per scope
   tipo. Pianificatore può forzare manualmente.
3. **Tie-break su specificità** (numero filtri attivi).
4. **Corsa di confine fascia oraria**: la **partenza** decide
   (semplificazione realistica).
5. **Strict mode globale al programma** (non per regola).

### Stato

- [x] Doc v0.1 scritto
- [ ] Validazione utente
- [ ] Sub 4.1: migration 0005 + modello SQLAlchemy
- [ ] Sub 4.2-4.5: implementazione

### Prossimo step

Feedback utente sulle 5 decisioni architetturali sopra. Poi parto
con migration 0005.

---

## 2026-04-26 (14) — Sprint 3.7.2-3.7.3: bulk INSERT + quick wins

### Contesto

Dopo aver chiuso 3.7.1 (delta-sync correttezza), ottimizzazioni
performance sull'import del PdE Trenord reale.

### Modifiche `pde_importer.py`

**Bulk operations (3.7.2)**:
- INSERT corse in chunk da 500 (limite ~32k bind params di Postgres)
- INSERT composizioni in chunk da 2000
- `pg_insert(...).values(payloads).returning(id)` ritorna gli id
  nell'ordine dei VALUES (garanzia Postgres) → allineamento con i
  `parsed` via `zip(strict=True)`
- Eliminato il loop "1 INSERT per corsa" che faceva ~10579 round-trip

**Quick wins (3.7.3)**:
- `read_pde_file()` spostato **dopo** il check di idempotenza: skip
  un file già visto non legge più il file Numbers (read = ~10s)
- `func.now()` → `func.clock_timestamp()` per `completed_at` di
  `corsa_import_run`. Postgres `now()` è alias di `transaction_timestamp`
  → tutti gli INSERT in una transazione hanno lo stesso timestamp e
  `completed_at - started_at = 0`. Con `clock_timestamp()` la durata
  reale del run viene salvata.

### Misure end-to-end (file Trenord 10579 righe)

| Operazione | Sprint 3.6 | Sprint 3.7.1 | **Sprint 3.7 finale** |
|---|---|---|---|
| Primo import (DB vuoto) | 52.3s | 69.4s | **30.3s** |
| Skip idempotente | 10.4s | 10.4s | **0.1s** |
| Force re-import (id stabili) | n/a | 16.7s | **16.4s** |
| Perdita dati | 53 corse | 0 | **0** |
| `dur_s` in DB | 0 (bug) | 0 (bug) | **valore reale** ✓ |

DB post-import: 10579 corse, 95211 composizioni, 163 stazioni, 2 run.
**10571 hash unici + 8 duplicati preservati** = invariante "no train
left behind" verificata sul file reale.

### Verifiche CI

- `pytest`: 113/113 verdi (invariato)
- `ruff` + `mypy strict`: tutti verdi (36 source files)

### Stato

**Sprint 3.7 chiuso completamente**. Importer PdE production-ready:
correttezza (no perdita dati), performance (30s primo import, 0.1s
skip), idempotenza (SHA-256 file), id stabili (delta-sync), invariante
forte (rollback se inconsistenza).

### Prossimo step

Sprint 4 — builder giro materiale dal PdE. Riferimenti:
- `docs/ALGORITMO-BUILDER.md` (storico, da riadattare)
- `docs/ARCHITETTURA-BUILDER-V4.md` (storico, da riadattare)

Le 10579 corse + 95211 composizioni in DB sono la base per
costruire i giri materiali. `corsa.id` stabile fra re-import del
PdE → ok per FK del giro.

---

## 2026-04-26 (13) — Sprint 3.7.1: delta-sync "no train left behind"

### Contesto

Smoke test sul file PdE Trenord reale (`All.1A5_14dic2025-12dic2026_TRENI
e BUS_Rev5_RL.numbers`, 6.9 MB, 10579 righe) ha rivelato un bug grave:
la chiave UNIQUE business `(azienda_id, numero_treno, valido_da)`
collassava silenziosamente **53 righe del PdE** (corse perse). Indagine:

| Chiave testata | Collisioni residue |
|---|---|
| `(numero, valido_da)` | 51 |
| `(numero, rete, valido_da)` | 17 |
| `(numero, rete, valido_da, valido_a, cod_dest)` | 11 |
| `(numero, rete, valido_da, valido_a, cod_dest, VCO)` | 6 |

Esempi reali: Treno 2277 RFI (Mi.Garibaldi→Bergamo) e Treno 2277 FN
(Mi.Cadorna→Novara) lo stesso giorno; Treno 2982 RFI con due
destinazioni alternative (Gallarate/Saronno); Treno 2840A RFI con
"variazione commerciale autorizzata" (VCO popolata) accanto al treno
base. **Nessuna superchiave business "ragionevole" elimina tutte le
collisioni** — il PdE Trenord ha varianti su colonne marginali.

Decisione utente (esplicita): *"Il programma è per una grande azienda.
Non possiamo permetterci di perdere dati. L'obiettivo è non dimenticare
nessun treno in giro."*

### Modifiche

**`backend/alembic/versions/0004_corsa_row_hash_no_unique.py`** (nuova):
- `DELETE` di tutti i dati spuri (10526 corse, 53 perse silenziosamente)
- `DROP CONSTRAINT corsa_commerciale_azienda_id_numero_treno_valido_da_key`
- `ADD COLUMN row_hash VARCHAR(64) NOT NULL` (SHA-256 dei campi grezzi)
- `CREATE INDEX idx_corsa_row_hash` su `(azienda_id, row_hash)` — non unique
- `CREATE INDEX idx_corsa_business` su `(azienda_id, numero_treno, rete, valido_da)`

**`backend/src/colazione/models/corse.py`**: aggiunto campo `row_hash`
sul modello `CorsaCommerciale`.

**`backend/src/colazione/importers/pde_importer.py`** (refactor totale):

- **`compute_row_hash(raw_row)`**: SHA-256 deterministico. Serializzazione
  JSON con `sort_keys=True`, separator stretto, `None`/`""` equivalenti,
  tipi non JSON → `str()`.
- **`ImportSummary` con semantica delta-sync**: campi `n_total`,
  `n_create`, `n_delete`, `n_kept` (sostituiscono il vecchio `n_update`).
- **`importa_pde()` con algoritmo multiset**:
  1. SHA-256 file → check idempotenza globale
  2. Bulk SELECT `(id, row_hash)` per azienda → `defaultdict[hash → list[id]]`
  3. **Diff multiset (Counter)**: per ogni riga del file, se esiste
     un'istanza non-matchata in DB con quel hash → kept; altrimenti
     INSERT. Esistenti che eccedono il count del file → DELETE.
  4. Bulk DELETE righe sparite (cascade su composizioni)
  5. INSERT righe nuove + 9 composizioni ciascuna
  6. **INVARIANTE FORTE**: `COUNT(*) corse == righe_file`. Se diverso
     → `raise RuntimeError` → rollback transazione completa.

Le righe completamente identiche nel PdE (8 coppie osservate sul file
2025-2026) **non vengono deduplicate**: ognuna ha la sua riga in DB.
Multiset semantics garantisce l'invariante.

**`docs/IMPORT-PDE.md`** §4-§5 riscritti per riflettere delta-sync.

### Test

**`tests/test_pde_importer.py`** (+5 unit test su `compute_row_hash`):
- Deterministico, key-order invariant, sensibile ai valori, sensibile
  ai campi extra, `None == ""`, gestisce datetime/Decimal.

**`tests/test_pde_importer_db.py`** (+1, totale 11 integration):
- `test_first_import_no_train_left_behind`: COUNT(*) = righe lette,
  fallisce con messaggio esplicito "PERDITA DATI" se diverso.
- `test_row_hash_populated_and_unique`: ogni corsa ha hash 64-char hex,
  38 hash unici per la fixture.
- `test_reimport_with_force_keeps_all_ids_stable`: snapshot id prima/dopo
  il force re-import → tutti id invariati (`{hash → id}` identico).
- Tests pre-esistenti adattati alla nuova semantica delta-sync.

### Verifiche end-to-end (file Trenord reale 10579 righe)

- **Run 61 (DB pulito)**: `total=10579 (kept=0 create=10579 delete=0)`,
  durata 69.4s. Invariante 10579=10579 ✓.
- **Run 62 (force re-import)**: `total=10579 (kept=10579 create=0
  delete=0)`, durata 16.7s, **id stabili** (all hash matchano).
- **Run 63 (skip idempotente)**: skip totale, run riusato, 10.4s.

DB post-import: 10579 corse, 95211 composizioni (10579×9), 163 stazioni,
2 run completed.

### Verifiche CI

- `pytest`: **113/113 verdi** (era 106, +7: 5 unit hash + 1 row_hash db
  + 1 stable-ids; il vecchio `test_reimport_with_force_overwrites_as_update`
  è stato rinominato/riscritto con nuova semantica)
- `ruff check` + `ruff format`: tutti verdi
- `mypy strict`: no issues in **36 source files** (invariato)

### Stato

**No train left behind verificato**. Sprint 3.7.1 (delta-sync core) chiuso.
Restano in coda nello stesso Sprint 3.7:

- 3.7.2 Performance: bulk INSERT chunked (target 69s → ~10s)
- 3.7.3 Quick wins: `read_pde_file` dopo idempotency check (skip 10s →
  ~1s); `clock_timestamp()` per `dur_s` reale in DB

### Prossimo step

Bulk operations (commit successivo).

---

## 2026-04-26 (12) — FASE D Sprint 3.6: DB importer + idempotenza + CLI

### Contesto

Chiusura Sprint 3.6 del PIANO-MVP. Il parser PdE puro (Sprint 3.1-3.5)
era pronto, mancava il pezzo che lo collega al DB:

- Bulk insert su `corsa_commerciale` + `corsa_composizione` + upsert
  dinamico delle `stazione` di cui non c'è seed
- Idempotenza basata su SHA-256 del file (skip se già importato, salvo
  `--force`)
- CLI argparse con `--file`, `--azienda`, `--force`
- Tracking dell'esecuzione in `corsa_import_run`

Tutto in **una transazione unica** per atomicità (rollback completo
in caso di errore).

### Modifiche

**Nuovo `backend/src/colazione/importers/pde_importer.py`** (~330 righe):

- `compute_sha256(path)`: hash streaming in chunk da 64KB
- `get_azienda_id(session, codice)`: risolve `codice` → `id`, solleva
  ValueError se non esiste
- `find_existing_run(session, hash, azienda_id)`: cerca run completato
  con stesso hash; più recente prima
- `collect_stazioni(parsed_rows, raw_rows)`: estrae `codice → nome`
  dalle 4 colonne PdE (Origine, Destinazione, Inizio CdS, Fine CdS),
  dedup, fallback a `codice` se nome vuoto
- `upsert_stazioni(session, stazioni, azienda_id)`: bulk INSERT con
  `ON CONFLICT (codice) DO NOTHING`
- `_corsa_payload(parsed, azienda_id, run_id)`: mappa `CorsaParsedRow`
  → 35 colonne `corsa_commerciale`
- `_composizione_rows(corsa_id, parsed)`: 9 dict per insert
- `upsert_corsa(session, parsed, azienda_id, run_id)`: SELECT esistente
  per chiave `(azienda_id, numero_treno, valido_da)`; UPDATE+REPLACE
  composizioni se trovata, INSERT+9 composizioni altrimenti
- `importa_pde(file_path, azienda_codice, force=False)`: top-level
  orchestrator a 5 step (hash+read fuori transazione, poi tutto in
  `session_scope()`)
- `main(argv)`: CLI argparse, exit code 0/1/2

**`docs/IMPORT-PDE.md`**: aggiornato §9.2 + §9.5 — comando passa da
`colazione.importers.pde` a `colazione.importers.pde_importer`. Il
modulo `pde.py` resta il parser puro (decisione utente Sprint 3.5).

**`backend/data/pde-input/README.md`**: stesso aggiornamento + nota
su `--force`.

### Test (24 nuovi: 14 unit + 10 integration)

**`tests/test_pde_importer.py`** (14 unit, no DB):
- `compute_sha256`: deterministico, sensibile al contenuto, vector
  NIST FIPS 180-4 (`abc` → noto), streaming su file >64KB
- `collect_stazioni`: dedup codici, first-name-wins, include CdS,
  skip None, fallback a codice come nome
- `_corsa_payload`: 13 chiavi NOT NULL presenti, Decimal preservato,
  optional None passa come None (non missing)
- `_composizione_rows`: 9 entry con corsa_id, attributi preservati

**`tests/test_pde_importer_db.py`** (10 integration, DB-skipif):
- Primo import: 38 corse, 342 composizioni, run completato (con
  source_hash 64-char hex), stazioni create dinamicamente con FK
  valide su tutte le 38 corse
- Idempotenza: re-import = skip, run_id stesso, no duplicato di run
- `--force`: 0 create + 38 update, run_id nuovo, 342 composizioni
  preservate (replace non duplica), 2 run totali
- Round-trip: treno 13 in DB ha tutti i campi attesi (rete=FN,
  origine=S01066, gg_anno=365, valido_in_date len=383)
- 9 composizioni del treno 13 con tutte le combinazioni stagione×giorno
- Edge cases: azienda inesistente → ValueError, file mancante →
  FileNotFoundError

### Verifiche end-to-end manuali

- `--help`: usage chiaro
- File mancante → exit 2 + messaggio
- Primo run sulla fixture: `✓ Run ID 37: 38 create, 0 update, 23 warning, 0.3s`
- Re-run: `⊘ skip: file già importato (run 37 il 2026-04-26 09:26), 0.1s`
- Re-run con `--force`: `✓ Run ID 38: 0 create, 38 update, 23 warning, 0.3s`

### Verifiche CI

- `pytest`: **106/106 verdi** (era 82, +24: 14 unit + 10 integration)
- `ruff check` / `ruff format`: tutti verdi (52 file)
- `mypy strict`: no issues in **36 source files** (era 35, +1
  pde_importer.py)

### Stato

Sprint 3 chiuso (3.1-3.6). Importer PdE end-to-end funzionante:
parser puro + DB + idempotenza + CLI. Pronto per importare il file
Trenord reale (10580 corse) quando l'utente lo richiede.

### Prossimo step

PIANO-MVP §4 — fine Sprint 3 (Strato 1 LIV 1 popolato). Possibili
successivi:

- **Sprint 4** (Strato 2): builder giro materiale dal PdE — primo
  pezzo di logica algoritmica nativa. Riferimento `docs/ALGORITMO-BUILDER.md`
  + `docs/ARCHITETTURA-BUILDER-V4.md` (storici, da riadattare).
- **Sprint extra**: import del file PdE Trenord reale (smoke test
  performance: target <30s per 10580 corse).

---

## 2026-04-26 (11) — Sprint 3 raffinamento: testo Periodicità = verità

### Contesto

Iterazione su Sprint 3 dopo discussione con utente. Il commit
precedente lasciava 8/38 righe della fixture (~21%) con `valido_in_date`
"approssimativo" e parser che falliva il cross-check Gg_*. L'utente
ha chiarito:

1. Il testo **`Periodicità` è la fonte di verità**, non `Codice Periodicità`.
2. Avere un calendario festività italiane interno al codice (sempre
   aggiornato per qualsiasi anno).

### Modifiche

**Nuovo `backend/src/colazione/importers/holidays.py`**:
- `easter_sunday(year)`: algoritmo gaussiano-gregoriano (verificato per
  2024-2030)
- `italian_holidays(year)`: 12 festività civili italiane (10 fisse +
  Pasqua + Pasquetta calcolate dinamicamente)
- `italian_holidays_in_range(start, end)`: subset in un intervallo

Disponibile come utility per il builder giro materiale e altre logiche.
**NON usato** in `compute_valido_in_date` (vedi sotto).

**`importers/pde.py` — aggiornamenti parser**:

1. `PeriodicitaParsed` ha nuovo campo `filtro_giorni_settimana: set[int]`
   (0=lun ... 6=dom).
2. `parse_periodicita` riconosce frasi come "Circola il sabato e la
   domenica" → filtro globale (solo se la frase contiene SOLO nomi
   giorno-settimana, no intervalli/date).
3. `compute_valido_in_date` applica:
   - Default base: `is_tutti_giorni` o `filtro_giorni_settimana`
   - Apply intervals (override del filtro: tutti i giorni dell'intervallo)
   - Apply dates esplicite
   - Skip intervals + dates
4. **NESSUN auto-suppress festività**: il parser segue letteralmente il
   testo. Se `Periodicità` dice "Circola tutti i giorni", il treno
   circola anche a Natale. La regola dell'utente: testo = verità.
5. `Codice Periodicità` rimane non parsato (dato informativo).
6. Cross-check `Gg_*` declassato a **warning informativo**: non blocca
   l'import. Se il testo Periodicità diverge dai conteggi Trenord, il
   parser segue il testo e logga la discrepanza.

### Risultati sulla fixture (38 righe)

- **33/38 (87%)** righe hanno `valido_in_date` = Gg_anno PdE → zero warning
- **5/38 (13%)** righe hanno discrepanza, ma il parser segue il testo:
  - Treni 83/84 (Δ=+39): testo dichiara 5 grandi intervalli, Codice
    Periodicità interno conta meno. Trenord usa Codice per Gg_anno.
  - Treni 393/394 (Δ=+1), 701 (Δ=+2): off-by-piccolo simile.

Per questi 5, il parser dice `valido_in_date_json` = quello che il
testo afferma; le warning loggano la discrepanza per audit.

### Test aggiornati

**`tests/test_holidays.py`** (7 nuovi):
- Pasqua corretta per 2024-2030
- 12 festività italiane in un anno
- Subset in range parziale
- Range cross-anno (cattura festività di entrambi gli anni)

**`tests/test_pde_periodicita.py`** (+5 nuovi):
- "Circola il sabato e la domenica" → `{5, 6}`
- "Circola il sabato" → `{5}`
- Filtro + override intervals (treno 786 reale)
- Frase con intervallo NON setta filtro globale
- `compute_valido_in_date` con filtro + override

**`tests/test_pde_row_parser.py`** (sostituito 2 test):
- `test_high_match_with_pde_gg_anno`: ≥80% righe combaciano (era 75%)
- `test_warnings_are_info_not_errors`: warning devono iniziare con
  `gg_*:` (sono cross-check info, non bug di parsing)

### Verifiche

- `pytest`: **82/82 verdi** (era 69, +13 nuovi: 7 holidays + 5 periodicità + nuove varianti)
- `ruff check` / `ruff format`: tutti verdi
- `mypy strict`: no issues in **35 source files** (era 34, +1 holidays.py)

### Stato

Sprint 3.1-3.5 raffinato secondo regole utente. Parser pronto per
Sprint 3.6 (DB + idempotenza + CLI).

### Prossimo step

Sprint 3.6-3.8 invariato:
- `pde_importer.py` con bulk insert + tracking
- Idempotenza SHA-256
- CLI argparse

---

## 2026-04-26 (10) — FASE D Sprint 3.1-3.5: Parser PdE puro

### Contesto

Sprint 3.1-3.5 del PIANO-MVP: parser puro PdE, no DB. Pipeline lettura
file → dataclass intermedio → calcolo `valido_in_date_json`
denormalizzato. DB + idempotenza + CLI rimandati a Sprint 3.6-3.8.

### Modifiche

**Nuovo `backend/src/colazione/importers/pde.py`** (~480 righe):

- **3 Pydantic models intermedi**:
  - `PeriodicitaParsed`: output del parser testuale (apply/skip
    intervals + dates + flag is_tutti_giorni)
  - `ComposizioneParsed`: 1 di 9 combinazioni stagione × giorno_tipo
  - `CorsaParsedRow`: corsa completa con composizioni nested + warnings

- **Reader** (`read_pde_file`): auto-detect dall'estensione, supporta
  `.numbers` (via `numbers-parser`) e `.xlsx` (via `openpyxl`). Header
  riga 0 → dict[colonna → valore].

- **Helper di normalizzazione**: `_to_str_treno` (float `13.0` → `'13'`),
  `_to_date`, `_to_time`, `_to_opt_decimal`, `_to_bool_si_no` (`SI`/`NO`
  + bool nativi).

- **`parse_corsa_row`**: mappa 1:1 i campi PdE → modello DB
  `corsa_commerciale`. Calcola `giorni_per_mese_json` (16 chiavi
  `gg_dic1AP`...`gg_anno`) e `valido_in_date_json` (lista ISO date).

- **`parse_composizioni`**: estrae le 9 righe di `corsa_composizione`
  (3 stagioni × 3 giorno_tipo × 6 attributi). Le 9 sono sempre
  presenti, anche se vuote.

- **`parse_periodicita`** (regex-based): tokenizza il testo per frasi
  su `". "`, riconosce 5 sub-pattern:
  - `Circola tutti i giorni` → `is_tutti_giorni=True`
  - `Circola dal X al Y` (anche multipli `, dal Z al W`)
  - `Circola DD/MM/YYYY, DD/MM/YYYY, ...`
  - `Non circola dal X al Y`
  - `Non circola DD/MM/YYYY, dal Z al W, ...` (misti)

- **`compute_valido_in_date`**: applica la periodicità all'intervallo
  `[valido_da, valido_a]`. Algoritmo:
  1. Se `is_tutti_giorni`, popola tutto il range
  2. Aggiungi `apply_intervals` (clip al range)
  3. Aggiungi `apply_dates` (filter al range)
  4. Sottrai `skip_intervals` e `skip_dates`

- **`cross_check_gg_mensili`**: confronta date calcolate con i
  `Gg_*` PdE per gen-nov (anno principale), dicembre split (dic1/dic2,
  dic1AP/dic2AP), e totale `gg_anno`. Ritorna lista di warning,
  vuota = match perfetto.

### Limite noto MVP (documentato in modulo)

Il parser usa **solo il campo testuale `Periodicità`**. Il PdE Trenord
ha anche `Codice Periodicità`, un mini-DSL con filtri giorno-della-
settimana (token tipo `G1-G7`, `EC`, `NCG`, `S`, `CP`, `P`, `ECF`)
che è la fonte di verità completa. Per i treni con filtri weekend
(es. `EC G6, G7 ...` = solo sabato/domenica), il `valido_in_date_json`
calcolato è **approssimativo** (eccessivo del ~50%).

Sulla fixture reale: **30/38 righe** (~79%) hanno periodicità
"semplice" e passano cross-check. **8/38 righe** (~21%) hanno
periodicità complessa con warning.

Decisione MVP: accetta i warning, importa comunque, log centralizzato.
Parser DSL `Codice Periodicità` rimandato a v1.x.

### Test (3 file, 31 nuovi test)

**`tests/test_pde_reader.py`** (5):
- Fixture esiste, ritorna 38 righe, 124 colonne
- Tipi: Periodicità è str, Treno 1 non None
- Formato non supportato → `ValueError`

**`tests/test_pde_periodicita.py`** (15):
- Empty text, `Circola tutti i giorni` puro, con skip interval, apply
  interval only, apply dates short list, `tutti i giorni dal X al Y`
  → apply_interval (NON is_tutti), long apply dates list, skip mixed,
  date interne intervallo non doppie
- `compute_valido_in_date`: tutti i giorni, minus skip, apply interval,
  apply dates filtered, skip overrides apply, clip to validity range

**`tests/test_pde_row_parser.py`** (11):
- Tutte le 38 righe parsano senza eccezioni
- Ogni riga ha 9 composizioni con keys complete (3×3 stagioni×giorni)
- ≥75% righe passano cross-check (threshold MVP, attualmente 79%)
- Sanity inverso: parser DEVE flaggare le righe complesse (non bug
  silenziosi)
- Riga 0 (treno 13 FN Cadorna→Laveno): campi base, valido_in_date
  popolato correttamente (383 giorni dal 14/12/2025 al 31/12/2026)
- Decimal preservati (`Decimal("72.152")` per km_tratta)
- Numero treno normalizzato a stringa intera (no trailing `.0`)

### Verifiche

- `pytest`: **69/69 verdi** (era 38/38, +31 nuovi)
- `ruff check`: All checks passed
- `ruff format --check`: 47 files formatted
- `mypy strict`: no issues found in **34 source files** (era 33, +1
  importers/pde.py)

### Stato

Sprint 3.1-3.5 completo. Parser PdE puro funzionante su fixture reale.
Limite documentato (filtro giorni settimana → v1.x).

### Prossimo step

**Sprint 3.6-3.8 — DB + CLI + idempotenza**:

- 3.6 `pde_importer.py`: orchestrator con bulk insert + transazione
  unica + tracking `corsa_import_run`
- 3.7 Idempotenza: SHA-256 file → skip se già importato; upsert per
  `(azienda_id, numero_treno, valido_da)`
- 3.8 CLI argparse: `python -m colazione.importers.pde --file ... --azienda ...`

Test integration end-to-end fixture → DB temp.

---

## 2026-04-26 (9) — Doc operativa import PdE

### Contesto

L'utente vuole tenere a portata di mano i comandi per importare il
PdE reale, così non si dimentica fra mesi. Documentati in 2 posti
complementari:

1. `docs/IMPORT-PDE.md` §9 — spec + workflow completo (per chi cerca
   "come funziona l'import")
2. `backend/data/pde-input/README.md` — quick reference dei comandi
   pronti copy-paste (per chi apre la cartella)

### Modifiche

**`docs/IMPORT-PDE.md`** §9 ricostruita: prima era 1 riga astratta
(`uv run ... --file ... --azienda trenord`), ora ha 6 sotto-sezioni:
- 9.1 Pre-requisiti (docker compose + alembic upgrade)
- 9.2 Procedura import (mkdir + cp + comando)
- 9.3 Output atteso
- 9.4 Verifica post-import (query DB)
- 9.5 Re-import + flag `--force`
- 9.6 Aggiornare la fixture quando arriva un nuovo PdE

**Nuovo `backend/data/pde-input/README.md`**: quick reference della
cartella locale. Ricorda comandi essenziali, convenzioni di
naming, workflow per multipli anni di PdE.

**`.gitignore`** raffinato: era `backend/data/pde-input/`
(ignora tutta la cartella). Ora `backend/data/pde-input/*` +
eccezione `!backend/data/pde-input/README.md`. Risultato verificato
con `git check-ignore`:
- `fake.numbers` → ignorato (regola riga 80)
- `README.md` → tracciato (eccezione riga 81)

### Verifica

`git check-ignore -v backend/data/pde-input/fake.numbers` ritorna
match con la regola `*` → ignorato. `git check-ignore -v README.md`
ritorna match con la regola `!` → committato.

### Stato

Fatto. La procedura di import PdE è documentata + accessibile sia
via `docs/` (spec) sia via cartella locale (cheat sheet).

### Prossimo step

Sprint 3.1+ vero — `importers/pde.py` con parser, idempotenza, CLI.
Stesso piano di prima, niente cambio scope.

---

## 2026-04-26 (8) — Sprint 3 prep: fixture PdE per test

### Contesto

Prima di scrivere il parser PdE (Sprint 3.1+), serve una **fixture
committata** per i test unitari + CI. Il file PdE reale (10580 righe,
6.9 MB) vive sul Mac dell'utente in
`/Users/spant87/Library/Mobile Documents/com~apple~Numbers/Documents/`,
**non si committa**: è dato commerciale e cambia ogni anno.

La fixture è una mini-versione del file reale, ~40 righe scelte per
coprire tutti i pattern di periodicità, salvata come `.xlsx` (formato
portable che gira ovunque, niente dipendenza `numbers-parser` su CI
Linux).

### Modifiche

**Nuovo `backend/scripts/build_pde_fixture.py`** (~140 righe):
- One-shot script per (ri)generare la fixture quando serve
- Apre file Numbers via `numbers-parser`, categorizza ~10580 righe per
  pattern (skip/apply interval, date list, doppia composizione,
  garantito festivo)
- Selezione deterministica: prime N indici per bucket
- Scrive `.xlsx` con `openpyxl` (header + righe + sheet "PdE RL")
- CLI: `--source <numbers-path>` `--output <xlsx-path>`

**Nuovo `backend/tests/fixtures/pde_sample.xlsx`** (19.5 KB):
- 124 colonne (header completo del PdE Trenord)
- 38 righe dati selezionate
- Coverage pattern Periodicità:
  - 10 skip interval (`Non circola dal X al Y`)
  - 8 apply interval (`Circola dal X al Y`)
  - 6 date list lunga (>20 slash, ~50-100 date)
  - 14 date list corta (1-5 date)
- Numero treno arriva come `int` (openpyxl converte i float
  integer-valued — comodo per il parser)

**`.gitignore`**: aggiunta sezione PdE input
(`backend/data/pde-input/`) per quando l'utente caricherà il file
reale localmente. Convenzione path:
`backend/data/pde-input/PdE-YYYY-MM-DD.numbers`.

### Verifica

- Script eseguito sul file reale Trenord 14dic2025-12dic2026 Rev5_RL
- Fixture rilegga correttamente con openpyxl: 124 colonne + 38 righe
- Conta pattern in fixture: 10+8+6+14 = 38 ✓
- File 19.5 KB → ben sotto soglia ragionevole per commit

### Stato

Sprint 3 prep fatto. Fixture committata, builder riproducibile.

### Prossimo step

**Sprint 3.1+ — Parser PdE vero** (`backend/src/colazione/importers/pde.py`):

- Lettura file `.numbers` o `.xlsx` (auto-detect dall'estensione)
- Parser singola riga → dataclass intermedio
- Parser composizione 9 combinazioni (stagione × giorno_tipo) per i 6
  attributi (categoria_posti, doppia_comp, vincolo, tipologia,
  bici, prm)
- Parser periodicità testuale → set di date ISO
- Calcolo `valido_in_date_json` denormalizzato (cross-validato con
  totali Gg_*)
- Bulk insert + transazione + tracking `corsa_import_run` + SHA-256
  per idempotenza
- CLI argparse

Effort stimato: ~3-4 turni di lavoro (Sprint 3 è il pezzo più fragile
del PIANO-MVP, parser periodicità è critico).

---

## 2026-04-26 (7) — FASE D Sprint 2: Auth JWT (Sprint 2 COMPLETATA)

### Contesto

Sprint 2 del PIANO-MVP: autenticazione JWT custom + bcrypt, endpoint
login/refresh/me, dependencies FastAPI per autorizzazione, seed di
2 utenti applicativi.

### Modifiche

**Modulo `backend/src/colazione/auth/`** (4 file):

- `password.py`: `hash_password()` + `verify_password()` su bcrypt
  (cost factor default 12). `verify_password` ritorna False (no
  raise) per hash malformati.
- `tokens.py`: `create_access_token()` (claims: sub, type=access,
  iat, exp, username, is_admin, roles, azienda_id),
  `create_refresh_token()` (claims minimi: sub, type=refresh, iat,
  exp), `decode_token(token, expected_type)` con
  `InvalidTokenError` per firma/scaduto/tipo errato. HS256.
- `dependencies.py`: `get_current_user()` da
  `Authorization: Bearer <token>` (HTTPBearer FastAPI), no DB query
  per request — claims vivono nel JWT. `require_role(role)` factory
  + `require_admin()` factory ritornano dependency che check
  ruolo/admin (admin bypassa role check).
- `__init__.py`: ri-esporta API pubblica del modulo.

**`backend/src/colazione/schemas/security.py`** (nuovo):
- `LoginRequest`, `TokenResponse`, `RefreshRequest`, `RefreshResponse`,
  `CurrentUser`. Distinto da `schemas/auth.py` perché qui sono shape
  I/O API, non entità DB.

**`backend/src/colazione/api/auth.py`** (nuovo):
- `POST /api/auth/login`: verify password → emette access+refresh,
  aggiorna `last_login_at`. Stessa risposta 401 per username
  inesistente o password sbagliata (no info leak).
- `POST /api/auth/refresh`: decode refresh → riemette access con
  ruoli aggiornati dal DB.
- `GET /api/auth/me`: ritorna `CurrentUser` corrente (utile per
  debug + frontend "chi sono io").

**`backend/src/colazione/main.py`**: registra
`app.include_router(auth_routes.router)`.

**Migrazione `backend/alembic/versions/0003_seed_users.py`**:
- 2 utenti: `admin` (is_admin=TRUE, ruolo ADMIN) +
  `pianificatore_giro_demo` (ruolo PIANIFICATORE_GIRO)
- Password da env `ADMIN_DEFAULT_PASSWORD` / `DEMO_PASSWORD`,
  fallback `admin12345` / `demo12345` per dev locale
- Hash bcrypt calcolato a runtime (cost 12) — implica che
  down/up cambia hash ma password resta uguale
- `downgrade()`: DELETE in ordine FK-safe (ruoli prima, app_user dopo)

**`backend/pyproject.toml`**: aggiunto
`[tool.ruff.lint.flake8-bugbear] extend-immutable-calls` per
ignorare B008 sulle `Depends/Query/Path/Body/Header/Cookie/Form/
File/Security` di FastAPI (pattern standard).

**`.github/workflows/backend-ci.yml`**: aggiunto step
`Apply Alembic migrations` (`alembic upgrade head`) prima di
pytest. Necessario per i test che richiedono schema + seed
(test_models_match_db_tables, test_auth_endpoints).
**Bug fix preesistente** introdotto in Sprint 1.7 — la CI con
test_models_match_db_tables falliva perché lo schema non era
applicato. Adesso risolto.

### Test (4 file, 24 test nuovi)

**`tests/test_auth_password.py`** (5):
- hash è stringa bcrypt-prefixed
- hash è random per call (salt diverso)
- verify password corretta
- verify password sbagliata
- verify ritorna False per hash malformato

**`tests/test_auth_tokens.py`** (6):
- access token roundtrip (claims completi)
- refresh token roundtrip (claims minimi)
- decode rifiuta type errato (access usato come refresh)
- decode rifiuta token scaduto
- decode rifiuta firma sbagliata
- decode rifiuta garbage

**`tests/test_auth_endpoints.py`** (13):
- login admin (200, claims is_admin + ruolo ADMIN)
- login demo (200, ruolo PIANIFICATORE_GIRO)
- login wrong password (401)
- login unknown user (401)
- login missing fields (422 validation)
- refresh success (200 + nuovo access valido)
- refresh rifiuta access token (401)
- refresh rifiuta garbage (401)
- refresh rifiuta user_id inesistente (401)
- /me senza auth (401)
- /me con access valido (200)
- /me rifiuta refresh come access (401)
- /me rifiuta scheme non Bearer (401)

### Verifiche

- `pytest`: **38/38 verdi** (era 14/14, +24 nuovi)
- `ruff check`: All checks passed (B008 esentato per FastAPI Depends)
- `ruff format --check`: 39 files formatted
- `mypy strict`: no issues found in **33 source files** (era 28, +5
  nuovi: password, tokens, dependencies, schemas/security, api/auth)
- `alembic upgrade head` (3 migrazioni applicate)
- `alembic downgrade -1` (0003 reverted) → `app_user` count = 0
- `alembic upgrade head` (re-apply) → idempotente, conteggi
  ripristinati

Login funzionale verificato direttamente:
- admin/admin12345 → access token con `is_admin=True`, `roles=[ADMIN]`
- pianificatore_giro_demo/demo12345 → `roles=[PIANIFICATORE_GIRO]`

### Stato

**Sprint 2 COMPLETATA**. Tutto Sprint 2.1-2.5 chiuso in un commit
unico (vs ipotesi PIANO-MVP di 5 commit separati).

Backend ora ha:
- Schema DB completo (Sprint 1)
- Seed Trenord + 2 utenti applicativi (Sprint 1.6 + 2.5)
- Modelli ORM (Sprint 1.7) e schemas Pydantic (Sprint 1.8)
- Auth JWT funzionante con login/refresh/me + role-based access
  control via `require_role(...)`

### Prossimo step

**Sprint 3 — Importer PdE** (stima 3-4 giorni nel PIANO-MVP, il pezzo
più fragile):

- 3.1 `importers/pde.py` skeleton + lettura file Numbers
- 3.2 Parser singola riga → CorsaCommercialeCreate
- 3.3 Parser composizione 9 combinazioni stagione × giorno_tipo
- 3.4 Parser periodicità testuale (intervalli skip, date singole,
      date extra)
- 3.5 Calcolo `valido_in_date_json` denormalizzato
- 3.6 Bulk insert + transazione + tracking corsa_import_run
- 3.7 Idempotenza (SHA-256 file, re-import 0 nuovi insert)
- 3.8 CLI: `uv run python -m colazione.importers.pde --file ...`

Il file PdE reale Trenord è ~10580 corse, target import < 30s.
Spec dettagliata in `docs/IMPORT-PDE.md`. Servirà fixture: prendere
50 righe del file reale.

Decision aperta: il file Numbers reale del PdE 2025-12-14 → 2026-12-12
è disponibile localmente o serve l'utente per fornirlo? Da chiedere
quando si parte con Sprint 3.

---

## 2026-04-26 (6) — FASE D Sprint 1.8: Schemas Pydantic (Sprint 1 COMPLETATA)

### Contesto

Sprint 1.8 (ULTIMO della Sprint 1): schemas Pydantic per
serializzazione I/O API. Specchio dei modelli ORM in 7 file per strato.

### Modifiche

**Nuovo `backend/src/colazione/schemas/` (7 file)**:

- `anagrafica.py`: AziendaRead, StazioneRead, MaterialeTipoRead,
  LocalitaManutenzioneRead, LocalitaManutenzioneDotazioneRead,
  DepotRead, DepotLineaAbilitataRead, DepotMaterialeAbilitatoRead
- `corse.py`: CorsaImportRunRead, CorsaCommercialeRead (~30 campi),
  CorsaComposizioneRead, CorsaMaterialeVuotoRead
- `giri.py`: GiroMaterialeRead, VersioneBaseGiroRead,
  GiroFinestraValiditaRead, GiroGiornataRead, GiroVarianteRead,
  GiroBloccoRead
- `revisioni.py`: RevisioneProvvisoriaRead, RevisioneProvvisoriaBloccoRead,
  RevisioneProvvisoriaPdcRead
- `turni_pdc.py`: TurnoPdcRead, TurnoPdcGiornataRead, TurnoPdcBloccoRead
- `personale.py`: PersonaRead, AssegnazioneGiornataRead,
  IndisponibilitaPersonaRead
- `auth.py`: AppUserRead (no `password_hash` per non leakare bcrypt
  in API), AppUserRuoloRead, NotificaRead, AuditLogRead

**Pattern Pydantic v2**:
- `model_config = ConfigDict(from_attributes=True)` su ogni schema
  (parsing da modelli ORM o da dict)
- Tipi standard Python (`int`, `str`, `bool`, `datetime`, `date`,
  `time`, `Decimal`, `dict[str, Any]`, `list[Any]`)
- `Mapped[X | None] = None` per nullable, default `None`
- Niente `Create`/`Update` (verranno aggiunti quando le route
  POST/PATCH ne avranno bisogno, Sprint 4+)
- Niente nested relationships (es. `composizioni: list[...]` su
  CorsaCommerciale) — minimalismo, si arricchirà quando servirà

**`schemas/__init__.py`**: importa e ri-esporta 31 schemi, ordinato
per strato in `__all__`.

### Test

**Nuovo `backend/tests/test_schemas.py`** (6 test):
- `test_schemas_all_exported`: 31 schemi nel `__all__`, tutti
  importabili
- `test_azienda_read_from_dict_fixture`: parsing da dict (input API
  request body)
- `test_azienda_read_from_orm_instance`: parsing da Azienda ORM
  in memoria (path response_model)
- `test_localita_manutenzione_read_pool_esterno`: schema con
  campo nullable + flag bool (POOL_TILO con `is_pool_esterno=True`)
- `test_corsa_commerciale_read_with_decimal_and_time`: tipi
  complessi (time, date, Decimal, JSONB)
- `test_schemas_serialize_to_json`: output `model_dump_json()`
  serializzabile (per FastAPI response)

### Verifiche

- `pytest`: **14/14 verdi** (era 8/8, +6 nuovi su schemi)
- `ruff check`: All checks passed (autofix applicato:
  `timezone.utc` → `datetime.UTC` per Python 3.11+)
- `ruff format --check`: 34 files already formatted
- `mypy strict`: no issues found in **28 source files** (era 21,
  +7 nuovi: 7 file schemas)

### Stato

**Sprint 1 COMPLETATA**. Backend ha:
- main.py + /health + config.py (Sprint 1.1, 1.2)
- db.py async (Sprint 1.3)
- Alembic setup (Sprint 1.4)
- Migrazione 0001 con 31 tabelle (Sprint 1.5)
- Migrazione 0002 con seed Trenord (Sprint 1.6)
- 31 modelli ORM (Sprint 1.7)
- 31 schemi Pydantic Read (Sprint 1.8)

Pronto per scrivere endpoint REST (auth + corse + depositi).

### Riepilogo Sprint 1

| Passo | Output | Commit |
|-------|--------|--------|
| 1.1 | main.py + /health | (in 0.1, `83b4f85`) |
| 1.2 | config.py Pydantic Settings | (in 0.1, `83b4f85`) |
| 1.3 | db.py async + Postgres CI | `4f4edcd` |
| 1.4 | Alembic setup async | `44e8fe8` |
| 1.5 | Migrazione 0001 (31 tabelle) | `e047672` |
| 1.6 | Migrazione 0002 seed Trenord | `59455ca` |
| 1.7 | Modelli SQLAlchemy ORM (31) | `56dfaee` |
| 1.8 | Schemas Pydantic Read (31) | (questo commit) |

Effort reale Sprint 1: ~1 sessione lavoro, vs stima 2-3 giorni
del PIANO-MVP. Stima generosa ma corretta come buffer.

### Prossimo step

**Sprint 2 — Auth + utenti** (stima 2 giorni):
- 2.1 `colazione/auth/` (hash bcrypt, JWT encode/decode, dependencies)
- 2.2 Endpoint `POST /api/auth/login`
- 2.3 Endpoint `POST /api/auth/refresh`
- 2.4 Dependency `get_current_user` + `require_role`
- 2.5 Migrazione `0003_seed_users.py` → admin + pianificatore_giro_demo

Modulo `auth/` da costruire da zero. JWT custom + bcrypt come da
STACK-TECNICO.md §6. Schemas dedicati in `schemas/security.py` (non
nel `auth.py` strato 5 dei modelli).

---

## 2026-04-26 (5) — FASE D Sprint 1.7: Modelli SQLAlchemy ORM

### Contesto

Sprint 1.7 del PIANO-MVP: mappare le 31 tabelle create dalle
migrazioni 0001/0002 in classi SQLAlchemy ORM, in modo che il backend
possa usarle via session async.

### Decisione layout (deviazione dal PIANO-MVP)

PIANO-MVP §2 step 1.7 dice "(1 file per entità)" → 31 file. Ho
optato per **1 file per strato (7 file)**:
- evita 31 file da 10-20 righe (boilerplate × 7)
- entità dello stesso strato sono fortemente correlate (es. `giro_*`
  o `turno_pdc_*`)
- pattern standard nei progetti SQLAlchemy seri
- la docstring di `db.py` (Sprint 1.3) è stata aggiornata di
  conseguenza

Le 31 classi restano tutte importabili da `colazione.models`.

### Modifiche

**Nuovo `backend/src/colazione/models/` (7 file)**:

- `anagrafica.py` (Strato 0, 8 classi): Azienda, Stazione,
  MaterialeTipo, LocalitaManutenzione, LocalitaManutenzioneDotazione,
  Depot, DepotLineaAbilitata, DepotMaterialeAbilitato
- `corse.py` (Strato 1, 4 classi): CorsaImportRun, CorsaCommerciale
  (la più grossa, ~30 colonne), CorsaComposizione, CorsaMaterialeVuoto
- `giri.py` (Strato 2, 6 classi): GiroMateriale, VersioneBaseGiro,
  GiroFinestraValidita, GiroGiornata, GiroVariante, GiroBlocco
- `revisioni.py` (Strato 2bis, 3 classi): RevisioneProvvisoria,
  RevisioneProvvisoriaBlocco, RevisioneProvvisoriaPdc
- `turni_pdc.py` (Strato 3, 3 classi): TurnoPdc, TurnoPdcGiornata,
  TurnoPdcBlocco
- `personale.py` (Strato 4, 3 classi): Persona, AssegnazioneGiornata,
  IndisponibilitaPersona
- `auth.py` (Strato 5, 4 classi): AppUser, AppUserRuolo, Notifica,
  AuditLog

**`models/__init__.py`**: importa e ri-esporta tutte le 31 classi
(elenco esplicito in `__all__`, ordinato per strato).

**Stile SQLAlchemy 2.0 moderno**:
- `Mapped[T]` + `mapped_column()` per type safety
- `Mapped[dict[str, Any]]` / `Mapped[list[Any]]` per JSONB
  (mypy strict richiede tipi parametrizzati)
- `Mapped[X | None]` per nullable
- `BigInteger`, `String(N)`, `Text`, `Boolean`, `Integer`,
  `Date`, `Time`, `DateTime(timezone=True)`, `Numeric(p,s)` per i
  tipi DB
- `JSONB` da `sqlalchemy.dialects.postgresql`, `INET` per audit IP
- `server_default=func.now()` per `created_at`/`updated_at`
- `default=dict` / `default=list` per JSONB Python-side default

**Cosa NON è incluso** (intenzionalmente, per minimalismo):
- CHECK constraint (sono in DB, validazione DB-side)
- UNIQUE multi-colonna come `__table_args__` (sono in DB)
- Indici secondari (sono in DB)
- `relationship()` (verrà aggiunto in Sprint 4 quando le route ne
  avranno bisogno)

L'ORM è "specchio della struttura DB" minimale. L'autorità del
schema resta nelle migrazioni Alembic, non nei modelli.

**Aggiornato `backend/src/colazione/db.py`**: docstring di `Base`
allineata al nuovo layout per-strato.

### Test

**Nuovo `backend/tests/test_models.py`** (3 test):
- `test_models_register_on_metadata`: 31 tabelle su `Base.metadata`
- `test_models_all_exported`: `__all__` contiene 31 nomi e tutti
  importabili
- `test_models_match_db_tables`: `__tablename__` ORM matchano le
  tabelle reali in `pg_tables` (skippato se DB non configurato)

### Verifiche

- `python -c "from colazione.models import *"` → 31 classi importate
  senza errori
- `Base.metadata.tables` → 31 tabelle, nomi tutti coerenti con DB
  (verificato anche via query `pg_tables`)
- `pytest`: **8/8 verdi** (era 5/5, +3 nuovi su modelli)
- `ruff check`: All checks passed
- `ruff format`: 26 files formatted
- `mypy src/colazione`: no issues found in **21 source files**
  (era 14 prima, +7 nuovi: 7 modelli)

### Stato

Sprint 1.7 completo. Backend ha schema DB completo + dati seed +
modelli ORM tutti registrati su `Base.metadata`. Pronto per scrivere
schemas Pydantic (Sprint 1.8) e poi gli endpoint API.

### Prossimo step

Sprint 1.8 del PIANO-MVP: schemas Pydantic in
`backend/src/colazione/schemas/` per serializzazione I/O API. Naming
convention `<Entita>Read`, `<Entita>Create`, `<Entita>Update` (vedi
PIANO-MVP §2 step 1.8). Tipico parsing con `from_attributes=True` per
costruire da modello ORM.

---

## 2026-04-26 (4) — FASE D Sprint 1.6: Migrazione 0002 seed Trenord

### Contesto

Sprint 1.6 del PIANO-MVP: popolamento iniziale dati Trenord nelle
tabelle anagrafica create da 0001. Materializza la sezione §12 di
`SCHEMA-DATI-NATIVO.md` in INSERT eseguibili via Alembic.

### Modifiche

**Nuovo `backend/alembic/versions/0002_seed_trenord.py`** (~340 righe):

Dati statici come liste Python in cima al file (estratti da
`docs/SCHEMA-DATI-NATIVO.md` §12 + `data/depositi_manutenzione_trenord_seed.json`):
- `LOCALITA_MANUTENZIONE` (7 tuple)
- `DEPOT_TRENORD` (25 tuple)
- `MATERIALE_CODES` (69 codici, ordinati alfabeticamente)
- `DOTAZIONE` (84 tuple)

Helper `_sql_str()` e `_sql_bool()` per costruire VALUES SQL safe (NULL
e quoting standard).

`upgrade()` — 5 sezioni di INSERT:
- §12.1 azienda Trenord con `normativa_pdc_json` completo (15 campi
  da NORMATIVA-PDC: 510/420 min, finestre refezione 11:30-15:30 e
  18:30-22:30, FR 1/sett 3/28gg, riposo 62h, ecc.)
- §12.2 7 località manutenzione: 6 IMPMAN reali + POOL_TILO_SVIZZERA
  (`is_pool_esterno=TRUE`, `azienda_proprietaria_esterna='TILO'`)
- §12.3 25 depot PdC, tutti `tipi_personale_ammessi='PdC'`
- `materiale_tipo` (69 codici, solo `codice` + `azienda_id`, altri
  campi NULL/default — arricchimento a builder time)
- `localita_manutenzione_dotazione` (84 righe, JOIN su
  `localita_manutenzione.codice` per risolvere FK runtime)

Stile `(VALUES …) AS v CROSS JOIN azienda` come da spec §12, evita
hard-coding di `azienda_id` (auto-generato).

`downgrade()`: 5 DELETE in ordine FK-safe (figli → padri), filtrati
per `azienda_id = (SELECT id FROM azienda WHERE codice='trenord')` —
non tocca seed di altre aziende future.

POOL_TILO_SVIZZERA è creato senza dotazione (pool esterno, materiale
non gestito da Trenord). NON_ASSEGNATO del seed JSON è escluso
(placeholder applicativo).

### Verifiche locali

`alembic upgrade head` → conteggi:
- `azienda` = 1
- `localita_manutenzione` = 7
- `depot` = 25
- `materiale_tipo` = 69
- `localita_manutenzione_dotazione` = 84

Totale pezzi materiale: 1612 (974 FIORENZA + 299 NOVATE + 169 CAMNAGO
+ 92 CREMONA + 57 LECCO + 21 ISEO).

`normativa_pdc_json` verificato con `jsonb_pretty()`: 15 chiavi
presenti coi valori corretti (max_prestazione 510, refez 30, finestre
[690,930] e [1110,1350], ecc.).

`alembic downgrade -1` → 5 tabelle a 0 righe (clean).
`alembic upgrade head` (di nuovo) → conteggi identici → **idempotente**.

`pytest`: 5/5 verdi.
`ruff check`: All checks passed.
`ruff format --check`: 18 files already formatted.
`mypy src/colazione`: no issues found in 14 source files.

### Stato

Sprint 1.6 completo. DB Postgres ha azienda Trenord + 7 località
manutenzione + 25 depot + 69 tipi materiale + 84 righe dotazione.
Schema 0001 + seed 0002 = base anagrafica pronta per Strato 1 (corse
PdE).

### Prossimo step

Sprint 1.7: modelli SQLAlchemy ORM in `backend/src/colazione/models/`,
una classe per entità (Azienda, LocalitaManutenzione, Depot,
MaterialeTipo, …). Usano `Base` da `db.py` (Sprint 1.3) e mappano le
tabelle create dalle migrazioni 0001/0002.

---

## 2026-04-26 (3) — FASE D Sprint 1.5: Migrazione 0001 (31 tabelle)

### Contesto

Sprint 1.5 del PIANO-MVP: il pezzo grosso. Materializza
SCHEMA-DATI-NATIVO.md in DDL eseguibile via Alembic.

### Modifiche

**`alembic.ini`**: post-write hook ruff_format cambiato da
`type=console_scripts` (non funziona con uv) a `type=exec` con
`executable=ruff`. Ora i file di migrazione generati sono auto-formattati.

**Nuovo `backend/alembic/versions/0001_initial_schema.py`** (~600 righe):

`upgrade()`:
- Estensione `pg_trgm`
- **Strato 0** (8 tabelle anagrafica): azienda, stazione,
  materiale_tipo, localita_manutenzione +dotazione, depot
  +linea_abilitata +materiale_abilitato
- **Strato 1** (4 tabelle LIV 1): corsa_import_run,
  corsa_commerciale, corsa_composizione, corsa_materiale_vuoto
- **Strato 2** (6 tabelle LIV 2): giro_materiale, versione_base_giro,
  giro_finestra_validita, giro_giornata, giro_variante, giro_blocco
- **Strato 2bis** (3 tabelle revisioni): revisione_provvisoria,
  revisione_provvisoria_blocco, revisione_provvisoria_pdc
- **Strato 3** (3 tabelle LIV 3): turno_pdc, turno_pdc_giornata,
  turno_pdc_blocco
- **Strato 4** (3 tabelle LIV 4): persona, assegnazione_giornata,
  indisponibilita_persona
- **Strato 5** (4 tabelle auth+audit): app_user, app_user_ruolo,
  notifica, audit_log
- FK cross-table risolte con ALTER (corsa_materiale_vuoto.giro_materiale_id,
  persona.user_id, indisponibilita_persona.approvato_da_user_id)
- ~30 indici secondari (FK, query frequenti, GIN su JSONB e trigram
  per persona.cognome/nome)

**Totale 31 tabelle** + `alembic_version` di Alembic = 32.

`downgrade()`: drop di tutto in ordine inverso, FK cross-table prima,
poi tabelle CASCADE. Ripristina DB pulito.

### Verifiche locali

- `alembic upgrade head`: 32 tabelle create (verificato con `\dt` +
  `SELECT COUNT(*) FROM information_schema.tables`)
- `alembic downgrade base`: torna a 1 tabella (alembic_version)
- `alembic upgrade head` (di nuovo): di nuovo 32 → **idempotente**
- `pytest`: 5/5 verdi
- `ruff/format/mypy`: tutti verdi

### Stato

Sprint 1.5 completo. DB Postgres ha schema completo del modello v0.5,
testato roundtrip up/down/up.

### Prossimo step

Sprint 1.6: migrazione `0002_seed_trenord.py` con 1 azienda + 7
località manutenzione + 25 depot + dotazione iniziale dal seed JSON.

---

## 2026-04-26 (2) — FASE D Sprint 1.4: Alembic setup async

### Contesto

Sprint 1.4 del PIANO-MVP: setup Alembic con env.py async-compatible.
Ancora niente migrazioni reali (quelle in 1.5).

### Modifiche

**`backend/alembic.ini`**:
- `script_location = alembic`
- `prepend_sys_path = src` (per import `colazione`)
- `file_template` con timestamp + slug per nomi file ordinati cronologicamente
- `sqlalchemy.url` vuoto (settato runtime da env in env.py)
- Post-write hook `ruff_format` (auto-format dei file generati)

**`backend/alembic/env.py`** (async support):
- Override `sqlalchemy.url` con `settings.database_url`
- `target_metadata = Base.metadata` (vuoto in v0, popolato in 1.7)
- `run_migrations_offline()` per modalità offline
- `run_async_migrations()` con `async_engine_from_config` + `connection.run_sync(do_run_migrations)`
- `compare_type=True`, `compare_server_default=True` per autogenerate accurato

**`backend/alembic/script.py.mako`**: template moderno con type hints
(`Sequence`, `str | None`).

### Verifiche

- `alembic current`: connessione DB OK, output pulito
- `alembic upgrade head`: no-op (nessuna migrazione presente, ok)
- `alembic history`: vuoto
- `pytest`: 5/5 passati
- `ruff`/`mypy`: tutti verdi

### Stato

Sprint 1.4 completo. Alembic pronto per accogliere migrazioni.

### Prossimo step

Sprint 1.5: migrazione `0001_initial_schema.py` con tutte le 31
tabelle da SCHEMA-DATI-NATIVO.md. È il pezzo grosso (~1000 righe SQL).

---

## 2026-04-26 — FASE D Sprint 1.3: db.py async + Postgres in CI

### Contesto

Inizio Sprint 1 (backend reale). Utente ha installato Docker Desktop
(v29.4.0) → Postgres 16.13 ora gira su localhost:5432 via
`docker compose up -d db`.

Sprint 1.3 del PIANO-MVP: layer DB async SQLAlchemy.

### Modifiche

**Nuovo `backend/src/colazione/db.py`**:
- `Base(DeclarativeBase)`: classe base ORM
- `get_engine()`: singleton lazy `AsyncEngine` con `pool_pre_ping`
- `get_session_factory()`: `async_sessionmaker`
- `session_scope()`: context manager async per script standalone
  (auto commit/rollback)
- `get_session()`: FastAPI dependency yields sessione per request
- `dispose_engine()`: cleanup al shutdown

**`pyproject.toml`**: deps DB rinforzate
- `sqlalchemy[asyncio]>=2.0` (era plain `sqlalchemy>=2.0`)
- `greenlet>=3.0` esplicito (richiesto per async SQLAlchemy)

**`backend/tests/test_db.py`**: 2 smoke test
- `test_db_connection_returns_one`: SELECT 1
- `test_db_postgres_version`: server_version_num >= 160000
- Skip automatico se `SKIP_DB_TESTS=1` env var

**`.github/workflows/backend-ci.yml`**: aggiunto service Postgres 16
- `services.postgres` con healthcheck
- env `DATABASE_URL` puntata a `localhost:5432`
- I test DB ora girano anche in CI

### Verifiche locali

- Postgres 16.13 healthy via Docker (5432 esposta)
- `pytest`: **5/5 passati** (3 main.py + 2 db)
- `ruff check`: All checks passed
- `ruff format --check`: 17 files formatted
- `mypy src/colazione`: no issues 14 source files

### Stato

Sprint 1.3 completo. Postgres locale in funzione, layer DB async
testato.

### Prossimo step

Sprint 1.4: Alembic setup (`alembic.ini` + `env.py` async + script.py.mako).

---

## 2026-04-25 (14) — FASE D Sprint 0.5: README.md (Sprint 0 COMPLETATA)

### Contesto

Sprint 0.5 del PIANO-MVP §2: README quick start per chiunque cloni il
repo. Ultimo passo della Sprint 0.

### Modifiche

**Nuovo `README.md` root** (~190 righe):
- Frase manifesto + diagramma piramide (PdE → giro → PdC → persone)
- Badge CI per backend-ci e frontend-ci
- Stato attuale (Sprint 0 quasi completa)
- Prerequisiti (Python 3.12, Node 20, uv, pnpm, Docker)
- Quick start in 5 comandi (clona → docker db → backend → frontend →
  browser)
- Alternativa "tutto in Docker"
- Comandi sviluppo backend + frontend (sync/test/lint/format/build)
- Albero struttura repo commentato
- Indice documentazione `docs/` (10 documenti linkati)
- Sezione "Contribuire" (Conventional Commits + TN-UPDATE +
  METODO-DI-LAVORO)
- Licenza Proprietary + manifesto greenfield

### Stato

**Sprint 0 COMPLETATA**. 5 passi atomici ognuno con commit + verifica.

### Riepilogo Sprint 0

| Passo | Output | Commit |
|-------|--------|--------|
| 0.1 | backend/ skeleton (FastAPI + uv + ruff + mypy + pytest) | `83b4f85` |
| 0.2 | frontend/ skeleton (React + Vite + TS + Tailwind + Vitest) | `b5873ca` |
| 0.3 | docker-compose.yml (Postgres + backend + frontend) | `d700e24` |
| 0.4 | GitHub Actions CI (backend-ci + frontend-ci) | `27b5914` |
| 0.5 | README.md quick start | (questo commit) |

### Verifiche locali (cumulative)

- Backend: pytest 3/3, ruff 0 errori, mypy strict no issues
- Frontend: vitest 2/2, eslint 0 errori, typecheck OK, build 143 KB
  gzip 46 KB, prettier check OK
- docker-compose.yml: YAML valido (3 servizi)
- CI workflows: YAML valido (2 workflow, jobs e triggers definiti)

### Verifica end-to-end CI

Da controllare a breve dopo questo push: stato di backend-ci e
frontend-ci su GitHub Actions per master. Se entrambi diventano verdi,
**Sprint 0 e' confermata funzionante anche su Linux pulito** (no
quirk path iCloud locale).

### Prossimo step

**Sprint 1 — Backend skeleton vero**:
- 1.1 main.py + /health (gia fatto in 0.1)
- 1.2 config.py Pydantic Settings (gia fatto in 0.1)
- 1.3 db.py async engine + session manager
- 1.4 Alembic setup + env.py async
- 1.5 Migrazione 0001_initial_schema.py (31 tabelle da SCHEMA-DATI-NATIVO.md)
- 1.6 Migrazione 0002_seed_trenord.py (azienda + 7 depositi + 25 depot)
- 1.7 Modelli SQLAlchemy ORM in models/
- 1.8 Schemas Pydantic in schemas/

Effort stimato Sprint 1: 2-3 giorni lavorativi. La parte grossa è la
migrazione 0001 (31 tabelle).

---

## 2026-04-25 (13) — FASE D Sprint 0.4: GitHub Actions CI

### Contesto

Sprint 0.4 del PIANO-MVP §2: CI automatica su push/PR per backend e
frontend. La CI girerà su Linux pulito (Ubuntu) e validerà che lo
skeleton funziona indipendentemente dalle quirk locali (path iCloud).

### Modifiche

**`.github/workflows/backend-ci.yml`**:
- Trigger: push su master, PR, workflow_dispatch (manual). Path
  filter su `backend/**` + workflow stesso.
- Steps: checkout → setup-python 3.12 → astral-sh/setup-uv (cache
  built-in) → `uv sync --extra dev` → `ruff check` → `ruff format
  --check` → `mypy strict` → `pytest --cov`.
- Working dir `backend/`.
- Timeout 10 min.

**`.github/workflows/frontend-ci.yml`**:
- Trigger: push su master, PR, workflow_dispatch (manual). Path
  filter su `frontend/**` + workflow stesso.
- Steps: checkout → setup-node 20 → pnpm/action-setup v10.33.2 →
  cache pnpm store → `pnpm install --frozen-lockfile` →
  `format:check` → `lint` → `typecheck` → `test` (vitest) → `build`.
- Cache `~/.pnpm-store` con key da hash di `pnpm-lock.yaml`.

### Verifiche

- Validato YAML manualmente con PyYAML: entrambi i workflow hanno
  triggers e jobs ben definiti.
- **La verifica vera arriverà al push**: GitHub Actions girerà
  backend-ci e frontend-ci. Se entrambi diventano verdi, lo skeleton
  e' confermato funzionante in CI Linux pulita.

### Stato

Sprint 0.4 file pronti, push imminente attiva i workflow.

### Prossimo step

Sprint 0.5 (ULTIMO della Sprint 0): `README.md` con quick start (clona
repo → 5 comandi per arrivare alla pagina home). Dopo questo, Sprint 0
finito, si passa a Sprint 1 (backend skeleton vero: SQLAlchemy +
Alembic + 31 tabelle).

---

## 2026-04-25 (12) — FASE D Sprint 0.3: docker-compose.yml

### Contesto

Sprint 0.3 del PIANO-MVP §2: orchestrazione 3 container (Postgres + backend
+ frontend) per dev locale.

### Modifiche

**Nuovo `docker-compose.yml`** (alla root):
- Service `db`: `postgres:16-alpine`, healthcheck `pg_isready`,
  volume nominato `colazione_pgdata`, porta 5432
- Service `backend`: build da `./backend/Dockerfile`, env DATABASE_URL
  pointing a `db:5432`, porta 8000, volumi montati per hot reload
  (src, tests, alembic), command override con `--reload --app-dir src`
- Service `frontend`: build da `./frontend/Dockerfile`, env
  `VITE_API_BASE_URL=http://localhost:8000`, porta 5173, volumi
  montati per hot reload (src, public, index.html)
- Dependency chain: frontend → backend → db (con `service_healthy`)

**`.gitignore`**: aggiunto `*.tsbuildinfo` (escludi cache TypeScript
incremental build, era trapelata in Sprint 0.2). Untracked
`frontend/tsconfig.app.tsbuildinfo` e `frontend/tsconfig.node.tsbuildinfo`.

### Verifiche

- Docker non installato sul sistema utente → impossibile
  `docker compose up` o `docker compose config`
- **Validato YAML manualmente** con PyYAML: 3 servizi (db, backend,
  frontend), 1 volume nominato (colazione_pgdata), porte 5432/8000/5173.
  Struttura coerente con STACK-TECNICO.md §7

### TODO post-Docker-install (sistema utente)

Quando l'utente installa Docker Desktop o OrbStack:
1. `docker compose config` → valida la sintassi con compose engine
2. `docker compose up -d db` → verifica Postgres parte (healthcheck OK)
3. `docker compose up backend` → verifica build + uvicorn risponde su :8000/health
4. `docker compose up frontend` → verifica Vite dev su :5173, app
   contatta backend
5. `docker compose down -v` → pulizia (cancella anche volume DB)

### Stato

Sprint 0.3 file committato. Verifica funzionale rinviata a quando
Docker sarà disponibile.

### Prossimo step

Sprint 0.4: GitHub Actions CI per backend + frontend. La CI gira su
container Linux puliti (no quirk path iCloud), quindi sarà la prima
verifica end-to-end "ufficiale" che lo skeleton funziona.

---

## 2026-04-25 (11) — FASE D Sprint 0.2: frontend skeleton

### Contesto

Sprint 0.2 del PIANO-MVP §2: scaffolding frontend React+TypeScript+
Vite+Tailwind. Niente template `npm create vite` (interattivo) — file
scritti a mano per controllo esplicito.

### Modifiche

**pnpm 10.33.2 installato** via `npm install -g pnpm` (corepack non
disponibile sul sistema utente).

**Nuovo `frontend/`**:
- `package.json`: deps React 18, react-router-dom, TanStack Query,
  Radix primitives (dialog, dropdown, popover, toast, slot), Tailwind
  3, lucide-react, class-variance-authority, clsx, tailwind-merge.
  Dev deps: TypeScript 5.7, ESLint 9 flat config, Prettier 3 +
  prettier-plugin-tailwindcss, Vitest 2 + @testing-library/react +
  jsdom, Vite 5.4 (compatibile Vitest 2)
- `tsconfig.json` + `tsconfig.app.json` + `tsconfig.node.json`:
  TypeScript strict, path alias `@/*` → `src/*`, target ES2022
- `vite.config.ts`: import da `vitest/config` per supportare campo
  `test`. Plugin React, alias `@`, server porta 5173
- `tailwind.config.ts`: palette base shadcn (background, foreground,
  primary, secondary, muted, accent, destructive)
- `postcss.config.js`: tailwindcss + autoprefixer
- `eslint.config.js`: flat config con typescript-eslint + react-hooks
  + react-refresh
- `.prettierrc.json`: semi true, double quotes, plugin Tailwind
- `.prettierignore`: dist/, node_modules/, lockfile
- `.env.example`: VITE_API_BASE_URL=http://localhost:8000
- `.nvmrc`: node 20
- `Dockerfile`: node:20-alpine + corepack + pnpm install
- `.dockerignore`

**`frontend/src/`**:
- `main.tsx`: createRoot + StrictMode + import App
- `App.tsx`: skeleton con titolo "Colazione" + sottotitolo Sprint
  0.2 + smoke test connessione backend (fetch `/health`)
- `index.css`: Tailwind directives + reset minimo body
- `lib/utils.ts`: helper shadcn `cn()` (clsx + tailwind-merge)
- `test/setup.ts`: import `@testing-library/jest-dom/vitest`
- `App.test.tsx`: 2 test smoke (titolo, sottotitolo Sprint)

**Cartelle vuote** create per moduli futuri:
- `components/ui/` (shadcn add per componente)
- `components/domain/` (componenti dominio)
- `routes/` (1 cartella per ruolo, vedi RUOLI-E-DASHBOARD.md)
- `hooks/` (TanStack Query hooks)

### Verifiche

- `pnpm install`: deps installate
- `pnpm typecheck`: no errori
- `pnpm lint`: no errori
- `pnpm test`: **2/2 test passati**
- `pnpm format:check`: All matched files use Prettier code style
- `pnpm build`: dist generato, **143 KB JS gzipped 46 KB**

### Quirk risolti durante setup

1. `defineConfig` da `vite` non supporta campo `test` → cambiato a
   import `from "vitest/config"`.
2. Vite 6 incompatibile con Vitest 2 (mismatch tipi PluginOption) →
   declassato Vite a `^5.4.0`.
3. ESLint 9 flat config richiede `@eslint/js` come dipendenza
   esplicita → aggiunta a devDependencies.

### Stato

Sprint 0.2 completo. Frontend skeleton pronto, smoke test backend
nella UI (mostrerà "non raggiungibile" se backend non gira).

### Prossimo step

Sprint 0.3: `docker-compose.yml` (Postgres + backend + frontend).
**Richiede installazione Docker Desktop o OrbStack** sul sistema
utente. Suggerisco di chiedere all'utente prima di procedere.

---

## 2026-04-25 (10) — FASE D Sprint 0.1: backend skeleton

### Contesto

Inizio costruzione codice. Sprint 0.1 del PIANO-MVP §2: scaffolding
backend FastAPI con Python 3.12 + uv, struttura cartelle per moduli
futuri.

### Modifiche

**Nuovo `backend/`**:
- `pyproject.toml`: dipendenze runtime (FastAPI, SQLAlchemy 2.0,
  alembic, psycopg3, Pydantic v2, bcrypt, pyjwt, openpyxl,
  numbers-parser) + extras dev (ruff, mypy, pytest, pytest-cov,
  pytest-asyncio, httpx). Config ruff line-length 100, mypy strict,
  pytest pythonpath=["src"]
- `.python-version`: 3.12
- `Dockerfile`: image python:3.12-slim + uv per build, multi-stage
  (deps cached, project install separato)
- `.dockerignore`
- `.env.example`: template per .env.local

**Struttura `backend/src/colazione/`**:
- `__init__.py` (versione 0.1.0)
- `main.py`: FastAPI app skeleton con `/health` endpoint + CORS
- `config.py`: Pydantic Settings (DATABASE_URL, JWT, admin, CORS)
- Cartelle vuote (con `__init__.py`) per: `auth/`, `models/`,
  `schemas/`, `api/`, `domain/{builder_giro,builder_pdc,normativa,revisioni}`,
  `importers/`

**`backend/tests/test_main.py`**:
- `test_health_endpoint_returns_ok` → 200 OK
- `test_app_metadata` → titolo + versione corretti
- `test_openapi_schema_exists` → /openapi.json contiene /health

**`backend/alembic/versions/.gitkeep`** (Alembic vero in Sprint 1.4)

**`.gitignore`** aggiornato: `.claude/` interamente ignorato (era
solo `.claude/settings.local.json`).

### Verifiche

- `uv sync --extra dev`: deps installate (~50 pacchetti)
- `uv run pytest -v`: **3/3 test passati**
- `uv run ruff check .`: All checks passed (dopo --fix automatico)
- `uv run ruff format --check .`: 15 files already formatted
- `uv run mypy src/colazione`: no issues found in 13 source files

### Quirk locale documentato

Il path repo `Mobile Documents/com~apple~CloudDocs/...` (iCloud sync)
con spazi e tilde **impedisce a Python di processare il file `.pth`
editable** generato da uv. Sintomo: `import colazione` da `python -c`
fallisce con ModuleNotFoundError. **Workaround**: `pythonpath = ["src"]`
in `[tool.pytest.ini_options]` per i test, `PYTHONPATH=src` per
script standalone. **In Docker/CI il problema non si presenta**
(nessuno spazio nel path).

### Stato

Sprint 0.1 completo. Backend skeleton committato, tutti i check
verdi.

### Prossimo step

Sprint 0.2: `frontend/` skeleton (React + Vite + TypeScript +
Tailwind + shadcn). Richiede installazione `pnpm` (suggerirò
`corepack enable` o `npm i -g pnpm`).

---

> Questo file viene aggiornato dopo **ogni modifica** al progetto.
> È il diario operativo del nuovo programma, costruito da zero.
>
> **Predecessore archiviato**: `docs/_archivio/LIVE-COLAZIONE-storico.md`
> contiene il diario del progetto vecchio (eliminato il 2026-04-25).
> Lì si trova la storia di come ci siamo arrivati al modello dati e
> all'architettura, in caso serva un riferimento.

---

## 2026-04-25 (9) — FASE C doc 7: PIANO-MVP.md (FASE C COMPLETA)

### Contesto

Ultimo documento architetturale. Definisce primo MVP girabile +
ordine costruzione + definizione "completato".

### Modifiche

**Nuovo `docs/PIANO-MVP.md` v0.1** (~430 righe):

**Definizione MVP v1**:
- Login + 5 dashboard navigabili (2 funzionanti su dati reali, 3
  scaffolding)
- Schema DB completo + seed Trenord
- Importer PdE da CLI (file Numbers reale)
- Vista corse + dashboard manutenzione

**Cosa NON e MVP**: builder giro, builder PdC, editor, persone,
revisioni, notifiche, mobile, deploy prod.

**8 sprint atomici** (1 commit per passo):
- Sprint 0 setup repo (1-2gg)
- Sprint 1 backend skeleton + Alembic + 31 tabelle (2-3gg)
- Sprint 2 auth JWT (2gg)
- Sprint 3 importer PdE Numbers (3-4gg, parser periodicita critico)
- Sprint 4 API base corse + depositi (2gg)
- Sprint 5 frontend skeleton React+shadcn (3-4gg)
- Sprint 6 dashboard MVP (2 reali + 3 scaffolding) (3-4gg)
- Sprint 7 test E2E + docs (1-2gg)

**Effort totale**: 17-23 gg lavorativi (3-4 settimane full time),
con buffer 30% = 22-30 gg reali (~5-6 settimane).

**12 criteri di "MVP completato"** verificabili.

**Roadmap v1.1-v1.7** post-MVP:
- v1.1 Builder giro materiale (Algoritmo A)
- v1.2 Editor giro (lettura)
- v1.3 Anagrafica persone
- v1.4 Builder turno PdC (Algoritmo B)
- v1.5 Editor scrittura (drag&drop)
- v1.6 Assegnazioni
- v1.7 Revisioni provvisorie (Algoritmo C)

**Decisioni rinviate** (non bloccanti MVP): file uploads, real-time
push, audit retention, backup, logging, hosting prod.

### Stato

**FASE C COMPLETATA**. Tutti i 7 documenti architetturali scritti:
1. ✅ VISIONE.md
2. ✅ STACK-TECNICO.md
3. ✅ RUOLI-E-DASHBOARD.md
4. ✅ LOGICA-COSTRUZIONE.md
5. ✅ SCHEMA-DATI-NATIVO.md
6. ✅ IMPORT-PDE.md
7. ✅ PIANO-MVP.md

Repo pronto per FASE D (codice).

### Prossimo step

Aspetto OK utente per iniziare FASE D Sprint 0 passo 0.1
(creare backend/ + pyproject.toml). Oppure utente chiede revisione
di qualche documento.

---

## 2026-04-25 (8) — FASE C doc 6: IMPORT-PDE.md

### Contesto

Specifica del primo importer del programma. Legge PdE Numbers/Excel
e popola corsa_commerciale + corsa_composizione. È il punto di ingresso
del sistema: senza questo, il resto della piramide non si popola.

### Modifiche

**Nuovo `docs/IMPORT-PDE.md` v0.1** (~470 righe):

- §1 Input: formati supportati (.numbers prio, .xlsx alt), 3 sheet
  Trenord (PdE RL = 10580 righe da importare; NOTE Treno e NOTE BUS
  per dopo)
- §2 Mapping completo 124 colonne PdE → schema DB:
  - identificativi (numero treno, rete, categoria, linea, direttrice)
  - geografia (origine/destinazione + CdS, orari, km, durate)
  - periodicità (testuale + flag garantito feriale/festivo)
  - 9 combinazioni stagione × giorno-tipo → corsa_composizione (95K
    record per Trenord)
  - calendario annuale (Gg_gen, Gg_feb, ..., Gg_anno)
  - aggregati (totale km, postikm, velocità commerciale)
- §3 **Algoritmo calcolo valido_in_date_json denormalizzato**:
  - parsing testo "Periodicità" (intervalli skip, date singole skip,
    date extra)
  - validazione incrociata con Gg_* per mese
  - retorna lista date ISO YYYY-MM-DD
- §4 Idempotenza:
  - chiave logica `(azienda_id, numero_treno, valido_da)` → upsert
  - SHA-256 file → skip se già importato
  - tracking corsa_import_run con n_create / n_update / warnings
- §5 Pseudo-codice top-level (transazione unica + bulk insert)
- §6 8 edge case noti (numero treno come float, date all'italiana,
  caratteri Unicode, sheet ordering, ecc.)
- §7 Performance: 10580 × 9 = 95K insert, target < 30s con bulk insert
  + transazione unica
- §8 Test (smoke + idempotenza + modifica + calcolo periodicità)
- §9 CLI: `uv run python -m colazione.importers.pde --file ... --azienda trenord`

### Stato

- Spec pronta per implementazione `backend/src/colazione/importers/pde.py`
- Anche pronta per la fixture di test (50 righe del file reale)

### Prossimo step

`docs/PIANO-MVP.md` (FASE C doc 7, ULTIMO): primo MVP girabile +
ordine costruzione codice + definizione "MVP completato". Dopo
questo, FASE C chiusa e si passa a FASE D (codice).

---

## 2026-04-25 (7) — FASE C doc 5: SCHEMA-DATI-NATIVO.md (DDL eseguibile)

### Contesto

Materializzazione di MODELLO-DATI v0.5 in DDL SQL eseguibile per
Postgres 16. Specifica per la prima migrazione Alembic
(0001_initial_schema.py).

### Modifiche

**Nuovo `docs/SCHEMA-DATI-NATIVO.md` v0.1** (~700 righe):

- §1 Convenzioni (naming, tipi, FK, indici)
- §2 Estensioni Postgres (pg_trgm)
- §3-§9 Schema in 7 strati con CREATE TABLE eseguibili:
  - Strato 0 anagrafica: azienda, stazione, materiale_tipo,
    localita_manutenzione, dotazione, depot, depot_linea_abilitata,
    depot_materiale_abilitato (8 tabelle)
  - Strato 1 corse LIV 1: corsa_commerciale, corsa_composizione,
    corsa_materiale_vuoto, corsa_import_run (4 tabelle)
  - Strato 2 giro LIV 2: giro_materiale, versione_base_giro,
    giro_finestra_validita, giro_giornata, giro_variante,
    giro_blocco (6 tabelle)
  - Strato 2bis revisioni: revisione_provvisoria,
    revisione_provvisoria_blocco, revisione_provvisoria_pdc (3 tabelle)
  - Strato 3 turno PdC LIV 3: turno_pdc, turno_pdc_giornata,
    turno_pdc_blocco (3 tabelle)
  - Strato 4 personale LIV 4: persona, assegnazione_giornata,
    indisponibilita_persona (3 tabelle)
  - Strato 5 auth/audit: app_user, app_user_ruolo, notifica,
    audit_log (4 tabelle)

Totale **31 tabelle**.

- §10 Indici secondari (FK, query frequenti, GIN su JSONB e trigram
  per cognome/nome persona)
- §11 5 vincoli consistenza come query SQL eseguibili (per test
  integrazione)
- §12 Seed iniziale Trenord:
  - 1 azienda Trenord con normativa_pdc_json completa
  - 7 localita_manutenzione (FIORENZA, NOVATE, CAMNAGO, LECCO,
    CREMONA, ISEO, POOL_TILO_SVIZZERA)
  - 25 depot Trenord (NORMATIVA §2.1)
- §13 Riepilogo numerico (record stimati: ~256k record totali in
  produzione Trenord)

### Stato

- DDL pronto per migrazione Alembic.
- 5 vincoli consistenza pronti per test integrazione.
- Seed Trenord pronti per popolamento iniziale.

### Prossimo step

`docs/IMPORT-PDE.md` (doc 6): come si legge PdE Numbers/Excel,
mapping colonne, calcolo valido_in_date denormalizzato, idempotenza.

---

## 2026-04-25 (6) — FASE C doc 4: LOGICA-COSTRUZIONE.md

### Contesto

Documento centrale degli algoritmi nativi. Tre algoritmi descritti in
modo formale + pseudo-codice + mapping a moduli Python.

### Modifiche

**Nuovo `docs/LOGICA-COSTRUZIONE.md` v0.1** (~600 righe):

**Algoritmo A — PdE → Giro Materiale**:
- Input: corse, localita_manutenzione, dotazione, giorno_tipo
- Greedy: per ogni località, costruisci catene di corse rispettando
  continuità geografica + tempo manovra + composizione coerente +
  ciclo chiuso
- Genera `corsa_materiale_vuoto` per posizionamento e rientro
- Multi-giornata + varianti calendario derivate da PdE periodicità

**Algoritmo B — Giro Materiale → Turno PdC**:
- Architettura "centrata sulla condotta" (riferimento ARCHITETTURA-
  BUILDER-V4 storico): seed produttivo (1-2 corse, 2-3h condotta) +
  posizionamento + gap handling + rientro
- 5 step: A scelta seed, B posizionamento, C gap (REFEZ in finestra),
  D rientro, E validazione
- Validazione vincoli singolo turno (NORMATIVA §11.8, §4.1, §9.2,
  §3, §6) + ciclo settimanale (§11.4, §11.5)

**Algoritmo C — Revisione provvisoria + cascading**:
- Crea `revisione_provvisoria` con causa esterna esplicita
- Modifica `giro_blocco` impattati (modifica/cancella/aggiungi)
- **Cascading**: per ogni giro modificato, crea
  `revisione_provvisoria_pdc` con stessa finestra
- Re-build automatico turni PdC nella finestra (Algoritmo B su giri-rev)
- Notifiche cross-ruolo
- Resolver query "cosa succede il giorno D?": base + override rev

**Validazione + scoring**:
- ValidatorePdC unificato in `domain/normativa/validator.py`
- Score per ranking soluzioni (n_pdc, prestazione_sotto_sfruttata,
  violazioni preferenziali §11.7)

**Mapping moduli Python**:
- `domain/builder_giro/`, `domain/builder_pdc/`, `domain/normativa/`,
  `domain/revisioni/` — tutti DB-agnostic
- Test puri in `tests/domain/`, fixtures con seed reali

**Edge case noti** (7 casi):
- Materiale pernotta fuori deposito
- Partenza senza U-numero
- CV Tirano (capolinea inversione)
- Cap 7h notturno
- MI.PG ↔ FIOz taxi obbligatorio
- Composizione mista
- POOL_TILO_SVIZZERA

### Stato

- Documento draft v0.1, ~600 righe.
- Pronto per implementazione (FASE D) ma 3 punti aperti:
  multi-giornata schema-tica, scoring seed con pesi placeholder,
  cascading re-build a maglie larghe.

### Prossimo step

`docs/SCHEMA-DATI-NATIVO.md` (FASE C doc 5): DDL SQL eseguibile.
Materializza `MODELLO-DATI.md` v0.5 in CREATE TABLE + indici + FK +
seed iniziali per Postgres 16.

---

## 2026-04-25 (5) — FASE C doc 3: RUOLI-E-DASHBOARD.md

### Contesto

Specifica dettagliata delle 5 dashboard per ruolo. Ogni ruolo ha
schermate, azioni, dati visualizzati, permessi. Documento operativo
per costruire frontend e backend coerenti.

### Modifiche

**Nuovo `docs/RUOLI-E-DASHBOARD.md` v0.1** (~530 righe):

- §1 Tabella riepilogativa 5 ruoli + ADMIN con privilegi
- §2 Schermate condivise (login, profilo, settings)
- §3 **Dashboard PIANIFICATORE_GIRO** (6 schermate):
  home, vista PdE, lista giri, editor giro (centrale, con Gantt
  orizzontale + drag&drop + valida live), revisioni, nuova revisione
- §4 **Dashboard PIANIFICATORE_PDC** (5 schermate):
  home, vista giri readonly, lista turni, editor turno PdC (centrale,
  Gantt giornaliero + validazione normativa live + pannello vincoli
  ciclo), revisioni cascading
- §5 **Dashboard MANUTENZIONE** (5 schermate):
  home, lista depositi, dettaglio deposito (inventario), spostamenti
  tra depositi, manutenzioni programmate
- §6 **Dashboard GESTIONE_PERSONALE** (6 schermate):
  home, anagrafica, scheda persona (calendario annuale + ore/sett),
  calendario assegnazioni (centrale, persone × date), indisponibilita,
  sostituzioni
- §7 **Dashboard PERSONALE_PDC** (5 schermate):
  oggi (banner + Gantt giornaliero), calendario, dettaglio turno data,
  ferie/assenze, segnalazioni
- §8 Matrix permessi cross-ruolo per 11 entita
- §9 Notifiche cross-ruolo (8 eventi tracciati)
- §10 Settings admin
- §11 Cosa NON e in v1 (dark mode, mobile native, PDF export ricco,
  WebSocket/SSE, drill-down KPI, conversazioni in-app)

### Stato

- Documento draft v0.1, ~30 schermate descritte.
- Pronto per priorizzazione in PIANO-MVP.md (doc 7).

### Prossimo step

`docs/LOGICA-COSTRUZIONE.md` (doc 4): algoritmo nativo PdE → giro
materiale → turno PdC. Riformula ALGORITMO-BUILDER.md + ARCHITETTURA-
BUILDER-V4.md in chiave nativa, senza riferimenti al codice vecchio.

---

## 2026-04-25 (4) — FASE C doc 2: STACK-TECNICO.md (scelte confermate)

### Contesto

Utente ha confermato in blocco le 6 scelte consigliate. Stack tecnico
definito.

### Modifiche

**Nuovo `docs/STACK-TECNICO.md` v1.0** (~390 righe):

Le 6 scelte:
1. Backend: **Python 3.12+**
2. Framework: **FastAPI** (async, OpenAPI auto-gen, Pydantic-native)
3. DB: **PostgreSQL 16+** (anche dev, no più SQLite-PG dual-mode)
4. Frontend: **React 18 + TypeScript + Vite**
5. UI Kit: **shadcn/ui** (Radix + Tailwind CSS)
6. Auth: **JWT custom + bcrypt**

Hosting differito (probabile VPS self-host quando arriva il momento).

**Struttura repo monorepo**:
- `backend/` (FastAPI con `src/colazione/` + `domain/` per business
  logic DB-agnostic)
- `frontend/` (Vite con routes per ruolo, non per tipo)
- `data/` (seed JSON gia presente)
- `docker-compose.yml` per dev (db + backend + frontend)
- Alembic per migrazioni schema versionate

**Tooling**:
- Backend: `uv` (package manager) + `ruff` (lint+format) + `mypy` + `pytest`
- Frontend: `pnpm` + `eslint` + `prettier` + `vitest` + `@testing-library/react`

**Convenzioni**:
- Python: type hints obbligatori, mypy strict, async ovunque
- React: function components, TanStack Query per stato server,
  Tailwind only (no CSS modules/styled-components)
- Commit: Conventional Commits in italiano

**Cosa NON useremo** (esplicito):
- Tauri (web-only per ora)
- GraphQL (REST sufficiente)
- Redis/Celery (non serve in MVP)
- Microservizi/k8s (monolite modulare)
- SSR/SSG (SPA classica)
- i18n (italiano-only)

### Stato

- Documento v1.0, completo per costruzione MVP.
- Modifiche future tracciate qui in TN-UPDATE.md.

### Prossimo step

`docs/RUOLI-E-DASHBOARD.md` (FASE C doc 3): dettaglio delle 5
dashboard, schermate per ruolo, azioni, permessi, mockup testuale.

---

## 2026-04-25 (3) — FASE C doc 1: VISIONE.md scritta

### Contesto

Primo documento architetturale del nuovo progetto. Scopo: chiarire
in modo permanente cosa stiamo costruendo, per chi, e perché. Punto
di riferimento per qualsiasi domanda di scope ("c'è dentro X?" → si
controlla qui).

### Modifiche

**Nuovo `docs/VISIONE.md` (draft v0.1)**:
- §1 Frase manifesto: sistema operativo per pianificazione
  ferroviaria nativa, dal contratto commerciale al singolo
  macchinista
- §2 Il problema reale: 3 silos disconnessi (PdE, turno materiale,
  turno PdC) cuciti con parser fragili
- §3 Cosa fa il programma: 4 funzioni primarie (importa PdE, genera
  giro, genera PdC, assegna persone) + 5a (revisioni provvisorie con
  cascading)
- §4 5 ruoli destinatari: pianificatore giro / pianificatore PdC /
  manutenzione / gestione personale / personale finale (PdC)
- §5 Cosa NON e': 6 esclusioni esplicite (no biglietteria, no real-
  time da zero, no manutenzione predittiva, no payroll, no RFI, no
  solo Trenord)
- §6 7 principi guida: costruzione non importazione, no parser
  fragili come ingresso primario, modello a piramide, multi-tenant
  giorno 1, 5 dashboard 1 modello, revisioni provvisorie tracciate,
  sviluppo iterativo
- §7 Definizione di successo (uomo davanti al monitor + scala
  industriale)
- §8 Ambito rilascio: MVP v1 → v1.0 → v1.x → v2.0 → v2.x (no date)
- §9 Riferimenti incrociati a documenti gia esistenti e in coda

### Stato

- Documento draft v0.1, ~250 righe.
- Pronto per revisione utente.

### Prossimo step

**MI FERMO QUI.** Il prossimo documento (`STACK-TECNICO.md`) richiede
decisioni dell'utente su:
- Linguaggio backend (Python? Node? Go? Rust?)
- Framework backend (FastAPI? Express? Fastify? altro?)
- Frontend (React? Vue? Svelte? Next/Remix?)
- DB primario (SQLite locale + Postgres prod come prima?)
- Hosting (Railway? Vercel? Fly.io? Cloudflare? self-host?)
- Auth (JWT? sessions? OAuth? Clerk/Auth0?)

Aspetto input dell'utente prima di scrivere STACK-TECNICO.md.

---

## 2026-04-25 (2) — FASE B completata: nuovo CLAUDE.md + .gitignore

### Contesto

CLAUDE.md vecchio era pieno di riferimenti al codice eliminato in
FASE A (server.py, FastAPI, Tauri, parser PDF, train_segment, builder
genetico, ecc.). Riscrittura completa per il nuovo progetto greenfield.

### Modifiche

**`CLAUDE.md`** completamente riscritto:
- Stato del progetto: greenfield, in scrittura specifiche
- 7 regole operative obbligatorie (lettura TN-UPDATE.md, aggiornamento
  TN-UPDATE.md dopo ogni task, METODO-DI-LAVORO.md, lettura dominio,
  manifesto greenfield, sviluppo per ruoli)
- Mappa dei documenti di dominio con "quando leggerli"
- Stato fasi A/B/C/D + lista 7 documenti FASE C
- Stack tecnologico: TBD in `docs/STACK-TECNICO.md` (FASE C doc 2)
- Glossario dominio essenziale (PdE, giro materiale, turno PdC, CV,
  PK, ACCp/ACCa, vettura, materiale vuoto, FR, S.COMP, ciclo 5+2)
- Convenzioni naming + riferimenti a tutti i .md

**`.gitignore`** aggiornato:
- Rimosse voci specifiche al vecchio (turni.db, server.log, uploads/
  hardcoded, ecc.)
- Aggiunte sezioni separate per Python e Node.js (entrambi ignorati
  finche non scegliamo lo stack)
- Strutturato per essere stack-agnostic e estendibile in FASE C

### Stato

- CLAUDE.md ora rispecchia il progetto attuale (greenfield)
- .gitignore agnostic per qualsiasi stack
- Repo pronto per FASE C (scrittura specifiche architetturali)

### Prossimo step

FASE C documento 1: `docs/VISIONE.md`. Cos'e' il programma, per chi,
cosa risolve, scope esplicito.

---

## 2026-04-25 — Greenfield reset (FASE A completata)

### Decisione

Il progetto vecchio (parser PDF Gantt centrato su `train_segment`,
backend FastAPI 60+ file Python, frontend React 1GB) è stato dichiarato
inutile dall'utente. Si parte da zero col nuovo programma nativo,
basato su:

- Logica di costruzione **PdE → giro materiale → turno PdC → personale**
- 5 dashboard separate per ruolo (pianificatori, manutenzione,
  gestione personale, personale finale)
- Modello dati a piramide v0.5 (vedi `docs/MODELLO-DATI.md`)
- Manifesto "non copiamo Trenord" — usano il loro sistema come
  ispirazione, non come template

### Cancellato in questo commit

| Categoria | Cosa | Motivo |
|-----------|------|--------|
| Backend | `server.py`, `app.py`, `api/` (18 file), `services/`, `src/` (1.2 MB di codice) | Logica vecchia centrata su parser PDF |
| Frontend | `frontend/` (~1 GB con node_modules), `static/`, `mockups/` | UI vecchia da riscrivere |
| Test | `tests/` (808 KB) | Test del codice vecchio |
| Dati runtime | `turni.db` (20 MB), `turni_backup_*.db`, `turno_materiale_treni.json`, `uploads/` (5.2 MB), `fr_stations.txt` | DB locale + dati vecchi |
| Config deploy | `Procfile`, `railway.toml`, `runtime.txt`, `.dockerignore`, `.railwayignore`, `requirements.txt`, `.env.example` | Deploy vecchio Railway |
| Script ad-hoc | `parse_turno_materiale.py`, `import_turno_materiale.py`, `debug_digits.py`, `scripts/enrich_db_*.py` | Tool 1-shot del vecchio |
| Junk | `nul`, `server.log`, `__pycache__/`, `.pytest_cache/`, `.venv/` | Cache + log |
| Config app | `config/` | Config app vecchia |

**Spazio liberato**: ~1.05 GB.

### Archiviato in `docs/_archivio/`

| Cosa | Motivo |
|------|--------|
| `LIVE-COLAZIONE-storico.md` (370 KB) | Memoria storica del progetto vecchio |
| `MIGRAZIONE-DATI.md` | Piano di migrazione DB (rinnegato — questo era progetto greenfield, non migrazione) |
| `GANTT-GUIDE.md`, `HANDOFF-*.md` (×5), `PROMPT-claude-design-*.md` (×5), `REFERENCE-*.css/.html` (×5), `PLAN-parser-refactor.md`, `claude-design-bundles/`, `stitch-mockups/` | UI vecchia (mockup, prompt, riferimenti) |
| `scripts/extract_depositi_manutenzione.py` | Utility 1-shot per estrarre depositi dal PDF (riutilizzabile se serve) |

### Tenuto (dominio + base nuovo progetto)

| Cosa | Motivo |
|------|--------|
| `docs/NORMATIVA-PDC.md` (1292 righe) | **Fonte verità** dominio Trenord |
| `docs/METODO-DI-LAVORO.md` | Framework comportamentale (vale sempre) |
| `docs/MODELLO-DATI.md` v0.5 | Modello concettuale (12 entità + manifesto) |
| `docs/ALGORITMO-BUILDER.md` | Spec algoritmo (riferimento, da riscrivere in chiave nativa) |
| `docs/ARCHITETTURA-BUILDER-V4.md` | Idea "centrata sulla condotta" (riferimento) |
| `docs/schema-pdc.md` | Schema dati turno PdC (riferimento) |
| `data/depositi_manutenzione_trenord_seed.json` | Anagrafica reale 7 depositi + 1884 pezzi |
| `CLAUDE.md` | Da **riscrivere** in FASE B per nuovo progetto |
| `.gitignore` | Da aggiornare per nuovo stack |
| `.claude/` | Config harness Claude Code |

### Stato repo dopo FASE A

```
COLAZIONE/
├── .claude/
├── .git/
├── .gitignore
├── CLAUDE.md                ← da riscrivere (FASE B)
├── TN-UPDATE.md             ← questo diario (nuovo)
├── data/
│   └── depositi_manutenzione_trenord_seed.json
└── docs/
    ├── ALGORITMO-BUILDER.md       ← riferimento
    ├── ARCHITETTURA-BUILDER-V4.md ← riferimento
    ├── METODO-DI-LAVORO.md        ← framework
    ├── MODELLO-DATI.md            ← v0.5
    ├── NORMATIVA-PDC.md           ← dominio
    ├── schema-pdc.md              ← riferimento
    └── _archivio/                 ← memoria progetto vecchio
```

### Prossimi step

- **FASE B**: riscrivere `CLAUDE.md` per il nuovo progetto
- **FASE C** (multi-commit): scrivere documentazione architetturale
  nativa, un documento per volta:
  1. `docs/VISIONE.md`
  2. `docs/STACK-TECNICO.md`
  3. `docs/RUOLI-E-DASHBOARD.md`
  4. `docs/LOGICA-COSTRUZIONE.md`
  5. `docs/SCHEMA-DATI-NATIVO.md`
  6. `docs/IMPORT-PDE.md`
  7. `docs/PIANO-MVP.md`
- **FASE D**: inizio costruzione codice (solo dopo che A+B+C sono
  chiusi e validati dall'utente)
