"""0044 — programma_materiale.builder_mode CHECK include 'linea_centrica' (Sprint 8.2 MR-D5b).

Sprint 8.2 Plan-D MR-D5b (entry 264): aggiunge ``'linea_centrica'``
ai valori ammessi del CHECK constraint
``programma_materiale_builder_mode_check`` (introdotto in 0041 MR-A1).

Pattern: DROP CONSTRAINT esistente + CREATE CONSTRAINT con 3 valori.

**Backward compat**: i programmi esistenti con
``builder_mode IN ('rigido', 'esplorativo')`` non sono toccati. Il
nuovo valore ``'linea_centrica'`` è opt-in via PATCH
``/api/programmi/{id}`` o creazione esplicita.

**Schema invariato**: la colonna è già ``String(20)`` (12 char per
``"linea_centrica"`` rientra). Nessun ALTER TYPE necessario.

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-05-09 23:00:00
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "f4a5b6c7d8e9"
down_revision = "e3f4a5b6c7d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "programma_materiale_builder_mode_check",
        "programma_materiale",
        type_="check",
    )
    op.create_check_constraint(
        "programma_materiale_builder_mode_check",
        "programma_materiale",
        "builder_mode IN ('rigido', 'esplorativo', 'linea_centrica')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "programma_materiale_builder_mode_check",
        "programma_materiale",
        type_="check",
    )
    op.create_check_constraint(
        "programma_materiale_builder_mode_check",
        "programma_materiale",
        "builder_mode IN ('rigido', 'esplorativo')",
    )
