# SEVERO — critica MR-A7: validazione end-to-end builder esplorativo

> **Data**: 2026-05-09
> **MR target**: Sprint 8.1 MR-A7 (validazione end-to-end builder esplorativo su programmi reali Trenord 16 e 17)
> **Motore SEVERO**: AMILCARE V4 Pro (DeepSeek diretto) via fallback NINO-orchestrato (subagent custom non bootato in sessione corrente)
> **FAUSTO consultato**: sì, per validazione semantica fix F4 fusione giri-corti (bug semantico individuato, F4 scartato)
> **Voto**: **3/10**

---

## TL;DR

Validazione esplorativa rumorosa, condotta su un pool corse cresciuto senza verifica e con copertura parziale. L'enormità di warning e giri non chiusi certifica che il dataset è sporco, rendendo inaffidabile ogni conclusione. Voto: **3/10**.

---

## Contesto MR-A7

NINO ha eseguito:

1. Dump DB Railway production → locale (Postgres 17 docker, FK orfana ignorata)
2. **Snapshot rigido prog 17**: 23 giri, 5 1g (21.7%), 12 sotto n_min=4 (52.2%), corse 765/765 (100%), residue=0
3. **Snapshot esplorativo prog 17**: 35 giri (+12), 5 1g (14.3%), 12 sotto-min (34.3%), corse 1651/1651, residue=0, 264 warning, 11 chiusi/24 non_chiusi/0 km_cap
4. **Diagnosi 12 sotto-min**: 6 'naturale', 3 'sotto_min', 2 'ciclo_aperto_irrisolto', 1 'non_chiuso'
5. **Test A4-tris** peso_n_giornate=−0.5→+1.0: ZERO effetto (distribuzione identica). Rollback senza commit.
6. **Decisione architetturale** (AMILCARE): "12 sotto-min è fatto del PdE non bug. Accetta naturali + UI badge".
7. **Fix F4 scartato** (FAUSTO): bug semantico (date disgiunte ≠ giornate consecutive).

---

## Finding

### HIGH-1 — Il pool esplorativo è inquinato e mai validato

Il salto da 765 a 1651 corse (+886, +116%) è avvenuto **senza alcun controllo di conformità al Tier 0**. I 264 warning "Catena scartata fuori whitelist sede" (che credevi risolti in MR-A3-bis entry 249) mostrano che il filtro a monte è ancora bucato.

Invece di fermarti hai girato il builder su immondizia, producendo **24/35 giri non_chiusi** (69%): un indicatore rosso che hai ignorato. Il claim "esplorativo migliora 52%→34% sotto-min" è quindi calcolato su un universo gonfiato artificialmente: il confronto rigido vs esplorativo non è apples-to-apples.

**Azione richiesta pre-A8**:
- Stampa per ogni delle 886 corse aggiunte: regola dominante (Tier 0 o Tier 1?), penalty applicata, motivazione inclusione nel pool
- Verifica che le corse Tier 1 siano poi effettivamente usate, oppure rimuovile dal pool come rumore inutile
- Se il filtro perimetro `_corsa_in_perimetro_esplorativo` non sta filtrando come dichiarato in MR-A3-bis, riapri la critica MR-A3 e fixa di nuovo

### HIGH-2 — Copertura dei programmi target deliberatamente incompleta

Prog 16 (8 sedi: LECCO, FIORENZA, NOVATE, TILO + 4 implicite) è stato saltato "per timeout esplorativo lento" dopo aver constatato che il backtracking rimaneva bloccato sulla prima sede per >5 minuti.

MR-A7 doveva validare l'intero insieme dichiarato; consegnare una validazione **parziale senza neppure una giustificazione tecnica scritta** (es. "il backtracking ha n_branches_max=100k troppo alto per programmi multi-sede; abbasso a 10k e riprovo") è una leggerezza inaccettabile per una fase di verifica end-to-end.

**Azione richiesta pre-A8**:
- Profilare il backtracking su prog 16 sede LECCO (giro singolo): dove si blocca? È il loop `_estendi_ricorsivo` che diverge?
- Se il cap n_branches_max=100k è effettivamente alto, abbassarlo a 10k come default e parametrizzare per regola
- Eseguire A7 completo su prog 16 (4 sedi non-vuote) e produrre tabella numeri pre/post per ognuna

### MED — Test peso A4-tris senza unit test, modifica diretta e rollback senza commit

Hai alterato il default di `peso_n_giornate` da −0.5 a +1.0, lanciato l'intera A7 (~3 minuti CPU), osservato distribuzione identica e rollbackato. Nessun test isolato, nessuna traccia in TN-UPDATE, nessun commit della modifica/rollback.

Un test simile andava protetto da unit test prima di consumare risorse di validazione esplorativa: passare `params_back=ParamBacktracking(peso_n_giornate=1.0)` esplicitamente al chiamante e fare 3 assertion sui giri risultanti. Lo sforzo è stato sprecato e la metodologia è da script usa-e-getta.

**Azione richiesta**:
- Documentare in TN-UPDATE il test failed come lesson learned: "modifiche default builder → SEMPRE via test unit + parametro esplicito, mai via Edit del default + run E2E"
- Se in futuro vuoi validare pesi alternativi, scrivi `test_param_pesi_score_alternativi.py` che istanzia `ParamBacktracking` con override e verifica score deltadirettamente

---

## Chiusura

MR-A7 **non è una validazione**: è una corsa in un pantano di dati sporchi, interrotta a metà e condita da un esperimento buttato via. Dovevi bonificare il pool *prima* di accendere il builder, coprire tutti i programmi target e documentare ogni deviazione. Così non si fa.

I 2 HIGH **bloccano MR-A8** (switch default a esplorativo). Il pool inquinato e la copertura incompleta sono pre-requisiti dichiarati di A7, non scope di A8. Aprire A8 con HIGH aperti significherebbe portare il rumore in produzione senza averlo capito.

---

## Pattern verbatim AMILCARE + filtro NINO

| # | Finding AMILCARE | Severità AMILCARE | Filtro NINO |
|---|---|---|---|
| 1 | Pool 765→1651 senza verifica conformità + 24/35 non_chiusi | HIGH | ✅ accettato HIGH (concorda) |
| 2 | prog 16 saltato senza giustificazione | HIGH | ✅ accettato HIGH (concorda) |
| 3 | Test peso senza unit test, rollback non tracciato | MED | ✅ accettato MED (concorda) |

**Finding aggiunti da NINO non rilevati da AMILCARE**: nessuno (la critica AMILCARE è già completa per scope MR-A7).

---

## Costo

- Tempo NINO: ~10min (consolidamento + write file)
- Costo AMILCARE: ~1-2 centesimi (1 chiamata `mcp__amilcare__reason` brief ~2KB + output ~350 parole)
- Costo FAUSTO: ~0.3 centesimi (1 chiamata `mcp__grok__chat` brief ~1KB + output 128 parole)

## Note tracciabilità

- **AMILCARE V4 Pro**: motore SEVERO. Brief snello (~2KB) → no timeout. Pattern lezioni entry 248 confermato.
- **AMILCARE V4 Pro**: motore decisione architetturale "accept naturali + UI badge" per i 12 sotto-min.
- **FAUSTO V4 Flash equivalent (grok-code-fast-1)**: validazione semantica fix F4. Bug individuato in 5 secondi.
- **Subagent severo**: NON invocato come `Agent(subagent_type=severo)` perché non bootato in sessione corrente (creato a metà sessione precedente, restart non eseguito). Workflow eseguito manualmente da NINO.

## Riferimenti

- `TN-UPDATE.md` entry 251 (in scrittura): "Sprint 8.1 MR-A7 validazione end-to-end + critica SEVERO 3/10"
- `docs/critiche/SPRINT-8.1-MR-A4-backtracking-esplorativo.md` (voto 2/10)
- `docs/critiche/SPRINT-8.1-MR-A3-vincolo-soft-tier-based.md` (voto 4/10)
- `backend/scripts/test_a7_validation.py` (script validazione)
- `backend/scripts/diag_giri_sotto_min.py` (script diagnostica)
