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

- **2026-05-09** — [Sprint 8.2 MR-D0..D3 codice committato (cuore architetturale)](SPRINT-8.2-MR-D0-D3-codice-committato.md) — voto: **8.5/10** approvato senza fix obbligatori. Critica obbligatoria post cuore architetturale. 5 commit greenfield (5 moduli ~2000 righe, 112 test passing): definizione_linea (D0), gestione_calendario_linea (D0.5), analizza_linee (D1), assegna_convogli_linea (D2), costruisci_turno_linea (D3). Architettura coerente, mypy/ruff clean. Le 2 raccomandazioni del piano (sosta esplicita + no_ciclo_aperto HARD) concretamente realizzate via VincoliSosta + `_e_compatibile()` con test dedicato. 3 raccomandazioni non bloccanti: test integrazione D2-D3 (scope MR-D7), doc API formali (scope MR-D8), corse_die==0 in D2 (già verificato gestito). Procedere con MR-D4. AMILCARE V4 Flash motore.
- **2026-05-09** — [Plan-D: riscrittura linea-centrica (opzione A radicale)](PLAN-D-riscrittura-linea-centrica.md) — voto finale: **7/10** approvato con 2 raccomandazioni obbligatorie. Critica preventiva sul PIANO prima del primo commit (regola memoria `feedback_severo_sempre_su_piani.md`). Iterazione 1 piano 5 MR/3-4 settimane voto 6/10 → 6 modifiche obbligatorie SEVERO (aggiunti MR-D0 definizione_linea + MR-D0.5 calendario, riscritto MR-D2 come ottimizzazione vincolata ILP, MR-D4 da zero, stima realistica 7 settimane, gate deprecation sprint 10). Iterazione 2 piano 10 MR/9-10 settimane voto 7/10 con riserve: (1) MR-D0.5 deve esplicitare vincolo sosta massima (chiude problema sosta 20h44' prog 14 giro 574); (2) MR-D2 deve trattare "no ciclo aperto fuori area Milano" come constraint HARD non soft. Risolve i 4 problemi reali (76 navette perse, 10 giri ciclo aperto, sosta 20h44', catene mix linee). AMILCARE V4 Flash motore (V4 Pro 2 timeout in fila).
- **2026-05-09** — [Sprint 8.2 PLAN preventivo revisione Pianificatore PdC](SPRINT-8.2-PLAN-PIANIFICATORE-PDC-revisione.md) — voto: **4/10 (provvisorio fallback)** — critica su PLAN PREVENTIVO (non commit) di 5 MR: tre forme di pigrizia §7 (S1 default P1=opt(c) ricalca pattern Sprint 7.10 MR 7.10.7 già bocciato dall'utente; S2 6 regole NORMATIVA tacite §10.3/§11.4/§15/§6 PK/§9 CV/§10 FR struttura; S6 P1 delegata utente pur avendo già default), 1 anti-pattern di MR paralleli (S3 C2||C3 senza interfaccia blocchi VETTURA documentata), 2 stime ottimistiche (S4 MR-C5 2-3h con migration+endpoint+errori async+E2E; S7 MR-C4 dipendente da audit C1 non ancora fatto), test plan per MR non dichiarato (S5), range stima 18-37h è 2× = fragile (S8). Bocciato per riapertura. ❌ AMILCARE V4 Pro non disponibile: 6 invocazioni timeout `-32001` su brief 2-5KB; ping minimale OK (server raggiungibile ma modello satura). Critica fallback NINO puro, voto provvisorio, da rifare con AMILCARE.
- **2026-05-09** — [Sprint 8.1 MR-B2: backtracking esteso a giri lunghi + peso_chiude_sede 50→500](SPRINT-8.1-MR-B2-backtracking-cross-rule-contamination.md) — voto: **2/10** — cross-rule contamination architetturale (HIGH-1 AMILCARE: `_trova_continuazioni_top_k` filtra solo materiale+località, mai per regola — catene di regole diverse same-material possono mischiarsi), trade-off mascherato da metriche favorevoli (HIGH-2 NINO: -13 non chiusi per +10 corse navetta non coperte, valore operativo invertito), test cross-rule mancante (MED), peso_chiude_sede=500 magic number senza A/B test (MED). Su prog 17 attuale 0 giri same-material cross-rule, ma fix architetturale necessario per programmi futuri. AMILCARE V4 Pro motore (brief ~3KB, no timeout) + verifica empirica DB post-critica.
- **2026-05-09** — [Sprint 8.1 MR-A7: validazione end-to-end builder esplorativo](SPRINT-8.1-MR-A7-validazione-end-to-end.md) — voto: **3/10** — pool corse cresciuto 765→1651 (+886) senza verifica conformità Tier 0 (HIGH-1, 264 warning whitelist sede + 24/35 non_chiusi), prog 16 saltato per timeout senza giustificazione (HIGH-2, copertura A7 incompleta), test peso A4-tris senza unit test + rollback non tracciato (MED). **MR-A8 BLOCCATO** finché HIGH-1 e HIGH-2 non chiusi. AMILCARE V4 Pro motore + FAUSTO consultato per validazione F4 (bug semantico, scartato).
- **2026-05-08** — [Sprint 8.1 MR-A4: backtracking esplorativo profondo](SPRINT-8.1-MR-A4-backtracking-esplorativo.md) — voto: **2/10** — beam×depth non misurato (HIGH-1), regressione vincoli MR-4 max_sosta_diurna/min_servizio_giornata (HIGH-2 BUG REALE), ordering A4→A2 con potenziale dispendio (HIGH-3 ridotto a MED da filtro NINO). + 3 MED auto-rilevati da NINO (score arbitraria, test no volume, regola 9 violata). **MR-A4-bis priorità #1 prima di A7**. Critica con AMILCARE V4 Pro operativo via DeepSeek diretto (entry 246).
- **2026-05-08** — [Sprint 8.1 MR-A3: vincolo soft tier-based in risolvi_corsa](SPRINT-8.1-MR-A3-vincolo-soft-tier-based.md) — voto: **4/10** — claim "sblocca sintomo R11" non dimostrato (HIGH-1 E2E rimandata MR-A7), `corse_perimetro=list(corse)` senza filtro = rischio giri spuri (HIGH-2 alzato da AMILCARE), tie-break Tier 1 su `len(filtri_json)` con filtri ignorati (HIGH-3), `TIER_1_PENALTY=50` contraddice matrice 20/40/70 (CRITICAL-1) + 2 MED. **MR-A3-bis priorità prima di A7** (~7-12h). Critica con AMILCARE V4 Pro operativo (entry 247).
