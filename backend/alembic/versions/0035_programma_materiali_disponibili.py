"""0035 — materiali_disponibili_codici_json su programma_materiale.

MR α (2026-05-06). Aggiunge colonna ``programma_materiale.materiali_disponibili_codici_json``
(JSONB list[str], default ``[]``).

Semantica:

- Lista vuota ``[]`` (default) = tutti i materiali della dotazione
  azienda sono ammissibili in questo programma. Retrocompat con i
  programmi esistenti: a migration applicata leggono ``[]`` e si
  comportano come prima.
- Lista non vuota = subset dichiarato dal pianificatore in fase di
  creazione (multi-select sulle ``MaterialeDotazioneAzienda``).
  Mostrato nel pannello "Materiali in flotta" che sostituisce i 6
  chip strict options nella dashboard del programma.

Origine: l'utente ha segnalato (sessione 2026-05-06) che le 6 chip
``no_corse_residue`` ecc. sono cripto-tecniche e poco utili. Al loro
posto vuole vedere la lista dei materiali messi a disposizione del
programma con i pezzi disponibili. Il campo ``strict_options_json``
NON viene rimosso: resta come legacy (default ``{}``), ma sparisce
dalla UI in MR α.

Revision ID: c3d4e5f6a1b2
Revises: b2c3d4e5f6a1 (0034)
Create Date: 2026-05-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a1b2"
down_revision: str | None = "b2c3d4e5f6a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "programma_materiale",
        sa.Column(
            "materiali_disponibili_codici_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
            comment=(
                "MR α: lista codici MaterialeTipo ammessi nel programma. "
                "[] = tutti i materiali della dotazione azienda (default)."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "programma_materiale",
        "materiali_disponibili_codici_json",
    )
