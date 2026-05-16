# Code Review — COLAZIONE Sprint 8.3/8.4

**Data**: 2026-05-16  
**Reviewer**: NINO (Claude Code, sesisone zen-babbage-Hwt1g)  
**Sprint corrente**: 8.3 backlog cleanup (8.4 in corso)  
**Scope**: backend/, alembic/, domain/, tests/ — cenni a frontend  
**Metodo**: lettura diretta file per file, confronto sistematico con NORMATIVA-PDC.md e MODELLO-DATI.md  

---

## Riepilogo

| Gravità | N | Area principale |
|---|---|---|
| CRITICO | 6 | Normativa, bug silenzioso DB, CI rotta |
| IMPORTANTE | 9 | Architettura, performance, normativa secondaria |
| MINORE | 5 | Style, placeholder stantii, cosmesi |

**Total: 20 finding.**

---

## CRITICI

### C1 · Violazione normativa §3.3 — ACCp preriscaldo (80') mai implementato

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:57`  
**File**: `backend/src/colazione/domain/builder_pdc/builder.py:1103`

```python
# builder.py:57
ACCESSORI_MIN_STANDARD = 40  # unico valore usato ovunque

# builder.py:1103 — nel persister
is_accessori_maggiorati=False,  # sempre, hardcoded
```

La NORMATIVA-PDC §3.3 prescrive:

| Caso | ACCp | ACCa |
|---|---|---|
| Condotta standard | 40' | 40' |
| Condotta con preriscaldo ● (dic-feb) | **80'** | 40' |

Il campo `is_accessori_maggiorati` esiste nel modello (`TurnoPdcBlocco.is_accessori_maggiorati: bool`, migration 0045) e nello schema response (`turni_pdc.py:185`), ma il builder lo imposta **sempre** a `False` e non calcola mai gli 80' per il mese del turno.

**Impatto**: ogni turno generato in dic-gen-feb ha una presa servizio 40 minuti troppo tardi. Il PdC inizierebbe gli accessori a T-40' invece di T-80', con una preparazione materialmente impossibile da completare in tempo. La normativa viene sistematicamente violata per circa 3 mesi all'anno.

**Fix**:
```python
# In _build_giornata_pdc, passare la data operativa:
def _build_giornata_pdc(
    numero_giornata: int,
    variante_calendario: str,
    blocchi_giro: list[GiroBlocco],
    data_operativa: date | None = None,  # aggiungere
) -> _GiornataPdcDraft | None:
    mese = data_operativa.month if data_operativa else None
    preriscaldo = mese in (12, 1, 2) if mese is not None else False
    accp_min = 80 if preriscaldo else ACCESSORI_MIN_STANDARD
    # ... usare accp_min per ora_inizio_accp
    # ... impostare is_accessori_maggiorati=preriscaldo nel blocco ACCp
```

---

### C2 · Bug normativo §4.4 — PK generato per qualsiasi gap > 0' (minimo reale: 40')

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:258`

```python
# builder.py:258
gap = _diff(prec.ora_fine, b.ora_inizio)
if gap > 0:
    drafts.append(_BloccoPdcDraft(tipo_evento="PK", durata_min=gap, ...))
```

La NORMATIVA-PDC §4.4 specifica:

> PK in arrivo: **20' minimo**  
> PK in partenza: **20' minimo**

Un PK minimo richiede 20'+20' = 40' totali. Il builder genera un "PK" di 1 minuto, 5 minuti, 15 minuti quando il gap tra condotte consecutive è inferiore a questa soglia. Questi blocchi non corrispondono a nessuna operazione fisicamente eseguibile dal PdC: non c'è tempo per mettere in sicurezza il mezzo e riprenderlo.

§6 chiarisce poi che un gap < 65' può essere CV o PK — ma entrambi richiedono tempo fisico (40' per PK, tempo di CV variabile). Un gap di 5 minuti non può essere risolto con nessuna delle modalità normative.

**Impatto**: turni generati contengono blocchi PK irreali che rendono il turno schedulatoriamente impossibile. La validazione §4.4 non viene mai sollevata come violazione.

**Fix**:
```python
# Classificazione corretta del gap:
PK_MIN_TOTALE = 40   # 20' arrivo + 20' partenza

if gap >= PK_MIN_TOTALE:
    drafts.append(_BloccoPdcDraft(tipo_evento="PK", durata_min=gap, ...))
elif gap > 0:
    # gap troppo breve per PK o ACC: potenziale CV se stazione ammessa
    # Per ora: segnala violazione invece di generare PK fantasma
    violazioni.append(f"gap_troppo_breve_per_pk_o_acc:{gap}min_tra_blocco_{i-1}_e_{i}")
```

---

### C3 · Violazione normativa §4.1 — REFEZ ai bordi può sforare la finestra

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:541`

```python
# builder.py:541
if ultimo_blocco is not None and _in_finestra(ora_fine_servizio % (24 * 60)):
    nuovo_ora_fine = (ora_fine_servizio + REFEZIONE_MIN_DURATA) % (24 * 60)
    refez = _BloccoPdcDraft(
        tipo_evento="REFEZ",
        ora_inizio=_from_min(ora_fine_servizio),
        ora_fine=_from_min(nuovo_ora_fine),
        ...
    )
```

`_in_finestra` controlla solo che `ora_fine_servizio` sia dentro la finestra (es. ≤ 22:30). Ma la REFEZ dura 30 minuti: se `ora_fine_servizio = 22:29`, la REFEZ va da 22:29 a 22:59. Solo 1 minuto cade nella finestra `[18:30, 22:30)`. La normativa §4.1 richiede che la REFEZ sia **dentro** la finestra, non solo che inizi dentro.

**Impatto**: turni con REFEZ inserita a 22:01-22:30 (fine servizio) escono parzialmente dalla finestra normativa. I 20-29 minuti fuori finestra sono tecnicamente una violazione contrattuale.

**Fix**:
```python
def _in_finestra(t: int) -> bool:
    # Verifica che la REFEZ (30') cada COMPLETAMENTE nella finestra
    return any(fa <= t and (t + REFEZIONE_MIN_DURATA) <= fb for fa, fb in REFEZIONE_FINESTRE)
```

---

### C4 · Violazione normativa §4.1 — REFEZ mancante non causa scarto del turno

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:368`  
**File**: `backend/src/colazione/domain/builder_pdc/deposito_first.py:293-298`

```python
# builder.py:368 — segnala ma non scarta
if prestazione_min > REFEZIONE_SOGLIA_MIN and refezione_min == 0:
    violazioni.append("refezione_mancante")
# Il turno viene costruito e ritornato comunque.

# deposito_first.py:293-298 — solo condotta e prestazione come HARD
if draft.condotta_min > CONDOTTA_MAX_MIN:
    return None, [...]   # ← HARD
# REFEZ mancante non è mai HARD, nemmeno nel builder deposito-first.
```

La NORMATIVA-PDC §4.1 prescrive esplicitamente:

> "Se non trova slot compatibili (gap ≥ 30' in finestra), il candidato turno è **scartato** per violazione di normativa."

Il builder MVP segnala la violazione in `violazioni` ma non scarica il turno. Questo è "lax" rispetto alla normativa: turni con `refezione_mancante` vengono persistiti in DB e visualizzati all'utente come generati.

**Impatto**: un pianificatore che genera e poi approva senza rileggere le violazioni produce turni illegali per i contratti PdC.

**Fix in `deposito_first.py`**:
```python
# Dopo step 1 (_build_giornata_pdc):
if draft.refezione_min == 0 and draft.prestazione_min > REFEZIONE_SOGLIA_MIN:
    return None, [
        f"giornata{numero_giornata}: refezione_mancante_hard "
        f"(prestazione {draft.prestazione_min}>{REFEZIONE_SOGLIA_MIN}min, §4.1)"
    ]
```

---

### C5 · Bug silenzioso DB — `updated_at` non si aggiorna sulle UPDATE

**File**: `backend/src/colazione/models/giri.py:79`  
**File**: `backend/src/colazione/models/turni_pdc.py:59`  
**File**: `backend/src/colazione/models/programmi.py:187`

```python
# In tutti e tre i modelli:
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now()   # ← solo INSERT, non UPDATE
)
```

`server_default` in SQLAlchemy si applica **esclusivamente** all'INSERT iniziale. Le righe aggiornate successivamente mantengono il valore originale di `updated_at` come se non fossero mai cambiate.

Questo non è stato rilevato probabilmente perché nessuna query filtra su `updated_at > ?` ancora, ma è una bomba silenziosa: quando arriverà il ruolo "Gestione Personale" o qualsiasi funzionalità di "ultima modifica", i dati saranno storicamente sbagliati e irrecuperabili.

**Impatto**: ogni turno PdC e ogni giro materiale mostra `updated_at = created_at` indipendentemente da quante volte è stato modificato.

**Fix**: aggiungere trigger PostgreSQL `BEFORE UPDATE` o usare SQLAlchemy `onupdate`:
```python
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
    onupdate=func.now(),    # ← aggiungere
)
```
Nota: `onupdate=func.now()` in SQLAlchemy ORM gestisce solo le UPDATE fatte via ORM session. Per aggiornamenti via query diretta SQL (Alembic data migrations, script di admin), serve un trigger PostgreSQL:
```sql
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ language 'plpgsql';

CREATE TRIGGER update_giro_materiale_updated_at
  BEFORE UPDATE ON giro_materiale
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
-- analogo per turno_pdc, programma_materiale
```

---

### C6 · 50 test falliti su master — CI rotta, nessun tracking

**Fonte**: TN-UPDATE entry 301: "⚠️ pytest full backend: 50 fallimenti pre-esistenti su `master` (verificato via `git stash` → stessi fail). Non sono regressioni di questo fix. Backlog."

Non è stato eseguito `pytest` in questo ambiente (modulo mancante), ma il dato è documentato nel diario operativo. Il problema non è che ci sono 50 failure — è che:

1. Non c'è un elenco di quali 50 test falliscono.
2. Non c'è un issue/task che li traccia.
3. Non c'è una strategia dichiarata (xfail, skip motivato, fix pianificato).
4. Il pattern TN-UPDATE "non sono mie regressioni → backlog" è stato ripetuto in almeno 3 entry consecutive senza chiudere.

**Impatto**: la test suite non garantisce nessuna proprietà di correttezza sui 50 casi falliti. Ogni PR che tocca quelle aree non ha safety net. In un codebase di dominio normativo (8h30, REFEZ obbligatoria, riposo 62h) questo è rischioso.

**Fix**: eseguire `pytest --tb=short -q 2>&1 | grep FAILED | head -60`, classificare i failure in:
- `xfail` con motivazione esplicita se il comportamento atteso non è ancora implementato
- Fix prioritario se è un bug nel codice di produzione
- `skip` con reason se richiede infrastruttura non disponibile in CI

---

## IMPORTANTI

### I1 · VOCTAXI_DURATA_DEFAULT_MIN = 30 fisso per tutti i depositi, inclusi periferici

**File**: `backend/src/colazione/domain/builder_pdc/vettura_resolver.py:97-103`

```python
#: Tempo VOCTAXI forfettario (taxi). Stima conservativa per Milano e
#: provincia immediata. Per depositi periferici (Sondrio, Cremona,
#: ecc.) il tempo reale può essere maggiore — il resolver lo stima
#: all'interno della finestra accettabile, lasciando al builder la
#: validazione del cap prestazione finale.
VOCTAXI_DURATA_DEFAULT_MIN: int = 30
```

Il commento **ammette** che la stima è sbagliata per i depositi periferici, ma non risolve il problema. Un taxi da Tirano al deposito SONDRIO non dura 30 minuti; da Cremona centro al deposito CREMONA potrebbe avvicinarsi, ma il resolver usa 30' per tutti i 25 depositi.

**Impatto**: il builder accetta turni con rientro VOCTAXI che stimano 30 minuti ma fisicamente ne richiedono 60-90. La validazione del cap 8h30 viene superata con un margine falso. Quando il pianificatore approva quel turno, il PdC risulta "dentro il cap" ma è nella realtà a 9h00+.

**Fix**: mappa minima per depositi lontani da Milano:
```python
VOCTAXI_DURATA_PER_DEPOSITO: dict[str, int] = {
    "SONDRIO": 60,
    "TIRANO": 60,   # da stazione al deposito SONDRIO
    "COLICO": 45,
    "CREMONA": 25,
    "MANTOVA": 35,
    "VERONA": 45,
    "PIACENZA": 30,
    # ... altri
}
def _voctaxi_durata(deposito_codice: str) -> int:
    return VOCTAXI_DURATA_PER_DEPOSITO.get(deposito_codice, VOCTAXI_DURATA_DEFAULT_MIN)
```
I valori precisi vanno concordati con l'utente — anche approssimazioni operative (±10') sono preferibili al 30' universale.

---

### I2 · `giornata_base.py` — pseudo-refactor che espone ancora simboli privati

**File**: `backend/src/colazione/domain/builder_pdc/giornata_base.py:31-72`

```python
# giornata_base.py
from colazione.domain.builder_pdc.builder import (
    _BloccoPdcDraft,   # ← import simbolo privato (underscore)
    _GiornataPdcDraft, # ← idem
    _build_giornata_pdc,  # ← idem
    ...
)
# Re-export come alias:
BloccoPdcDraft = _BloccoPdcDraft    # ← alias, non spostamento
build_giornata_pdc = _build_giornata_pdc
```

Il "refactor SEVERO S2 HIGH" intendeva risolvere che `deposito_first`, `multi_turno`, `split_cv` importavano simboli `_xxx` privati da `builder.py`. Il risultato è che ora i moduli consumatori importano da `giornata_base.py`, ma `giornata_base.py` stesso importa ancora da `builder.py` tramite i simboli `_xxx` — le DEFINIZIONI sono ancora private e nei posti sbagliati.

Se domani qualcuno rinomina `_BloccoPdcDraft` in `_BozzaBlocco` in `builder.py`, il test di `giornata_base.py` non rileva nulla di diverso — e `deposito_first.py` si rompe con ImportError.

**Fix effettivo**: spostare le DEFINIZIONI di `_BloccoPdcDraft`, `_GiornataPdcDraft`, le costanti normative e gli helper temporali (`_t`, `_from_min`, `_diff`) in un modulo `backend/src/colazione/domain/builder_pdc/primitives.py` (niente underscore). Poi fare fare `builder.py` importare da lì. `giornata_base.py` diventa il re-export del nuovo modulo pubblico. Nessun simbolo privato attraversa moduli.

---

### I3 · Query `from_db` registro vetture senza indice su `generation_metadata_json`

**File**: `backend/src/colazione/domain/builder_pdc/registro_vetture.py:194-226`

```python
turni_ids_subq = (
    select(TurnoPdc.id)
    .where(
        cast(
            func.jsonb_extract_path_text(
                TurnoPdc.generation_metadata_json, "giro_materiale_id"
            ),
            Integer,
        ).in_(giri_ids_subq)
    )
    .scalar_subquery()
)
```

Non esiste nessun indice su `turno_pdc.generation_metadata_json` (né GIN né funzionale). Ogni invocazione del builder deposito-first fa una full sequential scan sulla tabella `turno_pdc` per recuperare il registro vetture. Con 100 giri × 5 giornate × 3 varianti = 1500 turni PdC, questa query comincia a pesare.

**Fix immediato**: aggiungere migration con indice funzionale:
```sql
CREATE INDEX CONCURRENTLY ix_turno_pdc_giro_materiale_id
ON turno_pdc
USING btree (
    cast(jsonb_extract_path_text(generation_metadata_json, 'giro_materiale_id') as integer)
);
```
**Fix strutturale** (migration separata): aggiungere colonna `giro_materiale_id int` su `turno_pdc` (FK esplicita, indicizzata), popolata dal persister. La colonna rende l'intento esplicito e visibile nel modello invece di nascosto nel JSONB.

---

### I4 · `riposo_effettivo_min` assume 1 notte di stacco — invalido per varianti calendariali

**File**: `backend/src/colazione/domain/builder_pdc/riposo_intraturno.py:100-125`

```python
def riposo_effettivo_min(fine_prec: time, inizio_succ: time) -> int:
    # Assume giornate in giorni calendariali CONSECUTIVI (1 notte):
    return (24 * 60 - to_min(fine_prec)) + to_min(inizio_succ)
```

Il docstring stesso avverte: "Assume che le due giornate siano in giorni calendariali consecutivi". Ma un turno con variante G1=`LMXGV` e G2=`S` ha giornate che si materializzano non-consecutive: G1 di venerdì, G2 di sabato (1 notte di stacco ✓) oppure G1 di giovedì, G2 di sabato (2 notti). La formula restituisce lo stesso valore in entrambi i casi.

**Impatto**: la validazione §11.5 (riposo intraturno 11h/14h/16h) è sistematicamente imprecisa per turni con varianti calendariali miste. Una giornata che finisce giovedì sera con G2 il sabato ha 35h di riposo effettivo, ma la formula calcola solo le ore della singola "notte" tra fine e inizio — può risultare 9h e segnalare violazione di §11.5 che non esiste.

**Fix**: la funzione dovrebbe ricevere anche il numero di notti di stacco:
```python
def riposo_effettivo_min(
    fine_prec: time,
    inizio_succ: time,
    notti_stacco: int = 1,  # default backward-compat
) -> int:
    return (24 * 60 * notti_stacco - to_min(fine_prec)) + to_min(inizio_succ)
```
Il chiamante `calcola_e_valida_riposi_intraturno` deve calcolare `notti_stacco` dalla differenza fra le date concrete (richiede `enumera_date_giornata`).

---

### I5 · `_verifica_unicita_intra_turno` segnala falso positivo su split CV legittimo

**File**: `backend/src/colazione/domain/builder_pdc/deposito_first.py:666-710`

```python
def _verifica_unicita_intra_turno(drafts: list[GiornataPdcDraft]) -> list[str]:
    visti_cc: dict[int, str] = {}
    for draft in drafts:
        for blocco in draft.blocchi:
            if blocco.corsa_commerciale_id is not None:
                cci = blocco.corsa_commerciale_id
                if cci in visti_cc:
                    violazioni.append(...)  # ← segnala doppione
```

La NORMATIVA-PDC §15.3 specifica che uno split CV produce due blocchi CONDOTTA sulla stessa `corsa_commerciale_id` (prima metà PdC-A, seconda metà PdC-B) — NON è un doppione normativo: è la definizione di split CV.

Il validatore attuale non distingue tra:
1. Doppione illegale: corsa_commerciale_id appare 2× nello stesso turno senza split CV
2. Split CV legittimo: corsa_commerciale_id appare in due drafts separati con un CVa nel mezzo

**Impatto**: quando il builder multi-turno usa `split_cv`, ogni corsa spezzata genera una violazione `unicita_segmento_corsa_commerciale` fasulla. Il pianificatore deve scartarle manualmente — o peggio, impara a ignorare tutte le violazioni di unicità.

**Fix**: il blocco CONDOTTA post-split deve avere un flag `is_split_cv: bool = False` nella draft, oppure il validatore deve escludere dall'analisi i blocchi adiacenti a un CVa/CVp dichiarato:
```python
# Nel loop del validatore:
if blocco.tipo_evento in ("CVa", "CVp"):
    # La condotta successiva/precedente condivide legittimamente la corsa
    skip_next_cc_check = True
    continue
```

---

### I6 · Caricamento di TUTTI i TurnoPdc in memoria per filtraggio anti-rigenerazione

**File**: `backend/src/colazione/domain/builder_pdc/deposito_first.py:466-484`

```python
existing = list(
    (await session.execute(
        select(TurnoPdc).where(
            TurnoPdc.azienda_id == azienda_id,
            TurnoPdc.deposito_pdc_id == deposito_pdc_id,
        )
    )).scalars()
)
legati = [
    t for t in existing
    if (t.generation_metadata_json or {}).get("giro_materiale_id") == giro_id
]
```

Il filtro `giro_materiale_id` avviene in Python dopo aver caricato TUTTI i turni del deposito dalla DB. Con un deposito come GARIBALDI_TE (potenzialmente decine di programmi × molti giri), questa è una full table load ogni volta che si lancia il builder.

**Fix**: portare il filtro sul DB come subquery JSONB (identica a `registro_vetture.from_db`):
```python
existing = list(
    (await session.execute(
        select(TurnoPdc).where(
            TurnoPdc.azienda_id == azienda_id,
            TurnoPdc.deposito_pdc_id == deposito_pdc_id,
            cast(
                func.jsonb_extract_path_text(
                    TurnoPdc.generation_metadata_json, "giro_materiale_id"
                ),
                Integer,
            ) == giro_id,
        )
    )).scalars()
)
```
O, se si risolve I3 aggiungendo la colonna `giro_materiale_id` strutturata: semplicissima FK query.

---

### I7 · `split_cv.py` non applica risparmio accessori §6 (80' persi per ogni CV)

**File**: `backend/src/colazione/domain/builder_pdc/split_cv.py:27-31`

```
# Dalla docstring:
Limitazione MVP: non viene applicato il pattern CV no-overhead
(gap < 65' → CVa/CVp che sostituiscono ACCa/ACCp risparmiando 80').
Ogni ramo paga il costo accessori standard.
```

La NORMATIVA-PDC §6 è esplicita: CV < 65' → il mezzo non si spegne → nessun accessorio pieno. Il PdC "A" termina col CVa (variabile), il PdC "B" inizia col CVp (variabile), zero ACCa/ACCp. Con split_cv attuale ogni ramo di split genera ACCa 40' + ACCp 40' = 80 minuti di accessori "fantasma" per ogni punto di CV. Un turno P1 (Mi-Tirano) con due split paga 160 minuti in più rispetto alla realtà operativa.

**Impatto**: i turni generati con split CV risultano artificialmente più "lunghi" di quello che sarebbero in realtà, spingendo molte giornate oltre il cap 8h30 e causando scarto di giornate che potrebbero essere validamente costruite con CV no-overhead.

Questo è segnalato come "limitazione MVP" ma ha un impatto diretto sulla qualità dei turni generati, non è un'omissione cosmetica.

---

### I8 · `assert` in funzione di produzione — disabilitabili con `-O`

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:210, 253, 254`

```python
# builder.py:210
assert primo.ora_inizio is not None and ultimo.ora_fine is not None

# builder.py:253-254
assert b.ora_inizio is not None and b.ora_fine is not None
```

Python disabilita gli `assert` quando eseguito con il flag `-O` (optimization). Se Railway o qualsiasi runtime futuro lancia uvicorn con `-O`, questi assert silently scompaiono e il codice continua con `None.hour` producendo `AttributeError` in produzione invece di un errore intellegibile.

**Fix**: sostituire con guard espliciti:
```python
if primo.ora_inizio is None or ultimo.ora_fine is None:
    return None  # già gestito da blocchi_validi sopra, ma esplicito
```
O, se l'invariante è garantita dalla logica a monte, documentarlo nel commento e rimuovere l'assert.

---

### I9 · `revisioni_cascading_attive=0` hardcoded — placeholder da Sprint 7.6 (siamo a 8.4)

**File**: `backend/src/colazione/api/pianificatore_pdc.py:76`  
**File**: `backend/src/colazione/api/pianificatore_pdc.py:226`

```python
# pianificatore_pdc.py:76
`revisioni_cascading_attive` — placeholder Sprint 7.6+: il

# pianificatore_pdc.py:226
revisioni_cascading_attive=0,  # placeholder Sprint 7.6+
```

Sono al Sprint 8.4, questo campo ritorna sempre 0 nell'API response. Se il frontend legge questo campo per mostrare badge/alert ("X revisioni in cascata attive"), l'utente vede sempre "0 revisioni" anche quando ci sono revisioni provvisorie attive — potenzialmente ingannevole.

**Fix**: o implementare il conteggio reale (query `revisione_provvisoria` attiva per la data corrente), o rimuovere il campo dall'API response con una migration dello schema finché non è implementato.

---

## MINORI

### M1 · Gap numerazione migrazione: 0027 non esiste

**File**: `backend/alembic/versions/` — file `0027_*.py` assente

La catena Alembic è funzionalmente intatta (`0028.down_revision = 0026.revision`), ma il gap numerico crea confusione durante i code review ("cos'era 0027? è stato eliminato? è ancora da fare?"). Lo script `check_alembic_revisions.py` non rileva il gap perché controlla il chain, non i numeri.

**Fix**: aggiungere un commento in `0028_seed_depots_per_azienda.py`: `# NB: migrazione 0027 non creata — numerazione salta a 0028 (sprint 7.9 MR ε, gap intenzionale).`

---

### M2 · `Counter` importato e silenced con `# noqa: F841`

**File**: `backend/src/colazione/domain/builder_giro/varianti_calendariali.py:293`

```python
_ = Counter  # noqa: F841 — riservato per estensioni
```

Un import "riservato per estensioni future" è debito tecnico documentato nel posto sbagliato. Se `Counter` serve un giorno, aggiungilo allora. Oggi è dead code silenced.

**Fix**: rimuovere `from collections import Counter` e la riga `_ = Counter`.

---

### M3 · `label_origine = f"V{0}"` — formatta il letterale intero 0, non una variabile

**File**: `backend/src/colazione/api/giri.py:3015`

```python
label_origine = f"V{0}"  # placeholder; potremmo lookup la giornata
```

`f"V{0}"` è `"V0"` — la f-string interpola il valore `0`, non alcuna variabile. Il risultato è la stringa costante `"V0"` che finisce nell'API response come `label_origine`. Probabilmente era inteso come `f"V{variant_index}"` o simile.

**Fix**: determinare il valore corretto e sostituirlo, oppure sostituire con stringa letterale `"V0"` con un commento esplicativo se "V0" è il valore intenzionale.

---

### M4 · Commento stantio "placeholder, popolato in Sprint 2"

**File**: `backend/src/colazione/config.py:33`

```python
# --- Auth (placeholder, popolato in Sprint 2) ---
```

Siamo allo Sprint 8.4. Il commento non fornisce più contesto utile e può confondere nuovi lettori che cercano di capire cosa è auth e cosa non lo è.

**Fix**: rimuovere il riferimento allo Sprint 2 o sostituire con un commento sulla struttura attuale.

---

### M5 · Mancanza di indici espliciti su FK pivotali `GiroVariante.giro_giornata_id` e `TurnoPdcGiornata.turno_pdc_id`

**File**: `backend/src/colazione/models/giri.py:142`  
**File**: `backend/src/colazione/models/turni_pdc.py:72`

PostgreSQL crea automaticamente indici sulle PK, non sulle FK. Entrambe queste colonne sono FK usate in JOIN critici (caricate N volte per ogni build di turno):

```sql
-- Usata ogni volta in deposito_first.py
SELECT * FROM giro_variante WHERE giro_giornata_id IN (...)

-- Usata ogni GET turno PdC
SELECT * FROM turno_pdc_giornata WHERE turno_pdc_id = ?
```

Con 100 giri × 5 giornate = 500 righe in `giro_giornata`, e ogni giornata con 3-4 varianti, la tabella `giro_variante` ha ~2000 righe. Con 10 programmi e 500 turni PdC, `turno_pdc_giornata` ha ~3500 righe. Le seq scan esistenti sono tollerabili ora, ma con la crescita prevista del dataset Trenord (6536 corse → N giri) inizieranno a pesare.

**Fix**: migration dedicata con:
```sql
CREATE INDEX ix_giro_variante_giro_giornata_id ON giro_variante(giro_giornata_id);
CREATE INDEX ix_turno_pdc_giornata_turno_pdc_id ON turno_pdc_giornata(turno_pdc_id);
```

---

## Riepilogo priorità fix

| ID | Gravità | Costo stimato | Fix urgente? |
|----|---------|---------------|--------------|
| C1 | CRITICO | 3-4h | ✅ Sì — errori sistematici invernali |
| C2 | CRITICO | 2h | ✅ Sì — genera blocchi illegali |
| C3 | CRITICO | 30min | ✅ Sì — fix one-liner |
| C4 | CRITICO | 1h | ✅ Sì — turni illegali persistiti |
| C5 | CRITICO | 1h + migration | ✅ Sì — dato DB corrotto in silenzio |
| C6 | CRITICO | 2-4h diagnosi | ✅ Sì — CI cieca |
| I1 | IMPORTANTE | 2h | ⚡ Alta — impatta cap prestazione |
| I2 | IMPORTANTE | 3h refactor | 🔄 Prossimo Sprint |
| I3 | IMPORTANTE | 1h migration | ⚡ Alta — indice mancante |
| I4 | IMPORTANTE | 3-4h | 🔄 Richiede `enumera_date_giornata` |
| I5 | IMPORTANTE | 1h | 🔄 Prima di attivare split CV in prod |
| I6 | IMPORTANTE | 30min | ⚡ Alta — query N+1 |
| I7 | IMPORTANTE | 2-3 Sprint | 🔄 Impatto noto, documentato |
| I8 | IMPORTANTE | 30min | ✅ Sì — one-liner |
| I9 | IMPORTANTE | 1-2h o remove | 🔄 Prossimo Sprint |
| M1-M5 | MINORE | 30min ciascuno | 🔄 Quando si passa nei file |

---

## Note metodologiche

Questa review è stata condotta leggendo direttamente i file sorgente, senza eseguire la test suite (ambiente di review read-only). I finding C6 (50 test falliti) è basato su evidenza documentata in TN-UPDATE. I finding normativi (C1-C4) sono verificati contro `docs/NORMATIVA-PDC.md` riga per riga.

Nessuna modifica al codice di produzione è inclusa in questo documento.
