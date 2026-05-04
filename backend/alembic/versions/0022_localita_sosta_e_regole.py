"""0022 — localita_sosta + regola_invio_sosta (Sprint 7.9 MR β2-0)

Introduce due nuove entità di anagrafica per modellare i depositi di
SOSTA INTERMEDIA (= Milano San Rocco / "MISR" come overflow di Milano
Porta Garibaldi), distinti dai depositi di manutenzione esistenti
(``localita_manutenzione``).

Decisione utente 2026-05-04 (durante design β2):

> "in alcune località tipo milano porta garibaldi, possiamo usare il
> deposito loc di milano s.rocco molto utilizzato per soste notturne
> e per soste superiori alle 2 ore"

> "ATR125/115 sono di deposito a lecco, quindi andranno sempre in
> sosta a milano san rocco"

> "1: confermo" (= LocalitaSosta come anagrafica globale per azienda)
> "3: confermo" (= regole d'invio sono per programma + tabella
> separata azienda-level per regole universali, scope futuro β2-7)

Schema:

**localita_sosta**:
- ``id BIGSERIAL PRIMARY KEY``
- ``codice VARCHAR(40) NOT NULL`` — es. "MISR"
- ``nome TEXT NOT NULL``
- ``azienda_id BIGINT NOT NULL FK azienda(id) ON DELETE RESTRICT``
- ``stazione_collegata_codice VARCHAR(20) NULL FK stazione(codice) ON DELETE SET NULL``
- ``is_attiva BOOLEAN NOT NULL DEFAULT true``
- ``note TEXT NULL``
- ``created_at TIMESTAMPTZ NOT NULL DEFAULT now()``
- UNIQUE ``(azienda_id, codice)``

**regola_invio_sosta**:
- ``id BIGSERIAL PRIMARY KEY``
- ``programma_id BIGINT NOT NULL FK programma_materiale(id) ON DELETE CASCADE``
- ``stazione_sgancio_codice VARCHAR(20) NOT NULL FK stazione(codice) ON DELETE RESTRICT``
- ``tipo_materiale_codice VARCHAR(50) NOT NULL FK materiale_tipo(codice) ON DELETE RESTRICT``
- ``finestra_oraria_inizio TIME NOT NULL``
- ``finestra_oraria_fine TIME NOT NULL``
- ``localita_sosta_id BIGINT NOT NULL FK localita_sosta(id) ON DELETE RESTRICT``
- ``fallback_sosta_id BIGINT NULL FK localita_sosta(id) ON DELETE RESTRICT``
- ``note TEXT NULL``
- ``created_at TIMESTAMPTZ NOT NULL DEFAULT now()``

**Seed iniziale**: 1 record `LocalitaSosta` ``MISR`` (Milano San Rocco)
per Trenord (azienda_id=2), collegata alla stazione ``S01645``
(MILANO PORTA GARIBALDI). Niente regole pre-create — il pianificatore
le configurerà via UI quando attiverà la feature.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c5e4f8a92b13"
down_revision: str | None = "a4d92b7e1c08"  # 0021_builder_run
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "localita_sosta",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("codice", sa.String(40), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("azienda_id", sa.BigInteger(), nullable=False),
        sa.Column("stazione_collegata_codice", sa.String(20), nullable=True),
        sa.Column(
            "is_attiva", sa.Boolean(), nullable=False, server_default=sa.true()
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
            ["stazione_collegata_codice"],
            ["stazione.codice"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "azienda_id", "codice", name="uq_localita_sosta_azienda_codice"
        ),
    )

    op.create_table(
        "regola_invio_sosta",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("programma_id", sa.BigInteger(), nullable=False),
        sa.Column("stazione_sgancio_codice", sa.String(20), nullable=False),
        sa.Column("tipo_materiale_codice", sa.String(50), nullable=False),
        sa.Column("finestra_oraria_inizio", sa.Time(), nullable=False),
        sa.Column("finestra_oraria_fine", sa.Time(), nullable=False),
        sa.Column("localita_sosta_id", sa.BigInteger(), nullable=False),
        sa.Column("fallback_sosta_id", sa.BigInteger(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["programma_id"], ["programma_materiale.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["stazione_sgancio_codice"], ["stazione.codice"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["tipo_materiale_codice"], ["materiale_tipo.codice"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["localita_sosta_id"], ["localita_sosta.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["fallback_sosta_id"], ["localita_sosta.id"], ondelete="RESTRICT"
        ),
    )

    op.create_index(
        "ix_regola_invio_sosta_programma",
        "regola_invio_sosta",
        ["programma_id"],
    )

    # Seed: Milano San Rocco (MISR) per Trenord (azienda_id=2).
    # Idempotente: ON CONFLICT DO NOTHING (in caso il seed sia rieseguito).
    op.execute(
        sa.text(
            """
            INSERT INTO localita_sosta
                (codice, nome, azienda_id, stazione_collegata_codice, is_attiva, note)
            SELECT 'MISR', 'Milano San Rocco', 2, 'S01645', true,
                'Deposito di sosta intermedia (overflow di Garibaldi). Usato per '
                'soste notturne e soste >2h, soprattutto per ETR421/ATR125/ATR115 '
                'sganciati a Milano Porta Garibaldi.'
            WHERE EXISTS (SELECT 1 FROM azienda WHERE id = 2)
              AND NOT EXISTS (
                  SELECT 1 FROM localita_sosta
                  WHERE azienda_id = 2 AND codice = 'MISR'
              )
            """
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_regola_invio_sosta_programma", table_name="regola_invio_sosta"
    )
    op.drop_table("regola_invio_sosta")
    op.drop_table("localita_sosta")
