# Prompt per Claude Design — Gantt turno PdC (ispirato al PDF originale)

> Copia/incolla su claude.ai/design. Repo + cartella locale
> `COLAZIONE` già collegati.

---

## Contesto

Il **Gantt della giornata PdC** è il componente più importante
dell'app. Oggi esiste in `frontend/src/components/PdcGanttV2.tsx`
(1230 righe, già oggetto di `docs/PROMPT-claude-design-gestione.md` che
ha prodotto un primo redesign) e in `AutoBuilderGantt.tsx` (Gantt
usato nei risultati del builder automatico).

L'utente vuole ora un secondo giro di ridisegno che si avvicini di
più all'**aspetto del Gantt del PDF ufficiale Trenord** (dove i turni
sono stampati e letti dai PdC in servizio), pur mantenendo i vantaggi
interattivi del web.

## Riferimenti visivi

Salvali in `docs/screenshots/gantt-pdf-reference-*.png` prima di
iniziare. Sono 4 screenshot che ti mostrano:

1. **PDF pagina 386-387 (ALOR_C giorni 4 LMXGV + SD + 5 LMXGV + S + D)**
   – esempio "pulito" di turno reale con S.COMP, preriscaldo `●`,
   multiple giornate impilate.
2. **PDF pagina 388 (turno 7 LMXGV + S + D)** – esempi con CVp, REFEZ
   in stazione intermedia, linea produttiva continua con più treni.
3. **PDF intestazione turno** – fascia header con logo TRENORD,
   IMPIANTO, TURNO, PROFILO, DAL, AL.
4. **Output attuale del nostro builder (UI web corrente)** – per
   confronto: oggi è una lista di "card" con blocchi colorati, senza
   asse oraria chiara, metriche in riga.

## Cosa redesignare

**Componenti**:
- `frontend/src/components/AutoBuilderGantt.tsx` (Gantt post-generazione
  automatica) — PRIMARIO
- `frontend/src/components/PdcGanttV2.tsx` (Gantt dettaglio turno
  esistente) — SECONDARIO, da uniformare

**Pagine**: `AutoBuilderPage.tsx`, `PdcPage.tsx`

## Principi di design (la "falsa riga")

Dal PDF originale mantenere:

1. **Asse orario continua** 0-24h in ticks grandi ogni ora (segmenti
   orizzontali con separatori verticali), rendered in modo pulito
2. **Blocchi compatti** sopra l'asse — un blocco = un segmento
3. **Label verticali** sul blocco con:
   - Numero treno (es. `10042`) in grassetto
   - Stazione di destinazione sotto (`MIro`, `MORT`, `VOGH`) in minuto
4. **Distinzione grafica tipi blocco**:
   - **Condotta** → barra nera spessa continua
   - **Vettura (deadhead)** → barra punteggiata/tratteggiata (come nel
     PDF, parentesi `(10020 AL)`)
   - **Refezione** → etichetta `REFEZ <stazione>` con barra sottile
   - **Preriscaldo** → simbolo `●` prima del numero treno (nel PDF è
     un bullet nero)
   - **CVp / CVa** → prefisso `CVp` / `CVa` nell'etichetta
   - **S.COMP** → barra grande punteggiata tutta la giornata con
     etichetta `S.COMP <stazione>` al centro
5. **Minuti inferiori** sotto ogni segmento: nel PDF ogni segmento ha
   sotto due numeri in apice (minuti di inizio e fine espressi a 2
   cifre). Sono criptici per un dispatcher moderno; sostituirli con
   `HH:MM → HH:MM` sotto ogni blocco in font piccolo (senza ingombro).
6. **Colonna metriche a destra** fissa: `Lav`, `Cct`, `Km`, `Not`, `Rip`
   come nel PDF, ma con valori formattati human (es. `7h31` invece di
   `07:31`).
7. **Header giornata** a sinistra tipo "8 [07:18] [14:49]" (numero
   giornata + inizio + fine) — compatto, allineato verticalmente.
8. **Etichetta variante calendario** (LMXGV, S, SD, D, F) in alto a
   sinistra del blocco giornata, font grande grassetto (lettera corta,
   massima leggibilità per il dispatcher).

Dal Gantt attuale del web **mantenere**:

- Interattività: hover su blocco mostra tooltip con dettagli treno,
  click apre drawer `TrainDetailDrawer`
- Palette colori Kinetic Conductor (blu per condotta, grigio
  tratteggiato per vettura, giallo per refezione) — ok contrasto ma
  più vicino al "bianco/nero" del PDF se aiuta la leggibilità
- Riga warning/violazioni sotto il Gantt (es. WARN_DATA_MISMATCH,
  WEEKLY_HOURS_HIGH) — tenere, ma renderla meno invasiva
- Metriche top bar (Cct, Prest, Refez) in chip — tenere
- Menu contestuale `.right-click` per eliminare/sostituire blocchi

## Cosa cambia rispetto alla versione attuale

1. **Densità**: oggi ogni blocco è visivamente troppo grosso e
   "cardato". Nel redesign i blocchi sono **sottili come barre**
   (altezza ~18-22px) con label verticale tipo PDF. Un'intera giornata
   deve stare in una riga di altezza max ~60px.
2. **Multi-giornata impilate**: in PdcPage la stessa giornata può avere
   3 varianti (LMXGV, S, D). Nel PDF sono 3 righe Gantt impilate
   nella stessa "pagina" del turno. Voglio lo stesso nel web:
   tre strisce Gantt sovrapposte con etichetta variante a sinistra,
   allineate sullo stesso asse orario.
3. **Colonna metriche uniforme** a destra, allineata per tutte le
   varianti, come nel PDF (Lav/Cct/Km/Not/Rip).
4. **Niente chip/card intorno ai segmenti**: via border arrotondati e
   sfondi pieni. Voglio il look "stampato".

## Cosa NON cambiare

- Logica di parsing/rendering dei segmenti (`segments` props)
- Props e API dei componenti (`AutoBuilderGantt`, `PdcGanttV2`) —
  cambia solo la render, non l'interfaccia
- Menu contestuale e drawer di dettaglio treno
- Breakpoint responsive (il Gantt va bene da 1200px in su,
  mobile-fallback già esiste)

## Vincoli funzionali da preservare

- Il Gantt deve renderizzare correttamente turni:
  - Senza treni (S.COMP giornata intera)
  - Con 1 treno singolo
  - Con 7-8 segmenti (produttivo + vetture + refez)
  - Con overnight (fine > 24:00, es. turno 22:00-02:00)
- Click/hover/right-click devono funzionare sui blocchi
- Warning violazioni (colorati) devono essere chiaramente visibili

## Cosa mi aspetto da te

1. **Hi-fi mockup** del nuovo Gantt in 4 varianti:
   - Turno singola giornata con 4 treni (tipico auto-builder)
   - Turno con 3 varianti calendario impilate (LMXGV + S + D) — come
     nel PDF pag 388
   - Turno con S.COMP (disponibilità tutto il giorno)
   - Turno con FR / dormita (finisce in stazione fuori residenza,
     riparte giorno dopo da lì) — **screenshot esempio arriva dopo
     dall'utente, lasciare lo slot libero e annotare "placeholder FR"**
2. **Handoff markdown** `docs/HANDOFF-gantt-v3.md` con:
   - Descrizione del DS nuovo (token colore, altezza righe, spaziatura)
   - Struttura componenti (`<GanttRow>`, `<GanttBlock>`, `<GanttAxis>`,
     `<MetricsColumn>`, `<VariantLabel>`)
   - Esempio dati → rendering (un JSON di giornata + come viene
     renderizzata)
   - Edge case: overnight, refez, preriscaldo `●`, CV
3. **Esempio codice** (solo riferimento, non implementazione) per il
   rendering del blocco condotta vs vettura vs refez, così capisco la
   direzione tecnica.

---

## Appunti utente grezzi (non filtrati)

> "il gantt va ridisegnato sulla falsa riga dell'originale, ma non
> uguale. il PDF ha le barre nere e i label verticali, il nostro oggi
> ha card colorate con sfondi — ci stanno a metà, ma oggi siamo troppo
> colorati e non abbastanza denso. deve essere leggibile come un turno
> stampato ma interattivo come un'app moderna."

> "le due vetture inutili (bug appena risolto) si vedono ancora nel
> vecchio gantt come 4 blocchi — nel nuovo voglio vedere subito se una
> giornata ha viaggi in cerchio, quindi magari colora di rosso le
> vetture 'sospette' (quelle che invertono la direzione subito)."

Questi appunti sono indicativi — interpreta liberamente e proponi la
soluzione migliore.
