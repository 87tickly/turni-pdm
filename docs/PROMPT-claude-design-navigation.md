# Prompt per Claude Design — Navigation / Sidebar

> Copia/incolla su claude.ai/design. Hai già accesso al repo
> `87tickly/turni-pdm` e alla cartella `COLAZIONE`, quindi leggi i
> componenti sorgente direttamente.

---

## Contesto

Il facelift visivo globale di ARTURO è fatto (design system "Kinetic
Conductor", vedi `docs/HANDOFF-claude-design.md`). La sidebar attuale
ha 8 voci ma alcune sono obsolete e una voce nuova va aggiunta.

## Cosa redesignare

**File principale**: `frontend/src/components/Sidebar.tsx`
**Router**: `frontend/src/App.tsx`
**Pagine collegate**: `CalendarPage.tsx` (da eliminare), `TrainSearchPage.tsx`
(da eliminare), `DashboardPage.tsx`, `PdcPage.tsx`, `AutoBuilderPage.tsx`

## Cambi richiesti

### Rimuovere

1. **Cerca treni** (`/treni`, `TrainSearchPage.tsx`) — funzione non usata
   dai dispatcher, rumore nella nav
2. **Calendario** (`/calendario`, `CalendarPage.tsx`) — sostituito da
   "Calendario agente" con semantica diversa

### Aggiungere

1. **Calendario agente** — nuova pagina che mostra il calendario **per
   singolo PdC**: scroll temporale su 28 giorni, righe = PdC, colonne =
   giorni, celle = giornata assegnata (turno + codice + durata). Serve
   per vedere "chi lavora quando" nell'arco del mese, non più "quali
   turni esistono oggi".
   - Nuova route: `/calendario-agente`
   - Nuovo file: `frontend/src/pages/CalendarAgentePage.tsx`

### Riordinare

Voci attuali:
```
Dashboard
Cerca treni          ← RIMUOVI
Turni Materiale
Nuovo turno
Calendario           ← SOSTITUISCI
Turni PdC
Genera da materiale
Import
Impostazioni
```

Proposta ordine nuovo (ragionare sul flusso di lavoro del dispatcher):
```
Dashboard
Turni Materiale
Turni PdC
Genera da materiale
Calendario agente    ← NUOVO
Nuovo turno
Import
Impostazioni
```

Rationale: prima si vedono i dati (Turni Materiale → Turni PdC), poi si
generano (Genera da materiale), poi si verifica l'assegnazione nel tempo
(Calendario agente), poi si interviene manualmente (Nuovo turno / Import).

## Vincoli funzionali da preservare

- Layout sidebar fissa a sinistra, logo ARTURO in alto (animato con
  puntino verde, `Logo.tsx` — NON toccare)
- Campo cerca globale in alto (`⌘K` command palette) — resta
- Footer con username + logout — resta
- Icone lucide-react, stile coerente con resto UI
- Mobile: sidebar collassabile (se già così)

## Cosa mi aspetto da te

1. **Hi-fi mockup** della sidebar rifinita (tutte le 8 voci corrette,
   ordinate)
2. **Hi-fi mockup** della nuova pagina "Calendario agente" con almeno:
   - Header con filtri (mese, deposito)
   - Griglia PdC × giorni (28 giorni tipici)
   - Celle con stato visivo (lavorativo, riposo, FR, S.COMP, scoperto)
   - Sidebar dettagli giornata (opzionale)
3. **Handoff markdown** `docs/HANDOFF-calendario-agente.md` con:
   - Struttura componenti
   - Tipi TypeScript per i dati (riusa i tipi esistenti in
     `frontend/src/types/` se possibile)
   - Tokens CSS nuovi (se servono oltre a quelli in `index.css`)
   - Edge case: giornate NON chiudibili, FR candidate, S.COMP

Non toccare PdcPage, AutoBuilderPage, PdcBuilderPage in questo giro —
quelli sono scope separato.
