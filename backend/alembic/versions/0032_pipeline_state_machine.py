"""0032 — pipeline state machine per la concatenazione tra ruoli.

Sprint 8.0 MR 0 (entry 164). Introduce la **catena formale di handoff**
fra i 5 ruoli del programma:

    PIANIFICATORE MATERIALE → PIANIFICATORE PDC → GESTIONE PERSONALE → VISTA PDC
                                    │
                                    └─→ MANUTENZIONE (parallelo, NON blocca)

Modifiche schema:

1. ``programma_materiale.stato_pipeline_pdc`` (ramo principale, vincolante
   per Personale): ``PDE_IN_LAVORAZIONE`` → ``PDE_CONSOLIDATO`` →
   ``MATERIALE_GENERATO`` → ``MATERIALE_CONFERMATO`` → ``PDC_GENERATO`` →
   ``PDC_CONFERMATO`` → ``PERSONALE_ASSEGNATO`` → ``VISTA_PUBBLICATA``.
2. ``programma_materiale.stato_manutenzione`` (ramo parallelo,
   indipendente): ``IN_ATTESA`` → ``IN_LAVORAZIONE`` → ``MATRICOLE_ASSEGNATE``.
   Si attiva quando ``stato_pipeline_pdc >= MATERIALE_CONFERMATO`` ma
   non blocca le transizioni del ramo PdC.
3. ``corsa_import_run.programma_materiale_id`` (FK nullable): lega ogni
   import a un programma. Predispone il versioning multi-import (PdE
   base + variazioni successive). Nullable per i run preesistenti.
4. ``corsa_import_run.tipo`` (varchar): ``BASE`` (primo import),
   ``INTEGRAZIONE`` (nuove corse), ``VARIAZIONE_INTERRUZIONE`` (linea
   bloccata da-a date), ``VARIAZIONE_ORARIO`` (modifiche orari/comp),
   ``VARIAZIONE_CANCELLAZIONE`` (corse cancellate).

Stati codificati come ``VARCHAR + CHECK constraint`` invece di ENUM
nativo Postgres: aggiungere uno stato in futuro = ALTER constraint
(non DROP TYPE). Validazione applicativa via Pydantic + enum Python.

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4 (0031)
Create Date: 2026-05-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f0a1b2c3d4e5"
down_revision: str | None = "e9f0a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------------------------------------------------------------------------
# Stati ammessi (replicati a livello applicativo in Python enum)
# ---------------------------------------------------------------------------
STATI_PIPELINE_PDC = (
    "PDE_IN_LAVORAZIONE",
    "PDE_CONSOLIDATO",
    "MATERIALE_GENERATO",
    "MATERIALE_CONFERMATO",
    "PDC_GENERATO",
    "PDC_CONFERMATO",
    "PERSONALE_ASSEGNATO",
    "VISTA_PUBBLICATA",
)
STATI_MANUTENZIONE = (
    "IN_ATTESA",
    "IN_LAVORAZIONE",
    "MATRICOLE_ASSEGNATE",
)
TIPI_IMPORT_RUN = (
    "BASE",
    "INTEGRAZIONE",
    "VARIAZIONE_INTERRUZIONE",
    "VARIAZIONE_ORARIO",
    "VARIAZIONE_CANCELLAZIONE",
)


def _in_clause(values: tuple[str, ...]) -> str:
    """Costruisce la lista ``IN ('A','B','C')`` per il CHECK constraint."""
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    # === programma_materiale ===
    op.add_column(
        "programma_materiale",
        sa.Column(
            "stato_pipeline_pdc",
            sa.String(40),
            nullable=False,
            server_default="PDE_IN_LAVORAZIONE",
        ),
    )
    op.add_column(
        "programma_materiale",
        sa.Column(
            "stato_manutenzione",
            sa.String(40),
            nullable=False,
            server_default="IN_ATTESA",
        ),
    )
    op.create_check_constraint(
        "programma_materiale_stato_pipeline_pdc_check",
        "programma_materiale",
        f"stato_pipeline_pdc IN ({_in_clause(STATI_PIPELINE_PDC)})",
    )
    op.create_check_constraint(
        "programma_materiale_stato_manutenzione_check",
        "programma_materiale",
        f"stato_manutenzione IN ({_in_clause(STATI_MANUTENZIONE)})",
    )

    # === corsa_import_run ===
    op.add_column(
        "corsa_import_run",
        sa.Column(
            "programma_materiale_id",
            sa.BigInteger(),
            sa.ForeignKey("programma_materiale.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_corsa_import_run_programma_materiale_id",
        "corsa_import_run",
        ["programma_materiale_id"],
    )
    op.add_column(
        "corsa_import_run",
        sa.Column(
            "tipo",
            sa.String(40),
            nullable=False,
            server_default="BASE",
        ),
    )
    op.create_check_constraint(
        "corsa_import_run_tipo_check",
        "corsa_import_run",
        f"tipo IN ({_in_clause(TIPI_IMPORT_RUN)})",
    )


def downgrade() -> None:
    op.drop_constraint(
        "corsa_import_run_tipo_check", "corsa_import_run", type_="check"
    )
    op.drop_column("corsa_import_run", "tipo")
    op.drop_index(
        "ix_corsa_import_run_programma_materiale_id",
        table_name="corsa_import_run",
    )
    op.drop_column("corsa_import_run", "programma_materiale_id")

    op.drop_constraint(
        "programma_materiale_stato_manutenzione_check",
        "programma_materiale",
        type_="check",
    )
    op.drop_constraint(
        "programma_materiale_stato_pipeline_pdc_check",
        "programma_materiale",
        type_="check",
    )
    op.drop_column("programma_materiale", "stato_manutenzione")
    op.drop_column("programma_materiale", "stato_pipeline_pdc")
