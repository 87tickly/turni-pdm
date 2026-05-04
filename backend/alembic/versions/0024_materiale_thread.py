"""0024 — materiale_thread + materiale_thread_evento (Sprint 7.9 MR β2-4)

Tabelle per tracciare i thread logici (L2) dei materiali nei giri.
Decisione utente 2026-05-04: ogni "pezzo logico" ha la sua sequenza
temporale di eventi (corsa singolo, corsa doppia, vuoto, sosta,
aggancio, sgancio, rientro deposito).

Schema:

**materiale_thread**:
- id, azienda_id (RESTRICT), programma_id (CASCADE),
  giro_materiale_id_origine (CASCADE), tipo_materiale_codice
  (RESTRICT), matricola_id (NULLABLE, SET NULL su materiale_istanza),
  km_totali NUMERIC(10,3) DEFAULT 0, minuti_servizio INT DEFAULT 0,
  n_corse_commerciali INT DEFAULT 0, note TEXT, created_at.

**materiale_thread_evento**:
- id, thread_id (CASCADE), ordine INT (1-based progressivo),
  tipo VARCHAR(30) (corsa_singolo|corsa_doppia_pos1|...|sosta|
  aggancio|sgancio|uscita_deposito|rientro_deposito),
  giro_blocco_id (NULLABLE SET NULL), stazione_da/a_codice
  (NULLABLE SET NULL), ora_inizio/fine TIME, data_giorno DATE,
  km_tratta NUMERIC(10,3) NULLABLE, numero_treno VARCHAR(20) NULLABLE,
  note TEXT, created_at.
- UNIQUE (thread_id, ordine).

Niente seed. I thread vengono proiettati dall'algoritmo
`proietta_thread` (modulo nuovo `thread_proiezione.py`) durante la
generazione giri.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "e9a3f2c81d4b"
down_revision: str | None = "d8e1f5c4a920"  # 0023_materiale_istanza
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "materiale_thread",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("azienda_id", sa.BigInteger(), nullable=False),
        sa.Column("programma_id", sa.BigInteger(), nullable=False),
        sa.Column("giro_materiale_id_origine", sa.BigInteger(), nullable=False),
        sa.Column("tipo_materiale_codice", sa.String(50), nullable=False),
        sa.Column("matricola_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "km_totali",
            sa.Numeric(10, 3),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "minuti_servizio",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "n_corse_commerciali",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["azienda_id"], ["azienda.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["programma_id"],
            ["programma_materiale.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["giro_materiale_id_origine"],
            ["giro_materiale.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tipo_materiale_codice"],
            ["materiale_tipo.codice"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["matricola_id"],
            ["materiale_istanza.id"],
            ondelete="SET NULL",
        ),
    )

    op.create_index(
        "ix_materiale_thread_giro",
        "materiale_thread",
        ["giro_materiale_id_origine"],
    )
    op.create_index(
        "ix_materiale_thread_programma_tipo",
        "materiale_thread",
        ["programma_id", "tipo_materiale_codice"],
    )

    op.create_table(
        "materiale_thread_evento",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("thread_id", sa.BigInteger(), nullable=False),
        sa.Column("ordine", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(30), nullable=False),
        sa.Column("giro_blocco_id", sa.BigInteger(), nullable=True),
        sa.Column("stazione_da_codice", sa.String(20), nullable=True),
        sa.Column("stazione_a_codice", sa.String(20), nullable=True),
        sa.Column("ora_inizio", sa.Time(), nullable=True),
        sa.Column("ora_fine", sa.Time(), nullable=True),
        sa.Column("data_giorno", sa.Date(), nullable=True),
        sa.Column("km_tratta", sa.Numeric(10, 3), nullable=True),
        sa.Column("numero_treno", sa.String(20), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["materiale_thread.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["giro_blocco_id"],
            ["giro_blocco.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["stazione_da_codice"],
            ["stazione.codice"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["stazione_a_codice"],
            ["stazione.codice"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "thread_id", "ordine", name="uq_thread_evento_ordine"
        ),
    )

    op.create_index(
        "ix_thread_evento_thread_ordine",
        "materiale_thread_evento",
        ["thread_id", "ordine"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_thread_evento_thread_ordine",
        table_name="materiale_thread_evento",
    )
    op.drop_table("materiale_thread_evento")
    op.drop_index(
        "ix_materiale_thread_programma_tipo",
        table_name="materiale_thread",
    )
    op.drop_index("ix_materiale_thread_giro", table_name="materiale_thread")
    op.drop_table("materiale_thread")
