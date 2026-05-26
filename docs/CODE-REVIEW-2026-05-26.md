# CODE REVIEW — COLAZIONE (2026-05-26)

> **Autore**: NINO (Claude Code) con ausilio di 3 subagent paralleli  
> **Scope**: repository intero — backend Python, frontend TypeScript, modelli ORM,
> migrations, test, auth  
> **Metodo**: lettura diretta dei file critici + 3 agenti specializzati in parallelo  
> (dominio/builder, modelli/infrastruttura, frontend)  
> **Normativa di riferimento**: `docs/NORMATIVA-PDC.md` (fonte di verità — se il
> codice differisce, il codice ha torto)  
> **Richiesta originale**: "nessun fix automatico al codice — voglio leggere prima"

---

## Classificazione gravità

| Simbolo | Significato |
|---------|-------------|
| 🔴 CRITICO | Violazione normativa, bug latente, rischio sicurezza, debito tecnico bloccante |
| 🟠 IMPORTANTE | Qualità, manutenibilità, correttezza silente |
| 🟡 MINORE | Stile, consistenza, micro-ottimizzazioni |

---

## Sommario

| Area | 🔴 CRITICO | 🟠 IMPORTANTE | 🟡 MINORE | Totale |
|------|-----------|--------------|---------|--------|
| Backend — dominio e builder PdC | 6 | 8 | 6 | 20 |
| Backend — modelli e infrastruttura | 2 | 9 | 5 | 16 |
| Frontend — React/TypeScript | 2 | 7 | 4 | 13 |
| **TOTALE** | **10** | **24** | **15** | **49** |

---

## SEZIONE 1 — Backend: Dominio, Builder PdC, Validatori

---

### D-01 🔴 CRITICO — Cap prestazione calcolato con `is_notturno` invece di `is_cap_notturno`

**FILE**: `backend/src/colazione/api/turni_pdc.py:947`

**PROBLEMA**:  
`get_turno_pdc_dettaglio` calcola il badge `prestazione_violata` con:

```python
PRESTAZIONE_MAX_NOTTURNO if g.is_notturno else PRESTAZIONE_MAX_STANDARD
```

Il flag `is_notturno` è documentato come *superinclusivo per UI*: `True` se presa <05:00
**oppure** fine >22:00 **oppure** cross-mezzanotte. Il cap normativo 420 min
(§11.8 NORMATIVA-PDC) si applica **solo** alla presa 01:00–04:59.

Conseguenza concreta: un turno che finisce alle 22:30 con presa alle 06:00 e
durata 420 min viene marcato `prestazione_violata=True` perché `is_notturno=True`
(fine >22:00) e 420 > 420... no, scatta a 421 — ma un turno di 445 min con presa
06:00 che è **normativamente valido** (limit 510) viene marcato violato (445 > 420).
Falso positivo normativo mostrato all'utente nel pannello Gantt.

**FIX CONCRETO**:  
Derivare il cap dall'orario `inizio_prestazione` già persistito (nessuna migration):

```python
# turni_pdc.py:947 — sostituire il ternario esistente con:
def _cap_prestazione(g: TurnoPdcGiornata) -> int:
    if g.inizio_prestazione is None:
        return PRESTAZIONE_MAX_STANDARD
    h = g.inizio_prestazione.hour
    m = g.inizio_prestazione.minute
    minuti = h * 60 + m
    return PRESTAZIONE_MAX_NOTTURNO if (60 <= minuti < 300) else PRESTAZIONE_MAX_STANDARD
```

In alternativa: aggiungere colonna `is_cap_notturno BOOLEAN NOT NULL DEFAULT FALSE`
a `turno_pdc_giornata` e valorizzarla dal builder (più leggibile e testabile).

---

### D-02 🔴 CRITICO — Refezione ai bordi può portare la prestazione oltre il cap senza rilevarlo

**FILE**: `backend/src/colazione/domain/builder_pdc/builder.py:477–561` (funzione `_inserisci_refezione_ai_bordi`)

**PROBLEMA**:  
`_inserisci_refezione_ai_bordi` aggiunge 30 min di REFEZ estendendo `ora_presa`
o `ora_fine_servizio`. La nuova prestazione (`prestazione_min + 30`) **non viene
rivalidata** contro il cap (510/420 min) dentro `_build_giornata_pdc`.

La funzione è chiamata nel blocco 6.bis (dopo il calcolo delle violazioni a riga 317)
e il re-calcolo della `prestazione_min` alla riga 362 usa il valore post-bordi.
Ma la violazione `prestazione_max` viene valutata **prima** dell'inserimento (riga ~360),
quindi se il turno era 505 min, dopo l'inserimento diventa 535 min e la violazione
non viene riportata.

**FIX CONCRETO**:  
Dopo il blocco 6.bis (inserimento REFEZ ai bordi), ri-verificare il cap:

```python
# builder.py — subito dopo la chiamata a _inserisci_refezione_ai_bordi:
if prestazione_min > cap_prestazione:
    violazioni.append(f"prestazione_max:{prestazione_min}>{cap_prestazione}min")
```

Oppure, versione più robusta: fare in modo che `_inserisci_refezione_ai_bordi`
riceva `cap_prestazione` e rifiuti l'inserimento se la nuova prestazione lo supera
(ritorna il draft invariato e appende invece la violazione `refezione_mancante`).

---

### D-03 🔴 CRITICO — Registro vetture `from_db` usa `data_operativa=None` (wild card) — over-exclusion

**FILE**: `backend/src/colazione/domain/builder_pdc/registro_vetture.py:240`  
(commento: `# wild card S4 TODO`)

**PROBLEMA**:  
`RegistroVettureAssegnate.from_db` carica i blocchi VETTURA esistenti con
`data_operativa=None`. La wild card significa "questa vettura è esclusa per
**qualunque data**". Se il treno R_100 è usato come vettura nella settimana A del
ciclo (giornata 1), il builder per la settimana B (giornata 8, data diversa) non
può usare R_100 anche se è perfettamente valido.

Impatto operativo concreto: su giri Trenord reali con 7–14 giornate, il registro
over-esclude vetture basandosi su date sbagliate per la maggioranza delle giornate.
Il builder cade silenziosamente su MM/VOCTAXI anche quando una VETTURA valida è
disponibile.

**FIX CONCRETO**:  
Usare `TurnoPdc.valido_da` come `data_operativa` nel from_db invece di None:

```python
# registro_vetture.py — in from_db, JOIN con TurnoPdc:
# TurnoPdcBlocco → TurnoPdcGiornata → TurnoPdc.valido_da
# Registrare ogni blocco con data_operativa = turno.valido_da + timedelta(days=giornata.numero_giornata - 1)
```

Il `valido_da` è già nel modello ORM — il JOIN è 2-livelli. Stima: 1h di lavoro.

---

### D-04 🔴 CRITICO — `data_operativa` identica per tutte le giornate del ciclo

**FILE**: `backend/src/colazione/domain/builder_pdc/deposito_first.py:537–543`

**PROBLEMA**:  
`genera_turni_pdc_deposito_first` usa `valido_da_eff` come `data_operativa` per
**ogni** invocazione di `costruisci_giornata_deposito_first`, indipendentemente dal
`numero_giornata`. Un giro da 8 giornate ha:
- giornata 1 = `valido_da`
- giornata 2 = `valido_da + 1`
- ...
- giornata 8 = `valido_da + 7`

Usare la stessa data per tutte le giornate fa sì che il registro vetture e il cap FR
calcolino tutto sulla data sbagliata per le giornate 2–N.

**FIX CONCRETO** (stimato < 30 minuti):  
Nel loop `for gg in giornate_giro:` (riga 552), calcolare la data corretta:

```python
from datetime import timedelta

# dentro il loop:
data_operativa_giornata = valido_da_eff + timedelta(days=gg.numero_giornata - 1)
# e passarla a costruisci_giornata_deposito_first
```

Non richiede `enumera_date_giornata` per il caso lineare (ciclo senza varianti
calendariali multiple). Il TODO che rimanda all'helper è un caso avanzato, non
una scusa per non fare il caso base.

---

### D-05 🔴 CRITICO — Costanti normative doppiate con nomi divergenti in due moduli

**FILE**: `backend/src/colazione/domain/builder_pdc/builder.py:59` +  
`backend/src/colazione/domain/builder_pdc/vettura_resolver.py` (inizio file)

**PROBLEMA**:  
`builder.py` esporta `PRESTAZIONE_MAX_STANDARD = 510` e `PRESTAZIONE_MAX_NOTTURNO = 420`.  
`vettura_resolver.py` ridefinisce `PRESTAZIONE_MAX_STANDARD_MIN = 510` e
`PRESTAZIONE_MAX_NOTTURNO_MIN = 420` — stessi valori, nomi diversi (suffisso `_MIN`).

Se la normativa cambia un valore (evento raro ma non impossibile), il cambiamento
va fatto in due posti. Con nomi diversi non c'è nemmeno un errore di import che
segnali la discrepanza.

Stesso problema per `REFEZIONE_SOGLIA_MIN = 360` e `REFEZIONE_MIN_DURATA = 30` di
`builder.py` ricopiati come `PRESTAZIONE_REFEZIONE_SOGLIA_MIN = 360` e
`REFEZIONE_MIN_RICHIESTI = 30` in `api/turni_pdc.py:938–939`.

**FIX CONCRETO**:  
Creare `backend/src/colazione/domain/normativa_pdc.py` come unica fonte delle
costanti normative:

```python
# normativa_pdc.py — costanti estratte da NORMATIVA-PDC.md
PRESTAZIONE_MAX_MIN = 510      # §11.8 standard
PRESTAZIONE_NOTTURNO_MAX_MIN = 420  # §11.8 presa 01:00-04:59
CONDOTTA_MAX_MIN = 330         # §14.2
REFEZIONE_SOGLIA_MIN = 360     # §4.1 obbligo
REFEZIONE_DURATA_MIN = 30      # §4.1
ACCESSORI_MIN = 40             # §3.3 standard
ACCESSORI_PRERISCALDO_MIN = 80 # §3.3 dic-feb
PK_MINIMO_MIN = 20             # §4.4 in/out
```

Tutti i moduli importano da qui. Rimuovere le ridefinizioni locali.

---

### D-06 🔴 CRITICO — `giornata_base.py` è un relay di simboli privati — l'astrazione non ha effetto

**FILE**: `backend/src/colazione/domain/builder_pdc/giornata_base.py:48–57`

**PROBLEMA**:  
Sprint 8.2 (SEVERO S2) ha creato `giornata_base.py` per dare nomi pubblici ai
simboli privati di `builder.py`. L'implementazione è un re-export diretto:

```python
BloccoPdcDraft = _BloccoPdcDraft   # alias del privato
```

I test (`test_violazioni_normative_pdc.py:31`, `test_riposo_intraturno.py:7–9`)
importano ancora direttamente `_GiornataPdcDraft`, `_build_giornata_pdc` da
`builder.py`. L'astrazione non protegge i test — il contratto "simboli underscore
sono privati" è lettera morta.

**FIX CONCRETO**:  
Spostare le **definizioni** (non gli alias) da `builder.py` a `giornata_base.py`:
le classi `_BloccoPdcDraft`, `_GiornataPdcDraft`, le funzioni helper di costruzione.
`builder.py` importa da `giornata_base`. Aggiornare tutti i test per importare
dai simboli pubblici di `giornata_base` (senza underscore). Rimuovere gli alias.
I test esistenti guidano la regressione. Stima: < 2h.

---

### D-07 🟠 IMPORTANTE — `updated_at` senza `onupdate` — timestamp congelato dopo ogni UPDATE

**FILE**: `backend/src/colazione/models/turni_pdc.py:59` +  
`backend/src/colazione/models/giri.py:79` +  
`backend/src/colazione/models/programmi.py:187`

**PROBLEMA**:  
I campi `updated_at` su `TurnoPdc`, `GiroMateriale`, `ProgrammaMateriale` usano
`server_default=func.now()` ma **non** `onupdate=func.now()`. Un UPDATE via ORM
non aggiorna il timestamp — resta congelato al valore dell'INSERT. Il dettaglio
endpoint espone `updated_at` nel response schema; il builder fa UPDATE espliciti
(`stato_pipeline_pdc` aggiornato a `turni_pdc.py:433–437`). Il campo è stale
strutturalmente.

L'API layer compensa manualmente in alcuni path (es. `api/programmi.py:544`), ma
ogni nuovo endpoint che non ricordi di farlo lascia `updated_at` stale senza errori.

**FIX CONCRETO**:  

```python
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
    onupdate=func.now(),  # ← aggiungere
)
```

Per tutti e tre i modelli. Migration Alembic necessaria (ALTER COLUMN non cambia
dati, solo aggiunge il trigger ON UPDATE).

---

### D-08 🟠 IMPORTANTE — `TurnoPdc.codice` non ha vincolo UNIQUE

**FILE**: `backend/src/colazione/models/turni_pdc.py:39` + `builder.py:1222–1225`

**PROBLEMA**:  
`TurnoPdc.codice VARCHAR(50)` non ha UNIQUE constraint né a livello ORM né a livello
DB. La funzione `_genera_codice_turno` produce codici deterministici come
`T-BERGAMO-G-FIO-001-ETR526`. Se lo stesso giro viene rigenerato con `force=True`
due volte in sessioni diverse (race condition, bug), possono esistere due `TurnoPdc`
con lo stesso codice. L'UI usa il codice come display-key identificativo univoco.

**FIX CONCRETO**:  
Aggiungere a `TurnoPdc.__table_args__`:

```python
UniqueConstraint("azienda_id", "codice", name="uq_turno_pdc_azienda_codice"),
```

Pre-migration: verificare duplicati esistenti con
`SELECT codice, COUNT(*) FROM turno_pdc GROUP BY codice HAVING COUNT(*) > 1`.

---

### D-09 🟠 IMPORTANTE — `TIRANO` nelle deroghe CV hardcoded senza fondamento normativo

**FILE**: `backend/src/colazione/domain/builder_pdc/split_cv.py:61`

**PROBLEMA**:  
```python
STAZIONI_CV_DEROGA = frozenset({"MORTARA", "TIRANO"})
```

`MORTARA` è citata esplicitamente in NORMATIVA-PDC §7.1 come deroga CV.
`TIRANO` non è menzionata nel documento normativo. Il commento cita §7.1 ma
il testo della normativa ammette solo: deposito PdC, MORTARA, capolinea inversione.

Se TIRANO è un capolinea ammesso per "inversione", andrebbe messa in una lista
configurabile di capolinea per inversione — non hardcoded con MORTARA come deroga
speciale. Qualsiasi altro capolinea richiederà una code change.

**FIX CONCRETO**:  
Opzione A (immediata): aggiungere commento normativo preciso che cita l'articolo
che autorizza TIRANO, oppure rimuoverla se non documentata.  
Opzione B (strutturale): spostare la lista in una colonna
`is_stazione_cv_deroga BOOLEAN` sulla tabella `stazione` (o `depot`),
configurabile per azienda.

---

### D-10 🟠 IMPORTANTE — `assert` in codice di produzione — bypassati con `python -O`

**FILE**: `backend/src/colazione/domain/builder_pdc/builder.py:210, 253, 256` +  
`backend/src/colazione/api/turni_pdc.py:377`

**PROBLEMA**:  
`_build_giornata_pdc` usa `assert` per verificare invarianti di business logic.
In produzione con `python -O` (comune nei container Railway), gli `assert` sono
rimossi e il codice proseguirebbe con `None`, propagando `AttributeError` o calcoli
errati silenziosi.

`api/turni_pdc.py:377` ha `assert deposito_pdc_id is not None` in un endpoint
FastAPI — se avviato con `-O`, questa guardia sparisce.

**FIX CONCRETO**:  
Sostituire ogni `assert cond` con:

```python
if not cond:
    raise ValueError("messaggio diagnostico")   # nel dominio
    # oppure
    raise HTTPException(422, "...")             # nell'API layer
```

L'assert a `turni_pdc.py:377` è ridondante (validazione già a riga 332) — la
soluzione più pulita è rimuoverlo.

---

### D-11 🟠 IMPORTANTE — Anti-rigenerazione turni carica tutta la tabella senza filtro SQL

**FILE**: `backend/src/colazione/domain/builder_pdc/deposito_first.py:466–484` +  
`backend/src/colazione/domain/builder_pdc/builder.py:736–738`

**PROBLEMA**:  
La query anti-rigenerazione carica **tutti** i `TurnoPdc` dell'azienda con un
`WHERE azienda_id = ...` senza filtro su `giro_materiale_id`. Il filtro avviene
poi in Python con list comprehension. Per un'azienda con centinaia di turni, questo
è un full scan della tabella.

**FIX CONCRETO**:  
Filtrare in SQL via JSONB:

```python
select(TurnoPdc).where(
    TurnoPdc.azienda_id == azienda_id,
    cast(
        TurnoPdc.generation_metadata_json["giro_materiale_id"].astext,
        BigInteger
    ) == giro_id,
    TurnoPdc.deposito_pdc_id == deposito_pdc_id,
)
```

Il pattern è già usato correttamente in `api/turni_pdc.py:600–606`. Costo
indice: aggiungere `GIN index su generation_metadata_json` se la tabella cresce.

---

### D-12 🟠 IMPORTANTE — `DEPOT_MILANO_MM` non validato contro il DB al boot

**FILE**: `backend/src/colazione/domain/builder_pdc/vettura_resolver.py:82–91`

**PROBLEMA**:  
`DEPOT_MILANO_MM` lista codici depot hardcoded (`"GARIBALDI_ALE"`,
`"GARIBALDI_CADETTI"`, `"GRECO_TE"`, `"FIORENZA"`). Se i codici nel DB differiscono
(typo, naming diverso), il resolver non riconosce mai un deposito Milano e usa
sempre VOCTAXI invece di MM. Nessuna query, nessuna validazione al boot: il
fallback è silente.

**FIX CONCRETO**:  
Al boot (o lazy-load della BuilderProgrammaContext), verificare:

```python
count = await session.scalar(
    select(func.count()).select_from(Depot).where(
        Depot.codice.in_(DEPOT_MILANO_MM),
        Depot.azienda_id == azienda_id,
    )
)
if count == 0:
    logger.warning("DEPOT_MILANO_MM: nessun depot trovato nel DB — "
                   "vettura MM mai assegnata")
```

In prospettiva: spostare la lista in un campo `is_mm_servito BOOLEAN` sulla
tabella `depot`.

---

### D-13 🟠 IMPORTANTE — `_estrai_candidato` e `_estrai_candidato_with_reason` sono dead code

**FILE**: `backend/src/colazione/integrations/live_arturo.py:563–709`

**PROBLEMA**:  
Sprint 8.4 G3 ha refattorizzato `trova_treno_vettura` con la strategia 2-step
(fetch `/partenze/` + fetch `/treno/{numero}`). Il loop inline in
`trova_treno_vettura` gestisce ora tutta la logica direttamente. Le funzioni
`_estrai_candidato` (riga 638) e `_estrai_candidato_with_reason` (riga 563)
non sono più chiamate da nessun punto del codice di produzione.

Aggravante: le funzioni basano la logica sull'assunzione che `fermate` contenga
il percorso completo — assunzione che Sprint 8.4 G3 ha dimostrato essere **errata**
(root cause delle vetture mancanti). Dead code con logica obsoleta basata su un
contratto API sbagliato.

**FIX CONCRETO**:  
Verificare con `grep -rn "_estrai_candidato" backend/` che non siano importate nei
test, poi rimuovere entrambe le funzioni (righe 563–709). Pulizia diretta.

---

### D-14 🟠 IMPORTANTE — Accessori preriscaldo (80 min, dic-feb) non implementato — nessun TODO

**FILE**: `backend/src/colazione/domain/builder_pdc/builder.py:55–69` +  
`backend/src/colazione/models/turni_pdc.py` (campo `is_accessori_maggiorati`)

**PROBLEMA**:  
NORMATIVA-PDC §4.2: `ACCp/ACCa = 80 min` nel periodo dicembre–febbraio (preriscaldo
materiale). Il builder usa sempre `ACCESSORI_MIN_STANDARD = 40`. Il campo
`TurnoPdcBlocco.is_accessori_maggiorati` esiste nel modello ORM ma viene sempre
persistito a `False` (`builder.py:1103`). Non esiste nessun commento o TODO che
documenti questa mancanza.

**FIX CONCRETO**:  
Aggiungere un TODO esplicito con la stima di implementazione:

```python
# TODO(§4.2): accessori preriscaldo dic-feb = 80 min.
# Richiede: data_operativa già disponibile da deposito_first.py.
# Logica: ACCESSORI = 80 if month in {12, 1, 2} else 40
# Valorizzare is_accessori_maggiorati=True nel persister.
# Stima: < 1h.
```

Poi, implementarlo. È < 1h di lavoro per il caso base — non merita un TODO
a vita.

---

### D-15 🟡 MINORE — `riposo_min_post` ultima giornata usa magic number `24*60`

**FILE**: `backend/src/colazione/domain/builder_pdc/riposo_intraturno.py:189–195`

**PROBLEMA**:  
Per l'ultima giornata del ciclo, il modulo calcola:
```python
prec.riposo_min_post = gap_singola_notte + 24 * 60
```

Il `+24*60` è un placeholder arbitrario "stima conservativa". Non è autoesplicativo
né documentato come tale nella costante.

**FIX CONCRETO**:  
Estrarre la costante con nome e commento:

```python
_STIMA_RIPOSO_SETTIMANALE_EXTRA_MIN = 24 * 60  # placeholder: raffinare con enumera_date_giornata (TODO S4)
prec.riposo_min_post = gap_singola_notte + _STIMA_RIPOSO_SETTIMANALE_EXTRA_MIN
```

---

### D-16 🟡 MINORE — 3 test `xfail(strict=True)` possibilmente stale

**FILE**: `backend/tests/test_violazioni_normative_pdc.py`

**PROBLEMA**:  
I test `test_violazione_a_cap_condotta_*`, `test_violazione_c_giornata_chiude_in_*`,
`test_violazione_d_giornata_lontana_*` sono marcati `xfail(strict=True)` con
motivazione "Risolto in MR-PD3 builder deposito-first". Il builder deposito-first
è chiuso in Sprint 8.2. Se i test testano ancora `_build_giornata_pdc` (builder
monolitico non modificato), sono permanentemente xfail senza mai diventare green —
dead test code.

**FIX CONCRETO**:  
Verificare con `pytest -v test_violazioni_normative_pdc.py`. Se XFAIL:
aggiungere test paralleli che testino il builder deposito-first (il path corretto)
e marcare quelli sul monolitico come "regression test comportamento legacy"
senza promessa di fix. Se XPASS: rimuovere `xfail`.

---

### D-17 🟡 MINORE — `GiriEsistentiError` non inclusa nell'`__all__` di `giornata_base.py`

**FILE**: `backend/src/colazione/domain/builder_pdc/giornata_base.py:42, 74–101`

**PROBLEMA**:  
`GiriEsistentiError` è importata a riga 42 ma assente dall'`__all__` del modulo.
Chi usa `from giornata_base import *` non la ottiene. Il `__all__` incompleto
confonde la superficie pubblica del modulo.

**FIX CONCRETO**:  
Aggiungere `"GiriEsistentiError"` alla lista `__all__` di `giornata_base.py`.

---

### D-18 🟡 MINORE — Costanti normative ridefinite inline nell'endpoint invece di essere importate

**FILE**: `backend/src/colazione/api/turni_pdc.py:938–939`

**PROBLEMA**:  
`get_turno_pdc_dettaglio` ridefinisce localmente:

```python
PRESTAZIONE_REFEZIONE_SOGLIA_MIN = 360
REFEZIONE_MIN_RICHIESTI = 30
```

Identici a `REFEZIONE_SOGLIA_MIN = 360` e `REFEZIONE_MIN_DURATA = 30` già in
`builder.py` / `giornata_base.py`. Due sorgenti della verità.

**FIX CONCRETO**:  

```python
from colazione.domain.builder_pdc.giornata_base import (
    REFEZIONE_SOGLIA_MIN,
    REFEZIONE_MIN_DURATA,
)
```

Rimuovere le ridefinizioni locali. (Si consolida con D-05 nel fix strutturale.)

---

### D-19 🟡 MINORE — `_aggiungi_dormite_fr` è no-op per il builder deposito-first senza documentazione

**FILE**: `backend/src/colazione/domain/builder_pdc/builder.py:1131–1204`

**PROBLEMA**:  
`_aggiungi_dormite_fr` è chiamata anche per turni deposito-first. Per costruzione,
questi turni chiudono sempre al deposito sede — nessuna FR. La funzione ritorna
sempre `fr_log = []`. Il commento a riga 1148 "Limiti settimanali... NON enforced
nel MVP" non chiarisce che per deposito-first il calcolo è strutturalmente vuoto
(non un TODO, una conseguenza dell'invariante del builder).

**FIX CONCRETO**:  
Aggiungere doc-comment a `genera_turni_pdc_deposito_first`:

```python
# Per costruzione deposito-first non ci sono dormite FR (chiusura al deposito
# garantita). La chiamata a _aggiungi_dormite_fr è mantenuta per compatibilità
# API ma ritornerà sempre [].
```

---

### D-20 🟡 MINORE — `giornate_concrete.py` fallback over-include su variante non riconosciuta

**FILE**: `backend/src/colazione/domain/giornate_concrete.py`

**PROBLEMA**:  
Per stringhe variante non riconosciute, il fallback restituisce **tutti** i
candidati possibili. Un typo nella stringa di variante silenziosamente over-include
giornate di tutti i cicli.

**FIX CONCRETO**:  
Loggare `logger.warning("variante non riconosciuta: %s", variante_str)` nel ramo
fallback, così i typo sono tracciabili nei log invece di essere silenziosi.

---

## SEZIONE 2 — Backend: Modelli ORM e Infrastruttura

---

### I-01 🔴 CRITICO — JWT secret di default accettato in produzione

**FILE**: `backend/src/colazione/config.py:34–39`

**PROBLEMA**:  
`jwt_secret` ha default `"dev-secret-change-me-min-32-characters-long"`. Non
esiste nessun validatore Pydantic che verifichi in runtime che il secret sia stato
cambiato. Un deploy su Railway senza `JWT_SECRET` impostato esegue con la chiave
pubblica nota del repository: qualunque attore esterno che la conosca può forgiare
token JWT validi per qualsiasi utente.

**FIX CONCRETO**:  

```python
@field_validator("jwt_secret")
@classmethod
def jwt_secret_must_be_strong(cls, v: str) -> str:
    if v == "dev-secret-change-me-min-32-characters-long":
        if os.getenv("ENVIRONMENT", "dev") == "production":
            raise ValueError("JWT_SECRET non può essere il default in produzione")
    if len(v) < 32:
        raise ValueError("JWT_SECRET deve essere almeno 32 caratteri")
    return v
```

Alternativa più rigorosa: rendere `jwt_secret` required (nessun default) e gestire
il valore di sviluppo via `.env.local` escluso dal repo.

---

### I-02 🔴 CRITICO — JWT access token a 72h — nessun logout, nessuna revoca

**FILE**: `backend/src/colazione/config.py:39`

**PROBLEMA**:  
`jwt_access_token_expire_min = 4320` (72 ore). Non esiste endpoint di logout
né blacklist di token. Disattivare un utente compromesso non lo espelle per
fino a 3 giorni. Il `auth/dependencies.py` riconosce esplicitamente il problema
("il cambio diventa effettivo solo all'access token successivo") ma non lo risolve.

Per un sistema di pianificazione ferroviaria operativa con 5 ruoli distinti,
72h è una finestra di esposizione inaccettabile.

**FIX CONCRETO**:  
1. Ridurre access token a 15–30 min (standard industria).
2. Implementare logout che invalida il refresh token (tabella
   `refresh_token_blacklist(jti, exp)` o Redis).

Il `/api/auth/refresh` fa già DB lookup per `is_active` — la protezione esiste
per il refresh token, non per l'access token vivo.

---

### I-03 🟠 IMPORTANTE — FK senza `ondelete` esplicito in >15 colonne

**FILE** (elenco completo):

| Tabella | Colonna | File:riga | `ondelete` appropriato |
|---------|---------|-----------|----------------------|
| `giro_materiale` | `materiale_tipo_codice` | `models/giri.py:63` | `SET NULL` (nullable) o `RESTRICT` |
| `corsa_commerciale` | `codice_origine`, `codice_destinazione`, `codice_inizio_cds`, `codice_fine_cds` | `models/corse.py:92–95` | `RESTRICT` |
| `corsa_materiale_vuoto` | stazione FK | `models/corse.py:176–177` | `RESTRICT` |
| `revisione_provvisoria_blocco` | `corsa_commerciale_id`, stazione FK | `models/revisioni.py:59–67` | `RESTRICT`/`SET NULL` |
| `programma_materiale` | `created_by_user_id` | `models/programmi.py:184` | `SET NULL` |
| `turno_pdc_giornata` | `stazione_inizio`, `stazione_fine` | `models/turni_pdc.py:75–76` | `SET NULL` |
| `turno_pdc_blocco` | `stazione_da_codice`, `stazione_a_codice` | `models/turni_pdc.py:108–110` | `SET NULL` |
| `giro_blocco` | `stazione_da_codice`, `stazione_a_codice` | `models/giri.py:178–180` | `RESTRICT` |
| `depot_linea_abilitata` | `stazione_a_codice`, `stazione_b_codice` | `models/anagrafica.py:141–142` | `RESTRICT` |

**PROBLEMA**:  
PostgreSQL applica `NO ACTION` (equivalente a `RESTRICT`) come default, quindi
il comportamento funzionale è per lo più corretto. Ma: (1) l'intenzione non è
leggibile dal modello ORM; (2) i casi dove `SET NULL` sarebbe semanticamente
corretto (es. `created_by_user_id` su GDPR delete) restano a `RESTRICT` implicito
causando `ConstraintViolation` non documentata.

**FIX CONCRETO**:  
Aggiungere `ondelete=` esplicito a ciascuna FK secondo la tabella sopra. Le FK
`RESTRICT → RESTRICT` non richiedono migration (comportamento invariato, solo
leggibilità). Le FK che cambiano a `SET NULL` richiedono migration `ALTER TABLE`.

---

### I-04 🟠 IMPORTANTE — `GiroMateriale` UniqueConstraint su `(azienda_id, programma_id, numero_turno)` non dichiarato nell'ORM

**FILE**: `backend/src/colazione/models/giri.py:49`

**PROBLEMA**:  
Il commento a riga 49 cita "UNIQUE su (azienda_id, programma_id, numero_turno)" ma
`GiroMateriale` non ha `__table_args__` con `UniqueConstraint`. Il vincolo esiste
nel DB (creato da migration 0010) ma non nel modello ORM. Alembic autogenerate
può rilevare questa discrepanza come "drift" e proporre migrazioni ridondanti.

**FIX CONCRETO**:  

```python
__table_args__ = (
    UniqueConstraint(
        "azienda_id", "programma_id", "numero_turno",
        name="giro_materiale_azienda_id_programma_id_numero_turno_key",
    ),
)
```

---

### I-05 🟠 IMPORTANTE — `AssegnazioneGiornata` senza UniqueConstraint su `(persona_id, data)`

**FILE**: `backend/src/colazione/models/personale.py:52–68`

**PROBLEMA**:  
Senza questo vincolo è possibile inserire due assegnazioni per la stessa persona
nello stesso giorno (doppio turno). La correttezza è delegata interamente al layer
applicativo — se un path manca il controllo, inserisce silenziosamente un doppio.

**FIX CONCRETO**:  

```python
__table_args__ = (
    UniqueConstraint("persona_id", "data",
                     name="uq_assegnazione_giornata_persona_data"),
)
```

Migration necessaria. Verificare pre-migration che non esistano duplicati.

---

### I-06 🟠 IMPORTANTE — `BuilderRun.localita_codice` è VARCHAR senza FK verso `localita_manutenzione`

**FILE**: `backend/src/colazione/models/programmi.py:294`

**PROBLEMA**:  
`BuilderRun.localita_codice` è `Mapped[str] VARCHAR(64)` senza FK verso
`localita_manutenzione.codice`. Se una `LocalitaManutenzione` viene rinominata,
il `BuilderRun` storico diventa un audit trail con sede non più ricercabile.

**FIX CONCRETO**:  

```python
ForeignKey("localita_manutenzione.codice", ondelete="SET NULL")
```

+ colonna diventa nullable (i run storici non si perdono se la sede è eliminata).
Se la semantica voluta è "log string non-referenziale", documentarlo esplicitamente
con un commento nel modello.

---

### I-07 🟠 IMPORTANTE — `TurnoPdcBlocco` check constraint `tipo_evento` non nel modello ORM

**FILE**: `backend/src/colazione/models/turni_pdc.py:97`

**PROBLEMA**:  
Il `CHECK CONSTRAINT turno_pdc_blocco_tipo_check` (14 tipi ammessi dopo migration
0045) esiste solo nel DB. Il modello ORM non ha il `CheckConstraint` in
`__table_args__`. La mancanza si è già rivelata problematica: i tipi MM e VOCTAXI
in MR-PD2 erano stati aggiunti al codice Python ma dimenticati nel DB check —
trovato poi in migration 0045 come "bug latente". Un `CheckConstraint` ORM avrebbe
reso il drift rilevabile da alembic autogenerate al momento dell'aggiunta.

**FIX CONCRETO**:  

```python
__table_args__ = (
    # ... Index già esistente ...
    CheckConstraint(
        "tipo_evento IN ('CONDOTTA','VETTURA','REFEZ','ACCp','ACCa','CVp',"
        "'CVa','PK','SCOMP','PRESA','FINE','DORMITA','MM','VOCTAXI')",
        name="turno_pdc_blocco_tipo_check",
    ),
)
```

---

### I-08 🟠 IMPORTANTE — `normativa_pdc_json` su `Azienda` mai letto dal dominio

**FILE**: `backend/src/colazione/models/anagrafica.py:40`

**PROBLEMA**:  
Il campo `normativa_pdc_json: Mapped[dict[str, Any]]` esiste sul modello `Azienda`
(supporto multi-tenant configurabile). Nessun modulo del dominio o dell'API lo
legge per derivare le costanti normative. Tutte le costanti normative sono
hardcoded nel dominio (NORMATIVA-PDC Trenord). Il campo è dichiarato come
architettura ma non è operativo — nessun test verifica il comportamento con
normative diverse.

**FIX CONCRETO**:  
Questo è un debito architetturale di lunga durata. Nel breve termine:
documentare esplicitamente in `anagrafica.py` che il campo è "reserved for
future multi-tenant normativa config — attualmente non letto dal dominio".
Nel medio termine: il fix D-05 (modulo `normativa_pdc.py`) è il primo
passo — le costanti di quel modulo diventano il punto di injection per i
valori provenienti da `normativa_pdc_json`.

---

### I-09 🟡 MINORE — Migration 0043 dichiara downgrade irreversibile ma non solleva `NotImplementedError`

**FILE**: `backend/alembic/versions/0043_mr_pd2_deposito_pdc_not_null.py:26–27`

**PROBLEMA**:  
La docstring dichiara: "non re-inserisce i turni eventualmente cancellati nello
upgrade (irreversibile)". Ma la funzione `downgrade()` esiste e non lancia
`NotImplementedError`. Un operatore che esegue `alembic downgrade` si ritrova
con `deposito_pdc_id` nullable ma senza i turni cancellati — stato DB parzialmente
degradato silenzioso.

**FIX CONCRETO**:  

```python
def downgrade() -> None:
    raise NotImplementedError(
        "0043 downgrade irreversibile: i turni PdC cancellati nell'upgrade "
        "non sono recuperabili. Ripristinare da backup."
    )
```

---

### I-10 🟡 MINORE — `EXPECTED_TABLE_COUNT` nei test non tiene traccia di `BuilderRun`

**FILE**: `backend/tests/test_models.py:26`

**PROBLEMA**:  
Il commento di tracciamento tabelle riporta "Sprint 8.0 MR-E +2 → 45" ma non
menziona `BuilderRun` (aggiunta in Sprint 7.9). Il numero 45 è corretto ma il
log di accounting è incompleto — chi aggiunge una tabella domani non sa qual è
l'ultima entry valida.

**FIX CONCRETO**:  
Aggiungere l'entry mancante:
```
# Sprint 7.9 MR 11C: +1 (BuilderRun) → 44
# Sprint 8.0 MR-E: +2 → 46
```
(Ricalcolare il conteggio progressivo coerentemente dall'inizio.)

---

### I-11 🟡 MINORE — f-string per costruire SQL raw in `builder_giro/builder.py`

**FILE**: `backend/src/colazione/domain/builder_giro/builder.py:699`

**PROBLEMA**:  
```python
text(f"DELETE FROM giro_materiale {delete_where}")
```

Oggi `delete_where` è sempre hardcoded, quindi non c'è SQL injection. Ma il
pattern è pericoloso per future estensioni: se qualcuno aggiunge un parametro
stringa esterno nella costruzione di `delete_where`, il rischio diventa reale
e invisibile.

**FIX CONCRETO**:  
Riscrivere con SQLAlchemy Core:

```python
stmt = delete(GiroMateriale).where(
    GiroMateriale.programma_id == programma_id,
    *([GiroMateriale.localita_manutenzione_partenza_id == localita_id]
      if localita_id is not None else []),
)
await session.execute(stmt)
```

---

### I-12 🟡 MINORE — `api/giri.py` è un God Object da 4422 righe con logica di dominio inline

**FILE**: `backend/src/colazione/api/giri.py`

**PROBLEMA**:  
Il file contiene 30+ endpoint **e** implementa logica di dominio direttamente:
`riempi_gap` (riga ~1015), `aggrega_modifica` (riga ~1669), `sposta_blocco`
(riga ~2808), `inserisci_corsa_manuale` (riga ~3822). Queste funzioni appartengono
al layer dominio, non al layer API. Il file è il più grande del progetto backend
(4422 righe). La separazione `domain/api/persistence` è un principio dichiarato
dell'architettura (STACK-TECNICO.md).

**FIX CONCRETO**:  
Estrarre la logica di dominio in `domain/builder_giro/operations.py` o simile.
Gli endpoint diventano thin wrapper che chiamano il dominio e serializzano la
risposta. Non è una refactoring da fare in un singolo commit — è il senso della
regola §7 di CLAUDE.md "chiudi bene quello che si comincia".

---

### I-13 🟡 MINORE — `TurnoPdc.is_notturno` flag non persistito come `is_cap_notturno`

(Già coperto come fix preferibile in D-01 — qui si nota che il campo manca nel
modello e che la sua assenza costringe l'API a ricalcolarlo dall'orario.)

**FIX CONCRETO**: Aggiungere `is_cap_notturno BOOLEAN NOT NULL DEFAULT FALSE`
a `TurnoPdcGiornata`, valorizzato dal builder, usato in `turni_pdc.py:947` in
sostituzione del calcolo derivato. Migration semplice.

---

## SEZIONE 3 — Frontend TypeScript/React

---

### F-01 🔴 CRITICO — JWT in `localStorage` — XSS exfiltration in singola riga

**FILE**: `frontend/src/lib/auth/tokenStorage.ts:1–44`

**PROBLEMA**:  
Sia access token che refresh token in `localStorage`. Il commento riconosce il
trade-off ma lo minimizza: "mitigato da CSP + nessun `dangerouslySetInnerHTML`".
In realtà la CSP non impedisce a script già caricati (bundle, CDN compromessa,
dipendenza transitiva) di leggere `localStorage` con una singola riga.

Il refresh token in `localStorage` è il problema più grave: rubarlo permette
di ottenere nuovi access token silenziosamente per tutta la durata del cookie,
senza che l'utente sappia. La giustificazione "futuro Tauri" è architetturale
non realizzata — non mitiga il rischio oggi.

**FIX CONCRETO**:  
- Refresh token → cookie `httpOnly; SameSite=Strict` impostato dal backend in
  `Set-Cookie` alla risposta di login.
- Access token → variabile in-memory (modulo, non `localStorage`):

```typescript
// tokenStorage.ts
let _accessToken: string | null = null;
export function getAccessToken(): string | null { return _accessToken; }
export function setAccessToken(t: string | null): void { _accessToken = t; }
```

Il client `/api/auth/refresh` usa il cookie automaticamente senza esporre il
refresh token a JS. Backend: aggiungere `Set-Cookie` al login endpoint.
Compatibilità Tauri: risolvere separatamente con cookie store della webview.

---

### F-02 🔴 CRITICO — `window.setTimeout` senza `clearTimeout` in `useEffect` — memory leak

**FILE**: `frontend/src/routes/pianificatore-giro/GiroDettaglioRoute.tsx:431–444, 529–542`

**PROBLEMA**:  
Il `useEffect` a riga 416 chiama `window.setTimeout` (350ms) che ne annida
un secondo (3600ms per highlight). Nessuno dei due ha `clearTimeout` nel cleanup.
Se l'utente naviga via durante questi ritardi:
1. `el.classList.add("gantt-blocco-highlight")` viene eseguito su nodo DOM smontato.
2. Il secondo timeout (`3600ms`) chiama `classList.remove` su nodo inesistente.
3. React StrictMode lo esegue due volte, raddoppiando i timeout orfani.

**FIX CONCRETO**:  

```typescript
const timeoutRefs = useRef<number[]>([]);

useEffect(() => {
  const t1 = window.setTimeout(() => {
    const el = document.getElementById(`gantt-blocco-${target}`);
    if (el !== null) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.classList.add("gantt-blocco-highlight");
      const t2 = window.setTimeout(
        () => el.classList.remove("gantt-blocco-highlight"),
        3600
      );
      timeoutRefs.current.push(t2);
    }
  }, 350);
  timeoutRefs.current.push(t1);
  return () => {
    timeoutRefs.current.forEach(window.clearTimeout);
    timeoutRefs.current = [];
  };
}, [searchParams, query.data]);
```

---

### F-03 🟠 IMPORTANTE — `TurnoPdcDettaglioRoute.tsx` 1722 righe — 15+ componenti non estratti

**FILE**: `frontend/src/routes/pianificatore-giro/TurnoPdcDettaglioRoute.tsx:1–1722`

**PROBLEMA**:  
Il file contiene la route principale + `Header`, `DecisioneBuilderBanner`,
`DecisioneRiga`, `Stats`, `Stat`, `Avvisi`, `GanttPdc`, `AxisHeader`,
`GiornataRow`, `Fishbone`, `BloccoSegment`, `CommercialBlock`, `SimpleBlock`,
`Legenda`, `LegendaChip`, `BlocchiPanel`, `TrenoCell`, `StazioneCell`,
`BloccoTipoBadge`, `BloccoDetailDialog`, `DetailField` + 5 funzioni helper.

`GiroDettaglioRoute.tsx` è ancora più grande (4389 righe). Effetti concreti:
diff rumorosi, merge conflict garantiti, tree-shaking impossibile, test in
isolamento impossibili.

**FIX CONCRETO**:  
Estrarre almeno:
- `src/components/gantt/GanttPdc.tsx` (tutto il Gantt + helpers)
- `src/components/gantt/BloccoDetailDialog.tsx`
- `src/components/pdc/BlocchiPanel.tsx`

La route diventa ~200 righe di composizione. Soglia: nessun file route > 600
righe, nessun file componente > 400 righe.

---

### F-04 🟠 IMPORTANTE — `Record<string, unknown>` nei tipi API — equivalente funzionale a `any`

**FILE**: `frontend/src/lib/api/giri.ts:87, 133`

**PROBLEMA**:  
`GiroDettaglio.generation_metadata_json: Record<string, unknown>` e
`GiroBlocco.metadata_json: Record<string, unknown>`. Tutti i consumer fanno cast
`as Record<string, unknown>` (GiroDettaglioRoute:477, :927) o narrowing manuale.
Il compilatore non avverte se il backend cambia la shape, se si usa un nome errato,
se si aggiunge un accesso inesistente. Identico a `any` funzionale.

**FIX CONCRETO**:  
Definire interfacce strutturate:

```typescript
export interface GiroDettaglioMetadata {
  programma_id?: number;
  motivo_chiusura?: string;
  chiuso?: boolean;
  builder_version?: string;
  n_corse_processate?: number;
  [key: string]: unknown;  // escape hatch per campi futuri
}
```

Sostituire `Record<string, unknown>` in `GiroDettaglio` e `GiroBlocco`.
I cast nei consumer diventano non necessari.

---

### F-05 🟠 IMPORTANTE — Pattern `(err as Error).message` — cast non sicuro in 15+ file

**FILE**: `frontend/src/routes/pianificatore-giro/TurnoPdcDettaglioRoute.tsx:97`  
(e ~14 altri file con pattern identico)

**PROBLEMA**:  
Pattern ricorrente:
```typescript
query.error instanceof ApiError ? query.error.message : (query.error as Error).message
```

Se `query.error` è una stringa o un oggetto custom (network error del browser),
`.message` è `undefined` — l'UI mostra `undefined` silenziosamente. Il pattern è
copypastato in almeno 15 file.

**FIX CONCRETO**:  
Helper condiviso in `src/lib/errorMessage.ts`:

```typescript
export function getErrorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  if (typeof err === "string") return err;
  return "Errore sconosciuto";
}
```

Sostituire tutti i `(err as Error).message` con `getErrorMessage(err)`.

---

### F-06 🟠 IMPORTANTE — Auto-refresh 60s in `DashboardRoute` dichiarato ma non implementato

**FILE**: `frontend/src/routes/pianificatore-giro/DashboardRoute.tsx:27–31, 496–499`

**PROBLEMA**:  
Il commento dichiara `refetchInterval=60_000` per tutte le query. La costante
`REFRESH_MS = 60_000` è dichiarata. L'UI mostra "auto-refresh 60s". Ma
`refetchInterval` **non viene mai passato** a nessuna query. A riga 499:
`void REFRESH_MS` per silenziare il TypeScript warning della variabile inutilizzata.
L'etichetta "auto-refresh 60s" nell'UI è **falsa**.

**FIX CONCRETO**:  
Scelta A (implementare): aggiungere `refetchInterval: REFRESH_MS` alle query in
`useProgrammi` e `useGiriAzienda`.  
Scelta B (rimuovere): eliminare `REFRESH_MS`, il `void REFRESH_MS`, e l'etichetta
"auto-refresh 60s" dall'UI. La scelta B è preferibile finché il design non richiede
esplicitamente il polling.

---

### F-07 🟠 IMPORTANTE — `key={idx}` su liste con riordinamento — React mapping instabile

**FILE**: `frontend/src/routes/pianificatore-giro/GanttUnificatoRoute.tsx:285–291` +  
`frontend/src/routes/pianificatore-giro/TurnoPdcDettaglioRoute.tsx:448, 465`

**PROBLEMA**:  
`CorseNonCoperteRow` usa `key={idx}` per array `layeredRows` ricreato con `.sort()`
a ogni render. Se le corse cambiano ordine dopo un refetch, React mappa i vecchi
componenti ai nuovi per posizione, applicando animazioni al componente sbagliato.

**FIX CONCRETO**:  

```tsx
// layeredRows: usare chiave composta stabile
{layeredRows.map((row) => (
  <div key={row.map(c => c.corsa_id).join('-')}>
    {row.map((c) => <button key={c.corsa_id} ...>)}
  </div>
))}

// validazioniCiclo (array di stringhe):
key={`${i}-${v.slice(0, 20)}`}

// frGiornate:
key={fr.giornata}
```

---

### F-08 🟠 IMPORTANTE — Query TanStack senza `staleTime` esplicito — resilienza fragile al config change

**FILE**: `frontend/src/hooks/useTurniPdc.ts:23–62` +  
`frontend/src/hooks/useGiri.ts:61–94`

**PROBLEMA**:  
Le query principali (`useTurnoPdcDettaglio`, `useTurniPdcGiro`, `useGiroDettaglio`,
`useGiriProgramma`, `useTurniPdcAzienda`) non hanno `staleTime` proprio. Ereditano
il globale `staleTime: 30_000` da `queryClient.ts`. Se il default globale viene
abbassato (es. `staleTime: 0` nei test — già fatto in `renderWithProviders.tsx:17`),
queste query diventano iper-reattive su refocus. Per contrasto, `useLineeDistinct`
(`staleTime: 60_000`) e `useSuggerisciDepositi` (`staleTime: 5min`) già lo fanno
correttamente.

**FIX CONCRETO**:  
Aggiungere `staleTime: 60_000` (o `5 * 60_000` per i dettagli) alle 5 query
citate, con commento sul razionale.

---

### F-09 🟠 IMPORTANTE — Nessun codegen OpenAPI — ~50 interfacce TypeScript duplícate a mano

**FILE**: `frontend/` (progetto intero)

**PROBLEMA**:  
`package.json` non include nessun tool di codegen (niente orval, openapi-typescript).
Tutte le ~50 interfacce in `lib/api/` sono scritte a mano e allineate manualmente
con i Pydantic models backend. Con Sprint 8.x in rapida evoluzione, la divergenza
è inevitabile. Un campo rinominato nel backend produce `undefined` lato frontend
silenziosamente perché il tipo frontend ha ancora il vecchio nome.

**FIX CONCRETO**:  

```bash
pnpm add -D openapi-typescript
```

Script in `package.json`:

```json
"generate:api": "openapi-typescript http://localhost:8000/openapi.json -o src/lib/api/generated.ts"
```

I tipi generati diventano fonte di verità. Le interfacce in `lib/api/*.ts`
diventano re-export o wrapper tipizzati su `generated.ts`. Costo: ~2h di
migrazione iniziale. Return: zero divergenze tipo per ogni Sprint futuro.

---

### F-10 🟡 MINORE — `body as T` — cast non verificato del JSON di risposta in `apiJson`

**FILE**: `frontend/src/lib/api/client.ts:175`

**PROBLEMA**:  
`return body as T` senza validazione runtime. Se il backend cambia la shape della
risposta, TypeScript non aiuta a runtime: il componente riceve la shape sbagliata
con errori silenti (`undefined.split(...)`, `NaN` da stringa numerica, ecc.).

**FIX CONCRETO**:  
Step praticabile senza Zod: aggiungere la validazione solo per le risposte di
login/auth (dove un errore di shape blocca l'utente). In prospettiva: `apiJson`
accetta uno schema Zod opzionale.

---

### F-11 🟡 MINORE — Selezione variante hardcoded a 4 opzioni in `InserisciCorsaDialog`

**FILE**: `frontend/src/routes/pianificatore-giro/GanttUnificatoRoute.tsx:519–530`

**PROBLEMA**:  
Il dialog mostra sempre #0, #1, #2, #3 indipendentemente dal numero reale di
varianti del giro. Un giro con 2 varianti mostra #2 e #3 (che il backend
rifiuta con 422). Un giro con 5 varianti non permette di selezionare #4.

**FIX CONCRETO**:  
Aggiungere `max_varianti_per_giornata` (o equivalente) a `GiroListItem` nel
backend, e rendere dinamico il render delle opzioni variante in base a quel valore.

---

### F-12 🟡 MINORE — `handleSubmit` async in onClick senza `void` wrapper — floating promise

**FILE**: `frontend/src/routes/pianificatore-giro/GanttUnificatoRoute.tsx:399`

**PROBLEMA**:  
`onClick={handleSubmit}` con `handleSubmit: async () => Promise<void>`. Se un
errore sincrono avviene prima del `try-catch` interno, la Promise non è gestita
dall'evento DOM.

**FIX CONCRETO**:  

```tsx
<Button onClick={() => { void handleSubmit(); }}>
```

Pattern già corretto in altri punti del codebase (`GiroDettaglioRoute:485`).

---

### F-13 🟡 MINORE — JSDoc orfano attaccato alla funzione sbagliata

**FILE**: `frontend/src/hooks/useGiri.ts:449–461`

**PROBLEMA**:  
Un blocco JSDoc che descrive `useCercaTreno` (Sprint 8.0 MR-1) precede la
definizione di `useInserisciCorsaManuale` dopo un refactoring che ha riposizionato
le funzioni. Chi legge la firma di `useInserisciCorsaManuale` vede un JSDoc che
descrive una funzionalità completamente diversa.

**FIX CONCRETO**:  
Spostare il blocco commento (righe 449–461) direttamente sopra `useCercaTreno`
(riga 485) o rimuoverlo se il JSDoc a riga 485 è già sufficiente.

---

## Appendice — Priorità di intervento

### Da chiudere prima di qualsiasi deploy "stabile"

| # | ID | Gravità | Costo stimato | Motivo urgenza |
|---|----|---------|---------------|----------------|
| 1 | I-01 | 🔴 | 30 min | JWT secret default in prod → token forgiabili |
| 2 | I-02 | 🔴 | 2h | Access token 72h → nessuna revoca utente |
| 3 | D-01 | 🔴 | 1h | Falsi positivi normativi mostrati all'utente |
| 4 | D-04 | 🔴 | 30 min | data_operativa sbagliata → registro vetture errato |

### Sprint successivo (Sprint 8.4 cleanup)

| # | ID | Gravità | Costo stimato | Motivo |
|---|----|---------|---------------|--------|
| 5 | D-02 | 🔴 | 1h | Bug silente: prestazione può superare il cap |
| 6 | D-03 | 🔴 | 2h | Registro vetture over-exclusion sistematica |
| 7 | D-05 | 🔴 | 2h | Costanti normative doppiate — unificare |
| 8 | D-13 | 🟠 | 30 min | Dead code con logica API errata |
| 9 | D-14 | 🟠 | 1h | Preriscaldo non implementato — TODO + implement |
| 10 | F-06 | 🟠 | 15 min | Auto-refresh falso nell'UI |

### Backlog strutturale (non urgenti ma importanti)

| ID | Descrizione |
|----|-------------|
| D-06 | Refactor facade giornata_base — spostare definizioni |
| F-01 | JWT refresh → httpOnly cookie |
| F-02 | clearTimeout in useEffect |
| F-09 | Codegen OpenAPI |
| I-03 | FK ondelete espliciti |
| I-05 | UniqueConstraint AssegnazioneGiornata |
| I-12 | Estrarre dominio da api/giri.py God Object |

---

*Code review eseguita con 3 subagent paralleli specializzati (dominio/builder, modelli/infrastruttura, frontend) + analisi diretta NINO. Nessun file di produzione modificato.*
