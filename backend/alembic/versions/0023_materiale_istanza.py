"""0023 — materiale_istanza (Sprint 7.9 MR β2-1)

Tabella per tracciare le istanze fisiche L3 dei materiali (es. ETR526
con matricola "ETR526-000", "ETR526-001", ...). Decisione utente
2026-05-04: introduciamo da subito anche se il ruolo Manutenzione che
le userà davvero arriva in Sprint successivo — semplifica il modello
``MaterialeThread`` (β2-4) che potrà puntare a una matricola.

Schema:

- ``id BIGSERIAL PRIMARY KEY``
- ``azienda_id BIGINT NOT NULL FK azienda(id) ON DELETE RESTRICT``
- ``tipo_materiale_codice VARCHAR(50) NOT NULL FK materiale_tipo(codice) ON DELETE RESTRICT``
- ``matricola VARCHAR(40) NOT NULL`` — formato ``{TIPO}-{NNN}`` (es. ``ETR526-000``)
- ``sede_codice VARCHAR(80) NULL FK localita_manutenzione(codice) ON DELETE SET NULL``
- ``stato VARCHAR(20) NOT NULL DEFAULT 'attivo'``
- ``note TEXT NULL``
- ``created_at TIMESTAMPTZ NOT NULL DEFAULT now()``
- UNIQUE ``(azienda_id, matricola)``

**Seed automatico**: per ogni record di ``materiale_dotazione_azienda``
con ``pezzi_disponibili`` non NULL, genera N istanze con matricole
``{TIPO}-{seq}`` zero-padded a 3 cifre, partendo da 000 e incrementando
fino a N-1. ``sede_codice`` viene lasciato NULL (assegnabile in fase
Manutenzione futura).

Esempio: dotazione Trenord ETR526 = 11 → istanze ETR526-000..ETR526-010.
Idempotente: skip se la matricola esiste già per l'azienda (in caso di
re-run o di esecuzione su DB già popolato).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "d8e1f5c4a920"
down_revision: str | None = "c5e4f8a92b13"  # 0022_localita_sosta_e_regole
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "materiale_istanza",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("azienda_id", sa.BigInteger(), nullable=False),
        sa.Column("tipo_materiale_codice", sa.String(50), nullable=False),
        sa.Column("matricola", sa.String(40), nullable=False),
        sa.Column("sede_codice", sa.String(80), nullable=True),
        sa.Column(
            "stato", sa.String(20), nullable=False, server_default="attivo"
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
            ["tipo_materiale_codice"],
            ["materiale_tipo.codice"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["sede_codice"],
            ["localita_manutenzione.codice"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "azienda_id",
            "matricola",
            name="uq_materiale_istanza_azienda_matricola",
        ),
    )

    op.create_index(
        "ix_materiale_istanza_tipo_sede",
        "materiale_istanza",
        ["azienda_id", "tipo_materiale_codice", "sede_codice"],
    )

    # Seed automatico da `materiale_dotazione_azienda`. Per ogni
    # (azienda, materiale, qty), genera qty istanze con matricola
    # `{materiale_codice}-{seq:03d}` partendo da 000.
    #
    # Implementazione: usiamo `generate_series` di Postgres per
    # produrre N righe con seq 0..N-1 per ciascuna riga di dotazione.
    # Idempotente: ON CONFLICT DO NOTHING sulla UNIQUE
    # (azienda_id, matricola).
    op.execute(
        sa.text(
            """
            INSERT INTO materiale_istanza
                (azienda_id, tipo_materiale_codice, matricola, sede_codice, stato)
            SELECT
                mda.azienda_id,
                mda.materiale_codice,
                mda.materiale_codice || '-' || LPAD(seq::text, 3, '0'),
                NULL,
                'attivo'
            FROM materiale_dotazione_azienda mda
            CROSS JOIN LATERAL generate_series(0, mda.pezzi_disponibili - 1) AS seq
            WHERE mda.pezzi_disponibili IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM materiale_istanza mi
                  WHERE mi.azienda_id = mda.azienda_id
                    AND mi.matricola = mda.materiale_codice
                                       || '-' || LPAD(seq::text, 3, '0')
              )
            """
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_materiale_istanza_tipo_sede", table_name="materiale_istanza"
    )
    op.drop_table("materiale_istanza")
