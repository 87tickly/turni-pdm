"""0034 — soft-delete corsa_commerciale (variazioni PdE concrete).

Sub-MR 5.bis-a (Sprint 8.0 follow-up). Aggiunge 3 colonne a
``corsa_commerciale`` per supportare la cancellazione "concreta" di una
corsa via variazione PdE di tipo ``VARIAZIONE_CANCELLAZIONE``.

Hard-DELETE è impossibile sulle corse già consumate: ``turno_pdc_blocco``
ha FK RESTRICT su ``corsa_commerciale.id``. Soft-delete via flag dedicato
preserva l'integrità referenziale + traccia chi ha cancellato e quando.

Le 3 colonne sono coerenti tra loro (CHECK constraint):

- ``is_cancellata=FALSE`` ⟹ ``cancellata_da_run_id`` e ``cancellata_at``
  sono NULL (corsa attiva).
- ``is_cancellata=TRUE`` ⟹ entrambi NOT NULL (audit completo).

Indice parziale ``ix_corsa_commerciale_attive`` su ``(azienda_id)``
``WHERE is_cancellata = FALSE`` per accelerare le query del lato
consumer (la stragrande maggioranza).

Revision ID: b2c3d4e5f6a1
Revises: a1b2c3d4e5f6 (0033)
Create Date: 2026-05-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a1"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "corsa_commerciale",
        sa.Column(
            "is_cancellata",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment=(
                "Sub-MR 5.bis-a: soft-delete via VARIAZIONE_CANCELLAZIONE. "
                "TRUE = corsa cancellata, esclusa dalle query consumer. "
                "FALSE = attiva (default)."
            ),
        ),
    )
    op.add_column(
        "corsa_commerciale",
        sa.Column(
            "cancellata_da_run_id",
            sa.BigInteger(),
            sa.ForeignKey("corsa_import_run.id", ondelete="SET NULL"),
            nullable=True,
            comment=(
                "Sub-MR 5.bis-a: ID della CorsaImportRun che ha "
                "cancellato la corsa. SET NULL se il run viene rimosso."
            ),
        ),
    )
    op.add_column(
        "corsa_commerciale",
        sa.Column(
            "cancellata_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Sub-MR 5.bis-a: timestamp soft-delete.",
        ),
    )
    op.create_check_constraint(
        "corsa_commerciale_cancellazione_coerente",
        "corsa_commerciale",
        (
            "(is_cancellata = false "
            "AND cancellata_da_run_id IS NULL "
            "AND cancellata_at IS NULL) "
            "OR "
            "(is_cancellata = true "
            "AND cancellata_da_run_id IS NOT NULL "
            "AND cancellata_at IS NOT NULL)"
        ),
    )
    op.create_index(
        "ix_corsa_commerciale_attive",
        "corsa_commerciale",
        ["azienda_id"],
        postgresql_where=sa.text("is_cancellata = false"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_corsa_commerciale_attive",
        table_name="corsa_commerciale",
    )
    op.drop_constraint(
        "corsa_commerciale_cancellazione_coerente",
        "corsa_commerciale",
        type_="check",
    )
    op.drop_column("corsa_commerciale", "cancellata_at")
    op.drop_column("corsa_commerciale", "cancellata_da_run_id")
    op.drop_column("corsa_commerciale", "is_cancellata")
