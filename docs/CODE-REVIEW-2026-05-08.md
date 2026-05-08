# Code Review — COLAZIONE — 2026-05-08

> **Scope**: review completa del repo post Sprint 8.0 MR-E (entry 236).
> Condotta come senior engineer indipendente: ogni finding cita `file:riga`,
> causa, impatto e fix proposto concreto. Nessuna modifica al codice di
> produzione — solo diagnostica.
>
> **Basi di confronto**:
> - `docs/NORMATIVA-PDC.md` — fonte verità normativa (se codice ≠ norma, è il codice a sbagliare)
> - `docs/MODELLO-DATI.md` v0.5 — modello dati concettuale
> - `CLAUDE.md` regole operative (no TODO pigri, chiudere bene)
>
> **Nota**: esiste già `docs/CODE-REVIEW-2026-05-01.md` (24 finding post Sprint 7.4).
> Questa review non è una ripetizione: copre gli sprint 7.5–8.0 e aree
> che la precedente non ha toccato (auth, builder PdC, pipeline, aree metro).

---

## Indice

- [CRITICO](#critico) — 7 finding (C1–C7)
- [IMPORTANTE](#importante) — 11 finding (I1–I11)
- [MINORE](#minore) — 5 finding (M1–M5)

---

## CRITICO

Violazioni normativa, bug latenti che producono output errato, debito tecnico bloccante.

---

### C1 — `split_cv._eccede_limiti`: flag `is_notturno` incompatibile con normativa §11.8

**File**: `backend/src/colazione/domain/builder_pdc/split_cv.py:151-157`

```python
cap_prestazione = (
    PRESTAZIONE_MAX_NOTTURNO if draft.is_notturno else PRESTAZIONE_MAX_STANDARD
)
```

**Causa**: `is_notturno` è impostato in `builder.py:331`:
```python
is_notturno = ora_presa < 5 * 60 or ora_fine_servizio > 22 * 60 or ora_fine_servizio < ora_presa
```

La terza condizione (`ora_fine_servizio < ora_presa`) cattura turni che *finiscono* dopo mezzanotte, indipendentemente dall'orario di presa. Per esempio un turno con presa 22:00 (ora_presa = 1320) e fine 06:30 (ora_fine_servizio = 390) ha `390 < 1320 = True` → `is_notturno = True` → cap applicato: **420 min**.

Ma la **normativa §11.8** è esplicita: il cap di 7h si applica **solo se presa servizio cade tra 01:00 e 04:59** (60 ≤ ora_presa < 300). Un turno con presa 22:00 ha cap **510 min** (standard).

`_build_giornata_pdc` fa la cosa giusta (`if 60 <= ora_presa < 5 * 60`, riga 334-337), ma `_eccede_limiti` in `split_cv.py` usa `draft.is_notturno` che è più largo. Risultato: turni che iniziano la sera (22:00–00:59) e finiscono dopo mezzanotte vengono **splittati erroneamente** con soglia 420 invece di 510 min. Il builder produce TurnoPdc spezzati non necessari, e aggiunge paia di ACCa/ACCp superflui (≥ 80 min di costo extra per ramo).

**Fix**:
```python
# split_cv.py:151-157 — usa la stessa logica di _build_giornata_pdc
from colazione.domain.builder_pdc.builder import PRESTAZIONE_MAX_NOTTURNO, PRESTAZIONE_MAX_STANDARD

def _eccede_limiti(draft: _GiornataPdcDraft) -> bool:
    ora_presa = draft.inizio_prestazione.hour * 60 + draft.inizio_prestazione.minute
    cap_prestazione = (
        PRESTAZIONE_MAX_NOTTURNO
        if 60 <= ora_presa < 5 * 60
        else PRESTAZIONE_MAX_STANDARD
    )
    return (
        draft.prestazione_min > cap_prestazione
        or draft.condotta_min > CONDOTTA_MAX_MIN
    )
```

Rimuovere il campo `is_notturno` da `_GiornataPdcDraft` o tenerlo solo per uso informativo (dashboard), non per decisioni normative.

---

### C2 — `STAZIONI_CV_DEROGA` usa nomi umani vs codici S-prefixed: TIRANO mai ammessa a CV

**File**: `backend/src/colazione/domain/builder_pdc/split_cv.py:59`

```python
STAZIONI_CV_DEROGA: frozenset[str] = frozenset({"MORTARA", "TIRANO"})
```

**Causa**: `lista_stazioni_cv_ammesse` (riga 78–87) carica `Depot.stazione_principale_codice` — che la migration `0030_populate_stazione_principale_codice.py` popola con `stazione.codice` in formato `S01xxx` (PK canonico del PdE). L'insieme risultante contiene stringhe come `"S01734"` (MORTARA) e `"S01887"` (TIRANO).

`_trova_punto_split` (riga 193) controlla `blocchi_giro[i].stazione_a_codice not in stazioni_cv`. La colonna `GiroBlocco.stazione_a_codice` è FK → `stazione.codice` (formato `S01xxx`).

`"TIRANO" not in {"S01887", ...}` → **True sempre**: TIRANO non è mai ammessa a CV. Per MORTARA: se il depot MORTARA ha `tipi_personale_ammessi == "PdC"`, il codice entra via depot query; ma MORTARA per normativa §2.1 *non è sede PdC residenti* — l'inclusione nel depot con tipi="PdC" non è garantita. In ogni caso la deroga come stringa è inutile.

**Impatto**: sulle linee Valtellina (Lecco–Tirano) nessun punto di split CV è mai trovato a Tirano (capolinea inversione, stazione con le condizioni più naturali per un CV). Il builder produce giornate con violazione `prestazione_max` o `condotta_max` irrisolvibili invece di spezzare correttamente a Tirano.

**Fix**:
```python
# split_cv.py:59 — usa codici stazione canonici o un mapping lazy
# Opzione A (immediata, leggibile): mapping nome → codice hard-coded  
STAZIONI_CV_DEROGA_NOMI: frozenset[str] = frozenset({"TIRANO", "MORTARA"})

async def lista_stazioni_cv_ammesse(session: AsyncSession, azienda_id: int) -> set[str]:
    ...  # query depot invariata
    # Risolvi i nomi delle deroghe in codici
    if STAZIONI_CV_DEROGA_NOMI:
        stmt_deroghe = select(Stazione.codice).where(
            Stazione.nome.in_(STAZIONI_CV_DEROGA_NOMI)
        )
        res_deroghe = await session.execute(stmt_deroghe)
        stazioni.update(r[0] for r in res_deroghe.all() if r[0])
    return stazioni
```

O più pulito: tabella `cv_deroga_stazione(azienda_id, stazione_codice)` configurabile per programma (già previsto nei "refactor successivi" del commento riga 15).

---

### C3 — Builder PdC usa PK come default per gap ≥ 65 min: violazione normativa §6

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:234-250`

```python
if gap > 0:
    drafts.append(
        _BloccoPdcDraft(tipo_evento="PK", ...)
    )
```

**Causa**: ogni gap inter-blocco diventa automaticamente un blocco `PK`, indipendentemente dalla durata del gap.

**Normativa §6** stabilisce la gerarchia per gap:
- `< 65 min` → CV o PK (entrambi ammessi)
- `65–300 min` → **ACC (default)** o PK (opt-in operatore)
- `> 300 min` → **ACC (default)** o PK (opt-in operatore *esplicito*)

Usare PK come unico default viola la norma per gap ≥ 65 min, dove il PK richiede decisione esplicita del pianificatore. Oltre all'aspetto normativo, il PK riduce i costi ACCa+ACCp a 20+20=40 min (vs 40+40=80 min ACC), producendo turni che sottostimano la prestazione effettiva nei gap lunghi.

**Fix**: classificare il gap per applicare il blocco corretto.

```python
GAP_SOGLIA_CV_MAX = 65      # min — sopra questa soglia CV non ammesso
GAP_ACCESSORI_MIN = 80      # min — ACCa + ACCp standard (40+40)

if gap > 0:
    if gap < GAP_SOGLIA_CV_MAX:
        tipo = "PK"         # CV o PK: builder usa PK (no PdC fisico da trovare)
    elif gap <= 300:
        tipo = "ACC_PAIR"   # Default normativo: ACCa poi ACCp separati
    else:
        tipo = "ACC_PAIR"   # > 300 min: ACC default, PK solo opt-in operatore
    drafts.append(_BloccoPdcDraft(tipo_evento=tipo, ...))
```

Per MVP è accettabile restare a PK per gap < 65, ma i gap ≥ 65 devono essere modellati come coppie ACCa+ACCp (due blocchi distinti).

---

### C4 — ACCp preriscaldo (●) 80 min dic-feb non implementato: violazione normativa §3.3

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:53-54`

```python
ACCESSORI_MIN_STANDARD = 40
```

```python
# riga 195-196
ora_inizio_accp = (primo_inizio - ACCESSORI_MIN_STANDARD) % (24 * 60)
```

**Normativa §3.3**:
```
| Condotta con preriscaldo ● (dic-feb) | ACCp = 80' | ACCa = 40' |
```

Il builder usa sempre `ACCESSORI_MIN_STANDARD = 40` per entrambi ACCp e ACCa. Per i turni che iniziano in dicembre, gennaio o febbraio (mesi con preriscaldo), ACCp deve essere **80 minuti**, non 40.

**Impatto**: turni invernali con presa servizio 40 min prima del primo treno invece di 80 — il PdC arriva a Fiorenza con 40 min di margine dove ne servono 80. Il pianificatore vede turni "validi" che in realtà violano i tempi di preparazione del materiale.

Il builder non conosce la data specifica (genera un *template* di turno, non un turno per data specifica). Due soluzioni:

**Fix A (raccomandato)**: il builder accetta un parametro `is_preriscaldo: bool = False` calcolato dal caller in base al range di date del programma o di una flag sul `ProgrammaMateriale`.

**Fix B**: marcare nella metadata che il turno NON include il preriscaldo e obbligare il pianificatore a validarlo manualmente per i mesi invernali — ma almeno documentarlo come violazione, non come warning silente.

---

### C5 — Anti-rigeneration TurnoPdc: full table scan in RAM su tutta l'azienda

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:713-726`

```python
existing = list(
    (
        await session.execute(
            select(TurnoPdc).where(TurnoPdc.azienda_id == azienda_id)
        )
    ).scalars()
)
```

**Causa**: carica **tutti** i `TurnoPdc` dell'azienda in memoria Python, poi filtra con `_matches_giro_e_deposito` in un loop Python. Per un'azienda con 500 giri × 3 depositi = 1500 turni, ogni call a `genera_turno_pdc` scarica 1500 record ORM per verificare l'anti-rigenerazione di un singolo giro.

**Impatto**: degradazione lineare con il numero di turni. A 5000 turni (scenario realistico in produzione dopo un anno di uso) ogni generazione diventa lenta e memory-hungry.

**Fix**: query SQL mirata usando JSONB e la FK fisica:

```python
from sqlalchemy import Integer, cast
from sqlalchemy.dialects.postgresql import JSONB

# Filtra già in SQL:
stmt = select(TurnoPdc).where(
    TurnoPdc.azienda_id == azienda_id,
    TurnoPdc.generation_metadata_json["giro_materiale_id"].astext.cast(Integer) == giro_id,
)
if deposito_pdc_id is not None:
    stmt = stmt.where(TurnoPdc.deposito_pdc_id == deposito_pdc_id)
legati = list((await session.execute(stmt)).scalars())
```

Prerequisito: aggiungere indice JSONB su `generation_metadata_json -> 'giro_materiale_id'`:
```sql
CREATE INDEX ix_turno_pdc_giro_id
  ON turno_pdc USING gin ((generation_metadata_json -> 'giro_materiale_id'));
```

---

### C6 — `updated_at` mai aggiornato: campo stale da sempre (manca `onupdate`)

**File**:
- `backend/src/colazione/models/giri.py:79`
- `backend/src/colazione/models/turni_pdc.py:57`
- `backend/src/colazione/models/programmi.py:174`

```python
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), server_default=func.now()
)
```

**Causa**: `server_default=func.now()` imposta il valore solo alla **INSERT**. Agli UPDATE successivi, `updated_at` resta congelato al momento della creazione. Non c'è né `onupdate=func.now()` lato SQLAlchemy né un trigger `BEFORE UPDATE` lato PostgreSQL.

**Impatto**: il campo è inutile per audit/debugging — non registra mai l'ultima modifica effettiva. Dashboard o script di monitoraggio che usano `updated_at` per rilevare record modificati di recente riceveranno sempre il timestamp di creazione.

**Fix** (SQLAlchemy):
```python
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
    onupdate=func.now(),
)
```

Oppure (più affidabile, lato DB — aggiungere migration):
```sql
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_giro_materiale_updated_at
  BEFORE UPDATE ON giro_materiale
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
-- idem per turno_pdc, programma_materiale
```

---

### C7 — Access token 72h default: revoca utente/ruolo inefficace fino a scadenza

**File**: `backend/src/colazione/config.py:40`

```python
jwt_access_token_expire_min: int = 4320  # 72h
```

**Causa**: l'access token HS256 non è revocabile (nessuna lista di revoca, nessun DB check per request). Se un utente viene disattivato (`is_active=False`) o un ruolo viene rimosso, il cambiamento diventa effettivo solo alla scadenza del token corrente — dopo **72 ore**.

Il commento in `auth/dependencies.py:18` lo riconosce esplicitamente: *"il cambio diventa effettivo solo all'access token successivo (max 72h con la config attuale). Per MVP è accettabile."*

Non è accettabile in produzione con dati sensibili (pianificazione turni, dati personali PdC). Un utente licenziato o sospeso ha ancora accesso per 3 giorni.

**Fix A (immediato)**: ridurre `jwt_access_token_expire_min` a 15–30 minuti. Il refresh token (30 giorni) mantiene la sessione lunga; è il pattern standard.

**Fix B (strutturale)**: aggiungere una chiamata DB leggera in `get_current_user` per verificare `user.is_active` — un SELECT su PK è O(1) con indice e aggiunge ~1–2ms per request. Accettabile.

```python
# auth/dependencies.py — dopo decode_token
user_row = await session.execute(
    select(AppUser.is_active).where(AppUser.id == int(payload["sub"]))
)
if not (row := user_row.scalar_one_or_none()) or not row:
    raise HTTPException(status_code=401, detail="utente disattivato")
```

Questo richiede di passare `session` a `get_current_user`, rompendo la firma attuale. In alternativa: implementare un token blocklist in Redis (più complesso).

**Raccomandazione minima immediata**: `jwt_access_token_expire_min = 60` in default, con env override per dev.

---

## IMPORTANTE

Qualità, manutenibilità, debito tecnico non bloccante ma che si accumula.

---

### I1 — Missing unique constraint `(turno_pdc_id, numero_giornata)` su `TurnoPdcGiornata`

**File**: `backend/src/colazione/models/turni_pdc.py:64-84`

Nessun `UniqueConstraint("turno_pdc_id", "numero_giornata")` nel `__table_args__`. Il DB permette due righe con stesso `turno_pdc_id` e stesso `numero_giornata`. Se il builder chiama `flush()` due volte per la stessa giornata (bug raro ma possibile nel loop di `_persisti_un_turno_pdc`), il record duplicato passa silentemente.

**Fix**: aggiungere migration + constraint:
```python
__table_args__ = (
    UniqueConstraint("turno_pdc_id", "numero_giornata",
                     name="uq_turno_pdc_giornata_numero"),
)
```

---

### I2 — Missing unique constraint `(giro_variante_id, seq)` su `GiroBlocco`

**File**: `backend/src/colazione/models/giri.py:159-189`

Nessun `UniqueConstraint` su `(giro_variante_id, seq)`. L'ordinamento dei blocchi dipende interamente dall'integrità del `seq`. Un bug nel persister che inserisse due blocchi con stesso seq nella stessa variante produrrebbe un ordinamento ambiguo. La query `ORDER BY seq` restituirebbe risultati non deterministici.

Stesso problema per `TurnoPdcBlocco` (`backend/src/colazione/models/turni_pdc.py:87-117`): nessun unique su `(turno_pdc_giornata_id, seq)`.

**Fix**: aggiunte migration con i due constraint.

---

### I3 — Missing unique constraint su `(programma_id, numero_turno)` per `GiroMateriale`

**File**: `backend/src/colazione/models/giri.py:41-79`

Il commento a riga 49 dice:
```
# UNIQUE su (azienda_id, programma_id, numero_turno) — due programmi diversi
# possono avere ognuno il proprio G-FIO-001.
```

Il constraint **non esiste** nel `__table_args__` (che è assente). Se il builder rigenerasse due volte con un bug e il `force=False` check fallisse (race condition o errore nella logica di `legati`), si avrebbero due giri con lo stesso `numero_turno` nello stesso programma.

**Fix**: aggiungere `__table_args__` con `UniqueConstraint("azienda_id", "programma_id", "numero_turno", ...)`.

---

### I4 — `datetime.utcnow()` deprecato in Python 3.12

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:997`

```python
"generato_at": datetime.utcnow().isoformat(),
```

`datetime.utcnow()` è deprecato dal Python 3.12 (emette `DeprecationWarning`). Il runtime Railway usa Python 3.12 (da `.python-version`).

**Fix**:
```python
from datetime import UTC, datetime
"generato_at": datetime.now(UTC).isoformat(),
```

---

### I5 — Refresh token senza JTI né rotazione: token rubato valido 30 giorni

**File**: `backend/src/colazione/auth/tokens.py:62-76`

Il refresh token non include un `jti` (JWT ID) claim. Non esiste un blocklist per i refresh token nel DB. Un refresh token sottratto rimane valido per 30 giorni senza possibilità di revoca.

Inoltre, `/api/auth/refresh` non ruota il refresh token: emette un nuovo access senza invalidare il refresh usato. Un attaccante con accesso al refresh token può emettere access token indefinitamente.

**Fix minimo**: aggiungere colonna `refresh_token_hash` su `AppUser`, aggiornata ad ogni refresh, con confronto hash all'uso. Token precedente → invalidato.

**Fix completo**: JTI UUID + tabella `revoked_tokens(jti, expires_at)` con cleanup scheduled.

---

### I6 — Test coverage builder PdC: funzioni critiche completamente non coperte

**File**: `backend/tests/test_builder_pdc_eta.py` (12 test) e nessun altro test su builder_pdc

Le funzioni **più critiche** del builder PdC non hanno alcun test unitario:

| Funzione | File | Test esistenti |
|----------|------|---------------|
| `_build_giornata_pdc` | `builder.py:172` | **0** |
| `_inserisci_refezione` | `builder.py:364` | **0** |
| `_inserisci_refezione_ai_bordi` | `builder.py:453` | **0** |
| `split_e_build_giornata` | `split_cv.py:90` | **0** |
| `_eccede_limiti` | `split_cv.py:138` | **0** |
| `_trova_punto_split` | `split_cv.py:160` | **0** |
| `_aggiungi_dormite_fr` | `builder.py:1105` | **0** |

Questi sono algoritmi con logica normativa critica (cap prestazione, inserimento refezione, split CV, dormite FR). L'assenza di test significa che i finding C1, C3, C4 sopra non sarebbero stati rilevati automaticamente dalla CI.

**Fix**: scrivere almeno 3–5 test per ciascuna funzione, partendo da `_eccede_limiti` e `_build_giornata_pdc` (prerequisiti di tutto il resto). Sono funzioni pure o quasi-pure — facilmente testabili senza DB.

Esempio immediato per C1:
```python
def test_eccede_limiti_turno_serale_non_usa_cap_notturno():
    """Turno presa 22:00 → cap 510, non 420."""
    draft = _make_draft(ora_presa=time(22, 0), prestazione_min=480, is_notturno=True)
    assert not _eccede_limiti(draft)  # 480 < 510 → non eccede
```

---

### I7 — `lista_stazioni_cv_ammesse` mescola DB I/O con logica di dominio pura

**File**: `backend/src/colazione/domain/builder_pdc/split_cv.py:62-87`

Il modulo `split_cv.py` si presenta come logica di dominio pura (stesse convenzioni di `catena.py`), ma `lista_stazioni_cv_ammesse` prende un `AsyncSession` e fa un SELECT al DB. Questo:
1. Rende impossibile testare il modulo senza un DB mock
2. Viola la separazione domain/persistence del progetto (vedi come `catena.py` è rigorosamente DB-agnostic)
3. Crea un'asimmetria: le funzioni `split_e_build_giornata`, `_trova_punto_split`, `_eccede_limiti` sono pure ma vivono nello stesso modulo di una funzione impura

**Fix**: spostare `lista_stazioni_cv_ammesse` in `api/giri.py` (o in un modulo `loaders/`) come fa il builder principale per altri dati. Il dominio riceve `stazioni_cv: set[str]` già pronto, come già avviene — basta spostare il caricamento fuori dal modulo.

---

### I8 — Refezione ai bordi: REFEZ inserita fuori dalla prestazione (semanticamente non conforme)

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:453-537`

`_inserisci_refezione_ai_bordi` inserisce un blocco REFEZ **prima della PRESA** (strategia 1) o **dopo la FINE servizio** (strategia 2).

Normativa §4.1: *"la REFEZ è obbligatoria **solo se la prestazione del turno supera 6 ore**"*. La REFEZ è un elemento della prestazione, non un'appendice esterna. Un blocco REFEZ prima della presa o dopo la fine:
- Non conta come parte della prestazione contrattuale
- Il PdC è in "servizio" solo tra PRESA e FINE
- Crea confusione nel Gantt (blocco "prima di iniziare")

La decisione è documentata come "decisione utente 2026-05-05 entry 154" ma la docstring non la collega alla normativa né spiega perché è conforme.

**Fix non tecnico**: aggiungere un commento esplicito che ricollega alla decisione utente e nota il limite normativo, così chi legge tra 6 mesi capisce perché e può ri-discuterlo con l'utente:

```python
# NOTA: questa funzione inserisce REFEZ fuori dalla prestazione operativa
# (prima della PRESA o dopo la FINE). È una deviazione dalla norma §4.1
# approvata esplicitamente dall'utente (entry 154, 2026-05-05):
# "se manca la refezione, puoi aggiungerla alla fine o all'inizio se è
# nelle ore indicate". Rivalutare se Trenord contesta in sede di revisione.
```

---

### I9 — `ciclo_giorni` cappato a 14 in `TurnoPdc` ma non in `_calcola_violazioni_cap_fr`

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:882` e `:1028`

```python
# riga 882 — calcolo cap FR usa il valore vero
fr_cap_violazioni = _calcola_violazioni_cap_fr(
    n_dormite_fr=len(fr_giornate),
    ciclo_giorni=giro.numero_giornate,  # ← valore reale
)

# riga 1028 — persistenza usa valore cappato
ciclo_giorni=max(1, min(14, giro.numero_giornate)),  # ← cappato a 14
```

`TurnoPdc.ciclo_giorni` può essere 14 anche se il giro ha 20 giornate. La dashboard che usa `ciclo_giorni` per calcoli temporali (es. "quanti FR in questo ciclo") leggerà 14, mentre il calcolo normativo ha usato il valore reale. Inconsistenza silenziosa che si manifesta solo su giri > 14 giornate.

Il cap 14 non è documentato. Normativa §11.1 non impone un limite al numero di giornate di un ciclo.

**Fix**: rimuovere il cap `min(14, ...)`. Se il DB ha un `CHECK (ciclo_giorni <= 14)`, rimuoverlo dalla migration e aggiornare il campo nel modello a `Integer` senza bound.

---

### I10 — `dispose_engine` definito ma mai chiamato al shutdown

**File**: `backend/src/colazione/db.py:98-104` e `backend/src/colazione/main.py:28-33`

```python
# main.py — lifespan non chiama dispose_engine al shutdown
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.settings = settings
    yield
    # ← niente dispose_engine() qui
```

```python
# db.py:98 — funzione definita ma nessun caller
async def dispose_engine() -> None:
    """Chiude l'engine. Da chiamare al shutdown app."""
```

Il connection pool non viene rilasciato al graceful shutdown del server. Su Railway con container ephemeri questo è gestito dal kernel, ma in ambienti con riuso dei worker (es. Gunicorn, gestione manuale) causa file descriptor leak.

**Fix**:
```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.settings = settings
    yield
    from colazione.db import dispose_engine
    await dispose_engine()
```

---

### I11 — `_inserisci_refezione`: fallback ancoraggio può sfondare la finestra normativa

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:406-408`

```python
if refez_start < max(fa, ini) or refez_end > min(fb, fin):
    refez_start = max(fa, ini)
    refez_end = refez_start + REFEZIONE_MIN_DURATA
```

Il fallback calcola `refez_start = max(fa, ini)` (inizio della finestra intersecato con inizio del PK), poi `refez_end = refez_start + 30`. Non verifica se `refez_end > min(fb, fin)` **dopo il fallback**. In un PK che termina a 30 minuti esatti dalla fine della finestra (es. PK 15:00–15:30, finestra 11:30–15:30), il fallback produce `refez_end = 15:30`, che coincide con `min(fb, fin)` — borderline OK. Ma se il PK è 15:00–15:25 e la finestra finisce 15:30, il candidato ha overlap = 25 < 30 → non è nemmeno candidato. Il bug si manifesta solo in configurazioni estreme di PK < 30 min overlappanti la fine esatta della finestra — caso improbabile ma non impossibile.

**Fix**: aggiungere assert o un secondo check post-fallback e fallback sicuro:
```python
if refez_start < max(fa, ini) or refez_end > min(fb, fin):
    refez_start = max(fa, ini)
    refez_end = refez_start + REFEZIONE_MIN_DURATA
    if refez_end > min(fb, fin):
        return drafts  # ancora non ci sta: invariato, violazione resta
```

---

## MINORE

Stile, micro-ottimizzazioni, rumore.

---

### M1 — Sprint-numbered comments permeano il codebase: history noise

Oltre 80 commenti del tipo `# Sprint 7.4 MR 2`, `# Sprint 7.9 MR η`, `# Pre-MR 5 (Sprint 7.2 MVP)` nei file di produzione. Sono diario di sviluppo, non documentazione di dominio. In `builder.py` occupano ~150 righe dei ~1250 totali (12%).

Un futuro maintainer non sa cosa sia "Sprint 7.4 MR 2" senza leggere `TN-UPDATE.md`. I commit message e `TN-UPDATE.md` sono il posto giusto per questa storia.

**Fix**: cleanup incrementale. Priorità ai file più letti: `builder.py`, `split_cv.py`, `persister.py`. Regola: se il commento spiega il **perché** tecnico (invariante, workaround, decisione non ovvia) → tienilo. Se racconta **quando/chi** ha fatto qualcosa → rimuovilo.

---

### M2 — `_t()`/`_time_to_min()`: stesso helper duplicato in due moduli

**File**:
- `backend/src/colazione/domain/builder_pdc/builder.py:115-117` → `_t(t: time) -> int`
- `backend/src/colazione/domain/builder_giro/catena.py:126-128` → `_time_to_min(t: time) -> int`

Identiche: `t.hour * 60 + t.minute`. Anche `_diff` in `builder.py:126-131` è reimplementato altrove.

**Fix**: estrarre in `colazione/domain/utils_tempo.py` con funzioni pubbliche `minuti(t: time) -> int` e `diff_min(start: time, end: time) -> int`. Entrambi i moduli importano da lì.

---

### M3 — `multi_giornata.py` e `multi_giornata_v2.py` coesistono: dead code V1?

**File**: `backend/src/colazione/domain/builder_giro/`

`builder.py` importa da entrambi. Il V1 espone `costruisci_giri_multigiornata` (usato?) e il V2 espone `costruisci_turni_v2`. Non è chiaro dal codice se il V1 sia ancora attivamente chiamato o rimasto come backward-compat inutile.

**Fix**: verificare con `grep -rn "costruisci_giri_multigiornata"` se V1 ha callers ancora attivi. Se non ne ha, rimuovere il file e l'import.

---

### M4 — `stazione_inizio/fine` in `TurnoPdcGiornata`: VARCHAR(20) potenzialmente troppo corto

**File**: `backend/src/colazione/models/turni_pdc.py:73-74`

```python
stazione_inizio: Mapped[str | None] = mapped_column(String(20), ForeignKey("stazione.codice"))
```

`stazione.codice` è `String(50)` (anagrafica). Se un codice stazione avesse > 20 caratteri (attualmente i codici `S01xxx` sono 6 caratteri, ma codici interni come `"IMPMAN_MILANO_FIORENZA"` hanno 22 caratteri), la FK fallirebbe o tronca silenziosamente.

**Fix**: uniformare a `String(50)` come nella tabella `stazione`.

---

### M5 — `profilo="Condotta"` hardcoded in `_persisti_un_turno_pdc`

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:1027`

```python
profilo="Condotta",
```

Il modello `TurnoPdc.profilo` supporta enum (Condotta, Manovra, ecc. — da `MODELLO-DATI.md`). Il builder hardcoda sempre `"Condotta"` senza parametro. Se in futuro si dovessero generare turni Manovra da un giro materiale diverso, bisognerebbe modificare qui.

**Fix**: aggiungere parametro `profilo: str = "Condotta"` a `_persisti_un_turno_pdc` e `genera_turno_pdc`.

---

## Riepilogo conteggi

| Gravità | Count |
|---------|-------|
| CRITICO | 7 |
| IMPORTANTE | 11 |
| MINORE | 5 |
| **Totale** | **23** |

---

## Priorità di intervento suggerita

**Immediata** (prima del deploy successivo):

1. **C2** — STAZIONI_CV_DEROGA: fix di 5 righe, impatto diretto sulla correttezza dei CV Tirano/Valtellina
2. **C1** — `_eccede_limiti`: fix di 4 righe, toglie split spurii su turni serali
3. **C7** — Access token 72h: abbassare a 60 min nel default (1 riga `config.py`)

**Sprint successivo**:

4. **C5** — Anti-rigeneration query (performance + correttezza)
5. **C6** — `updated_at` onupdate (1 migration)
6. **I1+I2+I3** — Unique constraints mancanti (3 migration)
7. **I6** — Test coverage builder PdC (scrivere test per le 7 funzioni critiche)

**Iterazione futura**:

8. **C3** — Builder PdC gap ≥ 65 min → ACC default (refactor più ampio)
9. **C4** — ACCp preriscaldo (richiede parametro data/stagione al builder)
10. **I5** — Refresh token rotazione (richiede tabella DB)

---

*Review condotta il 2026-05-08. Reviewer: Claude (senior engineer). Nessuna modifica al codice di produzione — solo diagnosi.*
