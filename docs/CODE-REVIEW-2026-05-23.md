# Code Review COLAZIONE — 2026-05-23

> Richiesta: review senior completa del repo post-Sprint 8.4.
> Scope: backend + frontend, debito tecnico, violazioni normativa PdC, test coverage, qualità architetturale.
> Vincolo: NESSUNA modifica al codice di produzione. Solo analisi e proposte.

---

## Indice

- [CRITICI (4)](#critici)
- [IMPORTANTI (6)](#importanti)
- [MINORI (6)](#minori)
- [Tabella riassuntiva](#tabella-riassuntiva)

---

## CRITICI

### CR-1 — `is_cap_notturno` non persistito: le API producono false positive di violazione normativa

**File/righe**: `backend/src/colazione/api/turni_pdc.py:947`,
`backend/src/colazione/api/pianificatore_pdc.py:144–151`,
`backend/src/colazione/models/turni_pdc.py:83`

**Problema**

Sprint 8.2 SEVERO S1 ha introdotto il flag `is_cap_notturno` (True solo se presa
servizio 01:00–04:59, NORMATIVA-PDC §3) distinguendolo da `is_notturno` (superinclusivo
per UI: presa<05:00 **oppure** fine>22:00 **oppure** wrap-mezzanotte).

Il builder usa `is_cap_notturno` correttamente per scegliere il cap (420 vs 510 min).
Ma **`TurnoPdcGiornata` non ha la colonna `is_cap_notturno`** — il persister scrive solo
`is_notturno=d.is_notturno` (riga 1079 di `builder.py`).

Conseguenza: al momento della **lettura**, `turni_pdc.py:947` fa:

```python
cap_prestazione = PRESTAZIONE_MAX_NOTTURNO if g.is_notturno else PRESTAZIONE_MAX_STANDARD
```

Per un turno con presa 14:30 / fine 23:00 / prestazione 510 min:
- builder: `is_notturno=True` (fine>22), `is_cap_notturno=False` → cap=510, **nessuna violazione**
- API in lettura: `is_notturno=True` → cap=420 → **falsa violazione hard 510>420**

Lo stesso errore è nella query aggregata di `pianificatore_pdc.py:144–151`:

```python
and_(TurnoPdcGiornata.is_notturno.is_(True),
     TurnoPdcGiornata.prestazione_min > PRESTAZIONE_MAX_NOTTURNO),
```

Tutti i turni pomeriggio-sera (presa 13–18, fine 21–23) che toccano la finestra >22:00 e
hanno prestazione 8h30 vengono contati come violazioni nel KPI dashboard del pianificatore.

**Fix concreto**

1. Migration `0047_turno_pdc_giornata_is_cap_notturno.py`:
   ```sql
   ALTER TABLE turno_pdc_giornata
     ADD COLUMN is_cap_notturno BOOLEAN NOT NULL DEFAULT FALSE;
   UPDATE turno_pdc_giornata g
   SET is_cap_notturno = TRUE
   FROM turno_pdc_blocco b
   WHERE b.turno_pdc_giornata_id = g.id
     AND b.tipo_evento = 'PRESA'
     AND b.ora_inizio >= TIME '01:00' AND b.ora_inizio < TIME '05:00';
   ```
2. Aggiungere `is_cap_notturno: Mapped[bool]` in `models/turni_pdc.py:TurnoPdcGiornata`.
3. Aggiornare `_persisti_un_turno_pdc` (builder.py:1079) per scrivere `is_cap_notturno=d.is_cap_notturno`.
4. Aggiornare le due API per usare `g.is_cap_notturno` al posto di `g.is_notturno` nel discriminante cap.

---

### CR-2 — `multi_turno.py` carica TUTTI i `TurnoPdc` dell'azienda in RAM per trovare i legati a un giro

**File/righe**: `backend/src/colazione/domain/builder_pdc/multi_turno.py:590–600`

**Problema**

```python
existing = list(
    (await session.execute(
        select(TurnoPdc).where(TurnoPdc.azienda_id == azienda_id)
    )).scalars()
)
legati = [
    t for t in existing
    if (t.generation_metadata_json or {}).get("giro_materiale_id") == giro_id
]
```

Viene caricata **ogni** istanza di `TurnoPdc` per l'intera azienda (potenzialmente
centinaia × N depositi × N programmi = O(1000+) righe) solo per filtrare poi in Python
quelli con `giro_materiale_id == giro_id`.

Ogni riga ha un campo JSONB `generation_metadata_json` che viene deserializzato in
memoria. Con aziende con molti programmi attivi (es. due programmi annuali + varianti =
200+ giri × 5 depositi = 1000 TurnoPdc), questa query caricherà >1000 oggetti in ogni
call `genera_turni_pdc_multi`.

**Fix concreto**

Aggiungere un indice JSONB su `giro_materiale_id` e filtrare in SQL:

```python
# Migration 0047 (o 0048):
# CREATE INDEX ix_turno_pdc_giro_id
#   ON turno_pdc ((generation_metadata_json ->> 'giro_materiale_id'));

from sqlalchemy import cast, Integer, text

legati = list(
    (await session.execute(
        select(TurnoPdc)
        .where(TurnoPdc.azienda_id == azienda_id)
        .where(
            cast(TurnoPdc.generation_metadata_json["giro_materiale_id"].as_string(), Integer)
            == giro_id
        )
    )).scalars()
)
```

Oppure, senza indice ma con filtro push-down:

```python
.where(TurnoPdc.generation_metadata_json["giro_materiale_id"].as_integer() == giro_id)
```

---

### CR-3 — `inserisci_corsa_manuale` non invalida i `TurnoPdc` dipendenti → inconsistenza silente

**File/righe**: `backend/src/colazione/api/giri.py:4021–4048`

**Problema**

L'endpoint `POST /{giro_id}/inserisci-corsa-manuale` inserisce un `GiroBlocco` nel giro e
fa `session.commit()` (riga 4048) senza toccare i `TurnoPdc` già generati da quel giro.

Un turno PdC generato *prima* dell'inserimento manuale non include il nuovo blocco condotta.
Il campo `stato` del turno rimane `"bozza"` — invariato, senza alcun segnale che il giro
sottostante sia cambiato. L'operatore non riceve avviso.

La garanzia di tracciabilità ("ogni TurnoPdcBlocco.giro_blocco_id referenzia il blocco del
giro che lo ha generato") non copre questo caso perché il turno esistente manca del blocco
nuovo — non può avere una FK verso qualcosa creato dopo di lui.

**Fix concreto**

Dopo il `session.flush()` del nuovo blocco (riga 4047), prima del commit:

```python
# Cerca TurnoPdc dipendenti e marcali come da rigenerare.
turni_legati = list(
    (await session.execute(
        select(TurnoPdc)
        .where(TurnoPdc.azienda_id == giro.azienda_id)
        .where(
            TurnoPdc.generation_metadata_json["giro_materiale_id"].as_integer()
            == giro_id
        )
    )).scalars()
)
for t in turni_legati:
    t.stato = "da_rigenera"
n_invalidati = len(turni_legati)
```

E aggiungere `n_turni_invalidati: int` a `InserisciCorsaManualeResponse`. Aggiornare il
frontend per mostrare il banner di avviso quando `n_turni_invalidati > 0`.

---

### CR-4 — Registro vetture con `data_operativa=None` (wild card) blocca sistematicamente le vetture reali

**File/righe**: `backend/src/colazione/domain/builder_pdc/registro_vetture.py:15–17,157,240`,
`backend/src/colazione/domain/builder_pdc/deposito_first.py:542`

**Problema**

Il docstring di `registro_vetture.py` (riga 15–17):
> `data_operativa = None` nel registro funziona come **wild card match**
> (collide con qualunque data) — usato dal `from_db` MVP finché
> `enumera_date_giornata` non viene scritto (S4 SEVERO TODO).

Il `from_db` (riga 157, 240) carica tutti i blocchi VETTURA dal DB e li registra con
`data_operativa=None`. Questo significa che **ogni vettura storica blocca tutte le date
future**.

Conseguenza in produzione: con 50+ turni PdC già generati, ciascuno con 1–2 blocchi
VETTURA, il registro contiene decine di treni "bloccati per sempre". Quando `deposito_first`
genera un nuovo turno e chiama `risolvi_rientro`, `is_assegnata()` ritorna True per qualunque
treno già usato in passato → il resolver scala a MM o VOCTAXI invece di usare vetture reali.

L'implementazione `enumera_date_giornata` esiste già in
`domain/giornate_concrete.py:40–116` e supporta la sintassi MVP delle varianti
calendariali. Il collegamento mancante è solo nel `from_db`.

**Fix concreto**

In `registro_vetture.py`, funzione `from_db`:

```python
# Per ogni turno con blocco VETTURA, calcola le date concrete
# invece di usare wild card None.
for turno, blocco, giornata in rows:
    data_inizio = turno.valido_da
    ciclo = (turno.generation_metadata_json or {}).get("ciclo_giorni", 7)
    data_fine = data_inizio + timedelta(days=ciclo * 4)  # finestra 4 cicli
    festivita = festivita_italiane(data_inizio.year)
    date_concrete = enumera_date_giornata(
        numero_giornata=giornata.numero_giornata,
        variante_calendario=giornata.variante_calendario,
        ciclo_giorni=ciclo,
        data_inizio_programma=data_inizio,
        data_fine_programma=data_fine,
        festivita=festivita,
    )
    for d in date_concrete:
        registro.assegna(
            numero_treno=blocco.numero_treno_vettura,
            operatore=...,
            data_operativa=d,
        )
```

Costo stimato: 3–4h. Dipendenza su `festivita_italiane` già disponibile.

---

## IMPORTANTI

### IMP-1 — `assert` in codice di produzione — crash silente con `-O`

**File/righe**: `backend/src/colazione/domain/builder_pdc/builder.py:210,253,256`,
`backend/src/colazione/domain/builder_pdc/multi_turno.py:421,477,1140`

**Problema**

```python
assert primo.ora_inizio is not None and ultimo.ora_fine is not None  # builder.py:210
assert b.ora_inizio is not None and b.ora_fine is not None           # builder.py:253
assert prec.ora_fine is not None                                      # builder.py:256
assert stazione_apertura is not None                                  # multi_turno.py:421
assert stazione_chiusura is not None                                  # multi_turno.py:477
assert depot is not None and depot.id == depot_key                    # multi_turno.py:1140
```

Eseguendo Python con `-O` (ottimizzazione, comune in build di produzione), gli `assert`
vengono rimossi dal bytecode. Se un blocco giro arriva al builder con `ora_inizio=None`
(ad es. per un inserimento manuale incompleto — vedi CR-3), il codice prosegue e crasha
con `AttributeError: 'NoneType' object has no attribute 'hour'` invece del messaggio
esplicito.

**Fix concreto**

Sostituire con guard clause esplicite:

```python
# prima:
assert primo.ora_inizio is not None and ultimo.ora_fine is not None
# dopo:
if primo.ora_inizio is None or ultimo.ora_fine is None:
    return None  # _build_giornata_pdc ritorna None per giornata non elaborabile
```

```python
# prima:
assert depot is not None and depot.id == depot_key
# dopo:
if depot is None or depot.id != depot_key:
    raise RuntimeError(f"Invariante violato: depot_key={depot_key} non corrisponde a depot={depot}")
```

---

### IMP-2 — `_inserisci_refezione_ai_bordi` crea REFEZ prima di PRESA servizio

**File/righe**: `backend/src/colazione/domain/builder_pdc/builder.py:477–561`

**Problema**

La strategia 1 di `_inserisci_refezione_ai_bordi` inserisce un blocco REFEZ **prima** del
blocco PRESA, producendo la sequenza:

```
[REFEZ(12:00–12:30)][PRESA(12:30–12:45)][ACCp(12:45–13:25)][CONDOTTA...]
```

NORMATIVA-PDC §4.1: la REFEZ deve essere "dentro il turno". La PRESA servizio è il
confine di inizio del turno (§3.3). Una REFEZ prima della PRESA è strutturalmente fuori
turno.

L'autorizzazione utente (entry 154, `_inserisci_refezione_ai_bordi` docstring riga 492):
*"se manca la refezione, puoi aggiungerla alla fine o all'inizio se è nelle ore indicate"*
— probabilmente intendeva all'inizio/fine del **lavoro produttivo** (ACCp/ACCa), non prima
della presa di servizio. Il turno scritto nel modello Trenord potrebbe essere rigettato
con questa struttura.

Secondariamente: quando la bordi-strategia 1 sposta `ora_presa` indietro di 30 min, se il
turno originale aveva presa 01:05 (cap notturno 420 min), il nuovo `ora_presa` diventa
00:35, che è fuori dalla finestra cap 01:00–04:59. `is_cap_notturno` verrebbe settato
`False` ma la natura notturna del turno resta invariata. Questo può causare il cap
sbagliato se il turno è ai limiti.

**Fix concreto**

Strategia 1 corretta: spostare la PRESA servizio indietro di 30' E inserire la REFEZ tra
nuova-PRESA e vecchia-PRESA (non prima della PRESA):

```python
# Muovi PRESA all'indietro di 30':
drafts[0] = replace(drafts[0],
    ora_inizio=_from_min(nuovo_ora_presa),
    durata_min=drafts[0].durata_min)  # durata PRESA resta 15 min

# Inserisci REFEZ tra nuova-PRESA e vecchia-PRESA:
refez = _BloccoPdcDraft(
    seq=0,
    tipo_evento="REFEZ",
    ora_inizio=_from_min(nuovo_ora_presa + PRESA_SERVIZIO_MIN),
    ora_fine=_from_min(nuovo_ora_presa + PRESA_SERVIZIO_MIN + REFEZIONE_MIN_DURATA),
    durata_min=REFEZIONE_MIN_DURATA,
    ...
)
return (nuovo_ora_presa, ora_fine_servizio, [drafts[0], refez] + drafts[1:], ...)
```

---

### IMP-3 — `Depot.tipi_personale_ammessi == "PdC"` — filtro fragile su `String(20)`

**File/righe**: `backend/src/colazione/domain/builder_pdc/multi_turno.py:578–582`,
`backend/src/colazione/models/anagrafica.py:131`

**Problema**

```python
Depot.tipi_personale_ammessi == "PdC"
```

Il campo è `String(20)` con `default="PdC"`. Non c'è CHECK constraint né ENUM. Se un depot
futuro avesse `"PdC,Manutentore"` o `"PDC"` (uppercase) o `" PdC"` (whitespace), il filtro
di uguaglianza lo escluderebbe e il builder non lo vedrebbe. Non c'è nessun test che
esercita un depot con valore non-standard.

La colonna è usata in almeno 2 punti dei builder (multi_turno + deposito_first) come unico
meccanismo di selezione depositi PdC.

**Fix concreto**

Option A (rapida): aggiungere CHECK constraint nel DB e usare `contains` nel codice:

```python
.where(Depot.tipi_personale_ammessi.contains("PdC"))
```

Option B (robusta): convertire la colonna in `ARRAY(String)` PostgreSQL o in un ENUM e
aggiornare il filtro con `.any()`. Migration richiesta.

Nel frattempo, aggiungere almeno un test `test_depot_tipi_personale_ammessi_non_exact` che
verifica che un depot con `"PdC,Manutentore"` sia comunque incluso nel builder.

---

### IMP-4 — `builder_version` hardcoded `"mvp-7.9-eta"` per tutti e tre i builder

**File/righe**: `backend/src/colazione/domain/builder_pdc/builder.py:1023`

**Problema**

```python
metadata: dict[str, Any] = {
    ...
    "builder_version": "mvp-7.9-eta",
    ...
}
```

Questa riga è in `_persisti_un_turno_pdc`, condivisa da tutti i builder. I caller passano
`"builder_strategy"` via `extra_metadata` (es. `"deposito_first"`, `"multi_turno_dp_alpha8_ft"`),
ma `builder_version` non viene mai sovrascritta.

In produzione: tutti i `TurnoPdc.generation_metadata_json["builder_version"]` riportano
`"mvp-7.9-eta"` anche per turni generati da `deposito_first` (che è Sprint 8.2) o dal
multi-turno DP alpha8. Non è possibile fare audit per versione di algoritmo.

**Fix concreto**

```python
async def _persisti_un_turno_pdc(
    ...
    builder_version: str = "mvp-7.9-eta",
    ...
) -> BuilderTurnoPdcResult:
    metadata = {
        ...
        "builder_version": builder_version,
        ...
    }
```

Chiamate:
- `builder.py:genera_turno_pdc` → `builder_version="monolitico_7.9"`
- `multi_turno.py:genera_turni_pdc_multi` → `builder_version="multi_turno_dp_alpha8"`
- `deposito_first.py:genera_turni_pdc_deposito_first` → `builder_version="deposito_first_v1"`

---

### IMP-5 — §11.3 (ultimo giorno pre-riposo ≤15:00) non validato — vincolo normativo

**File/righe**: `backend/src/colazione/domain/normativa/assegnazione_persone.py:30–32`

**Problema**

Il docstring dichiara §11.3 "differito":
```
- §11.3 (ultimo giorno pre-riposo ≤15:00) — richiede schedule futuro.
```

Ma §11.3 (NORMATIVA-PDC) è una **regola**, non una preferenza. §11.2 è "preferenziale",
§11.3 è norma contrattuale. `auto_assegna` può assegnare sistematicamente a una persona
un turno che finisce alle 22:00 il venerdì senza alcun warning, violando §11.3.

La differenza rispetto a §11.2: §11.2 è già in `TipoWarningSoft` come soft warning;
§11.3 non è nemmeno un warning.

**Fix concreto**

Aggiungere a `TipoWarningSoft`:

```python
ULTIMO_GIORNO_PRE_RIPOSO_OLTRE_15 = "ultimo_giorno_pre_riposo_oltre_15"
```

In `_check_warning_soft`, dopo il check §11.2:

```python
# §11.3 — ultimo giorno pre-riposo ≤15:00
# "pre-riposo" = questa giornata è seguita da gap ≥2 giorni.
storia = stato.storia_per_persona.get(persona_id, [])
if len(storia) >= 2:
    next_g_idx = giornate_ord.index(g)
    if next_g_idx + 1 < len(giornate_ord):
        next_g = giornate_ord[next_g_idx + 1]
        if (next_g.data - g.data).days >= 2 and g.fine_prestazione > time(15, 0):
            out.append(WarningSoft(
                persona_id=persona_id,
                data=g.data,
                tipo=TipoWarningSoft.ULTIMO_GIORNO_PRE_RIPOSO_OLTRE_15,
                descrizione=f"Fine prestazione {g.fine_prestazione.strftime('%H:%M')} "
                            f"prima del riposo: §11.3 raccomanda ≤15:00",
            ))
```

---

### IMP-6 — Buchi di copertura test sul read-side del cap notturno

**File/righe**: `backend/tests/test_violazioni_normative_pdc.py`,
`backend/tests/test_turno_pdc_validazioni_api.py`

**Problema**

La fix SEVERO S1 (Sprint 8.2) ha introdotto `is_cap_notturno` nel builder, ma i test
esistenti verificano solo il **builder** (che è corretto). Non esiste un test che:
1. Genera un turno con presa 15:00 / fine 23:00 / prestazione 510 min (is_notturno=True, is_cap_notturno=False).
2. Lo legge via `GET /api/turni-pdc/{id}`.
3. Verifica che `n_violazioni_hard == 0` (nessuna falsa violazione).

Come conseguenza, il bug CR-1 sopra non viene rilevato dalla suite corrente. Il test
avrebbe rilevato il problema prima del deploy.

**Fix concreto**

Aggiungere in `test_turno_pdc_validazioni_api.py`:

```python
async def test_turno_notturno_fine_dopo_22_non_genera_false_positive(db_session, client, ...):
    """Turno presa 14:30 fine 23:00: is_notturno=True, cap=510, nessuna violazione."""
    # ... setup turno con prestazione_min=510, is_notturno=True (fine>22)
    resp = await client.get(f"/api/turni-pdc/{turno_id}")
    data = resp.json()
    assert data["n_violazioni_hard"] == 0, (
        "False positive: turno presa 14:30 fine 23:00 non viola normativa"
    )
```

---

## MINORI

### MIN-1 — Dead import `Counter` soppresso con `noqa`

**File/righe**: `backend/src/colazione/domain/builder_giro/varianti_calendariali.py:293`

```python
_ = Counter  # noqa: F841 — riservato per estensioni
```

Il `Counter` viene importato e poi "usato" solo per sopprimere il warning ruff. Non è
documentato per quale estensione futura serva. Rimuovere import + assegnazione.

---

### MIN-2 — Dead code soppresso con `noqa` in `builder_giro/builder.py`

**File/righe**: `backend/src/colazione/domain/builder_giro/builder.py:2757–2758`

```python
_ = festivita  # noqa: F841 (reservato per uso futuro)
_ = calcola_etichetta_giro  # noqa: F841 (export pubblico mantenuto)
```

Se `festivita` non viene usato nella funzione, è un parametro caricato invano. Se
`calcola_etichetta_giro` deve rimanere come export pubblico, dichiararlo in `__all__`
esplicitamente, non via `_=`.

---

### MIN-3 — Naming `multi_giornata_v2.py` in produzione — debito tecnico non risolto

**File/righe**: `backend/src/colazione/domain/builder_giro/multi_giornata_v2.py`,
`backend/src/colazione/domain/builder_giro/builder.py:97`

Il modulo `multi_giornata.py` contiene i dataclass/enum condivisi (Giro, MotivoChiusura,
ecc.); `multi_giornata_v2.py` contiene l'algoritmo di costruzione multi-giornata v2.

Il suffisso `v2` in un modulo di produzione segnala debito tecnico non risolto — il `v1`
non è mai stato ritirato o rinominato. Crea confusione su quale sia "la versione corrente".

**Fix concreto**: rinominare al prossimo MR che tocca `builder_giro`:
- `multi_giornata.py` → `tipi_giro.py` (solo dataclass)
- `multi_giornata_v2.py` → `costruttore_multi_giornata.py`

---

### MIN-4 — Loop `seq_target` in `inserisci_corsa_manuale` fragile con blocchi senza `ora_inizio`

**File/righe**: `backend/src/colazione/api/giri.py:3939–3951`

```python
seq_target = 1
for b in blocchi_esistenti:
    if b.ora_inizio is None:
        seq_target = b.seq + 1
        continue
    if _minuti(b.ora_inizio) < _minuti(corsa.ora_partenza):
        seq_target = b.seq + 1
    else:
        break
```

Blocchi senza `ora_inizio` aggiornano `seq_target = b.seq + 1` e continuano. Se tra due
blocchi con orario c'è un blocco-None, la corsa viene posizionata **dopo** il blocco-None
indipendentemente dal confronto temporale. Per i giri prodotti dal builder questa situazione
non si verifica, ma un inserimento manuale preesistente (CR-3 chain) potrebbe produrlo.

**Fix**: separare i blocchi con e senza orario, eseguire binary search solo sui blocchi con
`ora_inizio is not None`, e usare `len(blocchi_con_orario) + len(blocchi_senza_orario) + 1`
come default per il tail.

---

### MIN-5 — `live_arturo.py:124` — `pass` silenzioso in parsing orari

**File/righe**: `backend/src/colazione/integrations/live_arturo.py:120–126`

```python
try:
    parts = iso_or_hhmm.split(":")
    if len(parts) >= 2:
        return int(parts[0]) * 60 + int(parts[1])
except (ValueError, IndexError):
    pass
return None
```

Il `pass` sopprime ogni errore di parsing senza log. Se il formato API cambia (es. aggiunge
secondi, usa `.` invece di `:`), il resolver non trova orari validi e cade in fallback
VOCTAXI **senza nessun segnale in log**.

**Fix**: `logger.debug("_parse_min: formato orario inatteso %r: %s", iso_or_hhmm, exc)`.

---

### MIN-6 — 50 test falliti pre-esistenti non tracciati come backlog formale

**Contesto**: entry TN-UPDATE 301:
> "pytest full backend: 50 fallimenti pre-esistenti su `master` (verificato via `git stash` → stessi fail). Non sono regressioni di questo fix. Backlog."

**Problema**

Questi 50 fallimenti:
1. Non hanno issue o entry TN-UPDATE dedicata con la lista dei test falliti.
2. La CI pipeline (`.github/workflows/backend-ci.yml`) fallisce sistematicamente → nessun
   segnale utile su regressioni reali.
3. Non è chiaro quanti riguardano logica critica (builder PdC, validatori normativi) vs
   infrastruttura (DB non disponibile, fixture mancanti).

**Fix**:

```bash
cd backend && pytest --tb=no -q 2>&1 | grep FAILED > /tmp/failing_tests.txt
```

Classificare i 50 failing in:
- A) Infrastruttura (DB non disponibile in CI) → skippa con `@pytest.mark.skip` motivato
- B) Logica critica → fix entro Sprint 8.5
- C) Fixture rotto → riparazione veloce

Aprire una entry TN-UPDATE dedicata con la lista e il piano di triage.

---

## Tabella riassuntiva

| ID | Gravità | File principale | Riga | Descrizione breve |
|----|---------|-----------------|------|-------------------|
| CR-1 | CRITICO | `api/turni_pdc.py` | 947 | `is_cap_notturno` non persistito → false positive violazioni |
| CR-2 | CRITICO | `builder_pdc/multi_turno.py` | 590 | Carica TUTTI i TurnoPdc in RAM per anti-regen check |
| CR-3 | CRITICO | `api/giri.py` | 4048 | `inserisci_corsa_manuale` non invalida TurnoPdc dipendenti |
| CR-4 | CRITICO | `builder_pdc/registro_vetture.py` | 157 | Wild card `data_operativa=None` blocca vetture su ogni data |
| IMP-1 | IMPORTANTE | `builder_pdc/builder.py` | 210,253,256 | `assert` in produzione, crash silente con `-O` |
| IMP-2 | IMPORTANTE | `builder_pdc/builder.py` | 477 | REFEZ inserita prima di PRESA servizio — violazione struttura §4.1 |
| IMP-3 | IMPORTANTE | `builder_pdc/multi_turno.py` | 578 | Filtro `tipi_personale_ammessi == "PdC"` fragile su String |
| IMP-4 | IMPORTANTE | `builder_pdc/builder.py` | 1023 | `builder_version` hardcoded per tutti e tre i builder |
| IMP-5 | IMPORTANTE | `normativa/assegnazione_persone.py` | 30 | §11.3 non validato — vincolo normativo, non preferenziale |
| IMP-6 | IMPORTANTE | `tests/test_turno_pdc_validazioni_api.py` | — | Manca test read-side cap notturno (CR-1 non rilevato dai test) |
| MIN-1 | MINORE | `builder_giro/varianti_calendariali.py` | 293 | Dead import `Counter` soppresso con `noqa` |
| MIN-2 | MINORE | `builder_giro/builder.py` | 2757 | Dead code `_ = festivita` soppresso con `noqa` |
| MIN-3 | MINORE | `builder_giro/multi_giornata_v2.py` | — | Nome `v2` in produzione — debito tecnico non risolto |
| MIN-4 | MINORE | `api/giri.py` | 3939 | Loop `seq_target` fragile con blocchi `ora_inizio=None` |
| MIN-5 | MINORE | `integrations/live_arturo.py` | 124 | `pass` silenzioso in parsing orari API |
| MIN-6 | MINORE | `backend/tests/` | — | 50 test falliti non tracciati come backlog formale |

---

## Note metodologiche

**Fonti verificate**:
- Letti: `TN-UPDATE.md` (prime 5 entry), `docs/METODO-DI-LAVORO.md`,
  `docs/NORMATIVA-PDC.md` (§3, §4, §7, §10, §11), `docs/MODELLO-DATI.md`
- Analizzati in dettaglio: `builder_pdc/builder.py`, `builder_pdc/multi_turno.py`,
  `builder_pdc/deposito_first.py`, `builder_pdc/registro_vetture.py`,
  `builder_pdc/giornata_base.py`, `builder_pdc/vettura_resolver.py`,
  `normativa/assegnazione_persone.py`, `vincoli/inviolabili.py`,
  `api/turni_pdc.py`, `api/pianificatore_pdc.py`, `api/giri.py` (sezione inserisci-manuale),
  `integrations/live_arturo.py`, `models/turni_pdc.py`, `models/anagrafica.py`
- Ispezionati: tutti i 85 file test, struttura migrazioni, struttura frontend

**Non analizzati in dettaglio** (fuori tempo): `frontend/src/routes/` completo,
`domain/builder_giro/` (solo struttura + grep), `domain/calendario.py`,
`domain/dsl_varianti_calendariali.py`.

**Criteri di classificazione**:
- CRITICO: violazione normativa PdC documentata, o inconsistenza dati silenziosa,
  o scalability che blocca produzione.
- IMPORTANTE: qualità/manutenibilità con impatto operativo non immediato,
  o test coverage su logica critica.
- MINORE: stile, naming, dead code senza impatto funzionale.
