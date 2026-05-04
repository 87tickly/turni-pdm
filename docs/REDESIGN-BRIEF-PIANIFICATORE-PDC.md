# Redesign brief — Pianificatore Turno PdC + Sidebar

> **Cosa devi fare**: ridisegnare 5 schermate (Dashboard, Vista giri,
> Lista turni, Revisioni cascading, Visualizzatore Gantt turno PdC)
> e la barra laterale dell'app web ARTURO Business / COLAZIONE,
> sezione **Pianificatore Turno PdC**.
> L'obiettivo è **chiarezza visiva** della sidebar e del layout
> applicativo, mantenendo intatta l'identità brand (font, colori,
> logo, nomenclatura).

> **Cosa NON devi toccare**: font, palette colori, logo, terminologia
> italiana di dominio. Vedi sezione "Vincoli inviolabili".

---

## 1. Contesto del prodotto

- **Nome del prodotto**: ARTURO Business (codename interno: COLAZIONE)
- **Cosa fa**: software di pianificazione ferroviaria. Costruisce
  giri materiali e turni del personale di macchina (PdC) per
  operatori ferroviari come Trenord.
- **Utente del Pianificatore Turno PdC** (2° ruolo): ufficio
  pianificazione che, partendo dai giri materiali pubblicati dal
  1° ruolo, genera i turni dei macchinisti rispettando vincoli di
  prestazione, condotta, refezione, riposi.
- **Stato attuale dello sviluppo**: app già in produzione con
  layout funzionale ma "ingegneristico". Manca polish visivo e
  gerarchia chiara nella sidebar.

---

## 2. Vincoli inviolabili (NON modificare)

### 2.1 Font

- **Famiglia unica**: `"Exo 2"` (Google Fonts), fallback
  `system-ui, sans-serif`.
- Caricato come `font-sans` di default in Tailwind: tutto il markup
  eredita Exo 2 senza tag espliciti.
- Pesi disponibili da Google Fonts: 400 (regular), 600 (semibold),
  700 (bold), 900 (black). Non usare altri pesi.
- Heading di pagina (`h1`): weight 700, `letter-spacing: -0.01em`,
  colore `#0062CC`.
- Heading sezione (`h2`): weight 600, colore `#0062CC`.

### 2.2 Palette brand

| Token Tailwind | Valore | Uso |
|---|---|---|
| `primary` | `#0062CC` | Blu ARTURO. Heading, link attivi, item sidebar attivo, focus ring, CTA primary. |
| `primary-foreground` | `#FFFFFF` | Testo su sfondo primary. |
| `arturo-business` | `#B88B5C` | Terracotta/caramel. Solo nel logo (wordmark "Business" + dot animato). Non usare per UI generica. |
| `background` | `hsl(0 0% 100%)` | Bianco. Sfondo card. |
| `foreground` | `hsl(222.2 84% 4.9%)` | Testo principale. |
| `border` | `hsl(214.3 31.8% 91.4%)` | Bordo card, separatori, input. |
| `input` | `hsl(214.3 31.8% 91.4%)` | Bordo input. |
| `ring` | `#0062CC` | Outline focus-visible. |
| `secondary` / `accent` | `hsl(210 40% 96.1%)` | Hover sidebar, fondi neutri. |
| `muted` | `hsl(210 40% 96.1%)` | Background muted. |
| `muted-foreground` | `hsl(215.4 16.3% 46.9%)` | Testo secondario, hint, label. |
| `destructive` | `hsl(0 84.2% 60.2%)` | Errori, bordi destructive. |
| Body background | `#f7f9fc` con due gradienti radiali tenui (vedi 2.4) | Sfondo applicazione. |

### 2.3 Logo

Il wordmark `ARTURO • Business` è composto da tre elementi inline:

1. `ARTURO` — Exo 2 weight 900, colore `#0062CC`
2. cerchio `bg-arturo-business` (`#B88B5C`) con animazione
   `pulse-dot 1.6s ease-in-out infinite` (opacity 1↔0.45,
   scale 1↔0.78)
3. `Business` — Exo 2 weight 900, colore `#B88B5C`

Dimensioni: `sm` = `text-xl` + dot `h-2 w-2`; `lg` = `text-3xl` +
dot `h-3 w-3`. **Mantieni esattamente questo wordmark** in alto a
sinistra della sidebar. Non sostituire con altro logo, non
aggiungere icone, non cambiare i colori dei due segmenti.

### 2.4 Body background

```css
background:
  radial-gradient(circle at 0% 0%, rgba(0, 98, 204, 0.045), transparent 60%),
  radial-gradient(circle at 100% 100%, rgba(184, 139, 92, 0.04), transparent 55%),
  #f7f9fc;
```

Tenue, decorativo, non rimuovere.

### 2.5 Border-radius (token Tailwind)

- `rounded-lg` = `0.5rem`
- `rounded-md` = `0.375rem`
- `rounded-sm` = `0.25rem`

Card di solito `rounded-lg`. Bottoni e input `rounded-md`.

### 2.6 Nomenclatura italiana (NON tradurre, NON modificare)

| Termine UI | Significato |
|---|---|
| Pianificatore Turno PdC | Nome ruolo, header pagina |
| Pianificatore Giro Materiale | Altro ruolo (1°), già esistente nella sidebar |
| Giri materiali / Vista giri | Lista convogli rotabile |
| Turni PdC | Lista turni macchinisti |
| Rev. cascading | "Revisioni cascading" abbreviato in sidebar |
| Violazioni hard | KPI errori bloccanti su prestazione/condotta |
| Bozza · Pubblicato · Archiviato | Stati badge |
| Impianto | Deposito personale (es. MILANO_GA, BRESCIA, BERGAMO…) |
| Prestazione · Condotta | Metriche turno (in minuti) |
| Giornate | Numero giornate del giro/turno |
| km/giorno · km/anno | Metriche giro materiale |

---

## 3. Stack tecnico (output atteso)

### 3.1 Tecnologie

- React 18 + TypeScript + Vite
- Tailwind CSS 3 (config in `frontend/tailwind.config.ts`)
- Componenti UI custom in `frontend/src/components/ui/` con stile
  shadcn/ui (Radix-free, Tailwind only): `Card`, `Button`, `Input`,
  `Badge`, `Table`, `Spinner`, `Select`, `Dialog`, `Label`,
  `Textarea`.
- Icone: `lucide-react` (già in dipendenze). Le icone usate
  attualmente: `LayoutDashboard`, `ListOrdered`, `Workflow`,
  `AlertTriangle`, `LogOut`, `User`, `Search`, `AlertCircle`,
  `ArrowRight`, `ListChecks`. Puoi proporne altre dello stesso set.
- Routing: `react-router-dom` (NavLink, Link, useNavigate, Outlet).
- Data fetching: TanStack Query (hook custom già esistenti).

### 3.2 Output

Restituisci uno o entrambi:

**a) HTML statico** (mockup): `index.html` Tailwind-friendly che
posso aprire in browser per vedere il risultato visivo.

**b) Codice React/TSX** drop-in che sostituisce i file esistenti
mantenendo le **stesse props, hook e logica di data fetching**.
Il file riscritto deve continuare a chiamare gli stessi hook
(`usePianificatorePdcOverview`, `useGiriAzienda`,
`useTurniPdcAzienda`) e renderizzare gli stessi dati.

### 3.3 Vincoli aggiuntivi

- **Niente nuove dipendenze** (no shadcn install, no Radix, no
  framer-motion, no Headless UI).
- Solo classi Tailwind del config esistente.
- I componenti `Card`, `Button`, `Badge`, `Input`, `Table`,
  `Spinner` esistono già: usali, non riscriverli ex-novo.
- Mantieni le `data-testid` esistenti (es. `giro-row-${id}`,
  `turno-row-${id}`).
- Mantieni `aria-label`, `role="alert"` per errori,
  `focus-visible:ring-ring` per focus.

---

## 4. Sidebar — stato attuale e obiettivi del redesign

### 4.1 Stato attuale (oggi sono visibili 2 gruppi su 5 previsti)

Larghezza `w-60` (240px), `bg-white/70 backdrop-blur`, bordo destro
`border-border`. Struttura attuale:

```
┌──────────────────────┐
│  ARTURO • Business   │  ← logo, h-14, separatore in basso
├──────────────────────┤
│ PIANIFICATORE GIRO   │  ← label gruppo (uppercase, 11px, muted)
│  ▢ Home              │
│  ▢ Programmi         │
│                      │
│ PIANIFICATORE PDC    │  ← label gruppo
│  ▢ Home              │  ← attivo: bg-primary, text-white
│  ▢ Vista giri        │
│  ▢ Turni PdC         │
│  ▢ Rev. cascading    │
└──────────────────────┘
```

Item attivo: `bg-primary text-primary-foreground rounded-md`.
Item normale: hover `bg-accent text-accent-foreground`.

**A regime la sidebar avrà 5 gruppi**, uno per ciascun ruolo del
sistema (vedi `CLAUDE.md` regola operativa 8 — "Sviluppa per ruoli").
Oggi i gruppi 3-4-5 non sono implementati e sono nascosti dal
filtro `hasRole(group.requiredRole)`. Il redesign deve **prevedere
visivamente** lo spazio per tutti e 5, così quando i ruoli arriveranno
non sarà necessario ridisegnare la sidebar:

```
┌──────────────────────┐
│  ARTURO • Business   │
├──────────────────────┤
│ PIANIFICATORE GIRO   │ ← (1) implementato
│ PIANIFICATORE PDC    │ ← (2) implementato
│ MANUTENZIONE         │ ← (3) futuro
│ GESTIONE PERSONALE   │ ← (4) futuro
│ PERSONALE            │ ← (5) futuro (PdC finale)
└──────────────────────┘
```

Vedi `4.5` per il dettaglio dei 3 gruppi futuri.

### 4.2 Cosa migliorare

L'utente lamenta che la sidebar **non è abbastanza chiara**:

1. **Distinzione ruoli debole**: i due gruppi (Pianificatore Giro /
   Pianificatore PdC) sono visivamente molto simili. Quando lavori
   su un ruolo, l'altro ti distrae.
2. **Mancanza di "dove sono"**: serve un hint chiaro del ruolo
   corrente (oltre all'item attivo blu).
3. **Spazio tra gruppi**: i due gruppi sono troppo vicini, vanno
   separati visivamente (separatore, spacing extra, sfondo gruppo
   attivo leggermente diverso).
4. **Voci sidebar PdC poco esplicite**: "Vista giri" e "Rev.
   cascading" beneficerebbero di un sottotitolo o descrizione
   inline (es. "Vista giri" → in lettura dal 1° ruolo).

### 4.3 Proposte di miglioramento (puoi attuarle, mixarle, o proporne di equivalenti)

- **Header ruolo corrente**: piccolo box in cima al gruppo attivo
  con etichetta "RUOLO ATTIVO · Pianificatore PdC", sfondo
  `bg-primary/5` o simile.
- **Gruppo non-attivo collassato**: quando sei in PdC, il gruppo
  "Pianificatore Giro" mostra solo l'header label cliccabile per
  espandere; quando lo espandi diventa una mini-lista. Riduce
  rumore visivo.
- **Separatore tra gruppi**: linea sottile + spacing `mt-4`.
- **Counter inline opzionali**: es. accanto a "Turni PdC" un
  badge piccolo `12` con il numero turni esistenti, alimentato dal
  KPI già caricato in dashboard. Solo se naturale, non forzato.
- **Icone più consistenti**: oggi mix di `LayoutDashboard`,
  `Workflow`, `ListOrdered`, `AlertTriangle`. Mantieni icone
  semantiche, ma uniforma stile (stroke-width 1.75 ovunque, size
  `h-4 w-4`).
- **Footer sidebar opzionale**: piccolo elemento in fondo (es.
  versione build, link feedback, badge "azienda #2") per dare
  ancoraggio visivo al fondo.

### 4.4 Cosa NON fare

- Non eliminare i due gruppi (sono ruoli reali con permessi reali).
- Non rinominare le voci ("Home", "Programmi", "Vista giri",
  "Turni PdC", "Rev. cascading").
- Non rimuovere l'item attivo blu (è la convenzione consolidata).
- Non spostare il logo dall'angolo in alto a sinistra.
- Non rendere la sidebar collassabile completamente: l'utente vuole
  vederla sempre.
- Non eliminare lo spazio previsto per i 3 gruppi futuri (vedi 4.5):
  oggi sono nascosti per filtro ruolo, ma il design deve mostrare
  che la sidebar respira anche con 5 gruppi.

### 4.5 Gruppi futuri (3, 4, 5) — non implementati ma da prevedere visivamente

Il sistema avrà **5 ruoli totali** (vedi `CLAUDE.md` regola 8).
I 3 ruoli sotto **non sono ancora implementati**: niente route,
niente API, niente hook. Servono **al design** per due motivi:

1. **Capacity planning visivo**: a regime la sidebar dovrà ospitare
   5 gruppi senza diventare lunga e claustrofobica. Il redesign
   deve provare il layout con tutti e 5 caricati.
2. **Coerenza icone/etichette**: scegliere ora icone e label
   coerenti evita riprogettazioni quando i ruoli verranno
   implementati.

Per ognuno: **descrizione del ruolo · label sidebar · icona
proposta · voci tentative**. Le voci sono *placeholder* — il
design tool può mostrarle disabilitate / con stato "soon" / con
chip "wip" oppure ometterle e mostrare solo l'header gruppo.
La definizione finale delle voci avverrà in fase di sviluppo.

#### (3) MANUTENZIONE

- **Cosa fa**: gestione della dotazione fisica del materiale
  rotabile. Sa quanti pezzi di ogni tipo (es. ETR526 ×11,
  ETR425 ×18, ATR803 ×20) sono operativi, in IMP, fuori uso, e
  dove sono dislocati (FIORENZA, NOVATE, CAMNAGO, LECCO, CREMONA,
  ISEO + pool TILO).
- **Label sidebar**: `MANUTENZIONE`
- **Icona gruppo proposta**: `Wrench` (lucide-react). Alternative:
  `Cog`, `Settings2`.
- **Voci tentative**:
  - Home → `LayoutDashboard`
  - Dotazione flotta → `Layers` (elenco pezzi per tipo materiale)
  - Località manutenzione → `Building2` (sedi IMPMAN)
  - Manutenzioni programmate → `CalendarClock` (futuro)
- **Stato visivo nel mockup**: gruppo presente in sidebar ma con
  trattamento "anteprima" (es. opacity 0.6, niente hover attivo,
  oppure chip `presto` accanto al label gruppo).

#### (4) GESTIONE PERSONALE

- **Cosa fa**: anagrafica del personale di macchina (PdC) e
  assegnazione persone ai turni. Gestisce indisponibilità (ferie,
  malattia, formazione), profili, depositi di appartenenza
  (25 depositi PdC Trenord: ALESSANDRIA, ARONA, BERGAMO, BRESCIA,
  ecc.). NON costruisce i turni — quelli arrivano dal ruolo (2);
  qui si assegnano alle persone.
- **Label sidebar**: `GESTIONE PERSONALE`
- **Icona gruppo proposta**: `Users` (lucide-react). Alternative:
  `UserCog`, `Contact`.
- **Voci tentative**:
  - Home → `LayoutDashboard`
  - Anagrafica PdC → `Users`
  - Assegnazioni → `ClipboardList` (turno → persona)
  - Indisponibilità → `CalendarOff` (ferie, malattia)
- **Stato visivo nel mockup**: come (3).

#### (5) PERSONALE (PdC finale)

- **Cosa fa**: dashboard del singolo macchinista. Vede solo il
  proprio turno corrente, il proprio calendario, eventuali fuori
  residenza (FR) e la propria timbratura/disponibilità. Read-only
  per la maggior parte; può richiedere cambi turno o segnalare
  indisponibilità.
- **Label sidebar**: `PERSONALE`
- **Icona gruppo proposta**: `IdCard` (lucide-react). Alternative:
  `User`, `BadgeCheck`.
- **Voci tentative**:
  - Mio turno → `CalendarDays`
  - Calendario mensile → `Calendar`
  - FR (fuori residenza) → `MapPin`
  - Profilo → `User`
- **Stato visivo nel mockup**: come (3).
- **Nota**: questo ruolo userà probabilmente una vista più semplice,
  mobile-first. Non è l'oggetto di questo redesign — qui basta
  riservargli lo spazio sidebar.

#### Comportamento "filtro ruolo" attuale

Il codice già filtra i gruppi: `NAV_GROUPS.filter(g =>
hasRole(g.requiredRole))`. Quindi un utente che ha solo
`PIANIFICATORE_PDC` non vede gli altri 4 gruppi. **Il redesign deve
funzionare bene in tutti gli stati**:

- 1 solo gruppo visibile (utente con un solo ruolo)
- 2 gruppi (caso oggi tipico per pianificatori)
- 5 gruppi (utente admin con tutti i ruoli)

In quest'ultimo caso, la sidebar deve restare leggibile e non
diventare un muro indifferenziato. Soluzioni proposte (puoi mixare):

- Gruppo attivo espanso, gli altri 4 collassati (mostrano solo
  l'header label cliccabile per espandere).
- Separatore più marcato tra gruppi (linea + spacing maggiore).
- Header gruppo attivo con sfondo `bg-primary/5` e icona
  ruolo accanto al label.
- Possibilità di scroll interno alla sidebar se necessario, mai
  scroll della pagina intera.

---

## 5. Le 5 schermate da ridisegnare

### 5.1 Dashboard (route: `/pianificatore-pdc/dashboard`)

**H1**: "Dashboard Pianificatore Turno PdC"
**Sottotitolo**: "Benvenuto, {username}. Da qui costruisci i turni
del personale di macchina partendo dai giri materiali pubblicati."

**Sezione KPI** (4 card in grid `md:grid-cols-2 lg:grid-cols-4`):

| Card | Icona | Valore | Hint |
|---|---|---|---|
| Giri materiali | `Workflow` | numero | "Sorgente per i turni PdC" |
| Turni PdC | `ListChecks` | numero | "Nessun turno generato" oppure "Su N impianto/i" |
| Violazioni hard | `AlertTriangle` | numero | "Prestazione/condotta fuori cap" — bordo `border-amber-500/60` se >0 |
| Revisioni cascading | `Workflow` | numero | "Disponibile da Sprint 7.6" |

Stati possibili: loading (mostra `…`), error (mostra `—`),
success (mostra valore). Tutti i KPI possono essere `0` (è lo
stato iniziale, va leggibile e non triste).

**Sezione Action Cards** (2 card grandi in grid `md:grid-cols-2`):

- "Vista giri materiali" → link `/pianificatore-pdc/giri`,
  cta "Apri vista giri →"
- "Lista turni PdC" → link `/pianificatore-pdc/turni`,
  cta "Apri lista turni →"

Hover state: bordo `primary/50`, leggera shadow, freccia trasla
`translate-x-1`.

**Sezione "Distribuzione turni per impianto"** (card full-width):
lista di righe `impianto · count`, stati: loading / error / empty
("Nessun turno PdC presente per la tua azienda.") / lista.

**Cosa migliorare nel redesign**:

- I `0` sui 4 KPI sono visivamente piatti. Considera empty state
  più espressivo (illustrazione astratta, micro-copy "Inizia
  importando un giro materiale", CTA inline al primo passo).
- L'header pagina (h1 + descrizione) è poco gerarchizzato.
  Considera un hero più definito.
- Le 2 action card sono buone ma possono respirare di più.
- La card "Distribuzione" con empty è solo testo: l'utente non sa
  cosa farne. Migliorala.

### 5.2 Vista giri materiali (route: `/pianificatore-pdc/giri`)

**H1**: "Vista giri materiali"
**Sottotitolo**: "Giri pubblicati dal Pianificatore Giro, in sola
lettura. Click su una riga per il visualizzatore Gantt."

**Form filtri** (card border + bg-white, `flex flex-wrap items-end gap-3`):

- Input "Cerca per turno" (placeholder `es. A001, FIO-12, …`) +
  bottone outline con icona `Search`
- Select "Stato" (Tutti / Bozza / Pubblicato / Archiviato)

**Stati**:

- Loading: card con `Spinner` centrato, label "Caricamento giri…"
- Error: card `border-destructive/30 bg-destructive/5` con icona
  `AlertCircle`, messaggio, bottone "Riprova"
- Empty: card `border-dashed`, h2 "Nessun giro materiale",
  descrizione "I giri vengono creati dal Pianificatore Giro
  Materiale. Quando ce ne saranno, li vedrai qui in sola lettura."
- Lista: tabella con colonne **ID · Turno · Tipo materiale ·
  Giornate · km/giorno · km/anno · Stato · Creato**. Riga
  cliccabile (cursor-pointer). Numeri `tabular-nums`. Badge stato:
  `success` per pubblicato, `muted` per bozza, `outline` per
  archiviato.

**Cosa migliorare nel redesign**:

- Il form filtri ora è una banda larga: occupa molto verticale
  per pochi controlli. Considera barra compatta orizzontale,
  oppure filtri inline alla tabella.
- L'empty state è onesto ma plain. Migliora con illustrazione.

### 5.3 Lista turni PdC (route: `/pianificatore-pdc/turni`)

**H1**: "Lista turni PdC"
**Sottotitolo**: "Turni del personale di macchina dell'azienda.
Filtra per impianto, stato e codice. Click su una riga per il
visualizzatore Gantt."

**Form filtri**:

- Input "Cerca per codice" (placeholder `es. T-G-TCV-001, …`) +
  bottone search
- Input "Impianto" (placeholder `MILANO_GA, BRESCIA, …`)
- Select "Stato" (Tutti / Bozza / Pubblicato / Archiviato)

**Tabella** colonne: **ID · Codice · Impianto · Profilo · Giornate ·
Prest. (min) · Cond. (min) · Violaz. · Stato · Valido da**.

- Codice può avere badge laterale `Ramo X/Y` se è un ramo split.
- Violazioni: se `> 0`, testo `text-amber-700` con icona
  `AlertTriangle h-3 w-3`. Se 0, testo muted.
- Numeri `tabular-nums`.

**Empty**: "Nessun turno PdC. I turni si generano dal dettaglio di
un giro materiale (bottone 'Genera turni PdC'). Quando ce ne
saranno, li vedrai qui con i filtri per impianto/stato."

**Cosa migliorare**: stessa logica della 5.2 (filtri compatti,
empty più caldo).

### 5.4 Revisioni cascading (route: `/pianificatore-pdc/revisioni-cascading`)

Placeholder Sprint 7.6+. Layout attuale:

- Titolo "Revisioni cascading"
- Descrizione: "Quando il Pianificatore Giro pubblica una
  revisione provvisoria, qui arriva la proposta di cascading PdC
  automaticamente calcolata."
- Sub: "Sprint 7.6+ — richiede modello `revisione_provvisoria`"
- Endpoint atteso: "GET /api/revisioni-cascading (futuro)"

**Cosa migliorare**: rendere il "coming soon" elegante e
informativo (timeline, badge "WIP", spiegazione del flusso futuro
con piccolo diagramma o mockup ghosted).

### 5.5 Visualizzatore Gantt turno PdC (route: `/pianificatore-pdc/turni/:turnoId`)

Schermata raggiungibile dal click su una riga di "Lista turni PdC"
(§ 5.3). È un **visualizzatore Gantt sola lettura**: mostra il
turno scomposto in giornate, e ogni giornata come barra a 24 ore.
L'editing interattivo (drag&drop blocchi, modifica orari) è scope
futuro (Sprint 8+) — per ora il design deve servire la lettura,
non l'edit.

> **Vincolo importante — simile ma diverso dal Gantt giro materiale**:
> nel progetto esiste già un Gantt per il **giro materiale** (1° ruolo,
> stile "single-line PDF Trenord", asse 04→04 next day, classi
> `seg-comm/seg-vuoto/seg-rientro/seg-acc/seg-sosta/validato/gap-long/
> night-band/ticks-bg` in [`index.css:62-118`](../frontend/src/index.css)).
> Il Gantt **turno PdC** deve essere visivamente **parente**
> (stessa filosofia di lettura cronologica, stessa convenzione
> "tempo orizzontale", coerenza tipografica e di token), **ma
> riconoscibilmente diverso**. Il pianificatore turni deve capire
> a colpo d'occhio che è un'altra schermata, non una copia.
>
> Distinzioni concrete da preservare/accentuare:
>
> - **Asse orario**: il Gantt giro è 04→04 next day (ciclo
>   commerciale di una giornata-treno). Il Gantt turno PdC è
>   00→23 (giornata di lavoro umana). Non uniformare.
> - **Palette segmenti**: il Gantt giro usa rosso/viola/arancione
>   per natura del segmento commerciale (commerciale, vuoto,
>   rientro, accessori). Il Gantt turno PdC usa una palette per
>   tipo evento del lavoro PdC (CONDOTTA blu primary, VETTURA sky,
>   REFEZ emerald, ACCp/ACCa amber, CV orange, DORMITA viola,
>   PK/SCOMP secondary). Mantieni questa distinzione semantica.
> - **Granularità**: il Gantt giro è single-line per giornata,
>   denso. Il Gantt turno PdC è multi-pannello (una `GiornataPanel`
>   per giornata, con header dedicato, badge violazioni, tabella
>   blocchi sotto). Non collassarlo a single-line.
> - **Affordance**: il Gantt giro ha selezione blocco
>   (`gantt-selecting`/`is-selected`) e bordi di "validato manuale".
>   Il Gantt turno PdC oggi è puramente di lettura — qui hover
>   tooltip basta, non aggiungere selezione.
>
> In sintesi: stessa **grammatica visiva** (token Tailwind, font,
> pattern asse), **vocabolario diverso** (palette, layout
> giornata, densità). Non riusare le stesse classi CSS del Gantt
> giro materiale (`.seg-*`, `.night-band`, `.ticks-bg`): se servono
> elementi simili (es. tick verticali sull'asse), riproponili con
> classi proprie del turno PdC.

**Struttura attuale**:

1. **Back link** in alto: `← Lista turni PdC` (link a
   `/pianificatore-pdc/turni`).
2. **Header turno**: H1 = `codice turno` (es. `T-G-TCV-001`),
   badge outline impianto, eventuali altri meta.
3. **Stats**: card o riga con totali (prestazione, condotta,
   refezione, FR settimanali, ecc.).
4. **Avvisi** (visibili solo se ci sono): box giallo-amber con
   `validazioni_ciclo` (es. riposo settimanale insufficiente,
   FR > 1/settimana) e elenco giornate con FR (`fr_giornate`).
5. **Sezione "Giornate (N)"**: una `GiornataPanel` per ognuna,
   in colonna verticale, ognuna con:
   - Header giornata: `Giornata 1`, badge violazioni inline:
     - `prest. fuori cap` (warning) se prestazione > 510 min std
     - `cond. fuori cap` (warning) se condotta > 330 min
     - `refez. mancante` (amber outline) se prestazione > 6h e
       refezione mancante
   - Riga meta: `inizio→fine prestazione`, totali
     (`prestazione`, `condotta`, `refez`) in `formatHM`
     (es. `8:25`)
   - **GanttRow**: asse 24 colonne (`00..23`), barra alta `h-9`
     `bg-secondary/20`, blocchi posizionati in valore assoluto
     `left%/width%` calcolato su `MINUTI_GIORNO = 1440`. Min
     width container `768px` con `overflow-x-auto`.
   - **BlocchiList** (collapsible `<details>`): tabella con
     colonne `# · Tipo · Treno · Da · A · Inizio · Fine · Min`.

**Palette colori segmenti** (NON modificare — sono semantici per
tipo evento, vedi `colorForTipoEvento` nel file):

| `tipo_evento` | Classi Tailwind | Significato dominio |
|---|---|---|
| `CONDOTTA` | `bg-primary text-primary-foreground` | Guida del treno (blu ARTURO) |
| `VETTURA` | `bg-sky-200 text-sky-900` | PdC come passeggero (deadhead) |
| `REFEZ` | `bg-emerald-200 text-emerald-900` | Pausa pasto |
| `ACCp` / `ACCa` | `bg-amber-200 text-amber-900` | Accessori partenza/arrivo |
| `PK` / `SCOMP` | `bg-secondary text-secondary-foreground` | Parking, S.COMP |
| `PRESA` / `FINE` | `bg-slate-300 text-slate-800` | Presa/fine servizio |
| `CVp` / `CVa` | `bg-orange-200 text-orange-900` | Cambio Volante |
| `DORMITA` | `bg-violet-300 text-violet-900` | FR (Fuori Residenza) |
| default | `bg-muted text-muted-foreground` | — |

Etichetta sul blocco: numero treno se `CONDOTTA` con `numero_treno`,
`FR` se `DORMITA`, altrimenti il `tipo_evento`. `truncate` se non
sta. Tooltip nativo (`title`) con dettaglio completo.

**Cosa migliorare nel redesign**:

- **Leggibilità segmenti corti**: blocchi < 30 minuti (es.
  ACCp/ACCa = 40', CV con gap stretto) hanno etichette troncate
  o invisibili. Considera tooltip persistente al hover, oppure
  un'etichetta esterna (sopra/sotto la barra) per i blocchi
  troppo stretti.
- **Asse temporale più chiaro**: oggi il pattern `ticks-bg` esiste
  già in `index.css` per il Gantt giro materiale (linee verticali
  ogni 30'/60'). Considera di applicarlo anche qui per dare
  riferimento visivo agli orari, mantenendo l'header `00..23`.
- **Blocco "validato"** ha già una shadow inset emerald (`.validato`
  in CSS): assicurati che sia ben visibile sui colori chiari
  (sky-200, emerald-200, amber-200).
- **Avvisi e violazioni**: oggi sono badge inline alla giornata.
  Considera un riepilogo aggregato in cima ("3 violazioni hard,
  2 giornate con FR") con jump-to-giornata.
- **Legenda colori**: oggi assente. Per un visualizzatore Gantt è
  utile una legenda compatta (chip orizzontali in alto o footer)
  con la mappa tipo→colore. Solo legenda visiva — non interattiva.
- **Stati limite**: turno con 0 giornate, 0 blocchi in una
  giornata, valori `null` su orari (`?` placeholder già gestito
  nel codice). Mantieni questa robustezza.
- **Stampa / export**: opzionale, ma il Gantt è il candidato
  naturale per un PDF/print. Se proponi un design "stampabile"
  (palette adatta a B/N, eliminazione hover, layout fisso) è
  un plus.

**Cosa NON fare in questa schermata**:

- Non cambiare i colori dei segmenti per tipo evento (sono
  convenzioni dominio condivise con il Gantt giro materiale).
- Non sostituire la barra `h-9` con altezze drasticamente diverse
  (verticalità del componente è bilanciata col denso BlocchiList
  sotto).
- Non rimuovere la tabella `BlocchiList` (è la fonte primaria di
  dato per il pianificatore, il Gantt è la visualizzazione
  riassuntiva).
- Non implementare drag&drop o edit interattivo: è esplicitamente
  scope futuro (Sprint 8+), eviti di indurre in tentazione il
  pianificatore con affordance non funzionanti.

---

## 6. Layout applicativo (header)

L'header in alto (`h-14`, `bg-white border-b border-border`) mostra:

- **Sinistra**: titolo pagina (es. "Pianificatore Turno PdC") in
  `text-sm font-medium tracking-wide text-primary/80`
- **Destra**: utente loggato → icona `User`, username, badge
  `admin` (se admin: `bg-primary/10 text-primary`), label
  `azienda #N`, bottone `Esci` con icona `LogOut`

Mantienilo. Eventualmente migliora il bottone Esci (oggi è ghost
basico) e il badge admin.

---

## 7. Stati e micro-interazioni (riassunto)

- **Hover card cliccabile**: `border-primary/50` + `shadow-md`
- **Hover riga tabella cliccabile**: `bg-accent` (o lasciare il
  default) + `cursor-pointer`
- **Focus visible**: `ring-2 ring-ring ring-offset-0`
- **Transizioni**: `transition` o `transition-colors` di Tailwind
  default (no animazioni custom)
- **Empty state**: card `border-dashed`, padding generoso
  (`py-16`), testo centrato
- **Loading**: spinner centrato con label
- **Error**: card `border-destructive/30 bg-destructive/5` con
  icona, messaggio e CTA "Riprova"

---

## 8. Accessibilità (mantieni)

- Tutti i bottoni hanno `aria-label` se sono icon-only
- `role="alert"` per error block
- Focus ring visibile su tutti gli interactive
- Heading hierarchy corretta (un solo h1 per pagina)
- `aria-hidden` sulle icone decorative

---

## 9. Cosa NON fare

- Non cambiare font (Exo 2 è obbligatorio)
- Non cambiare blu primary (#0062CC) né terracotta arturo-business (#B88B5C)
- Non sostituire o ridisegnare il logo
- Non introdurre colori fuori palette (es. verdi/viola decorativi)
- Non aggiungere dipendenze nuove
- Non tradurre la nomenclatura italiana di dominio
- Non rimuovere features esistenti (filtri, KPI, badge stato, violazioni)
- Non eliminare le 4 voci sidebar PdC
- Non rendere la sidebar nascondibile
- Non ignorare i 3 gruppi futuri (Manutenzione, Gestione Personale,
  Personale): vanno previsti visivamente, anche se oggi nascosti dal
  filtro ruolo (vedi sezione 4.5)

---

## 10. Cosa devi consegnare

1. Mockup HTML con Tailwind CDN (apribile in browser) **OPPURE**
   set di file `.tsx` drop-in compatibili con la struttura
   esistente.
2. Una breve nota (in cima al file consegnato) che riassume le
   3-5 scelte principali del redesign (es. "Sidebar: ruolo attivo
   in header gruppo, gruppo non-attivo collassato; Dashboard: hero
   header + empty state KPI con micro-CTA; Tabelle: filtri inline
   come toolbar compatta sopra header tabella").
3. Se proponi alternative, mostra max 2 varianti per la sidebar e
   1 per la dashboard, ognuna ben distinta.

---

## 11. Riferimenti file (per la consegna in TSX)

| Cosa | File |
|---|---|
| Sidebar | `frontend/src/components/layout/Sidebar.tsx` |
| Header | `frontend/src/components/layout/Header.tsx` |
| Layout shell | `frontend/src/components/layout/AppLayout.tsx` |
| Logo (NON modificare) | `frontend/src/components/brand/ArturoLogo.tsx` |
| Dashboard PdC | `frontend/src/routes/pianificatore-pdc/DashboardRoute.tsx` |
| Vista giri | `frontend/src/routes/pianificatore-pdc/GiriRoute.tsx` |
| Lista turni | `frontend/src/routes/pianificatore-pdc/TurniRoute.tsx` |
| Rev. cascading | `frontend/src/routes/pianificatore-pdc/RevisioniCascadingRoute.tsx` |
| Gantt turno PdC (componente) | `frontend/src/routes/pianificatore-giro/TurnoPdcDettaglioRoute.tsx` |
| Gantt turno PdC (wrapper PdC) | `frontend/src/routes/pianificatore-pdc/TurnoDettaglioRoute.tsx` |
| Tailwind config | `frontend/tailwind.config.ts` |
| CSS globale | `frontend/src/index.css` |
| Card UI | `frontend/src/components/ui/Card.tsx` |
| Button UI | `frontend/src/components/ui/Button.tsx` |
| Input UI | `frontend/src/components/ui/Input.tsx` |
| Badge UI | `frontend/src/components/ui/Badge.tsx` |
| Table UI | `frontend/src/components/ui/Table.tsx` |
| Spinner UI | `frontend/src/components/ui/Spinner.tsx` |

---

## 12. Brief sintetico (TL;DR)

> Ridisegna la sidebar e le 5 schermate del Pianificatore Turno
> PdC di ARTURO Business (Dashboard, Vista giri, Lista turni,
> Rev. cascading, Visualizzatore Gantt turno PdC). Il Gantt turno
> PdC deve essere **simile ma diverso** dal Gantt giro materiale
> già esistente: stessa grammatica visiva, palette e layout
> diversi (vedi § 5.5). Mantieni Exo 2, blu `#0062CC`,
> terracotta `#B88B5C`, logo wordmark e nomenclatura italiana
> esattamente come sono. La sidebar oggi mostra 2 gruppi
> (Pianificatore Giro, Pianificatore PdC) ma a regime ne avrà 5
> (più Manutenzione, Gestione Personale, Personale): prevedi
> visivamente lo spazio per tutti, oggi i 3 futuri sono nascosti
> dal filtro ruolo ma vanno mostrati nel mockup (es. anteprima
> opacizzata o con chip "presto"). La sidebar deve dire chiaramente
> "su quale ruolo sto lavorando ora" e dare respiro tra i gruppi.
> La Dashboard deve avere un hero migliore e empty state più caldo
> (oggi i KPI sono `0` e sembrano un cimitero). Le due tabelle
> (Vista giri, Lista turni) hanno form filtri pesanti: compattali.
> Niente nuove dipendenze, solo Tailwind + componenti UI esistenti.
