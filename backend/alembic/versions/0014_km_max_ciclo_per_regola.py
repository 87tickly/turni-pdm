"""0014 — km_max_ciclo per regola (Sprint 7.7 MR 1)

Aggiunge la colonna ``km_max_ciclo INT NULL`` a
``programma_regola_assegnazione``. Lo scope del cap si sposta da
"per programma" (oggi `programma_materiale.km_max_ciclo`) a
"per regola/materiale": ogni materiale ha autonomie diverse
(ETR526 ~4500 km/ciclo, E464 ~6000, ATR803 diverso ancora).

Decisione utente 2026-05-02 (memoria
``project_km_cap_per_regola_TODO.md``):

> "il km max per ciclo va inserito sotto il materiale no all'inizio
> della creazione del turno materiale"

> "se non viene inserito dobbiamo considerare che in media un treno
> al giorno fa circa 700/1000 km"

Il cap effettivo nel builder diventa:

    cap_effettivo = (regola.km_max_ciclo
                     OR programma.km_max_ciclo  # legacy
                     OR DEFAULT_KM_MEDIO_GIORNALIERO * n_giornate_safety)

Backward compat: la colonna `programma_materiale.km_max_ciclo` resta
(deprecata) per non rompere programmi esistenti. Il refactor builder
(MR 7.7.1) la usa come fallback se la regola non ha cap.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "d2a8f17bc94e"
down_revision: str | None = "c1f5d932b8a2"  # 0013_km_giornata
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "programma_regola_assegnazione",
        sa.Column("km_max_ciclo", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("programma_regola_assegnazione", "km_max_ciclo")
