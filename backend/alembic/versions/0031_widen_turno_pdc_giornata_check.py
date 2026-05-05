"""Sprint 7.10 MR α.4.fix: allarga il check constraint su
turno_pdc_giornata.numero_giornata da 1-14 a 1-50.

Bug runtime smoke MR α.4 (entry 154):
``IntegrityError: turno_pdc_giornata_numero_giornata_check`` con
`numero_giornata: 15`. Il constraint storico (migration 0001
``CHECK (numero_giornata BETWEEN 1 AND 14)``) era pensato per turni
PdC con ciclo 1-2 settimane. Con l'accorpamento per deposito
introdotto da MR α.4 (e ancor di più con MR α.6 fill multi-giro
futuro), un singolo TurnoPdc può facilmente avere >14 giornate
sequenziali → l'INSERT fallisce.

50 è una stima generosa: copre cicli mensili (28-30gg) + margine
per casi multi-giro densi. Se in futuro serve di più, alziamo
ulteriormente.
"""

from __future__ import annotations

from alembic import op

# revision identifiers
revision: str = "e9f0a1b2c3d4"
down_revision: str | None = "d8e9f0a1b2c3"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE turno_pdc_giornata
        DROP CONSTRAINT IF EXISTS turno_pdc_giornata_numero_giornata_check
        """
    )
    op.execute(
        """
        ALTER TABLE turno_pdc_giornata
        ADD CONSTRAINT turno_pdc_giornata_numero_giornata_check
        CHECK (numero_giornata BETWEEN 1 AND 50)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE turno_pdc_giornata
        DROP CONSTRAINT IF EXISTS turno_pdc_giornata_numero_giornata_check
        """
    )
    op.execute(
        """
        ALTER TABLE turno_pdc_giornata
        ADD CONSTRAINT turno_pdc_giornata_numero_giornata_check
        CHECK (numero_giornata BETWEEN 1 AND 14)
        """
    )
