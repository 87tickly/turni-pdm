# Architettura Builder v4 — Centrato sulla Condotta

Proposta architetturale per risolvere il problema di fossilizzazione e
generare turni realistici tipo ALOR_C ALESSANDRIA. Riferimento:
pagine 386-387 del PDF "Turni PdC rete RFI dal 23 Febbraio 2026".

Questo documento deve essere **approvato dall'utente** prima di
implementare il codice.

---

## SEZIONE 1 — Come funziona ora (BUILDER v3, quello attuale)

### Schema logico

```
INPUT: deposito, n_giornate
                │
                ▼
┌───────────────────────────────┐
│ Per ogni giornata:            │
│                               │
│   ┌──────────────────────┐    │
│   │ DFS catene           │    │
│   │ che partono dal      │    │
│   │ DEPOSITO             │    │◄── Tutti i segmenti sono CONDOTTA
│   │                      │    │    (tranne posizionamento iniziale)
│   │ from_station =       │    │
│   │   deposito           │    │
│   └──────────┬───────────┘    │
│              │                │
│              ▼                │
│   ┌──────────────────────┐    │
│   │ Punteggia catene:    │    │
│   │ - condotta target    │    │
│   │ - rientro deposito   │    │
│   │ - diversita' linee   │    │
│   └──────────┬───────────┘    │
│              │                │
│              ▼                │
│   Scegli la migliore          │
└───────────────────────────────┘
                │
                ▼
OUTPUT: 5 giornate ognuna "AL → X → AL" tutto in condotta
```

### Problema

Il builder **assume che ogni segmento del turno sia un treno guidato
dal PdC**. Genera catene come:
```
ALESSANDRIA → [condotta 10578] → PAVIA → [condotta 10585] → ALESSANDRIA
```

Nel turno VERO ALOR_C G2 invece:
```
ALESSANDRIA → [VETTURA 11055] → VOGHERA
            → [CONDOTTA 2316]  → MILANO CENTRALE
            → [CONDOTTA U316]  → FIORENZA
            → [VETTURA 59AS]   → MILANO BOVISA
            → [VETTURA 24135]  → MILANO ROGOREDO
            → [REFEZIONE 30']
            → [CONDOTTA 10045] → ALESSANDRIA
            → [VETTURA CVa 10062] → ALESSANDRIA
```

**7 segmenti: 3 condotta + 4 vettura + 1 refezione**. Il mio DFS non sa
costruire questa cosa perche' assume "tutti condotta".

---

## SEZIONE 2 — Come deve funzionare (BUILDER v4, proposto)

### Principio architetturale

Ribaltare l'ordine di pensiero:
- **NON** parti dal deposito e concateni treni in condotta
- **SI** parti dal/dai **treno/i produttivo/i** (condotta target 2-3h)
  e costruisci intorno il posizionamento (vettura) + rientro

### Schema logico nuovo

```
INPUT: deposito, n_giornate
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│ Per ogni giornata:                                          │
│                                                             │
│ ┌─────────────────────────────────────────┐                 │
│ │ STEP A: SEED PRODUTTIVO                 │                 │
│ │                                         │                 │
│ │ Enumera tutte le combinazioni di        │                 │
│ │ 1-2 treni-condotta che totalizzano      │                 │
│ │ 2h-3h di condotta.                      │                 │
│ │                                         │                 │
│ │ Esempio per G2 ALOR_C:                  │                 │
│ │   [2316 + U316] = 55' + 22' = 77'       │                 │
│ │   + [10045] = 56' + 41' = 97'           │                 │
│ │   Totale condotta: 174' = 2h54 ✓        │                 │
│ │                                         │                 │
│ │ Questi sono i "seed" produttivi.        │                 │
│ └──────────────┬──────────────────────────┘                 │
│                │                                            │
│                ▼                                            │
│ ┌─────────────────────────────────────────┐                 │
│ │ STEP B: POSIZIONAMENTO INIZIALE         │                 │
│ │                                         │                 │
│ │ Dal DEPOSITO alla stazione di INIZIO    │                 │
│ │ del primo treno-condotta del seed.      │                 │
│ │                                         │                 │
│ │ Se seed inizia a VOGHERA:               │                 │
│ │   cerca treno ALESSANDRIA → VOGHERA     │                 │
│ │   marcato IS_DEADHEAD = True            │                 │
│ │   che arriva PRIMA dell'orario di       │                 │
│ │   inizio seed + 5' cambio treno         │                 │
│ │                                         │                 │
│ │ Puo' essere multi-hop:                  │                 │
│ │   AL → [vettura] → MILANO ROGOREDO      │                 │
│ │      → [vettura] → VOGHERA              │                 │
│ └──────────────┬──────────────────────────┘                 │
│                │                                            │
│                ▼                                            │
│ ┌─────────────────────────────────────────┐                 │
│ │ STEP C: GESTIONE GAP INTERNI / REFEZ    │                 │
│ │                                         │                 │
│ │ Tra i treni del seed ci sono gap        │                 │
│ │ (attese in stazione). Se un gap cade    │                 │
│ │ in finestra refezione (11:30-15:30 o    │                 │
│ │ 18:30-22:30) e dura ≥ 30': refezione    │                 │
│ │ li'.                                    │                 │
│ │                                         │                 │
│ │ Se gap tra treni e' > 30' ma non in     │                 │
│ │ finestra refezione: inserisci treno     │                 │
│ │ di connessione in vettura che porta il  │                 │
│ │ PdC alla stazione del treno successivo  │                 │
│ │ del seed (eventuale cambio linea).      │                 │
│ └──────────────┬──────────────────────────┘                 │
│                │                                            │
│                ▼                                            │
│ ┌─────────────────────────────────────────┐                 │
│ │ STEP D: RIENTRO                         │                 │
│ │                                         │                 │
│ │ Dalla stazione di FINE del seed al      │                 │
│ │ DEPOSITO. Puo' essere:                  │                 │
│ │                                         │                 │
│ │ a) L'ultimo treno del seed stesso e'    │                 │
│ │    gia' diretto al deposito (es.        │                 │
│ │    10045 MIRO → AL) → nessun rientro    │                 │
│ │    aggiuntivo                           │                 │
│ │ b) Treno di rientro in VETTURA (CVa)    │                 │
│ │ c) Treno di rientro in CONDOTTA se il   │                 │
│ │    PdC e' abilitato                     │                 │
│ │ d) Nessun rientro → FR legittimo se     │                 │
│ │    fine serale/notturna + stazione FR   │                 │
│ └──────────────┬──────────────────────────┘                 │
│                │                                            │
│                ▼                                            │
│ ┌─────────────────────────────────────────┐                 │
│ │ STEP E: VALIDA E SCEGLI                 │                 │
│ │                                         │                 │
│ │ Per ogni seed produttivo:               │                 │
│ │ 1. Prova tutti i posizionamenti validi  │                 │
│ │ 2. Prova tutti i rientri validi         │                 │
│ │ 3. Valida il turno completo (prest ≤    │                 │
│ │    8h30, riposo pre/post, refez, FR     │                 │
│ │    rules, contratto)                    │                 │
│ │ 4. Calcola score                        │                 │
│ │                                         │                 │
│ │ Scegli il migliore del giorno.          │                 │
│ └─────────────────────────────────────────┘                 │
└─────────────────────────────────────────────────────────────┘
                │
                ▼
OUTPUT: 5 giornate realistiche con pattern misto
        condotta/vettura/cambi volante/refezione
```

### Esempio generazione G2 ALOR_C col nuovo algoritmo

```
STEP A — Seed produttivo candidato:
  Treno A: 2316 MLCE (55', dep MLCE 07:58 arr FLOZ 08:06)
           U316 FLOZ (22', continuazione 08:06 → 08:16)
           Condotta: 77'
  Treno B: 10045 AL  (97', dep MLRO 13:56 arr AL 14:41)
           Condotta: 97'
  Totale seed: 174' = 2h54 ✓

STEP B — Posizionamento iniziale:
  Seed inizia a MLCE alle 07:58.
  Dal deposito ALESSANDRIA cerco treni che arrivano a MLCE ≤ 07:53.
  Opzione: AL 06:49 → (11055 via VOGHERA) → MLCE 07:49, in vettura.
  Tempo totale posizionamento: 1h

STEP C — Gap interno:
  Dopo U316 (arrivo FLOZ 08:16) → prima di 10045 (dep MLRO 13:56)
  Gap: 5h40 a FLOZ.
  Finestra refezione 11:30-15:30 cade dentro.
  Refezione 30' a MLRO (PdC prende vettura FLOZ→MLBA→MLRO intanto)
  Quindi: vettura 59AS (FLOZ 11:30 → MLBA 12:08), vettura 24135
  (MLBA 12:14 → MLRO 12:47), refezione a MLRO 12:47-13:17

STEP D — Rientro:
  L'ultimo treno del seed (10045) e' gia' diretto al deposito.
  Ma arriva alle 14:41. Se il turno termina li', va bene.
  Opzionale: CVa 10062 AL (cambio volante arrivo) se serve chiudere
  formalmente la giornata dopo altri minuti.

STEP E — Valida:
  Presentazione: 06:44 (AL)  [06:49 dep primo treno - 5' accessori]
  Fine: 15:01 (AL)           [14:41 + accessori + CVa]
  Prestazione: 8h17 ✓ (≤ 8h30)
  Condotta: 2h53 ✓ (≤ 5h30)
  Refezione: 30' a MLRO in finestra ✓
  Rientro al deposito: SI ✓
```

Questo **combacia esattamente** con il turno reale ALOR_C G2!

---

## SEZIONE 3 — Cosa cambio concretamente nel codice

### File toccati

| File | Cosa cambia |
|------|-------------|
| `src/turn_builder/auto_builder.py` | Riscrittura FASE 1 (era DFS catene, diventa "seed + wrap") |
| `src/turn_builder/seed_enumerator.py` | **NUOVO**: enumera combinazioni di 1-2 treni produttivi per giornata |
| `src/turn_builder/position_finder.py` | **NUOVO**: cerca percorsi in vettura deposito→stazione_X (multi-hop) |
| `src/turn_builder/day_assembler.py` | **NUOVO**: assembla seed + posizionamento + refez + rientro in un turno valido |
| `src/validator/rules.py` | Minori: aggiunge check su sequenza is_deadhead (gia' supportato) |
| Tests | Nuovi test unit per i 3 moduli nuovi |

### Cosa NON cambia

- Schema DB (resta com'e')
- Frontend (la forma dei dati ritornati e' compatibile)
- API endpoints `/build-auto`, `/abilitazioni/*`, `/constants`
- Cache `train_route_cache`
- Validator rules (prest, condotta, refez, riposo, FR)
- Gantt nei turni generati

### Stima tempo

- `seed_enumerator.py`: 1-2 ore
- `position_finder.py`: 1-2 ore (multi-hop ricerca percorsi in vettura)
- `day_assembler.py`: 2-3 ore (wire together + refezione + rientro)
- Integrazione + test: 1-2 ore
- **Totale: 5-9 ore** (una sessione lunga o 2 medie)

### Criteri di successo

Dopo la riscrittura, ALESSANDRIA 20 giornate deve produrre turni
**strutturalmente simili a ALOR_C**:
- 2-3h condotta media (non 4-5h)
- 6-8h prestazione media
- 3-5 segmenti per giornata (mix condotta+vettura)
- Almeno 3-4 linee diverse usate nel ciclo 5+2
- 0 giornate vuote
- Zero o minime NO_RIENTRO_BASE

---

## DECISIONI CHE MI SERVONO PRIMA DI PARTIRE

1. **Approva l'architettura a 3 moduli** (seed_enumerator, position_finder,
   day_assembler)? Oppure preferisci che resti tutto dentro `auto_builder.py`?

2. **Condotta target 2-3h** e' corretta per tutti i depositi o solo per
   ALESSANDRIA? (Se BRESCIA il PdC guida 4h, ridefinisco il target per deposito)

3. **Multi-hop vettura per posizionamento**: max quanti hop? Es. AL →
   [v] → MILANO → [v] → VOGHERA: 2 hop OK? 3 hop troppi?

4. **Quote di equita' tra depositi adiacenti** (tua osservazione su
   PAVIA): le inseriamo gia' in v4 o dopo come Fase 2?

5. **Algoritmo di ricerca seed**: enumerazione esaustiva o euristica
   greedy? Esaustiva e' piu' lenta ma trova l'ottimo globale.

Dammi le risposte a queste 5 e parto con l'implementazione.
