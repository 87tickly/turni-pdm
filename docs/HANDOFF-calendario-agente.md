# Handoff · Calendario agente

Piano implementativo per la nuova route `/calendario-agente`. Rispetta i token `@theme` in `frontend/src/index.css` + la No-Line rule del DS Kinetic Conductor.

## 1. File da toccare

| File | Azione |
|---|---|
| `frontend/src/components/Sidebar.tsx` | Rimuovi voci `Cerca treni` + `Calendario`. Aggiungi `Calendario agente` (`CalendarRange` icon). Riordina: Dashboard · Turni Materiale · Turni PdC · Genera da materiale · **Calendario agente** · Nuovo turno · Import · Impostazioni. Opz: 2 sotto-divisori tonal (`Dati` / `Operazioni`). |
| `frontend/src/App.tsx` | Rimuovi `<Route path="treni">` + `<Route path="calendario">`. Aggiungi `<Route path="calendario-agente" element={<CalendarAgentePage />} />`. |
| `frontend/src/pages/TrainSearchPage.tsx` | **Elimina**. Usa import + exports grep prima. |
| `frontend/src/pages/CalendarPage.tsx` | **Elimina** dopo migrare qualsiasi util ancora usata. |
| `frontend/src/pages/CalendarAgentePage.tsx` | **Nuovo**. |
| `frontend/src/lib/api.ts` | Aggiungi `getAgendaGrid`, tipi `AgentGridRow`, `AgentGridCell`. |

## 2. Struttura componenti

```
CalendarAgentePage.tsx
├── <PageHeader title="Calendario agente" subtitle="Chi lavora quando · 28 giorni"/>
├── <AgendaFilters />                 // mese | deposito | matricole | stato | search
├── <AgendaKpis />                    // 3 mini-kpi: coperture, scoperti, FR candidate
├── <AgendaLegend />                  // work/rest/FR/S.COMP/uncov/leave
├── <AgendaGrid>                      // css-grid 180px + repeat(28, 72px)
│   ├── <AgendaGrid.Corner />
│   ├── <AgendaGrid.Header days={Day[]} />
│   └── rows.map(row => (
│         <AgendaGrid.PdcRow pdc={row.pdc} cells={row.cells} onCellClick={...}/>
│       ))
└── <AgendaDayDrawer cell={selected}/>  // Radix Dialog right (440px) — riusa TrainDetailDrawer shell
```

## 3. Tipi (estendi `frontend/src/lib/api.ts`)

Riusa `DayVariant` esistente (`variant_type`, `is_fr`, `is_scomp`, `condotta_min`).

```ts
export type AgentCellState =
  | "work"      // giornata assegnata regolare
  | "rest"      // R — riposo settimanale
  | "fr"        // variant.is_fr === true
  | "scomp"     // variant.is_scomp === true
  | "uncov"     // scoperto · nessuna assegnazione per day_type richiesto
  | "leave"     // ferie/permesso
  | "locked";   // giornata NON chiudibile (vincolo normativo)

export interface AgentGridCell {
  date: string;                  // ISO "2026-04-23"
  state: AgentCellState;
  span?: number;                 // per leave multi-giorno (default 1)
  variant?: DayVariant;          // popolato quando state === work|fr|scomp
  turno_code?: string;           // es. "AROR 01"
  prestazione_min?: number;
  lock_reason?: string;          // state === locked
}

export interface AgentGridRow {
  pdc_id: number;
  pdc_code: string;              // es. "AROR_C"
  display_name: string;          // "Moretti A."
  matricola: string;             // "7832"
  deposito: string;
  totals: { work: number; rest: number; uncov: number; hours_min: number };
  cells: AgentGridCell[];        // length = range_days (28)
}

export interface AgentGridResponse {
  range_start: string;
  range_days: number;            // 28 default
  deposito?: string;
  rows: AgentGridRow[];
}

export async function getAgendaGrid(params: {
  start: string; days?: number; deposito?: string; query?: string;
}) {
  return api.get<AgentGridResponse>("/calendario-agente", params);
}
```

## 4. Tokens nuovi (solo se mancanti in `index.css`)

Già presenti via Kinetic handoff: surface-container-*, brand, dot, ghost, mono. Da aggiungere:

```css
@theme {
  /* FR notturno gradient */
  --gradient-fr: linear-gradient(135deg, #3B1773 0%, #5B21B6 100%);
  /* Scoperto hatch */
  --uncov-hatch: repeating-linear-gradient(
    -45deg,
    rgb(220 38 38 / 0.14) 0, rgb(220 38 38 / 0.14) 4px,
    rgb(220 38 38 / 0.06) 4px, rgb(220 38 38 / 0.06) 8px
  );
  /* Ferie hatch */
  --leave-hatch: repeating-linear-gradient(
    -45deg,
    var(--color-surface-container) 0, var(--color-surface-container) 4px,
    var(--color-surface-container-lowest) 4px, var(--color-surface-container-lowest) 8px
  );
}
```

## 5. Layout grid CSS (pattern)

```css
.agenda-grid {
  display: grid;
  grid-template-columns: 180px repeat(var(--days, 28), 72px);
}
.agenda-cell {
  min-height: 52px;
  box-shadow: inset 1px 0 0 var(--color-ghost), inset 0 1px 0 var(--color-ghost);
}
/* Sticky left name column + sticky top header */
.agenda-pdc-cell { position: sticky; left: 0; z-index: 1; }
.agenda-header   { position: sticky; top: 0;  z-index: 2; }
.agenda-corner   { position: sticky; top: 0; left: 0; z-index: 3; }
```

Scroll orizzontale libero; verticale contenuto dalla card. Evita `scrollIntoView`.

## 6. Edge case da gestire

| Caso | Comportamento atteso |
|---|---|
| **Giornata NON chiudibile** (vincoli normativi RFI: riposo 11h, max settimanale 48h) | `state: "locked"` → cella in `--color-surface-container-high` con icona 🔒 a 10px · tooltip con `lock_reason` · click apre drawer con la regola violata. NON cliccabile per assegnazione. |
| **FR candidate** | `variant.is_fr === true` → gradient viola `--gradient-fr`, testo bianco. Nel drawer: badge `FR · notturno` + durata condotta. Filtro "solo FR candidate" nell'header. |
| **S.COMP** | `variant.is_scomp === true` → bg `rgba(2,132,199,0.10)` testo `#075985`. Mostra `scomp_duration_min` se > 0. |
| **Scoperto multi-giorno** | Consecutivi `state: "uncov"` → il backend può raggrupparli con `span: N` su un'unica cella (pattern visibile nella mockup: "SCOPERTO · 2 gg"). Visivo: hatch rosso. |
| **Ferie / Permesso** | `state: "leave"` con `span` opzionale (es. 7gg) → cella unica che occupa `grid-column: span N`, hatch diagonale neutrale. |
| **Matricola senza assegnazioni nel range** | Riga comunque presente, tutte celle `rest` o `uncov` · `pdc-sub` mostra ultima assegnazione nota. |
| **Oggi** | `dcell.today` → numero giorno come cerchio brand. |

## 7. Interazioni

- **Click cella** → apre `AgendaDayDrawer` con dettaglio `DayVariant` (riusa pattern di `TrainDetailDrawer`).
- **Double-click cella** → modalità inline re-assign (combobox con turni validi per il `day_type` di quel PdC).
- **Drag cella** → sposta assegnazione a data adiacente (validazione lato backend: verifica `locked` + vincoli settimanali).
- **Shift+click** range → multi-select per azioni bulk.
- **`⌘K`** → rimane globale, nessuna interferenza.

## 8. Backend — nuovo endpoint

`GET /calendario-agente?start=2026-04-06&days=28&deposito=MIL`
→ `AgentGridResponse`. Il server risolve:
- PdC del deposito con assegnazioni nel range
- Espansione delle `DayVariant` sul calendario reale (map day_type → date)
- Rilevamento scoperti (giornate attese ma non assegnate) e `locked` per vincoli di riposo

## 9. Checklist di merge

- [ ] `Sidebar.tsx` mostra 8 voci nel nuovo ordine, Cerca treni e Calendario rimosse.
- [ ] Route `/treni` e `/calendario` rimosse, redirect 404 → `/`.
- [ ] `/calendario-agente` rende la griglia 180 + 28×72 con sticky corner.
- [ ] Celle `rest`, `work`, `fr`, `scomp`, `uncov`, `leave`, `locked` hanno stile distintivo (nessun `border: 1px solid` nuovo).
- [ ] Terminologia IT: `FR · notturno`, `S.COMP`, `SCOPERTO`, `FERIE`, `PERM`.
- [ ] `⌘K` funziona da `/calendario-agente`.
- [ ] `TrainSearchPage.tsx` + `CalendarPage.tsx` eliminati e nessun import residuo (grep).

*— ARTURO· Kinetic Conductor · v1.1 · calendar-agente*
