# Code Review — COLAZIONE (2026-05-12)

> **Scope**: review completa del repo dopo Sprint 8.4 G3 (entry 301).
> Revisore: NINO (Claude Code). Branch `claude/zen-babbage-M3AKq`.
> Commissione utente: nessuna modifica al codice di produzione in questo PR —
> solo documento. I fix accettati diventano MR separati.
>
> **Metodo**: lettura integrale di `TN-UPDATE.md` (prime 5 entry),
> `NORMATIVA-PDC.md`, `MODELLO-DATI.md`, `METODO-DI-LAVORO.md`,
> mapping completo dei file sorgente, lettura del codice critico (builder PdC,
> validatori, modelli, API, test runner). Ogni finding cita `file:riga`,
> confronto con la normativa dove applicabile, fix concreto proposto.

---

## Indice

- [CRITICI (C)](#critici)
- [IMPORTANTI (I)](#importanti)
- [MINORI (M)](#minori)
- [Riepilogo metrico](#riepilogo)

---

## CRITICI

### C-01 — `TurnoPdc.updated_at` non si aggiorna mai (bug silenzioso)

**File**: `backend/src/colazione/models/turni_pdc.py:59`

```python
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), server_default=func.now()
)
```

`server_default` valorizza il campo solo alla INSERT. Ogni UPDATE al record
(modifica `stato`, `generation_metadata_json`, ecc.) lascia `updated_at`
congelato alla data di creazione. L'audit trail è corrotto in silenzio: non
si può sapere quando è stato modificato l'ultimo turno.

**Fix**:
```python
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
    onupdate=func.now(),
)
```

Stessa issue su `GiroMateriale.updated_at`
(`backend/src/colazione/models/giri.py`): identico pattern.

---

### C-02 — Anti-rigenerazione in `deposito_first` carica TUTTI i turni del deposito in RAM

**File**: `backend/src/colazione/domain/builder_pdc/deposito_first.py:465-479`

```python
existing = list(
    (
        await session.execute(
            select(TurnoPdc).where(
                TurnoPdc.azienda_id == azienda_id,
                TurnoPdc.deposito_pdc_id == deposito_pdc_id,
            )
        )
    ).scalars()
)
legati = [
    t for t in existing
    if (t.generation_metadata_json or {}).get("giro_materiale_id") == giro_id
]
```

La query SQL non filtra per `giro_id`: carica TUTTI i `TurnoPdc`
dell'azienda + deposito in memoria, poi filtra in Python via `.get(...)`.
Su un deposito come `GARIBALDI_TE` con decine di turni attivi questo è
O(N) di I/O inutile. Il filtro JSONB è già disponibile
(`jsonb_extract_path_text` è già usato in `registro_vetture.py:200-212`).

**Fix** — filtra in SQL direttamente:
```python
from sqlalchemy import cast, func, Integer

legati = list(
    (
        await session.execute(
            select(TurnoPdc).where(
                TurnoPdc.azienda_id == azienda_id,
                TurnoPdc.deposito_pdc_id == deposito_pdc_id,
                cast(
                    func.jsonb_extract_path_text(
                        TurnoPdc.generation_metadata_json, "giro_materiale_id"
                    ),
                    Integer,
                ) == giro_id,
            )
        )
    ).scalars()
)
```

Elimina il loop Python e il caricamento massivo.

---

### C-03 — `registro_vetture.from_db`: 4 subquery annidate senza indice JSONB (query lenta su programma grande)

**File**: `backend/src/colazione/domain/builder_pdc/registro_vetture.py:188-230`

La query `from_db` ha questa catena:
1. `giri_ids_subq`: tutti i `GiroMateriale.id` del programma.
2. `turni_ids_subq`: `cast(jsonb_extract_path_text(generation_metadata_json, "giro_materiale_id"), Integer).in_(giri_ids_subq)` — full-scan della colonna JSONB su TUTTI i turni PdC dell'azienda.
3. `giornate_ids_subq`: giornate dei turni filtrati.
4. Query finale: blocchi VETTURA delle giornate.

Non esiste indice su `generation_metadata_json->'giro_materiale_id'`.
Su un programma con 6 536 corse (PdE reale Trenord 2025-2026, TN-UPDATE),
N giri generati, M turni PdC, PostgreSQL esegue nested loop su full-scan
JSONB per ogni row di `turno_pdc`. Il planner non può usare l'indice
`ix_turno_pdc_azienda_deposito` per questo filtro.

**Fix a breve termine**: aggiungere indice GIN sulla colonna JSONB:
```python
# In migration:
Index(
    "ix_turno_pdc_giro_id_jsonb",
    text("(generation_metadata_json->>'giro_materiale_id')"),
)
```

**Fix a medio termine** (MODELLO-DATI.md §LIV 3a): aggiungere colonna
`giro_materiale_id: Mapped[int | None]` esplicita su `TurnoPdc`, elimina
il `generation_metadata_json` come meccanismo di lookup di FK.

---

### C-04 — 78 test falliscono in collection su ambiente locale (no DB installato)

**File**: `backend/tests/test_riposo_intraturno.py:7`, `backend/tests/test_riposo_settimanale.py:7`

```python
from colazione.domain.builder_pdc.builder import _GiornataPdcDraft
```

I due test importano il simbolo PRIVATO `_GiornataPdcDraft` direttamente da
`builder.py` (bypassando il facade `giornata_base.py`). `builder.py` importa
`sqlalchemy` a livello modulo (`from sqlalchemy import select` — riga 39).
Quando pytest è lanciato con il Python di sistema (senza il venv backend,
che ha SQLAlchemy ma non ha pytest installato), questi due test trascinano in
errore di collection tutti i test che condividono il discovery path.

Risultato verificato: 78 `ERROR during collection` con
`ModuleNotFoundError: No module named 'sqlalchemy'`.

**Impatto**: la suite di test è di fatto non eseguibile localmente senza
configurazione specifica del runner. I test di DOMINIO PURO (riposo
intraturno/settimanale) non dovrebbero avere dipendenza da SQLAlchemy.

**Fix**: sostituire l'import privato con il facade pubblico in entrambi i test:
```python
# PRIMA (sbagliato):
from colazione.domain.builder_pdc.builder import _GiornataPdcDraft

# DOPO (corretto):
from colazione.domain.builder_pdc.giornata_base import GiornataPdcDraft
```

E rinominare le occorrenze `_GiornataPdcDraft` → `GiornataPdcDraft`
nel corpo dei test.

---

### C-05 — `assert` in codice di produzione (silently disabled con `python -O`)

**Files**:
- `backend/src/colazione/domain/builder_pdc/builder.py:210,253,256`
- `backend/src/colazione/domain/builder_pdc/multi_turno.py:421,477,1140`
- `backend/src/colazione/domain/builder_giro/capacity_routing.py:306`
- `backend/src/colazione/domain/builder_pdc/riposo_settimanale.py:271-273`

Gli `assert` vengono rimossi a compile-time se Python è lanciato con
ottimizzazioni (`-O` o `-OO`). Il comportamento diventa indefinito invece di
sollevare un errore chiaro. In ambiente Railway con Dockerfile che usa
`CMD uvicorn ...` senza esplicitare `-O`, il rischio è basso oggi, ma un
cambio di Dockerfile o immagine base ottimizzata romperebbe tutti gli
invarianti silenziosamente.

`riposo_settimanale.py:271-273` è particolarmente critico: i tre `assert`
che fanno type narrowing su `data_inizio_programma`, `data_fine_programma`,
`festivita` garantiscono che la branch `use_date_concrete` non sia mai
raggiunta con valori `None`. Se un refactoring introduce un path dove
`use_date_concrete=True` ma uno dei valori è None, con `assert` disabilitati
il codice solleva un `AttributeError` opaco invece di un errore leggibile.

**Fix** (esempio per `riposo_settimanale.py:271-273`):
```python
# PRIMA:
assert data_inizio_programma is not None  # type narrow
assert data_fine_programma is not None
assert festivita is not None

# DOPO:
if data_inizio_programma is None or data_fine_programma is None or festivita is None:
    raise ValueError(
        "_conta_giorni_solari_per_riposo: use_date_concrete=True "
        "richiede data_inizio/fine_programma e festivita non-None"
    )
```

**Fix** per `builder.py:210` (invariante post-filtro):
```python
# PRIMA:
assert primo.ora_inizio is not None and ultimo.ora_fine is not None

# DOPO:
if primo.ora_inizio is None or ultimo.ora_fine is None:
    return None  # già filtrato da `blocchi_validi`, non dovrebbe accadere
```

---

### C-06 — Normativa §4.4 violata: il builder genera blocchi PK con durata < 40 min senza warning

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:258-270`

```python
gap = _diff(prec.ora_fine, b.ora_inizio)
if gap > 0:
    drafts.append(
        _BloccoPdcDraft(seq=seq, tipo_evento="PK", ..., durata_min=gap, ...)
    )
```

La NORMATIVA-PDC §4.4 definisce:
> "PK in arrivo: **20' minimo** | PK in partenza: **20' minimo**"

Un gap totale valido per PK richiede almeno 20+20 = **40 minuti**.
Il builder genera un blocco `PK` per qualsiasi `gap > 0`, inclusi gap di
5, 10, 15, 30 minuti. Nessuna violazione viene emessa per PK < 40 min.

Esempio concreto: giro con due corse consecutive separate da 15 minuti →
il builder genera `PK 15min`. Questo non è un PK valido per normativa.

**Impatto**: i turni PdC generati possono contenere PK sotto-minimi non
segnalati. Il validatore finale non cattura questa violazione perché non
esiste un check `pk_min`.

**Fix**: aggiungere check nelle violazioni di `_build_giornata_pdc`:
```python
PK_MINIMO_MIN = 40  # 20' arrivo + 20' partenza (NORMATIVA §4.4)

for d in drafts:
    if d.tipo_evento == "PK" and d.durata_min < PK_MINIMO_MIN:
        violazioni.append(
            f"pk_sotto_minimo:{d.durata_min}<{PK_MINIMO_MIN}min"
            f"@seq{d.seq}"
        )
```

---

### C-07 — Normativa §3.3 violata: ACCp sempre 40', non implementa preriscaldo 80' (dic-feb)

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:215`

```python
ACCESSORI_MIN_STANDARD = 40
ora_inizio_accp = (primo_inizio - ACCESSORI_MIN_STANDARD) % (24 * 60)
```

La NORMATIVA-PDC §3.3:
> "Condotta con preriscaldo ● (dic-feb): **80' ACCp**, 40' ACCa"

Il builder usa sempre `ACCESSORI_MIN_STANDARD = 40` per ACCp, ignorando
il preriscaldo dicembre-febbraio. Ogni turno PdC generato per materiale
che parte in dic-feb ha ACCp sotto-stimato di 40 minuti.

Nota: §8.5 specifica che "il preriscaldo non esiste a Fiorenza" (i mezzi
sono sempre in PK). Quindi il fix si applica ai segmenti che NON partono
da Fiorenza in dic-feb.

**Questo è un finding HIGH** perché impatta direttamente la costruzione
dei turni per ~3 mesi su 12 dell'anno (dicembre, gennaio, febbraio).
Il coefficiente è visibile nel PDF con il marker ●.

**Fix**: aggiungere parametro `data_operativa` a `_build_giornata_pdc`,
calcolare `mese = data_operativa.month`, applicare 80' se `mese in (12, 1, 2)`
e la stazione di partenza non è Fiorenza.

---

### C-08 — `TurnoPdcBlocco.tipo_evento` e `TurnoPdc.stato`: string libere senza CHECK constraint DB

**Files**:
- `backend/src/colazione/models/turni_pdc.py:57` (`stato`)
- `backend/src/colazione/models/turni_pdc.py:97` (`tipo_evento`)

```python
stato: Mapped[str] = mapped_column(String(20), default="bozza")
tipo_evento: Mapped[str] = mapped_column(String(20))
```

Nessun `CHECK` constraint né `Enum` SQLAlchemy. Valori invalidi ("bozzaa",
"CONDOTTAXX") vengono persistiti silenziosamente nel DB. Con il builder che
genera `tipo_evento` programmaticamente, un typo o rename futuro corrompe i
dati senza errore visibile.

**Fix**: aggiungere `CheckConstraint` o migrare a `Enum` Python:

```python
from sqlalchemy import CheckConstraint, Enum as SAEnum

class TurnoPdcBlocco(Base):
    ...
    tipo_evento: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint(
            "tipo_evento IN ('CONDOTTA','VETTURA','REFEZ','ACCp','ACCa',"
            "'CVp','CVa','PK','PRESA','FINE','MM','VOCTAXI','SCOMP')",
            name="ck_turno_pdc_blocco_tipo_evento",
        )
    )
```

---

## IMPORTANTI

### I-01 — `giornata_base.py`: facade incompleto che ri-espone simboli `_privati`

**File**: `backend/src/colazione/domain/builder_pdc/giornata_base.py:48-71`

```python
from colazione.domain.builder_pdc.builder import (
    _BloccoPdcDraft,
    _build_giornata_pdc,
    _GiornataPdcDraft,
    ...
)

BloccoPdcDraft = _BloccoPdcDraft
GiornataPdcDraft = _GiornataPdcDraft
```

Il finding S2 di SEVERO Sprint 8.2 è stato indirizzato con un indirection
layer, non con una vera soluzione architetturale. Il problema rimane: le
definizioni di `_BloccoPdcDraft`, `_GiornataPdcDraft`, `_build_giornata_pdc`
vivono ancora in `builder.py` come simboli privati. Se qualcuno rinomina o
refactora quei simboli in `builder.py`, il facade `giornata_base.py` rompe
con `ImportError` che si manifesta solo a runtime.

La vera soluzione è **invertire la dipendenza**: spostare le definizioni in
`giornata_base.py` e fare importare `builder.py` da lì. Il facade diventa la
sorgente, non un proxy.

**Fix strutturale** (MR dedicato):
1. Spostare `_BloccoPdcDraft`, `_GiornataPdcDraft`, le costanti normative
   e `_build_giornata_pdc` in `giornata_base.py` con nomi pubblici.
2. In `builder.py`: `from colazione.domain.builder_pdc.giornata_base import ...`.
3. Rimuovere il file `giornata_base.py` come proxy; diventa la sorgente.

---

### I-02 — `registro_vetture.from_db`: operatore ignorato → cross-PdC deduplication non funziona come documentato

**File**: `backend/src/colazione/domain/builder_pdc/registro_vetture.py:233-241`

```python
registro.assegna(
    numero_treno=numero,
    operatore=None,      # ← sempre None, operatore non letto dal DB
    data_operativa=None,  # wild card S4 TODO
)
```

Il DB legge solo `numero_treno_vettura`, non l'operatore. Il match in
`is_assegnata` è strict per operatore (`None` matcha solo `None`). Quindi:

1. Il resolver cerca vettura `("2425", "TN")`.
2. Il registro ha `("2425", None)` (da DB).
3. Match: chiave `("2425", "TN")` ≠ `("2425", None)` → **non trovata** → la
   vettura NON viene esclusa anche se già assegnata a un altro turno.

La deduplication cross-PdC per numero treno funziona solo se l'operatore
recuperato dalla API live coincide con `None` (mai, perché l'API restituisce
sempre l'operatore quando disponibile). In pratica: `from_db` popola il
registro con entry mai matchabili → il registro è sostanzialmente un no-op
per i turni preesistenti.

**Fix**: aggiungere `operatore_treno_vettura: Mapped[str | None]` su
`TurnoPdcBlocco` (migration), popolare durante la persistenza, leggere nel
`from_db`. Costo: 1 migration + 3-4 righe di codice.

---

### I-03 — `VOCTAXI_DURATA_DEFAULT_MIN = 30` forfettaria uniforme per tutti i depositi

**File**: `backend/src/colazione/domain/builder_pdc/vettura_resolver.py:99-103`

```python
VOCTAXI_DURATA_DEFAULT_MIN: int = 30
```

30 minuti forfettari per VOCTAXI per qualsiasi deposito. La stessa normativa
§7.2 avverte: "per depositi periferici il tempo reale può essere maggiore".
Un taxi Sondrio→deposito è ovviamente diverso da Milano P.G→deposito.
La costante hardcoded fa sì che tutti i turni con VOCTAXI abbiano la stessa
durata stimata indipendentemente dal deposito, rendendo il cap prestazione
post-VOCTAXI una stima inaffidabile per depositi periferici.

**Fix**: aggiungere `voctaxi_durata_default_min: int` su `Depot` (DB,
default 30 per backward compat). Il resolver usa `depot.voctaxi_durata_default_min`
invece della costante modulo. Un'alternativa leggera: mappa statica
`{codice_depot: durata_min}` in `vettura_resolver.py` basata su esperienza
operativa.

---

### I-04 — `riposo_intraturno.calcola_e_valida_riposi_intraturno`: side-effect non contrattuale

**File**: `backend/src/colazione/domain/builder_pdc/riposo_intraturno.py:133-196`

La funzione `calcola_e_valida_riposi_intraturno` modifica `draft.riposo_min_post`
in-place su ogni elemento di `drafts`. Il contratto apparente dalla firma
`(drafts: list) -> list[str]` è "prendo dati, ritorno violazioni" (query-like),
ma ha un side-effect che altera il parametro in input. Il docstring lo dichiara
("**Side effect**") ma la firma non lo segnala esplicitamente.

Conseguenza: chi chiama questa funzione e poi riusa `drafts` non sa che sono
stati mutati. In `deposito_first.py:596-597` la chiamata è immediamente
seguita da `valida_riposo_settimanale(drafts, ...)` che dipende da
`draft.riposo_min_post` popolato — questo funziona solo perché l'ordine di
chiamata è fisso. Un refactoring che cambia l'ordine rompe
`valida_riposo_settimanale` in modo silenzioso.

**Fix**: rinominare la funzione a `popola_e_valida_riposi_intraturno` per
segnalare il side-effect, oppure fare ritornare i drafts modificati
(`-> tuple[list[GiornataPdcDraft], list[str]]`) senza mutare l'input.

---

### I-05 — `_inserisci_blocco_rientro` muta `BloccoPdcDraft` del chiamante in-place

**File**: `backend/src/colazione/domain/builder_pdc/deposito_first.py:210-213`

```python
for i, b in enumerate(nuovi_blocchi, start=1):
    b.seq = i          # ← muta il dataclass in-place
```

`nuovi_blocchi = list(blocchi[:fine_idx]) + [blocco_rientro, nuovo_fine]`.
I primi elementi di `nuovi_blocchi` sono riferimenti agli stessi oggetti
di `draft.blocchi` (non copie). Il `b.seq = i` muta i `BloccoPdcDraft`
originali nel draft. Se il chiamante riusa il `draft` dopo questa chiamata
(improbabile ma possibile dopo refactoring), vede i `seq` alterati.

**Fix**: `replace(b, seq=i)` (dataclass `replace`) invece di mutazione
in-place, oppure `copy.copy(b)` prima della renumerazione.

---

### I-06 — `builder.py` non ha `__all__`

**File**: `backend/src/colazione/domain/builder_pdc/builder.py`

Nessuna `__all__` dichiarata. `from builder import *` importa tutti i simboli
inclusi i `_xxx` privati. Questo vanifica il contratto del facade
`giornata_base.py` che cerca di separare API pubblica da privata.

**Fix**: aggiungere `__all__` esplicito in `builder.py` con solo i simboli
destinati a consumatori esterni:
```python
__all__ = [
    "BuilderTurnoPdcResult",
    "DepositoPdcNonTrovatoError",
    "GiriEsistentiError",
    "GiroNonTrovatoError",
    "GiroVuotoError",
    "genera_turno_pdc",
    # Costanti normative pubbliche:
    "CONDOTTA_MAX_MIN",
    "PRESTAZIONE_MAX_NOTTURNO",
    "PRESTAZIONE_MAX_STANDARD",
]
```

I simboli `_xxx` restano privati e inaccessibili da `import *`.

---

### I-07 — `TurnoPdcGiornata` e `TurnoPdcBlocco` mancano di `updated_at`

**File**: `backend/src/colazione/models/turni_pdc.py:66-124`

Le tabelle `turno_pdc_giornata` e `turno_pdc_blocco` non hanno `updated_at`.
Sono tabelle che cambiano frequentemente (rigenerazione turni, modifica
manuale blocchi da endpoint API). Senza timestamp di modifica, è impossibile
fare audit delle variazioni né implementare cache invalidation HTTP basata
su Last-Modified.

**Fix**: aggiungere a entrambe le tabelle:
```python
created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), server_default=func.now()
)
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
    onupdate=func.now(),
)
```

---

### I-08 — `riposo_settimanale._emit_violazione_striscia`: closure che cattura variabili mutabili

**File**: `backend/src/colazione/domain/builder_pdc/riposo_settimanale.py:178-193`

```python
def _emit_violazione_striscia(idx_chiusura_striscia: int) -> None:
    if (
        contatore >= GIORNATE_CONSECUTIVE_MAX_SENZA_RIPOSO
        and inizio_striscia_idx is not None
    ):
```

La closure cattura `contatore` e `inizio_striscia_idx` che sono variabili
locali del loop esterno. Python gestisce correttamente le closure su
variabili locali, ma questo pattern è fragile: se la funzione fosse
mai estratta come helper di modulo o testata in isolamento, i riferimenti
alle variabili del loop sarebbero rotti. La funzione dovrebbe ricevere
esplicitamente `contatore` e `inizio_striscia_idx` come parametri.

**Fix**:
```python
def _emit_violazione_striscia(
    idx_chiusura_striscia: int,
    contatore_corrente: int,
    idx_inizio: int | None,
) -> None:
    if contatore_corrente >= ... and idx_inizio is not None:
        ...
```

---

### I-09 — `registro_vetture` wild-card `data_operativa=None` è SOVRA-RESTRITTIVO in produzione

**File**: `backend/src/colazione/domain/builder_pdc/registro_vetture.py:157-161,240`

Il docstring spiega la scelta:
> "wild-card collide con qualunque data = il resolver esclude sempre la
> vettura. Effetto pratico: nessun turno PdC futuro può usare una vettura
> già usata da un turno qualsiasi del programma."

Su un programma reale di 6-12 mesi, una vettura può tornare sul percorso
deposito ogni giorno. Con wild-card, la PRIMA assegnazione blocca quella
vettura per tutto il programma — ogni turno successivo non potrà più usarla.
In pratica: dopo il primo giro generato, il resolver non trova più vetture
valide (tutte escluse) e cade sempre su MM/VOCTAXI.

Questo non è un "conservativo sicuro" — è un bug funzionale che invalida la
logica di rientro per i giri generati in sequenza.

**L'unico fix corretto** è implementare `enumera_date_giornata` per calcolare
le date concrete dei turni nel registro. La S4 TODO non è "nice to have",
è prerequisito per il corretto funzionamento del registro cross-PdC.

---

## MINORI

### M-01 — `GIORNO_DUMMY = "feriale"` magic string non documentata

**File**: `backend/src/colazione/domain/vincoli/inviolabili.py:326`

```python
GIORNO_DUMMY = "feriale"
corse_catturate = [
    c for c in corse_list if matches_all(filtri_geografici, c, GIORNO_DUMMY)
]
```

La costante locale (nome uppercase = stile costante di modulo) serve perché
`matches_all` richiede `giorno_tipo` ma i filtri geografici non lo usano
(già rimossi via `_filtri_senza_giorno_tipo`). Il nome `GIORNO_DUMMY` non
spiega perché "feriale" e non "festivo" o `""`. Il commento sopra spiega
(riga 325-327) ma il nome è opaco.

**Fix**: rinominare `_GIORNO_TIPO_PLACEHOLDER = "feriale"` con commento:
```python
# Placeholder richiesto dalla firma di matches_all; il valore è irrilevante
# perché i filtri giorno_tipo sono già stati rimossi da filtri_geografici.
_GIORNO_TIPO_PLACEHOLDER = "feriale"
```

---

### M-02 — `Vincolo.linee_descrizione` fonde ammesse + vietate senza distinzione

**File**: `backend/src/colazione/domain/vincoli/inviolabili.py:128-133`

```python
linee = tuple(
    v.get("linee_descrizione_ammesse", [])
    + v.get("linee_descrizione_vietate", [])
)
```

Il campo `linee_descrizione` concatena senza marker le linee ammesse e le
vietate. Non c'è modo di sapere quale parte è ammessa e quale vietata.
Il campo non viene usato in nessuna logica di validazione (solo documentativo),
ma chi legge un `Vincolo` serializzato non può ricostruire l'informazione
originale.

**Fix**: sostituire con due campi distinti nel dataclass:
```python
linee_descrizione_ammesse: tuple[str, ...] = ()
linee_descrizione_vietate: tuple[str, ...] = ()
```

---

### M-03 — `varianti_calendariali.py:293` importa `Counter` inutilizzato con `noqa`

**File**: `backend/src/colazione/domain/builder_giro/varianti_calendariali.py:293`

```python
_ = Counter  # noqa: F841 — riservato per estensioni
```

`Counter` è importato ma non usato. Il `noqa` sopprime il warning ruff.
Se l'uso futuro di `Counter` fosse confermato, il commento dovrebbe essere
un TODO esplicito. Altrimenti: rimuovere l'import e la riga.

---

### M-04 — `GanttUnificatoRoute.tsx` (~470 righe): nessun test frontend

**File**: `frontend/src/routes/pianificatore-giro/GanttUnificatoRoute.tsx`

Il componente più complesso del frontend (Sprint 8.4 G1, ~470 righe) non
ha test corrispondente `GanttUnificatoRoute.test.tsx`. Gli altri route
complessi hanno test:
- `ProgrammaDettaglioRoute.test.tsx` ✅
- `TurnoDettaglioRoute.test.tsx` ✅
- `TurnoValidazioni.test.tsx` ✅

La feature include logica di selezione blocchi, dialog di inserimento manuale
con warnings operativi, e interazione con l'endpoint
`POST /api/giri/{id}/inserisci-corsa-manuale`. È l'area più ad alto rischio
per regressioni silenziose.

---

### M-05 — `frontend/src/lib/stazioni-acronimi.ts`: copia locale non sincronizzata col DB

**File**: `frontend/src/lib/stazioni-acronimi.ts`

Il file contiene una mappa di acronimi stazioni (es. `"S01066": "MI.CAD"`)
definita localmente nel frontend. La sorgente canonica degli acronimi è
`stazione.nomi_alternativi` nel DB (MODELLO-DATI.md §3). Se l'anagrafica DB
cambia (aggiunta stazione, correzione acronimo), il file frontend non si
aggiorna automaticamente.

**Fix a lungo termine**: esporre `GET /api/stazioni/acronimi` (o includere
gli acronimi nella risposta `/api/stazioni/`) e caricare dal backend.
**Fix a breve termine**: almeno un test che confronta il file frontend con
i dati del seed DB.

---

### M-06 — Alembic: gap nella numerazione sequenziale (0021, 0027, 0038, 0041, 0042, 0044, 0047)

**Directory**: `backend/alembic/versions/`

I numeri di migration saltano 0021, 0027, 0038, 0041, 0042, 0044, 0047.
Il chain Alembic è comunque valido (verificato da `check_alembic_revisions.py`
in CI). Ma i gap rendono la storia illeggibile: chi legge la lista dei file
non sa se le migration mancanti sono state eliminate intenzionalmente o si
tratta di errori di archivio.

**Fix**: aggiungere un file `docs/alembic-gaps.md` che documenta quali
numeri sono stati saltati e perché (migration abortita, branch scartato,
ecc.). Non urgente ma evita confusione futura.

---

### M-07 — Alcune migration mancano di `downgrade()` implementato

**File**: Verificare `backend/alembic/versions/0046_mr_pd_fix_severo_3b_numero_treno_vettura.py`

Le ultime migration (0043, 0045, 0046) aggiungono colonne critiche
(`deposito_pdc_id NOT NULL`, nuovi tipo_evento, `numero_treno_vettura`).
Se il `downgrade()` è `pass` o stub, un rollback di emergenza in produzione
è impossibile. Raccomandazione: verificare che le migration dal 0043 in poi
abbiano `downgrade()` funzionante o dichiarino esplicitamente
`# irreversibile: DROP COLUMN NOT NULL` con motivazione.

---

## RIEPILOGO

| # | ID | Gravità | File:riga | Titolo |
|---|-----|---------|-----------|--------|
| 1 | C-01 | CRITICO | `models/turni_pdc.py:59` | `updated_at` non si aggiorna |
| 2 | C-02 | CRITICO | `deposito_first.py:465` | Anti-rigenerazione O(N) RAM |
| 3 | C-03 | CRITICO | `registro_vetture.py:188` | 4 subquery senza indice JSONB |
| 4 | C-04 | CRITICO | `test_riposo_intraturno.py:7` | 78 test falliscono in collection |
| 5 | C-05 | CRITICO | `builder.py:210`, `riposo_settimanale.py:271` | `assert` disabilitabili con `-O` |
| 6 | C-06 | CRITICO | `builder.py:258` | PK < 40 min senza warning (§4.4) |
| 7 | C-07 | CRITICO | `builder.py:215` | ACCp sempre 40', preriscaldo 80' dic-feb ignorato (§3.3) |
| 8 | C-08 | CRITICO | `models/turni_pdc.py:57,97` | `stato`/`tipo_evento` senza CHECK constraint |
| 9 | I-01 | IMPORTANTE | `giornata_base.py:48` | Facade incompleto, struttura invertita |
| 10 | I-02 | IMPORTANTE | `registro_vetture.py:233` | Operatore ignorato → deduplication no-op |
| 11 | I-03 | IMPORTANTE | `vettura_resolver.py:103` | VOCTAXI 30' uniforme, depositi periferici errati |
| 12 | I-04 | IMPORTANTE | `riposo_intraturno.py:133` | Side-effect non contrattuale |
| 13 | I-05 | IMPORTANTE | `deposito_first.py:210` | Mutazione in-place draft.blocchi |
| 14 | I-06 | IMPORTANTE | `builder.py` (riga 1) | Nessun `__all__`, simboli privati esposti |
| 15 | I-07 | IMPORTANTE | `models/turni_pdc.py:66` | `TurnoPdcGiornata/Blocco` senza `updated_at` |
| 16 | I-08 | IMPORTANTE | `riposo_settimanale.py:178` | Closure cattura variabili mutabili |
| 17 | I-09 | IMPORTANTE | `registro_vetture.py:157` | Wild-card data sovra-restrittiva in produzione |
| 18 | M-01 | MINORE | `inviolabili.py:326` | `GIORNO_DUMMY` magic string opaca |
| 19 | M-02 | MINORE | `inviolabili.py:128` | `linee_descrizione` fonde ammesse+vietate |
| 20 | M-03 | MINORE | `varianti_calendariali.py:293` | `Counter` inutilizzato con `noqa` |
| 21 | M-04 | MINORE | `GanttUnificatoRoute.tsx` | Nessun test (~470 righe) |
| 22 | M-05 | MINORE | `stazioni-acronimi.ts` | Copia locale non sincronizzata col DB |
| 23 | M-06 | MINORE | `alembic/versions/` | Gap numerazione migration |
| 24 | M-07 | MINORE | `alembic/versions/0043+` | `downgrade()` potenzialmente stub |

**Totale: 8 CRITICI · 9 IMPORTANTI · 7 MINORI = 24 finding**

---

## Note metodologiche

- I finding C-06 e C-07 sono **violazioni normative dirette**
  (NORMATIVA-PDC §3.3 e §4.4): il codice fa diversamente dalla normativa.
  Per regola CLAUDE.md §5, "se il codice fa diversamente, è il codice a
  essere sbagliato."
- I finding C-04, I-01, I-02, I-09 sono correlati: derivano tutti dal
  debito tecnico del facade `giornata_base.py` non completo e del registro
  vetture MVP con wild-card. Risolverli insieme in un unico MR è più
  efficiente che farlo separatamente.
- C-03 e I-09 insieme delineano un problema architetturale del
  `generation_metadata_json` come meccanismo di FK: va risolto a livello
  di schema (colonna `giro_materiale_id` esplicita su `TurnoPdc`).
- Nessun finding riguarda la logica di calcolo del riposo settimanale
  (§11.4) o intraturno (§11.5) — quella è implementata correttamente
  inclusa la scelta cautelativa 16h decisa dall'utente (entry 286).
