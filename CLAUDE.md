# COLAZIONE — Programma di pianificazione ferroviaria nativa (greenfield)

> **Stato del progetto**: greenfield, in fase di scrittura specifiche.
> Reset eseguito il **2026-04-25**. Il programma vecchio (parser PDF
> Gantt + backend FastAPI + frontend React) è stato eliminato — vedi
> `TN-UPDATE.md` per il diario, `docs/_archivio/` per la memoria storica.

---

## Regole operative OBBLIGATORIE

### 1. Leggi sempre `TN-UPDATE.md` a inizio sessione

Il diario operativo del nuovo progetto. Contiene la cronologia di
ogni modifica fatta, in ordine cronologico inverso (entry più recente
in cima). **Leggi le prime 2-3 entry prima di fare qualsiasi cosa.**

### 2. Aggiorna `TN-UPDATE.md` dopo ogni task completato

Dopo ogni feature, fix, refactoring, qualsiasi modifica:
- Aggiungi una entry in cima a `TN-UPDATE.md` con data, contesto,
  modifiche, stato, prossimo step
- `git add` dei file modificati
- `git commit` con messaggio descrittivo
- `git push`

L'entry segue la struttura: `## YYYY-MM-DD — titolo breve` + sezioni
`### Contesto`, `### Modifiche`, `### Stato`, `### Prossimo step`.

### 3. Mai lavorare senza contesto

Se non hai letto `TN-UPDATE.md`, leggilo prima di fare qualsiasi cosa.

### 4. Leggi `docs/METODO-DI-LAVORO.md` a inizio sessione

Subito dopo `TN-UPDATE.md`. È il framework di comportamento (7 regole:
diagnosi prima di azione, numeri non ipotesi, un passo alla volta,
ammettere l'errore, verifica prima del commit, preservare non
distruggere, costanza nel tempo). **NON è opzionale.** Nei momenti di
fretta o frustrazione è proprio quando serve fermarsi e ri-consultarlo.

### 5. Dominio: leggi i documenti di riferimento quando serve

| Documento | Quando leggerlo |
|-----------|-----------------|
| `docs/NORMATIVA-PDC.md` (1292 righe) | Quando lavori su builder turni PdC, validazione regole operative (accessori, refezione, CV, vetture, FR, ciclo settimanale, prestazione max). **Fonte verità Trenord** — se il codice fa diversamente, è il codice a essere sbagliato. |
| `docs/MODELLO-DATI.md` v0.5 | Quando tocchi entità del modello (corsa_commerciale, giro_materiale, turno_pdc, persona, revisioni, località manutenzione). Modello concettuale a piramide. |
| `docs/ALGORITMO-BUILDER.md` | Quando implementi l'algoritmo di costruzione turni PdC dal giro materiale. **Riferimento storico**: scritto per il vecchio progetto, va riadattato in chiave nativa, ma la logica algoritmica resta valida. |
| `docs/ARCHITETTURA-BUILDER-V4.md` | Idea "centrata sulla condotta" (seed produttivo + posizionamento + rientro). **Riferimento storico** — logica preziosa, riscrivere in chiave nativa quando si arriva al builder. |
| `docs/schema-pdc.md` | Schema JSON canonico turno PdC con esempi reali. Riferimento storico. |

### 6. Manifesto greenfield (vedi `docs/MODELLO-DATI.md` §⚠️)

**Non stiamo replicando il sistema Trenord.** Il programma è di
ARTURO × Trenord, ispirato dalla loro realtà operativa ma indipendente.
Multi-tenant: domani SAD/TILO/Trenitalia possono usare la stessa app
con normativa configurabile per azienda.

**Il vecchio progetto non torna.** Niente parser PDF Gantt come fonte
primaria, niente `train_segment` come entità centrale. La logica di
costruzione è:

```
PROPOSTA COMMERCIALE (PdE)        ← sorgente unica autorevole
        ↓
TURNO MATERIALE (giro)            ← lo COSTRUIAMO noi (algoritmo)
        ↓
TURNO PdC                         ← lo COSTRUIAMO noi (algoritmo)
        ↓
ASSEGNAZIONE PERSONE              ← anagrafica + indisponibilità
```

### 7. Sviluppa per ruoli — 5 dashboard separate

Il programma serve **persone con ruoli diversi**:
1. Pianificatore Giro Materiale
2. Pianificatore Turno PdC
3. Manutenzione (gestione dotazione fisica)
4. Gestione Personale (anagrafica + assegnazioni)
5. Personale finale (PdC che vede il proprio turno)

Ogni ruolo ha una propria dashboard con schermate, azioni, permessi.
Non costruire un'interfaccia unica.

---

## Stato attuale del progetto

| Fase | Stato | Output |
|------|-------|--------|
| **A — Greenfield reset** | ✅ completa (2026-04-25) | Repo pulito, solo dominio + 1 seed |
| **B — Nuovo CLAUDE.md** | 🔄 in corso | Questo file |
| **C — Documentazione architetturale** | ⏸️ in coda | 7 documenti da scrivere uno per volta con review utente |
| **D — Costruzione codice** | ⏸️ in coda | Solo dopo che C è chiusa e validata |

### Documenti FASE C da scrivere (ordine)

1. `docs/VISIONE.md` — cos'è il programma, per chi, cosa risolve
2. `docs/STACK-TECNICO.md` — backend/frontend/DB/hosting/auth (richiede decisioni utente)
3. `docs/RUOLI-E-DASHBOARD.md` — 5 dashboard, schermate, permessi
4. `docs/LOGICA-COSTRUZIONE.md` — algoritmo nativo PdE → giro → PdC
5. `docs/SCHEMA-DATI-NATIVO.md` — schema SQL concreto (eseguibile)
6. `docs/IMPORT-PDE.md` — come si legge il PdE Numbers
7. `docs/PIANO-MVP.md` — primo MVP girabile, ordine costruzione

---

## Stack tecnologico

**Da decidere in `docs/STACK-TECNICO.md`** (FASE C documento 2). Le scelte
impattano CLAUDE.md, che andrà aggiornato dopo.

Il progetto vecchio usava: Python 3.12 + FastAPI + React/TS + shadcn +
Tauri (pianificato) + SQLite/PostgreSQL + Railway. Possiamo riutilizzare
parte di queste scelte se rette, ma niente è obbligatorio.

---

## Variabili d'ambiente

Da definire in `docs/STACK-TECNICO.md`. Per ora nessuna.

---

## Glossario dominio

Riassunto rapido. Per il dettaglio normativo vedi `docs/NORMATIVA-PDC.md`.

| Termine IT | Significato |
|-----------|-------------|
| **PdE** (Programma di Esercizio) | Offerta commerciale annuale: elenco di tutte le corse treno con orari, periodicità, composizione. Fonte unica da cui tutto deriva. |
| **Giro materiale** (turno materiale) | Ciclo di rotazione di un convoglio fisico. N giornate × M varianti calendario × sequenza di corse coperte. |
| **Turno PdC** | Ciclo di lavoro di un macchinista. N giornate × M varianti × sequenza di blocchi (condotta, vettura, accessori, refezione, CV). |
| **Località di manutenzione** | Sede del materiale fisico (IMPMAN FIORENZA, NOVATE, CAMNAGO, LECCO, CREMONA, ISEO + pool TILO Svizzera). Distinta da deposito PdC. |
| **Deposito PdC** | Sede del personale di macchina (25 voci Trenord: ALESSANDRIA, ARONA, BERGAMO, BRESCIA, ecc.). |
| **Prestazione** | Durata totale turno giornaliero. Max 8h30 (510 min) standard, 7h (420 min) presa servizio 01:00-04:59. |
| **Condotta** | Tempo effettivo di guida. Max 5h30 (330 min). |
| **Refezione (REFEZ)** | Pausa pasto 30 min. Obbligatoria se prestazione > 6h. Finestre 11:30-15:30 o 18:30-22:30. |
| **CV** (CVp/CVa) | Cambio Volante: il PdC consegna/prende il mezzo in stazione ammessa, gap < 65'. |
| **PK** (Parking) | Materiale parcheggiato in stazione durante una pausa. Alternativa a CV. |
| **ACCp/ACCa** | Accessori in partenza/arrivo del treno (40' standard, 80' con preriscaldo dic-feb). |
| **Vettura** | PdC viaggia come passeggero (deadhead). Niente accessori, solo 15' pre/post servizio ai bordi del turno. |
| **Materiale vuoto (U\*\*\*\*)** | Treno senza passeggeri per posizionamento (es. da Fiorenza a Mi.Centrale). |
| **Treno commerciale "i"** | Treno con suffisso "i" (es. 28335i): traccia RFI ma materiale ancora vuoto, posizionamento. |
| **FR (Fuori Residenza)** | Pernottamento fuori sede. Max 1/settimana, max 3/28gg. |
| **S.COMP** | Disponibilità a comparto. Min 6h. |
| **Ciclo 5+2** | Blocco 5 giorni lavoro + 2 riposo. Riposo settimanale ≥ 62h con 2 giorni solari. |

---

## Convenzioni

- **Naming dominio**: termini italiani (prestazione, condotta, deposito, turno, giro materiale)
- **Naming codice**: inglese per struttura (routes, services, models), italiano per concetti di dominio (pdc, giro, refezione)
- **Orari**: minuti dall'inizio giornata (es. 510 = 8h30)
- **API**: RESTful, prefisso `/api/`, risposte JSON (da formalizzare in STACK-TECNICO.md)

---

## Riferimenti

- `TN-UPDATE.md` — diario operativo (cronologia modifiche)
- `docs/METODO-DI-LAVORO.md` — framework comportamentale
- `docs/NORMATIVA-PDC.md` — fonte verità dominio
- `docs/MODELLO-DATI.md` v0.5 — modello concettuale
- `data/depositi_manutenzione_trenord_seed.json` — anagrafica reale 7 depositi + 1884 pezzi
- `docs/_archivio/LIVE-COLAZIONE-storico.md` — diario progetto vecchio (memoria storica)
