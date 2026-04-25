# MODELLO DATI — Ecosistema ARTURO × Trenord (draft v0.1)

> **Stato**: bozza in revisione con l'utente. Niente codice ancora.
> Scopo: disegnare le entità e relazioni che reggono offerta commerciale,
> giro materiale, turno PdC, turno CT, anagrafica personale e loop
> real-time, **prima** di toccare DB o codice.
>
> **Da leggere come**: una mappa, non una specifica finale. Ogni nome,
> attributo o relazione è negoziabile. Quando il modello regge un caso
> reale → si congela. Solo dopo si scrive codice.

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
LIV 2   ROTAZIONE MATERIALE        ← turno materiale Trenord
        come gira il convoglio fisico per coprire le corse
                  │
                  v
LIV 3a  TURNO PdC      LIV 3b  TURNO CT
        chi guida              chi viaggia accompagnando
                  │                  │
                  └────────┬─────────┘
                           v
LIV 4   PERSONA + ASSEGNAZIONE
        anagrafica, qualifiche, sede, indisponibilità,
        chi-fa-quale-giornata-in-quale-data
                           │
                           v
LIV 5   ESERCIZIO REAL-TIME        ← ARTURO Live
        cosa sta succedendo ORA, ritardi, soppressioni
```

**Regola di propagazione**: ogni livello inferiore tiene un riferimento
chiave al livello superiore. Mai dati copiati. Le viste/query
ricostruiscono il dato denormalizzato a richiesta.

---

## 2. Le 5 entità principali

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

**Composizione materiale richiesta** (9 combinazioni
stagione × giorno-tipo): `categoria_posti`, `doppia_composizione`,
`tipologia_treno`, `vincolo_dichiarato`, `categoria_bici`,
`categoria_prm`. Vivono in una tabella figlia `corsa_composizione`
con (corsa_id, stagione, giorno_tipo) come chiave.

**Vincolo**: una corsa commerciale è una "intenzione" — non sa nulla
di chi la guida né di che convoglio fisico la realizza. Quelli sono
LIV 2 e LIV 3.

---

### LIV 2 — `rotazione_materiale`

L'unità del **come gira il convoglio fisico**. Una rotazione = un
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

#### `rotazione_giornata`

Una giornata del ciclo (1, 2, ..., N). Astratta: descrive "il giorno-
tipo G", indipendente da quale data calendario lo realizza.

| Attributo | Tipo | Esempio |
|-----------|------|---------|
| id | PK | |
| rotazione_id | FK → rotazione_materiale | |
| numero_giornata | int | 1, 2, ... |

#### `rotazione_variante`

Per ogni giornata, una o più varianti con calendario di applicabilità
(LV/SAB/DOM/festivi/date specifiche). Una variante = una sequenza
ordinata di blocchi (corsa commerciale o materiale-vuoto-interno).

| Attributo | Tipo | Esempio |
|-----------|------|---------|
| id | PK | |
| rotazione_giornata_id | FK | |
| variant_index | int | 0, 1, 2, ... |
| validita_testo | string | "LV 1:5 esclusi 2-3-4/3" |
| validita_dates_apply | json date[] | derivata, denormalizzata |
| validita_dates_skip | json date[] | derivata, denormalizzata |

#### `rotazione_blocco`

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
| rotazione_blocco_id | FK? | denormalizzato per join veloce |
| stazione_da | string | |
| stazione_a | string | |
| ora_inizio | time | |
| ora_fine | time | |
| accessori_maggiorati | bool | preriscaldamento ●NUMERO |

**Vincolo critico**: un blocco PdC di tipo CONDOTTA o VETTURA su una
corsa commerciale **deve coincidere temporalmente** con un
`rotazione_blocco` che copre quella stessa corsa. È quello che chiude
il triangolo PdE → MATERIALE → PdC.

---

### LIV 3b — `turno_ct` (nuovo)

L'unità del **chi viaggia accompagnando come Capotreno**. Struttura
parallela a `turno_pdc` ma con normativa diversa (più semplice: niente
condotta-max, niente cambio volante; restano refezione, ore
settimanali, riposi).

| Attributo | Tipo | Esempio |
|-----------|------|---------|
| id | PK | |
| codice | string | |
| impianto | string | "MILANO PORTA GARIBALDI" |
| ciclo_giorni | int | |
| ... | ... | (analogo a turno_pdc, semplificato) |

`turno_ct_giornata` e `turno_ct_blocco` analoghi a PdC, con vincoli
allentati (no condotta_min, sì lavoro_min).

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

### Esempio 2 — rotazione materiale Turno 1100

```
rotazione_materiale {
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

rotazione_giornata { id: 200, rotazione_id: 100, numero_giornata: 1 }
rotazione_giornata { id: 201, rotazione_id: 100, numero_giornata: 2 }

rotazione_variante {
  id: 300
  rotazione_giornata_id: 200
  variant_index: 0
  validita_testo: "LV 1:5 esclusi 2-3-4/3"
}

rotazione_blocco { variante_id: 300, seq: 1, tipo_blocco: "corsa_commerciale",
                   corsa_commerciale_id: <treno 10606>, ... }
rotazione_blocco { variante_id: 300, seq: 2, tipo_blocco: "corsa_commerciale",
                   corsa_commerciale_id: <treno 10603>, ... }
rotazione_blocco { variante_id: 300, seq: 3, tipo_blocco: "corsa_commerciale",
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
`corsa_commerciale_id` con il `rotazione_blocco` corrispondente nel
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
| `material_turn` table | Diventa `rotazione_materiale` (estesa) |
| `train_segment` table | Si **scompone** in `corsa_commerciale` (la parte commerciale) + `rotazione_blocco` (la parte di sequenza) |
| `day_variant` table | Diventa `rotazione_variante` |
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
   `rotazione_blocco` con la stessa `corsa_commerciale_id` la cui
   variante calendario sovrappone quella del PdC.
2. **Coerenza temporale**: ora_inizio/fine di un blocco PdC su una
   corsa = ora_partenza/arrivo della corsa stessa (tolleranza ±1 min
   per arrotondamenti).
3. **Una persona, una giornata**: per una persona e una data, esiste al
   massimo una `assegnazione_giornata` con stato non-annullato.
4. **Indisponibilità rispettate**: se persona X ha
   `indisponibilita_persona` approvata su data D, non può avere
   `assegnazione_giornata` su D.
5. **Stessa azienda**: una `rotazione_materiale` può consumare solo
   `corsa_commerciale` della stessa `azienda`. Un `turno_pdc` può
   coprire solo `rotazione_materiale` della stessa `azienda`.

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

## 8. Cosa decidere prima di passare al codice

Domande aperte da risolvere con l'utente leggendo questo doc:

1. **Granularità periodicità corsa**: tenerla come testo + array di
   date denormalizzato (semplice, calcolabile da `Gg_*` mensili)?
   Oppure normalizzarla con regole ricorrenti (DSL tipo cron)?
   → Proposta: **denormalizzata in `validita_dates_apply` JSON**.
   Calcoliamo una volta all'import, query semplici dopo.
2. **Materiale vuoto**: nel PdE non c'è. Va in tabella separata
   `corsa_materiale_vuoto` (sorella di `corsa_commerciale`) o come
   tipo enumerato dentro `corsa_commerciale`?
   → Proposta: **tabella sorella**, perché ha attributi diversi
   (no posti, no biglietto).
3. **Multi-tenancy ora o dopo**: introduciamo `azienda` da subito o
   solo Trenord per semplicità v1?
   → Proposta: **`azienda` da subito come campo, default 'trenord'**.
   Costo zero ora, riscrittura zero dopo.
4. **Turno CT v0**: lo introduciamo già nel modello o lo aggiungiamo
   in fase 2?
   → Proposta: **già nel modello** (giusto le tabelle vuote), così
   l'API e le viste lo prevedono. Implementazione effettiva può
   slittare.
5. **Persone/assegnazioni v0**: quanto in dettaglio? Solo anagrafica
   minima o anche turni festivi/notturni separati?
   → Proposta: **minimo solido** (persona + assegnazione +
   indisponibilità). Tutto il resto viene dopo.

---

## 9. Prossimo step (solo dopo sblocco di questo doc)

Quando l'utente legge e dà OK al modello (o lo corregge), il prossimo
step è **uno solo**:

> Scrivere `docs/MIGRAZIONE-DATI.md`: tabella per tabella, il piano di
> migrazione DB. Nessuna riga di codice ancora.

Solo dopo la migrazione documentata e approvata si tocca il DB.

---

**Fine draft v0.1.** Da revisionare con l'utente.
