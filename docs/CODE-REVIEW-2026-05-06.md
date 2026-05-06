# CODE REVIEW — COLAZIONE Sprint 8.0 (2026-05-06)

> Revisione completa del repo dopo Sprint 8.0 MR 5.bis (entry 175).
> Scope: `backend/`, `frontend/`, `data/`, `tests/`, `scripts/`.
> Condotta su: `f26ec2c` (branch `claude/zen-babbage-WyC3d`).
>
> Riferimenti di dominio usati: `docs/NORMATIVA-PDC.md`,
> `docs/MODELLO-DATI.md`, `TN-UPDATE.md` (ultime 5 entry).
>
> Per ogni finding: `file:riga` preciso, impatto, fix concreto.

---

## Sommario

| Categoria | N | Descrizione breve |
|-----------|---|-------------------|
| CRITICO   | 4 | Violazioni normativa PdC / bug latenti bloccanti |
| IMPORTANTE | 9 | Qualità, correttezza, manutenibilità |
| MINORE    | 5 | Style, coerenza, micro-debiti |
| **Totale** | **18** | |

---

## CRITICI

### C1 — `ACCESSORI_MIN_STANDARD` sempre 40': preriscaldo invernale §3.3 mai applicato

**File:** `backend/src/colazione/domain/builder_pdc/builder.py:57`

**Normativa §3.3:**

> ACCp standard = **40 minuti**. In dicembre, gennaio, febbraio
> (preriscaldo ●): **80 minuti** per i materiali che richiedono
> preriscaldo.

```python
# builder.py:57
ACCESSORI_MIN_STANDARD = 40  # ← usato SEMPRE, senza eccezione invernale
```

Le righe 195-196, 224, 276 usano sempre questa costante:

```python
ora_inizio_accp = (primo_inizio - ACCESSORI_MIN_STANDARD) % (24 * 60)
ora_presa       = (ora_inizio_accp - PRESA_SERVIZIO_MIN) % (24 * 60)
```

**Impatto:** Tutti i turni PdC costruiti in dicembre/gennaio/febbraio
hanno l'ACCp di 40' invece di 80'. Il macchinista arriva 40' prima
del necessario, la prestazione dichiarata è sottostimata di 40'. In
estate il builder è corretto; in inverno produce turni non conformi
alla normativa contrattuale.

**Fix:**

```python
# Aggiungere costante inverno
ACCESSORI_MIN_INVERNO = 80
_MESI_PRERISCALDO = frozenset({12, 1, 2})

# Aggiungere mese: int a _build_giornata_pdc (già riceve valido_da, passare .month)
def _build_giornata_pdc(
    blocchi_giro: list[GiroBlocco],
    mese: int,            # ← nuovo parametro
    stazioni_cv: frozenset[str],
    ...
) -> DraftGiornata:
    acc_min = ACCESSORI_MIN_INVERNO if mese in _MESI_PRERISCALDO else ACCESSORI_MIN_STANDARD
    ora_inizio_accp = (primo_inizio - acc_min) % (24 * 60)
    ...
```

Il sito del builder (riga ~920) che chiama `_build_giornata_pdc` ha
già `valido_da: date` nel contesto; passare `valido_da.month` è
sufficiente. Nessuna modifica al DB richiesta.

**Test assente:** `tests/test_builder_pdc_eta.py` non ha alcun
test che verifica ACCp in mese invernale. Aggiungere caso con
`date(2025, 12, 15)`.

---

### C2 — Riposo intraturno §11.5 cieco alle assegnazioni DB pre-esistenti

**File:** `backend/src/colazione/domain/normativa/assegnazione_persone.py:311`

```python
@dataclass
class _StatoAssegna:
    assegnate_per_persona_data: dict[tuple[int, date], bool] = field(default_factory=dict)
    """include esistenti DB + nuove."""

    storia_per_persona: dict[int, list[GiornataDaAssegnare]] = field(default_factory=dict)
    """SOLO giornate appena assegnate dall'algoritmo corrente."""    # ← BUG
```

La `storia_per_persona` viene usata al check riposo intraturno
(righe 493-499):

```python
storia = stato.storia_per_persona.get(persona.id)
if storia:
    ultima = storia[-1]
    gap_h = (_datetime_inizio(g) - _datetime_fine(ultima)).total_seconds() / 3600
    if gap_h < _riposo_richiesto_h(ultima):
        n_riposo += 1; continue
```

Se la persona aveva già un turno terminalizzato alle 23:00 nel giorno
precedente (persistito in DB da un run precedente), la
`storia_per_persona` è vuota → il check non si attiva → la persona può
ricevere un turno che inizia alle 06:00 il giorno stesso, con riposo
di 7h invece degli 11h richiesti da §11.5.

**Nota:** `assegnate_per_persona_data` è seeded correttamente con
le assegnazioni DB (endpoint righe ~968-978), ma
`storia_per_persona` no.

**Impatto:** Ogni run di auto-assegna su una finestra che si
sovrappone a run precedenti può produrre violazioni HARD §11.5.
Violazione silenziosa: nessun warning né errore, il PdC è
semplicemente assegnato con riposo insufficiente.

**Fix (endpoint `auto_assegna_persone_endpoint`):**

```python
# Dopo il caricamento assegnazioni_esistenti, aggiungere:
# Caricare le ultime giornate assegnate fuori finestra (per riposo retroattivo)
storia_pregressa_q = await session.execute(
    select(AssegnazioneGiornata)
    .where(
        AssegnazioneGiornata.persona_id.in_(persona_ids),
        AssegnazioneGiornata.data >= data_da - timedelta(days=2),
        AssegnazioneGiornata.data < data_da,   # fuori finestra corrente
        AssegnazioneGiornata.stato != "annullato",
    )
    .order_by(AssegnazioneGiornata.data)
)
# Convertire in GiornataDaAssegnare stub e popolare storia_per_persona nello stato iniziale
```

La funzione `auto_assegna` deve accettare un parametro
`storia_pregressa: dict[int, list[GiornataDaAssegnare]]` e usarlo
per inizializzare `_StatoAssegna.storia_per_persona` prima di
partire. La conversione richiede un `GiornataDaAssegnare` stub con
`inizio_prestazione`, `fine_prestazione`, `is_notturno` ricavati
dai dati `TurnoPdcGiornata` collegati.

---

### C3 — Cap FR §10.6 cieco alle FR DB pre-esistenti

**File:** `backend/src/colazione/domain/normativa/assegnazione_persone.py:315`

```python
fr_per_persona: dict[int, list[date]] = field(default_factory=dict)
"""SOLO FR generate dall'algoritmo corrente."""   # ← BUG
```

Il check soft §10.6 a righe 347-376:

```python
fr_dates = stato.fr_per_persona.get(persona_id, [])
# finestra_28 = [d for d in fr_dates if (g.data - d).days < 28]
```

Se un PdC aveva già 3 FR nei 28 giorni precedenti (da run
precedenti), `fr_per_persona` è vuota → nessun warning viene
emesso → la persona riceve una 4ª FR.

**Impatto:** Il cap FR §10.6 (`max 3/28gg`, `max 1/settimana`) è
un vincolo contrattuale. Violarlo silenziosamente può causare
contestazioni sindacali. L'impatto è SOFT (warning, non hard
block), ma il warning è lo strumento di compliance; non emettendolo
si perde l'unico presidio.

**Fix:** Stesso pattern di C2. Nel endpoint, caricare le
`AssegnazioneGiornata` con `is_fr=True` nella finestra
`[data_da - 28 days, data_da[` per ogni persona candidata e
popolare `fr_per_persona` nello stato iniziale prima di passarlo
ad `auto_assegna`. Richiedrà un join con `TurnoPdcGiornata` per
recuperare il flag `is_fr`.

---

### C4 — `is_notturno` troppo largo: turni 22:01-23:59 ricevono 16h di riposo (§11.5 richiede 11h)

**File 1:** `backend/src/colazione/domain/builder_pdc/builder.py:331`

```python
is_notturno = (
    ora_presa < 5 * 60           # presa 00:00-04:59 ✓
    or ora_fine_servizio > 22 * 60  # fine_servizio > 22:00 ← TROPPO LARGO
    or ora_fine_servizio < ora_presa  # cross-mezzanotte ✓
)
```

La seconda condizione cattura turni con fine servizio 22:01–23:59
che, per normativa §11.5, richiedono solo 11h di riposo
(categoria standard). Solo i turni con fine 00:01–05:00 richiedono
16h; fine 00:01–01:00 richiedono 14h.

**File 2:** `backend/src/colazione/domain/normativa/assegnazione_persone.py:281`

```python
def _riposo_richiesto_h(prev: GiornataDaAssegnare) -> int:
    if prev.is_notturno:          # ← usa il flag troppo largo
        return RIPOSO_INTRATURNO_MIN_NOTTURNA_H  # 16h
    fine_t = _datetime_fine(prev).time()
    if time(0, 1) <= fine_t <= time(1, 0):
        return RIPOSO_INTRATURNO_MIN_NOTTE_TARDA_H  # 14h
    return RIPOSO_INTRATURNO_MIN_STANDARD_H  # 11h
```

Un PdC che finisce servizio alle 22:30 avrà `is_notturno=True` →
`_riposo_richiesto_h` restituisce 16h → l'algoritmo lo esclude
dal turno delle 09:00 del giorno dopo (gap 10.5h < 16h) anche se
§11.5 consente riposo 11h. Effetto: il PdC viene inutilmente
marcato come non disponibile, aumentando il numero di mancanze.

**Impatto:** Over-blocking: riduce il pool di persone assegnabili
per la mattina successiva dopo un turno serale (22:00-23:59).
Produce mancanze false che la pianificazione umana poi deve risolvere
con override manuale. Non è una violazione contrattuale (è
conservativo), ma è operativamente inefficiente e clinicamente
sbagliato rispetto alla normativa.

**Fix in `_riposo_richiesto_h`:**

```python
def _riposo_richiesto_h(prev: GiornataDaAssegnare) -> int:
    """§11.5: riposo richiesto basato sulla fine_servizio EFFETTIVA."""
    fine_t = _datetime_fine(prev).time()
    # 16h solo se fine 00:01–05:00
    if time(0, 1) <= fine_t <= time(5, 0):
        return RIPOSO_INTRATURNO_MIN_NOTTURNA_H
    # 14h se fine 00:01–01:00 (sottoinsieme del precedente già coperto)
    # Nota: §11.5 "fine 00:01–01:00" → 14h; "fine 00:01–05:00" → 16h.
    # Il blocco sopra copre entrambi: 00:01-01:00 ⊂ 00:01-05:00.
    # Separare se si vuole granularità 14h vs 16h:
    if time(0, 1) <= fine_t <= time(1, 0):
        return RIPOSO_INTRATURNO_MIN_NOTTE_TARDA_H
    return RIPOSO_INTRATURNO_MIN_STANDARD_H
```

Non usare il flag `is_notturno` in `_riposo_richiesto_h`: il flag
esiste a scopi di display/calcolo prestazione, ha semantica
diversa dal riposo intraturno.

---

## IMPORTANTI

### I1 — Divergenza model-migration: UniqueConstraint e CHECK assenti nei modelli SQLAlchemy

**File 1:** `backend/src/colazione/models/turni_pdc.py:32–61`
**File 2:** `backend/src/colazione/models/personale.py:28–50`

La migration `0001_initial_schema.py` crea questi vincoli nel DB:

```sql
-- turno_pdc
CONSTRAINT turno_pdc_stato_check CHECK (stato IN ('bozza','definitivo','archiviato'))
UNIQUE(azienda_id, codice, valido_da)

-- turno_pdc_giornata
UNIQUE(turno_pdc_id, numero_giornata, variante_calendario)

-- persona
UNIQUE(azienda_id, codice_dipendente)
```

Nessuno di questi è dichiarato nei corrispondenti modelli
SQLAlchemy. I modelli dichiarano solo:

```python
# TurnoPdc.__table_args__
Index("ix_turno_pdc_azienda_deposito", "azienda_id", "deposito_pdc_id")
```

**Impatto:**

1. `alembic revision --autogenerate` emetterà `op.create_unique_constraint()`
   e `op.create_check_constraint()` su ogni invocazione, generando
   migration spurie che nel DB già hanno il vincolo → errore
   `DuplicateObject` alla prima `alembic upgrade head` successiva.
2. I developer che leggono il modello credono che `(azienda_id, codice,
   valido_da)` non sia unique, potendo scrivere codice che lo assume.
3. Il tipo `stato: str` non riflette l'enum DB, quindi nessun aiuto
   dal type checker per valori non validi.

**Fix (`turni_pdc.py`):**

```python
from sqlalchemy import CheckConstraint, UniqueConstraint

class TurnoPdc(Base):
    ...
    __table_args__ = (
        UniqueConstraint("azienda_id", "codice", "valido_da",
                         name="turno_pdc_azienda_codice_data_uq"),
        CheckConstraint(
            "stato IN ('bozza','definitivo','archiviato')",
            name="turno_pdc_stato_check",
        ),
        Index("ix_turno_pdc_azienda_deposito", "azienda_id", "deposito_pdc_id"),
    )

class TurnoPdcGiornata(Base):
    ...
    __table_args__ = (
        UniqueConstraint("turno_pdc_id", "numero_giornata", "variante_calendario",
                         name="turno_pdc_giornata_uq"),
        Index("ix_turno_pdc_giornata_turno", "turno_pdc_id"),
    )
```

**Fix (`personale.py`):**

```python
class Persona(Base):
    ...
    __table_args__ = (
        UniqueConstraint("azienda_id", "codice_dipendente",
                         name="persona_azienda_codice_uq"),
        Index("ix_persona_codice_dipendente", "codice_dipendente"),
    )
```

---

### I2 — Modelli non dichiarano gli indici FK: divergenza autogenerate

**File:** `backend/src/colazione/models/turni_pdc.py:64,87`
**File:** `backend/src/colazione/models/personale.py:52,72`

Gli indici esistono nel DB (migration 0001, righe 751-754, 774-779):

```sql
CREATE INDEX idx_giornata_pdc_turno ON turno_pdc_giornata(turno_pdc_id);
CREATE INDEX idx_blocco_pdc_giornata ON turno_pdc_blocco(turno_pdc_giornata_id);
CREATE INDEX idx_assegnazione_persona ON assegnazione_giornata(persona_id);
CREATE INDEX idx_assegnazione_data ON assegnazione_giornata(data);
CREATE INDEX idx_assegnazione_giornata_pdc ON assegnazione_giornata(turno_pdc_giornata_id);
CREATE INDEX idx_indisponibilita_persona ON indisponibilita_persona(persona_id);
```

Ma nessuno dei quattro modelli dichiara `__table_args__` con gli
`Index` corrispondenti. **`AssegnazioneGiornata` non ha nemmeno un
`__table_args__` vuoto.**

**Impatto:** Come per I1, `alembic --autogenerate` produrrà
migration spurie tentando di creare indici già esistenti. Oltre
a ciò, la mancanza di `__table_args__` su `AssegnazioneGiornata`
e `IndisponibilitaPersona` rende invisibile agli sviluppatori che
leggono il codice che `(persona_id, data)` è indicizzato — informazione
critica per capire la performance dell'auto-assegna.

**Fix:** Aggiungere `__table_args__` con `Index(...)` che
specchio gli indici effettivi del DB. Costo stimato: 20 righe,
nessuna migration necessaria (indici già esistono).

---

### I3 — Full table scan su `turno_pdc` per anti-rigenerazione

**File:** `backend/src/colazione/domain/builder_pdc/builder.py:712–720`

```python
existing = list(
    (
        await session.execute(
            select(TurnoPdc).where(TurnoPdc.azienda_id == azienda_id)
        )
    ).scalars()
)
```

Carica **tutti** i `TurnoPdc` dell'azienda in memoria per trovare
quelli relativi a `giro_id`. Con Trenord (centinaia di giri, cicli
pluriennali) questo può essere un carico rilevante.

La discriminazione avviene dopo, in `_matches_giro_e_deposito`:

```python
def _matches_giro_e_deposito(t: TurnoPdc) -> bool:
    if (t.generation_metadata_json or {}).get("giro_materiale_id") != giro_id:
        return False
    ...
```

**Fix:** Filtrare nel DB via JSONB:

```python
from sqlalchemy import cast, Integer

existing = list(
    (
        await session.execute(
            select(TurnoPdc).where(
                TurnoPdc.azienda_id == azienda_id,
                cast(
                    TurnoPdc.generation_metadata_json["giro_materiale_id"].astext,
                    Integer,
                ) == giro_id,
            )
        )
    ).scalars()
)
```

L'indice GIN su `generation_metadata_json` esiste già
(`idx_corsa_composizione_corsa` non copre questo campo, ma
un `CREATE INDEX ON turno_pdc USING gin(generation_metadata_json)`
in una nuova migration renderebbe il filtro molto efficiente).
Come minimo, il cast rimuove il Python-side filtering.

---

### I4 — `datetime.utcnow()` deprecato in Python 3.12

**File:** `backend/src/colazione/domain/builder_pdc/builder.py:997`

```python
"generato_at": datetime.utcnow().isoformat(),
```

`datetime.utcnow()` è deprecato da Python 3.12 (`DeprecationWarning`)
e restituisce un datetime naive in UTC, ambiguo se deserializzato
in un contesto timezone-aware.

**Fix:**

```python
from datetime import datetime, timezone
"generato_at": datetime.now(tz=timezone.utc).isoformat(),
```

---

### I5 — `assegna_manuale` non aggiorna `copertura_pct`

**File:** `backend/src/colazione/api/programmi.py:1104–1238`

L'endpoint `assegna_manuale` crea un `AssegnazioneGiornata` ma
non aggiorna `programma_materiale.copertura_pct`. Questo campo
viene aggiornato solo da `auto_assegna` (riga 1059):

```python
p.copertura_pct = risultato.delta_copertura_pct
```

**Scenario problematico:** il pianificatore fa 3 run di
`auto_assegna` (copertura 87%), poi risolve 10 mancanze con
`assegna_manuale` (copertura reale ~95%), poi clicca
"Conferma Personale". Il gate a riga 735:

```python
if p.copertura_pct < soglia:   # still 87%
    raise HTTPException(409, ...)
```

blocca la conferma anche se la copertura reale è ≥ soglia.
Il pianificatore deve ri-eseguire `auto_assegna` (che è idempotente,
ma può sovrascrivere gli override manuali) oppure è bloccato.

**Fix:** Al termine di `assegna_manuale`, ricalcolare
`copertura_pct` con una query aggregata:

```python
totale = await session.scalar(count_giornate_query)
assegnate = await session.scalar(count_assegnate_query)
p.copertura_pct = (assegnate / totale * 100) if totale else 100.0
await session.commit()
```

oppure, più semplice, aggiungere un parametro alla `auto_assegna`
funzione per eseguire solo il ricalcolo senza assegnare (dry
compute). Il debito è registrato in TN-UPDATE entry 173 come
"scope rinviato" ma costituisce un blocco concreto al flusso
normale.

---

### I6 — Fallback silente a `data_a = valido_da` quando `valido_a` è NULL

**File:** `backend/src/colazione/api/programmi.py:869`

```python
data_da = payload.data_da or p.valido_da
data_a = payload.data_a or p.valido_a or p.valido_da   # ← fallback su valido_da
```

Se `p.valido_a` è `None` e il caller non passa `data_a`, la
finestra di calcolo collassa a `[valido_da, valido_da]` — una
singola giornata. L'errore `data_da > data_a` non scatta perché
`valido_da == valido_da`, e il run procede silenziosamente
generando un piano su un solo giorno.

**Impatto:** Un programma senza `valido_a` (edge case possibile
se il programma è "aperto") con chiamata senza `data_a` esplicito
produce un risultato vuoto/minimale invece di un errore 400.
Il pianificatore non sa perché il piano è vuoto.

**Fix:**

```python
if p.valido_a is None and payload.data_a is None:
    raise HTTPException(
        status_code=400,
        detail=(
            "programma senza data_fine: specificare data_a nel payload "
            "oppure impostare valido_a sul programma"
        ),
    )
data_a = payload.data_a or p.valido_a
```

---

### I7 — `SOGLIA_COPERTURA_PCT = 95` hardcoded nel frontend, non sincronizzato con il backend

**File 1:** `frontend/src/routes/gestione-personale/AssegnaPersoneRoute.tsx:70`
**File 2:** `backend/src/colazione/api/programmi.py:145`

```typescript
// frontend
const SOGLIA_COPERTURA_PCT = 95;
```

```python
# backend
def _resolve_soglia_copertura_pct() -> float:
    # legge AUTO_ASSEGNA_SOGLIA_COPERTURA_PCT env var, default 95.0
```

Se l'operatore configura `AUTO_ASSEGNA_SOGLIA_COPERTURA_PCT=90` nel
backend, il frontend continua a mostrare "soglia 95%" e a bloccare
visivamente il pulsante "Conferma" sotto 95%, mentre il backend
accetterebbe una copertura al 90%. L'utente è confuso.

**Fix:** Esporre la soglia dal backend via un endpoint (es.
`GET /api/programmi/config` o come campo nel response body di
`auto_assegna`) e leggere il valore dal backend invece di hardcodarla.
In alternativa: documentare esplicitamente che la soglia UI è fissa
a 95 e rimuovere la env var da backend (o viceversa). La
incoerenza attuale è il problema, non il valore in sé.

---

### I8 — Cap riposo settimanale §11.4: warning description usa costante errata

**File:** `backend/src/colazione/domain/normativa/assegnazione_persone.py:392`

```python
out.append(
    WarningSoft(
        ...
        tipo=TipoWarningSoft.RIPOSO_SETTIMANALE_VIOLATO,
        descrizione=(
            f"{in_finestra} assegnazioni in 7gg ..."
            f"riposo settimanale §11.4 ≥{RIPOSO_INTRATURNO_MIN_NOTTURNA_H}"  # ← 16h
            "h non rispettabile"
        ),
    )
)
```

`RIPOSO_INTRATURNO_MIN_NOTTURNA_H = 16` è il riposo intraturno
notturno (§11.5), non il riposo settimanale (§11.4 = 62h in 7
giorni). La stringa descrive una violazione §11.4 ma cita "≥16h"
invece di "≥62h".

**Impatto:** Il warning mostrato al pianificatore è fuorviante.
In un sistema di compliance, una stringa errata crea precedenti
sbagliati durante le verifiche sindacali/ispettive.

**Fix:**

```python
RIPOSO_SETTIMANALE_MIN_H = 62  # §11.4

# nella descrizione:
f"riposo settimanale §11.4 ≥{RIPOSO_SETTIMANALE_MIN_H}h non rispettabile"
```

---

### I9 — `_variante_matcha_tipo_giorno`: fallback liberale produce sovra-assegnazione silenziosa

**File:** `backend/src/colazione/api/programmi.py:816`

```python
# Fallback liberale: variante non riconosciuta → match
return True
```

Una `variante_calendario` non riconosciuta (es. valore futuro
dal PdE come `"LXG"` o `"MXG"`) matcha qualsiasi tipo di giorno.
Il turno finisce assegnato 7 giorni su 7 invece che solo nei giorni
previsti.

**Impatto:** Le giornate "fantasma" non compaiono nella
visualizzazione calendario del PdC (filtraggio UI), ma entrano nel
conteggio `copertura_pct` e possono attivare il warning
`RIPOSO_SETTIMANALE_VIOLATO` su persone che non dovrebbero lavorare
quei giorni. Il bug è mascherato dall'euristica soft.

**Fix:** Loggare un warning (non sollevare eccezione, per
retrocompatibilità) e restituire `False` per varianti
non riconosciute, oppure mappare `"LXG"` come feriale e `"MXG"`
come feriale in base alla grammatica PdE Trenord:

```python
# Invece di return True:
import logging
_log = logging.getLogger(__name__)
_log.warning("variante_calendario non riconosciuta: %r, trattata come GG", variante)
return True  # conservare comportamento attuale ma renderlo visibile
```

Nel breve: almeno loggare. Nel medio termine, fallback su `False`
dopo un periodo di osservazione.

---

## MINORI

### M1 — `GiriEsistentiError` definita in fondo al file invece che con le altre eccezioni

**File:** `backend/src/colazione/domain/builder_pdc/builder.py:1245`

```python
# Riga 1245 — fondo del file
class GiriEsistentiError(Exception):
    ...
```

Le altre eccezioni del dominio (`GiroNonTrovatoError`,
`GiroVuotoError`) sono definite nelle prime righe del modulo.
`GiriEsistentiError` è finita in fondo dopo essere stata aggiunta
in sprint successivo.

**Fix:** Spostare la classe alle righe ~40-50, insieme alle altre
eccezioni. Nessun impatto funzionale.

---

### M2 — `PERSISTER_VERSION` stringa hardcoded senza aggancio a versioning

**File:** `backend/src/colazione/domain/builder_giro/persister.py:62`

```python
PERSISTER_VERSION = "7.7.5"
```

La versione è scritta a mano e non ha meccanismo di aggiornamento
automatico. È già stale (siamo in Sprint 8.0).

**Fix a costo zero:** rimuovere la versione e usare la data del
record `generation_metadata_json["generato_at"]` come identificatore
temporale sufficiente. Se si vuole tenere la versione, agganciarla
a `pyproject.toml` via `importlib.metadata.version("colazione")`.

---

### M3 — `Persona` manca di `__table_args__` con mirror degli indici DB

**File:** `backend/src/colazione/models/personale.py:28`

La migration 0001 crea `idx_persona_codice ON persona(codice_dipendente)`
e `UNIQUE(azienda_id, codice_dipendente)`. Il modello `Persona`
non ha `__table_args__`. Già parzialmente coperto da I1 per la
UniqueConstraint, questo punto riguarda specificamente la mancanza
del `Index` da mirror (cosmetico ma necessario per consistenza
autogenerate).

---

### M4 — `builder_pdc/builder.py`: parametro `valido_da` non usato per stagionalità

**File:** `backend/src/colazione/domain/builder_pdc/builder.py:591`

La funzione `build_turno_pdc_da_giro` riceve `valido_da: date | None`
(riga ~591), ma questo parametro non viene propagato a
`_build_giornata_pdc`. La stagionalità (preriscaldo invernale C1)
non può essere implementata senza questa propagazione, già documentata
in C1. Il punto qui è che il parametro esiste ma è parzialmente
inutilizzato come vettore di contesto stagionale.

---

### M5 — Nessun test per preriscaldo invernale e per riposo intraturno cross-run

**File:** `backend/tests/test_builder_pdc_eta.py`
**File:** `backend/tests/test_domain_assegnazione_persone.py`

`test_builder_pdc_eta.py` non contiene alcun test che verifichi
ACCp = 80' in mese invernale. `test_domain_assegnazione_persone.py`
non contiene alcun test con `storia_pregressa` pre-seeded, ovvero
il scenario di C2 (riposo intraturno cross-run) non è coperto.

Questi due test-gap lasciano i critici C1 e C2 senza rete di
regressione: un futuro refactor potrebbe rimuovere la fix di C1
senza che alcun test fallisca.

**Fix:** Aggiungere almeno:
- `test_builder_pdc_eta.py`: un caso con giornata in dicembre,
  verificare che `ACCp.durata_min == 80`.
- `test_domain_assegnazione_persone.py`: un caso dove una persona
  ha già una giornata serale (22:30 fine) e `storia_pregressa`
  lo riflette, verificare che la persona non venga assegnata a
  un turno mattutino con gap < 11h.

---

## Note architetturali

### Qualità generale

Il dominio è ben separato dall'API: `assegnazione_persone.py`,
`vincoli/inviolabili.py`, `pipeline.py` e `calendario.py` sono
funzioni pure senza dipendenze DB, facilmente testabili. Questa
scelta architetturale è corretta e va preservata.

### Debiti documentati in TN-UPDATE

Tre scope rinviati documentati in TN-UPDATE (entry 173-175) ma non
ancora risolti:

1. **UI variazioni PdE**: endpoint MR 5.bis esiste, il frontend non
   lo espone ancora (entry 175).
2. **Idempotenza fine-grained orari**: variazioni `VARIAZIONE_ORARIO`
   su corse già presenti non differenziano su `orario_partenza_effettivo`
   (entry 175).
3. **`assegna_manuale` non aggiorna `copertura_pct`**: già catalogato
   come I5 sopra — è il più bloccante dei tre.

---

*Autore: code review condotta su commit `f26ec2c` in data 2026-05-06.*
