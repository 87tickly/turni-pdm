"""0046 — turno_pdc_blocco.numero_treno_vettura nullable (Sprint 8.2 MR-PD-FIX-SEVERO 3b A1).

Aggiunge campo dedicato per il numero del treno commerciale usato come
VETTURA rientro al deposito. Sostituisce il pattern (anti-pattern)
precedente di scrivere il numero solo dentro ``accessori_note`` testuale,
che richiedeva regex parsing fragile (SEVERO finding S1 entry critica
SPRINT-8.2-MR-PD-FIX-SEVERO-3b-PIANO.md).

Il campo è nullable perché:
- I blocchi non-VETTURA (CONDOTTA, REFEZ, ACCp, MM, VOCTAXI, ecc.) NON
  hanno un numero treno vettura.
- I blocchi VETTURA storici (pre-MR-PD-FIX-SEVERO 3b) non popolano il
  campo: il `RegistroVettureAssegnate.from_db` MVP usa wild card match
  per backfill graduale (turni futuri popolano, vecchi sono "ignoti").

Operazioni:
1. ADD COLUMN ``numero_treno_vettura VARCHAR(20) NULL``.
2. INDEX ``ix_turno_pdc_blocco_numero_treno_vettura`` per lookup veloce
   nel registro (query frequente: ``SELECT numero_treno_vettura FROM
   turno_pdc_blocco WHERE tipo_evento = 'VETTURA' AND
   numero_treno_vettura IS NOT NULL``).

Rollback: DROP INDEX + DROP COLUMN.

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-05-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: str | None = "a6b7c8d9e0f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "turno_pdc_blocco",
        sa.Column("numero_treno_vettura", sa.String(length=20), nullable=True),
    )
    op.create_index(
        "ix_turno_pdc_blocco_numero_treno_vettura",
        "turno_pdc_blocco",
        ["numero_treno_vettura"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_turno_pdc_blocco_numero_treno_vettura",
        table_name="turno_pdc_blocco",
    )
    op.drop_column("turno_pdc_blocco", "numero_treno_vettura")
