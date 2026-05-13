# CODE REVIEW — COLAZIONE — 2026-05-13

> Seconda review sistematica del repo. La prima è in `docs/CODE-REVIEW-2026-05-01.md`
> (Sprint 7.4, 24 finding). Questa copre lo stato del codice al termine di Sprint 8.4
> (dopo entry 301), includendo tutti gli artefatti aggiunti da Sprint 7.5 a oggi.
>
> **Perimetro**: `backend/src/`, `backend/tests/`, `backend/alembic/`, `frontend/src/`.
> Documenti di dominio e `data/` esclusi (non sono codice).
>
> **Metodo**: lettura diretta dei file critici + grep sistematici su normativa,
> pattern di sicurezza, assert, TODO/FIXME, import circolari, indici DB.
> Nessuna modifica al codice di produzione.

---

## Indice

- [CRITICI](#critici) (6 finding)
- [IMPORTANTI](#importanti) (11 finding)
- [MINORI](#minori) (7 finding)
- [Riepilogo debito tracciato](#riepilogo-debito-tracciato)

---

## CRITICI

### C1 — PK senza validazione durata minima: violazione diretta §4.4

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:257-269`

**Normativa violata**: NORMATIVA-PDC §4.4 — "PK in arrivo: 20' minimo; PK in partenza: 20' minimo."

Il builder crea un blocco `tipo_evento="PK"` per **qualsiasi gap positivo** tra blocchi
consecutivi della giornata, incluso un gap di 1 minuto:

```python
gap = _diff(prec.ora_fine, b.ora_inizio)
if gap > 0:
    drafts.append(_BloccoPdcDraft(tipo_evento="PK", durata_min=gap, ...))
```

§4.4 richiede **40 minuti totali minimi** (20' in arrivo + 20' in partenza) per
eseguire un ciclo PK valido. Gap < 40' non possono essere marcati come PK.
Conseguenze concrete:

- Un gap di, es., 10' tra due treni consecutivi viene persistito come `tipo_evento="PK"`
  nel `TurnoPdcBlocco`.
- La UI mostra "PK" dove operativamente non è possibile fare il PK.
- Il validatore non segnala violazione: `test_vincoli_inviolabili.py` non copre questo
  caso.
- Il `deposito_first.py` eredita lo stesso bug tramite `build_giornata_pdc`.

**Fix proposto**: in `_build_giornata_pdc`, sostituire il controllo `if gap > 0` con
`if gap >= PK_MIN_CICLO` (dove `PK_MIN_CICLO = 40`). Per gap 0 < gap < 40 che non
ammettono PK né CV (stazioni non ammesse): emettere violazione
`"gap_tecnico_senza_soluzione:{gap}min"` invece di un PK falso. Aggiungere costante:

```python
PK_MIN_CICLO_MIN = 40  # §4.4: 20' in arrivo + 20' in partenza
```

---

### C2 — `giornata_base.py` facade incompleta: ri-esporta simboli privati `_xxx`

**File**: `backend/src/colazione/domain/builder_pdc/giornata_base.py:31-71`

La façade creata da MR-PD-FIX-SEVERO 2 (S2) espone alias pubblici dei simboli privati
di `builder.py`, ma la **definizione effettiva rimane privata** in `builder.py`:

```python
BloccoPdcDraft = _BloccoPdcDraft          # importa _BloccoPdcDraft da builder.py
build_giornata_pdc = _build_giornata_pdc  # importa _build_giornata_pdc da builder.py
```

Il commento stesso ammette: *"S2-bis previsto"* (spostare le definizioni fuori da
`builder.py`). Tre moduli ignorano il facade e importano direttamente da `builder.py`:

```
backend/src/colazione/api/turni_pdc.py:28
backend/src/colazione/api/pianificatore_pdc.py:23
backend/src/colazione/domain/builder_pdc/simulazione.py:21
```

Risultato: il facade esiste ma **non isola** il consumatore da `builder.py`. Qualsiasi
refactor di `builder.py` continua a rompere 3 siti extra oltre ai consumatori del facade.
Il debito introdotto da SEVERO come HIGH è rimasto a metà.

**Fix proposto**: spostare le classi `_BloccoPdcDraft`, `_GiornataPdcDraft` e le funzioni
`_build_giornata_pdc`, `_aggiungi_dormite_fr`, `_genera_codice_turno`, `_persisti_un_turno_pdc`
dentro `giornata_base.py` come simboli pubblici (senza underscore). `builder.py` importa
da `giornata_base`. I 3 siti che bypassano il facade vengono aggiornati per puntare a
`giornata_base.py`. Costo stimato: ~3h refactor + test.

---

### C3 — `RegistroVettureAssegnate.from_db` usa wild card `data_operativa=None`: §15 flawed

**File**: `backend/src/colazione/domain/builder_pdc/registro_vetture.py:157,240`

Il commento interno dichiara esplicitamente il bug:

> *"`data_operativa = None` nel registro funziona come wild card match (collide con
> qualunque data) — usato dal `from_db` MVP finché `enumera_date_giornata` non viene
> scritto (S4 SEVERO TODO)."*

`from_db` carica da DB tutti i blocchi `VETTURA` di tutti i turni PdC del programma
e li registra con `data_operativa=None`. Conseguenza: se il turno A ha una vettura
sul treno 2425 (registrata wild card), il builder del turno B **esclude sempre** il
treno 2425, indipendentemente dalla data — anche quando i due turni operano in giorni
calendario completamente diversi. Falsi positivi §15 = vetture legittime rifiutate.

Il finding era già classificato HIGH da SEVERO (entry 295). La closure parziale
(entry 297/299) ha fixato il test vacuo ma **non ha implementato** `enumera_date_giornata`.

**Fix proposto**: implementare `enumera_date_giornata(giro_giornata, programma)` che,
data una `GiroGiornata`, espande le sue `GiroVariante.dates_apply_json` nel range del
programma e restituisce le date concrete. Usarla in `from_db` per popolare
`data_operativa` con la data reale invece di `None`. Costo: ~4h (la funzione esiste
già come stub in `giornate_concrete.py`).

---

### C4 — `updated_at` senza `onupdate`: timestamp stale su UPDATE

**File**: tutti i modelli con `updated_at`:
`backend/src/colazione/models/turni_pdc.py:58`,
`backend/src/colazione/models/giri.py:79`,
`backend/src/colazione/models/programmi.py` (vari),
`backend/src/colazione/models/personale.py:69`

Tutti i campi `updated_at` sono definiti come:

```python
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), server_default=func.now()
)
```

`server_default` esegue `NOW()` solo all'INSERT, **non all'UPDATE**. Per aggiornare
`updated_at` su ogni UPDATE serve `onupdate=func.now()` o un trigger PostgreSQL.

Stato attuale inconsistente:
- `programmi.py` aggiorna manualmente `p.updated_at = datetime.now(UTC)` in 6 punti,
  ma NON in tutti gli endpoint (es. manca su `PATCH /programmi/{id}/pipeline-pdc`).
- `TurnoPdc.updated_at` non viene MAI aggiornato dopo la generazione iniziale.
- `GiroMateriale.updated_at` non viene aggiornato quando si aggiunge/modifica un giro.

La pipeline overview (`api/pipeline_overview.py:88,114`) usa `updated_at` per calcolare
"giorni dall'ultima modifica" — dato che può essere silenziosamente errato.

**Fix proposto**: aggiungere `onupdate=func.now()` a tutti i campi `updated_at` nei
modelli. Alternativamente, creare un trigger `BEFORE UPDATE` in PostgreSQL via migration
Alembic. Rimuovere le assegnazioni manuali `p.updated_at = datetime.now(UTC)` ridondanti.

---

### C5 — 50 test falliti su `master` non tracciati come issue aperta

**Fonte**: `TN-UPDATE.md` entry 301, riga 94

> *"pytest full backend: 50 fallimenti pre-esistenti su master (verificato via
> `git stash` → stessi fail). Non sono regressioni di questo fix. Backlog."*

50 test che falliscono silenziosamente su master sono **debito tecnico bloccante** per la
regola §7 CLAUDE.md: non si può dichiarare una feature "chiusa" se la suite di test non
passa integralmente. Il messaggio "non sono regressioni di questo fix" non è sufficiente:
la CI deve essere verde su master prima di ogni merge.

Senza eseguire pytest in questa sessione, non posso enumerare i 50 fallimenti, ma la loro
esistenza documentata è un finding critico di processo.

**Fix proposto**:
1. Eseguire `pytest backend/tests/ -x --tb=short 2>&1 | head -100` per identificare
   il primo blocco di fallimenti.
2. Triagiarli in: (a) test che validano codice effettivamente rotto → fix immediato,
   (b) test che hanno fixture obsolete → aggiornare fixture, (c) test che dipendono da
   infrastruttura non disponibile in CI → skipparli con `@pytest.mark.skip(reason=...)`.
3. Far passare la suite prima del prossimo merge su master.

---

### C6 — `split_cv` non implementa CVa/CVp no-overhead: prestazione gonfiata di 80' per ramo

**File**: `backend/src/colazione/domain/builder_pdc/split_cv.py:27-32`

Il commento dichiara esplicitamente la limitazione:

> *"non viene applicato il pattern CV no-overhead (gap < 65' → CVa/CVp che sostituiscono
> ACCa/ACCp risparmiando 80%). Ogni ramo paga il costo accessori standard."*

NORMATIVA-PDC §3.4 + §5: il CV è un cambio a mezzo acceso — il PdC smontante ha già
fatto l'ACCa durante il tratto finale, il PdC montante non rifà l'ACCp. Per ogni split
CV, il costo normativo corretto è:
- Ramo 1 (smontante): ACCp all'inizio + condotta + CVa (< 65' da ACCa standard)
- Ramo 2 (montante): CVp (< 65' da ACCp standard) + condotta + ACCa alla fine

Il builder invece dà ad entrambi i rami ACCp+condotta+ACCa completi, aggiungendo
**80' di accessori falsi** per ramo (40' ACCa del ramo 1 + 40' ACCp del ramo 2).
Questo causa:
- False violazioni `prestazione_max` sui rami di giornate lunghe.
- Turni PdC che in DB mostrano prestazioni maggiori di quelle operative reali.
- `condotta_min` corretto ma `prestazione_min` gonfiato.

**Fix proposto**: aggiungere parametro `is_ramo_medio: bool` a `_build_giornata_pdc`.
Se `True`, omettere ACCp iniziale (ramo montante) o ACCa finale (ramo smontante).
In `split_e_build_giornata`, il primo ramo ha ACCp ma non ACCa al punto di split;
l'ultimo ramo ha ACCa ma non ACCp al punto di split. Aggiungere invece blocchi `CVa`
e `CVp` con durata variabile (= gap tra fine treno precedente e inizio treno successivo,
cap < 65').

---

## IMPORTANTI

### I1 — JWT access token TTL = 72h: finestra di compromissione troppo ampia

**File**: `backend/src/colazione/config.py:39`

```python
jwt_access_token_expire_min: int = 4320  # 72h
```

`dependencies.py:19` riconosce: *"il cambio diventa effettivo solo all'access token
successivo (max 72h con la config attuale). Per MVP è accettabile."*

Un access token non revocabile di 72 ore è un rischio concreto: utente rimosso o con
ruolo revocato rimane autenticato per fino a 3 giorni. Per il sistema multi-tenant con
ruoli `PIANIFICATORE_PDC` che hanno accesso in scrittura ai turni, questo è un rischio
operativo reale (non solo teorico).

Best practice consolidata: access token 15-60 min + refresh token 7-30 gg. Il refresh
token rilegge ruoli/stato dal DB ad ogni rinnovo (già commentato in `auth.py`).

**Fix proposto**: ridurre `jwt_access_token_expire_min` a 60 (1 ora). Verificare che
il frontend gestisca la scadenza + refresh correttamente (TanStack Query + interceptor
401 in `frontend/src/lib/api/`). Costo: ~2h.

---

### I2 — `enumera_date_giornata` non implementata: infrastruttura calendario incompleta

**File**: `backend/src/colazione/domain/giornate_concrete.py:12`,
`backend/src/colazione/domain/builder_pdc/registro_vetture.py:17,157`

La funzione `enumera_date_giornata` è l'unico punto in cui una `GiroGiornata` (che
descrive un giorno-tipo astratto) viene mappata alle date calendario concrete del
programma. È necessaria per:
1. Il registro vetture cross-PdC §15 (C3 sopra).
2. Il calcolo corretto di `data_operativa` in `deposito_first.py` (I3 sotto).
3. Qualsiasi futura logica che voglia sapere "questa giornata del giro accade il 15
   maggio o il 3 giugno?".

Lo stub esiste già in `giornate_concrete.py` con il commento "S4 TODO, attualmente
wild card MVP". Non è stato assegnato a nessun MR esplicito.

**Fix proposto**: implementare `enumera_date_giornata(gg: GiroGiornata, programma: ProgrammaMateriale) -> list[date]`:
1. Prende `GiroVariante.dates_apply_json` per la variante canonica (`variant_index=0`).
2. Interseca con `[programma.valido_da, programma.valido_a]`.
3. Ritorna la lista di date concrete.
Costo: ~3h (logica semplice, la struttura dati è già presente).

---

### I3 — `deposito_first.py` usa `valido_da_eff` come data per tutte le giornate

**File**: `backend/src/colazione/domain/builder_pdc/deposito_first.py:566`

```python
draft, violazioni = await costruisci_giornata_deposito_first(
    ...
    data_operativa=valido_da_eff,  # MVP: data_operativa = valido_da per tutte le giornate
)
```

Il commento interno ammette: *"Helper `enumera_date_giornata` (S4 TODO) raffinerà per
varianti calendariali multi-data."* Conseguenza: tutte le giornate del turno vengono
costruite assumendo che operino nella data `valido_da` del programma (es. 2026-06-07),
anche se giornata 5 potrebbe operare mesi dopo.

Per il registro vetture cross-PdC §15, questo causa esclusioni di vetture basate sulla
data sbagliata. Per la ricerca della vettura via API `live.arturo.travel`, la finestra
temporale usata per la ricerca dei treni non è quella reale.

**Fix proposto**: dipende da I2. Una volta implementato `enumera_date_giornata`,
sostituire `data_operativa=valido_da_eff` con la prima data concreta della giornata
calcolata dalla funzione.

---

### I4 — `api/turni_pdc.py` e `api/pianificatore_pdc.py` bypassano il facade `giornata_base.py`

**File**: `backend/src/colazione/api/turni_pdc.py:28-38`,
`backend/src/colazione/api/pianificatore_pdc.py:23`,
`backend/src/colazione/domain/builder_pdc/simulazione.py:21`

Il facade `giornata_base.py` è stato creato per isolare i consumatori dall'API privata
di `builder.py`. Ma tre moduli ignorano il facade:

```python
# turni_pdc.py:28 — importa direttamente builder.py
from colazione.domain.builder_pdc.builder import (
    CONDOTTA_MAX_MIN, PRESTAZIONE_MAX_NOTTURNO, PRESTAZIONE_MAX_STANDARD,
    BuilderTurnoPdcResult, DepositoPdcNonTrovatoError, GiriEsistentiError,
    GiroNonTrovatoError, GiroVuotoError, genera_turno_pdc,
)
```

`genera_turno_pdc` è l'unica importazione legittima (non è ancora in `giornata_base`);
le costanti e le exception class invece esistono già in `giornata_base.__all__`.

**Fix proposto**: spostare le importazioni di costanti ed eccezioni da `builder.py` a
`giornata_base.py` in `turni_pdc.py`, `pianificatore_pdc.py`, `simulazione.py`.
Poi spostare `genera_turno_pdc` in `giornata_base.py` (o in un modulo `api.py` dedicato)
come parte di C2. Costo: ~1h.

---

### I5 — Nessun indice GIN su `corsa_commerciale.valido_in_date_json`: O(N) su 6536 righe

**File**: nessuna migration Alembic. `backend/src/colazione/models/corse.py:115`

```python
valido_in_date_json: Mapped[list[Any]] = mapped_column(JSONB, default=list)
```

Nessuna delle 46 migration Alembic aggiunge un indice GIN su questo campo. Ogni query
"trova corse che circolano il giorno D" scansiona sequenzialmente tutte le 6536 corse.
Il builder giro chiama `_carica_corse(session, azienda_id, data_inizio, data_fine)` che
carica TUTTE le corse e le filtra in Python — non in SQL. Questo è il percorso critico
della generazione giri.

Analogamente, `GiroVariante.dates_apply_json` (JSONB array di date) non ha indice GIN.

**Fix proposto**: migration Alembic con:

```sql
CREATE INDEX ix_corsa_commerciale_valido_in_date_gin
    ON corsa_commerciale USING GIN (valido_in_date_json jsonb_path_ops);
```

Poi aggiornare `_carica_corse` per filtrare in SQL:
```sql
WHERE valido_in_date_json @> '["2026-06-07"]'::jsonb
```

---

### I6 — `assert` in production code: silenzioso con `-O`, nessuna gestione errore

**File**:
- `backend/src/colazione/domain/builder_pdc/builder.py:210,253,256`
- `backend/src/colazione/domain/builder_pdc/multi_turno.py:421,477,1140`
- `backend/src/colazione/domain/builder_pdc/riposo_settimanale.py:271-273`
- `backend/src/colazione/api/giri.py:2891`
- `backend/src/colazione/api/turni_pdc.py:377`
- `backend/src/colazione/db.py:58`

14 `assert` trovati in production code. Con Python `-O` (ottimizzazione), le
`assert` vengono silenziosamente rimosse. La conseguenza è un `AttributeError` o
`TypeError` non gestito al posto di un errore chiaro.

Esempi:
```python
# builder.py:210
assert primo.ora_inizio is not None and ultimo.ora_fine is not None
# → se None, KeyError invece di errore comprensibile

# api/turni_pdc.py:377
assert deposito_pdc_id is not None  # validato sopra
# → implicit invariant che dovrebbe essere un ValueError esplicito

# api/giri.py:2891
assert target_giro.azienda_id == user.azienda_id
# → security invariant che dovrebbe lanciare HTTP 403, non AssertionError
```

**Fix proposto**: sostituire ogni `assert` di produzione con:
- Invarianti di sicurezza → `HTTPException(403)` o `HTTPException(404)`.
- Invarianti di dominio → `raise ValueError("...")` o eccezione dominio custom.
- Type narrowing post-validazione pydantic → `if x is None: raise ValueError(...)`.

---

### I7 — `_aggiungi_dormite_fr` non aggiorna `inizio_prestazione`: prestazione errata in UI

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:1193-1195`

Il commento dichiara:
> *"Per il MVP NON aggiorniamo inizio_prestazione: prestazione_min resta quella della
> giornata operativa, la dormita è informativa."*

Un turno con dormita FR ha un blocco `DORMITA` inserito all'inizio della giornata N+1,
ma `inizio_prestazione` e `prestazione_min` di quella giornata non vengono aggiornati.
La UI mostra quindi:
- `inizio_prestazione` = ora presa del giorno operativo (es. 05:30)
- Ma il blocco DORMITA inizia a `00:00`

Questo rende incoerente il Gantt visivo e i calcoli di prestazione nella dashboard
pianificatore PdC.

**Fix proposto**: dopo `curr.blocchi.insert(0, nuovo_blocco)`, aggiornare:
```python
curr.inizio_prestazione = time(0, 0)
curr.prestazione_min += inizio_n1  # aggiunge il tempo dormita
```
Oppure, se la dormita deve restare "informativa fuori dal cap", aggiungerla come
metadato separato e non come blocco nel flusso prestazione.

---

### I8 — `STAZIONI_CV_DEROGA` hardcoded non è tenant-configurable

**File**: `backend/src/colazione/domain/builder_pdc/split_cv.py:61`

```python
STAZIONI_CV_DEROGA: frozenset[str] = frozenset({"MORTARA", "TIRANO"})
```

Con l'architettura multi-tenant di COLAZIONE (SAD, TILO, Trenitalia come futuri
clienti), le deroghe CV sono Trenord-specifiche. Il commento riconosce:
*"refactor a regola configurabile per programma in iterazioni successive"* ma non è
tracciato come issue aperta.

**Fix proposto**: spostare `STAZIONI_CV_DEROGA` dentro `azienda.normativa_pdc` JSON
(già previsto in `MODELLO-DATI.md §3`) come campo `stazioni_cv_deroga: list[str]`.
Caricarla via `split_cv.lista_stazioni_cv_ammesse()` aggiungendo un join su `Azienda`.
Costo: ~2h.

---

### I9 — `ProgrammaMateriale.updated_at` aggiornato manualmente in 6 punti ma non in tutti

**File**: `backend/src/colazione/api/programmi.py:544,746,766,843,1479,1543`

L'endpoint `PATCH /programmi/{id}/pipeline-pdc` (che cambia `stato_pipeline_pdc`)
NON aggiorna `updated_at`. Idem per le operazioni che modificano `GiroMateriale`,
`TurnoPdc`, `TurnoPdcBlocco` — nessuno di questi aggiorna mai `updated_at` sulla
tabella genitore `programma_materiale`.

La pipeline overview usa `ProgrammaMateriale.updated_at` per "giorni dall'ultima
modifica" — questo valore è inaffidabile.

Questo è separato da C4 (mancanza di `onupdate` a livello ORM) perché anche fixando C4,
i modelli figli (`GiroMateriale`, `TurnoPdc`) non aggiornerebbero automaticamente
`ProgrammaMateriale.updated_at`. Serve una strategia esplicita (trigger PostgreSQL
o cascade applicativo).

**Fix proposto**: trigger PostgreSQL su `INSERT/UPDATE/DELETE` di `giro_materiale`,
`turno_pdc` per propagare `NOW()` al `programma_materiale.updated_at` corrispondente.
Alternativamente, aggiornarlo esplicitamente in ogni endpoint che modifica entità figlie.

---

### I10 — `split_cv` usa ricorsione per split multipli: nessun loop guard adeguato

**File**: `backend/src/colazione/domain/builder_pdc/split_cv.py:92-144`

`split_e_build_giornata` si chiama ricorsivamente con `livello` come guard:

```python
if livello >= MAX_LIVELLI_SPLIT:  # MAX_LIVELLI_SPLIT = 5
    return [build_giornata_pdc(...)]  # ritorna il ramo fuori-cap senza split
```

Il problema: quando `livello >= 5` il builder ritorna un ramo che **eccede i cap
normativi** senza emettere una violazione esplicita. Questa giornata fuori-cap viene
aggiunta silenziosamente ai draft e poi persista nel DB come turno valido (con
eventuale violazione nel metadata, ma non come ramo bloccante).

Se esistono giri con più di 5 punti CV necessari (ad es. giornate di 18+ ore su linee
con tanti depositi intermedi), il turno generato ha violazioni nascoste.

**Fix proposto**: quando `livello >= MAX_LIVELLI_SPLIT`, non ritornare il ramo silenziosamente
ma emettere una violazione esplicita `"split_cv_max_livelli_superato"` e ritornare
comunque il ramo con il flag violazione per renderlo visibile nella UI.

---

### I11 — Frontend: 14 test su 115 file di route (12% di copertura visibile)

**File**: `frontend/src/routes/`

115 file `.tsx`/`.ts` di route e componenti di route, 14 file di test (`.test.tsx`).
La stragrande maggioranza dei route critici non ha test:

- `GanttUnificatoRoute.tsx` (~470 righe, Sprint 8.4): nessun test.
- `TurnoPdcDettaglioRoute.tsx` (logica builder banner, vetture, FR): nessun test.
- `GiroDettaglioRoute.tsx` (Gantt principale, multi-blocco): nessun test.
- `PianificatorePdcDashboard.tsx`: nessun test.

I pochi test esistenti (`ProgrammaDettaglioRoute.test.tsx`, `ProgrammiRoute.test.tsx`,
`LoginRoute.test.tsx`, `ProtectedRoute.test.tsx`) verificano principalmente routing e
autenticazione, non la logica di business della UI.

Il rischio concreto: regressioni silenziose su componenti critici come il Gantt o il
dettaglio turno PdC non vengono rilevate automaticamente.

**Fix proposto**: aggiungere test Vitest/React Testing Library almeno per:
1. `GanttUnificatoRoute` — rendering blocchi, click su blocco, dialog inserimento.
2. `TurnoPdcDettaglioRoute` — rendering violazioni, badge VETTURA, banner FR.
3. `ProgrammaGiriRoute` — render lista giri, pulsante genera.
Non è necessaria copertura totale: focus sui percorsi critici (golden path + edge cases
di validazione).

---

## MINORI

### M1 — `DEPOT_MILANO_MM` hardcoded: non tenant-configurable

**File**: `backend/src/colazione/domain/builder_pdc/vettura_resolver.py:82-92`

```python
DEPOT_MILANO_MM: frozenset[str] = frozenset({
    "GARIBALDI_ALE", "GARIBALDI_CADETTI", "GARIBALDI_TE",
    "GRECO_TE", "GRECO_S9", "FIORENZA",
})
```

Come `STAZIONI_CV_DEROGA` (I8), questa frozenset è Trenord-specifica. Il campo
`azienda.normativa_pdc` JSON previsto da MODELLO-DATI.md §3 potrebbe accogliere
`depositi_serviti_mm: list[str]`.

---

### M2 — `_resolve_vincoli_path()` fragile: ricerca ascendente non deterministica

**File**: `backend/src/colazione/domain/vincoli/inviolabili.py:46-59`

Il file `vincoli_materiale_inviolabili.json` viene trovato risalendo i parent del
modulo. Funziona in dev e Docker (`/app/data/...`), ma può fallire in ambienti custom
(es. se i test vengono avviati da una directory fuori dal repo). L'env var
`COLAZIONE_VINCOLI_INVIOLABILI_PATH` mitiga il problema solo se configurata.

**Fix proposto**: usare `importlib.resources` per accedere al file come package
resource, oppure calcolare il path in base a una variabile nota (es. `os.environ.get("APP_ROOT")`
con fallback esplicito e messaggio di errore chiaro).

---

### M3 — Sprint-history comments inquinano il codice sorgente

**File**: >30 occorrenze in `builder.py`, `multi_turno.py`, `deposito_first.py`, `giri.py`

Commenti come:
```python
# Sprint 7.4 MR 2: split CV intermedio.
# Sprint 8.0 MR 0 (entry 164): lettura turni PdC ammessa ai 4 ruoli...
# Sprint 7.9 MR η — risolvi deposito target (se richiesto).
```

Questi commenti descrivono la **storia delle modifiche**, non il **comportamento del
codice**. La storia è in `TN-UPDATE.md` e nei commit. Nel sorgente creano rumore che
rende difficile leggere cosa fa il codice vs quando è stato aggiunto.

**Fix proposto**: rimuovere i commenti Sprint-history dal sorgente. Mantenere solo
commenti che spiegano il WHY non-ovvio (workaround normativi, invarianti sottili).
I tag `# NORMATIVA-PDC §X.Y` sono utili e vanno mantenuti.

---

### M4 — `multi_turno.py` VETTURA_GAP_PRE_MIN duplica costante già in `vettura_resolver.py`

**File**: `backend/src/colazione/domain/builder_pdc/multi_turno.py:103`,
`backend/src/colazione/domain/builder_pdc/vettura_resolver.py:67`

```python
# multi_turno.py
VETTURA_GAP_PRE_MIN = 5

# vettura_resolver.py
VETTURA_GAP_PRE_MIN: int = 5
```

Stessa costante, stesso valore, due definizioni separate. Se il valore cambia,
va aggiornata in due posti.

**Fix proposto**: rimuovere la definizione in `multi_turno.py` e importarla da
`vettura_resolver.py`. 5 minuti di lavoro.

---

### M5 — `GiroMateriale.updated_at` e `TurnoPdc.updated_at` mancano di indice

**File**: `backend/src/colazione/models/giri.py:79`,
`backend/src/colazione/models/turni_pdc.py:59`

La pipeline overview ordina per `ProgrammaMateriale.updated_at` (indicizzato indirettamente
via `ix_turno_pdc_azienda_deposito`). Ma query tipo "dammi i turni PdC aggiornati dopo
data X" non hanno un indice efficiente su `turno_pdc.updated_at`.

**Fix proposto**: se le query per `updated_at` crescono con la scala (oggi 50-200 turni,
futuro 5000+), aggiungere indici B-tree su `giro_materiale.updated_at` e
`turno_pdc.updated_at` in una migration.

---

### M6 — `TurnoPdcBlocco.tipo_evento` è stringa libera senza CHECK constraint

**File**: `backend/src/colazione/models/turni_pdc.py:97`

```python
tipo_evento: Mapped[str] = mapped_column(String(20))
```

Il dominio ammette: `CONDOTTA, VETTURA, REFEZ, ACCp, ACCa, CVp, CVa, PK, SCOMP, PRESA,
FINE, MM, VOCTAXI, DORMITA`. Ma nulla in DB impedisce di salvare valori arbitrari.
Migration `0045` aggiunge tipi estesi, ma senza CHECK constraint PostgreSQL.

**Fix proposto**: aggiungere una migration con:
```sql
ALTER TABLE turno_pdc_blocco
ADD CONSTRAINT turno_pdc_blocco_tipo_evento_check
CHECK (tipo_evento IN ('CONDOTTA','VETTURA','REFEZ','ACCp','ACCa','CVp','CVa','PK',
                       'SCOMP','PRESA','FINE','MM','VOCTAXI','DORMITA'));
```

---

### M7 — `_calcola_violazioni_cap_fr`: formula cicli multipli usa `ceil(ciclo/7)*1`

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:1247`

Il commento dice "conversione conservativa" ma la formula `settimane * FR_MAX_PER_SETTIMANA`
per cicli > 28gg è ottimistica: per un ciclo di 14gg il tetto calcolato è 2 FR. Ma
NORMATIVA-PDC §10.6 dice max 3 FR per 28gg — non "1/settimana scalabile linearmente".
Un ciclo di 14gg con 2 FR è dentro il limite settimanale (1/sett × 2 sett = 2 OK), ma
viola il limite mensile solo se il PdC è assegnato a questo turno continuativamente
(4 × 2 = 8 FR/mese >> 3/28gg).

La formula attuale non cattura questo scenario di violazione mensile per cicli corti
ripetuti. Per turni > 28gg invece il controllo mensile viene applicato correttamente.

**Fix proposto**: la formula corretta per cicli ≤ 28gg dovrebbe confrontare
`n_dormite_fr` con `FR_MAX_PER_28GG` (=3) a prescindere dal numero di settimane.
Per cicli > 28gg la formula pro-rata `settimane × 1` è accettabile come stima.

---

## Riepilogo debito tracciato

| ID | Gravità | Area | Stimato | Status post-review |
|----|---------|------|---------|-------------------|
| C1 | CRITICO | Builder PdC / Normativa §4.4 | ~2h | Aperto |
| C2 | CRITICO | Architettura builder_pdc | ~3h | Aperto |
| C3 | CRITICO | Registro vetture §15 | ~4h | Aperto |
| C4 | CRITICO | ORM / DB consistency | ~2h | Aperto |
| C5 | CRITICO | Test suite / CI | ~4h triage | Aperto |
| C6 | CRITICO | Builder PdC / Normativa §3.4+§5 | ~4h | Aperto |
| I1 | IMPORTANTE | Sicurezza JWT | ~2h | Aperto |
| I2 | IMPORTANTE | Infrastruttura calendario | ~3h | Aperto (bloccante per C3, I3) |
| I3 | IMPORTANTE | Builder deposito-first | ~1h (dopo I2) | Aperto |
| I4 | IMPORTANTE | Import architecture | ~1h | Aperto |
| I5 | IMPORTANTE | Performance DB / GIN index | ~1h | Aperto |
| I6 | IMPORTANTE | Solidità produzione / assert | ~2h | Aperto |
| I7 | IMPORTANTE | Builder PdC / FR UI | ~1h | Aperto |
| I8 | IMPORTANTE | Multi-tenancy | ~2h | Aperto |
| I9 | IMPORTANTE | updated_at cascade | ~2h | Aperto |
| I10 | IMPORTANTE | Builder split_cv | ~1h | Aperto |
| I11 | IMPORTANTE | Frontend test coverage | ~8h | Aperto |
| M1 | MINORE | Multi-tenancy | ~1h | Aperto |
| M2 | MINORE | Robustezza path | ~1h | Aperto |
| M3 | MINORE | Leggibilità codice | ~2h | Aperto |
| M4 | MINORE | Duplicazione costante | ~5min | Aperto |
| M5 | MINORE | Performance DB indici | ~30min | Aperto |
| M6 | MINORE | Integrità DB | ~30min | Aperto |
| M7 | MINORE | Builder / Normativa §10.6 | ~1h | Aperto |

**Totale stimato**: ~50-55h di fix distribuiti in 2-3 Sprint.

**Priorità suggerita** (by impact/effort):
1. C5 (50 test su master) — blocca la CI, deve venire prima di qualsiasi merge.
2. I2 → C3 → I3 (enumera_date_giornata) — prerequisito per §15 corretto.
3. C1 (PK minimo) — violazione normativa visibile in produzione.
4. C4 (updated_at) — consistency bug silenzioso con impatto UI.
5. C2 + I4 (facade) — debito architetturale che peggiora ad ogni nuovo modulo.
6. I1 (JWT TTL) — rischio sicurezza prima della produzione reale.

---

*Revisore*: NINO (Claude Code)
*Data*: 2026-05-13
*Metodo*: analisi statica manuale + grep sistematici. Nessuna esecuzione di test.
*Baseline*: commit `6571374` (Sprint 8.4 entry 301 — hotfix API partenze).
