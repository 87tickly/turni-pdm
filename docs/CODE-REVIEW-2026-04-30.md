# Code Review — COLAZIONE Sprint 8.2 (2026-05-10)

> **Scope**: codebase al commit `adbfd26` (entry 285 TN-UPDATE).
> Sprint 8.2 completato: Plan-D pipeline materiali misti + Piano α
> turni PdC + riposo intraturno §11.5 + riposo settimanale §11.4.
>
> **Metodologia**: lettura diretta dei sorgenti, confronto con
> `docs/NORMATIVA-PDC.md` come fonte di verità. Ogni finding ha
> `file:riga`, impatto, fix concreto e costo stimato.
>
> **Precedente review**: `docs/CODE-REVIEW-2026-05-01.md` (Sprint 7.4).
> Questa review NON ri-segnala finding già chiusi in quella review.
>
> **Nota su SEVERO S1–S10**: i finding SEVERO dell'entry 285 sono inclusi
> quando confermati dalla lettura del codice. Finding già chiusi in
> entry 284 (MR-D5h-bis + MR-D6) sono esclusi.

---

## Indice finding

| ID | Gravità | Area | Titolo breve |
|----|---------|------|--------------|
| C1 | CRITICO | builder_pdc | Facade strangler bucato: `_GiornataPdcDraft` importata da `builder.py` invece che da `giornata_base.py` |
| C2 | CRITICO | builder_pdc | §3.3 Preriscaldo ACCp 80' dic-feb non implementato |
| C3 | CRITICO | builder_pdc | §4.4 PK gap minimo 40' (20'+20') non validato |
| I1 | IMPORTANTE | builder_pdc | `RIPOSO_INTRATURNO_FINE_TARDA_MIN` esportata in `__all__` ma mai usata — 14h letterale §11.5 ignorato |
| I2 | IMPORTANTE | builder_pdc | `RegistroVettureAssegnate.from_db()` ignora `programma_id` → wild-card cross-programma |
| I3 | IMPORTANTE | builder_pdc | 4 import locali dentro funzione in `deposito_first.py` |
| I4 | IMPORTANTE | builder_pdc | Reset contatore `riposo_settimanale.py` post-violazione maschera cicli multipli |
| I5 | IMPORTANTE | modelli | `TurnoPdcGiornata` mancante campo `data: date` — root cause di I2 |
| I6 | IMPORTANTE | builder_pdc | `giornata_base.py` facade nella direzione sbagliata |
| I7 | IMPORTANTE | builder_pdc | `assert` per invarianti runtime — rimossi da Python -O |
| I8 | IMPORTANTE | domain | `enumera_date_giornata` fallback sovra-include su varianti parlanti Trenord |
| M1 | MINORE | vari | Anti-pattern `_ = SYMBOL` × 3 per silenziare ruff |
| M2 | MINORE | builder_giro | Dualità `multi_giornata.py` vs `multi_giornata_v2.py` non documentata |
| M3 | MINORE | test | Zero test e2e del piano α |
| M4 | MINORE | scripts | Accumulo script diagnostici non rimossi |
| M5 | MINORE | frontend | Zero test sui route critici (DashboardRoute, GiriRoute, TurniPdc) |

---

## CRITICI

### C1 — Facade strangler bucato: `_GiornataPdcDraft` importata direttamente da `builder.py`

**File**: `backend/src/colazione/domain/builder_pdc/riposo_intraturno.py:30`,
`backend/src/colazione/domain/builder_pdc/riposo_settimanale.py:42`

**Codice attuale**:
```python
# riposo_intraturno.py:30
from colazione.domain.builder_pdc.builder import _GiornataPdcDraft

# riposo_settimanale.py:42
from colazione.domain.builder_pdc.builder import _GiornataPdcDraft
```

**Problema**: `giornata_base.py` è stato creato in entry 273 (MR-PD-FIX-SEVERO 2, S2 HIGH)
esattamente per evitare che i moduli consumatori importassero `_GiornataPdcDraft`
direttamente da `builder.py`. I due nuovi moduli `riposo_intraturno.py` e
`riposo_settimanale.py`, creati il giorno successivo (entry 281–282), bypassano
la facade appena costruita. Strangler pattern bucato dopo 24 ore dalla sua creazione.

**Impatto**: se `_GiornataPdcDraft` viene spostata, rinominata o resa davvero
privata in `builder.py`, i due moduli si rompono senza warning di mypy (il campo
è già privato per convenzione). `giornata_base.py` re-esporta `GiornataPdcDraft`
con nome pubblico — è quel simbolo che i consumatori devono usare.

**Fix** (< 15 min, 2 righe per file):
```python
# riposo_intraturno.py:30
from colazione.domain.builder_pdc.giornata_base import GiornataPdcDraft

# riposo_settimanale.py:42
from colazione.domain.builder_pdc.giornata_base import GiornataPdcDraft
```
Poi sostituire tutte le occorrenze di `_GiornataPdcDraft` con `GiornataPdcDraft`
all'interno dei due file (5-6 occorrenze totali, tipo annotations only).

**Costo**: < 30 min. BLOCCANTE per la chiusura ufficiale Sprint 8.2 (regola §9 CLAUDE.md).

---

### C2 — §3.3 Preriscaldo ACCp 80' dic-feb non implementato

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:57,215-218`

**Codice attuale**:
```python
ACCESSORI_MIN_STANDARD = 40  # fisso, nessun branch per periodo

# _build_giornata_pdc
ora_inizio_accp = (primo_inizio - ACCESSORI_MIN_STANDARD) % (24 * 60)
ora_presa       = (primo_inizio - ACCESSORI_MIN_STANDARD - PRESA_SERVIZIO_MIN) % (24 * 60)
```

**Normativa** (`docs/NORMATIVA-PDC.md` §3.3):
```
| Caso                        | ACCp | ACCa |
|-----------------------------|------|------|
| Condotta standard           | 40'  | 40'  |
| Condotta con preriscaldo ● (dic-feb) | 80' | 40' |
```

**Problema**: il builder usa sempre ACCp = 40' indipendentemente dal mese. In
dicembre, gennaio, febbraio il preriscaldo (simbolo `●`) richiede ACCp = 80'.
Il PdC ha 40 minuti in meno per preparare il treno: i turni invernali prodotti
dal builder sono NON CONFORMI alla normativa. Non viene generata nessuna
violazione, nessun warning: il turno sembra valido ma è sbagliato.

**Impatto operativo**: turni invernali con presa servizio sbagliata di 40 minuti.
In un programma che va da dicembre a dicembre (12 mesi), tutti i turni
dic-gen-feb (≈ 25% del totale) hanno ACCp errato.

**Fix** (costo ~2h):
1. Aggiungere costante `ACCESSORI_MIN_PRERISCALDO = 80` in `builder.py`.
2. Aggiungere parametro `data_operativa: date | None = None` a
   `_build_giornata_pdc` (oppure derivarlo da `numero_giornata` + calendario
   programma, secondo la strategia scelta).
3. Calcolare `accp_min = ACCESSORI_MIN_PRERISCALDO if data_operativa is not None and data_operativa.month in (12, 1, 2) else ACCESSORI_MIN_STANDARD`.
4. Propagare `accp_min` al calcolo `ora_inizio_accp` e `ora_presa`.
5. Propagare la stessa logica a `deposito_first.py` via
   `costruisci_giornata_deposito_first`.

**Nota**: `is_accessori_maggiorati: Mapped[bool]` esiste già in
`TurnoPdcBlocco` (`turni_pdc.py:114`) ma non viene popolato. Questo campo
va aggiornato dal builder quando ACCp = 80'.

---

### C3 — §4.4 PK gap minimo 40' (20'+20') non validato

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:259-270`

**Codice attuale**:
```python
if gap > 0:
    drafts.append(_BloccoPdcDraft(
        tipo_evento="PK",
        durata_min=gap,   # qualsiasi valore > 0, anche 5'
        ...
    ))
```

**Normativa** (`docs/NORMATIVA-PDC.md` §4.4):
```
| Voce          | Minuti                                  |
|---------------|-----------------------------------------|
| PK in arrivo  | 20' minimo                              |
| PK in partenza| 20' minimo                              |
```

**Problema**: il builder inserisce blocchi PK per qualsiasi gap > 0 minuti tra
due condotte consecutive. Un gap di 5', 10', 15' genera un PK di 5', 10', 15'.
La normativa stabilisce che un PK richiede MINIMO 20' in arrivo + 20' in
partenza (= 40' totali). Un PK sotto i 40' non è operativamente realizzabile:
il PdC non ha tempo di mettere in sicurezza il mezzo e rimetterlo in moto.

**Impatto**: turni con PK impossibili vengono prodotti senza violazione. Il
validatore non segnala questi casi. In produzione, il pianificatore riceve un
turno che sembra valido ma non lo è.

**Fix** (costo ~1h):
Nel blocco `if gap > 0`, aggiungere validazione:
```python
PK_MIN_DURATA_TOTALE = 40  # 20' arrivo + 20' partenza (§4.4)

if gap > 0:
    if gap < PK_MIN_DURATA_TOTALE:
        # Gap insufficiente per PK: non è CV (nessun secondo turno),
        # non è PK (sotto il minimo). Documenta come violazione.
        violazioni.append(
            f"pk_gap_insufficiente:G{numero_giornata}:"
            f"gap_{gap}min<{PK_MIN_DURATA_TOTALE}min_minimo"
        )
    drafts.append(_BloccoPdcDraft(tipo_evento="PK", durata_min=gap, ...))
```

**Alternativa più conservativa**: non generare il blocco PK per gap < 40'
ma emetterlo come "buco tecnico" (assenza di blocco), lasciando il gap
non classificato per il pianificatore. Questa scelta dipende dalla volontà
dell'utente; il punto C3 chiede di segnalare la violazione.

---

## IMPORTANTI

### I1 — `RIPOSO_INTRATURNO_FINE_TARDA_MIN` zombie + 14h letterale §11.5 ignorato

**File**: `backend/src/colazione/domain/builder_pdc/riposo_intraturno.py:43,54-92`

**Codice attuale**:
```python
# Costante definita e in __all__, ma mai usata nella logica:
RIPOSO_INTRATURNO_FINE_TARDA_MIN: int = 14 * 60  # 14h

def riposo_richiesto_min(fine_prestazione: time) -> int:
    minuto_assoluto = h * 60 + m
    if 1 <= minuto_assoluto < 300:   # [00:01-05:00] → 16h SEMPRE
        return RIPOSO_INTRATURNO_NOTTURNO_MIN  # 16h
    return RIPOSO_INTRATURNO_STD_MIN  # 11h
    # RIPOSO_INTRATURNO_FINE_TARDA_MIN (14h) non appare MAI
```

**Normativa** (`docs/NORMATIVA-PDC.md` §11.5):
```
- 11 ore standard fra giornate consecutive
- 14 ore dopo una giornata che finisce tra 00:01 e 01:00
- 16 ore dopo una giornata notturna (tra 00:01 e 05:00)
```

**Problema**: la fascia [00:01-01:00] letterale richiede 14h. Il codice
la tratta come 16h (notturno). La costante `RIPOSO_INTRATURNO_FINE_TARDA_MIN`
segnala l'intenzione di gestire i 14h, ma non viene mai invocata. Il
docstring chiama questa scelta "decisione interpretativa NINO — adottiamo
la più cautelativa = 16h". Decisione unilaterale NINO, non validata
dall'utente. Produce riposi richiesti SOVRA-STRICT per la fascia 00:01-01:00:
il builder scarterà giornate che la normativa letterale ammetterebbe.

**Due opzioni** (richiede decisione utente):

**(a) Letterale normativa**:
```python
if 1 <= minuto_assoluto <= 60:    # [00:01-01:00] → 14h letterale
    return RIPOSO_INTRATURNO_FINE_TARDA_MIN
if 61 <= minuto_assoluto < 300:   # (01:00-05:00] → 16h notturno
    return RIPOSO_INTRATURNO_NOTTURNO_MIN
return RIPOSO_INTRATURNO_STD_MIN
```

**(b) Conservativo confermato dall'utente**: mantenere 16h per tutta la
fascia [00:01-05:00], ma rimuovere `RIPOSO_INTRATURNO_FINE_TARDA_MIN`
da `__all__` (o deprecarla esplicitamente) per eliminare il false signaling.

**Costo**: < 30 min. Richiede decisione utente prima del fix.

---

### I2 — `RegistroVettureAssegnate.from_db()` ignora `programma_id` → wild-card cross-programma

**File**: `backend/src/colazione/domain/builder_pdc/registro_vetture.py:186-213`

**Codice attuale**:
```python
stmt = select(TurnoPdcBlocco.numero_treno_vettura).where(
    TurnoPdcBlocco.tipo_evento == "VETTURA",
    TurnoPdcBlocco.numero_treno_vettura.is_not(None),
    # programma_id ignorato: carica TUTTO il DB
)
```

**Problema**: la query carica TUTTE le vetture VETTURA di TUTTI i programmi,
di tutte le aziende, di tutti i periodi. Il `programma_id` è ricevuto come
parametro ma viene usato solo nel log. In un sistema con 2 programmi attivi
(es. prog 2025-2026 e prog 2024-2025), ogni vettura usata nel programma vecchio
è bloccata anche per il nuovo. Il resolver VOCTAXI (fallback) scatta anche
quando la vettura sarebbe legittimamente disponibile.

**Impatto**: la "conservatività" dichiarata nel docstring è falsa:
bloccare vetture cross-programma NON è conservativo per la qualità dei
turni — genera rientri VOCTAXI artificialmente quando la vettura sarebbe
disponibile.

**Fix** (costo <1h, JOIN su 3 tabelle):
```python
from colazione.models.turni_pdc import TurnoPdcGiornata, TurnoPdc

stmt = (
    select(TurnoPdcBlocco.numero_treno_vettura)
    .join(TurnoPdcGiornata, TurnoPdcBlocco.turno_pdc_giornata_id == TurnoPdcGiornata.id)
    .join(TurnoPdc, TurnoPdcGiornata.turno_pdc_id == TurnoPdc.id)
    .where(
        TurnoPdcBlocco.tipo_evento == "VETTURA",
        TurnoPdcBlocco.numero_treno_vettura.is_not(None),
        TurnoPdc.programma_id == programma_id,  # filtro corretto
    )
)
```

**Prerequisito**: `TurnoPdc` deve avere campo `programma_id` (da verificare
che la FK esista — se non c'è, aggiungere la relazione prima del fix).

**Nota**: il debito della `data_operativa` wild-card (S4 SEVERO, issue I5)
rimane separato. Questo fix risolve il problema di scope del programma,
che è più urgente.

---

### I3 — 4 import locali dentro funzione in `deposito_first.py`

**File**: `backend/src/colazione/domain/builder_pdc/deposito_first.py:595-608`

**Codice attuale**:
```python
async def genera_turni_pdc_deposito_first(...):
    ...
    # 7.ter. §11.5
    from colazione.domain.builder_pdc.riposo_intraturno import (
        calcola_e_valida_riposi_intraturno,
    )
    ...
    # 7.quater. §11.4
    from colazione.domain.builder_pdc.riposo_settimanale import (
        valida_riposo_settimanale,
    )
    from colazione.domain.calendario import festivita_italiane
    from colazione.models.programmi import ProgrammaMateriale
```

**Problema**: import a livello di funzione invece che di modulo. Il commento
in `builder.py` spiega che l'import locale in quel file era necessario per
rompere il ciclo circolare `builder.py ↔ split_cv.py`. Ma questo non si
applica qui: `riposo_intraturno` e `riposo_settimanale` NON importano da
`deposito_first.py`. Non esiste un ciclo da rompere. L'import locale
maschera le dipendenze all'analisi statica di mypy e ruff, e viola PEP 8.

**Fix** (< 10 min): spostare i 4 import in cima al file, dopo gli altri
import del modulo. Verificare con `mypy --strict` e `ruff` che non ci siano
cicli reali.

---

### I4 — Reset contatore `riposo_settimanale.py` post-violazione maschera cicli multipli

**File**: `backend/src/colazione/domain/builder_pdc/riposo_settimanale.py:194-200`

**Codice attuale**:
```python
if contatore >= GIORNATE_CONSECUTIVE_MAX_SENZA_RIPOSO:
    violazioni.append(
        f"riposo_settimanale_no_in_7gg:contatore_raggiunto_{contatore}_a_G{d.numero_giornata}"
    )
    contatore = 0  # ← reset: le giornate successive non vengono conteggiate
```

**Problema**: se ci sono 14 giornate consecutive senza riposo settimanale,
il contatore raggiunge 7, emette 1 violazione, poi viene azzerato. Le
giornate 8-14 vengono riconteggiate da zero. La seconda violazione viene
emessa solo alla giornata 14. Ma siccome il loop termina, se le giornate
sono esattamente 14, la seconda violazione non viene emessa (il contatore
arriva a 7 alla fine del loop senza triggerare l'if).

**Impatto**: cicli con 14+ giornate consecutive senza riposo vengono
segnalati con 1 sola violazione invece di ⌈n/7⌉. Il pianificatore
riceve un report incompleto.

**Fix** (< 30 min): cambiare `contatore = 0` in `contatore = 1` dopo
la violazione. La giornata corrente che ha triggerato la violazione diventa
la giornata 1 del prossimo blocco di 7:
```python
contatore = 1  # la G corrente "conta" come prima del prossimo blocco
```
Aggiungere test: `test_riposo_settimanale.py` con 14 giornate consecutive
senza riposo → attese 2 violazioni.

---

### I5 — `TurnoPdcGiornata` mancante campo `data: date`

**File**: `backend/src/colazione/models/turni_pdc.py:66-86`

**Problema**: `TurnoPdcGiornata` identifica una giornata-tipo tramite
`numero_giornata + variante_calendario`, non tramite data concreta.
Questa è la causa radice di:

- I2: `from_db` usa wild-card su data perché non c'è data nel record
- `deposito_first.py:541`: `data_operativa = valido_da` per TUTTE le
  giornate (stessa data forfettaria)
- Il `riposo_settimanale.py` usa il proxy `gap_min // (24*60)` invece
  di giorni solari reali quando le date non sono disponibili

**Fix strutturale** (migration, costo ~2h):
Aggiungere `data_operativa: Mapped[date | None]` a `TurnoPdcGiornata`.
Popolare il campo dal builder usando `enumera_date_giornata` per ogni
giornata (già implementata in `giornate_concrete.py`).

**Attenzione**: la migration che aggiunge il campo è nullable (retro-compat
con giornate esistenti), ma richiede di ricalcolare `data_operativa` per i
turni già persistiti. Migration invasiva ma non grande: il campo è nullable,
nessun dato viene perso.

---

### I6 — `giornata_base.py` facade nella direzione sbagliata

**File**: `backend/src/colazione/domain/builder_pdc/giornata_base.py:31-58`

**Problema**: `giornata_base.py` importa i simboli privati da `builder.py`
e li ri-espone con nomi pubblici:

```python
# giornata_base.py
from colazione.domain.builder_pdc.builder import (
    _GiornataPdcDraft,   # simbolo privato
    _BloccoPdcDraft,
    ...
)

GiornataPdcDraft = _GiornataPdcDraft  # alias pubblico
```

Questo non è una facade nel senso architetturale: `builder.py` rimane la
**fonte di verità** e `giornata_base.py` è un proxy senza logica propria.
Se `_GiornataPdcDraft` viene spostata o rinominata in `builder.py`, entrambi
i file si rompono. Il disaccoppiamento è nominale, non reale.

**La direzione corretta** è l'inverso:
1. Spostare `_GiornataPdcDraft`, `_BloccoPdcDraft`, le costanti normative e
   le funzioni helper (`_t`, `_from_min`, `_diff`) in `giornata_base.py`
   come simboli pubblici.
2. `builder.py` importa da `giornata_base.py` (non viceversa).
3. I moduli consumatori importano da `giornata_base.py`.

**Costo**: refactoring non banale (~3h), ma non blocca il lavoro corrente.
L'architettura attuale funziona, ma rimane fragile. Va programmato come
MR dedicato (non inline con feature).

---

### I7 — `assert` per invarianti runtime invece di raise espliciti

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:210,253,256`

**Codice attuale**:
```python
# builder.py:210
assert primo.ora_inizio is not None and ultimo.ora_fine is not None

# builder.py:253
assert b.ora_inizio is not None and b.ora_fine is not None

# builder.py:256
assert prec.ora_fine is not None
```

**Problema**: `assert` viene rimosso da Python con il flag `-O`
(ottimizzazione). Anche senza `-O`, `AssertionError` è una sottoclasse di
`Exception` e viene catturata da `except Exception as exc` — pattern usato
in `builder.py:1653`. Le precondizioni sono reali (i blocchi validi sono
già filtrati a riga 204), ma la forma `assert` segnala "debug check" invece
di "invariante di produzione".

**Fix** (< 20 min):
```python
# Sostituire:
assert primo.ora_inizio is not None and ultimo.ora_fine is not None
# Con:
if primo.ora_inizio is None or ultimo.ora_fine is None:
    raise ValueError(
        f"blocco giro senza ora_inizio/ora_fine dopo filtro blocchi_validi: "
        f"{primo=}, {ultimo=}"
    )
```

---

### I8 — `enumera_date_giornata` fallback sovra-include su varianti parlanti Trenord

**File**: `backend/src/colazione/domain/giornate_concrete.py:128-153`

**Codice attuale**:
```python
# Fallback: testo non riconosciuto, sovra-include
logger.info(
    "enumera_date_giornata: variante '%s' non riconosciuta dal "
    "parser MVP, fallback sovra-include ...",
    variante,
    len(candidate),
)
return candidate  # TUTTE le date candidate
```

**Problema**: il PdE Trenord 2026 usa varianti calendariali come:
- `"LV 1:5"` (lavorativo con pattern specifico)
- `"F escluso FpF ed escl. 22/3, 12/4"`
- `"LV escluso 1/1, 6/1, Pasqua, 25/4"`

Queste non matchano nessun pattern MVP → fallback → tutte le date candidate.
Una giornata marcata "F escluso FpF" viene trattata come "giornaliera" (tutti
i giorni del ciclo), sovra-includendo di un fattore ~4-7×. Questo impatta:

- Il calcolo dei giorni solari in `riposo_settimanale.py:243-258`
  (usa `enumera_date_giornata` per determinare `start_dt` del riposo).
- Il `RegistroVettureAssegnate.from_db()` quando sarà rifatto per usare
  date concrete (I5).

**Impatto corrente**: il `riposo_settimanale.py` usa `enumera_date_giornata`
solo per determinare la PRIMA data di una giornata (non l'elenco completo),
quindi il fallback aggiunge rumore ma non cambia il risultato del validatore
(prende `date_pre[0]` che è la prima data candidata, correct anche con
sovra-include). Il rischio cresce quando il registro verrà raffinato.

**Fix** (costo 4-6h, stimato SEVERO S9): implementare un DSL parser
minimale per i pattern comuni Trenord. Alternativa a breve termine: log a
livello WARNING (non INFO) per le varianti non riconosciute, per renderle
visibili in produzione.

---

## MINORI

### M1 — Anti-pattern `_ = SYMBOL` per silenziare ruff

**File**:
- `backend/src/colazione/domain/builder_pdc/deposito_first.py:728`
- `backend/src/colazione/domain/builder_giro/varianti_calendariali.py:293`
- `backend/src/colazione/domain/builder_giro/builder.py:2721-2722`

**Codice attuale**:
```python
# deposito_first.py:728
_ = ACCESSORI_MIN_STANDARD  # silence unused-import warning per ruff

# varianti_calendariali.py:293
_ = Counter  # noqa: F841 — riservato per estensioni

# builder.py:2721-2722
_ = festivita  # noqa: F841 (reservato per uso futuro)
_ = calcola_etichetta_giro  # noqa: F841 (export pubblico mantenuto)
```

**Problema**: anti-pattern che maschera import non usati. Ruff segnala
correttamente. Le motivazioni addotte sono fragili:

- `deposito_first.py:728`: `ACCESSORI_MIN_STANDARD` non è usato nel file
  dopo il refactoring verso `giornata_base.py`. Rimuovere l'import.
- `varianti_calendariali.py:293`: `Counter` "riservato per estensioni
  future" non è un motivo per tenerlo importato ora. Rimuovere, reimportare
  quando serve.
- `builder.py:2721-2722`: `festivita` e `calcola_etichetta_giro` come
  "export pubblici mantenuti" vanno in `__all__`, non via side-effect `_=`.

**Fix** (< 10 min per file):
- Rimuovere gli import inutilizzati.
- Se l'export è intenzionale, aggiungere i simboli a `__all__` esplicitamente.

---

### M2 — Dualità `multi_giornata.py` vs `multi_giornata_v2.py` non documentata

**File**: `backend/src/colazione/domain/builder_giro/multi_giornata_v2.py:1-30`,
`backend/src/colazione/domain/builder_giro/builder.py:86-94`

**Problema**: `builder.py` importa da entrambi i moduli:
```python
from colazione.domain.builder_giro.multi_giornata import ...   # riga 86
from colazione.domain.builder_giro.multi_giornata_v2 import ... # riga 94
```

Il docstring di `multi_giornata_v2.py:29` dice "parallelo a
`multi_giornata.py` v1" ma non spiega quale sia il percorso futuro, né
quando v2 sostituirà v1, né se v2 è già in uso in produzione o è un
esperimento. `test_multi_giornata_v2.py` esiste ma copre solo v2.

**Fix** (< 30 min): aggiungere una sezione `## Status` in cima a
`multi_giornata_v2.py` che dichiari esplicitamente: "(a) v2 sostituirà v1 in
Sprint X" oppure "(b) v2 è un esperimento abbandonato → eliminare" oppure
"(c) v1 e v2 coesistono per modalità diverse (quale modalità usa quale?)".
Senza questa dichiarazione, un lettore non può decidere quale usare.

---

### M3 — Zero test e2e del piano α

**File**: `backend/tests/` (tutti)

**Problema**: i 75+ test del suite sono unit con mock. Non esiste un test
che esegua la pipeline completa: PdE reale → genera giri → genera turni PdC
deposito-first → valida riposo settimanale → persiste in DB test. Il piano
α è operativo in produzione ma il suo corretto funzionamento non è
verificabile offline con `pytest`.

**Fix** (costo 2-3h): aggiungere `test_piano_alpha_e2e.py` con:
1. Fixture PdE minimale (5-10 corse) con date concrete.
2. `POST /api/programmi/{id}/genera-giri` → assert n_giri_creati.
3. `POST /api/programmi/{id}/turni-pdc/genera` → assert n_turni_creati,
   n_violazioni == 0 (o lista known violations).
4. Query DB: verifica che i riposo_min_post siano ≥ 660 min (11h).

Il test richiede DB test disponibile (pattern già usato in
`test_pde_importer_db.py` e `test_genera_giri_api.py`).

---

### M4 — Accumulo script diagnostici non rimossi

**File**: `backend/scripts/`

**Lista**:
- `baseline_pre_pulizia.py` — usato prima di una pulizia dati, non più rilevante
- `diag_giri_sotto_min.py` — diagnostico one-shot Sprint 7
- `diag_pool_esplorativo.py` — diagnostico Sprint 8

**Problema**: script one-shot che hanno esaurito il loro scopo. Restano
nella directory creando l'impressione di "strumenti riutilizzabili". Ogni
nuovo sviluppatore (o il Claude di una sessione futura) potrebbe tentare
di riusarli in contesti sbagliati.

**Fix** (< 5 min): spostare gli script di diagnosi passati in
`scripts/_archivio/` o eliminarli. Tenere solo gli script con valore
continuativo (`seed_dotazione_trenord.py`, `seed_whitelist_e_accoppiamenti.py`).

---

### M5 — Frontend: zero test sui route critici

**File**: `frontend/src/routes/`

**Problema**: i test frontend esistenti coprono solo:
- `LoginRoute.test.tsx` — flow auth
- `ProtectedRoute.test.tsx` — guard auth
- `AssegnaPersoneRoute.test.tsx` — 1 route gestione personale

I route critici per il business (DashboardRoute pianificatore giro,
generazione giri, visualizzazione turni PdC, Gantt) hanno zero test.
Una regressione UI in un componente di questi route non verrebbe rilevata
dal CI.

**Fix** (costo per route ~1h): aggiungere test Vitest per i componenti
più critici, partendo dal golden path (render senza errori + elementi
chiave visibili). Non è necessario testare ogni interazione — un test
di smoke con `render + waitFor(screen.getByText(...))` è sufficiente per
intercettare regressioni di build.

---

## Riepilogo priorità

| Priorità | ID | Fix time | Blocca Sprint? |
|----------|----|----------|----------------|
| 1 | C1 | 30 min | ✅ SÌ (Sprint 8.2 chiusura ufficiale §9) |
| 2 | C2 | 2h | ⚠️ normativamente urgente |
| 3 | C3 | 1h | ⚠️ silenzioso in produzione |
| 4 | I1 | 30 min | richiede decisione utente prima |
| 5 | I2 | 1h | impatta qualità turni multi-programma |
| 6 | I3 | 10 min | manutenibilità |
| 7 | I4 | 30 min | correttezza validatore |
| 8 | I5 | 2h (migration) | root cause I2, I8 |
| 9 | I6 | 3h | architetturale, non urgente |
| 10 | I7 | 20 min | robustezza |
| 11 | I8 | 30 min (log upgrade) / 4-6h (DSL) | dipende dalla priorità |
| 12 | M1 | 10 min/file | cleanup |
| 13 | M2 | 30 min | chiarezza codebase |
| 14 | M3 | 2-3h | sicurezza regressioni |
| 15 | M4 | 5 min | ordine |
| 16 | M5 | 1h/route | copertura UI |
