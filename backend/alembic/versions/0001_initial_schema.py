"""0001 initial schema — 31 tabelle del modello dati v0.5

Riferimento: docs/SCHEMA-DATI-NATIVO.md (sezioni §3-§9).

Crea il database completo del programma in un colpo solo:
- Strato 0 anagrafica: azienda, stazione, materiale_tipo,
  localita_manutenzione (+dotazione), depot (+linee, materiali ammessi)
- Strato 1 corse LIV 1: corsa_commerciale, corsa_composizione,
  corsa_materiale_vuoto, corsa_import_run
- Strato 2 giro LIV 2: giro_materiale, versione_base_giro,
  giro_finestra_validita, giro_giornata, giro_variante, giro_blocco
- Strato 2bis revisioni: revisione_provvisoria,
  revisione_provvisoria_blocco, revisione_provvisoria_pdc
- Strato 3 turno PdC LIV 3: turno_pdc, turno_pdc_giornata,
  turno_pdc_blocco
- Strato 4 personale LIV 4: persona, assegnazione_giornata,
  indisponibilita_persona
- Strato 5 auth+audit: app_user, app_user_ruolo, notifica, audit_log

Plus indici secondari + estensione pg_trgm.

Revision ID: fea31638ebad
Revises:
Create Date: 2026-04-25 15:33:23.179662+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fea31638ebad"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # =================================================================
    # Estensioni
    # =================================================================
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # =================================================================
    # STRATO 0 — anagrafica
    # =================================================================
    op.execute("""
        CREATE TABLE azienda (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            codice VARCHAR(50) NOT NULL UNIQUE,
            nome TEXT NOT NULL,
            normativa_pdc_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            is_attiva BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT azienda_codice_format CHECK (codice ~ '^[a-z0-9_]+$')
        )
    """)

    op.execute("""
        CREATE TABLE stazione (
            codice VARCHAR(20) PRIMARY KEY,
            nome TEXT NOT NULL,
            nomi_alternativi_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            rete VARCHAR(10),
            is_sede_deposito BOOLEAN NOT NULL DEFAULT FALSE,
            azienda_id BIGINT NOT NULL REFERENCES azienda(id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT stazione_codice_format
                CHECK (codice ~ '^S[0-9]+$' OR codice ~ '^[A-Z]+$')
        )
    """)

    op.execute("""
        CREATE TABLE materiale_tipo (
            codice VARCHAR(50) PRIMARY KEY,
            nome_commerciale TEXT,
            famiglia TEXT,
            componenti_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            velocita_max_kmh INTEGER,
            posti_per_pezzo INTEGER,
            azienda_id BIGINT NOT NULL REFERENCES azienda(id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE localita_manutenzione (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            codice VARCHAR(80) NOT NULL UNIQUE,
            nome_canonico TEXT NOT NULL,
            nomi_alternativi_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            stazione_collegata_codice VARCHAR(20)
                REFERENCES stazione(codice) ON DELETE SET NULL,
            azienda_id BIGINT NOT NULL REFERENCES azienda(id) ON DELETE RESTRICT,
            is_pool_esterno BOOLEAN NOT NULL DEFAULT FALSE,
            azienda_proprietaria_esterna VARCHAR(100),
            is_attiva BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE localita_manutenzione_dotazione (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            localita_manutenzione_id BIGINT NOT NULL
                REFERENCES localita_manutenzione(id) ON DELETE CASCADE,
            materiale_tipo_codice VARCHAR(50) NOT NULL
                REFERENCES materiale_tipo(codice) ON DELETE RESTRICT,
            quantita INTEGER NOT NULL CHECK (quantita >= 0),
            famiglia_rotabile TEXT,
            note TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(localita_manutenzione_id, materiale_tipo_codice)
        )
    """)

    op.execute("""
        CREATE TABLE depot (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            codice VARCHAR(80) NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            azienda_id BIGINT NOT NULL REFERENCES azienda(id) ON DELETE RESTRICT,
            stazione_principale_codice VARCHAR(20)
                REFERENCES stazione(codice) ON DELETE SET NULL,
            tipi_personale_ammessi VARCHAR(20) NOT NULL DEFAULT 'PdC',
            is_attivo BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT depot_tipi_personale_check
                CHECK (tipi_personale_ammessi IN ('PdC', 'CT', 'ENTRAMBI'))
        )
    """)

    op.execute("""
        CREATE TABLE depot_linea_abilitata (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            depot_id BIGINT NOT NULL REFERENCES depot(id) ON DELETE CASCADE,
            stazione_a_codice VARCHAR(20) NOT NULL REFERENCES stazione(codice),
            stazione_b_codice VARCHAR(20) NOT NULL REFERENCES stazione(codice),
            UNIQUE(depot_id, stazione_a_codice, stazione_b_codice)
        )
    """)

    op.execute("""
        CREATE TABLE depot_materiale_abilitato (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            depot_id BIGINT NOT NULL REFERENCES depot(id) ON DELETE CASCADE,
            materiale_tipo_codice VARCHAR(50) NOT NULL
                REFERENCES materiale_tipo(codice) ON DELETE RESTRICT,
            UNIQUE(depot_id, materiale_tipo_codice)
        )
    """)

    # =================================================================
    # STRATO 1 — corse commerciali (LIV 1)
    # =================================================================
    op.execute("""
        CREATE TABLE corsa_import_run (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source_file TEXT NOT NULL,
            source_hash VARCHAR(64),
            n_corse INTEGER NOT NULL DEFAULT 0,
            n_corse_create INTEGER NOT NULL DEFAULT 0,
            n_corse_update INTEGER NOT NULL DEFAULT 0,
            azienda_id BIGINT NOT NULL REFERENCES azienda(id) ON DELETE RESTRICT,
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ,
            note TEXT
        )
    """)

    op.execute("""
        CREATE TABLE corsa_commerciale (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            azienda_id BIGINT NOT NULL REFERENCES azienda(id) ON DELETE RESTRICT,

            numero_treno VARCHAR(20) NOT NULL,
            rete VARCHAR(10),
            numero_treno_rfi VARCHAR(20),
            numero_treno_fn VARCHAR(20),
            categoria VARCHAR(20),
            codice_linea VARCHAR(20),
            direttrice TEXT,

            codice_origine VARCHAR(20) NOT NULL REFERENCES stazione(codice),
            codice_destinazione VARCHAR(20) NOT NULL REFERENCES stazione(codice),
            codice_inizio_cds VARCHAR(20) REFERENCES stazione(codice),
            codice_fine_cds VARCHAR(20) REFERENCES stazione(codice),

            ora_partenza TIME NOT NULL,
            ora_arrivo TIME NOT NULL,
            ora_inizio_cds TIME,
            ora_fine_cds TIME,
            min_tratta INTEGER,
            min_cds INTEGER,
            km_tratta NUMERIC(10,3),
            km_cds NUMERIC(10,3),

            valido_da DATE NOT NULL,
            valido_a DATE NOT NULL,
            codice_periodicita TEXT,
            periodicita_breve TEXT,
            is_treno_garantito_feriale BOOLEAN NOT NULL DEFAULT FALSE,
            is_treno_garantito_festivo BOOLEAN NOT NULL DEFAULT FALSE,
            fascia_oraria VARCHAR(10),

            giorni_per_mese_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            valido_in_date_json JSONB NOT NULL DEFAULT '[]'::jsonb,

            totale_km NUMERIC(12,3),
            totale_minuti INTEGER,
            posti_km NUMERIC(15,3),
            velocita_commerciale NUMERIC(8,4),

            import_source TEXT NOT NULL DEFAULT 'pde',
            import_run_id BIGINT REFERENCES corsa_import_run(id) ON DELETE SET NULL,
            imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),

            UNIQUE(azienda_id, numero_treno, valido_da)
        )
    """)

    op.execute("""
        CREATE TABLE corsa_composizione (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            corsa_commerciale_id BIGINT NOT NULL
                REFERENCES corsa_commerciale(id) ON DELETE CASCADE,
            stagione VARCHAR(20) NOT NULL,
            giorno_tipo VARCHAR(20) NOT NULL,
            categoria_posti TEXT,
            is_doppia_composizione BOOLEAN NOT NULL DEFAULT FALSE,
            tipologia_treno TEXT,
            vincolo_dichiarato TEXT,
            categoria_bici VARCHAR(10),
            categoria_prm VARCHAR(10),
            UNIQUE(corsa_commerciale_id, stagione, giorno_tipo),
            CONSTRAINT corsa_composizione_stagione_check
                CHECK (stagione IN ('invernale', 'estiva', 'agosto')),
            CONSTRAINT corsa_composizione_giorno_check
                CHECK (giorno_tipo IN ('feriale', 'sabato', 'festivo'))
        )
    """)

    op.execute("""
        CREATE TABLE corsa_materiale_vuoto (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            azienda_id BIGINT NOT NULL REFERENCES azienda(id) ON DELETE RESTRICT,
            numero_treno_vuoto VARCHAR(20) NOT NULL,
            codice_origine VARCHAR(20) NOT NULL REFERENCES stazione(codice),
            codice_destinazione VARCHAR(20) NOT NULL REFERENCES stazione(codice),
            ora_partenza TIME NOT NULL,
            ora_arrivo TIME NOT NULL,
            min_tratta INTEGER,
            km_tratta NUMERIC(10,3),
            origine VARCHAR(40) NOT NULL,
            giro_materiale_id BIGINT,
            valido_in_date_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            valido_da DATE,
            valido_a DATE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT corsa_materiale_vuoto_origine_check
                CHECK (origine IN (
                    'importato_pde', 'generato_da_giro_materiale', 'manuale'
                ))
        )
    """)

    # =================================================================
    # STRATO 2 — giro materiale (LIV 2)
    # =================================================================
    op.execute("""
        CREATE TABLE giro_materiale (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            azienda_id BIGINT NOT NULL REFERENCES azienda(id) ON DELETE RESTRICT,
            numero_turno VARCHAR(20) NOT NULL,
            validita_codice VARCHAR(10),
            tipo_materiale TEXT NOT NULL,
            descrizione_materiale TEXT,
            materiale_tipo_codice VARCHAR(50) REFERENCES materiale_tipo(codice),
            numero_giornate INTEGER NOT NULL CHECK (numero_giornate >= 1),
            km_media_giornaliera NUMERIC(10,2),
            km_media_annua NUMERIC(12,2),
            posti_1cl INTEGER NOT NULL DEFAULT 0,
            posti_2cl INTEGER NOT NULL DEFAULT 0,
            localita_manutenzione_partenza_id BIGINT NOT NULL
                REFERENCES localita_manutenzione(id) ON DELETE RESTRICT,
            localita_manutenzione_arrivo_id BIGINT NOT NULL
                REFERENCES localita_manutenzione(id) ON DELETE RESTRICT,
            stato VARCHAR(20) NOT NULL DEFAULT 'bozza',
            generation_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(azienda_id, numero_turno),
            CONSTRAINT giro_materiale_stato_check
                CHECK (stato IN ('bozza', 'pubblicato', 'archiviato'))
        )
    """)

    # FK circolare: corsa_materiale_vuoto.giro_materiale_id
    op.execute("""
        ALTER TABLE corsa_materiale_vuoto
            ADD CONSTRAINT corsa_materiale_vuoto_giro_fk
            FOREIGN KEY (giro_materiale_id)
            REFERENCES giro_materiale(id) ON DELETE SET NULL
    """)

    op.execute("""
        CREATE TABLE versione_base_giro (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            giro_materiale_id BIGINT NOT NULL UNIQUE
                REFERENCES giro_materiale(id) ON DELETE CASCADE,
            data_deposito DATE,
            source_file TEXT,
            imported_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE giro_finestra_validita (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            versione_base_giro_id BIGINT NOT NULL
                REFERENCES versione_base_giro(id) ON DELETE CASCADE,
            valido_da DATE NOT NULL,
            valido_a DATE NOT NULL,
            seq INTEGER NOT NULL DEFAULT 1,
            UNIQUE(versione_base_giro_id, seq),
            CONSTRAINT giro_finestra_validita_range
                CHECK (valido_da <= valido_a)
        )
    """)

    op.execute("""
        CREATE TABLE giro_giornata (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            giro_materiale_id BIGINT NOT NULL
                REFERENCES giro_materiale(id) ON DELETE CASCADE,
            numero_giornata INTEGER NOT NULL CHECK (numero_giornata >= 1),
            UNIQUE(giro_materiale_id, numero_giornata)
        )
    """)

    op.execute("""
        CREATE TABLE giro_variante (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            giro_giornata_id BIGINT NOT NULL
                REFERENCES giro_giornata(id) ON DELETE CASCADE,
            variant_index INTEGER NOT NULL DEFAULT 0,
            validita_testo TEXT NOT NULL DEFAULT 'GG',
            validita_dates_apply_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            validita_dates_skip_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            UNIQUE(giro_giornata_id, variant_index)
        )
    """)

    op.execute("""
        CREATE TABLE giro_blocco (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            giro_variante_id BIGINT NOT NULL
                REFERENCES giro_variante(id) ON DELETE CASCADE,
            seq INTEGER NOT NULL CHECK (seq >= 1),
            tipo_blocco VARCHAR(40) NOT NULL,
            corsa_commerciale_id BIGINT
                REFERENCES corsa_commerciale(id) ON DELETE RESTRICT,
            corsa_materiale_vuoto_id BIGINT
                REFERENCES corsa_materiale_vuoto(id) ON DELETE RESTRICT,
            stazione_da_codice VARCHAR(20) REFERENCES stazione(codice),
            stazione_a_codice VARCHAR(20) REFERENCES stazione(codice),
            ora_inizio TIME,
            ora_fine TIME,
            descrizione TEXT,
            UNIQUE(giro_variante_id, seq),
            CONSTRAINT giro_blocco_tipo_check
                CHECK (tipo_blocco IN (
                    'corsa_commerciale', 'materiale_vuoto',
                    'sosta_disponibile', 'manovra'
                )),
            CONSTRAINT giro_blocco_link_coerente
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
        )
    """)

    # =================================================================
    # STRATO 2bis — revisioni provvisorie
    # =================================================================
    op.execute("""
        CREATE TABLE revisione_provvisoria (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            giro_materiale_id BIGINT NOT NULL
                REFERENCES giro_materiale(id) ON DELETE CASCADE,
            codice_revisione VARCHAR(50) NOT NULL,
            causa VARCHAR(40) NOT NULL,
            comunicazione_esterna_rif TEXT,
            descrizione_evento TEXT NOT NULL,
            finestra_da DATE NOT NULL,
            finestra_a DATE NOT NULL,
            data_pubblicazione DATE NOT NULL DEFAULT CURRENT_DATE,
            source_file TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT revisione_provvisoria_causa_check
                CHECK (causa IN (
                    'interruzione_rfi', 'sciopero',
                    'manutenzione_straordinaria', 'evento_speciale', 'altro'
                )),
            CONSTRAINT revisione_provvisoria_finestra_range
                CHECK (finestra_da <= finestra_a),
            UNIQUE(giro_materiale_id, codice_revisione)
        )
    """)

    op.execute("""
        CREATE TABLE revisione_provvisoria_blocco (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            revisione_id BIGINT NOT NULL
                REFERENCES revisione_provvisoria(id) ON DELETE CASCADE,
            operazione VARCHAR(20) NOT NULL,
            giro_blocco_originale_id BIGINT REFERENCES giro_blocco(id) ON DELETE SET NULL,
            seq INTEGER,
            tipo_blocco VARCHAR(40),
            corsa_commerciale_id BIGINT REFERENCES corsa_commerciale(id),
            corsa_materiale_vuoto_id BIGINT REFERENCES corsa_materiale_vuoto(id),
            stazione_da_codice VARCHAR(20) REFERENCES stazione(codice),
            stazione_a_codice VARCHAR(20) REFERENCES stazione(codice),
            ora_inizio TIME,
            ora_fine TIME,
            CONSTRAINT revisione_blocco_op_check
                CHECK (operazione IN ('modifica', 'aggiungi', 'cancella'))
        )
    """)

    # =================================================================
    # STRATO 3 — turno PdC (LIV 3)
    # =================================================================
    op.execute("""
        CREATE TABLE turno_pdc (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            azienda_id BIGINT NOT NULL REFERENCES azienda(id) ON DELETE RESTRICT,
            codice VARCHAR(50) NOT NULL,
            impianto VARCHAR(80) NOT NULL,
            profilo VARCHAR(40) NOT NULL DEFAULT 'Condotta',
            ciclo_giorni INTEGER NOT NULL DEFAULT 7
                CHECK (ciclo_giorni BETWEEN 1 AND 14),
            valido_da DATE NOT NULL,
            valido_a DATE,
            source_file TEXT,
            generation_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            stato VARCHAR(20) NOT NULL DEFAULT 'bozza',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT turno_pdc_stato_check
                CHECK (stato IN ('bozza', 'pubblicato', 'archiviato')),
            UNIQUE(azienda_id, codice, valido_da)
        )
    """)

    # FK cross-table per revisione_provvisoria_pdc
    op.execute("""
        CREATE TABLE revisione_provvisoria_pdc (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            revisione_giro_id BIGINT NOT NULL
                REFERENCES revisione_provvisoria(id) ON DELETE CASCADE,
            turno_pdc_id BIGINT NOT NULL
                REFERENCES turno_pdc(id) ON DELETE CASCADE,
            codice_revisione VARCHAR(50) NOT NULL,
            finestra_da DATE NOT NULL,
            finestra_a DATE NOT NULL,
            UNIQUE(revisione_giro_id, turno_pdc_id)
        )
    """)

    op.execute("""
        CREATE TABLE turno_pdc_giornata (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            turno_pdc_id BIGINT NOT NULL
                REFERENCES turno_pdc(id) ON DELETE CASCADE,
            numero_giornata INTEGER NOT NULL
                CHECK (numero_giornata BETWEEN 1 AND 14),
            variante_calendario VARCHAR(20) NOT NULL DEFAULT 'LMXGV',
            stazione_inizio VARCHAR(20) REFERENCES stazione(codice),
            stazione_fine VARCHAR(20) REFERENCES stazione(codice),
            inizio_prestazione TIME,
            fine_prestazione TIME,
            prestazione_min INTEGER NOT NULL DEFAULT 0,
            condotta_min INTEGER NOT NULL DEFAULT 0,
            refezione_min INTEGER NOT NULL DEFAULT 0,
            km INTEGER NOT NULL DEFAULT 0,
            is_notturno BOOLEAN NOT NULL DEFAULT FALSE,
            is_riposo BOOLEAN NOT NULL DEFAULT FALSE,
            is_disponibile BOOLEAN NOT NULL DEFAULT FALSE,
            riposo_min INTEGER NOT NULL DEFAULT 0,
            UNIQUE(turno_pdc_id, numero_giornata, variante_calendario)
        )
    """)

    op.execute("""
        CREATE TABLE turno_pdc_blocco (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            turno_pdc_giornata_id BIGINT NOT NULL
                REFERENCES turno_pdc_giornata(id) ON DELETE CASCADE,
            seq INTEGER NOT NULL CHECK (seq >= 1),
            tipo_evento VARCHAR(20) NOT NULL,
            corsa_commerciale_id BIGINT
                REFERENCES corsa_commerciale(id) ON DELETE RESTRICT,
            corsa_materiale_vuoto_id BIGINT
                REFERENCES corsa_materiale_vuoto(id) ON DELETE RESTRICT,
            giro_blocco_id BIGINT REFERENCES giro_blocco(id) ON DELETE SET NULL,
            stazione_da_codice VARCHAR(20) REFERENCES stazione(codice),
            stazione_a_codice VARCHAR(20) REFERENCES stazione(codice),
            ora_inizio TIME,
            ora_fine TIME,
            durata_min INTEGER,
            is_accessori_maggiorati BOOLEAN NOT NULL DEFAULT FALSE,
            cv_parent_blocco_id BIGINT
                REFERENCES turno_pdc_blocco(id) ON DELETE SET NULL,
            accessori_note TEXT,
            fonte_orario VARCHAR(20) NOT NULL DEFAULT 'parsed',
            UNIQUE(turno_pdc_giornata_id, seq),
            CONSTRAINT turno_pdc_blocco_tipo_check
                CHECK (tipo_evento IN (
                    'CONDOTTA', 'VETTURA', 'REFEZ', 'ACCp', 'ACCa',
                    'CVp', 'CVa', 'PK', 'SCOMP', 'PRESA', 'FINE'
                ))
        )
    """)

    # =================================================================
    # STRATO 4 — anagrafica personale (LIV 4)
    # =================================================================
    op.execute("""
        CREATE TABLE persona (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            azienda_id BIGINT NOT NULL REFERENCES azienda(id) ON DELETE RESTRICT,
            codice_dipendente VARCHAR(40) NOT NULL,
            nome TEXT NOT NULL,
            cognome TEXT NOT NULL,
            profilo VARCHAR(20) NOT NULL DEFAULT 'PdC',
            sede_residenza_id BIGINT REFERENCES depot(id) ON DELETE SET NULL,
            qualifiche_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            is_matricola_attiva BOOLEAN NOT NULL DEFAULT TRUE,
            data_assunzione DATE,
            user_id BIGINT,
            email TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(azienda_id, codice_dipendente),
            CONSTRAINT persona_profilo_check
                CHECK (profilo IN ('PdC', 'CT', 'MANOVRA', 'COORD'))
        )
    """)

    op.execute("""
        CREATE TABLE assegnazione_giornata (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            persona_id BIGINT NOT NULL REFERENCES persona(id) ON DELETE RESTRICT,
            data DATE NOT NULL,
            turno_pdc_giornata_id BIGINT
                REFERENCES turno_pdc_giornata(id) ON DELETE SET NULL,
            stato VARCHAR(20) NOT NULL DEFAULT 'pianificato',
            sostituisce_persona_id BIGINT REFERENCES persona(id) ON DELETE SET NULL,
            note TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(persona_id, data),
            CONSTRAINT assegnazione_stato_check
                CHECK (stato IN (
                    'pianificato', 'confermato', 'sostituito', 'annullato'
                ))
        )
    """)

    op.execute("""
        CREATE TABLE indisponibilita_persona (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            persona_id BIGINT NOT NULL REFERENCES persona(id) ON DELETE CASCADE,
            tipo VARCHAR(20) NOT NULL,
            data_inizio DATE NOT NULL,
            data_fine DATE NOT NULL,
            is_approvato BOOLEAN NOT NULL DEFAULT FALSE,
            approvato_da_user_id BIGINT,
            approvato_at TIMESTAMPTZ,
            note TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT indisponibilita_tipo_check
                CHECK (tipo IN (
                    'ferie', 'malattia', 'congedo', 'ROL',
                    'sciopero', 'formazione'
                )),
            CONSTRAINT indisponibilita_range_check
                CHECK (data_inizio <= data_fine)
        )
    """)

    # =================================================================
    # STRATO 5 — auth + audit
    # =================================================================
    op.execute("""
        CREATE TABLE app_user (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            username VARCHAR(80) NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            is_admin BOOLEAN NOT NULL DEFAULT FALSE,
            persona_id BIGINT REFERENCES persona(id) ON DELETE SET NULL,
            azienda_id BIGINT NOT NULL REFERENCES azienda(id) ON DELETE RESTRICT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            last_login_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # FK cross-table: persona.user_id → app_user(id)
    op.execute("""
        ALTER TABLE persona
            ADD CONSTRAINT persona_user_fk
            FOREIGN KEY (user_id) REFERENCES app_user(id) ON DELETE SET NULL
    """)

    # FK cross-table: indisponibilita_persona.approvato_da_user_id → app_user(id)
    op.execute("""
        ALTER TABLE indisponibilita_persona
            ADD CONSTRAINT indisponibilita_approvatore_fk
            FOREIGN KEY (approvato_da_user_id)
            REFERENCES app_user(id) ON DELETE SET NULL
    """)

    op.execute("""
        CREATE TABLE app_user_ruolo (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            app_user_id BIGINT NOT NULL
                REFERENCES app_user(id) ON DELETE CASCADE,
            ruolo VARCHAR(40) NOT NULL,
            UNIQUE(app_user_id, ruolo),
            CONSTRAINT app_user_ruolo_check
                CHECK (ruolo IN (
                    'PIANIFICATORE_GIRO', 'PIANIFICATORE_PDC',
                    'MANUTENZIONE', 'GESTIONE_PERSONALE',
                    'PERSONALE_PDC', 'ADMIN'
                ))
        )
    """)

    op.execute("""
        CREATE TABLE notifica (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            destinatario_user_id BIGINT NOT NULL
                REFERENCES app_user(id) ON DELETE CASCADE,
            tipo VARCHAR(60) NOT NULL,
            titolo TEXT NOT NULL,
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            is_letta BOOLEAN NOT NULL DEFAULT FALSE,
            letta_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE audit_log (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            actor_user_id BIGINT REFERENCES app_user(id) ON DELETE SET NULL,
            azione VARCHAR(60) NOT NULL,
            target_tipo VARCHAR(60),
            target_id BIGINT,
            payload_json JSONB,
            ip_address INET,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # =================================================================
    # Indici secondari (FK + query frequenti)
    # =================================================================
    op.execute("CREATE INDEX idx_corsa_numero ON corsa_commerciale(numero_treno)")
    op.execute(
        "CREATE INDEX idx_corsa_origine_partenza "
        "ON corsa_commerciale(codice_origine, ora_partenza)"
    )
    op.execute(
        "CREATE INDEX idx_corsa_destinazione_arrivo "
        "ON corsa_commerciale(codice_destinazione, ora_arrivo)"
    )
    op.execute(
        "CREATE INDEX idx_corsa_validita ON corsa_commerciale(valido_da, valido_a)"
    )
    op.execute("CREATE INDEX idx_corsa_azienda ON corsa_commerciale(azienda_id)")
    op.execute(
        "CREATE INDEX idx_corsa_valido_in_date_gin "
        "ON corsa_commerciale USING GIN (valido_in_date_json)"
    )

    op.execute(
        "CREATE INDEX idx_corsa_composizione_corsa "
        "ON corsa_composizione(corsa_commerciale_id)"
    )

    op.execute(
        "CREATE INDEX idx_corsa_vuoto_numero ON corsa_materiale_vuoto(numero_treno_vuoto)"
    )
    op.execute(
        "CREATE INDEX idx_corsa_vuoto_giro ON corsa_materiale_vuoto(giro_materiale_id)"
    )

    op.execute("CREATE INDEX idx_giro_azienda ON giro_materiale(azienda_id)")
    op.execute(
        "CREATE INDEX idx_giro_localita_partenza "
        "ON giro_materiale(localita_manutenzione_partenza_id)"
    )
    op.execute("CREATE INDEX idx_giro_stato ON giro_materiale(stato)")

    op.execute(
        "CREATE INDEX idx_finestra_versione ON giro_finestra_validita(versione_base_giro_id)"
    )
    op.execute(
        "CREATE INDEX idx_finestra_dates ON giro_finestra_validita(valido_da, valido_a)"
    )

    op.execute("CREATE INDEX idx_giornata_giro ON giro_giornata(giro_materiale_id)")
    op.execute("CREATE INDEX idx_variante_giornata ON giro_variante(giro_giornata_id)")
    op.execute("CREATE INDEX idx_blocco_variante ON giro_blocco(giro_variante_id)")
    op.execute("CREATE INDEX idx_blocco_corsa ON giro_blocco(corsa_commerciale_id)")

    op.execute(
        "CREATE INDEX idx_revisione_giro ON revisione_provvisoria(giro_materiale_id)"
    )
    op.execute(
        "CREATE INDEX idx_revisione_finestra "
        "ON revisione_provvisoria(finestra_da, finestra_a)"
    )
    op.execute(
        "CREATE INDEX idx_rev_blocco_revisione ON revisione_provvisoria_blocco(revisione_id)"
    )
    op.execute(
        "CREATE INDEX idx_rev_pdc_revisione ON revisione_provvisoria_pdc(revisione_giro_id)"
    )
    op.execute("CREATE INDEX idx_rev_pdc_turno ON revisione_provvisoria_pdc(turno_pdc_id)")

    op.execute("CREATE INDEX idx_turno_codice ON turno_pdc(codice)")
    op.execute("CREATE INDEX idx_turno_impianto ON turno_pdc(impianto)")
    op.execute("CREATE INDEX idx_turno_validita ON turno_pdc(valido_da, valido_a)")
    op.execute("CREATE INDEX idx_turno_azienda ON turno_pdc(azienda_id)")
    op.execute("CREATE INDEX idx_turno_stato ON turno_pdc(stato)")

    op.execute(
        "CREATE INDEX idx_giornata_pdc_turno ON turno_pdc_giornata(turno_pdc_id)"
    )
    op.execute(
        "CREATE INDEX idx_blocco_pdc_giornata ON turno_pdc_blocco(turno_pdc_giornata_id)"
    )
    op.execute(
        "CREATE INDEX idx_blocco_pdc_corsa ON turno_pdc_blocco(corsa_commerciale_id)"
    )
    op.execute(
        "CREATE INDEX idx_blocco_pdc_giro_blocco ON turno_pdc_blocco(giro_blocco_id)"
    )

    op.execute("CREATE INDEX idx_persona_codice ON persona(codice_dipendente)")
    op.execute("CREATE INDEX idx_persona_sede ON persona(sede_residenza_id)")
    op.execute("CREATE INDEX idx_persona_user ON persona(user_id)")
    op.execute(
        "CREATE INDEX idx_persona_cognome_trgm ON persona USING GIN (cognome gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX idx_persona_nome_trgm ON persona USING GIN (nome gin_trgm_ops)"
    )

    op.execute(
        "CREATE INDEX idx_assegnazione_persona ON assegnazione_giornata(persona_id)"
    )
    op.execute("CREATE INDEX idx_assegnazione_data ON assegnazione_giornata(data)")
    op.execute(
        "CREATE INDEX idx_assegnazione_giornata_pdc "
        "ON assegnazione_giornata(turno_pdc_giornata_id)"
    )

    op.execute(
        "CREATE INDEX idx_indisponibilita_persona ON indisponibilita_persona(persona_id)"
    )
    op.execute(
        "CREATE INDEX idx_indisponibilita_range "
        "ON indisponibilita_persona(data_inizio, data_fine)"
    )

    op.execute("CREATE INDEX idx_user_persona ON app_user(persona_id)")
    op.execute("CREATE INDEX idx_user_ruolo_user ON app_user_ruolo(app_user_id)")
    op.execute(
        "CREATE INDEX idx_notifica_destinatario_letta "
        "ON notifica(destinatario_user_id, is_letta)"
    )
    op.execute("CREATE INDEX idx_audit_target ON audit_log(target_tipo, target_id)")
    op.execute(
        "CREATE INDEX idx_audit_actor ON audit_log(actor_user_id, created_at)"
    )


def downgrade() -> None:
    """Drop di tutto in ordine inverso (rispetta FK).

    Usato in test/CI per reset rapido. Non chiamato in prod.
    """
    # FK cross-table prima
    op.execute("ALTER TABLE persona DROP CONSTRAINT IF EXISTS persona_user_fk")
    op.execute(
        "ALTER TABLE indisponibilita_persona "
        "DROP CONSTRAINT IF EXISTS indisponibilita_approvatore_fk"
    )
    op.execute(
        "ALTER TABLE corsa_materiale_vuoto "
        "DROP CONSTRAINT IF EXISTS corsa_materiale_vuoto_giro_fk"
    )

    # Strato 5
    op.execute("DROP TABLE IF EXISTS audit_log CASCADE")
    op.execute("DROP TABLE IF EXISTS notifica CASCADE")
    op.execute("DROP TABLE IF EXISTS app_user_ruolo CASCADE")
    op.execute("DROP TABLE IF EXISTS app_user CASCADE")

    # Strato 4
    op.execute("DROP TABLE IF EXISTS indisponibilita_persona CASCADE")
    op.execute("DROP TABLE IF EXISTS assegnazione_giornata CASCADE")
    op.execute("DROP TABLE IF EXISTS persona CASCADE")

    # Strato 3
    op.execute("DROP TABLE IF EXISTS turno_pdc_blocco CASCADE")
    op.execute("DROP TABLE IF EXISTS turno_pdc_giornata CASCADE")
    op.execute("DROP TABLE IF EXISTS revisione_provvisoria_pdc CASCADE")
    op.execute("DROP TABLE IF EXISTS turno_pdc CASCADE")

    # Strato 2bis
    op.execute("DROP TABLE IF EXISTS revisione_provvisoria_blocco CASCADE")
    op.execute("DROP TABLE IF EXISTS revisione_provvisoria CASCADE")

    # Strato 2
    op.execute("DROP TABLE IF EXISTS giro_blocco CASCADE")
    op.execute("DROP TABLE IF EXISTS giro_variante CASCADE")
    op.execute("DROP TABLE IF EXISTS giro_giornata CASCADE")
    op.execute("DROP TABLE IF EXISTS giro_finestra_validita CASCADE")
    op.execute("DROP TABLE IF EXISTS versione_base_giro CASCADE")
    op.execute("DROP TABLE IF EXISTS giro_materiale CASCADE")

    # Strato 1
    op.execute("DROP TABLE IF EXISTS corsa_materiale_vuoto CASCADE")
    op.execute("DROP TABLE IF EXISTS corsa_composizione CASCADE")
    op.execute("DROP TABLE IF EXISTS corsa_commerciale CASCADE")
    op.execute("DROP TABLE IF EXISTS corsa_import_run CASCADE")

    # Strato 0
    op.execute("DROP TABLE IF EXISTS depot_materiale_abilitato CASCADE")
    op.execute("DROP TABLE IF EXISTS depot_linea_abilitata CASCADE")
    op.execute("DROP TABLE IF EXISTS depot CASCADE")
    op.execute("DROP TABLE IF EXISTS localita_manutenzione_dotazione CASCADE")
    op.execute("DROP TABLE IF EXISTS localita_manutenzione CASCADE")
    op.execute("DROP TABLE IF EXISTS materiale_tipo CASCADE")
    op.execute("DROP TABLE IF EXISTS stazione CASCADE")
    op.execute("DROP TABLE IF EXISTS azienda CASCADE")

    _ = sa  # keep import for autogenerated migrations consistency
