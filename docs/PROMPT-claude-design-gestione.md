# Prompt per Claude Design — Redesign "Gestione Turni PdC"

> Copia/incolla questo prompt su claude.ai/design. Claude Design ha già
> accesso al repo `87tickly/turni-pdm` e alla cartella locale `COLAZIONE`,
> quindi può leggere tutto senza upload.

---

## Contesto

Ho già completato il facelift visivo globale di ARTURO (logo, sidebar,
dashboard, cerca treni, login, settings, builder, ecc.) seguendo il
design system **Kinetic Conductor** che hai progettato tu nel bundle
precedente. Tutto documentato in `docs/HANDOFF-claude-design.md`.

Ora manca **l'area core dell'app**: la **gestione dei Turni PdC**.

Questa è la schermata più usata dai dispatcher ed è rimasta visivamente
arretrata rispetto al resto. In produzione appare sparsa, poco leggibile,
i blocchi Gantt sono minuscoli, le stazioni capolinea fluttuano sopra
l'asse senza gerarchia.

## Cosa redesignare

**Schermata**: `frontend/src/pages/PdcPage.tsx` (pagina Turni PdC)
**Componente chiave**: `frontend/src/components/PdcGanttV2.tsx` (Gantt interattivo, 1230 righe)
**Sottocomponenti**: `DayCard`, `BlocksList`, `TurnDetail` (tutti dentro `PdcPage.tsx`)

Zoom particolare sulla parte destra dello split layout (il "detail panel"):
- Header turno con codice/planning/profilo/validità
- Lista giornate espandibili (g1, g2, ...) con periodicità LMXGVSD
- Dentro ogni giornata: **Gantt visuale** + toggle Gantt/Lista
- Toggle attuale: "📊 Gantt" / "📋 Lista" (kitsch, da sostituire)

## Cosa non va oggi

Vedi gli screenshot in `docs/screenshots/pdc-page-current-*.png`
(produzione `web-production-0e9b9b.up.railway.app`, login richiesto —
te li mando io se non li hai già salvati):

1. **Gantt SVG troppo utilitario**: asse tick 1px, blocchi alti 22px,
   padding laterali infimi. Manca respiro
2. **Station label capolinea** fluttuano sopra l'asse senza contenitore
   visivo — sembrano volanti
3. **Blocchi treno** sono quasi invisibili perché stretti rispetto alla
   giornata 24h. Su turni corti (5h lavoro) si vede solo un pezzetto di
   Gantt pieno e tanto spazio vuoto
4. **DayCard header** con metriche inline (Lav/Cct/Km/Rip) leggibile
   ma compresso — meriterebbe respiro o layout tabellare pulito
5. **BlocksList (modalità lista)** usa chip colorati a bordo (`border
   bg-{color}-50`) non coerenti coi colori del Gantt SVG aggiornato.
   HANDOFF §01 aveva già indicato di sostituirli con le 5 classi
   `.gblock.{train,accp,vuota,refez,vettura}`
6. **Action bar 8-icone** che appare quando selezioni un blocco nel
   Gantt — non mi convince, stile "toolbar grigia" vecchia
7. **Toggle Gantt/Lista con emoji** (📊/📋) — da sostituire con icone
   lucide-react + look pulito

## Vincoli funzionali DA PRESERVARE (critici)

Interazioni attuali del `PdcGanttV2` che NON devono sparire:
- **Hover su blocco** → tooltip con dettagli
- **Click su blocco** → apre `TrainDetailDrawer` (drawer destro 440px,
  componente già redesignato da te — va bene così)
- **Drag sul centro di un treno** → sposta il blocco (+ CVp/CVa
  agganciati). Snap 5 minuti
- **Drag sui bordi** → resize start/end
- **Cross-day drop** (solo in PdcDepotPage) → trascina un blocco su
  un'altra giornata
- **Action bar 8 icone** (edit, move, duplicate, link, warn, detail,
  history, delete): può cambiare stile ma le 8 azioni devono restare

API componente (`PdcGanttV2Props`, righe 54-103 del file) deve restare
invariata — il redesign è solo visivo.

## Principi DS applicabili

Tutti già nel repo, letti automaticamente:
- `docs/HANDOFF-claude-design.md` — sezioni 01 (Gantt track), 03 (tokens)
- `docs/REFERENCE-claude-design-styles.css` — variabili base
- `docs/REFERENCE-claude-design-screens.css` — classi `.gblock.*` già
  definite (righe 147-182), `.day`, `.day-hd`, `.day-body` (se ci sono)
- `docs/REFERENCE-screen-editor.html` — reference originale Editor
  (righe 50-115 per il Gantt stile target)
- `frontend/src/index.css` — tokens `@theme` live in produzione

Regola chiave (già applicata altrove): **No-Line rule** (tonal shift
al posto di border-1 per sezionare), **font-mono** obbligatorio per
orari HH:MM e numeri treno, **kinetic dot** `#22C55E` per status attivo.

## Deliverable atteso

1. **Hi-fi mockup** (screenshot Claude Design, anche più di una
   variazione se utile)
2. **Handoff markdown** `HANDOFF-gestione-pdc.md` con:
   - Breakdown componente per componente (DayCard header, DayCard body
     Gantt, Gantt track rendering, Gantt ruler, Gantt selected state +
     action bar, BlocksList variante lista, TurnDetail header)
   - CSS/Tailwind snippet per ogni parte (riusando tokens esistenti)
   - Note su cosa riutilizzare da `REFERENCE-claude-design-screens.css`
     e cosa aggiungere ex novo
   - Check di coerenza: colori blocchi SVG corrispondono a `.gblock.*`
     CSS? Font? Spacing?
3. **Priorità implementativa** P0→P3 (così Claude Code può spezzare
   in commit atomici senza rompere funzionalità)

## Output non richiesto

- Non serve redesignare il `TrainDetailDrawer` (già fatto Fase 2 P0)
- Non serve toccare `PdcBuilderPage` / `PdcDepotPage` — quando il
  componente `PdcGanttV2` e `DayCard` saranno redesignati, ereditano
  loro il look
- Non serve proporre nuove feature funzionali — solo redesign visivo +
  coerenza DS

---

Grazie. Quando hai l'handoff pronto, lo passo a Claude Code e
implementiamo.
