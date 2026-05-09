# SEVERO — Critica codice MR-D0..D3 (cuore architetturale)

**Data**: 2026-05-09
**Trigger invocazione**: obbligatoria post cuore architetturale
(esplicito nel Plan-D approvato 7/10, regola memoria
`feedback_severo_sempre_su_piani.md`).
**Motore di SEVERO**: AMILCARE V4 Flash via `mcp__amilcare__code`
(brief ~3.5KB, output ~600 parole).

---

## TL;DR

5 commit committati, 5 moduli dominio (~2000 righe), 112 test
passing, mypy strict + ruff clean. Architettura coerente,
implementazione fedele al piano approvato 7/10. **Voto: 8.5/10**.
Procedere con MR-D4..D8 senza fix obbligatori.

---

## Voto qualità codice: **8.5/10**

Architettura coerente e ben stratificata. Ogni modulo ha
responsabilità chiara e interfacce pulite. Pattern a strati
(definizione → calendario → analisi → allocazione → turni)
rispetta il piano *linea-centrica* approvato. Mypy strict e ruff
clean sono segno di disciplina. I 112 test unitari coprono i casi
nominali + i bug storici (es. `_delta_minuti` in MR-D3, `festivita_italiane`
tuple-vs-list in MR-D0.5). Mancano test di integrazione tra moduli
ma scope MR-D7 e2e.

---

## Critiche per modulo

### MR-D0 `definizione_linea.py` (29 test, commit `285a73e`)

Baseline solida. Riduttivo: 1 segmento per linea, delega split
multi-tronco a MR-D1. Manca validazione input su `VincoliSosta`
(valori negativi non segnalati). **Mitigato**: scope dichiarato
nel docstring "MR-D1 raffinerà".

### MR-D0.5 `gestione_calendario_linea.py` (26 test, commit `92bf2ed`)

Il bug storico su `festivita_italiane()` (tuple vs lista) indica
coverage debole sulle strutture dati base esistenti. `classifica_data()`
è efficiente ma non testata per date fuori 2024-2026 (estrapolazione
generale OK perché algoritmica, ma test 2030/2050 mancano).

### MR-D1 `analizza_linee.py` (17 test, commit `96838c7`)

Logica *top-2 stazioni per frequenza con tie-break alfabetico* è
arbitraria. Potrebbe generare segmenti inconsistenti con 3+ stazioni
stessa frequenza (test attuale copre casi puliti, non patologici).
17 test sembrano pochi per la complessità dello splitting multi-tronco.

### MR-D2 `assegna_convogli_linea.py` (22 test, commit `7ed1e05`)

Greedy *most-constrained-first* corretto. La formula
`ceil(corse_die × tempo_rt / (2 × ore_servizio))` ignora finestre
di manutenzione e picchi orari — potrebbe sottostimare convogli.
Vincoli HARD ben implementati. **Verificato post-critica**: caso
`corse_die == 0` GIÀ gestito (`_calcola_n_convogli_minimo` ritorna 0
se `n_corse_per_die_media <= 0`, test esistente
`test_n_convogli_zero_se_n_corse_zero`).

### MR-D3 `costruisci_turno_linea.py` (18 test, commit `7295530`)

Cuore architetturale funziona. Gestione cross-day affidata a warning
(non blocking) — in produzione potrebbe causare turni notturni non
conformi al CCNL. Il bug `_delta_minuti` (catturato dai test, fix
`base + (1440 if ... else base)` → `if-else`) dimostra che il codice
era fragile; servono test per casi >24h (futuro).

---

## Allineamento al piano approvato 7/10

✅ I 5 moduli implementano fedelmente quanto dichiarato. Le due
raccomandazioni obbligatorie di SEVERO sul piano sono **concretamente
realizzate**:

1. **Vincolo sosta esplicito** (raccomandazione #1, doveva essere
   in MR-D0.5): realizzata già in MR-D0 via dataclass `VincoliSosta`
   embedded in ogni `SegmentoLinea`. Più granulare di quanto chiesto.

2. **No ciclo aperto fuori area Milano come HARD** (raccomandazione
   #2, doveva essere in MR-D2): realizzata via
   `_e_compatibile()` che richiede `sosta_notturna_diretta OR
   area_metropolitana_condivisa`. Constraint propagation fallisce
   con `errore="no_sede_compatibile"` se violato. Test dedicato
   `test_severo_constraint_2_no_ciclo_aperto_fuori_area`.

Nessuna deviazione rilevata.

---

## Rischi per MR-D4..D8

1. **API instabili**: interfacce fra moduli (es. attributi
   `SegmentoLinea`, `AssegnazioneSegmento`) non ancora documentate
   formalmente come Protocol. D4 (aggregazione linea-centrica) dovrà
   integrarle — qualunque cambio scattola modifiche.

2. **Copertura test insufficiente per integrazione**: 112 test tutti
   unitari. MR-D7 e2e rischia di scoprire bug di comunicazione fra
   moduli (es. ordinamento segmenti, gestione eccezioni cross-modulo).

3. **Formule di dimensionamento semplificate**: la formula round-trip
   in D2 non tiene conto di tempi di sosta effettivi del PdE. MR-D4
   potrebbe dover ricalcolare `n_convogli` con dati reali, generando
   disallineamento.

4. **Builder switch (MR-D5)**: il builder esistente (strangler)
   espone interfacce legacy; i nuovi moduli usano classi diverse —
   serve uno strato di adattamento non ancora previsto nel piano.

---

## Approvazione

**Voto 8.5/10 ≥ 7 → procedere con MR-D4**.

**Nessun fix obbligatorio**. Raccomandazioni non bloccanti:

1. Aggiungere test di integrazione minimi fra D2 e D3 (2-3 scenari)
   → **scope MR-D7 e2e**.
2. Documentare formalmente le interfacce pubbliche (Protocol o
   typing docstring) → **scope MR-D8 cleanup**.
3. Verificare formula `n_convogli` in D2 con `corse_die == 0`
   → **GIÀ verificato post-critica**, gestito correttamente.

---

## Riferimenti

- TN-UPDATE entry 261 (in scrittura) — narrazione codice committato
- Commit serie: `285a73e` (D0), `92bf2ed` (D0.5), `96838c7` (D1),
  `7ed1e05` (D2), `7295530` (D3)
- `docs/critiche/PLAN-D-riscrittura-linea-centrica.md` — critica
  precedente sul piano (voto 7/10 con 2 raccomandazioni)
- AMILCARE V4 Flash via `mcp__amilcare__code` — motore SEVERO
