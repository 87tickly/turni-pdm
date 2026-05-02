"""0013 — km_giornata su giro_giornata (Sprint 7.6 MR 3.2)

Aggiunge la colonna `km_giornata NUMERIC(8,2) NULL` a `giro_giornata`
per rendere visibile, nella vista dettaglio del giro, il chilometraggio
percorso in ogni singola giornata (somma di `km_tratta` delle corse
commerciali della giornata).

Decisione utente 2026-05-01: ogni inizio giornata del turno materiale
deve avere "un suo riepilogo: km giornalieri, mensili e altri piccoli
dettagli". Il `km_media_giornaliera` di `giro_materiale` resta come
aggregato del giro intero — questa colonna espone il dettaglio per
giornata.

Idempotente. Le righe pre-esistenti restano NULL; vengono ricalcolate
alla prossima generazione (`force=true` o nuove giornate aggiunte).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c1f5d932b8a2"
down_revision: str | None = "b9e4c712a83f"  # 0012
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "giro_giornata",
        sa.Column("km_giornata", sa.Numeric(8, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("giro_giornata", "km_giornata")
