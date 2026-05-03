"""0020 — materiale_dotazione_azienda (Sprint 7.9 MR 7D)

Tabella anagrafica per il numero di pezzi singoli in dotazione fisica
a ciascuna azienda per ogni tipo di materiale rotabile. Vincolo di
capacity per il builder: un programma non può richiedere più convogli
del materiale disponibile.

Decisione utente 2026-05-03 (memoria
``project_dotazione_trenord.md``): Trenord ha 333 pezzi totali
(ETR522×71, ETR421×44, ALe711/710×60, ETR204×35, ATR803×20,
ATR125×15, E464×18, ETR425×18, ETR245×12, ETR526×11, ETR103×10,
ETR104×8, ATR115×6, ETR521×5) + ETR524 FLIRT TILO (numero
non specificato → ``pezzi_disponibili = NULL`` = capacity illimitata
per quei turni).

Schema:

- ``azienda_id BIGINT NOT NULL FK azienda(id) ON DELETE CASCADE``
- ``materiale_codice VARCHAR(50) NOT NULL FK materiale_tipo(codice)
  ON DELETE RESTRICT``
- ``pezzi_disponibili INT NULL`` — NULL = "capacity illimitata"
  (es. FLIRT TILO copre tutti i turni TILO).
- ``note TEXT NULL``
- ``created_at TIMESTAMPTZ NOT NULL DEFAULT now()``
- ``updated_at TIMESTAMPTZ NOT NULL DEFAULT now()``

PK composta: ``(azienda_id, materiale_codice)``.
Check: ``pezzi_disponibili IS NULL OR pezzi_disponibili >= 0``.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "f3b8c1e29a47"
down_revision: str | None = "e7a2c5b91f4d"  # 0019_n_giornate_range_programma
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "materiale_dotazione_azienda",
        sa.Column("azienda_id", sa.BigInteger(), nullable=False),
        sa.Column("materiale_codice", sa.String(50), nullable=False),
        sa.Column("pezzi_disponibili", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("azienda_id", "materiale_codice"),
        sa.ForeignKeyConstraint(
            ["azienda_id"], ["azienda.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["materiale_codice"],
            ["materiale_tipo.codice"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "pezzi_disponibili IS NULL OR pezzi_disponibili >= 0",
            name="dotazione_pezzi_non_negativi",
        ),
    )


def downgrade() -> None:
    op.drop_table("materiale_dotazione_azienda")
