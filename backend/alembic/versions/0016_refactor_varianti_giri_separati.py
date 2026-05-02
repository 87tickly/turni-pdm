"""0016 — Refactor varianti → giri separati con etichetta (Sprint 7.7 MR 3)

Drop tabella `giro_variante` (modello obsoleto: N varianti calendario
per giornata risulta illeggibile per il pianificatore — cfr. memoria
``project_refactor_varianti_giri_separati_TODO.md`` 2026-05-02).
Sposta i campi di validità su `giro_giornata` (1 giornata = 1 sequenza
canonica). Aggiunge l'etichetta calcolata sul giro materiale.

Modello target:

- ``giro_materiale.etichetta_tipo`` enum
  ``feriale | sabato | domenica | festivo | data_specifica | personalizzata``
  — calcolato dal builder dalle date di applicazione del giro.
- ``giro_materiale.etichetta_dettaglio`` text NULL — leggibile per
  ``data_specifica`` (DD/MM/YYYY) o ``personalizzata`` (breakdown).
- ``giro_giornata.validita_testo`` text NULL — periodicita_breve PdE
  della prima corsa (era su giro_variante).
- ``giro_giornata.dates_apply_json`` jsonb — date in cui la giornata-
  tipo si applica (era ``validita_dates_apply_json`` su giro_variante).
- ``giro_giornata.dates_skip_json`` jsonb — date escluse.
- ``giro_blocco.giro_giornata_id`` (era ``giro_variante_id``).

Wipe pre-migration: l'utente ha esplicitamente concordato di
rigenerare i giri da zero (decisione 2026-05-02 — "li generiamo da
zero, sono solo prove"). Niente backfill: ``DELETE giro_materiale``
con CASCADE pulisce giornate/varianti/blocchi; i vuoti orfani
vengono eliminati esplicitamente (la FK
``corsa_materiale_vuoto.giro_materiale_id`` non è CASCADE).
"""

from __future__ import annotations

from alembic import op

revision: str = "f7c2b189e405"
down_revision: str | None = "e3b9a046f218"  # 0015_festivita_ufficiale
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ----------------------------------------------------------------
    # 1. Wipe giri esistenti — decisione utente 2026-05-02:
    #    "li generiamo da zero, sono solo prove".
    #    Ordine FK-safe (stesso pattern di
    #    ``builder.py:_wipe_giri_programma``):
    #    a. DELETE giro_materiale → CASCADE pulisce giornate/varianti/
    #       blocchi e libera la FK RESTRICT
    #       ``giro_blocco.corsa_materiale_vuoto_id``.
    #    b. DELETE corsa_materiale_vuoto orfane (hanno
    #       giro_materiale_id valorizzato ma il giro non c'è più).
    # ----------------------------------------------------------------
    op.execute("DELETE FROM giro_materiale")
    op.execute(
        "DELETE FROM corsa_materiale_vuoto WHERE giro_materiale_id IS NOT NULL"
    )

    # ----------------------------------------------------------------
    # 2. giro_materiale: etichetta calcolata dal builder
    # ----------------------------------------------------------------
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
    op.execute(
        "ALTER TABLE giro_materiale ADD COLUMN etichetta_dettaglio TEXT"
    )

    # ----------------------------------------------------------------
    # 3. giro_giornata: assorbe i campi validità (erano su giro_variante)
    # ----------------------------------------------------------------
    op.execute(
        "ALTER TABLE giro_giornata ADD COLUMN validita_testo TEXT"
    )
    op.execute(
        "ALTER TABLE giro_giornata "
        "ADD COLUMN dates_apply_json JSONB NOT NULL DEFAULT '[]'::jsonb"
    )
    op.execute(
        "ALTER TABLE giro_giornata "
        "ADD COLUMN dates_skip_json JSONB NOT NULL DEFAULT '[]'::jsonb"
    )

    # ----------------------------------------------------------------
    # 4. giro_blocco: rinomina la FK giro_variante_id → giro_giornata_id
    #    Tabella vuota dopo il wipe → posso ricreare la colonna NOT NULL
    #    senza backfill.
    # ----------------------------------------------------------------
    # Drop UNIQUE(giro_variante_id, seq) — auto-named dal CREATE TABLE
    # in 0001 come `giro_blocco_giro_variante_id_seq_key`.
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

    # ----------------------------------------------------------------
    # 5. DROP TABLE giro_variante
    # ----------------------------------------------------------------
    op.execute("DROP TABLE giro_variante")


def downgrade() -> None:
    # Re-create giro_variante (vuota — il rollback richiede rigenerazione
    # dei giri).
    op.execute(
        """
        CREATE TABLE giro_variante (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            giro_giornata_id BIGINT NOT NULL
                REFERENCES giro_giornata(id) ON DELETE CASCADE,
            variant_index INTEGER NOT NULL DEFAULT 0,
            validita_testo TEXT NOT NULL DEFAULT 'GG',
            validita_dates_apply_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            validita_dates_skip_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            UNIQUE(giro_giornata_id, variant_index)
        )
        """
    )

    # giro_blocco torna a giro_variante_id (tabella vuota in downgrade).
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

    # giro_giornata
    op.execute("ALTER TABLE giro_giornata DROP COLUMN dates_skip_json")
    op.execute("ALTER TABLE giro_giornata DROP COLUMN dates_apply_json")
    op.execute("ALTER TABLE giro_giornata DROP COLUMN validita_testo")

    # giro_materiale
    op.execute(
        "ALTER TABLE giro_materiale "
        "DROP CONSTRAINT IF EXISTS giro_materiale_etichetta_tipo_check"
    )
    op.execute("ALTER TABLE giro_materiale DROP COLUMN etichetta_dettaglio")
    op.execute("ALTER TABLE giro_materiale DROP COLUMN etichetta_tipo")
