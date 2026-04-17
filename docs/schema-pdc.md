# Schema PdC — modello dati v2

Versione: **MDL-PdC v1.0** · Fase 1 del rifacimento (mockup gantt-ideal-v5 → produzione).

Questo documento è la fonte unica di verità per:

- la forma del JSON che il parser v2 produce per ogni PDF PdC
- le tabelle del DB (SQLite locale / PostgreSQL Railway)
- il payload che il frontend `PdcGantt.tsx` consuma

Parser e frontend usano **lo stesso JSON**, nessuna trasformazione.

---

## 1. Versioning dei turni (sostituzione)

I turni Trenord cambiano a ogni pubblicazione (tipicamente ogni 1-3 mesi).
Ogni PDF contiene un set completo di tutti i turni validi per quel periodo.

**Regola operativa**: al caricamento di un nuovo PDF, i turni precedenti
diventano **non più attivi** — la UI di default mostra solo i turni del
pacchetto più recente. Lo storico resta nel DB come audit/sicurezza
(non viene cancellato).

### Tabella `pdc_import`
Un record per ogni caricamento PDF.

| Colonna | Tipo | Note |
|---|---|---|
| `id` | PK | |
| `filename` | TEXT | `"Turni PdC rete RFI dal 23 Febbraio 2026.pdf"` |
| `data_stampa` | DATE | dalla testata PDF (es. `2026-02-17`) |
| `data_pubblicazione` | DATE | dalla banda dei turni |
| `valido_dal` | DATE | min dei `valid_from` dei turni estratti |
| `valido_al` | DATE | max dei `valid_to` |
| `n_turni` | INT | numero turni estratti |
| `n_pagine_pdf` | INT | |
| `imported_at` | TIMESTAMP | momento del caricamento |
| `imported_by` | INT | FK users |

### Campi aggiunti a `pdc_turn`

| Colonna | Tipo | Note |
|---|---|---|
| `import_id` | INT FK → pdc_import | quale import ha prodotto questo turno |
| `superseded_by_import_id` | INT FK → pdc_import | NULL = turno **attivo**. Se valorizzato, è stato archiviato dall'import indicato |
| `data_pubblicazione` | TEXT | es. `"17/02/2026 14:44"` |

### Query "turni attivi"
```sql
SELECT * FROM pdc_turn WHERE superseded_by_import_id IS NULL
```

### Flusso sostituzione (nuovo PDF)
1. parser crea nuovo record `pdc_import` (stato = pending)
2. parser produce N turni con `import_id = nuovo.id` e `superseded_by_import_id = NULL`
3. UI mostra diff: nuovi vs esistenti per `(codice, impianto)`
4. su conferma:
   ```sql
   UPDATE pdc_turn
   SET superseded_by_import_id = :nuovo_import_id
   WHERE superseded_by_import_id IS NULL
     AND import_id <> :nuovo_import_id
     AND (codice, impianto) IN (
       SELECT codice, impianto FROM pdc_turn WHERE import_id = :nuovo_import_id
     )
   ```
   (archivia solo i turni che hanno una versione nuova; quelli non più presenti nel nuovo PDF rimangono attivi — richiedono una scelta esplicita utente)

---

## 2. Schema giornata (chiave `numero + periodicità`)

Una giornata del ciclo può avere **più varianti** (es. `2 LMXGVS` e `2 D` nel turno AROR_C). Già supportato dalla chiave composta di `pdc_turn_day`.

### Campi aggiunti a `pdc_turn_day`

| Colonna | Tipo | Note |
|---|---|---|
| `stazione_inizio` | TEXT | capolinea di inizio giornata (es. `"ARON"`) |
| `stazione_fine` | TEXT | capolinea di fine giornata |

Questi alimentano i label orizzontali ai bordi del Gantt (mockup v5).

---

## 3. Schema blocco (arricchito)

Tipi di `block_type` supportati:

```
train            treno commerciale (condotto dal macchinista)
coach_transfer   vettura / deadhead (macchinista viaggia senza condurre)
cv_partenza      Cambio Volante in Partenza (puntuale)
cv_arrivo        Cambio Volante in Arrivo (puntuale)
meal             refezione (30 min)
scomp            S.COMP — a disposizione del comparto
available        giornata "Disponibile" (riposo/disponibilità a casa)
accessori_inizio accessori di presa servizio (inizio giornata)   ← NUOVO
accessori_fine   accessori di consegna servizio (fine giornata)  ← NUOVO
```

### Campi aggiunti a `pdc_block`

| Colonna | Tipo | Note |
|---|---|---|
| `minuti_accessori` | TEXT | riga ausiliaria del PDF (`"5"`, `"27"`, `"10"` ecc.); stringa perché può essere interpretato diversamente per tipo |
| `fonte_orario` | TEXT | `parsed` (letto dal PDF), `interpolated` (ricostruito), `user` (editato manualmente) |
| `cv_parent_block_id` | INT FK → pdc_block | NULL tranne per `cv_partenza`/`cv_arrivo`: punta al blocco `train` padrone (quello a cui il cambio volante si riferisce). Permette drag&drop dove CVp/CVa seguono il treno |
| `accessori_note` | TEXT | testo libero, es. `"Tr.10205 tempi accessori maggiorati per preriscaldo"` |

Il flag `accessori_maggiorati` (0/1) **esiste già**.

---

## 4. JSON canonico

Esempio (AROR_C giorno 1 dal PDF reale, estratto atteso dal parser v2):

```json
{
  "documento": {
    "tipo": "turno_pdc",
    "filename": "Turni PdC rete RFI dal 23 Febbraio 2026.pdf",
    "rev": "M 704 - Rev.4",
    "data_stampa": "2026-02-17",
    "n_pagine": 446
  },
  "import": {
    "id": null,
    "imported_at": null,
    "valido_dal": "2026-02-23",
    "valido_al": "2026-12-12",
    "n_turni": 28
  },
  "turni": [
    {
      "codice": "AROR_C",
      "planning": "65053",
      "impianto": "ARONA",
      "profilo": "Condotta",
      "valido_dal": "2026-02-23",
      "valido_al": "2026-12-12",
      "data_pubblicazione": "17/02/2026 14:44",
      "giornate": [
        {
          "numero": 1,
          "periodicita": "LMXGVSD",
          "stazione_inizio": "ARON",
          "stazione_fine": "ARON",
          "inizio_prestazione": "18:20",
          "fine_prestazione": "00:25",
          "stats": {
            "lav_min": 365,
            "cct_min": 202,
            "km": 184,
            "notturno": true,
            "rip_min": 945
          },
          "blocchi": [
            {
              "seq": 1,
              "tipo": "coach_transfer",
              "numero_vettura": "2434",
              "stazione_da": "ARON",
              "stazione_a": "DOMO",
              "ora_inizio": "18:25",
              "ora_fine": "19:04",
              "minuti_accessori": "5",
              "fonte_orario": "parsed",
              "accessori_maggiorati": false
            },
            {
              "seq": 2,
              "tipo": "meal",
              "stazione_da": "DOMO",
              "stazione_a": "DOMO",
              "ora_inizio": "19:40",
              "ora_fine": "20:07",
              "minuti_accessori": "27",
              "fonte_orario": "parsed"
            },
            {
              "seq": 3,
              "tipo": "cv_partenza",
              "treno": "2434",
              "stazione_da": "DOMO",
              "ora_inizio": "20:20",
              "minuti_accessori": "5",
              "cv_parent_seq": 4,
              "fonte_orario": "parsed"
            },
            {
              "seq": 4,
              "tipo": "train",
              "treno": "10243",
              "stazione_da": "DOMO",
              "stazione_a": "Mlpg",
              "ora_inizio": "20:20",
              "ora_fine": "22:24",
              "fonte_orario": "parsed",
              "accessori_maggiorati": false
            },
            {
              "seq": 5,
              "tipo": "train",
              "treno": "10246",
              "stazione_da": "Mlpg",
              "stazione_a": "ARON",
              "ora_inizio": "22:40",
              "ora_fine": "23:45",
              "minuti_accessori": "10",
              "fonte_orario": "parsed"
            }
          ]
        },
        {
          "numero": 2,
          "periodicita": "LMXGVS",
          "stazione_inizio": "ARON",
          "stazione_fine": "ARON",
          "inizio_prestazione": "16:10",
          "fine_prestazione": "23:25",
          "stats": { "lav_min": 435, "cct_min": 195, "km": 193, "notturno": false, "rip_min": 811 },
          "blocchi": [ /* ... 6 blocchi ... */ ]
        },
        {
          "numero": 2,
          "periodicita": "D",
          "stazione_inizio": "ARON",
          "stazione_fine": "ARON",
          "inizio_prestazione": "16:10",
          "fine_prestazione": "23:25",
          "stats": { "lav_min": 435, "cct_min": 0, "km": 0, "notturno": false, "rip_min": 815 },
          "blocchi": [
            {
              "seq": 1,
              "tipo": "scomp",
              "stazione_da": "ARON",
              "stazione_a": "ARON",
              "ora_inizio": "16:10",
              "ora_fine": "23:25",
              "fonte_orario": "parsed"
            }
          ]
        }
      ],
      "note_treni": [
        {
          "treno": "10243",
          "periodicita_testo": "Circola tutti i giorni.",
          "non_circola": ["2025-12-25"],
          "circola_extra": []
        }
      ]
    }
  ]
}
```

---

## 5. Flusso frontend

Il componente `PdcGantt.tsx` v2 riceve in props:

```ts
interface PdcGanttProps {
  blocchi: Block[];           // blocchi della giornata corrente
  giornata: GiornataMeta;     // numero, periodicita, stazione_inizio/fine, prestazione
  stats: Stats;
  onBlocchiChange: (b: Block[]) => void;   // per edit/drag
  readOnly?: boolean;
  importIsActive: boolean;    // se il turno appartiene all'import attivo
}
```

Rendering segue il mockup v5:
- chip-card blu per `train`
- linea tratteggiata grigia + chip orizzontale stagger A per `coach_transfer`
- rettangolo ambra + chip orizzontale stagger B per `meal`
- tick viola + chip orizzontale stagger C per `cv_partenza`/`cv_arrivo`
- rettangolo ciano tratteggiato con label dentro per `scomp`
- badge "Disponibile" centrato per `available`

---

## 6. Migrazioni DB

Le migrazioni sono idempotenti via `_run_migration()` in `src/database/db.py`.

Pseudocodice:

```python
# 1. Crea tabella pdc_import (IF NOT EXISTS)
# 2. ALTER pdc_turn ADD COLUMN import_id
# 3. ALTER pdc_turn ADD COLUMN superseded_by_import_id
# 4. ALTER pdc_turn ADD COLUMN data_pubblicazione
# 5. ALTER pdc_turn_day ADD COLUMN stazione_inizio
# 6. ALTER pdc_turn_day ADD COLUMN stazione_fine
# 7. ALTER pdc_block ADD COLUMN minuti_accessori
# 8. ALTER pdc_block ADD COLUMN fonte_orario
# 9. ALTER pdc_block ADD COLUMN cv_parent_block_id
# 10. ALTER pdc_block ADD COLUMN accessori_note
```

Nessuna modifica alle colonne esistenti → zero impatto su dati già caricati.
Dati pre-versioning avranno `import_id = NULL` e `superseded_by_import_id = NULL`
→ restano "attivi" (il primo import nuovo li farà diventare superseded).
