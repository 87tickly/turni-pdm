# Guida Gantt ARTURO · v3

> Documento di riferimento consolidato per creare, modificare o estendere
> un componente Gantt nel progetto. Sintesi delle sessioni 23/04/2026
> (design handoff #2 Claude Design + cablaggio AutoBuilderGantt).
>
> **Sorgenti originali** (non duplicare, referenziare):
> - `docs/HANDOFF-gantt-v3.md` — handoff Claude Design completo
> - `frontend/src/components/gantt/` — implementazione reale
> - `docs/PROMPT-claude-design-gantt.md` — prompt che ha generato il design

---

## 1. Filosofia

Il Gantt ARTURO v3 è la **falsa riga del foglio turno PDF Trenord**:
leggibile come uno stampato, interattivo come un'app moderna.

Principi non negoziabili:

1. **Niente nero puro** — inchiostro `var(--color-on-surface-strong)`
   (#0A1322). Le barre condotta usano **blu petrolio** `#0B6AA8`, mai
   `#000`.
2. **Niente card arrotondate** sui segmenti (`border-radius > 2px`
   vietato). Look "stampato", non "widget colorato".
3. **Niente fill pieno brand** su segmenti `cond` in palette `hybrid`.
4. **Asse orario continuo 0-24h** (o esteso per overnight/FR), mai
   croppato al solo range del turno.
5. **Densità > decorazione**. Barre 20px default, mai blocchi alti
   card-style.

---

## 2. Quando usare il Gantt v3

Ogni visualizzazione di una **giornata PdC** (o multiple giornate
impilate per varianti calendario):

- Output auto-builder (`AutoBuilderGantt` — migrato 23/04/2026)
- Dettaglio turno PdC (`PdcGanttV2` — **ancora da migrare**)
- Preview dimostrativa (`/gantt-preview`)
- Futuri componenti (es. drawer con mini-Gantt giornata)

**Non usarlo** per:
- Calendario multi-giorno stile Excel (quella è `CalendarAgentePage`)
- Agenda settimana dispatcher (quella è `ShiftsPage` lista tabellare)

---

## 3. Architettura

```
frontend/src/components/gantt/
├── types.ts        — tipi pubblici (GanttSegment, GanttRow, etc.)
├── tokens.ts       — costanti pixel + colori + helpers time
└── GanttSheet.tsx  — componente SVG monolitico (~520 righe)
```

L'handoff originale prevedeva 7 file (`GanttAxis`, `GanttRow`,
`GanttBlock`, `VariantLabel`, `MetricsColumn`, `GanttSheet`, `tokens`)
— abbiamo scelto l'implementazione monolitica per React:
**un componente = una source of truth**, niente context/props drilling
per dimensioni/stato.

### Pattern di utilizzo

Ogni Gantt concreto è un **wrapper leggero** che:
1. Trasforma i dati dal formato API nel formato `GanttRow[]` + `metrics`
2. Calcola `range: [hStart, hEnd]`
3. Delega al `GanttSheet`

Esempio minimale (vedi `AutoBuilderGantt.tsx`):

```tsx
import { GanttSheet } from "@/components/gantt/GanttSheet"
import type { GanttRow } from "@/components/gantt/types"

export function MyGantt({ segments, presentationTime, endTime }) {
  const rows: GanttRow[] = [{
    label: "",
    segments: segments.map(s => ({
      kind: s.is_deadhead ? "dh" : "cond",
      train_id: s.train_id,
      from_station: s.from_station,
      to_station: s.to_station,
      dep_time: s.dep_time,
      arr_time: s.arr_time,
    })),
  }]
  return (
    <GanttSheet
      rows={rows}
      dayHead={{ num: 0, pres: presentationTime, end: endTime }}
      metrics={{ lav: "—", cct: "—", km: 0, not: "no", rip: "—" }}
      range={[6, 22]}
    />
  )
}
```

---

## 4. Tipi pubblici

### `GanttSegment`

```ts
type GanttSegmentKind =
  | "cond"    // condotta (produttivo) — blu petrolio
  | "dh"      // deadhead / vettura — tratteggiata
  | "refez"   // refezione in stazione — ambra sottile
  | "scomp"   // S.COMP disponibilita' — grigio tenue
  | "sleep"   // dormita FR fuori residenza — viola

interface GanttSegment {
  kind: GanttSegmentKind
  train_id: string          // "10208" · "(11555)" · "REFEZ VOGH" · "DORMITA · ALE"
  from_station: string
  to_station: string
  dep_time: string          // "HH:MM"
  arr_time: string          // "HH:MM"
  preheat?: boolean         // bullet ● prima del numero + striscia verticale blu
  suspect_reason?: string   // vettura sospetta (ciclo) — rosso + ⚠
  cvp?: boolean             // prefix "CVp " + striscia verticale ambra
  cva?: boolean             // prefix "CVa " + striscia verticale viola
}
```

**Convenzioni label** (dal PDF Trenord):
- Numero treno come da ministeriale: `"10208"`
- Vettura fra parentesi: `"(11555)"` oppure `"(11555 AL)"`
- Refezione con prefisso fisso: `"REFEZ VOGH"` (stazione abbreviata)
- Dormita: `"DORMITA · ALESSANDRIA"` (middle dot `·`)
- S.COMP: `"S.COMP MILANO C.LE"` (tutta maiuscola)

### `GanttRow`

```ts
interface GanttRow {
  label: string                         // "LMXGV" | "S" | "D" | "F" | "SD" | "G6 · LMXGV"
  segments: GanttSegment[]
  metrics_override?: Partial<GanttMetrics>  // override colonna destra
  warn?: boolean                        // pallino rosso a destra
  meta?: string                         // override header sinistra
}
```

Una giornata semplice → **1 row**. Una giornata con varianti calendario
impilate (es. LMXGV + S + D della stessa giornata) → **N row** con
stesso asse.

### `GanttMetrics`

```ts
interface GanttMetrics {
  lav: string     // "7h31"
  cct: string     // "03h03"
  km: number      // 153
  not: "sì" | "no"
  rip: string     // "14h55"
  fr?: boolean
}
```

Mostrate nella colonna destra fissa. Ogni row può avere il proprio
`metrics_override` per le varianti con numeri diversi.

### `GanttDayHead`

```ts
interface GanttDayHead {
  num: number       // numero giornata, es. 8
  pres: string      // presentazione "07:18"
  end: string       // fine "14:49"
  variant?: string  // opzionale, etichetta variante principale
}
```

Mostrato nella colonna sinistra (solo prima row se `meta` non è
fornito nelle row successive).

---

## 5. Props `GanttSheet`

```tsx
<GanttSheet
  rows={rows}                           // GanttRow[]
  dayHead={dayHead}
  metrics={metrics}
  range={[hStart, hEnd]}                // supporta overnight es. [18, 33]
  barHeight?={20}                        // 16-28, default 20
  labels?="auto"                         // "auto" | "vertical" | "horizontal"
  minutes?="hhmm"                        // "hhmm" | "duration" | "off"
  palette?="hybrid"                      // "hybrid" | "mono" | "brand"
  grid30?={false}                        // true = tick ogni 30 min
  suspect?={true}                        // highlight vetture sospette
  onSegmentClick?={(seg, rowIdx) => openDrawer(seg)}
  onSegmentContextMenu?={(seg, rowIdx, ev) => openMenu(ev)}
/>
```

---

## 6. Rendering per kind

Ogni kind ha un sub-render dedicato in `GanttSheet.tsx`. Riassunto:

### `cond` — Condotta

- Rectangle pieno `var(--gantt-bar-cond)` (#0B6AA8 blu petrolio)
- Label sopra: numero treno (bianco se barra piena, ink se tratteggiata)
- Sotto barra: `HH:MM` dep (sinistra) + `HH:MM` arr (destra), solo se
  barra > 40px; altrimenti solo dep al centro
- Con `preheat: true`: bullet ● a sinistra (r=2.8, ink) + striscia
  verticale blu brand sulla partenza + label "● Preriscaldo HH:MM"
  sopra la barra

### `dh` — Vettura / Deadhead

- Rectangle `var(--gantt-bar-dh-bg)` (#E9EEF5 fill leggero)
- Border tratteggiato `var(--gantt-bar-dh-line)` (#4E6A85, stroke-dasharray
  "3 2.5", width 1)
- Label sopra: numero treno in ink (non bianco)
- Se `suspect_reason` non vuoto E prop `suspect=true`:
  - fill rosso tenue `rgba(220,38,38,0.06)`
  - border rosso `var(--gantt-suspect)` stroke-width 1.2
  - icona ⚠ sopra la barra (offset -46, textAnchor middle)
- Sotto barra: idem cond

### `refez` — Refezione

- Rectangle **sottile** (altezza = 50% della bar-h) centrato verticalmente
- Fill `var(--gantt-refez)` (#D97706 ambra)
- Label `REFEZ <stazione>` sopra barra (verticale se < 50px,
  orizzontale centrata sopra)
- Nessun minuti sotto (non serve, `from == to`)

### `scomp` — S.COMP disponibilità

- Fascia piena alta (bar-h + 4) con fill tenue `rgba(108,116,136,0.12)`
- Linea orizzontale dash (stroke-dasharray "2 3") al centro barra
- Label centrale grande MAIUSCOLA ink-60, letter-spacing 0.06em

### `sleep` — Dormita FR

- Rectangle con fill `var(--gantt-sleep-bg)` (rgba 91/33/182/0.10)
  + border `var(--gantt-sleep)` (#5B21B6 viola, width 1)
- Label centrale `🌙 <train_id>` in viola ink
- Tooltip: `🌙 Dormita · <stazione> · HH:MM → HH:MM (giorno dopo)`

---

## 7. Flag speciali

### `preheat`

Aggiunge all'inizio del segmento condotta:
1. Bullet ● (cerchio pieno r=2.8) dentro la banda label
2. Striscia verticale 4px sopra/sotto la barra in `var(--gantt-preheat)`
   (#0062CC brand)
3. Label accessorio sopra la banda label: `"● Preriscaldo HH:MM"` in blu

Semantica backend: il treno richiede tempi maggiorati (80' di ACCp in
dic-feb, vedi Step 3/4 builder v4).

### `cvp` / `cva`

Aggiunge al segmento:
1. Prefisso nel label treno: `"CVp "` o `"CVa "`
2. Striscia verticale colorata (ambra #B45309 per CVp, viola #6B21A8
   per CVa)
3. Label accessorio: `"CVp HH:MM"` / `"CVa HH:MM"` sopra la banda

Semantica: Cambio Volante in Produzione (stesso PdC cambia mezzo e
continua a guidare) / Cambio Volante in Arrivo (un altro PdC prende
in consegna il mezzo). Vedi Step 5 builder v4 (`cv_registry.py`).

### `suspect_reason`

Segmento vettura sospetto (cerchio A→B + B→A consecutivi senza
produttivo in mezzo, rilevato da `cycle_optimizer.py` commit 68a2b6a).

Rendering:
- Fill rosso tenue + border rosso tratteggiato
- Icona ⚠ sopra la barra
- Tooltip: "⚠ `<suspect_reason>`"

Il backend rimuove i cicli silenziosamente (Step 10 fix). Flag
proposto per Step futuro: esporre `suspect_reason` in API in modo che
il dispatcher possa vedere/confermare prima della rimozione.

---

## 8. Design tokens

Tutti definiti in `frontend/src/index.css` sotto `:root`, referenziati
anche in `frontend/src/components/gantt/tokens.ts` per JS consumption.

### Dimensioni

| Token | Valore | Scope |
|---|---|---|
| `--gantt-px-per-hour` | 46px | larghezza 1 ora |
| `--gantt-bar-h` | 20px | altezza barra default |
| `--gantt-col-left` | 108px | label giornata sinistra |
| `--gantt-col-right` | 168px | colonna metriche destra |
| `--gantt-label-band` | 62px | banda sopra barra (label verticali + accessori) |
| `--gantt-minutes-band` | 24px | banda sotto barra (HH:MM) |

### Colori

| Token | Valore | Uso |
|---|---|---|
| `--gantt-bar-cond` | `#0B6AA8` | Condotta (blu petrolio, no brand pieno) |
| `--gantt-bar-cond-ink` | `#084F7F` | Border dark condotta |
| `--gantt-bar-dh-line` | `#4E6A85` | Contorno vettura |
| `--gantt-bar-dh-bg` | `#E9EEF5` | Fill vettura |
| `--gantt-refez` | `#D97706` | Refezione (ambra) |
| `--gantt-refez-ink` | `#B45309` | Label refez |
| `--gantt-scomp` | `#6C7488` | S.COMP grigio tenue |
| `--gantt-sleep` | `#5B21B6` | Dormita FR viola |
| `--gantt-sleep-bg` | `rgb(91 33 182 / 0.10)` | Fill dormita |
| `--gantt-fr` | `#7C3AED` | Accent FR |
| `--gantt-cvp` | `#B45309` | Accessorio CVp (ambra scura) |
| `--gantt-cva` | `#6B21A8` | Accessorio CVa (viola scuro) |
| `--gantt-preheat` | `#0062CC` | Bullet/striscia preriscaldo (brand) |
| `--gantt-suspect` | `#DC2626` | Vetture sospette rosse |
| `--gantt-ink-60` / `--gantt-ink-40` | `#3E4C67` / `#6C7488` | Ink derivati per testo muted |

**Mai usare**: `black`, `#000`, `#000000`, `#0D0D10`. L'inchiostro
ufficiale è `var(--color-on-surface-strong)` (#0A1322).

### Palette alternative (future)

`palette` prop supporta tre modalità:
- **`hybrid`** (default): blu petrolio condotta, vettura tenue, refez ambra
- **`mono`**: tutto in ink (#0A1322) — ottimizzato per export PDF/stampa
- **`brand`**: condotta brand pieno (#0062CC) — look più "app", solo UI

Oggi solo `hybrid` implementato. Le altre due sono supportate nei tipi
ma il rendering usa sempre hybrid.

---

## 9. Asse orario

### Range

`range: [hStart, hEnd]` in ore intere. Supporta:

- **Giornata diurna** classica: `[6, 22]` → 06:00 → 22:00
- **Overnight**: `[18, 33]` → 18:00 → 09:00 del giorno dopo
- **FR dormita**: `[15, 28]` → 15:00 → 04:00 del giorno dopo (cattura
  dormita + ripartenza mattutina)
- **Sempre 24h** (come PDF Trenord): `[3, 27]` → 03:00 → 03:00 del
  giorno dopo

Convenzione PDF Trenord: asse **sempre 24h continuo** (3→3). Se il
turno dura solo 4 ore, le altre 20 ore restano vuote ma l'asse è
leggibile come "giornata completa".

### Gestione overnight segmenti

Se `arr_time < dep_time` (es. dep 22:00, arr 02:00), il componente
aggiunge automaticamente 1440 minuti all'arrivo. Se `dep_time < hStart*60`
(segmento mattutino del giorno dopo), aggiunge 1440 anche a dep.

Attenzione: funziona solo se `range[1] > 24`. Se il turno attraversa
mezzanotte ma `range` è `[0, 24]`, il segmento viene troncato.

### Tick

- Numeri ora sopra la prima row (es. "03", "04", …, "27" → renderizzati
  come "03" perché `h % 24`)
- Tick verticali (5px sopra/sotto) su ogni row ad ogni ora intera
- Con `grid30: true`: tick mezzora piccoli (3px) in ink-40

---

## 10. Label treno

Prop `labels`:

- **`"auto"`** (default): vertical se barra `w < 60px`, horizontal altrimenti
- **`"vertical"`**: sempre vertical (rotazione -90°)
- **`"horizontal"`**: sempre horizontal

### Rendering vertical

```tsx
<g transform="translate(cx, barTop - 6) rotate(-90)">
  <text x={0} y={-5} textAnchor="start" dominantBaseline="central">
    {train_id}
  </text>
  <text x={0} y={6} ...>{to_station}</text>
</g>
```

Risultato: label ruotata 90° antioraria, numero treno in alto,
stazione destinazione in basso (come nel PDF).

### Rendering horizontal

```tsx
<text x={x1 + 4} y={yBarTop - 6}>
  {train_id}
  <tspan fontWeight={500}> · {to_station}</tspan>
</text>
```

Numero treno + middle-dot + stazione destinazione, 6px sopra la barra.

### Troncamento

Label lungo 14+ caratteri → troncamento con `...`, tooltip completo
su hover via `<title>` in hit-rect.

---

## 11. Minuti sotto barra

Prop `minutes`:

- **`"hhmm"`** (default): `HH:MM` dep (sinistra) + `HH:MM` arr (destra).
  Se barra `w < 40px`: solo dep al centro.
- **`"duration"`**: durata in minuti al centro (es. "56")
- **`"off"`**: nessun numero

Scomp e sleep **non hanno mai** minuti sotto (la durata è evidente dal
range della fascia).

---

## 12. Colonna metriche destra

Posizione fissa a destra dell'asse: `COL_RIGHT = 168px`.

5 colonne equally-spaced:

```
Lav    Cct    Km    Not   Rip
7h31   03h03  153   no    14h55
```

Header ink-60 uppercase 9.5px. Valori ink strong, font-mono 11px,
textAnchor middle.

Se `row.warn === true`: pallino rosso 4px a destra della colonna,
stessa y della metrica.

Per row con `metrics_override`, i valori override prevalgono su
`metrics` default (merge shallow).

---

## 13. Colonna sinistra

Posizione fissa: `COL_LEFT = 108px`.

Contenuto:
- **Label variante** (`row.label`): top, font display bold 13px,
  color ink, letter-spacing -0.01em. Es: `"LMXGV"`, `"S"`, `"D"`, `"SD"`.
- **Meta giornata**: sotto la label, font-mono 10.5px ink-60.
  Default (solo prima row): `<num>  [<pres>]  [<end>]` es
  `"8  [07:18]  [14:49]"`. Override per row con `row.meta`.

---

## 14. Multi-variante impilata

Pattern **LMXGV + S + D** (PDF pag 388): tre versioni della stessa
giornata con orari leggermente diversi, impilate verticalmente con
asse orario condiviso.

```tsx
<GanttSheet
  range={[3, 27]}
  rows={[
    { label: "LMXGV", segments: [...] },
    { label: "S",     segments: [...], metrics_override: {...} },
    { label: "D",     segments: [...], metrics_override: {...}, warn: true },
  ]}
  dayHead={{ num: 8, pres: "07:18", end: "14:49" }}
  metrics={{ lav: "7h31", cct: "03h03", km: 153, not: "no", rip: "14h55" }}
/>
```

Ogni row occupa `rowH = LABEL_BAND + BAR_H + MINUTES_BAND + ROW_GAP`
verticali. Asse orario disegnato su ognuna per allineamento visivo.

---

## 15. Edge case

| Caso | Comportamento |
|---|---|
| `arr_time < dep_time` | +1440 a arr (overnight entro la stessa giornata) |
| `dep_time < range[0]*60 - 60` | +1440 a dep (segmento del giorno dopo) |
| Barra < 2px | Clamp a 2px. Label forzata vertical, tooltip è l'unico canale info |
| Refez in stazione intermedia | `from == to == stazione`. Barra sottile 50% bar-h |
| FR dormita overnight | `range` esteso (es. `[15, 28]`). Segmento sleep copre fine giornata N → ripartenza N+1 |
| S.COMP giornata intera | Una sola `GanttSegment` kind=scomp da `pres` a `end`. Metriche: Cct 00h00, Km 0 |
| Preriscaldo fuori stagione | `preheat: true` ma data non in dic-feb → bullet mostrato (design), ma ACCp resta 40' (builder) |
| CVp/CVa su stesso PdC | Comunque prefix e striscia. Il registro `cv_ledger` tiene il tempo |
| Vettura sospetta | Solo se `suspect_reason` non vuoto E prop `suspect=true` (default) |
| Warn row | `row.warn === true` → pallino rosso accanto metriche |
| Overnight senza range extended | Il segmento viene **troncato** a `range[1]*60`. ERRORE di configurazione: estendere `range` |

---

## 16. Interazioni

### Hover tooltip

Implementato via SVG `<title>` dentro il hit-rect. Testo dinamico per
kind:

- **cond/dh**: `"<preheat?>"` + `"[vettura] "` (se dh) +
  `"<train> · <from> <dep> → <to> <arr>"` + `" · ⚠ <suspect_reason>"` (se sospetto)
- **refez**: `"REFEZ · <station> · <dep> → <arr>"`
- **scomp**: `"S.COMP · <train> · <dep> → <arr>"`
- **sleep**: `"🌙 Dormita · <train> · <dep> → <arr> (giorno dopo)"`

### Click

Prop `onSegmentClick(seg, rowIdx)`. Tipicamente apre un drawer dettaglio
(es. `TrainDetailDrawer`).

### Right-click (context menu)

Prop `onSegmentContextMenu(seg, rowIdx, ev)`. `ev.preventDefault()` è
già gestito dentro `GanttSheet`. Il caller deve solo aprire il menu.

### Drag & drop (NON implementato)

Il mockup Claude Design aveva drag orizzontale (sposta orario) +
verticale (cambia variante) con snap agli orari reali del treno.
**Non portato in produzione** perché richiede:
- Endpoint backend per validare cambi orario
- Vincoli normativi su riposi tra turni
- Design dedicato per conflitti

Residuo in `docs/HANDOFF-gantt-v3.md` §10.

---

## 17. Come aggiungere un nuovo wrapper

1. **Crea il componente** `frontend/src/components/MyGantt.tsx`:
   ```tsx
   import { GanttSheet } from "@/components/gantt/GanttSheet"
   import type { GanttRow } from "@/components/gantt/types"

   export function MyGantt({ data }) {
     const rows: GanttRow[] = transformData(data)
     return <GanttSheet rows={rows} ... />
   }
   ```

2. **Mapping dati**: trasforma i tuoi segmenti al formato
   `GanttSegment`. Riferimento completo: `AutoBuilderGantt.tsx`.

3. **Props invariate**: se stai migrando un Gantt esistente, mantieni
   l'API pubblica del componente. Solo il render interno cambia.

4. **Wrapper visivo**: avvolgi `GanttSheet` in un div con
   `overflow-x-auto` + background surface-container-low + padding.

5. **Click handler**: se vuoi drawer, passa `onSegmentClick`.

6. **Test**: scrivi almeno un test di smoke (render con un segmento
   fittizio) per ogni kind usato.

---

## 18. Anti-patterns (NON fare)

- ❌ `background: #000` / `#000000` — usa `var(--color-on-surface-strong)`
- ❌ `border-radius > 2px` sui segmenti — look stampato, no card
- ❌ `background-color: var(--color-brand)` su `kind="cond"` in
  palette hybrid — usa `--gantt-bar-cond`
- ❌ Position divs assoluti per simulare l'asse — usa SVG `<line>`/
  `<text>`, altrimenti tick e label non si allineano pixel-perfect
- ❌ Label orizzontali forzate sotto 60px di barra — illeggibili,
  sovrapposte
- ❌ Colors inline non tokenizzati — usa sempre `var(--gantt-*)`
- ❌ Missing `<title>` nel hit-rect — senza tooltip l'interazione
  è rotta

---

## 19. Checklist prima di PR

Quando modifichi o crei un nuovo Gantt:

- [ ] Palette `hybrid` rispettata (no nero, no brand pieno su cond)
- [ ] Nessun `border-radius > 2px` sui segmenti
- [ ] Overnight testato (segmento che attraversa mezzanotte)
- [ ] Range esteso per FR/sleep se il turno lo prevede
- [ ] Label auto-vertical sotto 60px
- [ ] Tooltip via `<title>` in ogni hit-rect
- [ ] Scomp renderizza senza barra "piena" (è una fascia)
- [ ] Refez con `from == to`, label sopra barra
- [ ] Preheat con bullet ● + striscia blu
- [ ] CVp/CVa con prefix label + striscia colore
- [ ] Vetture sospette con `suspect_reason` rosse + ⚠
- [ ] Metriche colonna destra con warn dot se `row.warn`
- [ ] TypeScript strict pass (import type per GanttSegment etc.)
- [ ] Build `npm run build` senza warning/error
- [ ] `docs/HANDOFF-gantt-v3.md` aggiornato se il contratto cambia
- [ ] Commit + LIVE-COLAZIONE.md entry per tracciabilità

---

## 20. Stato componenti Gantt

| Componente | Stato | Note |
|---|---|---|
| `frontend/src/components/gantt/GanttSheet.tsx` | ✅ DONE | Base SVG monolitica |
| `frontend/src/components/gantt/types.ts` | ✅ DONE | Tipi pubblici |
| `frontend/src/components/gantt/tokens.ts` | ✅ DONE | Costanti pixel + colori |
| `frontend/src/components/AutoBuilderGantt.tsx` | ✅ MIGRATO | Wrapper su GanttSheet (commit 2aa617b) |
| `frontend/src/components/PdcGanttV2.tsx` | ⏳ DA MIGRARE | Più complesso (drawer + context menu + toggle lista) |
| `frontend/src/pages/GanttPreviewPage.tsx` | ✅ DONE | 4 varianti demo (A/B/C/D) |

Per futuro: quando si migra `PdcGanttV2`, preservare:
- Click segmento → apre `TrainDetailDrawer` esistente
- Right-click → context menu Elimina/Sostituisci/Duplica
- Toggle "📊 Gantt / 📋 Lista" → sostituire emoji con icone `BarChart3` / `List` lucide-react
- Modalità lista: usare le 5 classi `.gblock.{train,accp,vuota,refez,vettura}` già in `docs/HANDOFF-claude-design.md` §01

---

## 21. Riferimenti

- `docs/HANDOFF-gantt-v3.md` — handoff Claude Design originale (checklist merge, contratto dati, tipi TS, euristiche backend)
- `docs/PROMPT-claude-design-gantt.md` — prompt che ha generato il design
- `docs/HANDOFF-claude-design.md` — design system Kinetic Conductor (tokens globali)
- `frontend/src/components/gantt/` — implementazione reale
- `frontend/src/pages/GanttPreviewPage.tsx` — esempi live in `/gantt-preview`
- `LIVE-COLAZIONE.md` — entry 2026-04-23 per storia dei commit Gantt v3

---

*ARTURO· · Kinetic Conductor · Gantt v3 guide*
