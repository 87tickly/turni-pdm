"""0009 dormita pdc — Sprint 7.2

Aggiunge `'DORMITA'` ai tipi ammessi di `turno_pdc_blocco.tipo_evento`.

Motivo: il builder MVP turno PdC genera blocchi DORMITA per
rappresentare i pernottamenti Fuori Residenza (FR) tra due giornate
consecutive che terminano/iniziano in una stazione diversa dal
deposito sede.

Tipi finali ammessi:
CONDOTTA, VETTURA, REFEZ, ACCp, ACCa, CVp, CVa, PK, SCOMP, PRESA,
FINE, **DORMITA**.
"""

from __future__ import annotations

from alembic import op

revision: str = "e3b1c8f47a92"
down_revision: str | None = "d8a91f2b3c47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE turno_pdc_blocco DROP CONSTRAINT turno_pdc_blocco_tipo_check")
    op.execute(
        """
        ALTER TABLE turno_pdc_blocco
        ADD CONSTRAINT turno_pdc_blocco_tipo_check
        CHECK (tipo_evento IN (
            'CONDOTTA', 'VETTURA', 'REFEZ', 'ACCp', 'ACCa',
            'CVp', 'CVa', 'PK', 'SCOMP', 'PRESA', 'FINE',
            'DORMITA'
        ))
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE turno_pdc_blocco DROP CONSTRAINT turno_pdc_blocco_tipo_check")
    op.execute(
        """
        ALTER TABLE turno_pdc_blocco
        ADD CONSTRAINT turno_pdc_blocco_tipo_check
        CHECK (tipo_evento IN (
            'CONDOTTA', 'VETTURA', 'REFEZ', 'ACCp', 'ACCa',
            'CVp', 'CVa', 'PK', 'SCOMP', 'PRESA', 'FINE'
        ))
        """
    )
