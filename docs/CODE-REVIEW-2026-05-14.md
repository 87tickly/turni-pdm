# Code Review — COLAZIONE — 2026-05-14

> **Scope**: review architetturale completa del repo post Sprint 8.4.
> Eseguita da NINO (Claude Code) con 6 agenti paralleli Explore su
> tutti i layer: builder_pdc, builder_giro, API/auth, models/migrations,
> test suite, frontend.
>
> **Metodo**: diagnosi prima di azione (regola §1 METODO-DI-LAVORO).
> Ogni finding cita `file:riga` verificato. Niente "probabilmente".
>
> **Non è SEVERO**: questa è una review tecnica di qualità generale.
> SEVERO va invocato separatamente per la critica retrospettiva
> post-Sprint.

---

## Indice

- [CRITICI — 6 finding](#critici)
- [IMPORTANTI — 18 finding](#importanti)
- [MINORI — 9 finding](#minori)
- [Riepilogo tabellare](#riepilogo)

---

## CRITICI

### CR-01 — CV gap < 65 min: violazione normativa §5 non implementata

**File**: `backend/src/colazione/domain/builder_pdc/split_cv.py:28`  
**Normativa**: NORMATIVA-PDC §5 + §6

La normativa §6 specifica che se il gap fra due segmenti di condotta è < 65 min,
il PdC esegue CVa/CVp (15+15 = 30 min di accessori totali) anziché ACCa/ACCp
(40+40 = 80 min). La docstring attuale lo dichiara esplicitamente come lacuna:

```python
# split_cv.py:28
# (gap < 65' → CVa/CVp che sostituiscono ACCa/ACCp risparmiando 80').
```

Il builder attuale usa **sempre** 80 min di accessori anche quando il gap è < 65 min.
Conseguenza: prestazioni calcolate con ~50 min di eccesso per ogni CV in finestra
ristretta → violazioni `prestazione > 8h30` generate artificialmente dove non esistono.

**Fix concreto**: in `split_cv.py`, aggiungere:

```python
def _tipo_accessori_per_gap(gap_min: int) -> tuple[int, str, str]:
    """Ritorna (durata_acc, tipo_partenza, tipo_arrivo) in base al gap."""
    if gap_min < 65:
        return (15, "CVp", "CVa")  # §5: gap < 65 min → CV (15+15)
    return (40, "ACCp", "ACCa")   # §3: gap >= 65 min → ACC (40+40)
```

Poi chiamarla in `_build_giornata_pdc` dove si costruiscono i blocchi accessori.

---

### CR-02 — API live.arturo.travel: nessun failover in `genera_turni_pdc_multi`

**File**: `backend/src/colazione/domain/builder_pdc/multi_turno.py:428, 478`  
**Gravità operativa**: blocca la generazione intera se l'API è down

`trova_treno_vettura()` può sollevare `httpx.RequestError` o `httpx.TimeoutException`
(timeout configurato 5s, vedi `config.py:69`). Le chiamate alle righe 428 e 478
sono senza `try/except`. Conseguenza: se `live.arturo.travel` è down durante
`genera_turni_pdc_multi()`, l'eccezione non gestita:

1. Interrompe l'intera generazione (N turni persi)
2. Non ha persistito niente (per via della sessione async aperta)
3. Lascia l'utente con 0 turni e un 500 generico

Il `vettura_resolver.py:281` ha già il pattern corretto (`except Exception: # noqa: BLE001`)
ma nasconde l'errore silenziosamente. La soluzione corretta è il fallback esplicito:

```python
# multi_turno.py, wrapping le chiamate a trova_treno_vettura
try:
    vettura = await trova_treno_vettura(...)
except (httpx.RequestError, httpx.TimeoutException) as exc:
    logger.warning("live_arturo API down per %s: %s — dormita_rientro fallback", staz, exc)
    vettura = None  # builder usa dormita_rientro come fallback
```

---

### CR-03 — JWT secret: default debole senza validazione prod

**File**: `backend/src/colazione/config.py:34-37`

```python
jwt_secret: str = Field(
    default="dev-secret-change-me-min-32-characters-long",  # ← nel repo pubblico
    description="Chiave firma JWT. Min 32 char in prod.",
)
```

Il valore di default è visibile nel repository. Chiunque lo legga può forgiare JWT
validi se l'env var `JWT_SECRET` non è stata impostata. Non c'è alcun validatore
che impedisca l'avvio con il default in produzione.

**Fix concreto**: aggiungere un `@field_validator` che rifiuta l'avvio:

```python
@field_validator("jwt_secret")
@classmethod
def _jwt_secret_non_default(cls, v: str) -> str:
    if v == "dev-secret-change-me-min-32-characters-long":
        raise ValueError(
            "JWT_SECRET deve essere sovrascritto da env var in produzione"
        )
    if len(v) < 32:
        raise ValueError("JWT_SECRET deve essere >= 32 caratteri")
    return v
```

In alternativa: impostare `default=""` e fare il check su stringa vuota, che fallisce
comunque al primo `jwt.encode()`.

---

### CR-04 — CSP assente: il commento "Mitigato da CSP" in tokenStorage.ts è falso

**File**: `frontend/src/lib/auth/tokenStorage.ts:8` e `backend/src/colazione/main.py:45-50`

Il token storage in localStorage è documentato come "Trade-off noto: vulnerabile a XSS.
**Mitigato da CSP** + nessun `dangerouslySetInnerHTML`". Ma `main.py` non imposta
nessun header CSP:

```python
# main.py:45-50 — nessun SecurityHeadersMiddleware, nessun CSP
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

La mitigazione dichiarata non esiste. I token JWT (access + refresh, 72h + 30gg)
sono esposti a qualsiasi XSS presente o futuro senza barriera CSP.

**Fix concreto** (due passi):

1. `main.py`: aggiungere `starlette.middleware.trustedhost` + header CSP:
   ```python
   from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
   
   @app.middleware("http")
   async def add_security_headers(request, call_next):
       response = await call_next(request)
       response.headers["Content-Security-Policy"] = (
           "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';"
       )
       response.headers["X-Content-Type-Options"] = "nosniff"
       response.headers["X-Frame-Options"] = "DENY"
       return response
   ```

2. Aggiornare il commento in `tokenStorage.ts` con lo stato reale: il CSP non è ancora
   implementato, il rischio XSS è aperto.

---

### CR-05 — `updated_at` non si aggiorna: `server_default` senza `onupdate`

**File**: tutti i modelli con `updated_at`:
- `models/turni_pdc.py:59`
- `models/giri.py:79`
- `models/programmi.py:187`
- `models/personale.py:69`
- `models/anagrafica.py:116, 557`

Tutti usano `server_default=func.now()` ma **mancano di `onupdate`**:

```python
# ATTUALE — aggiorna solo all'INSERT
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), server_default=func.now()
)

# CORRETTO — aggiorna anche all'UPDATE
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
    onupdate=func.now(),  # ← MANCA
)
```

Con SQLAlchemy async ORM, l'UPDATE emesso dalla sessione non triggera
`server_default` — serve `onupdate` o un trigger PostgreSQL. Il risultato
pratico è che `updated_at` è sempre uguale a `created_at` dopo ogni UPDATE.
Questo rende inutilizzabile `updated_at` per cache invalidation e audit.

**Fix concreto**: aggiungere `onupdate=func.now()` e una migration Alembic:
```python
op.execute(
    """CREATE OR REPLACE FUNCTION update_updated_at()
    RETURNS TRIGGER AS $$ BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
    $$ LANGUAGE plpgsql;"""
)
# + CREATE TRIGGER su ogni tabella interessata
```

---

### CR-06 — Refezione obbligatoria: violazione non blocca la persistenza

**File**: `backend/src/colazione/domain/builder_pdc/multi_turno.py:158-172`
e `builder.py:368-369`

Normativa §8.1: refezione 30 min **obbligatoria** se prestazione > 6h (360 min).
L'attuale `_segmento_valido()` in `multi_turno.py` accetta un segmento come valido
anche con `refezione_mancante` nella lista `violazioni`:

```python
# builder.py:368
if prestazione_min > REFEZIONE_SOGLIA_MIN and refezione_min == 0:
    violazioni.append("refezione_mancante")
    # ← nessun return None, nessun blocco
```

E in `multi_turno.py`, `_segmento_valido()` ritorna il draft anche se ha violazione
`refezione_mancante`. Risultato: turni con prestazione > 6h senza refezione vengono
persistiti nel DB senza blocco, violando la normativa.

**Fix concreto**: in `multi_turno._segmento_valido()`:

```python
# Dopo aver costruito il draft con _build_giornata_pdc:
if (
    draft.prestazione_min > REFEZIONE_SOGLIA_MIN
    and draft.refezione_min == 0
):
    return None  # HARD: refezione mancante → giornata invalida per multi-turno
```

Per il builder MVP single-turno, mantenere il comportamento attuale (violazione
segnalata ma non bloccante) per backward compat, **documentandolo esplicitamente**.

---

## IMPORTANTI

### IMP-01 — Access token 72h: troppo lungo per produzione

**File**: `backend/src/colazione/config.py:39`

```python
jwt_access_token_expire_min: int = 4320  # 72h
```

Best practice 2024: access token 15-30 min, refresh token 30 giorni.
Un token compromesso su un device dà accesso per 3 giorni interi.

**Fix**: `jwt_access_token_expire_min: int = 30` + logica di refresh
automatica nel frontend (già presente via `AuthContext.tsx`).

---

### IMP-02 — Nessun rate limiting su `/api/auth/login`

**File**: `backend/src/colazione/api/auth.py:44-78`

L'endpoint non ha rate limit. Un attacker può tentare N password/sec.
Nessuna protezione brute force, nessun lockout, nessun CAPTCHA.

**Fix**: aggiungere `slowapi` o middleware FastAPI:

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/login")
@limiter.limit("5/minute")
async def login(...):
```

---

### IMP-03 — Nessun endpoint `/logout`: refresh token non revocabili

**File**: `backend/src/colazione/api/auth.py` (endpoint mancante)

Il refresh token dura 30 giorni. Non esiste `/api/auth/logout`. Un utente
che perde il device non può invalidare la sessione.

**Fix MVP**: aggiungere blacklist in-memory con `jti` (JWT ID). Aggiungere
`jti=str(uuid4())` nel payload del refresh token, verificare la blacklist
al momento del refresh.

---

### IMP-04 — Liste API senza pagination: DoS indiretto

**File**: `backend/src/colazione/api/anagrafiche.py:120` (e molti altri)

Endpoint che caricano tutte le righe senza `LIMIT`:
- `GET /api/anagrafiche/stazioni` — tutte le stazioni
- `GET /api/anagrafiche/indisponibilita` — tutte le indisponibilità
- `GET /api/personale/persone` — tutte le persone
- `GET /api/giri/azienda` — tutti i giri

Con crescita dati, caricano MB in memoria. Aggiungere `limit: int = Query(200, le=2000)`
e `offset: int = Query(0, ge=0)` almeno agli endpoint che gestiscono entità unbounded
(persone, indisponibilità, corse non coperte).

---

### IMP-05 — FK senza `ondelete` esplicito su stazioni

**File**:
- `backend/src/colazione/models/corse.py:90-91` — `corsa_commerciale.codice_origine/destinazione` → `stazione`
- `backend/src/colazione/models/corse.py:173-174` — `corsa_materiale_vuoto.codice_origine/destinazione` → `stazione`
- `backend/src/colazione/models/turni_pdc.py:75-76` — `turno_pdc_giornata.stazione_inizio/fine` → `stazione`
- `backend/src/colazione/models/turni_pdc.py:107-110` — `turno_pdc_blocco.stazione_da/a_codice` → `stazione`

Queste FK non hanno `ondelete` → PostgreSQL usa `NO ACTION` (default),
che può causare errori cryptici ("violazione FK") invece di comportamento
semanticamente esplicito. Le altre FK nel progetto hanno già `ondelete` corretto
(vedi `giri.py`, `turni_pdc.py:53`). Questa è un'inconsistenza sistematica.

**Fix**: aggiungere `ondelete="RESTRICT"` per `corse_commerciale.codice_origine/destinazione`
e `ondelete="SET NULL"` per le stazioni nelle giornate/blocchi PdC.

---

### IMP-06 — Enum-like columns senza CHECK constraint nel DB

**File**: `backend/src/colazione/models/turni_pdc.py:57, 74, 97`

```python
stato: Mapped[str] = mapped_column(String(20), default="bozza")
variante_calendario: Mapped[str] = mapped_column(String(20), default="LMXGV")
tipo_evento: Mapped[str] = mapped_column(String(20))
```

Nessun CHECK constraint: il DB accetta valori arbitrari. I modelli che già
hanno CHECK corretto (es. `stato_pipeline_pdc`, `builder_mode`, `builder_version`)
mostrano il pattern giusto. Queste colonne ne sono prive.

Tabelle impattate: `turno_pdc.stato`, `turno_pdc_giornata.variante_calendario`,
`turno_pdc_blocco.tipo_evento`, `giro_materiale.stato`, `persona.profilo`,
`assegnazione_giornata.stato`, `indisponibilita_persona.tipo`,
`programma_materiale.stato`.

**Fix**: migration Alembic batch con `ALTER TABLE ... ADD CONSTRAINT CHECK(...)`.

---

### IMP-07 — JSONB strutturati senza schema Pydantic

**File**:
- `backend/src/colazione/models/anagrafica.py:97` — `azienda.normativa_pdc_json`
- `backend/src/colazione/models/giri.py:77` — `giro_materiale.generation_metadata_json`
- `backend/src/colazione/models/turni_pdc.py:56` — `turno_pdc.generation_metadata_json`

Questi campi sono `dict[str, Any]` (JSONB). Se una chiave cambia nome o tipo,
non c'è nessuna validazione che lo rilevi. Per confronto, `filtri_json` e
`composizione_json` in `programmi.py` hanno già lo schema Pydantic documentato.

**Fix**: definire TypedDict o Pydantic BaseModel per ogni campo:

```python
class TurnoPdcGenerationMetadata(TypedDict, total=False):
    fr_giornate: list[int]
    is_ramo_split: bool
    multi_turno_progressivo: int | None
    riposo_intraturno_violazioni: list[str]
```

---

### IMP-08 — FR cap multi-turno: dormite T-FT non contate

**File**: `backend/src/colazione/domain/builder_pdc/multi_turno.py:1080-1136`

I segmenti senza deposito valido generano turni T-FT con `dormita_partenza=True`.
Nessuna validazione che il totale dormite rispetti `FR_MAX_PER_SETTIMANA=1` e
`FR_MAX_PER_28GG=3` (definiti in `builder.py:68-69`). Il counter FR esiste per il
builder MVP single-turno, ma `multi_turno.py` non lo aggrega a livello ciclo.

**Fix**: in `_persisti_segmenti()`, contare le dormite totali cross-segmento
e propagarle come `violazioni_ciclo_extra` se superano i cap.

---

### IMP-09 — `except Exception` mascherano bug reali nel builder giro

**File**: `backend/src/colazione/domain/builder_giro/builder.py:1664, 1690`

```python
# builder.py:1664
except Exception as exc:  # noqa: BLE001
    warnings.append(f"Carica dotazione fallita; capacity check skippato")
    pezzi_per_tipo = {}

# builder.py:1690
except Exception as exc:  # noqa: BLE001
    warnings.append(f"Costruzione lookup durate vuoto fallita")
    lookup_durate = {}
```

`except Exception` cattura `AttributeError`, `ImportError`, `TypeError`,
`IntegrityError` — qualsiasi bug reale diventa un warning silente con fallback
applicato. Il `# noqa: BLE001` indica consapevolezza del problema ma non lo risolve.

**Fix**: specificare le eccezioni attese:

```python
# Per errori DB:
except (OperationalError, ProgrammingError) as exc:
    logger.warning("Lookup durate DB failed: %s — fallback 60min", exc)
    lookup_durate = {}
# Rilancia su AttributeError (bug codice), non nascondere
```

---

### IMP-10 — `n_branches: list[int]` passato per referenza in ricorsione

**File**: `backend/src/colazione/domain/builder_giro/backtracking_esplorativo.py:262, 274`

```python
def _estendi_ricorsivo(
    ...,
    n_branches: list[int],  # ← mutabile passato per riferimento
    ...
) -> list[_StatoBacktracking]:
    n_branches[0] += 1  # ← side effect implicito
```

È un "return implicito" tramite side effect su lista mutabile. Antipattern classico.
Se un futuro chiamante riusa la stessa lista per due run paralleli, i contatori
si sovrappongono. Non ha impatto oggi (la lista è creata fresh ogni call al riga 525),
ma degrada con qualsiasi refactor che aggiunge parallelismo.

**Fix**: `_estendi_ricorsivo` deve ritornare `tuple[list[_StatoBacktracking], int]`
(risultati, n_nodi_visitati) e il chiamante somma:

```python
def _estendi_ricorsivo(...) -> tuple[list[_StatoBacktracking], int]:
    ...
    risultati, n_figli = _estendi_ricorsivo(...)
    return totale, 1 + n_figli
```

---

### IMP-11 — `api/giri.py` God File: 4422 righe, 67 funzioni

**File**: `backend/src/colazione/api/giri.py`

4422 righe con 67 funzioni/classi. Mixare schema Pydantic, business logic di
dominio, query ORM e routing HTTP nello stesso file viola SRP. Già `api/programmi.py`
è a 2485 righe. Nessun altro file API è oltre le 500 righe.

**Fix proposto** (split in 4 moduli):
- `api/giri_core.py` — CRUD base + generazione (endpoint attuali righe 1-1600)
- `api/giri_editor.py` — riempi_gap, inserisci_corsa_manuale, sposta_blocco (righe 970-3400)
- `api/giri_aggregazione.py` — aggrega_modifica, wizard_da_linee (righe 1593-2275)
- `api/giri_gantt.py` — cerca_treno, corse_non_coperte, gantt_unificato (righe 514-970)

---

### IMP-12 — `TurnoPdcDettaglioRoute.tsx`: 1722 righe, logica dominio inline

**File**: `frontend/src/routes/pianificatore-giro/TurnoPdcDettaglioRoute.tsx`

Funzioni di dominio definite direttamente nel componente UI:
- `computeSostaNotturna()` (riga ~509) — calcolo durata riposo inter-giornata
- `parseTimeToMin()` (riga ~1484) — parsing "HH:MM" → minuti
- `minToPx()` (riga ~1495) — conversione minuti → pixel timeline
- `formatHM()` (riga ~1501) — formato "5h30"

Queste funzioni appartengono a `frontend/src/lib/time.ts`, non al componente.
La UI diventa inutilmente testabile solo con render completo.

**Fix**: estrarre in `lib/time.ts`:

```typescript
export function parseTimeToMin(t: string | null): number | null { ... }
export function computeSostaNotturna(fin: string | null, ini: string | null): ... { ... }
export function formatHM(min: number): string { ... }
```

---

### IMP-13 — `GiroDettaglioRoute.tsx` 4389 righe: God Component

**File**: `frontend/src/routes/pianificatore-giro/GiroDettaglioRoute.tsx`

Il file più grande del frontend con 4389 righe. Contiene:
1. React Query + state management globale Gantt
2. 5+ sub-componenti definiti inline (GiroRow, BloccoSegment, Dialog*)
3. Drag & drop logic (@dnd-kit)
4. Configurazione blocchi inline

Il splitting è non banale ma urgente prima che il file raggiunga i 6000+.

**Fix**: estrarre almeno i componenti Dialog e il Gantt rendering in file separati.

---

### IMP-14 — `test_a1_cross_pdc.py` referenziato ma inesistente

**File**: `backend/tests/test_registro_vetture.py:6`

```python
# test_registro_vetture.py:6
# integration end-to-end è in test_a1_cross_pdc.py
```

Il file `backend/tests/test_a1_cross_pdc.py` non esiste. Lo scenario
"due turni concorrenti che cercano la stessa vettura, secondo escluso da registro"
è criticamente non testato end-to-end (il finding S2 del ciclo SEVERO si era
soffermato su questo).

**Fix**: creare il file o integrare il test in `test_piano_alpha_integration.py`
come scenario #5.

---

### IMP-15 — Fixture `_ensure_depot_test` duplicata in 2 file

**File**:
- `backend/tests/test_turno_pdc_validazioni_api.py:59-86`
- `backend/tests/test_pianificatore_pdc_api.py:154-175`

Stessa logica "get-or-create depot TEST_DEPOT_PD2" duplicata con leggere variazioni.
Se si aggiunge un campo NOT NULL a `depot`, va aggiornata in entrambi.

**Fix**: estrarre in `backend/tests/conftest.py`:

```python
@pytest.fixture
async def test_depot(session: AsyncSession) -> int:
    row = (await session.execute(
        text("SELECT id FROM depot WHERE codice = 'TEST_DEPOT_PD2'")
    )).first()
    if row is not None:
        return int(row[0])
    await session.execute(text(
        "INSERT INTO depot (azienda_id, codice, display_name, is_attivo) "
        "VALUES (:az, 'TEST_DEPOT_PD2', 'Test Depot MR-PD2', true)"
    ), {"az": az_id})
    await session.flush()
    return int((await session.execute(...)).first()[0])
```

---

### IMP-16 — `xfail` senza reference a issue/MR che li risolverà

**File**: `backend/tests/test_violazioni_normative_pdc.py:79, 119, 161`

```python
@pytest.mark.xfail(strict=True, reason="MR-PD3 builder deposito-first che spezza per costruzione")
```

Il reason è generico: se MR-PD3 viene rinominata o splittata, il test diventa
orfano senza tracciabilità. Pattern corretto (già usato in alcuni test):
citare l'entry TN-UPDATE dove il fix è pianificato.

**Fix**:
```python
@pytest.mark.xfail(
    strict=True,
    reason="NORMATIVA §5 CV: builder usa sempre ACC 40+40 (CR-01). "
           "Fix pianificato in MR post-CR-2026-05-14."
)
```

---

### IMP-17 — CORS: `allow_methods=["*"]` e `allow_headers=["*"]`

**File**: `backend/src/colazione/main.py:49-50`

```python
allow_methods=["*"],   # ← DELETE su endpoint sbagliati via CORS bypass
allow_headers=["*"],   # ← header arbitrari accettati
```

**Fix**: specificare esplicitamente:

```python
allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
allow_headers=["Content-Type", "Authorization"],
max_age=600,
```

---

### IMP-18 — `db_bound helper` nel domain layer: `durata_vuoto.py`

**File**: `backend/src/colazione/domain/builder_giro/durata_vuoto.py:227-309`

Le funzioni `_carica_durate_corse_programma()` e `costruisci_lookup_durate()`
usano SQLAlchemy direttamente nel domain layer, mescolando ORM con logica di
aggregazione pura. L'architettura di riferimento (`ARCHITETTURA-BUILDER-V4.md`)
prevede un adapter layer separato.

Il domain layer dovrebbe ricevere dati già caricati e operare su strutture pure.

**Fix**: spostare le query in `backend/src/colazione/adapters/builder_repo.py`
(da creare) e passare `list[tuple[str, str, int]]` alla funzione di aggregazione.
Costo: ~2h refactor. La logica di aggregazione pura (`_aggrega_per_coppia()`) è
già separata e corretta.

---

## MINORI

### MIN-01 — `key={i}` su liste mutabili nel frontend

**File**:
- `frontend/src/routes/pianificatore-giro/GeneraGiriDialog.tsx:666, 681, 749`
- `frontend/src/routes/pianificatore-giro/GeneraTurnoPdcDialog.tsx:323, 341`
- `frontend/src/routes/pianificatore-giro/TurnoPdcDettaglioRoute.tsx:448, 465`
- `frontend/src/routes/pianificatore-giro/ProgrammaGiriRoute.tsx:1383`

Chiavi React basate sull'indice su liste che possono essere riordinate
(violazioni, warning, righe Gantt). Per elementi statici (errori di una
singola operazione) è accettabile. Per il Gantt row (riga 285 di
`GanttUnificatoRoute.tsx`) dove i blocchi si riordinano, è un bug reale.

**Fix per il caso Gantt**: `key={`row-${row.map(c => c.corsa_id).join('-')}`}`.
Per le liste di messaggi statici (violazioni/warning): `key={`v-${i}-${v.slice(0,15)}`}`.

---

### MIN-02 — `import` dinamico di `GiriEsistentiError` per evitare ciclo

**File**: `backend/src/colazione/domain/builder_pdc/multi_turno.py:604-606`

```python
# Inside function to avoid circular import
from colazione.domain.builder_pdc.giornata_base import GiriEsistentiError
```

Import a runtime dentro la funzione per spezzare un ciclo di dipendenze.
Antipattern: difficile da tracciare, mypy può ignorarlo, non si vede nel top-level.

**Fix**: creare `backend/src/colazione/domain/builder_pdc/exceptions.py` con
`GiriEsistentiError` e tutti gli altri errori di dominio, poi importare da lì.

---

### MIN-03 — `varianti_calendariali.py` export inutilizzato `Counter`

**File**: `backend/src/colazione/domain/builder_giro/varianti_calendariali.py:293`

```python
_ = Counter  # noqa: F841 — riservato per estensioni
```

Un nome `_` che punta a `Counter` per "riservarlo". Non è un pattern riconoscibile;
un futuro sviluppatore non capisce l'intento. Se `Counter` servirà in futuro, lo si
importa quando serve.

**Fix**: rimuovere la riga. `# noqa: F841` è un segnale che il codice sa di essere
"spazzatura" ma lo mantiene ugualmente.

---

### MIN-04 — `builder.py` variabile `_ = festivita` e `_ = calcola_etichetta_giro`

**File**: `backend/src/colazione/domain/builder_giro/builder.py:2757-2758`

```python
_ = festivita  # noqa: F841 (reservato per uso futuro)
_ = calcola_etichetta_giro  # noqa: F841 (export pubblico mantenuto)
```

Se `calcola_etichetta_giro` è un export pubblico, va in `__all__` del modulo.
Se `festivita` è un parametro non ancora usato, va annotato `# future: §X.Y`.
La forma `_ = ...` è ambigua e confonde i type checker.

**Fix**: aggiungere `__all__` al modulo con l'export esplicito, rimuovere le righe `_`.

---

### MIN-05 — Timing attack su login (enumerazione username)

**File**: `backend/src/colazione/api/auth.py:54`

```python
if user is None or not user.is_active or not verify_password(req.password, user.password_hash):
```

Lo short-circuit su `user is None` è più veloce della chiamata `verify_password()`.
Un attacker può misurare tempi per sapere se l'username esiste.

**Fix** (minore perché l'app non è multi-utente pubblico):

```python
# Dummy hash per constant-time anche su utente inesistente
DUMMY_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt())
check_hash = user.password_hash if user else DUMMY_HASH
password_ok = verify_password(req.password, check_hash)
if user is None or not user.is_active or not password_ok:
    raise HTTPException(...)
```

---

### MIN-06 — `_StubDepot` non frozen nei test: state leakage silente

**File**: `backend/tests/test_deposito_first.py:85-90`

```python
@dataclass
class _StubDepot:
    id: int
    stazione_principale_codice: str
    display_name: str
```

Se un test modifica `stub.stazione_principale_codice`, il cambiamento persiste
per il test successivo che riusa lo stesso stub. Antipattern silente.

**Fix**: `@dataclass(frozen=True)`.

---

### MIN-07 — Soft-delete inconsistente: solo `corsa_commerciale` ha `deleted_at`

**File**: tutti i modelli

`corsa_commerciale` ha `is_cancellata`, `cancellata_at`, `cancellata_da_run_id`
(migration 0034). Tutte le altre entità con `is_attiva`/`stato` non hanno
timestamp. Se serve un audit "quando è stato disattivato X", è impossibile.

**Fix**: non è urgente ma documentare la policy: aggiungere un commento in
`docs/SCHEMA-DATI-NATIVO.md` che spiega perché solo `corsa_commerciale` ha
soft-delete completo e quali tabelle ne potrebbero avere bisogno in futuro
(`depot`, `persona`, `localita_manutenzione`).

---

### MIN-08 — `health` endpoint espone versione app

**File**: `backend/src/colazione/main.py:53-56`

```python
@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
```

`version` nell'health check espone la versione dell'app a qualsiasi scanner.
Per un'app interna potrebbe essere accettabile, ma in produzione è information
disclosure non necessaria.

**Fix**: `return {"status": "ok"}`. La versione può vivere in un endpoint
separato autenticato `/api/system/version`.

---

### MIN-09 — `CORS allow_origins` non validato al boot

**File**: `backend/src/colazione/config.py:47`

```python
cors_allow_origins: str = "http://localhost:5173"
```

Se `CORS_ALLOW_ORIGINS` è impostato a `"*"` per debugging, non c'è nessun
validatore che lo rilevi e lo rifiuti in produzione. Un validator simile a
quello proposto per `jwt_secret` (CR-03) evita configurazioni accidentalmente
permissive.

---

## Riepilogo

| ID | Area | Gravità | File principale | Fix stimato |
|----|------|---------|-----------------|-------------|
| CR-01 | Normativa §5 | CRITICO | `split_cv.py:28` | 3-4h |
| CR-02 | Runtime API | CRITICO | `multi_turno.py:428,478` | 1h |
| CR-03 | Sicurezza auth | CRITICO | `config.py:34` | 30min |
| CR-04 | Sicurezza XSS | CRITICO | `main.py:45` / `tokenStorage.ts:8` | 2h |
| CR-05 | Persistenza DB | CRITICO | tutti i modelli `updated_at` | 1h + migration |
| CR-06 | Normativa §8 | CRITICO | `multi_turno.py:158` / `builder.py:368` | 1h |
| IMP-01 | Sicurezza auth | IMPORTANTE | `config.py:39` | 15min |
| IMP-02 | Sicurezza auth | IMPORTANTE | `auth.py:44` | 2h |
| IMP-03 | Sicurezza auth | IMPORTANTE | `auth.py` (mancante) | 3h |
| IMP-04 | Performance | IMPORTANTE | `anagrafiche.py:120` | 2h |
| IMP-05 | Schema DB | IMPORTANTE | `corse.py:90` / `turni_pdc.py:75` | 1h + migration |
| IMP-06 | Schema DB | IMPORTANTE | `turni_pdc.py:57,74,97` | 1h + migration |
| IMP-07 | Qualità | IMPORTANTE | `anagrafica.py:97` / `giri.py:77` | 2h |
| IMP-08 | Normativa §10 | IMPORTANTE | `multi_turno.py:1080` | 2h |
| IMP-09 | Qualità | IMPORTANTE | `builder_giro/builder.py:1664,1690` | 30min |
| IMP-10 | Qualità | IMPORTANTE | `backtracking_esplorativo.py:262` | 1h |
| IMP-11 | Architettura | IMPORTANTE | `api/giri.py` (4422 righe) | 4-6h |
| IMP-12 | Architettura | IMPORTANTE | `TurnoPdcDettaglioRoute.tsx` (1722 righe) | 2h |
| IMP-13 | Architettura | IMPORTANTE | `GiroDettaglioRoute.tsx` (4389 righe) | 6-8h |
| IMP-14 | Test | IMPORTANTE | `test_registro_vetture.py:6` | 2h |
| IMP-15 | Test | IMPORTANTE | `test_turno_pdc_validazioni_api.py:59` | 1h |
| IMP-16 | Test | IMPORTANTE | `test_violazioni_normative_pdc.py:79` | 30min |
| IMP-17 | Sicurezza | IMPORTANTE | `main.py:49` | 15min |
| IMP-18 | Architettura | IMPORTANTE | `durata_vuoto.py:227` | 2h |
| MIN-01 | Frontend | MINORE | `GanttUnificatoRoute.tsx:224` | 30min |
| MIN-02 | Qualità | MINORE | `multi_turno.py:604` | 30min |
| MIN-03 | Dead code | MINORE | `varianti_calendariali.py:293` | 5min |
| MIN-04 | Dead code | MINORE | `builder_giro/builder.py:2757` | 15min |
| MIN-05 | Sicurezza | MINORE | `auth.py:54` | 30min |
| MIN-06 | Test | MINORE | `test_deposito_first.py:85` | 5min |
| MIN-07 | Schema DB | MINORE | modelli `is_attiva` | doc only |
| MIN-08 | Sicurezza | MINORE | `main.py:53` | 5min |
| MIN-09 | Sicurezza | MINORE | `config.py:47` | 30min |

**Conteggi**: 6 CRITICI · 18 IMPORTANTI · 9 MINORI = **33 finding totali**

---

## Note di metodo

- Tutti i finding sono stati verificati aprendo il file e la riga citata.
  Nessun "probabilmente è così".
- I fix proposti sono concreti e scrivibili. Dove la stima è > 4h, indicato
  esplicitamente perché giustifica scope separato.
- CR-01 (CV gap < 65) e CR-06 (refezione bloccante) sono violazioni normative
  attive: i turni generati oggi possono essere fuori normativa. Priorità assoluta.
- IMP-11 (giri.py 4422 righe) e IMP-13 (GiroDettaglioRoute.tsx 4389 righe)
  sono debiti tecnici strutturali: non bloccano niente oggi ma ogni nuovo
  endpoint/componente aggiunto li peggiora.
