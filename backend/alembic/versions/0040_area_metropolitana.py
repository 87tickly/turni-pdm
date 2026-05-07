"""0040 area_metropolitana — whitelist stazioni intra-area

Sprint 8.0 MR-E entry 236: introduce il concetto di AREA METROPOLITANA
per permettere al builder di concatenare corse tra stazioni vicine
della stessa città (es. Milano Centrale ↔ Milano Garibaldi). Risolve
il problema dei turni mono-corsa che non riescono ad agganciarsi
perché la corsa successiva parte da una stazione diversa della stessa
area metropolitana.

Decisione utente entry 234: "risolvi il problema". Vincolo: NO vuoti
fake tra città diverse, ma SI vuoti intra-area.

Tabelle:
- ``area_metropolitana``: identità area (codice univoco, nome, azienda).
- ``area_stazione_membri``: M:N stazione-area (PK composito).

Niente seed automatico nelle membership: il seed è azienda-specifico
e richiede stazioni del PdE già importate. L'admin popola tramite
endpoint dedicato dopo l'import PdE.

Revision ID: aa01b2c3d4e5
Revises: 0c4f8a3b1e29
Create Date: 2026-05-07 21:00:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "aa01b2c3d4e5"
down_revision: str | None = "0c4f8a3b1e29"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "area_metropolitana",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "azienda_id",
            sa.BigInteger(),
            sa.ForeignKey("azienda.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("codice", sa.String(50), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column(
            "gap_intra_area_min",
            sa.Integer(),
            nullable=False,
            server_default="10",
            comment=(
                "Minuti del vuoto tecnico generato automaticamente quando "
                "il builder concatena 2 corse di stazioni diverse della "
                "stessa area. Default 10 min (tipico Milano)."
            ),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "azienda_id", "codice", name="uq_area_metropolitana_azienda_codice"
        ),
    )

    op.create_table(
        "area_stazione_membri",
        sa.Column(
            "area_id",
            sa.BigInteger(),
            sa.ForeignKey("area_metropolitana.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "stazione_codice",
            sa.String(20),
            sa.ForeignKey("stazione.codice", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    # Index inverso per lookup veloce "data stazione, dimmi le sue aree".
    op.create_index(
        "ix_area_stazione_membri_stazione",
        "area_stazione_membri",
        ["stazione_codice"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_area_stazione_membri_stazione", table_name="area_stazione_membri"
    )
    op.drop_table("area_stazione_membri")
    op.drop_table("area_metropolitana")
