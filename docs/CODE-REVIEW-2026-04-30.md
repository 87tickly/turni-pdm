# Code Review — COLAZIONE — 2026-04-30

> Eseguita il **2026-05-17** da NINO (Claude Code).
> Scope: intero repository post-Sprint 8.2/8.3/8.4.
> Metodo: lettura diretta del codice + grep sistematico per pattern
> noti (assert, noqa, TODO, onupdate, STAZIONI\_CV). Zero fix automatici.
> Ogni finding ha citazione `file:riga` verificata prima della scrittura.

---

## Executive Summary

| Gravità | Conteggio | Area principale |
|---------|-----------|-----------------|
| CRITICO | 4 | Normativa §9.2 (CV Tirano), sicurezza API, modelli DB |
| IMPORTANTE | 8 | Performance, tech-debt domain, sicurezza auth |
| MINORE | 6 | Dead code, stile, manutenibilità |

**Il finding più grave è C1**: `STAZIONI_CV_DEROGA` usa nomi italiani
invece di codici RFI, rendendo impossibile qualsiasi split CV al
capolinea di Tirano (linea Valtellina). Ogni turno Valtellina che
supera i cap normativa genera silenziosamente una violazione che nessun
validatore segnala perché il split non avviene mai.

---

## CRITICO

### C1 — STAZIONI\_CV\_DEROGA: nomi italiani vs codici RFI → CV Tirano impossibile

**File:** `backend/src/colazione/domain/builder_pdc/split_cv.py:61,88,197`

**Problema:**

```python
# split_cv.py:61
STAZIONI_CV_DEROGA: frozenset[str] = frozenset({"MORTARA", "TIRANO"})

# split_cv.py:64-88
async def lista_stazioni_cv_ammesse(...) -> set[str]:
    # Carica depositi PdC → stazioni con codice RFI (es. "S01440")
    stazioni: set[str] = set()
    for d in depositi:
        if d.stazione_principale_codice:
            stazioni.add(d.stazione_principale_codice)
    stazioni.update(STAZIONI_CV_DEROGA)   # ← aggiunge "TIRANO", "MORTARA"
    return stazioni

# split_cv.py:197
if stazione_a is None or stazione_a not in stazioni_cv:
```

`GiroBlocco.stazione_da_codice` è una FK su `stazione.codice` (formato
`"S01440"` per Tirano, `"S02154"` per Mortara). Il set
`stazioni_cv` restituito da `lista_stazioni_cv_ammesse` contiene
codici RFI per i depositi (caricati dalla migration 0030), ma le
deroghe hardcoded "TIRANO" e "MORTARA" sono stringhe in chiaro.
Il controllo `stazione_a not in stazioni_cv` confronta
`"S01440"` con `{"S01234", ..., "TIRANO", "MORTARA"}` → SEMPRE False
per Tirano.

**Conseguenza normativa:** §9.2 Normativa PdC ammette il CV al
capolinea di inversione (TIRANO). Questa deroga è di fatto non
operativa: qualsiasi giornata Valtellina che supera i cap
(prestazione > 510 min o condotta > 330 min) non può essere spezzata
a Tirano → le violazioni non vengono corrette → il turno viene
emesso con violazioni silenti.

MORTARA è parzialmente protetta perché migration 0030 la include
come deposito PdC e le assegna il codice RFI via `ILIKE '%MORTARA%'`.
Ma anche per MORTARA la stringa "MORTARA" nella frozenset è priva
di effetto reale.

**Fix:**

```python
# Rimuovere STAZIONI_CV_DEROGA come frozenset di nomi italiani.
# Aggiungere un set di codici RFI hardcoded per le stazioni non-deposito:
STAZIONI_CV_DEROGA_CODICE: frozenset[str] = frozenset({
    "S01440",  # TIRANO — capolinea inversione Valtellina (§9.2 deroga)
    # MORTARA è deposito, gestita via migration 0030 — non serve hardcode
})

async def lista_stazioni_cv_ammesse(...) -> set[str]:
    ...
    stazioni.update(STAZIONI_CV_DEROGA_CODICE)
    return stazioni
```

Il codice RFI di Tirano (`S01440`) va verificato da migration
0030 o da un seed stazioni. Aggiungere un test che `lista_stazioni_cv_ammesse`
includa `"S01440"` e NON includa `"TIRANO"`.

---

### C2 — Anti-rigenerazione: full table scan + Python filter su JSONB

**File:** `backend/src/colazione/domain/builder_pdc/multi_turno.py:590-599`

**Problema:**

```python
# multi_turno.py:590-599
existing = list(
    await session.execute(
        select(TurnoPdc).where(TurnoPdc.azienda_id == azienda_id)
    ).scalars()
)
legati = [
    t for t in existing
    if (t.generation_metadata_json or {}).get("giro_materiale_id") == giro_id
]
```

Carica TUTTI i `TurnoPdc` dell'azienda in memoria, poi filtra in Python
sul campo JSONB `generation_metadata_json->>'giro_materiale_id'`.
Con 10 aziende × 500 turni ciascuna = 5.000 ORM object caricati per ogni
chiamata a `genera_turni_pdc_multi`, anche quando il giro richiesto ha
zero turni preesistenti.

**Fix (SQL nativo su JSONB):**

```python
from sqlalchemy import cast, Text as SAText
from sqlalchemy.dialects.postgresql import JSONB as SAJSONB

legati = list(
    await session.execute(
        select(TurnoPdc).where(
            TurnoPdc.azienda_id == azienda_id,
            TurnoPdc.generation_metadata_json["giro_materiale_id"].as_integer()
            == giro_id,
        )
    ).scalars()
)
```

Alternativa con cast stringa (più sicura se il valore è stato serializzato
come stringa anziché intero):

```python
TurnoPdc.generation_metadata_json["giro_materiale_id"].as_string() == str(giro_id)
```

Aggiungere indice GIN o indice funzionale sul campo per rendere la query
O(log N) invece di O(N).

---

### C3 — Assert in path di sicurezza e infrastruttura critica

**File (sicurezza):** `backend/src/colazione/api/giri.py:2891`

**Problema:**

```python
# giri.py:2891
assert target_giro.azienda_id == user.azienda_id, (
    f"giro {giro_id} non appartiene ad azienda {user.azienda_id}"
)
```

Questo assert in un endpoint API è l'unico guardarails contro un
utente che accede al giro di un'altra azienda. Python avviato con
`-O` (optimize) o `PYTHONOPTIMIZE=1` rimuove silenziosamente tutti
gli assert → il check è disabilitato → privilege escalation cross-tenant.
Railway non usa `-O` di default, ma la dipendenza da questo comportamento
è un rischio documentato.

**Fix:**

```python
if target_giro.azienda_id != user.azienda_id:
    raise HTTPException(status_code=403, detail="Accesso non autorizzato")
```

**File (infrastruttura):** `backend/src/colazione/db.py:58`

```python
# db.py:58
assert _session_factory is not None
```

Ogni richiesta HTTP passa per questo codice. Se `_session_factory` è
None (startup incompleto, config mancante), Python -O produce un
`AttributeError` generico invece di un errore diagnostico.

**Fix:**

```python
if _session_factory is None:
    raise RuntimeError(
        "DB non inizializzato: chiamare init_db() prima di usare get_session()"
    )
```

---

### C4 — `updated_at` mai aggiornato dopo INSERT (missing `onupdate`)

**File:**
- `backend/src/colazione/models/turni_pdc.py:59`
- `backend/src/colazione/models/giri.py:79`
- `backend/src/colazione/models/programmi.py:187`

**Problema:**

```python
# turni_pdc.py:59 (e idem negli altri due file)
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), server_default=func.now()
)
```

`server_default=func.now()` valorizza `updated_at` **solo al momento
dell'INSERT** (DML `DEFAULT` di Postgres). Qualsiasi UPDATE successivo
lascia `updated_at` invariato al timestamp di creazione. Non esiste
`onupdate=func.now()` né un trigger Postgres a supporto.

Conseguenza pratica: qualsiasi query che ordina/filtra per
`updated_at` per trovare record modificati di recente (es. sync
incrementale, audit log, cache invalidation) restituisce dati
incorretti.

**Fix (SQLAlchemy ORM):**

```python
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
    onupdate=func.now(),
)
```

`onupdate=func.now()` istruisce SQLAlchemy a includere
`updated_at = now()` in ogni `UPDATE` generato dall'ORM. Aggiungere
la migration Alembic corrispondente (non è un DDL change ma una
modifica al comportamento ORM — va testata esplicitamente).

**Attenzione**: se si usano `session.execute(update(Model)...)` raw
(senza ORM), `onupdate` non scatta. In quel caso serve un trigger
Postgres o una colonna generata.

---

## IMPORTANTE

### I1 — Assert come guard interni nel domain layer (builder, multi\_turno)

**File:**
- `backend/src/colazione/domain/builder_pdc/builder.py:210,253,256`
- `backend/src/colazione/domain/builder_pdc/multi_turno.py:421,477,1140`

**Problema:**

```python
# builder.py:210
assert primo.ora_inizio is not None and ultimo.ora_fine is not None
# builder.py:253
assert b.ora_inizio is not None and b.ora_fine is not None
# builder.py:256
assert prec.ora_fine is not None

# multi_turno.py:421
assert stazione_apertura is not None
# multi_turno.py:477
assert stazione_chiusura is not None
# multi_turno.py:1140
assert depot is not None and depot.id == depot_key
```

Gli assert nel domain layer fungono da invarianti documentati ma sono
disattivati da Python `-O`. Se un builder produce un blocco con
`ora_inizio=None` (es. per import da PDF malformato o edge case
non coperto), il codice prosegue silenziosamente con arithmetic su
`None` e genera un `AttributeError` non contestualizzato in produzione.

**Fix:** sostituire con `raise ValueError(...)` espliciti che portano
contesto diagnostico:

```python
# builder.py:210
if primo.ora_inizio is None or ultimo.ora_fine is None:
    raise ValueError(
        f"giornata {numero_giornata}: primo blocco senza ora_inizio o "
        f"ultimo blocco senza ora_fine — dati giro inconsistenti"
    )
```

I sei assert possono essere convertiti in batch in un unico commit.

---

### I2 — Seconda query Depot in `_persisti_segmenti` dopo caricamento già avvenuto

**File:** `backend/src/colazione/domain/builder_pdc/multi_turno.py:1048-1060`

**Problema:**

```python
# multi_turno.py:571-574 — prima query
depositi = list(
    await session.execute(select(Depot).where(Depot.is_attivo == True)).scalars()
)

# ... 476 righe dopo ...

# multi_turno.py:1048-1058 — seconda query identica
# Carica tutti i depositi attivi (la heuristic ne aveva la lista
# ma non viene passata a _persisti_segmenti)
depositi_map = {
    d.id: d
    for d in (
        await session.execute(select(Depot).where(Depot.is_attivo == True)).scalars()
    )
}
```

La lista `depositi` è già disponibile nello scope di
`genera_turni_pdc_multi` al momento della chiamata a
`_persisti_segmenti`. Non viene passata come parametro → seconda
query identica. Per 25 depositi Trenord è trascurabile in assoluto,
ma è un pattern che si replica facilmente in contesti più onerosi.

**Fix:** passare `depositi` come argomento a `_persisti_segmenti`:

```python
# Chiamata
await _persisti_segmenti(session, segmenti_pdc, depositi, ...)

# Firma
async def _persisti_segmenti(
    session: AsyncSession,
    segmenti_pdc: list[...],
    depositi: list[Depot],
    ...
) -> list[TurnoPdc]:
    depositi_map = {d.id: d for d in depositi}
```

---

### I3 — `giornata_base.py`: facade di re-export simboli privati (tech debt S2-bis)

**File:** `backend/src/colazione/domain/builder_pdc/giornata_base.py`

**Problema:** Il modulo è un facade introdotto nel Sprint 8.2
MR-PD-FIX-SEVERO per risolvere il finding S2 di SEVERO senza
refactoring invasivo. Ri-esporta simboli `_privati` da `builder.py`
come nomi pubblici. Contiene `__all__` con `GiriEsistentiError` che
però non è inclusa nell'import top-level di `multi_turno.py` (vedi I4).

Il debito è **documentato nel sorgente** ("S2-bis previsto") ma non
ha una entry TN-UPDATE con stima di costo. Rimane in questo stato
indefinitamente.

**Fix:** pianificare S2-bis esplicitamente in TN-UPDATE con un costo
stimato. La risoluzione corretta è:
1. Spostare le funzioni `_private` usate da giornata_base in un
   modulo `_internals.py` o `_draft.py` senza underscore
2. `builder.py` e `giornata_base.py` importano entrambi da lì
3. Rimuovere giornata_base.py come wrapper

Costo stimato: 2-3h di refactoring + test di regressione.

---

### I4 — `registro_vetture.from_db`: date matching wild card, `enumera_date_giornata` non integrata

**File:** `backend/src/colazione/domain/builder_pdc/registro_vetture.py`

**Problema (S4 TODO):** `from_db` carica i blocchi VETTURA senza
filtrare per data concreta. Quando il caller chiede
"vettura disponibile per il giorno 2026-05-15", il registro restituisce
TUTTI i blocchi VETTURA indipendentemente dalla data. La funzione
`enumera_date_giornata` in `giornate_concrete.py` è già implementata
e funziona correttamente (MVP syntax + DSL fallback), ma non è mai
chiamata da `from_db`.

**Conseguenza:** il registro vetture cross-PdC non filtra per data,
il che può generare falsi positivi (conflitti vettura dichiarati su
date in cui la variante non è attiva) e falsi negativi (vetture
disponibili non proposte perché la variante è attiva solo su alcune
date).

**Fix:** in `from_db`, dopo il caricamento dei blocchi, espandere le
date concrete via `enumera_date_giornata(variante_calendario, valido_da, valido_a)`
e indicizzare per data invece che per variante testuale. La funzione
è già disponibile, serve solo il wiring.

---

### I5 — JWT 72h senza revoca: stale roles e utenti disattivati

**File:** `backend/src/colazione/auth/dependencies.py:19`

**Problema (commento nel codice):**

```python
# dependencies.py:19
# se un utente è disattivato o un ruolo è revocato, il cambio
# diventa effettivo solo all'access token successivo (max 72h con
# la config attuale)
```

72h di finestra di validità per un access token senza meccanismo
di revoca è pericoloso: un dipendente licenziato può operare per
72h post-revoca. La finestra è configurabile via
`JWT_ACCESS_TOKEN_EXPIRE_MIN` ma la configurazione attuale è
probabilmente rimasta al default alto usato in sviluppo.

Il debito è **noto e documentato** nel codice ma **non è tracciato
in TN-UPDATE come go-live blocker**.

**Fix:** scegliere uno dei tre pattern:
1. **Token breve** (raccomandato per MVP): `JWT_ACCESS_TOKEN_EXPIRE_MIN=15`
   + refresh token a lunga scadenza. La maggior parte degli attacchi
   window si restringe da 72h a 15 min con zero codice aggiuntivo.
2. **Blocklist in memoria** (Redis): add `jti` claim all'access token,
   blocklist lato server al logout/revoca. 1 lookup Redis per request.
3. **DB roundtrip per revoca urgente**: aggiungere `is_active` su User,
   check solo in `get_current_user` (1 query lightweight).

Aggiungere entry TN-UPDATE marcata "pre-go-live blocker" con la
scelta fatta e la deadline.

---

### I6 — Gap tra condotte sempre PK, mai CV preferito per gap < 65 min (§6)

**File:** `backend/src/colazione/domain/builder_pdc/builder.py` (logica gap filling)

**Problema:** la normativa §6 definisce la tabella gap/blocco:

| Durata gap | Blocco preferito |
|-----------|-----------------|
| < 65 min | CV (cambio volante) o PK |
| 65-300 min | ACC o PK |
| > 300 min | ACC (PK opzionale) |

Per gap < 65 min, CV è **preferito** perché il materiale passa a un
altro PdC senza soste lunghe. Il builder assegna **sempre PK**
a qualsiasi gap, ignorando la preferenza CV per gap brevi.
Conseguenza operativa: turni con molti gap brevi accumulano blocchi
PK sub-ottimali e perdono opportunità di Cambio Volante che
ridurrebbero la prestazione effettiva.

**Attenzione**: non è una violazione normativa (PK è consentito
per gap < 65 min), ma è una ottimizzazione normativa mancante che
impatta la qualità dei turni generati.

**Fix:** nel ciclo gap-filling, se `gap_min < 65` e la stazione è
in `stazioni_cv`, proporre un blocco `CV` invece di `PK`. Aggiungere
flag `preferisci_cv_breve: bool = True` come parametro builder per
consentire toggle. Questo richiede anche che `split_cv.py` sia
corretto (vedi C1) per essere efficace sulla linea Valtellina.

---

### I7 — Nessun `UniqueConstraint(azienda_id, codice)` su `TurnoPdc`

**File:** `backend/src/colazione/models/turni_pdc.py:39,61`

**Problema:**

```python
# turni_pdc.py:39
codice: Mapped[str] = mapped_column(String(50))
# turni_pdc.py:61
__table_args__ = (
    Index("ix_turno_pdc_azienda_deposito", "azienda_id", "deposito_pdc_id"),
)
```

L'indice c'è su `(azienda_id, deposito_pdc_id)` ma **non** su
`(azienda_id, codice)`. Nulla impedisce l'inserimento di due
`TurnoPdc` con lo stesso `codice` per la stessa azienda.
Il codice del turno è l'identificativo operativo (es. `G-FIO-001-ETR204`):
averne due identici nello stesso tenant causa ambiguità in lookup,
display e assegnazione.

**Fix:**

```python
from sqlalchemy import UniqueConstraint

__table_args__ = (
    Index("ix_turno_pdc_azienda_deposito", "azienda_id", "deposito_pdc_id"),
    UniqueConstraint("azienda_id", "codice", name="uq_turno_pdc_azienda_codice"),
)
```

Aggiungere migration Alembic. Verificare prima se esistono duplicati
nel DB di sviluppo (query: `SELECT azienda_id, codice, count(*) FROM turno_pdc GROUP BY 1,2 HAVING count(*)>1`).

---

### I8 — Import differito `GiriEsistentiError` dentro corpo funzione

**File:** `backend/src/colazione/domain/builder_pdc/multi_turno.py:60,604`

**Problema:**

```python
# multi_turno.py:60 — import top-level (altri simboli da giornata_base)
from colazione.domain.builder_pdc.giornata_base import (
    ...  # GiriEsistentiError non inclusa
)

# multi_turno.py:604 — import dentro corpo funzione
from colazione.domain.builder_pdc.giornata_base import GiriEsistentiError
raise GiriEsistentiError(...)
```

`GiriEsistentiError` è esportata da `giornata_base.__all__` ma
non è inclusa nell'import top-level di `multi_turno.py`. L'import
dentro la funzione è valido in Python ma:
1. Oscura le dipendenze del modulo (non visibili in cima al file)
2. Rallenta leggermente il path di errore (import lookup ad ogni
   invocazione della branch)
3. È inconsistente con tutti gli altri import del file

**Fix:** aggiungere `GiriEsistentiError` all'import top-level a
riga 60 e rimuovere l'import locale a riga 604.

---

## MINORE

### M1 — Dead import `_ = Counter` con noqa

**File:** `backend/src/colazione/domain/builder_giro/varianti_calendariali.py:293`

```python
_ = Counter  # noqa: F841 — riservato per estensioni
```

`Counter` è importato ma non usato. La noqa soppianta il check ruff
invece di risolvere il problema. "Riservato per estensioni" è un
commento di intenzione che non appartiene nel codice — appartiene in
un issue o in TN-UPDATE.

**Fix:** rimuovere la riga. Se `Counter` servirà, sarà re-aggiunto
quando serve.

---

### M2 — Dead references `_ = festivita` e `_ = calcola_etichetta_giro` con noqa

**File:** `backend/src/colazione/domain/builder_giro/builder.py:2757-2758`

```python
_ = festivita  # noqa: F841 (reservato per uso futuro)
_ = calcola_etichetta_giro  # noqa: F841 (export pubblico mantenuto)
```

`_ = calcola_etichetta_giro` è giustificata se il simbolo viene
esportato come API pubblica del modulo (anche senza uso interno) —
in quel caso il pattern corretto è `__all__ = [..., "calcola_etichetta_giro"]`.
`_ = festivita` non ha la stessa giustificazione.

**Fix per festivita:** rimuovere se non serve, importare dove serve.
**Fix per calcola_etichetta_giro:** usare `__all__` se è export
intenzionale.

---

### M3 — `_hhmm_to_min`: except silente senza log

**File:** `backend/src/colazione/integrations/live_arturo.py:123-124`

```python
# live_arturo.py:123-124
    except (ValueError, IndexError):
        pass
    return None
```

Un formato timestamp non riconosciuto dall'API live ARTURO (es.
`null`, `"--:--"`, ISO con timezone non standard) viene scartato
silenziosamente. Il chiamante riceve `None` senza contesto. In caso
di cambio API contract lato ARTURO, i bug saranno invisibili fino
a quando non mancano vetture in modo evidente (come è successo
in entry 301).

**Fix:** sostituire `pass` con un log di debug:

```python
    except (ValueError, IndexError):
        logger.debug(
            "live_arturo._hhmm_to_min: formato non riconosciuto '%s'",
            iso_or_hhmm,
        )
    return None
```

---

### M4 — Stringa deroga "MORTARA" ridondante dopo migration 0030

**File:** `backend/src/colazione/domain/builder_pdc/split_cv.py:61`

La migration 0030 include MORTARA nel pattern `ILIKE '%MORTARA%'` e
la lega al deposito PdC con il proprio codice RFI. `lista_stazioni_cv_ammesse`
carica già il codice RFI di MORTARA tramite la query depositi.
La stringa `"MORTARA"` nella frozenset è quindi ridondante (e nella
versione attuale inerte, per la stessa ragione di C1: il formato
non corrisponde ai codici RFI nel set).

**Fix (dopo C1 risolto):** rimuovere `"MORTARA"` da
`STAZIONI_CV_DEROGA_CODICE`. Aggiungere un test che verifica
che il codice RFI di MORTARA sia presente nel risultato di
`lista_stazioni_cv_ammesse` tramite il percorso depositi, non tramite
deroga hardcoded.

---

### M5 — `multi_giornata.py` v1 e v2 coesistono senza chiaro piano di deprecazione

**File:**
- `backend/src/colazione/domain/builder_giro/multi_giornata.py`
- `backend/src/colazione/domain/builder_giro/multi_giornata_v2.py`

I due file coesistono. Il routing tra v1 e v2 è su
`ProgrammaMateriale.builder_version`. Non esiste un commento nel v1
che dica "deprecato, usare v2", né una issue/entry TN-UPDATE con
piano di rimozione.

**Fix:** aggiungere in cima a `multi_giornata.py` un commento
esplicito: "Deprecato — usato solo per builder_version='v1'
(programmi importati pre-Sprint 8.x). Rimozione pianificata dopo
migrazione tutti i programmi a v2." Tracciare la rimozione in TN-UPDATE.

---

### M6 — 9 script diagnostici in `scripts/` senza status attivo/deprecato

**File:** `scripts/` (directory)

La directory contiene script diagnostici accumulati negli Sprint
(analisi km, import, smoke test, ecc.). Non è chiaro quali siano
ancora utili per la produzione, quali siano stati superseded da
test pytest, e quali siano stati scritti per un debug point-in-time
mai più necessario.

**Fix:** aggiungere un `scripts/README.md` con tabella:
- Nome script
- Scopo originale
- Stato: `ATTIVO` / `DEPRECATO` / `ONE-SHOT (già eseguito)`
- Alternativa (se deprecato)

Gli script `DEPRECATO` andrebbero rimossi o spostati in
`scripts/_archivio/` per non inquinare l'albero attivo.

---

## Note metodologiche

1. **50 test failure pre-esistenti** su `master` (entry TN-UPDATE 297):
   non analizzati in questa review perché già riconosciuti come backlog.
   Non sono tutti regressioni — alcuni sono fixture rotte per
   refactoring modello. Andrebbero triaged prima di qualsiasi go-live.

2. **Test coverage frontend**: 14 file test per ~100 file TypeScript.
   `GanttUnificatoRoute.tsx`, `TurnoPdcDettaglioRoute.tsx` e la
   maggior parte delle route business non hanno test. Accettabile per
   MVP ma va documentato come rischio.

3. **Finding non inclusi** (già tracciati in TN-UPDATE o fuori scope):
   - `VETTURA_ATTESA_MAX_MIN = 120` → fallback 240min (entry Sprint 8.4 G2, già noto)
   - wrap-around arithmetic in `_valuta_candidato` (corretto, verificato)
   - `is_cap_notturno` computation dopo `_inserisci_refezione_ai_bordi`
     (analizzato: la computazione a riga 356 avviene su `ora_presa`
     già aggiornato → nessun bug)

---

*Fine review. 4 CRITICO · 8 IMPORTANTE · 6 MINORE = 18 finding totali.*
*Zero modifiche al codice in questo documento.*
