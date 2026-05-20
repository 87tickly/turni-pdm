# Code Review — COLAZIONE Backend (2026-05-20)

> **Perimetro**: backend Python + modelli + test. Frontend non incluso (scopo sprint corrente).
> **Stato codebase**: Sprint 8.3 in corso, dopo chiusura Sprint 8.2 (builder deposito-first,
> §11.4/§11.5/§15 validatori, registro vetture cross-PdC).
> **Riferimento precedente**: `docs/CODE-REVIEW-2026-05-01.md` (24 finding post Sprint 7.4).

---

## Metodo

Lettura diretta dei file critici (builder_pdc, vincoli, api, models) + grep sistematico su:
`TODO/FIXME`, magic numbers normativi, `except Exception`, `type: ignore`,
`print()` vs `logger`, violazioni layering, import circolari, gaps di test.

Ogni finding cita **file:riga**, propone un fix concreto (non descrizioni generiche).

---

## CRITICO

*Violazione normativa confermata, bug latente che produce output errati in produzione,
o debito tecnico che blocca l'evoluzione.*

---

### C1 — Preriscaldo ACCp 80' mai implementato (violazione §3.3)

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:57, 215-216, 244, 296, 1103`

**Normativa §3.3**:

| Caso | ACCp | ACCa |
|------|------|------|
| Condotta standard | **40'** | **40'** |
| Condotta con preriscaldo ● (dic-feb) | **80'** | **40'** |

Il builder usa sempre `ACCESSORI_MIN_STANDARD = 40` per ACCp, senza distinzione stagionale. Il campo `TurnoPdcBlocco.is_accessori_maggiorati` esiste in DB (`models/turni_pdc.py:114`) e nello schema (`schemas/turni_pdc.py:67`) ma è persistito come `False` hardcoded a `builder.py:1103`.

**Impatto**: ogni turno generato per giri operativi in dicembre-gennaio-febbraio
ha l'ACCp sbagliato (40' invece di 80'). Prestazione calcolata 40 minuti sotto
il reale. Il validatore §3.3 non può scattare perché il valore errato non è
mai prodotto.

**Fix**:

1. Aggiungere costante:
   ```python
   # builder.py
   ACCESSORI_MIN_PRERISCALDO = 80  # NORMATIVA-PDC §3.3, dic-feb
   MESI_PRERISCALDO: frozenset[int] = frozenset({12, 1, 2})
   ```
2. Aggiungere parametro `mese_operativo: int | None = None` a `_build_giornata_pdc` e derivarlo da `data_operativa.month` nel chiamante (`genera_turno_pdc`).
3. Calcolare dinamicamente:
   ```python
   acc_p = (
       ACCESSORI_MIN_PRERISCALDO
       if mese_operativo in MESI_PRERISCALDO
       else ACCESSORI_MIN_STANDARD
   )
   ```
4. Passare `is_accessori_maggiorati=(mese_operativo in MESI_PRERISCALDO)` al `_BloccoPdcDraft` ACCp.

**Nessun test** su questo percorso (da aggiungere).

---

### C2 — Scelta ACC vs PK basata su gap (§6) non implementata

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:252-270`

**Normativa §6**:

| Gap fra blocchi consecutivi | Modalità ammesse |
|-----------------------------|------------------|
| < 65' | CV o PK (non ACC: non c'è tempo per 40'+40') |
| 65–300' | **ACC** (ACCa+ACCp) o PK |
| > 300' | **ACC** default, PK solo su opt-in operatore |

Il builder inserisce SEMPRE `tipo_evento="PK"` per qualsiasi `gap > 0`:

```python
# builder.py:258-269 — qualsiasi gap diventa PK
if gap > 0:
    drafts.append(_BloccoPdcDraft(
        tipo_evento="PK",  # ← sempre PK, §6 ignorata
        durata_min=gap,
        ...
    ))
```

**Impatto**: un gap di 120 minuti fra due corse consecutive (zona 65-300' → regola ACC:
ACCa 40' + buco 40' + ACCp 40' = 120') diventa un PK di 120'. Il PdC non ha gli
accessori dichiarati. Il calcolo del tempo condotta è errato (il gap è contato come PK
invece che come ACC+buco). Il validatore §6 non può scattare.

**Fix**:

```python
GAP_CV_MAX_MIN = 65    # §6: sotto questo gap, solo CV o PK
GAP_ACC_MIN_MIN = 65   # §6: sopra questo gap, ACC ammesso
GAP_PK_GRANDI_MIN = 300  # §6: > 300' → ACC default, PK su opt-in

if gap > 0:
    if gap < GAP_CV_MAX_MIN:
        # < 65': ACC non ammesso (non c'è fisicamente tempo).
        # PK default se non c'è stazione CV ammessa.
        tipo = "PK"
    elif gap <= GAP_PK_GRANDI_MIN:
        # 65-300': ACC (ACCa + corpo + ACCp) o PK.
        # Default builder: ACC (più corretto normativamente).
        # Inserire blocco ACCa(40) + buco residuo + ACCp(40).
        tipo = "ACC"
    else:
        # > 300': ACC di default.
        tipo = "ACC"
```

Nota: per `tipo="ACC"` occorre inserire 3 blocchi: `ACCa(40)` sul prec,
`BUCO(gap-80)` al centro, `ACCp(40)` sul succ — non un blocco unico.

---

### C3 — PK: nessun controllo sul minimo di 20' (violazione §4.4)

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:257-269`

**Normativa §4.4**: "PK in arrivo: **20' minimo**, PK in partenza: **20' minimo**".

Il builder inserisce PK per `gap > 0` senza floor check. Un gap di 3 minuti
produce un `PK(durata_min=3)` — normativamente invalido.

**Fix**:

```python
PK_MIN_DURATA_MIN = 20  # NORMATIVA-PDC §4.4

if gap >= PK_MIN_DURATA_MIN:
    drafts.append(_BloccoPdcDraft(tipo_evento="PK", durata_min=gap, ...))
else:
    # gap < 20': non è PK valido né ACC (< 65'). Tempo tecnico implicito.
    # Registrare come warning di giornata, non ignorare silenziosamente.
    violazioni.append(f"gap_sotto_minimo_pk:{gap}min_tra_{b_prec.numero}->{b.numero}")
```

---

### C4 — Full-table scan su `TurnoPdc` per anti-rigenerazione

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:734-738`

```python
existing = list(
    (
        await session.execute(
            select(TurnoPdc).where(TurnoPdc.azienda_id == azienda_id)  # ← tutti i turni
        )
    ).scalars()
)
```

La query carica in memoria **tutti i turni PdC dell'azienda** per poi filtrare in Python
con `_matches_giro_e_deposito`. Con Trenord (centinaia di turni generati su produzione),
ogni chiamata a `genera_turno_pdc` materializza N turni in RAM solo per trovarne K ≪ N.

**Fix**: Filtrare in SQL usando il campo JSONB (già fatto in `deposito_first.py:469-479`
che usa la stessa strategia ma con `deposito_pdc_id` come filtro SQL — applica lo stesso
pattern al builder legacy):

```python
# filtra per (azienda, deposito) in SQL; giro_materiale_id solo in Python
existing = list(
    (await session.execute(
        select(TurnoPdc).where(
            TurnoPdc.azienda_id == azienda_id,
            TurnoPdc.deposito_pdc_id == deposito_pdc_id,  # se valorizzato
        )
    )).scalars()
)
```

O, per il legacy senza deposito, aggiungere una FK diretta `TurnoPdc.giro_materiale_id`
(vedi I7) e filtrare in SQL su quella.

---

### C5 — §7.3 condotta come rientro produttivo non implementata

**File**: `backend/src/colazione/domain/builder_pdc/deposito_first.py:311-327`
e `vettura_resolver.py:13-14`

**Normativa §7.3**: se esiste un **treno di condotta** nel giro materiale che trasporta
il PdC verso il deposito, il PdC lo **conduce** — NON si usa il rientro passivo (vettura,
MM, VOCTAXI). La condotta produttiva ha **priorità superiore** alla vettura passiva.

Il builder `deposito_first.costruisci_giornata_deposito_first` invoca immediatamente
`risolvi_rientro` (priorità VETTURA→MM→VOCTAXI) senza verificare se esistono
blocchi giro successivi all'ultimo blocco corrente che portano al deposito.

**Impatto**: turni che potrebbero chiudersi con una corsa produttiva verso il deposito
vengono invece chiusi con una VETTURA passiva (o MM/VOCTAXI). Normativa violata,
ottimizzazione persa.

**Fix**: Aggiungere prima di `risolvi_rientro`:

```python
# Cerca un blocco di condotta successivo che raggiunga il deposito
rientro_produttivo = _trova_rientro_produttivo(
    blocchi_giro_rimanenti, deposito_stazione
)
if rientro_produttivo is not None:
    # Estendi la giornata con il blocco di condotta
    return _chiudi_con_condotta_produttiva(draft, rientro_produttivo)
```

Dove `blocchi_giro_rimanenti` sono i blocchi del giro NON ancora inclusi
nella giornata corrente.

---

### C6 — `data_operativa` statica per tutte le giornate del turno

**File**: `backend/src/colazione/domain/builder_pdc/deposito_first.py:537, 566`

```python
valido_da_eff = valido_da or date.today()
# ...
for gg in giornate_giro:
    # ...
    draft, violazioni = await costruisci_giornata_deposito_first(
        ...
        data_operativa=valido_da_eff,  # ← stessa data per TUTTE le giornate
    )
```

Il registro vetture usa `data_operativa` come chiave di registro cross-PdC
(NORMATIVA §15.1-§15.2). Per un turno di 7 giornate, giornata 1 è il giorno X,
giornata 7 è il giorno X+6, ma entrambe vengono registrate con data X.

**Impatto**: il registro non discrimina le vetture per giorno reale.
La giornata 7 "vede" come occupate le vetture della giornata 1
(stesso giorno nel registro) anche se le date calendariali sono diverse.
Efetto: il resolver esclude vetture erroneamente, peggiorando la coverage vetture.

**Fix interim** (in attesa di `enumera_date_giornata` S4):

```python
from datetime import timedelta
data_gg = valido_da_eff + timedelta(days=gg.numero_giornata - 1)
draft, violazioni = await costruisci_giornata_deposito_first(
    ...
    data_operativa=data_gg,
)
```

Questo assume 1 giornata del ciclo = 1 giorno calendariale, che è corretto per
il MVP (il ciclo del giro materiale è lineare, 1 giornata per giorno).

---

## IMPORTANTE

*Qualità, manutenibilità, debito tecnico non bloccante.*

---

### I1 — `giornata_base.py`: facade cosmetic che espone simboli privati

**File**: `backend/src/colazione/domain/builder_pdc/giornata_base.py:47-57`

Il modulo si presenta come "API stabile" ma re-esporta direttamente i simboli
privati `_xxx` di `builder.py`:

```python
from colazione.domain.builder_pdc.builder import (
    _aggiungi_dormite_fr,
    _BloccoPdcDraft,
    _build_giornata_pdc,
    _calcola_violazioni_cap_fr,
    ...
)
BloccoPdcDraft = _BloccoPdcDraft  # alias, non astrazione
```

Se `builder.py` rinomina `_build_giornata_pdc` → `_build_day`, il facade si rompe
ugualmente. L'astrazione non aggiunge valore: è un livello di indirezione senza
stabilità.

**Fix**: Spostare le primitive (`_BloccoPdcDraft`, `_GiornataPdcDraft`,
`_build_giornata_pdc`, ecc.) dentro `giornata_base.py` con nomi pubblici.
Far importare `builder.py` da `giornata_base.py`, invertendo la dipendenza.
La direzione corretta è:
```
giornata_base.py (primitive, pubbliche)
  ↑ importa
builder.py, deposito_first.py, multi_turno.py, split_cv.py
```

---

### I2 — `api/giri.py` da 4422 righe viola SRP

**File**: `backend/src/colazione/api/giri.py`

Il file unisce: routing FastAPI, business logic (inserimento corsa manuale,
riempimento gap), query SQL complesse (JOIN multi-tabella per Gantt unificato),
validazione del payload, orchestrazione della pipeline, e trasformazione dei
risultati per il frontend. È il file più lungo del progetto (4422 righe).

**Fix**: Estrarre almeno:

1. `services/giro_service.py` — logica inserimento corsa manuale, riempimento gap
2. `repositories/giro_repository.py` — query SQL ricorrenti (load giornate+varianti+blocchi)
3. `schemas/giri.py` — tipi e modelli Pydantic (già esiste `schemas/`, va completato)

La route residua diventa solo orchestrazione (dipendenze, auth, chiamata service).

---

### I3 — `updated_at` non si aggiorna sulle UPDATE (5 modelli)

**File**:
- `backend/src/colazione/models/turni_pdc.py:59`
- `backend/src/colazione/models/giri.py:79`
- `backend/src/colazione/models/personale.py:69`
- `backend/src/colazione/models/programmi.py:187`
- `backend/src/colazione/models/anagrafica.py:116`

Tutti usano `server_default=func.now()` senza `onupdate`. I record non aggiornano
`updated_at` quando vengono modificati via `session.execute(update(...))`.

**Fix**: Aggiungere `onupdate=func.now()` oppure usare un trigger Postgres
(preferibile se ci sono UPDATE dirette via SQL):

```python
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
    onupdate=func.now(),
)
```

Nota: `onupdate` SQLAlchemy funziona solo per UPDATE via ORM, non per
`session.execute(update(...))`. Per il secondo caso serve un trigger Postgres.

---

### I4 — `TurnoPdc.codice` senza UniqueConstraint su `(azienda_id, codice)`

**File**: `backend/src/colazione/models/turni_pdc.py:39, 61`

Il codice turno (`T-FIORENZA-001-ETR526`) non ha un vincolo UNIQUE nel DB.
La rigenerazione concorrente (due request parallele su stesso giro+deposito)
potrebbe creare duplicati prima che il check anti-rigenerazione in memoria li blocchi.
Il check in Python non è atomico rispetto a request concorrenti.

**Fix**:

```python
__table_args__ = (
    UniqueConstraint("azienda_id", "codice", name="uq_turno_pdc_azienda_codice"),
    Index("ix_turno_pdc_azienda_deposito", "azienda_id", "deposito_pdc_id"),
)
```

Con migration corrispondente (`0047_...`).

---

### I5 — Import deferred ciclico `split_cv ↔ builder`

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:771`

```python
# "Import deferred dentro le funzioni per evitare ciclo"
from colazione.domain.builder_pdc.split_cv import lista_stazioni_cv_ammesse
```

L'import dentro la funzione è un workaround per una dipendenza circolare tra
`builder.py` e `split_cv.py`. È fragile (mypy non rileva gli import deferred
fuori dal contesto di import) e segnala un problema architetturale.

**Fix**: Spostare `lista_stazioni_cv_ammesse` (funzione DB che carica i depot
ammessi a CV) in `stazioni_cv.py` — modulo autonomo. Né `builder.py` né
`split_cv.py` si importano più circolarmente:

```
stazioni_cv.py (nuovo)  ← importato da split_cv.py E builder.py
split_cv.py             ← importato da builder.py
builder.py              ← importato da api/
```

---

### I6 — `TurnoPdcGiornata.km` sempre 0 — dead data

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:1078`

```python
gg_orm = TurnoPdcGiornata(
    ...
    km=0,  # ← mai calcolato
    ...
)
```

Il campo `km` è nel modello, nello schema, e probabilmente esposto in API.
Il pianificatore legge sempre 0. È fuorviante.

**Fix**: Se il calcolo km non è prioritario ora, documentare esplicitamente:

```python
km=0,  # non calcolato — scope MR-PD-KM (post-Sprint 8.3)
```

E aggiungere una entry in `TN-UPDATE.md` come debito aperto.

---

### I7 — `generation_metadata_json.giro_materiale_id` usato come FK implicita

**File**: `backend/src/colazione/domain/builder_pdc/registro_vetture.py:189-213`

Il filtro per `programma_id` dipende da un CAST runtime di stringa JSONB:

```python
cast(
    func.jsonb_extract_path_text(
        TurnoPdc.generation_metadata_json, "giro_materiale_id"
    ),
    Integer,
).in_(giri_ids_subq)
```

- Se `generation_metadata_json` è `NULL` → CAST ritorna NULL → il turno sfugge
  al filtro silenziosamente (il registro vetture non carica le vetture di quel turno).
- Se il formato JSON cambia (es. chiave rinominata) → tutti i turni esistenti
  sfuggono al filtro, senza errore.
- La query non può usare un indice normale (scan JSONB O(n)).

**Fix**: Aggiungere colonna FK diretta `TurnoPdc.giro_materiale_id: int | None`
con indice. Il campo JSONB rimane per retrocompatibilità e audit, ma le query
usano la FK. Migration `0047_turno_pdc_giro_fk.py` con backfill.

---

### I8 — Riposo intraturno: ultima giornata usa stima conservativa non documentata

**File**: `backend/src/colazione/domain/builder_pdc/riposo_intraturno.py:190-195`

```python
# Ultima giornata: gap "settimanale" — stima.
gap_singola_notte = riposo_effettivo_min(prec.fine_prestazione, succ.inizio_prestazione)
prec.riposo_min_post = gap_singola_notte + 24 * 60  # +24h conservativo
```

Il `+24*60` è un'euristica non documentata normativa (§11.4 parla di 62h, non
di "notte + 24h"). Il commento lo chiama "placeholder finché §11.4 non lo raffina"
ma §11.4 (`riposo_settimanale.py`) è già implementata e valida separatamente.

**Impatto**: `riposo_min_post` dell'ultima giornata è artificialmente alto. La UI
e qualsiasi codice che legge `TurnoPdcGiornata.riposo_min` per l'ultima giornata
ottiene un valore non reale.

**Fix**: L'ultima giornata dovrebbe usare il gap dal dataset §11.4 quando disponibile.
Se non disponibile, documentare esplicitamente come `0` (valore "ignoto") invece
di un'euristica che sembra un dato reale.

---

### I9 — Buchi di copertura test su percorsi critici normativi

**Test mancanti**:

| Regola normativa | Implementata? | Test? |
|-----------------|---------------|-------|
| §3.3 ACCp 80' preriscaldo (dic-feb) | ❌ No | ❌ No |
| §4.4 PK minimo 20' | ❌ No | ❌ No |
| §6 ACC vs PK basata su gap | ❌ No | ❌ No |
| §7.3 condotta come rientro produttivo | ❌ No | ❌ No |
| §3.2 vettura di partenza (bordo turno) | ❌ No | ❌ No |

**Fix**: Le funzionalità non ancora implementate devono avere test marcati
`@pytest.mark.xfail(strict=True, reason="§X.Y non implementata, scope MR-...")`.
Questo:
1. Documenta il debito nel test suite (non in TODO nei commenti)
2. Garantisce che un'implementazione futura faccia scattare il test
3. Rompe la CI se qualcuno implementa senza aggiungere il test

---

## MINORE

*Stile, micro-ottimizzazioni, cleanup.*

---

### M1 — Sprint references nei commenti oscurano il WHY

Tutto il codebase è disseminato di commenti come:
- `# Sprint 7.4 MR 2: split CV intermedio`
- `# Sprint 8.2 MR-PD-FIX-SEVERO 3b A1: campo strutturato per registro`
- `# Sprint 8.3 S10 SEVERO post-Sprint: signature semplificata`

I numeri di sprint non sono informazioni utili per chi legge il codice in futuro
(non sa cosa era Sprint 7.4 MR 2). Diventano rumore. Il WHY tecnico che i commenti
dovrebbero trasmettere è sepolto sotto la burocrazia di versionamento.

**Fix**: Convertire in riferimenti normativi o note tecniche:
```python
# NORMATIVA-PDC §5: CV richiede stazione ammessa in lista Depot
# (codici MORTARA e TIRANO sono deroghe configurabili, hardcoded per MVP)
```

---

### M2 — Dead code mascherato con `# noqa: F841`

**File**:
- `backend/src/colazione/domain/builder_giro/builder.py:2757`: `_ = festivita  # noqa: F841`
- `backend/src/colazione/domain/builder_giro/varianti_calendariali.py:293`: `_ = Counter  # noqa: F841`

Import non usati mascherati da assegnazione. Se `festivita` e `Counter` non sono
usati, l'import va rimosso — non ignorato con noqa.

**Fix**: `git grep` per verificare se usati altrove nello stesso file.
Se no: rimuovere import + assegnazione.

---

### M3 — `except Exception:` in test senza `pytest.raises`

**File**: `backend/tests/test_domain_variazioni.py:409`

```python
except Exception:
    return  # ← maschera l'errore, non asserisce il tipo
```

Anti-pattern: il test supera anche se l'eccezione è sbagliata (es. `AttributeError`
invece di `FrozenInstanceError`).

**Fix**:
```python
import dataclasses
with pytest.raises(dataclasses.FrozenInstanceError):
    snap.is_cancellata = True
```

---

### M4 — `S.COMP` nel tipo_evento mai generato

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:141`

```python
tipo_evento: str  # CONDOTTA, VETTURA, REFEZ, ..., SCOMP, ...
```

Il tipo `SCOMP` (Disponibilità a comparto, §11.3: min 6h) è menzionato nella
docstring ma nessun builder lo genera. È dead type nell'enum testuale.

**Fix**: O implementare S.COMP (§11.3 non è ancora validata) o rimuoverlo
dalla lista e aggiungere una nota nel TODO `TN-UPDATE.md`.

---

### M5 — `ciclo_giorni=max(1, min(14, giro.numero_giornate))`: magic number 14

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:1053`

Il valore `14` non ha riferimento normativo documentato. Non c'è un commento
che spiega perché il ciclo è clamped a 14 giorni.

**Fix**: Sostituire con costante documentata:

```python
# Trenord usa cicli max 14gg (operativo, non da NORMATIVA-PDC).
# Giri più lunghi vengono troncati: revisione in MR-PD-CICLO-LUNGO se serve.
TURNO_PdC_CICLO_GIORNI_MAX = 14

ciclo_giorni=max(1, min(TURNO_PdC_CICLO_GIORNI_MAX, giro.numero_giornate)),
```

---

### M6 — `is_accessori_maggiorati` su `TurnoPdcBlocco` — campo dead finché C1 non è chiuso

**File**: `backend/src/colazione/models/turni_pdc.py:114`, `backend/src/colazione/domain/builder_pdc/builder.py:1103`

Il campo esiste e occupa spazio in ogni risposta API per ogni blocco, ma è sempre `False`.
Finché C1 (preriscaldo) non è implementato, il campo è dead data.

**Non è un fix di rimozione**: il campo va mantenuto per C1. Ma il docstring del
modello dovrebbe dichiarare: `# reserved: sarà True per ACCp dic-feb (NORMATIVA §3.3)`.

---

## Riepilogo per priorità

| ID | Gravità | Titolo breve | Effort stimato |
|----|---------|--------------|----------------|
| C1 | CRITICO | Preriscaldo ACCp 80' non implementato | 4h (builder + test) |
| C2 | CRITICO | Scelta ACC/PK/CV basata su gap non implementata | 1g (refactor builder + test) |
| C3 | CRITICO | PK minimo 20' non validato | 2h (builder + test) |
| C4 | CRITICO | Full-table scan TurnoPdc anti-rigenerazione | 2h (query SQL + migration FK) |
| C5 | CRITICO | §7.3 condotta rientro produttivo non implementata | 1g |
| C6 | CRITICO | data_operativa statica per tutte le giornate | 1h (fix interim) |
| I1 | IMPORTANTE | giornata_base.py facade cosmetic | 3h (refactor architettura) |
| I2 | IMPORTANTE | api/giri.py 4422 righe, SRP violato | 2g (estrazione service/repo) |
| I3 | IMPORTANTE | updated_at non aggiornato su UPDATE | 1h (5 modelli + migration trigger) |
| I4 | IMPORTANTE | TurnoPdc.codice senza UniqueConstraint | 1h (migration) |
| I5 | IMPORTANTE | Import deferred ciclico split_cv ↔ builder | 3h (nuovo modulo stazioni_cv) |
| I6 | IMPORTANTE | TurnoPdcGiornata.km sempre 0 | 30min (documentare o rimuovere) |
| I7 | IMPORTANTE | generation_metadata_json.giro_materiale_id come FK implicita | 4h (migration + query) |
| I8 | IMPORTANTE | Ultima giornata riposo_min_post euristica non documentata | 2h (chiarire semantica) |
| I9 | IMPORTANTE | Buchi test su percorsi normativi critici | 4h (xfail + test) |
| M1 | MINORE | Sprint references nei commenti | ongoing |
| M2 | MINORE | Dead code mascherato con noqa:F841 | 30min |
| M3 | MINORE | except Exception in test senza pytest.raises | 15min |
| M4 | MINORE | S.COMP tipo_evento dead | 30min (doc o TODO) |
| M5 | MINORE | ciclo_giorni magic number 14 | 15min (costante) |
| M6 | MINORE | is_accessori_maggiorati dead finché C1 non chiude | 15min (docstring) |

---

## Note finali

**Punti di forza del codebase**:
- Layering `models/domain/api` coerente: zero violazioni rilevate
- Costanti normative ben definite in `vettura_resolver.py` (510, 420, 15, 30, ecc.)
- Logging consistente (nessun `print()` in production code)
- `RegistroVettureAssegnate` ha logica di wild-card documentata e deliberata
- `riposo_settimanale.py` e `riposo_intraturno.py` sono corretti e ben testati (§11.4/§11.5)
- La state machine pipeline (`pipeline.py`) è funzionalmente corretta

**Debito più urgente** (in ordine operativo):

1. **C1** (preriscaldo): ogni turno generato in dic-gen-feb è sbagliato oggi
2. **C4** (full scan): performance degraderà con volume — da fare prima del go-live
3. **C6** (data_operativa): fix di 1 riga, impact alto sul registro vetture

---

*Documento generato il 2026-05-20. Riferimento: `docs/CODE-REVIEW-2026-05-01.md` (review precedente, Sprint 7.4).*
