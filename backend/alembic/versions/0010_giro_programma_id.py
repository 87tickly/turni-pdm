"""0010 giro programma_id — Sprint 7.3 fix

Aggiunge colonna esplicita ``giro_materiale.programma_id`` con FK a
``programma_materiale``. Backfilla dai dati esistenti
(``generation_metadata_json->>'programma_id'``).

**Motivazione**: il vincolo UNIQUE precedente
``(azienda_id, numero_turno)`` impediva a due programmi diversi della
stessa azienda di avere ognuno il proprio giro ``G-FIO-001``. Il
persister generava ``G-{LOC}-{NNN}`` ripartendo da 001 per programma,
quindi una rigenerazione di un secondo programma falliva con
``UniqueViolation``.

**Fix**: includere ``programma_id`` nella chiave unica. Ogni programma
ha la sua serie di giri indipendente. La numerazione utente
``G-FIO-001`` resta familiare; la disambiguazione è interna.

**Pre-requisiti**: tutti i 41 giri esistenti hanno
``generation_metadata_json->>'programma_id'`` valorizzato (verificato
in fase di sviluppo migration). Il backfill è quindi safe.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "f4c2d8a91b07"
down_revision: str | None = "e3b1c8f47a92"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add column nullable (per backfill)
    op.add_column(
        "giro_materiale",
        sa.Column("programma_id", sa.BigInteger(), nullable=True),
    )

    # 2. Backfill dai metadata
    op.execute(
        """
        UPDATE giro_materiale
        SET programma_id = (generation_metadata_json->>'programma_id')::bigint
        WHERE generation_metadata_json ? 'programma_id'
        """
    )

    # 3. Verifica nessun NULL residuo, poi ALTER NOT NULL
    op.execute(
        """
        DO $$
        DECLARE n_null int;
        BEGIN
          SELECT COUNT(*) INTO n_null FROM giro_materiale WHERE programma_id IS NULL;
          IF n_null > 0 THEN
            RAISE EXCEPTION 'Migration 0010: % giri senza programma_id, abortire', n_null;
          END IF;
        END$$;
        """
    )
    op.alter_column("giro_materiale", "programma_id", nullable=False)

    # 4. FK + indice
    op.create_foreign_key(
        "giro_materiale_programma_id_fkey",
        "giro_materiale",
        "programma_materiale",
        ["programma_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "idx_giro_materiale_programma_id",
        "giro_materiale",
        ["programma_id"],
    )

    # 5. Sostituisci UNIQUE constraint:
    # vecchio: (azienda_id, numero_turno) → blocca cross-programma
    # nuovo: (azienda_id, programma_id, numero_turno)
    op.drop_constraint(
        "giro_materiale_azienda_id_numero_turno_key",
        "giro_materiale",
        type_="unique",
    )
    op.create_unique_constraint(
        "giro_materiale_azienda_programma_turno_key",
        "giro_materiale",
        ["azienda_id", "programma_id", "numero_turno"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "giro_materiale_azienda_programma_turno_key",
        "giro_materiale",
        type_="unique",
    )
    op.create_unique_constraint(
        "giro_materiale_azienda_id_numero_turno_key",
        "giro_materiale",
        ["azienda_id", "numero_turno"],
    )
    op.drop_index("idx_giro_materiale_programma_id", table_name="giro_materiale")
    op.drop_constraint(
        "giro_materiale_programma_id_fkey", "giro_materiale", type_="foreignkey"
    )
    op.drop_column("giro_materiale", "programma_id")
