# Code review COLAZIONE — 2026-05-03

> Review eseguita su richiesta utente dopo chiusura Sprint 7.5 (refactor
> bug 5 + clustering A1) e Sprint 7.7 (varianti A2, re-introduzione
> `GiroVariante`). Stato di partenza: **523 passed, 12 skipped** backend,
> **53 passed** frontend, `mypy --strict` clean, `tsc -b --noEmit` clean.
>
> **Scope**: tutto il codebase — `backend/src/`, `backend/tests/`,
> `frontend/src/`, `alembic/versions/`. Ogni finding con `file:riga`,
> motivo, impatto e fix concreto (non generico).
>
> **Metodo**: lettura diretta dei file critici (~55 source backend,
> 30 test, 19 migrazioni, frontend routing + componenti),
> confronto sistematico con `docs/NORMATIVA-PDC.md` e
> `docs/MODELLO-DATI.md`.
>
> **Nota su continuità**: la review precedente (`CODE-REVIEW-2026-05-01.md`)
> ha identificato 6 critici e 11 importanti. Alcuni trovati allora
> sono ancora aperti (indicati esplicitamente). Le Sprint 7.4/7.5/7.7
> hanno aggiunto codice non coperto da quella review.

---

## Sintesi

| Categoria | Conteggio |
|-----------|----------:|
| **Critici** (violazioni normativa, bug funzionali, debiti strutturali bloccanti) | 6 |
| **Importanti** (correttezza, sicurezza, qualità API, test mancanti) | 11 |
| **Minori** (stile, dead code, micro-debiti) | 7 |

**Valutazione globale**: la codebase è solida per un MVP in
sviluppo attivo — mypy strict clean, test suite verde, architettura
domain/api/persistence rispettata. I finding critici hanno un pattern
comune: le **costanti normative** non hanno SSoT (C6), il **cap
prestazione notturno** è calcolato con un predicato troppo largo (C2),
e il **preriscaldo invernale** non è mai applicato (C3). I tre bug
C2/C3/C4 derivano tutti dalla stessa radice: il builder PdC è
un MVP dichiarato, ma alcune semplificazioni toccano la correttezza
normativa piuttosto che la completezza di feature.

---

## CRITICI

### C1 — Anti-rigenerazione turni PdC: full table scan + filtro Python in memoria
**⚠️ NOTO DA REVIEW 2026-05-01 — ANCORA APERTO**

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:533-541`

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

**Problema**: ad ogni chiamata `genera_turno_pdc()` vengono caricati in
memoria *tutti* i `TurnoPdc` dell'azienda, poi filtrati in Python
guardando dentro il campo JSONB. Per un'azienda con 300 giri × 5
varianti = 1 500 turni, ogni generazione fa una `SELECT *` da migliaia
di righe.

**Impatto**: progressivo. Su DB vuoto è invisibile; sul primo programma
annuale reale (100+ giri × N varianti) diventa query da secondi ad ogni
click "Genera turno PdC". Race condition possibile tra due generazioni
concorrenti (entrambe vedono 0 legati, entrambe inseriscono).

**Fix**:
1. Aggiungere migration `0019_turno_pdc_giro_materiale_id.py`:
   `ALTER TABLE turno_pdc ADD COLUMN giro_materiale_id BIGINT REFERENCES giro_materiale ON DELETE CASCADE`.
   Backfill: `UPDATE turno_pdc SET giro_materiale_id = (generation_metadata_json->>'giro_materiale_id')::BIGINT WHERE giro_materiale_id IS NULL`.
2. Sostituire la query con:
   ```python
   legati = list((await session.execute(
       select(TurnoPdc).where(
           TurnoPdc.azienda_id == azienda_id,
           TurnoPdc.giro_materiale_id == giro_id,
       )
   )).scalars())
   ```
3. Aggiungere indice `idx_turno_pdc_giro_materiale_id`.

**Costo stimato**: 3-4h (migration + backfill + refactor).

---

### C2 — Bug normativa §11.8: `_eccede_limiti` usa `is_notturno` come proxy per il cap 420 min — SBAGLIATO

**File**: `backend/src/colazione/domain/builder_pdc/split_cv.py:150-157`

```python
def _eccede_limiti(draft: _GiornataPdcDraft) -> bool:
    cap_prestazione = (
        PRESTAZIONE_MAX_NOTTURNO if draft.is_notturno else PRESTAZIONE_MAX_STANDARD
    )
    return (
        draft.prestazione_min > cap_prestazione
        or draft.condotta_min > CONDOTTA_MAX_MIN
    )
```

**Normativa §11.8**: il cap ridotto (420 min, 7h) si applica **solo** se
l'orario di presa servizio cade in `01:00 – 04:59` (minuti `60 ≤ presa < 300`).

**Problema**: `is_notturno` è settato in `builder.py:294`:
```python
is_notturno = ora_presa < 5 * 60 or ora_fine_servizio > 22 * 60 or ora_fine_servizio < ora_presa
```

Questo è `True` anche per:
- Turni con presa `05:00-08:00` che **finiscono dopo le 22:00** (`fine > 22*60`).
- Turni che **attraversano mezzanotte** senza presa notturna (es. presa 21:00, fine 02:00).

**Conseguenza concreta**: un turno con presa 05:30 e fine 23:00 ha
`is_notturno=True`, quindi `_eccede_limiti` usa cap 420. Il turno viene
splittato quando in realtà il cap corretto è 510 — il split è superfluo
e genera rami artificiali nel turno PdC.

**Fix**: in `_eccede_limiti`, calcolare il cap dalla `inizio_prestazione`
della giornata, non da `is_notturno`:
```python
def _eccede_limiti(draft: _GiornataPdcDraft) -> bool:
    ora_presa_min = draft.inizio_prestazione.hour * 60 + draft.inizio_prestazione.minute
    cap_prestazione = (
        PRESTAZIONE_MAX_NOTTURNO
        if 60 <= ora_presa_min < 5 * 60
        else PRESTAZIONE_MAX_STANDARD
    )
    return draft.prestazione_min > cap_prestazione or draft.condotta_min > CONDOTTA_MAX_MIN
```

**Nota**: il calcolo del cap in `_build_giornata_pdc:297-301` è già
corretto (usa `60 <= ora_presa < 5 * 60`). Solo `split_cv._eccede_limiti`
è sbagliato.

**Costo stimato**: 30 min (fix + test regression).

---

### C3 — Bug normativa §3.3 + §8.5: ACCp preriscaldo 80' (dic-feb) mai applicato

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:47-51`

```python
ACCESSORI_MIN_STANDARD = 40
# ...
# builder.py:845:
is_accessori_maggiorati=False,  # hardcoded
```

**Normativa §3.3**:
| Caso | ACCp | ACCa |
|------|------|------|
| Standard | 40' | 40' |
| Preriscaldo ● (dic-feb) | **80'** | 40' |

**Normativa §8.5**: a Fiorenza il preriscaldo non esiste — i mezzi sono
"tutti in PK" — quindi ACCp da Fiorenza è sempre 40'.

**Problema**: il builder usa `ACCESSORI_MIN_STANDARD = 40` fisso per
tutti i mesi. Per turni che iniziano in dicembre-febbraio a una stazione
normale (non Fiorenza), l'ACCp dovrebbe essere 80'. La prestazione viene
sottostimata di 40 min → violazioni `prestazione_max` non rilevate +
split CV non attivati quando dovrebbero.

**Fix**: aggiungere logica stagionale in `_build_giornata_pdc`:
```python
from datetime import date
# ...
def _accp_min(stazione_da: str | None, data: date | None) -> int:
    if stazione_da == "IMPMAN_MILANO_FIORENZA":  # §8.5: no preriscaldo a FIOz
        return ACCESSORI_MIN_STANDARD
    if data and data.month in (12, 1, 2):
        return 80  # §3.3: preriscaldo dic-feb
    return ACCESSORI_MIN_STANDARD
```
Il parametro `data` va passato fino a `_build_giornata_pdc`. Il campo
`is_accessori_maggiorati` sul blocco va settato `True` quando ACCp=80'.

**Costo stimato**: 2-3h (builder + test).

---

### C4 — Bug normativa §4.4: PK emesso per gap di qualsiasi durata, senza soglia minima 20'

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:218-231`

```python
gap = _diff(prec.ora_fine, b.ora_inizio)
if gap > 0:
    drafts.append(_BloccoPdcDraft(tipo_evento="PK", durata_min=gap, ...))
```

**Normativa §4.4**:
> "PK in arrivo: **20' minimo**" e "PK in partenza: **20' minimo**"
> "I 20' sono la soglia minima operativa."

**Problema**: gap di 1-19 min tra due corse produce un blocco PK con
durata 1-19 min. Questo è operativamente non valido (il PdC non può
mettere in sicurezza il mezzo in meno di 20 min). Il blocco viene
persistito nel DB e mostrato nel Gantt senza warning.

**Impatto**: il pianificatore vede blocchi PK di 3-5 minuti e non sa
se sono errori o intenzioni. La validazione `violazioni` non li segnala.

**Fix**: aggiungere validazione in `_build_giornata_pdc`:
```python
PK_MIN_DURATA = 20  # §4.4

# nel loop blocchi:
if gap > 0 and gap < PK_MIN_DURATA:
    violazioni.append(f"pk_sotto_minimo:gap={gap}min<{PK_MIN_DURATA}min")
# oppure: assorbire gap piccoli come tempo tecnico (senza blocco PK)
```
La scelta tra "segnala violazione" e "assorbi silenziosamente" va
decisa con l'utente (impatto sulla prestazione).

**Costo stimato**: 1h (fix + test).

---

### C5 — Sicurezza: access token lifetime 72 ore

**File**: `backend/.env.example:14`

```ini
JWT_ACCESS_TOKEN_EXPIRE_MIN=4320  # 72 ore
```

**Commento in codice** (`auth/dependencies.py:18-19`):
> "Conseguenza: se un utente è disattivato o un ruolo è revocato, il
> cambio diventa effettivo solo all'access token successivo
> (max 72h con la config attuale). Per MVP è accettabile."

**Problema**: 72 ore è la durata di un *refresh token* in sistemi
normali, non di un access token. In un sistema multi-tenant con dati
operativi ferroviari:
- Un impiegato dimesso può operare per 3 giorni dopo la revoca.
- Un token rubato ha una finestra di exploit di 3 giorni senza
  possibilità di invalidazione (non esiste blocklist token).

**Fix a breve termine** (nessuna riscrittura arch):
- Ridurre a `JWT_ACCESS_TOKEN_EXPIRE_MIN=30` (standard de facto).
- Aggiornare `.env.example`, documentare in `STACK-TECNICO.md`.

**Fix a lungo termine**: aggiungere tabella `token_blacklist` o
usare Redis per invalidazione esplicita su logout/revoca.

**Costo stimato**: 15 min per il fix immediato (cambiare il default);
2-4h per la blacklist.

---

### C6 — `domain/normativa/__init__.py` vuoto: parametri normativi senza SSoT

**File**: `backend/src/colazione/domain/normativa/__init__.py` (1 riga vuota)

**Problema**: il modulo `domain/normativa/` esiste ma è vuoto. Le
costanti critiche della normativa vivono in `builder_pdc/builder.py`:

```python
# builder_pdc/builder.py:47-60
PRESA_SERVIZIO_MIN = 15
FINE_SERVIZIO_MIN = 15
ACCESSORI_MIN_STANDARD = 40
PRESTAZIONE_MAX_STANDARD = 510
PRESTAZIONE_MAX_NOTTURNO = 420
CONDOTTA_MAX_MIN = 330
REFEZIONE_MIN_DURATA = 30
REFEZIONE_SOGLIA_MIN = 360
REFEZIONE_FINESTRE = [...]
```

Queste costanti sono **importate anche dall'API** (`api/turni_pdc.py:29-31`),
creando un accoppiamento diretto tra layer di presentazione e layer di
implementazione.

**Impatto**:
1. Nessun modulo può usare i valori normativi senza dipendere
   dall'implementazione del builder.
2. Quando arriverà SAD/Trenitalia (multi-tenant), non esiste un
   posto dove mettere `normativa_per_azienda`.
3. Le regole non sono testabili in isolamento (ogni test del builder
   testa implicitamente anche la costante).

**Fix**: spostare le costanti (e le funzioni di validazione pure) in
`domain/normativa/__init__.py` o in un file `domain/normativa/regole.py`:
```python
# domain/normativa/regole.py
PRESA_SERVIZIO_MIN: Final[int] = 15
ACCESSORI_MIN_STANDARD: Final[int] = 40
# ...
def cap_prestazione(ora_presa_min: int) -> int:
    """§11.8: cap dipende dall'orario di presa servizio."""
    return PRESTAZIONE_MAX_NOTTURNO if 60 <= ora_presa_min < 300 else PRESTAZIONE_MAX_STANDARD
```

**Costo stimato**: 1h (refactor + import update + test invariati).

---

## IMPORTANTI

### I1 — `TurnoPdc.impianto` popolato con `tipo_materiale[:80]` invece del deposito PdC

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:793`

```python
impianto=giro.tipo_materiale[:80] if giro.tipo_materiale else "ND",
```

**Problema**: il campo `impianto` in `TurnoPdc` (vedi `MODELLO-DATI.md:296`)
è la **sede del personale di macchina** (deposito PdC), non la
composizione del rotabile. Usare `tipo_materiale` ("1npBDL+5nBC-clim+1E464N")
come surrogate è semanticamente errato e rende il campo inutile.

**Fix**: per il builder automatico, `impianto` non è derivabile dal
giro (il deposito PdC è una scelta del pianificatore). Usare `"ND"` o
derivarlo dalla `stazione_sede` già calcolata:
```python
impianto=stazione_sede or "ND",
```

**Costo stimato**: 30 min.

---

### I2 — `datetime.utcnow()` deprecated in Python 3.12

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:780`

```python
"generato_at": datetime.utcnow().isoformat(),
```

**Problema**: `datetime.utcnow()` è deprecato in Python 3.12 e produce
un `datetime` timezone-naive. Il progetto usa Python 3.12 (`.python-version`).
La funzione sarà rimossa in Python 3.14.

**Fix**:
```python
from datetime import UTC
"generato_at": datetime.now(UTC).isoformat(),
```

**Costo stimato**: 5 min.

---

### I3 — `_validate_pubblicabile` documenta il check #3 ma non lo esegue

**File**: `backend/src/colazione/api/programmi.py:74-119`

**Problema**: il docstring della funzione elenca:
> "3. Tutti i `materiale_tipo` referenziati esistono."

ma il codice salta da check 2 a check 4 senza implementare il 3. Un
programma con `materiale_tipo_codice: "ETR999_INESISTENTE"` viene
pubblicato senza errori; la prima generazione giri fallisce dopo con
un errore non user-friendly da SQLAlchemy (FK violation nel builder).

**Fix**: aggiungere dopo il check 2:
```python
# 3. Tutti i materiale_tipo referenziati dalle regole esistono
codici = {
    item["materiale_tipo_codice"]
    for r in (await session.execute(
        select(ProgrammaRegolaAssegnazione.composizione_json)
        .where(ProgrammaRegolaAssegnazione.programma_id == programma.id)
    )).scalars()
    for item in r
}
if codici:
    esistenti = set((await session.execute(
        select(MateriaTipo.codice).where(MateriaTipo.codice.in_(codici))
    )).scalars())
    mancanti = codici - esistenti
    if mancanti:
        raise HTTPException(400, detail=f"materiale_tipo non trovati: {sorted(mancanti)}")
```

**Costo stimato**: 1h (implementazione + test).

---

### I4 — Manca UNIQUE constraint `(azienda_id, codice)` su `turno_pdc`

**File**: `backend/src/colazione/models/turni_pdc.py:32-48`

**Problema**: non esiste un constraint di unicità sul codice turno
per azienda. Due chiamate concorrenti a `genera_turno_pdc` sullo stesso
giro (con `force=False`) possono entrambe passare il check "legati vuoti"
e creare due turni con codice `T-1130` per la stessa azienda.

Il modello `giro_materiale` ha già la UNIQUE su `(azienda_id, programma_id, numero_turno)`.

**Fix**: aggiungere migration:
```sql
ALTER TABLE turno_pdc ADD CONSTRAINT uq_turno_pdc_azienda_codice
    UNIQUE (azienda_id, codice);
```

**Costo stimato**: 30 min (migration + model).

---

### I5 — `updated_at` non aggiornato automaticamente su `TurnoPdc` e `GiroMateriale`

**File**: `backend/src/colazione/models/turni_pdc.py:48`,
`backend/src/colazione/models/giri.py:79`

```python
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), server_default=func.now()
)
```

**Problema**: `server_default=func.now()` imposta il timestamp solo
alla INSERT. Nessun `onupdate` né trigger DB. Per `ProgrammaMateriale`
il codice aggiorna manualmente (`p.updated_at = datetime.now(UTC)`),
ma per `TurnoPdc` e `GiroMateriale` tutte le mutazioni (stato bozza →
pubblicato, aggiornamento metadati) lasciano `updated_at` congelato
al momento della creazione.

**Fix**: aggiungere trigger Postgres su ogni tabella interessata:
```sql
CREATE TRIGGER turno_pdc_set_updated_at
    BEFORE UPDATE ON turno_pdc
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
```
oppure aggiungere SQLAlchemy `onupdate=func.now()` (richiede
che il campo sia un `server_default` Postgres-side o gestito lato Python).

**Costo stimato**: 1h (migration + trigger function riutilizzabile).

---

### I6 — Modello `revisioni_provvisorie` presente ma completamente morto

**File**: `backend/src/colazione/models/revisioni.py`,
`backend/src/colazione/domain/revisioni/__init__.py` (vuoto)

**Problema**: `RevisioneProvvisoria` è definita come ORM model con FK
verso `giro_materiale`, ma:
- `domain/revisioni/__init__.py` è vuoto.
- Nessun endpoint API gestisce le revisioni.
- Nessun test copre il modello.
- Il builder ignora completamente le revisioni attive (sprint §2 di
  `MODELLO-DATI.md` descrive la logica di override).

**Impatto**: la feature è nel modello dati (vedi `MODELLO-DATI.md:504-551`)
ma non è accessibile. Un operatore che volesse gestire una revisione
provvisoria non ha strumenti.

**Nota**: non è un bug immediato (nessun dato nel DB), ma il modello
"morto" può creare confusione durante onboarding.

**Fix**: o implementare il minimo (CRUD API + test), o rimuovere il
modello ORM fino a quando la feature è priorizzata. Il debito è
esplicito nel `MODELLO-DATI.md` ma non tracciato in `TN-UPDATE.md`.

---

### I7 — `n_varianti_totale` nella lista giri letto da JSONB metadata, non da DB

**File**: `backend/src/colazione/api/giri.py:338-343`

```python
n_varianti_per_giornata = meta.get("n_varianti_per_giornata") or []
n_varianti_totale = (
    sum(int(x) for x in n_varianti_per_giornata)
    if isinstance(n_varianti_per_giornata, list)
    else 0
)
```

**Problema**: il campo `n_varianti_totale` è ricavato da
`generation_metadata_json["n_varianti_per_giornata"]` invece che da una
query `COUNT(giro_variante.id)`. Se il persister non valorizza la chiave
(record pre-MR5, o bug nel persister) il valore è 0 silenziosamente.
Stessa logica duplicata in `list_giri_azienda` (righe 415-420).

**Fix**:
```python
# Query con subquery aggregata:
stmt = (
    select(
        GiroMateriale,
        func.count(GiroVariante.id).label("n_varianti_totale"),
    )
    .outerjoin(GiroGiornata, ...)
    .outerjoin(GiroVariante, ...)
    .group_by(GiroMateriale.id)
    ...
)
```

**Costo stimato**: 1-2h (refactor + test).

---

### I8 — `list_giri_programma` richiede solo `PIANIFICATORE_GIRO`, non `PIANIFICATORE_PDC`

**File**: `backend/src/colazione/api/giri.py:316`

```python
async def list_giri_programma(
    programma_id: int,
    user: CurrentUser = _authz,   # ← solo PIANIFICATORE_GIRO
```

**Problema**: `list_giri_azienda` (endpoint cross-programma) usa
`_authz_read` (entrambi i ruoli), ma `list_giri_programma` (per
programma specifico) usa `_authz` (solo PIANIFICATORE_GIRO). Il
PIANIFICATORE_PDC che vuole vedere i giri di un programma specifico
ottiene **403**, dovendo usare `/api/giri?programma_id=X` come workaround.

**Fix**: cambiare `_authz` in `_authz_read` a riga 316 (1 carattere).

**Costo stimato**: 5 min.

---

### I9 — Rientro a sede: durata hardcoded a 30 min fissi

**File**: `backend/src/colazione/domain/builder_giro/persister.py:671`

```python
arrivo_min = (h * 60 + m + 30) % (24 * 60)  # +30 fissi
```

**Problema**: il tratto di rientro a sede (blocco `9XXXX`) è
calcolato sempre con 30 minuti fissi, indipendentemente dalla tratta
reale. Tratte Lecco→Fiorenza o Brescia→Cremona richiedono
tempi completamente diversi.

**Normativa §12.3**: "quando il builder inserisce un passivo, richiede
all'API il primo treno passeggero disponibile tra A e B nella finestra
oraria richiesta e ne usa partenza/arrivo reali."

**Impatto**: la prestazione del turno (e i km) del giro sono errati
per ogni giro con rientro non-triviale.

**Fix a breve**: parametro configurabile nel `ProgrammaMateriale`
(`durata_rientro_sede_min`) con default 30. Almeno il pianificatore
può correggerlo.
**Fix a lungo**: chiamata API ARTURO per tempi reali.

---

### I10 — Stazioni CV deroga `MORTARA` e `TIRANO` semanticamente distinte, aggregate nello stesso frozenset

**File**: `backend/src/colazione/domain/builder_pdc/split_cv.py:59`

```python
STAZIONI_CV_DEROGA: frozenset[str] = frozenset({"MORTARA", "TIRANO"})
```

**Normativa §9.2**: le stazioni ammesse a CV appartengono a 3 categorie:
1. Sede deposito PdC (25 voci, già in DB).
2. **MORTARA** come deroga esplicita (non deposito, non capolinea).
3. **Stazione capolinea con inversione** (es. TIRANO, DOMODOSSOLA).

`TIRANO` è categoria 3 (capolinea inversione Valtellina), non una
"deroga" come MORTARA. Mescolarli in `STAZIONI_CV_DEROGA` perde la
distinzione semantica e non scala: altri capolinea (DOMODOSSOLA,
CHIASSO, LUINO) richiederebbero modifica codice invece di
aggiornamento DB/config.

**Fix**: aggiungere colonna `is_capolinea_inversione` (bool) su
`Stazione` (o `Depot`) e leggere dinamicamente da DB invece di un
frozenset hardcoded.

**Costo stimato**: 2h (migration + refactor + test).

---

### I11 — Test mancanti: bug C2 non rivelato dalla suite attuale

**File**: `backend/tests/test_split_cv.py` (17 test)

**Problema**: nessun test in `test_split_cv.py` copre il caso in cui
`is_notturno=True` per `fine_servizio > 22h` con `presa >= 05:00`. Il
bug C2 non emerge dalla suite verde attuale.

Caso concreto da testare:
```python
# Presa 06:00, condotta 8h → fine ~15:30, ACCa+FINE → ~16:10
# → prestazione ~610 min
# Senza bug C2: cap 510, split attivato correttamente.
# Con bug C2 (presa 05:30, fine 23:00): is_notturno=True, cap 420 applicato, split errato.
draft_presa_standard_fine_tardiva = _GiornataPdcDraft(
    inizio_prestazione=time(5, 30), prestazione_min=510,
    condotta_min=300, is_notturno=True, ...
)
assert not _eccede_limiti(draft_presa_standard_fine_tardiva)  # fallisce con bug C2
```

**Fix**: aggiungere test di regression insieme al fix C2.

---

## MINORI

### M1 — Dead imports silenced con `# noqa: F841`

**File**: `backend/src/colazione/domain/builder_giro/builder.py:928-929`

```python
_ = festivita  # noqa: F841 (reservato per uso futuro)
_ = calcola_etichetta_giro  # noqa: F841 (export pubblico mantenuto)
```

Due import morti mantenuti con `noqa`. `calcola_etichetta_giro` è
importato e ri-esportato come "export pubblico" ma nessun consumatore
esterno lo usa. `festivita` è il risultato di una query che poi non
viene usato.

**Fix**: se l'export è intenzionale, usare `__all__`. Altrimenti rimuovere.

---

### M2 — Commenti `# Sprint X.Y MR Z:` nel codice di produzione

**File**: `builder.py`, `split_cv.py`, `persister.py`, `composizione.py`
(decine di occorrenze)

I commenti inline con riferimenti ai MR di sprint sono utili durante
lo sviluppo attivo ma diventano rumore nel lungo periodo: le sprint
cambiano nome, le entry TN-UPDATE vengono superate. La storia
appartiene al diario operativo e al `git log`, non al sorgente.

**Fix**: rimozione progressiva nelle sessioni di cleanup. Mantenere
solo commenti sul **perché** architetturale (es. "import deferred per
rompere il ciclo"), non sulla storia di quando è stato scritto.

---

### M3 — `_aggiungi_dormite_fr` assume `is_notturno` implichi attraversamento mezzanotte

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:902`

```python
if prec.is_notturno and fine_n < _t(prec.inizio_prestazione):
    durata_pernotto = max(0, inizio_n1 - fine_n)
else:
    durata_pernotto = (24 * 60 - fine_n) + inizio_n1
```

Lo stesso overloading di `is_notturno` (vedi C2) porta a calcoli
errati della durata del pernotto FR per giornate con `fine > 22h`
ma senza attraversamento mezzanotte.

---

### M4 — `variante_calendario` troncato silenziosamente a 20 char

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:810`

```python
variante_calendario=(d.variante_calendario or "GG")[:20],
```

Il `validita_testo` del PdE Trenord può essere più lungo di 20 char
(es. `"LV 1:5 esclusi 2-3-4/3, 11/4"`). Il troncamento silenzioso
perde informazione e non emette warning.

**Fix**: allargare il campo `TurnoPdcGiornata.variante_calendario` a
`String(100)` (migration) e rimuovere il `[:20]`.

---

### M5 — `ciclo_giorni` in `TurnoPdc` capped a 14 senza motivazione documentata

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:796`

```python
ciclo_giorni=max(1, min(14, giro.numero_giornate)),
```

Il cap a 14 è arbitrario — la normativa §11.1 non prescrive un limite
analogo. Giri con >14 giornate (teoricamente possibili) avrebbero
`ciclo_giorni=14` invece del valore reale.

---

### M6 — `stazione_da_codice` / `stazione_a_codice` nullable anche per blocchi CONDOTTA

**File**: `backend/src/colazione/models/turni_pdc.py:92-95`

```python
stazione_da_codice: Mapped[str | None] = mapped_column(String(20), ForeignKey("stazione.codice"))
stazione_a_codice: Mapped[str | None] = mapped_column(String(20), ForeignKey("stazione.codice"))
```

Per blocchi `CONDOTTA`, `VETTURA`, `ACCp`, `ACCa`, le stazioni devono
essere valorizzate. Accettarle come nullable permette inserimenti
parziali senza integrità.

---

### M7 — Ciclo import `builder_pdc` ↔ `split_cv` risolto con import lazy dentro funzione

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:40-44, 559, 637`

```python
# Sprint 7.4 MR 2: Import deferred dentro le funzioni per evitare ciclo
from colazione.domain.builder_pdc.split_cv import lista_stazioni_cv_ammesse
```

Il ciclo `builder → split_cv → builder` è risolto con import deferiti
a runtime. Il commento spiega il motivo, ma è un debito architetturale:
le strutture condivise (`_GiornataPdcDraft`, `_BloccoPdcDraft`, le
costanti normative) andrebbero estratte in un modulo `_types.py`
(o `normativa.py`, cfr. C6) che entrambi importano senza circolarità.

---

## Tabella riassuntiva

| ID | Categoria | File | Riga | Priorità fix |
|----|-----------|------|------|--------------|
| C1 | Full table scan + filtro Python | `builder_pdc/builder.py` | 533 | Alta — progressivo |
| C2 | `is_notturno` sbagliato per cap prestazione | `split_cv.py` | 150 | **Immediata** — bug normativo |
| C3 | ACCp 80' preriscaldo mai applicato | `builder_pdc/builder.py` | 47 | **Immediata** — bug normativo |
| C4 | PK senza soglia minima 20' | `builder_pdc/builder.py` | 218 | Alta — bug normativo |
| C5 | JWT 72h, nessuna revoca | `.env.example` | 14 | Alta — sicurezza |
| C6 | `normativa/__init__.py` vuoto | `domain/normativa/__init__.py` | — | Media — debito strutturale |
| I1 | `impianto` = tipo_materiale | `builder_pdc/builder.py` | 793 | Media |
| I2 | `datetime.utcnow()` deprecated | `builder_pdc/builder.py` | 780 | Bassa (5 min) |
| I3 | Check #3 pubblicazione non implementato | `api/programmi.py` | 79 | Media |
| I4 | No UNIQUE su `(azienda_id, codice)` | `models/turni_pdc.py` | — | Media |
| I5 | `updated_at` non si aggiorna | `models/turni_pdc.py` | 48 | Bassa |
| I6 | Revisioni: modello morto | `models/revisioni.py` | — | Bassa |
| I7 | `n_varianti_totale` da JSONB non da DB | `api/giri.py` | 338 | Bassa |
| I8 | `list_giri_programma` nega PIANIFICATORE_PDC | `api/giri.py` | 316 | **Immediata** (5 min) |
| I9 | Rientro sede: 30 min fissi | `persister.py` | 671 | Media |
| I10 | MORTARA/TIRANO nello stesso frozenset | `split_cv.py` | 59 | Media |
| I11 | Test mancante per bug C2 | `tests/test_split_cv.py` | — | **Immediata** (con C2) |
| M1 | Dead imports con `# noqa` | `builder_giro/builder.py` | 928 | Bassa |
| M2 | Commenti Sprint/MR nel sorgente | Vari | — | Bassa |
| M3 | FR: stesso overloading `is_notturno` | `builder_pdc/builder.py` | 902 | Bassa (con C2) |
| M4 | `variante_calendario` troncato 20 char | `builder_pdc/builder.py` | 810 | Bassa |
| M5 | `ciclo_giorni` cap 14 arbitrario | `builder_pdc/builder.py` | 796 | Bassa |
| M6 | Stazioni nullable per blocchi CONDOTTA | `models/turni_pdc.py` | 92 | Bassa |
| M7 | Ciclo import risolto con lazy import | `builder_pdc/builder.py` | 40 | Bassa |

---

## Verifiche negative (non trovati)

- **No SQL injection**: tutti i parametri passano via SQLAlchemy ORM,
  niente `text()` con interpolazione utente.
- **No secrets in codice**: `.env.example` usa placeholder, niente
  chiavi hardcoded.
- **No N+1 query evidente**: le query batch usano `.in_()` correttamente
  (vedi `get_giro_dettaglio:495-525`).
- **mypy --strict clean**: 58 file, 0 errori.
- **Test PdE importer**: buona copertura su parser + periodicità + edge case.
- **Auth middleware**: pattern `require_role`/`require_any_role` robusto
  e consistente su tutti gli endpoint.

---

*Review eseguita da Claude Code, modello claude-sonnet-4-6, sessione 2026-05-03.*
