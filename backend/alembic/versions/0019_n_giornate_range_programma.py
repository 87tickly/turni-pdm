"""0019 — n_giornate_min / n_giornate_max su programma_materiale (Sprint 7.8)

Aggiunge il range `[n_giornate_min, n_giornate_max]` a
``programma_materiale``. Il builder lo userà come **soft cap inferiore**
e **hard cap superiore** sulla lunghezza dei giri generati.

Decisione utente 2026-05-03:

> "non è che tutte le giornate sono 8 possiamo mettere un minimo di
> partenza fino a un max di 12, eccezion fatta quando dobbiamo chiudere
> i treni che potrebbe capitare che escano solo 2 giornate o cose simili"

Default scelti dal pianificatore (chat 2026-05-03):

- ``n_giornate_min = 4`` (soft: il builder può scendere sotto SOLO per
  i giri "di chiusura" delle corse rimaste a fine pool)
- ``n_giornate_max = 12`` (hard: nessun giro può superare 12 giornate)

Vincolo: ``n_giornate_max >= n_giornate_min >= 1``.

Backward compat: campi NOT NULL con default lato DB → tutti i programmi
esistenti ricevono ``min=4, max=12`` automaticamente alla migrazione.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "e7a2c5b91f4d"
down_revision: str | None = "b6f9c4a82dd1"  # 0018_varianti_per_giornata
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "programma_materiale",
        sa.Column(
            "n_giornate_min",
            sa.Integer(),
            nullable=False,
            server_default="4",
        ),
    )
    op.add_column(
        "programma_materiale",
        sa.Column(
            "n_giornate_max",
            sa.Integer(),
            nullable=False,
            server_default="12",
        ),
    )
    op.create_check_constraint(
        "programma_n_giornate_min_check",
        "programma_materiale",
        "n_giornate_min >= 1",
    )
    op.create_check_constraint(
        "programma_n_giornate_max_check",
        "programma_materiale",
        "n_giornate_max >= n_giornate_min",
    )


def downgrade() -> None:
    op.drop_constraint(
        "programma_n_giornate_max_check",
        "programma_materiale",
        type_="check",
    )
    op.drop_constraint(
        "programma_n_giornate_min_check",
        "programma_materiale",
        type_="check",
    )
    op.drop_column("programma_materiale", "n_giornate_max")
    op.drop_column("programma_materiale", "n_giornate_min")
