# TN-UPDATE — Diario del nuovo programma (greenfield)

> Questo file viene aggiornato dopo **ogni modifica** al progetto.
> È il diario operativo del nuovo programma, costruito da zero.
>
> **Predecessore archiviato**: `docs/_archivio/LIVE-COLAZIONE-storico.md`
> contiene il diario del progetto vecchio (eliminato il 2026-04-25).
> Lì si trova la storia di come ci siamo arrivati al modello dati e
> all'architettura, in caso serva un riferimento.

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
