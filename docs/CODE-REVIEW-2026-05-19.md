# Code Review — COLAZIONE — 2026-05-19

> Revisione sistematica del codebase eseguita a freddo (nessun fix
> automatico). Ogni finding cita file:linea, propone fix concreto.
> Classificazione: CRITICO / IMPORTANTE / MINORE.
>
> Scope: backend Python (domain, api, models, importers, tests),
> frontend TypeScript (limitato: struttura route e API client),
> migrazioni Alembic, script.

---

## CRITICO

**C1 — Anti-rigenerazione TurnoPdc: full table scan + race condition**
- file: `backend/src/colazione/domain/builder_pdc/builder.py:737`
- Il codice: `select(TurnoPdc).where(TurnoPdc.azienda_id == azienda_id)` carica in memoria Python TUTTI i `TurnoPdc` dell'azienda (potenzialmente migliaia), poi filtra in Python via `_matches_giro_e_deposito`. Con crescita del DB questo è O(N_turni). Inoltre, tra la SELECT e la DELETE non c'è lock: due richieste concorrenti per lo stesso `(giro_id, deposito_pdc_id)` superano entrambe il check `if legati and not force` e scrivono turni duplicati.
- Fix: aggiungere filtro SQL `TurnoPdc.deposito_pdc_id == deposito_pdc_id` (quando valorizzato) e filtrare il `generation_metadata_json` con un operatore JSONB (`TurnoPdc.generation_metadata_json["giro_materiale_id"].as_integer() == giro_id`). Per la race condition: `SELECT ... FOR UPDATE` o `UniqueConstraint` su `(azienda_id, codice)`.

**C2 — `GiriEsistentiError` omonima in due namespace diversi con gerarchia incompatibile**
- file A: `backend/src/colazione/domain/builder_giro/builder.py:166` → `class GiriEsistentiError(RuntimeError)`
- file B: `backend/src/colazione/domain/builder_pdc/builder.py:1271` → `class GiriEsistentiError(Exception)`
- `api/giri.py` importa da `builder_giro`; `api/turni_pdc.py` importa da `builder_pdc`. Un handler che importa tipo A non cattura tipo B. Se un futuro refactoring mischia le importazioni, eccezioni 409 diventano 500 silenti.
- Fix: rinominare una delle due. Proposta: `GiriEsistentiError` in `builder_giro` → `GiriGiroEsistentiError`; `GiriEsistentiError` in `builder_pdc` → `TurnoPdcEsistenteError`. Uniformare la base class a `RuntimeError` in entrambi.

**C3 — ACCp Fiorenza non implementa §8.5: i 7' U\*\*\*\* sono INCLUSI negli accessori, non sommati**
- file: `backend/src/colazione/domain/builder_pdc/builder.py:213-218`
- Il builder applica ACCp=40' PRIMA del primo blocco indiscriminatamente. Per i giri con primo blocco a Fiorenza (U\*\*\*\*→Mi.Certosa, 7'), la normativa §8.5 dice: "i 7 minuti FIOz→Mi.Certosa sono INCLUSI negli accessori ACCp. Non si sommano." Il builder quindi produce `ACCp(40') + U****(7')` = 47' totali prima del primo commerciale, ma la normativa prevede `ACCp(40')` che INCLUDE il trasferimento interno (= nessun blocco U\*\*\*\* separato prima, o U\*\*\*\* dentro l'ACCp).
- Impatto: prestazione calcolata +7' rispetto al reale, soglie cap potrebbero risultare falsamente rispettate su turni borderline.
- Fix: quando `primo.stazione_da_codice` è Fiorenza (o il blocco è di tipo `materiale_vuoto` con `ora_fine - ora_inizio <= 10'`), non aggiungere ACCp separato: espandere l'ACCp a coprire anche il trasferimento interno.

**C4 — Gap interni sempre PK: §6 non implementata (soglia CV 65')**
- file: `backend/src/colazione/domain/builder_pdc/builder.py:257-270`
- Ogni gap > 0' tra blocchi consecutivi viene classificato come PK. La normativa §6 prevede: gap < 65' → CV o PK (CV richiede incontro fisico tra PdC); gap 65-300' → ACC o PK; gap > 300' → ACC (o PK opt-in). Il builder emette sempre PK per tutti i gap, anche quando un CV sarebbe il tipo corretto (gap < 65' in stazione ammessa §9.2). Produce turni validi ma con gap-type errato visibile in UI e nei calcoli di prestazione.
- Fix: dopo la build giornata, post-process: per ogni PK con durata < 65', se la stazione è in `stazioni_cv`, convertire in `CVa`+`CVp` tentativo (il builder split_cv già lo fa per le giornate splittate; estendere ai PK interni).

**C5 — `TurnoPdcGiornata.variante_calendario: String(20)` con troncamento silenzioso**
- file: `backend/src/colazione/models/turni_pdc.py:74`; troncamento a `builder.py:1070`
- Le etichette parlanti Trenord (es. "LV 1:5 esclusi 2-3-4/3" = 24 char, "Si eff. 21-28/3, 11/4" = 22 char) superano 20 char. Il builder tronca silenziosamente con `[:20]` senza log né errore. Il testo viene salvato incompleto, compromettendo `enumera_date_giornata` che parsa il testo per ricostituire le date concrete.
- Fix: allargare la colonna a `String(100)` (migration) e rimuovere il troncamento a `builder.py:1070`. Aggiungere log WARNING se la stringa supera 20 char nel pre-fix.

**C6 — `updated_at` non si aggiorna sugli UPDATE (mancante `onupdate`)**
- file: `backend/src/colazione/models/turni_pdc.py:59`, `models/giri.py:79`, `models/programmi.py:187`, `models/anagrafica.py:116`, `models/personale.py:69`
- Tutti usano `server_default=func.now()` ma nessuno ha `onupdate=func.now()`. Dopo il record creato, qualsiasi UPDATE non aggiorna `updated_at`. Il timestamp diventa stale dopo il primo write: inutile per audit e per caching HTTP (ETag/Last-Modified).
- Fix: aggiungere `onupdate=func.now()` su tutte le colonne `updated_at`. In SQLAlchemy: `mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())`. Alternativa Postgres-nativa: trigger `BEFORE UPDATE SET updated_at = NOW()`.

**C7 — 50 test falliti pre-esistenti su `master`**
- fonte: TN-UPDATE.md entry 301 ("⚠️ pytest full backend: 50 fallimenti pre-esistenti su master (verificato via `git stash` → stessi fail)")
- Un codebase in produzione con 50 test rotti su `master` (non su un branch feature) non permette di distinguere regressioni reali da rumore. La CI viene bypass-ata implicitamente: ogni nuovo fix si verifica "50 fallimenti sono gli stessi di prima" invece di "0 fallimenti".
- Fix: audit i 50 test falliti, classificarli (rotto per cambio API, skip legittimo, regressione vera), e riparare o marcare come `skip` con `reason` esplicito. Obiettivo: 0 fallimenti su `master`.

---

## IMPORTANTE

**I1 — `giornata_base.py`: facade incompleta, ancora dipende da simboli privati**
- file: `backend/src/colazione/domain/builder_pdc/giornata_base.py:31-71`
- Il modulo dichiara di risolvere il finding SEVERO S2 ("consumatori dipendono da API privata di `builder.py`"). In realtà re-importa e aliasa i simboli privati `_BloccoPdcDraft`, `_GiornataPdcDraft`, `_t`, `_from_min`, `_aggiungi_dormite_fr`, ecc. Il problema strutturale rimane: `giornata_base.py` stessa dipende dai simboli underscore di `builder.py`. Rinominare o spostare un simbolo privato in `builder.py` richiede aggiornare anche `giornata_base.py`. Il fix corretto è spostare i dataclass in un modulo terzo indipendente (es. `builder_pdc/types.py`).

**I2 — `api/giri.py`: 4422 righe, violazione SRP**
- file: `backend/src/colazione/api/giri.py`
- Singolo file router con ~25+ endpoint che coprono: generazione giri materiali, inserimento manuale corse, gestione blocchi, pipeline overview, Gantt unificato, e logica di dominio (sorting, validazione, azioni batch). Rende i code review costosi, la navigazione difficile, e i conflitti di merge frequenti con il team.
- Fix: splitta in `api/giri_builder.py` (generazione), `api/giri_editor.py` (operazioni CRUD blocchi), `api/gantt.py` (Gantt unificato).

**I3 — Anti-rigenerazione `deposito_first.py`: carica tutti TurnoPdc del depot in memoria**
- file: `backend/src/colazione/domain/builder_pdc/deposito_first.py:468-488`
- Simile a C1 ma filtra almeno per `deposito_pdc_id`. Tuttavia carica TUTTI i turni del depot e poi filtra per `giro_materiale_id` in Python. Con N turni per depot la query è O(N). Fix identico a C1.

**I4 — `vettura_resolver.py`: VOCTAXI forfettario 30' per tutti i depositi**
- file: `backend/src/colazione/domain/builder_pdc/vettura_resolver.py:103`
- `VOCTAXI_DURATA_DEFAULT_MIN = 30` è una costante globale applicata a TUTTI i depositi. Per un PdC di SONDRIO o COLICO che chiude il turno a TIRANO, un taxi dura molto più di 30'. La prestazione calcolata sarà sistematicamente sotto-stimata per i depositi periferici, potenzialmente nascondendo violazioni del cap 8h30.
- Fix minimo: rendere il valore configurabile per deposito (mappa in `azienda.normativa_pdc` JSON, già previsto nel modello dati §3). Fix immediato: almeno documentare il placeholder come violazione annotata nel turno (aggiungere `"voctaxi_durata_stimata_non_verificata"` alla lista violazioni quando si sceglie VOCTAXI).

**I5 — `_inserisci_refezione_ai_bordi`: REFEZ prima della PRESA servizio è semanticamente non conforme**
- file: `backend/src/colazione/domain/builder_pdc/builder.py:477-540`
- La Strategia 1 inserisce un blocco REFEZ PRIMA del blocco PRESA, spostando `ora_presa - 30'`. Questo produce un turno dove il PdC fa refezione PRIMA di essere formalmente in servizio. La normativa §4.1 colloca la REFEZ come "pausa pasto dentro una finestra oraria prevista" — la formulazione implica che sia dentro il turno. L'interpretazione "refezione anticipata" è operativamente discutibile e non validata dall'utente in modo esplicito.
- Fix: rimuovere la Strategia 1 e mantenere solo la Strategia 2 (REFEZ dopo FINE). Se nessuna strategia è applicabile, annotare `"refezione_mancante"` come violazione (già previsto) senza estendere il turno.

**I6 — §15.1 unicità cross-turno non implementata, residuo non tracciato in TN-UPDATE.md**
- file: `backend/src/colazione/domain/builder_pdc/deposito_first.py:678-679`
- Commento nel codice: "la validazione cross-turno (lo stesso segmento in turni diversi dello stesso programma) è scope MR successivo". Il residuo NON è tracciato come item aperto in TN-UPDATE.md. Viola §7 CLAUDE.md: ogni residuo deve avere motivazione oggettiva documentata.
- Fix: aggiungere entry in TN-UPDATE.md con il residuo e la stima di complessità (richiede query DB su tutti i turni del programma post-persistenza → dipende dalla struttura del persister → stima 1 Sprint).

**I7 — `test_violazioni_normative_pdc.py`: importa simbolo privato `_build_giornata_pdc`**
- file: `backend/tests/test_violazioni_normative_pdc.py:28-30`
- Il test importa `_build_giornata_pdc` (underscore) direttamente da `builder.py` invece di `build_giornata_pdc` da `giornata_base.py`. Confligge con la motivazione stessa di `giornata_base.py` (nascondere i privati).
- Fix: aggiornare l'import a `from colazione.domain.builder_pdc.giornata_base import build_giornata_pdc`.

**I8 — `TurnoPdc.codice` mancante di `UniqueConstraint`**
- file: `backend/src/colazione/models/turni_pdc.py:39`
- Il codice è per design univoco (pattern `T-{depot}-{giro}`), ma nessun vincolo DB lo garantisce. Due inserimenti concorrenti per la stessa coppia `(giro_id, deposito_pdc_id)` produrrebbero due turni con lo stesso codice senza errore DB.
- Fix: aggiungere `UniqueConstraint("azienda_id", "codice")` in `__table_args__`. Migration necessaria.

---

## MINORE

**M1 — Commenti inline `Sprint X.Y MR Z` in codice di produzione**
- file: numerosi (es. `builder.py`, `deposito_first.py` ~19 occorrenze, `giornata_base.py`, `models/turni_pdc.py`)
- Commenti come `# Sprint 7.4 MR 2: split CV intermedio`, `# Sprint 8.2 MR-PD-FIX-SEVERO 3b A1` appartengono ai commit message e all'history git. Nel codice sorgente diventano rumore storico non manutenibile: nessuno li aggiorna quando le funzionalità cambiano.
- Fix: rimuovere tutti i commenti `Sprint X.Y MR Z`. Il WHY normativo (es. "§8.5: 7' inclusi negli accessori") va mantenuto; il WHEN (sprint) va rimosso.

**M2 — `assert` in codice di produzione (disattivati con `python -O`)**
- file: `backend/src/colazione/domain/builder_pdc/builder.py:210, 253, 256`
- `assert primo.ora_inizio is not None` e simili. Gli assert vengono rimossi con `python -O` (ottimizzazione). In produzione con `PYTHONOPTIMIZE=1` le guard diventano no-op e il codice prosegue verso un `AttributeError` invece di un messaggio d'errore comprensibile.
- Fix: sostituire con `if ... is None: raise ValueError(f"...")`.

**M3 — `_emit_violazione_striscia` nested con chiusura fragile**
- file: `backend/src/colazione/domain/builder_pdc/riposo_settimanale.py:178-193`
- Nested function con chiusura su `contatore`, `inizio_striscia_idx` dell'outer scope (read-only, non `nonlocal`). Funziona ma è difficile da testare in isolamento e fragile se estratta in un futuro refactoring. Aggiunge anche l'edge case `idx_chiusura_striscia = -1` (chiamata con `idx=0` al primo elemento) che accede a `drafts[-1]` — safe perché `contatore == 0` in quel momento, ma ragionamento non immediato.
- Fix: convertire in funzione pura a livello modulo con parametri espliciti `(contatore, inizio_striscia_idx, drafts, violazioni_list)`.

**M4 — Import non usato mascherato con noqa**
- file: `backend/src/colazione/domain/builder_giro/varianti_calendariali.py:293`
- `_ = Counter  # noqa: F841 — riservato per estensioni`. Se `Counter` non è usato, eliminare l'import. "Riservato per estensioni" non è una motivazione oggettiva.
- file: `backend/src/colazione/domain/builder_giro/builder.py:2757-2758` — stessa categoria.

**M5 — Import deferred in `multi_turno.py` segnala ciclo non risolto**
- file: `backend/src/colazione/domain/builder_pdc/multi_turno.py:604`
- `from colazione.domain.builder_pdc.giornata_base import GiriEsistentiError` dentro una funzione. L'import deferred è un workaround per un ciclo di importazione. Il ciclo è tra `multi_turno → giornata_base → builder → (split_cv ← multi_turno)`. Indica un'architettura di dipendenze non risolta.
- Fix (strutturale): le eccezioni di dominio dovrebbero vivere in un modulo `builder_pdc/exceptions.py` senza dipendenze, importabile da tutti.

**M6 — `TurnoPdc.km` sempre 0 nella giornata PdC**
- file: `backend/src/colazione/domain/builder_pdc/builder.py:1078`
- `km=0` hardcoded. Il campo esiste nel modello e nella UI ma non viene mai calcolato. Dato mancante non annotato come "non calcolato".

---

## Riepilogo

| Gravità | Count |
|---------|-------|
| CRITICO | 7 |
| IMPORTANTE | 8 |
| MINORE | 6 |

**Priorità assoluta di fix**: C1 (race condition + full scan), C2 (eccezioni omonime), C5 (troncamento dati silenzioso), C6 (updated_at stale), C7 (50 test rotti su master).
