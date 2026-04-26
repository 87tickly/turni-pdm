"""0004 corsa row_hash + drop UNIQUE business — Sprint 3.7

Cambio architetturale: il PdE Trenord ha varianti dello stesso treno
(reti diverse, variazioni commerciali VCO, periodi sovrapposti) che la
chiave business `(azienda_id, numero_treno, valido_da)` non distingue.
Sul file reale 2025-2026 questo causava la perdita di 53 corse su
10579.

Nuova strategia: **ogni riga del PdE = una riga in `corsa_commerciale`**.
- DROP UNIQUE business (era la causa della perdita)
- ADD `row_hash VARCHAR(64) NOT NULL` = SHA-256 dei campi grezzi della
  riga PdE. Identità naturale, deterministica, stabile fra re-import.
- INDEX `(azienda_id, row_hash)` per delta-sync veloce
- INDEX `(azienda_id, numero_treno, rete, valido_da)` per query business

Il dato esistente in DB è spurio (53 corse erano già state collassate
silenziosamente). La migration **wipa le tabelle corse + import_run +
stazione**: l'utente le ricostruisce con un re-import del PdE.

Revision ID: c4f7a92b1e30
Revises: eb558744cc79
Create Date: 2026-04-26 10:00:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4f7a92b1e30"
down_revision: str | None = "eb558744cc79"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1) Wipe dati spuri (le 10526 corse esistenti hanno collassato
    #    silenziosamente 53 righe del PdE per via del UNIQUE sbagliato).
    #    Ordine: figli prima dei padri (FK).
    # ------------------------------------------------------------------
    op.execute("DELETE FROM corsa_composizione")
    op.execute("DELETE FROM corsa_commerciale")
    op.execute("DELETE FROM corsa_import_run")
    op.execute("DELETE FROM stazione")

    # ------------------------------------------------------------------
    # 2) DROP UNIQUE business — causa della perdita dati
    # ------------------------------------------------------------------
    op.execute("""
        ALTER TABLE corsa_commerciale
        DROP CONSTRAINT corsa_commerciale_azienda_id_numero_treno_valido_da_key
    """)

    # ------------------------------------------------------------------
    # 3) ADD row_hash — natural identity per delta-sync
    #    SHA-256 hex = 64 char fissi.
    # ------------------------------------------------------------------
    op.execute("""
        ALTER TABLE corsa_commerciale
        ADD COLUMN row_hash VARCHAR(64) NOT NULL
    """)

    # ------------------------------------------------------------------
    # 4) Index per delta-sync veloce: lookup `(azienda_id, row_hash)`
    #    NON unique: l'importer dedup le righe identiche (raro ma
    #    possibile nel PdE) prima dell'INSERT.
    # ------------------------------------------------------------------
    op.execute("""
        CREATE INDEX idx_corsa_row_hash
        ON corsa_commerciale (azienda_id, row_hash)
    """)

    # ------------------------------------------------------------------
    # 5) Index business per query "cerca treno X di rete Y dal Z al W"
    #    Sostituisce parzialmente il vecchio UNIQUE (ma senza vincolo).
    # ------------------------------------------------------------------
    op.execute("""
        CREATE INDEX idx_corsa_business
        ON corsa_commerciale (azienda_id, numero_treno, rete, valido_da)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_corsa_business")
    op.execute("DROP INDEX IF EXISTS idx_corsa_row_hash")
    op.execute("ALTER TABLE corsa_commerciale DROP COLUMN IF EXISTS row_hash")
    # Re-create UNIQUE business (è quello sbagliato, ma è quello che c'era prima)
    # ATTENZIONE: il rollback fallisce se ci sono già righe duplicate sulla
    # vecchia chiave business. In quel caso pulire prima manualmente.
    op.execute("""
        ALTER TABLE corsa_commerciale
        ADD CONSTRAINT corsa_commerciale_azienda_id_numero_treno_valido_da_key
        UNIQUE (azienda_id, numero_treno, valido_da)
    """)
    # Wipe dati per essere sicuri: il downgrade è un'operazione di sviluppo,
    # non si rolla in produzione.
    op.execute("DELETE FROM corsa_composizione")
    op.execute("DELETE FROM corsa_commerciale")
    op.execute("DELETE FROM corsa_import_run")
    op.execute("DELETE FROM stazione")
