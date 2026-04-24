# Normativa Turni PdC — Fonte della verità

> Documento costruito passo-passo insieme all'utente. Ogni regola è
> stata dettata dall'utente e validata. Se il codice fa diversamente,
> è il codice a essere sbagliato, non questo documento.
>
> **Uso obbligatorio**: va letto a inizio sessione insieme a
> `LIVE-COLAZIONE.md` e `docs/METODO-DI-LAVORO.md` quando si lavora su
> builder (`src/turn_builder/`), parser PdC (`src/importer/`), o UI
> Gantt (`frontend/src/components/gantt/`).

---

## Convenzioni di lettura

Ogni regola segue questa struttura fissa:

```
### N.M Titolo breve

**Regola**: una frase imperativa diretta.
**Quando si applica**: contesto in cui vale.
**Valori**: tabella se ci sono numeri.
**Esempio**: scenario concreto con numeri.
**NON confondere con**: regole simili ma diverse.
```

Non tutti i blocchi sono obbligatori — se la regola è semplice si
omette ciò che non serve. Ma l'ordine è sempre questo.

---

## Indice

1. [Glossario sigle](#1-glossario-sigle) — chiuso
2. [Depositi PdC per linea](#2-depositi-pdc-per-linea) — chiuso
3. [Accessori (ACCp, ACCa) e presa/fine servizio](#3-accessori-accp-acca-e-presafine-servizio) — chiuso
4. [Pause: REFEZ, buco, pausa in vettura, PK](#4-pause-refez-buco-pausa-in-vettura-pk) — chiuso
5. [Cambio Volante (CVp / CVa)](#5-cambio-volante-cvp--cva) — chiuso
6. [Scelta fra CV / ACC / PK in base al gap](#6-scelta-fra-cv--acc--pk-in-base-al-gap) — chiuso
7. [Vetture e rientro a deposito](#7-vetture-e-rientro-a-deposito) — chiuso
8. [Materiale vuoto (numeri U****)](#8-materiale-vuoto-numeri-u) — chiuso
9. [Spezzare i treni (CV intermedi)](#9-spezzare-i-treni-cv-intermedi) — chiuso
10. [FR e pernotti](#10-fr-e-pernotti) — chiuso
11. [Ciclo settimanale e contesto turno](#11-ciclo-settimanale-e-contesto-turno) — chiuso
12. [Tempi e orari reali (fonte API)](#12-tempi-e-orari-reali-fonte-api) — chiuso
13. [Lettura PDF turno materiale](#13-lettura-pdf-turno-materiale) — chiuso
14. [Metodo di progettazione PdC](#14-metodo-di-progettazione-pdc) — chiuso
15. [Vincolo di unicità — no doppioni](#15-vincolo-di-unicit%C3%A0--no-doppioni) — chiuso

---

## 1. Glossario sigle

Sigle lette sui turni materiale e sui turni PdC. Ogni voce: sigla →
significato → dove compare.

### Stazioni e impianti

| Sigla | Significato | Note |
|-------|-------------|------|
| **FIOz** | Fiorenza | Deposito/impianto materiale **Trenord**. I treni "nascono" qui come materiale vuoto. |
| **MIce** | Milano Certosa | Stazione **RFI**. Qui il materiale vuoto `U****` cambia numero assumendo una traccia RFI (marcata "i" se ancora vuoto, vedi §1, oppure commerciale con passeggeri). |
| **MIcl** | Milano Centrale | Stazione **RFI**. Usata anche da PdC MI.PG. |
| **MIpg / MIPG** | Milano Porta Garibaldi | **Deposito PdC** principale Trenord. |
| **MIGP** | Milano Greco Pirelli | Impianto/stazione di servizio. |
| **MCPTC** | Indicazione aziendale "materiale in manutenzione" | Segnala che il materiale si trova all'interno di Fiorenza o di un altro impianto di manutenzione. |

### Segmenti del turno

| Sigla | Significato | Note |
|-------|-------------|------|
| **U\*\*\*\*** | Materiale vuoto | Numero che inizia per "U" (es. U8335, U8192). Treno senza passeggeri per posizionamento dal deposito Trenord a stazione RFI (o viceversa). |
| **\*\*\*\*i** | Marker materiale vuoto | Il suffisso "i" identifica treni **il cui materiale è un vuoto** (senza passeggeri, o traccia tecnica di posizionamento/rientro). Esempi: 28335i (testa giornata, materiale da FIOz), 28371i (coda giornata, materiale che si posiziona per pernotto fuori Fiorenza). **Non** è specifico di Fiorenza — marca qualunque movimento vuoto, sia in uscita/rientro impianto aziendale sia tra stazioni RFI per posizionamento notturno. |
| **●** | Preriscaldo | Tempi maggiorati ACCp 80' (dic-feb). |
| **ACCp** | Accessorio in partenza | Preparazione **del treno** (condotta). Vedi §3. |
| **ACCa** | Accessorio in arrivo | Spegnimento **del treno** (condotta). Vedi §3. |
| **CVp** | Cambio Volante in partenza | Il PdC prende il mezzo da un altro PdC. Vedi §5. |
| **CVa** | Cambio Volante in arrivo | Il PdC consegna il mezzo a un altro PdC. Vedi §5. |
| **PK** | Parking | Materiale parcheggiato in stazione durante una pausa (es. refezione in RFI). Vedi §4. |
| **REFEZ** | Refezione | Pausa pasto, 30 min. Vedi §4. |

### Vetture (PdC passeggero)

| Sigla | Significato | Note |
|-------|-------------|------|
| **6AS** | Vettura codice 6AS | Treno su cui il PdC viaggia come passeggero. Es: 6AS MI.PG→Fiorenza. |
| **VOCTAXI** | Vettura occasionale in taxi | Rientro in taxi. Per le regole di quando scatta vedi §7.2 (ordine di priorità). |
| **MM** | Metropolitana | Mezzo di rientro a deposito quando in servizio. |

*Sigle mancanti saranno aggiunte man mano che l'utente le introduce.*

---

## 2. Depositi PdC per linea

### 2.1 Lista depositi Trenord (da dropdown applicativo)

25 voci PdC configurate nel dropdown del builder (screenshot
24/04/2026):

ALESSANDRIA · ARONA · BERGAMO · BRESCIA · COLICO · COMO · CREMONA ·
DOMODOSSOLA · FIORENZA · GALLARATE · GARIBALDI_ALE ·
GARIBALDI_CADETTI · GARIBALDI_TE · GRECO_TE · GRECO_S9 · LECCO ·
LUINO · MANTOVA · MORTARA · PAVIA · PIACENZA · SONDRIO · TREVIGLIO ·
VERONA · VOGHERA

**Nota su MORTARA**: è una voce selezionabile come **contesto di
generazione turni**, ma **non è un deposito abitato da PdC
residenti**. Non c'è personale di macchina che "vive" a Mortara.
È nella lista perché i materiali vi sostano la notte e lì avvengono
CV (deroga, vedi §9.2) e dormite FR (vedi §10.2). TIRANO, che ha
lo stesso status di "non-deposito" per i PdC, **non è** nella lista
del dropdown.

### 2.2 Mia comprensione attuale (IPOTESI, da correggere)

Raggruppamento per corridoio geografico. Quello che credo di
dedurre; tutto da validare con l'utente.

**Gruppo Milano — "grandi" (abilitazioni ampie)**

I tre `GARIBALDI_*` sono **un solo deposito (MI.PG)** diviso in tre
gruppi di PdC con abilitazioni/tipologie diverse. Analogamente i due
`GRECO_*` sono **un solo deposito (MIGP)** con due gruppi.

| Voce dropdown | Deposito reale | Gruppo / abilitazione |
|---------------|---------------|----------------------|
| **GARIBALDI_ALE** | MI.PG | Gruppo che normalmente usa materiale **tipo ALE** (elettrotreni). |
| **GARIBALDI_CADETTI** | MI.PG | Gruppo **neo-assunti già abilitati**. Turni "peggiori" (dormite, orari difficili) — sempre dentro normativa. |
| **GARIBALDI_TE** | MI.PG | TE = trazione elettrica. |
| **GRECO_TE** | MIGP | TE = trazione elettrica. |
| **GRECO_S9** | MIGP | S9 = linea S9. |
| **FIORENZA** | FIORENZA (sia deposito PdC che impianto materiale) | Materiale normalmente **TSR** (acronimo di famiglia di materiale, tipicamente **ALe 711**). |

**Implicazione operativa**: il builder, quando parla di "rientro a
sede", deve considerare `MI.PG` come sede unica per i tre gruppi
GARIBALDI_\*, e `MIGP` come sede unica per i due gruppi GRECO_\*. Il
gruppo è un attributo di abilitazione del PdC, non una sede fisica
diversa.

**Nodo nord-ovest (Sempione, Luino, Como)**

| Deposito | Linee/corridoi ipotizzati |
|----------|---------------------------|
| **GALLARATE** | Snodo Milano-Arona-Domodossola e Milano-Luino. Corridoio Sempione. |
| **ARONA** | Linea Milano-Arona-Domodossola. |
| **DOMODOSSOLA** | Capolinea nord linea Sempione (verso Sv. Svizzera). |
| **LUINO** | Capolinea linea Gallarate-Luino (lago Maggiore, verso Svizzera). |
| **COMO** | Linea Milano-Como-Chiasso. |

**Nodo nord-est (Valtellina, Bergamasca, bresciano)**

| Deposito | Linee/corridoi ipotizzati |
|----------|---------------------------|
| **LECCO** | Milano-Lecco, Lecco-Sondrio, Lecco-Bergamo. Snodo linea Valtellina. |
| **COLICO** | Linea Lecco-Sondrio-Tirano, nodo Colico-Chiavenna. Deposito PdC vero (non solo stazione di servizio). |
| **SONDRIO** | Linea Lecco-Sondrio-Tirano (Valtellina). |
| **BERGAMO** | Milano-Bergamo, Bergamo-Brescia, Bergamo-Treviglio. |
| **TREVIGLIO** | Snodo Milano-Brescia-Verona e Milano-Bergamo. |
| **BRESCIA** | Brescia-Verona, Brescia-Parma, Brescia-Bergamo. |
| **VERONA** | Capolinea est Milano-Verona, linea del Brennero (?). |

**Nodo sud-ovest (Po, Alessandria, Piacenza)**

| Deposito | Linee/corridoi ipotizzati |
|----------|---------------------------|
| **ALESSANDRIA** | Milano-Pavia-Alessandria, Alessandria-Torino. Dati applicativi: 3 corridoi "Milano, Pavia/Po, ASTI". |
| **PAVIA** | Nodo Milano-Pavia, Pavia-Alessandria, Pavia-Mortara. |
| **VOGHERA** | Linea Milano-Voghera-Alessandria, Voghera-Genova (?). |
| **MORTARA** | Linea Milano-Mortara-Alessandria, Mortara-Pavia. |
| **PIACENZA** | Milano-Piacenza-Bologna (?), anche diramazioni per Cremona. |

**Nodo est (Cremonese, mantovano)**

| Deposito | Linee/corridoi ipotizzati |
|----------|---------------------------|
| **CREMONA** | Milano-Cremona, Cremona-Mantova, Cremona-Brescia. |
| **MANTOVA** | Mantova-Cremona, Mantova-Verona, Mantova-Modena (?). |

### 2.3 Regola del rientro a sede

**Regola**: il PdC rientra sempre al proprio deposito di appartenenza.
Vale per **tutti i 25 depositi**, senza eccezioni.

**Eccezione**: il **FR** (Fuori Residenza) è una **modalità di turno**
che scinde dal rientro in deposito nella giornata stessa — il PdC
dorme fuori sede e rientra in una giornata successiva. Vedi §10.

### 2.4 Cose ancora da chiarire

1. **Linee coperte da ogni deposito** (corridoi geografici): la §2.2
   contiene ancora ipotesi per i depositi periferici (Sempione,
   Valtellina, Po, Cremonese). Da validare deposito per deposito
   quando servirà al builder. Non urgente oggi.


---

## 3. Accessori (ACCp, ACCa) e presa/fine servizio

### 3.1 Principio fondamentale

**Regola**: gli accessori (ACCp, ACCa) si applicano **al treno** (mezzo
in condotta). **Non** si applicano alla vettura.

**Quando si applica**: sempre. È la regola generale. Le sottosezioni
specificano i valori e i casi particolari.

### 3.2 Presa e fine servizio con vettura

**Regola**:
- Se il **primo segmento** del turno è una **vettura** → la presa
  servizio è **15 minuti prima** della partenza vettura. Niente ACCp.
- Se l'**ultimo segmento** del turno è una **vettura** → la fine
  servizio è **15 minuti dopo** l'arrivo vettura. Niente ACCa.

**Quando si applica**: solo ai bordi del turno (primo/ultimo
segmento). Se nel mezzo del turno si alternano condotta e vettura, si
applicano ACCp/ACCa solo ai tratti in condotta.

**Esempio**:

Turno che inizia con vettura 6AS MI.PG→Fiorenza (partenza 03:40) e
finisce con vettura VOCTAXI Fiorenza→MI.PG (arrivo 10:32):

- Presa servizio: **03:25** (= 03:40 − 15')
- Fine servizio: **10:47** (= 10:32 + 15')
- Prestazione: 10:47 − 03:25 = **7h22**

**NON confondere con**: ACCp/ACCa della condotta (valori diversi,
vedi §3.3). I 15' pre/post vettura **non** sono accessori, sono
**estensione del servizio** del PdC.

### 3.3 Valori ACCp / ACCa

**Regola**: i valori si applicano **al treno** (condotta). Zero per
la vettura (vedi §3.2 per i 15' pre/post servizio).

**Valori**:

| Caso | ACCp | ACCa |
|------|------|------|
| Condotta standard | **40'** | **40'** |
| Condotta con preriscaldo ● (dic-feb) | **80'** | **40'** |
| Vettura | — | — |

**NON confondere con**: i 15' pre/post vettura (§3.2) — quelli non
sono accessori, sono estensione servizio.

### 3.4 Quando si applicano ACCp e ACCa

**Regola**: si guardano i segmenti **consecutivi nello stesso giro
materiale**. Se tra l'arrivo del treno precedente e la partenza del
successivo c'è **gap**, si applicano gli accessori (ACCa al treno
precedente, ACCp al treno successivo). Se **non c'è gap**, è un
**CV** (vedi §5).

**Quando si applica**: sempre, come criterio base. Le alternative e le
soglie precise di gap sono in §6.

**NON confondere con**: CV e PK. Gli ACC sono **uno dei tre modi**
possibili di trattare un gap — scelta guidata da §6.

---

## 4. Pause: REFEZ, buco, pausa in vettura, PK

Le pause non sono tutte uguali. Ci sono **quattro tipologie** con regole
diverse:

### 4.1 REFEZ (refezione formale)

**Regola**: pausa pasto di **30 minuti** dentro una finestra oraria
prevista. Formalizzata nel turno.

**Finestre orarie**:
- Pranzo: **11:30–15:30**
- Cena: **18:30–22:30**

**Dove**: ovunque sia consentito.

**NON confondere con**: un semplice buco. REFEZ è formale, ha durata
e finestra specifiche; il buco no.

### 4.2 Buco

**Regola**: gap **> 15 minuti** tra due treni in condotta, senza che
sia una refez formale. È comunque considerato pausa utilizzabile dal
PdC.

**Durata minima**: 15 minuti (sotto, non è pausa ma solo tempo
tecnico).

**NON confondere con**: REFEZ. Il buco non ha finestra oraria
obbligatoria, non è una refezione formale.

### 4.3 Pausa in vettura

**Regola**: il PdC può riposare o consumare pasto mentre è passeggero
su una vettura. È considerata una **pausa informale**.

**Non vale come refezione contrattuale**: non sostituisce REFEZ
(§4.1). È solo riposo del PdC durante il posizionamento passivo.

**NON confondere con**: REFEZ formale — la REFEZ ha durata e finestra
specifiche e va dichiarata nel turno; la pausa in vettura no.

### 4.4 PK (Parking)

**Regola**: il **materiale viene messo in sicurezza** (parcheggiato)
dal PdC durante una pausa. Il PdC mette in sicurezza il mezzo (più
veloce dello spegnimento completo), va a mangiare/fare pausa, poi
riparte **con lo stesso materiale**.

**Valori**:

| Voce | Minuti |
|------|--------|
| **PK in arrivo** | **20' minimo** (adattabili se c'è più spazio tra i treni) |
| **PK in partenza** | **20' minimo** (adattabili se c'è più spazio tra i treni) |

I 20' sono la **soglia minima** operativa. Se il gap tra due treni è
maggiore, il PK può estendersi fino a occupare la pausa, ma **mai
sotto i 20'**.

Rispetto all'ACC standard (40' + 40' = 80'), il PK standard è
**20' + 20' = 40'** → accessori effettivamente dimezzati.

**Dove si applica**: **ovunque sia consentito** — stazioni RFI,
depositi, anche **soste notturne** previo accordo con RFI.

**Quando si applica**: in **qualsiasi gap**, purché sia programmato
in fase di elaborazione turno. Non ha soglia minima/massima di gap
(a differenza del CV e dell'ACC). È la modalità più flessibile.

**Non richiede comunicazione fra PdC**: è questa la sua caratteristica
chiave rispetto al CV. Vedi §5 e §6.

**Struttura tipica** (PdC resta con lo stesso materiale):

```
treno arriva → PK in arrivo → REFEZ o buco → PK in partenza → treno parte
```

**Esempio** (treno 23333 a MI.PG, gap minimo):

| Ora | Evento |
|-----|--------|
| 12:00 | Arrivo treno 23333 a MI.PG |
| 12:00–12:20 | PK in arrivo (20' minimo) — sostituisce ACCa 40' |
| 12:20–12:50 | REFEZ (30') |
| 12:50–13:10 | PK in partenza (20' minimo) — sostituisce ACCp 40' |
| 13:10 | Partenza con lo stesso materiale |

Totale gap: 1h10. Con ACCa + REFEZ + ACCp sarebbero stati 40+30+40 =
1h50. Il PK risparmia 40 min al PdC.

Se tra i due treni c'è più tempo (es. gap totale 2h), i PK possono
estendersi (es. 30' + 30') per coprire meglio lo spazio.

**NON confondere con**: CV. PK = stesso materiale, stesso PdC, pausa
in mezzo. CV = scambio di materiale tra PdC diversi, mezzo acceso.

---

## 5. Cambio Volante (CVp / CVa)

### 5.1 Cos'è il CV

**Regola**: il **CV** (Cambio Volante) è uno **scambio diretto del
mezzo** tra due PdC di turni diversi che si passano lo **stesso
materiale**. Il mezzo **non viene spento**.

**Requisito obbligatorio**: i **due PdC devono vedersi e parlarsi**
(il PdC smontante consegna il mezzo al subentrante con passaggio
verbale di consegne). È questa la caratteristica distintiva del CV
rispetto al PK.

**NON confondere con**: una pausa. Il CV non è una pausa del PdC —
è un passaggio di consegna del mezzo tra PdC diversi. Se un PdC vuole
fare pausa tra due condotte, si usa buco / REFEZ / PK, non CV.

**NON confondere con**: PK. Il PK **toglie** il requisito
dell'incontro tra PdC: è la via alternativa quando i due PdC non si
possono vedere.

### 5.2 Tempi CVp / CVa

**Regola**: **non sono valori standard**. Sono **variabili, decisi
nel contesto dei due turni** e devono **combaciare esattamente**:

```
fine CVa del turno A = inizio CVp del turno B
```

**Esempio**: turno A arriva alle 12:30 e ha CVa 20' → fine CVa 12:50.
Il turno B deve avere CVp che inizia **esattamente alle 12:50** per
permettere l'incontro tra i due PdC.

**Nessun range numerico predefinito**: il builder non deve imporre
un min/max sui tempi CVp/CVa. I valori emergono dalla compatibilità
dei due turni coinvolti. Unica regola operativa: se l'incontro
fisico tra i due PdC **non è possibile** (per sforamento 8h30 di
uno dei due turni, o qualsiasi altra ragione operativa), allora il
CV **non si può fare** e si ripiega sul **PK** (vedi §6).

### 5.3 CVp (cambio volante in partenza)

**Regola**: il PdC subentrante **sale** su un mezzo già acceso
dall'altro PdC e riparte con esso.

**Tempo**: `cv_before_min` variabile, da coordinare col CVa del turno
che smonta.

### 5.4 CVa (cambio volante in arrivo)

**Regola**: il PdC smontante conduce fino in stazione, **scende**,
lascia il mezzo acceso all'altro PdC subentrante a cui passa le
consegne verbalmente.

**Tempo**: `cv_after_min` variabile, da coordinare col CVp del turno
che subentra.

---

## 6. Scelta fra CV / ACC / PK in base al gap

**Regola**: per ogni coppia di segmenti consecutivi dello stesso
materiale nel turno PdC, il gap determina le modalità ammesse.

| Gap (min) | Modalità ammesse | Requisito |
|-----------|------------------|-----------|
| **< 65** | **CV** | I due PdC si devono vedere e parlare. |
|           | **PK** | Programmato in fase di elaborazione turno. |
| **65 – 300** | **ACC** (ACCa + ACCp) | Nessuno specifico. |
|               | **PK** | Programmato in fase di elaborazione turno. |
| **> 300** | **ACC** (default) | Comportamento standard: ACCa + ACCp come per 65-300. |
|            | **PK** (opt-in operatore) | Ammesso solo se l'operatore spunta esplicitamente l'opzione "applica PK" in fase di produzione del turno. Non automatico. |

**Osservazioni chiave**:

- **PK è sempre disponibile**, in ogni range di gap. È la modalità
  più flessibile.
- **CV** è ammesso solo sotto i 65 min, **e** richiede che i due PdC
  si incontrino per il passaggio di consegne.
- **ACC** è ammesso solo sopra i 65 min (sotto non c'è fisicamente
  tempo per 40' di ACCa + 40' di ACCp).
- Se i due PdC non si possono incontrare (gap <65 min ma diversa
  sede / impossibilità operativa) → **PK** è la soluzione.

**Perché questa scelta conta**:

- **CV**: nessun accessorio al mezzo (mezzo acceso).
- **PK**: accessori dimezzati (il PdC mette in sicurezza invece di
  spegnere).
- **ACC**: accessori completi (40'+40').

Il builder deve scegliere la modalità **più efficiente compatibile**
col gap e coi vincoli operativi, e dichiararla esplicitamente.

**NON confondere con**: la regola dei 15' pre/post vettura (§3.2) —
quella riguarda i bordi del turno, non i passaggi interni tra treni.

---

## 7. Vetture e rientro a deposito

### 7.1 Cos'è una vettura

**Regola**: una **vettura** è **qualsiasi treno passeggero su cui il
PdC è fuori servizio di guida** (viaggia come passeggero). Non esiste
un "elenco di treni-vettura": qualunque treno commerciale può essere
usato come vettura da un PdC che deve spostarsi.

Sigle specifiche che incontriamo nei turni:
- **VOCTAXI** = vettura **in taxi** (non è un treno).
- Altri codici (es. **6AS**) = vettura come treno commerciale
  specifico.

### 7.2 Priorità mezzi per il rientro passivo a sede

**Regola generale**: la priorità è sempre **vettura di rientro**.
MM e taxi sono alternative che scattano solo in casi specifici.

**Obiettivo operativo**: **non sforare mai le 8h30** di prestazione
totale. Il mezzo di rientro viene scelto per far rispettare questo
limite.

**Ordine**:

1. **Vettura di rientro** (treno commerciale). Si controlla via API
   ARTURO Live (`live.arturo.travel`) se esiste un treno passeggeri
   utile. **Prima scelta sempre**.
2. **MM** (metropolitana). Si usa se la vettura di rientro
   **sforerebbe le 8h30** di prestazione **e** il deposito si trova
   in una località servita dalla MM (tipico: Milano). La MM è una
   "scorciatoia" per non sforare il limite.
3. **Taxi (VOCTAXI)**. Si usa in **tutti gli altri casi**: nessuna
   vettura utile, nessuna MM disponibile, orari notturni, oppure
   qualunque altra condizione in cui serve non sforare le 8h30.

**Esempio** (PdC MI.PG che finisce il turno a Mi.C.LE):
1. Vettura Mi.C.LE → MI.PG se esiste e rientra nelle 8h30.
2. Se la vettura sfora → MM Mi.C.LE → MI.PG (Milano è servita da MM).
3. Se MM fuori esercizio o indisponibile → VOCTAXI.

**Deposito periferico (es. Cremona, Sondrio, Colico)**: se la vettura
sfora le 8h30 e non c'è MM, si va **direttamente a taxi** (si salta
lo step 2).

### 7.3 Condotta come "rientro produttivo" (NON è priorità passiva)

**Regola a sé**: se nel turno materiale un **treno di condotta**
transita dalla stazione di fine produzione fino al deposito del PdC,
il PdC **conduce** quel treno invece di muoversi in modo passivo.
Non è "rientro passivo": è continuazione del servizio produttivo.

**NON confondere con**: la priorità §7.2. §7.2 vale quando non c'è
condotta utile disponibile. Se c'è, il principio produttivo (non
sprecare posizionamenti passivi su treni che puoi guidare) ha
precedenza.

---

## 8. Materiale vuoto (numeri U****)

### 8.1 Cos'è un materiale vuoto

**Regola**: un **materiale vuoto** è un **treno senza passeggeri**
che trasferisce il convoglio tra un **impianto Trenord** (es.
Fiorenza) e una **stazione RFI** (es. Milano Certosa). Il suo numero
inizia per "**U**" (es. U8335, U8192).

**Quando si applica**: in testa e in coda al ciclo giornaliero del
materiale. Il treno "nasce" all'impianto Trenord come materiale
vuoto, si posiziona in stazione RFI, lì **cambia numero** e diventa
traccia RFI (es. 28335i Mi.Certosa → Mi.C.LE). A fine giornata il
ciclo si inverte: rientro da stazione RFI all'impianto come materiale
vuoto, eventualmente preceduto da una traccia "i" di posizionamento.

### 8.2 Cambio numero (aziendale → traccia RFI)

Il materiale vuoto può attraversare **due livelli di numerazione**:

| Tratta | Numero | Natura |
|--------|--------|--------|
| Fiorenza → Mi.Certosa | **U8335** | Numero **aziendale** Trenord (§8.7). Invisibile su PDF e API. |
| Mi.Certosa → Mi.C.LE | **28335i** | Traccia **RFI** marcata "i" (§1). Visibile su PDF, **non** su API (§12.1.1). Treno vuoto, senza passeggeri. |

È lo **stesso materiale fisico**: al passaggio in stazione RFI cambia
solo il numero. Il PdC che sta conducendo continua.

**Nota**: in alcuni cicli il materiale vuoto diventa direttamente
commerciale (senza tappa "i" intermedia). Dipende dalla giornata.

Simmetrico al rientro: un treno che finisce a Mi.Certosa come
commerciale (es. 28192) prosegue fino a Fiorenza come materiale
vuoto (es. U8192), oppure prima come traccia "i" e poi come U****.

### 8.3 Tempi di trasferimento

I tempi della tratta materiale vuoto sono **tempi di trasferimento
materiale**, **condotti dal PdC** (non sono automatici del sistema).
Quindi:

- Contano come **condotta** nel computo del tempo guida.
- Richiedono **ACCp / ACCa / CV / PK** come qualunque altro treno in
  condotta (secondo le regole §3 e §6).
- Il PdC che conduce la tratta vuota può essere lo **stesso** che
  prosegue sul commerciale (nessun CV), oppure può esserci un
  cambio volante a Mi.Certosa (CVa vuoto / CVp commerciale).

### 8.4 Regola di coerenza PdC / materiale vuoto

**Regola**: per coerenza operativa, **lo stesso PdC** che conduce un
segmento commerciale si occupa anche del corrispondente materiale
vuoto da/per Fiorenza.

Nello specifico:
- Se un materiale **esce da Fiorenza come vuoto** → il PdC che lo
  preleva a Fiorenza lo conduce fino a destinazione (o fino al suo
  CVa), **nessun cambio PdC a Mi.Certosa solo per il cambio numero**.
- Se un materiale **termina commerciale in una stazione X** e deve
  rientrare a Fiorenza come vuoto → lo **stesso PdC** che l'ha
  condotto in commerciale lo porta a Fiorenza come U-numero.

**Implicazione per il builder**: non generare split artificiali
PdC-A-commerciale / PdC-B-vuoto. Il vuoto è coda/testa logica del
segmento commerciale e va abbinato allo stesso PdC salvo CV
dichiarato.

### 8.5 Preriscaldo e accessori a Fiorenza

**Regola**: Fiorenza è **impianto di manutenzione**, quindi **il
preriscaldo ● non esiste a Fiorenza**. I mezzi sono normalmente
**tutti in PK**.

**Conseguenza sui tempi**:
- **Nessun ACCp 80'** quando il primo segmento del turno parte da
  Fiorenza come U-numero.
- Il PdC fa comunque **almeno 40 minuti di accessori** all'ingresso
  nel materiale (minimo operativo).

**I 7 minuti FIOz → Mi.Certosa sono INCLUSI negli accessori**: la
percorrenza fisica del materiale vuoto dall'impianto alla stazione
RFI dura **7 minuti fissi** ed è **dentro** i 40' di ACCp. Non si
sommano. Esempio temporale:

| Evento | T | Dettaglio |
|--------|---|-----------|
| ACCp Fiorenza inizia | 04:45 | |
| Spostamento materiale FIOz → Mi.Certosa | 05:18–05:25 | 7' **dentro** i 40' ACCp |
| ACCp Fiorenza termina | 05:25 | Coincide con partenza traccia RFI |
| Partenza 28335i da Mi.Certosa | 05:25 | Nessun gap. Vuoto "i" (§1). |

**Esempio completo** (turno che inizia a Fiorenza, partendo da MI.PG):

| Evento | Tempo |
|--------|-------|
| Presa servizio MI.PG (15' pre-taxi, §3.2) | 03:25 |
| Taxi MI.PG → Fiorenza (durata stimata operativa, §8.5.1) | 03:40 → ~04:00 |
| ACCp Fiorenza (include trasferimento U-numero) | 04:45 → 05:25 |
| Partenza traccia RFI Mi.Certosa (es. 28335i, vuoto) | 05:25 |

### 8.5.1 Trasferimento MI.PG → Fiorenza (TAXI obbligatorio per ora)

**Regola**: ad oggi **non esistono tracce pubbliche** (né RFI né
ARTURO) per il collegamento passivo MI.PG → Fiorenza. Per il
posizionamento del PdC a inizio turno (e simmetricamente per il
rientro a fine turno) si usa sempre un **TAXI**.

**Perché**: la tratta è movimento aziendale interno Trenord, non
pubblicata come traccia viaggiatori. L'API ARTURO non la restituisce.

**Implicazione operativa**:
- L'orario taxi è **inserito dall'operatore** (o stimato dal builder
  con un tempo operativo di default), **non** letto da fonti.
- Finché non esiste una sorgente affidabile, il builder tratta
  questo collegamento come costo fisso in minuti (valore da
  parametrizzare, inizialmente stimato).
- **Futuro**: quando si troverà una fonte (es. orario interno
  Trenord), questa §8.5.1 sarà aggiornata e il builder passerà
  automaticamente alla fonte.

**NON confondere con**: vetture reali (treni commerciali su cui il
PdC viaggia passivo) — quelle sono sempre su API ARTURO. Qui si
parla del solo collegamento aziendale MI.PG ↔ FIOz.

### 8.6 Impianti Trenord che generano materiale vuoto

**Ad oggi, su ramo RFI, Fiorenza è l'unico** impianto da cui
nascono / a cui rientrano materiali vuoti. Tutti gli impianti PdC
possono entrare e uscire da Fiorenza (soggetto alla §8.4 regola di
coerenza).

### 8.7 Numerazione U**** (numero aziendale)

**Regola**: il numero `U****` (es. U8335, U8192) è un **numero
aziendale Trenord**, **non** una traccia RFI. Conseguenze:

- **Non appare sul PDF turno materiale** (che mostra solo tracce RFI,
  §13.1).
- **Non è interrogabile via API ARTURO Live** (`live.arturo.travel`
  espone tracce commerciali; i vuoti sono movimenti interni). Vedi
  §12.1 per il perimetro API.
- **Non ha un orario pubblicato**: la sua durata operativa è la
  percorrenza FIOz → stazione RFI, fissata a **7 min** (§8.5), e
  vive **dentro** gli accessori (ACCp in uscita FIOz, ACCa in
  rientro FIOz).

**Implicazione**: il builder **non deve** chiedere all'API l'orario
di un U-numero. Lo calcola così:
- Uscita FIOz: `partenza_commerciale_MiCertosa − 7 min`
- Rientro FIOz: `arrivo_commerciale_MiCertosa + 7 min`

---

## 9. Spezzare i treni (CV intermedi)

### 9.1 Cosa significa spezzare un treno

**Regola**: un treno commerciale lungo (es. Mi.C.LE → Tirano) può
essere condotto da **più PdC in sequenza**, con uno o più **CV** a
stazioni intermedie. Il treno fisico non si ferma oltre il normale:
cambia solo il PdC al volante.

### 9.2 Dove può avvenire un CV

**Regola**: un CV può avvenire **solo** in stazioni di una di queste
categorie:

1. **Stazione sede deposito PdC** (uno qualsiasi dei 25 depositi
   di §2.1).
2. **MORTARA**, come deroga: pur non essendo sede deposito, è
   stazione abilitata ai CV (presumibilmente per la sua funzione
   di nodo materiali con dormite FR).
3. **Stazione di capolinea dove il treno inverte il senso di
   marcia** (es. **TIRANO** sulla linea della Valtellina).

**Non sono ammessi** CV in stazioni intermedie "di passaggio" senza
deposito e senza inversione (es. un CV a Lecco Maggianico no, perché
è fermata di servizio senza deposito — fossimo a Lecco stazione
invece sì, perché è sede deposito).

### 9.3 Quando conviene spezzare

**Regola**: non esiste una logica univoca. Motivi tipici:

- Dare un **tratto produttivo** a un PdC di un deposito intermedio
  (es. PdC Lecco che subentra a Lecco e conduce fino a Tirano).
- Rispettare il **limite di condotta** (5h30) del primo PdC.
- Altri motivi operativi (bilanciamento carichi, presenza di PdC
  disponibile nel punto X, ecc.).

**Non è obbligatorio spezzare**: se un treno dura un'ora e attraversa
2 depositi, non si deve dividere per forza. Lo spezzamento è una
**leva operativa**, non una regola automatica.

### 9.4 Limiti

**Nessun numero massimo** di CV per treno. Il vincolo reale sono:
- Le regole §6 sui gap CV / ACC / PK.
- Le regole di condotta max per ciascun PdC coinvolto.
- I depositi disponibili lungo la linea (§9.2).

---

## 10. FR e pernotti

### 10.1 Cos'è un FR

**Regola**: il **FR** (Fuori Residenza) è una **modalità di turno**
in cui il PdC termina la prestazione del **giorno 1** in una stazione
**diversa dalla propria sede**, pernotta (albergo/foresteria), e
**il mattino del giorno 2** riprende servizio nella stessa stazione
per rientrare.

**Quando si applica**:
- **Forzato** quando nella stazione di fine giornata non esiste un
  deposito Trenord (es. **MORTARA**, **TIRANO**).
- **Facoltativo** quando in fase di elaborazione turno l'operatore
  sceglie esplicitamente la modalità FR (tipicamente per rendere un
  turno più produttivo senza sforare 8h30).

**Principio operativo**: non siamo **obbligati** a fare dormite FR.
Se il PdC può rientrare in giornata, meglio. FR è una leva per
coprire turni altrimenti impossibili, non la scelta di default.

### 10.2 Stazioni candidate FR

**Regola**: non esiste una lista fissa. Trenord crea dormite **in
base alle esigenze**.

**Certezze operative oggi**:
- **MORTARA**: dormita (non esiste deposito PdC a Mortara).
- **TIRANO**: dormita (non esiste deposito PdC a Tirano).
- Altre stazioni dove **materiali sostano la notte** fuori da un
  deposito PdC: quasi certamente candidate FR.

**In generale**: **tutte le stazioni principali** possono essere
sede FR se c'è esigenza. Il builder non deve assumere una white-list
chiusa.

### 10.3 Struttura del turno FR (giorno 1 + giorno 2)

**Regola**: giorno 1 e giorno 2 sono **la stessa unità-turno PdC**,
non due turni separati. La prestazione si "spezza" sul riposo in
albergo.

**Sequenza**:

```
Giorno 1
  Presa servizio sede → ... produzione ... → fine prestazione in Y
  (Y non è la sede PdC)
  Trasferimento Y-stazione → albergo
  Riposo in albergo

Giorno 2
  Trasferimento albergo → Y-stazione
  Ripresa servizio a Y → ... rientro verso sede ... → fine turno
```

**Il giorno 2 è continuazione del giorno 1**, non un turno
indipendente.

### 10.4 Produttività al rientro (giorno 2)

**Regola**: nel giorno 2 il PdC **deve condurre** quando possibile
(treno di condotta disponibile nella direzione sede). Vettura come
rientro passivo è ammessa solo se **non esiste** una condotta utile.

**Motivazione**: sfruttare il PdC già "fuori casa" per coprire treni
in direzione sede. Principio di produttività già visto in §6 e §7.3.

### 10.5 Riposo FR: durate e cosa include

**Minimo operativo**: **6 ore** fra la fine prestazione giorno 1 e
la ripresa servizio giorno 2.

**Il riposo FR include tutto**: spostamento stazione → albergo,
riposo fisico, spostamento albergo → stazione. Non si sommano tempi
di spostamento separati.

**Unica esclusione**: la **REFEZ**, se viene fatta durante il riposo
FR, non è compresa (ma normalmente la refez cade nel turno
produttivo, non durante la dormita).

**Massimo sensato**: **~10 ore**. Oltre diventa antiproduttivo
(spreco di tempo del PdC).

### 10.5b Riposo FR e riposo tra turni

Il riposo FR è una **cosa a sé** perché giorno 1 e giorno 2 sono un
unico turno-continuazione (§10.3). **Non è** un riposo tra-turni
standard.

I minimi di **11h / 14h / 16h** (riposo tra-turni) si applicano
**dopo la fine del giorno 2**, quando il PdC è finalmente rientrato
a casa.

**Esempio**: FR tra l'11 e il 12. Il 12 il PdC rientra a sede alle
10:00. Il turno successivo sarà il **giorno solare successivo**
(giorno 13), non lo stesso 12.

### 10.6 Vincoli mensili

**Per PdC** (non per turno):
- Massimo **1 FR per settimana**.
- Massimo **3 FR in 28 giorni**.

**Eccezione CADETTI**: nei turni del gruppo **GARIBALDI_CADETTI**
(MI.PG neo-assunti) è ammesso qualche turno più "pesante" in più
rispetto ai gruppi ordinari, nel rispetto dei limiti contrattuali.

> Obiettivo aziendale 2027: chiudere il gruppo CADETTI.

### 10.7 Spunta "FR abilitato" in UI

**Regola** (scelta di design): prima di generare un turno dal
builder, l'operatore deve poter spuntare una casella **"FR
abilitato"** (per ogni deposito). Se spuntata, il builder è
autorizzato a proporre turni con FR quando conviene. Se non
spuntata, genera solo turni giornalieri (ammessi FR **solo se
forzati** da mancanza di deposito nella stazione di fine giornata).

### 10.8 Cose ancora da chiarire

*Nessuna al momento. Punti D17 e D18 chiusi in §10.5 e §10.5b.*

---

## 11. Ciclo settimanale e contesto turno

### 11.1 Un turno PdC è un ciclo, non una giornata

**Regola**: un **turno** è una **sequenza di giornate lavorative
consecutive** separate da riposi. Non è la singola giornata.

Tipicamente (ciclo "5+2"): 5 giornate lavorative + 2 giornate di
riposo. Vedi il turno ALOR_C di esempio in `CLAUDE.md` (5 giornate
LMXGV + S + D + F con varianti calendario).

### 11.2 Primo giorno dopo riposo

**Regola**: il **primo giorno lavorativo dopo il riposo settimanale**
**non** si inizia con un **turno mattina**. Si parte quasi sempre
con un orario più tardo (pomeriggio / sera / notte).

**Motivazione**: dopo il riposo il PdC deve riprendere ritmo; un
inizio mattina forzato subito dopo il riposo è stressante.

### 11.3 Ultimo giorno prima del riposo

**Regola**: l'**ultimo giorno lavorativo prima del riposo
settimanale** deve **finire al massimo alle 15:00** (quando possibile).

**Motivazione**: finire entro le 15 massimizza il riposo reale e
permette al PdC di recuperare meglio per il ciclo successivo.

### 11.4 Riposo settimanale

**Regola**: riposo settimanale **≥ 62 ore consecutive**, **dentro
le quali** devono ricadere **almeno 2 giorni solari interi**.

I 2 giorni solari sono **compresi nelle 62 ore**, non aggiuntivi.

**Esempio**: ultimo turno del ciclo termina sabato alle 14:00. Il
riposo deve durare almeno 62 ore (quindi fino a martedì ~04:00) e
deve includere domenica e lunedì **interi** come due giorni solari
completi.

Se l'ultimo turno finisse domenica alle 10:00, le 62 ore si
chiuderebbero mercoledì ~00:00: ma i due giorni solari interi
(lunedì e martedì) ci stanno dentro — regola rispettata.

### 11.5 Riposo tra giornate (intraturno)

Già definito in `CLAUDE.md`:
- **11 ore** standard tra due giornate consecutive.
- **14 ore** dopo una giornata che finisce tra **00:01 e 01:00**.
- **16 ore** dopo una giornata **notturna** (tra 00:01 e 05:00).

### 11.6 Nota: la "forma a Z" del ciclo

**Origine del nome**: la lettera **Z** rende graficamente il
pattern del ciclo: inizio **tardo** il primo giorno (in alto a
sinistra), attraversamento della settimana, e fine **presto** (max
15:00) l'ultimo giorno (in basso a destra). Il tratto diagonale
della Z rappresenta appunto lo "spostamento" orario tra inizio e
fine del ciclo.

Non è una sigla operativa — è un'indicazione mnemonica della
**forma ottimale** del ciclo turno.

### 11.7 Preferenziale vs rigido

**Regola**: l'orario limite **15:00** dell'ultimo giorno pre-riposo
(§11.3) è **preferenziale**, non rigido. Il builder può sforare se
necessario — ma rispettare la preferenza è desiderabile.

Le regole **rigide** del ciclo sono:
- Riposo settimanale ≥ 62h con 2 giorni solari interi (§11.4)
- Riposo intraturno 11h / 14h / 16h (§11.5)

Le regole **preferenziali** sono:
- Primo giorno post-riposo non inizia mattino (§11.2)
- Ultimo giorno pre-riposo finisce entro le 15:00 (§11.3)

---

## 12. Tempi e orari reali (fonte API)

### 12.1 Principio fondamentale

**Regola**: in fase di sviluppo/runtime, **tutti gli orari reali** —
partenza/arrivo treni commerciali, tempi tratta, tempi vettura fra
stazioni — si prendono dall'**API ARTURO Live** (`live.arturo.travel`).
Non si stimano, non si hard-codano, non si leggono a occhio dal PDF.

**Quando si applica**:
- Quando il builder deve schedulare segmenti (tempi veri, non stime).
- Quando il builder deve inserire una vettura fra due punti (tempi
  treno passeggero fra quelle stazioni).
- Quando il validatore confronta prestazione/condotta sui numeri reali.

**Come si applica**: stessa chiave API già integrata nel progetto e
usata per i treni real-time (vedi `services/arturo_client.py`, memory
`reference_arturo_live_api.md`).

### 12.1.1 Perimetro API — cosa è interrogabile e cosa no

**L'API ARTURO copre solo i treni commerciali con passeggeri**.
**Non copre**:

- **Treni con suffisso "i"** (§1, §13.1). Sono materiali vuoti
  (senza passeggeri) e **non esistono** su ARTURO. Esempio: 28335i,
  28371i. I loro orari si leggono **solo dal PDF** turno materiale
  (§13.2).
- **Materiali vuoti `U****`** (numero aziendale Trenord, §8.7).
  Non sono pubblicati né su PDF né su API. Il builder li calcola
  come 7 min fissi FIOz↔Mi.Certosa, inclusi negli accessori (§8.5).
- **Movimenti taxi/MM interni** al deposito o fra depositi senza
  traccia pubblica.
- **Preparazioni e manovre** all'interno dell'impianto.

**Regola operativa per orari**:

| Tipo segmento | Fonte orario |
|---------------|--------------|
| Commerciale (numero senza "i", senza "U") | **API ARTURO** |
| Vuoto "i" (es. 28335i, 28371i) | **PDF turno materiale** (§13.2) |
| Vuoto `U****` (FIOz↔MiCertosa) | **Calcolato** da §8.7 |
| Vettura passiva (PdC a bordo commerciale) | **API ARTURO** |
| Taxi / MM | **Inserita dall'operatore**, non pubblicata |
| Collegamento MI.PG ↔ FIOz | **Sempre TAXI** (§8.5.1), no fonte pubblica |

**Quando un dato non è disponibile** da nessuna di queste fonti,
vale la regola di dominio scritta nella normativa (§8.5 per Fiorenza,
§3 per accessori, ecc.). **Non inventare** orari.

### 12.2 Ruolo del PDF turno materiale

**Regola**: il PDF turno materiale serve a **identificare la
sequenza** di treni del giro, **non** a leggere gli orari precisi.

Gli orari visibili nel PDF (cifre sotto le bande, vedi §13) sono utili
per:
- Capire la **struttura temporale** (prima/dopo, gap grossi).
- **Disambiguare** quale corsa si intende (se uno stesso numero ha
  più tracce nel giorno).

Ma il dato operativo per costruire un turno PdC **è sempre l'API**.

### 12.3 Tempi vettura fra depositi

**Regola**: non esiste una tabella statica dei tempi vettura fra
depositi. Quando il builder inserisce un passivo (vettura/taxi/MM),
richiede all'API il primo treno passeggero disponibile tra A e B nella
finestra oraria richiesta e ne usa partenza/arrivo reali.

**NON confondere con**: stime a naso ("Lecco-Milano ~1h"). Le stime
servono solo in fase di ragionamento di carta; il codice non le usa.

---

## 13. Lettura PDF turno materiale

### 13.1 Cosa mostra e cosa NON mostra

**Regola**: il PDF turno materiale pubblicato mostra **solo le tracce
commerciali emesse da RFI**. Non mostra i movimenti interni agli
impianti Trenord (es. Fiorenza).

**Il marker "i" indica un materiale vuoto**: ogni volta che sul turno
materiale compare un numero marcato "**i**" (es. 28335i, 28371i),
significa che **quel segmento è un vuoto** — senza passeggeri, o
posizionamento tecnico del materiale. Può trovarsi:

- **In testa giornata** (es. 28335i Mi.Certosa → Mi.C.LE): il materiale
  è appena uscito da un impianto Trenord (tipicamente Fiorenza, §8.1).
  Il passaggio FIOz → Mi.Certosa non compare nel PDF (è movimento
  aziendale interno), ma esiste ed è condotto dal PdC (§8.4, §8.7).
- **In coda giornata** (es. 28371i Tirano → Sondrio): il materiale si
  posiziona per il pernotto fuori residenza. Nessun impianto Trenord
  implicato, è un vuoto su rete RFI per lasciare il convoglio sul
  binario notturno.
- Altre collocazioni lungo il ciclo, ogni volta che il materiale si
  muove senza servizio commerciale.

**Implicazione sul PdC**:
- Se la "i" è in **testa** al giro e il materiale proviene da un
  impianto aziendale (FIOz), la **presa servizio reale** del PdC è
  all'impianto; accessori ACCp lì (§8.5).
- Se la "i" è in **coda** al giro e il materiale pernotta in
  stazione RFI, il PdC conduce il vuoto come qualunque altro
  segmento e l'ACCa si applica alla fine (o c'è CV / rientro in
  vettura secondo §6 e §7).

### 13.2 Scala oraria del PDF

**Regola**: la scala oraria si legge in **due livelli**:

1. **Ore intere**: stampate in alto, come intestazione di colonna
   (es. `3   4   5   6   7   8   9   10 …`). Sono le ore del giorno.
2. **Minuti**: stampati **sotto le bande nere** dei segmenti
   condotta, a livello delle cifre minori (es. `25  45  20  52 8 …`).

Per leggere l'orario di un punto (partenza o arrivo di un segmento):
- si prende la **colonna ora** in cui cade la cifra minuto;
- si compone `HH:MM`.

**Esempio** (giornata P1 turno materiale 1130):

| Punto | Ora colonna | Minuto sotto banda | Orario |
|-------|-------------|---------------------|--------|
| Partenza 28335i (Mi.Certosa) | 5 | 25 | **05:25** |
| Arrivo 28335i (Mi.C.LE) | 5 | 45 | **05:45** |
| Partenza 2812 (Mi.C.LE) | 6 | 20 | **06:20** |
| Arrivo 2812 (Tirano) | 8 | 52 | **08:52** |

**NON confondere con**: valori ACC/PK/gap. Le cifre sotto le bande
sono **orari**, non durate. Le durate si calcolano per differenza
(arrivo − partenza).

### 13.3 Bande e segmenti

**Regola**: ogni **banda nera orizzontale** sotto la riga oraria è un
**segmento di treno commerciale** condotto. Il numero treno è stampato
**sopra** la banda; le due cifre sotto la banda sono **minuto di
partenza** (sinistra) e **minuto di arrivo** (destra).

Tra due bande consecutive:
- **Stessa colonna ora, cifre vicine** → cambio numero in stazione
  con sosta breve (possibile CV o ACC+ACC, vedi §5–§6).
- **Gap visibile** → pausa operativa (PK/REFEZ/buco, vedi §4).

### 13.4 Flusso di lettura raccomandato

Ordine operativo per trascrivere una giornata del turno materiale:

1. Elencare tutti i **numeri treno** della giornata in ordine
   spaziale (sinistra → destra).
2. Per ciascun treno, leggere **partenza** e **arrivo** con la regola
   §13.2 (colonna ora + cifra minuto).
3. Se un treno è marcato "**i**" è un **materiale vuoto** (§1, §13.1):
   - **In testa giornata** e il vuoto proviene da un impianto
     aziendale (tipicamente FIOz): aggiungere mentalmente il
     segmento U\*\*\*\* impianto → stazione-RFI-di-partenza (invisibile
     sul PDF, 7' fissi per FIOz, vedi §8.7).
   - **In coda giornata** per pernotto su stazione RFI (es. Sondrio,
     Tirano): il segmento "i" è già visibile nel PDF con i suoi
     orari, non c'è U-numero aggiuntivo a valle.
4. **Non** stimare tempi tratta: usa l'API (§12.1) quando servono
   valori numerici affidabili.

**Esempio di trascrizione corretta** (P1 materiale 1130 completo):

| # | Treno | Da | A | Partenza | Arrivo | Note |
|---|-------|-----|-----|----------|--------|------|
| 0 | U8335 | Fiorenza | Mi.Certosa | 05:18 | 05:25 | Invisibile (§13.1). 7' fissi dentro ACCp (§8.5, §8.7). |
| 1 | 28335i | Mi.Certosa | Mi.C.LE | 05:25 | 05:45 | "i" di testa → materiale da FIOz |
| 2 | 2812 | Mi.C.LE | Tirano | 06:20 | 08:52 | Commerciale, cambio numero |
| 3 | 2821 | Tirano | Mi.C.LE | 09:08 | 11:40 | Commerciale, inversione Tirano |
| 4 | 2824 | Mi.C.LE | Tirano | 12:20 | 14:52 | Commerciale |
| 5 | 2833 | Tirano | Mi.C.LE | 15:08 | 17:40 | Commerciale |
| 6 | 2836 | Mi.C.LE | Tirano | 18:20 | 20:52 | Commerciale |
| 7 | 28371i | Tirano | Sondrio | 21:25 | 22:00 | "i" di coda → vuoto per pernotto Sondrio |

---

## 14. Metodo di progettazione PdC

### 14.1 Principio fondamentale

**Regola**: un turno PdC si progetta **partendo dai vincoli di
normativa**, non dalla geografia della linea o dall'abitudine ("qui
di solito si fa un CV"). I vincoli di normativa sono le condizioni
che il turno **deve** soddisfare; la geografia è solo lo spazio in
cui il turno esiste.

**Quando si applica**: sempre, sia che il PdC lo scriva un umano con
carta e matita, sia che lo generi il builder automatico.

### 14.2 Ordine di applicazione dei vincoli

Il builder — o il ragionamento manuale — procede in questo ordine:

1. **Vincoli rigidi del turno singolo** (non negoziabili):
   - Prestazione ≤ 8h30 (510 min), ≤ 7h se notturno (vedi §11, §1).
   - Condotta ≤ 5h30 (330 min).
   - REFEZ 30' dentro finestra 11:30–15:30 o 18:30–22:30 (§4.1).
   - Accessori corretti (§3) sui segmenti in condotta.
2. **Vincoli rigidi di ciclo** (legame con giornate adiacenti):
   - Riposo intraturno 11h / 14h / 16h (§11.5).
   - Riposo settimanale ≥ 62h (§11.4).
3. **Vincoli di sede e deroghe**:
   - Deposito PdC di appartenenza coerente con la linea (§2).
   - CV solo in stazioni ammesse (§9.2).
   - FR entro limiti 1/settimana, 3/28gg (§10).
4. **Preferenze** (non rigide):
   - Primo giorno post-riposo non mattino (§11.2).
   - Ultimo giorno pre-riposo ≤ 15:00 (§11.3).

Un candidato turno si costruisce rispettando il punto 1, poi il 2,
poi il 3, e infine si **valuta** contro il 4.

### 14.3 Cosa NON guida la progettazione

- **NON** "lungo questa linea ci deve essere un CV a X" → i CV
  emergono come conseguenza dei vincoli (prestazione/condotta che
  saturano, cambio turno fra depositi), non come scelta a priori.
- **NON** "di solito la mattina si va in Valtellina" → di solito è
  descrittivo, non prescrittivo. La normativa prescrive.
- **NON** "è comodo fare refezione a Lecco" → la REFEZ si fa dove
  è ammessa e dentro la finestra oraria, sulla base di gap
  operativi, non di comodità geografica.

**NON confondere con**: conoscenza operativa (sapere che Tirano
ammette CV per inversione, che Lecco è sede deposito) — quella è
materiale d'ingresso alla normativa, non un sostituto. I fatti
geografici **alimentano** i vincoli, non li rimpiazzano.

### 14.4 Come si applica in pratica al caso P1

Per costruire il PdC 1 di P1 si parte così:

1. **Materiale**: conosciuto (segmenti commerciali + U-numero di
   testa/coda).
2. **Depositi PdC coinvolgibili**: MI.PG, Lecco, Sondrio (§2.1).
3. **Primo candidato**: PdC MI.PG che prende a Fiorenza e spinge
   il materiale finché **prestazione + condotta + REFEZ** restano
   dentro i limiti (punto 1 di §14.2).
4. Al punto in cui un vincolo sta per saturare, **lì** emerge la
   necessità di un CV, in una stazione ammessa (§9.2). Prima di
   allora, nessun CV arbitrario.
5. Si valuta poi la compatibilità col ciclo (punto 2 di §14.2) e
   con la sede (punto 3).

**Esempio anti-pattern**: "il PdC 1 fa CV a Lecco perché Lecco è a
metà strada" → sbagliato. Giusto: "il PdC 1 prosegue fino a X
perché a X la condotta supera 5h30 / la prestazione supera 8h30 / è
la prima stazione ammessa §9.2 oltre quel limite". Se quel limite
cade a Lecco, ok; se cade a Tirano, è Tirano.

---

## 15. Vincolo di unicità — no doppioni

### 15.1 Principio fondamentale

**Regola**: ogni **segmento di treno** (commerciale o U-numero) del
turno materiale si assegna a **un solo** PdC. Nessun treno può
apparire in due PdC distinti dello stesso giorno.

**Quando si applica**: sempre, sia nella generazione manuale sia
nel builder automatico. Vale per l'intero ciclo giornaliero del
materiale e anche per il collegamento fra giornate consecutive
(P1 → P2 → …).

### 15.2 Implementazione nel builder

Il builder mantiene una **pool di segmenti disponibili** inizializzata
con tutti i treni del turno materiale (più gli U-numeri di testa e
coda, §8). Ogni volta che costruisce un PdC e gli assegna un
segmento, **rimuove** quel segmento dalla pool. Al termine:

- **Pool vuota** → coerente: tutto il materiale è coperto.
- **Pool non vuota** → errore: ci sono treni orfani, serve un PdC
  aggiuntivo o rivedere i confini dei PdC esistenti.
- **Tentativo di usare un segmento già assegnato** → errore:
  doppione, turno scartato.

### 15.3 Cosa conta come "usato"

Un segmento si considera usato quando compare nel PdC come:

- **Condotta** (il PdC guida il treno).
- **Vettura** (il PdC viaggia passivo a bordo di quel treno). Non
  usabile per nessun altro ruolo in un altro PdC.
- **CV in partenza / in arrivo** (il PdC prende o consegna il
  mezzo): il segmento è "usato" per la parte di condotta che
  precede/segue il CV — la sezione post-CV resta un "nuovo" segmento
  assegnabile all'altro PdC.

**NON confondere con**: un treno che viene spezzato da un CV (§9).
In quel caso il treno conta **due volte** come segmento di condotta
(prima parte per PdC-A, seconda per PdC-B). Non è un doppione, è
una legittima divisione del segmento, autorizzata solo perché c'è
un CV dichiarato in stazione ammessa (§9.2).

### 15.4 Conseguenza sui materiali vuoti

I **segmenti U-numero** (§8.7) seguono la stessa regola:

- U\*\*\*\* di testa (FIOz → Mi.Certosa) va assegnato al **primo PdC**
  della giornata, quello che prende servizio a Fiorenza (§8.4
  coerenza).
- U\*\*\*\* di coda (Mi.Certosa → FIOz) va assegnato all'**ultimo PdC**
  che porta il materiale in RFI prima del rientro.
- Se il materiale **pernotta fuori residenza** (es. a Sondrio), non
  c'è U-numero di coda giornaliero: il materiale resta sul binario
  e riparte il giorno dopo senza rientro FIOz.
