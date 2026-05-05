"""0033 — copertura_pct su programma_materiale (gating conferma-personale).

Sub-MR 2.bis-c (Sprint 8.0). Aggiunge colonna nullable
``programma_materiale.copertura_pct`` (Float, 0..100) popolata dal
side-effect dell'endpoint ``POST /api/programmi/{id}/auto-assegna-persone``
(sub-MR 2.bis-a, entry 172) ad ogni run.

L'endpoint ``POST /api/programmi/{id}/conferma-personale`` userà
questo valore per gating: 409 se ``copertura_pct < SOGLIA_COPERTURA_PCT``
(default 95.0%, configurabile via env ``AUTO_ASSEGNA_SOGLIA_COPERTURA_PCT``).

NULL semantica: nessun run di auto-assegna effettuato → conferma-personale
ritorna 409 con messaggio "esegui prima auto-assegna".

L'endpoint ``assegna-manuale`` (sub-MR 2.bis-b, entry 173) NON aggiorna
questo campo: limitazione dichiarata, l'utente deve ri-runnare
auto-assegna per aggiornare il KPI dopo override.

Revision ID: a1b2c3d4e5f6
Revises: f0a1b2c3d4e5 (0032)
Create Date: 2026-05-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f0a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "programma_materiale",
        sa.Column(
            "copertura_pct",
            sa.Float(),
            nullable=True,
            comment=(
                "Sub-MR 2.bis-c: % copertura ultima run auto-assegna. "
                "NULL = nessun run effettuato. Range 0..100. "
                "Gating su conferma-personale: 409 se < 95.0."
            ),
        ),
    )
    op.create_check_constraint(
        "programma_materiale_copertura_pct_range",
        "programma_materiale",
        "copertura_pct IS NULL OR (copertura_pct >= 0 AND copertura_pct <= 100)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "programma_materiale_copertura_pct_range",
        "programma_materiale",
        type_="check",
    )
    op.drop_column("programma_materiale", "copertura_pct")
