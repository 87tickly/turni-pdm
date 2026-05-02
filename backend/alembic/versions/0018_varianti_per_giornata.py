"""0018 — Varianti per giornata + aggregazione A2 (Sprint 7.7 MR 5)

Re-introduce ``giro_variante`` come "varianti calendariali della
giornata-tipo" (modello Trenord turno 1134). Ribalta il MR 7.7.3 che
aveva collassato il concetto: in realtà le varianti sono utili e
necessarie, vanno solo etichettate in modo parlante.

Decisione utente 2026-05-02 (PDF turno 1134 ETR204 FIO):

> "Se un giro materiale in un determinato giorno ha delle variazioni
> deve essere creato un giro solo per quel determinato giorno [...]
> oppure giornata festiva oppure giornata 7 LV"

> "B1: è lo stesso turno, ma in determinate giornate il materiale fa
> giri diversi perchè in quei giorni quei treni non ci sono"

Modello target (chiave A2 = ``(materiale, sede, n_giornate)``):

- 1 ``GiroMateriale`` per ciascuna combinazione ``(materiale_tipo_codice,
  localita_manutenzione, numero_giornate)``.
- ``GiroGiornata`` numerate (1..N).
- Ogni giornata ha M ``GiroVariante`` con sequenza di blocchi propria
  e date di applicazione disgiunte.
- ``validita_testo`` (es. "LV 1:5", "F") + ``dates_apply_json``
  (date concrete) sono per variante, non per giornata.
- L'etichetta parlante (es. "LV 1:5 · 12 date") è calcolata dalle
  query read-side, non persistita (deriva da ``validita_testo`` +
  ``len(dates_apply_json)``).

Wipe pre-migration: i giri MR 7.7.3/4 attuali nel DB sono solo prove
(decisione utente 2026-05-02). Niente backfill, rigenerazione da zero.

Schema diff dal MR 0016/0017:

- ``giro_giornata``: drop ``validita_testo``, ``dates_apply_json``,
  ``dates_skip_json`` (tornano su variante).
- ``giro_materiale``: drop ``etichetta_tipo``, ``etichetta_dettaglio``
  (concetto superseded — l'etichetta vive per variante).
- ``giro_blocco``: drop ``giro_giornata_id``, add ``giro_variante_id``.
- New table ``giro_variante`` (struttura simile a quella pre-MR 0016
  ma con commenti e default coerenti con MR 5).
"""

from __future__ import annotations

from alembic import op

revision: str = "b6f9c4a82dd1"
down_revision: str | None = "1a4d6e92c8b3"  # 0017_numero_turno_40
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ----------------------------------------------------------------
    # 1. Wipe giri esistenti (rigenerazione da zero; modello cambia
    #    nettamente, niente backfill possibile sensato).
    # ----------------------------------------------------------------
    op.execute("DELETE FROM giro_materiale")
    op.execute(
        "DELETE FROM corsa_materiale_vuoto WHERE giro_materiale_id IS NOT NULL"
    )

    # ----------------------------------------------------------------
    # 2. giro_materiale: drop etichetta (era MR 0016).
    # ----------------------------------------------------------------
    op.execute(
        "ALTER TABLE giro_materiale "
        "DROP CONSTRAINT IF EXISTS giro_materiale_etichetta_tipo_check"
    )
    op.execute("ALTER TABLE giro_materiale DROP COLUMN etichetta_dettaglio")
    op.execute("ALTER TABLE giro_materiale DROP COLUMN etichetta_tipo")

    # ----------------------------------------------------------------
    # 3. giro_giornata: drop campi validità (tornano su variante).
    # ----------------------------------------------------------------
    op.execute("ALTER TABLE giro_giornata DROP COLUMN dates_skip_json")
    op.execute("ALTER TABLE giro_giornata DROP COLUMN dates_apply_json")
    op.execute("ALTER TABLE giro_giornata DROP COLUMN validita_testo")

    # ----------------------------------------------------------------
    # 4. Re-create table giro_variante.
    # ----------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE giro_variante (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            giro_giornata_id BIGINT NOT NULL
                REFERENCES giro_giornata(id) ON DELETE CASCADE,
            variant_index INTEGER NOT NULL DEFAULT 0,
            -- Periodicità testuale del PdE per la prima corsa della
            -- variante (es. "LV 1:5", "F", "Si eff. 21-28/3, 11/4").
            -- Sprint 7.7 MR 5: NULLABLE (può non esserci se la prima
            -- corsa non ha periodicita_breve).
            validita_testo TEXT,
            -- Date in cui questa variante della giornata-tipo si
            -- applica nel periodo del programma. Per costruzione
            -- (clustering A1) è disgiunto dalle altre varianti
            -- della stessa giornata.
            dates_apply_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            -- Date escluse (per gestione "sospeso il NN/MM" in futuro).
            dates_skip_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            UNIQUE(giro_giornata_id, variant_index)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_giro_variante_giornata_id "
        "ON giro_variante(giro_giornata_id)"
    )

    # ----------------------------------------------------------------
    # 5. giro_blocco: rinomina FK giornata → variante.
    # ----------------------------------------------------------------
    op.execute(
        "ALTER TABLE giro_blocco "
        "DROP CONSTRAINT IF EXISTS giro_blocco_giro_giornata_id_seq_key"
    )
    op.execute(
        "ALTER TABLE giro_blocco "
        "ADD COLUMN giro_variante_id BIGINT "
        "REFERENCES giro_variante(id) ON DELETE CASCADE"
    )
    op.execute("ALTER TABLE giro_blocco DROP COLUMN giro_giornata_id")
    op.execute(
        "ALTER TABLE giro_blocco "
        "ALTER COLUMN giro_variante_id SET NOT NULL"
    )
    op.execute(
        "ALTER TABLE giro_blocco "
        "ADD CONSTRAINT giro_blocco_giro_variante_id_seq_key "
        "UNIQUE (giro_variante_id, seq)"
    )


def downgrade() -> None:
    # Rollback verso schema MR 0016/0017 (etichetta giro + validità su
    # giornata, no varianti). Tabelle vuote per costruzione (downgrade
    # richiede rigenerazione giri).

    # giro_blocco: torna a giro_giornata_id
    op.execute(
        "ALTER TABLE giro_blocco "
        "DROP CONSTRAINT IF EXISTS giro_blocco_giro_variante_id_seq_key"
    )
    op.execute(
        "ALTER TABLE giro_blocco "
        "ADD COLUMN giro_giornata_id BIGINT "
        "REFERENCES giro_giornata(id) ON DELETE CASCADE"
    )
    op.execute("ALTER TABLE giro_blocco DROP COLUMN giro_variante_id")
    op.execute(
        "ALTER TABLE giro_blocco "
        "ALTER COLUMN giro_giornata_id SET NOT NULL"
    )
    op.execute(
        "ALTER TABLE giro_blocco "
        "ADD CONSTRAINT giro_blocco_giro_giornata_id_seq_key "
        "UNIQUE (giro_giornata_id, seq)"
    )

    # Drop giro_variante
    op.execute("DROP INDEX IF EXISTS idx_giro_variante_giornata_id")
    op.execute("DROP TABLE giro_variante")

    # giro_giornata: re-add validità
    op.execute("ALTER TABLE giro_giornata ADD COLUMN validita_testo TEXT")
    op.execute(
        "ALTER TABLE giro_giornata "
        "ADD COLUMN dates_apply_json JSONB NOT NULL DEFAULT '[]'::jsonb"
    )
    op.execute(
        "ALTER TABLE giro_giornata "
        "ADD COLUMN dates_skip_json JSONB NOT NULL DEFAULT '[]'::jsonb"
    )

    # giro_materiale: re-add etichetta
    op.execute(
        "ALTER TABLE giro_materiale "
        "ADD COLUMN etichetta_tipo VARCHAR(20) NOT NULL "
        "DEFAULT 'personalizzata'"
    )
    op.execute(
        "ALTER TABLE giro_materiale "
        "ADD CONSTRAINT giro_materiale_etichetta_tipo_check "
        "CHECK (etichetta_tipo IN ("
        "'feriale', 'sabato', 'domenica', 'festivo', "
        "'data_specifica', 'personalizzata'"
        "))"
    )
    op.execute("ALTER TABLE giro_materiale ADD COLUMN etichetta_dettaglio TEXT")
