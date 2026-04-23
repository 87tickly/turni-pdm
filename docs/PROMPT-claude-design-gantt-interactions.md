# Prompt per Claude Design — GanttSheet interactions layer

> Copia/incolla su claude.ai/design. Repo `87tickly/turni-pdm` +
> cartella locale `COLAZIONE` già collegati come contesto filesystem
> diretto. NON serve upload bundle: leggi le sorgenti direttamente.

---

## Contesto

Il Gantt v3 (`frontend/src/components/gantt/GanttSheet.tsx`) è la nuova
base visiva "falsa riga PDF Trenord" prodotta dal tuo handoff
precedente (`docs/HANDOFF-gantt-v3.md`). Rendering eccellente, già
usata da `AutoBuilderGantt.tsx` e `/gantt-preview`.

**Problema**: la base `GanttSheet` supporta solo `onSegmentClick` e
`onSegmentContextMenu`. È un componente di **sola resa**.

In produzione, il Gantt giornata PdC è usato in 3 pagine che sono
tutti **editor interattivi vivi** e vivono oggi su `PdcGanttV2.tsx`
(~1400 righe di interazioni):

| Pagina | Interazioni attive oggi |
|--------|-------------------------|
| `frontend/src/pages/PdcPage.tsx` | drag move + resize + cross-day (canEdit=true sempre) |
| `frontend/src/pages/PdcBuilderPage.tsx` | drag + resize + cross-day + timeline click (add) + action bar (delete) |
| `frontend/src/pages/PdcDepotPage.tsx` | drag + cross-day + action bar (detail/warn/delete) |

La migrazione `PdcGanttV2 → GanttSheet` dichiarata nel handoff v3 §10
**non è possibile** finché `GanttSheet` non sa fare queste interazioni.
Se la forzo come wrapper "props invariate", perdo silenziosamente drag
e cross-day in tutte e 3 le pagine → regressione grave.

**Obiettivo di questo giro di redesign**: estendere `GanttSheet` con un
layer di interattività **opt-in** che copra tutte le funzionalità di
`PdcGanttV2`, senza rompere i consumer attuali (`AutoBuilderGantt`,
`GanttPreviewPage`) e senza alterare l'estetica "PDF" della base.

---

## Cosa redesignare

**File primario**:
- `frontend/src/components/gantt/GanttSheet.tsx` — aggiunta layer interazioni

**File che potrebbero richiedere estensioni**:
- `frontend/src/components/gantt/types.ts` (nuove props callback, tipo drag payload)
- `frontend/src/components/gantt/tokens.ts` (eventuali nuovi colori: selected ring, drag ghost, drop slot)

**File da leggere come reference delle interazioni da portare**:
- `frontend/src/components/PdcGanttV2.tsx` (sorgente canonico delle interazioni: drag, resize, cross-day DnD, action bar, tooltip, selected state, snap 5min, threshold 4px)
- `frontend/src/pages/PdcBuilderPage.tsx` §L800-850 (come vengono cablate le callback)
- `frontend/src/pages/PdcDepotPage.tsx` §L540-620 (idem in contesto depot con più Gantt sulla stessa pagina)
- `frontend/src/pages/PdcPage.tsx` §L470-505 e §L830-860 (idem in contesto "lettura-con-edit")

**Documenti di riferimento da leggere prima**:
- `docs/HANDOFF-gantt-v3.md` (base v3 + vincoli estetici già decisi)
- `docs/GANTT-GUIDE.md` (filosofia + 21 edge case + anti-pattern — **questa è la bibbia, non tradire nulla di qui**)
- `docs/HANDOFF-claude-design.md` (DS globale: palette Kinetic Conductor, tipografie, token generali)

---

## Interazioni da portare dentro `GanttSheet`

Sono 8 capacità distinte. Elencate come le ha `PdcGanttV2` oggi:

### 1. Drag "move" intra-Gantt
- Mouse down + trascinamento orizzontale → sposta blocco (intero range preservato)
- Threshold 4px prima di attivare drag (niente drag accidentale al click)
- Snap 5 minuti durante il drag
- Cursor `grab` → `grabbing` in drag
- Al mouse up → callback con le nuove coordinate

### 2. Resize start / resize end
- Handle `6px` ai bordi sinistro/destro di un blocco treno
- Cursor `ew-resize`
- Resize snap 5 minuti, vincolo `start < end - snap`
- Durante resize, gli eventuali CVp/CVa agganciati seguono il nuovo estremo (vedi §3)

### 3. Gruppo CVp/CVa legato al treno padrone
- Oggi CVp/CVa sono **flag** su `GanttSegment` (`cvp: boolean`, `cva: boolean`)
- Durante drag/resize del treno, il marker CVp (a inizio) e CVa (a fine) **seguono** il movimento, perché sono visualmente legati al treno stesso
- Un CVp/CVa isolato non si muove da solo: il drag sul suo punto deve essere reindirizzato al treno padrone
- Considera se questa modellazione (flag su treno) rimane giusta o se serve un tipo separato per segmento CV "satellite"; decidi tu

### 4. Cross-day drag (HTML5 DnD fra Gantt diversi)
- Un blocco può essere trascinato **fuori** dal Gantt e rilasciato in un altro Gantt della stessa pagina (es. Builder con 5 giornate impilate)
- Serve MIME custom (es. `application/x-colazione-block`), payload `{ganttId, block, index, linkedCvp?, linkedCva?}`
- Il componente sorgente chiama `onCrossDragStart` al momento del drag
- Il componente destinazione chiama `onCrossDrop(payload, targetGanttId, dropTime)` al rilascio
- Al drop riuscito (`dataTransfer.dropEffect === "move"`), il sorgente chiama `onCrossRemove(index, withLinkedCvs)` per togliere il blocco dal suo array
- Deve funzionare sia con 2 Gantt della stessa pagina Builder, sia con 2 Gantt di turni diversi in Depot
- Durante il drag un elemento deve esistere su ciascun Gantt targetable che evidenzi lo slot orario di drop (bordino verticale sull'asse al hover)

### 5. Click su timeline vuota (add block)
- Click in area asse ma non su un segmento → callback `onTimelineClick(hour, minute)`
- Usato da Builder per aggiungere un nuovo blocco "train" al click
- Cursor `crosshair` nell'area cliccabile

### 6. Hover tooltip
- Hover su un segmento → tooltip flottante con:
  - Titolo: tipo + id (`Treno 10045`, `Vettura 11055`, `CVp 10045`, `Refezione`, `S.COMP`)
  - Orario: `05:12 → 06:02`
  - Tratta: `AL → VOGH` (se presente)
  - `Accessori maggiorati (preriscaldo)` se `preheat=true`
  - `⚠ sospetto: <reason>` se `suspect_reason` presente
- Tooltip segue il mouse (niente jank)
- Si nasconde se inizia un drag

### 7. Action bar contestuale sopra blocco selezionato
- Click su blocco → entra in stato `selected` (ring verde kinetic, shadow marcata)
- Compare sopra il blocco una barra orizzontale con **8 icone** (ordine esatto di oggi):
  1. `✎` Modifica blocco
  2. `↔` Sposta (drag temporale o inter-turno)
  3. `⧉` Duplica blocco
  4. `🔗` Collega al giro materiale
  5. `⚠` Verifica discrepanze ARTURO Live (warn state)
  6. `↗` Apri dettaglio treno
  7. `⧗` Storico ritardi (ultimi 30 giorni)
  8. `×` Elimina blocco (danger state)
- Separatori verticali dopo icone 3, 5, 7 (raggruppamento semantico)
- Ogni icona emette un evento unico `action-<nome>`, il parent decide cosa farne (in PdcPage `detail/warn/history` apre il drawer; in Builder `delete` apre conferma; ecc.)
- La barra si posiziona sopra il blocco, clamp ai bordi del viewBox (se il blocco è vicino al margine, la barra si sposta orizzontalmente e la freccia-puntatore sotto si riposiziona per continuare a puntare il centro del blocco)
- Click fuori dal Gantt o `Esc` → deseleziona + nasconde action bar
- Prop `hideActionBar: boolean` → se true, action bar nascosta; in quel caso single-click apre direttamente il drawer via `onSegmentClick` (modalità "PdcPage lite" di oggi)

### 8. autoFit (opt-in) del range visibile
- Default: range fisso `[hStart, hEnd]` passato dal consumer (comportamento attuale)
- Con `autoFit: boolean` → range calcolato automaticamente dai tempi dei segmenti + padding 30min lato/lato, arrotondato all'ora, min 4h di span per leggibilità
- Utile in PdcPage quando una giornata ha range 07:00-14:00 e non voglio schiacciarla su 24h

---

## API finale auspicata (tu proponi, non forzo)

La base `GanttSheet` ha oggi queste props (non cambiano):

```ts
rows, dayHead, metrics, range, barHeight, labels, minutes, palette,
grid30, suspect, onSegmentClick, onSegmentContextMenu
```

Proponi l'API estesa. Pensieri miei (non obbligatori):

```ts
// Nuove props opt-in (se undefined, il comportamento resta "sola resa"
// attuale, garantendo 0-regressione per AutoBuilderGantt e preview)

ganttId?: string
// Identificatore usato per cross-day DnD

onSegmentDrag?: (
  rowIdx: number,
  segIdx: number,
  changes: { dep_time?: string; arr_time?: string },
) => void
// Mouse drag intra-Gantt (move / resize)

onTimelineClick?: (hour: number, minute: number, rowIdx: number) => void
// Click su asse vuoto

onCrossDragStart?: (payload: CrossDragPayload) => void
onCrossDrop?: (
  payload: CrossDragPayload,
  targetGanttId: string,
  dropTime: { hour: number; minute: number; rowIdx: number },
) => void
onCrossRemove?: (segIdx: number, withLinkedCvs: boolean) => void
// Cross-day DnD HTML5

onAction?: (
  action: GanttAction,
  seg: GanttSegment,
  rowIdx: number,
  segIdx: number,
) => void
// Click su icona action bar

hideActionBar?: boolean
autoFit?: boolean
snapMinutes?: number  // default 5
dragThresholdPx?: number  // default 4
```

Se trovi un'API più pulita, proponila — sono aperto.

---

## Vincoli duri (non negoziabili)

1. **Zero regressione** per consumer attuali:
   - `AutoBuilderGantt.tsx` non passa nessuna callback di interazione → deve continuare a renderizzare esattamente come oggi
   - `/gantt-preview` stessa cosa
2. **Estetica intatta**: niente card arrotondate, niente sfondi pieni sui blocchi condotta, asse 24h continuo, densità massima. Tutto quello che dice `GANTT-GUIDE.md` §01 Filosofia.
3. **Tipografia e colori**: usa i token esistenti in `tokens.ts`. Aggiungi nuovi token solo per stati interazione (selected ring, drag ghost, drop slot indicator, action bar bg).
4. **Nessuna dipendenza nuova** nel bundle React (niente librerie DnD tipo react-dnd): continuiamo con mouse events + HTML5 DnD nativo come fa PdcGanttV2.
5. **Accessibilità keyboard**: `Esc` deseleziona, `Tab` naviga fra segmenti, `Enter` apre drawer. Oggi PdcGanttV2 ha solo `Esc` — è ok come minimo, ma se hai idee per il resto, proponi.

---

## Vincoli soft (preferenze ma non bloccanti)

- Il drag in-progress deve avere un **ghost** discreto (non il blocco pieno trasparente stile OS drag, troppo cafone): idealmente un bordo tratteggiato colorato che segue il cursore sull'asse
- Il drop slot su un Gantt target durante cross-drag dovrebbe evidenziare una linea verticale sull'asse alla posizione oraria di drop (tipo text-cursor ma verticale, che cammina con il mouse)
- Durante resize, mostra l'orario corrente in un tooltip sticky vicino al mouse (così il dispatcher vede `06:05` mentre trascina invece di dover rilasciare per scoprire)
- Action bar: anima la comparsa (fade + scale da 0.95 a 1 in 120ms) — non essenziale ma rende il click più reattivo

---

## Cosa NON fare

- **Non aggiungere nuove capacità non elencate qui**. Niente rubber-band selection multipla, niente copy/paste con shortcut, niente undo/redo in-componente. Se servono, arrivano in un round successivo.
- **Non toccare il rendering dei segmenti cond/dh/refez/scomp/sleep** (quello di `GanttSheet` oggi). Aggiungi solo: stato selected (overlay), action bar (overlay SVG), ghost drag (overlay), drop slot indicator (overlay). Tutto **sopra** il rendering esistente.
- **Non spostare file** (`GanttSheet.tsx` resta dove sta). Se servono helper interni, inlinali o crea `frontend/src/components/gantt/interactions.ts` ma non refactorare la struttura.

---

## Edge case da coprire nell'handoff

1. **Blocco ai margini dell'asse**: drag vs clamp (non finisci prima di `hStart` o dopo `hEnd`).
2. **Blocco overnight che attraversa le 24:00**: drag deve gestire correttamente il wrap (oggi PdcGanttV2 gestisce con `minRel` encoded).
3. **Gantt con 0 righe** (giornata S.COMP intera): il rendering oggi è placeholder "Disponibile · riposo a casa"; l'action bar non si apre, il timeline click può o no essere attivo (decidi tu).
4. **Zoom fuori scala**: se il consumer passa range `[5, 29]` (24h overnight) + `autoFit=true` viene un conflitto. Proponi gerarchia: `autoFit` vince, `range` usato solo come fallback se 0 segmenti.
5. **Action bar clampata ai bordi**: il centro del blocco a `x=15` del viewBox → la bar larga 300px non può andare a `-135`; deve spostarsi a `x=5` e la freccia sotto della bar deve ri-centrare sul blocco (non sulla bar).
6. **Drag oltre lo scroll orizzontale**: se il Gantt è dentro `overflow-x-auto` e trascino oltre il bordo visibile, serve auto-scroll del container. Oggi PdcGanttV2 non lo fa bene — se puoi risolvere, ottimo.
7. **Selezione + drag**: single-click selezione, ma se l'utente fa mouse-down-drag (no click finale), il blocco non deve finire in selected. Threshold 4px decide chi vince (drag o click).
8. **Context menu destro vs action bar**: convivono? Oggi sì (right-click = context menu legacy; click = action bar). Valuta se unificare.

---

## Cosa mi aspetto da te

### A. Handoff markdown

Salva `docs/HANDOFF-gantt-v3-interactions.md` con:

1. **API estesa completa** (props + callback + tipi) con esempio TypeScript pronto da copiare
2. **Specifica interazioni dettagliata** — per ciascuna delle 8 capacità:
   - Trigger (mouse/keyboard)
   - Cursor states
   - Feedback visivo durante l'interazione (ghost, slot, tooltip sticky)
   - Snap/threshold/clamp
   - Callback signature
   - Edge case
3. **Architettura interna suggerita** — hook React, state machine, event listener delegation (globali vs scoped al container), ecc.
4. **Action bar spec**: layout SVG, token di stile, animazione, posizionamento clamp, hover states, separatori, raggruppamento semantico
5. **Cross-day DnD spec**: MIME payload structure, sequence diagram (source → target → removal), drop-slot indicator sull'asse target
6. **Tabella di copertura** `PdcGanttV2 → GanttSheet esteso`: ogni feature PdcGanttV2 ha una riga che dice "coperta da API X" o "non migrata (motivo)". Uso questa tabella per verificare che la migrazione sia 1:1 completa.
7. **Checklist di merge** (come in v3): cose da verificare post-implementazione (es. "Builder: drag un treno verso un'altra giornata impilata, verifica che il treno scompare dalla source e appare nella target con orario corretto").

### B. Hi-fi mockup o HTML reference

Almeno 4 stati illustrati:

1. **Stato idle** (nessuna interazione) — identico a oggi, per mostrare "niente cambia di default"
2. **Stato selected + action bar aperta** — un blocco treno con action bar sopra e ring kinetic
3. **Drag in progress** — ghost + slot indicator sull'asse + tooltip orario sticky
4. **Cross-day drag** — 2 Gantt impilati, il source evidenzia il blocco che si sta togliendo, il target mostra lo slot di arrivo

Se produci anche un esempio HTML autocontenuto (come `screen-gantt-v3.html` per la v3) lo apprezzo tantissimo — mi serve per validare le interazioni senza scrivere codice React.

### C. Nota in `GANTT-GUIDE.md`

Se l'handoff introduce nuovi pattern o anti-pattern, aggiungi una
sezione "Interazioni" alla guida consolidata. La guida è la source of
truth permanente e va tenuta viva.

---

## Appunti utente grezzi

> "PdcGanttV2 funziona bene ma è 1400 righe, AutoBuilderGantt è
> migrato su GanttSheet ed è 180. Voglio che tutti e 3 i consumer
> vadano su GanttSheet e PdcGanttV2 sparisca. Ma per farlo GanttSheet
> deve sapere tutto quello che sa PdcGanttV2 in termini di interazioni.
> Non voglio regressioni: se oggi il dispatcher può trascinare un treno
> da una giornata all'altra, domani deve poter fare la stessa cosa
> esattamente uguale o meglio."

> "Action bar con 8 icone l'ho provata bene, funziona. Tienila uguale
> come ordine e spacing, cambia solo se l'hai capita meglio di me."

> "Se hai idee per migliorare l'UX del drag (es. auto-scroll, ghost più
> chiaro, slot indicator sull'asse) prendile — però deve funzionare
> prima uguale a oggi."

---

## Nota operativa per Claude Design

Questo prompt è il seguito di `docs/HANDOFF-gantt-v3.md` (base
visiva, merged) e `docs/GANTT-GUIDE.md` (filosofia consolidata).
NON sto chiedendo un redesign estetico — chiedo il **layer
interazioni** sopra la resa esistente, che ho scelto di mantenere.

Priorità ordine deliverable:
1. Handoff markdown completo (senza questo non parte implementazione)
2. HTML reference funzionante (senza questo non valido interazioni)
3. Hi-fi mockup (nice to have, l'HTML già serve da proxy visivo)
