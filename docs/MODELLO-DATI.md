# MODELLO DATI — Ecosistema ARTURO × Trenord (draft v0.5)

## ⚠️ Manifesto — cos'è e cos'NON è questo modello (v0.5)

**NON è un calco del sistema Trenord.** Non stiamo replicando il loro
DB, non stiamo importando il loro formato. Il modello è di **ARTURO ×
Trenord**, non di Trenord-dentro-ARTURO.

**È un modello indipendente, ispirato dalla realtà operativa** che
osserviamo nei loro PDF (turno materiale, turno PdC) e nel loro PdE.
Tutti i dati estratti (anagrafica depositi, dotazione materiale, regole
operative) servono **a capire come funziona davvero un'azienda
ferroviaria**, per disegnare entità che reggano questa realtà.

**Implicazioni concrete:**
1. Se domani Trenord cambia formato PDF → il modello dati **non muta**.
   Cambia solo l'importer (`pdf_parser.py`, `extract_*.py`).
2. Se domani arriva SAD/TILO/Trenitalia/Tper come secondo cliente → il
   modello li accoglie con `azienda='sad'` (multi-tenancy v0.2). Zero
   riscrittura.
3. Le tabelle e i nomi sono **nostri**, non di Trenord. Es: noi
   abbiamo `corsa_commerciale`, `giro_materiale`, `turno_pdc`. Trenord
   ha "Programma di Esercizio", "Turno Materiale", "Turno PdC". Sono
   concetti analoghi, non identici.
4. Le regole operative codificate nel `TurnValidator` (max prestazione
   8h30, condotta 5h30, ecc.) sono Trenord-specifiche. Per altre
   aziende vivranno in `azienda.normativa_pdc` come JSON
   configurabile.

Il riferimento a Trenord nel titolo del documento significa
**"primo cliente di riferimento"**, non "calco passivo del loro
sistema".

---



> **Stato**: bozza in revisione con l'utente. Niente codice ancora.
> Scopo: disegnare le entità e relazioni che reggono offerta commerciale,
> giro materiale, turno PdC, anagrafica personale e loop
> real-time, **prima** di toccare DB o codice.
>
> **Da leggere come**: una mappa, non una specifica finale. Ogni nome,
> attributo o relazione è negoziabile. Quando il modello regge un caso
> reale → si congela. Solo dopo si scrive codice.

---

## 0. Decisioni v0.2 + correzioni v0.3

### v0.2 (decisioni di scoping)

| Tema | Decisione |
|------|-----------|
| **Periodicità corsa** | **Strada A — denormalizzata**. All'import del PdE, per ogni corsa si calcola l'elenco completo di date in cui circola (`valido_in_date` JSON). Query SI/NO immediate. |
| **Materiale vuoto** | Tabella sorella `corsa_materiale_vuoto`. **Non importato dal PdE — generato dal nostro algoritmo di costruzione giro materiale**. Campo `origine` traccia la provenienza. |
| **Multi-tenancy `azienda`** | **Strada A — campo da subito**. Default `'trenord'`, predisposto per SAD/Trenitalia/Tper futuri senza riscrittura. |
| **Turno CT** | **Differito**. Base struttura simile al PdC con piccole varianti contrattuali. In v0 si modella solo PdC. |
| **Anagrafica persone** | Minimo solido (persona + assegnazione + indisponibilità). |

### v0.3 (correzioni dopo revisione utente del 25/04/2026)

| Tema | Correzione |
|------|------------|
| **Località di manutenzione** | **Errore v0.2 corretto**: era una stringa libera `sede_omv`, ora è entità di prima classe `localita_manutenzione` con FK. Distinta da `depot` (sede personale). Anagrafica iniziale Trenord estratta dal PDF: 6 impianti reali (FIORENZA, LECCO, CREMONA, CAMNAGO, NOVATE, ISEO) + categoria "Non assegnato". |
| **Giro materiale parte/arriva** | Ogni `giro_materiale` ha ora `localita_manutenzione_partenza_id` e `localita_manutenzione_arrivo_id` (in genere uguali, ciclo chiuso). |
| **Revisioni: cosa sono** | **Errore v0.2 corretto**: NON sono versioning di documento. Sono **correzioni operative temporanee** dovute a eventi esterni (RFI comunica interruzioni → Trenord modifica). Modello separato in `versione_base_giro` (1 per giro, validità 12+ mesi) e `revisione_provvisoria` (N per giro, con causa, comunicazione esterna, finestra temporale). |
| **Cascading PdC** | **Punto chiarito dall'utente**: RFI non sopprime mai corse. RFI comunica interruzioni → Trenord modifica giro materiale **E** turni PdC contestualmente. Il modello prevede `revisione_provvisoria_pdc` collegata 1:N a `revisione_provvisoria` del giro. |

### v0.4 (parsing completo PDF turno materiale, 25/04/2026)

| Tema | Aggiunta |
|------|----------|
| **Dotazione per deposito** | Parsato l'intero PDF (54 cover + 299 Gantt). Per ogni deposito ho la lista completa dei tipi rotabile e la quantità totale (es. MILANO FIORENZA: 974 pezzi su 49 tipi distinti; ISEO: 21 pezzi su 4 tipi). Aggiunta tabella `localita_manutenzione_dotazione` con seed `data/depositi_manutenzione_trenord_seed.json`. |
| **Validità P/I/E** | Osservato che alcuni turni hanno cover multipli — vedi v0.5 per chiarimento. |
| **NON_ASSEGNATO modellato** | 7 turni (1190-1199, ETR524, 272 pezzi) non hanno deposito Trenord — vedi v0.5 per chiarimento. |
| **PDF è revisione provvisoria** | Validato il modello v0.3 con dato reale: il PDF "dal 2/3/26 — depositato 25/02/26" è esso stesso una revisione provvisoria, non il piano base annuale. |

### v0.5 (chiarimenti utente del 25/04/2026)

| Tema | Chiarimento + correzione |
|------|------|
| **Manifesto** | Aggiunto paragrafo introduttivo: questo NON è un calco del sistema Trenord. È modello nostro, ispirato dalla loro realtà ma indipendente. Si veda § all'inizio del doc. |
| **Codici turno con suffisso lettera (1161, 1161A...)** | **Erano lettura mia sbagliata**: non sono "validità P/I/E del codice" ma **codici turno distinti**. Esempio reale: Turno 1161 (valido fino al 27/3 e dal 29/9) e Turno 1161A (valido dal 1/8 al 28/9, estivo). Sono giri materiali separati con finestre di validità complementari sull'anno. |
| **Finestre di validità discontinue** | Il modello v0.4 aveva `versione_base_giro.valido_da/a` come singolo intervallo. Insufficiente per 1161 ("fino al 27/3 **E** dal 29/9"). Aggiunta tabella figlia `giro_finestra_validita` con 1+ intervalli per giro. |
| **NON_ASSEGNATO chiarito** | Sono **materiali svizzeri (TILO) per servizi Svizzera-Italia**, manutenuti dai vettori esteri, non da Trenord. Aggiunto flag `is_pool_esterno` + `azienda_proprietaria_esterna` su `localita_manutenzione`. |
| **Orario base** | Confermato: viene dal PdE (LIV 1 `corsa_commerciale.valido_da/a`). Già nel modello, nulla da cambiare. |

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
| **localita_manutenzione_partenza_id** | FK → `localita_manutenzione` | `IMPMAN_MILANO_FIORENZA` |
| **localita_manutenzione_arrivo_id** | FK → `localita_manutenzione` | in genere = partenza (ciclo chiuso) |
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

### Versione base + revisioni provvisorie (riformulato v0.3)

**Correzione importante v0.3** (rispetto a v0.2): le revisioni
**non sono versioning del documento**. Sono uno strumento operativo
specifico per gestire la discrepanza tra il piano teorico annuale e
la realtà operativa quando RFI Infrastruttura comunica eventi che
modificano l'esercizio.

#### Concetto di base

```
GIRO MATERIALE 1100
   |
   ├── versione_base (validità 14/12/2025 → 12/12/2026)
   |     pubblicata in offerta commerciale, allineata al PdE annuale
   |
   ├── revisione_provvisoria #A (15-30/04/2026)
   |     causa: interruzione_rfi  (lavori tratta Como-Lecco)
   |     comunicazione: PIR-2026-345
   |     → modifica giro materiale per quella finestra
   |     → CASCADING: trascina revisione_provvisoria del turno PdC
   |        (perché Trenord modifica entrambi insieme)
   |
   └── revisione_provvisoria #B (01-08/06/2026)
         causa: sciopero
         ...
```

#### `versione_base_giro` (1:1 con `giro_materiale`)

Una sola per giro materiale. È quella pubblicata con il PDF annuale.

| Attributo | Tipo | Esempio |
|-----------|------|---------|
| id | PK | |
| giro_materiale_id | FK | univoco |
| data_deposito | date | "2025-11-30" |
| source_file | string | path PDF originale |

**Nota v0.5**: i campi `valido_da/valido_a` sono stati rimossi da qui
e spostati in tabella figlia `giro_finestra_validita` perché un giro
può avere intervalli di validità **discontinui** sull'anno.

#### `giro_finestra_validita` (figlia di `versione_base_giro`, **nuova v0.5**)

Una o più finestre di validità per la versione base del giro.
La maggior parte dei giri ha 1 sola finestra (validità annuale
intera), ma alcuni ne hanno 2+ (es. Turno 1161 base = "fino al 27/3
e dal 29/9", che è coperto sull'estate dal Turno 1161A "dal 1/8
al 28/9").

| Attributo | Tipo | Esempio |
|-----------|------|---------|
| id | PK | |
| versione_base_giro_id | FK | |
| valido_da | date | "2026-09-29" |
| valido_a | date | "2026-12-12" |
| seq | int | 1, 2, 3... ordine cronologico |

**Esempio Turno 1161** (annuale con buco estivo coperto da 1161A):
```
giro_materiale {id: 161, numero_turno: "1161"}
versione_base_giro {id: 261, giro_materiale_id: 161}
giro_finestra_validita {versione_id: 261, seq: 1, da: 2025-12-14, a: 2026-03-27}
giro_finestra_validita {versione_id: 261, seq: 2, da: 2026-09-29, a: 2026-12-12}

giro_materiale {id: 162, numero_turno: "1161A"}  // turno-fratello estivo
versione_base_giro {id: 262, giro_materiale_id: 162}
giro_finestra_validita {versione_id: 262, seq: 1, da: 2026-08-01, a: 2026-09-28}
```

**Vincolo**: per un dato `numero_turno` (al netto del suffisso), le
finestre dei giri-fratelli **non si sovrappongono** (mai due giri
attivi nello stesso giorno per lo stesso codice base).

#### `revisione_provvisoria` (entità nuova v0.3)

Modifica temporanea con causa esterna esplicita.

| Attributo | Tipo | Esempio |
|-----------|------|---------|
| id | PK | |
| giro_materiale_id | FK | |
| codice_revisione | string | "1100-REV-2026-A" |
| **causa** | enum | `interruzione_rfi`, `sciopero`, `manutenzione_straordinaria`, `evento_speciale`, `altro` |
| comunicazione_esterna_rif | string | "PIR-2026-345" (riferimento RFI) |
| descrizione_evento | string | "Lavori interruzione Como-Lecco, deviazione via Bergamo" |
| finestra_da | date | "2026-04-15" |
| finestra_a | date | "2026-04-30" |
| data_pubblicazione | date | "2026-03-25" |
| source_file | string | PDF/comunicato originale |

Quando una `revisione_provvisoria` è attiva, **sostituisce** la
`versione_base` per la finestra temporale specificata. I `giro_blocco`
modificati vivono in `revisione_provvisoria_blocco` (figlia), che si
sovrappone ai blocchi della versione base.

#### Cascading sui turni PdC (regola operativa v0.3)

**Punto fondamentale chiarito dall'utente**: una revisione provvisoria
del giro materiale **NON resta isolata**. Trenord modifica
contestualmente anche il turno PdC, perché le corse cambiate vanno
ricoperte da macchinisti.

Modello:
- `revisione_provvisoria` (sul giro materiale) può avere **0 o più**
  `revisione_provvisoria_pdc` collegate, una per ciascun turno PdC
  impattato.
- Ogni `revisione_provvisoria_pdc` ha la **stessa finestra temporale**
  della rev del giro materiale che la causa.
- Un PdC che copriva la giornata X del turno-base, durante la finestra
  di revisione, copre la giornata X' del turno-rev. La sua
  `assegnazione_giornata` risolve automaticamente alla rev quando
  attiva.

| `revisione_provvisoria_pdc` | Tipo | Esempio |
|---|---|---|
| id | PK | |
| revisione_giro_id | FK → `revisione_provvisoria` | trigger della rev |
| turno_pdc_id | FK | turno modificato |
| codice_revisione | string | "ALOR_C-REV-2026-A" |
| finestra_da/finestra_a | date | (ereditate dalla rev giro) |

#### Risoluzione query "cosa fa il treno X il giorno D?"

```
1. trova giro_materiale che copre il treno X
2. cerca revisione_provvisoria per quel giro con finestra_da ≤ D ≤ finestra_a
   ├── se SÌ → usa giro_blocco della revisione (override)
   └── se NO → usa giro_blocco della versione_base
3. analogo per "chi guida il treno X il giorno D?":
   trova turno_pdc che copre la corsa, applica eventuale rev_pdc se
   D è nella finestra
```

Storia preservata: niente viene cancellato, le revisioni convivono
con la base.

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

### `impianto` / `deposito` (sede personale PdC/CT)

Esiste già come `depot`. È la **sede del personale** (ALESSANDRIA,
LECCO, BRESCIA, MILANO PORTA GARIBALDI...). **NON va confuso con
`localita_manutenzione`** (sede del materiale fisico).

Va esteso con:
- `tipi_personale_ammessi` (PdC, CT, ENTRAMBI)
- `materiali_ammessi` (FK → `materiale_tipo`)
- `linee_ammesse`

### `localita_manutenzione` (sede materiale, **nuova**)

**Decisione v0.3**: entità di prima classe distinta da `depot`.
Sostituisce la stringa `sede_omv` di v0.2 con una FK relazionale.

Una località di manutenzione è dove il materiale fisico (locomotive,
carrozze) viene rimessato per manutenzione/pulizia/preparazione.
Ogni `giro_materiale` parte da e termina in una località di
manutenzione (in genere la stessa: ciclo chiuso).

| Attributo | Tipo | Esempio |
|-----------|------|---------|
| id | PK | |
| codice | string | "IMPMAN_MILANO_FIORENZA" |
| nome_canonico | string | "TRENORD IMPMAN MILANO FIORENZA" |
| nomi_alternativi | json string[] | ["MILANO FIOREN", "Fiorenza", "MI FIOREN"] |
| stazione_collegata_id | FK → `stazione`? | "MILANO FIORENZA" se esiste come fermata commerciale |
| azienda_id | FK | "trenord" — chi gestisce operativamente |
| **is_pool_esterno** | bool | **v0.5**: true se i materiali sono di vettore estero (vedi sotto) |
| **azienda_proprietaria_esterna** | string? | **v0.5**: "TILO", "SBB", null per Trenord interno |
| attivo | bool | |

**Caso pool esterno (v0.5)**: alcuni servizi (es. Svizzera-Italia) sono
operati con materiali di vettori esteri (TILO, SBB) che **non sono
manutenuti da Trenord**. Nel PDF di Trenord questi turni appaiono con
"Non assegnato" come OMV/OML — non perché manchi il dato, ma perché la
manutenzione è altrove. Il modello li rappresenta con una pseudo-località:

```
localita_manutenzione {
  codice: "POOL_TILO_SVIZZERA",
  nome_canonico: "(Pool TILO - servizi Svizzera-Italia)",
  is_pool_esterno: true,
  azienda_proprietaria_esterna: "TILO",
  azienda_id: "trenord",  // chi gestisce operativamente in Italia
}
```

I 7 turni Trenord 1190-1199 con materiali ETR524 (272 pezzi totali —
164 Le524 + 108 Ale524) cadono in questa categoria.

#### Anagrafica iniziale Trenord (estratta dal PDF turno materiale 02/03/26)

Parsing completo del PDF (54 cover + 299 pagine Gantt) — output salvato
in `data/depositi_manutenzione_trenord_seed.json`.

| Codice | Nome canonico | Turni gestiti | Tipi pezzo | Pezzi totali |
|--------|---------------|--------------:|-----------:|-------------:|
| `IMPMAN_MILANO_FIORENZA` | TRENORD IMPMAN MILANO FIORENZA | **29** | 49 | **974** |
| `IMPMAN_NOVATE` | TRENORD IMPMAN NOVATE | 7 | 14 | 299 |
| `POOL_TILO_SVIZZERA` | (ETR524 servizi Svizzera-Italia, manutenzione TILO) | 7 | 2 | 272 |
| `IMPMAN_CAMNAGO` | TRENORD IMPMAN CAMNAGO | 2 | 7 | 169 |
| `IMPMAN_CREMONA` | TRENORD IMPMAN CREMONA | 2 | 4 | 92 |
| `IMPMAN_LECCO` | TRENORD IMPMAN LECCO | 3 | 6 | 57 |
| `IMPMAN_ISEO` | TRENORD IMPMAN ISEO | 4 | 4 | 21 |
| **TOTALE** | | **54** | | **1884** |

Per coerenza si **canonicalizzano i nomi maiuscolo** ("ImpMan" → "IMPMAN")
e si risolve il troncamento "FIOREN" → "FIORENZA" via `nomi_alternativi`.

#### `localita_manutenzione_dotazione` (tabella figlia, **nuova v0.4**)

Per ogni località, l'inventario dei rotabili per tipo. Permette di
sapere subito *quanti pezzi di tipo X sono di base in deposito Y*.

| Attributo | Tipo | Esempio |
|-----------|------|---------|
| id | PK | |
| localita_manutenzione_id | FK | `IMPMAN_MILANO_FIORENZA` |
| tipo_pezzo | string | "ALe710", "TN-Ale204-A4", "E464N" |
| quantita | int | 74 |
| famiglia_rotabile | string? | "TSR", "Coradia Lecco ETR204", "Vivalto", "Locomotiva E464" |
| note | string | calcolato come somma su tutti i turni del deposito |

**Specializzazione di ogni deposito** (dato concreto dal seed):

- **MILANO FIORENZA**: multi-flotta (49 tipi distinti). Top: ALe710 (74),
  ALe711 (64), nBBW (52, Vivalto), nBC-clim (51), TN-Ale204/Le204
  (48 ciascuno × 4 sigle), TN-Ale522/Le522 (36 × 5 sigle, Caravaggio),
  TN-Ale421/Le421 (34 × 3-4 sigle, Donizetti), E464N (22), poi
  ETR526 Coradia 526, ETR104, npBDL, npBDCTE...
- **NOVATE**: TSR (ALe710=53, ALe711=58), Le245 (30), TN-Le425 (28
  TILO ETR425), Le990 (20), Le736 (14), Ale760+761 (10+10), ALe506,
  ALe426. Specializzazione su TSR + TILO + treni Tibb di pool.
- **CAMNAGO**: ALe710 (56) + ALe711 (28) per TSR Mi-NO + ETR522
  Caravaggio (TA+DM1+DM2+TB+TX, 17 ciascuno). Solo 2 turni ma corposi.
- **CREMONA**: solo Aln803-A/B + Ln803-PP/C (23 pezzi ciascuno).
  Treni diesel DMU monolitici.
- **LECCO**: ETR204 Coradia Lecco (TN-Ale204-A1/A4 + TN-Le204-A2/A3,
  11 pezzi × 4 sigle = 44) + diesel ATR125 (9), ATR115 (4).
- **ISEO**: solo diesel — ATR125 (8), ALn668(1000) (8), ATR115 (4),
  D520 (1). Linee non elettrificate Brescia-Iseo-Edolo.
- **POOL_TILO_SVIZZERA** (ex "NON_ASSEGNATO" in v0.4): solo ETR524
  (Le524=164, Ale524=108) — 7 turni dedicati a servizi Svizzera-Italia.
  Materiali di proprietà TILO, manutenzione **non** Trenord.
  **Confermato dall'utente in v0.5**.

#### Osservazioni emerse dal parsing (v0.4)

1. **Validità multipla per stesso turno**: alcuni turni appaiono **due
   volte** nel PDF (es. cover di "1134" appare 2 volte, "1191" 2 volte,
   "1161" 3 volte). Sono **revisioni con validità diversa** (Validità
   P, I, E — Pasqua/Inverno/Estate o simili). Il modello v0.3 li gestiva
   come `versione_base_giro` 1:1 — ma in realtà servirà una variante:
   le validità calendar-based (P/I/E) **non sono** revisioni provvisorie
   per eventi RFI, sono **versioni stagionali pianificate**. Da chiarire
   in v0.5 se aggiungere `versione_stagionale_giro` o estendere
   `giro_variante` per coprire questo caso.

2. **NON_ASSEGNATO non è un bug, è una categoria reale**: 7 turni e 272
   pezzi (ETR524) non hanno deposito Trenord. Ipotesi: pool TILO o
   composizioni di terzi gestite da Trenord. Va modellato come
   pseudo-località con flag `is_pool_esterno=true`.

3. **Il PDF stesso è una revisione provvisoria**: "Turno Materiale
   Trenord dal 2/3/26 — Depositata il 25/02/2026" non è il piano base
   annuale, è una revisione che entra in vigore a marzo. Conferma il
   modello v0.3 (versione_base + revisione_provvisoria) con dati reali.

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
  localita_manutenzione_partenza_id: <FK IMPMAN_MILANO_FIORENZA>
  localita_manutenzione_arrivo_id: <FK IMPMAN_MILANO_FIORENZA>  // ciclo chiuso
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

**Correzione v0.3**: il modello v0.2 di `revisione_turno` come
"versioning di documento" era sbagliato. Riformulato in
`versione_base_giro` + `revisione_provvisoria` (con causa esterna +
finestra temporale + cascading sui turni PdC). Vedi §LIV 5+ per il
modello corretto.

**Aggiunta v0.3**: entità `localita_manutenzione` distinta da `depot`
PdC, con anagrafica iniziale Trenord estratta dal PDF (6 impianti reali
+ "Non assegnato"). Vedi §3.

---

## 9. Prossimo step (solo dopo sblocco di questo doc)

Quando l'utente legge e dà OK al modello (o lo corregge), il prossimo
step è **uno solo**:

> Scrivere `docs/MIGRAZIONE-DATI.md`: tabella per tabella, il piano di
> migrazione DB. Nessuna riga di codice ancora.

Solo dopo la migrazione documentata e approvata si tocca il DB.

---

**Fine draft v0.1.** Da revisionare con l'utente.
