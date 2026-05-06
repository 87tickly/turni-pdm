"""0036 — localita_codice su programma_regola_assegnazione (MR β).

MR β (2026-05-06). Aggiunge colonna nullable
``programma_regola_assegnazione.localita_codice`` (FK opzionale a
``localita_manutenzione.codice``).

Semantica:

- ``NULL`` (default per tutte le regole esistenti) = la regola non ha
  ancora una sede preferita. Il wizard pre-generazione mostra un
  dropdown vuoto e l'utente deve scegliere prima di lanciare il
  builder.
- Valore non NULL = sede memorizzata. Il wizard pre-generazione
  precompila il dropdown col valore (modificabile per quel run).

Decisione utente 2026-05-06: ogni regola (= linea) ha la sua sede
preferita. Il pianificatore la imposta in fase di creazione regola
oppure al primo wizard pre-generazione (auto-save sulla regola).

L'endpoint ``POST /api/programmi/{id}/genera-giri`` esistente NON
viene cambiato in MR β: continua ad accettare ``localita_codice``
come query param. Il wizard frontend chiama l'endpoint N volte
sequenzialmente (una per sede unica raccolta dalle regole), così il
backend non deve gestire il multi-sede in un solo run.

Revision ID: d4e5f6a1b2c3
Revises: c3d4e5f6a1b2 (0035)
Create Date: 2026-05-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a1b2c3"
down_revision: str | None = "c3d4e5f6a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "programma_regola_assegnazione",
        sa.Column(
            "localita_codice",
            sa.String(80),
            nullable=True,
            comment=(
                "MR β: sede manutentiva preferita per i giri generati da "
                "questa regola. NULL = da scegliere nel wizard pre-generazione."
            ),
        ),
    )
    op.create_foreign_key(
        "fk_regola_localita_manutenzione",
        "programma_regola_assegnazione",
        "localita_manutenzione",
        ["localita_codice"],
        ["codice"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_regola_localita_codice",
        "programma_regola_assegnazione",
        ["localita_codice"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_regola_localita_codice",
        table_name="programma_regola_assegnazione",
    )
    op.drop_constraint(
        "fk_regola_localita_manutenzione",
        "programma_regola_assegnazione",
        type_="foreignkey",
    )
    op.drop_column(
        "programma_regola_assegnazione",
        "localita_codice",
    )
