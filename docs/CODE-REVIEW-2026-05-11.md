# Code Review COLAZIONE — 2026-05-11

> **Revisore**: NINO (Claude Code) con supporto esplorativo di due subagent.
> **Commit di riferimento**: `6571374` (sprint-8.4 G3 HOTFIX, 2026-05-10).
> **Scope**: backend Python + frontend TypeScript. Nessun fix al codice
> prodotto: questo file è solo la diagnosi.
>
> Struttura: ogni finding cita `file:riga`, causa, impatto, fix concreto
> (codice eseguibile o descrizione precisa), stima di costo.
>
> Precedente review: `docs/CODE-REVIEW-2026-05-01.md` (24 finding Sprint 7.4).

---

## Indice

- [CRITICO](#critico) — 8 finding
- [IMPORTANTE](#importante) — 11 finding
- [MINORE](#minore) — 6 finding
- [Contesto test suite](#contesto-test-suite)

---

## CRITICO

### C1 — JWT access token scade in 72 ore: revoca utente inefficace per quasi 3 giorni

**File**: `backend/src/colazione/config.py:39`

```python
jwt_access_token_expire_min: int = 4320  # 72h
```

**Causa**: 4320 minuti = 72 ore. Un access token compatto (short-lived) dovrebbe
durare 15–60 min. Il commento stesso dice "72h".

**Impatto**: `dependencies.py:18-19` lo ammette esplicitamente: _"se un utente
è disattivato o un ruolo è revocato, il cambio diventa effettivo solo
all'access token successivo (max 72h)"_. Scenari concreti:
- Un operatore licenziato conserva accesso completo fino a 72h dopo la revoca.
- Un token rubato (intercettazione, leak log) vale quasi 3 giorni.
- Non è un MVP trade-off documentato come temporaneo: è un valore di default
  che è rimasto fisso da Sprint 2 senza essere riesaminato.

**Fix**: abbassare a 60 minuti max per produzione:

```python
jwt_access_token_expire_min: int = Field(
    default=60,
    description="Durata access token in minuti. Default=60. In dev alzabile.",
)
```

Il refresh token (30gg) compensa la necessità di non ri-autenticarsi ogni ora.
Costo: 15 min (1 riga + test).

---

### C2 — Nessuna validazione startup che il `JWT_SECRET` non sia il valore di default in produzione

**File**: `backend/src/colazione/config.py:34-36`

```python
jwt_secret: str = Field(
    default="dev-secret-change-me-min-32-characters-long",
    ...
)
```

**Causa**: `pydantic_settings` carica il valore di default se `JWT_SECRET` non
è nella env. Non c'è nessun validator `@field_validator` né check al boot che
impedisca al server di partire con il secret di default.

**Impatto**: se Railway o il deploy dimenticano di settare `JWT_SECRET`, il
backend parte silenziosamente con una chiave pubblica e predicibile. Qualunque
attaccante può forgiare token validi per qualsiasi utente/ruolo.

**Fix**: aggiungere un `model_validator` in `Settings`:

```python
from pydantic import model_validator

@model_validator(mode="after")
def _check_jwt_secret_produzione(self) -> "Settings":
    dev_default = "dev-secret-change-me-min-32-characters-long"
    if not self.debug and self.jwt_secret == dev_default:
        raise ValueError(
            "JWT_SECRET non configurata: valore di default non ammesso "
            "in produzione. Setta JWT_SECRET nell'ambiente."
        )
    if len(self.jwt_secret) < 32:
        raise ValueError("JWT_SECRET deve essere >= 32 caratteri.")
    return self
```

Costo: 30 min.

---

### C3 — `xfail(strict=True)` per violazioni A/C/D post-MR-PD3: i test passano, strict li trasforma in FAIL

**File**: `backend/tests/test_violazioni_normative_pdc.py:79, 119, 161`

```python
@pytest.mark.xfail(
    strict=True,
    reason="MR-PD1 red phase ... Risolto in MR-PD3 builder deposito-first ..."
)
def test_violazione_a_cap_condotta_giornata_non_supera_330min() -> None: ...
```

**Causa**: i 3 test `xfail(strict=True)` descrivono violazioni A, C, D del
builder MVP. MR-PD3 (deposito-first) è stato chiuso in Sprint 8.2 (TN-UPDATE
entry 2026-05-10). I test ora **passano** sul builder deposito-first. Con
`strict=True`, pytest segnala un test che passa come `XPASS` = **FAIL**.
Questo è confermato dall'entry 301 che cita _"50 fallimenti pre-esistenti su
master"_ senza indagarne la causa precisa.

**Impatto**: il test suite è in rosso permanente su `master` per questi tre
test. Ogni `pytest` produce almeno 3 XPASS failures. Il CI (se configurato)
blocca PR a prescindere dalla qualità delle modifiche.

**Fix**:
```python
# Rimuovere i 3 decorator @pytest.mark.xfail(strict=True) e verificare
# che le assert passino. Se passano → decoratori rimossi. Se falliscono
# ancora → builder non ha risolto la violazione per quel path specifico.
```

Costo: 1h (run test + diagnosi + rimozione o sostituzione decorator).

---

### C4 — `registro_vetture.py:240` wild-card `data_operativa=None`: §15.1 violato per eccesso (false exclusions cross-giornata)

**File**: `backend/src/colazione/domain/builder_pdc/registro_vetture.py:238-241`

```python
registro.assegna(
    numero_treno=numero,
    operatore=None,
    data_operativa=None,  # wild card S4 TODO
)
```

**Causa**: `from_db()` registra ogni vettura rientro con `data_operativa=None`
(wild card). Il metodo `is_assegnata()` a riga 106 ritorna `True` se `None in
date_assegnate`. Conseguenza: un treno usato in **qualsiasi turno storico del
programma** viene escluso per **tutte le date future**.

**Impatto**: §15.1 dice "ogni segmento si assegna a UN solo PdC per giornata".
Il wild-card lo interpreta come "un segmento si assegna a UN solo PdC per
SEMPRE". Se il treno R22 8042 è usato come vettura lunedì, martedì non può più
essere assegnato a nessun PdC — violando la normativa in senso inverso (falso
positivo garantito). In un programma con molte giornate, i treni disponibili
per vettura si esauriscono rapidamente.

La funzione `enumera_date_giornata` **esiste già** in
`backend/src/colazione/domain/giornate_concrete.py:40` ed è funzionante
(usata da `riposo_settimanale.py`). Non è stata collegata a `from_db`.

**Fix**: in `from_db()`, per ogni blocco VETTURA letto:
1. Recuperare `TurnoPdcGiornata.numero_giornata` + `variante_calendario` +
   `TurnoPdc.ciclo_giorni` + `ProgrammaMateriale.valido_da/valido_a`.
2. Chiamare `enumera_date_giornata(...)` per ottenere le date concrete.
3. Passare ogni data concreta ad `assegna(data_operativa=data_concreta)`.

Costo: 2h (query join + wiring + test).

---

### C5 — `builder.py:258`: PK creato per qualsiasi gap > 0, inclusi gap di 1 minuto. §4.4 violato.

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:257-270`

```python
gap = _diff(prec.ora_fine, b.ora_inizio)
if gap > 0:
    drafts.append(_BloccoPdcDraft(tipo_evento="PK", durata_min=gap, ...))
```

**Causa**: qualunque gap positivo tra blocchi condotta consecutivi diventa un
blocco PK. Non c'è soglia minima.

**Impatto**: §4.4 stabilisce:
- PK in arrivo: **20 min minimo**.
- PK in partenza: **20 min minimo**.

Un gap di 5 min tra due treni diventa un PK di 5 min, che è fisicamente
impossibile (il PdC non ha tempo di mettere in sicurezza il mezzo e
rientrare). Il builder genera blocchi normativamente invalidi senza segnalarlo.
Attualmente questo non produce violazione visibile perché nessun validatore
controlla la durata minima dei PK.

**Fix** (minimo): aggiungere la violazione al log se `gap < 40`:

```python
if gap > 0:
    if gap < 40:
        violazioni_pk.append(f"pk_troppo_breve:{gap}min<40min_minimo_§4.4")
    drafts.append(_BloccoPdcDraft(tipo_evento="PK", durata_min=gap, ...))
```

Fix completo: non creare PK < 40 min ma segnalare il gap come non coperabile
con PK (il builder deve scegliere CV o ACC in base a §6).

Costo fix minimo: 30 min. Fix completo: 3h (richiede integrazione con §6 logic).

---

### C6 — `builder.py:251-270`: tutti i gap intermedi diventano PK indipendentemente dalla durata. §6 violato.

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:251-270`

**Causa**: il builder MVP usa PK per **tutti** i gap intermedi senza considerare
la soglia di 65 min stabilita da §6.

**Impatto**: per §6:
- Gap **< 65 min** → CV o PK (entrambi ammessi).
- Gap **65–300 min** → ACC (default) o PK.
- Gap **> 300 min** → ACC standard; PK solo se l'operatore opta in.

Il builder attuale usa PK anche per gap di 2h (>300 min) in modo automatico,
violando la regola che il PK sopra 300 min non è automatico. Un gap di
90 min dovrebbe di default generare `ACCa 40min + pausa + ACCp 40min`,
non un monoblocco PK di 90 min che minimizza i tempi di accessorio.

Questo inflaziona artificialmente la produttività calcolata del PdC (meno
minuti di accessori = più condotta apparente = turno "migliore").

**Fix**: in `_build_giornata_pdc`, dopo il calcolo del gap, applicare §6:

```python
if gap >= 65:
    # Default ACC: ACCa 40 al treno precedente + ACCp 40 al successivo
    # Già in coda al blocco prec e in testa al blocco succ → no blocco PK
    # (i 40' vengono tolti dal gap netto disponibile per refezione/buco)
    ...
elif gap > 0:
    # PK (gap < 65 min, PK ammesso per §6)
    if gap < 40:
        ...  # segnalare violazione §4.4
```

Costo: 4h. Richiede refactoring del loop principale di `_build_giornata_pdc`.

---

### C7 — `assegnazione_persone.py:392`: interpolazione costante errata nel warning §11.4

**File**: `backend/src/colazione/domain/normativa/assegnazione_persone.py:388-396`

```python
descrizione=(
    f"{in_finestra} assegnazioni in 7gg "
    f"({finestra_inizio.isoformat()}..{g.data.isoformat()}): "
    f"riposo settimanale §11.4 ≥{RIPOSO_INTRATURNO_MIN_NOTTURNA_H}"
    "h non rispettabile"
),
```

**Causa**: `RIPOSO_INTRATURNO_MIN_NOTTURNA_H = 16` (ore riposo intraturno
notturno). Il messaggio genera: `"riposo settimanale §11.4 ≥16h non
rispettabile"`. Il riposo settimanale §11.4 è **62h**, non 16h.

**Impatto**: il messaggio di warning è palesemente sbagliato. Un operatore che
lo legge pensa che bastino 16h di riposo settimanale. Il bug non impatta la
logica (il check usa `SOGLIA_WARNING_RIPOSO_SETTIMANALE = 6 assegnazioni`
come proxy corretto) ma corrompe completamente la diagnostica.

**Fix**:
```python
# Aggiungere costante dedicata
RIPOSO_SETTIMANALE_MIN_H = 62  # §11.4

# Nella descrizione:
f"riposo settimanale §11.4 ≥{RIPOSO_SETTIMANALE_MIN_H}h non rispettabile"
```

Costo: 5 min.

---

### C8 — `updated_at` senza `onupdate`: timestamp stale su ogni record modificato

**File**: `backend/src/colazione/models/turni_pdc.py:59`,
`backend/src/colazione/models/giri.py:79`,
`backend/src/colazione/models/programmi.py:187`

```python
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), server_default=func.now()
)
```

**Causa**: `server_default=func.now()` imposta `updated_at` solo all'INSERT.
Non c'è `onupdate=func.now()` (SQLAlchemy ORM) né trigger Postgres.

**Impatto**: ogni record modificato ha `updated_at == created_at` per sempre.
Qualunque logica che usa `updated_at` per invalidare cache, rilevare
modifiche recenti o ordinare per "ultima modifica" restituisce dati errati.
In produzione oggi questo significa che la UI non può distinguere record
vecchi da quelli appena aggiornati.

**Fix**: aggiungere `onupdate` a livello ORM:

```python
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
    onupdate=func.now(),
)
```

Oppure via migration, trigger Postgres:
```sql
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;
```

Il trigger è più robusto (copre anche UPDATE diretti via SQL non ORM).

Costo: 30 min + migration.

---

## IMPORTANTE

### I1 — `giornata_base.py` importa i simboli `_xxx` privati di `builder.py` direttamente

**File**: `backend/src/colazione/domain/builder_pdc/giornata_base.py:48-57`

```python
from colazione.domain.builder_pdc.builder import (
    ...
    _aggiungi_dormite_fr,
    _BloccoPdcDraft,
    _build_giornata_pdc,
    ...
)
```

**Causa**: la rationale del modulo è "re-exportare i simboli privati con nomi
pubblici". Ma il modulo **continua a importare i nomi `_xxx`**, mantenendo la
dipendenza dal contratto privato. Il SEVERO finding S2 che ha motivato questo
modulo chiedeva di **rompere** la dipendenza dai privati — non di indirettarla.

**Impatto**: se `builder.py` rinomina `_BloccoPdcDraft` → `_BloccoInterno`, il
facade `giornata_base.py` rompe esattamente come prima. L'anti-pattern non è
stato risolto, è stato spostato di un livello. I consumatori
(`multi_turno.py`, `deposito_first.py`) ora dipendono dai nomi **pubblici** del
facade, ma il facade stesso è fragile quanto prima.

**Fix**: spostare la definizione dei tipi `_BloccoPdcDraft`, `_GiornataPdcDraft`
e le funzioni core **dentro** `giornata_base.py` (o in un modulo
`types_pdc.py`), ed importarle da lì in `builder.py`. Il facade diventa la
sorgente, non il riflesso.

Costo: 3h (refactoring + verifica import circolari).

---

### I2 — `STAZIONI_CV_DEROGA` hardcoded: §9.2 capolinea non coperto dinamicamente

**File**: `backend/src/colazione/domain/builder_pdc/split_cv.py:61`

```python
STAZIONI_CV_DEROGA: frozenset[str] = frozenset({"MORTARA", "TIRANO"})
```

**Causa**: §9.2 riconosce CV in tre categorie: (1) sede deposito PdC, (2)
MORTARA come deroga esplicita, (3) **"stazione di capolinea dove il treno
inverte il senso di marcia"**. Il caso (3) è dinamico (dipende dal giro
materiale) e non è coperto dalla lista statica.

**Impatto**: un giro che capovolge a LECCO o COLICO (stazioni con inversione
reale) non ammetterà CV lì se queste non sono anche depositi PdC. Un operatore
non può spezzare quel treno in una stazione capolinea legittima.

**Fix** (architetturale): aggiungere al `GiroMateriale` o `GiroBlocco` un
campo `is_inversione: bool`. La funzione `lista_stazioni_cv_ammesse` legge le
stazioni con `is_inversione=True` nel giro corrente e le aggiunge al set:

```python
stazioni_inversione = {b.stazione_da_codice for b in blocchi_giro if b.is_inversione}
stazioni.update(STAZIONI_CV_DEROGA)
stazioni.update(stazioni_inversione)
```

Costo: 4h (migration + campo + logica builder giro + test).

---

### I3 — `giro_blocco_id` con `ondelete="SET NULL"`: §15.2 pool tracking rotto alla cancellazione

**File**: `backend/src/colazione/models/turni_pdc.py:104-106`

```python
giro_blocco_id: Mapped[int | None] = mapped_column(
    BigInteger, ForeignKey("giro_blocco.id", ondelete="SET NULL")
)
```

**Causa**: se un `GiroBlocco` viene cancellato, il campo `giro_blocco_id` del
blocco PdC viene silenziosamente nullato.

**Impatto**: dopo una cancellazione, il `TurnoPdcBlocco` esiste senza collegamento
al segmento sorgente. È impossibile determinare quali segmenti del giro sono già
coperti. §15.2 richiede di tracciare la pool di segmenti usati — con
`giro_blocco_id=NULL` il tracking è perso. In più, i blocchi orfani non vengono
mai ripuliti.

**Fix**: valutare `ondelete="RESTRICT"` per impedire la cancellazione di un
blocco giro se ha turni PdC associati, oppure `ondelete="CASCADE"` se la
semantica corretta è "se cancello il blocco giro, cancello anche il blocco PdC
figlio". `SET NULL` è la scelta peggiore perché crea dati parzialmente validi.

Costo: 30 min (migration + decisione semantica).

---

### I4 — `operatore_treno_vettura` referenziato nel codice ma assente dal modello e dalle migrazioni

**File**: `backend/src/colazione/domain/builder_pdc/registro_vetture.py:232-236`

```python
# Operatore non recuperato dal DB MVP: chiave wild su
# operatore (None). Quando la migration aggiungerà
# operatore_treno_vettura, questo sarà raffinato.
registro.assegna(numero_treno=numero, operatore=None, ...)
```

**Causa**: il campo `TurnoPdcBlocco.operatore_treno_vettura` è anticipato
nel commento ma non esiste né nel modello (`turni_pdc.py`) né in nessuna
migration.

**Impatto**: §15.1 richiede unicità per `(numero_treno, data)`. Con
`operatore=None`, il registro non distingue "treno 2425 Trenord" da "treno
2425 TILO" — possono avere lo stesso numero. Un falso clash esclude un treno
lecito. La robustezza del registro è degradata finché il campo non esiste.

**Fix**:
1. Aggiungere migration `0047_numero_operatore_treno_vettura.py`:
   ```sql
   ALTER TABLE turno_pdc_blocco
   ADD COLUMN operatore_treno_vettura VARCHAR(20);
   ```
2. Aggiungere campo al modello.
3. Aggiornare `from_db()` per leggere e usare l'operatore.

Costo: 2h (migration + modello + logica `from_db`).

---

### I5 — `builder_giro/builder.py:2757-2758`: dead code `festivita` e `calcola_etichetta_giro` soppressi con noqa

**File**: `backend/src/colazione/domain/builder_giro/builder.py:2752-2758`

```python
_ = festivita  # noqa: F841 (reservato per uso futuro)
_ = calcola_etichetta_giro  # noqa: F841 (export pubblico mantenuto)
```

**Causa**: `festivita` viene caricata via query (linea ~1671) ma non viene
passata alla pipeline `ParamPipelineLineaCentrica`. `calcola_etichetta_giro`
è importata ma mai usata nell'orchestrator.

**Impatto**: il DB subisce una query non necessaria per ogni generazione giri
(overhead minimo ma semanticamente sbagliato). Il codice è confuso: un lettore
si aspetta che `festivita` venga usata ma non capisce dove.

**Fix**:
- Se `festivita` deve essere passata a `ParamPipelineLineaCentrica` ma non è
  ancora implementata: aggiungere il campo a `ParamPipelineLineaCentrica` e
  propagarlo (costo 1h).
- Se non serve ancora: **non caricarla** (rimuovere la query, tenere il campo
  nel struct per quando servirà). Costo: 15 min.
- `calcola_etichetta_giro`: se non usata dall'orchestrator, non importarla qui.
  Se deve restare esposta come API pubblica del modulo, spostarla nel `__all__`
  senza importarla in questo file. Costo: 5 min.

---

### I6 — `bare except Exception` in builder_giro/builder.py: errori di programmazione inghiottiti silenziosamente

**File**: `backend/src/colazione/domain/builder_giro/builder.py:1664, 1690`

```python
try:
    dotazione_obj = await carica_dotazione_per_azienda(...)
except Exception as exc:  # noqa: BLE001
    warnings.append(f"Carica dotazione fallita ({exc}); capacity check skippato.")
    dotazione_per_materiale = {}
```

**Causa**: `BLE001` (blind-except) è soppressa. Un `AttributeError` o
`TypeError` interno a `carica_dotazione_per_azienda` viene catturato e
trasformato in un warning, producendo il builder con `dotazione={}` (capacity
check disattivato silenziosamente).

**Impatto**: se c'è un bug nel codice di caricamento dotazione, non viene mai
visto in produzione. Il builder gira felicemente assegnando materiale anche
quando la dotazione ha dato errore. L'utente vede solo un warning oscuro nei
log.

**Fix**: catturare solo le eccezioni attese (es. `sqlalchemy.exc.SQLAlchemyError`
per errori DB):

```python
from sqlalchemy.exc import SQLAlchemyError

try:
    dotazione_obj = await carica_dotazione_per_azienda(...)
except SQLAlchemyError as exc:
    warnings.append(f"Carica dotazione fallita ({exc}); capacity check skippato.")
    dotazione_per_materiale = {}
```

Errori di programmazione (TypeError, AttributeError) risalgono e diventano
visibili. Idem per la riga 1690 (lookup durate vuoto).

Costo: 15 min × 2.

---

### I7 — `vettura_resolver.py:281`: bare except in resolver live.arturo.travel

**File**: `backend/src/colazione/domain/builder_pdc/vettura_resolver.py:281`

```python
except Exception as e:  # noqa: BLE001
```

**Causa**: stessa classe di problema di I6 ma in un punto ancora più critico:
il resolver che chiama l'API live. Un `AttributeError` sul parsing della risposta
HTTP viene catturato e trattato come "nessuna vettura trovata".

**Impatto**: un bug nel parsing della risposta API si traduce silenziosamente
in `vettura=None` → DORMITA, non in un errore visibile. Il builder sceglie
dormita anche quando la vettura esiste perché c'è un bug di codice.

**Fix**: catturare `httpx.HTTPError | httpx.TimeoutException` e fare log
esplicito per le eccezioni impreviste:

```python
except (httpx.HTTPError, httpx.TimeoutException) as e:
    logger.warning("vettura_resolver: timeout/HTTP error: %s", e)
    return None
except Exception as e:
    logger.error("vettura_resolver: errore imprevisto (bug?): %s", e, exc_info=True)
    return None
```

Costo: 20 min.

---

### I8 — Nessun indice su `turno_pdc_giornata.turno_pdc_id`

**File**: `backend/src/colazione/models/turni_pdc.py`

`TurnoPdc` → `TurnoPdcGiornata` è il join più frequente del builder PdC.
`TurnoPdcGiornata` non ha indice esplicito su `turno_pdc_id`.

PostgreSQL crea automaticamente l'indice sulle FK solo per PRIMARY KEY, non per
FK verso tabelle padre. Senza indice, ogni `JOIN turno_pdc_giornata ON
turno_pdc_id = ?` fa sequential scan sulla tabella giornate.

**Fix**: aggiungere migration:
```python
# 0047_ix_turno_pdc_giornata_turno_pdc_id.py
op.create_index("ix_turno_pdc_giornata_turno_pdc_id", "turno_pdc_giornata", ["turno_pdc_id"])
```

Costo: 15 min.

---

### I9 — `multi_turno.py`: magic numbers nelle finestre di ricerca vettura

**File**: `backend/src/colazione/domain/builder_pdc/multi_turno.py:426, 432, 441, 459, 460`

```python
ora_min_partenza_mattutina = (ora_apertura_min - 6 * 60) % (24 * 60)
max_attesa_min=6 * 60,
vettura_serale = await trova_treno_vettura(
    ora_min_partenza=19 * 60,   # non prima delle 19:00
    max_attesa_min=4 * 60 + 30, # finestra fino alle 23:30
    ...
)
```

**Causa**: le finestre orarie di ricerca vettura (6h prima apertura, 19:00 minimo
serale, 23:30 massimo) sono inline senza costanti nominate.

**Impatto**: non sono autocondocumentanti per chi modifica il file. La regola
"non prima delle 19:00" è una decisione operativa (entry 449) che deve essere
cambiabile senza cercare a naso nei numeri.

**Fix**: estrarre costanti di modulo:
```python
VETTURA_MATTUTINA_BUFFER_MIN: Final[int] = 6 * 60     # 6h prima apertura
VETTURA_MATTUTINA_MAX_VIAGGIO_MIN: Final[int] = 6 * 60
VETTURA_SERALE_INIZIO_MIN: Final[int] = 19 * 60        # non prima delle 19:00
VETTURA_SERALE_MAX_VIAGGIO_MIN: Final[int] = 4 * 60 + 30  # fino alle 23:30
```

Costo: 10 min.

---

### I10 — `riposo_intraturno.py:44-52`: collasso 14h → 16h non documentato in `NORMATIVA-PDC.md`

**File**: `backend/src/colazione/domain/builder_pdc/riposo_intraturno.py:44-52`

```python
#: NB Sprint 8.2 SEVERO post-Sprint S2 (entry 285 → decisione utente
#: cautelativa entry 286): NORMATIVA-PDC §11.5 letterale distinguerebbe
#: fascia [00:01-01:00] = 14h dalla [00:01-05:00] notturna = 16h. La
#: scelta cautelativa adottata è **applicare 16h sempre nell'intera
#: fascia [00:01-05:00]**.
RIPOSO_INTRATURNO_NOTTURNO_MIN: int = 16 * 60  # 16h
```

**Causa**: §11.5 normativa riconosce esplicitamente il caso 14h (fine giornata
00:01-01:00). Il codice lo collassa nel caso 16h per "cautelatività", per
decisione utente entry 286. La decisione è nel codice ma non nel documento
fonte della verità `NORMATIVA-PDC.md`.

**Impatto**: `NORMATIVA-PDC.md` è il riferimento per futuri sviluppatori e per
validazioni esterne. Dice 11h/14h/16h. Il codice fa 11h/16h. Chi legge solo
il doc pensa che il codice implementi 14h ma in realtà applica 16h anche nel
caso 14h. Divergenza silenziosa tra doc e implementazione.

**Fix**: aggiungere nota a `NORMATIVA-PDC.md §11.5`:
```markdown
**Implementazione attuale (decisione cautelativa 2026-05-10, entry 286)**:
il builder applica 16h per tutta la fascia [00:01-05:00], collassando
il caso 14h nel più restrittivo 16h. Questa scelta è conservativa
rispetto alla normativa letterale. Se serve la distinzione per
ottimizzazione, questa è la riga da modificare nel builder.
```

Costo: 10 min (doc only).

---

### I11 — `test_violazioni_normative_pdc.py` importa simbolo privato `_build_giornata_pdc`

**File**: `backend/tests/test_violazioni_normative_pdc.py:29-31`

```python
from colazione.domain.builder_pdc.builder import (
    CONDOTTA_MAX_MIN,
    _build_giornata_pdc,
)
```

**Causa**: il test accede direttamente a `_build_giornata_pdc` (simbolo privato).
Il refactoring della giornata_base (I1) cambierebbe la firma o il percorso di
questa funzione, rompendo il test.

**Fix**: importare da `giornata_base` usando il nome pubblico `build_giornata_pdc`:

```python
from colazione.domain.builder_pdc.giornata_base import (
    CONDOTTA_MAX_MIN,
    build_giornata_pdc,
)
```

Costo: 2 min.

---

## MINORE

### M1 — `builder.py:1` docstring "Sprint 7.2" stale

**File**: `backend/src/colazione/domain/builder_pdc/builder.py:1`

Il modulo docstring dice _"Builder MVP del turno PdC — Sprint 7.2"_ ma è stato
significativamente modificato in Sprint 7.4, 7.9, 8.2 (SEVERO fix). La data
è fuorviante per chi legge.

**Fix**: aggiornare docstring con ultima sprint significativa o rimuovere il
numero di sprint (che è info da commit history, non da docstring).

Costo: 2 min.

---

### M2 — `builder_giro/builder.py` usa `2**31 - 1` come "infinito"

**File**: `backend/src/colazione/domain/builder_giro/builder.py:145-146`
(valore `SPECIFICITY_WILDCARD`)

`2**31 - 1` è MAX_INT32 ma Python non ha un tipo int32. Il valore corretto per
"infinity sentinel" è `sys.maxsize` o `math.inf` (cast a int per il confronto).

**Fix**:
```python
import sys
SPECIFICITY_WILDCARD: Final[int] = sys.maxsize
```

Costo: 2 min.

---

### M3 — `varianti_calendariali.py:293` dead import `Counter` soppressa

**File**: `backend/src/colazione/domain/builder_giro/varianti_calendariali.py:293`

```python
_ = Counter  # noqa: F841 — riservato per estensioni
```

`Counter` è importato ma non usato. Tenere un import "per uso futuro" è
anti-pattern (YAGNI): inquina il modulo e confonde i linter.

**Fix**: rimuovere import e la riga `_ = Counter`.

Costo: 1 min.

---

### M4 — `giri.py:917` silencing `determina_giorno_tipo` inutilizzato

**File**: `backend/src/colazione/api/giri.py:917`

```python
_ = determina_giorno_tipo  # silence "unused" del linter
```

Stessa classe di M3: funzione importata ma non usata, soppressa invece di rimossa.

**Fix**: rimuovere import o usarlo. Costo: 1 min.

---

### M5 — `test_riposo_settimanale.py` usa date hardcoded senza commento sul giorno della settimana

**File**: `backend/tests/test_riposo_settimanale.py:51-56`

```python
datetime(2026, 3, 7, 14, 0)  # sabato — ma non è dichiarato nel test
datetime(2026, 3, 9, 9, 0)   # lunedì
```

I test dipendono dal fatto che 2026-03-07 sia sabato. Non è esplicitato.
Un futuro lettore o copier del test può cambiare la data e rompere la semantica
senza saperlo.

**Fix**: aggiungere commento inline `# sabato` o usare
`date(2026, 3, 7)  # weekday() == 5 (sabato)`.

Costo: 2 min.

---

### M6 — Frontend: nessun `ErrorBoundary` sulle route

**File**: `frontend/src/routes/AppRoutes.tsx`

Nessuna `<ErrorBoundary>` avvolge le route figlie. Un `TypeError` runtime in
qualunque componente causa il crash dell'intera app (schermata bianca), senza
messaggio d'errore leggibile dall'utente.

**Fix**: avvolgere ogni route con un `ErrorBoundary` React (anche minimale):

```tsx
<Route path="..." element={
  <ErrorBoundary fallback={<p>Errore nel caricamento</p>}>
    <ComponenteRoute />
  </ErrorBoundary>
} />
```

Costo: 1h (implementazione ErrorBoundary + wrapping tutte le route).

---

## Contesto test suite

**50 fallimenti pre-esistenti su `master`** (confermato TN-UPDATE entry 301):

I finding C3 (3 xfail XPASS) sono probabilmente 3 dei 50. Gli altri 47 non
sono stati investigati in questa review. Prima di qualunque lavoro sul test
suite, eseguire:

```bash
cd backend && uv run pytest --tb=no -q 2>&1 | grep "FAILED\|ERROR" | sort | uniq
```

e classificare i fallimenti per categoria (import error, xpass, assert failure,
fixture DB failure). Il CI è attualmente inutilizzabile come gate di qualità
finché questi 50 non vengono risolti o marcati esplicitamente come `skip` con
motivazione tracciata.

---

## Riepilogo

| ID | Gravità | File:riga | Costo stimato |
|----|---------|-----------|---------------|
| C1 | CRITICO | `config.py:39` | 15 min |
| C2 | CRITICO | `config.py:34` | 30 min |
| C3 | CRITICO | `test_violazioni_normative_pdc.py:79,119,161` | 1h |
| C4 | CRITICO | `registro_vetture.py:240` | 2h |
| C5 | CRITICO | `builder.py:258` (§4.4) | 30 min–3h |
| C6 | CRITICO | `builder.py:251-270` (§6) | 4h |
| C7 | CRITICO | `assegnazione_persone.py:392` | 5 min |
| C8 | CRITICO | `turni_pdc.py:59` + 2 altri | 30 min |
| I1 | IMPORTANTE | `giornata_base.py:48-57` | 3h |
| I2 | IMPORTANTE | `split_cv.py:61` | 4h |
| I3 | IMPORTANTE | `turni_pdc.py:104-106` | 30 min |
| I4 | IMPORTANTE | `registro_vetture.py:232-236` | 2h |
| I5 | IMPORTANTE | `builder_giro/builder.py:2757-2758` | 15–60 min |
| I6 | IMPORTANTE | `builder_giro/builder.py:1664,1690` | 30 min |
| I7 | IMPORTANTE | `vettura_resolver.py:281` | 20 min |
| I8 | IMPORTANTE | `turni_pdc.py` (no index) | 15 min |
| I9 | IMPORTANTE | `multi_turno.py:426,459` | 10 min |
| I10 | IMPORTANTE | `riposo_intraturno.py:44-52` | 10 min |
| I11 | IMPORTANTE | `test_violazioni_normative_pdc.py:29-31` | 2 min |
| M1 | MINORE | `builder.py:1` | 2 min |
| M2 | MINORE | `builder_giro/builder.py:145` | 2 min |
| M3 | MINORE | `varianti_calendariali.py:293` | 1 min |
| M4 | MINORE | `giri.py:917` | 1 min |
| M5 | MINORE | `test_riposo_settimanale.py:51` | 2 min |
| M6 | MINORE | `AppRoutes.tsx` | 1h |

**Critico con impatto normativo diretto (§ NORMATIVA-PDC)**:
- C4 → §15.1 (unicità vetture cross-giornata violata per eccesso)
- C5 → §4.4 (PK minimo 20 min non rispettato)
- C6 → §6 (PK per gap >65 min senza ACC: default normativo violato)
- C7 → §11.4 (messaggio diagnostico con valore sbagliato: 16h invece di 62h)

**Finding NON presenti** (verificati sani):
- Costanti normative (PRESTAZIONE_MAX, CONDOTTA_MAX, REFEZIONE_*): tutte corrette.
- Cap prestazione notturno §11.8 (is_cap_notturno vs is_notturno): corretto da Sprint 8.2 SEVERO S1.
- Auth endpoint coverage: tutti i router usano `require_role` / `require_any_role`.
- SQL injection: SQLAlchemy parametrizza tutto, nessun `.execute(raw_string)`.
- CORS: configurato con lista esplicita, non wildcard.
- Async/sync mixing: AsyncSession usato ovunque, nessun blocking call in handler.
