# Code review COLAZIONE — 2026-05-09

> Review completa del repo al 2026-05-09, eseguita su richiesta utente.
> Stato di partenza: 144 test backend verdi (post Sprint 8.1 MR-A3-bis +
> A4-bis), mypy --strict 82 file clean, typecheck frontend clean.
>
> **Scope**: backend + frontend + test + migrazioni + dominio normativo.
> Review precedente: `docs/CODE-REVIEW-2026-05-01.md` (6 critici, 11 importanti,
> 7 minori). Questa review aggiorna lo stato di quei finding e aggiunge i
> nuovi emersi dal codice scritto da 2026-05-01 ad oggi (Sprint 8.0–8.1:
> `multi_turno.py`, `assegnazione_persone.py`, `backtracking_esplorativo.py`,
> dashboard Manutenzione/PdC/GestionePersonale).
>
> **Metodo**: lettura diretta dei file sorgente (`builder_pdc/*.py`,
> `normativa/assegnazione_persone.py`, `models/*.py`, `api/*.py`,
> `frontend/src/routes/**/*.tsx`), confronto sistematico con
> `docs/NORMATIVA-PDC.md` come fonte di verità.

---

## Sintesi

| Categoria | Nuovi | Ancora aperti da 01-05 | Chiusi da 01-05 | Totale aperti |
|-----------|------:|----------------------:|----------------:|-------------:|
| **Critici** | 1 | 5 | 1 | **6** |
| **Importanti** | 6 | 9 | 2 | **15** |
| **Minori** | 3 | 5 | 2 | **8** |

Finding chiusi da review precedente: **C3** (FK-in-JSON programma_id → ✅ fix applicato in builder_giro) e **I1** (utcnow → ✅ ora usa `datetime.now(UTC)` ovunque).

---

## CRITICI

### C1 — Anti-rigenerazione turni PdC: full table scan + filtro Python *(aperto da 01-05)*

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:710-727`

```python
existing = list(
    (await session.execute(
        select(TurnoPdc).where(TurnoPdc.azienda_id == azienda_id)
    )).scalars()
)
if (t.generation_metadata_json or {}).get("giro_materiale_id") != giro_id:
    ...
```

**Cosa fa**: per ogni chiamata a `genera_turno_pdc`, carica in memoria
**tutti i turni PdC dell'azienda** e poi filtra in Python sul JSONB.

**Impatto**: O(N) su tutta la tabella `turno_pdc` ad ogni generazione.
Con 30 giri × 7 varianti × N programmi il numero cresce rapidamente.
Il JSONB path `generation_metadata_json->>'giro_materiale_id'` non usa
l'indice `ix_turno_pdc_azienda_deposito` (che copre `azienda_id, deposito_pdc_id`).

**Fix**:
1. Migration: aggiungere colonna FK `turno_pdc.giro_materiale_id BIGINT`
   (nullable per compat, backfill dal JSON, FK con `ondelete=CASCADE`).
2. Sostituire la query:
   ```python
   select(TurnoPdc).where(
       TurnoPdc.azienda_id == azienda_id,
       TurnoPdc.giro_materiale_id == giro_id,
   )
   ```
   e aggiungere filtro opzionale su `deposito_pdc_id` per i match con deposito.

**Costo**: ~2h (migration + backfill + test).

---

### C2 — Cap prestazione notturna: `is_notturno` e cap_prestazione divergono *(aperto da 01-05, aggravato da NC-2)*

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:331-337`
+ `backend/src/colazione/domain/builder_pdc/split_cv.py:151-153`
+ `backend/src/colazione/domain/builder_pdc/multi_turno.py:141, 905`

```python
# builder.py:331
is_notturno = ora_presa < 5 * 60 or ora_fine_servizio > 22 * 60 or ora_fine_servizio < ora_presa

# builder.py:334-337
cap_prestazione = (
    PRESTAZIONE_MAX_NOTTURNO     # 420 min
    if 60 <= ora_presa < 5 * 60  # = 01:00-04:59
    else PRESTAZIONE_MAX_STANDARD
)

# split_cv.py:152 — usa is_notturno (SBAGLIATO)
cap_prestazione = PRESTAZIONE_MAX_NOTTURNO if draft.is_notturno else PRESTAZIONE_MAX_STANDARD
```

**Il bug in 3 punti**:

1. `is_notturno=True` se `ora_presa=0` (mezzanotte), ma il cap notturno
   (420 min) scatta solo se `60 <= ora_presa < 300` (01:00-04:59).
   Una giornata con presa a 00:30 è marcata `is_notturno=True` ma applica
   il cap STANDARD (510 min) → può sforare senza violazione.

2. `split_cv._eccede_limiti` e `multi_turno._eccede_cap_prestazione`
   usano `draft.is_notturno` per decidere il cap: un turno con presa
   alle 06:00 e fine alle 23:00 (`is_notturno=True` per `fine > 22*60`)
   viene cappato a 420 min invece di 510 → split generato inutilmente.

3. Tre file contengono questa logica divergente. Nessun test copre i
   casi limite `ora_presa=0`, `ora_presa=59`, `ora_fine_servizio=22*60+1`
   con `ora_presa > 60`.

**Fix**:
```python
# Estrarre in costante o helper — un solo posto
def _is_presa_notturna(ora_presa_min: int) -> bool:
    """Normativa §11: cap 7h se presa servizio 01:00-04:59."""
    return 60 <= ora_presa_min < 300

# Allineare is_notturno (flag UI/DB) alla stessa formula se
# la normativa li collega, oppure separarli esplicitamente:
# - is_notturno (flag UI, broad) = turno che tocca le ore notturne
# - _is_presa_notturna (cap normativo, narrow) = solo 01:00-04:59
```
Usare `_is_presa_notturna(ora_presa)` (non `draft.is_notturno`) in
`_eccede_limiti` e `_eccede_cap_prestazione`.

**Costo**: ~1h + conferma utente sulla definizione esatta "notturno" per NORMATIVA §11.

---

### C3 — Preriscaldo ACCp 80' dic-feb: non implementato *(aperto da 01-05)*

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:55-58, 195-196`

```python
ACCESSORI_MIN_STANDARD = 40     # sempre usato — mai 80

ora_inizio_accp = (primo_inizio - ACCESSORI_MIN_STANDARD) % (24 * 60)
```

**Normativa**: `docs/NORMATIVA-PDC.md:245`
> Condotta con preriscaldo ● (dic-feb): ACCp = **80'**, ACCa = 40'

Il campo `TurnoPdcBlocco.is_accessori_maggiorati` (turni_pdc.py:112) esiste
ma il builder lo setta sempre `False` (builder.py:858).

**Impatto**: in dic-feb la prestazione è sottostimata di 40 min per ogni
turno con presa fuori Fiorenza. Cap 510 min apparentemente rispettato
mentre in realtà è 550 → split CV non scatta quando dovrebbe; violazione
normativa silenziosa.

**Decisioni necessarie** (richiede utente):
1. Prestazione "worst-case" (80' sempre, sicuro ma conservativo) o modello
   data-aware (ACCp diverso a seconda della data calendariale)?
2. Un `TurnoPdc` che copre dic-feb E marzo deve essere duplicato per regime,
   o una sola rappresentazione con flag?

**Fix minimo (worst-case)**:
```python
ACCESSORI_MIN_PRERISCALDO = 80

def _accp_min(stazione_partenza: str | None, data: date) -> int:
    """80' in dic-feb se stazione non è Fiorenza (NORMATIVA §3.3 + §8.5)."""
    if data.month in (12, 1, 2) and stazione_partenza != "FIO":
        return 80
    return ACCESSORI_MIN_STANDARD
```
e settare `is_accessori_maggiorati=True` sul blocco ACCp corrispondente.

**Costo**: 4-6h (decisione + implementazione + test).

---

### C4 — Gap fra blocchi sempre classificato PK: ACC/CV non distinti *(aperto da 01-05)*

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:239-249`

```python
drafts.append(_BloccoPdcDraft(
    tipo_evento="PK",   # sempre PK, indipendentemente dal gap
    ...
))
```

**Normativa** (§3.4, §5, §6): ogni gap > 0 può essere CV (<65 min),
PK (qualsiasi gap, programmato), o ACCa+ACCp (≥65 min). Il builder usa
sempre PK, senza distinguere. Impatto su:
1. Prestazione sottostimata (PK = 20'+20' vs ACC = 40'+40').
2. Turni intra-giornata che in realtà userebbero ACC pagano meno
   del dovuto → falso rispetto del cap 510 min.
3. Lo split CV tra rami paga ACCa+ACCp ai bordi ma la transizione
   tra rami dentro la stessa giornata è rappresentata come PK-gap → incoerente.

**Stato**: residuo documentato in TN-UPDATE entry 59, ma NON tracciato
in CLAUDE.md §7 "prossimo step" né in TN-UPDATE recenti.

**Fix**: strutturale (1-2 gg). Almeno documentare il residuo esplicitamente
nella review summary di TN-UPDATE corrente.

---

### C5 — `auto_assegna`: storia storica fuori-finestra non caricata *(NUOVO)*

**File**: `backend/src/colazione/domain/normativa/assegnazione_persone.py:444-503`
+ `backend/src/colazione/api/programmi.py:1196-1228`

**Il problema in dettaglio**:

Il caller di `auto_assegna` carica `AssegnazioneEsistente` così:

```python
# programmi.py:1202-1221
esist_rows = await session.execute(
    select(...).where(
        AssegnazioneGiornata.turno_pdc_giornata_id.in_(giornate_ids),  # ← solo questo programma
        AssegnazioneGiornata.data >= data_da,                           # ← solo la finestra
        AssegnazioneGiornata.data <= data_a,
        ...
    )
)
```

Queste `AssegnazioneEsistente` vengono usate **solo** per popolare
`_StatoAssegna.assegnate_per_persona_data` (check "già assegnato oggi").
Non vengono mai usate per alimentare `storia_per_persona` né `fr_per_persona`.

Risultato: il check **riposo intraturno** (§11.5) e il check **cap FR** (§10.6)
sono **ciechi alle assegnazioni fuori finestra/programma**.

**Scenario di violazione reale**:
- PdC Bianchi ha lavorato ieri (fuori finestra, turno diverso programma).
- Il run di auto_assegna di oggi non vede quell'assegnazione in
  `storia_per_persona` → `gap_h < _riposo_richiesto_h` = 0h < 11h → ma
  il check non scatta perché la storia è vuota → Bianchi viene assegnato.
- Violazione hard §11.5 non rilevata.

**Violazione formale**: §11.5 (riposo intraturno) è dichiarato HARD nel
docstring del modulo ma non è rispettato quando la storia è cross-run.

**Fix**:
Il caller deve caricare **anche** la storia recente di ogni persona
candidata (almeno 2 giorni prima di `data_da` per il riposo intraturno,
e rolling 28 giorni per il cap FR). Esempio:

```python
# Per ogni persona candidata, carica gli ultimi 2 giorni + 28gg se FR
storia_rows = await session.execute(
    select(
        AssegnazioneGiornata.persona_id,
        AssegnazioneGiornata.data,
        TurnoPdcGiornata.inizio_prestazione,
        TurnoPdcGiornata.fine_prestazione,
        TurnoPdcGiornata.is_notturno,
        TurnoPdcGiornata.is_fr,  # se esiste
    ).join(TurnoPdcGiornata, ...)
    .where(
        AssegnazioneGiornata.persona_id.in_(persona_ids),
        AssegnazioneGiornata.data >= data_da - timedelta(days=29),
        AssegnazioneGiornata.data < data_da,
        AssegnazioneGiornata.stato != "annullato",
    )
)
```
e iniettarla come `storia_precaricata` nell'algoritmo prima del loop.

**Costo**: ~3h (query + tipo `AssegnazioneStorica` + pre-populate stato
in `auto_assegna`).

---

### C6 — `STAZIONI_CV_DEROGA = {"MORTARA", "TIRANO"}` potrebbe non matchare il DB *(aperto da 01-05)*

**File**: `backend/src/colazione/domain/builder_pdc/split_cv.py:59`

`TIRANO` non è nel seed Trenord e il suo codice nel DB reale (dopo import
PdE) non è confermato. Se il codice fosse diverso, lo split CV non scatta
sulla direttrice Tirano. Smoke con giro che attraversa Tirano: mai scritto.

**Fix**: verifica empirica su DB reale + test integration.

---

## IMPORTANTI

### I1 — `TurnoPdcGiornata` e `TurnoPdcBlocco`: FK senza indice *(NUOVO)*

**File**: `backend/src/colazione/models/turni_pdc.py:64-117`

PostgreSQL NON crea automaticamente indici sulle FK. Le query critiche
(turni_pdc.py:572, 686, 730, 743) accedono a queste tabelle via FK:

```python
# turni_pdc.py:730
select(TurnoPdcGiornata).where(TurnoPdcGiornata.turno_pdc_id == turno_id)
# turni_pdc.py:743
select(TurnoPdcBlocco).where(TurnoPdcBlocco.turno_pdc_giornata_id.in_(giornata_ids))
```

Con N giri × G giornate × B blocchi per giornata, questi `SELECT` fanno
full-scan senza indice.

**Fix**:
```python
# turni_pdc.py — aggiungere __table_args__
class TurnoPdcGiornata(Base):
    __table_args__ = (
        Index("ix_turno_pdc_giornata_turno_pdc_id", "turno_pdc_id"),
    )

class TurnoPdcBlocco(Base):
    __table_args__ = (
        Index("ix_turno_pdc_blocco_giornata_id", "turno_pdc_giornata_id"),
    )
```
+ migration Alembic.

**Costo**: ~30 min + migration.

---

### I2 — `AssegnazioneGiornata`: doppio-booking possibile a DB level *(NUOVO)*

**File**: `backend/src/colazione/models/personale.py:52-69`

Non esiste `UniqueConstraint("persona_id", "data")` sulla tabella
`assegnazione_giornata`. L'algoritmo greedy lo evita in software,
ma endpoint di assegnazione manuale (programmi.py) non lo impedisce a DB.

Scenario: due richieste concorrenti di assegnazione manuale possono
inserire la stessa `(persona_id, data)` senza conflitto.

Manca anche un indice su `turno_pdc_giornata_id` (FK senza index, stesso
pattern I1 sopra, ma qui le query sono ancora più frequenti per il
check delle assegnazioni esistenti).

**Fix**:
```python
class AssegnazioneGiornata(Base):
    __table_args__ = (
        UniqueConstraint(
            "persona_id", "data",
            name="uq_assegnazione_giornata_persona_data",
        ),
        Index("ix_assegnazione_giornata_turno_pdc_giornata_id", "turno_pdc_giornata_id"),
    )
```
+ migration (con `ON CONFLICT DO NOTHING` sul backfill se ci sono duplicati legacy).

**Costo**: ~45 min + migration.

---

### I3 — `Persona.codice_dipendente`: nessun vincolo unicità per azienda *(NUOVO)*

**File**: `backend/src/colazione/models/personale.py:35`

```python
codice_dipendente: Mapped[str] = mapped_column(String(40))
```

Nessun `UniqueConstraint("azienda_id", "codice_dipendente")`. Due persone
con la stessa matricola dipendente possono coesistere nell'anagrafica di
un'azienda senza errore DB — errore rilevato solo a runtime applicativo.

**Fix**:
```python
__table_args__ = (
    UniqueConstraint(
        "azienda_id", "codice_dipendente",
        name="uq_persona_azienda_codice_dipendente",
    ),
)
```
+ migration.

**Costo**: 20 min + migration.

---

### I4 — `assert` per type narrowing in produzione *(aperto da 01-05)*

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:190, 233, 236, 413, 469, 1107`

```python
assert primo.ora_inizio is not None and ultimo.ora_fine is not None
assert b.ora_inizio is not None and b.ora_fine is not None
assert prec.ora_fine is not None
```

Python con ottimizzazioni (`-O`) streppa gli `assert`. Se Railway o il
deploy usa `-O`, questi controlli scompaiono silenziosamente. Il filtro
`blocchi_validi = [b for b in blocchi_giro if b.ora_inizio is not None]`
a riga 184 già garantisce la condizione — gli assert sono ridondanti e
falsi come safety net.

**Fix**: sostituire con `if ... is None: raise RuntimeError(...)` oppure
introdurre un `TypeVar` narrowato (`_BloccoConOrari`) per eliminare
l'Optional dal tipo e rimuovere la necessità dell'assert.

**Costo**: 30 min.

---

### I5 — `updated_at` non aggiornato sui write *(aperto da 01-05)*

**File**: `backend/src/colazione/models/turni_pdc.py:57`,
`backend/src/colazione/models/personale.py:69`,
`backend/src/colazione/models/anagrafica.py:116, 558`

```python
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), server_default=func.now()
)
```

`server_default=func.now()` imposta il valore alla INSERT e non lo aggiorna
mai sui successivi UPDATE. Il campo è inutile per audit/debug: mostra
sempre il momento della creazione. `TurnoPdc`, `AssegnazioneGiornata`,
`LocalitaSosta`, e `Stazione` sono le più impattanti.

*Nota*: `ProgrammaMateriale.updated_at` (programmi.py) viene aggiornato
manualmente via `p.updated_at = datetime.now(UTC)` in vari endpoint —
pattern corretto ma fragile (dipende dal caller ricordarsi di farlo).

**Fix**: aggiungere `onupdate=func.now()` alle colonne, oppure aggiungere
un trigger PostgreSQL `BEFORE UPDATE SET updated_at = now()`. La via più
robusta è il trigger (funziona anche per update diretti da migration).

**Costo**: 30 min modello + migration trigger (o `onupdate` per ogni tabella).

---

### I6 — JWT access token 72h *(aperto da 01-05)*

**File**: `backend/src/colazione/config.py:39`

```python
jwt_access_token_expire_min: int = 4320  # 72h
```

Con access token di 72h, la revoca di un ruolo o la disattivazione di un
utente diventano effettive solo dopo 3 giorni. Il default del secret
(`"dev-secret-change-me-min-32-characters-long"`) non ha validazione che
sia stato sovrascritto in produzione.

**Fix immediato**: ridurre a 30-60 min, alzare refresh a 7gg. Validare
che `jwt_secret != default` in produzione con un `@validator` in Settings.

**Costo**: 1h (incluso refresh flow frontend).

---

### I7 — `impianto` di TurnoPdc popolato col `tipo_materiale` *(aperto da 01-05)*

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:1021`

```python
impianto = giro.tipo_materiale[:80] if giro.tipo_materiale else "ND"
```

Il campo `TurnoPdc.impianto` (String 80) ha semantica "impianto di
manutenzione" (es. `FIO`, `NOV`). Viene invece popolato con il tipo
materiale (`ETR425`, `ETR526`). Query `WHERE impianto = 'FIO'` returnano
zero risultati perché tutti i record hanno `ETR*`. La dashboard
Pianificatore PdC (overview per impianto) mostra valori non significativi.

Fix: usare `loc.codice_breve` (già caricata come `loc` nell'endpoint).

**Costo**: 30 min.

---

### I8 — `window.alert` / `window.confirm` pervasivi nel frontend *(NUOVO)*

**File**: ~22 occorrenze in
`frontend/src/routes/pianificatore-giro/ProgrammaDettaglioRoute.tsx:334, 339, 406, 411, 450, 462, 536, 556`,
`frontend/src/routes/pianificatore-giro/ProgrammiRoute.tsx:585, 589, 596, 600, 616, 624`,
`frontend/src/routes/pianificatore-giro/GiroDettaglioRoute.tsx:371, 394, 561, 571, 580`,
`frontend/src/routes/manutenzione/DashboardRoute.tsx`,
`frontend/src/routes/pianificatore-pdc/DashboardRoute.tsx:829, 840`, ecc.

`window.confirm` e `window.alert` sono bloccanti (freezano il thread UI),
non accessibili (nessun focus management, non leggibili da screen reader),
non stilizzabili con Tailwind, e vengono soppressi in alcuni browser in
contesti embedded o cross-origin.

Il codebase ha già `Dialog.tsx` in `components/ui/` per questo scopo.

**Impatto**: tutte le azioni distruttive (pubblica programma, archivia,
elimina, conferma manutenzione) usano `window.confirm`. Su browser con
popup bloccati, queste azioni diventano inaccessibili.

**Fix**: sostituire con il componente `Dialog` esistente (modal di conferma
con i pulsanti Annulla / Conferma). Pattern presente ma non usato
sistematicamente.

**Costo**: ~3-4h per la sostituzione sistematica (22 occorrenze).

---

### I9 — Filtro perimetro pool con `giorno_tipo='feriale'` hardcoded *(aperto da 01-05)*

**File**: `backend/src/colazione/domain/builder_giro/builder.py:684, 1131, 1493`

```python
candidate = [r for r in regole if matches_all(r.filtri_json, prima_corsa, "feriale")]
```

Il filtro pool usa sempre `"feriale"` come euristica. Una corsa con regole
solo `giorno_tipo='festivo'` viene esclusa dal pool e non raggiunge mai
l'assegnazione finale. Per programmi che coprono servizi dedicati ai
festivi, le corse residue non vengono coperte.

**Fix**:
```python
GIORNI_TIPO = ("feriale", "sabato", "festivo")
def _corsa_in_perimetro(c) -> bool:
    return any(
        matches_all(r.filtri_json, c, gt)
        for r in regole for gt in GIORNI_TIPO
    )
```

**Costo**: 30 min + test con regola solo-festivo.

---

### I10 — `_aggiungi_dormite_fr` muta in-place i draft *(aperto da 01-05)*

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:879-952`

```python
curr.blocchi.insert(0, nuovo_blocco)
```

Muta la lista `blocchi` di un `_GiornataPdcDraft` esistente. Il pattern
corretto nel codebase è ritornare una nuova struttura (vedi `_inserisci_refezione`
che ritorna `list[_BloccoPdcDraft]` nuova). La mutazione in-place rende
i test più difficili e può introdurre bug se i draft fossero condivisi.

**Fix**: ritornare `list[_GiornataPdcDraft]` con blocchi prepended invece
di mutare in-place.

**Costo**: 1h.

---

### I11 — Test diretti mancanti per helper critici del builder PdC *(aperto da 01-05, parzialmente chiuso)*

**File**: `backend/tests/`

Da review 2026-05-01: `_inserisci_refezione`, `_aggiungi_dormite_fr`,
`_persisti_un_turno_pdc` senza test unitari diretti.

**Stato aggiornato**:
- ✅ `_inserisci_refezione_ai_bordi`: coperta in `test_refezione_ai_bordi.py`.
- ❌ `_inserisci_refezione` (la funzione primaria, non il bordi): ancora zero test diretti.
- ❌ `_aggiungi_dormite_fr`: zero test diretti.
- ❌ `_persisti_un_turno_pdc`: zero test diretti.

Quando uno di questi helper si rompe in modo sottile, il fallimento
emerge solo dallo smoke end-to-end — difficile da localizzare.

**Fix**: ≥6 test per `_inserisci_refezione` (PK breve, PK fuori finestra,
due candidati, PK al boundary); ≥4 test per `_aggiungi_dormite_fr`.

**Costo**: 2h.

---

### I12 — Race condition `_next_numero_rientro_sede` *(aperto da 01-05)*

**File**: `backend/src/colazione/domain/builder_giro/persister.py`

```python
last = (await session.execute(stmt)).scalar_one()
return f"9{(int(last) + 1):04d}"
```

Pattern `SELECT MAX → +1` senza lock. Due chiamate concorrenti generano
lo stesso numero e una INSERT fallisce per UNIQUE violation.

**Fix**: sequence PostgreSQL `CREATE SEQUENCE rientro_sede_seq` + `SELECT nextval(...)`.

**Costo**: 30 min + migration.

---

### I13 — `km_media_annua_giro` usa solo la prima corsa per giornata *(aperto da 01-05)*

**File**: `backend/src/colazione/domain/builder_giro/persister.py`

Usa la periodicità della prima corsa della giornata per stimare i km annui,
ignorando le corse successive (che potrebbero avere periodicità diversa).
Errore rilevante per la dashboard manutenzione (km cap → manutenzione
programmata).

**Fix**: intersezione delle `valido_in_date_json` di tutte le corse della
giornata invece di solo la prima.

**Costo**: 1h.

---

### I14 — `domain/normativa/__init__.py` vuoto *(aperto da 01-05, si aggrava)*

**File**: `backend/src/colazione/domain/normativa/__init__.py`

Il package normativa conteneva solo `__init__.py` vuoto al momento della
review precedente. Da allora è stato aggiunto `assegnazione_persone.py` —
ottimo — ma le costanti normative chiave (`PRESTAZIONE_MAX_STANDARD`,
`CONDOTTA_MAX_MIN`, `REFEZIONE_MIN_DURATA`, `REFEZIONE_FINESTRE`,
`REFEZIONE_SOGLIA_MIN`, `ACCESSORI_MIN_STANDARD`, `FR_MAX_PER_SETTIMANA`)
restano sparse in `builder_pdc/builder.py` invece di stare nel package
`normativa`. Il risultato è che `split_cv.py` e `multi_turno.py` importano
da `builder_pdc/builder.py` costanti normative (accoppiamento architetturale
sbagliato: la normativa dipende dal builder PdC invece del contrario).

**Fix**: migrare le costanti normative in `domain/normativa/costanti.py`
e farle importare da `builder_pdc/builder.py`, `split_cv.py`, `multi_turno.py`.

**Costo**: 1h (rename + update import, nessuna logica da spostare).

---

## MINORI

### M1 — `split_cv._eccede_limiti` e `multi_turno._eccede_cap_prestazione` propagano C2 *(NUOVO)*

**File**: `backend/src/colazione/domain/builder_pdc/split_cv.py:151-153`,
`backend/src/colazione/domain/builder_pdc/multi_turno.py:141, 905`

Tre funzioni indipendenti replicano la stessa logica difettosa (`is_notturno`
invece del range `01:00-04:59`). Quando C2 sarà risolto, il fix dovrà
essere applicato in 4 posti (builder.py + 3 qui). L'estrazione in helper
unico (vedi fix C2) risolve il problema strutturalmente.

---

### M2 — `httpx` importato a livello modulo in `multi_turno.py` *(NUOVO)*

**File**: `backend/src/colazione/domain/builder_pdc/multi_turno.py:52`

```python
import httpx
```

`httpx` è una dipendenza di I/O di rete usata solo nella heuristic
`_sceglie_deposito_ottimale` (integrazione API live Arturo). Il DP puro
(`_dp_segmenta_giornata`) non ne ha bisogno ma la dipendenza è ora
dichiarata a livello modulo. Rende impossibile testare il DP senza mock
di httpx e accoppia la logica algoritmica pura alla dipendenza HTTP.

**Fix**: passare il client httpx (o il risultato dell'API call) come
parametro alla heuristic. Il DP rimane puro e testabile senza mock.

**Costo**: 30 min refactor + aggiornamento test esistenti.

---

### M3 — `tipo_evento` in `_BloccoPdcDraft` è `str` libero *(NUOVO)*

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:141`

```python
tipo_evento: str  # CONDOTTA, VETTURA, REFEZ, ACCp, ACCa, CVp, CVa, PK, SCOMP, PRESA, FINE
```

I valori ammessi sono documentati nel commento ma non validati dal tipo.
Un typo (`"Condotta"` invece di `"CONDOTTA"`) passa mypy --strict senza
errore. Il frontend dipende da questi valori per il rendering Gantt.

**Fix**:
```python
from typing import Literal

TipoEventoPdc = Literal[
    "CONDOTTA", "VETTURA", "REFEZ", "ACCp", "ACCa",
    "CVp", "CVa", "PK", "SCOMP", "PRESA", "FINE"
]

@dataclass
class _BloccoPdcDraft:
    tipo_evento: TipoEventoPdc
```

**Costo**: 15 min (mypy catturerà eventuali discrepanze esistenti al momento del fix).

---

### M4 — `require_role` usa string match invece di Literal/Enum *(aperto da 01-05)*

**File**: `backend/src/colazione/auth/dependencies.py:66`

```python
def require_role(role: str) -> ...:
```

Typo (`"PIANIFICATORE_GIRRO"`) non viene catturato da mypy. 13 chiamanti
distribuiti in 10 file API.

**Fix**: `Literal["PIANIFICATORE_GIRO", "PIANIFICATORE_PDC", ...]`.

**Costo**: 15 min.

---

### M5 — Smoke scripts lasciano dati in DB *(aperto da 01-05)*

**File**: `backend/scripts/smoke_74_split_cv.py`, `smoke_75_bug5_chiuso.py`,
`smoke_56_cremona.py`, `smoke_56_tirano.py`

Scripts che lasciano dati in DB senza cleanup. Il secondo run fallisce o
crea duplicati. Serve `--cleanup` flag o programma con codice fisso
cancellato a inizio script.

**Costo**: 30 min.

---

### M6 — Dead code: `revisioni` module *(aperto da 01-05)*

**File**: `backend/src/colazione/models/revisioni.py`,
`backend/src/colazione/domain/revisioni/__init__.py`,
`backend/src/colazione/schemas/revisioni.py`

Non importato da nessuna API. Il placeholder `revisioni_cascading_attive`
nell'overview PdC (pianificatore_pdc.py) ritorna sempre `0`. Scope futuro
o idea abbandonata: documentare una delle due.

---

### M7 — `noqa: F841` su simboli "riservati per uso futuro" *(aperto da 01-05)*

**File**: `backend/src/colazione/domain/builder_giro/varianti_calendariali.py:293`,
`backend/src/colazione/domain/builder_giro/builder.py:2026-2027`

```python
_ = Counter  # noqa: F841 — riservato per estensioni
_ = festivita  # noqa: F841 (export pubblico mantenuto)
```

Pattern che sopprime warning senza risolvere il debito. Se `Counter` non
è usato, va rimosso o commentato. Se `festivita` è un export intenzionale,
va esposto in `__all__`.

---

### M8 — Auth: refresh token stateless, revoca impossibile *(aperto da 01-05)*

**File**: `backend/src/colazione/auth/tokens.py:62-76`

Il refresh token (30gg default) non ha store server-side. Logout o cambio
password non invalidano il refresh esistente. Documentato come scelta MVP
ma da segnalare per hardening pre-produzione.

---

## VERIFICHE NEGATIVE (cose cercate e non trovate)

- **SQL injection**: SQLAlchemy con parametrizzazione ovunque. ✓
- **XSS frontend**: React escape automatico, niente `dangerouslySetInnerHTML`. ✓
- **ondelete mancante**: tutti i FK hanno `ondelete` esplicito
  (`CASCADE`, `RESTRICT`, `SET NULL`). ✓
- **bcrypt cost factor**: `12` = OWASP-aligned. ✓
- **N+1 query evidenti**: le query critiche usano `.in_()` batch. ✓
- **datetime.utcnow() residuo**: ✓ eliminato, ora usa `datetime.now(UTC)`.
- **Import circolare**: l'unico gestito con import deferred in funzione
  (builder.py:46-50 per split_cv). Soluzione corretta e documentata.

---

## Stato finding review 2026-05-01

| Finding | Titolo | Stato |
|---------|--------|-------|
| C1 | Full table scan turni PdC | **Ancora aperto** (= C1 questa review) |
| C2 | Cap notturno boundary | **Ancora aperto** (= C2 questa review) |
| C3 | FK-in-JSON programma_id | **✅ CHIUSO** — `_count_giri_esistenti` e `_wipe_giri_programma` usano colonna |
| C4 | Preriscaldo dic-feb | **Ancora aperto** (= C3 questa review) |
| C5 | Gap sempre PK | **Ancora aperto** (= C4 questa review) |
| C6 | STAZIONI_CV_DEROGA TIRANO | **Ancora aperto** (= C6 questa review) |
| I1 | `datetime.utcnow()` deprecato | **✅ CHIUSO** — ora usa `datetime.now(UTC)` |
| I2 | `assert` in produzione | **Ancora aperto** (= I4 questa review) |
| I3 | JWT 72h | **Ancora aperto** (= I6 questa review) |
| I4 | `impianto` = `tipo_materiale` | **Ancora aperto** (= I7 questa review) |
| I5 | `updated_at` non aggiornato | **Ancora aperto** (= I5 questa review) |
| I6 | `feriale` hardcoded pool | **Ancora aperto** (= I9 questa review) |
| I7 | Mutazione FR draft | **Ancora aperto** (= I10 questa review) |
| I8 | Test mancanti helper PdC | **Parzialmente aperto** (= I11 questa review) |
| I9 | Query duplicata `_wipe`/`_count` | **✅ CHIUSO** (risolto insieme a C3) |
| I10 | `km_media_annua` prima corsa | **Ancora aperto** (= I13 questa review) |
| I11 | Race condition rientro sede | **Ancora aperto** (= I12 questa review) |
| M1 | `normativa/__init__.py` vuoto | **Parzialmente chiuso** — aggiunto `assegnazione_persone.py`; costanti ancora nel posto sbagliato (= I14 questa review) |
| M2 | Dead code revisioni | **Ancora aperto** (= M6 questa review) |
| M3 | `ciclo_giorni` cap 14 hardcoded | Non analizzato in questa review — invariato |
| M4 | Truncation codice turno silente | Non analizzato in questa review — invariato |
| M5 | Smoke lascia dati in DB | **Ancora aperto** (= M5 questa review) |
| M6 | `require_role` string match | **Ancora aperto** (= M4 questa review) |
| M7 | Refresh token stateless | **Ancora aperto** (= M8 questa review) |

---

## Riepilogo per priorità

**Urgenti — chiudibili in <2h ciascuno**:

- I1 (index FK turno_pdc_giornata + blocco) — 30 min
- I2 (unique constraint assegnazione_giornata) — 45 min
- I3 (unique constraint persona codice_dipendente) — 20 min
- I4 (assert → RuntimeError) — 30 min
- I7 (impianto = loc.codice_breve) — 30 min
- M1 → M8 (minori) — 2h totali

**Da decidere con utente prima**:

- C2 (definizione normativa di "notturno" per cap 7h: è solo 01:00-04:59
  o anche chi finisce dopo le 22:00?)
- C3 (preriscaldo: worst-case o data-aware? Eccezione Fiorenza confermata?)
- I6 (JWT 72h: quando abbassare per MVP → produzione?)
- I14 (costanti normativa in package `normativa`: timeline migration?)

**Strutturali grandi (>1 gg)**:

- C1 (FK turno_pdc → giro_materiale): migration + backfill.
- C4 (ACC/CV no-overhead): modello blocchi, decisioni design.
- C5 (storia storica auto_assegna): query + tipo `AssegnazioneStorica` + logica.
- I8 (`window.alert` → Dialog): 22 occorrenze, pattern sistematico.
- I11 (test `_inserisci_refezione`, `_aggiungi_dormite_fr`): 2h writing.

**Non chiudere ora (residui legittimi o post-MVP)**:

- C6 (TIRANO): richiede verifica empirica su DB reale con PdE importata.
- M8 (refresh stateless): hardening post-MVP.
- M6 (revisioni dead code): documentare scope o rimuovere.

---

*Review eseguita da NINO (Claude Code). Nessun fix automatico al codice
applicato in questa sessione — output esclusivamente documentale, come
concordato con l'utente.*
