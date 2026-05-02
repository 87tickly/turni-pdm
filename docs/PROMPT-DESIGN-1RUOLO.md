# Brief design — Pianificatore Giro Materiale (1° ruolo)

> Versione 2026-05-02 · COLAZIONE
>
> File destinato a un designer (es. Claude Design / artifact HTML)
> per ridisegnare l'interfaccia delle 5 schermate del **1° ruolo**
> del programma di pianificazione ferroviaria COLAZIONE.

---

## Come lavorare con questo brief (per il designer)

1. Leggi per intero la sezione **Contesto generale** sotto. Confermami
   "pronto" quando l'hai assimilata. Non disegnare ancora niente.
2. Disegna **una sola schermata alla volta**, nell'ordine:
   1. Dashboard
   2. Lista programmi
   3. Dettaglio programma
   4. Lista giri generati
   5. Visualizzatore Gantt giro
3. Per ogni schermata produci **un solo mockup HTML+Tailwind low-fi**,
   focalizzato sull'**Information Architecture** (cosa va dove, gerarchia,
   stati). Niente font fancy, niente immagini stock, niente animazioni,
   niente librerie esterne. Annota in un commento HTML in cima al file
   le scelte di IA che hai fatto.
4. Aspetta la review della singola schermata prima di passare alla
   successiva. Il visual design (colore brand, micro-interazioni, polish)
   verrà alzato **solo dopo che l'IA è approvata**.

---

## Contesto generale

### Cos'è il prodotto

**COLAZIONE** è una web app desktop-first per la pianificazione
ferroviaria delle aziende che gestiscono treni passeggeri.
Multi-tenant: oggi serve **Trenord** (azienda italiana, ~6.500
corse/anno), domani SAD/TILO/Trenitalia. La logica business non è
hardcoded sull'azienda: è configurabile via dato.

Il programma è organizzato in **5 ruoli operativi**, ciascuno con la
propria dashboard:

1. **Pianificatore Giro Materiale** ← stiamo ridisegnando questo
2. Pianificatore Turno PdC (personale di macchina)
3. Manutenzione (dotazione fisica dei treni)
4. Gestione Personale (anagrafica + assegnazioni)
5. PdC finale (macchinista che vede il proprio turno)

**Importante**: ogni ruolo ha la sua app. Non mescolare schermate di
ruoli diversi. In particolare il 2° ruolo (PdC) ha concetti come
"turni PdC", "violazioni hard", "revisioni cascading", "9NNNN
BG-LE" che **NON devono mai apparire** nelle schermate del 1° ruolo.

### Cosa fa il 1° ruolo

Il **Pianificatore Giro Materiale** decide come ruotano i convogli
(treni fisici) lungo la rete. Il suo lavoro tipico:

1. Crea un **Programma materiale** (es. "Esercizio Estivo 2026",
   periodo 15-giu → 14-set)
2. Configura le **regole di assegnazione**: "le corse della linea
   Tirano si fanno con ETR526, in coppia da 2 pezzi, cap km/ciclo
   4500"
3. **Pubblica** il programma (passa da bozza → attivo)
4. **Lancia il builder**: per ogni sede di manutenzione (FIO, NOV,
   CAM, LEC, CRE, ISE) costruisce i giri (= sequenze multi-giornata
   di corse coperte da un convoglio)
5. **Controlla i giri generati** (lista + Gantt giornata × blocchi)
   e decide se ri-generare con regole diverse

Output del builder per un programma reale: **600-900 giri** persistiti,
ciascuno coprendo da 1 a 7 giornate. Il pianificatore deve poter
scansionarli velocemente.

### Stack tecnico (vincolo)

- **React 18 + TypeScript + Vite**
- **Tailwind CSS**
- Componenti UI minimal in stile shadcn: `Card, Button, Badge, Dialog,
  Input, Label, Select, Spinner, Table, Textarea`. Niente Material UI,
  niente Chakra, niente Ant Design.
- **TanStack Query** per data fetching (le route hanno già hook
  `useProgrammi`, `useGiri`, `useGeneraGiri`, ecc.)
- **React Router v6**
- **Italiano** nei testi UI (è un prodotto italiano)
- Icon set: **lucide-react**

Output che mi serve: **HTML + Tailwind**, mockup low-fi. I colori usa
quelli neutri di Tailwind (gray/blue/amber/emerald come richiamo
semantico). Il brand colour del prodotto è blu (`#1d4ed8` circa) —
puoi assumerlo come `bg-primary`/`text-primary`.

### Glossario minimo

| Termine | Significato |
|---|---|
| **Programma** | Contenitore di un periodo di pianificazione. Ha periodo (es. 15/06–14/09), regole, stato (bozza / attivo / archiviato). Un programma = un turno materiale unico per la sua finestra di validità. |
| **Regola di assegnazione** | "Le corse che matchano questi filtri (linea, codice, stazione, ecc.) vengono coperte da questa composizione (ETR526 × 2 pezzi)". Una regola ha priorità + cap km. |
| **Giro materiale** | Convoglio polivalente che copre N giornate consecutive di servizio. Ha un `numero_turno` formato `G-{SEDE}-{NNN}-{MATERIALE}` (es. `G-FIO-001-ETR204`). Un giro = 1 sequenza canonica per giornata. |
| **Giornata di un giro** | Una giornata-tipo del giro (1° giorno, 2° giorno…). Ogni giornata ha una **etichetta** parlante: `feriale | sabato | domenica | festivo | data_specifica | personalizzata`. |
| **Blocco** (di una giornata) | Pezzo della sequenza di una giornata: corsa commerciale, vuoto tecnico (posizionamento), accessori, sosta, rientro a sede. Sui Gantt lo si rende come barra orizzontale. |
| **Sede materiale** | Località di manutenzione del materiale fisico: FIO=Fiorenza, NOV=Novate, CAM=Camnago, LEC=Lecco, CRE=Cremona, ISE=Iseo. 6 sedi per Trenord. Distinta dal deposito del personale. |
| **Builder** | L'algoritmo che, dato un programma + una sede, genera i giri. Dura ~30s-2min, restituisce stats (n_giri_creati, corse_residue, eventi_composizione, warnings). |
| **Motivo chiusura giro** | Perché l'algoritmo ha "chiuso" il giro: `naturale` (treno torna in whitelist sede + cap km raggiunto), `km_cap` (raggiunto cap senza essere in sede), `safety_n_giornate` (cap di sicurezza). I giri non chiusi naturalmente sono un alert per il pianificatore. |

### Cosa NON voglio mai vedere

- **Concetti del 2° ruolo (PdC)**: "Turni PdC", "Violazioni hard",
  "Cascading rev", "Conflict", "9NNNN BG-LE", "Build batch". Tutto
  ciò che riguarda il personale di macchina.
- **Termini inventati**: se vedi nei tuoi mockup precedenti "9NNNN
  BG-LE", "Errori cascading: 2", "Lavori 9NNNN BG-LE" — sono cose
  che non esistono nel nostro dominio. Usa solo terminologia che ti
  do io o che è derivabile dal glossario.
- **Inventare numeri**: ti do KPI realistici nei singoli prompt
  schermata. Non inventare percentuali o conteggi diversi.
- **Layout dashboard "tutto in uno"**: il primo tentativo che mi
  avevi proposto comprimeva 4 funzioni distinte in una pagina. Ogni
  schermata ha **un solo lavoro**.

### Layout di shell (uguale per tutte le schermate)

- **Sidebar fissa 240px** a sinistra con logo ARTURO Business in alto +
  2 voci di navigazione: **Home** (= dashboard) + **Programmi**.
- **Header in alto** (h-14) con breadcrumb a sinistra + utente/azienda
  a destra ("admin · ADMIN · azienda#2 · Esci").
- **Main content fluid** con padding 24-32px.
- **Stati visibili** per ogni schermata: loading (spinner centrato),
  empty (illustrazione minimale + CTA), error (banner rosso con
  retry), success (default).

### Schermate del 1° ruolo (mappa)

| # | Route | Titolo |
|---|---|---|
| 1 | `/pianificatore-giro/dashboard` | Home — overview operativa |
| 2 | `/pianificatore-giro/programmi` | Lista programmi — gestione |
| 3 | `/pianificatore-giro/programmi/:id` | Dettaglio programma — configurazione + run |
| 4 | `/pianificatore-giro/programmi/:id/giri` | Lista giri generati — output del builder |
| 5 | `/pianificatore-giro/giri/:id` | Visualizzatore Gantt di un giro |

**Conferma di aver letto questo brief, poi attendi che ti chieda la
schermata 1.**

---

## Schermata 1 — Dashboard `/pianificatore-giro/dashboard`

### Posizione in app

Pagina di **atterraggio** dopo login per chi ha il ruolo
`PIANIFICATORE_GIRO`. Voce sidebar "Home".

### Lavoro da svolgere in 30 secondi

L'utente atterra qui e vuole rispondere in ordine:

1. **C'è qualcosa che non va?** (warnings dell'ultimo builder, giri
   non chiusi naturalmente, corse residue scoperte)
2. **Quali programmi sono attivi adesso?** (probabile siano 2-3 in
   parallelo: estate + festività + lavori)
3. **Cosa è successo di recente?** (ultimo giro generato, ultimo
   programma pubblicato)
4. **Come accedo all'azione successiva?** (apri programma X, lancia
   un nuovo run su sede Y)

Non è una pagina di consultazione lunga: è una **status page** — 30
secondi di scan e poi click su qualcosa.

### Entità + stato

```ts
programmi_attivi: Programma[]   // tipicamente 1-4
  { id, nome, valido_da, valido_a, stato: "attivo",
    n_giri_totali, n_giri_chiusi_naturalmente, n_corse_residue }

ultimo_run: BuilderRun | null
  { programma_nome, sede_codice, eseguito_at,
    n_giri_creati, n_corse_residue, n_eventi_composizione, warnings: string[] }

alert_giri: AlertGiri
  { n_giri_non_chiusi: number, n_corse_residue_totali: number,
    n_warnings_aperti: number }
```

Esempi realistici (NON inventarne altri):

- **2 programmi attivi**: "Esercizio Estivo 2026" (15/06→14/09, 412
  giri totali, 387 chiusi naturalmente) + "Festività Pasqua 2026"
  (28/03→05/04, 18 giri, 18 chiusi)
- **Ultimo run**: 02/05/2026 14:22, programma "Esercizio Estivo 2026",
  sede FIO, 287 giri creati, 0 corse residue, 3 warnings
- **Alert**: 12 giri non chiusi naturalmente, 0 corse residue totali,
  3 warnings aperti

### Componenti riusabili

`Card`, `Badge` (varianti: default / secondary / success / warning /
destructive / outline / muted), `Button` (primary / outline / ghost),
`Spinner`. Icon: `LayoutDashboard, AlertTriangle, CheckCircle2, Play,
ArrowRight, Clock, ListOrdered`.

### Cosa NON deve esserci

- Niente **timeline annua dei programmi** (vive in `/programmi`)
- Niente concetti PdC: "turni", "violazioni hard", "cascading"
- Niente **mini-Gantt** dell'ultimo giro (vive in `/giri/:id`)
- Niente **form** di creazione/modifica programma (è in `/programmi`)
- Niente attività log lungo (max 4-5 eventi recenti, non 20)

### Suggerimento di IA

Layout 3-zone proposto (puoi alternative motivate):

1. **Banda alert in cima** — visibile solo se
   `alert_giri.n_giri_non_chiusi > 0` o `n_warnings_aperti > 0`.
   Stile amber/destructive con CTA "Vedi dettagli". Altrimenti
   nascosta del tutto.
2. **Card "Programmi attivi"** (1 o 2 colonne in base al numero) con
   per ogni programma: nome, periodo, n_giri totali, KPI piccolo
   (% giri chiusi naturalmente come progress bar sottile), CTA
   "Apri".
3. **Card "Ultimo run del builder"** con: timestamp relativo
   ("2 minuti fa"), programma + sede, n_giri creati, warnings count
   (badge se >0), CTA "Apri lista giri".

Sotto, opzionale: piccolo feed "Attività recenti" (4-5 eventi: pubblicato
programma X, eseguito run Y, archiviato Z) — solo se hai spazio.

---

## Schermata 2 — Lista programmi `/pianificatore-giro/programmi`

### Posizione in app

Voce sidebar "Programmi", oppure click "Apri" su un programma attivo
dalla Dashboard.

### Lavoro da svolgere in 30 secondi

1. **Vedere tutti i programmi** della sua azienda (5-15 in totale,
   mix di stati)
2. **Filtrare per stato** (bozza / attivo / archiviato) o capire
   visivamente la distribuzione
3. **Capire quando si sovrappongono** nel tempo (estate + festività
   + lavori contemporanei)
4. **Aprire** un programma per gestirlo, oppure **crearne uno nuovo**

Tipico operatore: ha 2-3 programmi attivi in parallelo + 1-2 bozze +
N archiviati storici.

### Entità + stato

```ts
Programma {
  id: number                 // es. 4711
  nome: string               // es. "Esercizio Estivo 2026"
  valido_da: string          // ISO date "2026-06-15"
  valido_a: string           // ISO date "2026-09-14"
  stato: "bozza" | "attivo" | "archiviato"
  km_max_ciclo: number | null  // legacy, mostralo discreto
  n_regole: number           // 0..N
  n_giri: number             // se attivo, giri persistiti
  updated_at: string         // ISO datetime
}

Filtro: stato (Tutti | Bozza | Attivo | Archiviato)
```

Esempi realistici (5-7 programmi):

- #4711 "Esercizio Estivo 2026" · 15/06–14/09/2026 · attivo · 8 regole · 412 giri
- #4710 "Esercizio Invernale 2026" · 15/12/2025–14/06/2026 · attivo · 12 regole · 587 giri
- #4715 "Festività Pasqua 2026" · 28/03–05/04/2026 · archiviato · 4 regole · 18 giri
- #4720 "Sostituzione PaSt 2026" · 10/09–22/09/2026 · bozza · 3 regole · 0 giri
- #4708 "Esercizio Estivo 2025" · 15/06–14/09/2025 · archiviato · 8 regole · 398 giri

### Componenti riusabili

`Table, TableHeader, TableRow, TableCell, Badge, Button, Select,
Spinner, Card`. Icon: `Plus, Send, Archive, Calendar, AlertCircle`.

`ProgrammaStatoBadge` già pronto: bozza=secondary/grigio,
attivo=success/verde, archiviato=muted/grigio chiaro.

### Decisione di IA

Voglio una vista a **due tab/segment** in cima:

1. **Tab "Tabella"** — la lista classica: ID, Nome, Periodo, Stato,
   Regole, Giri, Aggiornato, Azioni (Pubblica / Archivia)
2. **Tab "Calendario"** — Gantt orizzontale con righe = programmi,
   asse X = mesi (gen…dic) dell'anno corrente, barre colorate per
   stato. Click sulla barra = apri programma. Mostra anno
   precedente e successivo se ci sono programmi che ricadono lì
   (mini-pulsante navigazione anno).

**Default = Calendario** (è il valore aggiunto rispetto a oggi).
Filtro stato applicato a entrambe le viste.

Pulsante primary in alto a destra: **+ Nuovo programma** (apre
dialog separato — non disegnarlo qui).

### Cosa NON deve esserci

- Niente form inline di edit (apri pagina dedicata o dialog separato)
- Niente colonna km_max_ciclo prominente (è legacy, mostrala discreta
  o nascondila)
- Niente "errori" / "cascading" / concetti PdC
- Niente ricerca full-text avanzata (filtro stato è sufficiente)

---

## Schermata 3 — Dettaglio programma `/pianificatore-giro/programmi/:id`

### Posizione in app

Click su un programma dalla lista o dalla dashboard. È la schermata
operativa dove il pianificatore **configura le regole** di un
programma in bozza, poi lo **pubblica** e **lancia il builder** una
volta attivo.

### Lavoro da svolgere in 30 secondi

Dipende dallo stato del programma:

- **BOZZA** (programma nuovo o in editing): aggiungere/modificare/
  eliminare regole di assegnazione, modificare configurazione
  (periodo, km cap, fascia oraria, sosta extra), pubblicare. Non si
  possono ancora generare giri.
- **ATTIVO**: lanciare il builder per ogni sede, vedere lo storico
  dei run, aprire la lista dei giri generati. Le regole sono
  read-only.
- **ARCHIVIATO**: solo consultazione storica.

Le 3 azioni principali per stato attivo, in ordine di importanza:

1. **Genera giri** (per sede) — l'azione cardine del ruolo
2. **Vedi giri generati** (apre lista, schermata 4)
3. **Archivia / Pubblica** (transizione stato)

### Entità + stato

```ts
ProgrammaDettaglio {
  id, nome, valido_da, valido_a,
  stato: "bozza" | "attivo" | "archiviato",
  km_max_giornaliero: number | null,
  km_max_ciclo: number | null,                // legacy
  fascia_oraria_tolerance_min: number,        // es. 15
  strict_options_json: {                      // 6 flag che governano il rigore del builder
    no_corse_residue: boolean,
    no_overcapacity: boolean,
    no_aggancio_non_validato: boolean,
    no_orphan_blocks: boolean,
    no_giro_appeso: boolean,
    no_km_eccesso: boolean
  },
  stazioni_sosta_extra_json: string[],        // codici stazione, es. ["BOVISA", "GREC"]
  regole: Regola[],
  created_at, updated_at, created_by_user_id
}

Regola {
  id, priorita: number,
  filtri_json: { campo: string, op: string, valore: unknown }[],
  composizione_json: { materiale_tipo_codice: string, n_pezzi: number }[],
  km_max_ciclo: number | null,
  is_composizione_manuale: boolean,
  note: string | null
}

// Storico dei run del builder, per stato ATTIVO:
RunStoria {
  id, sede_codice, eseguito_at, eseguito_by,
  n_giri_creati, n_corse_residue, warnings_count,
  force: boolean   // true = ha rigenerato sovrascrivendo
}[]
```

Esempio realistico:

- Programma "Esercizio Estivo 2026" (id 4711), attivo, periodo
  15/06–14/09/2026
- 8 regole con priorità 10..80, composizioni miste (ETR526×2,
  ATR803×1, ETR425×3)
- Storico run: 5 entry, sedi FIO/NOV/CAM/LEC, varie date
- Strict options: 4 flag su 6 attivi
- 3 stazioni sosta extra: BOVISA, GREC, RHO

### Componenti riusabili

`Card, Badge, Button, Dialog (per Genera giri esiste già — non
disegnarlo), Spinner, Table`. Icon: `Send, Archive, Play, Plus,
Trash2, ArrowLeft, ListOrdered, AlertCircle, History, Settings`.

`RegolaCard` già pronto: mostra priorità + cap km + filtri (chip) +
composizione (chip) + note. Lo riusi così com'è.

### Decisione di IA

Layout proposto a 4 sezioni verticali:

1. **Hero header**: nome programma (h1) + badge stato + periodo +
   1-2 KPI sintetici (regole: 8, giri: 412 se attivo). Bottoni
   azione a destra in funzione dello stato:
   - bozza → "Pubblica" (primary, disabled se 0 regole)
   - attivo → "Genera giri" (primary, apre dialog) + "Vedi giri
     generati" (outline) + "Archivia" (ghost)
   - archiviato → solo "Vedi giri generati"
2. **Card Configurazione** in 2 colonne:
   - sinistra: parametri scalari (periodo, fascia tolerance,
     km/giorno max)
   - destra: strict_options come **lista di toggle/checkbox
     visualizzati come chip on/off** + stazioni sosta extra come
     chip lista. Tutto read-only se non bozza.
3. **Sezione Regole di assegnazione** con header + bottone "+ Nuova
   regola" (solo bozza) + lista verticale di RegolaCard. Empty
   state se 0 regole con CTA "Aggiungi la prima regola".
4. **Sezione Storico run del builder** (solo se stato = attivo) —
   tabella compatta: data/ora, sede, n_giri, residue, warnings,
   link "Apri lista giri filtrata". Se 0 run: empty state "Nessun
   run ancora — clicca Genera giri per il primo".

In alto: **breadcrumb** "← Lista programmi".

### Cosa NON deve esserci

- Niente form di edit del programma inline (le modifiche di
  periodo/nome aprono un dialog)
- Niente form di edit delle regole inline (RegolaCard è read-only,
  l'editor è un dialog separato)
- Niente Gantt giro qui (vive in `/giri/:id`)
- Niente concetti PdC

---

## Schermata 4 — Lista giri generati `/pianificatore-giro/programmi/:id/giri`

### Posizione in app

Da: dettaglio programma → "Vedi giri generati", oppure dal post-run
del builder. È l'**output principale del lavoro del 1° ruolo**:
quello che il pianificatore valuta per capire se la sua
configurazione di regole funziona o se deve ri-generare.

### Lavoro da svolgere in 30 secondi

Operatore tipico: ha generato 412 giri su 6 sedi. Vuole:

1. **Spottare i giri "problematici"**: non chiusi naturalmente,
   km/giorno troppo bassi (sotto-utilizzo), troppo alti (saturazione)
2. **Filtrare per sede** (FIO, NOV, CAM, LEC, CRE, ISE) e per
   **etichetta** (feriale, sabato, domenica, festivo, mix)
3. **Filtrare per motivo chiusura** (naturale, km_cap,
   safety_n_giornate)
4. **Aprire un giro** per vedere il suo Gantt giornata × blocchi
   (schermata 5)
5. Se molti giri sono problematici → tornare al programma e
   ri-generare con regole diverse

### Entità + stato

```ts
Giro {
  id, numero_turno: string,         // "G-FIO-001-ETR204" — formato G-{SEDE}-{NNN}-{MATERIALE}
  tipo_materiale: string,           // "ETR526" / "ATR803" / "MISTO"
  materiale_tipo_codice: string | null,
  numero_giornate: number,          // 1..7
  km_media_giornaliera: number | null,
  km_media_annua: number | null,
  motivo_chiusura: "naturale" | "km_cap" | "safety_n_giornate" | null,
  chiuso: boolean,
  etichetta_tipo: "feriale" | "sabato" | "domenica" | "festivo" | "data_specifica" | "personalizzata",
  etichetta_dettaglio: string | null,   // "12/04/2026" oppure "feriale+festivo"
  created_at: string
}

Filtri:
- sede (multi-select, derivata da numero_turno)
- tipo_materiale (multi-select)
- etichetta_tipo (multi-select)
- motivo_chiusura (multi-select)
- solo non chiusi (toggle)
- ricerca testuale (su numero_turno)
```

KPI in cima (4): giri totali, % chiusi naturalmente, km/giorno
cumulato, n_giri non chiusi (alert se >0).

Esempio realistico:

- 412 giri totali, 387 chiusi naturalmente (94%), 18 km_cap, 7 safety
- Sedi: FIO 142, NOV 89, CAM 67, LEC 48, CRE 41, ISE 25
- Materiali: ETR526 110, ETR425 188, ATR803 57, ETR524 22, MISTO 35

### Componenti riusabili

`Table, Badge, Button, Select, Input (per ricerca), Spinner, Card`.

Già pronti:

- `EtichettaBadge`: feriale=default, sabato=secondary,
  domenica/festivo=warning, data_specifica/personalizzata=outline
- `MotivoChiusuraBadge`: naturale=success, km_cap=outline,
  safety=warning, non chiuso=destructive

Icon: `Filter, Search, ArrowUpDown, AlertTriangle, CheckCircle2,
ArrowLeft`.

### Decisione di IA

Layout proposto:

1. **Breadcrumb**: "← Dettaglio programma · Esercizio Estivo 2026"
2. **Header** con titolo "Giri generati" + nome programma + bottone
   secondario "Apri dettaglio programma"
3. **Banda KPI 4 colonne** (giri totali, % chiusi naturalmente,
   km/giorno cumulato, n_giri non chiusi). Quest'ultimo cliccabile
   = filtra automaticamente solo non chiusi.
4. **Barra filtri sticky**: ricerca + 4 multi-select (sede,
   materiale, etichetta, motivo) + toggle "solo non chiusi" +
   bottone "Azzera filtri" + counter "412 giri (filtra: 28)"
5. **Tabella densa** con colonne: ID, Turno (mono-font), Materiale,
   Sede (estratta da numero_turno), Etichetta (badge), Giornate,
   km/giorno (tabular-nums, allineata destra), km/anno, Chiusura
   (badge), Creato (relative time). Click su riga = apri Gantt
   giro. Default sort: numero_turno asc.

Sotto la tabella: paginazione se >50 righe, sennò mostra tutte.

**Considera** un **pannello laterale destro collassabile**
"Anteprima giro" che mostra il mini-Gantt del giro selezionato — è
il pattern "preview pane" tipo email client. Click su riga apre
preview, doppio click apre la pagina dedicata. Decidi tu se è valore
aggiunto o complica troppo, e annota la scelta nel commento HTML.

### Cosa NON deve esserci

- Niente edit inline (i giri sono read-only — si rigenerano, non si
  modificano)
- Niente concetti PdC
- Niente vista calendario qui (è in `/programmi`)

---

## Schermata 5 — Visualizzatore Gantt giro `/pianificatore-giro/giri/:id`

È la schermata più "densa" del 1° ruolo. Deve **replicare la
leggibilità del PDF Trenord** che gli utenti conoscono da decenni,
ma in versione interattiva.

### Posizione in app

Click su una riga della lista giri (schermata 4).

### Lavoro da svolgere in 30 secondi

L'operatore vuole:

1. **Vedere la sequenza di blocchi** di ogni giornata del giro
   (1-7 giornate, ogni giornata 8-25 blocchi)
2. **Capire le pause** (gap tra un blocco e il successivo) e le
   **transizioni di stazione** (treno arriva a X, poi riparte da Y
   o dalla stessa X)
3. **Distinguere visivamente** corse commerciali (passeggeri) vs
   vuoti tecnici (posizionamento) vs rientro a sede (9NNNN, treno
   virtuale) vs accessori vs sosta
4. **Vedere l'etichetta della giornata** e a quali date concrete si
   applica (`dates_apply_json`)
5. **Ispezionare un blocco** (numero treno, stazioni, ora
   inizio/fine) hover/click
6. **Capire la "salute" del giro**: km totali, n. cambi materiale,
   chiusure forzate

### Entità + stato

```ts
GiroDettaglio {
  id, numero_turno: "G-FIO-001-ETR204",
  tipo_materiale: "ETR526",
  materiale_tipo_codice: "ETR526",
  numero_giornate: 5,
  km_media_giornaliera: 287, km_media_annua: 105000,
  localita_manutenzione_partenza_id, localita_manutenzione_arrivo_id,
  etichetta_tipo: "personalizzata",
  etichetta_dettaglio: "feriale+festivo",
  stato: "pubblicato",
  generation_metadata_json: { motivo_chiusura: "naturale", builder_version: "...", ... },
  created_at, updated_at,
  giornate: Giornata[]
}

Giornata {
  id, numero_giornata: 1..7,
  km_giornata: 287 | null,
  validita_testo: "Circola da L a V escluso festivi" | null,
  dates_apply_json: ["2026-06-15", "2026-06-16", ...],   // su quali date concrete si applica
  dates_skip_json: string[],                              // sospensioni
  blocchi: Blocco[]
}

Blocco {
  id, seq: number,           // 1..N, ordine sequenza
  tipo_blocco: "corsa_commerciale" | "vuoto_tecnico" | "sosta" | "accessori_partenza" | "accessori_arrivo" | "rientro_sede",
  corsa_commerciale_id: number | null,
  corsa_materiale_vuoto_id: number | null,
  stazione_da_codice, stazione_a_codice, stazione_da_nome, stazione_a_nome,
  numero_treno: "28335" | "U28336" | "90001" | null,    // 9NNNN = rientro
  ora_inizio: "06:14" | null,
  ora_fine: "07:42" | null,
  descrizione: string | null,
  is_validato_utente: boolean,
  metadata_json: Record<string, unknown>
}
```

Esempio realistico (giornata 1):

- 06:14 ACCp Fiorenza (40min) → 06:54 partenza
- 06:54 U-28330 vuoto Fiorenza→Mi.Centrale (18min)
- 07:12 28335 Mi.Centrale→Tirano (commerciale, 2h45)
- 09:57 sosta Tirano (45min)
- 10:42 28336 Tirano→Mi.Centrale
- 13:27 sosta Mi.Centrale (32min)
- 13:59 28339 Mi.Centrale→Tirano
- 16:44 sosta Tirano (1h)
- 17:44 28342 Tirano→Mi.Centrale
- 20:29 U-90001 rientro Mi.Centrale→Fiorenza
- 20:51 ACCa Fiorenza

Tipica giornata = 8-15 blocchi, span 04:00-23:59 (con cross-notte
possibile).

### Componenti riusabili

`Card, Badge, Button, Spinner`, eventuale `Tooltip` (sennò
attributo `title`). Icon: `ArrowLeft, AlertCircle, Train, Wrench,
Home, Coffee, Clock`.

**Niente libreria charting esterna**: il Gantt è **HTML+CSS pure**
con div assoluti su una timeline relativa. Asse X = ore della
giornata (04:00 → 04:00 next day, supporta cross-notte).

### Decisione di IA

Riferimento mentale: il PDF Trenord originale è una matrice ore ×
giornate dove ogni cella mostra le tratte (line weight per tipo:
spessa = passeggeri, sottile = vuoto, tratteggiata = sosta). Devi
**migliorare** quel paradigma, non copiarlo pari pari.

Layout proposto:

1. **Breadcrumb**: "← Lista giri · Esercizio Estivo 2026"
2. **Hero**: numero_turno (mono, grande), tipo_materiale (badge),
   etichetta (badge) + dettaglio, n_giornate, km_media_giornaliera
   (tabular-nums), motivo_chiusura (badge stato).
3. **Banda meta** in 2 righe: periodicità testuale del giro, sede
   partenza→arrivo, n_treni totali, n_treni 9NNNN (rientri),
   validato sì/no.
4. **Gantt** — il pezzo grosso. Layout:
   - **Asse X temporale** sticky in alto: ore 04:00, 06, 08, ...
     02:00 (cross-notte). Tick ogni 2 ore, mezza ogni 30 min.
   - **Righe = giornate** (1, 2, 3, 4, 5...). Etichetta a sinistra:
     "G1 · feriale" / "G2 · sabato" / "G3 · personalizzato (12/04)".
   - **Barre = blocchi** posizionate orizzontalmente per
     ora_inizio→ora_fine. Codice colore per tipo_blocco:
     - corsa_commerciale = blu solido
     - vuoto_tecnico = grigio tratteggiato
     - rientro_sede (9NNNN) = viola
     - sosta = bianco con bordo (gap visibile)
     - accessori_partenza/arrivo = arancione piccolo (40 min ai bordi)
   - **Hover blocco** = tooltip con numero_treno, stazioni, orario.
   - **Click blocco** = side panel destro con dettaglio completo.
5. **Pannello destro collassabile** (default chiuso) con dettaglio
   del blocco selezionato — è dove l'utente legge metadata, vede
   `is_validato_utente`, ecc.
6. **Sotto il Gantt**: per ogni giornata, una riga con
   `dates_apply_json` come chip date ("15/06, 16/06, 17/06 +12
   altre"), e `validita_testo` come citazione.

Considera che le **giornate possono essere 1-7**: con 7 il Gantt
sta verticale comodo, con 1 è disteso. Pensa al responsive.

Considera il **cross-notte**: alcuni blocchi finiscono dopo
mezzanotte (es. 23:30→01:15). Decidi se mostri 2 righe per giornata,
asse X esteso 04→04 next day, o un'altra soluzione. Annota la scelta
nel commento HTML.

### Cosa NON deve esserci

- Niente edit dei blocchi (read-only — si rigenera il giro, non si
  edita un blocco)
- Niente concetti PdC ("turno PdC", "violazione condotta")
- Niente "valida" / "approva" giro (non c'è ancora questo flow)
- Niente comparazione fra giri diversi (è un altro caso d'uso, non
  MVP)

---

## Riepilogo per il designer

5 schermate, una alla volta, mockup HTML+Tailwind low-fi con commento
HTML in cima che annota le scelte di IA. Aspetta review prima di
passare alla successiva. Visual polish solo dopo che l'IA è
approvata.

**Prima azione**: conferma di aver letto e dimmi pronto. Poi
attendo il via per la schermata 1.
