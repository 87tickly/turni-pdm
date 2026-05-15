# Code Review COLAZIONE — 2026-05-15

> Eseguita da NINO (Claude Code) con ausilio FAUSTO + AMILCARE per esplorazione parallela.
> Copertura: backend Python (domain, api, models, migrations, tests) + frontend TypeScript.
> Nessuna modifica al codice di produzione — solo diagnosi.
> Sprint corrente: 8.3 (backlog cleanup post-8.2).

---

## Indice

1. [CRITICI](#1-critici) — violazioni normativa, bug latenti, debito tecnico bloccante (9 finding)
2. [IMPORTANTI](#2-importanti) — qualità, manutenibilità, test coverage (13 finding)
3. [MINORI](#3-minori) — stile, naming, micro-ottimizzazioni (6 finding)
4. [Riepilogo rapido](#4-riepilogo-rapido)

---

## 1. CRITICI

### C-1 — `assert` in produzione nel builder PdC

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:210, 253, 256`

```python
assert primo.ora_inizio is not None and ultimo.ora_fine is not None  # riga 210
assert b.ora_inizio is not None and b.ora_fine is not None           # riga 253
assert prec.ora_fine is not None                                      # riga 256
```

**Problema**: `assert` in Python viene rimosso con `-O` (ottimizzazione). FastAPI in produzione può girare con `PYTHONOPTIMIZE=1` o `-O`. Se uno dei campi è `None` (blocco malformato, import parziale, edge case cross-notte) il builder crasha con `AssertionError` non catchata, che FastAPI trasforma in HTTP 500 senza dettagli diagnostici.

**Normativa**: il builder dovrebbe restituire un errore esplicito per input malformato, non crollare silenziosamente.

**Fix**: sostituire gli `assert` con `if ... is None: raise ValueError(f"blocco {b.id} manca ora_inizio/ora_fine")` oppure pre-validare i blocchi in entrata con un check esplicito che produce una risposta 422 a livello API.

---

### C-2 — Bug logica FR cap 28gg: cicli > 28 giorni sfuggono al controllo

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:1263`

```python
if ciclo_giorni <= 28 and n_dormite_fr > FR_MAX_PER_28GG:
```

**Problema**: la condizione esclude i cicli con `ciclo_giorni > 28` dal cap 3 FR/28gg. Esempio: ciclo 35 giorni con 5 dormite FR → la guardia settimanale controlla `ceil(35/7)=5 sett × 1 FR = 5 FR max` (nessuna violazione), ma nulla controlla che in una qualsiasi finestra mobile di 28 giorni ci siano ≤ 3 FR. Con 5 FR in 35 giorni è possibile averne 4 in 28 — violazione normativa non rilevata.

**Normativa**: NORMATIVA-PDC §10.6 "max 3/28gg" è una regola sliding-window, non un check sul totale del ciclo.

**Fix** (due opzioni):
- **Opzione A (corretta)**: implementare sliding-window check vero su `data_inizio` delle dormite FR. Complessità O(n) con due puntatori.
- **Opzione B (approssimazione sicura)**: rimuovere il `ciclo_giorni <= 28` e applicare sempre il check flat. Falsi positivi per cicli > 28gg, ma mai falsi negativi. Documentare la semplificazione.

La condizione `<= 28` non ha senso: un ciclo di 29+ giorni può violare 3/28gg proprio perché le dormite si concentrano nelle prime 4 settimane.

---

### C-3 — Costanti normativa duplicate: `vettura_resolver.py` ridefinisce `PRESTAZIONE_MAX_*` già in `builder.py`

**File**: `backend/src/colazione/domain/builder_pdc/vettura_resolver.py:57,60` vs `builder.py:58,59`

```python
# vettura_resolver.py
PRESTAZIONE_MAX_STANDARD_MIN: int = 510   # riga 57
PRESTAZIONE_MAX_NOTTURNO_MIN: int = 420   # riga 60

# builder.py
PRESTAZIONE_MAX_STANDARD = 510   # riga 58
PRESTAZIONE_MAX_NOTTURNO = 420   # riga 59
```

**Problema**: stessi valori, nomi parzialmente diversi (`*_MIN` vs no-suffix), due fonti di verità separate. Se domani la normativa cambia il cap (es. accordo sindacale porta prestazione standard a 540 min), il cambio richiede due aggiornamenti in due file distanti — con alta probabilità di dimenticare uno dei due. Il builder principale e il resolver potrebbero divergere silenziosamente.

**Normativa**: i cap 510 e 420 sono valori NORMATIVA-PDC §3. Devono avere una sola fonte di verità.

**Fix**: esportare le costanti da `giornata_base.py` (che già re-esporta da `builder.py`) e importarle in `vettura_resolver.py`. Rinominare consistentemente: usare lo stesso nome con o senza `_MIN` suffix ovunque. Candidato ideale: creare `domain/builder_pdc/normativa_pdc.py` con tutte le costanti normative (510, 420, 330, 360, finestre refezione, FR cap, ecc.) e importare da lì in tutti i moduli.

---

### C-4 — PK non modella PKa/PKp distinti: soglia 20' non verificata

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:258-269`

```python
if gap > 0:
    drafts.append(_BloccoPdcDraft(tipo_evento="PK", ...durata_min=gap...))
```

**Problema**: il builder crea un unico blocco `PK` per qualsiasi gap > 0 minuti tra due blocchi di condotta. La normativa §4.4 specifica che il PK ha struttura `PKa (≥20') → pausa → PKp (≥20')`, con ciascun componente minimo di 20 minuti. Un gap di 25 minuti produce un `PK` di 25 min, ma la struttura reale dovrebbe essere `PKa 20' + ... resto ...`. Quando poi `_inserisci_refezione` spezza il PK in `[PK_pre, REFEZ, PK_post]` può generare sub-blocchi con `durata_min=0` (esplicitamente previsto: "omettendo i PK con durata 0") — ma un `PKp` di 0 min è una violazione normativa, non una condizione ammessa.

**Normativa**: §4.4 "PK in arrivo: 20' minimo, PK in partenza: 20' minimo".

**Fix**: introdurre soglia esplicita `PK_COMPONENTE_MIN = 20`. Dopo `_inserisci_refezione`, verificare che i sub-blocchi PK residui abbiano `durata_min >= PK_COMPONENTE_MIN`. Se non lo rispettano, aggiungere una voce `violazioni`. Considerare se i gap < 40 min (20+20) possano legittimamente essere "buchi" (§4.2) anziché PK formali.

---

### C-5 — `_calcola_violazioni_cap_fr` non è enforcement: le violazioni sono solo string diagnostica

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:1228-1268`, `deposito_first.py:588-623`

**Problema**: `_calcola_violazioni_cap_fr()` ritorna una `list[str]` di descrizioni di violazione. In `deposito_first.py`, queste violazioni vengono aggiunte a `result.violazioni` nel `BuilderTurnoPdcResult`, ma il builder **non scarta il turno** — lo produce comunque. Il risultato viene serializzato e restituito all'API con le violazioni nel payload, ma lo stato del turno PdC nel DB è `GENERATO` indistinguibilmente da turni senza violazioni.

**Normativa**: un turno che viola il cap FR non dovrebbe essere considerato valido dalla normativa. Produrlo e persistierlo senza distinzione dal DB rischia che venga assegnato a persone reali senza che l'operatore se ne accorga.

**Fix**: nel modello `TurnoPdc` aggiungere un campo `has_violazioni_normativa: bool` (default False) che viene settato a True se `result.violazioni` è non-vuoto. Oppure, nel DB, salvare le violazioni come colonna JSONB (`violazioni_normativa: list[str]`). L'API di lista turni dovrebbe filtrare/marcare questi turni. Questo non richiede di scartarli (l'operatore deve poterli vedere e correggere manualmente) ma richiede che siano distinguibili.

---

### C-6 — `registro_vetture.py` usa `data_operativa=None` per tutti i blocchi VETTURA: wildcard cross-turno non filtrato per data

**File**: `backend/src/colazione/domain/builder_pdc/registro_vetture.py:240`

```python
data_operativa=None,  # wild card S4 TODO
```

**Problema**: il registro vetture usa `None` come wildcard per la data operativa — questo significa che due turni PdC su varianti calendariali diverse (es. uno LMXGV e uno SAB) possono "bloccarsi" a vicenda l'uso dello stesso numero treno anche se le date non si sovrappongono mai. In produzione, su PdE con 6.536 corse, questo può rendere indisponibili treni vettura per il rientro quando in realtà sarebbero liberi nelle date specifiche.

**Normativa**: §15 "vincolo unicità" si applica per data concreta, non per numero treno in assoluto su tutto il programma.

**Fix** (S4 TODO già identificato da SEVERO): implementare `enumera_date_giornata` che risolve le varianti calendariali di una giornata alle date concrete. Il registro deve operare su `(numero_treno, data_concreta)` non `(numero_treno, None)`. Questo è il fix S4 documentato in TN-UPDATE — va chiuso.

---

### C-7 — `multi_turno.py` aggiunge violazione invece di scartare se prestazione eccede cap post-vettura

**File**: `backend/src/colazione/domain/builder_pdc/multi_turno.py:935-943`

```python
# Aggiunge violazione anzichè scartare (diverso da deposito_first che scarta HARD)
```

**Problema**: comportamento inconsistente tra i due builder. `deposito_first.py` riga 362-372 scarta il turno con HARD CAP se la prestazione supera il cap dopo l'aggiunta del rientro. `multi_turno.py` invece aggiunge la violazione e continua, producendo turni che potrebbero eccedere 510 min. Un operatore che usa il builder multi-turno riceve risultati che violano il cap massimo senza che il sistema li abbia scartati.

**Normativa**: §11 "prestazione max 8h30 (510 min) standard, 7h (420 min) notturno". È un limite **assoluto** per legge, non una best-practice.

**Fix**: allineare `multi_turno.py` a `deposito_first.py`: se post-vettura la prestazione eccede il cap, scartare il candidato (`return None`) invece di produrre un turno violante. Documentare esplicitamente la scelta di fallback (VOCTAXI o DORMITA) invece di ignorare la violazione.

---

### C-8 — Tests xfail su violazioni normativa non hanno piano di sblocco esplicito

**File**: `backend/tests/test_violazioni_normative_pdc.py:79, 119, 161`

```python
@pytest.mark.xfail(strict=True, reason="builder non ancora valida ...")
```

**Problema**: 3 test per violazioni normativa (A: prestazione > cap, C: refezione mancante, D: condotta > cap) sono marcati `xfail(strict=True)` dal Sprint 8.x. `strict=True` significa che il test fallisce se il codice "per sbaglio" li fa passare — ma non dice quando il builder produrrà le violazioni corrette. La violazione B (deposito_pdc_id NOT NULL) è descritta come "rimandata" senza data. In pratica, il test file non ha mai un test che passa: è documentazione di feature mancante, non test suite funzionante.

**Fix**: o implementare le violazioni nel builder (la condotta e la refezione sono già calcolate — aggiungere la guardia è 10 righe), o spostare i test in un file `test_TBD_violazioni.py` chiaramente fuori dalla suite CI, invece di lasciare test `xfail` che misurano silenziosamente la non-implementazione.

---

### C-9 — Pipeline builder giro v2 (`multi_giornata_v2`) non operativa ma accettata dall'API

**File**: `backend/src/colazione/domain/builder_giro/builder.py:260-274`

```python
"Oggi solo ``v1`` è completamente operativa end-to-end. La pipeline
``v2`` (entry 202: catene-istanza → giornate-tipo → varianti
calendariali → concatenazione ciclica) è implementata in
``multi_giornata_v2.py`` ma il wiring al persister non è completato
(follow-up). Switching un programma a ``v2`` oggi genera questo
errore"
```

**Problema**: se un programma ha `builder_version='v2'`, l'API `POST /api/programmi/{id}/genera-giri` accetta la richiesta, tenta di chiamare `multi_giornata_v2`, e fallisce con un errore interno. Un errore 422 o 400 preciso sarebbe più corretto. Peggio: se in futuro il wiring viene collegato a metà, il builder v2 può produrre output parzialmente errato senza che sia chiaro all'operatore.

**Fix**: finché v2 non è end-to-end operativa, l'endpoint deve restituire 400/422 esplicito con messaggio "builder_version='v2' non ancora disponibile" **prima** di entrare nel codice del builder. La guardia attuale è dentro la logica del builder, non a livello API. Oppure: rimuovere dal DB il valore 'v2' dalla check constraint fino a quando v2 non è pronto.

---

## 2. IMPORTANTI

### I-1 — Costanti normativa non centralizzate: 3 `PRESTAZIONE_MAX_*` namespace diversi

**File**: 
- `builder.py:58-59` → `PRESTAZIONE_MAX_STANDARD`, `PRESTAZIONE_MAX_NOTTURNO`
- `vettura_resolver.py:57,60` → `PRESTAZIONE_MAX_STANDARD_MIN`, `PRESTAZIONE_MAX_NOTTURNO_MIN`
- `deposito_first.py:78-79` → import da `vettura_resolver`
- `split_cv.py:44-45` → import da `giornata_base` (che ri-esporta da `builder.py`)

**Problema**: due alberi di costanti diversi per la stessa normativa. `deposito_first.py` importa `PRESTAZIONE_MAX_STANDARD_MIN` da `vettura_resolver.py` (con `_MIN` nel nome) mentre la maggioranza dei moduli importa `PRESTAZIONE_MAX_STANDARD` (senza `_MIN`) da `giornata_base.py`. Non è un bug immediato (i valori sono identici) ma è una source of confusion che porterà a errori futuri.

**Fix**: vedi C-3. Un unico modulo `normativa_pdc.py` con tutti i valori normativa Trenord. Il multi-tenancy futuro (SAD, Trenitalia) userà questo modulo come punto di estensione per normative diverse.

---

### I-2 — Indici mancanti su colonne critiche per la ricerca

**File**: `backend/src/colazione/models/personale.py:57, 77, 80-81`

```python
persona_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("persona.id", ondelete="RESTRICT"))  # AssegnazioneGiornata
persona_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("persona.id", ondelete="CASCADE"))   # IndisponibilitaPersona
data_inizio: Mapped[date] = mapped_column(Date)  # IndisponibilitaPersona
data_fine: Mapped[date] = mapped_column(Date)    # IndisponibilitaPersona
```

**Problema**: le query più frequenti del modulo Gestione Personale filtrano per `persona_id` + intervallo `[data_inizio, data_fine]`. Senza indice composto, ogni query fa sequential scan su `indisponibilita_persona` e `assegnazione_giornata`. Con qualche centinaio di persone × centinaia di giorni, il problema è già percepibile.

**Fix**:
```python
# In IndisponibilitaPersona
Index("ix_indisponibilita_persona_id_date", "persona_id", "data_inizio", "data_fine")
# In AssegnazioneGiornata
mapped_column(..., index=True)  # su persona_id
mapped_column(Date, index=True)  # su data
```
Aggiungere come migration alembic.

---

### I-3 — `AssegnazioneGiornata.persona_id` → `ondelete="RESTRICT"` ma `IndisponibilitaPersona.persona_id` → `ondelete="CASCADE"`: semantica inconsistente

**File**: `backend/src/colazione/models/personale.py:57, 77`

```python
# AssegnazioneGiornata
ForeignKey("persona.id", ondelete="RESTRICT")   # blocca delete persona se ha assegnazioni
# IndisponibilitaPersona
ForeignKey("persona.id", ondelete="CASCADE")    # delete persona → delete indisponibilità
```

**Problema**: se un'azienda vuole eliminare un dipendente, il sistema blocca la delete perché ha assegnazioni (RESTRICT), ma cancella silenziosamente le indisponibilità (CASCADE). Logica opposta a quella che ci si aspetta: se vogliamo proteggere lo storico delle assegnazioni, dovremmo proteggere anche le indisponibilità.

**Fix**: decidere la semantica e allineare. Per lo storico operativo, probabilmente entrambe dovrebbero usare RESTRICT (la persona non può essere cancellata se ha storico). Oppure soft-delete su `persona` e rimuovere i DELETE fisici.

---

### I-4 — Scripts/ contiene codice smoke test non integrato nella test suite CI

**Directory**: `backend/scripts/smoke_56_cremona.py`, `smoke_56_tirano.py`, `smoke_74_split_cv.py`, `smoke_75_bug5_chiuso.py`, `test_a7_validation.py`

**Problema**: 5 file (totale ~1200 righe) contengono logica di test sviluppata durante Sprint precedenti. `test_a7_validation.py` nel nome inizia con `test_` ma è in `scripts/`, non in `tests/`. Questi script:
1. Non girano nella CI (non li trova pytest)
2. Possono diventare stale senza che nessuno se ne accorga
3. Duplicano in parte i test in `tests/`

**Fix**: per ogni script di smoke test che testa una feature ancora rilevante, creare un test parametrizzato in `tests/` con il corretto `pytestmark = pytest.mark.skipif(...)` se richiede DB. Gli script diagnostici (`diag_*.py`, `baseline_*.py`, `pulizia_*.py`) sono utility operative legittime e restano in `scripts/` ma dovrebbero avere un README che spiega quando usarli.

---

### I-5 — Test boundary numerici mancanti sui vincoli PdC (510, 420, 330 min esatti)

**File**: `backend/tests/test_violazioni_normative_pdc.py`, `test_builder_pdc_eta.py`

**Problema**: i test esistenti usano valori "comfortably over" (es. `condotta = 400` per testare violazione del cap 330) ma non testano i boundary esatti:
- Prestazione = 510 min: turno valido
- Prestazione = 511 min: turno violante
- Condotta = 330 min: valido
- Condotta = 331 min: violante
- REFEZ inizio 11:29: fuori finestra
- REFEZ inizio 11:30: in finestra
- REFEZ inizio 15:30: in finestra
- REFEZ inizio 15:31: fuori finestra

I boundary off-by-one sono i bug più frequenti nei sistemi di validazione. La normativa usa valori esatti (510, 330, 360) che corrispondono a `>` strict, non `>=`.

**Fix**: aggiungere test parametrizzati con `@pytest.mark.parametrize` che coprono i boundary ±1. Non richiede DB.

---

### I-6 — `multi_turno.py` DP fallback monolitico produce turni fuori-cap senza segnalazione all'operatore

**File**: `backend/src/colazione/domain/builder_pdc/multi_turno.py:635-640` (circa)

**Problema**: quando il DP non trova una segmentazione valida (tutti i segmenti eccedono il cap), il fallback è `[(0, len(blocchi) - 1)]` — cioè usa l'intero giro come un unico turno anche se eccede 510 min. Questo viene incluso nel risultato con flag `is_fuori_turno` probabilmente True, ma non è chiaro dall'output API che il turno è fisicamente impossibile vs che è solo non segmentabile con il giro dato.

**Fix**: il fallback dovrebbe aggiungere esplicitamente `"DP_fallback_monolitico_turno_fuori_cap:{prestazione_min}min"` alle violazioni, e il frontend dovrebbe mostrarlo come turno rosso non assegnabile, non come turno generico.

---

### I-7 — `generazione_metadata_json` su `TurnoPdcGiornata` è JSONB non tipato

**File**: `backend/src/colazione/models/turni_pdc.py` (campo `generation_metadata_json`)

**Problema**: il JSONB di metadata è consumato in `registro_vetture.py:197-212` con `jsonb_extract_path_text(...)` tramite cast manuale. Non c'è schema Pydantic per questo campo — il producer (builder) e il consumer (registro) sono accoppiati implicitamente via keys string "giro_materiale_id", "vettura_rientro", ecc. Un cambio di nome di una key rompe silenziosamente il registro senza errori di compilazione o runtime immediati.

**Fix**: definire una dataclass o Pydantic model `TurnoPdcGiornataMetadata` che modella il JSON. Il builder lo serializza con `.model_dump()`, il registro lo parsa con `.model_validate()`. Le key sono codificate una sola volta e mypy le controlla.

---

### I-8 — `test_violazioni_normative_pdc.py` violazione B (deposito_pdc_id NOT NULL) è "rimandata" senza traccia in TN-UPDATE

**File**: `backend/tests/test_violazioni_normative_pdc.py:203-210`

**Problema**: la violazione B (il builder deve rifiutare un giro senza `deposito_pdc_id`) è descritta come "rimandata a MR-PD2" ma non appare come residuo aperto in TN-UPDATE né come issue tracking. È un debito tecnico che si è accumulato silenziosamente fuori da qualsiasi sistema di tracciamento.

**Fix**: aggiungere entry in TN-UPDATE per la violazione B con stima di fix (< 1h: aggiungere una guardia in `deposito_first.py` al check `deposito_pdc_id is None`). Qualunque residuo senza stima e senza sistema di tracciamento è debito nascosto.

---

### I-9 — `stazione_inizio`/`stazione_fine` su `TurnoPdcGiornata` hanno `ForeignKey("stazione.codice")` senza `ondelete`

**File**: `backend/src/colazione/models/turni_pdc.py` (colonne `stazione_inizio`, `stazione_fine`)

**Problema**: FK a `stazione.codice` senza `ondelete` esplicito — PostgreSQL usa `RESTRICT` come default. Queste colonne sono nullable ma la stazione non può essere cancellata se referenziata da un turno PdC. L'incongruenza nullable+RESTRICT crea confusione: si aspetta che il campo possa essere NULL (stazione sconosciuta) ma la stazione, se nota, non può essere rimossa dall'anagrafica.

**Fix**: aggiungere `ondelete="SET NULL"` coerente con la nullable delle colonne. Aggiungere anche `index=True` su entrambe le colonne per le query che filtrano per stazione di inizio/fine turno.

---

### I-10 — Nessun test di integrazione end-to-end API per il builder PdC deposito-first

**File**: `backend/tests/test_deposito_first.py`, `test_piano_alpha_integration.py`

**Problema**: `test_deposito_first.py` testa il domain layer direttamente, non attraverso l'API. `test_piano_alpha_integration.py` usa mock su `trova_treno_vettura` (giusto per isolamento) ma **non verifica i valori numerici** di riposo intraturno e settimanale — solo che i campi esistono come lista. Un test di integrazione API che chiama `POST /api/giri/{id}/genera-turno-pdc?builder_strategy=deposito_first` e poi `GET /api/giri/{id}/turni-pdc` manca nella suite.

**Fix**: aggiungere un test di integrazione (con `pytestmark = pytest.mark.skipif(not _db_available())`) che crei un giro minimale, generi il turno PdC, e verifichi: `prestazione_min <= 510`, `condotta_min <= 330`, `refezione_min == 30 if prestazione > 360 else 0`.

---

### I-11 — `programmi.py` crea programma con regole in due operazioni non atomiche

**File**: `backend/src/colazione/api/programmi.py:324-369`

**Problema**: `create_programma` inserisce prima il programma (flush senza commit riga ~340), poi le regole (flush), poi esegue il commit. Se il commit fallisce (es. constraint violation su una delle regole), il rollback è corretto. Ma se il processo va in crash tra il secondo flush e il commit (es. SIGKILL su Railway), lo stato intermedio non è mai committato. Il vero problema è che non c'è `try/except` con rollback esplicito — SQLAlchemy fa autorollback su exception ma non su crash hardware.

**Fix**: avvolgere l'intera operazione di creazione in un try/except che chiama `await session.rollback()` esplicitamente in caso di errore, prima di sollevare HTTPException. Questo è il pattern corretto per FastAPI + SQLAlchemy async.

---

### I-12 — Mancanza di validation su `km_max_giornaliero` e `n_giornate_*` nel payload Pydantic dei programmi

**File**: `backend/src/colazione/api/programmi.py:324-337` (schema payload)

**Problema**: i campi `km_max_giornaliero`, `km_max_ciclo`, `n_giornate_min`, `n_giornate_max` non hanno `Field(ge=0)` o range check nel modello Pydantic. Un client malevolo (o un bug frontend) può inviare `km_max_giornaliero=-100` o `n_giornate_min=9999`. Il builder a runtime probabilmente fallisce in modo non elegante invece di dare 422.

**Fix**: aggiungere `Field(ge=0)` per i km, `Field(ge=1, le=30)` per n_giornate (range operativo reale Trenord: 2-15 giorni), `Field(ge=1)` validazione che `n_giornate_min <= n_giornate_max` (già fatto per PATCH ma non per POST).

---

### I-13 — `riposo_intraturno.py` e `riposo_settimanale.py` non applicati in `builder.py` e `multi_turno.py`

**File**: `backend/src/colazione/domain/builder_pdc/deposito_first.py:596, 612-623` vs `builder.py`, `multi_turno.py`

**Problema**: le validazioni di riposo intraturno (§11.5: ≥11h tra fine e inizio giornata successiva) e settimanale (§11.4: ≥62h ogni 7 giorni) sono implementate e chiamate in `deposito_first.py`, ma **non** in `builder.py` (builder legacy) né in `multi_turno.py` (builder DP). Il builder multi-turno può produrre turni che violano il riposo settimanale senza segnalazione.

**Normativa**: NORMATIVA-PDC §11.4-11.5. Il riposo settimanale non è opzionale.

**Fix**: estrarre la chiamata di validazione riposo in una funzione condivisa e chiamarla alla fine di ogni percorso di build, indipendentemente dalla strategia (legacy/deposito_first/multi).

---

## 3. MINORI

### M-1 — `tipo_evento: str` nella dataclass `_BloccoPdcDraft` dovrebbe essere un Literal o Enum

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:141`

```python
tipo_evento: str  # CONDOTTA, VETTURA, REFEZ, ACCp, ACCa, CVp, CVa, PK, SCOMP, PRESA, FINE, MM, VOCTAXI, DORMITA
```

Il commento enumera 14 valori ma mypy non può verificare che vengano usati solo quelli. Una typo ("CONOTTA" vs "CONDOTTA") è invisibile a compile time.

**Fix**: `tipo_evento: Literal["CONDOTTA", "VETTURA", "REFEZ", "ACCp", "ACCa", "CVp", "CVa", "PK", "SCOMP", "PRESA", "FINE", "MM", "VOCTAXI", "DORMITA"]` — mypy rileva immediatamente valori errati.

---

### M-2 — `multi_giornata_v2.py` contiene documentazione che cita `docs/MR-1110-DESIGN.md` inesistente

**File**: `backend/src/colazione/domain/builder_giro/multi_giornata_v2.py:5-6`

```python
"""...pipeline MR-1110 end-to-end... vedi `docs/MR-1110-DESIGN.md` §4.1..."""
```

Il file `docs/MR-1110-DESIGN.md` non esiste nella directory `docs/`. Il docstring punta a documentazione mancante, riducendo la leggibilità del modulo.

**Fix**: creare il documento mancante oppure aggiornare il docstring con il riferimento corretto (probabilmente `TN-UPDATE.md` entry 202).

---

### M-3 — Scripts smoke senza shebang, senza argomenti, non eseguibili standalone

**File**: `backend/scripts/smoke_56_tirano.py`, `smoke_74_split_cv.py`, ecc.

Gli script non hanno `#!/usr/bin/env python3`, non accettano argomenti CLI, hardcodano `azienda_id=1` o simili assunzioni sull'ambiente. Sono eseguibili solo in un contesto preciso (DB configurato, dati specifici) senza documentazione.

**Fix**: o convertire in test pytest (vedi I-4) oppure aggiungere un commento in testa con prerequisiti, come usarli, e quando sono ancora validi.

---

### M-4 — `registro_vetture.py` usa `cast(func.jsonb_extract_path_text(...), Integer)` senza commento sul perché non si usa `astext`

**File**: `backend/src/colazione/domain/builder_pdc/registro_vetture.py:197-212`

Il commento esistente spiega il workaround Postgres ma non perché `.astext` (il metodo canonico SQLAlchemy per JSONB path) non funziona. Questo è un caso dove il commento è **necessario** (comportamento non ovvio) ma incompleto.

**Fix**: aggiungere riga: "`.astext` con `Integer.in_()` causa `ProgrammingError: operator does not exist: text = integer` su Postgres 16 (parametro bind tipizzato). `cast(..., Integer)` forza la conversione lato DB."

---

### M-5 — `numero_treno_vettura` su `TurnoPdcBlocco` ha `index=True` ma non ha unicità cross-turno garantita dal DB

**File**: `backend/src/colazione/models/turni_pdc.py:124`

```python
numero_treno_vettura: Mapped[str | None] = mapped_column(String(20), index=True)
```

L'indice è utile per la ricerca per numero treno. Ma la garanzia di unicità cross-turno (§15) è implementata solo a livello applicativo (`registro_vetture.py`), non come vincolo DB. Se due builder girano in parallelo (es. due richieste concorrenti di `genera-turno-pdc`) possono assegnare lo stesso treno vettura senza che il DB si accorga.

**Fix**: aggiungere un `UniqueConstraint("numero_treno_vettura", "turno_pdc_giornata_id", name="uq_vettura_per_giornata")` oppure — se la garanzia cross-turno è più complessa — documentare esplicitamente che l'unicità è affidata al registro applicativo e che le richieste parallele non sono supportate (aggiungere un lock a livello API o serializzare via task queue).

---

### M-6 — Frontend: `stazioni-acronimi.ts` non ha copertura di test e non è tipato contro l'anagrafica backend

**File**: `frontend/src/lib/stazioni-acronimi.ts`

Il file mappa acronimi stazione a nomi completi. Se la lista stazioni nel backend (tabella `stazione`) evolve con nuove stazioni o nomi canonici aggiornati, il frontend rimane desincronizzato silenziosamente. Non c'è test che verifichi la coerenza.

**Fix**: generare `stazioni-acronimi.ts` da un endpoint backend (`GET /api/anagrafiche/stazioni`) oppure aggiungere un test e2e/snapshot che verifica che tutti i codici in `stazioni-acronimi.ts` esistano nella risposta dell'endpoint anagrafica.

---

## 4. Riepilogo rapido

| ID | Gravità | File | Linea | Fix stimato |
|----|---------|------|-------|-------------|
| C-1 | CRITICO | builder.py | 210, 253, 256 | 30 min |
| C-2 | CRITICO | builder.py | 1263 | 1h (sliding window) / 15 min (opzione B) |
| C-3 | CRITICO | vettura_resolver.py:57,60 / builder.py:58,59 | — | 1h refactor |
| C-4 | CRITICO | builder.py | 258-269 | 2h |
| C-5 | CRITICO | builder.py:1228 / deposito_first.py:588 | — | 2h (DB field + API) |
| C-6 | CRITICO | registro_vetture.py | 240 | 3h (enumera_date_giornata) |
| C-7 | CRITICO | multi_turno.py | 935-943 | 30 min |
| C-8 | CRITICO | test_violazioni_normative_pdc.py | 79, 119, 161 | 2h (implementare le guardie) |
| C-9 | CRITICO | builder_giro/builder.py | 260-274 | 30 min (API guard) |
| I-1 | IMPORTANTE | vettura_resolver.py / builder.py | — | 1h (segue C-3) |
| I-2 | IMPORTANTE | personale.py | 57, 77, 80-81 | 30 min (migration) |
| I-3 | IMPORTANTE | personale.py | 57, 77 | 15 min (allineamento semantica) |
| I-4 | IMPORTANTE | scripts/*.py | — | 2h (conversione test) |
| I-5 | IMPORTANTE | test_violazioni_normative_pdc.py | — | 1h (parametrize boundary) |
| I-6 | IMPORTANTE | multi_turno.py | ~637 | 30 min |
| I-7 | IMPORTANTE | turni_pdc.py (metadata JSONB) | — | 2h (Pydantic schema) |
| I-8 | IMPORTANTE | test_violazioni_normative_pdc.py | 203-210 | 15 min (tracking) |
| I-9 | IMPORTANTE | turni_pdc.py | stazione_inizio/fine FK | 20 min (migration) |
| I-10 | IMPORTANTE | tests/ (mancante) | — | 2h (test integrazione) |
| I-11 | IMPORTANTE | programmi.py | 324-369 | 30 min |
| I-12 | IMPORTANTE | programmi.py | 324-337 | 30 min (Pydantic Field) |
| I-13 | IMPORTANTE | builder.py / multi_turno.py | — | 1h (chiamata condivisa) |
| M-1 | MINORE | builder.py | 141 | 15 min |
| M-2 | MINORE | multi_giornata_v2.py | 5-6 | 15 min |
| M-3 | MINORE | scripts/*.py | — | 30 min/script |
| M-4 | MINORE | registro_vetture.py | 197-212 | 5 min |
| M-5 | MINORE | turni_pdc.py | 124 | 30 min |
| M-6 | MINORE | stazioni-acronimi.ts | — | 1h |

**Totale stimato** (con dipendenze): ~25-30h di sviluppo, di cui ~12h per i critici.

**Priorità raccomandata** (in ordine):
1. C-2 (bug FR cap silenzioso — normativa violata senza segnalazione)
2. C-7 (comportamento inconsistente builder multi-turno — turni fuori-cap prodotti)
3. C-1 (`assert` → crash non gestiti in produzione)
4. C-3 + I-1 (refactor costanti: unica fonte di verità normativa)
5. C-9 (builder v2 non operativo ma accettato dall'API)
6. C-8 (xfail senza piano → implementare le guardie sul builder)
7. I-13 (riposo settimanale non validato in multi_turno — normativa §11.4)
8. C-4 (PK min 20' non verificato — normativa §4.4)
9. C-5 + C-6 (violazioni non persistite, registro wildcard)
10. I-2 + I-9 (indici mancanti — performance)

---

*Review eseguita su commit HEAD del branch `master` (2026-05-10, entry 301 TN-UPDATE.md).*
*Nessuna modifica al codice di produzione in questa PR.*
