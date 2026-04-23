# Handoff · Gantt v3 — falsa riga del PDF Trenord

Redesign del Gantt giornata PdC ispirato al foglio turno stampato ufficiale, mantenendo interattività moderna (hover, click, drawer, menu contestuale). Si applica a **`AutoBuilderGantt.tsx`** (primario) e **`PdcGanttV2.tsx`** (uniformato allo stesso componente base).

---

## 1. File da toccare

| File | Azione |
|---|---|
| `frontend/src/components/gantt/` | **Nuova cartella**. Contiene il componente base condiviso. |
| `frontend/src/components/gantt/GanttSheet.tsx` | **Nuovo**. Wrapper con asse orario + metriche. |
| `frontend/src/components/gantt/GanttAxis.tsx` | **Nuovo**. Asse 0–24 con tick ogni ora (opz. 30 min). |
| `frontend/src/components/gantt/GanttRow.tsx` | **Nuovo**. Una riga = una variante (LMXGV / S / D / F / SD). |
| `frontend/src/components/gantt/GanttBlock.tsx` | **Nuovo**. Blocco singolo: condotta / vettura / refez / scomp / sleep. |
| `frontend/src/components/gantt/VariantLabel.tsx` | **Nuovo**. Etichetta sinistra (num giornata + orari). |
| `frontend/src/components/gantt/MetricsColumn.tsx` | **Nuovo**. Colonna destra `Lav Cct Km Not Rip`. |
| `frontend/src/components/gantt/tokens.ts` | **Nuovo**. Costanti: `PX_PER_HOUR`, `BAR_HEIGHT`, colori per kind. |
| `frontend/src/components/AutoBuilderGantt.tsx` | **Riscrittura render**. API props invariate. Usa `GanttSheet`. |
| `frontend/src/components/PdcGanttV2.tsx` | **Riscrittura render**. Usa `GanttSheet` con `rows` multiple per varianti. |

> **Vincolo**: le props pubbliche di `AutoBuilderGantt` e `PdcGanttV2` non cambiano. Cambia solo la resa visiva interna.

---

## 2. Design tokens (da aggiungere a `frontend/src/index.css`)

```css
@theme {
  /* Gantt v3 — dimensioni */
  --gantt-px-per-hour: 74px;
  --gantt-bar-h: 20px;
  --gantt-col-left: 96px;      /* label giornata */
  --gantt-col-right: 172px;    /* metriche */
  --gantt-label-band: 58px;    /* spazio sopra barra per label verticali */

  /* Gantt v3 — colori per kind (palette "ibrido", default) */
  --gantt-cond: #0D0D10;              /* condotta: nero inchiostro */
  --gantt-dh-fill: var(--color-surface-container-high);
  --gantt-dh-stroke: var(--color-on-surface-muted);
  --gantt-refez: #F59E0B;
  --gantt-refez-ink: #B45309;
  --gantt-scomp-ink: var(--color-on-surface-muted);
  --gantt-sleep: #5B21B6;
  --gantt-sleep-bg: rgb(91 33 182 / 0.12);
  --gantt-suspect: #DC2626;
  --gantt-preheat: #0D0D10;

  /* Palette alternativa "mono" — solo per print / export */
  --gantt-mono-ink: #0D0D10;
}
```

La palette si cambia con un prop `palette?: "hybrid" | "mono" | "brand"` sul componente `GanttSheet`. Default: `"hybrid"`.

---

## 3. Struttura componenti

```
<GanttSheet
  palette="hybrid"               // "mono" | "brand" | "hybrid"
  rows={[...]}                    // array di righe (1 o N varianti)
  dayHead={{ num, pres, end }}    // header giornata (sinistra)
  metrics={{ lav, cct, km, not, rip, fr? }}  // default per tutte le righe
  range={[6, 15]}                // [hStart, hEnd]  — supporta overnight (es. [18, 33])
  minutes="hhmm"                  // "hhmm" | "duration" | "off"
  labels="auto"                   // "auto" | "vertical" | "horizontal"
  grid30={false}                  // griglia ogni 30 min
  suspect={true}                  // highlight vetture sospette
  onSegmentClick={(seg, rowIdx) => openDrawer(seg)}
  onSegmentContextMenu={(seg, rowIdx, event) => openCtxMenu(...)}
/>
  ├── <GanttAxis hours rows grid30/>
  ├── rows.map(row => (
  │     <GanttRow>
  │       ├── <VariantLabel label pres end/>
  │       ├── row.segments.map(seg => <GanttBlock kind={seg.kind} ...onClick/>)
  │       └── <MetricsColumn values={row.metricsOverride || metrics}/>
  │     </GanttRow>
  │ ))
```

Il rendering interno è **SVG**, non `div` posizionati — garantisce ticks hairline allineati, rotazione label verticali perfetta, export PDF pulito.

---

## 4. Tipi TypeScript

Estendi `frontend/src/lib/api.ts`:

```ts
export type GanttSegmentKind =
  | "cond"     // condotta (produttivo)
  | "dh"       // deadhead / vettura
  | "refez"    // refezione in stazione
  | "scomp"    // S.COMP (giornata in disponibilità)
  | "sleep";   // dormita fuori residenza (FR)

export interface GanttSegment {
  kind: GanttSegmentKind;
  train_id: string;          // "10208" · "(11555)" · "REFEZ VOGH" · "DORMITA · ALESSANDRIA"
  from_station: string;      // "ML"
  to_station: string;        // "MRT" (stazione di destinazione, mostrata sotto la label)
  dep_time: string;          // "06:52"
  arr_time: string;          // "07:26"
  preheat?: boolean;         // ● preriscaldo prima della label
  suspect_reason?: string;   // NUOVO · se set, rende la vettura "sospetta"
  cvp?: boolean;             // CVp prefix nell'etichetta
  cva?: boolean;             // CVa prefix nell'etichetta
}

export interface GanttRow {
  label: string;                         // "LMXGV" · "S" · "D" · "F" · "SD"
  segments: GanttSegment[];
  metrics_override?: Partial<GanttMetrics>;  // se la variante ha valori diversi
  warn?: boolean;                        // pallino rosso a destra
  meta?: string;                         // override "[07:18] → [14:49]" per la riga
}

export interface GanttMetrics {
  lav: string;    // "7h31"
  cct: string;    // "03h03"
  km: number;     // 153
  not: "sì"|"no"; // notturno
  rip: string;    // "14h55"
  fr?: boolean;   // badge "FR · notturno"
}
```

---

## 5. Esempio dati → rendering

### Input (giornata con 3 varianti impilate, PDF pag 388)

```json
{
  "dayHead": { "num": 8, "pres": "07:18", "end": "14:49" },
  "range": [7, 16],
  "metrics": { "lav": "7h31", "cct": "03h03", "km": 153, "not": "no", "rip": "14h55" },
  "rows": [
    {
      "label": "LMXGV",
      "segments": [
        { "kind": "cond",  "train_id": "10208", "from_station": "ML",  "to_station": "MRT", "dep_time": "07:34", "arr_time": "08:08" },
        { "kind": "cond",  "train_id": "10221", "from_station": "MRT", "to_station": "ML",  "dep_time": "08:15", "arr_time": "08:42", "preheat": true },
        { "kind": "cond",  "train_id": "10042", "from_station": "ML",  "to_station": "VO",  "dep_time": "10:10", "arr_time": "11:05" },
        { "kind": "refez", "train_id": "REFEZ VOGH", "from_station": "VO", "to_station": "VO", "dep_time": "11:15", "arr_time": "11:55" },
        { "kind": "cond",  "train_id": "12588", "from_station": "VO",  "to_station": "AL",  "dep_time": "12:12", "arr_time": "12:56" },
        { "kind": "dh",    "train_id": "(2588 AL)", "from_station": "AL", "to_station": "ML", "dep_time": "13:30", "arr_time": "14:45" }
      ]
    },
    { "label": "S", "segments": [ /* stessa struttura, orari leggermente diversi */ ] },
    {
      "label": "D",
      "warn": true,
      "metrics_override": { "lav": "7h50", "cct": "02h02", "km": 102, "rip": "14h31" },
      "segments": [
        /* ... */
        { "kind": "dh", "train_id": "(10047)", "from_station": "VO",  "to_station": "MRT", "dep_time": "11:12", "arr_time": "11:48", "suspect_reason": "inversione direzione entro 5 min" },
        { "kind": "dh", "train_id": "(11367)", "from_station": "MRT", "to_station": "VO",  "dep_time": "11:52", "arr_time": "12:25", "suspect_reason": "inversione direzione entro 5 min" }
      ]
    }
  ]
}
```

### Rendering atteso

- 3 righe Gantt impilate verticalmente, stesso asse orario 7–16
- Etichette variante `LMXGV · S · D` a sinistra, font display grassetto
- Numero giornata `8` + `[07:18]  [14:49]` solo sulla prima riga (o per ogni riga se override)
- I due segmenti vettura `(10047)` e `(11367)` della variante D sono **rossi punteggiati con ⚠** perché hanno `suspect_reason`
- Colonna metriche a destra allineata per tutte e 3 le righe, con pallino warn rosso accanto alla riga D
- Label treno: verticali per barre < 60 px (auto), orizzontali per barre larghe tipo `10208 · MRT`
- Sotto ogni barra: `HH:MM` inizio (allineato sinistra) + `HH:MM` fine (allineato destra)

---

## 6. Esempio codice — render kind per kind (riferimento, non impl.)

```tsx
// GanttBlock.tsx — estratto
function GanttBlock({ seg, x1, x2, yBarTop, barH, palette, labels, minutes, onClick, onContextMenu }: Props) {
  const w = Math.max(x2 - x1, 2);

  // Click + right-click arrivano da qui
  const hit = (
    <rect className="seg-hit"
      x={x1} y={yBarTop - 16} width={w} height={barH + 32}
      onClick={e => onClick(seg, e)}
      onContextMenu={e => { e.preventDefault(); onContextMenu(seg, e); }}
    />
  );

  switch (seg.kind) {
    case "cond":
      return (<>
        <rect className="gv-cond" x={x1} y={yBarTop} width={w} height={barH} />
        <Label seg={seg} x1={x1} x2={x2} yBarTop={yBarTop} labels={labels} w={w} />
        {minutes !== "off" && <Minutes seg={seg} x1={x1} x2={x2} yBarBot={yBarTop + barH} mode={minutes} />}
        {hit}
      </>);

    case "dh": {
      const isSuspect = !!seg.suspect_reason;
      return (<>
        <rect className={cn("gv-dh", isSuspect && "gv-suspect")} x={x1} y={yBarTop} width={w} height={barH} />
        <rect className={cn("gv-dh-stroke", isSuspect && "gv-dh-stroke-suspect")}
              x={x1 + 0.5} y={yBarTop + 0.5} width={w - 1} height={barH - 1}
              fill="none" strokeDasharray="3 2.5" />
        <Label seg={seg} x1={x1} x2={x2} yBarTop={yBarTop} labels={labels} w={w} />
        {isSuspect && <text className="seg-warn" x={x1 + w/2} y={yBarTop - 44} textAnchor="middle">⚠</text>}
        {hit}
      </>);
    }

    case "refez":
      // Barra sottile gialla + label orizzontale "REFEZ VO" sopra
      return (<>
        <rect className="gv-refez" x={x1} y={yBarTop + barH*0.2} width={w} height={barH*0.6} />
        <text className="seg-refez-label" x={(x1+x2)/2} y={yBarTop - 6} textAnchor="middle">{seg.train_id}</text>
        {hit}
      </>);

    case "scomp":
      // Fascia punteggiata piena larga + label centrale maiuscola
      return (<>
        <rect className="gv-scomp" x={x1} y={yBarTop - 2} width={w} height={barH + 4} />
        <text className="seg-scomp-label" x={(x1+x2)/2} y={yBarTop + barH/2 + 4} textAnchor="middle">{seg.train_id}</text>
        {hit}
      </>);

    case "sleep":
      // FR: rettangolo viola tenue con bordo viola + label "DORMITA · <stazione>"
      return (<>
        <rect className="gv-sleep" x={x1} y={yBarTop} width={w} height={barH} />
        <text className="seg-sleep-label" x={(x1+x2)/2} y={yBarTop + barH/2 + 4} textAnchor="middle">{seg.train_id}</text>
        {hit}
      </>);
  }
}
```

---

## 7. Edge case da gestire

| Caso | Comportamento |
|---|---|
| **Overnight** (fine > 24:00, es. turno 22:00 → 02:00) | `range = [22, 26]` — il componente tratta le ore come minuti continui. Se `arr_time < dep_time` il blocco aggiunge 1440 ai minuti arr. |
| **FR · dormita fuori residenza** | Un segmento `kind: "sleep"` copre l'intervallo tra ultimo treno e primo treno del giorno dopo. `range` va esteso (es. `[18, 33]` = 18:00 → 09:00 giorno dopo). |
| **Refez in stazione intermedia** | `kind: "refez"`, `from = to = stazione`. Label `"REFEZ <stazione>"`. Barra sottile 60% altezza per distinguerla. |
| **Preriscaldo** | `preheat: true` → bullet `●` prima del numero treno nella label. Colore bullet = stesso del segmento. |
| **CVp / CVa** | Se `cvp` o `cva`, prefissa la label con `CVp ` o `CVa `. |
| **S.COMP giornata intera** | Una sola `GanttSegment` `kind: "scomp"` da `pres` a `end`. Metriche: `Cct 00h00`, `Km 0`. |
| **Label verticale troppo lunga** | Troncamento con `...` dopo 14 char; tooltip completo su hover. |
| **Barra < 2 px** (segmenti di transizione < 2 min) | Clamp a 2 px, label verticale forzata, tooltip primario canale di info. |
| **Vettura sospetta** | `suspect_reason` non vuoto → pattern rosso punteggiato + icona ⚠ sopra. Tooltip mostra `suspect_reason`. |
| **Warning variante** | Se `row.warn === true` → pallino rosso 4 px a destra della colonna metriche, stessa y-mid della barra. |

---

## 8. Interazioni (da preservare)

- **Hover su barra** → tooltip con `train · from dep → to arr` + `suspect_reason` se presente.
- **Click su barra** → apre `TrainDetailDrawer` (già esistente).
- **Right-click** → menu contestuale con `Elimina · Sostituisci · Duplica` (già esistente in `AutoBuilderGantt`).
- **Warning row** (WARN_DATA_MISMATCH, WEEKLY_HOURS_HIGH) → riga sotto il Gantt, font 11px, sfondo tonal, icona colorata per severità. Non invasiva.

---

## 9. Backend — campi da aggiungere (opzionali ma raccomandati)

```python
# src/database/models.py · TrainSegment
class TrainSegment(Base):
    # ... esistenti
    suspect_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    cvp: Mapped[bool] = mapped_column(Boolean, default=False)
    cva: Mapped[bool] = mapped_column(Boolean, default=False)
```

**Euristica `suspect_reason`** (esempio, da rifinire con il dispatcher):
```python
def detect_suspect_deadheads(segments: list[TrainSegment]) -> None:
    for i in range(len(segments) - 1):
        a, b = segments[i], segments[i + 1]
        if not (a.is_deadhead and b.is_deadhead):
            continue
        # Inversione: A va da X→Y, B va da Y→X, gap < 30 min
        same_pivot = a.to_station == b.from_station
        reverse = a.from_station == b.to_station
        gap_min = (time_to_min(b.dep_time) - time_to_min(a.arr_time)) % 1440
        if same_pivot and reverse and gap_min < 30:
            a.suspect_reason = f"inversione direzione entro {gap_min} min"
            b.suspect_reason = f"inversione direzione entro {gap_min} min"
```

---

## 10. Checklist di merge

- [ ] Nuova cartella `frontend/src/components/gantt/` con i 7 file elencati.
- [ ] Tokens aggiunti a `index.css` sotto `@theme`.
- [ ] `AutoBuilderGantt.tsx` riscritto per usare `<GanttSheet>`. Props invariate.
- [ ] `PdcGanttV2.tsx` riscritto per usare `<GanttSheet>` con `rows` multiple (una per variante calendario).
- [ ] Export PDF: `GanttSheet` accetta `palette="mono"` → nero puro per stampa.
- [ ] `TrainDetailDrawer` si apre al click su segmento (regression test).
- [ ] Menu contestuale funziona sul right-click (regression test).
- [ ] Overnight reso correttamente per turni che attraversano mezzanotte.
- [ ] Barre < 2 px renderizzate come clamp a 2 px con tooltip ancora cliccabile.
- [ ] Label `LMXGV · S · D · F · SD` font display grassetto 14 px, allineate a sinistra della riga corrispondente.
- [ ] Campo `suspect_reason` esposto nell'API `GET /auto-builder/suggest` e `GET /pdc-days/:id`.
- [ ] Nessun `border-radius > 2px` sui segmenti (look "stampato", no card arrotondate).
- [ ] Nessun `background-color` pieno brand sui segmenti `cond` in palette `"hybrid"` (solo nero inchiostro).

---

*ARTURO· · Kinetic Conductor · Gantt v3 · falsa riga PDF Trenord*
