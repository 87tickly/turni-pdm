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

*(Nessuna critica ancora prodotta. Questa lista verrà popolata da
SEVERO a partire dalla prima invocazione.)*
