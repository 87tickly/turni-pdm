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

- **2026-05-09** — [Sprint 8.1 MR-B2: backtracking esteso a giri lunghi + peso_chiude_sede 50→500](SPRINT-8.1-MR-B2-backtracking-cross-rule-contamination.md) — voto: **2/10** — cross-rule contamination architetturale (HIGH-1 AMILCARE: `_trova_continuazioni_top_k` filtra solo materiale+località, mai per regola — catene di regole diverse same-material possono mischiarsi), trade-off mascherato da metriche favorevoli (HIGH-2 NINO: -13 non chiusi per +10 corse navetta non coperte, valore operativo invertito), test cross-rule mancante (MED), peso_chiude_sede=500 magic number senza A/B test (MED). Su prog 17 attuale 0 giri same-material cross-rule, ma fix architetturale necessario per programmi futuri. AMILCARE V4 Pro motore (brief ~3KB, no timeout) + verifica empirica DB post-critica.
- **2026-05-09** — [Sprint 8.1 MR-A7: validazione end-to-end builder esplorativo](SPRINT-8.1-MR-A7-validazione-end-to-end.md) — voto: **3/10** — pool corse cresciuto 765→1651 (+886) senza verifica conformità Tier 0 (HIGH-1, 264 warning whitelist sede + 24/35 non_chiusi), prog 16 saltato per timeout senza giustificazione (HIGH-2, copertura A7 incompleta), test peso A4-tris senza unit test + rollback non tracciato (MED). **MR-A8 BLOCCATO** finché HIGH-1 e HIGH-2 non chiusi. AMILCARE V4 Pro motore + FAUSTO consultato per validazione F4 (bug semantico, scartato).
- **2026-05-08** — [Sprint 8.1 MR-A4: backtracking esplorativo profondo](SPRINT-8.1-MR-A4-backtracking-esplorativo.md) — voto: **2/10** — beam×depth non misurato (HIGH-1), regressione vincoli MR-4 max_sosta_diurna/min_servizio_giornata (HIGH-2 BUG REALE), ordering A4→A2 con potenziale dispendio (HIGH-3 ridotto a MED da filtro NINO). + 3 MED auto-rilevati da NINO (score arbitraria, test no volume, regola 9 violata). **MR-A4-bis priorità #1 prima di A7**. Critica con AMILCARE V4 Pro operativo via DeepSeek diretto (entry 246).
- **2026-05-08** — [Sprint 8.1 MR-A3: vincolo soft tier-based in risolvi_corsa](SPRINT-8.1-MR-A3-vincolo-soft-tier-based.md) — voto: **4/10** — claim "sblocca sintomo R11" non dimostrato (HIGH-1 E2E rimandata MR-A7), `corse_perimetro=list(corse)` senza filtro = rischio giri spuri (HIGH-2 alzato da AMILCARE), tie-break Tier 1 su `len(filtri_json)` con filtri ignorati (HIGH-3), `TIER_1_PENALTY=50` contraddice matrice 20/40/70 (CRITICAL-1) + 2 MED. **MR-A3-bis priorità prima di A7** (~7-12h). Critica con AMILCARE V4 Pro operativo (entry 247).
