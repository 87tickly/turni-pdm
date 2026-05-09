# Critica SEVERO — MR-D5h-bis + MR-D6 + fix migration 0046 (chiusura ciclo Plan-D)

**Data**: 2026-05-10
**Commit / range**: `a0cf6d3` (MR-D5h-bis: builder.py +112/-15, +5 test
+2 xfail), `c2e6fc9` (MR-D6: aggregazione_linea_centrica.py +111/-4,
+5 test), `40b64f5` (fix migration 0046 alembic revision ID univoco,
+2/-2). Diff cumulativo: +370/-15 in 3 file logici + 1 file migration
+ 2 file test.
**Entry TN-UPDATE**: 284 (chiusura ciclo), 283 (deploy success
post-fix migration), 278 (critica precedente 6/10\*).
**Motore usato**: ⚠️ AMILCARE V4 Pro NON disponibile in sessione
corrente: 3 timeout `-32001` consecutivi su `mcp__amilcare__reason`
con brief 4KB → 2KB → 1KB. Fallback su AMILCARE V4 Flash (motore
`mcp__amilcare__code`, V3-chat) operativo: 1 invocazione riuscita
con brief ~3KB. Output AMILCARE V4 Flash filtrato (2 falsi positivi
identificati e dichiarati: F4 numero_treno e F6 colpa migration). Voto
**provvisorio con asterisco** perché V4 Flash non equivale a V4 Pro
in profondità di ragionamento (margine atteso ~1 punto più severo
con V4 Pro).

---

## Sintesi (3 righe max)

Il ciclo MR-D5h-bis + MR-D6 chiude **operativamente** i 2 finding
sostanziali della critica entry 278 (S1 HIGH "tutti ETR204" + S4
MED "modalità sede silente") e produce le metriche promesse (chiusi
3→7/11, materiali 1→2 distinti, 4 ETR526 + 7 ETR204), ma **non
riesce a saltare il tetto strutturale 6/10\***: rimangono 4/11 giri
non_chiusi multi-giornata, una stima durata vuoto 60 min hardcoded
fragile per scenari distanti (LECCO-FIO ~80km plausibile, TIRANO-FIO
~190km no), un magic number `2**31 - 1` senza costante, e 2 test
`xfail strict` che sono **spec di MR futuri travestiti da test**
(non esercitano il codice corrente, fanno hasattr su attributi
inesistenti). **Voto provvisorio fallback: 5/10\*** (-1 vs critica
precedente 6/10\*, perché 2 finding chiusi onestamente ma 3 nuovi
finding emergono dal codice scritto + recidiva pattern "scope-cutting
silente con etichetta MR-D7").

---

## Cosa funziona

- **Diagnosi DB-first finalmente applicata pre-MR-D5h-bis** (entry
  284 dichiara: query SQL su prog 17 ha rivelato `priorita=60` su
  tutte le 7 regole come root cause). NINO ha applicato la
  raccomandazione R-PROC-4 della critica precedente *prima* di
  scrivere il fix, non dopo. Pattern corretto, da formalizzare.
- **5 test S1 collisione regole ben strutturati**
  (`test_builder_linea_centrica_loader.py:316-557`): caso felice
  specifica vince ampia, ordine input irrilevante (test 363
  cattura proprio il bug pre-MR-D5h-bis = last-write per id), tie-break
  id minore, `codice_linea` diretto vs `direttrice` ampia, scenario
  prog 17 reale simulato. Branch coverage del helper `_conta_linee_regola`
  + `_costruisci_mappature_regole_linee` solida.
- **5 test MR-D6 ben strutturati**
  (`test_aggregazione_linea_centrica.py:436-562`): caso felice (vuoto
  chiude giro), no-op se target=operativa, vuoto solo ultima
  giornata di 2 (test 488 = il caso che proprio limita 4/11 residui),
  backward-compat legacy invariato (test 519), defensive stazione
  target assente (test 539). Pattern parametrico + edge case
  adeguato per un MR di questa complessità.
- **Fix migration 0046 chirurgico e onesto**
  (`backend/alembic/versions/0046_*.py:revision`): bug NON di NINO,
  scoperto durante deploy, risolto in 1 commit minimale (revision
  ID univoco `c8d9e0f1a2b3` confermato con `alembic heads`). Entry
  283 dichiara apertamente "errore mio in entry 279 (MR-PD-FIX-SEVERO
  3b)". Regola §4 METODO ammettere l'errore rispettata.
- **Onestà operativa nell'entry 284**: limitazioni dichiarate
  apertamente (4/11 residui multi-giornata, 60 min "raffinabile
  MR-D7", filtri categoria-only xfail S5, granularità warning
  xfail S6). Niente claim "Plan-D tutto risolto".
- **Modalità degradata trasparente** (`builder.py:1503-1534` +
  schema response MR-D5h-bis FASE B): `BuilderResult.modalita_sede:
  str | None` con valori `'normale'` / `'degradata_single_sede'`
  esposto in `BuilderResultResponse`. Chiude S7 LOW entry 275 +
  S4 MED entry 278 (recidiva 2 critiche). Costo dichiarato ~30
  min, fix scrivibile in finestra del MR di follow-up = NINO
  finalmente ha smesso di posporre LOW.

---

## Cosa si poteva fare meglio

### S1 — MED — Magic number `2**31 - 1` per wildcard specificity senza costante simbolica

- **Severità**: MED
- **Dove**: `backend/src/colazione/domain/builder_giro/builder.py:1296`
  (return) + `:1268` (docstring) + `:1376-1378` (commento sort)
- **Cosa**: il helper `_conta_linee_regola` ritorna `2**31 - 1`
  per le regole "wildcard" (= no filtro linea/direttrice, es. solo
  `categoria=R`). Il valore è hardcoded inline, ripetuto in
  docstring + commento + return statement. Nessuna costante
  simbolica, nessun import da `sys.maxsize`, nessun `Final`.
- **Perché è un problema**:
  - **Leggibilità**: un lettore che vede `return 2**31 - 1` deve
    inferire la semantica dal contesto. Non è ovvio che sia un
    "infinito convenzionale" per ordinamento. Un nome simbolico
    (`SPECIFICITY_WILDCARD = 2**31 - 1` con commento) lo
    renderebbe ovvio.
  - **Fragilità**: se domani qualcuno cambia il valore (es. a
    `2**32 - 1` per supportare 64-bit) o lo refactora in
    `sys.maxsize`, deve cercare 3 occorrenze testuali, una nel
    docstring (non eseguibile = difficile da catturare con
    grep). Una costante = una fonte di verità.
  - **Non è un bug oggi**, ma è exactly il tipo di odore di
    codice che un senior nota in code review.
- **Fix proposto**: definire `SPECIFICITY_WILDCARD: Final[int] =
  2**31 - 1` come module-level constant in `builder.py` (sopra
  `_conta_linee_regola`) con commento "Score per regole wildcard
  senza filtro linea/direttrice: in fondo all'ordine specificity
  ASC". Sostituire 2 occorrenze (return + commento) + sostituire
  riferimento testuale in docstring con `:py:data:`SPECIFICITY_WILDCARD``.
- **Costo del fix**: 5 minuti, zero side-effects.

### S2 — HIGH — Stima durata vuoto rientro 60 min hardcoded fragile per scenari distanti

- **Severità**: HIGH (sale da MED a HIGH per impatto operativo
  realistico)
- **Dove**: `backend/src/colazione/domain/builder_giro/aggregazione_linea_centrica.py:96`
  (default param) + `:110-122` (docstring) + `:134` (uso interno
  `arrivo_min + durata_min_default`)
- **Cosa**: `_costruisci_vuoto_rientro_target(giornata,
  stazione_target, *, durata_min_default: int = 60)` accetta la
  durata come parametro keyword con default 60 min. **Il parametro
  NON viene mai passato dal chiamante** (`_costruisci_catena_posizionata:
  176-179` chiama senza override → fissa a 60 min in produzione).
  Stima identica per ogni scenario:
  - LECCO → FIORENZA ~80 km, 60 min plausibile (treno ~80 km/h media)
  - TIRANO → FIORENZA ~190 km, 60 min **drasticamente sotto**
    (~2h reali di percorrenza materiale vuoto)
  - SONDRIO → CADORNA ~140 km, 60 min sottostimato di ~30-40 min
- **Perché è un problema**:
  - **Bug silente per scenari distanti**: il vuoto_coda parte
    alle 16:00 e finisce alle 17:00. Se la realtà è 18:00, il
    Gantt mostra una giornata fittiziamente più corta di 1h. Il
    pianificatore non se ne accorge perché il giro chiude
    "naturale" e il blocco dura come dichiarato. Ma quando
    arriverà la fase assegnazione PdC (turno_pdc), la prestazione
    risulterà sotto-vincolata di 1h.
  - **Memoria progetto `project_dotazione_trenord` + matrice
    direttrice→materiale Trenord**: ogni materiale ha velocità
    media nota (ETR526 = 160 km/h, ATR125 = 90 km/h). Il dato
    esiste già nel sistema. Ignorarlo = scrivere logica
    sbagliata quando i dati sono lì.
  - **Pattern recidiva di "feature implementata a metà"**
    (CLAUDE.md §7 esempio letterale "calcolo stimato approssimativo,
    vero calcolo in futuro"). NINO dichiara entry 284: "raffinare
    con km/velocità reali (MR-D7)". Test del residuo §7: il
    raffinamento è scrivibile in <2h? Sì:
    - Helper `_durata_vuoto_stimata(stazione_origine, stazione_destinazione,
      materiale_tipo_codice) -> int` con tabella distanze (può
      stare in `data/`).
    - Fallback 60 min se distanza non in tabella (= comportamento
      attuale come safety).
    - 3-5 test parametrici (LEC→FIO, TIR→FIO, SO→CAD,
      LEC→FIO con materiale lento, fallback).
  - Costo stimato: 1.5-2h. **Soglia §7 NIENTE PIGRIZIA violata
    letteralmente** (entry 284 dichiara "scope MR-D7" senza
    motivazione oggettiva = è scope-cutting).
- **Fix proposto**:
  1. Helper privato `_durata_vuoto_stimata` con tabella distanze
     pre-popolata dalle 25 stazioni operative principali Trenord
     (memoria `project_stazione_collegata_localita`).
  2. Velocità media per `materiale_tipo_codice` da
     `dotazione_trenord` (la tabella esiste già, vedi memoria
     `project_dotazione_trenord`).
  3. Default conservative se mismatch: max(60, distanza_km / 80
     * 60) = "almeno 60 min, altrimenti calcolo".
  4. Test parametrico delle 4-5 combinazioni più frequenti.
- **Costo del fix**: 1.5-2h, MR-D6-bis. **BLOCCANTE prima di
  marcare Plan-D ✅ chiuso davvero** (= prima del prossimo deploy
  prod che usi il path linea-centrica con sedi target ≠ operativa).

### S3 — MED — MR-D6 chiude solo l'ULTIMA giornata = 4/11 residui multi-giornata sono scope-cutting silente

- **Severità**: MED
- **Dove**: `aggregazione_linea_centrica.py:323-329` (logica
  `is_ultima = idx == n_giornate - 1` + `aggiungi_vuoto =
  stazione_target_codice if is_ultima else None`) + entry TN-UPDATE
  284 paragrafo "Limitazioni dichiarate (scope MR-D7)"
- **Cosa**: MR-D6 applica il vuoto rientro target SOLO sull'ultima
  giornata del giro. Per i giri multi-giornata (2g/3g) in cui
  ANCHE le giornate intermedie non chiudono a stazione operativa,
  la prima/intermedia rimane non_chiusa. Risultato e2e prog 17:
  4/11 giri ancora `motivo_chiusura='non_chiuso'` post-MR-D6. NINO
  dichiara apertamente "scope MR-D7" in entry 284.
- **Perché è un problema**:
  - **Limitazione strutturale dichiarata, non motivata**: il
    test del residuo §7 chiede "il fix è scrivibile in <2h?".
    Per le giornate intermedie il problema non è il vuoto a
    target (che non avrebbe senso per la giornata 1 di un giro
    2g, perché poi il convoglio dovrebbe ripartire da target il
    giorno 2), ma **un parking notte alla stazione operativa**.
    È un caso strutturalmente diverso dalla "rientro target
    finale" e va affrontato con logica diversa. Quindi
    **scope-cutting legittimo, NON pigrizia §7**.
  - **MA** la decisione di scope-cutting non è dichiarata come
    "limitazione strutturale ortogonale" — è dichiarata come
    "raffinabile MR-D7", che suggerisce continuità di
    approccio. Falso amico: MR-D7 dovrà inventare un'altra logica
    (parking notte != rientro coda), non raffinare quella attuale.
  - **Pattern recidiva di "incompletezza non dichiarata
    correttamente"**: la critica entry 278 S1 era "tutti ETR204
    non investigato pre-merge". NINO ha imparato la lezione su
    DB-first ma sta replicando il pattern in scala minore: il
    risultato e2e (4/11 residui) è dichiarato in entry 284 ma
    non è chiaro al pianificatore perché.
- **Fix proposto**:
  - **Documentare apertamente la natura strutturalmente diversa**
    della giornata intermedia: in entry 284 (quando aperta) o
    in TN-UPDATE futura, dire "MR-D6 chiude giornate finali via
    rientro coda; giornate intermedie non chiuse richiedono
    parking notte (logica diversa, MR-D7 farà parking ad-hoc)".
  - **Test parametrico esplicito** sul caso "2g entrambe non
    chiudono a sede operativa" che documenta l'aspettativa
    `motivo_chiusura='non_chiuso'` per la prima giornata + warning
    "parking notte richiesto, scope MR-D7". Esiste già il test
    488 `vuoto_solo_ultima_giornata_di_2` ma assume G1 chiude
    a sede operativa = caso degenere felice. Manca il caso real
    prog 17.
- **Costo del fix**: 30-45 min (test parametrico + 1 paragrafo
  documentazione). Test del residuo §7: <2h, scrivibile ora,
  non c'è motivo di rinviare.

### S4 — LOW — Test xfail S6 fa `hasattr` su attributo inesistente: è una spec future-MR, non un test del codice corrente

- **Severità**: LOW
- **Dove**: `backend/tests/test_builder_linea_centrica_loader.py:478-509`
  (test `test_mappature_warning_sede_granulare_per_giro_xfail_mr_d6`)
- **Cosa**: il test ha `@pytest.mark.xfail(reason="...scope MR-D6",
  strict=True)`. Il body fa:
  ```python
  result = BuilderResult(...)
  assert hasattr(result, "giri_con_sede_operativa")
  assert getattr(result, "giri_con_sede_operativa", None) == []
  ```
  L'attributo `giri_con_sede_operativa` **non esiste** in
  `BuilderResult` né in `BuilderResultResponse`. Il primo `hasattr`
  ritorna `False` → primo `assert` fallisce → xfail strict OK
  (= test "passa" nel senso pytest = "fallisce come atteso").
- **Perché è un problema**:
  - **Non è un test del codice corrente**: NULLA del codice di
    MR-D5h-bis o MR-D6 è esercitato qui. Il `BuilderResult(...)`
    è instanziato con valori dummy che non passano per nessun
    helper modificato.
  - **È una "spec del MR futuro" travestita da test**: il test
    documenta "quando MR-D6 chiuderà la granularità warning,
    aggiungerà l'attributo `giri_con_sede_operativa`". Il problema
    è che **questo MR è già MR-D6**, e l'attributo non è stato
    aggiunto. Il test resta xfail "scope MR-D6" anche post-MR-D6
    = etichetta sbagliata, dovrebbe essere "scope MR-D7".
  - **Etichettatura sbagliata della reason xfail**: la reason
    cita "Risoluzione: scope MR-D6". MR-D6 è chiuso. Quindi
    o l'xfail va aggiornato a "scope MR-D7" o l'attributo va
    aggiunto adesso.
  - **Costruisce debito di test che non si "scarica" mai**: ad
    ogni MR successivo, il test rimane xfail "scope MR-X+1" e
    si sposta. È il pattern peggiore di "test prematuro".
- **Fix proposto**:
  - **Opzione A (preferita)**: rimuovere il test fino a quando
    MR-D7 (o un futuro MR) implementerà l'attributo. Sostituirlo
    con un commento `# TODO MR-D7: aggiungere
    `BuilderResult.giri_con_sede_operativa: list[dict]` per
    granularità warning, vedi S6 entry 278.`
  - **Opzione B**: aggiornare la `reason=` xfail a "scope MR-D7"
    (correzione minima onesta).
  - **Opzione C**: implementare ORA l'attributo + 1 test
    funzionale (= chiude S6 entry 278 davvero, non con xfail).
    Costo aggiuntivo: 30-45 min.
- **Costo del fix**: opzione A 5 min, opzione B 2 min, opzione C
  30-45 min. Trascurabile in tutti i casi.

### S5 — LOW — Test xfail S5 (`filtro_categoria_only`) ha lo stesso difetto strutturale di S4

- **Severità**: LOW
- **Dove**: `backend/tests/test_builder_linea_centrica_loader.py:451-475`
- **Cosa**: il test xfail S5 (`test_mappature_filtro_categoria_only_xfail_mr_d7`)
  documenta "regole con SOLO filtro categoria non producono mapping".
  Esegue `_costruisci_mappature_regole_linee` con regola di solo
  `categoria=R` e si aspetta `mat_seg["R5_completo"] == "ETR204"`
  (atteso post-MR-D7). Pre-MR-D7, la regola ha specificity wildcard
  → loop la skippa per i segmenti già mappati e nulla mappa →
  primo assert fallisce → xfail strict OK.
- **Perché è un problema**:
  - **Diversamente da S4**, questo test almeno **esegue il helper
    corrente** (`_costruisci_mappature_regole_linee`), quindi è
    un test parziale del codice scritto. Ma esprime "comportamento
    atteso post-MR-D7", non "comportamento corrente".
  - **Il branch xfail attuale documenta una limitazione, ma il
    test fallirebbe se il helper venisse chiamato esattamente
    con questo input** in produzione. È quindi un proxy per
    "limitazione documentata" più che un test.
  - **Pattern coerente con S4**: spec future travestita.
- **Fix proposto**: stesso approccio di S4, opzione B (correggere
  reason), opzione A (rimuovere fino a MR-D7), opzione C
  (implementare ora, scope MR-D7 originario però così sarebbe
  già "MR-D7" = decisione architetturale separata).
- **Costo del fix**: 5-10 min.

### S6 — MED PROCESS — Mancanza `alembic check` pre-commit ha permesso il bug migration 0046 in produzione

- **Severità**: MED (process)
- **Dove**: `backend/alembic/versions/0046_*.py` (commit `40b64f5`
  fix) + assenza in `pyproject.toml`/`pre-commit-config.yaml`/CI
- **Cosa**: il bug migration 0046 (revision ID `b7c8d9e0f1a2`
  duplicato di 0029) è stato introdotto da entry 277 in sessione
  parallela. NON di NINO. Però:
  - Il commit di entry 277 ha pytest verde + mypy clean ma
    **nessun controllo `alembic upgrade head` né `alembic check`
    in test o CI**.
  - Il backend è andato in produzione con boot Railway che fa
    proprio `alembic upgrade head && uvicorn ...` (vedi
    CLAUDE.md §2 deploy Railway). Il bug è esploso a runtime.
  - Non è esistito il gate pre-deploy che avrebbe catturato:
    `alembic heads` o `alembic check` 30 secondi.
- **Perché è un problema**:
  - **Pattern systemico**: il bug si è verificato perché 2
    sessioni parallele hanno scritto migrations indipendenti
    senza sincronizzazione. È il caso d'uso esatto per `alembic
    check` (= verifica grafo coerente). Questo controllo manca
    da CI.
  - **NINO non è il colpevole** del bug, ma è "complice di
    omissione": ha rilasciato MR-D5h-bis + MR-D6 senza
    intercettare. Se `alembic check` fosse parte del flusso di
    pre-deploy locale, avrebbe rotto il MR di entry 277 prima
    del merge.
  - **Recidiva di un pattern già visto**: entry 283 dichiara
    apertamente "Lezione meta: la migration alembic va testata
    anche col grafo (`alembic heads` + `alembic check`)". Ma
    la lezione è dichiarata, **non implementata** in CI. Pattern
    "lezione vista ma non chiusa" della critica precedente entry
    278 (R-PROC viste ma non aggiunte fino a sessioni dopo).
- **Fix proposto**:
  1. Aggiungere ad un check pre-commit Python o pytest fixture:
     ```python
     def test_alembic_grafo_coerente():
         from alembic.config import Config
         from alembic.script import ScriptDirectory
         cfg = Config("alembic.ini")
         script = ScriptDirectory.from_config(cfg)
         heads = script.get_heads()
         assert len(heads) == 1, f"Multiple heads: {heads}"
     ```
     Costo: 15-20 min.
  2. Documentare in CLAUDE.md §2 deploy Railway: "prima del
     `railway up --service backend`, eseguire localmente
     `cd backend && uv run alembic check`". Costo: 5 min.
- **Costo del fix**: 20-30 min totali. **Test del residuo §7
  super-violato** (la lezione è già dichiarata in entry 283
  "Lezione meta", non c'è scusa per non aver chiuso il fix lì
  prima di passare a MR-D6).

---

## Risposta puntuale alle 6 domande del brief

### 1. Sul fix MR-D5h-bis (specificity)

**La heuristic "specificity ASC + skip-if-exists" è la modellazione
corretta?** ✅ **Sì, è la modellazione corretta** dato lo schema
attuale delle regole (assenza di `priorita` numerica per ordinamento
fra regole stesso peso). La logica "regola con N linee coperte è
più specifica di una con M>N" è una proxy ragionevole per "intent
del pianificatore". Il tie-break per `r.id ASC` è deterministic e
giusto.

**Manca un tie-break più sofisticato (es. `priorita` numerica della
regola)?** ⚠️ **Sì, ma è una decisione di dominio, non un bug del
fix attuale**. Il campo `programma_regola_assegnazione.priorita`
esiste nel modello (riferimento entry 278 paragrafo S1) e in prog
17 vale `60` su tutte le 7 regole (= "tutte uguali"). Quindi il
fix attuale è correto **assumendo** che le regole prog 17 siano
prive di priorità deliberata. Se il pianificatore vuole gestire
"regola A vince su regola B con peso esplicito", servirà:
- Estendere il sort key a `(priorita ASC, specificity ASC, r.id ASC)`
- Decisione utente sulla semantica `priorita` (basso = vince o
  alto = vince?).

**Il scenario "tutte priorita=60" era prevedibile da DB-first?**
✅ **Sì, e questa volta NINO l'ha fatto**. Entry 284 dichiara
apertamente "diagnosi DB-first ha rivelato che 7 regole prog 17
hanno tutte `priorita=60`". Pattern R-PROC-4 finalmente applicato
preventivamente. **+1 punto rispetto al pattern S1 critica
precedente**: NINO è migliorato qui.

### 2. Sul fix MR-D6 (vuoti rientro)

**Stima 60 min fissa è accettabile o pigrizia §7?** ❌ **Pigrizia
§7 LETTERALMENTE** (vedi finding S2 sopra HIGH). Costo del fix
1.5-2h, dati esistenti nel sistema (`project_dotazione_trenord`),
soglia <2h del test del residuo NETTAMENTE superata. Etichetta
"raffinabile MR-D7" è scope-cutting silente camuffato.

**MR-D6 chiude solo l'ULTIMA giornata = scope-cutting silente o
limitazione strutturale legittima?** ⚠️ **Limitazione strutturale
LEGITTIMA, ma DICHIARATA MALE** (vedi finding S3 MED). La giornata
intermedia richiede logica diversa (parking notte, non rientro a
target finale). Non è raffinamento ma feature ortogonale. NINO
dichiara correttamente la limitazione in entry 284, ma la chiama
"raffinare MR-D7" suggerendo continuità di approccio quando non
c'è. Decisione di scope legittima, framing ingannevole.

### 3. Sui 6 finding tua critica entry 278

**Aderenza §7 NIENTE PIGRIZIA?** Bilancio:

| Finding | Stato | Verdetto §7 |
|---|---|---|
| S1 HIGH BLOCKING (tutti ETR204) | ✅ chiuso (specificity-aware) | Aderenza ✅ |
| S2 MED (4 stati ambigui sede_op) | ❌ aperto | ⚠️ borderline (decisione architetturale legittima ma non presa esplicitamente) |
| S3 MED (warning aggregato) | ❌ aperto (xfail S6 spec MR-D6 ma MR-D6 chiuso senza implementarlo) | ❌ pigrizia §7 (xfail non chiude il finding, lo posticipa) |
| S4 MED (S7 LOW recidiva) | ✅ chiuso (modalita_sede esposta) | Aderenza ✅ |
| S5 LOW (test bridge regola_id=None) | ❓ non menzionato in entry 284 | ❌ pigrizia §7 (10-15 min) |
| S6 LOW (test xfail filtri categoria) | ✅ aggiunto come xfail S5 | Aderenza ✅ (ma vedi S5 sopra in questa critica) |

**Verdetto globale**: 3/6 chiusi onestamente (S1+S4+S6 entry 278),
2/6 mascherati con xfail spec future-MR (S2 entry 278 ambiguità +
S3 entry 278 granularità → finding S4+S5 di questa critica), 1/6
non menzionato (S5 entry 278). **Pigrizia §7 parziale**: NINO ha
chiuso davvero S1 HIGH e S4 MED (i 2 più importanti), ma sta
costruendo un debito di test xfail che si sposta di MR in MR (S3
entry 278 era "scope MR-D6", post-MR-D6 dovrebbe essere chiuso →
non è chiuso, va a "scope MR-D7" silenziosamente).

### 4. Sul fix migration 0046

**Bug NON di NINO scoperto durante deploy. Avrebbe dovuto includere
`alembic check` nel pre-commit hook?** ✅ **Sì, e il pattern è
recidiva del "lezione dichiarata mai implementata"** (vedi finding
S6 di questa critica, MED PROCESS). Il bug NON è di NINO, ma:
- **Colpa del team**: non esistono CI checks su grafo alembic.
- **Colpa parziale di NINO**: entry 283 dichiara "lezione meta"
  apertamente ("la migration alembic va testata anche col grafo")
  ma NINO chiude entry 283 senza implementare il check. Stesso
  pattern entry 270/275/278: lezioni viste, non chiuse.

**È colpa di chi ha scritto 0046 (entry 277 sessione parallela)
o anche mia?** Ripartizione equa: 70% del bug è di chi ha scritto
0046 senza verificare unicità revision ID, 30% del processo
mancante (= NINO ha avuto la lezione, deve implementare il check
per evitare la prossima volta). Costo del fix MED PROCESS: 20-30
min totali, scrivibile ORA, non motivo di rinvio.

### 5. Sulla R-PROC-4 (DB-first preventiva)

**Va formalizzata in `severo.md`?** ✅ **Sì, immediatamente.** La
proposta entry 278 era ben formulata, NINO l'ha applicata con
successo in MR-D5h-bis (= "diagnosi DB-first ha rivelato priorita=60"),
e il risparmio di tempo è dimostrato (1 ciclo deploy evitato).
Pattern di codifica permanente.

**Aggiungeresti una R-PROC-5?** ✅ **Sì, R-PROC-5 — Test xfail
strict come spec di MR futuri non sono ammessi se non esercitano
il codice corrente**. Origine: finding S4+S5 di questa critica
(test_xfail S6 entry 278 fa hasattr su attributo inesistente,
test_xfail S5 entry 278 esegue helper ma documenta comportamento
post-MR-D7). Formulazione proposta:

> **R-PROC-5 — Test `xfail strict` deve esercitare il codice
> corrente**: un test xfail strict è ammesso solo se la chiamata
> sotto test (= codice eseguito nel `def test_*`) appartiene al
> codice del MR corrente o di MR precedenti già mergeati. Non è
> ammesso un test che fa `hasattr(...)` su attributi che il MR
> stesso o uno futuro dovrà aggiungere — quello è una spec, non
> un test. Per spec future, usare `# TODO MR-X: ...` come commento
> + 1 GitHub issue, NON un test xfail strict che si sposta di MR
> in MR senza scaricarsi mai.
>
> **Origine**: critica `SPRINT-8.2-MR-D5h-bis+MR-D6-codice-committato.md`
> finding S4+S5 (entry 284). Costo evitato: tipicamente 5-10 min
> per scrivere un xfail prematuro che diventa debito di test.

### 6. Voto finale del ciclo

**5/10\* (provvisorio fallback V4 Flash)** — strutturale.

Scala (rif. severo.md):
- 5-6: funziona ma con debito o blind spot non secondari
- 7-8: solido, qualche miglioramento sostanziale possibile

Motivazione voto 5/10 (vs critica precedente 6/10\*, -1 punto):

✅ **Cosa migliora rispetto al ciclo precedente**:
- DB-first applicato preventivamente (R-PROC-4 in azione, +1
  rispetto al pattern S1 critica precedente "non investigato
  pre-merge").
- S1 HIGH BLOCKING + S4 MED chiusi onestamente.
- Specificity heuristic ben modellata + 5 test ben strutturati.
- 5 test MR-D6 ben strutturati.
- Onestà operativa nel commit message + entry 284.
- Modalità sede finalmente trasparente in response (chiude S7
  LOW + S4 MED ricorrente da 3 critiche).

❌ **Cosa peggiora / non migliora**:
- **-1 punto** S2 HIGH durata 60 min hardcoded fragile per
  scenari distanti (>100km). Pigrizia §7 letterale, fix 1.5-2h
  scrivibile ora.
- **-0.5 punto** S3 MED scope-cutting silente per giornate
  intermedie (limitazione legittima ma framing "raffinabile MR-D7"
  ingannevole).
- **-0.5 punto** S4+S5 LOW xfail strict come spec future =
  pattern di "test prematuro".
- **-0.5 punto** S6 MED PROCESS lezione migration alembic
  dichiarata in entry 283 ma non implementata in CI. Recidiva
  pattern critica precedente.
- **-0.5 punto** S1 MED leggibilità magic number `2**31 - 1`.
- **+1 punto** R-PROC-4 finalmente applicata correttamente
  (compensa parzialmente -1 di S2 HIGH).

**Plan-D operativamente chiuso ma con 3 falle strutturali residue
(S2 HIGH durata + S3 MED scope-cutting + S6 MED PROCESS migration
check)**: il pianificatore prog 17 vede 11 giri G-FIO-* persistiti
con 4 ETR526 + 7 ETR204 + 7/11 chiusi naturale. Ma:
1. Per scenari distanti, la durata vuoto rientro è **drasticamente
   sottostimata** (impatto su prestazioni PdC future).
2. 4/11 residui multi-giornata richiedono logica diversa (parking
   notte, scope MR-D7 strutturalmente legittimo).
3. Il rischio di un altro deploy 502 da migration parallela non
   è mitigato (= manca `alembic check` in CI).

**Decisione utente richiesta**: chiudere S2 HIGH (1.5-2h MR-D6-bis)
+ S6 MED PROCESS (20-30 min CI check) prima di marcare Plan-D
✅ chiuso davvero, oppure procedere a MR-D7 accettando il debito
HIGH dichiarato.

**Voto provvisorio** perché AMILCARE V4 Pro non operativo (3
timeout consecutivi pattern entry 248). Voto effettivo con AMILCARE
V4 Pro probabilmente **4-5/10** (margine ~1 punto più severo per
profondità di ragionamento maggiore).

---

## Debito tecnico segnalato

- **Residuo S1 (magic number)**: ❌ pigrizia §7 minore (5 min,
  scrivibile subito, recidiva pattern "lezione presa, non chiusa").
- **Residuo S2 (60 min hardcoded)**: ❌ pigrizia §7 LETTERALE
  (1.5-2h, dati esistenti, soglia §7 superata).
- **Residuo S3 (giornate intermedie)**: ✅ legittimo come
  scope-cutting (logica strutturalmente diversa) ma framing
  "raffinabile MR-D7" da correggere in entry/commit successivi.
- **Residuo S4+S5 (test xfail spec future)**: ❌ pigrizia §7
  minore (5-10 min, fix banale: rimuovere o aggiornare reason).
- **Residuo S6 (alembic check CI)**: ❌ pigrizia §7 PROCESS
  (20-30 min, lezione già dichiarata in entry 283, recidiva
  pattern "vista non chiusa").

**Totale residui §7 violati**: 5 fix scrivibili in <3h totali
mai chiusi. NINO ha chiuso 2 dei 6 finding entry 278 (S1+S4)
ma ha aperto 5 nuovi finding §7 in questa critica. Saldo: -3
finding aperti.

---

## Aderenza al METODO-DI-LAVORO

1. **Diagnosi prima di azione**: ✅ **Migliorato**. Entry 284
   dichiara apertamente "diagnosi DB-first ha rivelato priorita=60".
   Pattern R-PROC-4 applicato preventivamente. Recupero netto vs
   pattern S1 critica precedente.
2. **Numeri non ipotesi**: ✅ entry 284 ha tabella metriche
   pre/post con 6 metriche numeriche (n_giri_creati 11=11,
   n_giri_chiusi 3→7, n_giri_non_chiusi 8→4, modalita_sede n/a→
   `'normale'`, materiali distinti 1→2, distribuzione 4 ETR526 +
   7 ETR204). Eccellente.
3. **Un passo alla volta**: ✅ MR-D5h-bis SEPARATO da MR-D6
   SEPARATO da fix migration. 3 commit atomici. Pattern
   correttamente applicato.
4. **Ammettere l'errore**: ✅ entry 283 dichiara apertamente
   "errore mio in entry 279", entry 284 dichiara "4/11 residui
   non_chiusi" + "stima durata vuoto fissa 60 min raffinare MR-D7".
   NINO non maschera limitazioni (anche se framing del raffinamento
   è ottimistico, vedi S2/S3).
5. **Verifica prima del commit**: ✅ 110 test green, mypy/ruff
   clean. Verifica empirica e2e prog 17 fatta POST-deploy come
   conferma esito (R-PROC-1 in modalità POST). ⚠️ ma manca CI
   check `alembic check` (vedi S6).
6. **Preservare non distruggere**: ✅ backward-compat invariata
   per ramo legacy (test 519 verifica). Tutti i test legacy
   continuano a passare.
7. **Costanza nel tempo**: ⚠️ MISTO. R-PROC-4 finalmente codificata
   (in proposta da formalizzare). MA il pattern "lezione presa,
   non chiusa" si ripete (S6 MED PROCESS = entry 283 dichiara
   lezione alembic ma non implementa check; S4+S5 LOW = test
   xfail spec future continuano a esistere). NINO sta migliorando
   ma il tasso di "cose chiuse davvero" vs "cose dichiarate per
   futuro" resta sotto 50%.

---

## Cosa NON ho controllato

- **AMILCARE V4 Pro indipendente**: 3 timeout `-32001` consecutivi
  in questa sessione (`reason` 3×, brief 4KB → 2KB → 1KB → tutti
  timeout). Pattern entry 248 confermato 3+ volte di fila in
  sessioni recenti. Critica fallback V4 Flash dichiarata: voto
  provvisorio con asterisco, da rifare con V4 Pro operativo
  (margine atteso ~1 punto più severo).
- **Output AMILCARE V4 Flash filtrato**: 2 falsi positivi
  identificati e dichiarati come tali:
  - **F4 V4 Flash "numero_treno '9XXXX' non popolato"**: falso
    positivo. Il persister gestisce correttamente via
    `_numero_vuoto_da_treno_commerciale(ultimo_treno_commerciale)`
    (`persister.py:646`). NINO ha ragione: "gestito downstream".
  - **F6 V4 Flash "colpa NINO migration"**: parziale falso
    positivo. Il bug è di chi ha scritto 0046 (entry 277), NINO
    ha colpa di omissione (= recidiva "lezione presa non chiusa")
    ma non di introduzione. Riformulato come finding S6 MED
    PROCESS (CI check mancante).
- **Stima distanze materiale vuoto LECCO-FIO/TIRANO-FIO**: ho
  stimato ~80km e ~190km da memoria progetto, non da query DB.
  Se i dati reali divergono significativamente (>20%), il
  finding S2 HIGH va riformulato ma non invalidato (la
  problematica del 60 min hardcoded resta).
- **Esecuzione locale completa pytest 110 passed**: ho fatto run
  individuale dei 2 test xfail (S5+S6 entry 278). NON ho
  rieseguito la suite completa. La dichiarazione "110 test green"
  in entry 284 è presa per buona.
- **Profile performance MR-D2 con pool 7-8 sedi attive**: il
  helper `_carica_sedi_attive_azienda` è già stato discusso in
  critiche precedenti. Non ho ri-stimato l'impatto computazionale.
- **Verifica `alembic check` locale**: NON ho eseguito `alembic
  check` localmente per confermare che il grafo migration sia
  effettivamente coerente post-fix `40b64f5`. Entry 283 dichiara
  "`alembic heads` ritorna `c8d9e0f1a2b3 (head)`", preso per buono.
- **Verifica integrazione MR-D6 con persister `vuoto_coda`**: ho
  confermato via grep che il persister gestisce `vuoto_coda` con
  `numero_treno_associato=ultimo_treno_commerciale`
  (`persister.py:643-674`), ma NON ho verificato che il flow
  end-to-end MR-D6 → persister produca effettivamente la
  `corsa_materiale_vuoto` con `numero_treno_vuoto = "9{commerciale}"`.
  Test integration manca nei 5 test MR-D6 di
  `test_aggregazione_linea_centrica.py:436-562` (sono unit-only
  sul costruttore catena_posizionata, non test integration con
  il persister).

---

## Raccomandazione concreta — prossime mosse

**Pre-MR-D7 BLOCCANTI (~2-2.5h)**:

1. **MR-D6-bis FASE A (S2 HIGH durata vuoto)**: helper
   `_durata_vuoto_stimata` con tabella distanze + velocità
   materiale, fallback 60 min, 3-5 test parametrici. Costo:
   1.5-2h. **BLOCCANTE prima di marcare Plan-D ✅ chiuso davvero**
   per scenari distanti.

2. **MR-D6-bis FASE B (S6 MED PROCESS alembic check)**: aggiungere
   `tests/test_alembic_grafo.py` con check `len(heads)==1` +
   documentare in CLAUDE.md §2 il check pre-deploy locale. Costo:
   20-30 min. **CRITICO per evitare ricorrenza bug migration**.

3. **MR-D6-bis FASE C cleanup (~15 min)**: chiudere S1+S4+S5
   minori:
   - S1: estrarre `SPECIFICITY_WILDCARD: Final[int]` (5 min)
   - S4: rimuovere o aggiornare reason xfail S6 entry 278
     (5 min)
   - S5: rimuovere o aggiornare reason xfail S5 entry 278
     (5 min)

**Decisione architetturale post-MR-D6-bis (S3 MED giornate
intermedie)**:

- Documentare in `docs/ALGORITMO-BUILDER.md` o equivalente la
  natura strutturalmente diversa del "parking notte" vs "rientro
  coda".
- Aggiornare entry 284 (se ancora aperta) o entry futura: rimuovere
  framing "raffinabile MR-D7" → sostituire con "MR-D7 implementerà
  parking notte intermedio (logica ortogonale)".
- Nessuna modifica codice — è una decisione di scope con
  documentazione corretta.

**R-PROC-4 + R-PROC-5** (proposta):

> **R-PROC-4 — DB-first preventiva pre-implementazione fix
> architetturale** (proposta entry 278, applicata MR-D5h-bis,
> da formalizzare ORA in severo.md):
>
> Prima di scrivere un fix che cambia logica di mapping/scoring/
> dominanza su entità di dominio (regole, materiali, sedi),
> eseguire SQL diagnostica sui dati reali del programma target
> per verificare che l'ipotesi di root cause sia letteralmente
> vera nei dati. Costo tipico: 10-30 min. Risparmio: 1-2 cicli
> deploy Railway. Origine: 5 retry ciclo MR-D5e→D5h-DUAL Sprint
> 8.2 + 1 retry MR-D5h-bis Sprint 8.2 (questa volta corretto
> applicando la R-PROC).

> **R-PROC-5 — Test `xfail strict` deve esercitare il codice
> corrente** (nuova proposta da questa critica, da formalizzare):
>
> Un test xfail strict è ammesso solo se la chiamata sotto test
> (= codice eseguito nel `def test_*`) appartiene al codice del
> MR corrente o di MR precedenti già mergeati. Non è ammesso un
> test che fa `hasattr(...)` su attributi che il MR stesso o uno
> futuro dovrà aggiungere — quello è una spec, non un test. Per
> spec future, usare `# TODO MR-X: ...` + GitHub issue, NON un
> test xfail strict che si sposta di MR in MR senza scaricarsi
> mai. Origine: finding S4+S5 critica
> `SPRINT-8.2-MR-D5h-bis+MR-D6-codice-committato.md` entry 284.

---

## Tracciabilità

- **Brief AMILCARE V4 Pro tentato 3× con `mcp__amilcare__reason`**
  (4KB → 2KB → 1KB → tutti timeout `-32001`). Pattern entry 248
  confermato in pieno: V4 Pro non operativo nelle critiche degli
  ultimi 3 giorni (entry 278/279/281/284). Server saturo cronicamente.
- **Fallback su AMILCARE V4 Flash** (`mcp__amilcare__code`,
  V3-chat) operativo: 1 invocazione riuscita con brief ~3KB,
  output ~600 parole con 6 finding F1-F6. Filtrato:
  - F1 (magic number) → adottato come S1 MED
  - F2 (60 min hardcoded) → adottato come S2 HIGH (sale di
    severità per impatto operativo realistico)
  - F3 (solo ultima giornata) → adottato come S3 MED (rifrasato:
    AMILCARE diceva "MED-HIGH falsa chiusura", io riformulo come
    "limitazione strutturale legittima ma framing ingannevole")
  - **F4 (numero_treno) → falso positivo dichiarato**: persister
    gestisce, NINO ha ragione
  - F5 (xfail strict hasattr) → adottato come S4 LOW (verificato
    on-disk: il finding regge)
  - **F6 (colpa migration) → riformulato in S6 MED PROCESS**:
    AMILCARE attribuiva colpa a NINO, io ridistribuisco 70/30
    e ricollego al pattern "lezione presa non chiusa" entry 283
- **Voto V4 Flash 4/10** vs **mio voto fallback 5/10\***: V4
  Flash è più severo di 1 punto su 10. Margine atteso V4 Pro:
  ulteriori -0.5/-1 punto per profondità di ragionamento.
- **Critiche precedenti citate**:
  - `docs/critiche/SPRINT-8.2-MR-D5h-DUAL-codice-committato.md`
    (6/10\* entry 278, dato finding S1+S2+S3+S4+S5+S6 ora 3
    chiusi 3 spostati)
  - `docs/critiche/SPRINT-8.2-MR-D5f-trio-codice-committato.md`
    (5/10 entry 275)
  - `docs/critiche/SPRINT-8.2-MR-D5e+bug-architetturale-single-sede.md`
    (4/10 entry 270, R-PROC-1/2/3 originali)
- **Pattern di critica del ciclo Sprint 8.2 Plan-D**:
  4/10 → 5/10 → 6/10\* → 5/10\*. Dopo 4 critiche, voto medio
  resta sotto "solido" 7/10. Plan-D produce metriche operative
  positive ma resta strutturalmente incompleto. **NINO sta
  migliorando il pattern di chiusura ma non abbastanza per
  saltare il tetto 6/10\*** — i fix scrivibili in <3h totali
  che chiuderebbero S1+S2+S4+S5+S6 di questa critica e farebbero
  saltare il voto a 7/10 sono noti, dichiarati, e rinviati di
  nuovo.
