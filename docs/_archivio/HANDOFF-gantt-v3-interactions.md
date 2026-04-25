# HANDOFF · Gantt v3 · Interactions layer

> Risposta di Claude Design al prompt
> `docs/PROMPT-claude-design-gantt-interactions.md`.
> Estratto da `docs/claude-design-bundles/gantt-interactions/`
> (`screen-gantt-interactions.html` + `gantt-ix.css`) — sorgente
> autoritativo in caso di ambiguità.

## Obiettivo

Aggiungere un **layer interazioni opt-in** sopra `GanttSheet`
mantenendolo "sola resa" di default. Tutte le nuove capacità sono
attivate solo se il consumer passa le callback corrispondenti.

**Invariante chiave**: `AutoBuilderGantt`, `/gantt-preview` e ogni
altro consumer che non passa callback di interazione **non vede
nessuna differenza**. Zero-regressione garantita.

**Copertura dichiarata**: 100% delle 10 feature interattive di
`PdcGanttV2`, più 3 miglioramenti (auto-scroll drag, sticky time
tooltip durante resize, keyboard nav Tab/Enter).

---

## API estesa · Props

Aggiunte a `GanttSheetProps` (tutte opzionali):

```ts
// Identity — obbligatorio solo per cross-day DnD
ganttId?: string

// Drag temporale intra-Gantt (move + resize start + resize end)
onSegmentDrag?: (
  rowIdx: number,
  segIdx: number,
  changes: { dep_time?: string; arr_time?: string },
) => void

// Click su area asse vuota (add-block in Builder)
onTimelineClick?: (
  hour: number,
  minute: number,
  rowIdx: number,
) => void

// Cross-day HTML5 DnD — 3 callback coordinate
onCrossDragStart?: (p: CrossDragPayload) => void
onCrossDrop?: (
  p: CrossDragPayload,
  targetGanttId: string,
  dropTime: { hour: number; minute: number; rowIdx: number },
) => void
onCrossRemove?: (
  segIdx: number,
  withLinkedCvs: boolean,
) => void

// Action bar 8-icone su blocco selected
onAction?: (
  action: GanttAction,
  seg: GanttSegment,
  rowIdx: number,
  segIdx: number,
) => void

// Tuning
hideActionBar?: boolean    // default false — se true: click apre onSegmentClick invece di mostrare action bar
autoFit?: boolean          // default false — se true: range calcolato da segments + padding
snapMinutes?: number       // default 5
dragThresholdPx?: number   // default 4
```

## API estesa · Nuovi tipi

Da aggiungere a `frontend/src/components/gantt/types.ts`:

```ts
export type GanttAction =
  | "edit"
  | "move"
  | "duplicate"
  | "link"
  | "warn"
  | "detail"
  | "history"
  | "delete"

export interface CrossDragPayload {
  ganttId: string
  seg: GanttSegment
  rowIdx: number
  segIdx: number
  // Per CVp/CVa linkati al treno padrone (seguono durante drag)
  linkedCvp?: GanttSegment
  linkedCva?: GanttSegment
}

export const CROSS_DAY_MIME = "application/x-colazione-block"
```

## API estesa · Nuovi token

Da aggiungere a `frontend/src/components/gantt/tokens.ts` in
`GANTT_COLORS`:

```ts
SELECTED_RING:     "#22C55E"                   // kinetic green
SELECTED_SHADOW:   "0 3px 8px rgba(34,197,94,.35)"
DRAG_GHOST_BORDER: "#0062CC"                   // brand, dashed
DROP_SLOT:         "#0062CC"                   // riga verticale sull'asse target
DROP_SLOT_HALO:    "rgb(0 98 204 / 0.12)"      // alone del drop-slot
ACTION_BAR_BG:     "var(--surface-container-lowest)"
STICKY_TIME_BG:    "#0A1322"                   // tooltip dark durante drag/resize
```

---

## I 4 stati visivi

### S1 · idle (default — comportamento attuale)

- `ganttId=undefined`, nessuna callback interattiva passata
- Cursor `default` ovunque
- Tooltip nativo SVG `<title>` (già presente oggi)
- **Zero overlay, zero handle, zero cursor particolari**
- Consumer d'esempio: `AutoBuilderGantt`, `/gantt-preview`

### S2 · selected + action bar 8-icone

**Trigger**: single-click su un segmento.

**Resa**:
- Ring verde kinetic (`SELECTED_RING`) 2px attorno al segmento, `rx=2`
- Drop-shadow verde (`SELECTED_SHADOW`) sul segmento
- "Kinetic dot" — cerchio 4px `#22C55E` all'angolo destro-alto del
  segmento, con halo 7px `opacity=0.25`
- Action bar HTML overlay (posizionata assoluta sopra il blocco)

**Action bar spec**:
- **Ordine esatto** (invariato da PdcGanttV2): `✎ ↔ ⧉ | 🔗 ⚠ | ↗ ⧗ | ×`
- **3 separatori verticali** dopo icone 3, 5, 7 — grouping semantico:
  - Gruppo 1 (edit/move/duplicate) — operazioni sul blocco
  - Gruppo 2 (link/warn) — relazioni esterne
  - Gruppo 3 (detail/history) — lettura
  - Singola (delete) — distruttivo
- Icone `.warn` in ambra `#B45309`, hover bg `rgb(234 88 12 / 0.10)`
- Icona `.danger` in rosso `#B91C1C`, hover bg `rgb(220 38 38 / 0.10)`
- Dimensioni button: 28×28px, font-mono 13px
- Background bar: `ACTION_BAR_BG`, box-shadow doppia
  `0 8px 24px rgba(11,13,16,0.16), 0 2px 4px rgba(11,13,16,0.08)`
- Freccia-puntatore `::after` 8×8 ruotata 45°, posizionata via
  CSS var `--arrow-x` (default 50%, clamp con variabile custom)
- **Animazione in**: `gixActionBarIn` 140ms
  `cubic-bezier(0.18, 0.9, 0.32, 1.15)` — fade + scale 0.94→1

**Clamp ai bordi**:
- Se il centro del blocco è a `x<150`, la bar si sposta a sinistra
  ma la freccia `::after` resta centrata sul blocco via `--arrow-x`
- Stessa logica a destra se `barX + barW > totalW - 5`

**Dismiss**:
- Click fuori dal SVG → deseleziona + fade-out
- Tasto `Esc` → idem
- `hideActionBar=true` → overlay disabilitato completamente;
  single-click emette `onSegmentClick` direttamente (modo PdcPage
  "lettura con-edit" di oggi)

### S3 · drag in progress

**Trigger**: mouse-down + movimento ≥ `dragThresholdPx` (default 4px).

**Resa**:
- Cursor `grabbing` sul segmento sorgente e sul documento
- **Ghost back-reference** (posizione originale): rettangolo
  `fill=rgba(11,106,168,0.08)` + bordo tratteggiato `DRAG_GHOST_BORDER`
  `stroke-dasharray="3 2"` `opacity=0.5`
- **Rettangolo in drag** (posizione corrente): bordo tratteggiato
  `DRAG_GHOST_BORDER` `stroke-width=1.2` `stroke-dasharray="4 3"`,
  drop-shadow `0 4px 10px rgba(0,98,204,0.30)`
- Label orari alle estremità in brand `#0062CC` (non muted)
- **Slot indicator verticale sull'asse**:
  - Div assoluto, width 2px, `background: var(--brand)`,
    `box-shadow: 0 0 0 3px rgb(0 98 204 / 0.12)`
  - `::before` con attr `data-time` → pill orario 10px bold
    `background: var(--brand) color: #fff` in alto (-20px)
- **Sticky time tooltip** vicino al cursore:
  - Posizione assoluta, segue il mouse
  - bg `STICKY_TIME_BG` (#0A1322), testo bianco, font-mono 11px
    bold, padding 4px 8px
  - Mostra `HH:MM → HH:MM` aggiornato real-time durante resize/drag
  - Triangle `::before` 6px ruotato 45°
- Altri segmenti della row non trascinati: `opacity=0.4-0.5` per
  evidenziare il target del drag

**Snap**: ogni 5 minuti (override via `snapMinutes`).

**Linkage CVp/CVa**:
- Se si trascina un treno che ha `cvp` agganciato, la callback
  emette aggiornamenti coordinati su treno + CVp (stesso dep_time)
  e/o treno + CVa (stesso arr_time)
- Un CVp/CVa isolato non si muove da solo: il drag sul suo punto
  viene reindirizzato al treno padrone (look up nella row)

### S4 · cross-day HTML5 DnD

**Trigger**: drag che esce dal bounding box del Gantt sorgente.

**Resa source**:
- Il segmento in uscita va a `opacity=0.35` (mantiene la posizione
  ma segnala "in rimozione")
- Label sotto il segmento: `"↗ uscita in <targetGanttId>"` in
  rosso `#DC2626` font-mono 10px bold (appare al drag-over
  target conferm)

**Resa target**:
- Stage `.gix-stage.is-target` — background leggermente più freddo
  (`#F8F9FB`)
- Drop-slot indicator identico a S3 (riga verticale brand + pill
  orario)
- Ghost preview del blocco in arrivo: rettangolo bordo tratteggiato
  `stroke=DROP_SLOT stroke-width=1.5 stroke-dasharray="4 3"` alla
  posizione oraria di drop, con label `"preview <train_id>"` sotto

**Flow atomico** (sequence):
1. Source `onCrossDragStart(payload)` → payload contiene `{ganttId,
   seg, rowIdx, segIdx, linkedCvp?, linkedCva?}`
2. Browser drag: serializzazione JSON del payload sul MIME
   `CROSS_DAY_MIME`. Fallback `text/plain` per browser strict.
3. Target accetta drop (`dragover` + `preventDefault` se il MIME è
   quello giusto); chiama `onCrossDrop(payload, targetGanttId, {hour, minute, rowIdx})`
4. Se `dataTransfer.dropEffect === "move"`, source chiama
   `onCrossRemove(segIdx, withLinkedCvs)` (con `withLinkedCvs=true`
   se il seg rimosso è un treno con CVp/CVa adiacenti)

**Drop rejection**:
- Se `payload.ganttId === target.ganttId` → drop ignorato (il
  drag intra-Gantt gestisce già move temporale)

---

## Coverage 1:1 · PdcGanttV2 → GanttSheet esteso

| Feature PdcGanttV2 | API GanttSheet esteso | Status | Note |
|---|---|---|---|
| Drag move intra-Gantt (threshold 4px, snap 5min) | `onSegmentDrag(rowIdx, segIdx, {dep_time, arr_time})` | 1:1 | Event listener globali `mousemove`/`mouseup` scoped al drag corrente |
| Resize start (handle 6px sx) | `onSegmentDrag` con solo `dep_time` modificato | 1:1 | Vincolo `dep < arr - snap` |
| Resize end (handle 6px dx) | `onSegmentDrag` con solo `arr_time` modificato | 1:1 | Idem |
| Gruppo CVp/CVa legato al treno | Interno (flag `cvp`/`cva` già in `GanttSegment`) | 1:1 | Drag padre emette callback consecutive: treno + CVp + CVa |
| Cross-day drag (HTML5 DnD) | `onCrossDragStart` / `onCrossDrop` / `onCrossRemove` | 1:1 | MIME `application/x-colazione-block`, payload serializzato |
| Click su timeline vuota (add) | `onTimelineClick(hour, minute, rowIdx)` | 1:1 | Cursor `crosshair` in area asse scoperta |
| Hover tooltip custom | Interno (overlay DOM via wrapperRef) | 1:1 | Se non fornito, fallback a `<title>` SVG |
| Action bar 8 icone (selected) | `onAction` + `hideActionBar` | 1:1 | Ordine icone + 3 separatori + clamp bordi preservati |
| Esc / click fuori → deseleziona | Interno (listener doc, unmount-safe) | 1:1 | — |
| autoFit range visivo | `autoFit: boolean` | 1:1 | Fallback a `range` se 0 segmenti |
| Debug logging | `debug: boolean` (già presente) | 1:1 | — |
| Auto-scroll durante drag oltre bordo | Interno (RAF + scroll container detection) | Migliorato | Non funzionava bene in v2; nuovo RAF loop in `gantt/interactions.ts` |
| Sticky time tooltip durante resize | Interno | Nuovo | Non presente in v2, aggiunto come richiesto in §vincoli soft |
| Keyboard nav (Tab/Enter) | `tabindex` + `onKeyDown` | Nuovo | Minimo: Tab naviga segmenti, Enter apre drawer (= `onSegmentClick`) |

---

## Architettura di implementazione suggerita

Non dichiarata esplicitamente da Claude Design — di seguito la mia
deduzione dall'HTML/CSS + prompt:

### Nuovo file `frontend/src/components/gantt/interactions.ts`

Helper hook / utility che **non** vive dentro `GanttSheet.tsx` per
non gonfiarlo. Esponendo:

```ts
export function useGanttInteractions(opts: {
  svgRef: RefObject<SVGSVGElement>
  containerRef: RefObject<HTMLDivElement>
  rows: GanttRow[]
  xFor: (min: number) => number
  minFor: (x: number) => number  // inverso di xFor
  snapMinutes: number
  dragThresholdPx: number
  ganttId?: string
  onSegmentDrag?: (...)
  onCrossDragStart?: (...)
  onCrossDrop?: (...)
  onCrossRemove?: (...)
  onTimelineClick?: (...)
  onAction?: (...)
  hideActionBar: boolean
}): {
  // State
  selectedSegIdx: number | null
  dragState: DragState | null
  // Handlers per componenti
  bindSegmentProps: (rowIdx, segIdx) => { onMouseDown, onClick, onKeyDown, tabIndex, ... }
  bindTimelineProps: () => { onClick, onMouseMove, ... }
  // Overlay render helpers
  renderActionBar: () => ReactNode | null
  renderDragGhost: () => ReactNode | null
  renderSlotIndicator: () => ReactNode | null
  renderStickyTime: () => ReactNode | null
}
```

### Modifiche a `GanttSheet.tsx`

1. Accetta le nuove props (opt-in)
2. Chiama `useGanttInteractions(...)` se almeno una callback passata
3. Nel JSX: avvolge ogni segment in `<g data-row={i} data-seg={si}>`
   con `{...bindSegmentProps(i, si)}`
4. Aggiunge un overlay HTML fratello dell'SVG (`<div
   className="gantt-overlays">`) per: action bar, sticky time tooltip
5. Aggiunge overlay SVG interno (prima dei segmenti) per: ghost,
   drop-slot, resize handles

### Modifiche a `tokens.ts`

Aggiungere solo i nuovi token elencati sopra. Nulla da rimuovere.

### Modifiche a `types.ts`

Aggiungere `GanttAction`, `CrossDragPayload`, `CROSS_DAY_MIME`
export. Estendere `GanttSheetProps` con le nuove props opt-in.

### Riscrittura di `PdcGanttV2.tsx`

Una volta che `GanttSheet` supporta tutto, `PdcGanttV2` diventa un
wrapper fine (~150 righe vs 1400 di oggi):

1. Mappa `PdcBlock[]` → `GanttSegment[]` (merge CVp/CVa nei treni)
2. Passa tutte le callback legacy (`onBlocksChange`,
   `onCrossDayDragStart`, ecc.) alle nuove callback di `GanttSheet`
3. Un mapping bidirezionale `blockIdx ↔ segIdx` per convertire gli
   indici nei callback (perché CVp/CVa sono merge di 2 blocchi in 1
   segment nel modello `GanttSegment`)

### Migrazione dei 3 consumer

Da fare in un **commit unico** per evitare stati ibridi:

- `PdcPage.tsx:471`
- `PdcBuilderPage.tsx:801`
- `PdcDepotPage.tsx:545`

Non cambiano l'interfaccia: continuano a passare
`onBlocksChange` / `onCrossDay*` / `onAction` a `PdcGanttV2` wrapper.
Test manuale su tutte e 3 le pagine prima del commit.

---

## Edge case coperti dalla spec

Elencati dal prompt `§edge case` e tutti affrontati dalla soluzione
Claude Design:

1. **Blocco ai margini** → clamp su `hStart`/`hEnd` durante drag
2. **Overnight wrap (>24:00)** → `minRel` encoded, conversione
   `minutesRelToHhmm` preservata
3. **Gantt vuoto S.COMP** → rendering placeholder "Disponibile",
   action bar disabilitata, `onTimelineClick` può rimanere attivo
4. **autoFit vs range**: `autoFit` vince, `range` usato come
   fallback se 0 segmenti
5. **Action bar clampata** → CSS var `--arrow-x`
6. **Drag oltre viewport** → RAF auto-scroll del container
   (miglioria vs v2)
7. **Threshold 4px** click-vs-drag → selected solo se
   `didDragRef=false` al mouseup
8. **Context menu destro + action bar** → coesistono (right-click
   legacy → context menu; single-click → action bar)

---

## Checklist di merge (estratta + integrata)

- [ ] `types.ts` estesi con `GanttAction`, `CrossDragPayload`,
      `CROSS_DAY_MIME`, nuove props su `GanttSheetProps`
- [ ] `tokens.ts` ha i 6 nuovi token
- [ ] `interactions.ts` creato con `useGanttInteractions`
- [ ] `GanttSheet.tsx` accetta le nuove props e delega a
      `useGanttInteractions`
- [ ] `AutoBuilderGantt` e `/gantt-preview` invariati (verifica
      visiva — devono renderizzare pixel-identici a oggi)
- [ ] `PdcGanttV2.tsx` riscritto come wrapper (~150 righe)
- [ ] 3 consumer (`PdcPage`, `PdcBuilderPage`, `PdcDepotPage`)
      migrati in un unico commit
- [ ] Test manuale: drag + resize su PdcPage
- [ ] Test manuale: cross-day drag su PdcBuilderPage (5 giornate
      impilate)
- [ ] Test manuale: cross-day drag su PdcDepotPage (più turni)
- [ ] Test manuale: action bar 8 icone su tutti e 3 i consumer
- [ ] Test keyboard: Tab naviga, Enter apre drawer, Esc deseleziona
- [ ] Aggiornare `docs/HANDOFF-gantt-v3.md` §10 (checkbox
      PdcGanttV2 completato)
- [ ] Aggiornare `docs/GANTT-GUIDE.md` con sezione "Interazioni"

---

## File sorgente di riferimento

- `docs/claude-design-bundles/gantt-interactions/screen-gantt-interactions.html`
  — mockup HTML dei 4 stati + API completa in `<pre>` + coverage table
- `docs/claude-design-bundles/gantt-interactions/gantt-ix.css` —
  CSS autoritativo per action bar, slot indicator, sticky time,
  kinetic ring, ghost
- `docs/claude-design-bundles/gantt-interactions/BUNDLE-README.md` —
  README del bundle Claude Design originale

In caso di ambiguità tra questo handoff e i sorgenti CSS/HTML del
bundle, **vincono i sorgenti**.
