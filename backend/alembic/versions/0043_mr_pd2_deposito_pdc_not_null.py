"""0043 — turno_pdc.deposito_pdc_id NOT NULL + FK ondelete RESTRICT (Sprint 8.2 MR-PD2).

MR-PD2 dello Sprint 8.2 (entry 260, 2026-05-09): chiude la
**Violazione B** dichiarata dall'utente nell'audit
``docs/AUDIT-PDC-NORMATIVA-2026-05-09.md`` ("non associ i turni ai
depositi"). Il modello `TurnoPdc` aveva `deposito_pdc_id` nullable
per backward compat post-Sprint 7.9 MR η; ora diventa **obbligatorio**
in linea con NORMATIVA-PDC §2.3 ("ogni PdC appartiene a uno dei 25
depositi"), prerequisito del builder deposito-first di MR-PD3.

**Operazioni**:

1. **Backfill destructive** (greenfield, dati MVP rigenerabili):
   ``DELETE FROM turno_pdc WHERE deposito_pdc_id IS NULL``.
   Sono leftover Sprint 7.2 pre-MR η, verranno rigenerati dal nuovo
   builder deposito-first (MR-PD3). Nessun dato utente perduto: i
   turni `bozza` non hanno valore semantico oltre il debug.
2. ``ALTER COLUMN deposito_pdc_id SET NOT NULL``.
3. **FK ondelete: SET NULL → RESTRICT**. Con NOT NULL + SET NULL un
   ipotetico DELETE su depot fallirebbe a runtime con errore
   "null value violates not-null constraint". Più semantico:
   RESTRICT impedisce esplicitamente la cancellazione di un depot
   che ha turni associati.

**Rollback**: rimuove vincolo NOT NULL e ripristina FK ondelete
SET NULL. Non re-inserisce i turni eventualmente cancellati nello
upgrade (irreversibile).

Revision ID: e3f4a5b6c7d8
Revises: c2d3e4f5a6b7
Create Date: 2026-05-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e3f4a5b6c7d8"
down_revision: str | None = "c2d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_FK_NAME = "turno_pdc_deposito_pdc_id_fkey"


def upgrade() -> None:
    # 1. Backfill destructive: rimuovi turni orfani prima del NOT NULL.
    # Greenfield, dati MVP rigenerabili dal nuovo builder MR-PD3.
    op.execute(
        "DELETE FROM turno_pdc WHERE deposito_pdc_id IS NULL"
    )

    # 2. Drop FK esistente (ondelete=SET NULL).
    op.drop_constraint(_FK_NAME, "turno_pdc", type_="foreignkey")

    # 3. Set NOT NULL.
    op.alter_column(
        "turno_pdc",
        "deposito_pdc_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )

    # 4. Re-create FK con ondelete=RESTRICT.
    op.create_foreign_key(
        _FK_NAME,
        "turno_pdc",
        "depot",
        ["deposito_pdc_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    # Inverso: drop FK RESTRICT, allenta NOT NULL, ricrea FK SET NULL.
    op.drop_constraint(_FK_NAME, "turno_pdc", type_="foreignkey")

    op.alter_column(
        "turno_pdc",
        "deposito_pdc_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )

    op.create_foreign_key(
        _FK_NAME,
        "turno_pdc",
        "depot",
        ["deposito_pdc_id"],
        ["id"],
        ondelete="SET NULL",
    )
