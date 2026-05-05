"""0029 — turno_pdc.deposito_pdc_id FK→depot + best-effort backfill.

Sprint 7.9 MR η: il builder PdC non ha mai avuto un'associazione esplicita
fra il turno generato e il deposito PdC che lo ricoprirà. Lo si poteva
inferire solo indirettamente via assegnazione persone → ``persona.sede_residenza_id``,
che oggi non è popolata. Risultato: la dashboard non sa "a quale
deposito appartiene il turno", il builder non può minimizzare i FR
(Fuori Residenza) rispetto al deposito di chi lo guiderà, e il filtro
``GET /api/turni-pdc?impianto=`` raggruppa per ``materiale_tipo``
anziché per deposito (semantica errata).

Questa migration:

1. Aggiunge ``turno_pdc.deposito_pdc_id`` nullable, FK → ``depot.id``,
   ``ON DELETE SET NULL`` (un depot non viene mai cancellato in
   pratica, ma se succede non vogliamo perdere i turni).
2. Crea un indice composito ``(azienda_id, deposito_pdc_id)`` per le
   query "turni di questo deposito" usate da dashboard/lista.
3. **Backfill best-effort** per i turni esistenti: se
   ``generation_metadata_json->>'stazione_sede'`` corrisponde alla
   ``stazione_principale_codice`` di un singolo Depot dell'azienda,
   imposta quel ``deposito_pdc_id``. I turni con stazione_sede ambigua
   (più match) o assente restano NULL — il pianificatore PdC potrà
   assegnarli a posteriori da UI.

Idempotente: ``ADD COLUMN IF NOT EXISTS`` non è disponibile in
SQLAlchemy/Alembic in modo portabile, ma la migration è eseguita una
sola volta dal versioning Alembic. ``downgrade()`` rimuove indice +
colonna.

Revision ID: b7c8d9e0f1a2
Revises: c3d4e5f6a7b8 (0028_seed_depots_per_azienda)
Create Date: 2026-05-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7c8d9e0f1a2"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Aggiunge colonna FK nullable.
    op.add_column(
        "turno_pdc",
        sa.Column(
            "deposito_pdc_id",
            sa.BigInteger(),
            sa.ForeignKey("depot.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # 2. Indice composito per le query per deposito (lista, dashboard,
    # KPI distribuzione). Niente UNIQUE: un deposito ha N turni.
    op.create_index(
        "ix_turno_pdc_azienda_deposito",
        "turno_pdc",
        ["azienda_id", "deposito_pdc_id"],
    )

    # 3. Backfill best-effort: aggancia i turni esistenti al depot la
    # cui ``stazione_principale_codice`` matcha la ``stazione_sede``
    # registrata nel ``generation_metadata_json`` del builder. Gestiamo
    # solo il caso "match unico per azienda" — se più depot hanno la
    # stessa stazione principale (improbabile ma possibile), lasciamo
    # NULL e l'utente assegna in UI.
    op.execute("""
        WITH match_unico AS (
            SELECT
                t.id AS turno_id,
                MIN(d.id) AS depot_id,
                COUNT(*)  AS n_match
            FROM turno_pdc t
            JOIN depot d
              ON d.azienda_id = t.azienda_id
             AND d.is_attivo = TRUE
             AND d.stazione_principale_codice IS NOT NULL
             AND d.stazione_principale_codice =
                 t.generation_metadata_json->>'stazione_sede'
            WHERE t.deposito_pdc_id IS NULL
              AND t.generation_metadata_json ? 'stazione_sede'
            GROUP BY t.id
            HAVING COUNT(*) = 1
        )
        UPDATE turno_pdc
        SET deposito_pdc_id = match_unico.depot_id
        FROM match_unico
        WHERE turno_pdc.id = match_unico.turno_id
    """)


def downgrade() -> None:
    op.drop_index("ix_turno_pdc_azienda_deposito", table_name="turno_pdc")
    op.drop_column("turno_pdc", "deposito_pdc_id")
