# CODE REVIEW — COLAZIONE — 2026-05-25

> Reviewer: NINO (Claude Code)
> Scope: repo intero — backend, frontend, domain, tests, migrations
> Ref normativa: `docs/NORMATIVA-PDC.md` (fonte verità)
> Commit HEAD: `6571374` (sprint-8.4 G3 HOTFIX)

---

## Metodologia

Review strutturata su 5 assi:

1. **Violazioni di normativa** — il codice fa diversamente da `NORMATIVA-PDC.md`
2. **Debito tecnico** — TODO/half-job dichiarati e non, scope-cutting silente
3. **Correttezza architetturale** — separazione dominio/API/persistenza
4. **Buchi di test** — logica critica non coperta
5. **Qualità del codice** — naming, dead code, anti-pattern

Ogni finding cita `file:riga`, propone un fix concreto, e indica il costo
stimato in ore per chiuderlo.

---

## CRITICI

### CR-1 — §4.4 Violazione normativa: PK inferiore a 20' prodotto e persistito

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:258-269`

**Normativa**: §4.4 — "PK in arrivo: 20 minuti minimo. PK in partenza: 20
minuti minimo."

**Il codice**: nel loop `_build_giornata_pdc`, qualsiasi gap > 0 fra due
blocchi consecutivi genera un blocco `tipo_evento="PK"`:

```python
# riga 258-269
if gap > 0:
    drafts.append(
        _BloccoPdcDraft(
            seq=seq,
            tipo_evento="PK",
            ...
            durata_min=gap,   # gap può essere 1, 3, 7 minuti — nessun check
        )
    )
```

Non esiste la costante `PK_MIN_MIN` né un check sul valore. Un gap di 5
minuti produce un PK 5' che è operativamente invalido ma non genera violazione.
La normativa prevede che gap < 20' debbano essere trattati come tempo tecnico
(non PK), e che il builder scelga tra CV (se gap < 65') o ACC (se gap ≥ 65').

**Fix concreto** (costo: 2-3h):

```python
# In builder.py dopo ACCESSORI_MIN_STANDARD
PK_MIN_MIN = 20  # §4.4: soglia minima PK operativo

# Nel loop blocchi:
if gap > 0:
    if gap < PK_MIN_MIN:
        # gap troppo corto per PK: segnala come violazione tecnica,
        # non creare blocco PK
        violazioni_draft.append(f"pk_sotto_minimo:{gap}min<{PK_MIN_MIN}min")
    else:
        drafts.append(_BloccoPdcDraft(tipo_evento="PK", durata_min=gap, ...))
```

La stessa costante va aggiunta a `giornata_base.py` per l'esportazione pubblica.

---

### CR-2 — §6 Violazione normativa: split CV prodotto senza verifica gap < 65'

**File**: `backend/src/colazione/domain/builder_pdc/split_cv.py:27-28,
164-205`

**Normativa**: §6 — "Gap < 65': modalità ammesse = CV o PK. Gap 65-300':
modalità ammesse = ACC o PK. Gap > 300': ACC (default), PK opt-in."

**Il codice**: `split_cv.py` dichiara esplicitamente a riga 27-28:

```
Limitazione MVP: non viene applicato il pattern CV no-overhead
(gap < 65' → CVa/CVp che sostituiscono ACCa/ACCp risparmiando 80').
```

Questo viene letto come se l'unica mancanza fosse "non ottimizziamo i
tempi ACCa/CVp". Ma il problema è più grave: **il builder usa split_cv
per dividere qualsiasi giornata che sfora i cap, senza verificare che il
gap al punto di split sia < 65'**. Se una giornata sfora a LECCO con un
gap di 90' prima del treno successivo, `_trova_punto_split` inserisce
un CV a LECCO con gap 90' — violazione §6 (con 90' si fa ACC, non CV).

`_trova_punto_split` (riga 164-205) filtra solo per stazione CV ammessa,
non per dimensione del gap.

**Fix concreto** (costo: 3-4h):

```python
# In _trova_punto_split, dopo aver identificato stazione_a come candidato CV:
gap_al_punto = _diff(blocchi_giro[i].ora_fine, blocchi_giro[i+1].ora_inizio)
if gap_al_punto >= 65:
    # Gap troppo lungo per CV: salta questo punto, usa ACC invece
    continue
# ... resto della logica
```

Nota: questa fix cambierà il comportamento del builder su giri esistenti.
Valutare impatto prima di deployare.

---

### CR-3 — §3.2 Violazione normativa: vettura rientro non aggiunge i 15' post-arrivo

**File**: `backend/src/colazione/domain/builder_pdc/multi_turno.py:923-955`,
`backend/src/colazione/domain/builder_pdc/vettura_resolver.py:62-63`

**Normativa**: §3.2 — "Se l'ULTIMO segmento del turno è una vettura → la fine
servizio è 15 minuti dopo l'arrivo vettura."

**Il codice**: `vettura_resolver.py:62-63` definisce correttamente:

```python
FINE_SERVIZIO_POST_VETTURA_MIN: int = 15
```

Ma `_aggiungi_vettura_rientro` (`multi_turno.py:923-955`) aggiorna
`fine_prestazione = treno.arrivo_min` **senza** aggiungere i 15':

```python
nuova_fine_min = treno.arrivo_min   # ← manca + FINE_SERVIZIO_POST_VETTURA_MIN
nuova_prest = nuova_fine_min - inizio_prest_min
```

La costante `FINE_SERVIZIO_POST_VETTURA_MIN` è importata in
`vettura_resolver.py` ma **non viene usata nel path di aggiornamento
prestazione del draft**.

Effetto: i turni con vettura rientro hanno `prestazione_min` sotto-stimata
di 15', e la timeline nel Gantt non mostra i 15' di "fine servizio" che il
PdC deve ancora completare dopo l'arrivo del treno.

**Fix concreto** (costo: 1-2h):

```python
# multi_turno.py - _aggiungi_vettura_rientro
from colazione.domain.builder_pdc.vettura_resolver import FINE_SERVIZIO_POST_VETTURA_MIN

nuova_fine_min = treno.arrivo_min + FINE_SERVIZIO_POST_VETTURA_MIN
# (gestire wrap mezzanotte come già fatto per inizio_prest_min)
```

Aggiungere anche un blocco `tipo_evento="FINE"` di 15' dopo il blocco VETTURA
in `nuovi_blocchi` (simmetrico a come `_build_giornata_pdc` aggiunge FINE
dopo ACCa).

---

### CR-4 — §3.2 Violazione normativa: vettura partenza mantiene ACCp e non sposta PRESA

**File**: `backend/src/colazione/domain/builder_pdc/multi_turno.py:788-822`

**Normativa**: §3.2 — "Se il PRIMO segmento del turno è una vettura → la
presa servizio è 15 minuti prima della partenza vettura. Niente ACCp."

**Il codice**: `_aggiungi_vettura_partenza` prepende il blocco VETTURA
prima dei blocchi esistenti ma **lascia invariati** `inizio_prestazione`
e `prestazione_min`:

```python
# riga 799-816
# `inizio_prestazione` rimane invariato (la vettura è prima della presa,
# quindi è prestazione "extra" notional).
return GiornataPdcDraft(
    ...
    inizio_prestazione=draft.inizio_prestazione,  # invariato = pre-ACCp
    prestazione_min=draft.prestazione_min,         # invariato
)
```

Il risultato è un turno dove la VETTURA appare prima della PRESA, cosa
geometricamente impossibile: il PdC sale sul treno prima ancora di "prendere
servizio". La normativa §3.2 richiede che la PRESA sia 15' prima della
partenza vettura, e che NON ci sia ACCp per il treno successivo.

Il builder invece mantiene la struttura:
`PRESA → ACCp → [primo treno] → ... → VETTURA`
quando dovrebbe essere:
`PRESA (15' pre-vettura) → VETTURA → ACCp → [primo treno] → ...`

**Fix concreto** (costo: 4-6h): ristruttare `_aggiungi_vettura_partenza`
per rimuovere i blocchi PRESA e ACCp originali dal draft e ricalcolare
`inizio_prestazione = vettura.partenza_min - PRESA_SERVIZIO_MIN`.

---

### CR-5 — `assert` in codice di produzione: silent failure con python -O

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:210,253,256`,
`backend/src/colazione/domain/builder_pdc/multi_turno.py:421,477,1140`

**Problema**: `assert` viene eliminato da CPython con `-O` (ottimizzazione).
Se Railway, Docker o qualunque futuro runner usa `python -O` (o
`PYTHONOPTIMIZE=1`), tutti questi assert diventano no-op. I crash che
dovrebbero essere chiari (`AssertionError`) diventano `AttributeError: 'NoneType'
has no attribute ...` decine di righe dopo.

Esempi:

```python
# builder.py:210
assert primo.ora_inizio is not None and ultimo.ora_fine is not None

# multi_turno.py:421
assert stazione_apertura is not None

# multi_turno.py:1140
assert depot is not None and depot.id == depot_key
```

In `multi_turno.py:1140` l'assert è dentro un loop async che persiste turni
nel DB — un fallimento silenzioso lì corrompe lo stato.

**Fix concreto** (costo: 1h): sostituire ogni `assert` in codice runtime
con `if ... is None: raise ValueError(...)` o `if ...: raise RuntimeError(...)`.
Lasciare `assert` solo nei test.

---

### CR-6 — `giornata_base.py`: facade di re-export è un anti-pattern strutturale

**File**: `backend/src/colazione/domain/builder_pdc/giornata_base.py:31-71`

**Problema**: il modulo importa simboli privati (`_xxx`) da `builder.py`
e li ri-esporta con nomi pubblici:

```python
from colazione.domain.builder_pdc.builder import (
    _BloccoPdcDraft,
    _GiornataPdcDraft,
    _aggiungi_dormite_fr,
    ...
)
BloccoPdcDraft = _BloccoPdcDraft  # alias pubblico
```

Il commento nel file lo definisce "refactor" ma in realtà è un livello di
indirezione che mantiene intatta la dipendenza su `builder.py` come source
of truth. Se qualcuno aggiunge `__all__` a `builder.py` escludendo i simboli
`_`, o li rinomina, la catena rompe silenziosamente (import funziona ma
l'alias punti a `None` o a un tipo sbagliato).

Il refactor corretto (finding S2 SEVERO Sprint 8.2 era sulla direzione
giusta ma si è fermato a metà):
- Spostare le definizioni di `_BloccoPdcDraft`, `_GiornataPdcDraft`, tutte
  le costanti normative e le funzioni helper IN `giornata_base.py`.
- Fare in modo che `builder.py` le importi da `giornata_base`.
- Eliminare il pattern re-export.

**Fix concreto** (costo: 4-6h): inversione della dipendenza. Alto impatto
su tutti i moduli che importano da `giornata_base`.

---

## IMPORTANTI

### IM-1 — §15 debito: wild card `data_operativa=None` produce falsi positivi cross-PdC

**File**: `backend/src/colazione/domain/builder_pdc/registro_vetture.py:157,240`

**Problema**: il registro vetture usa `data_operativa=None` come wild card per
i turni storici caricati da DB (funzione `from_db`):

```python
# riga 240
data_operativa=None,  # wild card S4 TODO
```

Con `None`, il metodo `is_assegnata` collide con **qualsiasi data futura**:

```python
def is_assegnata(self, *, numero_treno, operatore, data_operativa):
    chiave = (numero_treno, operatore)
    if chiave not in self._vetture:
        return False
    date_assegnate = self._vetture[chiave]
    if None in date_assegnate:
        return True   # ← wild card: blocca anche date non coincidenti
```

Effetto operativo: un turno storico che usa il treno 12345 blocca quel treno
per qualsiasi data futura, anche se la data non si sovrappone. Genera falsi
"§15 violato" e impedisce l'assegnazione di vetture valide.

Il S4 TODO è documentato ma non ha un MR assegnato né una data target.

**Fix concreto** (costo: 6-8h): implementare `enumera_date_giornata` (già
presente in `giornate_concrete.py` come stub) per calcolare le date concrete
di ogni giornata del turno e usarle nel registro. Rimuovere il wild card
`None` come valore valido nel `from_db`.

---

### IM-2 — `split_cv.py:61`: deroghe CV hardcoded in sistema multi-tenant

**File**: `backend/src/colazione/domain/builder_pdc/split_cv.py:61`

**Problema**:

```python
STAZIONI_CV_DEROGA: frozenset[str] = frozenset({"MORTARA", "TIRANO"})
```

Hardcoded a livello di modulo, non configurabile per azienda. In un sistema
multi-tenant (SAD, TILO, Trenitalia hanno normative diverse), queste deroghe
non sono universali. TIRANO è un capolinea specifico della rete Trenord
Valtellina — non ha senso per TILO.

Il commento dice "refactor a regola configurabile per programma in iterazioni
successive" senza MR assegnato. È debito tecnico architetturale silente.

**Fix concreto** (costo: 4-6h): passare `stazioni_cv_deroga: frozenset[str]`
come parametro esplicito di `lista_stazioni_cv_ammesse`, caricato da una
tabella `stazione_cv_deroga` con FK su `azienda_id`. Default vuoto per
aziende non-Trenord.

---

### IM-3 — Suite test con 50 fallimenti pre-esistenti dichiarati

**File**: TN-UPDATE.md entry 301

**Problema**: la entry 301 dichiara esplicitamente:

```
⚠️ pytest full backend: 50 fallimenti pre-esistenti su `master`
(verificato via `git stash` → stessi fail). Non sono regressioni di
questo fix. Backlog.
```

Una suite con 50 test rossi è una suite inutilizzabile come guardrail. Non
è possibile distinguere una nuova regressione dal rumore esistente. Il CI
(`backend-ci.yml`) diventa teatro: il developer guarda il rosso, assume
sia pre-esistente, e committa.

**Fix concreto** (costo: variabile — diagnosi 2h, fix dipende dal tipo di
fallimento): eseguire `pytest --tb=no -q` su master e categorizzare i 50
fallimenti per tipo. Probabili cause: test che richiedono DB running (da
skippare con marker `@pytest.mark.requires_db` in CI), fixture obsolete,
o regressioni vere. Chiudere entro lo Sprint corrente.

---

### IM-4 — Assenza di test per §6: regola gap CV/ACC/PK

**File**: nessun file di test

**Problema**: la regola §6 (la più complessa della normativa, governa 3 range
di gap con modalità diverse) non ha un singolo test unitario che verifichi:
- gap < 65': CV ammesso
- gap 65-300': ACC ammesso, CV non ammesso
- gap > 300': ACC default, PK opt-in

`test_split_cv.py` testa solo che il split avvenga quando la prestazione
sfora i cap, non che il tipo di transizione (CV vs ACC) sia corretto in
funzione del gap.

**Fix concreto** (costo: 3-4h): aggiungere `test_gap_regola_scelta_cv_acc_pk.py`
con parametric test per i 3 range. Coprire anche il caso misto (turno con
gap 30' poi gap 90' → CV al primo, ACC al secondo).

---

### IM-5 — `api/giri.py`: God object da 4422 righe con 20+ endpoint

**File**: `backend/src/colazione/api/giri.py`

**Problema**: 4422 righe, 20+ endpoint (`genera_giri`, `list_giri_programma`,
`riempi_gap`, `aggrega_modifica`, `wizard_da_linee`, `inserisci_corsa_manuale`,
`elimina_blocco`, `duplica_giro`, ecc.), più helper e logica di dominio inline
(`_check_fattibilita_variante`, `_blocchi_variante`, `_minuti`).

Conseguenze:
- Ogni PR tocca questo file → conflitti git frequenti
- Impossibile testare un endpoint in isolamento
- `_check_fattibilita_variante` (riga 2711) è logica di dominio dentro un
  modulo API — viola la separazione domain/api

**Fix concreto** (costo: 8-12h, ma ben decomponibile):
- `api/giri_read.py`: GET endpoints + helper lettura
- `api/giri_write.py`: POST/PATCH endpoints di modifica giro
- `api/giri_builder.py`: endpoint `genera-giri`, `riempi-gap`, `genera-da-residue`
- `api/giri_gantt.py`: `gantt-unificato`, `inserisci-corsa-manuale`
- Spostare `_check_fattibilita_variante` in `domain/builder_giro/validator.py`

---

### IM-6 — `multi_turno.py:788-822`: prestazione non aggiornata con vettura partenza

**File**: `backend/src/colazione/domain/builder_pdc/multi_turno.py:799-816`

**Problema** (distinto da CR-4 che riguarda la struttura normativa dei blocchi):
indipendentemente da come si risolve CR-4, il campo `prestazione_min` e
`inizio_prestazione` rimangono invariati dopo l'aggiunta della vettura
partenza. Il commento a riga 799 dice:

```
# `inizio_prestazione` rimane invariato (la vettura è prima della presa,
# quindi è prestazione "extra" notional). Per ora teniamo invariato...
```

Questo significa che la dashboard mostra una prestazione sotto-stimata. Se
la vettura dura 45', il turno che appare come 7h30 dura effettivamente 8h15
per il PdC (inclusa la vettura di posizionamento). Il check cap prestazione
non include questo tempo.

**Fix concreto** (costo: dipende da CR-4, se si risolve insieme 0h extra):
aggiornare `inizio_prestazione = vettura.partenza_min - PRESA_SERVIZIO_MIN`
e ricalcolare `prestazione_min`.

---

### IM-7 — Auth: nessuna token revocation (rischio sicurezza)

**File**: `backend/src/colazione/auth/tokens.py`,
`backend/src/colazione/auth/dependencies.py`

**Problema**: i JWT access token non sono revocabili. Se un token viene
compromesso (leak log, XSS frontend, man-in-the-middle), è valido fino alla
scadenza (`JWT_ACCESS_TOKEN_EXPIRE_MIN`). Non esiste endpoint per invalidare
un token, né lista nera lato server.

In produzione su Railway, l'unica soluzione è cambiare `JWT_SECRET` (invalida
**tutti** i token di tutti gli utenti — downtime operativo).

**Fix concreto** (costo: 8-12h): aggiungere tabella `refresh_token_blacklist`
(uuid + scadenza) e controllare l'UUID del refresh token al login/refresh.
Per i token access, ridurre `JWT_ACCESS_TOKEN_EXPIRE_MIN` a 15 minuti (già
configurabile, verificare il default attuale) e affidare la continuità al
refresh. Non implementare una blacklist per i token access (overhead alto,
beneficio limitato se la scadenza è breve).

---

### IM-8 — `giornate_concrete.py:12`: S4 TODO senza backlog attivo

**File**: `backend/src/colazione/domain/giornate_concrete.py:12`

**Problema**: il commento dichiara "S4 TODO, attualmente wild card MVP". Questo
TODO impatta direttamente:
- `registro_vetture.py:240` (IM-1): data_operativa wild card
- `deposito_first.py:542`: varianti calendariali non gestite per date
- `riposo_settimanale.py:267-285`: fallback proxy invece di date concrete

Tre moduli critici di dominio si appoggiano su un'implementazione placeholder.
Non risulta un MR numerato assegnato a questo issue.

**Fix concreto** (costo: 6-10h): implementare `enumera_date_giornata` completo
con supporto varianti calendariali reali. Creare test che verifichino i 4
tipi di variante (feriale, sabato, domenica, festivo) su un programma con
periodo noto.

---

## MINORI

### MI-1 — `calendario.py:20`: riferimento a file inesistente nel repo

**File**: `backend/src/colazione/domain/calendario.py:20`

```python
# Decisione utente 2026-05-02 (memoria
# `project_refactor_varianti_giri_separati_TODO.md`): ...
```

Il file `project_refactor_varianti_giri_separati_TODO.md` non esiste nel
repo. Il commento punta a una risorsa irrintracciabile che rende la
motivazione della decisione opaca per un lettore futuro.

**Fix**: sostituire la citazione con il riferimento all'entry TN-UPDATE
corrispondente (es. "entry 2026-05-02, vedi TN-UPDATE §X").

---

### MI-2 — `varianti_calendariali.py:293`: dead import mascherato da noqa

**File**: `backend/src/colazione/domain/builder_giro/varianti_calendariali.py:293`

```python
_ = Counter  # noqa: F841 — riservato per estensioni
```

Un'importazione inutilizzata marcata "riservato" non è una giustificazione
tecnica. O si usa nel ciclo corrente o si rimuove. "Riservato per estensioni"
appartiene a un PR futuro, non al codice corrente.

**Fix**: rimuovere l'import e la riga. Riaggiungerlo quando serve.

---

### MI-3 — `builder.py:2757-2758`: due variabili `_` inutili con noqa

**File**: `backend/src/colazione/domain/builder_giro/builder.py:2757-2758`

```python
_ = festivita  # noqa: F841 (reservato per uso futuro)
_ = calcola_etichetta_giro  # noqa: F841 (export pubblico mantenuto)
```

Il secondo spiega "export pubblico mantenuto" ma l'assegnazione a `_` non
mantiene nessun export — se `calcola_etichetta_giro` è importato e non usato
in questo contesto, è dead code. Se deve essere re-esportato, va in `__all__`.

**Fix**: rimuovere entrambe le righe, aggiungere a `__all__` se necessario.

---

### MI-4 — `riposo_settimanale.py:268`: proxy giorni solari può sovra-stimare

**File**: `backend/src/colazione/domain/builder_pdc/riposo_settimanale.py:268`

```python
return gap_min // (24 * 60)
```

Con `gap_min = 62 * 60 = 3720`, restituisce 2 — corretto nel caso standard.
Ma se il riposo inizia sabato alle 22:00 e dura 62h esatte (fino a martedì
00:00), i giorni interi reali sono solo domenica e lunedì (2 — OK). Se però
inizia sabato alle 23:30 e dura 62h (fino a martedì 01:30), il proxy dà
ancora `3720//1440 = 2` ma i giorni interi sono effettivamente domenica e
lunedì (2 — OK per caso). Il proxy non è sbagliato nel caso normale ma non
rileva la violazione quando il riposo inizia e finisce a ridosso di
mezzanotte. Questo bug è secondario rispetto all'IM-8 (implementare date
concrete risolve questo e IM-1 insieme).

**Fix**: parte del fix IM-8 (`enumera_date_giornata` completo).

---

### MI-5 — `GanttUnificatoRoute.tsx`: variante dropdown hardcoded a 4 valori

**File**: `frontend/src/routes/pianificatore-giro/GanttUnificatoRoute.tsx`

TN-UPDATE entry 300 dichiara: "il dialog inserimento corsa offre solo i
primi 4 indici di variante (0=canonica + 3 successive). Per giri con
varianti calendariali multiple, l'utente potrebbe doverne selezionare una
specifica → scope iterazione."

Un giro Trenord con 4+ varianti calendariali (es. F/S/D/F+spec) ha indici
oltre il 3. Il dropdown mostra 0-3 sempre, anche se il giro ne ha 6.
L'utente inserisce la corsa sulla variante sbagliata senza saperlo.

**Fix** (costo: 2-3h): fetch `GiroGiornata` per recuperare le varianti
reali e popolare dinamicamente il dropdown.

---

### MI-6 — `vettura_resolver.py:281`: bare exception catch

**File**: `backend/src/colazione/domain/builder_pdc/vettura_resolver.py:281`

```python
except Exception as e:  # noqa: BLE001
```

Catch-all che ingoia qualsiasi eccezione (incluse `KeyboardInterrupt`,
`SystemExit` su Python < 3.8 non inclusi in `Exception` ma potenzialmente
`asyncio.CancelledError` su Python 3.7). In un handler async, inghiottire
`CancelledError` rompe la cancellazione dei task.

**Fix**: restringere a `except (httpx.HTTPError, TimeoutError) as e:`.

---

### MI-7 — `insert_corsa_manuale`: nessuna validazione su `variante_index` out-of-range

**File**: `backend/src/colazione/api/giri.py:3908-3920`

**Problema**: l'endpoint cerca `GiroVariante` con `variant_index == payload.variante_index`
e restituisce 404 se non trovato. Ma se il payload dice `variante_index=5` e
il giro ne ha 3, il messaggio di errore è "Variante index=5 non trovata per
giornata X" — poco chiaro per il frontend. Un input validation con range check
esplicito darebbe un 422 più descrittivo.

**Fix**: aggiungere `Field(ge=0, le=20)` allo schema `variante_index` in
`InserisciCorsaManualePayload`.

---

## Riepilogo per priorità

| ID | Gravità | File principale | Fix stimato | Impatto |
|----|---------|-----------------|-------------|---------|
| CR-1 | **CRITICO** | `builder.py:258-269` | 2-3h | Turni con PK sotto i 20' invalidi silenziosamente |
| CR-2 | **CRITICO** | `split_cv.py:164-205` | 3-4h | CV con gap > 65' — violazione §6 |
| CR-3 | **CRITICO** | `multi_turno.py:923-955` | 1-2h | Prestazione sotto-stimata di 15' per vettura rientro |
| CR-4 | **CRITICO** | `multi_turno.py:788-822` | 4-6h | Struttura turno con vettura partenza viola §3.2 |
| CR-5 | **CRITICO** | `builder.py:210,253,256` | 1h | assert silenti con python -O |
| CR-6 | **CRITICO** | `giornata_base.py` | 4-6h | Anti-pattern re-export simboli privati |
| IM-1 | **IMPORTANTE** | `registro_vetture.py:240` | 6-8h | Falsi positivi §15 wild card data |
| IM-2 | **IMPORTANTE** | `split_cv.py:61` | 4-6h | Deroghe CV hardcoded, non multi-tenant |
| IM-3 | **IMPORTANTE** | TN-UPDATE entry 301 | variabile | 50 test falliti = CI inutilizzabile |
| IM-4 | **IMPORTANTE** | test mancante | 3-4h | §6 gap/modalità non testato |
| IM-5 | **IMPORTANTE** | `giri.py` 4422 righe | 8-12h | God object, accoppiamento massimo |
| IM-6 | **IMPORTANTE** | `multi_turno.py:799` | part. di CR-4 | Prestazione sotto-stimata vettura partenza |
| IM-7 | **IMPORTANTE** | `tokens.py` | 8-12h | Nessuna revoca token in produzione |
| IM-8 | **IMPORTANTE** | `giornate_concrete.py:12` | 6-10h | S4 TODO blocca IM-1, riposo settimanale reale |
| MI-1 | minore | `calendario.py:20` | 10min | Commento punta a file inesistente |
| MI-2 | minore | `varianti_calendariali.py:293` | 5min | Dead import mascherato |
| MI-3 | minore | `builder_giro/builder.py:2757` | 5min | Variabili `_` inutili |
| MI-4 | minore | `riposo_settimanale.py:268` | coperto da IM-8 | Proxy giorni solari impreciso |
| MI-5 | minore | `GanttUnificatoRoute.tsx` | 2-3h | Dropdown varianti hardcoded a 4 |
| MI-6 | minore | `vettura_resolver.py:281` | 30min | Bare exception catch |
| MI-7 | minore | `giri.py:3908` | 30min | Nessun range check su variante_index |

---

## Ordine di risoluzione consigliato

**Sprint immediato (critici bloccanti)**:
1. CR-5 (assert → eccezioni): 1h, zero rischio regressioni
2. CR-3 (15' post-vettura rientro): 1-2h, fix puntuale senza side effects
3. CR-1 (PK minimo 20'): 2-3h, aggiunge validazione senza rompere il builder

**Sprint successivo**:
4. CR-2 (CV gap ≥ 65' non ammesso): impatta output builder — pianificare
   con l'utente perché cambierà turni già generati
5. CR-4 (vettura partenza §3.2): architetturale, richiede discussione
6. IM-3 (50 test rossi): diagnosi urgente prima di procedere con altri fix

**Backlog strutturale**:
7. CR-6 (refactor giornata_base) + IM-8 (enumera_date_giornata) + IM-1
   (wild card registro): da fare come tripletta coerente
8. IM-5 (split giri.py): bassa urgenza ma alta manutenibilità
9. IM-7 (token revocation): security, non urgente in MVP ma da pianificare

---

*Review eseguita su HEAD commit `6571374`. I finding non implicano fix
automatici — da discutere con l'utente prima di procedere.*
