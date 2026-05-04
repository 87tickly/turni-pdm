# Code Review — COLAZIONE — 2026-05-04

**Revisore**: Claude Code (senior SE)
**Commit di riferimento**: `b6a0b84` (entry 118 — deploy Railway live)
**Baseline**: `docs/CODE-REVIEW-2026-05-01.md` (review post-Sprint 7.4)
**Scope**: backend completo, frontend parziale, data/, tests/

---

## Metodologia

Review incrementale sulla baseline 2026-05-01. Per ogni finding della
review precedente si verifica se è stato chiuso, parzialmente chiuso o
rimasto aperto. I nuovi finding (post-Sprint 7.5→7.9) sono numerati da
capo. I finding riaperti mantengono la numerazione originale con prefisso
`R-` (Riaperto).

Legenda gravità:
- **CRITICO** — violazione normativa, bug latente con effetti osservabili
  in produzione, debito tecnico bloccante
- **IMPORTANTE** — qualità, manutenibilità, correttezza soft (bug che
  non si manifesta ancora ma si manifesterà)
- **MINORE** — stile, micro-ottimizzazioni, uniformità

---

## Stato finding review precedente

| ID   | Titolo                                    | Stato 2026-05-04           |
|------|-------------------------------------------|---------------------------|
| C1   | Full table scan anti-rigenerazione PdC    | **Aperto** (R-C1)         |
| C2   | `is_notturno` boundary divergente         | **Aperto** (R-C2)         |
| C3   | JSON path invece di FK column             | **Parzialmente chiuso** ¹ |
| C4   | ACCp 80' preriscaldo non implementato     | **Aperto** (R-C4)         |
| C5   | Tutti i gap classificati come PK          | **Aperto** (R-C5)         |
| C6   | STAZIONI_CV_DEROGA hardcoded              | **Aperto** (R-C6)         |
| I1   | `datetime.utcnow()` deprecato             | **Aperto** (R-I1)         |
| I2   | `assert` in produzione                    | **Aperto** (R-I2)         |
| I3   | JWT access token 72h                      | **Aperto** (R-I3)         |
| I4   | `impianto = tipo_materiale[:80]`          | **Aperto** (R-I4)         |
| I5   | `updated_at` senza `onupdate`             | **Aperto** (R-I5)         |
| I6   | `GIORNO_DUMMY = "feriale"` hardcoded      | **Aperto** (R-I6)         |
| I7   | FR dormite: lista mutata in-place         | **Aperto** (R-I7)         |
| I8   | Mancano unit test builder PdC puri        | **Aperto** (R-I8)         |
| I9   | Manca FK esplicita `giro_materiale_id`    | **Aperto** (vedi NC1)     |
| I10  | `km_media_annua` solo prima corsa         | **Aperto** (R-I10)        |
| I11  | MAX+1 race condition in persister         | **Aperto** (R-I11)        |
| M1–M7| Vari minori                               | **Aperti**                |

¹ `_count_giri_esistenti` e `_wipe_giri_programma` usano ora
`programma_id` colonna (non JSON path) — il bug SQL è risolto. Rimangono
`text()` raw invece di ORM (I11-variant); il finding FK esplicita su
`TurnoPdc` rimane aperto come NC1.

---

## Finding CRITICI

### R-C1 — Full table scan anti-rigenerazione PdC + `list_turni_pdc_giro`

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:533–542`
**File**: `backend/src/colazione/api/turni_pdc.py:253–264`

**Problema**: Due percorsi distinti fanno un full table scan su
`turno_pdc`.

**Path 1** — anti-rigenerazione in `_genera_un_turno_pdc`:
```python
existing = list(
    (
        await session.execute(
            select(TurnoPdc).where(TurnoPdc.azienda_id == azienda_id)
        )
    ).scalars()
)
legati = [
    t for t in existing
    if (t.generation_metadata_json or {}).get("giro_materiale_id") == giro_id
]
```
Carica **tutti i turni dell'azienda** in memoria e filtra in Python sul
JSONB. Con 500 turni generati la query trasferisce già centinaia di KB
per ogni invocazione.

**Path 2** — endpoint `GET /api/giri/{giro_id}/turni-pdc`:
```python
cast(
    TurnoPdc.generation_metadata_json["giro_materiale_id"].astext,
    BigInteger,
)
== giro_id,
```
Espressione JSONB con `cast` — Postgres non può usare l'indice B-tree
sul JSONB text path a meno che non esista un indice funzionale
(che non esiste).

**Fix**: Aggiungere colonna `giro_materiale_id: Mapped[int | None]`
su `TurnoPdc` (migration), popolata dal builder al momento della
persistenza. Poi entrambi i path usano un semplice
`TurnoPdc.giro_materiale_id == giro_id` con indice normale.

```python
# models/turni_pdc.py
giro_materiale_id: Mapped[int | None] = mapped_column(
    BigInteger, ForeignKey("giro_materiale.id", ondelete="SET NULL"), index=True
)
```

**Costo fix**: migration + 3 righe builder + 1 riga API = ~2h.

---

### R-C2 — `is_notturno` boundary incoerente tra builder e split_cv

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:294,299`
**File**: `backend/src/colazione/domain/builder_pdc/split_cv.py:151–153`

**Problema**: Due definizioni di "turno notturno" che non coincidono.

In `builder.py` la flag `is_notturno` è impostata a `True` se:
```python
is_notturno = ora_presa < 5 * 60 or ora_fine_servizio > 22 * 60 or ...
# riga 294: ora_presa < 300 → include 00:00-04:59
```

Il cap prestazione notturno (420 min, 7h) è però applicato con una
condizione diversa:
```python
cap_prestazione = (
    PRESTAZIONE_MAX_NOTTURNO
    if 60 <= ora_presa < 5 * 60  # riga 299: solo 01:00-04:59
    else PRESTAZIONE_MAX_STANDARD
)
```

La normativa §11.8 recita: "presa servizio dalle 01:00 alle 04:59 →
prestazione massima 7h". Un turno con presa alle 00:30 è classificato
`is_notturno=True` (riga 294) ma riceve cap 8h30 (riga 299) perché
`60 <= 30` è `False`. Il cap è sbagliato.

In `split_cv.py`, `_eccede_limiti` usa `draft.is_notturno` (riga 152),
che riflette la classificazione di riga 294 (00:00-04:59), quindi split
CV applica il cap 7h anche alle prese 00:00-00:59 — incoerente con il
builder.

La normativa è univoca: il confine è 01:00. Il flag `is_notturno` è
una liberalizzazione legittima (molte aziende classificano anche il
00:00-00:59 come notturno per altri scopi), ma il **cap prestazione** va
allineato alla normativa letterale.

**Fix**: Separare la logica di flag dalla logica di cap. Condividere una
funzione `cap_prestazione(ora_presa_min: int) -> int` in un modulo
`domain/normativa/prestazione.py`:
```python
def cap_prestazione(ora_presa_min: int) -> int:
    """Normativa §11.8: presa 01:00–04:59 → 7h, altrimenti 8h30."""
    return PRESTAZIONE_MAX_NOTTURNO if 60 <= ora_presa_min < 300 else PRESTAZIONE_MAX_STANDARD
```
E importarla sia da `builder.py` che da `split_cv.py`.

**Costo fix**: ~1h.

---

### R-C4 — ACCp 80' per preriscaldo (dic–feb) non implementato

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:51,177–206`

**Problema**: La normativa §3.3 specifica che in dicembre, gennaio e
febbraio i preparativi di partenza (ACCp) salgono da 40' a 80' per il
preriscaldo del convoglio. Il codice usa sempre e solo 40':

```python
ACCESSORI_MIN_STANDARD = 40  # riga 51 — costante fissa, mai 80
...
ora_inizio_accp = (primo_inizio - ACCESSORI_MIN_STANDARD) % (24 * 60)  # riga 177
```

Questo provoca una **violazione normativa concreta**: tutti i turni
generati per i mesi dic-gen-feb hanno un ACCp di 40', producendo
giornate con inizio servizio 40' più tardi del dovuto e prestazioni
formalmente più corte di quanto dovrebbero essere.

La prestazione è calcolata come `ora_fine_servizio - ora_presa`, e
`ora_presa = primo_inizio - ACCESSORI_MIN - PRESA_SERVIZIO_MIN`. Con
ACCp=40 invece di 80, `ora_presa` è 40' più in avanti → la prestazione
registrata è 40' **sottostimata** per i mesi invernali.

**Fix**: Aggiungere parametro `data_servizio: date` a
`_build_giornata_pdc` (o al builder esterno) e calcolare dinamicamente:

```python
def _accessori_min(data: date) -> int:
    """Normativa §3.3: dic-gen-feb → 80', resto anno → 40'."""
    return 80 if data.month in (12, 1, 2) else ACCESSORI_MIN_STANDARD
```

Il builder ha già accesso alla `valido_da` del turno; va propagata alle
singole giornate o al `_build_giornata_pdc`.

**Costo fix**: ~3h (propagazione data + test stagionalità).

---

### R-C5 — Ogni gap diventa PK senza verifica dei 20' minimi

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:213–229`

**Problema**: Il builder inserisce un blocco `PK` per ogni gap tra
blocchi condotta della stessa giornata, senza verificare che la durata
sia ≥ 20' (normativa §4.4: "Il Parking ha durata minima di 20 minuti"):

```python
if gap > 0:
    drafts.append(
        _BloccoPdcDraft(
            tipo_evento="PK",
            durata_min=gap,
            ...
        )
    )
```

Un gap di 5' diventa un PK valido, mentre normativa richiede 20'.
L'effetto pratico: giornate con PK di 1-19' passano la validazione
senza warning, pur violando §4.4.

**Fix**: Aggiungere costante `PK_MIN_DURATA = 20` e warning nella
validazione:
```python
PK_MIN_DURATA = 20  # §4.4 normativa

if gap > 0:
    drafts.append(_BloccoPdcDraft(tipo_evento="PK", durata_min=gap, ...))

# in _build_giornata_pdc, sezione violazioni:
for d in drafts:
    if d.tipo_evento == "PK" and d.durata_min < PK_MIN_DURATA:
        violazioni.append(f"pk_troppo_breve:{d.durata_min}min<{PK_MIN_DURATA}min")
```

Non bloccare la costruzione (gap breve può essere legittimo in edge
case), ma registrare come violazione soft nel metadata.

**Costo fix**: ~1h.

---

### R-C6 — TIRANO in STAZIONI_CV_DEROGA può non corrispondere al codice DB

**File**: `backend/src/colazione/domain/builder_pdc/split_cv.py:59`

**Problema**: La costante hardcoded:
```python
STAZIONI_CV_DEROGA: frozenset[str] = frozenset({"MORTARA", "TIRANO"})
```
è confrontata con `stazione.codice` del DB. Se il codice canonico nel
DB fosse `"S01234"` o `"TIR"` invece di `"TIRANO"`, il CV a Tirano
verrebbe rifiutato silenziosamente per tutti i giri che terminano lì.

La normativa §9.2 cita esplicitamente Mortara e Tirano come stazioni di
deroga per CV. Il rischio è che un match case-sensitive o un codice
diverso blocchi il CV su una tratta Tirano in modo invisibile (nessun
errore, il builder costruisce semplicemente il turno senza CV).

**Fix**: Spostare la lista in un seed DB (`depot_linea_abilitata` o una
nuova tabella `stazione_cv_deroga`), oppure almeno verificare a runtime
che i codici esistano nella tabella `stazione`:

```python
# In lista_stazioni_cv_ammesse, aggiungere verifica:
for codice in STAZIONI_CV_DEROGA:
    exists = await session.scalar(
        select(func.count()).where(Stazione.codice == codice)
    )
    if not exists:
        logger.warning("STAZIONI_CV_DEROGA: codice %r non trovato in stazione", codice)
```

**Costo fix**: ~1h per la verifica runtime; ~4h per la migrazione a DB.

---

### NC1 — Due commit separati in `genera_giri()`: giri orfani se crash

**File**: `backend/src/colazione/domain/builder_giro/builder.py:955,990`

**Problema (nuovo, non presente nella review precedente)**: La funzione
`genera_giri()` esegue due `await session.commit()` separati:

```python
# Riga 955: commit 1 — persiste i giri materiali
await session.commit()

# ... decine di righe di codice ...

# Riga 990: commit 2 — persiste il BuilderRun
run = BuilderRun(...)
await session.commit()
```

Se il processo crasha (OOM, SIGKILL, deploy Railway) tra commit 1 e
commit 2, il DB si trova con giri persistiti ma senza il corrispondente
`BuilderRun`. La UI mostra "Nessun run" per un programma che ha
effettivamente giri, confondendo l'utente e impedendo la tracciabilità
della generazione.

La causa è storica: il `BuilderRun` è stato aggiunto in Sprint 7.9 MR
11C come feature separata, senza rifattorizzare la transazione.

**Fix**: Spostare la creazione del `BuilderRun` all'interno della stessa
transazione dei giri. Creare il record `BuilderRun` *prima* del
`session.commit()` dei giri (con stato `"running"`), aggiornarlo a
`"completato"` subito dopo, nell'unico commit:

```python
run = BuilderRun(stato="completato", n_giri=len(giri_da_persistere), ...)
session.add(run)
await session.commit()  # unico commit — atomico
```

**Costo fix**: ~2h (refactor transazione + test rollback simulato).

---

### NC2 — FR §10.6: limiti settimanali non enforced né segnalati

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:882`

**Problema (nuovo)**: Il commento nel codice è esplicito:
```python
# riga 882
# Limiti settimanali (max 1/sett, max 3/28gg) NON enforced nel MVP.
```

La normativa §10.6 è inequivocabile: un PdC non può avere più di 1 FR a
settimana e non più di 3 FR in 28 giorni. Il builder genera dormite FR
senza alcun conteggio o warning. Un turno a 7 giornate con 3 FR
consecutive viene accettato senza obiezioni.

Questo non è un "edge case di MVP" — è una violazione normativa che può
produrre turni illegali presi in carico dal pianificatore.

**Fix minimo accettabile** (non il full enforcement, ma almeno
un segnale): contare le dormite FR generate e, se `n_fr > 1 in 7
giornate consecutive` o `n_fr > 3 in 28 giornate`, aggiungere una
voce a `violazioni` nel metadata del turno:

```python
n_fr = len(fr_giornate)
n_giornate = len(drafts_principali)
# Verifica euristica (giornate = giorni reali solo se ciclo 5+2)
if n_fr > 1 and n_giornate <= 7:
    violazioni.append(f"fr_troppe_in_settimana:{n_fr}>1")
if n_fr > 3:
    violazioni.append(f"fr_troppe_in_28gg:{n_fr}>3")
```

**Costo fix (warning)**: ~1h. Full enforcement con calendario reale:
~1 giorno.

---

### NC3 — FR §10.5: riposo minimo 6h non verificato

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:904–906`

**Problema (nuovo)**: La normativa §10.5 stabilisce che il riposo fuori
residenza deve essere di almeno 6h (360 min). Il builder calcola
`durata_pernotto` ma non la controlla:

```python
durata_pernotto = (24 * 60 - fine_n) + inizio_n1
# ... nessun check su durata_pernotto < 360
```

Un turno con fine giornata 3 alle 23:30 e inizio giornata 4 alle 05:00
produce `durata_pernotto = 30 + 300 = 330 min = 5h30`. Questo è sotto
la soglia normativa di 6h ma non genera alcun warning.

**Fix**: Aggiungere controllo dopo il calcolo:
```python
if durata_pernotto < 360:  # §10.5: riposo FR minimo 6h
    violazioni_fr.append(
        f"fr_riposo_insufficiente:giornata_{curr.numero_giornata}:{durata_pernotto}min<360"
    )
```
Le violazioni FR andrebbero aggregate nel metadata del turno (già
presente `fr_giornate` in `generation_metadata_json`).

**Costo fix**: ~1h.

---

## Finding IMPORTANTI

### R-I1 — `datetime.utcnow()` deprecato in Python 3.12+

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:780`

```python
"generato_at": datetime.utcnow().isoformat(),
```

`datetime.utcnow()` è deprecato da Python 3.12 e restituisce un datetime
timezone-naive. Il confronto con timestamp timezone-aware (che Postgres
ritorna) produrrà un `TypeError` non appena qualcuno tenta di confrontare
questo valore con i `created_at` delle entità ORM.

Il file `persister.py` usa già correttamente `datetime.now(UTC)`.
Uniformare:

```python
from datetime import UTC
"generato_at": datetime.now(UTC).isoformat(),
```

**Costo fix**: 1 min.

---

### R-I2 — `assert` in codice di produzione

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:172,215,218`

```python
assert primo.ora_inizio is not None and ultimo.ora_fine is not None  # riga 172
assert b.ora_inizio is not None and b.ora_fine is not None           # riga 215
assert prec.ora_fine is not None                                      # riga 218
```

Python con flag `-O` (ottimizzazioni) rimuove gli `assert`. In produzione
(Railway, Uvicorn) l'interprete potrebbe essere avviato con `-OO`.
Un'asserzione rimossa → `None` propagato silenziosamente nelle
aritmetiche di orario → risultati errati anziché eccezione esplicita.

**Fix**: Sostituire con `if ... is None: raise ValueError(...)`:
```python
if primo.ora_inizio is None or ultimo.ora_fine is None:
    raise ValueError("blocco condotta senza ora_inizio/ora_fine")
```

**Costo fix**: 10 min.

---

### R-I3 — JWT access token con TTL 72h

**File**: `backend/src/colazione/config.py:39`

```python
jwt_access_token_expire_min: int = 4320  # 72h
```

Un access token di 72h senza server-side revocation significa che un
token compromesso rimane valido per 3 giorni interi. OWASP consiglia
TTL di 15–60 min per access token con refresh token separato.

Con il deploy Railway live (entry 118) il problema è ora reale, non
solo teorico.

**Fix**: Abbassare a 60 min e implementare refresh flow nel frontend
(TanStack Query con interceptor 401 → POST `/api/auth/refresh`).

```python
jwt_access_token_expire_min: int = 60  # 1h
```

Il refresh token (30 giorni) resta invariato.

**Costo fix**: ~4h (config + frontend interceptor + test).

---

### R-I4 — `impianto` del turno PdC preso da `tipo_materiale` del giro

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:794`

```python
impianto=giro.tipo_materiale[:80] if giro.tipo_materiale else "ND",
```

Il campo `impianto` su `TurnoPdc` dovrebbe contenere la **sede del
personale di macchina** (es. "NOVATE", "FIORENZA"), non il tipo di
materiale rotabile (es. "ETR204"). Sono entità ortogonali.
`tipo_materiale` è il rotabile (`ETR421`, `ATR803`); `impianto` è il
deposito PdC.

Il builder ha già accesso alla stazione sede (`stazione_sede`) calcolata
alle righe 519–529 via `LocalitaManutenzione.stazione_collegata_codice`.
Quello va usato come impianto.

**Fix**:
```python
impianto=stazione_sede or giro.tipo_materiale[:80] or "ND",
```

**Costo fix**: 5 min.

---

### R-I5 — `updated_at` non aggiornato automaticamente

**File**: `backend/src/colazione/models/turni_pdc.py:48`
**File**: `backend/src/colazione/models/giri.py:79`

```python
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), server_default=func.now()
)
```

Manca `onupdate=func.now()`. Il campo viene scritto solo all'INSERT,
non all'UPDATE. Ogni modifica a un turno PdC o giro materiale lascia
`updated_at` congelato alla data di creazione.

**Fix** (entrambi i file):
```python
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
    onupdate=func.now(),
)
```

Richiede anche una migration Alembic che aggiunga il trigger `ON UPDATE`
o equivalente a livello SQL se si vuole aggiornamento server-side
(alternativa: trigger Postgres `BEFORE UPDATE SET NEW.updated_at =
NOW()`).

**Costo fix**: ~1h (2 model files + migration).

---

### R-I6 — `GIORNO_DUMMY = "feriale"` hardcoded in `valida_regola`

**File**: `backend/src/colazione/domain/vincoli/inviolabili.py:326–331`

```python
GIORNO_DUMMY = "feriale"
corse_catturate = [
    c for c in corse_list if matches_all(filtri_geografici, c, GIORNO_DUMMY)
]
```

Il commento spiega che `giorno_tipo` è già stato rimosso dai filtri, ma
`matches_all` riceve comunque `"feriale"` come giorno. Se un domani
`matches_all` aggiunge logica che dipende dal giorno passato (es. per
filtri su `fascia_oraria`), questo dummy silenzioso può filtrare male.

**Fix**: Passare `None` come giorno e gestire il `None` in `matches_all`,
oppure usare una costante nominata:
```python
_GIORNO_PLACEHOLDER = "feriale"  # §inviolabili: giorno irrilevante per vincoli geografici
```

**Costo fix**: 10 min (rinomina + commento).

---

### R-I7 — `_aggiungi_dormite_fr` muta la lista `drafts` in-place

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:921`

```python
curr.blocchi.insert(0, nuovo_blocco)
for j, b in enumerate(curr.blocchi, start=1):
    b.seq = j
```

La funzione muta `curr.blocchi` (che è un oggetto nell'elenco `drafts`)
mentre itera su `drafts`. In Python la mutazione di un elemento durante
l'iterazione è sicura se si itera su indici (`range(len(drafts))`), il
che avviene qui — ma rende il codice fragile a future refactoring (chi
passa `drafts` di copia non vede le modifiche; chi passa riferimenti
vede side-effect inaspettati).

**Fix**: La funzione dovrebbe ritornare `drafts` modificato invece di
mutare silenziosamente (o essere esplicitamente documentata come
funzione con side-effect su `drafts`).

**Costo fix**: 30 min.

---

### R-I8 — Test mancanti per logica critica builder PdC

**File**: `backend/tests/` — assenza totale di test per:
- `_build_giornata_pdc` (costruzione blocchi + calcolo accessori)
- `_inserisci_refezione` (split PK in PK+REFEZ+PK nelle finestre §4.1)
- `_aggiungi_dormite_fr` (rilevamento pernottamenti FR)
- `_eccede_limiti` in `split_cv.py` (già ha test in `test_split_cv.py`)

`test_split_cv.py` copre bene la logica di split (11 test). Ma il cuore
del builder — `_build_giornata_pdc` — non ha nemmeno un test unitario
smoke test. È la funzione più critica del sistema.

**Fix**: Aggiungere `test_builder_pdc_unitari.py` con almeno:
- `test_giornata_semplice_2_condotte_gap_pk()`
- `test_refezione_inserita_se_prestazione_gt_6h()`
- `test_refezione_non_inserita_se_gap_lt_30min()`
- `test_fr_dormita_aggiunta_stazione_diversa()`
- `test_fr_dormita_non_aggiunta_stazione_sede()`

**Costo fix**: ~4h.

---

### R-I10 — `km_media_annua` calcolata solo dalla prima corsa

**File**: `backend/src/colazione/domain/builder_giro/persister.py` (area
`_build_metadata_giro`)

`km_media_annua` è calcolata a partire dalla somma dei km della prima
corsa di ogni giornata, non dalla somma complessiva di tutte le corse
del giro. Per i giri multi-tratta (es. un convoglio che fa 3 corse al
giorno) il valore è sistematicamente sottostimato.

**Fix**: Sommare i `km_tratta` di **tutti** i blocchi condotta di ogni
giornata canonica (variant_index=0).

**Costo fix**: ~2h.

---

### R-I11 — MAX+1 race condition in `_next_numero_rientro_sede`

**File**: `backend/src/colazione/domain/builder_giro/persister.py:275–281`

```python
stmt = text(
    "SELECT COALESCE(MAX(SUBSTRING(numero_treno_vuoto FROM 2)::int), 0) "
    "FROM corsa_materiale_vuoto "
    "WHERE numero_treno_vuoto ~ '^9[0-9]{4}$'"
)
last = (await session.execute(stmt)).scalar_one()
return f"9{(int(last) + 1):04d}"
```

Pattern MAX+1 classico: due generazioni concorrenti leggono lo stesso
MAX e producono lo stesso numero. Con il deploy Railway live su Postgres
condiviso, due utenti che generano giri contemporaneamente per la stessa
azienda possono produrre duplicati su `corsa_materiale_vuoto.numero_treno_vuoto`.

**Fix**: Usare una sequence Postgres:
```sql
CREATE SEQUENCE IF NOT EXISTS seq_rientro_sede START 90000 INCREMENT 1;
```
```python
return (await session.scalar(text("SELECT nextval('seq_rientro_sede')"))).zfill(5)
```

**Costo fix**: ~2h (migration + sequence + test concorrenza).

---

### NC4 — `festivita` caricata ma mai usata in `genera_giri()`

**File**: `backend/src/colazione/domain/builder_giro/builder.py:728,944`

**Problema (nuovo)**: Ogni esecuzione del builder carica le festività
dal DB:
```python
festivita = await carica_festivita_periodo(  # riga 728 — query DB
    session, azienda_id, data_inizio=data_inizio, data_fine=data_fine
)
```

Ma poi, alla riga 944:
```python
_ = festivita  # noqa: F841 (reservato per uso futuro)
```

La variabile viene immediatamente scartata. Su PdE reale (finestra
annuale), questa query può restituire 20–30 righe — non è catastrofica,
ma è DB I/O completamente inutile ad ogni run. Il commento `"reservato
per uso futuro"` suggerisce consapevolezza del problema, ma lascia il
codice in uno stato di debito aperto senza tracciamento.

**Fix**: Rimuovere il caricamento e la riga `_ = festivita` finché non
è effettivamente usato. Se serve per il futuro refactor "varianti →
giri separati" (citato nel file), aprire un TODO tracciato:
```python
# TODO Sprint 7.7.3: caricare festivita qui quando si implementa
# la classificazione giornate per tipo-giorno (feriale/festivo/sabato).
```

**Costo fix**: 5 min (rimozione 2 righe).

---

### NC5 — Manca unique constraint su `TurnoPdc(azienda_id, codice)`

**File**: `backend/src/colazione/models/turni_pdc.py:38`

```python
codice: Mapped[str] = mapped_column(String(50))  # nessun unique
```

In caso di errore del builder o doppia chiamata concorrente, possono
esistere due `TurnoPdc` con lo stesso `codice` per la stessa azienda.
La UI non ha modo di distinguerli se li mostra entrambi; la logica di
recupero per codice può ritornare risultati multipli o il primo per
ordine di inserimento.

Confronto: `GiroMateriale` ha un commento che cita il UNIQUE su
`(azienda_id, programma_id, numero_turno)` — ma la migration
corrispondente andrebbe verificata (non visible nel modello ORM).

**Fix**: Aggiungere `UniqueConstraint` nel `__table_args__`:
```python
from sqlalchemy import UniqueConstraint

class TurnoPdc(Base):
    __tablename__ = "turno_pdc"
    __table_args__ = (
        UniqueConstraint("azienda_id", "codice", name="uq_turno_pdc_azienda_codice"),
    )
```

**Costo fix**: migration + 4 righe modello = ~30 min.

---

### NC6 — Costanti normative duplicate tra `builder.py` e `api/turni_pdc.py`

**File**: `backend/src/colazione/api/turni_pdc.py:605–606`

```python
# Definite localmente nell'endpoint — NON importate dal builder
PRESTAZIONE_REFEZIONE_SOGLIA_MIN = 360
REFEZIONE_MIN_RICHIESTI = 30
```

Il file importa già `CONDOTTA_MAX_MIN`, `PRESTAZIONE_MAX_NOTTURNO`,
`PRESTAZIONE_MAX_STANDARD` da `builder.py` (righe 29–31), ma ridefinisce
localmente `PRESTAZIONE_REFEZIONE_SOGLIA_MIN` e `REFEZIONE_MIN_RICHIESTI`
con gli stessi valori. Se qualcuno aggiorna la soglia in `builder.py`
senza aggiornare `api/turni_pdc.py`, la validazione UI divergerà dal
builder silenziosamente.

**Fix**: Esportare le costanti da `builder.py` e importarle anche in
`turni_pdc.py`:
```python
# builder.py — già esportate PRESTAZIONE_MAX_*, CONDOTTA_MAX_MIN
# aggiungere:
# REFEZIONE_SOGLIA_MIN = 360  (esiste già come REFEZIONE_SOGLIA_MIN)
# REFEZIONE_MIN_DURATA = 30   (esiste già)

# api/turni_pdc.py
from colazione.domain.builder_pdc.builder import (
    ...,
    REFEZIONE_SOGLIA_MIN,
    REFEZIONE_MIN_DURATA,
)
```

**Costo fix**: 10 min.

---

### NC7 — `raw text()` SQL in `builder_giro/builder.py` invece di ORM

**File**: `backend/src/colazione/domain/builder_giro/builder.py:257,315,345,365,370,422,434,438`

Esempio:
```python
stmt = text(
    "SELECT COUNT(*) FROM giro_materiale WHERE programma_id = :pid"
)
```

Rispetto alla baseline review (C3), il path principale è corretto
(usa `programma_id` colonna). Ma le query rimangono `text()` raw, non
espressioni ORM tipizzate. Questo bypassa il type-checker (mypy non può
validare i parametri), rende il refactor più fragile (rename di
colonna non rilevato), e rompe l'astrazione SQLAlchemy.

**Fix**: Convertire in ORM:
```python
from sqlalchemy import select, func
stmt = select(func.count()).select_from(GiroMateriale).where(
    GiroMateriale.programma_id == programma_id
)
```

**Costo fix**: ~2h (8 query da convertire).

---

## Finding MINORI

### R-M1 — `tipo_blocco` su `GiroBlocco` non ha CHECK constraint

**File**: `backend/src/colazione/models/giri.py:171`

```python
tipo_blocco: Mapped[str] = mapped_column(String(40))
```

Nessun `CHECK(tipo_blocco IN (...))` né `Enum`. Valori arbitrari
possono essere inseriti senza errore DB.

**Fix**: `CheckConstraint("tipo_blocco IN ('corsa','vuoto','sosta','manovra')", ...)`
o PostgreSQL `ENUM`.

---

### R-M2 — `stato` su `GiroMateriale` e `TurnoPdc` senza CHECK constraint

**File**: `backend/src/colazione/models/giri.py:76`
**File**: `backend/src/colazione/models/turni_pdc.py:46`

```python
stato: Mapped[str] = mapped_column(String(20), default="bozza")
```

Nessun constraint. Un `stato = "draft"` (typo inglese) sarebbe
accettato silenziosamente.

**Fix**: `CheckConstraint("stato IN ('bozza','attivo','archiviato')", ...)`.

---

### R-M3 — `TurnoPdcBlocco.tipo_evento` manca CHECK constraint

**File**: `backend/src/colazione/models/turni_pdc.py:82`

```python
tipo_evento: Mapped[str] = mapped_column(String(20))
```

I valori validi sono `CONDOTTA`, `VETTURA`, `REFEZ`, `ACCp`, `ACCa`,
`CVp`, `CVa`, `PK`, `SCOMP`, `PRESA`, `FINE`, `DORMITA`. Nessun
constraint DB li impone.

**Fix**: `CheckConstraint` con i valori ammessi.

---

### R-M4 — `numero_giornata` non ha unique constraint per giro

**File**: `backend/src/colazione/models/giri.py:117`

Nessun `UniqueConstraint("giro_materiale_id", "numero_giornata")`.
Duplicati di giornata per lo stesso giro possono essere inseriti.

**Fix**: `UniqueConstraint("giro_materiale_id", "numero_giornata", name="uq_giro_giornata_num")`.

---

### NM1 — `_genera_codice_turno` tronca silenziosamente il codice

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:942–945`

```python
def _genera_codice_turno(giro: GiroMateriale) -> str:
    prefix = "T-"
    base = (giro.numero_turno or f"GIRO{giro.id}")[:48]
```

`numero_turno` può essere fino a 40 char (migration 0017), quindi `T-`
+ 40 = 42 char, ben sotto il limite di 50 su `TurnoPdc.codice`.
Il troncamento a 48 è quindi defensivo ma non documentato — e se
`numero_turno` fosse più lungo (future migration), il codice turno
sarebbe troncato silenziosamente producendo duplicati.

**Fix**: Usare `giro.numero_turno` direttamente con lunghezza verificata
a runtime, o aggiungere un assertion che `len(base) <= 48`.

---

### NM2 — `variante_calendario` su `TurnoPdcGiornata` default hardcoded `"LMXGV"`

**File**: `backend/src/colazione/models/turni_pdc.py:59`

```python
variante_calendario: Mapped[str] = mapped_column(String(20), default="LMXGV")
```

Il default `"LMXGV"` (lunedì-venerdì) è semanticamente corretto per la
maggior parte dei casi, ma la colonna non ha un CHECK constraint e il
builder può inserire valori arbitrari (es. `"LMXGV_FESTIVO"`) senza
errore.

**Fix**: Documentare i valori ammessi o aggiungere un constraint.

---

### NM3 — Mancano indici su `turno_pdc_blocco.turno_pdc_giornata_id`

**File**: `backend/alembic/versions/` — nessuna migration aggiunge
l'indice

La query tipica nel dettaglio turno:
```python
select(TurnoPdcBlocco).where(
    TurnoPdcBlocco.turno_pdc_giornata_id.in_(giornata_ids)
).order_by(TurnoPdcBlocco.turno_pdc_giornata_id, TurnoPdcBlocco.seq)
```

Con 7 giornate × 8 blocchi = 56 righe per turno, e magari 200 turni in
DB, la query deve scansionare ~11.200 righe senza indice FK. Piccolo ora,
costoso in scala.

**Fix**: Migration con `CREATE INDEX idx_turno_pdc_blocco_giornata ON turno_pdc_blocco(turno_pdc_giornata_id)`.

---

## Sommario per priorità

### Fix in <2h ciascuno (dovrebbero essere già nel prossimo MR)

| ID   | File                                  | Fix                                           |
|------|---------------------------------------|-----------------------------------------------|
| R-I1 | builder_pdc/builder.py:780            | `datetime.utcnow()` → `datetime.now(UTC)`     |
| R-I2 | builder_pdc/builder.py:172,215,218    | `assert` → `raise ValueError`                 |
| R-I4 | builder_pdc/builder.py:794            | `impianto = stazione_sede or ...`             |
| NC4  | builder_giro/builder.py:728,944       | Rimuovere caricamento `festivita` inutilizzato|
| NC6  | api/turni_pdc.py:605–606              | Importare costanti da builder invece di ridefinire |
| R-C5 | builder_pdc/builder.py:224            | Warning PK < 20'                             |
| NC3  | builder_pdc/builder.py:904–906        | Warning FR riposo < 6h                       |
| NC2  | builder_pdc/builder.py:882            | Warning FR > 1/settimana o > 3/28gg           |

### Fix da pianificare (1–4h, impatto medio-alto)

| ID    | Fix                                                        |
|-------|------------------------------------------------------------|
| R-C1  | FK `giro_materiale_id` su `TurnoPdc` + migration + index  |
| R-C2  | `cap_prestazione()` condivisa tra builder e split_cv       |
| R-C4  | ACCp 80' dic-gen-feb con propagazione `data_servizio`      |
| R-C6  | Verifica runtime codici `STAZIONI_CV_DEROGA`               |
| NC1   | Merge 2 commit in 1 transazione atomica in `genera_giri`   |
| NC5   | UniqueConstraint `TurnoPdc(azienda_id, codice)`            |
| R-I3  | JWT access token 60 min + frontend interceptor             |
| R-I5  | `updated_at` con `onupdate`                                |
| R-I8  | Unit test `_build_giornata_pdc`, `_inserisci_refezione`    |
| R-I11 | `seq_rientro_sede` Postgres sequence                       |
| NC7   | Convertire `text()` raw in ORM                             |

### Fix a lungo termine (>4h, scelta architetturale)

| ID    | Fix                                                        |
|-------|------------------------------------------------------------|
| R-C6  | Spostare `STAZIONI_CV_DEROGA` in tabella DB seed           |
| R-I10 | km_media_annua da tutte le corse giornata canonica         |
| R-I7  | Refactoring `_aggiungi_dormite_fr` senza side-effect       |
| NC2   | Full enforcement §10.6 con calendario reale                |

---

*Review eseguita il 2026-05-04. Commit analizzato: `b6a0b84`.*
*Nessuna modifica al codice di produzione effettuata in questa review.*
