# Handoff · Step 0 Abilitazioni — redesign

> Sintesi dal bundle Claude Design `wZp8lKDl6NNAwq9ntepASA`
> (`screen-abilitazioni.html` + note della chat). Non c'era un
> `HANDOFF-abilitazioni.md` esplicito nel bundle: questo documento
> ricostruisce le specifiche dal mockup per tracciabilita'.

## 1. Scopo

Ridisegnare la sezione "Step 0 · Abilitazioni" di
`AutoBuilderPage.tsx` (pannello `AbilitazioniPanel`) in modo che:

- **Collapsed**: il dispatcher capisce in 1 sguardo se il deposito è
  configurato bene — senza espandere nulla.
- **Expanded**: linee raggruppate per **corridoio**, chip materiali in
  alto (non piu' "codina" in fondo), search inline con shortcut `/`,
  bulk toggle per corridoio e globale.

## 2. File toccati

| File | Azione |
|---|---|
| `frontend/src/lib/corridors.ts` | **NEW** — mapping deterministico stazione → corridoio (5 corridoi + fallback "Altri") e `groupLinesByCorridor(lines)`. |
| `frontend/src/components/AbilitazioniPanel.tsx` | **Riscritto**. API prop invariata (`deposito: string`), stesse chiamate API backend. |

## 3. Contratto API preservato

Nessun cambio backend. Il componente usa:

- `getAbilitazioni(deposito)` — legge `available_lines` +
  `available_materials` (con `enabled: boolean` e
  `material_turn_count: number`).
- `addLinea(deposito, a, b)` / `removeLinea(deposito, a, b)`
- `addMateriale(deposito, mat)` / `removeMateriale(deposito, mat)`

Toggle sono ottimistici (chiamata immediata + reload), come prima.

## 4. Logica raggruppamento corridoi

Per il deposito ALESSANDRIA (estendibile per altri depositi):

| Ordine | Corridoio | Badge | Stazioni matcher |
|---|---|---|---|
| 1 | Transit ASTI | `AT` ambra | `ASTI` in A o B |
| 2 | Milano | `MI` blu brand | `MI.*` oppure `MILANO*` |
| 3 | Bergamo | `BG` viola | `BERGAMO` / `TREVIGLIO` |
| 4 | Pavia/Po | `PV` teal | `PAVIA` / `BELGIOIOSO` / `TORTONA` |
| 5 | Mortara/Vigevano | `MV` slate | `MORTARA` / `VIGEVANO` / `VERCELLI` / `CREMONA` / `CASALPUSTERLENGO` / `BRESCIA` |
| 99 | Altri | `OT` | fallback |

**Ordine importante**: il primo match vince. Questo risolve casi di
confine come `PAVIA↔VERCELLI` → Pavia/Po (non Mortara/Vig) e
`MILANO ROGOREDO↔MORTARA` → Milano (non Mortara/Vig).

Se serve granularita' per-deposito, estendere come
`CORRIDORS_BY_DEPOT[deposito]: Record<string, (s: string) => boolean>`.

## 5. Stati visivi

### Collapsed (card chiusa)

- Shield icon (verde se configurato, warning se no)
- Contatore `N/M linee · P/Q materiali`
- Nome dei primi 3 corridoi coperti
- **Mini coverage bar**: 6 colonne, una per corridoio attivo (o 5 +
  "Altri" se presente), ciascuna con nome + `enabled/total` e
  riempimento colorato proporzionale al ratio enabled.
- Chevron giu' a destra per espandere

### Expanded (card aperta)

- **Chip materiali** orizzontali in alto (promossi rispetto alla
  "codina" legacy)
- **Linee per corridoio** sotto, ciascuno con:
  - Badge colorato (`MI`, `PV`, `AT`, `BG`, `MV`, `OT`)
  - Nome corridoio + contatore `enabled/total`
  - Bottoni inline `Tutte` / `Nessuna`
  - Chevron collassabile per nascondere le righe
- **Search inline** con shortcut `/` (filtro live case-insensitive
  su station_a OR station_b)
- **Bulk** `Attiva visibili` (add su tutto il filtered-grouped) e
  `Azzera tutto` (remove su tutte le enabled)

## 6. Tokens / colori

Usa i token esistenti del DS Kinetic Conductor:
- `--color-success` per enabled (verde)
- `--color-warning` per not-fully-configured
- `--color-on-surface-*` gerarchia ink
- Badge colors per corridoio definiti in `CORRIDORS` di
  `frontend/src/lib/corridors.ts`

## 7. Interazioni

| Azione | Comportamento |
|---|---|
| Click riga linea | toggle on/off (ottimistico) |
| Click chip materiale | toggle on/off |
| Click header corridoio | espandi/collassa |
| Click `Tutte` corridoio | enable ogni linea del corridoio (loop API) |
| Click `Nessuna` corridoio | disable ogni linea del corridoio |
| Input search | filtro live su station_a / station_b |
| Focus `/` globale | focus input search (solo quando expanded) |
| `Attiva visibili` | enable tutte le linee attualmente visibili post-filtro |
| `Azzera tutto` | disable tutte le linee enabled del deposito |

## 8. Residui / future

- Migrazione backend per ridurre round-trip (`POST /abilitazioni/bulk`)
  invece del loop `addLinea` — il design funziona oggi, ma il loop è
  lento su corridoi grandi (es. Bergamo 4 linee × ~100ms).
- Tooltip su coverage bar con lista linee (non prioritario).
- Drag-drop per ri-assegnare una linea a un corridoio manualmente
  (se la classificazione automatica sbaglia) — non necessario oggi, il
  mapping copre tutti i casi reali osservati.
