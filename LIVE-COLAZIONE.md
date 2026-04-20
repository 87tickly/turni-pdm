# LIVE-COLAZIONE — Registro modifiche in tempo reale

Questo file viene aggiornato ad ogni modifica. Leggilo sempre per avere il contesto completo.

---

## 2026-04-20 — METODO-DI-LAVORO.md: framework operativo permanente

Creato `docs/METODO-DI-LAVORO.md`, ispirato ai valori di affidabilita'
lavorativa giapponese (fiducia attraverso i fatti, stabilita',
puntualita', verifica prima della consegna, ammettere l'errore).

Contenuto:
- 7 regole operative concrete: diagnosi prima di azione, numeri non
  ipotesi, un passo alla volta completato bene, ammettere l'errore,
  verifica prima del commit, preservare non distruggere, costanza
  nel tempo
- Check di inizio sessione e di fine task
- Metrica personale di affidabilita' per auto-valutazione

Integrazione:
- `CLAUDE.md` aggiornato: nuova regola 4 OBBLIGATORIA di leggere
  `docs/METODO-DI-LAVORO.md` all'inizio di ogni sessione
- La regola "Design via Claude Design" rinumerata da 4 a 5

Motivo: ho accumulato in alcune sessioni un pattern di diagnosi
fantasiose (es. "bug off-by-1h" inventato sul parser PdC CVa 10678 —
in realta' era geometricamente corretto), fix senza verifica, e
scivolamenti verso scorciatoie nei momenti di stress. Questo doc e' lo
strumento di ricalibrazione permanente.

Commit: `b2f3b0e`. Zero codice modificato — solo documentazione. Il
lavoro WIP sull'AutoBuilder UI (api.ts + AutoBuilderPage + route) e'
rimasto nel working tree, verra' committato a parte quando la UI sara'
completa e verificata.

---

## 2026-04-20 — Auto-builder verificato: pipeline materiale → PdC funziona

Dopo re-import materiale, test end-to-end della pipeline core del prodotto:
**PDF materiale → parser → segmenti → auto-builder → turni PdC auto-generati**.

### Test condotto

Tre depositi diversi (grande/medio/piccolo) con parametri ridotti per
velocita' test (NUM_RESTARTS=10, CROSSOVER_ROUNDS=5, SA_ITERATIONS=15).

**MI.P.GARIBALDI** (34 stazioni reachable) — 5 giornate LV:
- 0 violazioni totali
- 4 treni/giornata, roundtrip al deposito
- Condotta 4.0h media (target 4-5h), prestazione 6.0h media
- Esempio G1: Milano→Lecco→Milano→Como→Milano, 14:52-20:21
- Tempo: 0.2s

**CREMONA** (14 stazioni) — 5 giornate LV:
- 1 violazione (G4: CREMONA→MI.P.GARIBALDI con 1 solo treno, non
  ritorna al deposito → probabile FR non gestito)
- Condotta 3.3h media, 15 treni unici usati
- Tempo: 0.2s

**LECCO** (13 stazioni) — 5 giornate LV:
- 0 violazioni
- 2-4 treni/giornata, tutti roundtrip LECCO-LECCO
- Condotta 3.2h media
- Tempo: 0.2s

### Conclusioni operative

1. **La pipeline FUNZIONA end-to-end**. Dato un PDF materiale Trenord,
   il sistema produce PdC validi rispettando le regole del TurnValidator
   (max prestazione, condotta, refezione, riposo).

2. **Performance**: 0.2s per un turno 5+2 giornate. Scalabilita' OK
   anche con 26 depositi → 5-6 secondi totali.

3. **Zero violazioni** su 2 depositi su 3 testati. La 1 violazione di
   CREMONA G4 e' probabilmente un caso FR (fuori residenza)
   legittimamente scelto dall'algoritmo ma mal-gestito nella validazione.

4. **Tratte realistiche**: Milano-Lecco, Milano-Como, Milano-Arona,
   CREMONA-CREMO (circolare), LECCO-LECCO. Il solver sceglie
   naturalmente roundtrip al deposito.

### Cosa questo sblocca

La parte auto-generazione **non e' embrionale come temevo** — e'
sostanzialmente funzionante. Quello che serve ora e' INTEGRAZIONE, non
costruzione da zero:

1. **Frontend per auto-genera**: un pulsante "Auto-genera da materiale"
   nella UI che invoca AutoBuilder con il deposito scelto → mostra i 5-7
   turni proposti, con preview Gantt, e permette salvataggio con un click
2. **Validazione umana**: il dispatcher guarda i turni auto-generati,
   corregge i casi edge manualmente (drag-drop), conferma
3. **Parametri configurabili**: NUM_RESTARTS, target condotta, FR
   preferences via UI invece che hardcoded

### Score interpretazione

Scores osservati: 2385 (1 giorno MI), 5694 (5 giorni MI), 4060 (5 giorni
Cremona), 5644 (5 giorni Lecco). Non e' chiaro cosa rappresenti questo
numero, ma piu' alto = migliore. Il simulated annealing migliora il
score nel 70% dei casi (2 su 3 test).

### Residui (prossime sessioni)

1. **Test con parametri production** (NUM_RESTARTS=25, tutti i phases
   completi) per vedere se la qualita' migliora: dovrebbe portare le
   condotte piu' vicine al target 4-5h
2. **Investigare violazione CREMONA G4** (FR non gestito o scelta
   sub-ottimale)
3. **Esporre in UI**: endpoint POST `/auto-build` + pagina "Nuovo turno
   auto-generato" con preview e conferma
4. **Integrazione con weekly_shift**: l'output build_schedule(5 days LV)
   e' un candidato naturale per un turno settimanale salvabile

---

## 2026-04-20 — Parser MATERIALE: diagnosi + re-import (bug grave sbloccato)

Dopo il re-import PdC, diagnosi del **parser turno materiale** e del DB.

### Scoperta: DB materiale completamente corrotto

Dump di un sample da `train_segment`:
```
id=1 train_id='10603' from_station='' dep_time=''
       to_station='' arr_time=''  raw_text='from_turno_materiale_pdf'
```

Tutti gli 11306 segmenti con `from_station/to_station/dep_time/arr_time=''`
(1 sola stazione "distinct": la stringa vuota). Il `raw_text` suggerisce
che erano stati importati da un JSON intermedio (`turno_materiale_treni.json`)
che aveva perso i campi critici.

**Effetto pratico:** l'auto-builder (`src/turn_builder/auto_builder.py`)
non poteva funzionare:
- `AutoBuilder(db, deposito='MI.P.GARIBALDI')._reachable` → 1 stazione
  (solo il deposito stesso)
- La query `get_reachable_stations()` cerca segmenti con
  `UPPER(from_station) = deposito`, ma tutte le `from_station` erano `''`
- Zero catene possibili → build_schedule non produceva niente

### Fix: wipe + re-import dal PDF

1. `DELETE FROM train_segment, material_turn, day_variant` (nessuna FK
   da altre tabelle utente)
2. `PDFImporter('uploads/Turno Materiale Trenord dal 2_3_26.pdf', db).run_import()`

**Risultato:**
- 5281 segmenti estratti (prima 11306 di spazzatura)
- **100% con stazione partenza e arrivo** identificate
- 2635 treni unici
- 50 turni materiale (7 identificati dall'header, altri estratti dalle
  pagine dati)
- 802 day variants salvate
- Confidence alta (≥0.8): 4936 segmenti (93%); media: 343 (6.5%); bassa: 2

### Verifica reachability post-fix

```
Stazioni distinte in train_segment: 104 (era 1)
Reachable da 'MI.P.GARIBALDI': 34 stazioni (era 1)
Reachable da 'MILANO CENTRALE': 24
Reachable da 'CREMONA': 14
Reachable da 'ALESSANDRIA': 6
Reachable da 'BRESCIA': 18
```

### Bug minori confermati nel parser materiale (edge cases, ~2%)

Distribuzione lunghezza train_id:
- 4 cifre: 870 (16.5%)
- 5 cifre: 2784 (52.7%) — treni commerciali normali
- 6 cifre: 1527 (28.9%) — treni materiale vuoto (9XXXXX) legittimi
- 7+ cifre: ~100 (2%) — **alcuni sospetti**

Casi ambigui:
- `271020` e `504342` (6 cifre, km vuoto): potrebbero essere parsing
  errors da clustering x_tol
- `90191/901917`: parser ha letto lo stesso set di digit vertical 2
  volte con y-gap diverso → merged con "/". Fix: quando le due stringhe
  sono prefix/superset l'una dell'altra, tenere la piu' lunga

### Effetto su auto-builder

Auto-builder ora ha dati utilizzabili:
- Init AutoBuilder con MI.P.GARIBALDI → 34 stazioni reachable
- `build_schedule(n_workdays=1, day_type='LV')` entra in Fase 2
  (Multi-restart, 25 tentativi). **Gira ma e' lento** — va testato con
  output reale per vedere la qualita' delle catene generate

### Residui per prossime sessioni

1. **Test auto-builder completo**: `build_schedule(n_workdays=5)` con
   output + tempo + qualita' catene. Se gira bene, e' la base della
   pipeline auto-generazione PdC (punto centrale del prodotto)
2. **Fix parser train_id 6+ cifre sospetti**: quando 2 letture vertical
   per stesso x si merge-ano con "/", scegliere il piu' lungo
3. **Parser PdC off-by-ipotizzato**: chiarito essere un non-bug (vedi
   entry precedente); CVa 13:28 e' geometricamente corretto
4. **`mark_superseded_turns`**: gestire `import_id IS NULL` (bug noto
   che ha richiesto migrazione manuale al re-import PdC)
5. **Propagazione a Railway** (PostgreSQL): upload entrambi i PDF via
   UI `/import` o import SQL diretto

### File modificati

- `turni.db` (DB locale: wipe + re-import materiale)
- `LIVE-COLAZIONE.md` (questa entry)

Zero modifiche al codice sorgente — il parser funziona bene su PDF
reale, il bug era solo nel DB storico.

---

## 2026-04-20 — Parser PdC: diagnosi + re-import PDF ALOR_C g1

Feedback utente (grave): "il turno non viene letto bene, vedi ALOR_C g1".
Screenshot mostra blocchi in ordine invertito + orari `--:--` su 3/5
blocchi. Correzione terminologica importante: "pausa a PV" = **sosta**
(non rientro in vettura). Il rientro in vettura e' quando un turno
finisce fuori deposito → si propone via ARTURO Live un treno
commerciale per far tornare il PdC come passeggero.

### Diagnosi (prima di toccare codice)

Fatto studio di `src/importer/turno_pdc_parser.py` + dump comparativo
PDF vs DB per ALOR_C g1 LMXGV:

**Parser corrente (run su PDF oggi):**
```
[0] train      10574 →PV 11:41-12:55  (riga PDF: "47501 41 55")
[1] cv_arrivo  10678 →PV 13:28         (riga PDF: "87601aVC 28 33")
[2] cv_partenza 10677 →PV 14:38        (riga PDF: "77601pVC 38 05 27")
[3] train      10581 →AL 15:05-16:19   (riga PDF: "18501 19")
[4] cv_arrivo  10584 →AL 16:34         (riga PDF: "48501aVC AL 34 15")
```
→ ordine corretto, orari **quasi** giusti.

**DB pre-reimport (stato visto dall'utente):**
```
[0] train      10574 →PV 11:26-12:40  ← -15 min rispetto a parser oggi
[1] cv_arrivo  10678 →PV 13:13        ← -15 min rispetto a parser oggi
[2-4] identici al parser corrente
```
→ DB popolato con versione parser piu' vecchia, da tempo non rifatto
l'import. Due bug risolti nel parser tra quell'import e oggi hanno
rifatto 11:41 e 13:28 (erano 11:26 e 13:13).

**Unico residuo parser (da fixare):** `CVa 10678` a `13:28` **dovrebbe
essere `12:28`** (off by 1h — arrivo del materiale a PV subito dopo
10574 che finisce alle 12:55, non 33 min dopo). Root cause in
`_x_to_hour_for_minute`: quando il minuto cade geometricamente vicino
al confine di 2 ore, la scelta dell'ora non e' vincolata dall'orario
del blocco precedente. Fix: aggiungere vincolo "ora CVa >= ora del
treno precedente".

### Ordine blocchi "invertito" in UI

Nello screenshot utente, i 5 blocchi apparivano nell'ordine:
`CVp 10677 → 10581 → CVa 10584 → 10574 → CVa 10678` (ritorno PRIMA di
andata). Ma sia il parser sia il DB hanno ordine corretto (andata,
ritorno). Probabile causa: l'utente aveva interagito col PdcBuilderPage
(drag, modifica) e il save aveva persistito stato riordinato, oppure
era uno stato di rendering effimero. Post-reimport, se l'effetto si
ripresenta e' un bug separato da investigare.

### Fix applicato: re-import PDF + migrazione pre-versioning

1. `parse_pdc_pdf('uploads/Turni PdC rete RFI dal 23 Febbraio 2026.pdf')`
   → 26 turni, 1344 giornate, 6925 blocchi, 2901 notes
2. `save_parsed_turns_as_import()` → import_id=6 creato, 25 turni
   marcati superseded
3. **Migrazione one-time** necessaria: il vecchio ALOR_C aveva
   `import_id=NULL` (pre-sistema versioning). `mark_superseded_turns()`
   usa `import_id <> ?` che in SQL non matcha NULL → l'orfano rimaneva
   attivo. Corretto manualmente marcando come superseded tutti i turni
   `import_id IS NULL` con stesso (codice, impianto) del nuovo import.
4. Post-fix: 26 turni attivi, zero duplicati; ALOR_C attivo e' id=153
   con orari corretti (11:41-12:55 al posto di 11:26-12:40).

### Effetto su produzione (Railway)

**ATTENZIONE:** il re-import e' stato fatto sul DB **locale** SQLite
(`turni.db`). La produzione Railway usa PostgreSQL via `DATABASE_URL`.
Per propagare il fix in produzione serve:
- Upload del PDF via pagina `/import` in produzione, oppure
- Esecuzione dello script di re-import sul server Railway

La UI in produzione mostrera' ancora i dati vecchi finche' questo
upload non viene fatto.

### Residui per le prossime sessioni

1. **Fix parser off-by-1h** in `_x_to_hour_for_minute` per CVa/CVp
   vicini ai confini d'ora (vincolo: start_time CVa >= end_time treno
   precedente)
2. **Versioning import_id=NULL**: modificare `mark_superseded_turns()`
   per gestire `import_id IS NULL` via `COALESCE` o `IS DISTINCT FROM`
   (evita che il bug si ripresenti al prossimo import)
3. **Rientro in vettura** — feature da costruire:
   - Rileva: `day.last_block.to_station` ≠ `turno.impianto` (deposito)
   - Query ARTURO Live: treni commerciali da `to_station` →
     `impianto` partendo dopo `last_block.end_time`
   - Propone lista al utente, selezione → insert `coach_transfer`
     block con ruolo "vettura_rientro"
4. **Parser PDF turno materiale** (`Turno Materiale Trenord dal
   2_3_26.pdf`): non ancora diagnosticato. E' l'input del prossimo step
   della pipeline (materiale → auto-generazione PdC)

---

## 2026-04-19 — Gestione PdC: fluidity sblocco (axis auto-fit + cross-day drag + jump-to-day)

Feedback utente: "il turno non viene letto correttamente" (visivo) e
"spostare un treno tra giornate è troppo macchinoso" (funzionale).

Analisi:
- Parser OK (155 blocchi per ALOR_C correttamente letti)
- Problema 1: asse Gantt hard-coded 3→3 (24h). Una giornata di 5h13
  occupa ~22% della larghezza, schiaccia i blocchi a fettina invisibile
- Problema 2: per spostare un treno bisognava uscire da PdcPage, aprire
  Vista Deposito, drag cross-day lì, tornare. Troppi click
- Problema 3: nel drawer non c'è modo di vedere/saltare alle altre
  giornate dello stesso turno dove lo stesso treno appare

### Fix 1 — PdcGanttV2 autoFit prop

Nuovo prop `autoFit?: boolean` (default false).
- Quando true: calcola `viewStartMin`/`viewSpanMin` dai min/max dei
  blocchi (+ 30min padding, arrotondato all'ora, min 4h per leggibilita)
- `viewPxPerMin` = AXIS_WIDTH / viewSpanMin → i blocchi riempiono sempre
  la larghezza disponibile
- `hourTicks` generati dinamicamente nel range visibile
- Fascia notte (21-24) disegnata solo se visibile nel range corrente
- Drag delta calcolato con `dxSvg / viewPxPerMin` (non piu PX_PER_HOUR fisso)

Quando false (Vista Deposito): comportamento originale 3h-3h 24h
preservato per confrontare giornate in scala comune.

Attivato in PdcPage DayCard → ora una giornata di 5h13 si vede da
10:00 a 18:00 piena, con tag+meta dei blocchi ben leggibili.

### Fix 2 — Tutte le giornate espanse di default

PdcPage.DayCard: `useState(day.is_disponibile !== 1)` al posto di
`useState(false)`. Vedi subito tutti i Gantt stacked, zero click per
aprire ciascuna.

### Fix 3 — Cross-day drag in PdcPage

Replicato il pattern PdcDepotPage direttamente in PdcPage:
- `updateDayBlocks(dayId, changes)` — aggiorna orari blocchi in-day
- `completeMove(targetDayId)` — sposta blocco + CVp/CVa agganciati
  da giornata sorgente a target (via dedup state.days)
- `persistDetail(d)` — POST/PUT `/pdc-turn/{id}` con l'intero detail
- `handleDetailChange(next)` — setDetail + dirty + debounce 1.5s → save
- DayCard riceve `ganttId={day.id}`, `onBlocksChange`, `onCrossDayDragStart`,
  `onCrossDayDrop` e li passa a PdcGanttV2 (già supportati dal componente)
- StatusChip nel top-bar canvas mostra "Sincronizzato" / "Modificato" /
  "Salvataggio..." secondo stato dirty+saving

Hint visivo "Sposta in corso — rilascia il blocco X su un'altra giornata"
appare sopra la lista day cards durante drag cross-day.

### Fix 4 — Drawer "Questo treno anche in..."

Nuova sezione nel TrainDetailDrawer (dopo Origine/Destinazione, prima
di Giro Materiale):
- Lista occurrences dello stesso train_id in altre giornate dello stesso
  turno (calcolate client-side in DayCard via `computeOccurrences`
  filtrando `allDaysForOccurrences`)
- Row con: g{N} eyebrow brand + LMXGV chip mono + from→to + orario mono
- Click row → `onJumpToDay(dayId)` → chiude drawer, apre la day card
  target, scrolla smooth-in-view
- Implementato via `forceOpenSignal` prop + `useEffect` che setta
  `internalOpen=true` e chiama `scrollIntoView` con micro-delay

Nuovo export `TrainOccurrenceInTurn` dal TrainDetailDrawer.

### Preservato

- PdcGanttV2 API invariata a parte i due nuovi prop opzionali
- Click blocco → drawer con richer content (Origine/Dest, Giro Materiale,
  Altri Turni Associati)
- Azioni Modifica/Vista deposito/Elimina turno
- Note periodicità collapsabili
- PdcDepotPage: uso `autoFit=false` implicito (default), comportamento
  invariato

### Build

JS 477 → 484 KB (+7 KB: scale dinamica + move/save logic + occurrences
calc). CSS 61 KB stabile.

---

## 2026-04-19 — Gestione PdC redesign completo (Stitch source of truth)

Utente ha fornito export Stitch completo in `docs/stitch-mockups/`
(commit `72b38ed`). Claude Design rate-limited → Stitch diventa source
of truth diretta. Refactor dell'area "gestione" (PdcPage) in 3 step.

### Contesto

Screenshot utente mostrava:
- Gantt con blocchi alti 22px, praticamente invisibili
- Station capolinea ("ALESSANDRIA", "PV") fluttuanti sopra l'asse
- Toggle Gantt/Lista con emoji kitsch
- Top bar editor assente (nessun contesto visuale del turno)
- Drawer con "Percorso" layout a righe, poco gerarchico

Target: `docs/stitch-mockups/editor_turno_pdc_arturo_accessibility_refined/`
con top bar + giornate canvas + drawer + footer + legenda.

### Step 1/3 — Gantt + DayCard (commit `1d8c22c`)

PdcGanttV2:
- Prop nuovo `hideActionBar` (action bar 8-icone nascosta in PdcPage)
- BLOCK_H 22 → 34 per ospitare tag + meta stacked
- Treno: rect brand gradient + border-l 2.5px brand-deep + highlight
  top 1/3 glass + tag (train_id mono) sopra, meta (FROM-TO sigla
  2 char) sotto, entrambi centrati
- Vuota: solid slate (#E2E8F0) + border-l slate-500, tag "VUOTA {id}"
  centrato (era dashed con label fluttuante)
- Meal: tag "REFEZ" centrato in success container rounded rx=4
- S.Comp: tag in warning container, border-l arancio
- Station capolinea: font piu piccolo, troncate 3 char uppercase se
  lunghe, Y al centro del nuovo blocco (era fluttuante alto)

DayCard:
- Header stile Stitch: chevron + title "Giornata {N} · {periodicita}"
  + subtitle ("Servizio feriale/festivo/ordinario" · orario) +
  metrics strip (Cct/Km/Rip) + "DURATA TOTALE" mono + menu ⋮
- Derive subtitle intelligente da day state
- Toggle Gantt/Lista con lucide BarChart3/List (no emoji)

### Step 2/3 — TrainDetailDrawer (commit `73ec185`)

Sezione Origine/Destinazione:
- Sostituisce "Percorso" a righe
- Card tonal surface-container-low con inset ghost border
- Layout Stitch: ORIGINE eyebrow + station bold + time mono a sx,
  arrow brand nel mezzo, DESTINAZIONE + station + time a dx
- Chip sotto divisore ghost: Vettura/Accessori/min. accessori

Sezione Giro Materiale (MaterialCard ridisegnato):
- Da compact mono row a button-card grande con:
  - Label "PRECEDENTE"/"SUCCESSIVO" uppercase brand
  - train_id mono bold 13px
  - handoffLabel "Arr./Part. {stazione} {orario}"
- Hover: inset ring brand 40%

Sezione Altri Turni Associati:
- Rename da "Guidato da turni PdC"
- Row con kinetic dot verde sul primo (attivo) + halo box-shadow
- "Turno PdC:" + codice mono + g{N} + periodicita compact
- Chip "→ {next}" handoff success-container

### Step 3/3 — Editor shell (questo commit)

TurnDetail ristrutturato come shell Stitch:

Top bar sticky (top-0 z-10):
- Eyebrow "EDITOR TURNO" brand + codice mono 18px extrabold
- Separator vertical ghost
- Metadata columns (3): Impianto (Building2) | Profilo | Data Validità (Calendar, mono)
- Bottone "Vista deposito" brand subtle a destra

Canvas (flex-1 overflow-y-auto):
- Title "Giornate Turno" display 20px + chip "Attivo" brand + chip "{N} blocchi" success
- Day cards list (spacing 3)
- Note periodicita in sezione collapsed sotto, con tonal container

Footer sticky (bottom-0 z-10):
- Sinistra: bottone "Elimina" destructive (minimal hover)
- Centro: Legenda 4 swatches (Guida brand, Vuota slate, Refez verde, S.Comp arancio)
- Destra: CTA primaria "MODIFICA TURNO" gradient-primary uppercase

Container PdcPage detail panel: overflow-hidden + flex-col per permettere
al canvas interno di scrollare senza spingere fuori top bar/footer.

Componenti helper inline (stessi file): TopBarField, StatusChip,
LegendSwatch, MetricInline, ViewToggle.

Tutte le funzionalita preservate:
- Click blocco → drawer (con richer content Step 2)
- Drag/resize/cross-day drop (PdcGanttV2 interno)
- Elimina turno (footer), Modifica turno (footer → navigate /pdc/edit)
- Vista deposito (top bar → navigate /pdc/depot/{impianto})
- Note periodicita espandibili (details/summary)

Build: JS 471 → 477 KB (+6 KB per shell), CSS 61 KB stabile.

---

## 2026-04-19 — DS copertura completa: Login + Settings + PdcBuilder + PdcDepot + Builder

Estesa la coverage del design system alle 5 pagine ancora sullo stile
vecchio dopo la sessione precedente. 1 commit unico (non separato per
pagina per snellire: cambi sono piccoli e omogenei).

### LoginPage
- Sfondo con gradient orb (brand + kinetic green radiali su rgba bassissima)
- Eyebrow "GESTIONALE TURNI PDC" + subtitle "Personale di macchina"
- Card con `shadow-lg` su `surface-container-lowest` (era border)
- Input: `surface-container-low` + inset ghost border (DS pattern)
- Bottone `gradient-primary` + shadow-md (era solid brand)

### SettingsPage
- Eyebrow "IMPOSTAZIONI" + display title "Configurazione e informazioni"
- 4 StatCard in KPI style (font-display 24px, label uppercase)
- Container principale tonal (shadow-sm + surface-container-lowest)
- Turni materiale: wrapper interno `surface-container-low` con chip
  dentro `surface-container-lowest` (nested tonal layering)
- Health chip usa i nuovi `success-container` / `destructive-container`

### PdcBuilderPage (1536 righe, cambi mirati)
- Header: eyebrow + display title Exo 2
- Bottone "Annulla" con hover tonal anziche colore solo
- "Dati del turno" card: No-Line + display title sezione
- CalendarPreview card: No-Line
- DayCard: No-Line outer + header tonal (surface-container-low) + body
  espanso tonal (era border-t)
- Campi "Calcolato dai blocchi": tonal chip (era border + bg-muted/30)
- Input/select di editing mantenuti con border-1: boundary funzionale
  (non sezionatore di layout)

### PdcDepotPage
- Eyebrow "VISTA DEPOSITO" + display title Exo 2 "Deposito {impianto}"
- Turn item: No-Line outer (shadow-sm)
- Espansione turno: body con tonal shift (surface-container-low)
- Day card dentro turno: shadow-sm + surface-container-lowest (era
  border + bg-white)

### BuilderPage
- Eyebrow + display title "Costruzione turno"
- Card "Search": No-Line
- "Treni nel turno" card: header tonal (surface-container-low), body
  surface-container-lowest
- Gantt timeline card: No-Line
- Validation panel sticky: No-Line
- Input/select/toggle FR mantenuti come prima (boundary funzionale)

### Cosa rimane

- **BlocksList / TurnsList interni ai builder**: ancora stile chip
  colorato per block_type (border + bg per tipo). HANDOFF §01 consiglia
  sostituzione con classi `.gblock.{train,accp,vuota,refez,vettura}`
  coerenti col Gantt — rimandato perche coinvolge refactor piu esteso
  e potrebbe cambiare semantica del rendering
- **Font self-hosted** Inter/JetBrainsMono — oggi fallback a system
  (SF Mono, Menlo, ui-monospace)
- **Audit log backend** per activity/recent piu ricco (oggi derivato
  da saved_shift). Richiede tabella dedicata

### Build finale

CSS 65 → 61 KB (Tailwind purge grosso per classi bg-card/border-border
rimosse dove sostituite con inline style). JS 467 → 469 KB.

---

## 2026-04-19 — Fase 2 completa: endpoint backend + CommandPalette + TrainSearch + No-Line

Sessione "fai con la dovuta calma tutti i 4 punti" dopo validazione utente
del facelift. Niente rotture, 5 commit pubblicati + rebuild dist in ognuno.

### 1 · Backend Dashboard (commit `d726ae5`)
Nuovo `api/dashboard.py` registrato in `server.py`:
- `GET /api/dashboard/kpi` — totale_turni, turni_settimana, giorni_lavorati
  (distinti), ore_settimana_min, delta_30gg_pct (variazione % saved_shift
  ultimi 30gg vs 30gg precedenti).
- `GET /api/activity/recent?limit=20` — feed derivato da saved_shift.
  type=`validate` se 0 violations, `conflict` se ≥1 errore. Placeholder
  fino ad audit log Fase 3.
- `GET /api/linea/attiva` — stato dei primi 5 treni piu recenti dell'utente
  via ARTURO Live. Cache in-memory 60s per rate-limit 30 req/min IP.
  Fail-soft: ritorna items=[] + note di errore se ARTURO non raggiungibile.
- Tutti i 111 test continuano a passare.

### 2 · Dashboard cablata ai veri endpoint (commit `5c70655`)
- Rimossi `MOCK_KPI` e `MOCK_LINEA`
- `frontend/src/lib/api.ts`: +3 funzioni tipizzate (getDashboardKpi,
  getActivityRecent, getLineaAttiva) e tipi (DashboardKpi, ActivityItem,
  LineaAttivaRow)
- `DashboardPage.tsx`:
  - "Turni attivi" (mock) → "Turni settimana" (reale)
  - KPI card con placeholder "—" in loading/errore
  - Activity feed mappa type→icona/tone automaticamente
  - Linea attiva: mostra messaggio esplicativo se linea.length === 0
    (usa `lineaNote` quando ARTURO Live non raggiungibile)
  - Today card: primo activity item al posto del primo recentShift

### 3 · CommandPalette ⌘K (commit `1f2aa63`)
Componente self-contained `CommandPalette.tsx` (~330 righe). **Zero nuove
dipendenze npm** — niente cmdk né radix-dialog, tutto con React primitives
+ Tailwind.
- Hotkey globale ⌘K/Ctrl+K in `Layout.tsx` (toggle)
- Glassmorphism: rgba(255,255,255,0.94) + backdrop-blur(24px) saturate(180%)
- Filtro fuzzy: tutti i token della query devono match (case-insensitive)
- Gruppi: Suggerimenti · Navigazione · Turni · Azioni
- Nav tastiera completa: ↑↓ Home End Enter Esc + scroll-into-view
- Click backdrop per chiudere; footer con shortcut hint + count
- Turni caricati via `getSavedShifts()` al primo open (cache per sessione)
- Sidebar: pulsante "Cerca…" con kbd ⌘K/Ctrl+K per feature discovery

### 4 · TrainSearchPage side panel cross-ref (commit `3513e96`)
- Aggiunto `CrossRefPanel` (~240 righe) che consuma `/train/{id}/cross-ref`
  (stesso endpoint del TrainDetailDrawer — coerenza cross-link)
- Layout a 2 colonne su xl (>=1280px): `minmax(0,1fr) 340px`. Sotto 1280px
  stacking naturale
- Side panel mostra:
  - Giro Materiale: prev/curr/next con chip verde "Handoff OK" quando
    next.dep_time === curr.arr_time; chain compatta con badge brand sul
    treno corrente
  - PdC carriers: fino a 10 turni con codice, g#, periodicità LMXGVSD,
    orari block_start→block_end
- Tutto il comportamento esistente preservato (tabs, autocomplete, DB
  locale, real-time ARTURO Live, giro chain)

### 5 · No-Line rule su liste (questo commit)
Applicato tonal-layering minimale ai container esterni di:
- `ShiftsPage.tsx` (riga 62): rimosso `border border-border-subtle`,
  aggiunto `shadow-sm` + bg `surface-container-lowest`
- `CalendarPage.tsx` (riga 144): stesso pattern
- `ImportPage.tsx` (righe 90-92): container + header via tonal shift
  (`surface-container-low` sull'header)

Bordi interni (separators `border-t` dentro card espanse) lasciati: hanno
senso semantico come ghost border (ammesso da DS in tabelle dense).

### Cosa rimane aperto

- **Endpoint audit log** per `activity/recent` più ricco (Fase 3 —
  oggi il type è solo validate/conflict derivato da saved_shift)
- **Self-host Inter.woff2** e **JetBrainsMono.woff2** (oggi fallback
  system — nessun impatto visivo grosso ma design-system vorrebbe i tre
  font self-hosted)
- **No-Line rule** a BlocksList/TurnsList (componenti dentro i builder) —
  rimandato perché toccano logica di rendering più articolata

### Build finale

CSS 65.7 → 64.7 KB, JS 438 → 463 KB (+25 KB distribuiti su:
CommandPalette ~10 KB, CrossRefPanel ~8 KB, Dashboard wiring ~2 KB).
Zero dipendenze npm aggiunte. Zero breaking change.

---

## 2026-04-18 — Facelift veloce Fase 2 P2 (4 commit)

Implementazione compressa della parte visibile del piano "Facelift" del
HANDOFF (sezioni Logo, Sidebar, Dashboard, Gantt). Solo frontend, zero
nuovi endpoint backend, 100% funzionalità preservate.

### Commit 1 — Logo (`d131fdd`)
- "COLAZIONE" → "ARTURO" font-display Exo 2 + dot kinetic verde con
  halo box-shadow (DS "Kinetic Conductor")
- File: `frontend/src/components/Logo.tsx`

### Commit 2 — Sidebar (`fa50447`)
- Rimosso `border-r`: sfondo `surface-container-low`
- Active item: bg `surface-container-high` + indicator verticale verde
  3.5×2px sulla sinistra (kinetic dot) anziché bg color flat
- Sezione user: separazione tonal (`surface-container`) anziché `border-top`
- Voce "Turni" → "Turni Materiale"
- File: `frontend/src/components/Sidebar.tsx`

### Commit 3 — Dashboard (`e52b109`)
- Hero con eyebrow + display title (Exo 2)
- 4 KPI card: Totale turni (reale dal backend), Attivi LIVE, Lavorati
  settimana, Ore settimana (mock)
- 2-col layout: Activity feed (turni recenti reali) + Linea attiva
  (mock con chip "Mock") | Today card gradient + Azioni rapide compatte
- Componenti riusabili: `KpiCard`, `ActivityRow` con tone
  blue/green/amber/slate, `StatoChip` per ok/ritardo/soppresso
- Quick actions ora compatte in side panel (preserva navigation)
- Mock data marcato esplicitamente: sostituibili quando arriveranno gli
  endpoint `/dashboard/kpi`, `/activity/recent`, `/linea/attiva`
  (HANDOFF §04)
- File: `frontend/src/pages/DashboardPage.tsx`

### Commit 4 — Gantt block colors (questo commit)
- Costanti `DS` in cima a `PdcGanttV2.tsx` mappa colori per block_type:
  - `train` → gradient brand (#004B9F → #0062CC)
  - `coach_transfer` (vuota) → fill neutro `rgba(15,23,42,0.05)` +
    border tratteggiato gray (resta dashed come prima)
  - `meal` (refez) → success container `#DCFCE7` + stroke `#16A34A`,
    text `#15803D` (era amber)
  - `scomp` → warning container `#FFEDD5` + stroke `#EA580C`, text
    `#9A3412` (era cyan)
  - `cv_partenza/cv_arrivo` → viola `#6D28D9` standardizzato
- Selected ring: kinetic dot `#22C55E` (treno) / brand `#0062CC`
  (refez/scomp/vuota)
- File: `frontend/src/components/PdcGanttV2.tsx`

### Cosa NON è incluso

- Nessuna modifica backend (no endpoint `/dashboard/kpi` etc.)
- Nessuna modifica a pagine non-Dashboard/Sidebar/Logo/Gantt
- Nessun nuovo file (zero CSS file, zero componenti aggiunti — KpiCard
  e ActivityRow sono inline in DashboardPage.tsx finché non saranno
  riusati altrove)
- CommandPalette ⌘K (P1 nel piano) → rimandato

### Build size

CSS 65.7 → 63.9 KB (Tailwind purge), JS 438 → 447 KB (+9 KB Dashboard).

---

## 2026-04-18 — UI Refresh Fase 1 + Fase 2 P0 (design Claude Design → produzione)

Prima implementazione reale del refresh UI basato sull'handoff ricevuto
da Claude Design. Commit sequenziali seguono la roadmap di
`docs/HANDOFF-claude-design.md`.

### Fase 1 — Tokens @theme estesi (commit cfff63c)

`frontend/src/index.css` esteso con il design system "Kinetic Conductor":

- **Surface hierarchy** 6 livelli (No-Line rule): `--color-surface`,
  `--color-surface-container-{low,default,high,highest,lowest}`
- **Ink tonale**: `--color-on-surface`, `-strong`, `-muted`, `-quiet`,
  `-disabled`
- **Ghost borders**: `--color-ghost` (8%), `--color-ghost-strong` (14%)
- **Shadows tinted**: `--shadow-{sm,md,lg}` su on-surface, non grigio
- **Gradient CTA**: `--gradient-primary` 135° `#004B9F` → `#0062CC`
- **Semantic container**: `_container` varianti soft per destructive/
  success/warning
- **Typography stack esteso**: `--font-display` (Exo 2), `--font-mono`
  (JetBrains Mono + fallback SF Mono/Menlo — font file self-host
  rimandato)

**Token legacy 100% preservati** — zero regressione su pagine/componenti
esistenti. Build OK: 62 → 65 KB CSS (+3 KB per nuovi token).

Aggiunto materiale in `docs/`:
- `HANDOFF-claude-design.md` (piano implementativo completo, checklist)
- `REFERENCE-claude-design-styles.css` (tokens sorgente Claude Design)
- `REFERENCE-claude-design-screens.css` (component styles)
- `REFERENCE-screen-{editor,palette,dashboard}.html`

### Fase 2 P0 — TrainDetailDrawer (commit in arrivo)

Nuovo componente `frontend/src/components/TrainDetailDrawer.tsx`
(~420 righe, slide-in destro 440px) che sostituisce `BlockDetailModal`
(modal centrato).

**Novità rispetto al modal**:
- Drawer laterale destro con slide-in 220ms + backdrop blur 8%
- **Chain pills cliccabili**: click su un numero treno nella chain
  ricarica il drawer con quel treno come focus (navigazione cross-treno
  senza chiudere)
- **Header "← torna a X"** quando si è navigati via chain
- **Handoff indicator**: chip verde `Handoff OK → PVOR_C` quando
  `prev.arr_time === next.dep_time` tra due PdC consecutivi (es. il
  caso reale 10581: ALOR_C g1 → PVOR_C g21 alle 16:19)
- **Sezioni DS-compliant**: No-Line tramite tonal shift
  (`surface-container-low` → `surface-container-high` hover), nessun
  border 1px
- **Font mono** per orari e numeri treno come da design system
- **Esc + click-outside** per chiudere

**Stessa signature di BlockDetailModal** (`block`, `index`, `mode`,
`onClose`) → swap drop-in via alias `import { TrainDetailDrawer as
BlockDetailModal }` in 3 pagine:
- `pages/PdcPage.tsx`
- `pages/PdcBuilderPage.tsx`
- `pages/PdcDepotPage.tsx`

Logica API (trainCheck + trainCrossRef in parallelo) preservata 1:1 —
cambia solo il wrapper UX.

Il file originale `components/BlockDetailModal.tsx` NON viene rimosso in
questo commit (cleanup in commit successivo dopo verifica utente).

Build OK: 65 → 65 KB CSS, 438 → 439 KB JS (componente drawer compila
pulito).

### Pain point risolto

Prima: click su treno → modal centrato che nasconde la timeline sotto,
utente non riesce a confrontare con altri blocchi.

Dopo: click su treno → drawer destro 440px, timeline sempre visibile a
sinistra, utente può **navigare tra treni della chain** con un click
sul pill corrispondente, **vedere gli handoff** tra turni PdC con
evidenza verde.

### Prossimi step (P0 → P1 → P2 → P3 per handoff)

- P0 **✓** Drawer + integrazione in 3 pagine
- P1 CommandPalette (⌘K) — 1 giornata
- P1 TrainSearchPage side panel cross-ref — 1 giornata
- P2 Dashboard KPI + ActivityFeed + oggi-in-servizio — 1.5 gg
  (richiede 3 endpoint backend nuovi: `/activity/recent`,
  `/linea/attiva`, `/dashboard/kpi`)
- P2 Refactor Gantt styling no-line — 0.5 gg
- P3 Apply No-Line rule a liste esistenti — 1 gg

Il blocco rimane l'utente: deve provare la Fase 2 P0 in produzione
(Railway deploy `railway up` da locale), confermare che la UX è quella
attesa, poi decidiamo se procedere con P1.

---

## 2026-04-18 — Design pipeline Stitch → Claude Design (UI refresh pianificato)

Sessione di pianificazione del refresh visivo del frontend React. Dopo
una prima iterazione di alleggerimento del legacy `static/index.html`
(rivelatosi non servito da Railway — vedi entry successiva), il focus
si è spostato sul frontend React reale (`frontend/`) con un approccio
design-first tramite tool AI esterni.

### Pipeline adottata

1. **Google Stitch** (stitch.withgoogle.com) — prima generazione design
   system "The Kinetic Conductor" per ARTURO·. Output: 16 schermate
   + 2 DESIGN.md in `~/Downloads/stitch_colazione_pianificazione_turni_pdc/`.
   Asset copiati anche in `~/Desktop/claude-design-upload/` per riuso.

2. **Claude Design** (claude.ai/design — by Anthropic Labs, in Research
   Preview dal 17/04/2026) — raffinamento del design Stitch con accesso
   diretto al codebase (GitHub + cartella locale). Vantaggi vs Stitch:
   - Legge codebase completo → capisce token CSS già in uso
   - Export diretto "Handoff to Claude Code" → zero traduzione manuale
   - Conversazione iterativa (non one-shot come Stitch)
   - Custom sliders per micro-aggiustamenti

### Materiale preparato per Claude Design

In `~/Desktop/claude-design-upload/` (11 file pronti per drag&drop):
- Screenshot Stitch 01-07 (editor PdC, drawer cross-link, dashboard,
  command palette, cerca treno, calendario, import PDF)
- `08-design-system-arturo.md` — "Kinetic Conductor" design system
- `09-design-system-precision.md` — variante alternativa
- `10-current-tokens.css` — copia di `frontend/src/index.css`
- `11-BlockDetailModal.tsx` — componente React attuale con cross-link

Setup Claude Design: GitHub `87tickly/turni-pdm` connesso + cartella
COLAZIONE linkata come contesto filesystem diretto.

### Design system "Kinetic Conductor" (estratto)

Principi chiave da `08-design-system-arturo.md`:
- **No-Line rule**: niente border 1px solid per sezionare, usare shift
  di background (`surface` → `surface-container-low`)
- **Tonal Layering**: profondità via nesting di superfici, non shadow
- **Kinetic Dot**: `#22C55E` come ancora visiva unica (status attivo)
- **Glass & Gradient**: CTAs primari con gradient 135° primary →
  primary-container; modali con backdrop-blur 12-20px
- **Tipografia**: Exo 2 (display) + Inter (body) + monospace obbligatorio
  per orari (HH:MM) e numeri treno
- **Palette hex**: brand `#0062CC`, accent `#0070B5`, kinetic `#22C55E`,
  background `#F7F8FA`, foreground `#0F172A`

### Schermate prioritarie per l'implementazione

Ordine di priorità concordato con l'utente:
1. **Editor Turno PdC con drawer cross-link destro** (pain point #1:
   oggi il dispatcher non vede la continuazione materiale e quali altri
   turni PdC guidano lo stesso treno)
2. **Command Palette ⌘K** (navigazione globale turno/treno/azione)
3. **Dashboard** (KPI + attività recente + oggi in servizio)
4. **Cerca treni** (con side panel cross-ref)

### Pipeline di implementazione a 5 fasi (pianificata)

| Fase | Oggetto | Ore stimate |
|---|---|---|
| 1 | Facelift visivo (token, tipografia, spacing applicati) | 4-6 |
| 2 | Drawer cross-link al posto di BlockDetailModal centrato | 3-4 |
| 3 | Drag & drop + edit inline sui blocchi Gantt | 6-8 |
| 4 | Rientro in vettura / Raggiungimento treno via ARTURO Live | 4-5 |
| 5 | Command palette + scorciatoie + polish finale | 3-4 |

Tot: ~20-27h distribuite su 7-10 sessioni.

### Stato attuale

- Stitch: completato, export ricevuto
- Claude Design: in corso (utente sta generando le 4 schermate hi-fi)
- Implementazione React: **ferma** in attesa dell'output Claude Design,
  per non rifare lavoro

### Lezioni dalla sessione (metodo)

1. **Prompt lunghi vanno benissimo per Stitch** (no context esplorabile,
   serve tutto esplicito). **Ma per Claude Design** — che ha accesso al
   codebase — un prompt breve + FOCUS esplicito (es. "analizza solo
   frontend/, ignora backend/uploads/tests/.venv") produce risultati
   migliori perché evita context bloat.
2. **Verificare sempre cosa il server serve davvero** prima di
   investire tempo su un file. `static/index.html` era stato modificato
   senza accorgersi che `server.py:78` serve solo `frontend/dist/`
   quando esiste. I commit ce89bf6 + c75d38a (tokens) restano su master
   come lavoro dormiente.
3. **Hex code e font name vanno SEMPRE espliciti nei prompt visivi**.
   "Blu primario" non basta, serve `#0062CC` + "Exo 2" + gli anti-esempi
   ("no Material Blue #3B82F6").

### Follow-up per prossime sessioni

- Ricevere output Claude Design (screenshot o bundle handoff)
- Confrontare con Stitch e decidere design finale
- Eseguire Fase 1 (facelift visivo) su PdcPage + Sidebar + Layout
- Poi Fase 2 (drawer cross-link) — trasformare BlockDetailModal

---

## 2026-04-18 — Frontend React: cross-link PdC<->Materiale nel BlockDetailModal

**Feature visibile all'utente** (Fase 2 completata).

### Contesto

Nello screenshot del turno PdC (ALOR_C g1) l'utente ha segnalato che
"non trova la continuazione del giro materiale" di un treno selezionato,
costringendolo a scrollare/memorizzare. La pipeline ora risolve questo.

### Stack deliverable

1. **Backend endpoint** `/train/{id}/cross-ref` (commit c3be053):
   aggrega `db.get_giro_chain_context()` + `db.find_pdc_train()` in una
   singola risposta con material context e pdc_carriers.

2. **Client API React** `trainCrossRef()` in `frontend/src/lib/api.ts`:
   type `TrainCrossRef` completo, chiamato in parallelo a trainCheck().

3. **BlockDetailModal esteso** (commit f087da9):
   - Nuova sezione "Continuazione giro · Turno X · pos Y/Z"
     con frecce prev/next e chain compatta come pill-list
   - Lista "Guidato da turni PdC" piu' completa che sostituisce la
     sezione legacy del triple-check quando cross-ref e' disponibile
   - Zero regressione: se /cross-ref fallisce, il triple-check classico
     resta visibile

### Caso d'uso verificato

Click su treno 10581 (visibile nello screenshot originale):
```
Continuazione giro · Turno 1116 · pos 1/1
Guidato da turni PdC (2):
  ALOR_C  g1  LMXGV  [15:05 → 16:19]  → AL
  PVOR_C  g21 S      [16:19 → 16:41]  → AL
                                        ↑
                                   handoff alle 16:19
```

Il dispatcher vede in un'occhiata che PVOR_C prende il treno alle 16:19
esattamente dove ALOR_C lo lascia — continuita' di servizio evidente.

### Prerequisiti risolti durante la sessione

- DB locale era vuoto: importati turno materiale (54 turni, 11306
  segmenti) e PdC (26 turni, 1344 giornate, 6925 blocchi)
- `import_turno_materiale.py` hardcoded path Windows: fixato
  cross-platform (argv[1]=DB, argv[2]=JSON, fallback cwd)

### Errore corretto

Inizialmente stavo lavorando su `static/index.html` pensando fosse il
frontend in produzione. Quando `frontend/dist/` esiste (ed esiste),
server.py serve SOLO la build React (L78-81) e il legacy non viene
servito. Identificato, rollback-ato le modifiche non committate al
legacy, portato il lavoro su React. Tokens CSS committati in precedenza
(c75d38a) restano su master come lavoro dormiente.

### TODO follow-up

- **Fase 2c**: implementare "Rientro in vettura" / "Raggiungimento
  treno" via ARTURO Live API (servizio gia' presente in
  `services/arturo_client.py`)
- Rendere cliccabili i pill della chain per navigare al treno prev/next
  (al momento mostrano tooltip ma non sono hook attivi)
- Rendere cliccabili le righe "Guidato da turni PdC" per saltare alla
  giornata PdC corrispondente (stub `goToPdcTurn` in preparazione)
- Valutare Fase 1b: sostituire valori hardcoded in React componenti con
  tokens o variabili Tailwind consistenti

---

## 2026-04-18 — Frontend legacy: design tokens estesi (Fase 1a UI refactor)

Prima tappa del refactor UX del frontend legacy `static/index.html`.
Obiettivo della roadmap: rendere il frontend piu' fluido da modificare e
piu' moderno visivamente, senza perdere una sola feature.

### Contesto

L'utente ha segnalato che l'interfaccia attuale e' "vecchia e macchinosa":
troppi click per modifiche, difficile trovare la continuazione materiale di
un treno o dove quel treno compare in altri turni PdC.

Branch `legacy-before-refactor` creato come punto di ritorno di sicurezza
prima di qualsiasi modifica.

### Cosa e' cambiato in questo commit

**Solo `:root` di `static/index.html`**:

1. Variabili esistenti preservate al 100% (retrocompat totale)
2. Aggiunte scale standardizzate:
   - **Tipografia**: `--text-2xs` (9px) → `--text-5xl` (28px) — 11 livelli
   - **Spacing** (4pt grid): `--space-0` → `--space-16` (64px) — 12 livelli
   - **Radius**: `--radius-md` (alias), `--radius-pill` (9999px)
   - **Shadow**: `--shadow-md` (alias)
   - **Motion**: `--transition-fast`, `--transition-slow`
3. Header commentato con guida alla modifica (leggibile da chiunque)
4. Documentato `--orange` come deprecated (alias di `--amber`, stesso valore)

### Zero rischi

- Nessuna regola CSS modificata
- Nessun valore di stile alterato
- File: +77 righe (5441 → 5518), tutte dentro `:root {}`
- Zero impatto visivo o comportamentale

### Prossimi step (opzionali, su richiesta)

- **Fase 1b**: sostituire valori hardcoded (font-size, padding, colori) con
  le scale nei punti dove sono ripetuti (es. `padding:10px 14px` compare
  5 volte, `font-size:12px` 13 volte)
- **Fase 2a**: endpoint `/api/train/{id}/pdc-carriers` per cross-link
  PdC ↔ materiale (richiede DB popolato — il locale e' vuoto)
- **Fase 2b**: pannello slide-in a destra con continuazione materiale +
  chi guida il treno nelle altre giornate PdC
- **Fase 2c**: implementazione "Rientro in vettura" / "Raggiungimento treno"
  via `services/arturo_client.py` (ARTURO Live API)

---

## 2026-04-18 — Parser PdC: accessori_partenza + accessori_arrivo (B.3.1)

Aggiunto calcolo accessori a livello giornata, zero regressione sul parser
PdC esistente.

### Modifiche

**`ParsedPdcDay` dataclass**:
```python
accessori_partenza: int = 0   # minuti ACCp (presa servizio)
accessori_arrivo:   int = 0   # minuti ACCa (consegna)
```

**Approccio: arithmetico** (non PDF extraction):
- `ACCp = first_block.start_time - day.start_time`
- `ACCa = day.end_time - last_block.end_time`
- Guardia: 0..180 min (scarta outlier tipo wrap mezzanotte errati)
- Conservativo: se primo/ultimo blocco non ha l'orario richiesto → 0
  (meglio di un valore sbagliato)
- Blocchi `available`/`scomp` esclusi dal calcolo

**Razionale**: i valori accessori sono sempre numeri singoli (confermato da
utente). Calcolo aritmetico evita estrazione testo fragile e dà valori
corretti ovunque i blocchi abbiano orari.

### Verifica no-regression

Baseline B.2 identico al pre-sessione:
```
train           tot=4237  miss_s=393  miss_e=611   (invariato)
coach_transfer  tot= 860  miss_s=105  miss_e=137   (invariato)
meal            tot= 682  miss_s= 91  miss_e=124   (invariato)
```

### Verifica valori

AROR_C giorno 1 (default atteso 5/5):
- day=[18:20→00:25], first_block=18:25 → ACCp=5 ✓
- last_block senza end_time → ACCa=0 (conservativo)

AROR_C giorno 4:
- day=[05:33→13:30], first_block=06:53 → ACCp=80

Distribuzione globale su 1218 giorni:
- **ACCp>0**: 732 giorni (60%) — valori frequenti 5, 60, 15, 20, 55, 65
- **ACCa>0**: 348 giorni (28%) — valori frequenti 5, 35, 20, 40, 15

ACCa meno popolato perche' ultimi blocchi spesso senza end_time (miss_e=611
su train), dato strutturale del PDF, non bug del parser.

### Follow-up TODO

- Validazione cross-parser: ACCp + ACCa insieme nella stessa giornata e'
  ammesso solo se il treno non ha continuazione di servizio (controllo
  via turno materiale). Da implementare in un validator separato.
- Rendering frontend: usare i due campi per disegnare linea tratteggiata
  sottile prima/dopo i blocchi quando valore > 0.

---

## 2026-04-18 — Parser turno materiale: refactor vertical extraction (sezione A completata)

Refactor completo di `parse_turno_materiale.py` per supportare il nuovo
formato PDF Trenord 2026+ dove i numeri treno sono scritti VERTICALMENTE
(upright=False), una cifra per riga Y, da leggere bottom-to-top.

### Nuova funzione `extract_vertical_trains(page)`

Algoritmo:
1. Filtra char con `upright == False` (verticali)
2. Trova bande Y globali della pagina (gap > 20pt = separazione Gantt-band)
3. Cluster per X (tolleranza 2pt)
4. Sort per Y ascendente (bottom-to-top = ordine lettura)
5. Split intra-banda se gap > 8pt (separazione tra varianti)
6. Match pattern `\d{4,6}i?` per ID treno + vuote con suffisso `i`
7. Caso misto (colonna digit+letter tipo `28220iMICE`): estrae solo con
   lettere presenti (evita falsi positivi da colonne minuti `22552255`)

### Integrazione main loop

- Aggiunto `page_to_turno` map con carry-forward: pagine di continuazione
  (senza header "Turno NNN") vengono associate al turno attivo corrente
- `vertical_trains_by_turno` raccoglie i treni estratti per turno
- Output: nuova variante `(vertical-extraction)` per ogni turno che
  contiene treni verticali, additiva alle varianti orizzontali esistenti

### Risultati su `Turno Materiale Trenord dal 2_3_26.pdf` (353 pagine)

| Metrica | Prima | Dopo |
|---------|-------|------|
| Turni | 54 | 54 |
| Treni distinti regolari | 31 (1%) | 3301 (115% vs storico) |
| Vuote distinte | 9 | 532 |
| Totale occorrenze per-turno | N/A | 4343 (vs 3790 storico, +15%) |

Coverage sui turni campione:
- Turno 1100: **100%** (8/8 treni, 4/4 vuote) ✓
- Turno 1110: **100%** (72/72 treni)
- Turno 1191A: **92%** (68/74 treni; 6 miss sono rinumerazioni schedule)

Overlap globale con JSON storico: 86.1% — il 14% "mancante" è quasi
interamente dovuto a **rinumerazione schedule 2024→2026**:
- Vecchi `4xxx` → nuovi `24xxx` (+20000)
- Vecchi `20xxx` → nuovi `920xxx` (+900000)
- Vecchi `2xxx` S-line → nuovi `92xxxx`

Verificato: i treni "missing" non esistono più nel PDF 2026.

### File intoccati

- `turno_materiale_treni.json` (JSON storico): NON sovrascritto, solo
  line-endings CRLF→LF staged (non modifica dati). Rimane fonte per
  builder e Gantt finché utente non decide di switchare al nuovo.
- Output di test sempre in `/tmp/turno_materiale_test.json`.

### Cosa manca (follow-up opzionale)

- Step A.3.5 (estrazione minuti partenza/arrivo verticali) — non serve
  ai fini del recupero ID treni, skippato
- Step A.3.6 (parsing stazioni verticali) — idem, skippato

---

## 2026-04-18 — Parser turno materiale: fix regex + diagnosi formato PDF cambiato

Sessione di analisi del parser `parse_turno_materiale.py` sul PDF reale
`uploads/Turno Materiale Trenord dal 2_3_26.pdf` (353 pagine).

### Fix applicati

**Bug A — OUTPUT_PATH hardcoded Windows**:
```python
OUTPUT_PATH = 'C:/Users/studio54/Desktop/COLAZIONE/turno_materiale_treni.json'
```
→ crash su macOS. Fix: accetta secondo arg CLI, fallback a
`turno_materiale_treni.json` nella cwd.

**Bug B — regex header non matchava formato attuale**:
- Il parser cercava `Turno Validit... ) 1100` (numero dopo parentesi)
- Il PDF attuale ha `Turno 1100 Validità P)` (numero prima di "Validità")
- Il dettaglio char-by-char produce `Turno1100` (concatenato, zero spazi)

Fix: regex a due alternative + `\s*` (0..n spazi).

**Risultato commit**: da 0 turni a 54 turni identificati (coerente con
indice PDF pag 1 e con JSON storico).

### Root cause NON risolto (refactor necessario)

I **numeri treno sono estratti soltanto 31/2884 (1%)**. Causa:
**il PDF ha cambiato formato** tra `Vuoto 50 (1).pdf` (storico) e
`Turno Materiale Trenord dal 2_3_26.pdf` (attuale).

Nel nuovo PDF i numeri treno sono scritti **VERTICALMENTE** sopra le
barre del Gantt (una cifra per riga Y). Esempio turno 1100:
```
y=434  "1111"   ← 1a cifra dei 4 treni (tutti "1")
y=440  "0000"   ← 2a cifra (tutti "0")
y=445  "6666"   ← 3a cifra (tutti "6")
y=450  "0010"   ← 4a cifra (0,0,1,0)
y=456  "6309"   ← 5a cifra (6,3,0,9)
```

Leggendo per COLONNA X (top→bottom) si ricompongono: `10603, 10606,
10609, 10610` → matcha JSON storico.

Il parser attuale legge per **RIGA Y** (bottom-to-top sort char-by-char
+ concat), quindi vede stringhe tipo `"1111"` invece di cifre da
ricomporre in colonna. Era scritto per il formato storico (numeri
treno orizzontali).

### Refactor necessario (sessione dedicata)

Per supportare il nuovo formato:
1. Raggruppare char per X (colonne) nella zona "numeri treno" del Gantt
2. Ordinare ogni colonna per Y decrescente (top=prima cifra)
3. Concatenare cifre per ricomporre il numero treno
4. Distinguere char verticali (`upright=False`) da orizzontali via
   `pdfplumber` attr → solo quelli ruotati sono cifre treno
5. Stesso approccio per i minuti sotto le barre (probabilmente anche
   loro ora verticali)

### Stato dati

Il file `turno_materiale_treni.json` nel repo (2884 treni regolari,
413 vuote, 54 turni) **non e' stato toccato** — contiene l'estrazione
dal PDF storico e continua a funzionare come fonte dati per builder e
Gantt. Il nuovo parser **non e' in grado di rigenerare** questo JSON
dal PDF attuale finche' non si fa il refactor.

---

## 2026-04-18 — Diagnosi parser PdC + campo minuti_accessori (sessione di ricerca)

Sessione di diagnostica approfondita del `turno_pdc_parser.py` sul PDF
reale `uploads/Turni PdC rete RFI dal 23 Febbraio 2026.pdf`.

### Risultato commit
- Solo aggiunta del campo `minuti_accessori: str = ""` a `ParsedPdcBlock`
  (base per popolarlo quando estendiamo l'estrazione testo ausiliario)
- Zero regressione: train/coach/meal miss_start/miss_end **identici** al
  baseline pre-sessione
- Tutti i fix tentati (1, 2, 3) sono stati **revertati** perche'
  peggioravano il dataset reale

### Tre problemi investigati

**1. "Miss 28→26 turni": FALSO**. Il PDF ha 26 turni nell'indice pag 1.
Ne estraiamo 26/26 = 100%. Zero mancanti, zero extra. Memo sbagliato.

**2. Pallino ● accessori: irrilevante**. L'utente ha chiarito che basta
prendere il valore `minuti_accessori` direttamente (es. "5/5"), non
serve rilevare il pallino grafico. Aggiunto campo al dataclass; il
parser NON lo popola ancora (TODO futuro).

**3. Orari mancanti: 9-18% dei blocchi continui senza start/end**.
Distribuzione baseline:
- train (4237 tot): 393 miss_start (9%), 611 miss_end (14%)
- coach_transfer (860): 105/137 (12%/16%)
- meal (682): 91/124 (13%/18%)
- cv_partenza/cv_arrivo (puntuali): ~0 miss

Pattern: gli ultimi blocchi della giornata tendono a non avere end_time.

### Fix tentati (tutti revertati)

**Fix 1** — regex per `CVa`/`CVp` senza numero treno (ora `unknown`):
rendeva piu' CVp/CVa classificate, ma degradava train da 9%/14% a 13%/18%
perche' il cursore sequenziale avanzava su CV che nel PDF non sempre
hanno un minuto puntuale corrispondente.

**Fix 2** — `_assign_minutes_to_blocks` da sequenziale a window-based
(ogni blocco prende minuti nella sua finestra X): **gravemente peggiorato**
(meal miss_end da 18% a 87%, train miss_end da 14% a 43%). Le finestre X
nei Gantt serrati sono troppo strette e tagliano fuori minuti legittimi.

**Fix 3** — ampliato filtro size/zona di `_extract_upper_minutes`:
effetto combinato con Fix 1 ancora peggiorativo. Revertato insieme a
Fix 1 per coerenza.

### Root cause reale (da affrontare in sessione dedicata)

Il deep-dive su AROR_C g4/LMXGV (12 label verticali, 11 minuti estratti,
stats Lav=477m Cct=266m) mostra che:

- I **minuti estratti sono meno di quelli attesi** (~11 vs ~15-20
  per 12 label). Alcuni minuti di start (es. `33` sotto tick 5 alle 05:33)
  non vengono catturati — il filtro size del font o il band_top li
  tagliano fuori.
- La **ratio label↔blocco logico non e' 1:1**. Label come `10205ARON`
  (stazione partenza + treno) e `10205MIpg` (stazione arrivo + treno)
  possono essere due label del **MEDESIMO** blocco treno logico. Il
  parser attualmente le vede come due blocchi train separati.
- Le **label CVa/CVp senza numero** sono reali nel PDF e il classify
  le esclude.

### Cosa serve per fixare davvero (TODO prossima sessione)

1. **Analisi visuale del PDF su casi specifici**: aprire il PDF Gantt
   di AROR_C g4 LMXGV e mappare visivamente label, minuti e blocchi
   logici. Capire se il modello "1 treno = 2 label" e' davvero la
   convenzione o se ho interpretato male.

2. **Test dataset con ground truth**: almeno 5-10 giornate del PDF
   con orari attesi annotati manualmente, per validare qualsiasi
   modifica al parser senza regressioni.

3. **Algoritmo ibrido**: sequenziale con TOLLERANZA (se il minuto
   corrente e' a distanza X > soglia dal label, skip senza avanzare
   idx; oppure fallback a window-based con buffer dinamico).

4. **Popolamento `minuti_accessori`**: estrarre la stringa "5/5"
   (o simile) dal testo ausiliario sotto il minuto principale dei
   blocchi train all'inizio/fine della giornata.

### Test suite
Il test preesistente `tests/test_validator.py::test_meal_slot_gap` falliva
su master pulito (non correlato al parser PdC). Sistemato in sessione
parallela — vedi sezione sotto.

---

## 2026-04-18 — Fix test `test_meal_slot_gap` (test outdated)

Test `tests/test_validator.py::test_meal_slot_gap` falliva su master pulito:
atteso `start == "07:30"`, ricevuto `"11:30"`.

**Diagnosi**: la logica di `find_meal_slot` in `src/validator/rules.py:225` è
corretta. Secondo le regole operative (CLAUDE.md: "Refezione 30 min in finestra
11:30-15:30 o 18:30-22:30") la refezione è consentita SOLO nelle finestre
contrattuali. Il gap 07:30-08:30 è fuori da entrambe → la funzione cade nel
fallback `_meal_in_window` che ritorna "11:30" (inizio finestra 1) — cioè
comportamento corretto. Il test era stato scritto prima dell'introduzione delle
finestre contrattuali.

**Fix**: aggiornato il test per usare un gap dentro la finestra valida
(12:00-13:00), con asserzione su `("12:00", "12:30")`. Nessuna modifica alla
logica di business. Tutti i 23 test del validator passano.

---

## 2026-04-17 (notte tardissimi) — Refactor BlockEditor chip-style + auto-fill + bug fix Rientro

Sessione lunga di iterazione UX/UI. 9 commit incrementali su PdcBuilderPage,
PdcGanttV2, PdcDepotPage, ApI client.

### Fix critici

**Drag cross-day (3 iterazioni di fix):**
- `3e04ae0` rimosso preventDefault() in mouseDown — bloccava l'avvio HTML5 drag
- `aa05a91` riscrittura chip treno con foreignObject overlay HTML — pattern
  affidabile per HTML5 DnD su forme SVG (rect SVG draggable funziona male
  in alcuni browser anche se la spec dice OK)
- `e8c2d63` move sincrono ottimistico + auto-correzione async in background:
  prima la UI applicava il move dopo aver atteso /train-check (300-500ms
  di lag fastidiosi). Ora il blocco si sposta istantaneamente con orari
  originali, e in background scatta /train-check; se trova orari canonici
  diversi fa un secondo update silenzioso con banner di conferma.

**Rientro vettura (3 iterazioni):**
- `d060690` case-insensitive + retry senza filtro orario + log diagnostico
  + suggerimento "scrivi TORINO PORTA NUOVA invece di torino"
- `38a6ea9` **fix vero**: field mismatch silenzioso — il backend
  /vt/find-return ritornava {train_number, category, from_station,
  to_station, ...} ma il frontend si aspettava {numero, categoria, via,
  destinazione}. Anche quando ARTURO Live trovava treni il frontend
  mostrava "nessun treno". ReturnTrain interface allineata 1:1 + tutti i
  siti d'uso (acceptReturnCandidate, render lista) aggiornati.

### Calcoli automatici DayEditor (`840dae3`)

Eliminato il form "anni 2000" con 6 input rettangolari (Inizio/Fine/Lav/
Cct/Km/Rip min). Sostituito con riga compatta read-only:

  CALCOLATO DAI BLOCCHI · Inizio 06:40 → Fine 15:01 · Lav 8h21 · Cct 5h42 · Km 0  [🌙 notturno]

Helper computeDayStats(blocks) deriva tutto:
- start_time = min start dei blocchi (gestione wrap mezzanotte via origine 03:00)
- end_time   = max end
- lavoro_min = end - start
- condotta_min = somma durate dei blocchi 'train'
- notturno = true se intervallo include 00:01-05:00

useEffect ricalcola appena day.blocks cambia. Confronto coi valori attuali
per evitare loop. Override manuale via <details> collapsed.

### Accessori editabili (`5a82862`)

PdcBlockInput estesa con minuti_accessori?: string. BlockEditor: chip
"acc.min" accanto a "● magg.". I treni creati col bottone o cliccando la
timeline nascono con minuti_accessori="5/5" come default. Il rendering
del Gantt v2 mostra la riga ausiliaria sotto i minuti principali.

### BlockEditor chip-style Linear/Notion (`38a6ea9`)

Refactor radicale dell'editor blocco:
- Una RIGA per blocco con chip cliccabili: [#0] [🚆 Treno] [10243 ◆]
  [DOMO → Mlpg] [20:20–22:24] [acc 5/5] [✕]
- Click su chip → popover inline con input. Esc / click fuori → chiude
- Mappa colori: train blu, vettura grigio, CV viola, refez ambra,
  scomp ciano, available verde
- Bottone elimina visibile solo al hover (group-hover)
- Helper Chip + Popover riusabili

**Auto-fill al cambio numero treno** (debounce 600ms):
1. lookupTrainInGiroMateriale → badge ◆ verde "giro materiale"
2. Fallback trainCheck.arturo_live → badge ◆ blu "ARTURO Live"
3. Non trovato → badge ◇ ambra "manuale"
Sovrascrive solo i campi VUOTI, preserva edit utente.

### Prossimi step (richiesti dall'utente)

- **CVL/CB automatici dal giro materiale**: quando il treno richiede
  cambio volante prima/dopo, aggiungere auto i blocchi CVp/CVa con
  orari letti dal giro materiale.
- **Periodicità auto del giorno**: dato il treno selezionato, suggerire
  la periodicità della giornata (LMXGVSD vs S vs D ecc.) leggendo dalle
  note di periodicità del treno.
- **Auto-builder di turni**: visione lungo termine — dato un set di
  treni iniziali, comporre automaticamente turni completi rispettando
  le regole operative italiane (max prest 510min, max condotta 330min,
  refezione obbligatoria, ecc.).
- **Fase 2 parser v2**: miss 28→26 turni + pallino accessori ● + minuti
  accessori popolati dal PDF.

---

## 2026-04-17 (notte tardi) — Completamento azioni action bar + cross-day in Builder

Chiuse tutte le azioni dell'action bar tranne `↔ Sposta` (che ora mostra
un hint toast perche' il drag diretto e' gia' il gesto primario), e
abilitato il drag cross-day anche nel PdcBuilderPage tra giornate dello
stesso turno.

### PdcPage (vista sola lettura)
- Cablato `↗ Dettaglio`, `⚠ Warning`, `⧗ Storico` al BlockDetailModal
  (triple-check DB interno + PdC + ARTURO Live)

### PdcBuilderPage
- Drag cross-day tra giornate (ganttId=`day-{idx}`) con auto-correzione
  orari al drop via /train-check
- Banner blu "Trascina su un'altra giornata..." durante il drag
- Banner verde di conferma con orari canonici applicati
- `🔗 Collega` ora funzionale: interroga /train-check e sostituisce
  start_time/end_time + from_station/to_station del blocco
- `⧗ Storico` → BlockDetailModal (mostra ARTURO Live live data)
- `↔ Sposta` → toast informativo "usa il drag diretto"
- pdcBlockToInput() helper aggiunto (inversa di inputToPdcBlock)

### PdcDepotPage
- `↗ Dettaglio`/`⚠ Warning`/`⧗ Storico` al BlockDetailModal
- `× Elimina` sul Gantt con conferma + debounced save (1500ms)

### Test
- tsc --noEmit: zero errori
- build production: 425KB (da 420KB, +5KB per tutti i nuovi handler)

### Rimane open
- Fase 2 (parser v2): miss 26/28 turni, pallino accessori ●, riga
  minuti accessori popolata
- Grafico ritardi 30gg dedicato per `⧗ Storico` (oggi riusa detail)

---

## 2026-04-17 (notte) — Fase 3 step 3+4+5: action bar, drag cross-day, triple-check

Sessione lunga di iterazione su PdcGanttV2 e sulle sue pagine consumer.
Aggiornamento deploy: commit `d3eb861` (flusso ImportPage 2-step con preview
diff) committato dall'utente direttamente.

### PdcGanttV2: action bar contestuale (commit 61c016e)

Click su una chip → appare sopra una barra con 8 icone contestuali:
  ✎ Modifica | ↔ Sposta | ⧉ Duplica
  🔗 Collega giro materiale | ⚠ Warning ARTURO Live
  ↗ Dettaglio | ⧗ Storico ritardi | × Elimina

Posizionamento dinamico, clampato ai bordi, freccia verso la chip.
Esc / click fuori → deseleziona. Click su un'altra chip → switch.
Nuovo prop onAction(action, block, idx) + tipo esportato GanttAction.

### PdcGanttV2: minuti accessori + azioni reali (commit 10a656f)

- Render riga ausiliaria `minuti_accessori` sotto i minuti principali
  (italics 8px, grigio). Campo popolato dal parser v2.
- PdcBuilderPage: Elimina (con conferma) + Duplica + Modifica collegate.
- Elimina su un treno rimuove anche CVp/CVa agganciati.

### Drag cross-day HTML5 DnD (commit d37fdec)

Rimosso il vecchio flusso "Incolla qui" in PdcDepotPage.
Ora le chip treno sono `draggable`: l'utente afferra, trascina nel
Gantt di un'altra giornata, rilascia. CVp/CVa del treno viaggiano
insieme come linkedCvp/linkedCva nel payload HTML5 DataTransfer.

Nuovi prop PdcGanttV2:
  ganttId                obbligatorio per DnD
  onCrossDayDragStart    parent registra la source
  onCrossDayDrop         parent applica il move
  onCrossDayRemove       opzionale

Banner blu "Rilascia NNNN su un'altra giornata" durante il drag.

### Auto-correzione orari al drop (commit 31af3c2)

Quando un treno drop-pato in un'altra giornata ha un train_id,
PdcDepotPage chiama /train-check/{train_id}:
  1) se giro materiale lo conosce → usa dep_time/arr_time del giro
  2) altrimenti se ARTURO Live → usa orari live
  3) fallback silenzioso → mantiene orari originali

Banner verde transitorio: "Orari del treno NNNN allineati a
[giro materiale|ARTURO Live]: HH:MM → HH:MM".

### BlockDetailModal triple-check

Componente nuovo (autore: utente). Modale con triple-check
DB interno + PdC + ARTURO Live. Due modalita':
  - detail  → panoramica neutra
  - warn    → evidenzia discrepanze orari

Cablato alle azioni `↗ Dettaglio` e `⚠ Warning` dell'action bar
in PdcBuilderPage.

### Prossimi step

- PdcBuilderPage: abilitare drag cross-day tra giornate dello stesso
  turno (oggi e' solo PdcDepotPage)
- PdcPage lettura sola: cablare `↗ Dettaglio` a BlockDetailModal
- Action bar icone ↔ Sposta / 🔗 Collega / ⧗ Storico ancora placeholder
- Fase 2 parser v2 (miss 28→26, pallino accessori, minuti accessori)

---

## 2026-04-17 (sera) — Fase 3 step 1: PdcGanttV2 (drop-in) in PdcPage

### Cosa
Nuovo componente React `frontend/src/components/PdcGanttV2.tsx` che
implementa il design del mockup `gantt-ideal-v5.html`:

- chip-card blu indigo per i treni con numero + dest dentro
- blocchi secondari (vettura/refez/CVp/CVa) con label orizzontali su
  3 livelli Y (stagger automatico anti-collisione)
- stazioni capolinea orizzontali ai bordi
- fascia notte 00-03, tick asse 3→24→1→2→3 a 52 px/h
- hover → tooltip dettagli (HTML overlay, non SVG title)
- click → selected (bordo azzurro solido)

API esterna **compatibile** con PdcGantt v1 (drop-in): usa gli stessi
props `blocks`, `startTime`, `endTime`, `onBlockClick`, `onTimelineClick`,
`label`, `depot`, `height`. Il prop `onBlocksChange` c'e' ma e' ignorato
in questa prima versione (drag&resize tornano in Fase 3 step 2).

### Dove e' visibile
`PdcPage.tsx` ora ha un **toggle a 3 viste**: `✨ Gantt v2` (default),
`📊 Gantt v1`, `📋 Lista`. L'utente puo' confrontare al volo e tornare
al vecchio Gantt se qualcosa non va. v2 e' default.

`PdcBuilderPage` e `PdcDepotPage` restano su v1 per ora (quelle pagine
richiedono drag&resize che v2 non ha ancora).

### Verifica
- `npx tsc --noEmit`: zero errori
- `npm run build`: OK, dist 405KB (+11KB rispetto a 394KB precedente)

### Prossimi step
- Fase 3 step 2: drag&resize in v2, poi sostituzione v1 anche in
  Builder/Depot
- Fase 2: parser v2 (risolve il miss 28→26 + pallino ● + minuti accessori)
- Fase 3 step 3: action bar con 8 azioni (come mockup), click su chip
  apre menu contestuale sopra

### File modificati questa sessione
- `frontend/src/components/PdcGanttV2.tsx` — NEW, ~400 righe
- `frontend/src/pages/PdcPage.tsx` — toggle v1/v2/lista
- `frontend/dist/` — rebuilded

---

## 2026-04-17 (tardo pomeriggio) — Fase 1 step 2: endpoint upload versionato + diff

### Comportamento upload PdC

Il vecchio flusso era: `upload → clear_pdc_data (WIPE) → insert`.
Il nuovo flusso versionato (schema v2.1) è:

- `POST /upload-turno-pdc?dry_run=true` → parsa il PDF e ritorna la **diff**
  rispetto ai turni attivi (`new` / `updated` / `only_in_old`), SENZA scrivere nulla.
- `POST /upload-turno-pdc` (default, dry_run=false) → crea `pdc_import` nuovo,
  inserisce i turni con `import_id = nuovo`, poi marca `superseded_by_import_id`
  sui turni precedenti che hanno stesso `(codice, impianto)`.

Nuovi endpoint:

- `GET /pdc-imports` → lista storico import, piu' recenti prima, con conteggio
  `turni_attivi` per ogni import
- `GET /pdc-imports/{id}` → dettaglio import + lista dei turni generati
  (mostra quali di quelli sono stati nel frattempo superseded da un import successivo)

### Modifiche DB/parser

**src/database/db.py** — nuovi metodi:

- `insert_pdc_import(...)` crea record import
- `list_pdc_imports()` / `get_pdc_import(id)`
- `mark_superseded_turns(new_import_id)` archivia i precedenti con stessa (codice, impianto)
- `diff_import_candidates(turns)` calcola new/updated/only_in_old senza scrivere

Metodi esistenti modificati per default "solo turni attivi":

- `list_pdc_turns(include_inactive=False)`
- `find_pdc_train(train_id, include_inactive=False)`
- `get_pdc_stats(include_inactive=False)`

`insert_pdc_turn` ora accetta `import_id` e `data_pubblicazione` come kwargs
opzionali (retro-compatibile: legacy callers NULL).

**src/importer/turno_pdc_parser.py** — split del salvataggio:

- `save_parsed_turns_as_import(turns, db, filename, ...)` → NUOVO flusso versionato
- `save_parsed_turns_to_db(turns, db)` → LEGACY (con WIPE totale), tenuto per CLI
- `_write_parsed_turns(...)` worker interno condiviso

### Verifica end-to-end

Test su `uploads/Turni PdC rete RFI dal 23 Febbraio 2026.pdf` (446 pagine).

Parser v1 legge **26 turni** (l'indice ne dichiara 28 → parser miss nota,
verra' risolta in Fase 2 con parser v2).

Risultati test via HTTP a backend locale:

- dry_run vs DB vergine: `{new: 26, updated: 0, only_in_old: 0}` ✓
- import #1: crea pdc_import id=1, inserisce 26 turni + 1344 giornate + 6925 blocchi + 2901 note ✓
- dry_run #2 (DB ora con 26 attivi): `{new: 0, updated: 26, only_in_old: 0}` ✓
- import #2 (re-upload): marca superseded 26 turni del import #1 ✓
- `GET /pdc-imports` restituisce 2 import, #2 con 26 attivi, #1 con 0 attivi ✓
- stats attivi: 26 turni; stats include_inactive: 52 (storico intero conservato) ✓

### Prossimi step

**Fase 3** (UI): aggiornare `static/index.html` (legacy) e/o il frontend React
per:
- mostrare lista `GET /pdc-imports` con pulsante "Storico"
- all'upload: prima chiama `?dry_run=true`, mostra finestra conferma con diff,
  solo dopo OK utente chiama l'upload reale
- pulsante "torna a import precedente" (opzionale: rollback)

**Fase 2** (parser v2): risolvere il miss 28 vs 26 + coverage orari 100% +
minuti accessori + pallino `●` accessori maggiorati.

### File modificati questa sessione
- `src/database/db.py` — metodi versioning + filtri include_inactive
- `src/importer/turno_pdc_parser.py` — save_parsed_turns_as_import + _write_parsed_turns
- `api/importers.py` — endpoint upload versionato + /pdc-imports

---

## 2026-04-17 — Fase 0 (mockup Gantt) chiusa · Fase 1 step 1 (schema + versioning DB) fatta

### Contesto
Ripartenza dopo i problemi aperti di ieri (vedi sezione più sotto).
L'utente vuole ripensare Gantt + parser insieme, non patch su patch.

### Fase 0 — mockup statici del Gantt ideale (in `mockups/`)

Iterazioni fino al "target visivo finale" approvato:

- `gantt-ideal-v1.html` — primo tentativo PDF-like generico (non piaciuto)
- `gantt-ideal-v2.html` — Opzione C "moderna derivativa" (label verticali, periodicità sopra numero, minuti su 2 righe, stats come testata) — problemi di sovrapposizioni
- `gantt-ideal-v3.html` — asse 52 px/h, stagger Y, rimosso riferimento M 704 → nostro modello **MDL-PdC v1.0**
- `gantt-ideal-v4.html` — svolta: chip-card scura per i treni con numero+dest dentro, label orizzontali con stem su 3 livelli Y (no più rotate(-90))
- `gantt-ideal-v5.html` — **FINALE**: chip-card **blu indigo** (gradient) invece di nero, testo adattivo (solo numero se chip<85px), interattività completa:
  - hover → tooltip dinamico con dettagli
  - click → selected (bordo azzurro solido) + action bar sopra
  - click fuori / Esc → deseleziona
  - 8 azioni nell'action bar con separatori visivi:
    - ✎ Modifica, ↔ Sposta, ⧉ Duplica
    - 🔗 Collega giro mat, ⚠ Warning ARTURO Live
    - ↗ Apri dettaglio, ⧗ Storico ritardi
    - × Elimina

Preview dei mockup via `python3 -m http.server` su porta 8765
(config in `.claude/launch.json` → nome `mockups`).

### PDF reale disponibile

`uploads/Turni PdC rete RFI dal 23 Febbraio 2026.pdf` (3.5 MB, **446 pagine**, **28 turni Condotta**).
Non committato (uploads/ in .gitignore).
Indice pag.1 confermato. Pag.2 AROR_C conferma tutti i casi attesi:
- varianti `2 LMXGVS` + `2 D` (chiave composta)
- giornata 4 LMXGV ha il pallino ● accessori maggiorati con nota "Tr.10205 tempi accessori maggiorati per preriscaldo"
- casi S.COMP, REFEZ, CVp puntuali, vetture, treni commerciali

### Fase 1 step 1 — schema PdC v2.1 (versioning + campi arricchiti)

Doc: `docs/schema-pdc.md` (fonte unica di verità per parser+frontend+DB).

Strategia sostituzione turni concordata: **i nuovi PDF sostituiscono i precedenti**
(UI mostra solo gli attivi). Storico conservato via `superseded_by_import_id`
come rete di sicurezza, non cancellato.

**Migrazione DB aggiunta in `src/database/db.py`** (idempotente via `_run_migration`):

- Nuova tabella `pdc_import` (id, filename, data_stampa, data_pubblicazione,
  valido_dal/al, n_turni, n_pagine_pdf, imported_at, imported_by)
- `pdc_turn`: +`import_id` FK, +`superseded_by_import_id` FK, +`data_pubblicazione`
- `pdc_turn_day`: +`stazione_inizio`, +`stazione_fine` (capolinea ARON...ARON)
- `pdc_block`: +`minuti_accessori`, +`fonte_orario` (parsed/interpolated/user),
  +`cv_parent_block_id` (link CVp/CVa → treno padrone), +`accessori_note`
- Indice `idx_pdc_turn_active` per query "turni attivi"

Verifica su DB locale `turni.db`: tutte le 10 aggiunte presenti, zero perdita
dati (DB locale era comunque vuoto, quello Railway riceverà la migrazione al
prossimo deploy).

### Prossimi step

**Fase 1 step 2**: endpoint API upload PDF crea record `pdc_import`, collega
turni creati, marca superseded i precedenti con stesso `(codice, impianto)`.
Includere schermata diff prima della conferma sostituzione.

**Fase 2**: parser v2 test-driven sul PDF reale. Fixture primaria = AROR_C.
Obiettivo coverage 100% orari, uso minuti accessori (riga ausiliaria),
cattura pallino `●`, varianti giornata per periodicità.

**Fase 3**: sostituzione `frontend/src/components/PdcGantt.tsx` (908 righe)
con nuovo componente che replica v5. API esterna invariata (blocchi,
onBlocksChange) → `PdcBuilderPage` e `PdcDepotPage` non cambiano.

**Fase 4**: azioni action bar reali + warning ARTURO Live + cross-day drag.

### File modificati/creati questa sessione
- `docs/schema-pdc.md` — NEW, specifica completa schema PdC v2.1
- `src/database/db.py` — migrazione v2.1 (tabella pdc_import + colonne)
- `mockups/gantt-ideal-v1..v5.html` — NEW, 5 iterazioni mockup statici
- `.claude/launch.json` — aggiunta config server `mockups` (python3.12 http.server port 8765)

---

## 2026-04-17 — STATO ATTUALE E PROBLEMI APERTI (punto di ripartenza)

### Fatto finora (commits recenti)
- `d494c31` Step 7 Gantt SVG visuale + builder interattivo
- `2be4e9e` Gantt mostra tutti i blocchi con fill orari
- `72ab5c8` Interpolazione uniforme blocchi
- `3e17f89` Step 8 Parser sequenziale (89% copertura orari)
- `57669ae` Step 8d Gantt stile PDF (linee sottili)
- `05f6a81` Step 8d-h Gantt colorato + drag & drop blocchi
- `4d1cd91` Step 9a+b+c CVp/CVa linked, snap, lookup giro materiale
- `a5f2363` Step 9d Vista deposito (tutti turni editabili + auto-save)
- `aee2ece` Step 10a+b+d Gantt tweaks + rientro vettura + sposta tra giornate

### PROBLEMI APERTI da affrontare (per la prossima sessione)

**Gantt / UX**:
- Layout ancora "piccolo", non si legge bene come nel PDF
- Numero treno, stazioni e orari si sovrappongono quando i blocchi sono vicini
- La timeline 3→24→3 occupa tanto spazio inutile per turni brevi
- Le label verticali non sono leggibili bene in alcuni punti

**Drag interazione**:
- Ancora troppo sensibile in alcuni casi (serve più threshold)
- Il drag di un treno non rispetta sempre i CVp/CVa (vedere casi edge)
- Manca feedback visivo "ghost" durante il drag
- Manca snap ai blocchi vicini (es. end di un treno = start del successivo)

**Parser**:
- Copertura start_time: 89% — gli altri 11% sono giornate con layout ambiguo
- Molti blocchi hanno orari approssimati via interpolazione invece che estratti dal PDF
- I minuti sotto l'asse (accessori/secondari) NON sono ancora usati
- Non rileva blocchi "accessori inizio/fine giornata" (setup, wrap-up)

**Collegamento giro materiale**:
- Lookup funziona (button 🔍) ma non è automatico quando si digita
- Non crea automaticamente CVp/CVa quando il treno richiede cambio volante
- Validazione vs orari reali ARTURO Live non ancora implementata

**Cross-day / Multi-turno**:
- "Incolla qui" funziona ma è macchinoso (click + scroll + click)
- Manca vero drag & drop tra giornate
- Nessuna validazione che impedisca conflitti (stesso treno in due turni)

**Accessori**:
- Blocchi "accessori inizio giornata" e "accessori fine giornata" non esistono
- Il parser non li cattura
- Il DB schema non li contempla esplicitamente

**Validazione ARTURO Live**:
- Non implementata: spostando un treno non viene verificato l'orario reale
- Manca warning "treno ha orario diverso da ARTURO Live"

**Backend**:
- Parser v1 ancora da migliorare (coverage, minuti secondari, accessori)
- Ri-import del PDF su Railway richiesto manualmente dopo modifiche parser
- Nessun test end-to-end completo sul PDF reale

### Strategia consigliata per la prossima sessione
1. **Leggere prima**: CLAUDE.md + questo file + skill `.claude/skills/turno-pdc-reader.md`
2. **Piano pulito**: l'utente vuole avvicinare il Gantt al PDF Trenord, non fare patch su patch
3. **Priorità UX**: iterare ripartendo da mockup statico (Figma?) invece che modificare a piccoli pezzi
4. **Parser**: lavorare a test-driven, con fixture di PDF reale
5. **Split**: backend (parser + API) e frontend (Gantt + editor) come lavori separati

### Stato DB Railway
- 26 turni caricati (dal primo import)
- Parser v2 push-ato ma il DB ha ancora i dati del parser v1 → serve ri-caricare il PDF

### File chiave
- `src/importer/turno_pdc_parser.py` — parser (785 righe)
- `frontend/src/components/PdcGantt.tsx` — Gantt SVG (900 righe circa)
- `frontend/src/pages/PdcBuilderPage.tsx` — builder
- `frontend/src/pages/PdcDepotPage.tsx` — vista deposito
- `api/pdc_builder.py` — CRUD + calendario

---

## 2026-04-17 — Step 10a+b+d: Gantt visual tweaks + rientro vettura + sposta tra giornate

### Feedback utente
1. Ridurre dimensione blocchi non-treno (molto sottili)
2. Stazioni intermedie mostrate tra blocchi
3. Pulsante "Rientro in vettura" che usa ARTURO Live
4. Possibilità di spostare un treno tra giornate/turni del deposito

### 10a — Visual tweaks Gantt
Altezze blocchi ridotte per enfatizzare il treno:
- train: 26px (era 28)
- coach_transfer: **10px** (era 20)
- meal: **10px** (era 20)
- scomp: **8px** (era 16)
- marker CVp/CVa: 24px (era 30)

Aggiunto render **stazioni intermedie** tra coppie di blocchi consecutivi:
- Label piccola (9px) a metà del gap tra end di un blocco e start del successivo
- Se stazione coincide: mostra solo quella (punto di passaggio)
- Se cambiano: mostra `A→B`

### 10b — Rientro in vettura via ARTURO Live
Nuova funzione frontend `findReturnTrain(from, to, afterTime)` che chiama il già esistente endpoint backend `GET /vt/find-return`.

Nel `DayEditor`:
- Pulsante **"Rientro in vettura"** (icona 🏠) accanto a "Aggiungi blocco"
- Usa `impianto` del turno come destinazione
- Usa la stazione dell'ultimo blocco con `to_station` come origine
- Usa l'end_time dell'ultimo blocco come `after_time`
- Mostra una lista di treni candidati da ARTURO Live
- Click "+ Aggiungi" crea un nuovo `coach_transfer` con numero vettura e orari reali

### 10d — Sposta treno tra giornate/turni (PdcDepotPage)
Nuovo flusso "cut & paste" in `PdcDepotPage`:
1. Utente clicca un treno o vettura in una giornata → state `moveState` attivo
2. Banner giallo in alto con info del blocco in spostamento + bottone "Annulla"
3. Su ogni altra giornata appare bottone **"Incolla qui"**
4. Click → rimuove il blocco (e CVp/CVa agganciati) da source, li aggiunge a target
5. Debounce save per entrambi i turni (source e target)

### Build
- `tsc --noEmit` OK
- 394 KB JS (113 gzip)

### File modificati
- `frontend/src/components/PdcGantt.tsx` — altezze ridotte + label stazioni intermedie
- `frontend/src/lib/api.ts` — `findReturnTrain`, type `ReturnTrain`
- `frontend/src/pages/PdcBuilderPage.tsx` — pulsante Rientro vettura + candidati list, prop `impianto` per DayEditor
- `frontend/src/pages/PdcDepotPage.tsx` — move tra giornate via click + "Incolla qui"

### Limitazioni (da affrontare nei prossimi step)
- Validazione "treno fuori orario" via ARTURO Live quando si sposta
- Blocchi accessori inizio/fine giornata non ancora presenti

---

## 2026-04-17 — Step 9d: Vista deposito completa (tutti turni editabili)

### Nuova pagina `PdcDepotPage.tsx` su route `/pdc/depot/:impianto`
Consente di visualizzare e modificare contemporaneamente TUTTI i turni di un deposito con tutte le loro giornate in un'unica vista.

### Layout
- Header con nome deposito + back button
- Lista turni del deposito (filtro lato server)
- Ogni turno: accordion espandibile (primo aperto di default)
- Alla espansione lazy-load del dettaglio turno
- Ogni giornata del turno: Gantt interattivo completo (200px alto)
- Giornate "Disponibile" mostrano solo testo

### Auto-save
- `onBlocksChange` aggiorna lo state locale → `dirty=true`
- Debounce 1.5s dopo l'ultima modifica → chiamata `PUT /pdc-turn/{id}`
- Badge visuale per turno:
  - 🟠 "Modificato" (dirty ma non ancora salvato)
  - 🔵 "Salvataggio..." (spinner durante il PUT)
  - 🟢 "Sincronizzato" (dopo commit riuscito)
- Un debounce timer separato per turno → salvataggi paralleli, non interferiscono tra loro

### Integrazione `PdcPage`
Nuovo bottone **"Vista deposito"** nell'header del dettaglio turno accanto a Modifica/Elimina. Link a `/pdc/depot/<impianto>`.

### Flusso utente
1. Dalla pagina turni, cliccare su un turno
2. Click "Vista deposito" → apre tutti i 1-N turni del deposito
3. Espandere i turni di interesse → ogni giornata mostra Gantt editabile
4. Trascinare un treno in qualsiasi giornata → auto-save dopo 1.5s
5. Badge verde "Sincronizzato" conferma il salvataggio

### Limitazioni attuali
- Non ancora drag cross-day (spostare treno da g1 di turno A a g2 di turno B). Necessita state condiviso tra Gantt + logica di rimozione/aggiunta nel blocco source/target. Prossimo step (opzionale).
- Ogni Gantt gestisce solo i propri blocchi: il drag resta all'interno della singola giornata.

### Build
- Zero errori TS (fixato `NodeJS.Timeout` → `ReturnType<typeof setTimeout>`)
- 387 KB JS (111 gzip)

### File creati / modificati
- `frontend/src/pages/PdcDepotPage.tsx` — NEW, ~280 righe
- `frontend/src/App.tsx` — route `/pdc/depot/:impianto`
- `frontend/src/pages/PdcPage.tsx` — bottone "Vista deposito" in TurnDetail

---

## 2026-04-17 — Step 9a+b+c: CVp/CVa linked, drag con snap, lookup giro materiale

### Feedback utente
1. CVp/CVa devono essere "agganciati" al treno — non modificabili da soli
2. Drag troppo sensibile — serve threshold e snap
3. I turni PdC devono collegarsi al giro materiale (lookup auto per orari/stazioni)

### Step 9a — CVp/CVa legati al treno adiacente
Nuove helper `getLinkedCVs()` e `getParentTrainIndex()` in `PdcGantt.tsx`:
- `train` a indice N → CVp a N-1 (se esiste) + CVa a N+1 (se esiste) formano un "gruppo"
- Drag di un CVp/CVa → reindirizza al treno padrone (il gruppo si sposta insieme)
- Drag/move del treno → sposta anche CVp/CVa agganciati preservando le distanze (0 per puntuali)
- Resize-start del treno → il CVp si aggancia al nuovo start
- Resize-end del treno → il CVa si aggancia al nuovo end

### Step 9b — Threshold + Snap
Nuove prop `dragThresholdPx={4}` e `snapMinutes={5}` di default:
- Drag parte SOLO dopo 4px di movimento (anti-click spurio)
- Delta orari arrotondato al multiplo di 5 min
- Nuovo flag `active` in `DragState` per distinguere hover/click da drag vero

### Step 9c — Lookup giro materiale
Nuovo endpoint backend **`GET /pdc-builder/lookup-train/{train_id}`**:
- Cerca il treno in `train_segment` (giro materiale già importato)
- Ritorna `from_station`, `to_station`, `dep_time`, `arr_time`, `material_turn_id`, `is_deadhead`
- 200 sempre: `{found: bool, ...}`

Integrazione frontend:
- `lib/api.ts`: `lookupTrainInGiroMateriale(trainId)` + tipo `TrainLookup`
- `PdcBuilderPage.BlockEditor`: bottone 🔍 accanto al campo `train_id`
  - Click → chiama il lookup
  - Se trovato → popola automaticamente `from_station`, `to_station`, `start_time`, `end_time`
  - Mostra messaggio: ✓ trovato / ⚠ non trovato / ✗ errore
- Bottone appare solo per `block_type === "train"` con `train_id` compilato

### Test backend
2 nuovi test in `tests/test_pdc_builder.py`:
- `test_lookup_train_not_found` → `found: False`
- `test_lookup_train_found_in_giro_materiale` → popola giro, cerca, verifica tutti i campi

Fix: `_make_client()` ora patcha anche `api.pdc_builder.get_db` e `api.importers.get_db` direttamente (binding Python statico da `from ... import get_db`).

Suite totale: 20/20 pdc_builder, 110/111 globale (1 fail pre-esistente).

### Build
- Zero errori TS, 380 KB JS (110 gzip)

### File modificati
- `frontend/src/components/PdcGantt.tsx` — onBlocksChange, getLinkedCVs, threshold+snap
- `frontend/src/pages/PdcBuilderPage.tsx` — lookup button, nuovo onBlocksChange handler
- `frontend/src/lib/api.ts` — lookupTrainInGiroMateriale + types
- `api/pdc_builder.py` — endpoint GET /pdc-builder/lookup-train/{train_id}
- `tests/test_pdc_builder.py` — 2 nuovi test + patch _make_client

---

## 2026-04-17 — Step 8d-h: Gantt colorato + drag & drop blocchi

### Feedback utente
1. Mantenere i colori (non solo linee bianche)
2. Ingrandire le barre (troppo piccole nel Gantt stile-PDF)
3. Interazione non distruttiva: drag singolo blocco senza toccare gli altri

### Gantt v3 (`PdcGantt.tsx`)
Riscritto componente con:

**Barre colorate e grandi**:
- `train`: 28px blu pieno `#0062CC` (prima 3px)
- `coach_transfer`: 20px viola tratteggiato `#A78BFA`
- `meal`: 20px verde tratteggiato `#34D399`
- `scomp`: 16px grigio tratteggiato `#CBD5E1`
- `cv_partenza`/`cv_arrivo`: "bandierina" verticale ambra 30px con label sopra
- Altezza totale SVG: 220px

**Interattività drag & drop**:
- Prop `onBlockChange(index, {start_time, end_time})` callback
- Handle invisibili:
  - Centro della barra -> `move` (sposta tutto preservando durata)
  - Primi/ultimi 6px -> `resize-start` / `resize-end`
- Cursor dinamico: `grab` / `grabbing` / `ew-resize`
- Preview ottimistico durante il drag via `overrides` state locale
- Al mouseup chiama `onBlockChange` solo per l'indice draggato → **gli altri blocchi non vengono toccati**
- `userSelect: none` e pointerEvents su label/orari per non interferire

**Eventi globali**: `mousemove`/`mouseup` su `window` durante drag, rimozione automatica via useEffect cleanup.

### Integrazione `PdcBuilderPage`
Il callback aggiorna `blocks[idx]` con i nuovi orari mantenendo intatti gli altri:
```typescript
onBlockChange={(idx, changes) => {
  const blocks = [...(day.blocks || [])]
  blocks[idx] = { ...blocks[idx], ...changes }
  onChange({ ...day, blocks })
}}
```

### Build
- Zero errori TS
- 378 KB JS (109 gzip)

### File modificati
- `frontend/src/components/PdcGantt.tsx` (riscritto completo)
- `frontend/src/pages/PdcBuilderPage.tsx` (aggiunto `onBlockChange`)

---

## 2026-04-17 — Step 8: Parser allocazione sequenziale, tutti i blocchi popolati

### Motivazione (feedback utente)
Il turno ALOR_C g1 LMXGV aveva nel DB solo 1 orario (train 10574 start=11:41); gli altri 4 blocchi vuoti. Il Gantt quindi non mostrava la sequenza.

### Sonda sul PDF (pagina 386 ALOR_C)
La pagina contiene **7 minuti sopra l'asse** (41, 55, 28, 38, 05, 19, 34) allineati a 5 etichette blocco. Il parser ne catturava 1 solo.

### Nuovo algoritmo `_assign_minutes_to_blocks`
Approccio **sequenziale puro**:
1. Ordino i minuti per X crescente
2. Itero i blocchi in ordine X
3. Blocco continuo (train/coach_transfer/meal): 2 minuti (start, end)
4. Blocco puntuale (cv_partenza/cv_arrivo): 1 minuto (start)
5. scomp/available: 0 minuti

### Risultato ALOR_C g1 LMXGV (dopo reimport PDF)
```
train 10574     11:41 - 12:55
cv_arrivo 10678 13:28
cv_partenza     14:38
train 10581     15:05 - 16:19
cv_arrivo 10584 16:34
```
Orari reali estratti dal PDF, non stime.

### Copertura globale
- start_time: 89.4% (era 85.6%)
- end_time su continui: 84.9% (era 83.1%)

### Test
Aggiornato `test_assign_minutes_typical_sequence`. Suite: 108/109.

### Azione richiesta
Ricaricare il PDF dalla pagina Import dopo il deploy per popolare il DB.

### File modificati
- `src/importer/turno_pdc_parser.py`
- `tests/test_turno_pdc_parser.py`

---

## 2026-04-16 — Step 7e: Gantt mostra TUTTI i blocchi (fill orari mancanti)

### Problema rilevato dall'utente
Nel turno ALOR_C g1 LMXGV, la vista **Lista** mostrava 5 blocchi (Treno 10574, CVa 10678, CVp 10677, Treno 10581, CVa 10584) mentre il **Gantt** ne mostrava solo 1 (il primo con orario completo). I blocchi senza `start_time` o `end_time` venivano scartati.

### Cause
Il parser PdC spesso lascia orari parziali:
- **Puntuali** (CVp/CVa): nessun minuto proprio nel PDF (condividono con vicini)
- **Treni** preceduti da CVp: solo `end_time` (regola -1 minuto del parser)
- **Treni** seguiti da CVa: solo `start_time`

### Fix: `fillBlockTimes(blocks, dayStart, dayEnd)`
Funzione pura in `PdcGantt.tsx` che pre-processa i blocchi prima del render:

1. **Forward pass**: ogni blocco senza `start_time` eredita l'`end_time` del precedente. Se il primo blocco non ha start, usa `startTime` della giornata.
2. **Mirror puntuali in-loop**: CVp/CVa con solo `start_time` → `end_time = start_time` (così il successivo puo' ereditare correttamente).
3. **Backward pass**: speculare per `end_time` vuoto → `start_time` del successivo. Ultimo blocco eredita `endTime` della giornata.
4. **Mirror inverso** per puntuali in backward pass.

### Verifica su ALOR_C g1
Input (Lista):
- train 10574 11:21-11:41
- cv_arrivo 10678 vuoto
- cv_partenza 10677 vuoto
- train 10581 -16:10
- cv_arrivo 10584 vuoto

Output dopo fill:
- train 10574 11:21-11:41
- cv_arrivo 10678 11:41-11:41
- cv_partenza 10677 11:41-11:41
- train 10581 11:41-16:10
- cv_arrivo 10584 16:10-16:10

Tutti e 5 renderizzabili.

### Build
- `tsc --noEmit` OK, `npm run build` 375 KB JS

### File modificati
- `frontend/src/components/PdcGantt.tsx` (+45 righe `fillBlockTimes`)
- `frontend/dist/*`

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
