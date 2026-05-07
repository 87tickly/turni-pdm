# Code Review COLAZIONE — 2026-05-07

> Reviewer: Claude Code (senior engineering review, sprint 7.9 + sprint 8.0 finale)
> Scope: intero repo — backend/src/, backend/tests/, frontend/src/, models, migrations, auth, domain
> Periodo coperto: dall'entry più recente di TN-UPDATE (entry 209) a ritroso
> Documenti letti: CLAUDE.md, TN-UPDATE.md (prime 5 entry), METODO-DI-LAVORO.md, NORMATIVA-PDC.md, MODELLO-DATI.md
> Nessuna modifica al codice: solo osservazione e classificazione

---

## Indice

- [CRITICI (5)](#critici)
- [IMPORTANTI (10)](#importanti)
- [MINORI (8)](#minori)
- [Buchi di test notevoli](#buchi-di-test-notevoli)
- [Architettura — osservazioni trasversali](#architettura--osservazioni-trasversali)

---

## CRITICI

Violazioni di normativa, bug latenti che si attivano su dati reali, o debiti tecnici bloccanti.

---

### C1 — PK generato per gap > 0 min: viola minimo normativo 20' (NORMATIVA §4.4)

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:238–249`

**Codice attuale**:
```python
gap = _diff(prec.ora_fine, b.ora_inizio)
if gap > 0:
    drafts.append(_BloccoPdcDraft(
        tipo_evento="PK",
        durata_min=gap,
        ...
    ))
```

**Normativa violata**: NORMATIVA-PDC §4.4:
> "PK in arrivo: **20' minimo**. PK in partenza: **20' minimo**."
> Struttura tipica: `treno arriva → PK in arrivo (20' min) → pausa → PK in partenza (20' min) → treno parte`

**Problema**: un gap di 1–19 minuti tra due blocchi condotta diventa un `TurnoPdcBlocco` di tipo "PK" con durata inferiore al minimo normativo. Un PK di 5 minuti è fisicamente impossibile: non c'è tempo per la messa in sicurezza del materiale. Questi blocchi falsi emergono in turni con giri densi (treni ravvicinati), che sono comuni nelle linee suburbane S.

Secondo NORMATIVA §4.2, un gap di 15–60 minuti è un "buco" (pausa informale), non un PK formale. Gap < 15 minuti non sono nemmeno classificabili come buco: sono semplicemente connessioni tecniche senza evento operativo.

**Fix proposto**:
```python
gap = _diff(prec.ora_fine, b.ora_inizio)
PK_MIN_DURATA = 20  # NORMATIVA §4.4
BUCO_MIN_DURATA = 15  # NORMATIVA §4.2

if gap >= PK_MIN_DURATA:
    drafts.append(_BloccoPdcDraft(tipo_evento="PK", durata_min=gap, ...))
elif gap >= BUCO_MIN_DURATA:
    drafts.append(_BloccoPdcDraft(tipo_evento="BUCO", durata_min=gap, ...))
# gap < 15 min: connessione tecnica, nessun blocco
```

**Impatto**: tutti i turni PdC generati da giri con treni ravvicinati (gap < 20') contengono blocchi PK non conformi. La violazione è silente — non appare nella lista `violazioni` — e il pianificatore vede un turno apparentemente valido con PK impossibili.

---

### C2 — `datetime.utcnow()` deprecated in Python 3.12: timestamp timezone-naive nel metadata

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:997`

**Codice attuale**:
```python
"generato_at": datetime.utcnow().isoformat(),
```

**Problema**: `datetime.utcnow()` è deprecato in Python 3.12 e produce un `datetime` **timezone-naive**. Questo significa che il timestamp serializzato in `generation_metadata_json` non porta informazione di timezone. Se un futuro consumer deserializza questo valore e lo confronta con un `datetime` timezone-aware (tutti gli altri timestamp del progetto usano `TIMESTAMPTZ`), ottiene un `TypeError` o un confronto silenziosamente errato.

Il modulo già importa correttamente `UTC` a riga 24: `from datetime import UTC, datetime, timedelta`.

**Fix** (1 riga):
```python
# backend/src/colazione/domain/builder_pdc/builder.py:997
"generato_at": datetime.now(UTC).isoformat(),
```

**Impatto**: ogni TurnoPdc generato dal builder ha un `generato_at` non-aware. Tutti gli altri timestamp del sistema (created_at, updated_at) sono `TIMESTAMPTZ` (aware). Inconsistenza che si manifesta se si fa analisi/audit su questo campo.

---

### C3 — Anti-rigenerazione carica TUTTI i TurnoPdc dell'azienda in memoria: OOM risk

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:710–728`

**Codice attuale**:
```python
existing = list(
    (
        await session.execute(
            select(TurnoPdc).where(TurnoPdc.azienda_id == azienda_id)
        )
    ).scalars()
)
def _matches_giro_e_deposito(t: TurnoPdc) -> bool: ...
legati = [t for t in existing if _matches_giro_e_deposito(t)]
```

**Problema**: la query carica in memoria **tutti** i `TurnoPdc` dell'azienda, indipendentemente dal giro. Con un'azienda come Trenord (ingegneria ferroviaria: tipicamente centinaia di giri × depositi × varianti), la tabella può contenere decine di migliaia di righe. Ogni riga è un oggetto ORM pesante.

Il filtro `_matches_giro_e_deposito` usa `generation_metadata_json['giro_materiale_id']` — un campo JSONB non indicizzato per questa query — e `deposito_pdc_id` (questo indicizzato). Niente impedisce di farlo a livello SQL.

**Fix**:
```python
# SQL-level filter: condizione su JSONB cast + deposito_pdc_id
from sqlalchemy import Integer, cast
from sqlalchemy.dialects.postgresql import JSONB

stmt = (
    select(TurnoPdc)
    .where(TurnoPdc.azienda_id == azienda_id)
    .where(
        cast(
            TurnoPdc.generation_metadata_json["giro_materiale_id"].astext,
            Integer
        ) == giro_id
    )
)
if deposito_pdc_id is not None:
    stmt = stmt.where(TurnoPdc.deposito_pdc_id == deposito_pdc_id)
legati = list((await session.execute(stmt)).scalars())
```

Aggiungere un indice GIN su `generation_metadata_json` se la query diventa frequente (migration futura).

**Impatto**: la generazione turni PdC per un'azienda con molti turni pregenerati può causare picchi di memoria e latenza crescente lineare. Il builder viene chiamato interattivamente dal pianificatore — una risposta lenta su N giri è un problema UX immediato.

---

### C4 — Preriscaldo invernale (ACCp 80') non implementato: turni invernali sistematicamente sbagliati

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:57, 1078`

**Codice attuale**:
```python
# riga 57
ACCESSORI_MIN_STANDARD = 40  # sempre, in ogni mese

# riga 1078 — nel persister
is_accessori_maggiorati=False,  # sempre False
```

**Normativa violata**: NORMATIVA-PDC §3.3:
> | Caso | ACCp | ACCa |
> |------|------|------|
> | Condotta standard | **40'** | **40'** |
> | Condotta con preriscaldo ● (dic-feb) | **80'** | **40'** |

**Problema**: il campo `TurnoPdcBlocco.is_accessori_maggiorati` esiste nel modello (migration 0001, colonna `Boolean NOT NULL DEFAULT false`) ed è esposto nell'API di lettura (`schemas/turni_pdc.py:67`). È strutturalmente pronto per il preriscaldo. Ma il builder lo imposta sempre a `False` e usa sempre `ACCESSORI_MIN_STANDARD = 40`.

Conseguenza concreta: per tutti i turni generati nei mesi dicembre, gennaio e febbraio, l'ACCp è di 40 minuti anziché 80. La prestazione stimata è 40 minuti più corta del reale → i turni appaiono conformi quando sforano il cap.

**Il campo `is_accessori_maggiorati` è dead infrastructure**: esiste in DB, schema e API read-side, ma non viene mai impostato a `True`.

**Fix** (scope stimato: ~2h):
1. Aggiungere costante `ACCESSORI_MIN_PRERISCALDO = 80`.
2. In `_build_giornata_pdc`, ricevere `data_giornata: date | None = None` (o estrarlo dal contesto).
3. Se `data_giornata.month in (12, 1, 2)` → usare 80' per ACCp, impostare `is_accessori_maggiorati=True` sul blocco ACCp.
4. Il persister (`_persisti_un_turno_pdc`) già passa `is_accessori_maggiorati` al blocco ORM.

**Impatto**: violazione normativa HARD per tutti i turni invernali. I cap di prestazione sono calcolati su numeri errati. Il pianificatore vede turni "OK" che in realtà sforano.

---

### C5 — `assert` in produzione in `db.py`: no-op con `-O`, comportamento imprevedibile

**File**: `backend/src/colazione/db.py:58`

**Codice attuale**:
```python
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        get_engine()  # inizializza
    assert _session_factory is not None  # ← assert in produzione
    return _session_factory
```

**Problema**: `assert` in codice di produzione è disabilitata se Python è eseguito con `-O` (ottimizzazione). In produzione con `PYTHONOPTIMIZE=1` o flag `-O`, la riga diventa un no-op e la funzione ritorna `None` — che poi causa un `AttributeError` quando il caller tenta di usare la factory.

`get_session_factory()` è chiamata da ogni request HTTP via `get_session()`. Un crash silente qui causa 500 su tutte le richieste in produzione ottimizzata.

**Fix**:
```python
if _session_factory is None:
    raise RuntimeError(
        "Session factory non inizializzata. Chiamare get_engine() prima."
    )
return _session_factory
```

**Impatto**: crash catastrofico di ogni request se il server è avviato con Python ottimizzato. Railway/Docker non attivano `-O` di default, ma è una bomba a orologeria.

---

## IMPORTANTI

Qualità, manutenibilità, o rischi di sicurezza significativi senza violazione normativa immediata.

---

### I1 — JWT secret di default non validato in produzione

**File**: `backend/src/colazione/config.py:34`

**Codice attuale**:
```python
jwt_secret: str = Field(
    default="dev-secret-change-me-min-32-characters-long",
    ...
)
```

**Problema**: se l'env var `JWT_SECRET` non è configurata in Railway, il server parte con il secret di default. Chiunque conosca il codebase (GitHub è pubblico per questa repo) può forgiare JWT validi e impersonare qualsiasi utente.

Non c'è nessun controllo che il secret sia stato cambiato. La documentazione CLAUDE.md dice "Min 32 char in prod" ma non c'è enforcement a runtime.

**Fix** (model_validator su Settings):
```python
from pydantic import model_validator

@model_validator(mode="after")
def _check_jwt_secret_in_prod(self) -> "Settings":
    if not self.debug and self.jwt_secret == "dev-secret-change-me-min-32-characters-long":
        raise ValueError(
            "JWT_SECRET non configurato. Impostare una chiave sicura in produzione."
        )
    return self
```

---

### I2 — Access token con scadenza 72h: finestra di intercettazione eccessiva

**File**: `backend/src/colazione/config.py:39`

```python
jwt_access_token_expire_min: int = 4320  # 72h
```

Lo stesso file `auth/dependencies.py:19` riconosce: *"se un utente è disattivato o un ruolo è revocato, il cambio diventa effettivo solo all'access token successivo (max 72h con la config attuale). Per MVP è accettabile."*

72h è accettabile per MVP locale ma non per produzione su Railway. Con 30 giorni di refresh token, un utente disattivato può restare operativo fino a 72h + il sistema di logout non invalida i token in-flight (stateless JWT).

**Fix**: abbassare `jwt_access_token_expire_min` a 60 (1h) e implementare refresh rotation. Nessuna migration necessaria.

---

### I3 — `updated_at` senza `onupdate`: timestamp stale dopo ogni UPDATE

**File**:
- `backend/src/colazione/models/turni_pdc.py:57`
- `backend/src/colazione/models/programmi.py:153`
- `backend/src/colazione/models/giri.py:79`
- `backend/src/colazione/models/anagrafica.py:114`
- `backend/src/colazione/models/personale.py:69`

**Codice attuale** (identico in tutti i modelli):
```python
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), server_default=func.now()
)
```

**Problema**: `server_default=func.now()` imposta il timestamp solo alla INSERT. Dopo un UPDATE via ORM, il campo `updated_at` resta al valore della creazione. Non c'è né `onupdate=func.now()` lato ORM né trigger PostgreSQL.

Questo significa che la dashboard "Variazioni impatto" e qualsiasi logica basata su `updated_at` per detect modifiche recenti leggerà sempre la data di creazione.

**Fix** (per tutti i modelli affetti):
```python
from sqlalchemy import func, text

updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
    onupdate=func.now(),  # aggiunto
)
```

Alternativamente, aggiungere trigger PostgreSQL `BEFORE UPDATE` via migration Alembic (più robusto perché copre anche aggiornamenti SQL diretti).

---

### I4 — `is_notturno` builder più ampio della normativa: 16h riposo applicato in eccesso

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:331`

**Codice attuale**:
```python
is_notturno = ora_presa < 5 * 60 or ora_fine_servizio > 22 * 60 or ora_fine_servizio < ora_presa
```

**Normativa** (§11.5): i **16h di riposo** si applicano dopo giornata **notturna (tra 00:01 e 05:00)**. La normativa definisce "notturna" per l'ora di fine prestazione che cade nella finestra 00:01-05:00.

**Problema**: la definizione del builder cattura anche turni che:
- Iniziano prima delle 05:00 (es. presa alle 04:30) ma non finiscono in zona notturna
- Finiscono dopo le 22:00 (es. 23:00) — non è "notturno" per normativa

Un turno 04:30–13:00 ha `ora_presa < 300` → `is_notturno=True` → 16h di riposo obbligatorio. Per normativa richiederebbe solo 11h (è un turno mattiniero precoce, non notturno).

Il valore propagato in DB (`TurnoPdcGiornata.is_notturno`) è poi letto dall'algoritmo di assegnazione persone (`normativa/assegnazione_persone.py:283`), che applica i 16h basandosi ciecamente su quel campo.

**Fix**: separare la flag "notturno per riposo" (normativa §11.5) dalla flag "turno con orari difficili" (informativa):
```python
# per il calcolo cap prestazione (§11.8): 01:00-04:59
is_cap_notturno = 60 <= ora_presa < 300

# per il riposo post-turno (§11.5): fine tra 00:01-05:00
is_notturno_riposo = (ora_fine_servizio % 1440) < 300 and (ora_fine_servizio % 1440) > 0

# flag informativa per UI (turno con orari difficili)
is_notturno_ui = ora_presa < 300 or ora_fine_servizio > 1320 or ora_fine_servizio < ora_presa
```

---

### I5 — `assert` in codice di dominio: 7 occorrenze in produzione

**File**: multipli

```
builder_pdc/builder.py:190  — assert primo.ora_inizio is not None
builder_pdc/builder.py:233  — assert b.ora_inizio is not None
builder_pdc/builder.py:236  — assert prec.ora_fine is not None
builder_pdc/multi_turno.py:413  — assert stazione_apertura is not None
builder_pdc/multi_turno.py:469  — assert stazione_chiusura is not None
builder_pdc/multi_turno.py:1107 — assert depot is not None
domain/builder_giro/capacity_routing.py:308 — assert nuova_comp is not None
```

Le `assert` documentano invarianti utili ma sono silenziosamente rimosse con `python -O`. In produzione producono crash `AssertionError` con traceback poco informativi per il pianificatore.

**Fix pattern** (uniform):
```python
# Prima
assert primo.ora_inizio is not None

# Dopo
if primo.ora_inizio is None:
    raise ValueError(f"Blocco {primo.id} privo di ora_inizio: dato DB inconsistente")
```

---

### I6 — `TurnoPdcBlocco.corsa_commerciale_id` con `ondelete=RESTRICT`: blocca variazioni PdE

**File**: `backend/src/colazione/models/turni_pdc.py:97`

```python
corsa_commerciale_id: Mapped[int | None] = mapped_column(
    BigInteger, ForeignKey("corsa_commerciale.id", ondelete="RESTRICT")
)
```

**Problema**: la normativa operativa prevede che le corse possano essere cancellate o sostituite tramite variazioni PdE. Il modulo `variazioni_pde.py` gestisce già questo flusso. Ma con `ondelete=RESTRICT`, qualsiasi DELETE su `corsa_commerciale` è bloccata da PostgreSQL se esiste almeno un `TurnoPdcBlocco` che la referenzia — anche se il turno è archiviato.

In pratica: per applicare una variazione che cancella una corsa storica, bisogna prima cancellare tutti i blocchi PdC che la referenziano. Questo rompe la tracciabilità storica (i turni archiviati perdono i riferimenti alle corse).

**Fix**: cambiare in `ondelete="SET NULL"` (il blocco perde il FK ma resta storico), oppure aggiungere un soft-delete sulla corsa e non cancellarla mai fisicamente. La decisione dipende dal requisito di auditabilità storica — da discutere con l'utente prima di applicare.

**Costo stimato**: migration semplice, 30 min. Ma richiede decisione di business.

---

### I7 — Accoppiamento privato tra `multi_turno.py` e `builder.py`

**File**: `backend/src/colazione/domain/builder_pdc/multi_turno.py:57–73`

```python
from colazione.domain.builder_pdc.builder import (
    ACCESSORI_MIN_STANDARD,
    CONDOTTA_MAX_MIN,
    # ...
    _BloccoPdcDraft,       # prefisso _ = privato
    _build_giornata_pdc,   # prefisso _ = privato
    _from_min,             # prefisso _ = privato
    _GiornataPdcDraft,     # prefisso _ = privato
    _persisti_un_turno_pdc,# prefisso _ = privato
    _t,                    # prefisso _ = privato
)
```

`multi_turno.py` importa 6 funzioni/classi private da `builder.py`. In Python il prefisso `_` è una convenzione di "non usare fuori dal modulo". Questo accoppiamento stretto:
1. Impedisce di refactoring builder.py senza rompere multi_turno.py
2. Oscura il contratto pubblico del modulo builder
3. È l'origine del ciclo import risolto con deferred import (vedi M7)

**Fix**: creare `backend/src/colazione/domain/builder_pdc/_base.py` con le strutture condivise (`_BloccoPdcDraft`, `_GiornataPdcDraft`, `_build_giornata_pdc`, `_t`, `_from_min`). Entrambi i moduli importano da `_base`. Elimina il ciclo e l'accoppiamento diretto.

---

### I8 — `STAZIONI_CV_DEROGA` hardcoded: non configurabile per programma

**File**: `backend/src/colazione/domain/builder_pdc/split_cv.py:59`

```python
STAZIONI_CV_DEROGA: frozenset[str] = frozenset({"MORTARA", "TIRANO"})
```

Documentato nel commento: *"Refactor a regola configurabile per programma in iterazioni successive."*

Il problema è che la deroga è globale: se un programma Linea Valtellina non prevede CV a TIRANO, non può escluderlo. Viceversa, un programma potrebbe avere deroghe diverse.

La normativa §9.2.3 dice "stazione di capolinea dove il treno inverte il senso di marcia": TIRANO è un capolinea fisso, MORTARA è una deroga operativa. Le due hanno natura diversa e dovrebbero essere gestite diversamente.

**Fix**: aggiungere campo `stazioni_cv_deroga_json: list[str]` a `ProgrammaMateriale` (con migration Alembic). Il builder legge da lì invece della costante globale. Il seed iniziale popola il campo con `["MORTARA", "TIRANO"]` per Trenord. Costo: ~3h.

---

### I9 — `ciclo_giorni` cappato a 14 senza giustificazione normativa

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:1028`

```python
turno = TurnoPdc(
    ...
    ciclo_giorni=max(1, min(14, giro.numero_giornate)),
    ...
)
```

La migration 0001 ha `CHECK (ciclo_giorni BETWEEN 1 AND 14)` sulla tabella `turno_pdc`. Il builder rispetta questo vincolo DB.

**Problema**: la normativa §11 descrive cicli "5+2" (7 giorni) come pattern standard. Non esiste un cap esplicito di 14 giorni nella normativa. Un giro materiale di 28 giorni (frequente per programmi mensili) produce un `TurnoPdc` con `ciclo_giorni=14` — metà del ciclo reale. Il pianificatore vede un turno con ciclo errato.

**Fix**: rivedere se il cap è intenzionale (motivazione non trovata in TN-UPDATE né in NORMATIVA-PDC). Se non c'è motivazione normativa, allargare il CHECK constraint a `BETWEEN 1 AND 90` (trimestre). Se è una scelta di design, documentarla in NORMATIVA-PDC.md §11 con la motivazione specifica.

---

### I10 — `get_session()` non ha rollback esplicito: commit mancato è silente

**File**: `backend/src/colazione/db.py:81–95`

```python
async def get_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session
```

`async_sessionmaker` con `AsyncSession` in SQLAlchemy 2.x: il context manager **non committa** automaticamente (commits sono espliciti nei handler). Se un handler dimentica `await session.commit()`, la transazione è silenziosamente rollbackata al termine della request — nessun errore, nessun dato salvato.

Questo è accettabile solo se ogni handler che scrive è disciplinato. Con 12 router e ~50 endpoint, un errore è probabile. In confronto, `session_scope()` (usato negli script) ha commit+rollback espliciti.

**Fix** (opzionale — dipende dalla filosofia di design):
Mantenere il commit esplicito per i writer ma aggiungere un log warning quando la sessione è dirty al termine (dirty = transazione con modifiche non committate che vengono rollbackate):
```python
async with factory() as session:
    yield session
    if session.in_transaction() and session.dirty:
        import logging
        logging.warning("Sessione con modifiche non committate — rollback implicito")
```

---

## MINORI

Stile, naming, micro-ottimizzazioni senza impatto normativo o funzionale immediato.

---

### M1 — `datetime.utcnow()` unico: già contato in C2, nessun altro occorrenza

Verificato: `grep -rn "datetime.utcnow"` → 1 sola occorrenza (`builder_pdc/builder.py:997`). Il resto del codebase usa correttamente `datetime.now(UTC)`.

---

### M2 — `variante_calendario VARCHAR(20)`: troncamento silenzioso delle etichette v2

**File**: `backend/src/colazione/models/turni_pdc.py:72`, `builder_pdc/builder.py:1045`

```python
# modello
variante_calendario: Mapped[str] = mapped_column(String(20), default="LMXGV")

# builder — troncamento esplicito
variante_calendario=(d.variante_calendario or "GG")[:20],
```

Le etichette v2 Trenord (entry 205) possono essere molto più lunghe di 20 caratteri:
- `"LV escluso FpF ed escl. 22/3, 12/4"` = 37 caratteri
- `"Si eff. 21-28/3, 11/4"` = 22 caratteri

Il troncamento è documentato con `[:20]` ma silenzioso per il pianificatore. La migration per allargare a VARCHAR(100) è semplice e non-breaking.

**Fix**: migration Alembic `ALTER TABLE turno_pdc_giornata ALTER COLUMN variante_calendario TYPE VARCHAR(100)`, rimuovere `[:20]` dal builder.

---

### M3 — `calendario.py`: docstring con riferimento a file inesistente

**File**: `backend/src/colazione/domain/calendario.py:20`

```python
# `project_refactor_varianti_giri_separati_TODO.md`): il calendario è
```

Il file `project_refactor_varianti_giri_separati_TODO.md` non esiste nel repo. Residuo di un refactoring precedente. La docstring fa riferimento a un documento che non si trova da nessuna parte.

**Fix**: aggiornare il commento con un riferimento al documento effettivo (probabilmente TN-UPDATE entry del refactoring varianti) o rimuoverlo.

---

### M4 — `builder_version` nel metadata: stringa narrativa non ordinabile

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:998`

```python
"builder_version": "mvp-7.9-eta",
```

Una stringa come `"mvp-7.9-eta"` non è un identificatore semver né un enum. Non si può confrontare programmaticamente (`"mvp-7.9-eta" > "mvp-7.4"` è confronto lessicale, non semantico). Se il builder viene aggiornato, il valore va aggiornato manualmente senza garanzia.

**Fix**: usare un identificatore stabile (es. `"pdc-builder-1.0"` con semver) o una enum Python esportata. Se il valore serve solo per tracing/debug, è accettabile così purché non venga mai usato per logica condizionale.

---

### M5 — `SOGLIA_WARNING_RIPOSO_SETTIMANALE = 6`: euristica imprecisa per §11.4

**File**: `backend/src/colazione/domain/normativa/assegnazione_persone.py:79–80`

```python
#: ≥6 giornate in 7gg → 62h consecutive non sono fisicamente possibili.
SOGLIA_WARNING_RIPOSO_SETTIMANALE = 6
```

L'euristica è conservativa ma troppo aggressiva: con 6 giornate in 7 giorni, il riposo è 24h (tra la 6ª giornata e la 7ª), non 62h. Il warning è corretto MA ci sono configurazioni di 6 giornate in 7gg che rispettano i 62h se i turni sono corti (es. 6 turni da 6h con il 7° giorno libero + riposo inizia presto il 6° giorno).

Il commento lo riconosce come "euristica MVP". Da documentare come tale e considerare una verifica precisa.

---

### M6 — `"builder_version": "mvp-7.9-eta"` nel persister PdC: tracking non coerente con `ProgrammaMateriale.builder_version`

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:998`

Il programma materiale ha ora un campo `builder_version: Literal["v1", "v2"]` (migration 0038, entry 206). Il `TurnoPdc` ha invece `"builder_version": "mvp-7.9-eta"` nel JSONB. Sono due versioni diverse con due schemi diversi — confusione futura garantita per chi analizza lo storico.

**Fix**: allineare la naming convention: usare la stessa stringa di versione in entrambi i posti, o usare uno schema esplicito (es. `{"giro_builder_version": "v1", "pdc_builder_version": "1.0"}`).

---

### M7 — Ciclo import builder↔split_cv risolto con deferred import: design-debt aperto

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:747, 827`

```python
# Sprint 7.4 MR 2: import deferred dentro le funzioni per evitare ciclo:
# `split_cv` importa `_build_giornata_pdc` e le costanti normative da questo
# modulo, e questo modulo lo richiama. L'import a livello funzione
# rompe la dipendenza al collection time.
from colazione.domain.builder_pdc.split_cv import lista_stazioni_cv_ammesse
from colazione.domain.builder_pdc.split_cv import split_e_build_giornata
```

Il ciclo è reale e correttamente risolto, ma i deferred import sono un workaround. Ogni chiamata a `genera_turno_pdc` / `_genera_un_turno_pdc` esegue l'import runtime (Python lo caccha dopo la prima volta, quindi costo basso). Il problema principale è la leggibilità: un lettore del file non vede subito tutte le dipendenze.

La soluzione pulita (vedi I7) è creare un modulo `_base.py` con le strutture condivise.

---

### M8 — Test `_aggiungi_dormite_fr`: nessun test diretto per scenari FR multi-giornata

**File**: `backend/tests/` — assente

Il file `test_simulazione_pdc.py` ha in apertura: *"\_aggiungi_dormite_fr e \_calcola_violazioni_cap_fr già testati"* — ma cercando nel repo, `_aggiungi_dormite_fr` non ha test unitari diretti. I test in `test_simulazione_pdc.py` coprono `SimulazioneFRResult` come struttura dati, non la logica FR.

Casi non testati:
- Giornata N finisce a stazione X diversa dalla sede → giornata N+1 inizia da X → FR rilevato correttamente
- Giornata N finisce a stazione X = sede → nessun FR (caso normale)
- Giornata N notturna + giornata N+1: calcolo `durata_pernotto` con wrap-mezzanotte
- Giro senza FR (tutto in sede): `fr_log = []`

**Fix**: aggiungere `test_aggiungi_dormite_fr.py` con 4 scenari sopra. Costo: ~1h.

---

## Buchi di test notevoli

Oltre a M8, questi moduli hanno coverage insufficiente rispetto alla loro criticità:

| Modulo | Criticità | Test presenti | Gap |
|--------|-----------|---------------|-----|
| `builder_pdc/multi_turno.py` (1274 righe) | ALTA — algoritmo DP | Smoke in `test_pianificatore_pdc_api.py` | Nessun unit test per DP interno, assegnazione deposito, vettore passivo |
| `domain/variazioni.py` | ALTA — cascade variazioni | `test_domain_variazioni.py` presente | Da verificare coverage branch edge cases |
| `normativa/assegnazione_persone.py` | ALTA — normativa §10+§11 | `test_domain_assegnazione_persone.py` | Verificare copertura §11.4 (62h) e §11.5 (16h notturno) |
| `builder_pdc/simulazione.py` | MEDIA — read-only, ma fa calcoli FR | `test_simulazione_pdc.py` parziale | Scenario `stazione_sede_fallback=True` testato ma non tutti i rami FR |

---

## Architettura — osservazioni trasversali

### Positivo

1. **Separazione domain/api/persistence** ben tenuta: le route HTTP non contengono logica di business, il dominio non importa FastAPI. Pattern rispettato in tutti i 12 router.

2. **Multi-tenant coerente**: ogni query usa `azienda_id` come scope. Il JWT porta `azienda_id` e viene validato nel dependency `get_current_user`. Nessuna query DB senza filtro azienda trovata nel codice di produzione.

3. **Validazione schema JSONB**: l'uso di `JSONB` è appropriato per metadata evolutivo (`generation_metadata_json`, `filtri_json`). I campi JSONB non sostituiscono mai dati strutturali che richiedono join indicizzati.

4. **Test coverage builder_giro**: 57 file di test per 20 moduli src. La copertura del builder giro materiale (pipeline core) è buona con scenari realistici (test_builder_giri.py, test_multi_giornata.py, test_catena.py, ecc.).

5. **Normativa §10.6 FR cap**: `_calcola_violazioni_cap_fr` è corretta e testata (test_builder_pdc_eta.py). La formula settimane = `ceil(ciclo / 7)` è conservativa ma coerente.

### Debito tecnico dichiarato (non nuovi finding)

Già tracciato in TN-UPDATE e commenti:
- Wiring v2 persister (adapter `TurnoConVarianti → GiroDaPersistere`): entry 209
- Deroghe CV configurabili per programma: split_cv.py:58
- Qualifiche persona vs linee turno: assegnazione_persone.py:32
- §11.3 ultimo giorno pre-riposo ≤15:00: assegnazione_persone.py:30

Questi sono correttamente tracciati. Nessuno di essi emerge come urgente rispetto ai 5 critici sopra.

---

## Riepilogo priorità

| ID | Gravità | File | Fix stimato | Richiede decisione utente |
|----|---------|------|-------------|--------------------------|
| C1 | CRITICO | builder_pdc/builder.py:238 | 1h | No |
| C2 | CRITICO | builder_pdc/builder.py:997 | 5 min | No |
| C3 | CRITICO | builder_pdc/builder.py:710 | 2h | No |
| C4 | CRITICO | builder_pdc/builder.py:57 | 2h | No |
| C5 | CRITICO | db.py:58 | 10 min | No |
| I1 | IMPORTANTE | config.py:34 | 30 min | No |
| I2 | IMPORTANTE | config.py:39 | 5 min | Sì (quanto abbassare?) |
| I3 | IMPORTANTE | models multipli | 1h + migration | No |
| I4 | IMPORTANTE | builder_pdc/builder.py:331 | 2h | No |
| I5 | IMPORTANTE | dominio multipli | 1h | No |
| I6 | IMPORTANTE | models/turni_pdc.py:97 | 30 min + migration | Sì (SET NULL vs soft-delete?) |
| I7 | IMPORTANTE | multi_turno.py:57 | 3h | No |
| I8 | IMPORTANTE | split_cv.py:59 | 3h + migration | No |
| I9 | IMPORTANTE | builder_pdc/builder.py:1028 | 30 min + migration | Sì (cap normativo?) |
| I10 | IMPORTANTE | db.py:81 | 30 min | Sì (filosofia design) |
| M1–M8 | MINORE | vari | 30 min–2h cad. | Dipende |

**Quick wins immediati (tutti < 30 min, nessuna decisione utente)**:
- C2: sostituire `datetime.utcnow()` → `datetime.now(UTC)`
- C5: sostituire `assert` in `db.py` → `raise RuntimeError`
- I5: sostituire gli 8 `assert` in dominio → eccezioni esplicite (find+replace)

**Fix a maggiore impatto normativo** (da fare prima del prossimo sprint):
- C1: PK minimo 20' — ogni turno invernale denso è sbagliato
- C4: preriscaldo ACCp 80' — ogni turno invernale è sbagliato

---

*Review generata il 2026-05-07. Nessun fix applicato al codice. Leggere e decidere l'ordine di intervento prima di aprire MR.*
