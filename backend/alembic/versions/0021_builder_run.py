"""0021 — builder_run (Sprint 7.9 MR 11C, entry 116)

Tabella che persiste l'esito di ogni esecuzione del builder per un
programma. Sostituisce la card "Storico run del builder · in arrivo"
mostrata in UI fino a entry 86.

Decisione utente 2026-05-04: dopo che il builder produce 0 giri (caso
sede non coerente con regola, vedi entry 115), il pianificatore deve
poter vedere PERCHÉ — i warning del run e il numero di corse residue
sono già prodotti dal builder ma persi dopo la response. La tabella
``builder_run`` li conserva per visualizzazione storica e
diagnostica.

Schema:

- ``id BIGSERIAL PRIMARY KEY``
- ``programma_id BIGINT NOT NULL FK programma_materiale(id) ON DELETE CASCADE``
- ``azienda_id BIGINT NOT NULL FK azienda(id) ON DELETE CASCADE``
- ``localita_codice VARCHAR(64) NOT NULL`` — sede scelta per il run
- ``eseguito_da_user_id BIGINT NULL FK app_user(id) ON DELETE SET NULL``
- ``eseguito_at TIMESTAMPTZ NOT NULL DEFAULT now()``
- ``n_giri_creati INT NOT NULL DEFAULT 0``
- ``n_giri_chiusi INT NOT NULL DEFAULT 0``
- ``n_giri_non_chiusi INT NOT NULL DEFAULT 0``
- ``n_corse_processate INT NOT NULL DEFAULT 0``
- ``n_corse_residue INT NOT NULL DEFAULT 0``
- ``n_eventi_composizione INT NOT NULL DEFAULT 0``
- ``n_incompatibilita_materiale INT NOT NULL DEFAULT 0``
- ``warnings_json JSONB NOT NULL DEFAULT '[]'``
- ``force BOOLEAN NOT NULL DEFAULT false``

Indici:
- ``(programma_id, eseguito_at DESC)`` per recuperare l'ultimo run
  con UNA query.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a4d92b7e1c08"
down_revision: str | None = "f3b8c1e29a47"  # 0020_materiale_dotazione_azienda
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "builder_run",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("programma_id", sa.BigInteger(), nullable=False),
        sa.Column("azienda_id", sa.BigInteger(), nullable=False),
        sa.Column("localita_codice", sa.String(64), nullable=False),
        sa.Column("eseguito_da_user_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "eseguito_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("n_giri_creati", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_giri_chiusi", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "n_giri_non_chiusi", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "n_corse_processate", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("n_corse_residue", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "n_eventi_composizione", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "n_incompatibilita_materiale",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "warnings_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("force", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(
            ["programma_id"], ["programma_materiale.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["azienda_id"], ["azienda.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["eseguito_da_user_id"], ["app_user.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_builder_run_programma_eseguito_at",
        "builder_run",
        ["programma_id", sa.text("eseguito_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_builder_run_programma_eseguito_at", table_name="builder_run")
    op.drop_table("builder_run")
