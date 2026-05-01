# Code Review — COLAZIONE — 2026-04-30

> **Scope**: review completa post-Sprint-7.4, pre-Sprint-7.5.
> Copertura: backend (`domain/`, `api/`, `models/`, `alembic/`),
> frontend (`src/lib/`, `src/routes/`), infrastruttura (`config.py`,
> `auth/`, `docker-compose.yml`).
>
> **Metodo**: lettura diretta del codice + grep mirati + confronto
> sistematico con `docs/NORMATIVA-PDC.md` (fonte di verità) e
> `docs/MODELLO-DATI.md`. Nessuna modifica al codice di produzione.
>
> **Classificazione**:
> - **CRITICO** — violazione normativa, bug latente, debito tecnico
>   bloccante per la correttezza del programma.
> - **IMPORTANTE** — qualità, manutenibilità, sicurezza, scalabilità.
> - **MINORE** — stile, micro-ottimizzazioni, dead code.

---

## Indice

- [CRITICI](#critici)
  - [C1 — Anti-rigenerazione turni PdC: full table scan in memoria](#c1--anti-rigenerazione-turni-pdc-full-table-scan-in-memoria)
  - [C2 — Cap notturno 420' applicato a turni 00:00-00:59 (bug off-by-range)](#c2--cap-notturno-420-applicato-a-turni-0000-0059-bug-off-by-range)
  - [C3 — `_count_giri_esistenti` e `_wipe_giri_programma` ignorano la FK esplicita](#c3--_count_giri_esistenti-e-_wipe_giri_programma-ignorano-la-fk-esplicita)
  - [C4 — Preriscaldo ACCp 80' non implementato (violazione normativa §3.3)](#c4--preriscaldo-accp-80-non-implementato-violazione-normativa-33)
  - [C5 — Tutti i gap classificati come PK indipendentemente dalla durata (violazione normativa §6)](#c5--tutti-i-gap-classificati-come-pk-indipendentemente-dalla-durata-violazione-normativa-6)
  - [C6 — STAZIONI_CV_DEROGA hardcoded con nomi leggibili, non codici DB](#c6--stazioni_cv_deroga-hardcoded-con-nomi-leggibili-non-codici-db)
- [IMPORTANTI](#importanti)
  - [I1 — `datetime.utcnow()` deprecato da Python 3.12](#i1--datetimeutcnow-deprecato-da-python-312)
  - [I2 — `assert` in codice di produzione (non nei test)](#i2--assert-in-codice-di-produzione-non-nei-test)
  - [I3 — JWT access token expire = 72h: troppo lungo per best practice](#i3--jwt-access-token-expire--72h-troppo-lungo-per-best-practice)
  - [I4 — `impianto` su TurnoPdc popolato con `tipo_materiale` (semantica sbagliata)](#i4--impianto-su-turno-pdc-popolato-con-tipo_materiale-semantica-sbagliata)
  - [I5 — `updated_at` non viene mai aggiornato (manca trigger o ORM onupdate)](#i5--updated_at-non-viene-mai-aggiornato-manca-trigger-o-orm-onupdate)
  - [I6 — Codice duplicato: logica varianti `numero_treno` in due API](#i6--codice-duplicato-logica-varianti-numero_treno-in-due-api)
  - [I7 — Filtro pool catene usa `giorno_tipo="feriale"` fisso (corse sabato/domenica perse)](#i7--filtro-pool-catene-usa-giorno_tipoferiale-fisso-corse-sabatodom-perse)
  - [I8 — `_aggiungi_dormite_fr` muta `curr.blocchi` in-place (side-effect fragile)](#i8--_aggiungi_dormite_fr-muta-currblocchi-in-place-side-effect-fragile)
  - [I9 — Zero test unitari per `builder_pdc/_inserisci_refezione` e `_aggiungi_dormite_fr`](#i9--zero-test-unitari-per-builder_pdc_inserisci_refezione-e-_aggiungi_dormite_fr)
  - [I10 — `domain/normativa/` package vuoto senza documentazione](#i10--domainnormativa-package-vuoto-senza-documentazione)
- [MINORI](#minori)
  - [M1 — `GiroBlocco.is_validato_utente` non usato in nessun path applicativo](#m1--giroblocco-is_validato_utente-non-usato-in-nessun-path-applicativo)
  - [M2 — Smoke scripts non hanno cleanup garantito](#m2--smoke-scripts-non-hanno-cleanup-garantito)
  - [M3 — Gap negativo (corse sovrappaste) non rilevato dal builder PdC](#m3--gap-negativo-corse-sovrapposte-non-rilevato-dal-builder-pdc)
  - [M4 — `codice_breve` su `LocalitaManutenzione` non ha CHECK constraint nel modello ORM](#m4--codice_breve-su-localitamanutenzione-non-ha-check-constraint-nel-modello-orm)
  - [M5 — Auth: `require_role` crea una closure per ogni invocazione HTTP](#m5--auth-require_role-crea-una-closure-per-ogni-invocazione-http)

---

## CRITICI

---

### C1 — Anti-rigenerazione turni PdC: full table scan in memoria

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:528-537`

```python
existing = list(
    (
        await session.execute(
            select(TurnoPdc).where(TurnoPdc.azienda_id == azienda_id)  # ← TUTTI i turni dell'azienda
        )
    ).scalars()
)
legati = [
    t for t in existing if (t.generation_metadata_json or {}).get("giro_materiale_id") == giro_id
]
```

**Problema**: la query carica in memoria Python **tutti** i `TurnoPdc` dell'intera azienda
(potenzialmente centinaia in un deployment reale), poi filtra con un loop Python sul JSONB.

Un programma reale Trenord (350+ giri materiale × N varianti calendario) produce facilmente
400-800 `TurnoPdc`. Al secondo programma la query porta in RAM 800+ righe ORM per controllare
1 solo `giro_id`. È O(N_turni_azienda) invece di O(1) con query JSONB diretta.

**Fix corretto**:

```python
from sqlalchemy import cast, BigInteger, text

legati = list(
    (
        await session.execute(
            select(TurnoPdc).where(
                TurnoPdc.azienda_id == azienda_id,
                cast(
                    TurnoPdc.generation_metadata_json["giro_materiale_id"].astext,
                    BigInteger,
                ) == giro_id,
            )
        )
    ).scalars()
)
```

(La stessa sintassi è già usata in `api/turni_pdc.py:230-235` per la GET lista — va copiata qui.)

---

### C2 — Cap notturno 420' applicato a turni 00:00-00:59 (bug off-by-range)

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:295-301`
**File (effetto)**: `backend/src/colazione/domain/builder_pdc/split_cv.py:143-157` (in `_eccede_limiti`)

```python
# builder.py riga 295
is_notturno = ora_presa < 5 * 60 or ora_fine_servizio > 22 * 60 or ora_fine_servizio < ora_presa

# builder.py riga 299-301 — cap corretto (usa range [60, 300))
cap_prestazione = (
    PRESTAZIONE_MAX_NOTTURNO   # 420'
    if 60 <= ora_presa < 5 * 60
    else PRESTAZIONE_MAX_STANDARD  # 510'
)
```

**Normativa (NORMATIVA-PDC.md §docstring builder, riga 54)**:
> cap 7h (420 min) se presa servizio **01:00-04:59**

Il flag `is_notturno` usa `ora_presa < 5 * 60` — include 00:00-00:59 (mezzanotte).
Il cap di prestazione in `builder.py` usa correttamente `60 <= ora_presa < 5 * 60`
(01:00-04:59).

**Il bug è in `split_cv._eccede_limiti` (riga 143-157)**:

```python
def _eccede_limiti(draft: _GiornataPdcDraft) -> bool:
    cap_prestazione = (
        PRESTAZIONE_MAX_NOTTURNO if draft.is_notturno else PRESTAZIONE_MAX_STANDARD
    )
```

`draft.is_notturno` è `True` per turni che iniziano a mezzanotte (00:00-00:59),
quindi `_eccede_limiti` applica il cap 420' anche a turni mezzanotte che per normativa
dovrebbero avere cap 510'. Conseguenza: giornate che iniziano a 00:00-00:59 vengono
splittate con soglia 420' invece di 510' → split non necessari, rami corti.

**Fix**: in `split_cv.py` replicare la condizione precisa invece di usare `is_notturno`:

```python
def _eccede_limiti(draft: _GiornataPdcDraft) -> bool:
    ora_presa = _t(draft.inizio_prestazione)  # inizio_prestazione è il PRESA
    cap_prestazione = (
        PRESTAZIONE_MAX_NOTTURNO
        if 60 <= ora_presa < 5 * 60  # 01:00-04:59
        else PRESTAZIONE_MAX_STANDARD
    )
    return (
        draft.prestazione_min > cap_prestazione
        or draft.condotta_min > CONDOTTA_MAX_MIN
    )
```

Nota: `inizio_prestazione` del draft è l'ora del blocco PRESA, che coincide con
`_from_min(ora_presa)` — il valore da confrontare.

---

### C3 — `_count_giri_esistenti` e `_wipe_giri_programma` ignorano la FK esplicita

**File**: `backend/src/colazione/domain/builder_giro/builder.py:269-313`

```python
async def _count_giri_esistenti(session: AsyncSession, programma_id: int) -> int:
    stmt = text(
        "SELECT COUNT(*) FROM giro_materiale WHERE generation_metadata_json->>'programma_id' = :pid"
    )
    row = await session.execute(stmt, {"pid": str(programma_id)})  # ← cast a stringa!
```

**Problema**: la migration `0010_giro_programma_id.py` ha aggiunto `giro_materiale.programma_id`
come **colonna FK esplicita** con indice `idx_giro_materiale_programma_id`. Eppure `_count_giri_esistenti`
e `_wipe_giri_programma` usano ancora la vecchia via JSON (`generation_metadata_json->>'programma_id'`),
che:

1. Non può usare l'indice B-tree sulla FK — produce un full scan JSONB su PostgreSQL.
2. Confronta `programma_id` come stringa (`str(programma_id)`) invece di intero.
3. È disallineato dalla semantica del modello aggiornato.

**Fix**:

```python
async def _count_giri_esistenti(session: AsyncSession, programma_id: int) -> int:
    stmt = text("SELECT COUNT(*) FROM giro_materiale WHERE programma_id = :pid")
    row = await session.execute(stmt, {"pid": programma_id})  # intero, non stringa
    return int(row.scalar_one())

async def _wipe_giri_programma(session: AsyncSession, programma_id: int) -> None:
    # passo 1: salva cmv collegati (stessa logica, cambia solo il filtro)
    cmv_ids = list(
        (await session.execute(
            text("SELECT cmv.id FROM corsa_materiale_vuoto cmv "
                 "JOIN giro_materiale gm ON gm.id = cmv.giro_materiale_id "
                 "WHERE gm.programma_id = :pid"),
            {"pid": programma_id},
        )).scalars().all()
    )
    await session.execute(
        text("DELETE FROM giro_materiale WHERE programma_id = :pid"),
        {"pid": programma_id},
    )
    # passo 2: vuoti orfani (invariato)
    ...
```

---

### C4 — Preriscaldo ACCp 80' non implementato (violazione normativa §3.3)

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:52`, `858`

```python
ACCESSORI_MIN_STANDARD = 40   # ← unico valore usato

# riga 858, in _persisti_un_turno_pdc:
is_accessori_maggiorati=False,  # ← sempre False
```

**Normativa (NORMATIVA-PDC.md §3.3)**:

| Caso | ACCp | ACCa |
|------|------|------|
| Condotta standard | 40' | 40' |
| Condotta con preriscaldo ● (dic-feb) | **80'** | 40' |

Il builder assegna sempre `ACCESSORI_MIN_STANDARD = 40'` all'ACCp, senza mai leggere il mese
del calendario (dicembre-febbraio → preriscaldo obbligatorio). Il campo `is_accessori_maggiorati`
è persistito sempre `False`.

**Impatto concreto**: turni generati in dicembre/gennaio/febbraio per giri che partono da
impianti Trenord hanno ACCp 40' invece di 80'. La prestazione calcolata è sottostimata di 40'.
Se un turno è già a 470' con ACC standard, con preriscaldo reale è a 510' (al limite normativo) —
ma il builder mostra 470' e nessuna violazione. In produzione il pianificatore prende una decisione
su un numero sbagliato.

**Fix**: aggiungere costante + logica mese:

```python
ACCESSORI_MIN_PRERISCALDO = 80   # dic-feb, ACCp only

def _calcola_accp(data_riferimento: date | None) -> int:
    """ACCp = 80' in dic/gen/feb, 40' altrimenti."""
    if data_riferimento is not None and data_riferimento.month in (12, 1, 2):
        return ACCESSORI_MIN_PRERISCALDO
    return ACCESSORI_MIN_STANDARD
```

`_build_giornata_pdc` deve accettare `data_riferimento: date | None` e propagarla
a `_genera_un_turno_pdc` / `genera_turno_pdc` (il `valido_da_eff` è già disponibile nel
contesto del chiamante).

---

### C5 — Tutti i gap classificati come PK indipendentemente dalla durata (violazione normativa §6)

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:214-233`

```python
# 3. Blocchi condotta + PK intermedi
for i, b in enumerate(blocchi_validi):
    if i > 0:
        prec = blocchi_validi[i - 1]
        gap = _diff(prec.ora_fine, b.ora_inizio)
        if gap > 0:
            drafts.append(
                _BloccoPdcDraft(
                    tipo_evento="PK",   # ← SEMPRE PK, qualunque sia il gap
                    ...
                )
            )
```

**Normativa (NORMATIVA-PDC.md §6)**:

| Gap | Modalità ammessa |
|-----|------------------|
| < 65' | CV o PK |
| 65-300' | **ACC** (ACCa + ACCp) o PK |
| > 300' | ACC (default) o PK opt-in |

Un gap di 90' tra due corse dello **stesso materiale** dovrebbe essere `ACCa (40') + buco + ACCp (40')`,
non un unico blocco PK. PK implica materiale in custodia del PdC (acceso, messa in sicurezza); ACC
implica materiale spento e riavviato. Sono due situazioni operative diverse con impatti diversi su:
- computo prestazione (PK non aggiunge accessori, ACC sì — ma il builder PK attuale ignora questa distinzione)
- visualizzazione pianificatore (vede PK dove il vero turno prevede ACC + buco)
- corrispettivo economico del PdC (PK e ACC hanno tariffe diverse)

**Nota di onestà**: il docstring del builder (riga 9) dichiara esplicitamente il PK come scelta MVP.
Il debito è noto ma non tracciato in `TN-UPDATE.md` come residuo aperto. Va aperto formalmente.

**Fix strutturale**: l'algoritmo corretto deve controllare il gap e scegliere:
- `gap < 65` → PK (CV possibile ma richiede coordinamento turni multipli)
- `65 <= gap <= 300` → `[ACCa 40', buco (gap-80'), ACCp 40']` se gap ≥ 80', altrimenti PK
- `gap > 300` → `[ACCa 40', buco (gap-80'), ACCp 40']` (di default, PK solo su richiesta)

Questo è un MR dedicato non banale (cambia la struttura dei blocchi e impatta i test).
**Va tracciato in TN-UPDATE.md come debito normativo aperto.**

---

### C6 — STAZIONI_CV_DEROGA hardcoded con nomi leggibili, non codici DB

**File**: `backend/src/colazione/domain/builder_pdc/split_cv.py:59`

```python
STAZIONI_CV_DEROGA: frozenset[str] = frozenset({"MORTARA", "TIRANO"})
```

**Problema**: lo splitter confronta `blocchi_giro[i].stazione_a_codice` (FK `VARCHAR(20)` a
`stazione.codice`) con questa frozenset. Il codice stazione nel DB può essere:
- Sigla breve (es. `MORTARA`, `TIRANO`) se importato così dal PdE
- Codice RFI (es. `S03388`, `S01978`) se importato con codice canonico

Il test smoke (`smoke_74_split_cv.py`) usa blocchi sintetici costruiti in memoria con
`stazione_a_codice="MORTARA"` hardcoded — non testa lo scenario reale con dati importati
dal PdE. Se il PdE usa codici RFI, le deroghe non matchano mai → nessuno split CV a Mortara.

**Verifica richiesta**: controllare quale formato usa `stazione.codice` nel seed reale.
In `alembic/versions/0001_initial_schema.py:71`:
```sql
CONSTRAINT stazione_codice_format
    CHECK (codice ~ '^S[0-9]+$' OR codice ~ '^[A-Z]+$')
```
Il CHECK ammette entrambi i formati. Quindi i codici potrebbero essere `S03388` o `MORTARA`
a seconda di come viene importato il PdE — non è determinato dal constraint.

**Fix**: aggiungere un integration test che usa stazioni con codice RFI reale per verificare
che il match avvenga. Se il DB usa codici RFI, le deroghe vanno aggiornate di conseguenza
oppure la ricerca va fatta via JOIN su `stazione.nomi_alternativi_json`.

---

## IMPORTANTI

---

### I1 — `datetime.utcnow()` deprecato da Python 3.12

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:797`

```python
"generato_at": datetime.utcnow().isoformat(),
```

`datetime.utcnow()` è deprecated in Python 3.12 (emette `DeprecationWarning`).
Il progetto usa Python 3.12 (`.python-version`).

**Fix**:

```python
from datetime import UTC
"generato_at": datetime.now(UTC).isoformat(),
```

---

### I2 — `assert` in codice di produzione (non nei test)

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:173,216,219`

```python
assert primo.ora_inizio is not None and ultimo.ora_fine is not None   # riga 173
assert b.ora_inizio is not None and b.ora_fine is not None             # riga 216
assert prec.ora_fine is not None                                        # riga 219
```

Con `python -O` (ottimizzazione) gli `assert` vengono rimossi. In produzione su Railway
con `CMD ["python", "-O", "-m", "uvicorn", ...]` (o se mai si aggiunge `-O`) questi controlli
spariscono silenziosamente.

I valori sono garantiti dal filtro `blocchi_validi` due righe sopra, quindi gli `assert` sono
ridondanti — ma rendono l'invariante implicita. La scelta è:

**Opzione A** (preferita): rimuovere gli assert e aggiungere un commento che spiega perché
i valori non possono essere None in quel punto.

**Opzione B**: sostituire con controlli espliciti:

```python
if primo.ora_inizio is None or ultimo.ora_fine is None:
    return None  # difensivo, non dovrebbe mai succedere post-filtro
```

---

### I3 — JWT access token expire = 72h: troppo lungo per best practice

**File**: `backend/src/colazione/config.py:39`

```python
jwt_access_token_expire_min: int = 4320  # 72h
```

Il commento in `auth/dependencies.py:19` lo riconosce come trade-off:
> "il cambio diventa effettivo solo all'access token successivo (max 72h con la config attuale)"

72h è 3× il massimo standard industry (tipicamente 15-60 min). Un access token
compromesso (XSS, log leak, intercettazione) rimane valido per 3 giorni senza possibilità
di revoca (il sistema non fa DB lookup per ogni richiesta).

**Raccomandazione**: ridurre a 30-60 minuti. Il refresh token a 30 giorni compensa per
l'UX. Se la scelta è intenzionale per ridurre i refresh in questa fase MVP, documentarla
esplicitamente in `docs/STACK-TECNICO.md` come decisione temporanea.

---

### I4 — `impianto` su TurnoPdc popolato con `tipo_materiale` (semantica sbagliata)

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:807`

```python
turno = TurnoPdc(
    ...
    impianto=giro.tipo_materiale[:80] if giro.tipo_materiale else "ND",
    ...
)
```

Il campo `TurnoPdc.impianto` (`VARCHAR(80)`) per semantica del modello e per la UI
dovrebbe essere il **deposito PdC** (es. `"GARIBALDI_ALE"`, `"ALESSANDRIA"`), non il
tipo di materiale del giro (es. `"1npBDL+5nBC-clim+1E464N"`).

L'utente che vede la lista turni PdC in UI (`TurniPdcGiroRoute.tsx`) vede in colonna
"Impianto" una stringa come `"1npBDL+5nBC-clim+1E464N"` — incomprensibile e
semanticamente sbagliata.

**Causa**: in fase MVP il concetto di "deposito PdC" non è ancora associato al builder
giro (il giro conosce solo la `localita_manutenzione`, non il deposito PdC). La
`stazione_sede` è ricavata dalla `LocalitaManutenzione.stazione_collegata_codice` ma
non viene usata per `impianto`.

**Fix immediato** (MVP): usare `stazione_sede_eff or "ND"` invece di `tipo_materiale`.
Rappresenta ancora solo la stazione di partenza, non il vero deposito PdC, ma è molto
più leggibile e avvicina alla semantica corretta.

```python
impianto=(stazione_sede_eff or "ND")[:80],
```

**Fix strutturale** (post-MVP): l'utente/operatore specifica il deposito PdC target
prima di generare il turno; il builder lo riceve come parametro esplicito.

---

### I5 — `updated_at` non viene mai aggiornato (manca trigger o ORM onupdate)

**File**: `backend/src/colazione/models/giri.py:68`,
`backend/src/colazione/models/turni_pdc.py:48`

```python
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), server_default=func.now()
)
```

`server_default=func.now()` imposta il valore solo all'INSERT. Non c'è:
- un trigger PostgreSQL `BEFORE UPDATE SET updated_at = now()`
- né `onupdate=func.now()` nella definizione ORM (che richiederebbe explicit flush)
- né aggiornamento manuale nel codice applicativo

Conseguenza: `updated_at` rimane identico a `created_at` per tutta la vita del record,
anche dopo modifiche. Il campo è inutilizzabile per ordinamento "recentemente modificato"
o audit leggero.

**Fix** (preferito — una migration):

```sql
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_giro_materiale_updated_at
BEFORE UPDATE ON giro_materiale
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_turno_pdc_updated_at
BEFORE UPDATE ON turno_pdc
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

---

### I6 — Codice duplicato: logica varianti `numero_treno` in due API

**File**: `backend/src/colazione/api/turni_pdc.py:374-413`
**File**: `backend/src/colazione/api/giri.py` (stessa logica riconosciuta nel commento a riga 375)

Il commento a `turni_pdc.py:375-377` lo dichiara esplicitamente:
> "Sprint 7.3: trasparenza varianti numero_treno (vedi `api/giri.py` per la stessa logica)"

Il blocco SQL window function (`row_number() over partition_by numero_treno`) è copiato
tra i due moduli senza astrazione. Se la logica di conteggio varianti cambia (es. si
aggiunge un filtro per `azienda_id` o si cambia il criterio di ordinamento), va cambiata
in due posti.

**Fix**: estrarre in una funzione helper condivisa:

```python
# colazione/api/_helpers.py
async def calcola_varianti_per_corsa(
    session: AsyncSession,
    azienda_id: int,
    corsa_ids: set[int],
    numero_treno_per_corsa: dict[int, str],
) -> dict[int, tuple[int, int]]:
    """Ritorna {corsa_id: (indice_1based, totale_varianti)} per le corse date."""
    ...
```

---

### I7 — Filtro pool catene usa `giorno_tipo="feriale"` fisso (corse sabato/domenica perse)

**File**: `backend/src/colazione/domain/builder_giro/builder.py:503-508`

```python
def _corsa_in_perimetro_programma(c: Any) -> bool:
    return any(matches_all(r.filtri_json, c, "feriale") for r in regole)
```

Il filtro `_corsa_in_perimetro_programma` usa sempre `giorno_tipo="feriale"` per
stabilire se una corsa appartiene al perimetro del programma. Corse che circolano **solo**
il sabato o la domenica (es. corse festive speciali) hanno regole con
`giorno_tipo in ("sabato", "festivo")` — non matchano mai `"feriale"` → vengono escluse
dal pool del builder → mai assegnate → contate come `n_corse_residue`.

**Il commento nel codice lo riconosce** (riga 502: "il giorno_tipo è euristico — ai fini
del filtro pool è sufficiente"), ma il problema è reale su PdE Trenord reale che include
corse con calendario sabato/domenica/festivi diverso dal feriale.

**Fix**: usare `OR` su tutti i giorno_tipo presenti nelle regole del programma:

```python
giorno_tipi = {gt for r in regole
               for gt in (r.filtri_json.get("giorno_tipo") or ["feriale"])
               if isinstance(gt, str)}

def _corsa_in_perimetro_programma(c: Any) -> bool:
    return any(
        any(matches_all(r.filtri_json, c, gt) for gt in giorno_tipi)
        for r in regole
    )
```

---

### I8 — `_aggiungi_dormite_fr` muta `curr.blocchi` in-place (side-effect fragile)

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:934`

```python
curr.blocchi.insert(0, nuovo_blocco)  # mutazione in-place di _GiornataPdcDraft
for j, b in enumerate(curr.blocchi, start=1):
    b.seq = j
```

`_GiornataPdcDraft` è una dataclass mutabile. La funzione modifica `curr.blocchi` in-place
invece di ritornare un nuovo draft. Questo è safe oggi perché i rami split vengono creati
**dopo** che `_aggiungi_dormite_fr` è chiamata sui `drafts_principali`, ma:

1. È un side-effect nascosto non segnalato dalla firma della funzione.
2. Se l'ordine di esecuzione in `_genera_un_turno_pdc` dovesse cambiare, la mutazione
   potrebbe applicarsi a drafts già consegnati ai rami split.

**Fix**: ritornare nuovi `_GiornataPdcDraft` invece di mutare:

```python
def _aggiungi_dormite_fr(
    drafts: list[_GiornataPdcDraft],
    stazione_sede: str | None,
) -> tuple[list[_GiornataPdcDraft], list[dict[str, Any]]]:
    """Ritorna (drafts_aggiornati, fr_log) senza mutare l'input."""
    ...
```

---

### I9 — Zero test unitari per `_inserisci_refezione` e `_aggiungi_dormite_fr`

**File**: `backend/tests/` (assenza)

Le due funzioni più complesse del builder PdC non hanno nemmeno un test unitario diretto:

- `_inserisci_refezione` (builder.py:328-414): logica di ancoraggio centro/intersezione
  finestra, selezione candidato PK più lungo, sostituzione [PK pre, REFEZ, PK post].
  **Nessun test**. La validazione è indiretta solo tramite smoke scripts.

- `_aggiungi_dormite_fr` (builder.py:879-952): logica FR cross-notte, calcolo durata
  pernotto con gestione is_notturno. **Nessun test**.

Entrambe le funzioni gestiscono casi edge (PK a cavallo della finestra, giornata notturna,
gap mezzanotte) che sono stati documentati come problematici in TN-UPDATE (entry 59 sui
residui `refezione_mancante`).

**Fix**: aggiungere `backend/tests/test_builder_pdc.py` con:
- `test_inserisci_refezione_pk_intero_in_finestra`: PK 60' tutto nella finestra pranzo → REFEZ 30' al centro
- `test_inserisci_refezione_pk_a_cavallo_finestra`: PK che inizia prima della finestra → REFEZ ancorata all'inizio finestra
- `test_inserisci_refezione_nessun_pk_valido`: nessun PK ≥ 30' → draft invariato
- `test_aggiungi_dormite_fr_giornata_notturna`: giornata che finisce dopo mezzanotte → calcolo durata pernotto corretto
- `test_aggiungi_dormite_fr_stessa_stazione_sede`: fine giornata in stazione sede → nessuna dormita

---

### I10 — `domain/normativa/` package vuoto senza documentazione

**File**: `backend/src/colazione/domain/normativa/__init__.py` (1 riga vuota)

Il package `colazione.domain.normativa` esiste ma è completamente vuoto. La normativa
è implementata direttamente nelle costanti di `builder_pdc/builder.py` (righe 48-62) e
nella logica di `split_cv.py`.

Due problemi:
1. Un lettore del codice si aspetta di trovare qui la validazione normativa centralizzata
   (TurnValidator, regole per azienda, etc.) — trova niente.
2. Le costanti normative disperse nel builder non sono usabili da altri moduli senza
   importare da `builder_pdc.builder` (creando dipendenza inversa implicita).

**Fix**: due opzioni:

**A** (breve termine): rimuovere il package vuoto. Le costanti rimangono nel builder fino
a quando non serve estrarle.

**B** (medio termine): spostare le costanti normative in `domain/normativa/trenord.py`:
```python
# domain/normativa/trenord.py
PRESTAZIONE_MAX_STANDARD = 510
PRESTAZIONE_MAX_NOTTURNO = 420
CONDOTTA_MAX_MIN = 330
# ... ecc.
```
Poi importare da lì sia in `builder_pdc/builder.py` che in `split_cv.py`.

---

## MINORI

---

### M1 — `GiroBlocco.is_validato_utente` non usato in nessun path applicativo

**File**: `backend/src/colazione/models/giri.py:148-149`

```python
is_validato_utente: Mapped[bool] = mapped_column(Boolean, default=False)
```

Il commento spiega la semantica futura (editor giro, validazione pianificatore), ma non
c'è mai scritto `is_validato_utente=True` in nessun path del codice applicativo, e nessun
endpoint legge o filtra su questo campo. Dead field per ora — non è un problema, ma va
documentato in TN-UPDATE come residuo intenzionale con scope futuro.

---

### M2 — Smoke scripts non hanno cleanup garantito

**File**: `backend/scripts/smoke_74_split_cv.py` (e i 3 smoke precedenti)

Gli script smoke lasciano dati nel DB (commento: "Lascia i dati in DB per verifica visuale
frontend"). Eseguiti una seconda volta senza `force=True` raisano `GiriEsistentiError`.
Non c'è un meccanismo di cleanup automatico né un `--cleanup` flag.

**Fix**: aggiungere al main degli script:

```python
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--cleanup", action="store_true", help="Rimuove il programma dopo il smoke")
args = parser.parse_args()
...
if args.cleanup:
    await session.delete(programma)
    await session.commit()
```

---

### M3 — Gap negativo (corse sovrapposte) non rilevato dal builder PdC

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:220-221`

```python
gap = _diff(prec.ora_fine, b.ora_inizio)
if gap > 0:
    # crea PK
```

`_diff` gestisce il wrap mezzanotte: `_diff(23:00, 01:00) = 120`. Ma non distingue
"gap cross-notte legittimo" da "sovrapposizione incoerente tra corse dello stesso
giro-giornata". Se il PdE importato ha due blocchi con ora_inizio < ora_fine del precedente
(senza cross-notte), `_diff` produce un numero positivo enorme (24h - sovrapposizione),
generando un PK di ore che ingoia la violazione. Non è un caso frequente su dati reali,
ma è un failure mode silente.

**Fix**: aggiungere un controllo esplicito per overlap (considerato bug del giro, non del builder):

```python
if gap > 12 * 60 and not prec.is_notturno:  # gap > 12h non-notturno → sospetto
    warnings.append(f"Gap anomalo {gap}' tra blocchi {prec.seq} e {b.seq}: verificare giro")
```

---

### M4 — `codice_breve` su `LocalitaManutenzione` non ha CHECK constraint nel modello ORM

**File**: `backend/src/colazione/models/anagrafica.py:82`

```python
codice_breve: Mapped[str] = mapped_column(String(8))
```

Il commento dice `^[A-Z]{2,8}$` ma il constraint è solo nella migration SQL
(`0006_localita_codice_breve.py`, da verificare), non nell'ORM. Se qualcuno inserisce
un `codice_breve` con caratteri lowercase o spazi via Python direttamente (es. nei
test), non viene rifiutato dall'ORM — passa silenziosamente e poi rompe il naming
convention `G-{LOC_BREVE}-{NNN}`.

**Fix**: aggiungere `CheckConstraint` nell'ORM:

```python
from sqlalchemy import CheckConstraint
__table_args__ = (
    CheckConstraint(r"codice_breve ~ '^[A-Z]{2,8}$'", name="localita_codice_breve_format"),
)
```

---

### M5 — Auth: `require_role` crea una closure per ogni invocazione HTTP

**File**: `backend/src/colazione/auth/dependencies.py:66-78`

```python
def require_role(role: str) -> Callable[..., Awaitable[CurrentUser]]:
    async def _checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.is_admin or role in user.roles:
            return user
        raise HTTPException(...)
    return _checker
```

`require_role("PIANIFICATORE_GIRO")` è chiamato a tempo di definizione del router (livello
modulo), quindi la closure viene creata **una volta sola** — non per ogni request. Non è
un bug di performance, ma la struttura è inusuale per FastAPI: la dipendenza è assegnata
a `_authz = Depends(require_role("PIANIFICATORE_GIRO"))` una volta, poi condivisa.

L'unico rischio minore: se qualcuno chiama `require_role(...)` **dentro** un handler
(invece di a livello modulo), crea una nuova closure per ogni request. Il pattern
attuale è corretto ma fragile — non c'è niente che impedisca l'uso scorretto.

Non richiede fix urgente. Documentare nel commento della funzione:
> "Deve essere chiamata a livello modulo, non dentro un handler."

---

## Riepilogo per priorità di fix

| ID | Gravità | Fix stimato | Prerequisiti |
|----|---------|------------|--------------|
| C1 | CRITICO | 30 min | Nessuno |
| C2 | CRITICO | 1h | Lettura `inizio_prestazione` in `split_cv` |
| C3 | CRITICO | 30 min | Nessuno |
| C4 | CRITICO | 2-3h | Decidere come passare la data al builder |
| C5 | CRITICO (debito strutturale) | MR dedicato, 1-2 giorni | Decisione architetturale su ACC vs PK |
| C6 | CRITICO (da verificare) | 2h (verifica + eventuale fix) | Query DB per confermare formato codici stazione |
| I1 | IMPORTANTE | 5 min | Nessuno |
| I2 | IMPORTANTE | 15 min | Nessuno |
| I3 | IMPORTANTE | 10 min (config) + discussione | Decisione utente |
| I4 | IMPORTANTE | 30 min | Nessuno (fix MVP) |
| I5 | IMPORTANTE | 1h (migration trigger) | Nuova migration |
| I6 | IMPORTANTE | 1h | Nessuno |
| I7 | IMPORTANTE | 1h | Test su dati sabato/domenica |
| I8 | IMPORTANTE | 1h | Refactor firma + chiamanti |
| I9 | IMPORTANTE | 2h (scrittura test) | Nessuno |
| I10 | IMPORTANTE | 15 min | Decisione A o B |
| M1-M5 | MINORE | 15-30 min cad. | Nessuno |

---

## Note conclusive

**Qualità generale del codebase**: alta per uno sprint greenfield a questo stadio.
Type coverage mypy strict a 51 file, 414 test, architettura a piramide rispettata
(domain puro, API thin, modelli ORM separati). Il lavoro Sprint 7.4 (split CV intermedio)
è solido nella struttura e nei test unitari (`test_split_cv.py`).

**Aree di debito più significative**:
1. Il builder PdC conosce solo PK come tipo di gap — tutta la semantica ACC/CV/PK
   del §6 normativa è non implementata (C5). Non è un bug critico per l'MVP smoke,
   ma è il residuo normativo più grosso del sistema.
2. Il preriscaldo (C4) è silente e sbagliato in produzione da dicembre a febbraio.
3. Il full scan in C1 diventa visibile al primo programma reale di produzione.

**Cosa non è stato trovato**:
- SQL injection: tutte le query usano parametri bind o ORM.
- XSS: il frontend usa React con JSX, nessun `dangerouslySetInnerHTML` trovato.
- Credenziali hardcoded: nessuna (solo `dev-secret-change-me` nel default, protetto
  da `Field(description=...)`).
- Violazioni FK non gestite: il `ondelete` strategy è consistente in tutto il modello.
- Race condition nella generazione giri: `force=True` usa `flush()` prima della
  ricreazione, corretto.
