# Code review COLAZIONE — 2026-05-05

> Review eseguita il 2026-05-05 dopo chiusura Sprint 7.9 β2 (7 sub-MR,
> entries 131–138). Stato di partenza: branch `claude/zen-babbage-bBE8q`,
> commit `29730c6`. Backend `mypy --strict` 63 file clean, smoke E2E
> β2 superato in produzione.
>
> **Scope**: tutto il repo (backend + frontend + test + migrazioni),
> con attenzione speciale al codice introdotto durante Sprint β2.
> I finding della review precedente (`docs/CODE-REVIEW-2026-05-01.md`)
> sono referenziati quando ancora aperti — non ripetuti per esteso.
>
> **Metodo**: lettura diretta di ~60 sorgenti backend, ~20 file test,
> 24 migrazioni, ~65 file frontend; confronto puntuale con
> `docs/NORMATIVA-PDC.md` e `docs/MODELLO-DATI.md`.
>
> **File letti integralmente**: `builder_pdc/builder.py` (951r),
> `builder_pdc/split_cv.py` (203r), `domain/vincoli/inviolabili.py`
> (390r), `capacity_temporale.py` (161r), `thread_proiezione.py`
> (393r), `sourcing.py`, `models/anagrafica.py` (558r),
> `models/turni_pdc.py`, `models/giri.py`, `api/turni_pdc.py` (683r),
> `auth/dependencies.py`.

---

## Sintesi

| Categoria | Conteggio |
|-----------|----------:|
| **Critici** (bug funzionali, violazioni normativa, debiti bloccanti) | 10 |
| **Importanti** (correttezza, security, performance, test mancanti) | 15 |
| **Minori** (stile, dead code, micro-ottimizzazioni) | 9 |

**Confronto con review 2026-05-01**: tutti i 6 critici e 10 dei 11
importanti della review precedente sono **ancora aperti** (l'unica
eccezione: I10 `_km_media_annua_giro` è stato fixato in Sprint 7.7
MR 5 — ora usa tutte le varianti). Questo documento aggiunge 4 nuovi
critici e 5 nuovi importanti emersi dallo Sprint β2.

**Stato globale**: il codebase è funzionale su dati reali (smoke E2E
β2 superato). I finding critici aperti sono principalmente debiti
accumulati intenzionalmente (preriscaldo, ACC/CV no-overhead, full
table scan), ma tre nuovi trovati nello Sprint β2 meritano priorità
alta: `TurnoPdcGiornata.km=0` (dato mancante in dashboard),
riposo FR senza check minimo 6h (violazione normativa silente), e
`_prima_data_applicabile` che invalida il capacity temporale su
programmi annuali.

---

## CRITICI

### C1 — [RESIDUO da review 2026-05-01 C2] `is_notturno` vs `cap_prestazione`: divergenza formula — BUG FUNZIONALE

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:294-302`
e `builder_pdc/split_cv.py:151-153`

In `_build_giornata_pdc`:

```python
# riga 294
is_notturno = ora_presa < 5 * 60 or ora_fine_servizio > 22 * 60 or ...
# riga 297-301
cap_prestazione = (
    PRESTAZIONE_MAX_NOTTURNO
    if 60 <= ora_presa < 5 * 60   # ← 01:00–04:59
    else PRESTAZIONE_MAX_STANDARD
)
```

In `_eccede_limiti` (split_cv.py:151-153):

```python
cap_prestazione = (
    PRESTAZIONE_MAX_NOTTURNO if draft.is_notturno else PRESTAZIONE_MAX_STANDARD
)
```

**Scenario rotto**: `ora_presa = 0` (mezzanotte esatta).
- `is_notturno`: `0 < 300` → **True**. Flag persistito in `TurnoPdcGiornata.is_notturno`.
- Cap nel builder: `60 <= 0` → **False** → cap STANDARD 510'.
- Cap nello splitter (legge `draft.is_notturno=True`): cap **NOTTURNO 420'**.
- Risultato: una giornata con presa mezzanotte **calcola prestazione con cap 510'** ma
  **lo splitter attiva solo a 420'** → due piani divergenti, split può
  scattare inutilmente; viceversa una giornata `ora_presa=30` (00:30)
  ha `is_notturno=True` ma cap 510' nel validatore → violazione non
  segnalata.

**Normativa**: §11.8 definisce il cap ridotto per presa servizio
`01:00–04:59` (= `60 <= min < 300`). Presa a `00:00` non rientra
nel range — il cap STANDARD è normativo. Il bug è quindi nella
definizione di `is_notturno` che è troppo larga (include anche `< 60`).

**Fix** (3 righe):

```python
def _is_presa_notturna(ora_presa: int) -> bool:
    """Vero se presa servizio cade in 01:00–04:59 (NORMATIVA §11.8)."""
    return 60 <= ora_presa < 300

# In _build_giornata_pdc:
is_notturno_cap = _is_presa_notturna(ora_presa)
cap_prestazione = PRESTAZIONE_MAX_NOTTURNO if is_notturno_cap else PRESTAZIONE_MAX_STANDARD
```

Allineare anche `is_notturno` persistito (separare "turno con orari
notturni" da "turno soggetto al cap 420'") oppure rendere
`is_notturno=is_notturno_cap` per coerenza con lo splitter.

**Costo stima**: 1h (fix + 5 test di boundary: 00:00, 00:59, 01:00,
04:59, 05:00).

---

### C2 — [RESIDUO da review 2026-05-01 C1] Anti-rigenerazione turni PdC: full table scan

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:533-542`

```python
existing = list(
    (await session.execute(
        select(TurnoPdc).where(TurnoPdc.azienda_id == azienda_id)
    )).scalars()
)
legati = [t for t in existing if
    (t.generation_metadata_json or {}).get("giro_materiale_id") == giro_id
]
```

Carica **tutti** i `TurnoPdc` dell'azienda in memoria per filtrare via
JSON. Con N programmi × M giri × K varianti la query diventa proibitiva.
Fix: aggiungere colonna FK `turno_pdc.giro_materiale_id` (migration
analoga alla 0010 già fatta per `giro_materiale.programma_id`).

**Costo stima**: 2–3h. Vedere fix completo in review 2026-05-01 C1.

---

### C3 — [RESIDUO da review 2026-05-01 C3] FK `programma_id` introdotta ma mai usata nel builder

**File**: `backend/src/colazione/domain/builder_giro/builder.py:269-321`

La migration 0010 ha aggiunto `giro_materiale.programma_id` con indice +
FK `ondelete=CASCADE`. Il builder usa ancora query `text(...)` su
`generation_metadata_json->>'programma_id'`, vanificando indice e
CASCADE. Fix: refactor a ORM con `GiroMateriale.programma_id`.

**Costo stima**: 1h. Vedere fix in review 2026-05-01 C3.

---

### C4 — [RESIDUO da review 2026-05-01 C4] Preriscaldo ACCp 80' dic-feb non implementato

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:52, 178, 207`

`ACCESSORI_MIN_STANDARD = 40` usato per tutti i mesi. In dicembre-
febbraio (escluso Fiorenza, NORMATIVA §3.3 + §8.5) l'ACCp deve essere
80'. Il campo `TurnoPdcBlocco.is_accessori_maggiorati` esiste ma è
sempre `False`. In inverno la prestazione è sottostimata di 40' →
cap sforato silenziosamente.

**Costo stima**: 4–6h + decisione utente su worst-case vs stagionale.

---

### C5 — [RESIDUO da review 2026-05-01 C5] Gap fra blocchi classificato sempre PK

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:215-233`

Ogni gap > 0 fra blocchi consecutivi diventa `PK`. Non è modellato
né `ACC` (gap ≥ 65' → ACCa + ACCp), né `CV` (gap < 65', stazione CV,
scambio tra PdC). Prestazione sovrastimata nei rami post-split per il
costo ACCa+ACCp che in un vero CV no-overhead non si paga. Residuo
dichiarato Sprint 7.4 entry 59, ma ancora bloccante per la correttezza
delle prestazioni calcolate.

**Costo stima**: 1–2 gg. Vedere analisi in review 2026-05-01 C5.

---

### C6 — [RESIDUO da review 2026-05-01 C6] `STAZIONI_CV_DEROGA = {"MORTARA", "TIRANO"}` non verificate nel DB

**File**: `backend/src/colazione/domain/builder_pdc/split_cv.py:59`

Il codice `"TIRANO"` potrebbe non matchare il codice stazione nel DB
reale (potrebbe essere `"S00321"` o simile dopo import PdE). Smoke
Sprint 7.4 verifica MORTARA ma non TIRANO. Se il codice è errato, lo
split CV non si attiva sulla direttrice Valtellina — caso d'uso critico.

**Fix**: query `SELECT codice FROM stazione WHERE nome ILIKE '%TIRANO%'`
sul DB di produzione. Poi: promuovere a regola configurabile per
programma (residuo dichiarato) oppure match per nome invece di codice.

**Costo stima**: 30 min verifica + 1–2h fix.

---

### C7 — **[NUOVO]** `TurnoPdcGiornata.km` sempre 0: km pilotati mai calcolati

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:820`

```python
gg_orm = TurnoPdcGiornata(
    ...
    km=0,  # ← hardcoded, mai calcolato
    ...
)
```

Il campo `TurnoPdcGiornata.km` (colonna `INTEGER`) è progettato per
contenere i chilometri percorsi dal PdC in quella giornata. Il builder
lo lascia sempre a `0`.

**Impatto**: le dashboard `TurniRoute` e `TurnoDettaglioRoute` del
Pianificatore PdC non possono mai mostrare "km condotti per giornata",
che è un KPI rilevante per la pianificazione (bilanciamento carichi,
verifica km mensili PdC). Il dato è disponibile — è la somma dei
`km_tratta` delle corse commerciali coperte dai blocchi `CONDOTTA`.

**Fix**:

```python
# In _build_giornata_pdc, prima del return:
km_giornata = sum(
    b.durata_min  # placeholder — usare km_tratta se disponibile
    for b in drafts if b.tipo_evento == "CONDOTTA" and b.corsa_commerciale_id
)
# Oppure più corretto: sommare direttamente i km_tratta dai GiroBlocco
# corrispondenti ai blocchi CONDOTTA (già nella lista blocchi_validi).
```

Meglio: passare i `km_tratta` dai `GiroBlocco` di input nella
costruzione dei `_BloccoPdcDraft`, poi sommarli in `_GiornataPdcDraft`.

**Costo stima**: 1–2h (propagazione km attraverso i draft + test).

---

### C8 — **[NUOVO]** FR riposo minimo 6h non verificato: violazione normativa §10.5 silente

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:866-938`

`_aggiungi_dormite_fr` calcola `durata_pernotto` (riga 903-906) e la
annota nelle note del blocco `DORMITA` (`riga 919`), ma **non verifica**
che sia ≥ 360 minuti (6 ore minimo NORMATIVA §10.5).

```python
fr_log.append({
    "giornata": curr.numero_giornata,
    "stazione": curr.stazione_inizio,
    "ore": round(durata_pernotto / 60, 1),
})
# ← nessun check su durata_pernotto < 360
```

**Normativa §10.5** (fonte verità):
> "**Minimo operativo**: **6 ore** fra la fine prestazione giorno 1
> e la ripresa servizio giorno 2."

**Scenario concreto**: giro con giornata 1 che finisce alle 23:30 e
giornata 2 che inizia alle 04:30 → `durata_pernotto = (24×60 − 1410)
+ 270 = 30 + 270 = 300 min = 5h` → **sotto il minimo**. Il turno
viene persistito senza violazione segnalata.

**Fix**:

```python
if durata_pernotto < 360:  # NORMATIVA §10.5
    curr.violazioni.append(
        f"fr_riposo_minimo:{durata_pernotto}min<360min"
    )
```

Aggiungere anche la verifica a livello di ciclo nel metadata
`generation_metadata_json.violazioni` (come già fatto per prestazione
e condotta).

**Costo stima**: 30 min + 2 test (riposo < 6h, riposo ≥ 6h).

---

### C9 — **[NUOVO]** `RegolaInvioSosta`: schema + API CRUD completi, builder la ignora — half-job §10.7

**File**:
- Schema: `backend/src/colazione/models/anagrafica.py:284-338`
- API: `backend/src/colazione/api/anagrafiche.py` (`POST/GET/DELETE
  /api/programmi/{id}/regole-invio-sosta`)
- Builder sourcing: `backend/src/colazione/domain/builder_giro/sourcing.py`

Sprint β2-7 (entry 137) ha costruito schema + CRUD API per
`RegolaInvioSosta`. Il builder (`arricchisci_sourcing`) ignora
completamente queste regole e usa solo il fallback "deposito sede"
per popolare `dest_descrizione` degli sganci.

**Impatto**: il pianificatore può configurare "ETR421 sganciato a
Garibaldi 06:00–19:00 → Milano San Rocco" ma questa regola non viene
mai consultata. La decisione di sourcing in produzione è sempre
sbagliata per sganci che dovrebbero andare a una `LocalitaSosta` invece
del deposito sede.

**Stato dichiarato**: entry 137 li marca come scope `β2-7 v2`.
Tuttavia, avere schema + API funzionanti ma algoritmo che non le usa
è una half-feature per definizione (CLAUDE.md §7).

**Test del residuo** (CLAUDE.md §7):
1. Scrivibile in < 2h? No — richiede integrazione sourcing + logica
   finestra oraria + test di integrazione.
2. Richiede decisione utente? Parzialmente — la logica è definita,
   manca l'implementazione.
3. Migration grande? No — schema già fatto.

→ **Il residuo è legittimo per ora**, ma deve essere tracciato
esplicitamente in TN-UPDATE con stima effort, altrimenti si
accumula silente.

**Fix** (quando schedulato):

```python
# In arricchisci_sourcing, dove ora c'è solo fallback:
regola = await _trova_regola_invio_sosta(
    session, programma_id, stazione_sgancio, tipo_materiale, ora_sgancio
)
if regola:
    dest_descrizione = f"Pezzi a sosta {regola.localita_sosta.codice}"
else:
    dest_descrizione = f"Pezzi a deposito {localita_sede.codice_breve}"
```

---

### C10 — **[NUOVO]** `_prima_data_applicabile`: capacity temporale valida solo per il primo giorno del cluster

**File**: `backend/src/colazione/domain/builder_giro/thread_proiezione.py:352-370`

```python
def _prima_data_applicabile(variante: GiroVariante) -> date_t | None:
    """...Prima data del cluster A1..."""
    dates = variante.dates_apply_json or []
    ...
    return date_t.fromisoformat(dates[0])  # ← SOLO la prima
```

Ogni evento `MaterialeThreadEvento` riceve `data_giorno = prima_data_del_cluster`.
Per un cluster annuale con 200 date, tutti gli eventi risultano datati
al giorno 1. `verifica_capacity_temporale` (capacity_temporale.py:133-141)
aggrega per `(data_giorno, materiale)` → il check è **significativo
solo per il primo giorno del cluster**, non per i successivi.

**Impatto concreto**: un programma con 644 run che funziona da dicembre
a dicembre produrrà un unico picco fittizio su una data (la prima di
ogni cluster) e zero warning per tutti gli altri 200+ giorni reali di
servizio. Il capacity check temporale è **essenzialmente inutile per
programmi annuali**.

**Normativa**: questo invalida il proposito del check (NORMATIVA implicita:
la dotazione fisica è una risorsa che si esaurisce ogni singolo giorno di
esercizio, non solo il primo).

**Stato dichiarato**: entry 137 limitazione 2, entry 135 docstring.
Ma l'impatto non è dichiarato esplicitamente come "il check non copre
i giorni reali".

**Fix** (sprint successivo):

```python
# In proietta_thread_giro, per ogni blocco:
for data in variante.dates_apply_json:  # ← tutte le date
    evento = MaterialeThreadEvento(
        ...
        data_giorno=date_t.fromisoformat(data),
        ...
    )
    session.add(evento)
```

Richiede rifactoring del persister del thread (oggi crea 1 evento per
blocco, non N eventi per N date). Alternativa più leggera: tabella
separata `materiale_thread_date_applicazione` per il calendario senza
duplicare gli eventi.

**Costo stima**: 2–3gg (architetturale). Residuo bloccante per
l'utilità reale del capacity temporale in produzione.

---

## IMPORTANTI

### I1–I9, I11 — [RESIDUI da review 2026-05-01]

I seguenti 10 finding della review 2026-05-01 sono **ancora tutti aperti**:

| ID | Descrizione | File:riga |
|----|-------------|-----------|
| **I1** | `datetime.utcnow()` deprecato Python 3.12+ | `builder_pdc/builder.py:797` |
| **I2** | `assert` per type narrowing (disabilitato con `-O`) | `builder_pdc/builder.py:173,216,219` |
| **I3** | JWT access token TTL 72h (standard industriale: 15 min) | `config.py:39` |
| **I4** | `TurnoPdc.impianto = giro.tipo_materiale` semantica errata | `builder_pdc/builder.py:807` |
| **I5** | `updated_at` senza `onupdate=func.now()` su 3+ tabelle | `models/turni_pdc.py:48`, `models/giri.py:68` |
| **I6** | Filtro pool catene con `giorno_tipo='feriale'` hardcoded | `builder_giro/builder.py:506-509` |
| **I7** | `_aggiungi_dormite_fr` muta `curr.blocchi` in-place | `builder_pdc/builder.py:879-952` |
| **I8** | `_inserisci_refezione`, `_aggiungi_dormite_fr`, `_persisti_un_turno_pdc` senza test unitari | `tests/` (0 test su questi 3 helper) |
| **I9** | `_count_giri_esistenti` + `_wipe_giri_programma` query JSON duplicata 3× | `builder_giro/builder.py:269-321` |
| **I11** | `_next_numero_rientro_sede` race condition SELECT MAX → +1 | `builder_giro/persister.py:267-273` |

Fix proposti dettagliati in `docs/CODE-REVIEW-2026-05-01.md` per ognuno.

---

### I12 — **[NUOVO]** `verifica_capacity_temporale`: query SQL carica tutti gli eventi senza filtro tipo

**File**: `backend/src/colazione/domain/builder_giro/capacity_temporale.py:117-130`

```python
stmt = (
    select(
        MaterialeThreadEvento.thread_id,
        MaterialeThreadEvento.tipo,
        MaterialeThreadEvento.data_giorno,
        MaterialeThread.tipo_materiale_codice,
    )
    .join(MaterialeThread, ...)
    .where(MaterialeThread.azienda_id == azienda_id)
    # ← nessun filtro su tipo evento
)
rows = (await session.execute(stmt)).all()
```

La query carica **tutti** gli eventi di **tutti** i thread dell'azienda
(tipi inclusi: `sosta_in_stazione`, `aggancio`, `sgancio`, `uscita/
rientro_deposito`, `corsa_*`), poi filtra in Python con:

```python
if row.tipo not in _TIPI_IN_USO:
    continue
```

Con un'azienda reale (644 run × ~20 eventi per thread × N thread per
run), questo può portare decine di migliaia di righe in memoria solo
per scartarne la metà.

**Fix** (1 riga):

```python
.where(
    MaterialeThread.azienda_id == azienda_id,
    MaterialeThreadEvento.tipo.in_(list(_TIPI_IN_USO)),  # ← aggiunta
)
```

**Costo stima**: 15 min.

---

### I13 — **[NUOVO]** Limiti FR settimanali non enforced: normativa §10.6 ignorata

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:883`

```python
# Limiti settimanali (max 1/sett, max 3/28gg) NON enforced nel MVP.
```

**Normativa §10.6**:
> "Per PdC: massimo **1 FR per settimana**. Massimo **3 FR in 28 giorni**."

Il builder `_aggiungi_dormite_fr` aggiunge dormite FR senza verificare
questi limiti. Un giro con 5 giornate consecutive in stazioni diverse
potrebbe produrre 4 FR senza alcuna violazione segnalata.

**Impatto**: i turni PdC prodotti non rispettano i vincoli contrattuali
mensili. Un pianificatore che usa i turni generati come base rischia
di avere turni illeciti che passano la validazione automatica.

**Nota**: il limite settimanale (§10.6) è diverso dal riposo minimo 6h
(§10.5 — finding C8). Entrambi mancano.

**Fix**: in `_aggiungi_dormite_fr`, contare i FR già registrati nel
ciclo e limitare a 1 per settimana / 3 per 28gg:

```python
fr_count = len(fr_log)
if fr_count >= 3:  # hard limit 3/28gg
    # non aggiungere FR, aggiungere violazione
    curr.violazioni.append("fr_limite_28gg:superato")
    continue
```

Per il limite settimanale serve sapere il numero di giorno nel ciclo —
già disponibile via `numero_giornata`.

**Costo stima**: 1h + test.

---

### I14 — **[NUOVO]** Thread proiezione solo su variante canonica: under-counting strutturale

**File**: `backend/src/colazione/domain/builder_giro/thread_proiezione.py:64-94`

```python
async def _carica_blocchi_variante_canonica(giro_id: int, session):
    ...
    .where(GiroVariante.variant_index == 0)  # ← solo canonica
```

La proiezione thread considera **solo la variante canonica
(`variant_index=0`)** per ogni giornata. Giri con varianti A2
(giornata-tipo che ha sequenze diverse in certi periodi dell'anno)
producono thread incompleti: le corse delle varianti non-canoniche non
appaiono nella timeline del thread.

**Impatto** (doppio):
1. `MaterialeThread.km_totali` sotto-stimato per giri con varianti.
2. `verifica_capacity_temporale` — già penalizzato da C10 — risulta
   ulteriormente impreciso perché mancano eventi di varianti non-canoniche.

**Stato dichiarato**: entry 137 limitazione 1.

**Fix** (sprint successivo): proiettare un thread per variante, o
unificare eventi di tutte le varianti con tag `variante_index` e
aggiornare il capacity check per gestire date variante-specifiche.

**Costo stima**: 2–4h (dipende dalla decisione modello).

---

### I15 — **[NUOVO]** `Stazione` PK solo `codice`: crack multi-tenancy latente

**File**: `backend/src/colazione/models/anagrafica.py:43-54`

```python
class Stazione(Base):
    __tablename__ = "stazione"
    codice: Mapped[str] = mapped_column(String(20), primary_key=True)
    ...
    azienda_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("azienda.id", ondelete="RESTRICT")
    )
```

`codice` è PK senza `azienda_id`. La tabella `stazione` è quindi
**globale**: tutte le aziende condividono lo stesso spazio dei codici.
Un'azienda non può registrare una stazione con lo stesso codice di
un'altra.

**Problema per multi-tenancy**: TILO/SAD potrebbero usare codici
stazione diversi per le stesse stazioni fisiche (es. "LUGANO-CFF"
vs "LUGANO-RFI"), o avere stazioni locali con codici che collidono
con quelli Trenord.

**Impatto immediato**: la migration 0002 (seed Trenord) inserisce
stazioni con `azienda_id=1`. Se si aggiunge SAD in futuro, i codici
Trenord sono già occupati — le sue stazioni sovrapponentisi sarebbero
rifiutate dal PK.

**Fix strutturale** (non urgente per MVP mono-tenant):

```sql
ALTER TABLE stazione DROP CONSTRAINT stazione_pkey;
ALTER TABLE stazione ADD PRIMARY KEY (azienda_id, codice);
```

Tutte le FK verso `stazione.codice` dovranno diventare FK composite
verso `(azienda_id, codice)`. È una migration invasiva: da pianificare
prima del secondo tenant, non dopo.

**Costo stima**: 2–3gg (migration + cascata FK).

---

### I16 — **[NUOVO residuo β2]** `arricchisci_sourcing` non consulta `RegolaInvioSosta` — sourcing sempre fallback deposito

Già citato in C9 come critico per la completezza funzionale. Ripetuto
qui come "importante" perché ha una componente di test coverage: non
esiste nessun test su `sourcing.py` che verifichi il caso "regola
trovata → usa localita_sosta invece di deposito".

**File**: `backend/tests/test_sourcing.py` (verificare copertura).

**Fix parziale ora**: aggiungere test con `RegolaInvioSosta` in DB di
test + mock di `arricchisci_sourcing` che verifica il fallback. Anche
prima di implementare la logica reale, il test documenterebbe il
comportamento atteso.

---

## MINORI

### M1–M7 — [RESIDUI da review 2026-05-01]

I 7 minori della review precedente sono ancora aperti:

| ID | Descrizione | File:riga |
|----|-------------|-----------|
| **M1** | `domain/normativa/__init__.py` vuoto — package fantasma | `domain/normativa/__init__.py:1` |
| **M2** | Dead code: moduli `revisioni` importati ma inutilizzati | `models/revisioni.py`, `domain/revisioni/__init__.py` |
| **M3** | `ciclo_giorni = max(1, min(14, ...))` cap 14 senza commento | `builder_pdc/builder.py:809` |
| **M4** | `_genera_codice_turno` taglia `numero_turno` a 48 char silentemente | `builder_pdc/builder.py:958` |
| **M5** | Smoke scripts lasciano dati in DB (no `--cleanup` flag) | `scripts/smoke_74_split_cv.py` ecc. |
| **M6** | `require_role(role: str)`: typo non catturato da mypy | `auth/dependencies.py:66` |
| **M7** | Refresh token senza revoca server-side (stateless, valido 30gg) | `auth/tokens.py:62-76` |

---

### M8 — **[NUOVO]** `MaterialeThread.programma_id` ridondante: denormalizzazione evitabile

**File**: `backend/src/colazione/models/anagrafica.py:383-385`

`MaterialeThread` ha sia `programma_id` (FK diretto) sia
`giro_materiale_id_origine` (FK al giro che, post migration 0010, ha
già `programma_id NOT NULL`). La `programma_id` sul thread è
derivabile tramite join: `thread → giro_materiale → programma_id`.

La denormalizzazione crea un potenziale update anomaly: se il giro
viene spostato di programma (caso teoricamente impossibile per le FK,
ma se si dovesse fare un refactor) i due valori potrebbero divergere.

**Fix**: eliminare `MaterialeThread.programma_id` (migration DROP
COLUMN) e derivare sempre via join. Se si ha bisogno di query rapide
per programma, aggiungere un indice su
`giro_materiale.programma_id` (già c'è da migration 0010).

**Costo stima**: 45 min + migration.

---

### M9 — **[NUOVO]** `LocalitaManutenzioneDotazione.updated_at` manca `onupdate`

**File**: `backend/src/colazione/models/anagrafica.py:114`

```python
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), server_default=func.now()
)
```

Come il già-noto I5 di turni_pdc e giri, manca `onupdate=func.now()`.
Quando la dotazione viene aggiornata (es. "ridotta ETR421 da 44 a 12
per smoke test"), `updated_at` rimane uguale a `created_at`. La
dashboard Manutenzione non sa quando la dotazione è stata modificata
l'ultima volta.

**Fix**: `onupdate=func.now()` (1 riga + migration `ALTER TABLE`).

---

### M10 — **[NUOVO]** Smoke scripts β2 non cleanup, non parametrizzati: re-run fallisce

**File**: `backend/scripts/` (tutti gli smoke_*)

I nuovi smoke script `smoke_56_cremona.py`, `smoke_56_tirano.py`,
`smoke_75_bug5_chiuso.py` non hanno la flag `--cleanup` che M5 già
segnalava per `smoke_74_split_cv.py`. Al secondo run, o trovano dati
preesistenti (409 Conflict), o creano duplicati se il check non c'è.

Soluzione standard per tutti: seed con `codice_fisso = "SMOKE_TEST_*"`
+ `DELETE WHERE codice LIKE 'SMOKE_TEST%'` all'inizio e/o alla fine
del run.

**Costo stima**: 30 min (pattern unico applicato a tutti gli smoke).

---

## VERIFICHE NEGATIVE (cose cercate e NON trovate)

- **SQL injection**: tutto via ORM SQLAlchemy con bound parameters. I
  due `text(...)` residui (C3, I11) usano `:param` binding. ✅
- **XSS frontend**: React + escape automatico, nessun
  `dangerouslySetInnerHTML`. ✅
- **Credenziali hardcoded**: `jwt_secret` ha default debole ma solo
  in `config.py` con documentazione esplicita. ✅
- **FK `ondelete` incoerenti**: tutti i FK post-β2 hanno `ondelete`
  esplicito e semanticamente coerente (`CASCADE` sui figli di
  `programma_id`, `RESTRICT` sulle corse, `SET NULL` sulle cose
  opzionali). `RegolaInvioSosta.programma_id` correttamente `CASCADE`. ✅
- **Race condition nuove**: `genera_turno_pdc` è single-session.
  `verifica_capacity_temporale` è read-only. ✅ (I11 già noto è
  l'unica race non risolta.)
- **Memory leak / N+1**: query batch corrette in `verifica_capacity_temporale`,
  `proietta_thread_giro`, `get_turno_pdc_dettaglio`. Nessun lazy load
  evidente. ✅ (I12 è solo mancanza di filtro SQL, non N+1.)
- **Fix hotfix β2-5 corretto**: `MaterialeThread.azienda_id` usato
  al posto di `programma_id` in capacity_temporale. ✅ La logica
  post-fix è corretta per il caso smoke (unico programma per azienda);
  il limite strutturale è C10 (data_giorno = prima data del cluster).
- **Violazioni FK sul modello β2**: `MaterialeThread` e
  `MaterialeThreadEvento` hanno FK corrette verso `giro_materiale`,
  `programma_materiale`, `giro_blocco`, `stazione`. ✅
- **UniqueConstraint `uq_thread_evento_ordine`** su `(thread_id,
  ordine)`: garantisce serialità della timeline per thread. ✅

---

## Riepilogo priorità di chiusura

**Chiudi subito (< 2h):**

- C8 (FR riposo 6h min) — 30 min + test
- I12 (filtro SQL capacity_temporale) — 15 min
- M9 (onupdate dotazione) — 30 min + migration

**Chiudi con decisione utente:**

- C1 (cap notturno boundary — conferma formula 01:00–04:59)
- C6 (codice TIRANO nel DB — verifica empirica)
- C7 (km giornata — come propagare km_tratta attraverso i draft)
- I13 (FR limiti settimanali — encoding nel ciclo)

**Strutturali grandi (1+ gg):**

- C2, C3 (FK refactor — migration analoga a 0010): 2–3h
- C4 (preriscaldo dic-feb): 4–6h + decisione modello stagionale
- C5 (ACC/CV no-overhead): 1–2gg
- C10 + I14 (capacity temporale su tutte le date + varianti): 2–4gg
  — BLOCCANTE per rendere il capacity check utile in produzione
- I15 (Stazione PK multi-tenant): 2–3gg, prima del secondo tenant

**Non chiudere ora (residui legittimi documentati):**

- C9 (RegolaInvioSosta builder): scope β2-7 v2
- M2 (revisioni dead code): scope futuro v1
- M6, M7 (auth hardening): post-MVP
- M8 (denormalizzazione programma_id thread): cosmetic

---

## Note metodologiche

- Review eseguita secondo CLAUDE.md + METODO-DI-LAVORO.md: lettura
  diretta dei file prima di ogni affermazione, file:riga per ogni
  finding, niente supposizioni.
- Coerenza con NORMATIVA-PDC verificata su: cap notturno §11.8
  (C1), preriscaldo §3.3 + §8.5 (C4), gap CV/ACC/PK §6 (C5),
  stazioni CV §9.2 (C6), FR riposo minimo §10.5 (C8), FR limiti
  settimanali §10.6 (I13).
- `I10 _km_media_annua_giro`: **CHIUSO** — Sprint 7.7 MR 5 ha
  refactored la funzione per usare tutte le varianti (non solo la prima
  corsa). Unico finding della review 2026-05-01 risolto.
- Scope Sprint β2 analizzato: `capacity_temporale.py` (C10, I12),
  `thread_proiezione.py` (I14, C10), `sourcing.py` (C9), `anagrafica.py`
  β2-4 e β2-7 (M8, M9), `builder_pdc/builder.py` FR section (C8, I13).
- Fausto (grok-code-fast-1) non consultato in questa pass: context
  di sessione è esteso, i finding sono tutti tracciabili con lettura
  diretta senza second opinion necessaria per questa review.
