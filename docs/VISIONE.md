# VISIONE — Cosa stiamo costruendo (draft v0.1)

> Documento ad alta quota. Cosa è il programma, per chi, cosa risolve,
> cosa NON è. Le scelte tecniche stanno in `STACK-TECNICO.md`.
>
> **Scopo di questo file**: dopo averlo letto, una persona deve poter
> dire in 30 secondi cosa stiamo costruendo, perché, e perché conta.

---

## 1. Frase manifesto

**Costruiamo un sistema operativo per la pianificazione ferroviaria
nativa, che parte dall'offerta commerciale e arriva al singolo
macchinista, senza scorciatoie e senza importare formati esterni.**

Non un parser di PDF. Non un foglio Excel evoluto. Non un clone di
un sistema esistente. Un programma che **costruisce** il piano del
servizio dal contratto commerciale fino a chi guida il treno il
27/04/2026 alle 06:39.

---

## 2. Il problema reale

In un'azienda ferroviaria oggi (esempio Trenord, ma vale per
qualsiasi vettore) la pianificazione vive in **silos disconnessi**:

```
PdE Excel/Numbers  ──┐
                     │
Turno materiale PDF ─┼──── nessun database unificato.
                     │     Tre fonti che dicono cose
Turno PdC PDF ───────┘     che dovrebbero coincidere
                           e a volte non coincidono.
```

Conseguenze:
- Modifiche a una corsa commerciale non si propagano da nessuna parte
- Le revisioni provvisorie (RFI comunica un'interruzione → modifiche
  a giro + PdC) sono operazioni manuali con margini di errore
- Il personale non sa con certezza quale revisione del proprio turno
  è quella valida oggi
- Manutenzione, pianificatori, gestione personale lavorano su carte
  diverse della stessa partita
- La generazione automatica di turni materiali e turni PdC è
  approssimata o assente

I sistemi software in uso oggi tentano di **importare** queste fonti
e cucirle insieme con parser fragili. È un approccio inverso: parte
dall'output cartaceo invece che dall'input commerciale.

---

## 3. Cosa fa il nostro programma

### 3.1 Quattro funzioni primarie

1. **Importa la proposta commerciale** (PdE) come **fonte unica di
   verità**. Niente PDF, niente parser fragili: si legge la fonte
   strutturata che già esiste (Numbers, Excel, eventualmente XML
   futuro). Una volta letta, le 10.000+ corse diventano dati
   operativi.

2. **Genera il giro materiale** (turno materiale) sulla base del
   PdE. Algoritmo nativo: dato l'elenco delle corse + le località
   di manutenzione + la dotazione fisica del materiale, costruisce
   le rotazioni dei convogli rispettando vincoli fisici (composizione,
   capienza, ciclo chiuso, manovre, manutenzione programmata).

3. **Genera il turno PdC** sulla base del giro materiale. Algoritmo
   nativo: dato il giro materiale + i depositi PdC + le abilitazioni
   personale, costruisce i turni del personale di macchina rispettando
   la **normativa Trenord** (max 8h30/7h, condotta max 5h30,
   refezione 30' in finestra, CV in stazioni ammesse, FR entro limiti,
   ciclo settimanale 5+2 con riposo ≥ 62h, ecc.).

4. **Assegna le persone** ai turni. Anagrafica del personale +
   indisponibilità (ferie, malattia, ROL, sciopero, formazione) +
   qualifiche → ogni giornata di ogni turno PdC è coperta da una
   persona reale. La revisione provvisoria (es. interruzione RFI)
   viene cascade automaticamente: chi guidava il treno X il 27/04
   viene riassegnato secondo il nuovo PdC.

### 3.2 Quinta funzione: revisioni provvisorie

Quando RFI comunica un'interruzione di linea (es. "Como-Lecco chiusa
15-30 aprile"), il programma:

1. Riceve la comunicazione
2. Ricalcola **giro materiale** per la finestra interessata (treni
   deviati, sostituiti, soppressi → corse alternative o bus)
3. Ricalcola **turno PdC** per propagare le modifiche
4. Aggiorna le **assegnazioni persone** automaticamente
5. Notifica i ruoli interessati (manutenzione, personale, gestione)

Il piano base resta intatto, la revisione provvisoria sostituisce
solo la finestra temporale. Quando la finestra finisce, si torna al
piano base.

---

## 4. Per chi è (i 5 ruoli)

Il programma è uno strumento collaborativo per **5 ruoli distinti**
in azienda ferroviaria. Ogni ruolo ha la sua **dashboard dedicata**
con schermate, azioni e permessi propri.

| Ruolo | Cosa fa | Ha bisogno di |
|-------|---------|---------------|
| **Pianificatore Giro Materiale** | Costruisce e revisiona i giri materiale dal PdE | Vista PdE (corse), algoritmo costruzione giri, editor giri (modifica manuale dove serve), validatore vincoli fisici |
| **Pianificatore Turno PdC** | Costruisce e revisiona turni PdC dai giri | Vista giri materiale, algoritmo costruzione PdC, editor PdC, validatore normativa, gestione cicli settimanali |
| **Manutenzione** | Gestisce dotazione fisica del materiale per deposito | Inventario per località manutenzione, manutenzioni programmate, spostamenti tra depositi, dotazione "fuori servizio" |
| **Gestione Personale** | Anagrafica + assegnazione persone ai turni + gestione indisponibilità | Calendario persone, abbinamento persona → turno, ferie/ROL/malattia, sostituzioni |
| **Personale finale** (PdC) | Vede il **proprio** turno, segnala problemi, richiede ferie | Dashboard personale ridotta: il mio turno, le mie ore, le mie ferie, comunicazioni operative |

Le 5 dashboard non sono "pannelli diversi della stessa interfaccia".
Sono **applicazioni separate** dentro lo stesso sistema, con un
modello dati condiviso e permessi diversi.

---

## 5. Cosa NON è il programma

Esplicito, anti-scope-creep:

1. **Non è un'app di biglietteria**. Niente vendita, niente tariffe,
   niente carrello. Il PdE è input, non output da pubblicare al
   cliente finale.
2. **Non è un sistema di tracciamento real-time da zero**. Per quello
   esiste già **ARTURO Live** (live.arturo.travel). Il programma
   **consuma** ARTURO Live come fonte di dati real-time per chiudere
   il loop "chi sta facendo cosa ORA", non lo replica.
3. **Non è un sistema di manutenzione predittiva del materiale**.
   Gestiamo dotazione (chi sta dove), non guasti, ricambi, OEM.
4. **Non è un payroll / busta paga**. Tracciamo ore lavorate per
   normativa (8h30, riposo, FR), non per pagamento.
5. **Non è un sostituto di RFI**. Riceviamo le sue comunicazioni
   (interruzioni linea, deviazioni), non le originiamo.
6. **Non è solo Trenord**. Il programma è multi-tenant fin dal
   modello dati: quando arriverà SAD, TILO, Trenitalia, Tper, ognuno
   userà il proprio insieme di regole operative configurabili (vedi
   `MODELLO-DATI.md` §3 `azienda.normativa_pdc`).

---

## 6. Principi guida

### 6.1 Costruzione, non importazione

Il programma **costruisce** il piano operativo a partire dall'unica
fonte autorevole (il PdE). Non importa output di altri sistemi (PDF
turno materiale, PDF turno PdC) per "ricostruire" lo stato. La
costruzione è un algoritmo deterministico a partire da regole
documentate.

### 6.2 Niente parser fragili come ingresso primario

Il PdE Numbers/Excel è **strutturato** — si legge come tabella, non
si parsa pixel per pixel come un PDF. Eventuali parser di documenti
esistenti (PDF turno materiale Trenord) servono **solo come
validatori incrociati** o come dati di seed iniziale, mai come fonte
primaria.

### 6.3 Modello dati a piramide (vedi `MODELLO-DATI.md` v0.5)

```
LIV 1   CORSA COMMERCIALE     (dal PdE)
        ↓
LIV 2   GIRO MATERIALE        (generato)
        ↓
LIV 3   TURNO PdC             (generato)
        ↓
LIV 4   PERSONA + ASSEGNAZIONE (anagrafica)
        ↓
LIV 5   ESERCIZIO REAL-TIME   (consumo ARTURO Live)
```

Ogni livello consuma quello sopra. Niente duplicazione, propagazione
automatica.

### 6.4 Multi-tenant fin dal giorno 1

Ogni entità porta `azienda_id`. Default `'trenord'`, ma struttura
predisposta per N aziende. La normativa specifica (8h30 Trenord,
forse 8h SAD) vive in `azienda.normativa_pdc` come JSON
configurabile.

### 6.5 Cinque dashboard, un solo modello dati

L'interfaccia è specializzata per ruolo, ma i dati sono unificati.
Il pianificatore PdC vede i giri materiali in sola lettura. Il
manutentore vede l'inventario dei suoi depositi. Il PdC personale
vede solo il suo turno. **Stessa verità, viste diverse.**

### 6.6 Revisioni provvisorie tracciate, mai overwrite

Il piano base resta sempre. Le revisioni provvisorie sono entità
separate con causa esterna esplicita (RFI, sciopero, evento) e
finestra temporale. Storia preservata, query coerenti.

### 6.7 Sviluppo iterativo, MVP prima

Il primo MVP non risolve tutti i 5 ruoli. Risolve UN ruolo (il più
critico) con UN flusso end-to-end. Da lì si itera. Il piano è in
`PIANO-MVP.md` (FASE C documento 7).

---

## 7. Successo: come sappiamo che funziona

Il programma è "funzionante" quando una persona Trenord (in
qualsiasi dei 5 ruoli) può, davanti al monitor:

1. Vedere il piano del giorno corrente per la sua area di
   competenza
2. Identificare istantaneamente se c'è una revisione provvisoria
   attiva e perché
3. Modificare ciò che gli compete (ruolo permettendo) con
   propagazione automatica agli altri ruoli interessati
4. Avere certezza che la fonte mostrata è la più recente

E il programma è "industriale" quando questo vale per:
- 365 giorni l'anno con orario base annuale + revisioni intra-anno
- 10.000+ corse commerciali
- 100+ giri materiali
- 200+ turni PdC
- 1000+ persone
- 5 ruoli concorrenti senza conflitti

Non ci arriviamo al primo MVP. Ma il modello dati e l'architettura
**devono essere disegnati per arrivarci** senza riscritture.

---

## 8. Ambito di rilascio

| Step | Cosa | Quando |
|------|------|--------|
| **MVP v1** | Un solo ruolo, un solo flusso (probabile: import PdE → vista corse) | Da definire in `PIANO-MVP.md` |
| **v1.0** | Tutti e 5 i ruoli con dashboard funzionanti, ma solo Trenord | TBD |
| **v1.x** | Revisioni provvisorie con cascading PdC | TBD |
| **v2.0** | Multi-tenant: secondo cliente (TILO/SAD/altri) | TBD |
| **v2.x** | Integrazione completa con ARTURO Live (loop real-time) | TBD |

Niente date stringenti. Il principio è "un passo alla volta
completato bene" (METODO-DI-LAVORO.md regola 3).

---

## 9. Riferimenti

- `docs/MODELLO-DATI.md` v0.5 — modello concettuale (12 entità, 5
  vincoli)
- `docs/NORMATIVA-PDC.md` — fonte verità Trenord (15 capitoli)
- `docs/METODO-DI-LAVORO.md` — framework di sviluppo
- `docs/STACK-TECNICO.md` — scelte tecniche (FASE C doc 2, in coda)
- `docs/RUOLI-E-DASHBOARD.md` — dettaglio 5 dashboard (FASE C doc 3)
- `docs/LOGICA-COSTRUZIONE.md` — algoritmo PdE → giro → PdC (FASE
  C doc 4)
- `docs/PIANO-MVP.md` — primo MVP girabile (FASE C doc 7)

---

**Fine draft v0.1**. Da revisionare con l'utente.
