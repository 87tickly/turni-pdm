# Code Review COLAZIONE — 2026-05-21

> **Autore**: NINO (Claude Code), review autonoma richiesta dall'utente.
>
> **Scope**: intero repo `turni-pdm` — backend Python, frontend TypeScript,
> migrations Alembic, test suite, scripts. Nessuna modifica al codice di
> produzione.
>
> **Basi lette**:
> - `CLAUDE.md` (regole operative)
> - `TN-UPDATE.md` (prime 5 entry — contesto Sprint 8.3/8.4)
> - `docs/METODO-DI-LAVORO.md` (7 regole)
> - `docs/NORMATIVA-PDC.md` (fonte verità dominio)
> - `docs/MODELLO-DATI.md` (modello concettuale)
>
> **Stato base**: commit `6571374` (Sprint 8.4 G3, entry 301).
>
> I finding sono organizzati per gravità: **CRITICO** → **IMPORTANTE**
> → **MINORE**. Per ogni finding: `file:riga`, motivazione, impatto,
> fix proposto.

---

## Indice

- [CRITICO (5 finding)](#critico)
- [IMPORTANTE (10 finding)](#importante)
- [MINORE (6 finding)](#minore)
- [Riepilogo tabellare](#riepilogo)

---

## CRITICO

### C1 — Preriscaldo 80' completamente assente da tutti i builder

**File**:
- `backend/src/colazione/domain/builder_pdc/builder.py:57`
- `backend/src/colazione/domain/builder_pdc/giornata_base.py:38` (re-export)
- (stesso valore usato in `multi_turno.py` e `deposito_first.py` via giornata_base)

**Normativa violata**: §3.3

> ACCp con preriscaldo ● (dicembre–febbraio) = **80'** (non 40').

**Problema**:

```python
ACCESSORI_MIN_STANDARD = 40  # sempre 40, anche in inverno
```

La firma di `_build_giornata_pdc` (e quindi `build_giornata_pdc`) non ha
alcun parametro `mese`, `data_operativa` o `is_preriscaldo`. Nessun
calendar check. Ogni turno generato dicembre-febbraio ha ACCp calcolato
di 40' invece di 80' → la presa servizio del PdC è posizionata di 40
minuti tardi rispetto al reale.

**Impatto**: ogni turno invernale prodotto ha `inizio_prestazione` 40'
sbagliato, violazione §3.3 silente, presa-servizio non corretta in
produzione. I turni generati tra novembre e marzo sono normativamente
invalidi senza che venga sollevata alcuna violazione.

**Fix proposto**:

1. Aggiungere parametro `data_operativa: date | None` a `build_giornata_pdc`.
2. Calcolare `is_preriscaldo = data_operativa is not None and data_operativa.month in {12, 1, 2}`.
3. Sostituire `ACCESSORI_MIN_STANDARD` con:
   ```python
   accp_min = 80 if is_preriscaldo else 40
   acca_min = 40  # ACCa invariato (§3.3)
   ```
4. Aggiornare tutti i chiamanti: `deposito_first.py`, `multi_turno.py`,
   `split_cv.py` (la firma pubblica passa già `data_operativa` in alcuni
   punti — allineare).

---

### C2 — assert IDOR check in API HTTP

**File**: `backend/src/colazione/api/giri.py:2891`

```python
assert target_giro.azienda_id == user.azienda_id, (
    f"IDOR: giro {target_giro.id} non appartiene ad azienda {user.azienda_id}"
)
```

**Problema**: `assert` è un controllo di **sicurezza multi-tenant** che
verifica l'appartenenza del giro al tenant corretto (prevenzione IDOR).
Con `python -O` (standard in molti ambienti prod e Docker) tutti gli
`assert` vengono eliminati a compile time. L'`assert` diventa un
**no-op silente**: se un utente di azienda A riesce a passare l'id di
un giro di azienda B, la request procede senza errori.

**Impatto**: potenziale IDOR (Insecure Direct Object Reference) in
produzione con `python -O`. Il dato di un'altra azienda è accessibile.

**Fix proposto**: sostituire con eccezione HTTP esplicita:

```python
if target_giro.azienda_id != user.azienda_id:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                        detail="giro non appartiene all'azienda corrente")
```

---

### C3 — `updated_at` non si aggiorna mai dopo l'INSERT

**File**: tutti i modelli con colonna `updated_at`:
- `backend/src/colazione/models/turni_pdc.py:59`
- `backend/src/colazione/models/giri.py:79`
- `backend/src/colazione/models/programmi.py:187`
- `backend/src/colazione/models/anagrafica.py:116, 557`
- `backend/src/colazione/models/personale.py:69`

**Problema**:

```python
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), server_default=func.now()
)
```

`server_default` imposta il valore **solo all'INSERT**. Manca
`onupdate=func.now()` (lato ORM) o un trigger PostgreSQL
`BEFORE UPDATE`. Il risultato: `updated_at` è identico a `created_at`
per tutta la vita della riga, indipendentemente dagli UPDATE successivi.

**Impatto**: audit trail silenziosamente broken. Chi legge `updated_at`
per capire se un record è aggiornato (es. dashboard "ultima modifica",
debug, sync) riceve dati falsi. Colpisce `TurnoPdc`, `GiroMateriale`,
`ProgrammaMateriale`, `Depot`, `Persona`.

**Fix proposto**: aggiungere `onupdate` a ogni colonna:

```python
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
    onupdate=func.now(),  # aggiunge questa riga
)
```

Oppure, in alternativa più robusta, un trigger PostgreSQL
`BEFORE UPDATE SET updated_at = now()` applicato via migration
(immune a bypass ORM con query raw).

---

### C4 — 50 test falliscono su master, root cause non tracciata

**File**: `TN-UPDATE.md` entry 301 (sezione "Verifiche"):

> `⚠️ pytest full backend: 50 fallimenti pre-esistenti su master
> (verificato via git stash → stessi fail). Non sono regressioni di
> questo fix. Backlog.`

**Problema**: la suite `pytest` ha 50 test che falliscono stabilmente
su `master`. Non è documentato:
1. Quali sono i test specifici che falliscono (nomi, file, riga).
2. Qual è la root cause (schema DB mancante? import rotto? fixture
   stale?).
3. Quando sono stati introdotti i fallimenti.

Il commento "Backlog" non è un tracking sufficiente (CLAUDE.md §7:
"chiudere bene quello che si comincia").

**Impatto**: la CI è de facto inutilizzabile come gate di qualità. Un
commit che introduce una regressione non è distinguibile dal rumore
preesistente. Il team non sa se la suite è verde o rossa senza
filtraggio manuale.

**Fix proposto** (in ordine di urgenza):
1. Eseguire `pytest -v 2>&1 | grep FAILED` e documentare i 50 test
   in un tracking issue o sezione dedicata di `TN-UPDATE.md`.
2. Classificare: test rotti per schema (migration mancante?), import
   broken (dipendenza circolare?), logica (behavior cambiato?).
3. Fix o `pytest.mark.skip` con motivazione esplicita e issue number.
   I test `skip` devono riapparire sul radar mensile.

---

### C5 — Registro vetture §15 usa wildcard permanente: over-exclusion sistematica

**File**:
- `backend/src/colazione/domain/builder_pdc/registro_vetture.py:17, 157, 240`
- `backend/src/colazione/domain/builder_pdc/deposito_first.py:542`

**Normativa rilevante**: §15.1-§15.2 ("ogni segmento di treno si
assegna a UN solo PdC, sempre").

**Problema**:

```python
data_operativa=None,  # wild card S4 TODO
```

Il registro cross-PdC viene popolato con `data_operativa=None` (wildcard)
perché `enumera_date_giornata` non è ancora implementato. Il match
wildcard funziona così:

```python
# da registro_vetture.py — None collide con QUALUNQUE data
if None in date_set or data_operativa in date_set:
    return True  # esclusa
```

Quindi: ogni vettura prenotata da un turno PdC viene esclusa per
**tutte le date future** di qualsiasi altro PdC, non solo per la data
specifica del turno che la usa.

**Impatto**: il resolver §7.2 over-esclude vetture → genera più
VOCTAXI del necessario invece di usare treni commerciali disponibili.
Turni PdC più costosi e meno produttivi del reale.

**Fix proposto** (come da TODO stesso):

Implementare `enumera_date_giornata(giro_giornata)` che restituisce
le date concrete (considerando le varianti calendariali). Passare la
data effettiva al registro invece di `None`. Il modello
`GiroFinestraValidita` e `GiroVariante.validita_testo` contengono
le informazioni necessarie.

---

## IMPORTANTE

### I1 — PK di durata < 20' generati come PK normativi

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:257-270`

**Normativa violata**: §4.4

> "PK in arrivo: **20' minimo**. PK in partenza: **20' minimo**."

**Problema**:

```python
gap = _diff(prec.ora_fine, b.ora_inizio)
if gap > 0:
    drafts.append(_BloccoPdcDraft(
        tipo_evento="PK",
        durata_min=gap,  # può essere 1, 3, 5 minuti
        ...
    ))
```

Qualsiasi gap > 0 tra blocchi condotta consecutivi diventa un blocco
`tipo_evento="PK"`. Un gap di 3 minuti genera un `PK` di 3 minuti, che
è operativamente impossibile: il PdC non può mettere in sicurezza il
treno, fare pausa, e riprendere in 3 minuti.

**Impatto**: turni con blocchi `PK` falsamente piccoli. La UI li mostra
come PK normativi, ma violano §4.4. Nessuna violazione viene sollevata.

**Fix proposto**: separare i gap in due categorie:

```python
PK_MIN_DURATA = 40  # 20' in + 20' out = PK completo minimo normativo
if gap >= PK_MIN_DURATA:
    tipo = "PK"
elif gap > 0:
    tipo = "SOSTA"  # gap tecnico non normativo (nuovo tipo_evento)
```

Oppure: aggiungere violazione `"pk_sotto_minimo"` quando `gap < 20`.
La soluzione "SOSTA" è preferibile perché distingue il tipo semantico
senza falsificare il normativo.

---

### I2 — `giornata_base.py` è un alias layer, non un facade

**File**: `backend/src/colazione/domain/builder_pdc/giornata_base.py:31-58`

**Problema**: il modulo è descritto come "API stabile del builder-base"
(finding SEVERO S2) ma importa i simboli privati `_xxx` da `builder.py`
e li ri-assegna con alias:

```python
from colazione.domain.builder_pdc.builder import (
    _aggiungi_dormite_fr,
    _BloccoPdcDraft,
    _build_giornata_pdc,
    ...
)
BloccoPdcDraft = _BloccoPdcDraft
aggiungi_dormite_fr = _aggiungi_dormite_fr
# ecc.
```

Non sposta le definizioni: le definizioni reali sono ancora in
`builder.py`. Il "refactor S2" ha aggiunto indirection senza risolvere
la dipendenza. I test continuano a importare direttamente da `builder.py`
(es. `test_builder_pdc_eta.py:15-18`). Se `builder.py` cambia i simboli
`_xxx`, si rompono sia `giornata_base.py` sia tutti i consumer via
facade.

**Impatto**: falsa sicurezza sul contratto della facade. La manutenzione
di `builder.py` deve ancora tenere conto di tutti i consumer indiretti.

**Fix proposto**: spostare le definizioni da `builder.py` a
`giornata_base.py` (le classi `_BloccoPdcDraft`, `_GiornataPdcDraft`,
le pure functions `_build_giornata_pdc`, `_inserisci_refezione`, ecc.)
e fare in modo che `builder.py` le importi da `giornata_base.py`, non
viceversa. Questo è un refactor di ~100 righe di spostamento ma chiude
il problema strutturalmente.

---

### I3 — `assert` usati come guard conditions in codice di dominio

**File**:
- `backend/src/colazione/domain/builder_pdc/builder.py:210, 253, 256`
- `backend/src/colazione/domain/builder_pdc/multi_turno.py:421, 477, 1140`
- `backend/src/colazione/domain/builder_pdc/riposo_settimanale.py:272, 273`

**Problema**:

```python
assert primo.ora_inizio is not None and ultimo.ora_fine is not None
assert stazione_apertura is not None
assert stazione_chiusura is not None
```

Usati come guard conditions per invarianti di flusso nel dominio
critico. Con `python -O` (common in Docker/produzione) gli `assert`
vengono eliminati a compile time. Se un `GiroBlocco` ha `ora_inizio=None`
(colonna nullable nel modello), il builder procede con `None` e produce
calcoli errati silenziosamente.

**Impatto**: un blocco con orario mancante non viene rilevato → il
builder produce un turno con orari `None` → persiste dati corrotti.
Non è teorico: il modello dichiara `ora_inizio: Mapped[time | None]`.

**Fix proposto**: sostituire ogni `assert` di guardia con eccezione
esplicita:

```python
if primo.ora_inizio is None or ultimo.ora_fine is None:
    raise ValueError(
        f"GiroBlocco {primo.id}: ora_inizio/fine None in blocco valido"
    )
```

(Le `assert` nei test rimangono ovviamente corrette.)

---

### I4 — FIORENZA in `DEPOT_MILANO_MM`: MM non raggiunge Fiorenza

**File**: `backend/src/colazione/domain/builder_pdc/vettura_resolver.py:89`

**Normativa rilevante**: §8.5.1

> "Non esistono tracce pubbliche per il collegamento passivo MI.PG →
> Fiorenza. Si usa sempre un **TAXI**."

**Problema**:

```python
DEPOT_MILANO_MM: frozenset[str] = frozenset({
    "GARIBALDI_ALE", "GARIBALDI_CADETTI", "GARIBALDI_TE",
    "GRECO_TE", "GRECO_S9",
    "FIORENZA",  # ← questo
})
```

Fiorenza è un impianto Trenord (FNM interno), non una stazione servita
dalla metropolitana pubblica milanese. §8.5.1 dichiara esplicitamente
che il collegamento con Fiorenza si fa in taxi, non in MM. Il resolver
genera `SceltaMM` (metro, 30' forfettario) per i PdC con deposito
FIORENZA quando la vettura sfora il cap. Dovrebbe generare `SceltaVOCTAXI`.

**Impatto**: turni PdC con blocco `MM` che non corrisponde a nessuna
realtà operativa. Il PdC non può prendere la metropolitana e arrivare
a Fiorenza.

**Fix proposto**: rimuovere `"FIORENZA"` da `DEPOT_MILANO_MM`. Se in
futuro esisterà un collegamento MM utile verso Fiorenza, aggiungere
con nota esplicita.

---

### I5 — `builder_version` hardcoded a stringa stale

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:1023`

```python
"builder_version": "mvp-7.9-eta",
```

**Problema**: tutti i `TurnoPdc` persistiti via `_persisti_un_turno_pdc`
(chiamato anche da `multi_turno.py` e `deposito_first.py` via `giornata_base`)
portano la versione `"mvp-7.9-eta"` nel `generation_metadata_json`. I
turni generati con `deposito_first` (Sprint 8.2) o `multi_turno` (Sprint
7.10+) hanno una versione sbagliata nel metadata. Non è possibile
distinguere retrospettivamente quale builder ha generato il turno.

**Impatto**: debugging e audit difficili. Quando emerge un bug in produzione,
`builder_version` nel metadata non dice quale path di generazione è
stato usato.

**Fix proposto**: passare `builder_version` come parametro a
`persisti_un_turno_pdc` e valorizzarlo correttamente nel chiamante:

```python
# in deposito_first.py
"builder_version": "deposito-first-8.2",

# in multi_turno.py
"builder_version": "multi-turno-dp-7.10",

# in builder.py (legacy)
"builder_version": "legacy-monolithic-7.9",
```

---

### I6 — Ciclo settimanale §11 non enforced come hard constraint nel builder

**File**: `backend/src/colazione/domain/builder_pdc/deposito_first.py:32-33` (docstring)

**Normativa rilevante**: §11 (ciclo 5+2, riposo settimanale ≥ 62h
con 2 giorni solari).

**Problema**: il builder `deposito_first` chiama `valida_riposo_settimanale`
e `calcola_e_valida_riposi_intraturno` in modalità **validation-only**
post-costruzione. Se il turno viola §11, viene segnalato come violazione
nel campo `violazioni[]` ma il builder **non rigetta la giornata né
riprova**. Il turno viene persistito con la violazione inclusa.

```python
# da deposito_first — validation post-hoc, non constraint
riposo_viol = valida_riposo_settimanale(...)
violazioni.extend(riposo_viol)
# il turno viene persistito ugualmente
```

**Impatto**: turni con violazioni §11 vengono prodotti e persistiti.
Il pianificatore deve scoprirle a mano dal pannello violazioni. In un
sistema orientato alla compliance, i vincoli §11 dovrebbero essere
HARD (scarta il candidato e prova configurazione alternativa).

**Fix proposto**: verificare le violazioni §11 e, se presenti per una
giornata HARD-violated (es. riposo < 62h), marcare la giornata come
scartata e ritornare `None` (stesso pattern del check `condotta_max`
a `deposito_first.py`).

---

### I7 — `eslint-disable exhaustive-deps` senza spiegazione

**File**:
- `frontend/src/routes/pianificatore-giro/ModificaGruppoDialog.tsx:75`
- `frontend/src/routes/pianificatore-giro/WizardDaLineeDialog.tsx:96`
- `frontend/src/routes/pianificatore-giro/GiroDettaglioRoute.tsx` (presunto, da grep)

**Problema**:

```tsx
// eslint-disable-next-line react-hooks/exhaustive-deps
useEffect(() => { ... }, [dipendenzaIncompleta]);
```

`exhaustive-deps` viene disabilitata senza motivazione inline. Le
closure nelle dependency array incomplete possono catturare valori
stale (stale closure). Nei form dialogs complessi con stato condiviso
parent-child, questo produce comportamenti erratici difficili da
debuggare (es. il dialog che mostra dati della submission precedente).

**Fix proposto**: per ogni occorrenza, scegliere una delle tre opzioni:
1. Completare la dependency array (se sicuro).
2. Usare `useCallback`/`useMemo` per stabilizzare le referenze.
3. Mantenere il disable con commento esplicito della ragione:
   `// eslint-disable-next-line react-hooks/exhaustive-deps — intenzionale: vuole solo il mount`.

---

### I8 — `window.alert()` per errori API: 15+ occorrenze nel frontend

**File** (campione):
- `frontend/src/routes/manutenzione/DashboardRoute.tsx:179`
- `frontend/src/routes/pianificatore-giro/ProgrammaDettaglioRoute.tsx:339,411,462,556`
- `frontend/src/routes/pianificatore-giro/ProgrammiRoute.tsx:589,600,624`
- `frontend/src/routes/pianificatore-giro/GiroDettaglioRoute.tsx:371,394,571,580`
- `frontend/src/routes/pianificatore-pdc/DashboardRoute.tsx:840`

**Problema**: gli errori API sono comunicati via `window.alert()`:

```tsx
window.alert(`Conferma fallita: ${msg}`)
```

`window.alert` è un dialog modale bloccante, non è parte del design
system (niente Tailwind/shadcn), non si può stilare, non supporta
testo ricco, blocca il main thread. In produzione Railway su browser
moderni può essere soppresso dalle impostazioni utente.

**Fix proposto**: implementare un `useToast()` hook (shadcn `Toaster`
già disponibile nel repo come componente UI) o un context globale di
notification, e rimpiazzare tutte le `window.alert` con
`toast({ title: "Errore", description: msg, variant: "destructive" })`.
Un'ora di lavoro, elimina 15+ occorrenze.

---

### I9 — Migrazione `0027` mancante: gap nella sequenza Alembic

**File**: `backend/alembic/versions/`

La sequenza salta da `0026_repair_depots_persone.py` a
`0028_seed_depots_per_azienda.py`. `0027` non esiste nel repo.

**Problema**: un gap nella sequenza Alembic indica una delle seguenti
situazioni:
1. Una migrazione è stata applicata manualmente a un DB di sviluppo e
   poi eliminata senza aggiornare la chain Alembic.
2. Una migrazione è stata scritta e committata, poi rimossa da un
   `git reset` o `git rebase`.
3. La chain `down_revision` di `0028` potrebbe puntare erroneamente a
   `0026` o a `0027` (che non esiste).

**Impatto**: un ambiente fresh che esegue `alembic upgrade head` potrebbe
fallire se la chain è spezzata. Il check `test_check_alembic_revisions.py`
(esiste nel repo) dovrebbe coprirlo, ma se il test è tra i 50 che
falliscono (finding C4), passa inosservato.

**Fix proposto**: eseguire `alembic history` e verificare che la chain
sia lineare e continua. Se `0028.down_revision == "0026"` la chain è
intatta e il gap è solo un numero mancante (ridenominare non è
necessario, ma documentare la causa in `TN-UPDATE.md`).

---

### I10 — `builder_pdc/builder.py` e `builder_giro/builder.py` privi di test unitari diretti

**File**: nessun file `test_builder_pdc_builder.py` né `test_builder_giro_builder.py` esiste.

**Problema**: i moduli centrali del dominio — `builder.py` per entrambi
i builder giro e PdC — non hanno test unitari propri. I test esistenti
coprono moduli ausiliari (multi_turno_dp, deposito_first, split_cv,
aggregazione_a2, ecc.) ma non le pure functions fondamentali:

- `_build_giornata_pdc` (presa, ACCp, PK, REFEZ, ACCa, FINE)
- `_inserisci_refezione` (ancoraggio finestra, split PK)
- `_inserisci_refezione_ai_bordi` (fallback bordi)
- `_aggiungi_dormite_fr` (identificazione FR cross-giornata)
- `_calcola_violazioni_cap_fr` (ha test — `test_builder_pdc_eta.py`)
- `_genera_codice_turno` (ha test — `test_builder_pdc_eta.py`)

Le funzioni `_inserisci_refezione` e `_aggiungi_dormite_fr` contengono
logica normativa critica (finestre refezione §4.1, FR §10) e NON SONO
testate in isolamento. Il bug del finding C1 (preriscaldo mancante)
e I1 (PK sotto minimo) non sarebbero rilevabili da test anche se
esistessero finché la firma non include il parametro.

**Fix proposto**: aggiungere `backend/tests/test_builder_pdc_core.py`
con test delle pure functions:

```python
def test_inserisci_refezione_finestra_pranzo(): ...
def test_inserisci_refezione_fallback_bordo_fine(): ...
def test_build_giornata_pdc_prestazione_max(): ...
def test_build_giornata_pdc_condotta_max(): ...
def test_aggiungi_dormite_fr_sede_diversa(): ...
```

Costo stimato: 3-4 ore, 20-25 test. Alta resa: ogni future modifica
alle pure functions ha copertura automatica.

---

## MINORE

### M1 — Commenti di Sprint nel codice sorgente (pervasivo)

**File**: pressoché ogni file in `domain/builder_pdc/` e `api/giri.py`.

```python
# Sprint 7.4 MR 2: split CV intermedio.
# Sprint 8.2 MR-PD-FIX-SEVERO 3b A1: numero treno vettura (popolato
# SOLO per tipo_evento='VETTURA' rientro deposito). FK testuale al ...
```

Centinaia di commenti di tipo `Sprint X.Y MR Z` nel codice sorgente.
Appartengono al commit history e a `TN-UPDATE.md`, non al codice.
Si deteriorano col tempo (lo Sprint 7.4 non dice più niente al
manutentore tra 1 anno). L'unico commento utile nel codice sorgente è
il "perché non ovvio" (vincolo operativo, workaround bug specifico).

**Fix proposto**: non una pulizia massiva (troppo rischio di rumore
nel diff), ma come regola operativa: i nuovi commit non aggiungono
commenti `Sprint X.Y`.

---

### M2 — Dead code con `noqa: F841` come ornamento

**File**:
- `backend/src/colazione/domain/builder_giro/varianti_calendariali.py:293`
- `backend/src/colazione/domain/builder_giro/builder.py:2757-2758`

```python
_ = Counter  # noqa: F841 — riservato per estensioni
_ = festivita  # noqa: F841 (reservato per uso futuro)
_ = calcola_etichetta_giro  # noqa: F841 (export pubblico mantenuto)
```

Tre variabili dummy assegnate e immediatamente silenziati con `noqa`.
Se `Counter`, `festivita`, `calcola_etichetta_giro` devono essere
nel namespace, devono stare in `__all__`. Se non devono, vanno rimossi.

**Fix proposto**: se il simbolo deve essere esportato, aggiungerlo
a `__all__`. Altrimenti eliminare la riga.

---

### M3 — `tipo_evento` in `TurnoPdcBlocco` senza CHECK constraint

**File**: `backend/src/colazione/models/turni_pdc.py:98`

```python
tipo_evento: Mapped[str] = mapped_column(String(20))
```

La colonna `tipo_evento` accetta qualsiasi stringa VARCHAR(20).
I valori validi sono: `CONDOTTA`, `VETTURA`, `REFEZ`, `ACCp`, `ACCa`,
`CVp`, `CVa`, `PK`, `SCOMP`, `PRESA`, `FINE`, `MM`, `VOCTAXI`,
`DORMITA`. Un valore errato (es. `"condotta"` minuscolo, `"FAKE"`)
viene persistito senza errore.

**Fix proposto**: aggiungere un CHECK constraint in migration:

```python
CheckConstraint(
    "tipo_evento IN ('CONDOTTA','VETTURA','REFEZ','ACCp','ACCa',"
    "'CVp','CVa','PK','SCOMP','PRESA','FINE','MM','VOCTAXI','DORMITA')",
    name="ck_turno_pdc_blocco_tipo_evento"
)
```

---

### M4 — `profilo` in `TurnoPdc` sempre "Condotta", senza CHECK

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:1058`

```python
turno = TurnoPdc(
    ...
    profilo="Condotta",  # hardcoded, nessun altro valore mai usato
)
```

Il campo `profilo` nel modello `TurnoPdc` è `String(40)` senza CHECK
constraint e non viene mai variato dal builder. Se il valore è sempre
"Condotta", il campo non aggiunge informazione. Se in futuro ci sarà
un profilo "Accompagnatore" o "Capotreno", il tipo dovrebbe essere un
enum.

**Fix proposto**: in attesa di casi d'uso reali, aggiungere almeno un
CHECK `profilo IN ('Condotta')` per documentare il vincolo attuale e
impedire valori arbitrari.

---

### M5 — `km=0` hardcoded nelle giornate PdC

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:1078`

```python
gg_orm = TurnoPdcGiornata(
    ...
    km=0,  # non calcolato
)
```

Il campo `km` in `TurnoPdcGiornata` è sempre 0. I km della giornata
(sum dei `km` delle corse coperte) non vengono mai calcolati né
persistiti. Le statistiche km del pianificatore PdC sono quindi sempre
a zero.

**Fix proposto**: calcolare `km = sum(b.km_percorso for b in blocchi_giro if b.km_percorso)` durante la costruzione della giornata e persistirlo.

---

### M6 — Auth: token revocation assente (documentato ma non tracciato)

**File**: `backend/src/colazione/auth/dependencies.py:17-19`

```python
# Se un utente è disattivato o un ruolo è revocato, il cambio
# diventa effettivo solo all'access token successivo (max 72h
# con la config attuale). Per MVP è accettabile.
```

La finestra di 72h (3 giorni) in cui un utente disabilitato ha ancora
accesso è dichiarata come "accettabile per MVP" ma non è tracciata
come debito tecnico in `TN-UPDATE.md`. Per un sistema che gestisce
dati operativi di pianificazione ferroviaria, 72h è un intervallo
operativamente significativo.

**Fix proposto**: documentare esplicitamente in `TN-UPDATE.md` come
debito tecnico con stima costo (JWT blacklist via Redis, o riduzione
`JWT_ACCESS_TOKEN_EXPIRE_MIN` a 15-30 min con refresh più frequente).
Non è urgente per MVP ma deve avere un owner.

---

## Riepilogo

| ID | Gravità | Area | Titolo breve | Azione richiesta |
|----|---------|------|-------------|-----------------|
| C1 | CRITICO | Domain/Builder | Preriscaldo 80' assente | Fix parametro + calendar check |
| C2 | CRITICO | API/Security | assert IDOR check bypassabile | → HTTPException 403 |
| C3 | CRITICO | Models | `updated_at` non si aggiorna | `onupdate=func.now()` |
| C4 | CRITICO | Tests | 50 test falliscono, root cause non tracciata | Documenta + fix |
| C5 | CRITICO | Domain | Registro vetture wildcard: over-exclusion | Implementa `enumera_date_giornata` |
| I1 | IMPORTANTE | Domain/Builder | PK sotto 20' generati come normativi | Soglia minima + tipo SOSTA |
| I2 | IMPORTANTE | Architecture | `giornata_base.py` è alias, non facade | Sposta definizioni |
| I3 | IMPORTANTE | Domain | `assert` bypassabili in dominio critico | → `ValueError`/`RuntimeError` |
| I4 | IMPORTANTE | Domain | FIORENZA in DEPOT_MILANO_MM errato | Rimuovere da set |
| I5 | IMPORTANTE | Domain | `builder_version` stale in metadata | Parametrizzare versione |
| I6 | IMPORTANTE | Domain | §11 ciclo settimanale validation-only | Hard constraint nel builder |
| I7 | IMPORTANTE | Frontend | `eslint-disable exhaustive-deps` senza nota | Documentare o fixare |
| I8 | IMPORTANTE | Frontend | `window.alert()` per errori API | Toast/notification component |
| I9 | IMPORTANTE | Migrations | Gap `0027` mancante in Alembic | Verificare chain |
| I10 | IMPORTANTE | Tests | Builder core senza test unitari | Aggiungere `test_builder_pdc_core.py` |
| M1 | MINORE | Code | Commenti Sprint nel sorgente | Regola operativa nuovi commit |
| M2 | MINORE | Code | Dead code `_ = X  # noqa: F841` | `__all__` o eliminare |
| M3 | MINORE | Models | `tipo_evento` senza CHECK constraint | Migration CHECK |
| M4 | MINORE | Models | `profilo` hardcoded senza CHECK | Migration CHECK o enum |
| M5 | MINORE | Domain | `km=0` hardcoded, mai calcolato | Calcolo dal giro |
| M6 | MINORE | Auth | Token revocation 72h non tracciata | TN-UPDATE debt tracking |

---

## Priorità di fix raccomandata

**Immediati (prossima sessione)**:
1. **C2** (assert IDOR) — 15 min, alto impatto sicurezza
2. **C3** (`updated_at`) — 30 min + migration, audit trail broken
3. **C4** (50 test rotti) — 2h diagnostica, prerequisito per CI affidabile
4. **I4** (FIORENZA in MM) — 5 min, violazione normativa chiara

**Sprint dedicato**:
5. **C1** (preriscaldo 80') — richiede propagazione parametro `data_operativa` su tutti i builder
6. **C5** (registro vetture wildcard) — richiede implementare `enumera_date_giornata`
7. **I1** (PK sotto 20') — modifica `_build_giornata_pdc` + test
8. **I10** (test builder core) — nuovo file di test, nessun rischio

**Refactoring pianificato**:
9. **I2** (`giornata_base` facade) — richiede piano di spostamento coordinate
10. **I3** (assert → ValueError) — sweep meccanico, basso rischio

---

*Review eseguita senza modifiche al codice di produzione.*
*Riferimento commit base: `6571374` (Sprint 8.4 G3, 2026-05-10).*
