"""0042 — programma_materiale.builder_mode default 'esplorativo' (Sprint 8.1 MR-A8).

MR-A8 dello Sprint 8.1 (entry 251, 2026-05-09): switch default
`builder_mode` da ``'rigido'`` a ``'esplorativo'`` post-validazione A7
con fix HIGH-1 SEVERO (MR-A3-quater).

**Semantica**:

- Solo lo `server_default` cambia: nuovi programmi creati senza valore
  esplicito ricevono `'esplorativo'`. Programmi esistenti DB **non
  cambiano** (server_default applica solo a INSERT senza valore).
- Per ripristinare il default legacy (es. rollback), eseguire
  `alembic downgrade 0042 → b1c2d3e4f5a6`.

**Validazione A7 (entry 251)**:
- Prog 17 (1 regola ETR522 FIO 3 direttrici): sotto-min 52.2%→8.1% (-75%)
- Prog 16 (8 regole multi-sede): sotto-min 32.8%→4.4% (-81%)
- Pool perimetro pulito (HIGH-1 SEVERO chiuso da MR-A3-quater):
  Tier 1 fallback attivato SOLO quando Tier 0 è VUOTO.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-05-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Solo server_default: i programmi esistenti non cambiano
    # (UPDATE esplicito non eseguito per preservare scelta utente
    # storica). Solo INSERT futuri senza valore ricevono 'esplorativo'.
    op.alter_column(
        "programma_materiale",
        "builder_mode",
        server_default="esplorativo",
        existing_type=sa.String(20),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "programma_materiale",
        "builder_mode",
        server_default="rigido",
        existing_type=sa.String(20),
        existing_nullable=False,
    )
