"""0017 — `numero_turno` 20 → 40 char (Sprint 7.7 MR 4)

Allarga ``giro_materiale.numero_turno`` e
``corsa_materiale_vuoto.numero_treno_vuoto`` da ``VARCHAR(20)`` a
``VARCHAR(40)`` per accogliere il suffisso materiale introdotto in
MR 7.7.4.

Decisione utente 2026-05-02:
> "quando generi un giro [...] aggiungi anche il materiale che
> stiamo usando, es: G-FIO-001-204"

Formato (Sprint 7.7 MR 4):
- ``giro_materiale.numero_turno`` =
  ``G-{LOC_BREVE}-{SEQ:03d}-{materiale_tipo_codice}``
- ``corsa_materiale_vuoto.numero_treno_vuoto`` =
  ``V-{numero_turno}-{SEQ:03d}`` quindi serve allargarla anch'essa.

Casi più lunghi noti dal seed Trenord:
- numero_turno ``G-FIO-001-ALe245_treno`` (22 char)
- numero_treno_vuoto ``V-G-FIO-001-ALe245_treno-000`` (28 char)

40 char danno margine ampio anche per materiali futuri con codici
più lunghi.
"""

from __future__ import annotations

from alembic import op

revision: str = "1a4d6e92c8b3"
down_revision: str | None = "f7c2b189e405"  # 0016_refactor_varianti_giri_separati
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE giro_materiale "
        "ALTER COLUMN numero_turno TYPE VARCHAR(40)"
    )
    op.execute(
        "ALTER TABLE corsa_materiale_vuoto "
        "ALTER COLUMN numero_treno_vuoto TYPE VARCHAR(40)"
    )


def downgrade() -> None:
    # Tornare a 20 char fa fallire se ci sono righe con valori > 20 char.
    # Il caller del downgrade deve prima rigenerare i giri o troncare.
    op.execute(
        "ALTER TABLE corsa_materiale_vuoto "
        "ALTER COLUMN numero_treno_vuoto TYPE VARCHAR(20)"
    )
    op.execute(
        "ALTER TABLE giro_materiale "
        "ALTER COLUMN numero_turno TYPE VARCHAR(20)"
    )
