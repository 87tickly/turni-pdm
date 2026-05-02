# Code review COLAZIONE — 2026-05-02

> Review eseguita su richiesta utente dopo Sprint 7.6 MR 1 (UX modal
> regola assegnazione). Stato di partenza: 53 test frontend verdi,
> codebase in sviluppo attivo.
>
> **Scope**: tutto il codice del repo (backend + frontend + test +
> migrazioni). **Profondità**: ogni finding con `file:riga`, motivo,
> impatto, fix proposto.
>
> **Metodo**: lettura sistematica di tutti i source file Python e
> TypeScript, confronto con `docs/NORMATIVA-PDC.md` e
> `docs/MODELLO-DATI.md`, verifica rispetto alle entry TN-UPDATE
> precedenti.

## Sintesi

| Categoria | Conteggio |
|-----------|----------:|
| **Critici** (bug funzionali, debiti normativi/strutturali grossi) | 7 |
| **Importanti** (correttezza, security, performance, test mancanti) | 11 |
| **Minori** (stile, dead code, naming) | 6 |

**Top 3 da chiudere nell'ordine**:
1. C3 (`impianto` sbagliato) — invalida tutti i turni generati finora
2. C1 (`is_notturno` soglia errata) — invalida flag in DB su tutti i turni con presa 00:xx
3. C2 (full table scan) — scalabilità bloccante già su dataset medi

**Più veloci da chiudere** (< 30 min ciascuno):
- C5 (`datetime.utcnow()` deprecato)
- M2 (commento §3.2 → §4.1)
- I9 (datalist id non univoco nel DOM)

---

## CRITICI

### C1 — `is_notturno` usa soglia 00:00 invece di 01:00 (NORMATIVA-PDC §11.8)

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:295`

**Codice attuale**:
```python
is_notturno = ora_presa < 5 * 60 or ora_fine_servizio > 22 * 60 or ora_fine_servizio < ora_presa
```

**Problema**: `ora_presa < 300` attiva il flag per qualsiasi turno con
presa da mezzanotte (es. 00:30 → ora_presa = 30). La NORMATIVA §11.8
stabilisce che il regime notturno (cap prestazione 420 min) si applica
per presa servizio **tra 01:00 e 04:59**, non da mezzanotte. Il
`cap_prestazione` alle righe 299-302 usa già `60 <= ora_presa < 300`
correttamente, ma il flag `is_notturno` salvato in DB rimane sbagliato.

**Propagazione del bug**:
- `TurnoPdcGiornata.is_notturno` persistito in DB con valore errato
- `split_cv._eccede_limiti()` legge `is_notturno` → soglia split errata
- Query SQL in `pianificatore_pdc.py:109-119` → KPI violazioni sbagliati
- API espone `is_notturno` → frontend mostra badge "notturno" errato

**Fix**:
```python
is_notturno = (60 <= ora_presa < 5 * 60) or ora_fine_servizio > 22 * 60 or ora_fine_servizio < ora_presa
```

---

### C2 — Full table scan `TurnoPdc` per lookup `giro_materiale_id`

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:528-536`

**Codice attuale**:
```python
existing = list(
    (await session.execute(select(TurnoPdc).where(TurnoPdc.azienda_id == azienda_id))).scalars()
)
legati = [t for t in existing if (t.generation_metadata_json or {}).get("giro_materiale_id") == giro_id]
```

**Problema**: carica tutti i `TurnoPdc` dell'azienda in memoria Python
per filtrare su un valore JSONB. Con 1000+ turni genera una scansione
completa della tabella con deserializzazione di tutti i JSONB. Il percorso
corretto — query JSONB diretta sul DB — è già usato in
`api/turni_pdc.py:255-262` per la stessa logica.

**Fix**:
```python
from sqlalchemy import cast, BigInteger
legati = list(
    (await session.execute(
        select(TurnoPdc).where(
            TurnoPdc.azienda_id == azienda_id,
            cast(TurnoPdc.generation_metadata_json["giro_materiale_id"].astext, BigInteger) == giro_id,
        )
    )).scalars()
)
```

---

### C3 — `TurnoPdc.impianto` popolato con `tipo_materiale` del giro (campo semanticamente sbagliato)

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:807`

**Codice attuale**:
```python
impianto=giro.tipo_materiale[:80] if giro.tipo_materiale else "ND",
```

**Problema**: `impianto` del `TurnoPdc` deve essere il **deposito PdC**
(sede del personale: MILANO_GA, BERGAMO, LECCO, ecc.). Il builder usa
`giro.tipo_materiale` che è la famiglia del rotabile (ETR526, E464+VIVALTO):
valori radicalmente diversi.

**Conseguenza diretta**: `GET /api/pianificatore-pdc/overview` raggruppa
turni per `impianto` → la distribuzione "per deposito PdC" mostra in
realtà il tipo di treno. Tutti i turni generati finora hanno `impianto`
errato in DB.

**Fix**: aggiungere parametro `impianto: str` a `genera_turno_pdc()` e
all'endpoint `/genera-turno-pdc`. A breve termine: usare `stazione_sede`
(già calcolata a riga 514 nella stessa funzione) come proxy del deposito.

---

### C4 — `_count_giri_esistenti` e `_wipe_giri_programma` ignorano la colonna `programma_id` introdotta in migration 0010

**File**: `backend/src/colazione/domain/builder_giro/builder.py:269-276` e `298-314`

**Codice attuale**:
```python
stmt = text("SELECT COUNT(*) FROM giro_materiale WHERE generation_metadata_json->>'programma_id' = :pid")
# ...
text("DELETE FROM giro_materiale WHERE generation_metadata_json->>'programma_id' = :pid")
```

**Problema**: migration 0010 ha aggiunto colonna esplicita
`giro_materiale.programma_id` con FK + indice. `list_giri_programma` in
`api/giri.py:299-304` usa già la colonna ORM. Ma le funzioni critiche di
count/wipe usano ancora il JSONB text path → seq scan senza beneficio
dell'indice. Rischio di inconsistenza: se un giro avesse discrepanza tra
colonna e JSONB, la wipe lo lascerebbe orfano.

**Fix**:
```python
# count
stmt = select(func.count()).select_from(GiroMateriale).where(
    GiroMateriale.programma_id == programma_id
)
# delete
await session.execute(
    delete(GiroMateriale).where(GiroMateriale.programma_id == programma_id)
)
```

---

### C5 — `datetime.utcnow()` deprecato in Python 3.12

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:797`

**Codice attuale**:
```python
"generato_at": datetime.utcnow().isoformat(),
```

**Problema**: `datetime.utcnow()` è deprecato da Python 3.12 e verrà rimosso
in versioni future. Produce un datetime naive (senza timezone), inconsistente
con il resto del sistema che usa `datetime.now(UTC)`.

**Fix**:
```python
from datetime import UTC
"generato_at": datetime.now(UTC).isoformat(),
```

---

### C6 — `TurnoPdc.codice` senza `UNIQUE` constraint per azienda

**File**: `backend/src/colazione/models/turni_pdc.py:38`

**Codice attuale**:
```python
codice: Mapped[str] = mapped_column(String(50))
```

**Problema**: manca `UniqueConstraint("azienda_id", "codice")`. Due richieste
concorrenti a `genera_turno_pdc` possono generare turni con codice identico.
Il codice viene generato in Python (senza lock DB), senza atomicità.

**Fix**: migration con:
```python
UniqueConstraint("azienda_id", "codice", name="uq_turno_pdc_azienda_codice")
```

---

### C7 — JWT access token lifetime 72 ore senza meccanismo di revoca

**File**: `backend/src/colazione/config.py`

**Codice attuale**:
```python
jwt_access_token_expire_min: int = 4320  # 72h
```

**Problema**: token compromesso rimane valido 72 ore. Il sistema è stateless
(niente blacklist). Per un sistema multi-tenant di pianificazione ferroviaria
con dati operativi sensibili, 72h è inaccettabile.

**Nota**: il refresh silenzioso in `frontend/src/lib/api/client.ts` gestisce
già il rinnovo trasparente, quindi ridurre il lifetime non impatta l'UX.

**Fix**: ridurre a 15-30 minuti (`jwt_access_token_expire_min: int = 15`).

---

## IMPORTANTI

### I1 — Costanti normativa duplicate tra builder, API e modulo normativa vuoto

**File**: `backend/src/colazione/api/turni_pdc.py:605-606` e
`backend/src/colazione/domain/normativa/__init__.py` (vuoto)

**Codice in turni_pdc.py**:
```python
PRESTAZIONE_REFEZIONE_SOGLIA_MIN = 360
REFEZIONE_MIN_RICHIESTI = 30
```

**Problema**: duplicano `REFEZIONE_SOGLIA_MIN=360` e `REFEZIONE_MIN_DURATA=30`
già presenti in builder.py. Il modulo `domain/normativa/__init__.py` esiste
ma è vuoto — era il posto naturale per queste costanti. Se la normativa
cambia, il builder viene aggiornato ma le API restano con valori vecchi.

In più, il commento `# NORMATIVA-PDC §3.2` a riga 604 è sbagliato — il
riferimento corretto è §4.1 (Refezione). Vedi anche M2.

**Fix**: popolare `domain/normativa/__init__.py` con tutte le costanti
normative (`PRESTAZIONE_MAX_STANDARD`, `CONDOTTA_MAX_MIN`,
`REFEZIONE_SOGLIA_MIN`, ecc.) e importarle uniformemente ovunque.

---

### I2 — Blocco `varianti_per_corsa` (~35 righe) duplicato tra `turni_pdc.py` e `giri.py`

**File**: `backend/src/colazione/api/turni_pdc.py:505-540` e
`backend/src/colazione/api/giri.py:479-514`

**Problema**: il blocco SQL con window function
`row_number() over (partition by numero_treno order by valido_da, id)` è
identico in entrambi i file. Qualsiasi fix va applicato due volte.

**Fix**: estrarre in funzione condivisa:
```python
async def _get_varianti_per_corsa(
    session: AsyncSession, azienda_id: int, corsa_ids: list[int]
) -> dict[int, tuple[int, int]]: ...
```
in `backend/src/colazione/api/_shared.py` o simile.

---

### I3 — PK creati per gap di 1 minuto (violazione NORMATIVA-PDC §4.4)

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:221`

**Codice attuale**:
```python
if gap > 0:
    drafts.append(_BloccoPdcDraft(...tipo_evento="PK", ...durata_min=gap, ...))
```

**Problema**: NORMATIVA §4.4: "PK minimo 20 minuti su ciascun lato". Gap
di 1-19 minuti producono blocchi PK non-normativi che vengono persistiti
in DB e mostrati nel Gantt come eventi validi.

**Fix**:
```python
PK_MIN_DURATA = 20  # NORMATIVA §4.4
if gap >= PK_MIN_DURATA:
    drafts.append(...)
```

---

### I4 — ACCp preriscaldo (80') non implementato per mesi invernali (NORMATIVA §3.3)

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:57` e `:178`

**Problema**: NORMATIVA §3.3 specifica ACCp 80' per dicembre-febbraio
(preriscaldo). Il builder usa sempre `ACCESSORI_MIN_STANDARD = 40`. I turni
invernali hanno `prestazione_min` sottostimata di 40 minuti; alcune
violazioni non vengono rilevate.

**Fix**: passare `valido_da: date` a `_build_giornata_pdc` e usare:
```python
mese = valido_da.month
accp = 80 if mese in (12, 1, 2) else ACCESSORI_MIN_STANDARD
```

---

### I5 — FR limits (max 1/settimana, max 3/28gg) non enforced

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:893-896`

**Problema**: il builder marca le giornate FR ma non verifica i limiti di
NORMATIVA §10.6. Turni con 2 FR nella stessa settimana non generano
violazione. Il codice ha un commento esplicito "NON enforced nel MVP".
Il test `test_turno_pdc_validazioni_api.py` non copre questo scenario.

**Fix**: dopo il loop giornate, sliding window 7gg e 28gg su `fr_giornate`:
```python
for i, g in enumerate(giornate_with_fr):
    same_week = [x for x in fr_giornate if abs((x.valido_da - g.valido_da).days) < 7]
    if len(same_week) > 1:
        violazioni.append("fr_oltre_1_su_settimana")
```
Costo stimato < 2h.

---

### I6 — `n_corse_update` usato semanticamente come `n_corse_delete`

**File**: `backend/src/colazione/importers/pde_importer.py:500`

**Codice attuale**:
```python
n_corse_update=n_delete,  # riusato come "delta deleted" — vedi note
```

**Problema**: chi legge il valore dal DB si aspetta "corse aggiornate" ma
ottiene "corse cancellate". I report di import via UI mostrano dato
semanticamente errato.

**Fix**: aggiungere colonna `n_corse_delete` al modello (migration) e
tenerla separata.

---

### I7 — `updated_at` senza `onupdate` in `GiroMateriale` e `TurnoPdc`

**File**: `backend/src/colazione/models/giri.py:68` e
`backend/src/colazione/models/turni_pdc.py:48`

**Problema**: `updated_at` ha solo `server_default=func.now()`. Un UPDATE
via ORM non aggiorna automaticamente il campo. I route handler attuali lo
aggiornano manualmente (es. `api/programmi.py:258`), ma il pattern è fragile:
un futuro handler che dimentica il commit manuale produrrà `updated_at` stale
silenziosamente.

**Fix**:
```python
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
    onupdate=func.now(),
)
```
Oppure trigger PostgreSQL `BEFORE UPDATE` via migration.

---

### I8 — `TurnoPdc.codice` senza indice per query di lista e ordinamento

**File**: `backend/src/colazione/models/turni_pdc.py:38`

**Problema**: `GET /api/turni-pdc` usa
`TurnoPdc.codice.ilike(f"%{q}%")` (full scan) e
`order_by(TurnoPdc.codice)` senza indice. Su tabelle con migliaia di turni
le query di lista sono lente.

**Fix**:
```python
codice: Mapped[str] = mapped_column(String(50), index=True)
```
Per `ilike` efficace su prefix: indice GIN con `pg_trgm` tramite migration.

---

### I9 — `datalist id="categorie-comuni"` non univoco nel DOM con più righe filtro

**File**: `frontend/src/routes/pianificatore-giro/regola/FiltriEditor.tsx:318`

**Problema**: due filtri `categoria eq` nella stessa regola producono due
`<datalist id="categorie-comuni">` nel DOM. HTML richiede id univoci;
l'autocomplete del secondo filtro può non funzionare su alcuni browser.

**Fix**:
```tsx
<datalist id={`categorie-comuni-${row.id}`}>
<Input list={`categorie-comuni-${row.id}`} ... />
```

---

### I10 — `get_session()` senza auto-commit: rischio perdita dati silenziosa

**File**: `backend/src/colazione/db.py:81-95`

**Problema**: la session FastAPI dependency non fa auto-commit. Ogni handler
deve esplicitamente chiamare `await session.commit()`. Tutti gli handler
attuali lo fanno, ma il pattern è fragile: un futuro handler che dimentica
il commit ritorna 200 OK con dati persi, senza errore visibile.

**Fix**: documentare esplicitamente con un avviso in docstring della
dependency. Aggiungere almeno un integration test che verifica la
persistenza effettiva dopo ogni route POST/PATCH/DELETE critico.

---

### I11 — Access e refresh token entrambi in `localStorage` (XSS surface)

**File**: `frontend/src/lib/auth/tokenStorage.ts`

**Problema**: sia access che refresh token sono in `localStorage`,
accessibile a qualsiasi JS sulla pagina. Un attacco XSS su una dipendenza
npm compromette entrambi i token in una sola iniezione.

**Fix a breve termine**: ridurre access token lifetime (vedi C7) per
limitare la finestra di esposizione.

**Fix architetturale**: refresh token in httpOnly cookie via `Set-Cookie`
lato backend; access token in React state (memory-only, zero XSS surface).

---

## MINORI

### M1 — Router in `turni_pdc.py` con prefix `/api/giri` (confusionario)

**File**: `backend/src/colazione/api/turni_pdc.py:43`

**Codice attuale**:
```python
router = APIRouter(prefix="/api/giri", tags=["turni-pdc"])
```

Il file gestisce turni PdC ma ha prefix `/api/giri`. Funzionalmente corretto
(gli endpoint vivono sotto `/api/giri/{giro_id}/genera-turno-pdc`), ma
confonde chi legge il file isolato. Aggiungere un commento:
```python
# Prefix /api/giri perché gli endpoint PdC sono nested sotto il giro materiale
```

---

### M2 — Commento `# NORMATIVA-PDC §3.2` errato in `turni_pdc.py`

**File**: `backend/src/colazione/api/turni_pdc.py:604`

Commento: `# NORMATIVA-PDC §3.2` — deve essere `# NORMATIVA-PDC §4.1`
(Refezione/REFEZ, non Condotta).

---

### M3 — `pytestmark_db` naming confusionario in `test_split_cv.py`

**File**: `backend/tests/test_split_cv.py:331`

`pytestmark_db` sembra un alias di `pytestmark` (che pytest applica
automaticamente a livello modulo), ma è un marker custom da applicare
esplicitamente con il decoratore. Un futuro contributor potrebbe non capire
il comportamento. Rinominare in `db_skip_mark` per disambiguare.

---

### M4 — `GiriEsistentiError` definita centinaia di righe dopo il primo uso

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:~962`
(definizione) vs `:539` (primo uso)

Python funziona perché le classi si risolvono al caricamento del modulo, ma
viola la convenzione "definisci prima di usare". In `builder_giro/builder.py`
le eccezioni sono tutte in cima (righe 86-126). Spostare la definizione
insieme alle altre eccezioni in cima al file.

---

### M5 — `adattaComposizioneAlModo` tronca righe senza feedback UX

**File**: `frontend/src/routes/pianificatore-giro/regola/RegolaEditor.tsx:63-81`

Passaggio da "Personalizzata" a "Singola" tronca le righe aggiuntive
silenziosamente. Il dato non è persistito (editing locale), quindi non è
perdita dati permanente — ma l'UX è confusionaria. Finding F2 di FAUSTO
(entry 68 TN-UPDATE), accettato come improvement futuro. Considerare un
avviso inline simile al banner amber già presente in `FiltriEditor.tsx`
per AND multipli.

---

### M6 — Stazione lookup filtrata per `azienda_id` ma `Stazione.codice` è PK globale

**File**: `backend/src/colazione/api/turni_pdc.py:473-484`

`Stazione.codice` è PK globale (non per-azienda) ma il lookup filtra per
`azienda_id`. In un futuro scenario multi-tenant con stazioni condivise tra
aziende, i nomi stazione non sarebbero trovati per aziende che non hanno
importato le stazioni direttamente. Tensione nel modello dati da risolvere
prima del lancio multi-tenant.

---

## Non trovati (verifiche negative significative)

- Nessuna SQL injection: tutti i parametri usano bind variables SQLAlchemy.
- Nessuna N+1 query evidente nei percorsi critici (builder e overview usano
  `selectinload`/`joinedload` dove serve).
- Nessuna chiave API o secret hardcoded nel sorgente; caricamento da
  `pydantic_settings` corretto.
- Nessun cross-tenant data leak evidente: tutti i SELECT critici filtrano
  su `azienda_id`.
- Migrations Alembic: nessuna `down_revision` mancante, catena coerente.
