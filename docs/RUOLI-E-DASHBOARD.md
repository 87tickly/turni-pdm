# RUOLI E DASHBOARD — 5 utenti, 5 dashboard, 1 modello dati (draft v0.1)

> Specifica delle interfacce per ruolo. Per ogni dashboard: chi la usa,
> cosa fa, schermate, azioni, dati visualizzati, permessi.
>
> **Principio guida**: 5 dashboard separate (`frontend/src/routes/<ruolo>/`),
> un solo modello dati condiviso, permessi enforced **lato backend**
> via JWT claims.
>
> **Non specificato qui**: layout pixel-perfect, palette colori, font,
> spacing — quelli vivranno in `frontend/src/components/ui/` (shadcn) e
> in eventuali mockup futuri (Claude Design o Figma).

---

## 1. I 5 ruoli e relativi accessi

| Ruolo | Codice | Cosa fa | Crea/edita | Solo lettura |
|-------|--------|---------|------------|--------------|
| **PIANIFICATORE_GIRO** | `pianificatore-giro` | Costruisce/modifica giri materiale dal PdE | Giro materiale, varianti, blocchi, materiale vuoto generato, revisioni provvisorie giro | PdE corse commerciali, dotazione manutenzione |
| **PIANIFICATORE_PDC** | `pianificatore-pdc` | Costruisce/modifica turni PdC dai giri | Turno PdC, giornate, blocchi, revisioni provvisorie PdC | Giri materiale, depositi, PdE |
| **MANUTENZIONE** | `manutenzione` | Gestisce dotazione fisica per deposito | Inventario, manutenzioni programmate, spostamenti tra depositi, "fuori servizio" | Tutto il resto |
| **GESTIONE_PERSONALE** | `gestione-personale` | Anagrafica + assegnazioni + indisponibilità | Persone, assegnazione_giornata, indisponibilita_persona, sostituzioni | Turni PdC, giri, PdE |
| **PERSONALE_PDC** | `personale-pdc` | Vede il proprio turno, segnala, richiede ferie | Le proprie richieste (ferie, ROL, segnalazioni) | Solo i propri dati |
| **ADMIN** | `admin` | Gestione sistema, utenti, multi-tenant, audit | Tutto | Tutto |

I ruoli sono **claim del JWT**. Ogni endpoint API verifica che l'utente
abbia il ruolo necessario. Nessuna logica di permesso vive nel
frontend (solo UX hints — es. nascondi pulsante "Salva" se readonly).

Una persona può avere **più ruoli** contemporaneamente (es. un
admin sviluppatore ha tutti i ruoli). Il login porta alla dashboard
del ruolo principale; switch ruolo via menu utente.

---

## 2. Schermate condivise (tutti i ruoli)

Pagine non specifiche di un ruolo, accessibili da tutti i loggati:

| Schermata | Path | Descrizione |
|-----------|------|-------------|
| Login | `/login` | Email + password. JWT in cookie httpOnly o localStorage. |
| Profilo personale | `/profilo` | Cambia password, avatar, preferenze (timezone, lingua) |
| Settings (admin only) | `/settings` | Gestione utenti, ruoli, aziende, normative, audit |
| Health check | `/health` | Endpoint API + pagina diagnostica (admin) |
| 404 / 403 / 500 | `/errors/*` | Pagine errore standard |

Header globale: logo, nome utente, ruolo attivo (con switch se più
ruoli), notifiche, logout.

Sidebar a sinistra: voci specifiche del ruolo attivo.

---

## 3. Dashboard 1 — PIANIFICATORE GIRO MATERIALE

### Utente target

La persona (o team) che, partendo dall'offerta commerciale (PdE),
disegna come i convogli fisici coprono le corse. È il nodo che traduce
"cosa serve fare" in "come lo facciamo con il materiale che abbiamo".

### Schermate

#### 3.1 `/pianificatore-giro/dashboard` — Home

Mostra all'apertura:
- **Stato del PdE**: ultima versione importata, n. corse, validità da/a
- **Giri materiali esistenti**: contatore + lista con stato
  (`bozza`, `pubblicato`, `in_revisione`)
- **Revisioni provvisorie attive**: con causa (RFI/sciopero/ecc.) e
  finestra
- **Validazioni in sospeso**: giri con vincoli violati da risolvere
- Azioni rapide: "Importa nuovo PdE", "Nuovo giro materiale", "Nuova revisione"

```
┌─────────────────────────────────────────────────────────────────┐
│ Dashboard Pianificatore Giro Materiale                          │
├─────────────────────────────────────────────────────────────────┤
│  PdE attivo: 2025-12-14 → 2026-12-12       [Aggiorna]          │
│  10580 corse · 7 depositi · 1884 pezzi materiali               │
│                                                                 │
│  GIRI MATERIALI                              [+ Nuovo giro]    │
│  ├ 1100 (bozza)         29 corse  validità annuale            │
│  ├ 1101 (pubblicato)    87 corse  10 giornate                 │
│  ├ 1102 (in revisione)  42 corse  variante stagionale         │
│  └ ... (altri 51)                                              │
│                                                                 │
│  REVISIONI PROVVISORIE ATTIVE                                  │
│  ├ Como-Lecco interrotta 15-30/04   → modifica a giri 1130, 1135│
│  └ Sciopero 8 maggio 2026                                       │
└─────────────────────────────────────────────────────────────────┘
```

#### 3.2 `/pianificatore-giro/pde` — Vista PdE corse commerciali

Lista tabellare delle 10580 corse (paginata + filtrabile):
- Filtri: linea, direttrice, periodicità, validità data, fascia oraria,
  azienda
- Colonne: numero treno, rete, categoria, origine → destinazione,
  ora_partenza → ora_arrivo, km, periodicità breve
- Click su riga: drawer laterale con dettagli completi (composizione,
  9 combinazioni stagione × giorno-tipo, calendario circolazione)

Sola lettura per il pianificatore giro (la modifica del PdE arriva da
import — non si edita corsa per corsa).

#### 3.3 `/pianificatore-giro/giri` — Lista giri materiali

Tabella con tutti i giri del proprio azienda:
- Colonne: codice (1100), tipo materiale, n. giornate, deposito
  manutenzione, validità (con icona se discontinua), stato, ultima
  modifica
- Filtri: deposito, stato, validità in data X
- Bulk actions: pubblica selezionati, archivia

#### 3.4 `/pianificatore-giro/giri/:id` — Editor giro materiale

**Schermata centrale del ruolo.** Per un giro specifico:

- **Header**: codice, tipo materiale, validità (con visualizzazione
  finestre se discontinue), località manutenzione partenza/arrivo,
  km giornaliera/annua
- **Tabs per giornata** (1, 2, ..., N): ogni tab mostra le varianti
  calendario di quella giornata
- **Editor blocchi**: per ogni variante, sequenza di blocchi
  visualizzata come **Gantt orizzontale** con ore in alto:
  ```
  Variante: LMXGV (esclusi 2-3-4 marzo)
  06:00      08:00      10:00      12:00      14:00      16:00
  ├──────────┼──────────┼──────────┼──────────┼──────────┼─────
  │██10606██ ░░ ░░ ██10603██░░ ██10610██ ██10609██
  └ CREMONA → MIPG → CREMONA → MIPG → MILANO ROGOREDO
  ```
  - Blocco verde = corsa commerciale
  - Blocco grigio chiaro = sosta_disponibile
  - Blocco arancio = materiale_vuoto generato
  - Blocco viola = manovra
- **Drag & drop** per riordinare blocchi
- **Click blocco** → modifica orari, stazioni, tipo
- **Bottone "Genera automaticamente"**: invoca l'algoritmo di
  costruzione (vedi `LOGICA-COSTRUZIONE.md`) per popolare la variante
  da zero
- **Validazione live**: badge rosso/giallo/verde sopra il Gantt che
  segnala vincoli violati (sovrapposizioni, gap troppo lunghi, ecc.)

#### 3.5 `/pianificatore-giro/revisioni` — Revisioni provvisorie

Lista delle revisioni attive (interruzione_rfi, sciopero, ecc.):
- Filtri: causa, finestra temporale, giri impattati
- Click → drawer con dettaglio modifiche e cascading PdC

#### 3.6 `/pianificatore-giro/revisioni/nuova` — Nuova revisione

Form a step:
1. Causa (dropdown enum)
2. Comunicazione esterna (testo, es. "PIR-2026-345")
3. Finestra (data_da, data_a)
4. Selezione giri impattati (con lista corse coinvolte)
5. Per ogni giro: editor blocchi modificati (operazione: modifica /
   aggiungi / cancella)
6. Anteprima cascading PdC (calcolato automaticamente)
7. Conferma → notifica pianificatore PdC

### Permessi backend

```python
# Endpoint pseudocode
GET    /api/corse              role: PIANIFICATORE_GIRO ∪ ALTRI_LETTURA
GET    /api/giri               role: PIANIFICATORE_GIRO ∪ ALTRI_LETTURA
POST   /api/giri               role: PIANIFICATORE_GIRO
PUT    /api/giri/:id           role: PIANIFICATORE_GIRO
DELETE /api/giri/:id           role: ADMIN (mai pianificatore)
POST   /api/giri/:id/publish   role: PIANIFICATORE_GIRO
POST   /api/revisioni          role: PIANIFICATORE_GIRO
```

---

## 4. Dashboard 2 — PIANIFICATORE TURNO PdC

### Utente target

La persona (o team) che, partendo dai giri materiali, disegna i turni
del personale di macchina rispettando la normativa Trenord (ciclo 5+2,
prestazione max, condotta max, refezione, CV, vetture, FR, ecc.).

### Schermate

#### 4.1 `/pianificatore-pdc/dashboard` — Home

- **Giri materiali pubblicati**: contatore + filtro per deposito
- **Turni PdC esistenti**: divisi per impianto (deposito personale)
- **Validazioni normativa in sospeso**: turni con vincoli §11.8 / §4.1
  / §9.2 violati
- **Revisioni cascading attive**: rev provvisorie del giro che richiedono
  modifica turno PdC
- Azioni rapide: "Genera turni da giro X", "Nuovo turno manuale"

#### 4.2 `/pianificatore-pdc/giri` — Vista giri (sola lettura)

Stessa tabella della dashboard 1 ma senza pulsanti di modifica. Click
su un giro apre il **viewer** (non editor): si vede il Gantt ma non si
edita.

#### 4.3 `/pianificatore-pdc/turni` — Lista turni PdC

Tabella con i turni del proprio azienda:
- Colonne: codice (es. ALOR_C [65046]), impianto, profilo (Condotta),
  ciclo giorni, validità, stato
- Filtri: impianto, validità in data, stato

#### 4.4 `/pianificatore-pdc/turni/:id` — Editor turno PdC

**Schermata centrale del ruolo.** Struttura simile all'editor giro:

- **Header**: codice, impianto, profilo, ciclo, validità
- **Tabs per giornata** (G1...G7 con riposi)
- **Editor blocchi PdC** (Gantt giornaliero):
  ```
  G2 LMXGV — Prestazione 8h17 · Condotta 2h53 · ✓ Valida
  06:00      08:00      10:00      12:00      14:00      16:00
  ├──────────┼──────────┼──────────┼──────────┼──────────┼─────
  ▶V11055    ●ACCp 2316 ─→─ ●U316 ─→─ V59AS V24135 ▥REFEZ ●10045 CVa
  ```
  Tipi blocco:
  - **▶V** vettura (blu chiaro)
  - **●** condotta con ACCp/ACCa (verde)
  - **▥** refezione (arancio)
  - **CVa/CVp** cambio volante (viola)
  - **PK** parking (grigio)
- **Validazione live** in cima alla giornata:
  - Prestazione (vs cap 8h30 / 7h notte)
  - Condotta (vs cap 5h30)
  - Refezione (presente in finestra se prest > 6h)
  - CV in stazione ammessa (§9.2)
- **Bottone "Genera automaticamente"**: invoca l'algoritmo (`LOGICA-COSTRUZIONE.md`)
  per popolare la giornata partendo dai giri materiali coperti dal
  deposito
- **Pannello vincoli ciclo**: tab separato che valida riposo intra-ciclo
  (11h/14h/16h §11.5), riposo settimanale (62h §11.4), FR limiti
  (1/settimana, 3/28gg §10.6)

#### 4.5 `/pianificatore-pdc/revisioni-cascading` — Revisioni cascading

Quando il pianificatore-giro pubblica una revisione_provvisoria, qui
arriva la **proposta di cascading PdC** automaticamente calcolata.
Il pianificatore-pdc:
- Rivede le modifiche proposte
- Le accetta in blocco oppure le edita manualmente
- Pubblica → notifica gestione personale (cambio assegnazioni)

### Permessi backend

```python
GET    /api/giri                read-only
POST   /api/turni-pdc           role: PIANIFICATORE_PDC
PUT    /api/turni-pdc/:id       role: PIANIFICATORE_PDC
POST   /api/turni-pdc/:id/build-auto  role: PIANIFICATORE_PDC
```

---

## 5. Dashboard 3 — MANUTENZIONE

### Utente target

Chi gestisce la dotazione fisica del materiale: chi è dove, quando va
in officina, manutenzioni programmate, spostamenti tra depositi.

### Schermate

#### 5.1 `/manutenzione/dashboard` — Home

- **Inventario per deposito**: cards con i 7 depositi Trenord (e POOL_TILO),
  ognuna con quantità totale + tipi pezzo distinti
- **Manutenzioni programmate prossimi 30gg**: lista (placeholder se
  non ancora implementato)
- **Materiali fuori servizio**: contatore + lista con causa
- **Spostamenti pendenti**: trasferimenti tra depositi non ancora confermati

#### 5.2 `/manutenzione/depositi` — Lista località manutenzione

Tabella con i 7 depositi reali + eventuali aggiunti:
- Colonne: codice, nome canonico, n. tipi pezzo, pezzi totali, is_pool_esterno
- Click → drilldown deposito (vedi 5.3)

#### 5.3 `/manutenzione/depositi/:id` — Dettaglio deposito

- **Header**: codice (`IMPMAN_MILANO_FIORENZA`), nome canonico,
  azienda proprietaria, stazione collegata
- **Inventario**: tabella `localita_manutenzione_dotazione`:
  - Colonne: tipo pezzo (es. ALe710), famiglia rotabile (es. TSR),
    quantità, note
  - Bottone "+ aggiungi pezzo" / "modifica"
- **Storico spostamenti**: pezzi entrati/usciti
- **Manutenzioni programmate**: agenda

#### 5.4 `/manutenzione/spostamenti` — Trasferimenti tra depositi

Form per registrare uno spostamento di pezzi:
- Da deposito → A deposito
- Tipo pezzo + quantità
- Data trasferimento, motivo (manutenzione / riallocazione / pool)
- Stato: pianificato / in corso / completato

#### 5.5 `/manutenzione/manutenzioni-programmate` — Agenda

Calendario con manutenzioni pianificate:
- Vista mensile / lista
- Filtri: deposito, tipo pezzo, tipo manutenzione (revisione, controllo,
  pulizia approfondita)

### Permessi backend

```python
GET    /api/depositi-manutenzione         role: MANUTENZIONE ∪ READ
POST   /api/depositi-manutenzione/:id/dotazione  role: MANUTENZIONE
POST   /api/spostamenti-materiale         role: MANUTENZIONE
POST   /api/manutenzioni-programmate      role: MANUTENZIONE
```

---

## 6. Dashboard 4 — GESTIONE PERSONALE

### Utente target

Chi gestisce le persone reali: anagrafica, qualifiche, sede,
assegnazione delle giornate dei turni alle date calendario, ferie,
malattie, ROL, sostituzioni.

### Schermate

#### 6.1 `/gestione-personale/dashboard` — Home

- **Persone attive**: contatore + breakdown per impianto + per profilo
- **Indisponibilità in corso**: ferie/malattia/ROL attivi oggi
- **Assegnazioni mancanti prossimi 7gg**: giornate turno senza persona
  assegnata
- **Sostituzioni urgenti**: assegnazioni "annullate" da coprire

#### 6.2 `/gestione-personale/persone` — Anagrafica

Tabella persone:
- Colonne: codice dipendente, nome cognome, profilo, sede, qualifiche,
  attivo
- Filtri: impianto, profilo, attivo
- Bottone "+ nuova persona" / import CSV

#### 6.3 `/gestione-personale/persone/:id` — Scheda persona

- **Anagrafica**: dati personali, contatti, data assunzione
- **Qualifiche**: tag list (linee abilitate, materiali abilitati)
- **Calendario annuale**: vista mensile con giornate assegnate
  (colore per turno) + indisponibilità (colore per tipo)
- **Storico assegnazioni**: lista paginata
- **Ore lavorate per settimana**: grafico con vincoli normativa
  (target 35h30, min 33h, max 38h)

#### 6.4 `/gestione-personale/calendario` — Calendario assegnazioni

**Schermata centrale del ruolo.** Vista globale:

- Dimensioni: persone (righe) × date (colonne, settimana o mese)
- Cella: giornata turno assegnata (colore + codice turno) o indisponibilità
- Drag & drop per riassegnare
- Click cella → drawer con dettagli + opzioni (sostituisci, annulla)
- Filtri: impianto, profilo, mostra solo "scoperti", periodo

#### 6.5 `/gestione-personale/indisponibilita` — Ferie & assenze

Lista delle indisponibilità:
- Tab per tipo: ferie, malattia, ROL, sciopero, formazione, congedo
- Filtri: stato (richiesta/approvata/rifiutata), persona, periodo
- Workflow approvazione: richiesta → revisione → approvata → effettiva

#### 6.6 `/gestione-personale/sostituzioni` — Cambi turno

Quando una persona non può fare il proprio turno (malattia improvvisa,
emergenza), interfaccia per:
- Trovare persone disponibili con stesse qualifiche e nello stesso
  impianto
- Proporre la sostituzione → notifica al sostituto
- Conferma → l'assegnazione_giornata si aggiorna con
  `sostituisce_persona_id`

### Permessi backend

```python
GET    /api/persone                       role: GESTIONE_PERSONALE ∪ ADMIN
POST   /api/persone                       role: GESTIONE_PERSONALE
POST   /api/assegnazioni                  role: GESTIONE_PERSONALE
PUT    /api/assegnazioni/:id              role: GESTIONE_PERSONALE
POST   /api/indisponibilita               role: GESTIONE_PERSONALE ∪ PERSONALE_PDC (richiesta)
POST   /api/indisponibilita/:id/approve   role: GESTIONE_PERSONALE
```

---

## 7. Dashboard 5 — PERSONALE PDC (utente finale)

### Utente target

Il singolo macchinista. Vede il **proprio** turno, segnala problemi,
richiede ferie. Niente altro.

### Schermate

#### 7.1 `/personale/oggi` — La mia giornata

Schermata di apertura post-login:
- **Banner grande**: turno di oggi (codice, giornata, prestazione, condotta)
- **Gantt giornaliero** (sola lettura) con i blocchi della propria
  giornata
- **Notifiche**: revisioni provvisorie che impattano la giornata,
  comunicazioni operative dall'azienda
- Azioni rapide: "Segnala anomalia", "Richiedi sostituzione"

#### 7.2 `/personale/calendario` — Il mio calendario

Vista mensile:
- Celle: giornate turno (colore turno) + indisponibilità
- Click → drawer con dettagli giornata
- Tab "ore mensili": breakdown lavorate/condotta/refezione/FR

#### 7.3 `/personale/turno/:data` — Dettaglio turno data D

Per una specifica data:
- Sequenza blocchi (Gantt o lista)
- Stazioni di servizio, treni guidati, vetture, refezione
- Mapping con giro materiale (quale convoglio sto guidando)
- Pulsante "Esporta PDF" (per chi preferisce stampare)

#### 7.4 `/personale/ferie` — Le mie ferie & assenze

Lista delle proprie indisponibilità + form per richiesta:
- Form: tipo (ferie/ROL/permesso), periodo, motivo
- Workflow: bozza → invia → in revisione → approvata/rifiutata
- Storico: passate, in corso, future

#### 7.5 `/personale/segnalazioni` — Segnalazioni operative

Form per segnalare problemi durante il servizio:
- Tipo: ritardo, malfunzionamento materiale, evento ferroviario, altro
- Data/ora, treno, descrizione, foto allegate
- Storico segnalazioni con stato (aperta, presa in carico, chiusa)

### Permessi backend

```python
# IMPORTANTE: ogni endpoint filtra per persona_id = utente_loggato
GET    /api/personale/me                  role: PERSONALE_PDC
GET    /api/personale/me/turni            role: PERSONALE_PDC
GET    /api/personale/me/turni/:data      role: PERSONALE_PDC
POST   /api/indisponibilita-richieste     role: PERSONALE_PDC (request)
POST   /api/segnalazioni                  role: PERSONALE_PDC
```

---

## 8. Boundaries fra ruoli — chi vede cosa

Riepilogo permessi in tabella matrix:

| Entità | PIANIF_GIRO | PIANIF_PDC | MANUTENZIONE | GESTIONE | PERSONALE | ADMIN |
|--------|:-----------:|:----------:|:------------:|:--------:|:---------:|:-----:|
| `corsa_commerciale` | RW (import) | R | R | R | R (filtrato) | RW |
| `giro_materiale` | RW | R | R | R | R (filtrato) | RW |
| `revisione_provvisoria` (giro) | RW | R + propose cascading | R | R | R (notifica) | RW |
| `turno_pdc` | R | RW | R | R | R (filtrato) | RW |
| `revisione_provvisoria_pdc` | R | RW | R | R | R | RW |
| `localita_manutenzione` | R | R | RW | R | — | RW |
| `dotazione` | R | — | RW | — | — | RW |
| `persona` | — | — | — | RW | R (solo me) | RW |
| `assegnazione_giornata` | — | — | — | RW | R (solo mie) | RW |
| `indisponibilita_persona` | — | — | — | RW | RW (richieste) | RW |
| `segnalazione` | — | — | — | R | RW (proprie) | RW |

`R` = read · `W` = write · `RW` = read+write · `—` = nessun accesso

---

## 9. Notifiche cross-ruolo

Eventi che generano notifiche fra ruoli (via UI badge + opzionalmente
email):

| Evento | Da | A |
|--------|----|----|
| Pubblicato nuovo PdE | sistema | PIANIF_GIRO |
| Pubblicato nuovo giro materiale | PIANIF_GIRO | PIANIF_PDC |
| Pubblicata revisione provvisoria giro | PIANIF_GIRO | PIANIF_PDC, GESTIONE_PERSONALE |
| Pubblicato cascading PdC | PIANIF_PDC | GESTIONE_PERSONALE |
| Cambio assegnazione | GESTIONE_PERSONALE | PERSONALE_PDC interessato |
| Richiesta ferie | PERSONALE_PDC | GESTIONE_PERSONALE |
| Approvazione/rifiuto ferie | GESTIONE_PERSONALE | PERSONALE_PDC |
| Materiale fuori servizio | MANUTENZIONE | PIANIF_GIRO (se impatta giri attivi) |
| Segnalazione operativa | PERSONALE_PDC | GESTIONE_PERSONALE + ADMIN |

Implementazione MVP: tabella `notifica` con `(destinatario_persona_id,
tipo, payload_json, letto, creato_at)`. Polling client ogni 30s per
nuove notifiche. WebSocket/SSE differiti.

---

## 10. Schermata Settings (admin only)

Vista trasversale per admin:
- **Utenti & ruoli**: CRUD utenti, assegnazione ruoli
- **Aziende**: multi-tenant config, normativa_pdc JSON per azienda
- **Audit log**: tracciamento modifiche critiche (chi ha cancellato cosa)
- **Import/Export**: import CSV anagrafica, export bulk
- **Configurazione sistema**: feature flags, banner manutenzione

---

## 11. Cosa NON è in v1 delle dashboard

Anti-scope-creep esplicito:

- **Dark mode** → diff. v1.x
- **Multi-lingua** → diff. v2.0 (italiano-only per ora)
- **Mobile native** → no, web responsive sufficiente
- **PDF export ricco** (con grafica come oggi PDF Trenord) → diff.
  v1.x. MVP esporta CSV/JSON.
- **Real-time push** (WebSocket/SSE) → diff. v1.x. MVP polling.
- **Drag&drop avanzato sul calendario assegnazioni** → MVP solo
  click+modal. Drag&drop arriva quando l'esperienza base è solida.
- **Drill-down statistiche / KPI** → diff. v2.x (BI separato)
- **Conversazioni in-app fra ruoli** → diff. (oggi notifiche unilaterali)

---

## 12. Riferimenti

- `docs/VISIONE.md` §4 (i 5 ruoli)
- `docs/MODELLO-DATI.md` v0.5 (entità referenziate)
- `docs/STACK-TECNICO.md` §2 (struttura `frontend/src/routes/`)
- `docs/LOGICA-COSTRUZIONE.md` (algoritmo invocato dai bottoni
  "Genera automaticamente", FASE C doc 4)
- `docs/PIANO-MVP.md` (quale dashboard si costruisce per prima, FASE
  C doc 7)

---

**Fine draft v0.1**. Da revisionare con l'utente. In particolare:
le schermate sono 30+, vanno priorizzate in `PIANO-MVP.md`.
