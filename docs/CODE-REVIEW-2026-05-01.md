# Code review COLAZIONE — 2026-05-01

> Review eseguita su richiesta utente dopo chiusura Sprint 7.4
> (4 MR, 2026-04-30). Stato di partenza: 414 test backend + 31
> frontend verdi, mypy --strict clean, typecheck clean, smoke
> end-to-end con dati reali superato.
>
> **Scope**: tutto il codice del repo (backend + frontend + test +
> migrazioni). **Profondità**: ogni finding con `file:riga`, motivo,
> impatto, fix proposto.
>
> **Metodo**: lettura diretta dei file critici (~50 source backend,
> 27 test, 11 migrazioni, 60 ts/tsx frontend), confronto con
> `docs/NORMATIVA-PDC.md` e `docs/MODELLO-DATI.md`.

## Sintesi

| Categoria | Conteggio |
|-----------|----------:|
| **Critici** (bug funzionali, debiti normativi/strutturali grossi) | 6 |
| **Importanti** (correttezza, security, performance, test mancanti) | 11 |
| **Minori** (stile, dead code, micro-ottimizzazioni) | 7 |
| **Non trovati** (verifiche negative significative) | — |

**Stato globale**: codebase **maturo per un MVP**, scelte di scope
documentate esplicitamente in TN-UPDATE e nei commenti, niente bug
nascosti gravi. I findings critici sono in larga parte **debiti
strutturali** lasciati indietro per priorità (split CV ha avuto la
precedenza), non errori. Il debito più impattante è il pattern
**FK-in-JSON** (vedi C1, C3): la migration 0010 ha già introdotto la
colonna FK `giro_materiale.programma_id` ma il codice non l'ha
integrata; la stessa scelta progettuale si ripete su `turno_pdc` →
`giro_materiale`.

---

## CRITICI

### C1 — Anti-rigenerazione turni PdC: full table scan + filtro Python

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:528-547`

```python
existing = list(
    (await session.execute(
        select(TurnoPdc).where(TurnoPdc.azienda_id == azienda_id)
    )).scalars()
)
legati = [
    t for t in existing if (t.generation_metadata_json or {})
        .get("giro_materiale_id") == giro_id
]
```

**Cosa fa**: per controllare se esistono turni PdC del giro corrente,
carica **tutti i turni dell'azienda** in memoria, poi filtra in
Python guardando dentro il JSONB.

**Problema**:

1. Non scala. Con 100 giri × 1 turno = 100 turni → trascurabile.
   Con 365 giorni × 30 giri × 7 varianti calendario il caso reale
   produce migliaia di righe. Ogni `genera_turno_pdc()` farà un
   `SELECT *` su tutti.
2. Pattern speculare a quello già visto su `giro_materiale` →
   `programma_id` (migration 0010). Lì hai aggiunto colonna FK
   esplicita. Qui no: il `giro_materiale_id` resta dentro il JSON.

**Impatto**: performance regression progressiva con la dimensione del
DB. Per il MVP non si vede; al primo programma reale di un anno sì.

**Fix**:

- Aggiungere colonna FK `turno_pdc.giro_materiale_id` (nullable
  inizialmente, backfill dal JSON, poi NOT NULL + indice + FK con
  `ondelete=CASCADE`). Migration analoga a 0010.
- Sostituire la query con `select(TurnoPdc).where(azienda_id, giro_materiale_id == giro_id)`.
- Rimuovere il filtro Python.

**Costo stima**: 2-3h (migration + backfill + refactor builder + API
`list_turni_pdc_giro:230` che ha lo stesso pattern + test).

---

### C2 — Cap prestazione notturna: condizione boundary errata

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:295-302`

```python
is_notturno = ora_presa < 5 * 60 or ora_fine_servizio > 22 * 60 or ora_fine_servizio < ora_presa
# ...
cap_prestazione = (
    PRESTAZIONE_MAX_NOTTURNO
    if 60 <= ora_presa < 5 * 60
    else PRESTAZIONE_MAX_STANDARD
)
```

**Cosa fa**: due definizioni divergenti del concetto "notturno":

- `is_notturno` (riga 295): persistito in `TurnoPdcGiornata.is_notturno`
  e usato da `_eccede_limiti` in split_cv.
- `cap_prestazione` (riga 298-302): usa una formula diversa
  (`60 <= ora_presa < 300`) per scegliere il cap.

**Problema**:

1. Una giornata con `ora_presa = 0` (mezzanotte) ha
   `is_notturno=True` (riga 295: `0 < 300`) **MA** prende
   `cap_prestazione = STANDARD` (riga 300: `60 <= 0` è False).
   La giornata fra 00:00 e 01:00 è marcata notturna ma NON ha il
   cap notturno applicato.
2. `split_cv._eccede_limiti:151-153` legge `draft.is_notturno`
   per scegliere il cap — quindi splitter e validatore principale
   **non concordano** sul cap di una giornata che parte fra 00:00
   e 00:59.
3. Una giornata con `ora_presa = 30` (00:30) → notturna SI, cap
   notturno NO → potenziale falso negativo di violazione.

**Impatto**: bug funzionale silente. Una giornata con presa servizio
dopo mezzanotte ma prima delle 01:00 può sforare il cap 420' senza
essere flaggata, e lo splitter non si attiva. Sull'orario Trenord
reale è raro ma non impossibile (treni notturni di posizionamento).

**Fix**:

- Unificare la definizione. Probabilmente la normativa parla di
  "presa servizio 01:00-04:59" (che è inclusivo 01:00, esclusivo
  05:00 → range `[60, 300)`). Da verificare con NORMATIVA-PDC §3.1.
- Allineare `is_notturno` e `cap_prestazione` alla stessa formula,
  estraendola in costante o helper:

  ```python
  def _is_presa_notturna(ora_presa: int) -> bool:
      return 60 <= ora_presa < 300  # 01:00-04:59
  ```

- Test dedicato per i casi limite: 00:00, 00:59, 01:00, 04:59, 05:00.

**Costo stima**: 1h (decisione utente sulla regola corretta + fix +
test).

---

### C3 — `_count_giri_esistenti` legge JSON invece della FK appena introdotta

**File**: `backend/src/colazione/domain/builder_giro/builder.py:269-321`

```python
async def _count_giri_esistenti(...) -> int:
    stmt = text(
        "SELECT COUNT(*) FROM giro_materiale "
        "WHERE generation_metadata_json->>'programma_id' = :pid"
    )
```

E identico pattern in `_wipe_giri_programma` riga 295-321.

**Cosa fa**: conta/cancella giri di un programma usando il valore
`programma_id` dentro `generation_metadata_json`.

**Problema**: la **migration 0010** (`backend/alembic/versions/0010_giro_programma_id.py`)
ha già:

1. Aggiunto colonna `giro_materiale.programma_id BIGINT NOT NULL`.
2. Backfillato dai metadata.
3. Creato FK con `ondelete=CASCADE`.
4. Creato indice `idx_giro_materiale_programma_id`.
5. Sostituito UNIQUE `(azienda_id, numero_turno)` con
   `(azienda_id, programma_id, numero_turno)`.

Il modello `GiroMateriale.programma_id` (giri.py:44-46) lo dichiara.
**Ma le query nel builder continuano ad usare il JSON**.

**Impatto**:

1. L'indice creato dalla migration 0010 non viene usato (query JSON
   path non lo sfrutta a meno di un GIN sull'expression — non
   creato). La performance promessa dalla migration è persa.
2. `ondelete=CASCADE` su `programma_id` significa che cancellando
   un programma i suoi giri vanno via in automatico. Ma
   `_wipe_giri_programma` continua a cancellare a mano via JSON path
   — ridondante e fragile (se il backfill JSON+colonna divergesse,
   il wipe e i CASCADE cancellerebbero set diversi).
3. Codice che pretende di non avere bisogno della migration
   (potrebbe girare su DB pre-0010), ma il modello dichiara
   `programma_id` NOT NULL → **insert fallisce su DB pre-0010**.
   Inconsistenza.

**Fix**:

```python
async def _count_giri_esistenti(session, programma_id):
    return (await session.execute(
        select(func.count()).select_from(GiroMateriale)
            .where(GiroMateriale.programma_id == programma_id)
    )).scalar_one()

async def _wipe_giri_programma(session, programma_id):
    # CASCADE FK farà il resto + esplicito DELETE per chiarezza
    await session.execute(
        delete(GiroMateriale).where(GiroMateriale.programma_id == programma_id)
    )
    # I CorsaMaterialeVuoto orfani vanno gestiti come prima.
```

**Costo stima**: 1h (fix + verifica che CASCADE chain copra
giornate/varianti/blocchi — già nel modello).

---

### C4 — Preriscaldo ACCp 80' dic-feb: non implementato

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:52`

```python
ACCESSORI_MIN_STANDARD = 40
```

**Normativa**: `docs/NORMATIVA-PDC.md:75, 245`

> | Condotta con preriscaldo ● (dic-feb) | **80'** | **40'** |

`ACCp` passa da 40' a 80' nel periodo dicembre-febbraio (preriscaldo
del materiale).

**Eccezione**: NORMATIVA §8.5 (riga 606-613) — Fiorenza è esonerata
("a Fiorenza il preriscaldo non esiste, i mezzi sono normalmente
caldi").

**Cosa manca**:

- Il builder usa sempre `40` per ACCp (riga 178, 207).
- Modello `TurnoPdcBlocco.is_accessori_maggiorati` ESISTE (turni_pdc.py:99)
  ma il builder lo setta sempre `False` (builder.py:858).
- Niente logica di mese.
- Niente eccezione Fiorenza.

**Impatto**: in inverno la **prestazione viene sottostimata di 40'
per giornata** in turni che partono fuori Fiorenza. Una giornata che
calcola 510' di prestazione potrebbe in realtà essere 550' → cap
sforato silenziosamente. Lo split CV potrebbe non scattare quando
dovrebbe.

**Fix**:

```python
# In _build_giornata_pdc, dopo aver determinato primo.stazione_da_codice e data:
def _accp_min(stazione_partenza: str, data: date) -> int:
    if data.month in (12, 1, 2) and not _is_fiorenza(stazione_partenza):
        return 80
    return 40
```

E settare `is_accessori_maggiorati=True` sul blocco ACCp corrispondente.

Ma c'è un problema di scope: oggi il builder PdC opera sulla
giornata-tipo **senza una data calendariale** specifica (la giornata
si applica a N date via `validita_dates_apply_json`). Se il giro
copre dicembre AND gennaio AND aprile, lo stesso turno ha
prestazione diversa a seconda della data.

**Decisioni necessarie da utente**:

1. Calcolare prestazione "worst-case" (con preriscaldo) sempre, o
   un turno **per regime stagionale**?
2. Se split CV scatta solo in inverno per quella stessa giornata-tipo,
   come si rappresenta in `TurnoPdc`?

**Costo stima**: 4-6h (richiede decisione + implementazione +
modello data-aware).

**Severity**: critico per correttezza. Per ora dichiarato come
residuo in TN-UPDATE entry 42, ma non è citato in entry 59 dei
limiti residui Sprint 7.4 — andrebbe ri-promosso a residuo
esplicito.

---

### C5 — Gap fra blocchi sempre classificato PK: ACC/CV non distinti

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:215-233`

```python
for i, b in enumerate(blocchi_validi):
    if i > 0:
        prec = blocchi_validi[i - 1]
        gap = _diff(prec.ora_fine, b.ora_inizio)
        if gap > 0:
            drafts.append(_BloccoPdcDraft(
                ...
                tipo_evento="PK",  # SEMPRE PK
                ...
            ))
```

**Cosa fa**: ogni gap > 0 fra due blocchi consecutivi del giro
diventa un blocco `PK` (parking).

**Normativa** (`docs/NORMATIVA-PDC.md` §3.4 + §5 + §6):

Un gap fra due blocchi consecutivi può essere:

1. **CV** (Cambio Volante) — gap < 65' E stazione in lista CV E i
   due PdC si incontrano. CVa al PdC che consegna, CVp al PdC che
   prende.
2. **ACCa+ACCp** — gap qualsiasi, PdC consegna fisicamente il mezzo
   (40'+40' = 80' di accessori). Si applica come default se NON è
   un CV.
3. **PK** (Parking) — il mezzo resta col PdC, niente cambio.

Il codice distingue solo PK; non c'è ACC fra blocchi consecutivi né
CV no-overhead.

**Impatto**:

1. Una pausa di 30' fra due blocchi viene rappresentata come 30' di
   PK, mentre nella realtà operativa potrebbe essere 30' di
   stazionamento + ACCa di 40' al treno arrivato + ACCp di 40' al
   treno successivo, **prima che il PdC riprenda il volante**.
   Manca tutta la "ginnastica" accessori intra-giornata.
2. Lo split CV (Sprint 7.4) divide la giornata in N rami, ognuno
   pagando ACCp+ACCa standard ai bordi (riga 178, 180). MA fra due
   rami consecutivi della stessa giornata fisica, il PdC non sta
   davvero facendo PRESA→ACCp→...→ACCa→FINE→PRESA→ACCp→... per ogni
   ramo. Il modello rappresentativo è corretto perché i rami sono
   PdC distinti (uno consegna a CV, l'altro prende), ma allora la
   **transizione fra rami** dovrebbe essere CVa+CVp, non
   ACCa+ACCp.
3. La normativa §5 prevede che un CV "no-overhead" risparmi 80'
   rispetto a ACCa+ACCp. Lo split CV attuale paga questo costo
   anche dove la normativa direbbe di non farlo.

**Stato dichiarato**: TN-UPDATE entry 59 cita
"CV no-overhead non implementato per MVP". Quindi è residuo noto.

**Impatto reale**:

- Prestazione sovrastimata del ramo successivo a uno split (paga
  PRESA+ACCp che non dovrebbe pagare).
- Confronto pre/post-split (smoke entry 59) torna favorevole
  comunque (380 min vs 680 min) perché il sovraccosto del CV
  no-overhead (~80 min) è inferiore al guadagno dello split.
- Ma una giornata border-line potrebbe non beneficiare dello split
  se il sovraccosto erode il margine.

**Fix**:

Strutturale, non scrivibile in <2h. Richiede:

1. Decisione sul modello dati: il blocco "transizione fra rami" è
   `CVa` (sul ramo precedente) + `CVp` (sul ramo successivo), o
   un blocco dedicato che li unifica?
2. Lookup stazione+gap per scegliere fra CV / ACC / PK in
   `_build_giornata_pdc`.
3. Cosa fare quando fra blocchi del giro c'è gap > 0 e non c'è
   stazione CV: ACC e basta? (il gap invece di rappresentarsi come
   PK rappresenta come ACCa+gap_residuo+ACCp).

**Costo stima**: 1-2 giornate. È il MR successivo logico dello
Sprint 7.4.

---

### C6 — `STAZIONI_CV_DEROGA = {"MORTARA", "TIRANO"}` potrebbe non matchare il DB

**File**: `backend/src/colazione/domain/builder_pdc/split_cv.py:59`

```python
STAZIONI_CV_DEROGA: frozenset[str] = frozenset({"MORTARA", "TIRANO"})
```

**Cosa fa**: hardcoded set di codici stazione ammessi a CV in
deroga (oltre i depositi PdC dell'azienda). Usato per fare
`stazione_codice in STAZIONI_CV_DEROGA`.

**Verifica**: ho cercato i due codici nel seed Trenord (`backend/alembic/versions/0002_seed_trenord.py`):

- `MORTARA` → presente come tupla `("MORTARA", "Mortara")` (riga 73).
- `TIRANO` → **non trovato nel seed**.

`TIRANO` è probabilmente il codice di una stazione che entra nel DB
via `Stazione` derivata dalle corse PdE (durante l'import). Potrebbe
quindi finire come `"TIRANO"`, ma anche come `"MILANO TIRANO"`,
`"S00321"` (codice RFI numerico), o `"MITIRA"` (abbreviazione
Trenord). Senza verifica empirica sul DB reale post-import #1289 non
è certo che il match avvenga.

**Impatto**:

- Lo smoke 7.4 testa **MORTARA** (entry 59) → conferma che il
  match funziona per quella stazione.
- TIRANO non è testato. Se il codice nel DB fosse diverso, la
  deroga non si applica e lo split CV non si attiva sulla
  direttrice Tirano (caso d'uso prioritario da memoria utente
  `project_etr425_526_solo_diretti.md` e
  `project_stazioni_sosta_notturna.md`).

**Fix**:

1. Verifica empirica: query `SELECT codice, nome FROM stazione
   WHERE nome ILIKE '%TIRANO%'` su DB reale dopo import
   programma #1289.
2. Se il codice non è `"TIRANO"`, due opzioni:
   - Promuovere a regola configurabile per programma (residuo
     dichiarato in TN-UPDATE entry 59) → soluzione strutturale.
   - Toppa minima: estrarre lookup via `Stazione.nome ILIKE` invece
     di codice esatto.
3. Test integration: smoke con un giro che attraversa Tirano e
   verifica che lo split scatti.

**Costo stima**: 30 min verifica + 1-2h fix (a seconda dell'opzione).

---

## IMPORTANTI

### I1 — `datetime.utcnow()` deprecato

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:797`

```python
"generato_at": datetime.utcnow().isoformat(),
```

**Problema**: `datetime.utcnow()` è deprecated in Python 3.12+ (warning),
rimosso in versioni future. Il resto del codebase usa correttamente
`datetime.now(UTC)` (es. persister.py:303 e tokens.py:35).

**Fix**: `datetime.now(UTC).isoformat()` con import `from datetime import UTC`.

**Costo**: 5 min.

---

### I2 — `assert` per type narrowing in produzione

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:173, 216, 219`

```python
primo = blocchi_validi[0]
ultimo = blocchi_validi[-1]
assert primo.ora_inizio is not None and ultimo.ora_fine is not None
```

**Problema**: `python -O` strippa gli assert. In quel caso fallirebbe
silenziosamente con `TypeError: unsupported operand` quando il check
serviva a guardare l'invariante.

In più alcuni assert sono **ridondanti** (riga 167-168 ha già un
filter su `ora_inizio is not None and ora_fine is not None`,
quindi mypy può narrarsi senza assert).

**Fix**: usare `if not ... raise RuntimeError(...)` per gli assert
funzionali, e refactor del filter per produrre direttamente una
lista di `_BloccoConOrari` con campi non-Optional (NewType o
TypedDict) per il narrowing mypy.

**Costo**: 30 min.

---

### I3 — JWT access token con TTL 72h

**File**: `backend/src/colazione/config.py:39`

```python
jwt_access_token_expire_min: int = 4320  # 72h
```

**Problema**: 72h è 288× lo standard industriale (15 min). Significa
che credenziali compromesse o ruoli revocati restano validi fino a
72h. `dependencies.py:19` documenta esplicitamente la scelta come
"accettabile per MVP" — ma è una scelta da rivedere prima del primo
deploy non-MVP.

**Fix**: ridurre a 30-60 min, alzare il refresh a 1-7gg (già 30gg).
Frontend deve gestire refresh automatico.

**Costo**: ~1 giornata se manca il refresh flow nel frontend.

---

### I4 — `impianto` di TurnoPdc popolato col `tipo_materiale` (semantica errata)

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:807`

```python
turno = TurnoPdc(
    ...
    impianto=giro.tipo_materiale[:80] if giro.tipo_materiale else "ND",
    ...
)
```

**Problema**: il campo `TurnoPdc.impianto` (turni_pdc.py:39, `String(80)`)
ha semantica "impianto manutenzione" (es. `FIO`, `NOV`, `IMPMAN_MILANO_FIORENZA`).
Qui ci stiamo mettendo `tipo_materiale` (es. `ETR425`, `ETR526`, `MISTO`).

Sono due dimensioni completamente diverse. Domani filtri `WHERE impianto
= 'FIO'` tornerà 0 risultati perché tutti hanno `ETR425`.

**Cosa è disponibile**: `giro.localita_manutenzione_partenza_id` →
`LocalitaManutenzione.codice` o `.codice_breve`. È quello che dovrebbe
finire in `impianto`.

**Fix**:

```python
loc_partenza = ... # già caricata sopra come `loc`
impianto_codice = loc.codice_breve if loc else "ND"
turno = TurnoPdc(..., impianto=impianto_codice[:80], ...)
```

**Costo**: 30 min + verifica che dashboard frontend non si aspetti
`tipo_materiale` su quel campo.

---

### I5 — `updated_at` non aggiornato sui write

**File**: `backend/src/colazione/models/turni_pdc.py:48`,
`backend/src/colazione/models/giri.py:68`

```python
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), server_default=func.now()
)
```

**Problema**: `server_default=func.now()` setta il valore alla **insert**.
Non c'è `onupdate=func.now()`. Quando il pianificatore modifica il
giro/turno (in editor giro futuro o forzato via `force=True`),
`updated_at` resta uguale a `created_at`.

**Fix**: aggiungere `onupdate=func.now()`. Vale per tutte le tabelle
con `updated_at`.

**Costo**: 30 min + migration server (Alembic non lo regge da solo,
serve `op.alter_column` esplicito).

---

### I6 — Filtro pool catene con `giorno_tipo='feriale'` hardcoded

**File**: `backend/src/colazione/domain/builder_giro/builder.py:506-509`

```python
def _corsa_in_perimetro_programma(c: Any) -> bool:
    return any(matches_all(r.filtri_json, c, "feriale") for r in regole)

corse_perimetro = [c for c in corse if _corsa_in_perimetro_programma(c)]
```

**Problema**: il filtro pool usa **sempre** "feriale" come euristica.
Se una corsa ha regole solo `giorno_tipo='festivo'` (raro, ma
possibile per servizi dedicati), il filtro pool la scarta. Poi
l'assegnazione finale non potrà più assegnarla → corsa residua.

Il commento dice "ai fini del filtro pool è sufficiente; l'assegnazione
finale userà il giorno_tipo reale" — ma se il filtro pool la elimina,
l'assegnazione non la vede mai.

**Fix**: testare con tutti i `giorno_tipo` possibili (`feriale`,
`sabato`, `festivo`):

```python
GIORNI_TIPO = ("feriale", "sabato", "festivo")
def _corsa_in_perimetro_programma(c) -> bool:
    return any(
        matches_all(r.filtri_json, c, gt)
        for r in regole for gt in GIORNI_TIPO
    )
```

**Costo**: 30 min + test con regola solo-festivo.

---

### I7 — `_aggiungi_dormite_fr` muta in-place i draft

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:879-952`

```python
curr.blocchi.insert(0, nuovo_blocco)
for j, b in enumerate(curr.blocchi, start=1):
    b.seq = j
```

**Problema**: la funzione muta `curr.blocchi` (lista dentro un
`_GiornataPdcDraft`). Pattern fragile:

1. Se i draft sono shared (oggi non lo sono ma niente lo impedisce),
   muta uno degli usi.
2. Test difficili da scrivere — devi sempre ricostruire il draft
   prima di chiamare la funzione.
3. Ritorno = lista di metadata FR ma il "vero" cambiamento è la
   mutazione → asimmetria tra valore di ritorno e side effect.

**Fix**: ritornare una nuova lista `list[_GiornataPdcDraft]` con i
blocchi DORMITA prepended dove necessario. Pattern allineato a
`_inserisci_refezione` che già ritorna una nuova lista.

**Costo**: 1h.

---

### I8 — `_persisti_un_turno_pdc`, `_inserisci_refezione`, `_aggiungi_dormite_fr` senza test unitari

**File**: `backend/tests/` (verificato con grep)

```text
zero file con `_inserisci_refezione`, `_aggiungi_dormite_fr`, `_persisti_un_turno_pdc`
```

**Problema**: 3 helper privati del builder PdC, ognuno con logica
non banale (refezione: ricerca PK candidato, posizionamento ottimale;
FR: detection cross-giornata, calcolo durata pernotto;
persisti: orchestrazione ORM con metadata split). Nessuno ha test
unitario diretto.

Il builder è coperto solo dal test di alto livello + smoke runtime.
Quando uno di questi helper si rompe in modo sottile, salta solo lo
smoke (1 numero che non quadra) e il bug è difficile da localizzare.

**Fix**: scrivere test unitari per i 3 helper:

- `_inserisci_refezione`: ≥6 test (PK breve, PK fuori finestra, 2 PK
  candidati, PK al boundary di finestra, no PK, PK che si centra in
  finestra).
- `_aggiungi_dormite_fr`: ≥4 test (FR rilevato, no FR perché stazione
  uguale, no FR perché sede coincide, FR cross-notte).
- `_persisti_un_turno_pdc`: 2 test (con DB SQLite in-memory) — uno
  con `is_ramo_split=False`, uno con `True`.

**Costo**: 2-3h.

---

### I9 — `_count_giri_esistenti` e `_wipe_giri_programma` query duplicata

**File**: `backend/src/colazione/domain/builder_giro/builder.py:269-321`

**Problema**: oltre al bug C3, c'è duplicazione: la stessa query JSON
path è ripetuta 3 volte (in `_count`, `_wipe` per i giri, `_wipe`
per i vuoti orfani). Manutenzione fragile: cambia il path → cambi 3
posti.

**Fix**: estrarre un helper `def _giri_di_programma_subquery(...)` o
(meglio, dopo C3) usare la FK colonna.

**Costo**: 15 min con C3.

---

### I10 — `_km_media_annua_giro` usa solo la prima corsa per giornata

**File**: `backend/src/colazione/domain/builder_giro/persister.py:214-217, 240-244`

```python
prima = corse[0]
valido_dates = getattr(prima, "valido_in_date_json", None)
# ... usa SOLO le date della prima corsa per moltiplicare i km della
# giornata intera.
```

**Problema**: assume che la prima corsa di una giornata abbia la
stessa periodicità di tutte le altre della stessa giornata. È falso
quando una giornata ha corse a periodicità mista (es. prima corsa
feriale, ultima corsa anche festivi).

Il commento ammette: "Approssimazione: ... stima al rialzo o al
ribasso a seconda del mix".

**Impatto**: km_media_annua sbagliata (anche significativamente).
Per dashboard manutenzione (km cap → manutenzione programmata) è
un dato critico — memoria utente lo dichiara "sempre fondamentale"
(`feedback_km_sempre_fondamentali.md`).

**Fix**: una stima onesta è l'**intersezione** delle
`valido_in_date_json` di tutte le corse della giornata (set
intersection, non solo prima):

```python
date_giornata_valide = set(corse[0].valido_in_date_json or [])
for c in corse[1:]:
    date_giornata_valide &= set(c.valido_in_date_json or [])
n_giorni = sum(1 for d in date_giornata_valide
               if valido_da_iso <= str(d) <= valido_a_iso)
```

**Costo**: 1h (refactor + test).

---

### I11 — `_next_numero_rientro_sede` race condition

**File**: `backend/src/colazione/domain/builder_giro/persister.py:267-273`

```python
stmt = text(
    "SELECT COALESCE(MAX(SUBSTRING(numero_treno_vuoto FROM 2)::int), 0) "
    "FROM corsa_materiale_vuoto "
    "WHERE numero_treno_vuoto ~ '^9[0-9]{4}$'"
)
last = (await session.execute(stmt)).scalar_one()
return f"9{(int(last) + 1):04d}"
```

**Problema**: classica race condition `SELECT MAX → +1`. Due
chiamate concorrenti vedono lo stesso `MAX` e generano lo stesso
numero. UNIQUE su `numero_treno_vuoto` → una insert fallisce.

**Stato pratico**: oggi il pianificatore lavora sequenzialmente,
quindi non si manifesta. Ma `genera_giri()` produce N giri e per
ognuno chiama questa funzione → loop sequenziale ok ma
**vulnerabile a future async parallelization**.

**Fix**: PostgreSQL sequence dedicata:

```sql
CREATE SEQUENCE rientro_sede_seq START 1 MAXVALUE 9999;
```

```python
seq = (await session.execute(text("SELECT nextval('rientro_sede_seq')"))).scalar_one()
return f"9{seq:04d}"
```

**Costo**: 30 min + migration.

---

## MINORI

### M1 — `domain/normativa/__init__.py` vuoto

**File**: `backend/src/colazione/domain/normativa/__init__.py`

Package dichiarato in `Glob` ma file di 1 riga vuota. CLAUDE.md cita
`docs/NORMATIVA-PDC.md` come fonte di verità ma il package code
omonimo è inutilizzato. Rimuoverlo o popolarlo con costanti normative
estratte (oggi sparpagliate fra `builder_pdc/builder.py` e
`split_cv.py`).

---

### M2 — Dead code: `revisioni`

**File**: `backend/src/colazione/domain/revisioni/__init__.py`,
`backend/src/colazione/models/revisioni.py`,
`backend/src/colazione/schemas/revisioni.py`

Modulo presente ma non importato da nessuna API o builder. Verifica
se è scope futuro o residuo di un'idea abbandonata.

---

### M3 — `ciclo_giorni` cap arbitrario a 14

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:809`

```python
ciclo_giorni=max(1, min(14, giro.numero_giornate)),
```

Cap a 14 senza commento. `giro.numero_giornate` è già limitato dal
builder giro (max 30 safety). Documentare o uniformare i cap.

---

### M4 — `_genera_codice_turno` taglia a 48 char senza warning

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:958`

```python
base = (giro.numero_turno or f"GIRO{giro.id}")[:48]
```

Truncation silente. Se `numero_turno` è `G-IMPMAN_MILANO_FIORENZA-001`
(28 char) ok, ma con `G-{LOC_BREVE}-{NNN}` di solito è breve. Vale
la pena di un `len > 48 -> log warning`.

---

### M5 — Smoke `smoke_74_split_cv.py` lascia dati in DB

**File**: `backend/scripts/smoke_74_split_cv.py` (citato in TN-UPDATE
entry 59)

> "Lascia i dati in DB per verifica visuale frontend".

Per re-run idempotente serve un cleanup esplicito (`--cleanup` flag
o programma con codice fisso `TEST_SMOKE_SPLIT_CV` cancellato a
inizio). Altrimenti il secondo run fa errore o crea duplicati.

---

### M6 — `require_role` usa string match invece di enum

**File**: `backend/src/colazione/auth/dependencies.py:66-79`

```python
def require_role(role: str) -> ...:
```

Tutto stringato. Typo (`PIANIFICATORE_GIRRO` invece di `PIANIFICATORE_GIRO`)
non viene preso da mypy. Definire un `Literal["PIANIFICATORE_GIRO",
"PIANIFICATORE_PDC", ...]` o un Enum.

---

### M7 — Auth: refresh token senza revoca server-side

**File**: `backend/src/colazione/auth/tokens.py:62-76`

Il refresh token è stateless (no DB lookup). Quando un utente fa
logout o cambia password, il refresh resta valido fino a scadenza
(30gg). Standard è una blacklist o JWT jti store. Documentato come
scelta MVP, ma da segnalare per future iterazioni.

---

## VERIFICHE NEGATIVE (cose cercate e NON trovate)

- **SQL injection**: tutto via SQLAlchemy con parametrizzazione, niente
  string concatenation. ✓
- **XSS frontend**: React + escape automatico, niente
  `dangerouslySetInnerHTML`. ✓
- **Credenziali hardcoded**: `jwt_secret` ha default debole
  (`"dev-secret-change-me-min-32-characters-long"`) ma è dev-only;
  production deve passare via env. ✓ (ma verifica deploy che lo
  imponga).
- **Violazioni FK incoerenti**: tutti i FK hanno `ondelete`
  esplicito (`CASCADE`, `RESTRICT`, `SET NULL`) coerentemente con
  la semantica. ✓
- **Race condition nel builder**: il builder è single-session. Niente
  scrittura concorrente prevista. ✓ (eccezione: I11 sopra).
- **Memory leak / lazy load N+1**: query batch corrette in
  `_carica_corse`, `genera_turno_pdc`, `get_turno_pdc_dettaglio`.
  Niente lazy loading evidente. ✓
- **bcrypt cost factor**: default 12 = OWASP-aligned. ✓

---

## Riepilogo per priorità di chiusura

**Da chiudere subito (<2h ognuno)**:

- I1, I2, I9 (cleanup mypy/style) — 30 min totali
- C3 (FK programma_id già pronta) — 1h
- M1, M3, M4, M5 (cleanup) — 30 min totali

**Da decidere con utente prima di chiudere**:

- C2 (cap notturno boundary): conferma regola normativa.
- C6 (TIRANO codice): verifica empirica sul DB reale.
- I3 (JWT 72h): scelta MVP vs hardening.
- I4 (impianto = tipo_materiale): conferma semantica voluta.

**Strutturali grandi (1+ gg)**:

- C1 (FK turno_pdc → giro_materiale): refactor pari a migration 0010.
- C4 (preriscaldo dic-feb): richiede modello data-aware.
- C5 (ACC/CV no-overhead): MR successivo Sprint 7.4.
- I8 (test mancanti): 2-3h una tantum, debito permanente.
- I5 (`updated_at`), I7 (mutazione FR), I10 (km_annua),
  I11 (race rientro): batch ~3-4h.

**Non chiudere ora (residui legittimi documentati)**:

- M2 (revisioni): scope futuro.
- M6, M7 (auth refinement): post-MVP.

---

## Note metodologiche

- Review eseguita seguendo regole CLAUDE.md (lettura prima di
  proposta, conferma con file:riga, niente sintesi vaghe).
- Numeri di test contati con `Grep`: 415 funzioni `test_*` su 26
  file, allineato con TN-UPDATE entry 59 (414+1).
- Coerenza codice ↔ NORMATIVA-PDC verificata su: cap prestazione
  (riga 53-54 vs §3.1), refezione finestre (riga 58-61 vs §4.1),
  CV gap 65 min (vs §5 e §6), preriscaldo 80' (riga 52 vs §3.3 +
  §8.5), deroga MORTARA/TIRANO (split_cv.py:59 vs §9.2).
- Coerenza codice ↔ MODELLO-DATI: confermata semantica `LocalitaManutenzione`
  (sede materiale) vs `Depot` (sede PdC) — usate correttamente in
  builder.py:514 e split_cv.py:78. Niente confusione strutturale.

Nessun finding emerge da Fausto (review indipendente non richiesta
in questa pass — può essere il prossimo passo se l'utente vuole
una second-opinion sui critici).
