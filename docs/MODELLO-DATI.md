# MODELLO DATI — Ecosistema ARTURO × Trenord (draft v0.2)

> **Stato**: bozza in revisione con l'utente. Niente codice ancora.
> Scopo: disegnare le entità e relazioni che reggono offerta commerciale,
> giro materiale, turno PdC, anagrafica personale e loop
> real-time, **prima** di toccare DB o codice.
>
> **Da leggere come**: una mappa, non una specifica finale. Ogni nome,
> attributo o relazione è negoziabile. Quando il modello regge un caso
> reale → si congela. Solo dopo si scrive codice.

---

## 0. Decisioni v0.2 (recepite dall'utente)

Decisioni prese il 2026-04-25 dopo revisione v0.1:

| Tema | Decisione |
|------|-----------|
| **Periodicità corsa** | **Strada A — denormalizzata**. All'import del PdE, per ogni corsa si calcola l'elenco completo di date in cui circola (`valido_in_date` JSON). Query SI/NO immediate. |
| **Materiale vuoto** | Tabella sorella `corsa_materiale_vuoto`. **Non importato dal PdE — generato dal nostro algoritmo di costruzione giro materiale**. Campo `origine` traccia la provenienza. |
| **Multi-tenancy `azienda`** | **Strada A — campo da subito**. Default `'trenord'`, predisposto per SAD/Trenitalia/Tper futuri senza riscrittura. |
| **Turno CT** | **Differito**. Base struttura simile al PdC con piccole varianti contrattuali. In v0 si modella solo PdC, il modello CT è un punto di estensione esplicito (§3b di questo doc). |
| **Anagrafica persone** | Minimo solido (persona + assegnazione + indisponibilità). |
| **Validità 12+ mesi con revisioni** | Aggiunta entità `revisione_turno`: lega un turno PdC o un giro materiale a una versione datata. Due "Turno 1100" con date diverse = revisioni dello stesso turno, non turni separati. |

---

## 1. Filosofia

**Una piramide, non una rete.** Ogni livello consuma quello sopra e
**non duplica** i dati. Cambiare una corsa commerciale → propagazione
discendente automatica. Vedere un evento ARTURO → risali deterministico
a chi è coinvolto.

```
LIV 1   CORSA COMMERCIALE          ← PdE (Programma di Esercizio)
        cosa fa l'azienda davanti al cliente
                  │
                  v
LIV 2   GIRO MATERIALE        ← turno materiale Trenord
        come gira il convoglio fisico per coprire le corse
                  │
                  v
LIV 3   TURNO PdC                  ← turno personale di macchina
        chi guida                    [LIV 3b TURNO CT differito a v1]
                  │
                  v
LIV 4   PERSONA + ASSEGNAZIONE
        anagrafica, qualifiche, sede, indisponibilità,
        chi-fa-quale-giornata-in-quale-data
                  │
                  v
LIV 5   ESERCIZIO REAL-TIME        ← ARTURO Live
        cosa sta succedendo ORA, ritardi, soppressioni
```

**Nota CT**: il LIV 3b (turno_ct) è strutturalmente parallelo al LIV 3a
(turno_pdc) — stesso scheletro, normativa più leggera. Si modellerà in
v1 quando definiamo le differenze contrattuali. La piramide è
predisposta per accoglierlo senza riscritture.

**Regola di propagazione**: ogni livello inferiore tiene un riferimento
chiave al livello superiore. Mai dati copiati. Le viste/query
ricostruiscono il dato denormalizzato a richiesta.

---

## 2. Le 4 entità principali (v0)

### LIV 1 — `corsa_commerciale`

L'unità atomica del **cosa va fatto** dal punto di vista del cliente.
Ogni riga = una corsa giornaliera-tipo (es. "treno 13 Milano Cadorna →
Laveno, partenza 06:39, feriale, da X dicembre 2025 a Y dicembre 2026").

| Attributo | Tipo | Sorgente | Note |
|-----------|------|----------|------|
| id | PK |  | |
| numero_treno | string | PdE col[7] | "13", "10603", ecc. |
| rete | enum | PdE col[8] | FN, RFI |
| numero_treno_rfi | string? | PdE col[11] | quando differisce |
| numero_treno_fn | string? | PdE col[12] | quando differisce |
| categoria | enum | PdE col[14] | R, RE, S, ECC |
| codice_linea | string | PdE col[18] | "R22", "RE1" |
| direttrice | string | PdE col[21] | nome direttrice |
| codice_origine | string | PdE col[22] | "S01066" canonico |
| stazione_origine | string | PdE col[23] | "MILANO CADORNA" |
| codice_destinazione | string | PdE col[24] | "S01747" canonico |
| stazione_destinazione | string | PdE col[25] | "LAVENO MOMBELLO LAGO" |
| ora_partenza | time | PdE col[26] | "06:39:00" |
| ora_arrivo | time | PdE col[27] | "08:23:00" |
| min_tratta | int | PdE col[34] | 104 |
| km_tratta | float | PdE col[36] | 72.152 |
| valido_da | date | PdE col[4] | inizio orario |
| valido_a | date | PdE col[5] | fine orario |
| codice_periodicita | string | PdE col[38] | testo tecnico |
| periodicita_breve | string | PdE col[40] | umano |
| treno_garantito_feriale | bool | PdE col[41] | |
| treno_garantito_festivo | bool | PdE col[123] | |
| fascia_oraria | enum | PdE col[42] | FR, FNR |
| (giorni_per_mese) | embed | PdE col[98..113] | calendar nativo |
| **valido_in_date** | json date[] | **derivato all'import** | **dec. #1**: lista completa date di circolazione, es. `["2025-12-14", "2025-12-15", ...]`. Query "circola il D?" = lookup, no calcolo |
| azienda | string | default `'trenord'` | **dec. #3**: multi-tenancy |

**Composizione materiale richiesta** (9 combinazioni
stagione × giorno-tipo): `categoria_posti`, `doppia_composizione`,
`tipologia_treno`, `vincolo_dichiarato`, `categoria_bici`,
`categoria_prm`. Vivono in una tabella figlia `corsa_composizione`
con (corsa_id, stagione, giorno_tipo) come chiave.

**Vincolo**: una corsa commerciale è una "intenzione" — non sa nulla
di chi la guida né di che convoglio fisico la realizza. Quelli sono
LIV 2 e LIV 3.

#### `corsa_materiale_vuoto` *(tabella sorella)*

**Decisione #2**: i treni di servizio (numeri come `28183`, `93058`,
`U316`) **non sono nel PdE** — sono corse di posizionamento del
materiale fisico, generate dal nostro algoritmo di costruzione del giro
materiale. Per non confonderli con le corse commerciali vivono in una
tabella separata.

| Attributo | Tipo | Esempio |
|-----------|------|---------|
| id | PK | |
| numero_treno_vuoto | string | "U316", "28183", "93058" |
| stazione_origine | string | "FIORENZA" |
| stazione_destinazione | string | "MILANO BOVISA" |
| ora_partenza | time | |
| ora_arrivo | time | |
| min_tratta | int | |
| km_tratta | float | |
| **origine** | enum | `importato_pde` (raro), `generato_da_giro_materiale` (default), `manuale` |
| giro_materiale_id | FK? | popolato se generato per uno specifico giro |
| valido_in_date | json date[] | derivato come per `corsa_commerciale` |
| azienda | string | default `'trenord'` |

L'algoritmo di costruzione giro materiale, quando deve spostare il
convoglio dal punto A al punto B per coprire la corsa successiva,
**inventa** un `corsa_materiale_vuoto` con `origine='generato_da_giro_materiale'`
e lo collega al `giro_blocco` corrispondente.

---

### LIV 2 — `giro_materiale`

L'unità del **come gira il convoglio fisico**. Un giro materiale = un
ciclo ripetitivo di N giornate per un singolo tipo materiale.

| Attributo | Tipo | Esempio |
|-----------|------|---------|
| id | PK | |
| numero_turno | string | "1100", "1130" |
| validita_codice | string | "P", "I", "E" |
| tipo_materiale | string | "1npBDL+5nBC-clim+1E464N" |
| descrizione_materiale | string | "PR 270 - PPF 120 - m. 174 - MD" |
| numero_giornate | int | 2, 9, 10 |
| km_media_giornaliera | float | 270.69 |
| km_media_annua | float | 154832.47 |
| sede_omv | string | "TRENORD IMPMAN MILANO FIOREN" |
| posti_1cl | int | 0 |
| posti_2cl | int | 470 |
| valido_da | date | |
| valido_a | date | |
| azienda | enum | trenord, sad, ecc |

**Composizione fisica** (figlia, `rotazione_pezzo`):
una riga per ogni pezzo del materiale e quanti pezzi servono in totale
per coprire la rotazione (es. Turno 1100 → 2× npBDL, 10× nBC-clim,
2× E464N, perché 2 giornate × 1 convoglio).

#### `giro_giornata`

Una giornata del ciclo (1, 2, ..., N). Astratta: descrive "il giorno-
tipo G", indipendente da quale data calendario lo realizza.

| Attributo | Tipo | Esempio |
|-----------|------|---------|
| id | PK | |
| rotazione_id | FK → giro_materiale | |
| numero_giornata | int | 1, 2, ... |

#### `giro_variante`

Per ogni giornata, una o più varianti con calendario di applicabilità
(LV/SAB/DOM/festivi/date specifiche). Una variante = una sequenza
ordinata di blocchi (corsa commerciale o materiale-vuoto-interno).

| Attributo | Tipo | Esempio |
|-----------|------|---------|
| id | PK | |
| giro_giornata_id | FK | |
| variant_index | int | 0, 1, 2, ... |
| validita_testo | string | "LV 1:5 esclusi 2-3-4/3" |
| validita_dates_apply | json date[] | derivata, denormalizzata |
| validita_dates_skip | json date[] | derivata, denormalizzata |

#### `giro_blocco`

Un singolo elemento della sequenza giornaliera della variante.

| Attributo | Tipo | Esempio |
|-----------|------|---------|
| id | PK | |
| variante_id | FK | |
| seq | int | ordine 1, 2, 3... |
| tipo_blocco | enum | corsa_commerciale, materiale_vuoto, sosta_disponibile, manovra |
| corsa_commerciale_id | FK? | popolato se tipo=corsa_commerciale |
| numero_treno_vuoto | string? | "U93058", "28220" se tipo=materiale_vuoto |
| stazione_da | string | per soste e manovre |
| stazione_a | string | |
| ora_inizio | time | |
| ora_fine | time | |
| descrizione | string | "CREMONA(DISPONIBILE)CREMONA" |

**Vincolo**: per un blocco di tipo `corsa_commerciale`, la coppia
(stazione_da/a, ora_inizio/fine) **deve coincidere** con la corsa
linkata. È la query di consistenza più importante del modello — se
fallisce, qualcosa è incoerente tra PdE e turno materiale.

---

### LIV 3a — `turno_pdc`

L'unità del **chi guida**. Già esiste come `pdc_turn` nello schema
attuale, va arricchita.

| Attributo | Tipo | Esempio |
|-----------|------|---------|
| id | PK | |
| codice | string | "ALOR_C [65046]" |
| impianto | string | "ALESSANDRIA" |
| profilo | enum | Condotta, Manovra, ecc |
| ciclo_giorni | int | 5+2 = 7 |
| valido_da | date | |
| valido_a | date | |
| azienda | enum | |

#### `turno_pdc_giornata` (esiste già come `pdc_turn_day`)

Una giornata del ciclo PdC: G1...G5 + 2 riposi.

| Attributo | Tipo | Esempio |
|-----------|------|---------|
| id | PK | |
| turno_pdc_id | FK | |
| numero_giornata | int | 1..7 |
| variante_calendario | enum | LMXGV, S, D, SD, F |
| start_time | time | |
| end_time | time | |
| prestazione_min | int | |
| condotta_min | int | |
| refezione_min | int | |
| is_riposo | bool | |
| is_disponibile | bool | S.COMP |

#### `turno_pdc_blocco` (esiste già come `pdc_block`)

Un evento dentro la giornata PdC: condotta su treno X, vettura su
treno Y, refezione, accessori, CV, ecc.

| Attributo | Tipo | Esempio |
|-----------|------|---------|
| id | PK | |
| giornata_id | FK | |
| seq | int | |
| tipo_evento | enum | CONDOTTA, VETTURA, REFEZ, ACCp, ACCa, CVp, CVa, PK |
| corsa_commerciale_id | FK? | se evento è su corsa nota (CONDOTTA/VETTURA) |
| materiale_vuoto_id | FK? | se evento è su treno vuoto |
| giro_blocco_id | FK? | denormalizzato per join veloce |
| stazione_da | string | |
| stazione_a | string | |
| ora_inizio | time | |
| ora_fine | time | |
| accessori_maggiorati | bool | preriscaldamento ●NUMERO |

**Vincolo critico**: un blocco PdC di tipo CONDOTTA o VETTURA su una
corsa commerciale **deve coincidere temporalmente** con un
`giro_blocco` che copre quella stessa corsa. È quello che chiude
il triangolo PdE → MATERIALE → PdC.

---

### LIV 3b — `turno_ct` *(differito a v1)*

**Decisione utente (v0.2)**: il modello CT è strutturalmente analogo a
`turno_pdc` con normativa contrattuale più leggera (niente condotta-max,
niente CV; restano refezione, ore settimanali, riposi). Verrà definito
in fase v1, dopo la definizione precisa delle differenze contrattuali.

In v0 quindi: nessuna tabella CT viene creata. Le tabelle PdC sono
disegnate in modo da essere replicabili pari-pari per CT con campi
opzionali (es. `condotta_min` nullable). Punto di estensione esplicito.

---

### LIV 4 — `persona`, `assegnazione`, `indisponibilita`

Anagrafica e pianificazione. **Modulo nuovo, oggi non esiste.**

#### `persona`

| Attributo | Tipo | Esempio |
|-----------|------|---------|
| id | PK | |
| codice_dipendente | string | "M12345" |
| nome | string | |
| cognome | string | |
| profilo | enum | PdC, CT, MANOVRA, COORD |
| sede_residenza | FK → impianto | "ALESSANDRIA" |
| qualifiche | json string[] | ["AB-CDE-FGH", "linea-X"] |
| matricola_attiva | bool | |
| data_assunzione | date | |

#### `assegnazione_giornata`

Lega una persona a una specifica giornata di un turno (PdC o CT) in
una data calendario specifica. È l'unità della **pianificazione
mensile**.

| Attributo | Tipo | Esempio |
|-----------|------|---------|
| id | PK | |
| persona_id | FK | |
| data | date | "2026-04-25" |
| turno_pdc_giornata_id | FK? | uno dei due popolato |
| turno_ct_giornata_id | FK? | |
| stato | enum | pianificato, confermato, sostituito, annullato |
| sostituisce_persona_id | FK? | per cambi turno |
| note | string | |

#### `indisponibilita_persona`

Periodi in cui la persona non è assegnabile.

| Attributo | Tipo | Esempio |
|-----------|------|---------|
| id | PK | |
| persona_id | FK | |
| tipo | enum | ferie, malattia, congedo, ROL, sciopero, formazione |
| data_inizio | date | |
| data_fine | date | |
| approvato | bool | |

**Vincolo**: una `assegnazione_giornata` su data D non può esistere
se per la stessa persona c'è un `indisponibilita_persona` che copre D
con `approvato=true`.

---

### LIV 5 — eventi real-time (ARTURO Live)

**Non si memorizza qui.** Il loop ARTURO è un consumatore: legge
LIV 1-4 dal nostro DB, riceve dati real-time da `live.arturo.travel`,
e produce **viste** (dashboard, notifiche). Eventuali ritardi/soppressioni
restano in ARTURO, non duplicati nel nostro modello.

L'unica cosa che potremmo persistere è un `evento_eccezione` (es. "il
treno 10603 del 25/04 era guidato da Mario Rossi al posto di Luigi
Bianchi") quando la realtà devia dalla pianificazione. Ma è opzionale
e va ragionato dopo.

---

### Entità trasversale — `revisione_turno`

**Decisione #5 (validità 12+ mesi con revisioni)**: i turni materiali
e i turni PdC vengono pubblicati con validità lunga (es. 14/12/2025 →
12/12/2026), ma **all'interno di quella validità** subiscono revisioni
periodiche (es. il PDF "Turno Materiale Trenord dal 2/3/26" è una
revisione del turno principale 2025-2026).

Due turni con stesso codice (es. due "Turno 1100") ma date depositata
diverse **non sono turni separati**: sono **revisioni dello stesso
turno**. Il modello deve riflettere questo.

| Attributo | Tipo | Esempio |
|-----------|------|---------|
| id | PK | |
| target_tipo | enum | `giro_materiale`, `turno_pdc` |
| target_id | FK | id del giro o del turno PdC |
| versione | int | 1, 2, 3... ordine cronologico |
| data_deposito | date | "2026-02-25" (PDF "Depositata il 25/02/2026") |
| valida_da | date | "2026-03-02" |
| valida_a | date | "2026-12-12" o NULL se ultima |
| source_file | string | path PDF originale |
| imported_at | datetime | |
| note | string | descrizione cambiamenti rispetto a precedente |

**Regola**: per ogni `target` e per una qualsiasi data D, esiste **una
sola** revisione attiva (quella con `valida_da ≤ D ≤ valida_a` o
`valida_a IS NULL`). Le query "qual è il turno 1100 il 15/04/2026?"
risolvono automaticamente alla revisione corretta.

Quando arriva una nuova revisione: la precedente non viene cancellata,
ma chiusa (`valida_a` settato al giorno prima della nuova `valida_da`).
Storia preservata, query coerenti.

---

## 3. Entità di supporto

### `stazione`

Anagrafica canonica.

| Attributo | Tipo | Esempio |
|-----------|------|---------|
| codice | PK | "S01066" |
| nome | string | "MILANO CADORNA" |
| nomi_alternativi | json string[] | ["MI.CAD", "MI CADORNA", "MILANO C."] |
| rete | enum | RFI, FN |
| sede_deposito | bool | true se è sede PdC/CT |

Risolve il problema attuale di nomi-stazione fuzzy ("MILANO P.
GARIBALDI" vs "MI.P.GAR" vs "MILANO PORTA GARIBALDI").

### `materiale_tipo`

Anagrafica dei rotabili.

| Attributo | Tipo | Esempio |
|-----------|------|---------|
| codice | PK | "Coradia526", "Vivalto", "TAF" |
| nome_commerciale | string | "Coradia 526" |
| componenti | json | descrizione tecnica |
| velocita_max | int | km/h |
| posti_per_pezzo | int | |

### `impianto` / `deposito`

Esiste già come `depot`. Va esteso con:
- `tipi_personale_ammessi` (PdC, CT, ENTRAMBI)
- `materiali_ammessi` (FK → `materiale_tipo`)
- `linee_ammesse`

### `azienda`

Multi-tenancy: Trenord, SAD, Trenitalia... Tutte le entità
LIV 1-4 portano un `azienda_id`.

| Attributo | Tipo | Esempio |
|-----------|------|---------|
| codice | PK | "trenord" |
| nome | string | "Trenord SRL" |
| normativa_pdc | json | regole specifiche (8h30, 5h30, ...) |

Per ora normativa_pdc è hardcoded; quando avremo SAD diventerà JSON
configurabile.

---

## 4. Esempi reali

### Esempio 1 — corsa commerciale dal PdE

```
corsa_commerciale {
  id: 7421
  numero_treno: "10603"
  rete: "FN"
  categoria: "R"
  codice_linea: "R22"
  direttrice: "LAVENO-VARESE-SARONNO-MILANO"
  codice_origine: "S01066"
  stazione_origine: "MILANO CADORNA"
  codice_destinazione: "S01747"
  stazione_destinazione: "LAVENO MOMBELLO LAGO"
  ora_partenza: "06:39:00"
  ora_arrivo: "08:23:00"
  min_tratta: 104
  km_tratta: 72.152
  valido_da: 2025-12-14
  valido_a: 2026-12-31
  ...
}
```

### Esempio 2 — giro materiale Turno 1100

```
giro_materiale {
  id: 100
  numero_turno: "1100"
  validita_codice: "P"
  tipo_materiale: "1npBDL+5nBC-clim+1E464N"
  descrizione_materiale: "PR 270 - PPF 120 - m. 174 - MD"
  numero_giornate: 2
  km_media_giornaliera: 270.69
  km_media_annua: 154832.47
  sede_omv: "TRENORD IMPMAN MILANO FIOREN"
  azienda: "trenord"
}

giro_giornata { id: 200, rotazione_id: 100, numero_giornata: 1 }
giro_giornata { id: 201, rotazione_id: 100, numero_giornata: 2 }

giro_variante {
  id: 300
  giro_giornata_id: 200
  variant_index: 0
  validita_testo: "LV 1:5 esclusi 2-3-4/3"
}

giro_blocco { variante_id: 300, seq: 1, tipo_blocco: "corsa_commerciale",
                   corsa_commerciale_id: <treno 10606>, ... }
giro_blocco { variante_id: 300, seq: 2, tipo_blocco: "corsa_commerciale",
                   corsa_commerciale_id: <treno 10603>, ... }
giro_blocco { variante_id: 300, seq: 3, tipo_blocco: "corsa_commerciale",
                   corsa_commerciale_id: <treno 10610>, ... }
...
```

### Esempio 3 — turno PdC ALOR_C giornata 2 LMXGV

```
turno_pdc { id: 50, codice: "ALOR_C [65046]", impianto: "ALESSANDRIA", ... }

turno_pdc_giornata {
  id: 60, turno_pdc_id: 50, numero_giornata: 2,
  variante_calendario: "LMXGV", prestazione_min: 497, condotta_min: 173
}

turno_pdc_blocco { giornata_id: 60, seq: 1, tipo_evento: "VETTURA",
                   corsa_commerciale_id: <treno 11055>, stazione_da: "AL",
                   stazione_a: "VOGHERA" }
turno_pdc_blocco { giornata_id: 60, seq: 2, tipo_evento: "CONDOTTA",
                   corsa_commerciale_id: <treno 2316>, ... }
turno_pdc_blocco { giornata_id: 60, seq: 3, tipo_evento: "CONDOTTA",
                   materiale_vuoto_id: <U316>, ... }
turno_pdc_blocco { giornata_id: 60, seq: 4, tipo_evento: "VETTURA",
                   corsa_commerciale_id: <treno 59AS>, ... }
turno_pdc_blocco { giornata_id: 60, seq: 5, tipo_evento: "VETTURA",
                   corsa_commerciale_id: <treno 24135>, ... }
turno_pdc_blocco { giornata_id: 60, seq: 6, tipo_evento: "REFEZ",
                   stazione_da: "MILANO ROGOREDO", durata: 30 }
turno_pdc_blocco { giornata_id: 60, seq: 7, tipo_evento: "CONDOTTA",
                   corsa_commerciale_id: <treno 10045>, ... }
turno_pdc_blocco { giornata_id: 60, seq: 8, tipo_evento: "CVa",
                   corsa_commerciale_id: <treno 10062>, stazione_da: "AL" }
```

Tutti i blocchi su corse commerciali condividono la **stessa**
`corsa_commerciale_id` con il `giro_blocco` corrispondente nel
turno materiale che fisicamente fa quel treno. Triangolo chiuso.

### Esempio 4 — assegnazione persona a giornata

```
persona {
  id: 1024,
  codice_dipendente: "M00845",
  nome: "Mario", cognome: "Rossi",
  profilo: "PdC",
  sede_residenza: "ALESSANDRIA"
}

assegnazione_giornata {
  persona_id: 1024,
  data: 2026-04-27,
  turno_pdc_giornata_id: 60,    // ← G2 LMXGV di ALOR_C
  stato: "confermato"
}
```

Da qui derivo automaticamente: chi guida il treno 2316 il 27/04? →
join con `turno_pdc_blocco` su `corsa_commerciale_id` → Mario Rossi.

---

## 5. Cosa sopravvive del codice attuale

| Componente attuale | Destino |
|--------------------|---------|
| `material_turn` table | Diventa `giro_materiale` (estesa) |
| `train_segment` table | Si **scompone** in `corsa_commerciale` (la parte commerciale) + `giro_blocco` (la parte di sequenza) |
| `day_variant` table | Diventa `giro_variante` |
| `pdc_turn` + `pdc_turn_day` + `pdc_block` | Restano, rinominati a `turno_pdc*` (italiano), arricchiti con FK a `corsa_commerciale` |
| `pdc_train_periodicity` | Deprecato — la periodicità sta nella `corsa_commerciale` |
| `train_route_cache` | Resta come cache ARTURO Live |
| `cv_ledger` | Resta |
| `users`, `depot`, `depot_enabled_*` | Restano, `depot` esteso con `tipi_personale_ammessi` |
| `pdf_parser.py` | Resta come **importer** di rotazioni materiali (LIV 2), non più fonte primaria di treni |
| `turno_pdc_parser.py` | Resta come importer turni PdC (LIV 3a) |
| `auto_builder.py` / `build_from_material.py` | Restano come **generatori** sopra il modello, non sotto |
| `TurnValidator` (rules.py) | Resta, ma valida `turno_pdc_giornata` |
| Frontend Gantt | Si adatta a leggere dal nuovo modello (probabilmente solo cambio source di fetch) |

**Nessuna riscrittura totale.** Il parser PDF Gantt e il TurnValidator
sono il valore principale del progetto e restano. Cambia il modello che
ci sta sotto.

---

## 6. Vincoli di consistenza

I 5 vincoli che il sistema deve sempre rispettare. Sono i test di
salute del DB.

1. **Triangolo chiuso**: per ogni `turno_pdc_blocco` di tipo
   CONDOTTA/VETTURA con `corsa_commerciale_id` valorizzato, esiste un
   `giro_blocco` con la stessa `corsa_commerciale_id` la cui
   variante calendario sovrappone quella del PdC.
2. **Coerenza temporale**: ora_inizio/fine di un blocco PdC su una
   corsa = ora_partenza/arrivo della corsa stessa (tolleranza ±1 min
   per arrotondamenti).
3. **Una persona, una giornata**: per una persona e una data, esiste al
   massimo una `assegnazione_giornata` con stato non-annullato.
4. **Indisponibilità rispettate**: se persona X ha
   `indisponibilita_persona` approvata su data D, non può avere
   `assegnazione_giornata` su D.
5. **Stessa azienda**: una `giro_materiale` può consumare solo
   `corsa_commerciale` della stessa `azienda`. Un `turno_pdc` può
   coprire solo `giro_materiale` della stessa `azienda`.

---

## 7. Cosa NON è in questo modello

Esplicito, per evitare scope creep:

- **Storia ritardi/soppressioni** — vive in ARTURO Live, non
  duplicato.
- **Audit log** delle modifiche — utile, ma è feature trasversale,
  non parte del modello di dominio.
- **Comunicazioni operative** (avvisi, ordini di servizio) — modulo
  separato.
- **Manutenzione materiale** (corse di posizionamento OMV per
  manutenzione) — il PdE non le contiene; vanno modellate separatamente
  se servono.
- **Biglietteria/tariffe** — fuori scope (è altro mondo).
- **Sicurezza/abilitazioni dettagliate per linea** — esiste già
  `depot_enabled_line`, va integrato ma non ridisegnato qui.

---

## 8. Decisioni risolte (v0.2)

Tutte le domande aperte di v0.1 sono state risolte dall'utente il
2026-04-25. Riepilogo per riferimento storico:

1. **Granularità periodicità corsa**: ✅ **Strada A** — denormalizzata
   in `valido_in_date` JSON. All'import del PdE si calcola la lista
   completa di date di circolazione per ogni corsa, query SI/NO
   immediate.
2. **Materiale vuoto**: ✅ **Tabella sorella** `corsa_materiale_vuoto`,
   con campo `origine` per distinguere `importato_pde` (raro) vs
   `generato_da_giro_materiale` (default — l'algoritmo li inventa).
3. **Multi-tenancy `azienda`**: ✅ **Strada A** — campo da subito su
   ogni tabella, default `'trenord'`.
4. **Turno CT**: ⏸️ **Differito a v1**. In v0 si modella solo `turno_pdc`
   con campi disegnati per essere replicabili (es. `condotta_min`
   nullable). Punto di estensione esplicito in §LIV 3b.
5. **Persone/assegnazioni**: ✅ **Minimo solido** — `persona` +
   `assegnazione_giornata` + `indisponibilita_persona`, niente di più
   in v0.

**Aggiunta v0.2**: entità trasversale `revisione_turno` per gestire la
validità lunga (12+ mesi) con revisioni interne — vedi §LIV 5+.

---

## 9. Prossimo step (solo dopo sblocco di questo doc)

Quando l'utente legge e dà OK al modello (o lo corregge), il prossimo
step è **uno solo**:

> Scrivere `docs/MIGRAZIONE-DATI.md`: tabella per tabella, il piano di
> migrazione DB. Nessuna riga di codice ancora.

Solo dopo la migrazione documentata e approvata si tocca il DB.

---

**Fine draft v0.1.** Da revisionare con l'utente.
