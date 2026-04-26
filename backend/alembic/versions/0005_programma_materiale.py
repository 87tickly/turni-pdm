"""0005 programma_materiale + regola_assegnazione + alter giro_blocco — Sprint 4.1

Crea il modello dati per il **programma materiale** (vedi
`docs/PROGRAMMA-MATERIALE.md` v0.2): l'input umano del pianificatore
giro materiale che assegna rotabili alle corse del PdE.

Tabelle nuove:
- `programma_materiale`: intestazione + parametri globali del programma
- `programma_regola_assegnazione`: regole AND-filter → (tipo, n_pezzi)

Modifiche su `giro_blocco`:
- aggiunge `is_validato_utente BOOLEAN` (per eventi aggancio/sgancio
  proposti dal builder ma da confermare dal pianificatore)
- aggiunge `metadata_json JSONB` (per pezzi_delta, note builder, ecc.)
- estende i constraint `giro_blocco_tipo_check` e
  `giro_blocco_link_coerente` per ammettere `'aggancio'` e `'sgancio'`

NB: i tipi blocco esistenti in 0001 sono `'corsa_commerciale'`,
`'materiale_vuoto'`, `'sosta_disponibile'`, `'manovra'`. Aggiungiamo
`'aggancio'` e `'sgancio'` allo stesso ramo "no FK" di
`'sosta_disponibile'` / `'manovra'`.

Revision ID: a8e2f57d4c91
Revises: c4f7a92b1e30
Create Date: 2026-04-26 12:00:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a8e2f57d4c91"
down_revision: str | None = "c4f7a92b1e30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # =================================================================
    # 1) programma_materiale
    # =================================================================
    op.execute("""
        CREATE TABLE programma_materiale (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            azienda_id BIGINT NOT NULL REFERENCES azienda(id) ON DELETE RESTRICT,

            nome TEXT NOT NULL,
            stagione VARCHAR(20),
            valido_da DATE NOT NULL,
            valido_a DATE NOT NULL,
            stato VARCHAR(20) NOT NULL DEFAULT 'bozza',

            -- Parametri globali
            km_max_giornaliero INTEGER,
            n_giornate_default INTEGER NOT NULL DEFAULT 1,
            fascia_oraria_tolerance_min INTEGER NOT NULL DEFAULT 30,

            -- Strict mode granulare (default tutto false = tolerant)
            strict_options_json JSONB NOT NULL DEFAULT '{
                "no_corse_residue": false,
                "no_overcapacity": false,
                "no_aggancio_non_validato": false,
                "no_orphan_blocks": false,
                "no_giro_non_chiuso_a_localita": false,
                "no_km_eccesso": false
            }'::jsonb,

            -- Tracking
            created_by_user_id BIGINT REFERENCES app_user(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT programma_stato_check
                CHECK (stato IN ('bozza', 'attivo', 'archiviato')),
            CONSTRAINT programma_stagione_check
                CHECK (stagione IN ('invernale', 'estiva', 'agosto') OR stagione IS NULL),
            CONSTRAINT programma_validita_check
                CHECK (valido_a >= valido_da),
            CONSTRAINT programma_giornate_check
                CHECK (n_giornate_default >= 1),
            CONSTRAINT programma_tolerance_check
                CHECK (fascia_oraria_tolerance_min >= 0 AND fascia_oraria_tolerance_min <= 120)
        )
    """)
    op.execute("CREATE INDEX idx_programma_azienda ON programma_materiale(azienda_id)")
    op.execute("CREATE INDEX idx_programma_stato ON programma_materiale(stato)")
    op.execute(
        "CREATE INDEX idx_programma_validita ON programma_materiale(valido_da, valido_a)"
    )

    # =================================================================
    # 2) programma_regola_assegnazione
    # =================================================================
    op.execute("""
        CREATE TABLE programma_regola_assegnazione (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            programma_id BIGINT NOT NULL
                REFERENCES programma_materiale(id) ON DELETE CASCADE,

            -- Filtri AND su 12+ campi (validazione applicativa Pydantic)
            -- Es. [
            --   {"campo": "codice_linea", "op": "eq", "valore": "S5"},
            --   {"campo": "fascia_oraria", "op": "between", "valore": ["04:00", "15:59"]},
            --   {"campo": "giorno_tipo", "op": "in", "valore": ["feriale"]}
            -- ]
            filtri_json JSONB NOT NULL DEFAULT '[]'::jsonb,

            -- Assegnazione
            materiale_tipo_codice VARCHAR(50) NOT NULL
                REFERENCES materiale_tipo(codice) ON DELETE RESTRICT,
            numero_pezzi INTEGER NOT NULL,

            -- Priorità + tracking
            priorita INTEGER NOT NULL DEFAULT 60,
            note TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT regola_pezzi_check CHECK (numero_pezzi >= 1),
            CONSTRAINT regola_priorita_check
                CHECK (priorita >= 0 AND priorita <= 100)
        )
    """)
    op.execute(
        "CREATE INDEX idx_regola_programma ON programma_regola_assegnazione(programma_id)"
    )
    op.execute(
        "CREATE INDEX idx_regola_priorita "
        "ON programma_regola_assegnazione(priorita DESC)"
    )
    # GIN su filtri_json: query rapide tipo "che regole filtrano per linea X?"
    op.execute(
        "CREATE INDEX idx_regola_filtri_gin "
        "ON programma_regola_assegnazione USING GIN (filtri_json)"
    )

    # =================================================================
    # 3) Alter giro_blocco — supporto a aggancio/sgancio + validazione
    # =================================================================
    op.execute(
        "ALTER TABLE giro_blocco "
        "ADD COLUMN is_validato_utente BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE giro_blocco "
        "ADD COLUMN metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb"
    )

    # Estendi check tipo_blocco: aggiungi 'aggancio' e 'sgancio'
    op.execute("ALTER TABLE giro_blocco DROP CONSTRAINT giro_blocco_tipo_check")
    op.execute("""
        ALTER TABLE giro_blocco
        ADD CONSTRAINT giro_blocco_tipo_check
        CHECK (tipo_blocco IN (
            'corsa_commerciale', 'materiale_vuoto',
            'sosta_disponibile', 'manovra',
            'aggancio', 'sgancio'
        ))
    """)

    # Estendi check link_coerente: aggiungi i nuovi tipi al ramo "no FK"
    op.execute("ALTER TABLE giro_blocco DROP CONSTRAINT giro_blocco_link_coerente")
    op.execute("""
        ALTER TABLE giro_blocco
        ADD CONSTRAINT giro_blocco_link_coerente
        CHECK (
            (tipo_blocco = 'corsa_commerciale'
             AND corsa_commerciale_id IS NOT NULL
             AND corsa_materiale_vuoto_id IS NULL)
            OR (tipo_blocco = 'materiale_vuoto'
             AND corsa_materiale_vuoto_id IS NOT NULL
             AND corsa_commerciale_id IS NULL)
            OR (tipo_blocco IN ('sosta_disponibile', 'manovra',
                                'aggancio', 'sgancio')
             AND corsa_commerciale_id IS NULL
             AND corsa_materiale_vuoto_id IS NULL)
        )
    """)


def downgrade() -> None:
    # Rollback constraint giro_blocco (ai valori 0001)
    op.execute("ALTER TABLE giro_blocco DROP CONSTRAINT IF EXISTS giro_blocco_link_coerente")
    op.execute("""
        ALTER TABLE giro_blocco
        ADD CONSTRAINT giro_blocco_link_coerente
        CHECK (
            (tipo_blocco = 'corsa_commerciale'
             AND corsa_commerciale_id IS NOT NULL
             AND corsa_materiale_vuoto_id IS NULL)
            OR (tipo_blocco = 'materiale_vuoto'
             AND corsa_materiale_vuoto_id IS NOT NULL
             AND corsa_commerciale_id IS NULL)
            OR (tipo_blocco IN ('sosta_disponibile', 'manovra')
             AND corsa_commerciale_id IS NULL
             AND corsa_materiale_vuoto_id IS NULL)
        )
    """)
    op.execute("ALTER TABLE giro_blocco DROP CONSTRAINT IF EXISTS giro_blocco_tipo_check")
    op.execute("""
        ALTER TABLE giro_blocco
        ADD CONSTRAINT giro_blocco_tipo_check
        CHECK (tipo_blocco IN (
            'corsa_commerciale', 'materiale_vuoto',
            'sosta_disponibile', 'manovra'
        ))
    """)

    op.execute("ALTER TABLE giro_blocco DROP COLUMN IF EXISTS metadata_json")
    op.execute("ALTER TABLE giro_blocco DROP COLUMN IF EXISTS is_validato_utente")

    # Drop tabelle nuove
    op.execute("DROP TABLE IF EXISTS programma_regola_assegnazione CASCADE")
    op.execute("DROP TABLE IF EXISTS programma_materiale CASCADE")
