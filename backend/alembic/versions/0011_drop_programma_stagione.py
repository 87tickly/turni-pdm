"""0011 drop programma_materiale.stagione — Sprint 7.3 fix

Rimuove il campo cosmetico ``stagione`` da ``programma_materiale``.
Il filtro temporale delle corse è ora interamente data-driven via
``corsa_commerciale.valido_in_date_json`` intersecato con
``[programma.valido_da, programma.valido_a]``.

Le 3 stagioni (``invernale/estiva/agosto``) restano valide solo a
livello di ``corsa_composizione.stagione`` (composizione-tipo del
materiale per stagione, dato strutturale del PdE).

**Idempotente al downgrade**: il downgrade ricrea la colonna
nullable senza ripopolarla (il dato è perso). Non è un problema in
pratica perché il sistema non lo legge più.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "a8d3c5f97e21"
down_revision: str | None = "f4c2d8a91b07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("programma_materiale", "stagione")


def downgrade() -> None:
    op.add_column(
        "programma_materiale",
        sa.Column("stagione", sa.String(length=20), nullable=True),
    )
