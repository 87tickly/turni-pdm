# SEVERO — Critica codice MR-D4 + MR-D5 + MR-D5b

**Data**: 2026-05-09
**Trigger invocazione**: obbligatoria post-MR significativo
(MR-D5b tocca builder.py = primo cambio rischioso strangler).
**Motore di SEVERO**: AMILCARE V4 Flash via `mcp__amilcare__code`
(brief ~3.5KB, output ~600 parole, no timeout).

---

## TL;DR

3 commit committati (MR-D4 bridge + MR-D5 orchestrator + MR-D5b
builder integration), 32 nuovi test, 231 test totali passing,
zero regressioni. **Voto: 9.0/10** (era 8.5/10 su MR-D0..D3).
Strangler integrity verificata. Una raccomandazione obbligatoria:
fix adapter `blocchi_assegnati=()` empty.

---

## Voto: **9.0/10** (+0.5 vs 8.5/10 precedente)

Miglioramenti concreti rispetto alla critica precedente:
- 32 test nuovi (+14% coverage)
- Test integrazione D2→D3→D4 cross-modulo (parziale soddisfacimento
  raccomandazione SEVERO #1 ultima critica)
- Pipeline end-to-end testata smoke multi-scenario
- Strangler integrity verificata (zero regressioni 87 test legacy)
- mypy strict + ruff clean

Penalità (-1.0 da 10):
- Adapter `_giro_linea_centrica_a_aggregato` con
  `blocchi_assegnati=()` empty = bug latente (vd. §3)
- Doc API formali (Protocol typing) ancora rinviate a MR-D8
- Pipeline testata solo in mock = rischio bug latenti su dati reali

---

## Findings

### 1) Strangler integrity: ✅ pulito

Modifica `builder.py` è early return dopo `area_per_stazione`,
posizionata DOPO il punto legacy:

```python
if programma.builder_mode == "linea_centrica":
    return await _genera_giri_linea_centrica(...)
```

Tutti i percorsi originali invariati per `builder_mode ≠
'linea_centrica'`. 87 test legacy passano inalterati (no leak
stato, no cambio comportamento laterale).

Rischio teorico: caricamento `dotazione` failure (DB down) cascade
all'intero `genera_giri()`. **Mitigato**: chiamata readonly,
fallimento gestito dal chiamante. Accettabile.

### 2) HIGH — Adapter `blocchi_assegnati=()` empty

**Bug latente**. `GiroAggregato.blocchi_assegnati` conserva info
turni effettive (sosta, ciclo aperto, catene). Se vuoto:
- Componenti legacy che leggono `blocchi_assegnati` troveranno lista
  vuota dopo persistenza.
- Capacity check post-persistenza, conflitti, composizioni miste
  future fallirebbero silenziosamente.

**Raccomandazione obbligatoria**: in MR-D6 (o MR-D5c separato)
mappare i blocchi reali del `Giro` puro-dominio.

Pattern: per ogni corsa del giro, creare `BloccoAssegnato` con
`regola_id` derivata da `materiale_per_segmento`. Test che persiste
e ricarica `GiroAggregato` e verifica `blocchi_assegnati` non vuoto.

### 3) MED — Pipeline solo in mock, rischio dati reali

I test smoke usano dati fittizi (linee R31_completo con 2-4 corse
sintetiche). Sui reali prog 17/14 possono emergere:
- **Segmentazione fuori area**: `analizza_linee` può dividere tratte
  in modo inatteso con dati real (curve velocità, ID stazioni Trenord).
- **Capacity overflow su festività reali**: `genera_calendario` con
  festività complete potrebbe trovare picchi non testati.
- **Giri sosta >20h44'**: se tempi reali divergono dai mock, il
  vincolo sosta_max_diurna_min potrebbe essere violato.

**Mitigazione PRIMA di MR-D7**:
1. Esegui pipeline su sottoinsieme reale (2-3 linee, 1 settimana)
2. Confronta metriche chiave: navette perse (deve scendere), nessun
   giro fuori area, sosta <20h44', catene mix = 0
3. Aggiungi test property-based su D2/D3 (capacità variabili)

Riduce rischio bug latenti del ~70%.

### 4) LOW — Doc API formali rinviate a MR-D8

Le interfacce fra moduli (`SegmentoLinea`, `AssegnazioneSegmento`,
`TurnoConvoglio`, `Giro`) non sono ancora documentate come Protocol
typing. MR-D5b ha esposto le funzioni async (`_genera_giri_linea_centrica`,
`_giro_linea_centrica_a_aggregato`) ma le firme sono solo via
docstring. Scope MR-D8 cleanup. **Accettabile** per ora ma sale
priorità con altri MR.

---

## Approvazione

**Voto 9.0/10 ≥ 7 → procedere con MR-D6**.

**Raccomandazione obbligatoria** (chiude HIGH-1):
- MR-D6 (o MR-D5c standalone) deve fixare l'adapter
  `_giro_linea_centrica_a_aggregato`: `blocchi_assegnati` deve
  contenere `BloccoAssegnato` validi per ogni corsa del giro.
- Aggiungere test integrazione: persisti + ricarica + verifica
  `blocchi_assegnati` non vuoto.

**Raccomandazioni non bloccanti**:
- (MR-D6/D7) Validazione su dati reali prima di MR-D7 e2e completo.
- (MR-D8) Doc API formali con Protocol typing.

---

## Riferimenti

- TN-UPDATE entry 264 — narrazione MR-D5b builder integration
- Commit serie post 8.5/10: `6594ded` (D4), `291743f` (D5),
  `4a54023` (D5b)
- Critica precedente:
  `docs/critiche/SPRINT-8.2-MR-D0-D3-codice-committato.md`
  (voto 8.5/10)
- AMILCARE V4 Flash via `mcp__amilcare__code` — motore SEVERO
