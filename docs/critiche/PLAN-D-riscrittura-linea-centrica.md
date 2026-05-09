# SEVERO — Critica Plan-D (riscrittura linea-centrica, opzione A radicale)

**Data**: 2026-05-09
**Trigger invocazione**: utente esplicito (`devi sempre invocare SEVERO`),
prima dell'inizio implementazione di un piano architetturale di
riscrittura di dominio.
**Motore di SEVERO**: AMILCARE V4 Flash via `mcp__amilcare__code`
(brief ~3.5KB, output ~600 parole). V4 Pro ha avuto 2 timeout MCP
prima di passare al fallback Flash.
**Pattern**: due iterazioni di critica (piano originale 6/10 →
modifiche obbligatorie → piano rivisto 7/10 approvato con riserve).

---

## TL;DR

Plan-D riscrive il modello del builder da "catena-libera topologica"
a "linea-centrico Trenord-realistic". 10 MR sequenziali, 9-10 settimane
stimate. Risolve i 4 problemi reali (76 navette perse, 10 giri ciclo
aperto, sosta 20h44', catene mix linee). Voto SEVERO finale: **7/10**
con 2 raccomandazioni obbligatorie integrate nel piano.

---

## Iterazione 1: piano originale 5 MR (3-4 settimane) → voto 6/10

NINO ha proposto:
- MR-D1 analizza_linee
- MR-D2 assegna_convogli
- MR-D3 costruisci_turno
- MR-D4 refactor aggregazione_a2
- MR-D5 builder.py switch

**6 modifiche obbligatorie SEVERO**:

1. Aggiungere MR-D0 `definizione_linea.py`: modello formale `Linea` +
   `SegmentoLinea` (tronco/completo) + capolinee + sosta notturna per
   segmento. Senza, le navette (problema #1) non sono catturate.
2. Aggiungere MR-D0.5 `gestione_calendario_linea.py`: varianti
   giornaliere (feriale/festivo/scolastico/eccezioni) per ogni
   segmento.
3. Sostituire MR-D4 da "refactor" a riscrittura da zero di
   `aggregazione_linea_centrica.py` (no parallelismo aggregazione
   vecchia/nuova in default execution).
4. Riscrivere MR-D2 come algoritmo di **ottimizzazione vincolata**
   (ILP o constraint propagation), NON greedy.
5. Stima 3-4 settimane → realistica **7 settimane** (SEVERO
   considera 8 giorni MR-D7 e 10 giorni MR-D3 sottostimati nel
   piano NINO).
6. Strangler con **gate deprecation entro sprint 10** + **test
   regressione automatici** confronto vecchio vs nuovo.

---

## Iterazione 2: piano rivisto 10 MR (9-10 settimane) → voto 7/10

NINO ha applicato tutte le 6 modifiche.

**Per ogni problema, il piano rivisto risolve?**

| # | Problema | MR risolutivo | Voto chiusura | Assunzione fragile |
|---|---|---|---|---|
| 1 | 76 navette intra-day perse | D0 + D1 + D2 | ✅ chiude alla radice | Gerarchia `Linea→SegmentoLinea` cattura tutte le navette se i dati UI prog 17 sono completi |
| 2 | 10 giri ciclo aperto fuori Milano | D6 + D2 | ✅ chiude alla radice | Definizione "area Milano" + capolinee/depositi ben definiti |
| 3 | Sosta 20h44' fra giornate | D3 | ⚠️ **potrebbe chiudere** se MR-D3 inserisce vincolo sosta massima (oggi NON esplicitato nel piano) | **Vincolo non esplicito** nel piano — raccomandazione obbligatoria #1 |
| 4 | Catene mix linee same-regola | D0 + D6 | ✅ chiude se gate sprint 10 oscura le regole legacy | Drift se gate non implementato |

**Strangler + test regressione**: parzialmente sufficienti. MR-D7
prevede smoke ma il test regressione automatico non copre
esplicitamente la non-ricomparsa dei 4 problemi. Gate sprint 10 deve
assicurare: (a) nessuna chiamata legacy per linee migrate, (b) test
automatici dei 4 problemi, (c) `VALIDATION_LAYER` che blocchi output
non conformi.

**Rischi MR-D3 (10gg) e MR-D7 (8gg)**:

MR-D3 — slippage probabile su gestione eccezioni (festivi, scioperi,
lavori). Check intermedi ogni 2-3 giorni:
- Giorno 2: turno linea semplice, sosta notturna ≤12h
- Giorno 5: turno con navette + vuoti, no ciclo aperto fuori area
- Giorno 8: turno linea lunga, no break >6h ingiustificato

MR-D7 — slippage su dati test incompleti / ambienti integrazione.
Check intermedi:
- Giorno 4: smoke funzionante su prog 17 con 50% linee
- Giorno 6: regressione automatica 4 problemi superata su set linee

---

## Raccomandazioni obbligatorie integrate (per mantenere voto 7+)

### Raccomandazione 1 — Vincolo sosta esplicito in MR-D0.5

**Cosa**: MR-D0.5 deve produrre specifica formale dei vincoli di
sosta come dati strutturati:
- `sosta_massima_diurna_min` per segmento (default 240 min = 4h)
- `sosta_massima_notturna_min` per segmento (default 720 min = 12h)
- `criteri_rottura` se sosta > soglia (rientro deposito vs vuoto
  tecnico vs cambio convoglio)

**Perché**: senza questo, MR-D3 produrrebbe ancora pattern come la
sosta 20h44' del caso prog 14 giro 574. Il vincolo va nei dati
(programma_regola_assegnazione o nuovo campo Linea), non hardcoded.

### Raccomandazione 2 — Constraint hard "no ciclo aperto fuori area"

**Cosa**: MR-D2 deve trattare "nessun ciclo aperto fuori area Milano"
come **vincolo hard** (constraint che fa fallire l'ottimizzazione se
violato), non come penalità score.

**Perché**: con penalità soft, l'ottimizzatore può accettare un
ciclo aperto se altre componenti score compensano. La realtà
operativa Trenord non lo permette: un convoglio resta in deposito
o in stazione di sosta ammessa, mai vagante fuori area senza
rientro programmato.

**Implementazione**: `constraint_no_ciclo_aperto_fuori_area`
parametrizzato per programma con whitelist aree ammesse.

---

## Approvazione

**Voto: 7/10 — procedere con MR-D0**

NINO procede con l'implementazione. Le 2 raccomandazioni obbligatorie
sono integrate nei rispettivi MR (D0.5 e D2). Mancata integrazione
porterà a voto negativo allo step successivo.

---

## Riferimenti

- TN-UPDATE entry 257 (in scrittura) — narrazione approvazione plan-D
- `docs/critiche/SPRINT-8.1-MR-B2-backtracking-cross-rule-contamination.md`
  — critica precedente che ha innescato la riscrittura
- AMILCARE V4 Flash via `mcp__amilcare__code` — motore SEVERO usato
  per entrambe le iterazioni (V4 Pro instabile in entry 252-256)
