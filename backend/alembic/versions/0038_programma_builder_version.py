"""0038 — programma_materiale.builder_version (MR-1110 sotto-MR 10).

MR-1110 sotto-MR 10 (Sprint 8.0, entry 206). Aggiunge
``programma_materiale.builder_version`` (String(5), NOT NULL,
default ``"v1"``).

**Semantica**:

- ``"v1"`` (default, retrocompat) = pipeline builder legacy
  (``costruisci_giri_multigiornata`` + fusione cluster A1 di Sprint
  7.9 MR 12). Usato da tutti i programmi pre-merge.
- ``"v2"`` = pipeline ``costruisci_turni_v2`` (entry 202):
  catene-istanza → giornate-tipo → varianti calendariali → turni
  concatenati ciclicamente. Modello PDF Trenord turno 1134.

**CHECK constraint**: il campo accetta solo ``"v1"`` o ``"v2"``.
Tentativi di set ad altri valori falliscono al COMMIT.

**Backward compat**: programmi esistenti ricevono ``"v1"`` via
``server_default``, nessuna logica esistente si rompe. Il routing
nel ``builder.py::genera_giri`` controlla ``programma.builder_version``
per scegliere quale pipeline invocare. Decisione utente 2026-05-06:
"chiudi sotto-MR 7/8/10".

Revision ID: f6a1b2c3d4e5
Revises: e5f6a1b2c3d4 (0037)
Create Date: 2026-05-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6a1b2c3d4e5"
down_revision: str | None = "e5f6a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "programma_materiale",
        sa.Column(
            "builder_version",
            sa.String(5),
            nullable=False,
            server_default="v1",
            comment=(
                "MR-1110 sotto-MR 10: pipeline builder selezionata. "
                "'v1' = legacy multi_giornata + fusione cluster A1 "
                "(Sprint 7.9 MR 12). 'v2' = costruisci_turni_v2 "
                "(entry 202). Default 'v1' retrocompat. Sprint 8.0 "
                "entry 206."
            ),
        ),
    )
    op.create_check_constraint(
        "programma_materiale_builder_version_check",
        "programma_materiale",
        "builder_version IN ('v1', 'v2')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "programma_materiale_builder_version_check",
        "programma_materiale",
        type_="check",
    )
    op.drop_column("programma_materiale", "builder_version")
