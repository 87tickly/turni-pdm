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

1. [Glossario sigle](#1-glossario-sigle) — in corso
2. [Depositi PdC per linea](#2-depositi-pdc-per-linea) — *TODO*
3. [Accessori (ACCp, ACCa) e presa/fine servizio](#3-accessori-accp-acca-e-presafine-servizio) — in corso
4. [Pause: REFEZ, buco, pausa in vettura, PK](#4-pause-refez-buco-pausa-in-vettura-pk) — in corso
5. [Cambio Volante (CVp / CVa)](#5-cambio-volante-cvp--cva) — in corso
6. [Scelta fra CV / ACC / PK in base al gap](#6-scelta-fra-cv--acc--pk-in-base-al-gap) — in corso
7. [Vetture e rientro a deposito](#7-vetture-e-rientro-a-deposito) — *TODO*
8. [Materiale vuoto (numeri U****)](#8-materiale-vuoto-numeri-u) — *TODO*
9. [Spezzare i treni (CV intermedi)](#9-spezzare-i-treni-cv-intermedi) — chiuso
10. [FR e pernotti](#10-fr-e-pernotti) — chiuso
11. [Ciclo settimanale e contesto turno](#11-ciclo-settimanale-e-contesto-turno) — chiuso
12. [Tempi vettura reali tra stazioni](#12-tempi-vettura-reali-tra-stazioni) — *TODO*

---

## 1. Glossario sigle

Sigle lette sui turni materiale e sui turni PdC. Ogni voce: sigla →
significato → dove compare.

### Stazioni e impianti

| Sigla | Significato | Note |
|-------|-------------|------|
| **FIOz** | Fiorenza | Deposito/impianto materiale **Trenord**. I treni "nascono" qui come materiale vuoto. |
| **MIce** | Milano Certosa | Stazione **RFI**. Qui il materiale vuoto cambia numero e diventa commerciale. |
| **MIcl** | Milano Centrale | Stazione **RFI**. Usata anche da PdC MI.PG. |
| **MIpg / MIPG** | Milano Porta Garibaldi | **Deposito PdC** principale Trenord. |
| **MIGP** | Milano Greco Pirelli | Impianto/stazione di servizio. |
| **MCPTC** | *Da confermare* | Letta nel turno 1130 (Lv5) in prossimità di Mi.Certosa. Probabile sigla di impianto. |

### Segmenti del turno

| Sigla | Significato | Note |
|-------|-------------|------|
| **U\*\*\*\*** | Materiale vuoto | Numero che inizia per "U" (es. U8335, U8192). Treno senza passeggeri per posizionamento dal deposito Trenord a stazione RFI (o viceversa). |
| **\*\*\*\*i** | *Da confermare* | Suffisso "i" (es. 28335i, 28371i). Sospetto: treno "interno" o di trasferimento. |
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
| **VOCTAXI** | Vettura occasionale in taxi | Usato quando manca un treno utile. Taxi ammesso **solo di notte** o **al limite 8h30 prestazione**. |
| **MM** | Metropolitana | Mezzo di rientro a deposito quando in servizio. |

*Sigle mancanti saranno aggiunte man mano che l'utente le introduce.*

---

## 2. Depositi PdC per linea

### 2.1 Lista depositi Trenord (da dropdown applicativo)

25 depositi PdC configurati (screenshot 24/04/2026):

ALESSANDRIA · ARONA · BERGAMO · BRESCIA · COLICO · COMO · CREMONA ·
DOMODOSSOLA · FIORENZA · GALLARATE · GARIBALDI_ALE ·
GARIBALDI_CADETTI · GARIBALDI_TE · GRECO_TE · GRECO_S9 · LECCO ·
LUINO · MANTOVA · MORTARA · PAVIA · PIACENZA · SONDRIO · TREVIGLIO ·
VERONA · VOGHERA

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
dal PdC durante una pausa. Il PK **dimezza** i tempi accessori: il
PdC mette in sicurezza il mezzo (più veloce dello spegnimento
completo), va a mangiare/fare pausa, poi riparte **con lo stesso
materiale**.

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

**Esempio** (treno 23333 a MI.PG):

| Ora | Evento |
|-----|--------|
| 12:00 | Arrivo treno 23333 a MI.PG |
| 12:00–12:20 | PK in arrivo (20') — sostituisce ACCa 40' |
| 12:20–12:50 | REFEZ (30') |
| 12:50–13:20 | PK in partenza (30') — sostituisce ACCp 40' |
| 13:20 | Partenza con lo stesso materiale |

Totale gap: 1h20. Con ACCa + REFEZ + ACCp sarebbero stati 40+30+40 =
1h50. Il PK risparmia ~30 min al PdC.

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

**Regola**: dopo l'ultimo tratto produttivo del turno, il PdC deve
rientrare al proprio deposito (§2.3). La scelta del mezzo passivo
segue una scala di priorità fissa:

1. **Vettura** (treno commerciale). Si controlla via **API ARTURO
   Live** (`live.arturo.travel`) se esistono treni passeggeri utili
   che coprono il tragitto stazione-arrivo → deposito sede.
2. **MM** (metropolitana). Si usa quando:
   - nessuna vettura utile è disponibile, **oppure**
   - le vetture disponibili sforerebbero il limite **8h30** di
     prestazione totale del turno.
3. **VOCTAXI** (taxi). Si usa quando **non esiste nessun
   spostamento convenzionale** (né vettura né MM):
   - es. deposito periferico senza MM (Cremona, Sondrio, Colico…),
   - es. orari notturni fuori esercizio MM,
   - es. tragitti per cui non passa nessun treno passeggero utile.

**Esempio** (PdC MI.PG che finisce il turno a Mi.C.LE):
1. Prima scelta: prendere una vettura Mi.C.LE → MI.PG se disponibile
   entro il budget 8h30.
2. Se non c'è o sfora: MM Mi.C.LE → MI.PG.
3. Se MM fuori esercizio (notte): VOCTAXI.

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
**commerciale** (es. 28335i, 2812…). A fine giornata il ciclo si
inverte: rientro da stazione RFI all'impianto come materiale vuoto.

### 8.2 Cambio numero (vuoto → commerciale)

**Esempio**:

| Tratta | Numero |
|--------|--------|
| Fiorenza → Mi.Certosa | **U8335** (materiale vuoto) |
| Mi.Certosa → Mi.C.LE (e oltre) | **28335i** (commerciale) |

È lo **stesso materiale fisico**: al passaggio in stazione RFI cambia
solo il numero ufficiale. Il PdC che sta conducendo continua.

Simmetrico al rientro: un treno che finisce a Mi.Certosa come
commerciale (es. 28192) prosegue fino a Fiorenza come materiale
vuoto (es. U8192).

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

**Esempio**:

| Evento | Tempo |
|--------|-------|
| Presa servizio MI.PG | T |
| Vettura 6AS → Fiorenza | +~25 min |
| ACCp Fiorenza | **≥ 40'** (niente ● nemmeno in inverno) |
| Condotta U-numero Fiorenza → Mi.Certosa | — |

### 8.6 Impianti Trenord che generano materiale vuoto

**Ad oggi, su ramo RFI, Fiorenza è l'unico** impianto da cui
nascono / a cui rientrano materiali vuoti. Tutti gli impianti PdC
possono entrare e uscire da Fiorenza (soggetto alla §8.4 regola di
coerenza).

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

## 12. Tempi vettura reali tra stazioni

*Sezione da popolare. Fonte: API ARTURO Live (`live.arturo.travel`).*
