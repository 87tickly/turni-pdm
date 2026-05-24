# Code Review — COLAZIONE · Sprint 8.3 / 8.4

**Data**: 2026-05-24  
**Revisore**: NINO (Claude Code)  
**Scope**: intero repo (`backend/`, `frontend/`, `docs/`, `scripts/`)  
**Metodo**: lettura diretta dei file, confronto con `docs/NORMATIVA-PDC.md`,
`docs/MODELLO-DATI.md`, TN-UPDATE.md. Nessuna modifica al codice.

---

## Indice

- [CRITICO (6)](#critici)
- [IMPORTANTE (8)](#importanti)
- [MINORE (6)](#minori)

---

## CRITICI

### CR-1 · `is_accessori_maggiorati=False` hardcoded — preriscaldo mai applicato

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:57,1103`

**Problema**: `ACCESSORI_MIN_STANDARD = 40` è l'unica costante usata per ACCp
e ACCa. NORMATIVA-PDC §3.3 prescrive **ACCp = 80' in dicembre-febbraio**
(marcato ● = preriscaldo). Il campo `TurnoPdcBlocco.is_accessori_maggiorati`
esiste nel modello ma è sempre `False` a riga 1103:

```python
is_accessori_maggiorati=False,  # ← hardcoded, sempre falso
```

Stesso problema in `deposito_first.py` e `giornata_base.py` dove tutti i
percorsi usano `ACCESSORI_MIN_STANDARD`.

**Impatto normativa**: tutti i turni generati da dicembre a febbraio hanno ACCp
40' invece di 80'. La prestazione risultante è sottostimata di 40'. Turni che
con il preriscaldo supererebbero 8h30 vengono generati come conformi.

**Fix**: aggiungere `ACCESSORI_MIN_PRERISCALDO = 80` e un parametro
`data_esecuzione: date` a `_build_giornata_pdc` (o a `build_giornata_pdc` in
`giornata_base`). Nel builder: `acc_min = ACCESSORI_MIN_PRERISCALDO if 1 <=
data_esecuzione.month <= 2 or data_esecuzione.month == 12 else
ACCESSORI_MIN_STANDARD`. Propagare `is_accessori_maggiorati=True` al blocco
ACCp quando si applica.

---

### CR-2 · `assert` in codice di produzione — crash silente con `-O`

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:210,253,256`

```python
assert primo.ora_inizio is not None and ultimo.ora_fine is not None  # 210
    assert b.ora_inizio is not None and b.ora_fine is not None        # 253
            assert prec.ora_fine is not None                           # 256
```

**Problema**: `GiroBlocco.ora_inizio` e `ora_fine` sono `Mapped[time | None]`
nel modello — campi legittimamente nullable. Il check a riga 204 filtra
`blocchi_validi`, ma le asserzioni riassumono un'ipotesi che la logica
precedente non garantisce formalmente.

Con Python `-O` (compilazione ottimizzata, usata da alcuni ambienti Docker e
da `uvicorn --no-access-log`) **gli `assert` vengono rimossi silenziosamente**
→ `AttributeError: 'NoneType' object has no attribute 'hour'` a runtime,
senza traccia del contesto.

**Fix**: sostituire con guard espliciti:
```python
if primo.ora_inizio is None or ultimo.ora_fine is None:
    raise ValueError(
        f"Blocco giro {primo.id} / {ultimo.id}: ora_inizio/fine None "
        "dopo il filtraggio. Dati giro inconsistenti."
    )
```

---

### CR-3 · `codice_ramo` può superare VARCHAR(50) — crash in produzione

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:934-935`

```python
codice_ramo = (
    f"{codice_principale}-G{n_giornata_origine:02d}-R{idx_ramo}"
)
```

`_genera_codice_turno` (riga 1224) produce `codice_principale` fino a 50 char:
`T-` + `composto[:48]`. Il suffisso split `-G14-R5` aggiunge 7 char → totale
**57 char** vs `VARCHAR(50)`.

PostgreSQL non tronca silenziosamente: alza
`DataError: value too long for type character varying(50)` al `session.flush()`
→ transazione rolled back, nessun turno PdC prodotto, nessun log descrittivo
dal router.

**Impatto**: ogni giro che richiede split CV per sforamento cap prestazione
(scenario normale per giri lunghi) crasha silenziosamente.

**Fix**: a `_genera_codice_turno` troncare a 42 char (50 − 8 = margine
`-G14-R5`):
```python
return f"T-{composto[:42]}"
```
Oppure cambiare la colonna a `VARCHAR(60)` con migration + check constraint.

---

### CR-4 · `giornata_base.py` — facade che importa simboli privati: S2-bis non chiuso

**File**: `backend/src/colazione/domain/builder_pdc/giornata_base.py:31-71`

```python
from colazione.domain.builder_pdc.builder import (
    ...
    _aggiungi_dormite_fr,
    _BloccoPdcDraft,
    _build_giornata_pdc,
    ...
)
BloccoPdcDraft = _BloccoPdcDraft
aggiungi_dormite_fr = _aggiungi_dormite_fr
```

Il modulo docstring dichiara di essere la "API stabile del builder-base" e
rimuove gli underscore, ma importa direttamente i simboli `_xxx` di
`builder.py`. Il "S2-bis previsto" (spostare le definizioni su `giornata_base`)
non è stato eseguito.

**Impatto**: qualsiasi rename di un simbolo privato in `builder.py` rompe
`giornata_base.py` a import time senza errori evidenti durante lo sviluppo
(solo un `ImportError` in produzione). I moduli che consumano `giornata_base`
(`deposito_first`, `split_cv`, `multi_turno`) dipendono da un'astrazione falsa.

**Fix**: spostare le definizioni di `_BloccoPdcDraft`, `_GiornataPdcDraft`,
le costanti normative e le funzioni pure (`_build_giornata_pdc`,
`_aggiungi_dormite_fr`, ecc.) direttamente in `giornata_base.py`.
`builder.py` importa da `giornata_base` invece del contrario.

---

### CR-5 · `updated_at` mai aggiornato su UPDATE — audit e change detection rotti

**File**: `backend/src/colazione/models/turni_pdc.py:59`,
`backend/src/colazione/models/giri.py:79`,
`backend/src/colazione/models/anagrafica.py:116,557-558`  
(e altri 8+ modelli)

```python
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), server_default=func.now()
)
```

`server_default` imposta il valore solo all'INSERT. Senza `onupdate` (Python
ORM) o trigger DB, ogni UPDATE lascia `updated_at` al timestamp originale.

**Impatto concreto**:
- `turno_pdc.updated_at` è sempre uguale a `created_at`, anche dopo 20 rigenere.
- Qualsiasi logica che usa `updated_at > soglia` per invalidare cache,
  detectare modifiche, o trigger pipeline è silenziosamente rotta.
- La dashboard "Aggiornato X tempo fa" mostrerà sempre la data di creazione.

**Fix** (due opzioni):
1. ORM side: `onupdate=func.now()` non funziona per update SQL-side. Usare
   `onupdate=datetime.utcnow` (Python-side, limitato a ORM update).
2. DB side: migration con trigger `BEFORE UPDATE` su ogni tabella interessata.
   Più robusto per update SQL diretti.

Raccomandazione: migration trigger, visto che ci sono anche update diretti
via `session.execute(update(...))` nei builder.

---

### CR-6 · `builder.py:731-751` — carica TUTTI i TurnoPdc dell'azienda in memoria

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:736-751`

```python
existing = list(
    (
        await session.execute(
            select(TurnoPdc).where(TurnoPdc.azienda_id == azienda_id)
        )
    ).scalars()
)
```

La query carica **tutti** i `TurnoPdc` dell'azienda per fare il check
anti-rigenerazione. Poi filtra in Python:
```python
legati = [t for t in existing if _matches_giro_e_deposito(t)]
```

Con l'accumulo di generazioni, questa lista cresce senza limite. A 1000 turni
→ 1000 ORM objects in RAM + 1000 righe trasferite via rete per ogni singola
chiamata a `genera_turno_pdc`.

**Fix**: spostare il filtro nel DB:
```python
from sqlalchemy import func, cast as sa_cast, BigInteger
stmt = (
    select(TurnoPdc)
    .where(
        TurnoPdc.azienda_id == azienda_id,
        sa_cast(
            func.jsonb_extract_path_text(
                TurnoPdc.generation_metadata_json, "giro_materiale_id"
            ),
            BigInteger,
        ) == giro_id,
    )
)
```
E aggiungere il filtro `deposito_pdc_id == deposito_pdc_id` se specificato.

---

## IMPORTANTI

### IMP-1 · PK creato per gap = 1' — viola minimo normativo 20'

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:257-270`

```python
gap = _diff(prec.ora_fine, b.ora_inizio)
if gap > 0:
    drafts.append(
        _BloccoPdcDraft(
            tipo_evento="PK",
            ...
            durata_min=gap,
        )
    )
```

NORMATIVA-PDC §4.4: "PK in arrivo 20' minimo, PK in partenza 20' minimo".
Il builder crea un blocco PK per **qualsiasi gap > 0**, inclusi gap di
1-3 minuti che non hanno senso operativo e violano il minimo normativo.

**Fix**: `if gap >= 20:`. Se gap < 20 e > 0, il gap va gestito diversamente
(potenzialmente è tempo tecnico di manovra incluso nel blocco condotta
precedente, o è un dato di giro errato da segnalare come warning).

---

### IMP-2 · §3.2 vettura in apertura non implementata

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:222-248`,
`backend/src/colazione/domain/builder_pdc/deposito_first.py` (docstring riga 32)

NORMATIVA-PDC §3.2: se il **primo segmento** del turno è una vettura, la presa
servizio è 15' prima della vettura e **non si applica ACCp**. Il builder
ignora questo — ogni turno inizia con `PRESA (15') + ACCp (40')` anche quando
il PdC non guida il primo treno ma ci sale come passeggero.

`deposito_first.py` esplicita il gap: *"§3.2 vettura ai bordi DI PARTENZA (è
il rientro che gestiamo qui)"*. Il rientro (fine turno) è gestito, la
partenza (inizio turno) no.

**Impatto**: prestazione in apertura sovrastimata di 40'. Un turno che inizia
con vettura VOCTAXI verso la stazione di presa viene contabilizzato con 40'
di ACCp che fisicamente non esistono.

**Fix**: in `_build_giornata_pdc` (o `build_giornata_pdc`), se il primo blocco
del giro è di tipo `VETTURA`, sostituire la sequenza `PRESA + ACCp + CONDOTTA`
con `PRESA (15' prima vettura) + VETTURA`.

---

### IMP-3 · §7.3 condotta come rientro produttivo non implementato

**File**: `backend/src/colazione/domain/builder_pdc/deposito_first.py:26-29`

NORMATIVA-PDC §7.3: se nel turno materiale esiste un treno di condotta che
porta il PdC verso il deposito, il PdC **conduce** quel treno — non lo usa
come vettura passiva. Ha priorità SUPERIORE alla vettura passiva.

`deposito_first.py` salta questo check e invoca direttamente `risolvi_rientro`
(VETTURA→MM→VOCTAXI). Il turno risultante ha un blocco VETTURA passivo anche
quando il PdC potrebbe stare guidando, producendo:
- Ore di condotta sottostimate nel turno.
- Vettura passiva su un treno che andrebbe invece in CONDOTTA.
- Prestazione più alta del necessario (VETTURA + FINE vs CONDOTTA + ACCa + FINE).

**Fix**: prima di invocare `risolvi_rientro`, controllare se tra i blocchi del
giro materiale ce n'è uno con `tipo_evento=CONDOTTA` e
`stazione_a_codice == depot.stazione_principale_codice`. Se sì, costruire un
blocco CONDOTTA standard invece di invocare il resolver.

---

### IMP-4 · Token JWT senza `jti` — revoca impossibile

**File**: `backend/src/colazione/auth/tokens.py:49-58`

Il token non include `jti` (JWT ID unico). La dependency `dependencies.py`
nota esplicitamente (riga 19): *"se un utente è disattivato o un ruolo è
revocato, il cambio diventa effettivo solo all'access token successivo
(max 72h)"*. Con `jti` + una tabella `revoked_tokens` (o Redis set), la
revoca sarebbe immediata.

**Impatto security**: account compromesso (password rubata) non può essere
revocato istantaneamente. Il token resta valido fino a scadenza.

**Fix MVP**: aggiungere `"jti": str(uuid4())` al payload + tabella
`revoked_tokens(jti TEXT PRIMARY KEY, revoked_at TIMESTAMPTZ)`. La dependency
`get_current_user` fa un `EXISTS` check cheap. Pulizia automatica via cron o
al boot.

---

### IMP-5 · `registro_vetture.from_db()` — operatore sempre `None`, falsi positivi

**File**: `backend/src/colazione/domain/builder_pdc/registro_vetture.py:236-240`

```python
registro.assegna(
    numero_treno=numero,
    operatore=None,     # ← wild card, sempre
    data_operativa=None,
)
```

Tutti i record nel registro usano `operatore=None`. Se Trenord e TILO operano
entrambi un treno con numero "10" (o qualsiasi numero a 2 cifre), il registro
li confonde. Il resolver `is_assegnata()` utilizza match strict su operatore:
`None` matcha solo `None` → in realtà il match è per numero solo.

**Fix**: salvare anche l'operatore nel blocco `TurnoPdcBlocco` (migration per
colonna `operatore_treno_vettura VARCHAR(10)`) e propagarlo dal
`live_arturo.TrenoVettura.operatore` già disponibile nel resolver.

---

### IMP-6 · `registro_vetture.from_db()` — 3 subquery `IN` nidificate

**File**: `backend/src/colazione/domain/builder_pdc/registro_vetture.py:188-228`

La query usa tre livelli di `.in_(scalar_subquery())`. Con N turni
crescenti, il piano di esecuzione Postgres per `IN(subquery)` può degradare
a nested loop O(N²). Alternativa con JOIN esplicito:

```sql
SELECT b.numero_treno_vettura
FROM turno_pdc_blocco b
JOIN turno_pdc_giornata gg ON gg.id = b.turno_pdc_giornata_id
JOIN turno_pdc t ON t.id = gg.turno_pdc_id
JOIN giro_materiale g ON
    CAST(t.generation_metadata_json->>'giro_materiale_id' AS INTEGER) = g.id
WHERE g.programma_id = :programma_id
  AND b.tipo_evento = 'VETTURA'
  AND b.numero_treno_vettura IS NOT NULL
```

Un JOIN permette al planner di scegliere hash join o merge join
invece di nested loops ripetuti.

---

### IMP-7 · `giornate_concrete.py` — fallback "sovra-include" non tracciato come residuo

**File**: `backend/src/colazione/domain/giornate_concrete.py:159-165`

```python
logger.info(
    "enumera_date_giornata: variante '%s' non riconosciuta ...",
)
return candidate  # tutte le date
```

Quando `variante_calendario` contiene etichette complesse Trenord non
riconosciute ("LV 1:5", "Si eff. 21-28/3, 11/4", ecc.), la funzione ritorna
**tutte le date** senza filtrare. Il chiamante (`riposo_settimanale.py`) usa
il conteggio date per validare §11.4, producendo risultati errati.

Il fallback esiste dal Sprint 8.2 MR-PD7b-1. Nessun residuo in TN-UPDATE
specifica quante etichette Trenord reali non sono riconosciute dal parser DSL.

**Fix a breve termine**: aggiungere un contatore Prometheus/log.warning per
ogni fallback attivato in produzione. Misurare % di varianti non riconosciute
su traffico reale per prioritizzare l'estensione del parser.

---

### IMP-8 · `get_session` FastAPI — nessun commit automatico, pattern asimmetrico

**File**: `backend/src/colazione/db.py:81-95`

```python
async def get_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session
```

`session_scope()` (per script CLI, riga 63-78) committa automaticamente.
`get_session()` (per route FastAPI) **no** — ogni route deve chiamare
`await session.commit()` esplicitamente.

Se uno sviluppatore dimentica il commit, le modifiche vengono scartate
**silenziosamente** (no errore, la route risponde 200, il DB non cambia).
Questo è avvenuto almeno una volta nel progetto (evidenza indiretta da
entry TN-UPDATE che corregge "dati non persistiti").

**Fix**: aggiungere un flag di auto-commit opzionale alla dependency, o
(più semplice) aggiungere alla documentazione del pattern un commento
esplicito `# Ricordati: await session.commit() è richiesto in questa route`.
Oppure usare un middleware che committa automaticamente se la response è 2xx.

---

## MINORI

### MIN-1 · Indici mancanti su FK critiche

**File**: `backend/src/colazione/models/turni_pdc.py`,
`backend/src/colazione/models/giri.py`

| Tabella | Colonna | Tipo query critica |
|---------|---------|-------------------|
| `turno_pdc` | `codice` | `WHERE codice = '...'` nella UI dettaglio |
| `giro_materiale` | `programma_id` | `WHERE programma_id = N` nel builder e read endpoint |
| `giro_blocco` | `giro_variante_id` | `WHERE giro_variante_id IN (...)` nel builder PdC |
| `turno_pdc_giornata` | `turno_pdc_id` | `WHERE turno_pdc_id = N` in ogni load giornate |

`ix_turno_pdc_azienda_deposito` esiste (riga 62 `turni_pdc.py`). Mancano
gli altri. Con giri attuali (6.536 corse → 78+ giri × N giornate × N blocchi),
queste scansioni sequenziali sono già misurabili.

**Fix**: migration con `CREATE INDEX CONCURRENTLY` su ciascuna.

---

### MIN-2 · `multi_giornata_v2.py` — relazione con v1 non documentata

**File**: `backend/src/colazione/domain/builder_giro/multi_giornata_v2.py`

Il file (227 righe) esiste accanto a `multi_giornata.py` (746 righe) senza
alcun commento che spieghi il rapporto. `builder.py` importa da entrambi
(righe 89-97). Non è chiaro se:
- La v2 è la versione "aggiornata" e la v1 è legacy da eliminare.
- La v2 è una pipeline alternativa (es. linea-centrica).
- Entrambe devono essere mantenute in parallelo.

**Fix**: aggiungere a `multi_giornata_v2.py` un docstring con:
- Relazione con v1 (è un'alternativa? è una specializzazione?).
- Se v1 è in deprecazione, timeline e piano di migrazione.

---

### MIN-3 · `scripts/` — script operativi senza guardie di sicurezza

**File**: `backend/scripts/pulizia_dati_prova.py`, `backend/scripts/seed_*.py`

I 10 script in `backend/scripts/` eseguono operazioni distruttive (DELETE,
seed massiccio) senza check `if __name__ == "__main__":` robusti o
conferme interattive. Eseguiti per errore in ambiente produzione (Railway)
silenziano dati reali.

`pulizia_dati_prova.py` in particolare ha un nome che suggerisce
"dati di prova" ma opera sulla stessa connessione DB configurata in `.env`.

**Fix**: aggiungere a ogni script distruttivo:
```python
if os.environ.get("COLAZIONE_ENV") != "development":
    raise SystemExit("Script solo per sviluppo locale")
```

---

### MIN-4 · `TODO` in codice di produzione non tracciati in TN-UPDATE

**File**: vari (17 occorrenze totali trovate con `grep -rn "TODO\|FIXME"`)

I più significativi:

| File | Riga | Testo |
|------|------|-------|
| `registro_vetture.py` | 17 | `S4 TODO, attualmente wild card MVP` |
| `deposito_first.py` | 542 | `enumera_date_giornata (S4 TODO) raffinerà per varianti` |
| `giornate_concrete.py` | 12 | `S4 TODO, attualmente wild card MVP` |
| `varianti_calendariali.py` | 293 | `_ = Counter  # noqa: F841 — riservato per estensioni` |

Secondo CLAUDE.md §7: i residui aperti richiedono motivazione oggettiva
dichiarata. "S4 TODO" è tracciato nelle critiche SEVERO ma non risulta
in TN-UPDATE come entry aperta con priorità e sprint target.

**Fix**: aprire entry TN-UPDATE con sprint target per ogni TODO rilevante.
Rimuovere i `noqa: F841` su variabili non usate effettivamente riservate
("per estensioni future") — o usarle, o cancellarle.

---

### MIN-5 · `__all__` mancante nella maggior parte dei moduli

**File**: tutti i moduli `backend/src/colazione/domain/builder_pdc/`,
`backend/src/colazione/domain/builder_giro/`

Solo `giornate_concrete.py` e `registro_vetture.py` hanno `__all__`. Gli altri
moduli espongono tutto implicitamente, rendendo difficile capire qual è la
superficie API pubblica vs simboli interni.

**Fix**: aggiungere `__all__` ai moduli di dominio principali (`builder.py`,
`deposito_first.py`, `split_cv.py`, `multi_turno.py`).

---

### MIN-6 · `health` endpoint senza DB check

**File**: `backend/src/colazione/main.py:53-56`

```python
@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
```

Railway/K8s usa `/health` come liveness probe. Se il DB è down ma il processo
FastAPI è up, il probe risponde 200 e Railway non fa restart del service.
Il backend risponde a tutte le richieste con 500.

**Fix**:
```python
from sqlalchemy import text

@app.get("/health")
async def health(session: AsyncSession = Depends(get_session)) -> dict:
    await session.execute(text("SELECT 1"))
    return {"status": "ok", "version": __version__}
```

---

## Riepilogo

| Gravità | N | Impatto principale |
|---------|---|-------------------|
| CRITICO | 6 | Violazione normativa (preriscaldo), crash runtime (codice ramo), data loss silente (updated_at), performance O(N) per request |
| IMPORTANTE | 8 | Logica dominio incompleta (§3.2/§7.3/§7.1 operatore), sicurezza (JWT revoca), performance (query nidificate) |
| MINORE | 6 | Manutenibilità (naming, indici, guardie script) |

**Priorità di fix suggerita**:
1. CR-3 (VARCHAR overflow) — crash in produzione immediato su qualsiasi giro con split CV.
2. CR-6 (full table scan in memoria) — degradazione performance a ogni build.
3. CR-1 (preriscaldo) — violazione normativa, impatta qualità turni dicembre-febbraio.
4. CR-5 (updated_at) — migration semplice, impatta audit/cache.
5. CR-2 (assert) — rischio teorico basso ma fix banale.
6. CR-4 (facade S2-bis) — debito architetturale da chiudere nel prossimo Sprint builder.

---

*Nessun fix applicato al codice di produzione. Tutti i finding sono segnalazioni.*  
*Riferimento precedente: `docs/CODE-REVIEW-2026-05-01.md` (Sprint 7.4 — 24 finding).*
