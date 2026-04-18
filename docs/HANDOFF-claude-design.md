# Handoff · ARTURO· Hi-fi → Claude Code

> Generato da **Claude Design** (claude.ai/design, Anthropic Labs) il 2026-04-18.
> Input: cartella COLAZIONE + 7 screenshot Stitch + 2 DESIGN.md + index.css attuale.
>
> File HTML/CSS sorgenti di riferimento salvati in `docs/REFERENCE-*`.

Piano implementativo per portare in codice i 4 schermi hi-fi. Rispetta i
token `@theme` esistenti in `frontend/src/index.css` e introduce solo i
token mancanti elencati in §3. Terminologia italiana (Turno PdC, Giro
Materiale, CVp/CVa, ACCp/ACCa, periodicità LMXGVSD) da NON tradurre.

---

## 01 · Mapping componenti

| Componente UI | File sorgente | Azione | Note |
|---|---|---|---|
| Sidebar | `components/Sidebar.tsx` | **RIUSO** | Rimuovere `border-r`: usare `bg-surface-container-low` sul contenitore. Aggiungere Kinetic-dot `::before` su `active` (3px, `--color-dot`). |
| Logo ARTURO· | `components/Logo.tsx` | **RIUSO** | Verificare dot green già presente; allineare dimensione a 6px con box-shadow pulse. |
| Gantt track | `components/PdcGanttV2.tsx` | **REFACTOR** | Mantieni 1230 righe di logica percentuali; sostituisci styling blocchi con le 5 classi `.gblock.{train,accp,vuota,refez,vettura}`. Sostituisci bordo con `box-shadow: inset` + tonal shift per No-Line. |
| BlockDetailModal | `components/BlockDetailModal.tsx` | **REFACTOR** | Trasforma da modal centrato a Drawer laterale destro (440px). Conserva la logica `trainCrossRef`/`trainCheck` — cambia solo il wrapper. Vedi nuovo componente `TrainDetailDrawer`. |
| TrainDetailDrawer (nuovo) | `components/TrainDetailDrawer.tsx` | **NUOVO** | Usa Radix Dialog con slide-in destro. Sezioni: Trip · Giro Materiale (prev/curr/next + chain) · PdC carriers · Status/Duty. Handoff indicator chip-success se orari allineati. |
| CommandPalette | `components/CommandPalette.tsx` | **NUOVO** | Radix Dialog + `cmdk`. Glassmorphism: `backdrop-blur(24px) saturate(180%)`, bg `rgba(255,255,255,0.86)`. Hotkey globale ⌘K/Ctrl+K. Gruppi: Suggerimenti, Turni, Treni, Azioni. |
| KPI card | `components/KpiCard.tsx` | **NUOVO** | Riuso su Dashboard + PdcPage stats esistenti. Variante `live` con pulse-dot verde. |
| ActivityFeed | `components/ActivityFeed.tsx` | **NUOVO** | Endpoint backend: proporre `GET /activity/recent?limit=20`. Icona coerente con tipo evento (blu: edit, verde: validato, ambra: conflitto, slate: import). |
| LineaAttivaTable | `components/LineaAttivaTable.tsx` | **NUOVO** | Wrapper su ARTURO Live (`services/arturo_client.py`). No `<tr>` border: tonal zebra via `bg-surface-container-low` su hover. |
| TrainSearchPage | `pages/TrainSearchPage.tsx` | **REFACTOR** | Split a 2 colonne (`1fr 340px`). Tabella fermate senza bordi — usa ghost border 15% solo in `tr.current`. Cross-ref side panel consuma lo stesso `trainCrossRef` del drawer. |
| PeriodicityChip | `components/PeriodicityChip.tsx` | **NUOVO** | Renderizza LMXGVSD. Props: `active: string` (es. `"LMXGV"`). 16×16 square, mono, brand per i giorni attivi. |
| PageHeader | `components/PageHeader.tsx` | **NUOVO** | Astrae la riga eyebrow + display title + subtitle + actions. Display usa Exo 2 700, tracking-tight -0.02em. |

---

## 02 · Priorità implementativa

Ordinate per impatto sul pain point principale (cross-link treno ↔ turni
PdC) e reuse percentage.

| # | Task | Stima | Dipendenze |
|---|---|---|---|
| P0 | `TrainDetailDrawer` — refactor di `BlockDetailModal` da modal a drawer destro. Conservare logica API, spostare markup. Highlight handoff time quando `prev.arr_time === next.dep_time`. | 1.5 gg | tokens (§3) |
| P0 | Integrare il drawer in `PdcPage` (single-click su blocco → open drawer) e in `PdcBuilderPage` (già apre modal oggi). | 0.5 gg | P0 sopra |
| P1 | `CommandPalette` + hotkey globale. Fonti dati: `listPdcTurns`, `searchTrains`, azioni statiche. | 1 gg | `cmdk` |
| P1 | `TrainSearchPage` — side panel cross-ref. Stesso endpoint `/train/{id}/cross-ref` del drawer. | 1 gg | P0 |
| P2 | `DashboardPage` — KPI + ActivityFeed + Today card + LineaAttiva. Backend: due endpoint nuovi (`/activity/recent`, `/linea/attiva`) o mock iniziale. | 1.5 gg | `KpiCard`, `ActivityFeed` |
| P2 | Refactor Gantt styling (no-line rule, nuove classi blocco, selezione con doppio ring). | 0.5 gg | tokens |
| P3 | Applicare No-Line rule a tutte le liste esistenti (`BlocksList`, `TurnsList`, pages: Calendario, Import). Sostituire border con tonal shift. | 1 gg | — |

---

## 03 · Token mancanti da aggiungere a `index.css`

Estendere il `@theme` esistente. **Non rimuovere** nessun token attuale
(breaking per le pagine in vita).

```css
@theme {
  /* ── Surface hierarchy (No-Line) ── */
  --color-surface:                   #FAF8FF;
  --color-surface-container-low:     #F2F3FF;
  --color-surface-container:         #E9ECFB;
  --color-surface-container-high:    #DFE3F7;
  --color-surface-container-highest: #D3DBF0;
  --color-surface-container-lowest:  #FFFFFF;

  /* ── Ink tonale ── */
  --color-on-surface:          #0B1C30;
  --color-on-surface-strong:   #0A1322;
  --color-on-surface-muted:    #5A6478;
  --color-on-surface-quiet:    #8992A6;

  /* ── Ghost border (solo fallback a11y) ── */
  --color-ghost:         rgb(15 23 42 / 0.08);
  --color-ghost-strong:  rgb(15 23 42 / 0.14);

  /* ── Shadows tinted ── */
  --shadow-sm: 0 1px 2px rgb(11 28 48 / 0.04);
  --shadow-md: 0 4px 12px rgb(11 28 48 / 0.06);
  --shadow-lg: 0 12px 40px rgb(11 28 48 / 0.08);

  /* ── Gradient CTA (Kinetic) ── */
  --gradient-primary: linear-gradient(135deg, #004B9F 0%, #0062CC 100%);

  /* ── Type ── */
  --font-display: "Exo 2", ui-sans-serif, system-ui, sans-serif;
  --font-sans:    "Inter", ui-sans-serif, system-ui, sans-serif;
  --font-mono:    "JetBrains Mono", ui-monospace, "SF Mono", Menlo, monospace;
}
```

**Regola No-Line.** Prima di aggiungere un `border-1` chiedi: si può
ottenere la separazione con uno shift tonale (`surface-container-low`
accanto a `surface-container-lowest`)? Se sì, niente bordo. Solo in
tabelle ad alta densità è ammesso `--color-ghost` (15% opacità).

---

## 04 · Nuovi endpoint da esporre

- `GET /activity/recent?limit=20` — feed eventi Dashboard. Payload:
  `{ id, type: "edit"|"validate"|"import"|"conflict", title, subtitle, created_at }`.
- `GET /linea/attiva` — treni attualmente monitorati. Consumer esistente
  `services/arturo_client.py`; aggregare per linea commerciale.
- `GET /dashboard/kpi` — KPI aggregati (totale turni, attivi, ore
  settimana, lavorati). Cache 60s.

---

## 05 · Font loading

Exo 2 è già self-hosted (`public/fonts/Exo2-Variable.ttf`). Aggiungere:

- `public/fonts/Inter-Variable.woff2` — body
- `public/fonts/JetBrainsMono-Variable.woff2` — mono per orari/treni

Dichiarare con `@font-face` + `font-display: swap` come per Exo 2.

---

## 06 · Checklist di merge

- [ ] Un click su blocco treno apre drawer destro (non più modal centrato).
- [ ] Drawer mostra: prev/curr/next + chain compatta + lista PdC carriers
      cliccabile + badge handoff.
- [ ] ⌘K/Ctrl+K apre il Command Palette da qualsiasi pagina.
- [ ] Nessun `border: 1px solid` nuovo introdotto per sezionare layout.
- [ ] Tutti gli orari HH:MM e numeri treno renderizzano in `font-mono`.
- [ ] Terminologia IT invariata: Turno PdC · Giro Materiale · CVp/CVa ·
      ACCp/ACCa · LMXGVSD.

---

ARTURO· · Editorial Precision · v1.0 · hi-fi handoff
