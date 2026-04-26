"""0006 localita_manutenzione.codice_breve + backfill — Sprint 4.4.5b

Aggiunge campo ``codice_breve VARCHAR(8)`` a ``localita_manutenzione``
per la generazione del ``numero_turno`` dei giri secondo la convenzione
ARTURO ``G-{LOC_BREVE}-{SEQ:03d}`` (es. ``G-FIO-001``,
``G-TILO-003``).

Backfill per le 7 località Trenord del seed (vedi 0002):

| codice                     | codice_breve |
|----------------------------|--------------|
| IMPMAN_MILANO_FIORENZA     | FIO          |
| IMPMAN_NOVATE              | NOV          |
| IMPMAN_CAMNAGO             | CAM          |
| IMPMAN_LECCO               | LEC          |
| IMPMAN_CREMONA             | CRE          |
| IMPMAN_ISEO                | ISE          |
| POOL_TILO_SVIZZERA         | TILO         |

Constraint:
- ``codice_breve`` UNIQUE per azienda (no collisioni nei nomi giro)
- formato ``^[A-Z]{2,8}$`` (solo lettere maiuscole, 2-8 caratteri)
- NOT NULL (dopo backfill)

Revision ID: b3f2e7a91d54
Revises: a8e2f57d4c91
Create Date: 2026-04-26 18:00:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3f2e7a91d54"
down_revision: str | None = "a8e2f57d4c91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Mappa codice → codice_breve per le località del seed Trenord (0002)
_BACKFILL_TRENORD: list[tuple[str, str]] = [
    ("IMPMAN_MILANO_FIORENZA", "FIO"),
    ("IMPMAN_NOVATE", "NOV"),
    ("IMPMAN_CAMNAGO", "CAM"),
    ("IMPMAN_LECCO", "LEC"),
    ("IMPMAN_CREMONA", "CRE"),
    ("IMPMAN_ISEO", "ISE"),
    ("POOL_TILO_SVIZZERA", "TILO"),
]


def upgrade() -> None:
    # 1) Aggiungi colonna nullable (per permettere il backfill prima del NOT NULL)
    op.execute("ALTER TABLE localita_manutenzione ADD COLUMN codice_breve VARCHAR(8)")

    # 2) Backfill seed Trenord
    for codice, breve in _BACKFILL_TRENORD:
        op.execute(
            f"UPDATE localita_manutenzione SET codice_breve = '{breve}' "  # noqa: S608
            f"WHERE codice = '{codice}'"
        )

    # 3) Verifica che tutte le righe esistenti abbiano un valore (fail-fast
    # se ci sono località non gestite dal backfill: il pianificatore deve
    # configurarle prima di rilanciare la migration).
    op.execute("""
        DO $$
        DECLARE n_null INTEGER;
        BEGIN
            SELECT COUNT(*) INTO n_null
            FROM localita_manutenzione
            WHERE codice_breve IS NULL;
            IF n_null > 0 THEN
                RAISE EXCEPTION 'Migration 0006: % righe localita_manutenzione '
                    'senza codice_breve. Aggiorna il backfill o i dati.', n_null;
            END IF;
        END $$;
    """)

    # 4) Promuovi a NOT NULL + constraint formato + UNIQUE per azienda
    op.execute("ALTER TABLE localita_manutenzione ALTER COLUMN codice_breve SET NOT NULL")
    op.execute("""
        ALTER TABLE localita_manutenzione
        ADD CONSTRAINT localita_codice_breve_format
        CHECK (codice_breve ~ '^[A-Z]{2,8}$')
    """)
    op.execute("""
        ALTER TABLE localita_manutenzione
        ADD CONSTRAINT localita_codice_breve_uq UNIQUE (azienda_id, codice_breve)
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE localita_manutenzione DROP CONSTRAINT localita_codice_breve_uq")
    op.execute("ALTER TABLE localita_manutenzione DROP CONSTRAINT localita_codice_breve_format")
    op.execute("ALTER TABLE localita_manutenzione DROP COLUMN codice_breve")
