"""0008 stazioni sosta extra — Sprint 5.6 (smoke v4)

Aggiunge `programma_materiale.stazioni_sosta_extra_json JSONB`:
lista codici stazione PdE (es. `["S01440", "S01430"]`) ammessi come
**sosta notturna del materiale**, oltre alla whitelist sede.

La lista finale `stazioni_sosta_ammesse` del builder = whitelist sede ∪
stazioni del campo `stazione_principale_codice` dei depot PdC ∪
`stazioni_sosta_extra_json` del programma.

Decisione utente 2026-04-28 (vedi memoria persistente
`project_chiusura_giro_dinamica.md` e
`project_stazioni_sosta_da_depositi_pdc.md`): la stazione di chiusura
giornata di un giro multi-giornata DEVE essere in
`stazioni_sosta_ammesse`, mai altrove.

Default: `[]` (nessuna sosta extra → solo depot PdC + whitelist sede).
NOT NULL.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "d8a91f2b3c47"
down_revision: str | None = "c4e7f3a92d68"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "programma_materiale",
        sa.Column(
            "stazioni_sosta_extra_json",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("programma_materiale", "stazioni_sosta_extra_json")
