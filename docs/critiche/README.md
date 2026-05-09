# Critiche di SEVERO — indice

> Output canonico delle critiche prodotte da **SEVERO**, il critico
> permanente del framework ausili (4° attore — vedi
> `docs/AUSILI-CODICE.md` e `.claude/agents/severo.md`).
>
> Ogni critica vive in un file dedicato; questo è solo l'indice
> cronologico inverso.

---

## Cosa trovi qui

Un file per ogni critica fatta da SEVERO. Convenzione di naming:

- `SPRINT-X.Y-MR-Z-titolo-breve.md` (se la critica è su un MR
  specifico identificabile)
- `YYYY-MM-DD-titolo.md` (se la critica è trasversale o non legata
  a un singolo MR)

Format di ogni file: vedi sezione "Format dell'output canonico" in
`.claude/agents/severo.md`.

## Cosa NON è SEVERO

- **Non è una review tecnica pre-commit** (FAUSTO/AMILCARE
  fanno quelle, prima del commit, per migliorare il codice prima
  di chiuderlo)
- **Non è un audit di sicurezza**
- **Non è un piano di refactor** (può segnalare debito tecnico,
  ma il piano di azione resta di NINO + utente)
- **Non sostituisce CODE-REVIEW-2026-05-01.md** (review manuale
  storica con 24 finding, vedi `docs/CODE-REVIEW-2026-05-01.md`)

## Quando viene invocato

Vedi regola 9 di `CLAUDE.md` ("Invocazione SEVERO — quando è
obbligatorio") e §10 di `docs/AUSILI-CODICE.md` (trigger linguistici).

In sintesi:
- ✅ A fine Sprint
- ✅ Dopo MR significativo (multi-file, refactor di dominio,
  cambio architetturale, nuovo algoritmo)
- ✅ Quando l'utente chiede esplicitamente
- ❌ Micro-commit (typo, doc, rename triviale)
- ❌ Hotfix urgenti

---

## Cronologia critiche (più recente in cima)

<!-- Quando SEVERO produce una nuova critica, aggiungere una riga
     in cima a questa lista nel formato:
     - **YYYY-MM-DD** — [titolo](file.md) — voto: X/10 — sintesi 1 riga
-->

- **2026-05-09** — [Sprint 8.2 MR-D5e + 2° bug architetturale single-sede vs multi-sede](SPRINT-8.2-MR-D5e+bug-architetturale-single-sede.md) — voto: **4/10 (provvisorio fallback)** — strutturale: il fix MR-D5e (commit `ff2873d`, builder.py +52 -9) chiude correttamente la FK violation MISTO su `materiale_thread.tipo_materiale_codice` (causa: cascata segmenti `_tronco_X` non mappati → fallback `MISTO` → NOT NULL+FK RESTRICT). Ma 2 residui §7 violati: S1 HIGH `loss-of-data invisibile` (giro scartato con `warnings.append` → l'utente vede HTTP 200 + n_giri=0 senza percepire lo scarto, va esposto `n_giri_scartati` in response API; <2h fix); S2 HIGH `manca test sul ramo regola_id=None→scarto` (53 test green coprono solo caso felice; <30 min fix). + S3 HIGH `2° bug architetturale single-sede` (builder.py:1252-1254 passa solo 1 sede a MR-D2 che applica racc SEVERO #2 HARD originale → 26/26 segmenti non-Milano scartati → 0 giri/52 corse vs 51 giri/2450 esplorativo, 98% perdita). La racc SEVERO #2 era corretta in multi-sede ma fatale in single-sede: assunzione mai esplicitata nel piano. + S4 MED `_materiale_da_regola[0]` amplifica limitazione monomateriale per regole multi (ETR526+ETR425 → solo ETR526). + S5 MED falla sistemica processo: 4 voti SEVERO ≥7+ tutti mock-only, e2e fallisce al primo run reale → la racc MED 9.0/10 'pipeline solo mock-tested' era corretta ma è stata ignorata da NINO + non è stata catalogata HIGH BLOCKING al primo cambio strangler (D5b). + S6 LOW `materiale_per_giro` info-only zombie code. **Raccomandazione**: (c) immediato (rollback prog 17 a `esplorativo` già fatto) + (a) MR-D5f sprint 8.3 (carica tutte sedi attive del programma in `sedi_disponibili`, mantieni persistenza scoping per `localita.codice`). 3 R-PROC processo: SEVERO obbligatorio con verifica e2e su prog reale al primo cambio strangler builder.py (max 6/10 se mock-only); ogni raccomandazione HARD esplicita assunzioni input ('HARD assumendo X'); raccomandazione MED diventa HIGH BLOCKING al primo cambio in produzione del codice mock-only. Revisione obbligatoria racc SEVERO #2 originale ('no ciclo aperto fuori area Milano' va riscritta come 'HARD assumendo MR-D2 riceve pool completo sedi attive; SOFT con proxy rientro-via-vuoto in single-sede'). ❌ AMILCARE V4 Pro non disponibile: 3 timeout `-32001` su `reason` (brief 3.5/2.5/1KB) + 1 timeout su `code` (3.5KB) → output ricevuto solo con `code` brief 1KB su V4 Flash, output filtrato da NINO (rimosso falso positivo "`_materiale_da_regola[0]` IndexError" — è funzione, gestisce composizione vuota). Voto provvisorio, da rifare con AMILCARE V4 Pro operativo.
- **2026-05-09** — [Sprint 8.2 MR-PD3a + MR-PD3b+PD4 deposito-first builder](SPRINT-8.2-MR-PD3-deposito-first.md) — voto: **4.5/10 (provvisorio fallback)** — Cuore architetturale resolver/builder corretto, ma 4 falle pre-MR-PD5: S1 CRITICAL `is_notturno` superinclusivo applicato come discriminante cap (turni con presa serale 22-23 falsamente scartati con cap 420 invece di 510, builder.py:331 vs deposito_first.py:296 incoerenti); S2 HIGH coupling cross-module su 5 simboli underscore privati di builder.py (`_BloccoPdcDraft`, `_build_giornata_pdc`, etc.) — si rompe al refactor MR-PD5+; S4 HIGH test cap-eccede ambivalente (`if draft is None... else...` accetta entrambi gli esiti, green-phase compromesso); S5 HIGH zero integration test (17 test tutti mockano resolver/API, rischio bug latenti pre-endpoint). + S3 HIGH-LATENT §7.3 condotta produttiva ignorata (scope-cutting attivo solo se giro contiene treni post-ACCa, MR-C7 dichiarato), S6 MED `DEPOT_MILANO_MM` frozenset hardcoded modulo invece di `Depot.is_servito_da_mm` DB, S7 LOW refuso `Scelza`→`Scelta` propagato 50+ occorrenze 4 file, S8 MED costanti cap duplicate 2 moduli con 2 nomi diversi (`PRESTAZIONE_MAX_*` vs `*_MIN`), S9 MED-LOW helper `_inserisci_blocco_rientro` cerca "primo FINE" si rompe con split CV MR-C7, S10 MED gap ACCa→VETTURA senza blocco esplicito (Gantt buco), S11 LOW `+15` post MM/VOCTAXI estrapola §3.2 senza documentazione. Pre-MR-PD5 obbligatori 6-8h (S1+S2+S4+S5+S7), raccomandati 2-3h (S6+S8+S9+B12). ❌ AMILCARE V4 Pro non disponibile: 4 invocazioni timeout `-32001` su brief 1.5–5KB. Fallback motore FAUSTO (Grok Code Fast) dichiarato, voto provvisorio da rifare con AMILCARE operativo.
- **2026-05-09** — [Sprint 8.2 MR-D4+D5+D5b codice committato (bridge + orchestrator + builder integration)](SPRINT-8.2-MR-D4-D5-D5b-codice-committato.md) — voto: **9.0/10** (+0.5 vs 8.5/10) approvato con 1 raccomandazione obbligatoria. 3 commit committati post 8.5/10: MR-D4 bridge TurnoConvoglio→Giro (commit `6594ded`), MR-D5 orchestrator pure-domain (commit `291743f`), MR-D5b builder.py integration + persister (commit `4a54023`). 32 nuovi test, 231 totali, ZERO regressioni su 87 test legacy. Strangler integrity verificata. HIGH-1 obbligatorio: adapter `_giro_linea_centrica_a_aggregato` con `blocchi_assegnati=()` empty = bug latente per capacity check post-persistenza → fix in MR-D5c. MED: pipeline solo mock-tested, mitigazione prima MR-D7 (run su 2-3 linee reali). LOW: doc API formali rinviate MR-D8. AMILCARE V4 Flash motore.
- **2026-05-09** — [Sprint 8.2 MR-D0..D3 codice committato (cuore architetturale)](SPRINT-8.2-MR-D0-D3-codice-committato.md) — voto: **8.5/10** approvato senza fix obbligatori. Critica obbligatoria post cuore architetturale. 5 commit greenfield (5 moduli ~2000 righe, 112 test passing): definizione_linea (D0), gestione_calendario_linea (D0.5), analizza_linee (D1), assegna_convogli_linea (D2), costruisci_turno_linea (D3). Architettura coerente, mypy/ruff clean. Le 2 raccomandazioni del piano (sosta esplicita + no_ciclo_aperto HARD) concretamente realizzate via VincoliSosta + `_e_compatibile()` con test dedicato. 3 raccomandazioni non bloccanti: test integrazione D2-D3 (scope MR-D7), doc API formali (scope MR-D8), corse_die==0 in D2 (già verificato gestito). Procedere con MR-D4. AMILCARE V4 Flash motore.
- **2026-05-09** — [Plan-D: riscrittura linea-centrica (opzione A radicale)](PLAN-D-riscrittura-linea-centrica.md) — voto finale: **7/10** approvato con 2 raccomandazioni obbligatorie. Critica preventiva sul PIANO prima del primo commit (regola memoria `feedback_severo_sempre_su_piani.md`). Iterazione 1 piano 5 MR/3-4 settimane voto 6/10 → 6 modifiche obbligatorie SEVERO (aggiunti MR-D0 definizione_linea + MR-D0.5 calendario, riscritto MR-D2 come ottimizzazione vincolata ILP, MR-D4 da zero, stima realistica 7 settimane, gate deprecation sprint 10). Iterazione 2 piano 10 MR/9-10 settimane voto 7/10 con riserve: (1) MR-D0.5 deve esplicitare vincolo sosta massima (chiude problema sosta 20h44' prog 14 giro 574); (2) MR-D2 deve trattare "no ciclo aperto fuori area Milano" come constraint HARD non soft. Risolve i 4 problemi reali (76 navette perse, 10 giri ciclo aperto, sosta 20h44', catene mix linee). AMILCARE V4 Flash motore (V4 Pro 2 timeout in fila).
- **2026-05-09** — [Sprint 8.2 PLAN preventivo revisione Pianificatore PdC](SPRINT-8.2-PLAN-PIANIFICATORE-PDC-revisione.md) — voto: **4/10 (provvisorio fallback)** — critica su PLAN PREVENTIVO (non commit) di 5 MR: tre forme di pigrizia §7 (S1 default P1=opt(c) ricalca pattern Sprint 7.10 MR 7.10.7 già bocciato dall'utente; S2 6 regole NORMATIVA tacite §10.3/§11.4/§15/§6 PK/§9 CV/§10 FR struttura; S6 P1 delegata utente pur avendo già default), 1 anti-pattern di MR paralleli (S3 C2||C3 senza interfaccia blocchi VETTURA documentata), 2 stime ottimistiche (S4 MR-C5 2-3h con migration+endpoint+errori async+E2E; S7 MR-C4 dipendente da audit C1 non ancora fatto), test plan per MR non dichiarato (S5), range stima 18-37h è 2× = fragile (S8). Bocciato per riapertura. ❌ AMILCARE V4 Pro non disponibile: 6 invocazioni timeout `-32001` su brief 2-5KB; ping minimale OK (server raggiungibile ma modello satura). Critica fallback NINO puro, voto provvisorio, da rifare con AMILCARE.
- **2026-05-09** — [Sprint 8.1 MR-B2: backtracking esteso a giri lunghi + peso_chiude_sede 50→500](SPRINT-8.1-MR-B2-backtracking-cross-rule-contamination.md) — voto: **2/10** — cross-rule contamination architetturale (HIGH-1 AMILCARE: `_trova_continuazioni_top_k` filtra solo materiale+località, mai per regola — catene di regole diverse same-material possono mischiarsi), trade-off mascherato da metriche favorevoli (HIGH-2 NINO: -13 non chiusi per +10 corse navetta non coperte, valore operativo invertito), test cross-rule mancante (MED), peso_chiude_sede=500 magic number senza A/B test (MED). Su prog 17 attuale 0 giri same-material cross-rule, ma fix architetturale necessario per programmi futuri. AMILCARE V4 Pro motore (brief ~3KB, no timeout) + verifica empirica DB post-critica.
- **2026-05-09** — [Sprint 8.1 MR-A7: validazione end-to-end builder esplorativo](SPRINT-8.1-MR-A7-validazione-end-to-end.md) — voto: **3/10** — pool corse cresciuto 765→1651 (+886) senza verifica conformità Tier 0 (HIGH-1, 264 warning whitelist sede + 24/35 non_chiusi), prog 16 saltato per timeout senza giustificazione (HIGH-2, copertura A7 incompleta), test peso A4-tris senza unit test + rollback non tracciato (MED). **MR-A8 BLOCCATO** finché HIGH-1 e HIGH-2 non chiusi. AMILCARE V4 Pro motore + FAUSTO consultato per validazione F4 (bug semantico, scartato).
- **2026-05-08** — [Sprint 8.1 MR-A4: backtracking esplorativo profondo](SPRINT-8.1-MR-A4-backtracking-esplorativo.md) — voto: **2/10** — beam×depth non misurato (HIGH-1), regressione vincoli MR-4 max_sosta_diurna/min_servizio_giornata (HIGH-2 BUG REALE), ordering A4→A2 con potenziale dispendio (HIGH-3 ridotto a MED da filtro NINO). + 3 MED auto-rilevati da NINO (score arbitraria, test no volume, regola 9 violata). **MR-A4-bis priorità #1 prima di A7**. Critica con AMILCARE V4 Pro operativo via DeepSeek diretto (entry 246).
- **2026-05-08** — [Sprint 8.1 MR-A3: vincolo soft tier-based in risolvi_corsa](SPRINT-8.1-MR-A3-vincolo-soft-tier-based.md) — voto: **4/10** — claim "sblocca sintomo R11" non dimostrato (HIGH-1 E2E rimandata MR-A7), `corse_perimetro=list(corse)` senza filtro = rischio giri spuri (HIGH-2 alzato da AMILCARE), tie-break Tier 1 su `len(filtri_json)` con filtri ignorati (HIGH-3), `TIER_1_PENALTY=50` contraddice matrice 20/40/70 (CRITICAL-1) + 2 MED. **MR-A3-bis priorità prima di A7** (~7-12h). Critica con AMILCARE V4 Pro operativo (entry 247).
