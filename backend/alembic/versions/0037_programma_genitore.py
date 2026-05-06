"""0037 — programma_genitore_id su programma_materiale (sub-MR 5.bis-fork).

Sub-MR 5.bis-fork (Sprint 8.0 follow-up, entry 190). Aggiunge
``programma_materiale.programma_genitore_id`` (BigInteger nullable,
FK self-reference SET NULL).

**Semantica**:

- ``NULL`` = programma "base" autonomo (default, retrocompat per
  tutti i programmi esistenti).
- ``int`` = programma "figlio" creato come fork da una variazione
  PdE applicata. Il programma figlio prevale sul genitore per le
  date all'interno del proprio ``valido_da..valido_a``.

**Convenzione "merge per data"** (documentata, NON applicata in
questo MR ai consumer): per ogni data X richiesta da un consumer
(vista PdC finale, builder, assegnazioni), si sceglie il programma
con il ``valido_da..valido_a`` più stretto che include X. Quando
multipli figli si sovrappongono, deterministico per ``id`` minimo
(o ``created_at`` più recente — TBD nel sub-MR successivo).

**ON DELETE SET NULL**: se un programma genitore viene eliminato
(operazione rara, oggi cascading via ``stato='archiviato'``), i
figli restano e diventano "orfani" (autonomi). Più sicuro di CASCADE
che eliminerebbe a catena.

Revision ID: e5f6a1b2c3d4
Revises: d4e5f6a1b2c3 (0036)
Create Date: 2026-05-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a1b2c3d4"
down_revision: str | None = "d4e5f6a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "programma_materiale",
        sa.Column(
            "programma_genitore_id",
            sa.BigInteger(),
            sa.ForeignKey("programma_materiale.id", ondelete="SET NULL"),
            nullable=True,
            comment=(
                "Sub-MR 5.bis-fork: FK self verso il programma genitore di "
                "cui questo è figlio (variazione di periodo). NULL = "
                "programma base autonomo. Sprint 8.0 entry 190."
            ),
        ),
    )
    op.create_index(
        "ix_programma_materiale_genitore",
        "programma_materiale",
        ["programma_genitore_id"],
        postgresql_where=sa.text("programma_genitore_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_programma_materiale_genitore",
        table_name="programma_materiale",
    )
    op.drop_column("programma_materiale", "programma_genitore_id")
