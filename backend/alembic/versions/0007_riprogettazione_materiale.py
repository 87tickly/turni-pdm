"""0007 riprogettazione materiale — Sprint 5.1

Estensione schema DB per il nuovo modello operativo del builder giro
materiale (vedi `docs/SPRINT-5-RIPENSAMENTO.md`):

1. Whitelist M:N stazioni-vicine-sede (`localita_stazione_vicina`):
   per ogni sede manutentiva un set di stazioni in cui sono ammessi i
   vuoti tecnici. Esempio FIO: Mi.Garibaldi, Mi.Centrale, Mi.Lambrate,
   Mi.Rogoredo, Mi.Greco-Pirelli. Una stazione può appartenere a più
   sedi (es. Saronno per NOV+CAM).

2. Vincoli accoppiamento materiali (`materiale_accoppiamento_ammesso`):
   coppie ammesse di rotabili in doppia composizione. Normalizzata
   lessicograficamente (a <= b) per unicità simmetrica. Esempi:
   ETR421+ETR421, ETR526+ETR526, ETR526+ETR425.

3. Estensione regola assegnazione (`programma_regola_assegnazione`):
   - `composizione_json JSONB NOT NULL`: lista
     `[{materiale_tipo_codice, n_pezzi}, ...]`. Sostituisce a regime i
     campi legacy `materiale_tipo_codice` + `numero_pezzi` (resi
     nullable, deprecati ma non rimossi: `risolvi_corsa()` li legge
     fino a Sprint 5.5).
   - `is_composizione_manuale BOOLEAN`: se True, bypass del check
     `materiale_accoppiamento_ammesso` (override pianificatore).

4. Cap km ciclo (`programma_materiale.km_max_ciclo INTEGER`):
   km cumulati massimi sul ciclo intero (NON giornaliero). Quando
   raggiunto, il giro chiude con rientro programmato. Default NULL
   (configurato dal pianificatore per ogni programma).

5. Rinomina chiave JSONB strict
   `no_giro_non_chiuso_a_localita` → `no_giro_appeso`:
   semantica corretta del nuovo modello multi-giornata (un giro non
   deve essere "appeso", cioè avere un rientro programmato a fine
   ciclo, NON ogni sera). Lo schema Pydantic StrictOptions cambia di
   conseguenza.

6. Sede manutentiva default per materiale
   (`materiale_tipo.localita_manutenzione_default_id`):
   campo nullable assegnabile dal pianificatore. Inizialmente NULL
   per tutti i materiali; configurato via UI/seed/API.

Revision ID: c4e7f3a92d68
Revises: b3f2e7a91d54
Create Date: 2026-04-27 14:00:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e7f3a92d68"
down_revision: str | None = "b3f2e7a91d54"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # =================================================================
    # 1) Whitelist M:N stazioni-vicine-sede
    # =================================================================
    op.execute("""
        CREATE TABLE localita_stazione_vicina (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            localita_manutenzione_id BIGINT NOT NULL
                REFERENCES localita_manutenzione(id) ON DELETE CASCADE,
            stazione_codice VARCHAR(20) NOT NULL
                REFERENCES stazione(codice) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (localita_manutenzione_id, stazione_codice)
        )
    """)
    op.execute(
        "CREATE INDEX idx_localita_stazione_vicina_loc "
        "ON localita_stazione_vicina(localita_manutenzione_id)"
    )
    op.execute(
        "CREATE INDEX idx_localita_stazione_vicina_staz "
        "ON localita_stazione_vicina(stazione_codice)"
    )

    # =================================================================
    # 2) Vincoli accoppiamento materiali (normalizzata: a <= b)
    # =================================================================
    op.execute("""
        CREATE TABLE materiale_accoppiamento_ammesso (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            materiale_a_codice VARCHAR(50) NOT NULL
                REFERENCES materiale_tipo(codice) ON DELETE RESTRICT,
            materiale_b_codice VARCHAR(50) NOT NULL
                REFERENCES materiale_tipo(codice) ON DELETE RESTRICT,
            note TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (materiale_a_codice, materiale_b_codice),
            CONSTRAINT materiale_accoppiamento_normalizzato
                CHECK (materiale_a_codice <= materiale_b_codice)
        )
    """)

    # =================================================================
    # 3) Estensione regola assegnazione: composizione_json + manuale
    # =================================================================
    op.execute(
        "ALTER TABLE programma_regola_assegnazione "
        "ADD COLUMN composizione_json JSONB"
    )
    op.execute(
        "ALTER TABLE programma_regola_assegnazione "
        "ADD COLUMN is_composizione_manuale BOOLEAN NOT NULL DEFAULT FALSE"
    )

    # Backfill: composizione_json = [{materiale_tipo_codice, n_pezzi}]
    op.execute("""
        UPDATE programma_regola_assegnazione
        SET composizione_json = jsonb_build_array(
            jsonb_build_object(
                'materiale_tipo_codice', materiale_tipo_codice,
                'n_pezzi', numero_pezzi
            )
        )
        WHERE composizione_json IS NULL
    """)

    # Promuovi NOT NULL dopo il backfill
    op.execute(
        "ALTER TABLE programma_regola_assegnazione "
        "ALTER COLUMN composizione_json SET NOT NULL"
    )

    # I campi legacy (materiale_tipo_codice, numero_pezzi) diventano nullable.
    # Sono ancora letti da risolvi_corsa() fino a Sprint 5.5; le nuove righe
    # li popolano dal primo elemento di composizione_json (handler API).
    op.execute(
        "ALTER TABLE programma_regola_assegnazione "
        "ALTER COLUMN materiale_tipo_codice DROP NOT NULL"
    )
    op.execute(
        "ALTER TABLE programma_regola_assegnazione "
        "ALTER COLUMN numero_pezzi DROP NOT NULL"
    )

    # =================================================================
    # 4) Cap km ciclo su programma_materiale
    # =================================================================
    op.execute(
        "ALTER TABLE programma_materiale ADD COLUMN km_max_ciclo INTEGER"
    )
    op.execute("""
        ALTER TABLE programma_materiale
        ADD CONSTRAINT programma_materiale_km_max_ciclo_positivo
        CHECK (km_max_ciclo IS NULL OR km_max_ciclo >= 1)
    """)

    # =================================================================
    # 5) Rename chiave JSONB strict: no_giro_non_chiuso_a_localita → no_giro_appeso
    # =================================================================
    # Solo righe che hanno la chiave vecchia. Le nuove non sono toccate
    # (Pydantic StrictOptions emette già il nuovo nome).
    op.execute("""
        UPDATE programma_materiale
        SET strict_options_json = (
            (strict_options_json - 'no_giro_non_chiuso_a_localita')
            || jsonb_build_object(
                'no_giro_appeso',
                COALESCE(
                    strict_options_json->'no_giro_non_chiuso_a_localita',
                    'false'::jsonb
                )
            )
        )
        WHERE strict_options_json ? 'no_giro_non_chiuso_a_localita'
    """)
    # Aggiorna anche il DEFAULT della colonna (era settato in 0005 col nome
    # vecchio): nuove righe inserite senza valore esplicito useranno il
    # nome corretto `no_giro_appeso`.
    op.execute("""
        ALTER TABLE programma_materiale
        ALTER COLUMN strict_options_json SET DEFAULT '{
            "no_corse_residue": false,
            "no_overcapacity": false,
            "no_aggancio_non_validato": false,
            "no_orphan_blocks": false,
            "no_giro_appeso": false,
            "no_km_eccesso": false
        }'::jsonb
    """)

    # =================================================================
    # 6) Sede manutentiva default per materiale_tipo
    # =================================================================
    op.execute(
        "ALTER TABLE materiale_tipo "
        "ADD COLUMN localita_manutenzione_default_id BIGINT "
        "REFERENCES localita_manutenzione(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX idx_materiale_tipo_localita_default "
        "ON materiale_tipo(localita_manutenzione_default_id) "
        "WHERE localita_manutenzione_default_id IS NOT NULL"
    )


def downgrade() -> None:
    # 6) materiale_tipo.localita_manutenzione_default_id
    op.execute("DROP INDEX IF EXISTS idx_materiale_tipo_localita_default")
    op.execute(
        "ALTER TABLE materiale_tipo DROP COLUMN localita_manutenzione_default_id"
    )

    # 5) Rename strict (back: no_giro_appeso → no_giro_non_chiuso_a_localita)
    op.execute("""
        UPDATE programma_materiale
        SET strict_options_json = (
            (strict_options_json - 'no_giro_appeso')
            || jsonb_build_object(
                'no_giro_non_chiuso_a_localita',
                COALESCE(
                    strict_options_json->'no_giro_appeso',
                    'false'::jsonb
                )
            )
        )
        WHERE strict_options_json ? 'no_giro_appeso'
    """)
    # Ripristina il DEFAULT col nome vecchio (matcha 0005).
    op.execute("""
        ALTER TABLE programma_materiale
        ALTER COLUMN strict_options_json SET DEFAULT '{
            "no_corse_residue": false,
            "no_overcapacity": false,
            "no_aggancio_non_validato": false,
            "no_orphan_blocks": false,
            "no_giro_non_chiuso_a_localita": false,
            "no_km_eccesso": false
        }'::jsonb
    """)

    # 4) km_max_ciclo
    op.execute(
        "ALTER TABLE programma_materiale "
        "DROP CONSTRAINT programma_materiale_km_max_ciclo_positivo"
    )
    op.execute("ALTER TABLE programma_materiale DROP COLUMN km_max_ciclo")

    # 3) Regola: ripristina NOT NULL su legacy + drop nuovi campi.
    # Per ripristinare NOT NULL servono valori non-null in tutte le righe.
    # Le righe create dopo 0007 con solo composizione_json possono avere
    # legacy NULL: fail-fast esplicito se così è (downgrade richiede pulizia).
    op.execute("""
        DO $$
        DECLARE n_legacy_null INTEGER;
        BEGIN
            SELECT COUNT(*) INTO n_legacy_null
            FROM programma_regola_assegnazione
            WHERE materiale_tipo_codice IS NULL OR numero_pezzi IS NULL;
            IF n_legacy_null > 0 THEN
                RAISE EXCEPTION 'Migration 0007 downgrade: % regole con '
                    'legacy NULL. Esegui prima il backfill manuale dai '
                    'campi composizione_json.', n_legacy_null;
            END IF;
        END $$;
    """)
    op.execute(
        "ALTER TABLE programma_regola_assegnazione "
        "ALTER COLUMN materiale_tipo_codice SET NOT NULL"
    )
    op.execute(
        "ALTER TABLE programma_regola_assegnazione "
        "ALTER COLUMN numero_pezzi SET NOT NULL"
    )
    op.execute(
        "ALTER TABLE programma_regola_assegnazione "
        "DROP COLUMN is_composizione_manuale"
    )
    op.execute(
        "ALTER TABLE programma_regola_assegnazione "
        "DROP COLUMN composizione_json"
    )

    # 2) materiale_accoppiamento_ammesso
    op.execute("DROP TABLE IF EXISTS materiale_accoppiamento_ammesso")

    # 1) localita_stazione_vicina
    op.execute("DROP INDEX IF EXISTS idx_localita_stazione_vicina_staz")
    op.execute("DROP INDEX IF EXISTS idx_localita_stazione_vicina_loc")
    op.execute("DROP TABLE IF EXISTS localita_stazione_vicina")
