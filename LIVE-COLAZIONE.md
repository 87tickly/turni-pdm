# LIVE-COLAZIONE — Registro modifiche in tempo reale

Questo file viene aggiornato ad ogni modifica. Leggilo sempre per avere il contesto completo.

---

## 2026-04-16 — Step 7: Gantt SVG visuale + builder interattivo

### Motivazione (feedback utente)
Le tabelle testuali nel dettaglio turno e nel builder erano poco leggibili:
"ok le tabelle come le hai create ma devi anche creare i grafici e agire
direttamente interagendo". Serviva una visualizzazione Gantt stile PDF Trenord.

### Nuovo componente `PdcGantt.tsx`
Timeline SVG orizzontale, scala **3 → 24 → 1 → 2 → 3** (27 tick, giornata operativa attraversa mezzanotte).

**Rendering per tipo blocco**:
- `train` -> barra alta (22px) blu `#0062CC`
- `coach_transfer` -> barra media (14px) viola tratteggiata
- `meal` -> barra media verde tratteggiata (label "REFEZ")
- `scomp` -> barra bassa (10px) grigia tratteggiata (label "S.COMP")
- `cv_partenza`/`cv_arrivo` -> marker verticale ambra (label "CVp"/"CVa")
- `available` -> box grigio chiaro (label "DISP.")
- `accessori_maggiorati=1` -> pallino nero sul blocco

**Rendering informazioni**:
- Etichetta treno/vettura sopra il blocco
- Stazione destinazione a destra
- Orari start/end sotto la barra
- Zona "prestazione" evidenziata (fascia azzurra tra start_time e end_time della giornata)
- Griglia verticale, numeri ora sull'asse

**Interattività** (props opzionali):
- `onBlockClick(block, index)` -> cursor pointer, click evidenzia il blocco
- `onTimelineClick(hour, minute)` -> cursor crosshair, click aggiunge blocco

**Legenda** sotto il grafico con 6 tipologie.

### Integrazione in `PdcPage.tsx`
Ogni `DayCard` espansa ora mostra toggle **Gantt / Lista**:
- 📊 Gantt (default): visualizzazione SVG
- 📋 Lista: tabella compatta come prima
Le giornate "Disponibile" mostrano solo testo (no Gantt).

### Integrazione in `PdcBuilderPage.tsx`
Ogni giornata in editing mostra:
1. Gantt SVG **cliccabile** con tutti i blocchi inseriti
2. Click su un blocco del Gantt -> scrolla e highlight (ring blu 1.5s) sull'editor del blocco
3. Click su zona vuota della timeline -> aggiunge nuovo blocco `train` con `start_time` = orario cliccato
4. Sotto il Gantt, la lista blocchi editabili classica

Helper `inputToPdcBlock(input)` converte `PdcBlockInput` del builder in `PdcBlock` per il renderer.

### Build
- `tsc --noEmit` 0 errori
- `npm run build` 374 KB JS (108 gzip), 54 KB CSS

### Flusso utente visuale
1. Apri un turno -> vedi **Gantt visivo** di ogni giornata (come il PDF originale)
2. Nel builder, clicca sulla timeline alle 08:30 -> crea blocco treno alle 08:30
3. Click su un blocco esistente nel Gantt -> scroll + highlight dell'editor
4. Puoi comunque modificare tutti i dettagli via form tabellare sotto

### File creati / modificati
- `frontend/src/components/PdcGantt.tsx` (NEW, ~280 righe)
- `frontend/src/pages/PdcPage.tsx` (toggle Gantt/Lista)
- `frontend/src/pages/PdcBuilderPage.tsx` (Gantt interattivo + click-to-add)
- `frontend/dist/*` (build)

---

## 2026-04-16 — Step 6b+6c/6 redesign turni PdC: builder frontend + integrazione

### Step 6b — Pagina `PdcBuilderPage.tsx`
Form completo per creare / modificare turni PdC nel medesimo schema v2.

**Route**:
- `/pdc/new`  — creazione nuovo turno
- `/pdc/edit?edit=<id>` — modifica turno esistente (carica dati)

**Layout**:
1. **CalendarPreview** — selettore data che mostra live weekday + festivita'
2. **Dati turno** (6 campi): codice*, planning, impianto*, profilo (Condotta/Scorta), valido_dal, valido_al
3. **Giornate** (lista espandibile):
   - Numero + periodicita' (dropdown: LMXGVSD/LMXGVS/LMXGV/SD/S/D/V/G)
   - Flag "Disponibile"
   - Orari prestazione, stats (Lav/Cct/Km/Rip)
   - Elenco blocchi editabili
4. **Blocchi per giornata**:
   - Tipo: train/coach_transfer/cv_partenza/cv_arrivo/meal/scomp/available
   - Train_id / vettura_id (context-sensitive)
   - Stazioni from/to
   - Orari start/end
   - Flag "accessori maggiorati"
5. **Azioni sticky bottom**: Annulla / Salva (o Aggiorna)

Gestisce editing caricando `getPdcTurn(id)` e pre-compilando tutti i campi.
Success → redirect automatico a `/pdc` dopo 1s.

### Step 6c — Integrazione in `PdcPage.tsx`
- **Bottone "Nuovo turno"** in alto a destra -> `/pdc/new`
- **Bottoni "Modifica" e "Elimina"** nell'header del dettaglio turno
- Elimina chiede conferma con `confirm()` prima di chiamare DELETE

### Frontend api.ts aggiornato
Aggiunti:
- `api.put<T>()` (mancava, necessario per PUT endpoint)
- `createPdcTurn(data)`, `updatePdcTurn(id, data)`, `deletePdcTurn(id)`
- `getCalendarPeriodicity(date, local?)` per il preview calendario
- Tipi: `PdcTurnInput`, `PdcDayInput`, `PdcBlockInput`, `CalendarPeriodicity`

### Build
- `tsc --noEmit` → 0 errori
- `npm run build` → 367 KB JS (106 KB gzip), 53 KB CSS

### Flusso utente completo ora disponibile
1. **Import** -> carica PDF turno PdC Trenord
2. **Turni PdC** -> vede la lista dei 26 turni
3. Click **"Nuovo turno"** -> apre builder, crea turno manuale
4. Click su turno -> vede dettaglio, click **Modifica** -> riapre builder con dati
5. **Elimina** turno con conferma
6. Il builder mostra preview calendario: inserisci una data, vedi letter+festivita'

**Il builder produce turni nello STESSO schema DB dei PdC importati**
-> confrontabili, modificabili, eliminabili uniformemente.

### File creati / modificati
- `frontend/src/pages/PdcBuilderPage.tsx` (NEW, ~500 righe)
- `frontend/src/pages/PdcPage.tsx` (bottoni azioni)
- `frontend/src/App.tsx` (2 nuove route)
- `frontend/src/lib/api.ts` (put + 4 funzioni nuove + tipi)
- `frontend/dist/*` (build)

### Tutti i 6 step completati!
Il redesign dei turni PdC è terminato. Le prossime iterazioni potranno aggiungere:
- Export PDF/Excel di un turno PdC
- Confronto diff tra due turni (originale vs modificato)
- Applicazione calendario: "mostrami tutti i giorni del 2026 con le loro varianti"
- Gantt SVG interattivo per i blocchi

---

## 2026-04-16 — Step 6a/6 redesign turni PdC: endpoint builder manuale + calendar

### Nuovo router `api/pdc_builder.py`
Gestisce creazione/modifica manuale di turni PdC via API: lo stesso
schema v2 dei PdC importati da PDF, in modo che **il builder interno
produca turni isomorfi** a quelli ufficiali.

### Endpoint CRUD
- **`POST /pdc-turn`** — crea un turno nuovo con tutto il grafo (turno + giornate + blocchi + note) in un singolo body. Validazione payload via Pydantic.
- **`PUT /pdc-turn/{id}`** — sostituisce tutto il contenuto di un turno esistente (cancella + reinserisce).
- **`DELETE /pdc-turn/{id}`** — elimina turno e tutti i figli (CASCADE).

### Endpoint Calendario
- **`GET /italian-calendar/periodicity?date_str=YYYY-MM-DD&local=milano`** — ritorna letter (L/M/X/G/V/S/D con festivi forzati a D), weekday italiano, is_holiday, holiday_name, eventuale patrono locale.
- **`GET /pdc-turn/{id}/apply-to-date?date_str=...`** — dato un turno e una data, trova quale variante giornata si applica (periodicita' contiene la lettera della data).

### Validazione Pydantic
- Codice e impianto obbligatori
- Profilo in {Condotta, Scorta}
- Periodicita' in {LMXGVSD, LMXGVS, LMXGV, ..., D, SD, ...}
- block_type in {train, coach_transfer, cv_partenza, cv_arrivo, meal, scomp, available}
- No duplicati (day_number, periodicita)

### Registrazione in server.py
`app.include_router(pdc_builder_router)` dopo importers.

### Test (`tests/test_pdc_builder.py`) — 18 test
- `POST /pdc-turn`: minimal, con 2 giornate e 3 blocchi + 1 nota, reject profilo/periodicita/block_type invalidi, reject duplicate day, reject campi mancanti
- `PUT`: sostituzione completa + 404 se non esiste
- `DELETE`: cascade (verifica figli rimossi) + 404
- `GET /italian-calendar/periodicity`: lunedi normale, Liberazione su sabato, Pasqua, patrono Milano opt-in, data invalida
- `GET /pdc-turn/{id}/apply-to-date`: selezione variante corretta (LMXGV per lunedi, SD per domenica/festivo sabato)

Tutti 18/18 passano. Suite totale: 108/109 (1 fail pre-esistente).

### Prossimi sotto-step
6b. Frontend: pagina PdcBuilderPage (form per creare turno)
6c. Integrazione in PdcPage (bottoni Nuovo/Modifica/Elimina)

### File creati
- `api/pdc_builder.py` — router ~270 righe
- `tests/test_pdc_builder.py` — 18 test
- `server.py` — import + include_router

---

## 2026-04-16 — Step 5/6 redesign turni PdC: pagina frontend dedicata

### Nuova pagina `/pdc`
Route aggiunta a `App.tsx`, voce sidebar "Turni PdC" con icona Train.

### Layout split
**Colonna sinistra (280px)**: lista turni
- Filtro per impianto (dropdown "Tutti gli impianti" + 26 impianti)
- Card per turno: codice mono grassetto + impianto
- Stato selezionato evidenziato con border sx primary

**Colonna destra (fluid)**: dettaglio turno
- Header: codice + planning + profilo badge + impianto + validita'
- Sezione "Giornate": card espandibili per ogni giornata
  - Collapsed: `g<N> <periodicita> <start>–<end>` + stats (Lav/Cct/Km/Not/Rip)
  - Expanded: lista blocchi colorati per tipo
- Sezione "Note periodicita' treni": `<details>` per treno con non_circola / circola_extra

### Componente blocchi
Ogni blocco ha:
- Badge colorato per tipo (Treno blu, Vettura viola, CVp/CVa ambra, Refezione verde, S.COMP/Disp grigio)
- Icona tematica (Train, Route, Clock, Coffee, Pause)
- Identifier (train_id o vettura_id)
- Stazioni from → to
- Orari start – end
- Pallino "●" ambra per accessori maggiorati

### Stats header pagina
5 stat pill: Turni / Giornate / Blocchi / Treni / Impianti (dai dati `/pdc-stats`).

### Build
- `tsc --noEmit` (incluso strict) → 0 errori
- `npm run build` → 348 KB JS (102 KB gzip), 52 KB CSS

### Ora l'utente puo' davvero:
1. Caricare un PDF dalla pagina Import (endpoint Step 4)
2. Navigare a `/pdc`, vedere 26 turni, filtrare per impianto
3. Selezionare un turno, vedere 15+ giornate con periodicita' (D/LMXGV/SD...)
4. Espandere giornate per vedere i blocchi con orari precisi
5. Consultare le note periodicita' con date ISO non-circola / circola-extra

### File creati / modificati
- `frontend/src/pages/PdcPage.tsx` (NEW, ~330 righe)
- `frontend/src/App.tsx` (route /pdc)
- `frontend/src/components/Sidebar.tsx` (voce Turni PdC)
- `frontend/dist/*` (build)

### Prossimo step
6. Builder interno isomorfo — il "Nuovo turno" produce turni nello stesso schema, validati contro calendario italiano.

---

## 2026-04-16 — Step 4/6 redesign turni PdC: endpoint upload + lettura

### Endpoint riattivato e riscritto
**`POST /upload-turno-pdc`** — ora funzionante su schema v2:
1. Valida formato PDF
2. Salva in tempfile
3. Parser via `src.importer.turno_pdc_parser.parse_pdc_pdf`
4. Persiste con `save_parsed_turns_to_db` (clear + insert)
5. Risposta ricca:
   ```json
   {
     "status": "ok",
     "filename": "...",
     "turni_imported": 26,
     "days_imported": 1344,
     "blocks_imported": 6925,
     "notes_imported": 2901,
     "trains_cited": 1889,
     "stats": {...},
     "summary": [{"codice":"AROR_C","impianto":"ARONA","days":15,"notes":20,...}, ...]
   }
   ```

### Nuovi endpoint di lettura (per frontend Step 5)
- **`GET /pdc-stats`** — statistiche globali (loaded, turni, days, blocks, trains, impianti, validita')
- **`GET /pdc-turns?impianto=X&profilo=Y`** — lista turni filtrabile
- **`GET /pdc-turn/{id}`** — dettaglio turno con giornate annidate + blocchi + note

### Frontend `api.ts` aggiornato
Nuove interfacce TypeScript su schema v2:
- `TurnoPdcResult` — response dell'upload arricchita
- `PdcStats`, `PdcTurn`, `PdcDay`, `PdcBlock`, `PdcNote`, `PdcTurnDetail`
- `PdcTurnSummary` — riga della tabella summary
- Nuove funzioni: `listPdcTurns()`, `getPdcTurn()`

### Frontend `ImportPage.tsx` aggiornato
Il componente `PdcResult` ora mostra:
- 4 stat pill (Turni / Giornate / Blocchi / Treni citati)
- Tabella summary dei turni importati (codice, impianto, giornate, note)
- Scrollabile, max-height 40

### Test end-to-end
Con PDF reale "Turni PdC rete RFI 23/02/2026" via `TestClient(app)`:
- POST /upload-turno-pdc -> 200, 26 turni, 1344 giornate, 6925 blocchi
- GET /pdc-stats -> loaded=true
- GET /pdc-turns -> count=26
- GET /pdc-turns?impianto=ARONA -> count=1
- GET /pdc-turn/1 -> AROR_C con 15 giornate, 20 note, blocchi con orari reali
- GET /pdc-find-train/10243 -> found=true, 3 occorrenze
- GET /pdc-turn/99999 -> 404 atteso

### Frontend build
- `tsc --noEmit` → 0 errori
- `npm run build` → 336 KB JS (gzip 100 KB), 48 KB CSS

### File modificati
- `api/importers.py` — endpoint upload riattivato + 3 endpoint di lettura
- `frontend/src/lib/api.ts` — tipi e funzioni nuove
- `frontend/src/pages/ImportPage.tsx` — `PdcResult` con stats ricche
- `frontend/dist/*` — build rigenerata

### Prossimi step
5. Pagina frontend **dedicata** per browsing dei turni PdC (Gantt con blocchi)
6. Builder interno isomorfo

---

## 2026-04-16 — Step 3d redesign turni PdC: orari al minuto dei blocchi

### Contesto
Dopo lo Step 3, i blocchi avevano tipo e train_id ma `start_time`/`end_time` vuoti. Feature core per poter visualizzare il Gantt preciso e calcolare statistiche esatte.

### Cosa fa il parser ora
Per ogni banda-giornata:
1. Trova l'asse orario (riga con >=15 numeri 1-24 size ~5.5, stessa Y).
2. Ne costruisce la lista di tick: `(x_start, x_center, x_end, hour)`.
3. Estrae i minuti SOPRA l'asse (size 4-6.5, y < axis_y - 2, numeri 0-59).
4. Assegna i minuti ai blocchi in ordine di X, con regole diverse per tipo:
   - `coach_transfer`, `meal`: consumano 2 minuti (start + end)
   - `train`: 2 minuti di norma. 1 se preceduto da `cv_partenza` (solo end) o seguito da `cv_arrivo` (solo start). 0 se tra due CV.
   - `cv_partenza`, `cv_arrivo`: 0 minuti (puntuali, ereditano dal treno adiacente)
   - `scomp`, `available`, `unknown`: ignorati
5. Per ogni coppia (minuto, x), l'ora e' dedotta minimizzando `|x - (x_start_H + min/60 * tick_width)|`. Evita errori su minuti grandi (es. :40 che graficamente finisce oltre il tick successivo).
6. Correzione rollover: se `start_total > end_total` con differenza < 2h, decrementa h_start di 1.

### Fix di contorno
Restrizione della banda Y per evitare sovrapposizione con la giornata successiva: `band_top = mk_y - 60`, `band_bot = mk_y + 22`, con clamping rispetto ai marker vicini.

### Esito sul PDF reale (446 pagine, Turni PdC rete RFI dal 23/02/2026)
- **Blocchi continui totali**: 5779 (train, coach_transfer, meal)
- **Con start_time popolato**: 4947 (85.6%)
- **Con end_time popolato**: 4800 (83.1%)

Esempio AROR_C g1 `[18:20][00:25]`:
- coach_transfer 2434 ARON→DOMO: 18:25 – 19:04
- meal DOMO: 19:40 – 20:07
- cv_partenza 2434 (puntuale)
- train 10243 DOMO→MIpg: → 22:24 (arr)
- train 10246 MIpg→ARON: 22:40 – 23:45

### Nuove funzioni (tutte pure + testate)
- `_find_axis_y(words, band_top, band_bot)` — cluster Y dei numeri piccoli
- `_build_axis_ticks(words, axis_y)` — lista di tick ordinati
- `_x_to_hour(x, ticks)` — fallback best-effort
- `_x_to_hour_for_minute(x, minute, ticks)` — minimizza distanza attesa
- `_extract_upper_minutes(words, band_top, axis_y)` — minuti sopra l'asse
- `_hhmm_fix_rollover(h1, m1, h2, m2)` — corregge rollover < 2h
- `_assign_minutes_to_blocks(blocks_with_x, upper_mins, ticks)` — driver

### Test — `tests/test_turno_pdc_parser.py`
9 nuovi test (+21 esistenti = 30 totali):
- `_x_to_hour_for_minute` per minuti piccoli/grandi/zero
- `_hhmm_fix_rollover` no-change, within-hour, large-diff
- `_assign_minutes_to_blocks` sequenza tipica, insufficient minutes, safe con ticks vuoti

Suite totale: 90/91 (1 fail pre-esistente non correlato su `test_meal_slot_gap`).

### Limitazione residua
~15% dei blocchi senza orario (train isolati in serie lunghe senza CVp/CVa noti). Accettabile per MVP: il frontend mostrera' "—" per questi blocchi.

### File modificati
- `src/importer/turno_pdc_parser.py` (+150 righe)
- `tests/test_turno_pdc_parser.py` (+9 test)

---

## 2026-04-16 — Step 3/6 redesign turni PdC: parser PDF v2

### Contesto
Il parser esistente di `turno_pdc_parser.py` produceva solo `train_ids[]` flat per pagina — niente dettaglio Gantt (vetture, CVp/CVa, refezioni, scomp, accessori maggiorati) ne' note periodicita' treni. Riscritto da zero sul nuovo schema v2.

### Analisi geometrica del PDF (pagine tipiche)
- Pagina = 842×595 pt (A4 landscape)
- Header pagina: parole orizzontali y~11 (`IMPIANTO:`, `[CODICE]`, `[PLANNING]`, `PROFILO:`, `DAL:`, `AL:`)
- Numero giornata: orizzontale size=12, x<20 (ancora per banda Y)
- Periodicita': orizzontale size=10, sopra il numero (`LMXGVSD`, `D`, `SD`, …)
- Orari prestazione: orizzontale size=8.5, tipo `[HH:MM]`
- Asse orario: size=5.5, tick 3..24..1..2..3
- Stats: size=6.5, colonna destra x>720 (Lav/Cct/Km/Not/Rip)
- Stazioni sul Gantt: orizzontali size=7 ai bordi
- **Etichette blocchi**: testo ruotato (`upright=False`). Lettura:
  concatenare i caratteri della stessa colonna X ordinati per Y crescente,
  poi **invertire** la stringa risultante (il testo e' scritto bottom-to-top).

### Modulo `src/importer/turno_pdc_parser.py` v2
Riscritto completamente. Contiene:

**Dataclass parse-time** (serializzabili):
- `ParsedPdcBlock` (seq, block_type, train_id, vettura_id, from_station, to_station, start_time, end_time, accessori_maggiorati)
- `ParsedPdcDay` (day_number, periodicita, orari, stats, is_disponibile, blocks[])
- `ParsedPdcNote` (train_id, periodicita_text, non_circola_dates[], circola_extra_dates[])
- `ParsedPdcTurn` (codice, planning, impianto, profilo, validita', days[], notes[], source_pages[])

**Funzioni pure** (testate unitariamente):
- `_hhmm_to_min`, `_it_to_iso_date`, `_reverse`
- `_cluster_vertical_labels(words, x_tol=2)` — raggruppa caratteri verticali per colonna X e inverte
- `_classify_vertical_label(label)` — classifica in `train`/`coach_transfer`/`cv_partenza`/`cv_arrivo`/`meal`/`scomp`/`unknown` + estrae train_id / vettura_id / to_station / accessori_maggiorati
- `_find_day_markers(words)` — identifica i numeri giornata grandi a sinistra
- `_extract_day_from_band(words, band_top, band_bot, page_width)` — estrae una giornata completa dalla banda Y
- `_parse_train_notes(text)` — parse regex della pagina finale con `Treno NNN - Circola ... Non circola ...`

**Driver principale**:
- `parse_pdc_pdf(pdf_path) -> list[ParsedPdcTurn]` — scorre le pagine, aggrega per (impianto, codice), estrae giornate + blocchi + note.
- `save_parsed_turns_to_db(turns, db, source_file)` — persiste via CRUD schema v2 (clear_pdc_data poi insert_*).

### Esito sul PDF reale (Turni PdC rete RFI dal 23 Febbraio 2026, 446 pagine)
- **26 turni** estratti (tutti gli impianti unici: ARONA, BERGAMO, BRESCIA, CREMONA, ecc.)
- **1315 giornate** con periodicita', orari prestazione e stats corrette
- **6054 blocchi** Gantt classificati: 3807 `train`, 738 `coach_transfer`, 532 `meal`, 370 `cv_arrivo`, altri `cv_partenza`/`scomp`/`available`
- **1716 treni** distinti citati nei blocchi
- **2901 note periodicita'** treni con date ISO (non circola + circola extra)

### Test — `tests/test_turno_pdc_parser.py`
21 test unitari su funzioni pure:
- Utility (hhmm_to_min, it_to_iso_date, reverse)
- Cluster verticali (DOMO da lettere separate, `2434` da numero intero, due colonne distinte, ignora parole orizzontali)
- Classificazione etichette (train, train+accessori, coach_transfer, cv_partenza, cv_arrivo, meal, scomp con/senza punto, unknown)
- Day markers (size>=10 su x<20)
- Parse note treni (base, dedup, multiline, empty)

Tutti 21/21 passano. Suite totale: 81/82 (1 fail pre-esistente non correlato su test_meal_slot_gap).

### Limitazioni note (da affinare eventualmente)
- La periodicita' della prima giornata di AROR_C risulta `LMXGVS` invece di `LMXGVSD` — piccolo mismatch del matching di banda Y. Da investigare con test fixture mirato.
- Gli orari al minuto dei blocchi (numeri sotto l'asse) NON sono ancora popolati: i blocchi hanno `start_time`/`end_time` vuoti. Sufficiente per MVP — da aggiungere in una v2 se servira' per la visualizzazione Gantt dettagliata.
- Le stazioni `from_station` di ogni blocco non sono popolate (serve logica aggiuntiva per associare le parole orizzontali ARON/DOMO ai blocchi).

### Prossimi step
4. Riattivare `POST /upload-turno-pdc` che chiami il nuovo parser + `save_parsed_turns_to_db`
5. Pagina frontend per visualizzare i turni PdC (riusa `GanttTimeline`)
6. Builder interno isomorfo

### File modificati / creati
- `src/importer/turno_pdc_parser.py` — riscritto (510 righe)
- `tests/test_turno_pdc_parser.py` — NUOVO (21 test)

---

## 2026-04-16 — Step 2/6 redesign turni PdC: calendario italiano

### Contesto
Il turno PdC usa periodicita' `D` che significa "Domenica OPPURE festivo infrasettimanale". Per applicare correttamente una giornata di turno a una data del calendario reale serve un modulo che sappia:
- calcolare la domenica di Pasqua (mobile)
- conoscere tutte le festivita' fisse italiane
- decidere se un sabato o un feriale cade su una festivita'

### Modulo `src/italian_holidays.py`
File singolo, isolato (nessun import dal resto del progetto), utility puro.

**Festivita' fisse** (10): 1/1, 6/1, 25/4, 1/5, 2/6, 15/8, 1/11, 8/12, 25/12, 26/12

**Festivita' mobili** (2): Pasqua (Computus / algoritmo di Gauss, forma anonima Meeus-Jones-Butcher), Pasquetta (Pasqua+1).

**Patroni locali** (opt-in, 14 citta'): Milano (Sant'Ambrogio 7/12), Torino, Roma, Napoli, Venezia, Firenze, Bologna, Palermo, Bari, Genova, Verona, Trieste, Cagliari, Catania. NON inclusi di default — solo se `include_local=<citta>` e' passato.

**API pubblica**:
- `easter_sunday(year) -> date`
- `easter_monday(year) -> date`
- `italian_national_holidays(year) -> frozenset[date]` (cached)
- `italian_holidays(year, include_local=None) -> frozenset[date]`
- `is_italian_holiday(d, include_local=None) -> bool`
- `weekday_for_periodicity(d, include_local=None) -> str` (L/M/X/G/V/S/D)
- `matches_periodicity(d, periodicita, include_local=None) -> bool`
- `upcoming_holidays(start, end, include_local=None) -> list[date]`

**Regole**:
- Domenica normale -> `'D'`
- Festivo infrasettimanale (anche su sabato o feriale) -> `'D'`
- Patrono locale, se richiesto, -> `'D'`
- Festivo che cade di domenica resta `'D'` (nessun conflitto)

### Test — `tests/test_italian_holidays.py`
23 test unitari che coprono:
- Date di Pasqua verificate per 2024-2030 contro calendario liturgico
- Invariante Pasqua sempre domenica (2020-2050)
- Pasquetta = Pasqua+1, sempre lunedi
- Conteggio festivita' nazionali = 12/anno
- Contenuto festivita' 2026 verificato una per una
- `is_italian_holiday` casi true/false
- Patrono Milano opt-in, case-insensitive
- `weekday_for_periodicity` per giorni normali, festivi su sabato (25/04/26), Pasquetta su lunedi, Natale su venerdi
- `matches_periodicity` per varianti `LMXGVSD`, `LMXGVS`, `LMXGV`, `SD`, `S`, `D`
- `upcoming_holidays` single year + partial range + cross-year
- Cache lru stabile

Tutti 23/23 passano. Suite totale: 60 passed (1 fail pre-esistente su `test_meal_slot_gap`, non correlato).

### Prossimi step
3. Parser PDF turno PdC che usa sia lo schema DB v2 sia il calendario italiano
4. Rimettere online `POST /upload-turno-pdc`
5. Pagina frontend visualizzazione turni PdC
6. Builder interno isomorfo (validazione date contro calendario italiano)

### File creati
- `src/italian_holidays.py` — 175 righe, isolato, zero dipendenze interne
- `tests/test_italian_holidays.py` — 23 test

---

## 2026-04-16 — Step 1/6 redesign turni PdC: schema DB v2

### Contesto
Primo step del redesign dei turni PdC. Obiettivo: sostituire lo schema scheletro (`pdc_turno`/`pdc_prog`/`pdc_prog_train`) con uno schema che catturi il dettaglio Gantt (vettura, CVp/CVa, REFEZ, S.COMP, pallino accessori maggiorati) secondo le regole della skill `turno-pdc-reader.md`.

### Schema DB v2
4 nuove tabelle in `src/database/db.py`:

1. **`pdc_turn`** — header turno (codice, planning, impianto, profilo, validita', source_file)
2. **`pdc_turn_day`** — giornata del ciclo, chiave logica `(pdc_turn_id, day_number, periodicita)` + stats (lavoro/condotta/km/notturno/riposo) + flag `is_disponibile`
3. **`pdc_block`** — blocco grafico del Gantt, `block_type ∈ {train, coach_transfer, cv_partenza, cv_arrivo, meal, scomp, available}` + `accessori_maggiorati` (pallino nero)
4. **`pdc_train_periodicity`** — note periodicita' treni dalla pagina finale del PDF (testo + date JSON non-circola / circola-extra)

Tutti con FK cascade + indici su (impianto, codice, day_number, train_id).

### Migrazione
DROP IF EXISTS delle 3 tabelle vecchie + CREATE IF NOT EXISTS delle 4 nuove — idempotente, zero rischi (le vecchie erano vuote su entrambi i DB).

### Metodi CRUD in `db.py`
Rimossi: `import_pdc_turni`, `pdc_find_train`, `pdc_get_stats`, `pdc_get_depot_turno` (legati al vecchio schema).

Aggiunti:
- `insert_pdc_turn`, `insert_pdc_turn_day`, `insert_pdc_block`, `insert_pdc_train_periodicity`
- `clear_pdc_data`
- `get_pdc_stats`, `list_pdc_turns`, `get_pdc_turn`, `get_pdc_turn_days`, `get_pdc_blocks`, `get_pdc_train_periodicity`
- `find_pdc_train` (cerca treno nei blocchi PdC)

### Endpoint temporanei (`api/importers.py`)
- `POST /upload-turno-pdc` → **501** fino allo Step 3 (parser riscritto)
- `GET /pdc-stats` → ora usa `db.get_pdc_stats()` — torna `{loaded: false}` finche' vuoto
- `GET /pdc-find-train/{id}` → ora usa `db.find_pdc_train()`
- `GET /train-check/{id}` → sezione `pdc` ora usa `db.find_pdc_train()`

### Test
- `tests/test_database.py`: 2 nuovi test — `test_pdc_schema_v2_crud` (insert completo + tutte le query) + `test_pdc_old_tables_are_dropped`
- Tutti i 7 test DB passano.
- Non introdotta regressione sugli altri 28 test del repo.

### Prossimi step
2. Modulo calendario italiano (festivita' + `weekday_for_periodicity`)
3. Parser PDF turno PdC (nuovo, usa lo schema v2)
4. Rimettere online `POST /upload-turno-pdc`
5. Pagina frontend visualizzazione turni PdC (Gantt riusabile)
6. Builder interno isomorfo

### File modificati
- `src/database/db.py` — schema v2 + metodi CRUD nuovi
- `api/importers.py` — endpoint aggiornati, upload 501 temporaneo
- `tests/test_database.py` — 2 nuovi test

---

## 2026-04-16 — Skill turno PdC reader (contesto lettura turno personale)

### Contesto
Nuova fase: dopo il parser turno materiale serve imparare a leggere il **turno PdC** (Posto di Condotta) — il PDF ufficiale Trenord con i turni del personale di macchina/scorta per ogni impianto. Le stesse regole varranno anche per il builder interno: un turno costruito in COLAZIONE deve essere "isomorfo" a un turno PdC ufficiale.

### Regole consolidate con l'utente (via screenshot + spiegazione)

**Header pagina turno**: `IMPIANTO: <deposito> | TURNO: [<codice>] [<planning>] | PROFILO: <Condotta|Scorta> | DAL/AL`
- `Condotta` = macchinista; `Scorta` = capotreno.
- Validita' `DAL/AL` e' informativa, non operativa.

**Periodicita'** (label sopra il numero giornata):
- `LMXGVSD` (tutti), `LMXGVS` (no domenica), `LMXGV` (feriali), `SD`, `S`, `D`
- `D` significa **Domenica E festivo infrasettimanale** → serve calendario italiano (Capodanno, Epifania, Pasqua/Pasquetta, 25/4, 1/5, 2/6, 15/8, 1/11, 8/12, 25/12, 26/12). Patroni locali opzionali per impianto.

**Chiave logica giornata**: `(numero_giornata, periodicita)` — la stessa giornata puo' avere piu' righe se la periodicita' e' spezzata (es. giornata 2 esiste sia in `LMXGVS` sia in `D`, con Gantt diversi).

**Asse orario**: `3 → 24 → 1 → 2 → 3` (giornata operativa attraverso mezzanotte).

**Blocchi sopra l'asse**:
| Etichetta | Grafico | Tipo |
|---|---|---|
| `<num> <staz>` | linea continua | treno commerciale |
| `(<num> <staz>` | linea tratteggiata | vettura (deadhead) — `(` = numero vettura |
| `CVp <num>` | marker | Cambio Volante in **Partenza** |
| `CVa <num>` | marker | Cambio Volante in **Arrivo** |
| `REFEZ <staz>` | blocco | refezione (pausa pasto) |
| `S.COMP <staz>` | blocco lungo | a disposizione |
| `● <num>` | pallino nero | accessori maggiorati (preriscaldo invernale) |
| `Disponibile` | testo grande | riposo / disponibilita' |

**Numeri sotto l'asse**: minuti degli eventi (partenza/arrivo treno, partenza/arrivo vettura, inizio/fine refezione, cambi volante, inizio accessori). Ora completa = tick sopra + minuti sotto.

**Stats riga destra**: `Lav | Cct | Km | Not(si/no) | Rip`.

**Pagina finale turno**: `Note sulla periodicita' dei treni` — per ogni treno: periodicita' testuale + date di non-circolazione + date di circolazione extra. Sono autoritative.

### Output
- `.claude/skills/turno-pdc-reader.md` — NUOVA skill (solo locale, `.claude/` e' gitignorato) con:
  - Struttura documento + mapping blocchi grafici
  - Tabella festivita' italiane (fisse + mobili via Computus)
  - Schema JSON estratto
  - Proposta data model DB (`pdc_turn`, `pdc_turn_day`, `pdc_block`, `pdc_train_periodicity`)
  - Modulo calendario italiano (`easter_sunday`, `italian_national_holidays`, `weekday_for_periodicity`)
  - Use case: caricamento PDF + builder interno "isomorfo"
  - Note implementative (parser, calendario, frontend, test)

### Prossimi passi (dopo check utente)
1. Implementare modulo calendario italiano in `src/calendar/italian_holidays.py`
2. Rafforzare `src/importer/turno_pdc_parser.py` (esiste gia' a livello scheletro) usando le regole della skill
3. Creare tabelle `pdc_*` in `src/database/db.py` con migrazioni idempotenti
4. Endpoint di upload/query per turni PdC
5. Pagina frontend per visualizzare il turno PdC (riusa `GanttTimeline`)
6. Adattare il builder COLAZIONE per produrre turni nel medesimo schema

---

## 2026-04-16 — Reset turni salvati pre 15/04 (clean slate per redesign)

### Contesto
Stiamo ridisegnando tutto. I turni salvati esistenti (creati prima del 15/04/2026) sono dati di test ormai obsoleti — vanno via per partire da zero.

### Operazione (una tantum, NON modifica codice)
- DB locale `turni.db`: era già vuoto (0 saved_shift, 0 weekly_shift) — nessuna azione.
- DB Railway PostgreSQL: cancellati **20 record** da `saved_shift` con `created_at < '2026-04-15'`.
  - 0 record in `weekly_shift` e `shift_day_variant` (non ce n'erano)
  - DELETE eseguito in transazione con sanity check (rollback se rowcount > soglia)
  - Stato finale Railway: saved_shift=0, weekly_shift=0, shift_day_variant=0

### Comportamento NON cambiato
`db.clear_all()` continua a non toccare i `saved_shift` (riga 2010 di `src/database/db.py`). Il prossimo import PDF cancellerà solo segmenti/treni/turni materiale, lasciando intatti i turni salvati che verranno creati da qui in poi.

### Snapshot turni cancellati
Per traccia, prima del DELETE c'erano 20 turni — tutti di test, pre-redesign:
- 12 turni `ALESSANDRIA G1` (LV/SAB/DOM, varianti) creati 17/03–27/03
- 1 `ALESSANDRIA DISPONIBILE LV` del 27/03
- 10 duplicati `SONDRIO G1-G5 LV` del 02/04

---

## 2026-04-14 — Sessione A: CLAUDE.md + Sicurezza

### CLAUDE.md creato
- Documentato scopo, stack, glossario dominio, regole operative, convenzioni, roadmap

### Fix sicurezza
- `src/database/db.py`: rimossa password admin hardcoded `"Manu1982!"` → env var `ADMIN_DEFAULT_PASSWORD` o generazione random
- `server.py`: `JWT_SECRET` obbligatorio in produzione (se `DATABASE_URL` impostato)
- Creato `.env.example` con tutte le variabili ambiente
- Aggiunto `.env` a `.gitignore`

---

## 2026-04-14 — Sessione B: Ristrutturazione server.py

### server.py spezzato (2834 → 62 righe)
Struttura creata:
- `api/deps.py` — dipendenze condivise (DB, JWT auth, password utils)
- `api/auth.py` — 6 endpoint (register, login, me, admin/*)
- `api/health.py` — 3 endpoint (/, health, info)
- `api/upload.py` — 2 endpoint (upload PDF, delete DB)
- `api/trains.py` — 12 endpoint (query treni/stazioni, giro materiale, connections)
- `api/validation.py` — 4 endpoint (constants, validate-day, check-validity)
- `api/builder.py` — 4 endpoint (build-auto, build-auto-all, calendar, weekly)
- `api/shifts.py` — 9 endpoint (CRUD turni salvati/settimanali, timeline, used-trains)
- `api/importers.py` — 5 endpoint (turno personale, PdC, train-check)
- `api/viaggiatreno.py` — 8 endpoint (dati real-time)

### Service layer estratto
- `services/segments.py` — dedup_segments, serialize_segments, seg_get
- `services/timeline.py` — build_timeline_blocks (~280 righe di logica timeline)

---

## 2026-04-14 — Switch VT → ARTURO Live

### API ViaggiaTreno sostituite con ARTURO Live
- `services/arturo_client.py` — NUOVO: client API live.arturo.travel (httpx sincrono, nessuna auth)
- `api/viaggiatreno.py` — riscritto da 735 a 320 righe, usa arturo_client
- `api/importers.py` — train-check ora usa ARTURO Live (era VT diretto)
- URL `/vt/*` mantenuti per retrocompatibilità frontend legacy

### Mapping endpoint
| COLAZIONE `/vt/*` | ARTURO Live |
|---|---|
| autocomplete-station | `GET /api/cerca/stazione?q=` |
| departures | `GET /api/partenze/{id}` |
| arrivals | `GET /api/arrivi/{id}` |
| train-info | `GET /api/treno/{numero}` |
| solutions | `GET /api/cerca/tratta?da=&a=` |
| find-return | Combinazione partenze + arrivi |

---

## 2026-04-14 — Sessione C: Configurazione multi-azienda

### Sistema config/ creato
- `config/schema.py` — dataclass `CompanyConfig` con 40+ campi e default normativi italiani
- `config/trenord.py` — override specifici Trenord (25 depositi, 19 FR, CVL, tempi fissi)
- `config/loader.py` — `get_active_config()`, selezione via env var `COLAZIONE_COMPANY`

### src/constants.py → wrapper retrocompatibile
- Non contiene più valori hardcoded
- Legge tutto da `config/loader.get_active_config()`
- Esporta gli stessi nomi di prima → zero modifiche a validator/builder/consumer

### Multi-deposito nel DB
- Tabella `depot` (code, display_name, company, active) aggiunta a `db.py`
- `depot_id` nullable aggiunto a `material_turn`, `saved_shift`, `weekly_shift`
- Auto-seed depositi dalla configurazione attiva all'avvio
- Migrazioni idempotenti via `_run_migration()`

### Per aggiungere nuova azienda
1. Creare `config/nuovaazienda.py` con `CompanyConfig(...)`
2. Registrarlo in `config/loader.py` dict `configs`
3. Settare `COLAZIONE_COMPANY=nuovaazienda`

---

## 2026-04-14 — Sessione D: Setup frontend React + TypeScript

### Scaffold progetto
- `frontend/` creato con Vite + React + TypeScript
- Tailwind CSS 4 configurato via `@tailwindcss/vite` plugin
- Path alias `@/` → `src/` configurato in vite.config.ts + tsconfig
- Proxy API configurato in Vite dev server (tutte le route backend proxied a :8002)

### Dipendenze installate
- `tailwindcss`, `@tailwindcss/vite` — CSS utility framework
- `react-router-dom` — routing client-side
- `lucide-react` — icone (stile minimale)
- `clsx`, `tailwind-merge` — utility per classi CSS condizionali

### Design system
- Palette colori custom in `index.css` via `@theme` (background, foreground, primary blu ARTURO, sidebar scura)
- Font: SF Pro Display/Text con fallback a Segoe UI/Roboto
- Sidebar scura (171717) con navigazione attiva evidenziata

### Struttura frontend
```
frontend/src/
├── main.tsx              — entry point
├── App.tsx               — routing (BrowserRouter + Routes)
├── index.css             — Tailwind + design tokens
├── lib/
│   ├── api.ts            — client API con JWT auth (get/post/delete + login/register/getMe/getHealth/getDbInfo)
│   └── utils.ts          — cn(), fmtMin(), timeToMin()
├── hooks/
│   └── useAuth.ts        — hook autenticazione (user state, loading, logout)
├── components/
│   ├── Layout.tsx         — layout con sidebar + Outlet (redirect a /login se non autenticato)
│   └── Sidebar.tsx        — sidebar navigazione (Dashboard, Treni, Turni, Calendario, Import, Impostazioni)
└── pages/
    ├── LoginPage.tsx      — login/register con form
    ├── DashboardPage.tsx  — stats DB (segmenti, treni, turni materiale, day indices)
    └── PlaceholderPage.tsx — placeholder per sezioni in costruzione
```

### Route
- `/login` — pagina login/registrazione (pubblica)
- `/` — Dashboard (protetta)
- `/treni` — Ricerca Treni (placeholder)
- `/turni` — Gestione Turni (placeholder)
- `/calendario` — Calendario (placeholder)
- `/import` — Import PDF (placeholder)
- `/impostazioni` — Impostazioni (placeholder)

### Build verificata
- `tsc --noEmit` → 0 errori
- `npm run build` → 272KB JS + 15KB CSS

---

## 2026-04-14 — Redesign frontend: dark theme professionale

### Problema
Il primo design (sfondo grigio chiaro, card bianche) era troppo generico/template. Bocciato dall'utente.

### Nuovo design system
- **Palette scura** ispirata a Linear/Raycast: background #0a0a0b, card #131316, border #27272a
- **Accent blu elettrico** ARTURO (#3b82f6) con varianti hover/muted
- **Colori semantici** con varianti muted (success, warning, info, destructive)
- **Font**: Inter con font-features cv02/cv03/cv04/cv11
- **Scrollbar minimale** custom
- **Glow effect** su login page

### Componenti rifatti
- **Sidebar**: più compatta (w-56), icona brand con badge blu, sezioni Menu/Sistema, shortcut keyboard visibili on hover, avatar utente con iniziale
- **Layout**: spinner di caricamento animato, max-w-6xl centrato
- **Dashboard**: stat cards con accent colorati (blu/verde/giallo), badge "Operativo" pill, turni materiale con hover effect
- **Login**: sfondo scuro con glow blu diffuso, icona treno in contenitore con bordo primary, input scuri con focus ring blu, spinner nel bottone durante loading
- **Placeholder**: icona in contenitore muted, testo minimale

---

## 2026-04-14 — Pagina Cerca Treni (prima pagina operativa)

### Funzionalità implementate
- **Ricerca per numero treno**: cerca nel DB locale, mostra segmenti (stazione A → B, orari)
- **Dettaglio real-time espandibile**: pannello "Dati real-time (ARTURO Live)" con stato treno, operatore, ritardo, 14 fermate con orari arr/dep/binario/ritardo
- **Giro materiale**: se il treno ha un giro materiale nel DB, mostra la catena con posizione evidenziata
- **Ricerca per stazione**: autocomplete via ARTURO Live (nome stazione → suggerimenti con codice)
- **Partenze/Arrivi**: tabellone con numero treno, categoria, destinazione, operatore, orario, ritardo

### File
- `frontend/src/pages/TrainSearchPage.tsx` — ~450 righe, pagina completa
- `frontend/src/lib/api.ts` — aggiunte API: queryTrain, queryStation, listStations, getGiroChain, vtAutocompleteStation, vtDepartures, vtArrivals, vtTrainInfo
- `frontend/src/App.tsx` — route /treni punta a TrainSearchPage

### Note tecniche
- Due fonti dati separate: DB locale (dati PDF statici) e ARTURO Live (real-time)
- Nessuna "allucinazione": mostra solo dati dalle API, non inventa nulla
- Autocomplete stazione supporta nodi aggregati (node:milano = tutte le stazioni di Milano)

---

## 2026-04-14 — Pagina Turni salvati con timeline visiva

### Funzionalità implementate
- **Lista turni salvati** con filtro per tipo giorno (Tutti/LV/SAB/DOM)
- **Card turno espandibile**: nome, deposito, tipo giorno, numero treni, badge FR, conteggio violazioni
- **Stats in card**: prestazione (ore:min), condotta, orario inizio/fine
- **Timeline visiva**: barra colorata proporzionale con blocchi (treno, vettura, refezione, accessori, extra, spostamento, giro materiale)
- **Dettaglio timeline**: lista blocchi con tipo, label, orari, durata
- **Legenda colori**: 7 tipi blocco con colori distinti
- **Violazioni**: lista con icona e messaggio
- **Eliminazione**: conferma prima di cancellare
- **Stato vuoto**: placeholder quando non ci sono turni

### File
- `frontend/src/pages/ShiftsPage.tsx` — ~400 righe
- `frontend/src/lib/api.ts` — aggiunte API: getSavedShifts, deleteSavedShift, getShiftTimeline, getWeeklyShifts, deleteWeeklyShift + tutti i types
- `frontend/src/App.tsx` — route /turni punta a ShiftsPage

---

## 2026-04-14 — Pagina Builder Turno manuale (cuore del software)

### Funzionalità implementate
- **Configurazione**: selezione deposito (25 depositi), tipo giorno (LV/SAB/DOM), tipo accessori (Standard/Maggiorato/CVL), toggle FR
- **Ricerca treni**: per numero (DB locale) con risultati cliccabili per aggiunta
- **Connessioni intelligenti**: tab "Connessioni da [ultima stazione]" appare automaticamente dopo il primo treno
- **Lista treni nel turno**: con orari, stazioni, bottone VET (vettura/deadhead), bottone rimuovi
- **Validazione real-time**: si aggiorna automaticamente (300ms debounce) ad ogni modifica
  - Prestazione con limite max (8h30)
  - Condotta con limite max (5h30)
  - Refezione, Accessori
  - Violazioni con messaggi dettagliati
  - Badge "Valido" verde o "N violazioni" rosso
- **Timeline visiva**: barra colorata + lista blocchi dettagliata (Extra, Accessori, Treno, Refezione, Spostamento, Giro materiale) con orari e durate
- **Rientro deposito**: segnala automaticamente se manca il treno di rientro
- **Salvataggio**: campo nome + bottone "Salva turno" con feedback (spinner, "Salvato" verde)
- **Layout**: due colonne — builder a sinistra, pannello validazione sticky a destra

### File
- `frontend/src/pages/BuilderPage.tsx` — ~500 righe, pagina completa
- `frontend/src/lib/api.ts` — aggiunte: validateDayWithTimeline, getConnections, saveShift, AppConstants type
- `frontend/src/App.tsx` — route /builder
- `frontend/src/components/Sidebar.tsx` — aggiunta voce "Nuovo turno" con icona PlusCircle

---

## 2026-04-15 — Rebrand ARTURO + Timeline Gantt

### Brand ARTURO applicato
- **Font Exo 2** (variable, weight 100-900) — self-hosted da /public/fonts/
- **Colori brand**: #0062CC (primario), #0070B5 (secondario), #30D158 (dot verde), #38BDF8 (accent)
- **Palette dark**: background #0A0F1A, card #111827, text #F1F5F9, muted #94A3B8
- **Logo COLAZIONE**: componente React con font Exo 2 black + dot verde pulsante (stile ARTURO Live/Business)
- Animazione `pulse-dot` per il pallino verde

### Timeline Gantt orizzontale (stile PDF Trenord)
- Componente SVG `GanttTimeline` con griglia oraria 3→24→3
- Barre proporzionali per durata blocchi
- Testo verticale sopra le barre (numero treno + stazione)
- Linee tratteggiate per attese/spostamenti/refezione
- Colonne totali a destra: Lav, Cct, Km, Not, Rip
- Label giornata a sinistra (LV, SAB, DOM) con orari [inizio][fine]
- Deposito mostrato come label
- Wrapper `GanttFromValidation` per conversione dati validazione → Gantt

### File creati/modificati
- `frontend/public/fonts/Exo2-Variable.ttf`, `Exo2-Italic-Variable.ttf` — font self-hosted
- `frontend/src/index.css` — palette brand ARTURO + @font-face Exo 2
- `frontend/src/components/Logo.tsx` — NUOVO: logo COLAZIONE stile ARTURO
- `frontend/src/components/GanttTimeline.tsx` — NUOVO: timeline Gantt SVG
- `frontend/src/components/Sidebar.tsx` — usa Logo component
- `frontend/src/pages/LoginPage.tsx` — usa Logo component
- `frontend/src/pages/BuilderPage.tsx` — usa GanttFromValidation al posto delle barre colorate

---

## 2026-04-15 — Gantt dinamico v2 + unificazione Gantt in ShiftsPage

### Miglioramenti Gantt
- **Scala DINAMICA**: mostra solo le ore rilevanti (1h prima e 1h dopo il turno), non più 24h fisse
- **Barre più grandi**: BAR_H=18px (era 14), min 55px/ora (era ~37.5)
- **Testo più leggibile**: font size aumentati, stazione fino a 8 char (era 6)
- **Deposito duplice**: label deposito sia a inizio che a fine riga (come PDF)
- **Totali verticali**: Lav/Cct/Km/Not/Rip in colonna verticale a destra (era orizzontale)
- **Orari treno**: orario partenza sotto le barre dei treni se c'è spazio
- **SVG responsive**: width="100%" con viewBox, scrollabile orizzontalmente

### ShiftsPage unificata
- Rimossi componenti vecchi (TimelineBar, TimelineDetail, TimelineLegend)
- Usa GanttFromValidation come il BuilderPage — stesso stile ovunque

### Nota FR
- L'utente richiede Gantt a doppia riga per dormite FR (giorno 1 sera + giorno 2 mattina)
- Richiede supporto backend per blocchi multi-giorno — segnato per prossima iterazione

---

## 2026-04-15 — Tauri desktop app (macOS)

### Setup completato
- Rust 1.94.1 installato via rustup
- Tauri v2 configurato in `frontend/src-tauri/`
- Build produce `COLAZIONE.app` + `COLAZIONE_0.1.0_aarch64.dmg`
- Finestra 1280x800, min 900x600, resizable
- Identifier: `com.arturo.colazione`

### File creati
- `frontend/src-tauri/Cargo.toml` — dipendenze Rust (tauri v2, serde)
- `frontend/src-tauri/tauri.conf.json` — config app (titolo, dimensioni, bundle)
- `frontend/src-tauri/src/main.rs` — entry point Rust
- `frontend/src-tauri/build.rs` — build script
- `frontend/src-tauri/icons/` — icone placeholder (PNG blu #0062CC)

### Nota
- L'app desktop wrappa il frontend React — al momento richiede backend Python avviato separatamente
- Per Windows serve cross-compile o build su macchina Windows
- Le icone sono placeholder — da sostituire con logo COLAZIONE vero

---

## 2026-04-15 — Deploy Railway configurato per nuovo frontend

### Configurazione
- `railway.toml`: buildCommand aggiunto per buildare frontend React prima del deploy
- `nixpacks.toml`: NUOVO — configura nodejs_22 + python312 + gcc per build ibrida
- `server.py`: serve `frontend/dist/` (React build) in produzione, `static/` come fallback
- `api/health.py`: rimossa route `/` redirect (il frontend è servito dal mount statico)

### Come funziona in produzione
1. Railway esegue `cd frontend && npm install && npm run build`
2. Output in `frontend/dist/` (HTML + JS + CSS + assets)
3. FastAPI monta `frontend/dist/` su `/` come StaticFiles con `html=True`
4. Le API hanno priorità (router inclusi PRIMA del mount statico)
5. `railway up` per deployare

### Testato localmente
- `/api/health` → JSON ok
- `/` → serve index.html del frontend React
- Le due cose funzionano insieme senza conflitti

---

## 2026-04-15 — Palette slate più chiara + fix Tauri

### Palette v3 (slate chiaro)
- Background: `#1E293B` (era #0A0F1A — molto più chiaro)
- Card: `#273549` (era #111827)
- Sidebar: `#182336`
- Border: `#3D5472` (visibili)
- Muted: `#334B68`
- Card e sfondo ora distinguibili, bordi visibili, non più "buco nero"

### Fix Tauri
- API client rileva Tauri via `__TAURI__` window property → punta a `http://localhost:8002`
- CSP aggiornato per permettere `connect-src localhost:*`
- Il DMG funziona ma richiede backend avviato separatamente (sidecar non ancora integrato)

### Nota operativa
- Ogni modifica frontend richiede: `npm run build` per aggiornare `frontend/dist/`
- Per aggiornare il DMG: `npx tauri build`
- Per uso quotidiano: `uvicorn server:app --port 8002` + browser su `localhost:8002`

---

## 2026-04-15 — Redesign tema bianco + nuova Dashboard

### Palette light (bianca, pulita)
- Background: `#F7F8FA` (quasi bianco)
- Card: `#FFFFFF` (bianco puro)
- Foreground: `#0F172A` (testo scuro)
- Muted: `#F1F5F9` (grigio chiarissimo)
- Border: `#E2E8F0` (bordi leggeri)
- Sidebar: `#FFFFFF` (bianco con bordo destro)
- Primary: `#0062CC` (brand ARTURO blu) — era `#38BDF8` (cyan)
- Active sidebar: `bg-brand/8 text-brand` (sfumatura blu leggera)
- Scrollbar: grigio chiaro (#CBD5E1)

### Dashboard ridisegnata
- **Rimossi** i 4 stat cards tecnici (Segmenti, Treni unici, Turni materiale, Varianti giorno)
- **Saluto** personalizzato: "Buongiorno/Buon pomeriggio/Buonasera, [username]"
- **Quick actions**: 4 card con icone gradient colorate (Nuovo turno, Cerca treni, Turni salvati, Importa dati)
- **Turni recenti**: lista ultimi 5 turni salvati con deposito, tipo giorno, numero treni
- **Empty state**: messaggio + CTA "Crea turno" quando non ci sono turni

### SettingsPage creata (Impostazioni)
- Stats DB spostati qui (Segmenti, Treni unici, Turni materiale, Varianti giorno)
- Lista turni materiale importati
- Badge "Operativo" per stato sistema
- Route `/impostazioni` punta a `SettingsPage` (era `PlaceholderPage`)

### GanttTimeline adattato a tema chiaro
- Colori SVG hardcoded aggiornati per sfondo bianco
- text: `#0F172A` (era #F1F5F9)
- grid: `#CBD5E1` (era #475569)
- Barre treno: `#0062CC` brand blu (era #F1F5F9 bianco)
- Accessori/extra: grigi chiari (#CBD5E1, #E2E8F0)

### LoginPage
- Sfondo: gradiente bianco/azzurro sfumato (`from-slate-50 via-blue-50/30`)
- Card: bianca con ombra leggera
- Focus input: ring brand blu

### File modificati
- `frontend/src/index.css` — palette completa da dark a light
- `frontend/src/pages/DashboardPage.tsx` — riscritto: welcome + quick actions + turni recenti
- `frontend/src/pages/SettingsPage.tsx` — NUOVO: info sistema + stats DB
- `frontend/src/pages/LoginPage.tsx` — adattato a tema chiaro
- `frontend/src/components/Sidebar.tsx` — sidebar bianca, active state brand blu
- `frontend/src/components/GanttTimeline.tsx` — colori SVG per sfondo chiaro
- `frontend/src/App.tsx` — route impostazioni → SettingsPage

---

## 2026-04-15 — GanttTimeline v3: colori saturi + scala fissa

### Modifiche Gantt
- **Scala fissa 0-24**: griglia completa dalle 0 alle 24 ore (era dinamica)
- **Sfondo grigio chiaro**: wrapper `bg-[#F1F5F9]` con `rounded-lg p-3` per staccare dalla pagina bianca
- **Altezze differenziate per tipo blocco**:
  - Treno: 22px (barra grande, dominante)
  - Deadhead/spostamento/giro_return: 14px (media)
  - Accessori/extra: 10px (piccoli, secondari)
  - Tutte centrate verticalmente sullo stesso asse
- **Colori saturi e distinti**:
  - Treno: `#0062CC` (blu brand)
  - Deadhead/giro_return: `#7C3AED` (viola)
  - Accessori: `#F59E0B` (ambra)
  - Extra: `#FB923C` (arancione)
  - Spostamento: `#0891B2` (ciano)
- **Anti-sovrapposizione**: sistema di rilevamento collisioni tra label verticali, label shiftate verso l'alto se troppo vicine
- **Testo più grande e grassetto**: fontSize 11, fontWeight 900 per label treni
- **Durata** mostrata solo per blocchi treno (non accessori/extra)
- **Rimossi orari duplicati** sotto l'asse per evitare sovrapposizioni con numeri griglia

---

## 2026-04-15 — Deploy Railway risolto

### Problemi risolti
1. **`pip: command not found`**: `nixPkgs` custom sovrascriveva i default di nixpacks, rimuovendo Python
2. **`No module named pip`**: `python312Full` non bastava, il problema era nelle `cmds` custom
3. **Upload timeout CLI**: repo troppo grande (1.2GB per `src-tauri/target/`)
4. **`self.conn.execute()` su psycopg2**: PostgreSQL richiede `cursor().execute()`, fix in `db.py`

### Soluzione finale
- **Rimosso `nixpacks.toml`** completamente — nixpacks auto-rileva Python da `requirements.txt`
- **`railway.toml`** minimale: solo `startCommand` per uvicorn
- **`frontend/dist/`** committato nel repo (rimosso da `.gitignore` e `frontend/.gitignore`)
- **`.dockerignore`** creato: esclude `src-tauri/target/` (863MB), `node_modules/`, `frontend/src/`
- **Fix `db.py`**: `self.conn.cursor().execute()` in `_run_migration()` per compatibilità psycopg2

### Stato deploy
- Servizio: **Arturo-Turni** su Railway (progetto `affectionate-embrace` era sbagliato)
- URL: **web-production-0e9b9b.up.railway.app**
- Auto-deploy da GitHub attivo
- DB: PostgreSQL su Railway (separato da SQLite locale)

### Workflow aggiornato
1. Modifica codice frontend
2. `cd frontend && npm run build` per aggiornare `frontend/dist/`
3. `git add frontend/dist/ ...` + commit + push
4. Railway auto-deploya da GitHub

---

## 2026-04-15 — Pagina Calendario + Import PDF

### CalendarPage (`/calendario`)
- **Lista turni settimanali** con card espandibili (pattern ShiftsPage)
- Card header: nome, deposito, numero giorni, ore settimanali medie, note
- Card expanded: griglia giorni con varianti (LMXGV/SAB/DOM)
- Ogni variante mostra: treni, prestazione, condotta, badge FR/SCOMP, violazioni
- Eliminazione con conferma
- Empty state quando non ci sono turni settimanali

### ImportPage (`/import`)
- **3 sezioni upload** (una per tipo import):
  - **Turno Materiale** (primario): drag & drop PDF, mostra segmenti/treni/confidenza/warnings
  - **Turno Personale**: upload PDF, solo visualizzazione (non salva nel DB)
  - **Turno PdC (RFI)**: upload PDF, mostra turni importati
- Stato upload: idle → uploading (spinner) → success/error
- Stats correnti del DB in fondo (segmenti, treni, turni materiale, varianti giorno)
- Drop zone con drag & drop support

### Modifiche collaterali
- `api.ts`: tipi `DayVariant`, `WeeklyDay` tipizzati (era `Record<string, unknown>[]`)
- `api.ts`: funzioni `uploadTurnoMateriale()`, `uploadTurnoPersonale()`, `uploadTurnoPdc()`, `getPdcStats()` + helper `uploadFile()` per multipart FormData
- `api.ts`: tipi `UploadResult`, `TurnoPersonaleResult`, `TurnoPdcResult`, `PdcStats`
- `App.tsx`: route aggiornate, rimosso import `PlaceholderPage` (non più usato)

### File
- `frontend/src/pages/CalendarPage.tsx` — NUOVO (~300 righe)
- `frontend/src/pages/ImportPage.tsx` — NUOVO (~310 righe)
- `frontend/src/App.tsx` — modificato
- `frontend/src/lib/api.ts` — modificato

### Build
- `tsc --noEmit` → 0 errori
- `npm run build` → 335KB JS + 48KB CSS

---

## 2026-04-16 — Fix critico: 500 su /train su PostgreSQL (psycopg2 + %)

### Problema
Dopo il deploy delle query con LIKE multi-numero, su Railway (PostgreSQL) tutte le chiamate `/train/{numero}` rispondevano `Internal Server Error`. SQLite locale invece funzionava.

### Causa
Le mie query contenevano `%` letterali nelle stringhe:
```sql
'/' || train_id || '/' LIKE '%/' || ? || '/%'
```
psycopg2 interpreta i `%` come format specifier per i parametri. Trovando `%/` o `/%` "non riconosciuti", il driver crashava prima ancora di eseguire la query.

### Fix
Pattern LIKE costruito lato Python e passato come parametro normale, eliminando i `%` letterali dalla query string:
```python
like_pattern = f"%/{train_id}/%"
cur.execute(
    "... WHERE train_id = ? OR '/' || train_id || '/' LIKE ?",
    (train_id, like_pattern),
)
```
Funziona identico in SQLite e PostgreSQL.

### Query fixate
- `query_train()` — endpoint `/train/<num>`
- `get_material_cycle()` — costruzione catena giro materiale
- `get_material_turn_info()` — info turno per un treno

### Test
Verificato in locale: match esatto, match slash-joined, no false positive da substring, get_material_cycle e get_material_turn_info ritornano dati corretti.

### File modificato
- `src/database/db.py` — 3 query

---

## 2026-04-16 — Fix giro materiale ricerca per train_id slash-joined

### Problema
Dopo il merge multi-numero (commit precedente), cercando `3086` via `/giro-chain/3086`:
- `query_train()` trovava il segmento `3085/3086` (fix gia' presente)
- MA `get_material_cycle()` e `get_giro_chain_context()` NON costruivano la chain perche' cercavano `train_id` come chiave esatta in dict/array interni

Sintomo: API ritornava `chain=[], position=-1, total=0` anche se il segmento esisteva.

### Fix
- `get_material_cycle()`: aggiunta funzione locale `_canonical_tid(needle)` che cerca la chiave canonica nel `train_info` dict, provando prima match esatto e poi `needle in key.split("/")`. Usata come punto di partenza della catena.
- `get_giro_chain_context()`: aggiornato il calcolo di `position` per accettare match slash-joined (`train_id in cid.split("/")`).

### Verifica end-to-end
Con seed DB (`3085/3086` da GALLARATE a VENTIMIGLIA + `10606` rientro):
- `/giro-chain/3086` → chain=[3085/3086, 10606], position=0, material_type=E464N ✓
- `/giro-chain/3085` → stesso risultato ✓
- `/giro-chain/10606` → prev=3085/3086, position=1 ✓

Badge `E464N` visibile in `/impostazioni` accanto al turno `1100` (screenshot).

### File modificati
- `src/database/db.py` — `get_material_cycle` + `get_giro_chain_context`
- `.claude/launch.json` — aggiunto config backend per preview locale

---

## 2026-04-16 — Parser v2: accessori, CVL/CB, multi-numero + badge frontend

### Nuove regole di riconoscimento sul PDF
L'utente ha definito 3 regole aggiuntive da applicare dopo l'estrazione dei segmenti grezzi:

1. **Accessori inizio/fine giornata**: il PRIMO e l'ULTIMO segmento di ogni `(turno, day_index)` vengono marcati come `is_accessory=1`. Rappresentano setup/wrap-up gia' definiti per il macchinista, non servizi commerciali.

2. **CVL / CB (Cambio Veloce Locomotiva / Cambio Banco)**: 2+ segmenti consecutivi con span totale ≤ 80 minuti (dal `dep_time` del primo all'`arr_time` dell'ultimo) vengono marcati con `segment_kind='cvl_cb'`. Algoritmo a finestra scorrevole che gestisce correttamente burst multipli in una stessa giornata.

3. **Treni multi-numero sulla stessa barra rossa**: quando due numeri treno (es. 3085 e 3086) condividono identiche stazioni e orari, il parser li fonde in un unico segmento con `train_id="3085/3086"` (sort numerico, duplicati eliminati).

### Modifiche DB (`src/database/db.py`)
- Tabella `train_segment`:
  - Nuova colonna `is_accessory INTEGER DEFAULT 0`
  - Nuova colonna `segment_kind TEXT DEFAULT 'train'` (valori: `train`, `cvl_cb`)
  - Commento chiarifica che `train_id` puo' contenere multipli ID separati da `/`
- Migrazioni idempotenti aggiunte per entrambe le colonne
- `TrainSegment` dataclass aggiornata con i 2 nuovi campi
- `insert_segment` e `bulk_insert_segments` aggiornati per i nuovi campi

### Query API flessibili per slash
Aggiornate 3 query per matchare ID sia esatti sia "token in lista slash-separated":
```sql
WHERE train_id = ? OR '/' || train_id || '/' LIKE '%/' || ? || '/%'
```
- `query_train()` — ricerca principale treno
- `get_material_cycle()` — primo SELECT del giro
- `get_material_turn_info()` — anche include ora `material_type` nel SELECT

Cercando `3086` trova sia righe `3086` che righe `3085/3086`; cercando `60` NON matcha `10606` (grazie ai separatori `/`).

### Parser (`src/importer/pdf_parser.py`)
- `ParsedSegment` dataclass: nuovi campi `is_accessory`, `segment_kind`
- Nuove funzioni pure:
  - `_time_to_min(hhmm)` helper
  - `mark_accessory_segments(segments)` — flag primo/ultimo per `(turno, day)`
  - `mark_cvl_cb_segments(segments, max_span_min=80)` — finestra scorrevole
  - `merge_multinumber_segments(segments)` — fonde segmenti identici tranne train_id
- `parse_pdf()` applica la pipeline dopo il dedup:
  ```
  dedup → merge_multinumber → mark_accessory → mark_cvl_cb
  ```
- Dict segmento e TrainSegment DB popolati con i nuovi campi

### Frontend (badge material_type)
- `lib/api.ts`:
  - `DbInfo.material_turns[].material_type?: string`
  - `GiroChainContext.material_type?: string`
- `TrainSearchPage.tsx`: badge brand-blu `E464N` accanto a "Giro materiale — turno X"
- `SettingsPage.tsx`: badge inline nella lista dei turni materiale
- `get_giro_chain_context()` (backend): restituisce ora anche `material_type`
- `frontend/dist/` rigenerato: 335KB JS + 48KB CSS, 0 errori TS

### Test
- 6 casi funzionali su merge/accessory/CVL con assert (tutti passano)
- Test multi-numero DB: query('3086') trova '3085/3086', `60` non matcha `10606`, `material_type` persistito correttamente
- `tests/test_database.py` e `tests/test_builder.py` tutti verdi

### Impatto
- PDF futuri importati avranno `is_accessory`, `segment_kind` e multi-numero mergiati automaticamente
- Dati gia' importati restano invariati (default 0/'train'/single-id) finche' non reimportati
- Nessuna breaking change API: i nuovi campi sono opzionali lato frontend

### File modificati
- `src/database/db.py` — schema + migrazioni + insert + 3 query + get_giro_chain_context
- `src/importer/pdf_parser.py` — dataclass + 4 funzioni nuove + pipeline
- `frontend/src/lib/api.ts` — tipi
- `frontend/src/pages/TrainSearchPage.tsx` — badge
- `frontend/src/pages/SettingsPage.tsx` — badge
- `frontend/dist/*` — build aggiornata

---

## 2026-04-16 — Parser turno materiale: estrazione tipo locomotiva

### Contesto
Nell'intestazione di ogni turno materiale (prima pagina, prima del Gantt) c'e' una tabella "Impegno del materiale (n.pezzi)" che elenca i pezzi del convoglio:
```
Pezzo        Numero
npBDL        2
nBC-clim     10
E464N        2
```
Le righe lowercase (`npBDL`, `nBC-clim`) sono carrozze, la riga UPPERCASE (`E464N`) e' la locomotiva. Il parser prima non estraeva questo dato.

### Modifiche
- **`src/database/db.py`**:
  - Colonna `material_type TEXT DEFAULT ''` aggiunta a `material_turn`
  - Migrazione idempotente: `ALTER TABLE material_turn ADD COLUMN material_type TEXT DEFAULT ''`
  - `insert_material_turn()` accetta parametro opzionale `material_type`
- **`src/importer/pdf_parser.py`**:
  - Nuova regex `RE_LOCO` per codici locomotiva Trenord (E464, E464N, E484, ETR*, ALn*, ALe*, TAF, TSR)
  - Nuova funzione `extract_material_type(words)` con 2 strategie:
    1. Anchor su "Impegno" + scansione della zona sottostante (tabella)
    2. Fallback: scansione di tutta l'header area (top < 110 pt)
  - `parse_pdf()` costruisce `turno_material_types: dict[turn_number, str]` registrando il primo match per turno
  - Il dict `material_turns` ritornato include `material_type`
  - `PDFImporter.run_import()` passa `material_type` a `insert_material_turn()`
- **`.claude/skills/turno-materiale-reader.md`**:
  - Nuova sezione "Tabella Impegno del materiale" con convenzione lowercase/uppercase
  - Elenco codici locomotiva riconosciuti dalla regex
  - Schema JSON aggiornato con campo `material_type`

### Test
- Regex: verificata su E464/E464N/E484/ETR425/TAF/TSR/ALn668 (match) + npBDL/nBC-clim/10606 (no match)
- extract_material_type: 5 casi di test (tabella standard, fallback header, nessuna loco, lista vuota, ETR)
- `tests/test_database.py` e `tests/test_builder.py`: tutti passanti

### Impatto
- Import PDF futuri registreranno `material_type` nel DB
- I turni gia' importati avranno `material_type=''` — si popoleranno al prossimo re-import del PDF
- `GET /material-turns` (via SELECT *) ritorna automaticamente il nuovo campo senza modifiche API

### File modificati
- `src/database/db.py` — schema + migrazione + insert_material_turn
- `src/importer/pdf_parser.py` — regex + extract_material_type + parse_pdf + run_import
- `.claude/skills/turno-materiale-reader.md` — documentazione

---

## 2026-04-16 — Fix import PDF su PostgreSQL (FK violation)

### Problema
In produzione (PostgreSQL su Railway) l'import di un PDF turno materiale falliva con:
```
update or delete on table "material_turn" violates foreign key constraint
"day_variant_material_turn_id_fkey" on table "day_variant"
DETAIL: Key (id)=(1) is still referenced from table "day_variant".
```
In locale (SQLite) il problema non si manifestava perché SQLite non applica le FK per default.

### Causa
In `src/database/db.py::clear_all()` l'ordine dei DELETE cancellava `material_turn` PRIMA di `day_variant`, che però ha una FK verso `material_turn`. PostgreSQL (che applica sempre le FK) rifiutava l'operazione.

### Fix
Riordinati i DELETE in modo che i figli (che hanno FK verso `material_turn`) vengano cancellati per primi, poi il padre:
1. `non_train_event` (nessuna FK)
2. `train_segment` (figlio)
3. `day_variant` (figlio) ← spostato qui prima di material_turn
4. `material_turn` (padre) ← ora per ultimo

Nessuna migrazione DB necessaria: è solo un riordino di statement.

### File modificato
- `src/database/db.py::clear_all()` — ordine DELETE corretto

---

## 2026-04-16 — Fix routing SPA su Railway (404 su /login)

### Problema
Aprendo `web-production-0e9b9b.up.railway.app/login` (o qualsiasi altra route React Router come `/treni`, `/turni`, ecc.) il server rispondeva `{"detail":"Not Found"}` invece di servire il frontend.

### Causa
`StaticFiles(html=True)` di Starlette serve `index.html` solo per la root `/`. Per qualsiasi altro path che non corrisponde a un file statico esistente ritorna 404. Le route SPA gestite lato client da React Router non sono file fisici sotto `frontend/dist/`, quindi cadevano nel 404.

### Fix
- `server.py`: nuova classe `SPAStaticFiles(StaticFiles)` che cattura il 404 e fa fallback a `index.html`, così React Router può gestire la route lato client.
- Eccezione: i path che iniziano con `api/` o `vt/` mantengono il 404 originale (i client API ricevono JSON 404 coerente, non HTML).
- Mount `/` aggiornato per usare `SPAStaticFiles` al posto di `StaticFiles`.

### Verifica locale
| Route | Prima | Dopo |
|---|---|---|
| `/` | 200 (index.html) | 200 (index.html) |
| `/login` | 404 JSON | 200 (index.html → React Router) |
| `/treni` | 404 JSON | 200 (index.html → React Router) |
| `/api/health` | 200 JSON | 200 JSON |
| `/api/nonexistent` | 404 JSON | 404 JSON (immutato) |
| `/favicon.svg` | 200 | 200 |

### File modificato
- `server.py` — aggiunta classe `SPAStaticFiles`, mount `/` aggiornato

---

## 2026-04-15 — Skill turno materiale reader

### Contesto appreso (insegnato dall'utente con screenshot PDF)
Il PDF turno materiale Trenord ha struttura Gantt orizzontale:
- **Asse X**: ore 0-23
- **Colonna sinistra**: periodicita (LV 1:5, 6, F, Effettuato 6F) + numero giro
- **Segmenti**: stazione origine (verde) → numero treno (blu) → stazione arrivo (verde)
- **Barra rossa**: durata viaggio, numeri sotto = minuti partenza/arrivo
- **Suffisso "i"**: materiale vuoto (senza passeggeri), destinazione tipica Fiorenza
- **DISPONIBILE**: materiale fermo, nessun servizio
- **Colonna "Per"**: sequenza giornate + Km

### Skill creata
- `.claude/skills/turno-materiale-reader.md` — skill completa con:
  - Struttura documento PDF
  - Come leggere la griglia Gantt
  - Codici periodicita (LV, 6, F, 6F)
  - Tipologie segmenti (commerciale, vuoto, disponibile)
  - Schema JSON per estrazione dati strutturati
  - Relazione turno materiale → turno personale
  - Note per implementazione parser

### Memory aggiornata
- `reference_turno_materiale.md` — puntatore rapido alla skill
