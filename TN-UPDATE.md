# TN-UPDATE — Diario del nuovo programma (greenfield)

> Questo file viene aggiornato dopo **ogni modifica** al progetto.
> È il diario operativo del nuovo programma, costruito da zero.
>
> **Predecessore archiviato**: `docs/_archivio/LIVE-COLAZIONE-storico.md`
> contiene il diario del progetto vecchio (eliminato il 2026-04-25).
> Lì si trova la storia di come ci siamo arrivati al modello dati e
> all'architettura, in caso serva un riferimento.

---

## 2026-04-25 (3) — FASE C doc 1: VISIONE.md scritta

### Contesto

Primo documento architetturale del nuovo progetto. Scopo: chiarire
in modo permanente cosa stiamo costruendo, per chi, e perché. Punto
di riferimento per qualsiasi domanda di scope ("c'è dentro X?" → si
controlla qui).

### Modifiche

**Nuovo `docs/VISIONE.md` (draft v0.1)**:
- §1 Frase manifesto: sistema operativo per pianificazione
  ferroviaria nativa, dal contratto commerciale al singolo
  macchinista
- §2 Il problema reale: 3 silos disconnessi (PdE, turno materiale,
  turno PdC) cuciti con parser fragili
- §3 Cosa fa il programma: 4 funzioni primarie (importa PdE, genera
  giro, genera PdC, assegna persone) + 5a (revisioni provvisorie con
  cascading)
- §4 5 ruoli destinatari: pianificatore giro / pianificatore PdC /
  manutenzione / gestione personale / personale finale (PdC)
- §5 Cosa NON e': 6 esclusioni esplicite (no biglietteria, no real-
  time da zero, no manutenzione predittiva, no payroll, no RFI, no
  solo Trenord)
- §6 7 principi guida: costruzione non importazione, no parser
  fragili come ingresso primario, modello a piramide, multi-tenant
  giorno 1, 5 dashboard 1 modello, revisioni provvisorie tracciate,
  sviluppo iterativo
- §7 Definizione di successo (uomo davanti al monitor + scala
  industriale)
- §8 Ambito rilascio: MVP v1 → v1.0 → v1.x → v2.0 → v2.x (no date)
- §9 Riferimenti incrociati a documenti gia esistenti e in coda

### Stato

- Documento draft v0.1, ~250 righe.
- Pronto per revisione utente.

### Prossimo step

**MI FERMO QUI.** Il prossimo documento (`STACK-TECNICO.md`) richiede
decisioni dell'utente su:
- Linguaggio backend (Python? Node? Go? Rust?)
- Framework backend (FastAPI? Express? Fastify? altro?)
- Frontend (React? Vue? Svelte? Next/Remix?)
- DB primario (SQLite locale + Postgres prod come prima?)
- Hosting (Railway? Vercel? Fly.io? Cloudflare? self-host?)
- Auth (JWT? sessions? OAuth? Clerk/Auth0?)

Aspetto input dell'utente prima di scrivere STACK-TECNICO.md.

---

## 2026-04-25 (2) — FASE B completata: nuovo CLAUDE.md + .gitignore

### Contesto

CLAUDE.md vecchio era pieno di riferimenti al codice eliminato in
FASE A (server.py, FastAPI, Tauri, parser PDF, train_segment, builder
genetico, ecc.). Riscrittura completa per il nuovo progetto greenfield.

### Modifiche

**`CLAUDE.md`** completamente riscritto:
- Stato del progetto: greenfield, in scrittura specifiche
- 7 regole operative obbligatorie (lettura TN-UPDATE.md, aggiornamento
  TN-UPDATE.md dopo ogni task, METODO-DI-LAVORO.md, lettura dominio,
  manifesto greenfield, sviluppo per ruoli)
- Mappa dei documenti di dominio con "quando leggerli"
- Stato fasi A/B/C/D + lista 7 documenti FASE C
- Stack tecnologico: TBD in `docs/STACK-TECNICO.md` (FASE C doc 2)
- Glossario dominio essenziale (PdE, giro materiale, turno PdC, CV,
  PK, ACCp/ACCa, vettura, materiale vuoto, FR, S.COMP, ciclo 5+2)
- Convenzioni naming + riferimenti a tutti i .md

**`.gitignore`** aggiornato:
- Rimosse voci specifiche al vecchio (turni.db, server.log, uploads/
  hardcoded, ecc.)
- Aggiunte sezioni separate per Python e Node.js (entrambi ignorati
  finche non scegliamo lo stack)
- Strutturato per essere stack-agnostic e estendibile in FASE C

### Stato

- CLAUDE.md ora rispecchia il progetto attuale (greenfield)
- .gitignore agnostic per qualsiasi stack
- Repo pronto per FASE C (scrittura specifiche architetturali)

### Prossimo step

FASE C documento 1: `docs/VISIONE.md`. Cos'e' il programma, per chi,
cosa risolve, scope esplicito.

---

## 2026-04-25 — Greenfield reset (FASE A completata)

### Decisione

Il progetto vecchio (parser PDF Gantt centrato su `train_segment`,
backend FastAPI 60+ file Python, frontend React 1GB) è stato dichiarato
inutile dall'utente. Si parte da zero col nuovo programma nativo,
basato su:

- Logica di costruzione **PdE → giro materiale → turno PdC → personale**
- 5 dashboard separate per ruolo (pianificatori, manutenzione,
  gestione personale, personale finale)
- Modello dati a piramide v0.5 (vedi `docs/MODELLO-DATI.md`)
- Manifesto "non copiamo Trenord" — usano il loro sistema come
  ispirazione, non come template

### Cancellato in questo commit

| Categoria | Cosa | Motivo |
|-----------|------|--------|
| Backend | `server.py`, `app.py`, `api/` (18 file), `services/`, `src/` (1.2 MB di codice) | Logica vecchia centrata su parser PDF |
| Frontend | `frontend/` (~1 GB con node_modules), `static/`, `mockups/` | UI vecchia da riscrivere |
| Test | `tests/` (808 KB) | Test del codice vecchio |
| Dati runtime | `turni.db` (20 MB), `turni_backup_*.db`, `turno_materiale_treni.json`, `uploads/` (5.2 MB), `fr_stations.txt` | DB locale + dati vecchi |
| Config deploy | `Procfile`, `railway.toml`, `runtime.txt`, `.dockerignore`, `.railwayignore`, `requirements.txt`, `.env.example` | Deploy vecchio Railway |
| Script ad-hoc | `parse_turno_materiale.py`, `import_turno_materiale.py`, `debug_digits.py`, `scripts/enrich_db_*.py` | Tool 1-shot del vecchio |
| Junk | `nul`, `server.log`, `__pycache__/`, `.pytest_cache/`, `.venv/` | Cache + log |
| Config app | `config/` | Config app vecchia |

**Spazio liberato**: ~1.05 GB.

### Archiviato in `docs/_archivio/`

| Cosa | Motivo |
|------|--------|
| `LIVE-COLAZIONE-storico.md` (370 KB) | Memoria storica del progetto vecchio |
| `MIGRAZIONE-DATI.md` | Piano di migrazione DB (rinnegato — questo era progetto greenfield, non migrazione) |
| `GANTT-GUIDE.md`, `HANDOFF-*.md` (×5), `PROMPT-claude-design-*.md` (×5), `REFERENCE-*.css/.html` (×5), `PLAN-parser-refactor.md`, `claude-design-bundles/`, `stitch-mockups/` | UI vecchia (mockup, prompt, riferimenti) |
| `scripts/extract_depositi_manutenzione.py` | Utility 1-shot per estrarre depositi dal PDF (riutilizzabile se serve) |

### Tenuto (dominio + base nuovo progetto)

| Cosa | Motivo |
|------|--------|
| `docs/NORMATIVA-PDC.md` (1292 righe) | **Fonte verità** dominio Trenord |
| `docs/METODO-DI-LAVORO.md` | Framework comportamentale (vale sempre) |
| `docs/MODELLO-DATI.md` v0.5 | Modello concettuale (12 entità + manifesto) |
| `docs/ALGORITMO-BUILDER.md` | Spec algoritmo (riferimento, da riscrivere in chiave nativa) |
| `docs/ARCHITETTURA-BUILDER-V4.md` | Idea "centrata sulla condotta" (riferimento) |
| `docs/schema-pdc.md` | Schema dati turno PdC (riferimento) |
| `data/depositi_manutenzione_trenord_seed.json` | Anagrafica reale 7 depositi + 1884 pezzi |
| `CLAUDE.md` | Da **riscrivere** in FASE B per nuovo progetto |
| `.gitignore` | Da aggiornare per nuovo stack |
| `.claude/` | Config harness Claude Code |

### Stato repo dopo FASE A

```
COLAZIONE/
├── .claude/
├── .git/
├── .gitignore
├── CLAUDE.md                ← da riscrivere (FASE B)
├── TN-UPDATE.md             ← questo diario (nuovo)
├── data/
│   └── depositi_manutenzione_trenord_seed.json
└── docs/
    ├── ALGORITMO-BUILDER.md       ← riferimento
    ├── ARCHITETTURA-BUILDER-V4.md ← riferimento
    ├── METODO-DI-LAVORO.md        ← framework
    ├── MODELLO-DATI.md            ← v0.5
    ├── NORMATIVA-PDC.md           ← dominio
    ├── schema-pdc.md              ← riferimento
    └── _archivio/                 ← memoria progetto vecchio
```

### Prossimi step

- **FASE B**: riscrivere `CLAUDE.md` per il nuovo progetto
- **FASE C** (multi-commit): scrivere documentazione architetturale
  nativa, un documento per volta:
  1. `docs/VISIONE.md`
  2. `docs/STACK-TECNICO.md`
  3. `docs/RUOLI-E-DASHBOARD.md`
  4. `docs/LOGICA-COSTRUZIONE.md`
  5. `docs/SCHEMA-DATI-NATIVO.md`
  6. `docs/IMPORT-PDE.md`
  7. `docs/PIANO-MVP.md`
- **FASE D**: inizio costruzione codice (solo dopo che A+B+C sono
  chiusi e validati dall'utente)
