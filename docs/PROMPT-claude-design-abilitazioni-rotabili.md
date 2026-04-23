# Prompt per Claude Design — Abilitazioni + Rotabili (STEP 0 Genera turni)

> Copia/incolla su claude.ai/design. Repo + cartella locale
> `COLAZIONE` già collegati.

---

## Contesto

Nella pagina **"Genera turni PdC dal materiale"**
(`frontend/src/pages/AutoBuilderPage.tsx`) c'è una sezione "STEP 0 —
ABILITAZIONI" che mostra:

1. Lista **linee** (es. ALESSANDRIA ↔ MI.CERTOSA, ALESSANDRIA ↔ PAVIA,
   ecc.) con checkbox per abilitare/disabilitare
2. Lista **materiale rotabile** (es. E464N, ETR522, "non specificato")
   con checkbox

Oggi funziona ma visivamente è **disperso e difficile da navigare**:
- Lista linee in verticale a lunghezza piena (12 attive su 38 totali,
  quindi 38 righe da scorrere)
- Ogni riga una check + etichetta + contatore "1 giro" / "2 giri" a
  destra
- Nessun raggruppamento: tutte le linee mischiate (quelle da/verso
  ALESSANDRIA, ASTI, BELGIOIOSO... tutte insieme)
- Materiale rotabile sotto, stessa lista verticale 3 righe
- La sezione "STEP 0 — ABILITAZIONI ALESSANDRIA 12/38 linee · 2/3
  materiali" è un collapsible ma una volta aperto occupa tantissimo
  spazio

Vedi screenshot di riferimento in chat (due screenshot attuali pagina).

## Cosa redesignare

**File**: `frontend/src/pages/AutoBuilderPage.tsx` (sezione "Step 0")
**Componente**: probabilmente `AbilitazioniPanel.tsx` (in
`frontend/src/components/`)

## Cosa non va oggi

1. Lista linee piatta da 38 righe — troppo scrolling
2. Nessun raggruppamento per **capolinea di origine** (logico: il
   dispatcher pensa "le linee che partono/arrivano al mio deposito")
3. Il contatore "1 giro" / "2 giri" a destra è poco informativo da solo
   — manca cosa c'è in quel giro
4. Sezione materiale rotabile in fondo come "codina" — poco evidente
5. Filtro/ricerca mancante: se il deposito ha 38 linee diventa infame
6. Toggle "abilita tutte" / "disabilita tutte" per categoria mancante

## Proposta di direzione

Raggruppare le linee per **tipologia / capolinea** con intestazioni:

```
┌─ Linee del deposito ALESSANDRIA ────────────────────────┐
│                                                          │
│  🔍 Cerca linea...                        [✓ Tutte] [✗]  │
│                                                          │
│  ── Linee verso Milano (5 attive / 8) ─────────────────  │
│  ✓ ALESSANDRIA ↔ MI.CERTOSA       2 giri               │
│  ✓ ALESSANDRIA ↔ MILANO CENTRALE  1 giro                │
│  ✓ ALESSANDRIA ↔ MILANO ROGOREDO  2 giri                │
│  ○ ALESSANDRIA ↔ MI.LAMBRATE      1 giro                │
│  ... (mostra 3, expand per altre)                       │
│                                                          │
│  ── Linee del Po (2 attive / 4) ───────────────────────  │
│  ✓ ALESSANDRIA ↔ PAVIA             1 giro               │
│  ○ ALESSANDRIA ↔ VERCELLI          1 giro               │
│  ...                                                     │
│                                                          │
│  ── Linee transit (ASTI) (3 attive / 3) ───────────────  │
│  ✓ ASTI ↔ MI.CERTOSA                                   │
│  ✓ ASTI ↔ MILANO CENTRALE                              │
│  ✓ ASTI ↔ MILANO ROGOREDO                              │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

Il raggruppamento reale può essere derivato dai capolinea (MI*, PAV,
VERC/MORT/VIGE, ASTI/VOGH/TORT, ecc.). Se necessario, crea un piccolo
grouper in TS (`groupLinesByCorridor`) che categorizza le stazioni in
"corridoi".

**Materiale rotabile**: trasforma in chip/pill orizzontali compatte in
alto alla sezione, non in fondo. Esempio:

```
Materiale abilitato:  [✓ E464N]  [✓ ETR522]  [○ (non specificato)]
```

## Vincoli funzionali da preservare

- Stato abilitato/disabilitato va persistito sul backend (endpoint già
  esistenti: `/api/depot/{deposito}/enabled-lines`,
  `/api/depot/{deposito}/enabled-materials`)
- Contatore "N giri" deve restare visibile (informazione utile)
- Toggle singolo deve essere immediato (no bottone "salva")
- Sezione resta collapsible (se già lo era)

## Cosa mi aspetto da te

1. **Hi-fi mockup** della nuova Step 0 in 2 stati:
   - chiuso (collapsed): compatto con riassunto tipo "12/38 linee
     attive · 3 corridoi principali coperti"
   - aperto (expanded): layout raggruppato per corridoi con search +
     chip materiali in alto
2. **Schema TypeScript** dei tipi coinvolti (o conferma riusa tipi
   esistenti in `frontend/src/types/`)
3. **Handoff markdown** `docs/HANDOFF-abilitazioni.md` con:
   - Struttura componenti (es. `<CorridorGroup>`, `<LineRow>`,
     `<MaterialChip>`)
   - Logica raggruppamento corridoi (quali stazioni vanno in quale
     gruppo per il deposito ALESSANDRIA — casi di esempio)
   - Interazioni (search filter, toggle all per gruppo, stato loading)

Non toccare la logica di generazione turni in basso — è un altro scope.
