# PdE input — cartella locale per i file PdE reali

Questa cartella ospita i file `.numbers` o `.xlsx` del **Programma
di Esercizio** che vuoi importare nel DB. **Tutto il contenuto è
gitignored** (eccetto questo README): i file PdE sono dati
commerciali, decine di MB, e cambiano ogni anno — non finiscono mai
su GitHub.

La spec completa dell'import è in
[`docs/IMPORT-PDE.md`](../../../docs/IMPORT-PDE.md). Qui sotto solo
i comandi essenziali per ricordarsi come fare.

---

## Importare un PdE (workflow di tutti i giorni)

```bash
# 1) Postgres up + migrazioni applicate
docker compose up -d db
cd backend && uv run alembic upgrade head

# 2) Copia il PdE qui (esempio: file Trenord 2025-2026)
cp "/Users/spant87/Library/Mobile Documents/com~apple~Numbers/Documents/All.1A5_14dic2025-12dic2026_TRENI e BUS_Rev5_RL.numbers" \
   backend/data/pde-input/

# 3) Importa
cd backend
uv run python -m colazione.importers.pde \
    --file "data/pde-input/All.1A5_14dic2025-12dic2026_TRENI e BUS_Rev5_RL.numbers" \
    --azienda trenord
```

Atteso: ~25-30s, 10580 corse + 95220 composizioni nel DB.

## Verifica post-import

```bash
docker exec colazione_db psql -U colazione -d colazione -c "
  SELECT COUNT(*) FROM corsa_commerciale;
  SELECT COUNT(*) FROM corsa_composizione;
  SELECT * FROM corsa_import_run ORDER BY started_at DESC LIMIT 1;
"
```

## Convenzioni

- **Nome file**: lascialo come arriva da Trenord (es.
  `All.1A5_14dic2025-12dic2026_TRENI e BUS_Rev5_RL.numbers`). Il
  parser usa il nome per il tracking in `corsa_import_run.source_file`
  + lo SHA-256 per l'idempotenza.
- **Più anni**: puoi tenere più PdE qui dentro (`PdE-2024.numbers`,
  `PdE-2025.numbers`, ...). L'importer prende quello che gli passi
  con `--file`.
- **Pulizia**: per liberare spazio, semplicemente cancella i file —
  il DB conserva i dati importati e il record di `corsa_import_run`.

## Quando il PdE cambia

Se il PdE viene revisionato (es. `Rev6_RL`), copia il nuovo file qui
e lancia l'importer: idempotenza per `(numero_treno, valido_da)` →
update solo le corse modificate.

Se la fixture di test va aggiornata coi nuovi pattern:

```bash
PYTHONPATH=src uv run python scripts/build_pde_fixture.py \
    --source "data/pde-input/<nuovo-pde>.numbers"
git add tests/fixtures/pde_sample.xlsx
git commit -m "chore: aggiorna fixture PdE"
```
