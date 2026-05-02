# Linee Trenord ↔ Famiglie materiale (PdE 2026)

> Sintesi automatica da `Turno Materiale Trenord dal 2/3/26.pdf` (Turnificazione 912, depositata 25/02/2026, validità da 2/3/26).
> Estratto il 2026-05-02 con `pdftotext` + parser Python.
> Famiglia commerciale **letta dalle note Gantt del PDF** (fonte autorevole Trenord), non dedotta dalla composizione.
> Dato grezzo: [`data/turni_materiale_2026_dump.json`](turni_materiale_2026_dump.json)

**54 turni materiale** | **23 linee identificate** | **18 famiglie** (tutte da fonte PDF autorevole)

> **Vincoli inviolabili a livello tipo materiale**: vedi [`vincoli_materiale_inviolabili.json`](vincoli_materiale_inviolabili.json) — 3 vincoli HARD (TILO Flirt, materiale elettrico, Treno dei Sapori), tutti verificati: 0/54 violazioni nel dataset.

---

## Famiglie commerciali Trenord (dal PDF)

Le note del PDF Trenord dichiarano esplicitamente la famiglia commerciale per ogni turno. 
Estratte le seguenti denominazioni:

| Famiglia | Codici/composizione | Esempio nota PDF |
|---|---|---|
| **Caravaggio** | ETR421 + ETR522 | `Caravaggio 4pz - 1°CL (ETR421) - m.110` |
| **Donizetti** | ETR204 | `Donizetti - ETR 204 - m.84` |
| **Coradia 245** | ETR245 | `Coradia 245 - m.83` |
| **Coradia 425** | ETR425 | `Coradia 425 - m.82` |
| **Coradia 526** | ETR526 | `Coradia 526 - m.98` |
| **Rock** | ETR521 | `Rock 5pz - m.137` |
| **POP** | ETR103/ETR104 | `POP 3pz - m.66` |
| **TILO Flirt** | ETR524 | `TILO S10 - Flirt 4pz - m.74` |
| **TSR** | ALe711+ALe710 | `TSR 3pz - m.79`, `TSR 5pz - m.131` |
| **TAF** | ALe506+ALe426+Le736 (ex Trenitalia) | `TAF TI - m.106` |
| **R-TAF** | ALe760/761+Le990 (storico Trenord) | `R-TAF - m.106` |
| **Vivalto** | E464 + nBBW (loco-trainata doppio piano) | `PR 402 - PPF 125 - m.174 - VIVALTO` |
| **MDVE/MDVC** | E464 + npBDL/npBDCTE + nBC (loco-trainata classica) | `PR 270 - MD - Materiale Attrezzato con AI` |
| **ATR803 Coleoni** | diesel ibrido | `ATR 803 (Colleoni) - m.67` |
| **ATR125 / ATR115** | diesel Minuetto / Pesa | `ATR 125 - m.78`, `ATR 115 - m.40` |
| **ALn668** | diesel storico | `2 Aln668 - m.47` |
| **Treno dei Sapori** | turistico speciale (D520) | `Turno dedicato Treno dei Sapori` |

> **NB importante** distinzione TSR / TAF / R-TAF (terminologia Trenord):
> - **TSR** = ALe711+ALe710 (è il "normale" doppio piano elettromotrice Trenord moderno)
> - **TAF** = ALe506+ALe426+Le736 ex Trenitalia (un'altra composizione storica diversa)
> - **R-TAF** = ALe760/761+Le990 (variante storica Trenord)

---

## 1. Linee → Famiglie ammesse

Quale famiglia di materiale Trenord può andare su quale linea, secondo i giri reali del PdE 2026.

### Bergamo-Milano via Carnate (capolinea attuale: Ponte S.Pietro - tratta PSP-BG chiusa)
*5 turni unici*

| Famiglia materiale | Turni |
|---|---|
| **ATR125 Minuetto (diesel)** | 1114 |
| **Caravaggio (ETR421/ETR522)** | 1126 |
| **Donizetti (ETR204)** | 1131, 1132 |
| **MDVE/MDVC (E464+npBDL/BDCTE+nBC)** | 1103 |

### Bergamo-Milano via Pioltello (linea diretta)
*15 turni unici*

| Famiglia materiale | Turni |
|---|---|
| **Caravaggio (ETR421/ETR522)** | 1121, 1122, 1123, 1124, 1125, 1126, 1127, 1160 *(+4 altri)* |
| **TSR (ALe711+ALe710)** | 1110, 1111, 1112 |

### Bergamo-Milano via Treviglio
*1 turni unici*

| Famiglia materiale | Turni |
|---|---|
| **Vivalto (E464+nBBW loco-trainata)** | 1101 |

### Bergamo-Ventimiglia (treno turistico stagionale)
*2 turni unici*

| Famiglia materiale | Turni |
|---|---|
| **MDVE/MDVC (E464+npBDL/BDCTE+nBC)** | 1104, 1105 |

### Brescia-Iseo-Edolo (NON elettrificata)
*4 turni unici*

| Famiglia materiale | Turni |
|---|---|
| **ALn668 (diesel storico)** | 1182 |
| **ATR115 (diesel)** | 1181 |
| **ATR125 Minuetto (diesel)** | 1180 |
| **Treno dei Sapori (turistico speciale)** | 1184 |

### Brescia-Milano (linea storica)
*8 turni unici*

| Famiglia materiale | Turni |
|---|---|
| **ATR803 Coleoni (diesel ibrido)** | 1115 |
| **Caravaggio (ETR421/ETR522)** | 1122, 1124, 1125, 1126 |
| **Donizetti (ETR204)** | 1133, 1134, 1134I |

### Brescia-Parma (NON elettrificata)
*1 turni unici*

| Famiglia materiale | Turni |
|---|---|
| **ATR803 Coleoni (diesel ibrido)** | 1115 |

### Como-Chiasso-Milano
*6 turni unici*

| Famiglia materiale | Turni |
|---|---|
| **TILO Flirt (ETR524)** | 1191, 1191A, 1192, 1195, 1196, 1199 |

### Cremona-Codogno-Milano
*5 turni unici*

| Famiglia materiale | Turni |
|---|---|
| **ATR803 Coleoni (diesel ibrido)** | 1116 |
| **Caravaggio (ETR421/ETR522)** | 1121 |
| **Donizetti (ETR204)** | 1134, 1134I |
| **MDVE/MDVC (E464+npBDL/BDCTE+nBC)** | 1100 |

### Cremona-Treviglio-Milano
*4 turni unici*

| Famiglia materiale | Turni |
|---|---|
| **Caravaggio (ETR421/ETR522)** | 1127 |
| **Donizetti (ETR204)** | 1134, 1134I |
| **MDVE/MDVC (E464+npBDL/BDCTE+nBC)** | 1100 |

### Genova-Voghera-Milano
*3 turni unici*

| Famiglia materiale | Turni |
|---|---|
| **Caravaggio (ETR421/ETR522)** | 1125 |
| **Donizetti (ETR204)** | 1135 |
| **Vivalto (E464+nBBW loco-trainata)** | 1102 |

### Lecco-Molteno-Milano
*2 turni unici*

| Famiglia materiale | Turni |
|---|---|
| **ATR115 (diesel)** | 1113 |
| **ATR125 Minuetto (diesel)** | 1114 |

### Linea passante Milano
*5 turni unici*

| Famiglia materiale | Turni |
|---|---|
| **Caravaggio (ETR421/ETR522)** | 1125 |
| **Coradia 245 (ETR245)** | 1162 |
| **Donizetti (ETR204)** | 1131 |
| **TAF (ALe426+ALe506+Le736 ex Trenitalia)** | 1170 |
| **Vivalto (E464+nBBW loco-trainata)** | 1101 |

### Luino-Gallarate-Milano
*3 turni unici*

| Famiglia materiale | Turni |
|---|---|
| **POP (ETR103/ETR104)** | 1136, 1137 |
| **TILO Flirt (ETR524)** | 1190 |

### Mantova-Cremona-Milano
*3 turni unici*

| Famiglia materiale | Turni |
|---|---|
| **ATR803 Coleoni (diesel ibrido)** | 1115 |
| **Caravaggio (ETR421/ETR522)** | 1127 |
| **Vivalto (E464+nBBW loco-trainata)** | 1102 |

### Milano-Domodossola
*2 turni unici*

| Famiglia materiale | Turni |
|---|---|
| **Caravaggio (ETR421/ETR522)** | 1121, 1127 |

### Milano-Gallarate
*3 turni unici*

| Famiglia materiale | Turni |
|---|---|
| **Caravaggio (ETR421/ETR522)** | 1160 |
| **TSR (ALe711+ALe710)** | 1110, 1111 |

### Milano-Lecco
*3 turni unici*

| Famiglia materiale | Turni |
|---|---|
| **ATR115 (diesel)** | 1113 |
| **ATR125 Minuetto (diesel)** | 1114 |
| **Caravaggio (ETR421/ETR522)** | 1123 |

### Milano-Lecco-Tirano
*3 turni unici*

| Famiglia materiale | Turni |
|---|---|
| **Coradia 526 (ETR526)** | 1130 |
| **Donizetti (ETR204)** | 1131, 1132 |

### Milano-Mortara-Alessandria
*3 turni unici*

| Famiglia materiale | Turni |
|---|---|
| **ATR803 Coleoni (diesel ibrido)** | 1116 |
| **Caravaggio (ETR421/ETR522)** | 1125 |
| **Vivalto (E464+nBBW loco-trainata)** | 1101 |

### Novara-Pioltello-Milano
*7 turni unici*

| Famiglia materiale | Turni |
|---|---|
| **Caravaggio (ETR421/ETR522)** | 1123, 1171 |
| **R-TAF (ALe760/761+Le990 storico)** | 1169 |
| **TSR (ALe711+ALe710)** | 1110, 1111, 1112, 1168 |

### Pavia-Stradella-Milano
*2 turni unici*

| Famiglia materiale | Turni |
|---|---|
| **ATR803 Coleoni (diesel ibrido)** | 1116 |
| **TSR (ALe711+ALe710)** | 1168 |

### Varese-Saronno-Milano
*12 turni unici*

| Famiglia materiale | Turni |
|---|---|
| **Caravaggio (ETR421/ETR522)** | 1160, 1171 |
| **Coradia 425 (ETR425)** | 1163 |
| **R-TAF (ALe760/761+Le990 storico)** | 1169 |
| **Rock (ETR521)** | 1128 |
| **TILO Flirt (ETR524)** | 1195 |
| **TSR (ALe711+ALe710)** | 1110, 1111, 1165, 1166, 1167, 1168 |

---

## 2. Famiglie → Linee servite

### ALn668 (diesel storico)
*1 turni unici, 1 linee*

| Linea | Turni |
|---|---|
| Brescia-Iseo-Edolo (NON elettrificata) | 1182 |

### ATR115 (diesel)
*2 turni unici, 3 linee*

| Linea | Turni |
|---|---|
| Brescia-Iseo-Edolo (NON elettrificata) | 1181 |
| Lecco-Molteno-Milano | 1113 |
| Milano-Lecco | 1113 |

### ATR125 Minuetto (diesel)
*2 turni unici, 4 linee*

| Linea | Turni |
|---|---|
| Bergamo-Milano via Carnate (capolinea attuale: Ponte S.Pietro - tratta PSP-BG chiusa) | 1114 |
| Brescia-Iseo-Edolo (NON elettrificata) | 1180 |
| Lecco-Molteno-Milano | 1114 |
| Milano-Lecco | 1114 |

### ATR803 Coleoni (diesel ibrido)
*2 turni unici, 6 linee*

| Linea | Turni |
|---|---|
| Brescia-Milano (linea storica) | 1115 |
| Brescia-Parma (NON elettrificata) | 1115 |
| Cremona-Codogno-Milano | 1116 |
| Mantova-Cremona-Milano | 1115 |
| Milano-Mortara-Alessandria | 1116 |
| Pavia-Stradella-Milano | 1116 |

### Caravaggio (ETR421/ETR522)
*12 turni unici, 14 linee*

| Linea | Turni |
|---|---|
| Bergamo-Milano via Carnate (capolinea attuale: Ponte S.Pietro - tratta PSP-BG chiusa) | 1126 |
| Bergamo-Milano via Pioltello (linea diretta) | 1121, 1122, 1123, 1124, 1125, 1126, 1127, 1160 *(+4 altri)* |
| Brescia-Milano (linea storica) | 1122, 1124, 1125, 1126 |
| Cremona-Codogno-Milano | 1121 |
| Cremona-Treviglio-Milano | 1127 |
| Genova-Voghera-Milano | 1125 |
| Linea passante Milano | 1125 |
| Mantova-Cremona-Milano | 1127 |
| Milano-Domodossola | 1121, 1127 |
| Milano-Gallarate | 1160 |
| Milano-Lecco | 1123 |
| Milano-Mortara-Alessandria | 1125 |
| Novara-Pioltello-Milano | 1123, 1171 |
| Varese-Saronno-Milano | 1160, 1171 |

### Coradia 245 (ETR245)
*1 turni unici, 1 linee*

| Linea | Turni |
|---|---|
| Linea passante Milano | 1162 |

### Coradia 425 (ETR425)
*1 turni unici, 1 linee*

| Linea | Turni |
|---|---|
| Varese-Saronno-Milano | 1163 |

### Coradia 526 (ETR526)
*1 turni unici, 1 linee*

| Linea | Turni |
|---|---|
| Milano-Lecco-Tirano | 1130 |

### Donizetti (ETR204)
*6 turni unici, 7 linee*

| Linea | Turni |
|---|---|
| Bergamo-Milano via Carnate (capolinea attuale: Ponte S.Pietro - tratta PSP-BG chiusa) | 1131, 1132 |
| Brescia-Milano (linea storica) | 1133, 1134, 1134I |
| Cremona-Codogno-Milano | 1134, 1134I |
| Cremona-Treviglio-Milano | 1134, 1134I |
| Genova-Voghera-Milano | 1135 |
| Linea passante Milano | 1131 |
| Milano-Lecco-Tirano | 1131, 1132 |

### MDVE/MDVC (E464+npBDL/BDCTE+nBC)
*4 turni unici, 4 linee*

| Linea | Turni |
|---|---|
| Bergamo-Milano via Carnate (capolinea attuale: Ponte S.Pietro - tratta PSP-BG chiusa) | 1103 |
| Bergamo-Ventimiglia (treno turistico stagionale) | 1104, 1105 |
| Cremona-Codogno-Milano | 1100 |
| Cremona-Treviglio-Milano | 1100 |

### POP (ETR103/ETR104)
*2 turni unici, 1 linee*

| Linea | Turni |
|---|---|
| Luino-Gallarate-Milano | 1136, 1137 |

### R-TAF (ALe760/761+Le990 storico)
*1 turni unici, 2 linee*

| Linea | Turni |
|---|---|
| Novara-Pioltello-Milano | 1169 |
| Varese-Saronno-Milano | 1169 |

### Rock (ETR521)
*1 turni unici, 1 linee*

| Linea | Turni |
|---|---|
| Varese-Saronno-Milano | 1128 |

### TAF (ALe426+ALe506+Le736 ex Trenitalia)
*1 turni unici, 1 linee*

| Linea | Turni |
|---|---|
| Linea passante Milano | 1170 |

### TILO Flirt (ETR524)
*7 turni unici, 3 linee*

| Linea | Turni |
|---|---|
| Como-Chiasso-Milano | 1191, 1191A, 1192, 1195, 1196, 1199 |
| Luino-Gallarate-Milano | 1190 |
| Varese-Saronno-Milano | 1195 |

### TSR (ALe711+ALe710)
*7 turni unici, 5 linee*

| Linea | Turni |
|---|---|
| Bergamo-Milano via Pioltello (linea diretta) | 1110, 1111, 1112 |
| Milano-Gallarate | 1110, 1111 |
| Novara-Pioltello-Milano | 1110, 1111, 1112, 1168 |
| Pavia-Stradella-Milano | 1168 |
| Varese-Saronno-Milano | 1110, 1111, 1165, 1166, 1167, 1168 |

### Treno dei Sapori (turistico speciale)
*1 turni unici, 1 linee*

| Linea | Turni |
|---|---|
| Brescia-Iseo-Edolo (NON elettrificata) | 1184 |

### Vivalto (E464+nBBW loco-trainata)
*2 turni unici, 5 linee*

| Linea | Turni |
|---|---|
| Bergamo-Milano via Treviglio | 1101 |
| Genova-Voghera-Milano | 1102 |
| Linea passante Milano | 1101 |
| Mantova-Cremona-Milano | 1102 |
| Milano-Mortara-Alessandria | 1101 |

---

## 3. Vincoli inviolabili (HARD) e tratte chiuse

> Distinzione importante:
> - **Vincoli inviolabili** (questo file): a livello *tipo materiale*, validi sempre. Il pianificatore non può creare regole `programma_regola_assegnazione` che li violino. Documentati in [`vincoli_materiale_inviolabili.json`](vincoli_materiale_inviolabili.json).
> - **Vincoli operativi soft**: scelte del pianificatore per il singolo programma. Vivono in `programma_regola_assegnazione` (DB).

I tre vincoli inviolabili documentati sono:

### 3.1 Materiale elettrico ↔ obbligo catenaria (`tipo: tecnico_alimentazione`)

**Modalità**: blacklist. Materiale puramente elettrico (sia elettromotrice sia loco-trainata E464) richiede catenaria, NON può circolare su linee non elettrificate. Vale per **tutto il materiale elettrico Trenord** (13 famiglie su 18: Caravaggio, Donizetti, Coradia 245/425/526, Rock, POP, TSR, TAF, R-TAF, TILO Flirt, Vivalto, MDVE/MDVC).

**Linee vietate**: `Brescia-Iseo-Edolo (NON elettrificata)`, `Brescia-Parma (NON elettrificata)`.

**Famiglie esenti** (diesel/ibrido): ATR803 Coleoni, ATR125, ATR115, ALn668, Treno dei Sapori. ATR803 è ibrido (può anche elettrificate); le altre sono diesel pure.

**Verifica dataset**: 46 turni con materiale elettrico, **0 violazioni**.

### 3.2 TILO Flirt (ETR524) — omologazione TILO/CH (`tipo: contrattuale_omologazione`)

**Modalità**: whitelist. Ammesso solo su linee con destinazione **Chiasso**, **MXP-Varese**, o **Luino-MXP** (accordo Trenord-SBB).

Servizi commerciali dichiarati nel PDF: `S10`, `S30`, `S40`. **Verifica dataset**: 7 turni ETR524 (1190-1199), **0 violazioni** (tutti su Como-Chiasso, Luino-Gallarate, Varese-Saronno).

### 3.3 Treno dei Sapori (D520) — solo Brescia-Iseo-Edolo (`tipo: operativo_turistico`)

**Modalità**: whitelist. Convoglio turistico speciale Trenord trainato dal locomotore diesel D520, in servizio solo sulla linea della Valcamonica. **Verifica dataset**: 1 turno (1184), **0 violazioni**.

### 3.4 Tratte chiuse al 2026-05-02

- **Bergamo ↔ Ponte S.Pietro**: tratta **chiusa**. Tutti i treni "via Carnate" terminano a **Ponte S.Pietro** (non a Bergamo). L'etichetta linea nel dataset è *"Bergamo-Milano via Carnate (capolinea attuale: Ponte S.Pietro - tratta PSP-BG chiusa)"*.
- **Lecco-Bergamo**: linea **sospesa**. Verificato sul dataset: 0 turni del PdE 2026 toccano entrambe le stazioni Lecco e Bergamo (coerente con la chiusura).

### 3.5 Linee Bergamo - 3 routing distinti

- **Via Pioltello (linea diretta)**: passa per Caravaggio/Pioltello/Vignate. R3 (Bergamo via Pioltello).
- **Via Carnate**: passa per Ponte S.Pietro/Carnate Usmate. R5 (capolinea attuale Ponte S.Pietro - vedi 3.2).
- **Via Treviglio**: RE3 (Bergamo via Treviglio).

---

## 4. Pattern operativi dedotti

### 4.1 Linee non elettrificate → solo diesel

- **Brescia-Iseo-Edolo**: `ALn668`, `ATR115`, `ATR125 Minuetto`, `Treno dei Sapori (D520)` (4 turni: 1180, 1181, 1182, 1184).
- **Brescia-Parma**: solo `ATR803 Coleoni` (turno 1115).

### 4.2 ATR803 Coleoni — polivalente su elettrificate

Diesel ibrido, compare su Mantova-Cremona, Cremona-Codogno, Milano-Mortara-Alessandria, Pavia-Stradella, Brescia-Milano, Brescia-Parma. La trazione termica lo rende compatibile sia con linee elettrificate sia diesel.

### 4.3 Linee specializzate

- **Como-Chiasso-Milano**: solo `TILO Flirt (ETR524)`.
- **Milano-Lecco-Tirano** (Valtellina): `Coradia 526` + `Donizetti` su sotto-tratte.
- **Bergamo-Ventimiglia** (Treno del Mare, stagionale 28/3-28/9): esclusivamente loco-trainata MDVE estiva (`E464+npBDCTE+nBC`).
- **Luino-Gallarate-Milano**: `POP` (ETR103/ETR104) + TILO (1190).

### 4.4 Linee polivalenti (multi-famiglia)

- **Varese-Saronno-Milano** (12 turni): la più trafficata. Caravaggio, Coradia 425, Rock, TILO, TSR, R-TAF, TAF.
- **Bergamo-Milano via Pioltello** (~15 turni): Caravaggio, TSR.
- **Cremona-Codogno-Milano**: ATR803, Caravaggio, Donizetti, MDVE.

---

## 5. Riferimenti

- **Sorgente PDF**: `Turno Materiale Trenord dal 2_3_26.pdf` (esterno al repo)
- **Dump JSON**: [`turni_materiale_2026_dump.json`](turni_materiale_2026_dump.json)
- **Memoria**: `project_direttrici_materiali_trenord.md` (3 confermate finora) + `reference_pdf_turno_materiale_2026.md` (questo dump)
