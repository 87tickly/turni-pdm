"""0039 — programma_materiale: max_sosta_diurna_min + min_servizio_giornata_pct (MR-4).

Sprint 8.0 MR-4 (entry 224). Aggiunge 2 vincoli configurabili per
programma:

- ``max_sosta_diurna_min INTEGER NULL``: minuti diurni MAX di sosta
  intergiornata (fuori 22:00-06:00). ``NULL`` = disattivato. Tipico 300.
- ``min_servizio_giornata_pct INTEGER NULL``: percentuale MINIMA di
  servizio richiesta per ogni giornata. ``NULL`` = disattivato. Tipico 30.

Decisione utente entry 224: dopo che entry 222 ha provato a forzare
5h diurni come default globale (rollback in entry 223), l'utente ha
chiesto di rendere il vincolo **configurabile per programma** + un
secondo vincolo "% servizio giornata" per intercettare giornate
sottoutilizzate (es. G1 ETR421 con 1h32 di servizio in 24h = 6%).

Entrambi i campi sono ``NULL`` per default → nessuna logica esistente
si rompe. Il pianificatore attiva esplicitamente i vincoli nei
programmi che vuole.

Revision ID: a1b2c3d4e5f6
Revises: f6a1b2c3d4e5 (0038)
Create Date: 2026-05-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f6a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "programma_materiale",
        sa.Column(
            "max_sosta_diurna_min",
            sa.Integer(),
            nullable=True,
            comment=(
                "Sprint 8.0 MR-4 (entry 224): minuti diurni MAX di sosta "
                "intergiornata, fuori dalla fascia 22:00-06:00. NULL = "
                "vincolo disattivato. Tipico 300 (5h). Verificato dal "
                "builder via _minuti_diurni_sosta_intergiornata."
            ),
        ),
    )
    op.add_column(
        "programma_materiale",
        sa.Column(
            "min_servizio_giornata_pct",
            sa.Integer(),
            nullable=True,
            comment=(
                "Sprint 8.0 MR-4 (entry 224): percentuale MINIMA di "
                "servizio richiesta per ogni giornata di un giro. "
                "Calcolata come somma_minuti_corse / 1440 × 100. "
                "Giornate sottoutilizzate causano chiusura giro. NULL = "
                "disattivato. Tipico 30 (= 30% di un giorno)."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("programma_materiale", "min_servizio_giornata_pct")
    op.drop_column("programma_materiale", "max_sosta_diurna_min")
