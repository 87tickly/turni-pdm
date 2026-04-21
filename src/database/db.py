"""
Database duale SQLite / PostgreSQL per archiviazione treni e turni materiale.

Se la variabile d'ambiente DATABASE_URL e' presente si usa PostgreSQL (psycopg2),
altrimenti si usa SQLite come fallback locale.
"""

import json
import os
import sqlite3
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class TrainSegment:
    id: Optional[int]
    train_id: str          # Puo' contenere piu' numeri separati da "/"
    from_station: str
    dep_time: str          # HH:MM
    to_station: str
    arr_time: str          # HH:MM
    material_turn_id: Optional[int]
    day_index: int
    seq: int
    confidence: float
    raw_text: str
    source_page: int
    is_deadhead: bool = False
    is_accessory: bool = False   # primo/ultimo segmento del giorno
    segment_kind: str = "train"  # 'train' | 'cvl_cb'

    @property
    def duration_min(self) -> int:
        dh, dm = map(int, self.dep_time.split(":"))
        ah, am = map(int, self.arr_time.split(":"))
        dep_total = dh * 60 + dm
        arr_total = ah * 60 + am
        if arr_total < dep_total:
            arr_total += 24 * 60
        return arr_total - dep_total


@dataclass
class MaterialTurn:
    id: Optional[int]
    turn_number: str
    source_file: str
    total_segments: int


@dataclass
class NonTrainEvent:
    id: Optional[int]
    event_type: str        # MEAL, ACCESSORY, EXTRA, OVERNIGHT_FR, REST
    start_time: Optional[str]
    end_time: Optional[str]
    duration_min: int
    description: str
    day_index: int


DB_DEFAULT_PATH = "turni.db"


class Database:
    def __init__(self, db_path: str = DB_DEFAULT_PATH):
        self.db_path = db_path
        database_url = os.environ.get("DATABASE_URL")

        if database_url:
            # ── PostgreSQL ──
            import psycopg2
            import psycopg2.extras
            self.is_pg = True
            self.conn = psycopg2.connect(database_url)
            self.conn.autocommit = False
        else:
            # ── SQLite ──
            self.is_pg = False
            self.conn = sqlite3.connect(db_path)
            self.conn.row_factory = sqlite3.Row

        self._create_tables()

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------
    def _q(self, sql: str) -> str:
        """Converte placeholder ? -> %s per PostgreSQL."""
        if self.is_pg:
            return sql.replace("?", "%s")
        return sql

    def _cursor(self):
        """Restituisce un cursore: RealDictCursor per PG, normale per SQLite."""
        if self.is_pg:
            import psycopg2.extras
            return self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        return self.conn.cursor()

    def _dict(self, row) -> Optional[dict]:
        """Converte una riga in dict (gestisce sqlite3.Row e RealDictRow)."""
        if row is None:
            return None
        if self.is_pg:
            return dict(row)
        return dict(row)

    def _lastrowid(self, cur, sql: str, params: tuple) -> int:
        """Esegue INSERT e restituisce l'ID generato.
        Per PostgreSQL appende RETURNING id; per SQLite usa lastrowid."""
        if self.is_pg:
            cur.execute(self._q(sql) + " RETURNING id", params)
            return cur.fetchone()["id"]
        else:
            cur.execute(sql, params)
            return cur.lastrowid

    # ------------------------------------------------------------------
    # TABLE CREATION
    # ------------------------------------------------------------------
    def _create_tables(self):
        cur = self._cursor()

        if self.is_pg:
            pk = "SERIAL PRIMARY KEY"
        else:
            pk = "INTEGER PRIMARY KEY AUTOINCREMENT"

        # -- material_turn
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS material_turn (
                id {pk},
                turn_number TEXT NOT NULL,
                source_file TEXT NOT NULL,
                total_segments INTEGER DEFAULT 0,
                material_type TEXT DEFAULT ''
            )
        """)

        # -- train_segment
        # NB: train_id puo' contenere piu' numeri separati da "/"
        #     (es. "3085/3086") quando uno stesso convoglio/barra rossa
        #     cambia numero a meta' strada senza cambio materiale.
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS train_segment (
                id {pk},
                train_id TEXT NOT NULL,
                from_station TEXT NOT NULL,
                dep_time TEXT NOT NULL,
                to_station TEXT NOT NULL,
                arr_time TEXT NOT NULL,
                material_turn_id INTEGER,
                day_index INTEGER DEFAULT 0,
                seq INTEGER DEFAULT 0,
                confidence REAL DEFAULT 1.0,
                raw_text TEXT DEFAULT '',
                source_page INTEGER DEFAULT 0,
                is_deadhead INTEGER DEFAULT 0,
                is_accessory INTEGER DEFAULT 0,
                segment_kind TEXT DEFAULT 'train',
                FOREIGN KEY (material_turn_id) REFERENCES material_turn(id)
            )
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_train_id ON train_segment(train_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_from_dep ON train_segment(from_station, dep_time)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_to_arr ON train_segment(to_station, arr_time)")

        # -- non_train_event
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS non_train_event (
                id {pk},
                event_type TEXT NOT NULL,
                start_time TEXT,
                end_time TEXT,
                duration_min INTEGER DEFAULT 0,
                description TEXT DEFAULT '',
                day_index INTEGER DEFAULT 0
            )
        """)

        # -- day_variant
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS day_variant (
                id {pk},
                day_index INTEGER NOT NULL,
                material_turn_id INTEGER,
                validity_text TEXT NOT NULL DEFAULT 'GG',
                UNIQUE(day_index, material_turn_id),
                FOREIGN KEY (material_turn_id) REFERENCES material_turn(id)
            )
        """)

        # -- saved_shift
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS saved_shift (
                id {pk},
                name TEXT NOT NULL,
                deposito TEXT DEFAULT '',
                day_type TEXT DEFAULT 'LV',
                created_at TEXT NOT NULL,
                train_ids TEXT NOT NULL,
                deadhead_ids TEXT DEFAULT '[]',
                prestazione_min INTEGER DEFAULT 0,
                condotta_min INTEGER DEFAULT 0,
                meal_min INTEGER DEFAULT 0,
                accessori_min INTEGER DEFAULT 0,
                extra_min INTEGER DEFAULT 0,
                is_fr INTEGER DEFAULT 0,
                last_station TEXT DEFAULT '',
                violations TEXT DEFAULT '[]',
                accessory_type TEXT DEFAULT 'standard',
                presentation_time TEXT DEFAULT '',
                end_time TEXT DEFAULT '',
                user_id INTEGER DEFAULT NULL
            )
        """)

        # -- weekly_shift
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS weekly_shift (
                id {pk},
                name TEXT NOT NULL,
                deposito TEXT NOT NULL,
                created_at TEXT NOT NULL,
                num_days INTEGER DEFAULT 5,
                weekly_prestazione_min INTEGER DEFAULT 0,
                weekly_condotta_min INTEGER DEFAULT 0,
                weighted_hours_per_day REAL DEFAULT 0,
                accessory_type TEXT DEFAULT 'standard',
                notes TEXT DEFAULT '',
                user_id INTEGER DEFAULT NULL
            )
        """)

        # -- shift_day_variant
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS shift_day_variant (
                id {pk},
                weekly_shift_id INTEGER NOT NULL,
                day_number INTEGER NOT NULL,
                variant_type TEXT NOT NULL DEFAULT 'LMXGV',
                day_type TEXT NOT NULL DEFAULT 'LV',
                train_ids TEXT NOT NULL DEFAULT '[]',
                prestazione_min INTEGER DEFAULT 0,
                condotta_min INTEGER DEFAULT 0,
                meal_min INTEGER DEFAULT 0,
                is_fr INTEGER DEFAULT 0,
                is_scomp INTEGER DEFAULT 0,
                scomp_duration_min INTEGER DEFAULT 0,
                last_station TEXT DEFAULT '',
                violations TEXT DEFAULT '[]',
                FOREIGN KEY (weekly_shift_id) REFERENCES weekly_shift(id) ON DELETE CASCADE
            )
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_sdv_weekly ON shift_day_variant(weekly_shift_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sdv_day ON shift_day_variant(weekly_shift_id, day_number)")

        # ── PdC schema v2 (turno Posto di Condotta, formato Trenord M704) ──
        # Rimuove le vecchie tabelle scheletro (pdc_turno/pdc_prog/pdc_prog_train)
        # che non conservavano il dettaglio Gantt dei blocchi.
        cur.execute("DROP TABLE IF EXISTS pdc_prog_train")
        cur.execute("DROP TABLE IF EXISTS pdc_prog")
        cur.execute("DROP TABLE IF EXISTS pdc_turno")

        # -- pdc_turn: un turno pubblicato (es. AROR_C a ARONA)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS pdc_turn (
                id {pk},
                codice TEXT NOT NULL,
                planning TEXT DEFAULT '',
                impianto TEXT NOT NULL,
                profilo TEXT DEFAULT 'Condotta',
                valid_from TEXT DEFAULT '',
                valid_to TEXT DEFAULT '',
                source_file TEXT DEFAULT '',
                imported_at TEXT DEFAULT ''
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pdc_turn_impianto ON pdc_turn(impianto)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pdc_turn_codice ON pdc_turn(codice)")

        # -- pdc_turn_day: una giornata del ciclo con periodicita' specifica
        #    chiave logica = (pdc_turn_id, day_number, periodicita)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS pdc_turn_day (
                id {pk},
                pdc_turn_id INTEGER NOT NULL,
                day_number INTEGER NOT NULL,
                periodicita TEXT NOT NULL DEFAULT 'LMXGVSD',
                start_time TEXT DEFAULT '',
                end_time TEXT DEFAULT '',
                lavoro_min INTEGER DEFAULT 0,
                condotta_min INTEGER DEFAULT 0,
                km INTEGER DEFAULT 0,
                notturno INTEGER DEFAULT 0,
                riposo_min INTEGER DEFAULT 0,
                is_disponibile INTEGER DEFAULT 0,
                FOREIGN KEY (pdc_turn_id) REFERENCES pdc_turn(id) ON DELETE CASCADE
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pdc_day_turn ON pdc_turn_day(pdc_turn_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pdc_day_num ON pdc_turn_day(pdc_turn_id, day_number)")

        # -- pdc_block: un blocco grafico del Gantt della giornata
        #    block_type: 'train' | 'coach_transfer' | 'cv_partenza' | 'cv_arrivo'
        #                | 'meal' | 'scomp' | 'available'
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS pdc_block (
                id {pk},
                pdc_turn_day_id INTEGER NOT NULL,
                seq INTEGER DEFAULT 0,
                block_type TEXT NOT NULL,
                train_id TEXT DEFAULT '',
                vettura_id TEXT DEFAULT '',
                from_station TEXT DEFAULT '',
                to_station TEXT DEFAULT '',
                start_time TEXT DEFAULT '',
                end_time TEXT DEFAULT '',
                accessori_maggiorati INTEGER DEFAULT 0,
                FOREIGN KEY (pdc_turn_day_id) REFERENCES pdc_turn_day(id) ON DELETE CASCADE
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pdc_block_day ON pdc_block(pdc_turn_day_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pdc_block_train ON pdc_block(train_id)")

        # -- pdc_train_periodicity: note periodicita' treni (pagina finale del turno)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS pdc_train_periodicity (
                id {pk},
                pdc_turn_id INTEGER NOT NULL,
                train_id TEXT NOT NULL,
                periodicita_text TEXT DEFAULT '',
                non_circola_dates TEXT DEFAULT '[]',
                circola_extra_dates TEXT DEFAULT '[]',
                FOREIGN KEY (pdc_turn_id) REFERENCES pdc_turn(id) ON DELETE CASCADE
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pdc_tp_turn ON pdc_train_periodicity(pdc_turn_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pdc_tp_train ON pdc_train_periodicity(train_id)")

        # -- users
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS users (
                id {pk},
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                last_login TEXT DEFAULT NULL
            )
        """)

        # ── Abilitazioni per deposito (PdC) ──
        # Linea: coppia di stazioni estremi del giro materiale,
        # normalizzata alfabeticamente (station_a < station_b).
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS depot_enabled_line (
                id {pk},
                deposito TEXT NOT NULL,
                station_a TEXT NOT NULL,
                station_b TEXT NOT NULL,
                UNIQUE(deposito, station_a, station_b)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_depot_enabled_line_depot ON depot_enabled_line(deposito)")

        # Materiale rotabile abilitato per deposito (es. E464N, ATR220, TSR).
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS depot_enabled_material (
                id {pk},
                deposito TEXT NOT NULL,
                material_type TEXT NOT NULL,
                UNIQUE(deposito, material_type)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_depot_enabled_material_depot ON depot_enabled_material(deposito)")

        self.conn.commit()

        # ── Migrazioni per colonne aggiunte dopo la prima release ──
        self._run_migration(
            "SELECT deadhead_ids FROM saved_shift LIMIT 1",
            "ALTER TABLE saved_shift ADD COLUMN deadhead_ids TEXT DEFAULT '[]'"
        )
        self._run_migration(
            "SELECT presentation_time FROM saved_shift LIMIT 1",
            [
                "ALTER TABLE saved_shift ADD COLUMN presentation_time TEXT DEFAULT ''",
                "ALTER TABLE saved_shift ADD COLUMN end_time TEXT DEFAULT ''",
            ]
        )
        self._run_migration(
            "SELECT user_id FROM saved_shift LIMIT 1",
            "ALTER TABLE saved_shift ADD COLUMN user_id INTEGER DEFAULT NULL"
        )
        self._run_migration(
            "SELECT user_id FROM weekly_shift LIMIT 1",
            "ALTER TABLE weekly_shift ADD COLUMN user_id INTEGER DEFAULT NULL"
        )

        # ── Tabella depot (multi-deposito) ──
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS depot (
                id {pk},
                code TEXT NOT NULL UNIQUE,
                display_name TEXT DEFAULT '',
                company TEXT DEFAULT 'trenord',
                active INTEGER DEFAULT 1
            )
        """)

        # Migrazioni: aggiunta depot_id alle tabelle esistenti
        self._run_migration(
            "SELECT depot_id FROM material_turn LIMIT 1",
            "ALTER TABLE material_turn ADD COLUMN depot_id INTEGER REFERENCES depot(id)"
        )
        # Migrazione: tipo materiale (codice locomotiva, es. E464N) per ogni giro
        self._run_migration(
            "SELECT material_type FROM material_turn LIMIT 1",
            "ALTER TABLE material_turn ADD COLUMN material_type TEXT DEFAULT ''"
        )

        # Migrazioni: marcatori segmento accessorio e tipologia (train/cvl_cb)
        self._run_migration(
            "SELECT is_accessory FROM train_segment LIMIT 1",
            "ALTER TABLE train_segment ADD COLUMN is_accessory INTEGER DEFAULT 0"
        )
        self._run_migration(
            "SELECT segment_kind FROM train_segment LIMIT 1",
            "ALTER TABLE train_segment ADD COLUMN segment_kind TEXT DEFAULT 'train'"
        )
        self._run_migration(
            "SELECT depot_id FROM saved_shift LIMIT 1",
            "ALTER TABLE saved_shift ADD COLUMN depot_id INTEGER REFERENCES depot(id)"
        )
        self._run_migration(
            "SELECT depot_id FROM weekly_shift LIMIT 1",
            "ALTER TABLE weekly_shift ADD COLUMN depot_id INTEGER REFERENCES depot(id)"
        )

        # ── PdC schema v2.1: versioning import + campi arricchiti (Fase 1) ──
        # Documentato in docs/schema-pdc.md
        #
        # Strategia sostituzione turni:
        #   ogni upload PDF crea un record in pdc_import. I turni precedenti
        #   aventi stesso (codice, impianto) vengono marcati come archiviati
        #   valorizzando pdc_turn.superseded_by_import_id. La UI mostra di
        #   default solo i turni attivi (superseded_by_import_id IS NULL).

        # Tabella pdc_import (IF NOT EXISTS → idempotente)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS pdc_import (
                id {pk},
                filename TEXT NOT NULL,
                data_stampa TEXT DEFAULT '',
                data_pubblicazione TEXT DEFAULT '',
                valido_dal TEXT DEFAULT '',
                valido_al TEXT DEFAULT '',
                n_turni INTEGER DEFAULT 0,
                n_pagine_pdf INTEGER DEFAULT 0,
                imported_at TEXT DEFAULT '',
                imported_by INTEGER DEFAULT NULL
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pdc_import_filename ON pdc_import(filename)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pdc_import_stampa ON pdc_import(data_stampa)")

        # Campi versioning su pdc_turn
        self._run_migration(
            "SELECT import_id FROM pdc_turn LIMIT 1",
            "ALTER TABLE pdc_turn ADD COLUMN import_id INTEGER DEFAULT NULL REFERENCES pdc_import(id)"
        )
        self._run_migration(
            "SELECT superseded_by_import_id FROM pdc_turn LIMIT 1",
            "ALTER TABLE pdc_turn ADD COLUMN superseded_by_import_id INTEGER DEFAULT NULL REFERENCES pdc_import(id)"
        )
        self._run_migration(
            "SELECT data_pubblicazione FROM pdc_turn LIMIT 1",
            "ALTER TABLE pdc_turn ADD COLUMN data_pubblicazione TEXT DEFAULT ''"
        )
        # Indice per la query "turni attivi"
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_pdc_turn_active "
            "ON pdc_turn(superseded_by_import_id, impianto, codice)"
        )

        # Campi capolinea giornata (ARON...ARON nel PDF)
        self._run_migration(
            "SELECT stazione_inizio FROM pdc_turn_day LIMIT 1",
            [
                "ALTER TABLE pdc_turn_day ADD COLUMN stazione_inizio TEXT DEFAULT ''",
                "ALTER TABLE pdc_turn_day ADD COLUMN stazione_fine TEXT DEFAULT ''",
            ]
        )

        # Campi arricchiti su pdc_block
        self._run_migration(
            "SELECT minuti_accessori FROM pdc_block LIMIT 1",
            "ALTER TABLE pdc_block ADD COLUMN minuti_accessori TEXT DEFAULT ''"
        )
        self._run_migration(
            "SELECT fonte_orario FROM pdc_block LIMIT 1",
            "ALTER TABLE pdc_block ADD COLUMN fonte_orario TEXT DEFAULT 'parsed'"
        )
        self._run_migration(
            "SELECT cv_parent_block_id FROM pdc_block LIMIT 1",
            "ALTER TABLE pdc_block ADD COLUMN cv_parent_block_id INTEGER DEFAULT NULL REFERENCES pdc_block(id)"
        )
        self._run_migration(
            "SELECT accessori_note FROM pdc_block LIMIT 1",
            "ALTER TABLE pdc_block ADD COLUMN accessori_note TEXT DEFAULT ''"
        )

        # Auto-seed depot dalla configurazione attiva
        self._seed_depots()

        # ── Admin seed ──
        self._seed_admin()

    def _run_migration(self, check_sql: str, alter_sqls):
        """Esegue una migrazione: prova check_sql, se fallisce esegue alter_sqls.
        Per PostgreSQL usa SAVEPOINT per evitare transaction abort."""
        if isinstance(alter_sqls, str):
            alter_sqls = [alter_sqls]
        try:
            if self.is_pg:
                self.conn.cursor().execute("SAVEPOINT migration_check")
            self.conn.cursor().execute(self._q(check_sql))
            if self.is_pg:
                self.conn.cursor().execute("RELEASE SAVEPOINT migration_check")
        except Exception:
            if self.is_pg:
                self.conn.cursor().execute("ROLLBACK TO SAVEPOINT migration_check")
                self.conn.cursor().execute("RELEASE SAVEPOINT migration_check")
            for sql in alter_sqls:
                self.conn.cursor().execute(self._q(sql))
            self.conn.commit()

    def _seed_depots(self):
        """Popola la tabella depot dalla configurazione aziendale attiva.
        Aggiunge solo i depositi mancanti, non rimuove quelli esistenti."""
        from config.loader import get_active_config
        cfg = get_active_config()
        cur = self._cursor()
        for code in cfg.depots:
            try:
                cur.execute(
                    self._q(
                        "INSERT INTO depot (code, display_name, company) "
                        "VALUES (?, ?, ?)"
                    ),
                    (code, code, cfg.company_code or cfg.company_name),
                )
            except Exception:
                pass  # UNIQUE constraint — deposito già presente
        self.conn.commit()

    def _seed_admin(self):
        """Se la tabella users e' vuota, inserisce l'utente admin di default.
        La password viene letta da ADMIN_DEFAULT_PASSWORD env var.
        Se non impostata, genera una password random e la stampa in console."""
        cur = self._cursor()
        cur.execute("SELECT COUNT(*) as cnt FROM users")
        row = cur.fetchone()
        count = row["cnt"] if isinstance(row, dict) else row[0]
        if count == 0:
            import bcrypt
            import secrets
            admin_password = os.environ.get("ADMIN_DEFAULT_PASSWORD")
            if not admin_password:
                admin_password = secrets.token_urlsafe(16)
                print(f"[ADMIN] Password admin generata: {admin_password}")
                print("[ADMIN] Imposta ADMIN_DEFAULT_PASSWORD env var per fissarla.")
            admin_username = os.environ.get("ADMIN_USERNAME", "admin")
            password_hash = bcrypt.hashpw(admin_password.encode(), bcrypt.gensalt()).decode()
            cur.execute(
                self._q(
                    "INSERT INTO users (username, password_hash, is_admin, created_at) "
                    "VALUES (?, ?, ?, ?)"
                ),
                (admin_username, password_hash, 1, datetime.now().isoformat()),
            )
            self.conn.commit()
            print(f"[ADMIN] Utente admin '{admin_username}' creato.")

    # ------------------------------------------------------------------
    # USER METHODS
    # ------------------------------------------------------------------
    def create_user(self, username: str, password_hash: str,
                    is_admin: bool = False) -> int:
        cur = self._cursor()
        new_id = self._lastrowid(
            cur,
            "INSERT INTO users (username, password_hash, is_admin, created_at) "
            "VALUES (?, ?, ?, ?)",
            (username, password_hash, int(is_admin), datetime.now().isoformat()),
        )
        self.conn.commit()
        return new_id

    def get_user_by_username(self, username: str) -> Optional[dict]:
        cur = self._cursor()
        cur.execute(
            self._q("SELECT * FROM users WHERE username = ?"),
            (username,),
        )
        row = cur.fetchone()
        return self._dict(row)

    def get_user_by_id(self, user_id: int) -> Optional[dict]:
        cur = self._cursor()
        cur.execute(
            self._q("SELECT * FROM users WHERE id = ?"),
            (user_id,),
        )
        row = cur.fetchone()
        return self._dict(row)

    def user_count(self) -> int:
        cur = self._cursor()
        cur.execute("SELECT COUNT(*) as cnt FROM users")
        row = cur.fetchone()
        return row["cnt"] if isinstance(row, dict) else row[0]

    def get_all_users(self) -> list[dict]:
        cur = self._cursor()
        cur.execute("SELECT * FROM users ORDER BY id")
        return [self._dict(row) for row in cur.fetchall()]

    def update_last_login(self, user_id: int):
        cur = self._cursor()
        cur.execute(
            self._q("UPDATE users SET last_login = ? WHERE id = ?"),
            (datetime.now().isoformat(), user_id),
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # MATERIAL TURN
    # ------------------------------------------------------------------
    def insert_material_turn(self, turn_number: str, source_file: str,
                             total_segments: int = 0,
                             material_type: str = "") -> int:
        cur = self._cursor()
        new_id = self._lastrowid(
            cur,
            "INSERT INTO material_turn "
            "(turn_number, source_file, total_segments, material_type) "
            "VALUES (?, ?, ?, ?)",
            (turn_number, source_file, total_segments, material_type),
        )
        self.conn.commit()
        return new_id

    def get_material_turns(self) -> list[dict]:
        cur = self._cursor()
        cur.execute("SELECT * FROM material_turn ORDER BY turn_number")
        return [self._dict(row) for row in cur.fetchall()]

    # ------------------------------------------------------------------
    # TRAIN SEGMENT
    # ------------------------------------------------------------------
    def insert_segment(self, seg: TrainSegment) -> int:
        cur = self._cursor()
        new_id = self._lastrowid(
            cur,
            "INSERT INTO train_segment "
            "(train_id, from_station, dep_time, to_station, arr_time, "
            " material_turn_id, day_index, seq, confidence, raw_text, "
            " source_page, is_deadhead, is_accessory, segment_kind) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                seg.train_id, seg.from_station, seg.dep_time,
                seg.to_station, seg.arr_time, seg.material_turn_id,
                seg.day_index, seg.seq, seg.confidence, seg.raw_text,
                seg.source_page, int(seg.is_deadhead),
                int(seg.is_accessory), seg.segment_kind,
            ),
        )
        self.conn.commit()
        return new_id

    def bulk_insert_segments(self, segments: list[TrainSegment]):
        cur = self._cursor()
        sql = self._q(
            "INSERT INTO train_segment "
            "(train_id, from_station, dep_time, to_station, arr_time, "
            " material_turn_id, day_index, seq, confidence, raw_text, "
            " source_page, is_deadhead, is_accessory, segment_kind) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        data = [
            (
                s.train_id, s.from_station, s.dep_time,
                s.to_station, s.arr_time, s.material_turn_id,
                s.day_index, s.seq, s.confidence, s.raw_text,
                s.source_page, int(s.is_deadhead),
                int(s.is_accessory), s.segment_kind,
            )
            for s in segments
        ]
        cur.executemany(sql, data)
        self.conn.commit()

    def query_train(self, train_id: str) -> list[dict]:
        """Find all segments for a train id.

        Matches both the exact value and slash-joined multi-ids: searching
        for '3086' finds rows stored as '3086' or '3085/3086' or '3086/3087'.
        Pattern viene costruito lato Python per evitare clash dei '%'
        letterali con i format specifier di psycopg2.
        """
        cur = self._cursor()
        like_pattern = f"%/{train_id}/%"
        cur.execute(
            self._q(
                "SELECT * FROM train_segment "
                "WHERE train_id = ? "
                "   OR '/' || train_id || '/' LIKE ? "
                "ORDER BY day_index, seq"
            ),
            (train_id, like_pattern),
        )
        return [self._dict(row) for row in cur.fetchall()]

    def query_station_departures(self, station: str) -> list[dict]:
        cur = self._cursor()
        cur.execute(
            self._q(
                "SELECT * FROM train_segment WHERE UPPER(from_station) = UPPER(?) "
                "ORDER BY dep_time"
            ),
            (station,),
        )
        return [self._dict(row) for row in cur.fetchall()]

    def query_station_arrivals(self, station: str) -> list[dict]:
        cur = self._cursor()
        cur.execute(
            self._q(
                "SELECT * FROM train_segment WHERE UPPER(to_station) = UPPER(?) "
                "ORDER BY arr_time"
            ),
            (station,),
        )
        return [self._dict(row) for row in cur.fetchall()]

    def get_all_segments(self, day_index: Optional[int] = None) -> list[dict]:
        cur = self._cursor()
        if day_index is not None:
            cur.execute(
                self._q(
                    "SELECT * FROM train_segment WHERE day_index = ? "
                    "ORDER BY dep_time, seq"
                ),
                (day_index,),
            )
        else:
            cur.execute(
                "SELECT * FROM train_segment ORDER BY day_index, dep_time, seq"
            )
        return [self._dict(row) for row in cur.fetchall()]

    def get_segment_by_id(self, seg_id: int) -> Optional[dict]:
        cur = self._cursor()
        cur.execute(
            self._q("SELECT * FROM train_segment WHERE id = ?"), (seg_id,)
        )
        row = cur.fetchone()
        return self._dict(row)

    def get_distinct_day_indices(self) -> list[int]:
        cur = self._cursor()
        cur.execute("SELECT DISTINCT day_index FROM train_segment ORDER BY day_index")
        rows = cur.fetchall()
        return [r["day_index"] if isinstance(r, dict) else r[0] for r in rows]

    # ------------------------------------------------------------------
    # NON-TRAIN EVENT
    # ------------------------------------------------------------------
    def insert_event(self, event: NonTrainEvent) -> int:
        cur = self._cursor()
        new_id = self._lastrowid(
            cur,
            "INSERT INTO non_train_event "
            "(event_type, start_time, end_time, duration_min, description, day_index) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                event.event_type, event.start_time, event.end_time,
                event.duration_min, event.description, event.day_index,
            ),
        )
        self.conn.commit()
        return new_id

    # ------------------------------------------------------------------
    # GEOGRAPHIC REACHABILITY
    # ------------------------------------------------------------------
    def get_reachable_stations(self, deposito: str) -> list[str]:
        """
        Restituisce le stazioni raggiungibili direttamente dal deposito.
        Cioè tutte le stazioni che compaiono come from_station o to_station
        in segmenti che toccano il deposito (connessioni dirette = 1-hop).
        Include il deposito stesso.
        """
        deposito = deposito.upper().strip()
        cur = self._cursor()
        cur.execute(self._q("""
            SELECT DISTINCT
                CASE WHEN UPPER(from_station) = ? THEN to_station
                     ELSE from_station END AS other
            FROM train_segment
            WHERE UPPER(from_station) = ? OR UPPER(to_station) = ?
        """), (deposito, deposito, deposito))
        rows = cur.fetchall()
        stations = [r["other"] if isinstance(r, dict) else r[0] for r in rows]
        # Aggiungi il deposito stesso
        if deposito not in [s.upper() for s in stations]:
            stations.append(deposito)
        return sorted(stations)

    def get_all_unique_stations(self) -> list[str]:
        """Restituisce tutte le stazioni uniche nel database."""
        cur = self._cursor()
        cur.execute("""
            SELECT DISTINCT station FROM (
                SELECT from_station AS station FROM train_segment
                UNION
                SELECT to_station AS station FROM train_segment
            ) AS sub ORDER BY station
        """)
        rows = cur.fetchall()
        return [r["station"] if isinstance(r, dict) else r[0] for r in rows]

    # ------------------------------------------------------------------
    # DEPOT ABILITAZIONI (linee + materiale rotabile per deposito)
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_line_pair(station_a: str, station_b: str) -> tuple[str, str]:
        """Maiuscolo + ordine alfabetico (a <= b)."""
        a = (station_a or "").upper().strip()
        b = (station_b or "").upper().strip()
        return (a, b) if a <= b else (b, a)

    def get_material_turn_lines(self, material_turn_id: int) -> set:
        """
        Restituisce l'insieme di tutte le coppie (station_a, station_b)
        normalizzate alfabeticamente che compaiono nei segmenti del giro
        materiale. Una "linea" corrisponde a un singolo collegamento
        diretto tra due stazioni (from-to o to-from di un segmento).

        Cosi' un giro come 1101 che tocca ALES/CREMONA/MORTARA/PAVIA/
        VERCELLI viene scomposto in tutte le coppie effettivamente
        servite dai treni del giro (es. ALES-PAVIA, PAVIA-VERCELLI,
        MORTARA-VERCELLI, ecc.) — non solo gli estremi.
        """
        cur = self._cursor()
        cur.execute(self._q(
            "SELECT DISTINCT from_station, to_station FROM train_segment "
            "WHERE material_turn_id = ?"
        ), (material_turn_id,))
        out = set()
        for r in cur.fetchall():
            d = self._dict(r)
            a = (d["from_station"] or "").upper().strip()
            b = (d["to_station"] or "").upper().strip()
            if a and b and a != b:
                out.add(self._normalize_line_pair(a, b))
        return out

    def add_enabled_line(self, deposito: str, station_a: str, station_b: str) -> bool:
        """Aggiunge abilitazione linea. True se inserita, False se gia' presente."""
        dep = (deposito or "").upper().strip()
        a, b = self._normalize_line_pair(station_a, station_b)
        if not dep or not a or not b:
            return False
        cur = self._cursor()
        try:
            cur.execute(self._q(
                "INSERT INTO depot_enabled_line (deposito, station_a, station_b) "
                "VALUES (?, ?, ?)"
            ), (dep, a, b))
            self.conn.commit()
            return True
        except Exception:
            if self.is_pg:
                self.conn.rollback()
            return False

    def remove_enabled_line(self, deposito: str, station_a: str, station_b: str) -> int:
        """Rimuove abilitazione linea. Ritorna numero righe eliminate."""
        dep = (deposito or "").upper().strip()
        a, b = self._normalize_line_pair(station_a, station_b)
        cur = self._cursor()
        cur.execute(self._q(
            "DELETE FROM depot_enabled_line "
            "WHERE deposito = ? AND station_a = ? AND station_b = ?"
        ), (dep, a, b))
        self.conn.commit()
        return cur.rowcount

    def get_enabled_lines(self, deposito: str) -> list[tuple[str, str]]:
        """Lista coppie (station_a, station_b) abilitate per un deposito."""
        dep = (deposito or "").upper().strip()
        cur = self._cursor()
        cur.execute(self._q(
            "SELECT station_a, station_b FROM depot_enabled_line "
            "WHERE deposito = ? ORDER BY station_a, station_b"
        ), (dep,))
        rows = cur.fetchall()
        out: list[tuple[str, str]] = []
        for r in rows:
            d = self._dict(r)
            out.append((d["station_a"], d["station_b"]))
        return out

    def add_enabled_material(self, deposito: str, material_type: str) -> bool:
        dep = (deposito or "").upper().strip()
        mat = (material_type or "").upper().strip()
        if not dep or not mat:
            return False
        cur = self._cursor()
        try:
            cur.execute(self._q(
                "INSERT INTO depot_enabled_material (deposito, material_type) VALUES (?, ?)"
            ), (dep, mat))
            self.conn.commit()
            return True
        except Exception:
            if self.is_pg:
                self.conn.rollback()
            return False

    def remove_enabled_material(self, deposito: str, material_type: str) -> int:
        dep = (deposito or "").upper().strip()
        mat = (material_type or "").upper().strip()
        cur = self._cursor()
        cur.execute(self._q(
            "DELETE FROM depot_enabled_material "
            "WHERE deposito = ? AND material_type = ?"
        ), (dep, mat))
        self.conn.commit()
        return cur.rowcount

    def get_enabled_materials(self, deposito: str) -> list[str]:
        dep = (deposito or "").upper().strip()
        cur = self._cursor()
        cur.execute(self._q(
            "SELECT material_type FROM depot_enabled_material "
            "WHERE deposito = ? ORDER BY material_type"
        ), (dep,))
        rows = cur.fetchall()
        return [self._dict(r)["material_type"] for r in rows]

    def is_segment_enabled(self, deposito: str, segment: dict) -> bool:
        """
        Un segmento e' abilitato per un deposito se:
          - la sua coppia (from, to) normalizzata e' nelle linee
            abilitate, AND
          - il suo materiale e' abilitato OPPURE material_type vuoto
            (wildcard prudente per il bug parser).
        Se il deposito non ha nessuna linea configurata, ritorna False.
        """
        dep = (deposito or "").upper().strip()
        # Linea = coppia normalizzata del segmento stesso
        from_st = (segment.get("from_station", "") if isinstance(segment, dict) else getattr(segment, "from_station", "")).upper().strip()
        to_st = (segment.get("to_station", "") if isinstance(segment, dict) else getattr(segment, "to_station", "")).upper().strip()
        if not from_st or not to_st or from_st == to_st:
            return False
        line = self._normalize_line_pair(from_st, to_st)
        if line not in set(self.get_enabled_lines(dep)):
            return False
        # Materiale del giro
        mat_turn_id = segment.get("material_turn_id") if isinstance(segment, dict) else getattr(segment, "material_turn_id", None)
        if not mat_turn_id:
            # Segmento senza giro materiale: lo lasciamo passare se la
            # linea e' abilitata (caso edge, raro)
            return True
        cur = self._cursor()
        cur.execute(self._q(
            "SELECT material_type FROM material_turn WHERE id = ?"
        ), (mat_turn_id,))
        row = cur.fetchone()
        if not row:
            return True
        mat = (self._dict(row).get("material_type") or "").upper().strip()
        # Wildcard sul materiale: se il parser non ha estratto material_type
        # (33 giri su 50 in DB attuale), accetta comunque pur che la linea
        # sia abilitata. Vedi LIVE-COLAZIONE bug parser.
        if not mat:
            return True
        return mat in set(self.get_enabled_materials(dep))

    def get_available_lines_for_depot(self, deposito: str) -> list[dict]:
        """
        Elenca tutte le coppie (station_a, station_b) servite dai giri
        materiale che toccano il deposito. Una coppia = un singolo
        collegamento diretto tra due stazioni nei segmenti del giro.
        Cosi' per ogni giro non vediamo solo gli estremi ma TUTTE le
        tratte effettivamente percorse (utile a granularita' alta).
        Ritorna [{'station_a', 'station_b', 'material_turn_count', 'enabled'}].
        """
        dep = (deposito or "").upper().strip()
        cur = self._cursor()
        cur.execute(self._q("""
            SELECT DISTINCT material_turn_id
            FROM train_segment
            WHERE material_turn_id IS NOT NULL
              AND (UPPER(from_station) = ? OR UPPER(to_station) = ?)
        """), (dep, dep))
        rows = cur.fetchall()
        turn_ids = [self._dict(r)["material_turn_id"] for r in rows]
        enabled_set = set(self.get_enabled_lines(dep))
        counts: dict = {}
        for tid in turn_ids:
            for line in self.get_material_turn_lines(tid):
                counts[line] = counts.get(line, 0) + 1
        out = []
        for (a, b), n in sorted(counts.items()):
            out.append({
                "station_a": a,
                "station_b": b,
                "material_turn_count": n,
                "enabled": (a, b) in enabled_set,
            })
        return out

    def get_available_materials_for_depot(self, deposito: str) -> list[dict]:
        """
        Materiali rotabili presenti nei giri che toccano il deposito.
        Include anche i giri con material_type vuoto (parser bug noto):
        vengono mostrati come '(non specificato)' e l'utente puo'
        abilitarli esplicitamente per non escludere quei giri.
        Ritorna [{'material_type', 'material_turn_count', 'enabled'}].
        """
        dep = (deposito or "").upper().strip()
        cur = self._cursor()
        cur.execute(self._q("""
            SELECT mt.material_type, COUNT(DISTINCT mt.id) AS n
            FROM material_turn mt
            WHERE mt.id IN (
                SELECT DISTINCT material_turn_id FROM train_segment
                WHERE material_turn_id IS NOT NULL
                  AND (UPPER(from_station) = ? OR UPPER(to_station) = ?)
            )
            GROUP BY mt.material_type
            ORDER BY mt.material_type
        """), (dep, dep))
        rows = cur.fetchall()
        enabled_set = set(self.get_enabled_materials(dep))
        out = []
        for r in rows:
            d = self._dict(r)
            raw = d["material_type"] or ""
            mat = raw.upper().strip()
            display = mat if mat else "(non specificato)"
            out.append({
                "material_type": display,
                "material_turn_count": d["n"],
                "enabled": (mat in enabled_set) if mat else True,  # vuoto = wildcard, sempre on
            })
        return out

    # ------------------------------------------------------------------
    # DAY VARIANT
    # ------------------------------------------------------------------
    def insert_day_variant(self, day_index: int, material_turn_id: int,
                           validity_text: str):
        cur = self._cursor()
        if self.is_pg:
            cur.execute(
                self._q(
                    "INSERT INTO day_variant (day_index, material_turn_id, validity_text) "
                    "VALUES (?, ?, ?) "
                    "ON CONFLICT (day_index, material_turn_id) "
                    "DO UPDATE SET validity_text = EXCLUDED.validity_text"
                ),
                (day_index, material_turn_id, validity_text.upper()),
            )
        else:
            cur.execute(
                "INSERT OR REPLACE INTO day_variant "
                "(day_index, material_turn_id, validity_text) VALUES (?, ?, ?)",
                (day_index, material_turn_id, validity_text.upper()),
            )
        self.conn.commit()

    def get_day_variants(self) -> list[dict]:
        cur = self._cursor()
        cur.execute(
            "SELECT dv.*, mt.turn_number FROM day_variant dv "
            "LEFT JOIN material_turn mt ON dv.material_turn_id = mt.id "
            "ORDER BY dv.material_turn_id, dv.day_index"
        )
        return [self._dict(row) for row in cur.fetchall()]

    def get_day_indices_for_validity(self, target_day: str) -> list[int]:
        """Dato un tipo giorno (LV, SAB, DOM, FEST), ritorna i day_index compatibili."""
        from ..constants import VALIDITY_MAP
        valid_types = VALIDITY_MAP.get(target_day.upper(), ["GG"])
        placeholders = ",".join([self._q("?")] * len(valid_types))
        cur = self._cursor()
        cur.execute(
            f"SELECT DISTINCT day_index FROM day_variant "
            f"WHERE UPPER(validity_text) IN ({placeholders}) "
            f"ORDER BY day_index",
            valid_types,
        )
        rows = cur.fetchall()
        result = [r["day_index"] if isinstance(r, dict) else r[0] for r in rows]
        if not result:
            # Fallback: ritorna tutti i day_index se nessun match
            return self.get_distinct_day_indices()
        return result

    def check_trains_for_day_type(self, train_ids: list[str],
                                  target_day: str) -> dict:
        """Per ogni train_id, verifica se esiste nei day_index compatibili
        con target_day. Usa euristica basata su densita segmenti per gruppo
        giorno. Ritorna {train_id: {found: bool, day_indices: []}}."""
        # Usa get_day_index_groups per una mappatura euristica affidabile
        groups = self.get_day_index_groups()
        target_upper = target_day.upper()
        if target_upper in ("SAB", "S"):
            valid_indices = groups.get("SAB", [])
        elif target_upper in ("DOM", "D", "FEST"):
            valid_indices = groups.get("DOM", [])
        else:
            valid_indices = groups.get("LV", [])

        # Fallback a get_day_indices_for_validity se gruppi vuoti
        if not valid_indices:
            valid_indices = self.get_day_indices_for_validity(target_day)

        result = {}
        cur = self._cursor()
        for tid in train_ids:
            # Salta marker speciali
            if tid in ("S.COMP",) or not tid.strip():
                result[tid] = {"found": True, "day_indices": []}
                continue
            if not valid_indices:
                result[tid] = {"found": False, "day_indices": []}
                continue
            placeholders = ",".join([self._q("?")] * len(valid_indices))
            cur.execute(
                self._q(
                    f"SELECT DISTINCT day_index FROM train_segment "
                    f"WHERE train_id = ? AND day_index IN ({placeholders})"
                ),
                [tid] + valid_indices,
            )
            rows = cur.fetchall()
            found_indices = [r["day_index"] if isinstance(r, dict) else r[0] for r in rows]
            result[tid] = {
                "found": len(found_indices) > 0,
                "day_indices": found_indices,
            }
        return result

    # ------------------------------------------------------------------
    # SAVED SHIFT
    # ------------------------------------------------------------------
    def save_shift(self, name: str, deposito: str, day_type: str,
                   train_ids: list[str], prestazione_min: int,
                   condotta_min: int, meal_min: int, accessori_min: int,
                   extra_min: int, is_fr: bool, last_station: str,
                   violations: list, accessory_type: str = "standard",
                   deadhead_ids: list[str] = None,
                   presentation_time: str = "",
                   end_time: str = "",
                   user_id: Optional[int] = None) -> int:
        cur = self._cursor()
        new_id = self._lastrowid(
            cur,
            "INSERT INTO saved_shift "
            "(name, deposito, day_type, created_at, train_ids, deadhead_ids, "
            " prestazione_min, condotta_min, meal_min, accessori_min, "
            " extra_min, is_fr, last_station, violations, accessory_type,"
            " presentation_time, end_time, user_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                name, deposito, day_type, datetime.now().isoformat(),
                json.dumps(train_ids), json.dumps(deadhead_ids or []),
                prestazione_min, condotta_min,
                meal_min, accessori_min, extra_min, int(is_fr),
                last_station, json.dumps(violations), accessory_type,
                presentation_time, end_time, user_id,
            ),
        )
        self.conn.commit()
        return new_id

    def get_saved_shifts(self, day_type: str = None,
                         user_id: Optional[int] = None) -> list[dict]:
        cur = self._cursor()
        conditions = []
        params: list = []
        if day_type:
            conditions.append(self._q("day_type = ?"))
            params.append(day_type)
        if user_id is not None:
            conditions.append(self._q("user_id = ?"))
            params.append(user_id)

        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        cur.execute(
            f"SELECT * FROM saved_shift{where} ORDER BY created_at DESC",
            params,
        )
        rows = []
        for row in cur.fetchall():
            d = self._dict(row)
            d["train_ids"] = json.loads(d["train_ids"])
            d["violations"] = json.loads(d["violations"])
            d["is_fr"] = bool(d["is_fr"])
            try:
                d["deadhead_ids"] = json.loads(d.get("deadhead_ids") or "[]")
            except Exception:
                d["deadhead_ids"] = []
            rows.append(d)
        return rows

    def delete_saved_shift(self, shift_id: int,
                           user_id: Optional[int] = None):
        cur = self._cursor()
        if user_id is not None:
            cur.execute(
                self._q("DELETE FROM saved_shift WHERE id = ? AND user_id = ?"),
                (shift_id, user_id),
            )
        else:
            cur.execute(
                self._q("DELETE FROM saved_shift WHERE id = ?"), (shift_id,)
            )
        self.conn.commit()

    def get_used_train_ids(self, day_type: str = None,
                           user_id: Optional[int] = None) -> list[str]:
        """Ritorna tutti i train_id gia usati in turni salvati."""
        shifts = self.get_saved_shifts(day_type=day_type, user_id=user_id)
        used = set()
        for s in shifts:
            used.update(s["train_ids"])
        return sorted(used)

    # ------------------------------------------------------------------
    # WEEKLY SHIFT (turno settimanale unificato)
    # ------------------------------------------------------------------
    def save_weekly_shift(self, name: str, deposito: str, days: list[dict],
                          accessory_type: str = "standard",
                          notes: str = "",
                          user_id: Optional[int] = None) -> int:
        """Salva un turno settimanale con tutte le varianti giornaliere.

        days = [
            {
                "day_number": 1,
                "variants": [
                    {"variant_type": "LMXGV", "day_type": "LV", "train_ids": [...],
                     "prestazione_min": 480, "condotta_min": 300, "meal_min": 30,
                     "is_fr": False, "is_scomp": False, "scomp_duration_min": 0,
                     "last_station": "ALESSANDRIA", "violations": []},
                    {"variant_type": "S", "day_type": "SAB", ...},
                    {"variant_type": "D", "day_type": "DOM", ...},
                ]
            }, ...
        ]
        """
        cur = self._cursor()

        # Calcola metriche settimanali pesate
        total_pres = 0
        total_cond = 0
        freq_map = {"LMXGV": 5, "S": 1, "D": 1}
        total_freq = 0
        for day in days:
            for v in day.get("variants", []):
                freq = freq_map.get(v.get("variant_type", "LMXGV"), 1)
                pres = v.get("prestazione_min", 0)
                cond = v.get("condotta_min", 0)
                if v.get("is_scomp"):
                    pres = v.get("scomp_duration_min", 360)
                total_pres += pres * freq
                total_cond += cond * freq
                total_freq += freq

        weighted_per_day = total_pres / total_freq if total_freq > 0 else 0

        weekly_id = self._lastrowid(
            cur,
            "INSERT INTO weekly_shift "
            "(name, deposito, created_at, num_days, weekly_prestazione_min, "
            " weekly_condotta_min, weighted_hours_per_day, accessory_type, notes, user_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, deposito, datetime.now().isoformat(), len(days),
             total_pres, total_cond, weighted_per_day, accessory_type, notes,
             user_id),
        )

        # Inserisci varianti giornaliere
        for day in days:
            for v in day.get("variants", []):
                cur.execute(
                    self._q(
                        "INSERT INTO shift_day_variant "
                        "(weekly_shift_id, day_number, variant_type, day_type, "
                        " train_ids, prestazione_min, condotta_min, meal_min, "
                        " is_fr, is_scomp, scomp_duration_min, last_station, violations) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (weekly_id, day["day_number"],
                     v.get("variant_type", "LMXGV"),
                     v.get("day_type", "LV"),
                     json.dumps(v.get("train_ids", [])),
                     v.get("prestazione_min", 0),
                     v.get("condotta_min", 0),
                     v.get("meal_min", 0),
                     int(v.get("is_fr", False)),
                     int(v.get("is_scomp", False)),
                     v.get("scomp_duration_min", 0),
                     v.get("last_station", ""),
                     json.dumps(v.get("violations", [])),
                    ),
                )

        self.conn.commit()
        return weekly_id

    def get_weekly_shifts(self, user_id: Optional[int] = None) -> list[dict]:
        """Restituisce tutti i turni settimanali salvati con le loro varianti."""
        cur = self._cursor()
        if user_id is not None:
            cur.execute(
                self._q("SELECT * FROM weekly_shift WHERE user_id = ? ORDER BY created_at DESC"),
                (user_id,),
            )
        else:
            cur.execute("SELECT * FROM weekly_shift ORDER BY created_at DESC")
        result = []
        for ws in cur.fetchall():
            ws_dict = self._dict(ws)
            # Carica varianti
            cur2 = self._cursor()
            cur2.execute(
                self._q(
                    "SELECT * FROM shift_day_variant WHERE weekly_shift_id = ? "
                    "ORDER BY day_number, variant_type"
                ),
                (ws_dict["id"],),
            )
            days_map = {}
            for v in cur2.fetchall():
                vd = self._dict(v)
                vd["train_ids"] = json.loads(vd["train_ids"])
                vd["violations"] = json.loads(vd["violations"])
                vd["is_fr"] = bool(vd["is_fr"])
                vd["is_scomp"] = bool(vd["is_scomp"])
                dn = vd["day_number"]
                if dn not in days_map:
                    days_map[dn] = {"day_number": dn, "variants": []}
                days_map[dn]["variants"].append(vd)
            ws_dict["days"] = sorted(days_map.values(), key=lambda d: d["day_number"])
            result.append(ws_dict)
        return result

    def delete_weekly_shift(self, weekly_id: int,
                            user_id: Optional[int] = None):
        """Elimina un turno settimanale e tutte le sue varianti (CASCADE)."""
        cur = self._cursor()
        if user_id is not None:
            # Prima verifica ownership, poi cancella
            cur.execute(
                self._q(
                    "DELETE FROM shift_day_variant WHERE weekly_shift_id IN "
                    "(SELECT id FROM weekly_shift WHERE id = ? AND user_id = ?)"
                ),
                (weekly_id, user_id),
            )
            cur.execute(
                self._q("DELETE FROM weekly_shift WHERE id = ? AND user_id = ?"),
                (weekly_id, user_id),
            )
        else:
            cur.execute(
                self._q("DELETE FROM shift_day_variant WHERE weekly_shift_id = ?"),
                (weekly_id,),
            )
            cur.execute(
                self._q("DELETE FROM weekly_shift WHERE id = ?"), (weekly_id,)
            )
        self.conn.commit()

    def get_weekly_used_train_ids(self, user_id: Optional[int] = None) -> list[str]:
        """Ritorna tutti i train_id usati in turni settimanali salvati."""
        cur = self._cursor()
        if user_id is not None:
            cur.execute(
                self._q(
                    "SELECT sdv.train_ids FROM shift_day_variant sdv "
                    "JOIN weekly_shift ws ON ws.id = sdv.weekly_shift_id "
                    "WHERE ws.user_id = ?"
                ),
                (user_id,),
            )
        else:
            cur.execute("SELECT train_ids FROM shift_day_variant")
        used = set()
        for row in cur.fetchall():
            r = self._dict(row)
            ids = json.loads(r["train_ids"])
            used.update(ids)
        return sorted(used)

    # ------------------------------------------------------------------
    # GIRO MATERIALE (ciclo completo del treno materiale)
    # ------------------------------------------------------------------
    def get_material_cycle(self, train_id: str) -> dict:
        """
        Dato un train_id, trova il giro materiale completo per la VARIANTE
        specifica a cui appartiene. Ogni variante ha un day_index unico
        e una validity_text che indica quando è attiva.
        """
        from collections import OrderedDict
        cur = self._cursor()

        # 1. Trova material_turn_id e day_index del treno cercato.
        #    Match flessibile per train_id "slash-joined" (es. 3085/3086).
        like_pattern = f"%/{train_id}/%"
        cur.execute(
            self._q(
                "SELECT DISTINCT day_index, material_turn_id "
                "FROM train_segment "
                "WHERE train_id = ? "
                "   OR '/' || train_id || '/' LIKE ?"
            ),
            (train_id, like_pattern),
        )
        refs = [self._dict(row) for row in cur.fetchall()]
        if not refs:
            return {"train_id": train_id, "material_turn": None, "cycle": [],
                    "variants": []}

        # 2. Per ogni variante (day_index) in cui il treno appare,
        #    ottieni tutti i segmenti della stessa variante
        variants_data = []
        mt_ids = set()
        for ref in refs:
            day_idx = ref["day_index"]
            mt_id = ref["material_turn_id"]
            if mt_id:
                mt_ids.add(mt_id)

            # Ottieni tutti i segmenti di questa variante
            cur.execute(
                self._q(
                    "SELECT * FROM train_segment "
                    "WHERE material_turn_id = ? AND day_index = ? "
                    "ORDER BY dep_time, seq"
                ),
                (mt_id, day_idx),
            )
            segments = [self._dict(r) for r in cur.fetchall()]

            # Ottieni validity_text dalla day_variant
            validity = ""
            if mt_id is not None:
                cur.execute(
                    self._q(
                        "SELECT validity_text FROM day_variant "
                        "WHERE material_turn_id = ? AND day_index = ?"
                    ),
                    (mt_id, day_idx),
                )
                dv_row = cur.fetchone()
                if dv_row:
                    dv_d = self._dict(dv_row)
                    validity = dv_d["validity_text"]

            # Costruisce il giro materiale per CONTINUITA' GEOGRAFICA:
            # il treno successivo parte dalla stazione di arrivo del precedente,
            # entro un tempo ragionevole (< MAX_GAP minuti).
            # Questo esclude automaticamente i treni dopo una dormita materiale.

            def _hhmm_to_min(t: str) -> int:
                try:
                    parts = t.split(":")
                    return int(parts[0]) * 60 + int(parts[1])
                except Exception:
                    return -1

            def _station_match(a: str, b: str) -> bool:
                """Controlla se due nomi stazione si riferiscono allo stesso luogo."""
                if not a or not b:
                    return False
                a, b = a.strip().upper(), b.strip().upper()
                if a == b:
                    return True
                # Abbreviazioni comuni
                abbrevs = {
                    "MI.ROG.": "MILANO ROGOREDO", "MI ROG": "MILANO ROGOREDO",
                    "MI.CERTOSA": "MILANO CERTOSA", "MI.LAMBRATE": "MILANO LAMBRATE",
                    "MI.P.GARIBALDI": "MILANO PORTA GARIBALDI",
                    "MI.S.CRISTOFORO": "MILANO SAN CRISTOFORO",
                    "ALESSAN.": "ALESSANDRIA",
                }
                na = abbrevs.get(a, a)
                nb = abbrevs.get(b, b)
                return na == nb

            MAX_GAP = 180  # minuti

            # Raggruppa segmenti per train_id
            train_map: dict[str, list] = {}
            for seg in segments:
                tid = seg["train_id"]
                if tid not in train_map:
                    train_map[tid] = []
                train_map[tid].append(seg)

            # Info per ogni treno: prima partenza, ultimo arrivo, stazioni
            train_info: dict[str, dict] = {}
            for tid, segs in train_map.items():
                sorted_segs = sorted(segs, key=lambda s: s.get("dep_time", ""))
                first = sorted_segs[0]
                last = sorted(segs, key=lambda s: s.get("arr_time", ""))[-1]
                train_info[tid] = {
                    "dep_station": first.get("from_station", ""),
                    "dep_time": first.get("dep_time", ""),
                    "dep_min": _hhmm_to_min(first.get("dep_time", "")),
                    "arr_station": last.get("to_station", ""),
                    "arr_time": last.get("arr_time", ""),
                    "arr_min": _hhmm_to_min(last.get("arr_time", "")),
                }

            # Trova la chiave canonica nel train_info: gestisce train_id
            # "slash-joined" come "3085/3086" quando si cerca "3086".
            def _canonical_tid(needle: str) -> Optional[str]:
                if needle in train_info:
                    return needle
                for k in train_info:
                    if needle in k.split("/"):
                        return k
                return None

            canonical = _canonical_tid(train_id)

            # Costruisci catena all'indietro dal treno cercato
            chain = [canonical] if canonical else []
            if chain:
                # Indietro: trova chi arriva dove parte il treno corrente
                current = canonical
                while True:
                    ci = train_info[current]
                    best_tid, best_gap = None, MAX_GAP + 1
                    for tid, ti in train_info.items():
                        if tid in chain:
                            continue
                        if _station_match(ti["arr_station"], ci["dep_station"]):
                            gap = ci["dep_min"] - ti["arr_min"]
                            if gap < 0:
                                gap += 24 * 60
                            # Gap ragionevole e il treno arriva PRIMA della partenza
                            if 0 <= gap <= MAX_GAP and gap < best_gap:
                                best_tid = tid
                                best_gap = gap
                    if best_tid:
                        chain.insert(0, best_tid)
                        current = best_tid
                    else:
                        break

                # Avanti: trova chi parte da dove arriva il treno corrente
                current = canonical
                while True:
                    ci = train_info[current]
                    best_tid, best_gap = None, MAX_GAP + 1
                    for tid, ti in train_info.items():
                        if tid in chain:
                            continue
                        if _station_match(ti["dep_station"], ci["arr_station"]):
                            gap = ti["dep_min"] - ci["arr_min"]
                            if gap < 0:
                                gap += 24 * 60
                            if 0 <= gap <= MAX_GAP and gap < best_gap:
                                best_tid = tid
                                best_gap = gap
                    if best_tid:
                        chain.append(best_tid)
                        current = best_tid
                    else:
                        break

            trains: dict[str, list] = OrderedDict()
            for tid in chain:
                trains[tid] = sorted(train_map[tid],
                                     key=lambda s: (s["dep_time"], s["seq"]))

            variants_data.append({
                "day_index": day_idx,
                "validity": validity,
                "cycle_trains": list(trains.keys()),
                "cycle": [
                    {"train_id": tid, "segments": segs}
                    for tid, segs in trains.items()
                ],
                "total_segments": len(segments),
            })

        # 3. Info material turn
        mt_info = None
        if mt_ids:
            mt_id_first = list(mt_ids)[0]
            cur.execute(
                self._q("SELECT * FROM material_turn WHERE id = ?"),
                (mt_id_first,),
            )
            row = cur.fetchone()
            if row:
                mt_info = self._dict(row)

        # 4. Ottieni TUTTE le varianti del turno
        all_variants = []
        if mt_ids:
            mt_id_first = list(mt_ids)[0]
            if self.is_pg:
                agg_func = "STRING_AGG(DISTINCT ts.train_id, ',')"
            else:
                agg_func = "GROUP_CONCAT(DISTINCT ts.train_id)"
            cur.execute(
                self._q(
                    f"SELECT dv.day_index, dv.validity_text, "
                    f"{agg_func} as train_ids "
                    f"FROM day_variant dv "
                    f"LEFT JOIN train_segment ts ON ts.material_turn_id = dv.material_turn_id "
                    f"AND ts.day_index = dv.day_index "
                    f"WHERE dv.material_turn_id = ? "
                    f"GROUP BY dv.day_index, dv.validity_text "
                    f"ORDER BY dv.day_index"
                ),
                (mt_id_first,),
            )
            for row in cur.fetchall():
                r = self._dict(row)
                tids = r["train_ids"].split(",") if r["train_ids"] else []
                all_variants.append({
                    "day_index": r["day_index"],
                    "validity": r["validity_text"],
                    "train_ids": tids,
                    "contains_searched": train_id in tids,
                })

        # Backward compat: first variant as main cycle
        first = variants_data[0] if variants_data else {}

        return {
            "train_id": train_id,
            "material_turn": mt_info,
            "cycle_trains": first.get("cycle_trains", []),
            "cycle": first.get("cycle", []),
            "total_segments": first.get("total_segments", 0),
            "validity": first.get("validity", ""),
            "variants": variants_data,
            "all_variants": all_variants,
        }

    def get_material_turn_info(self, train_id: str) -> dict:
        """Returns material_turn info (turn_number) for a train.

        Match flessibile per train_id slash-joined.
        """
        cur = self._cursor()
        like_pattern = f"%/{train_id}/%"
        cur.execute(self._q("""
            SELECT mt.id, mt.turn_number, mt.total_segments, mt.source_file,
                   mt.material_type
            FROM train_segment ts
            JOIN material_turn mt ON ts.material_turn_id = mt.id
            WHERE ts.train_id = ?
               OR '/' || ts.train_id || '/' LIKE ?
            LIMIT 1
        """), (train_id, like_pattern))
        row = cur.fetchone()
        if row:
            return self._dict(row)
        return None

    def get_giro_chain_context(self, train_id: str) -> dict:
        """Given a train_id, returns its position in the giro materiale chain:
        prev train, current, next train, and full chain summary.
        This is the KEY method for understanding what the material does."""
        cycle = self.get_material_cycle(train_id)
        if not cycle or not cycle.get("cycle"):
            return {"train_id": train_id, "prev": None, "next": None,
                    "chain": [], "turn_number": None, "material_type": "",
                    "position": -1, "total": 0}

        chain = cycle["cycle"]
        turn_number = None
        material_type = ""
        mt = cycle.get("material_turn")
        if mt:
            turn_number = mt.get("turn_number")
            material_type = mt.get("material_type") or ""

        # Find position of this train in the chain. Supports slash-joined
        # train_ids (e.g. "3085/3086" matches search for "3086").
        pos = -1
        for i, c in enumerate(chain):
            cid = c["train_id"]
            if cid == train_id or train_id in cid.split("/"):
                pos = i
                break

        prev_train = None
        next_train = None
        if pos > 0:
            p = chain[pos - 1]
            segs = [s for s in p.get("segments", [])
                    if s.get("confidence", 1) >= 0.3
                    and s.get("from_station") != s.get("to_station")]
            if segs:
                prev_train = {
                    "train_id": p["train_id"],
                    "from_station": segs[0].get("from_station", ""),
                    "to_station": segs[-1].get("to_station", ""),
                    "dep_time": segs[0].get("dep_time", ""),
                    "arr_time": segs[-1].get("arr_time", ""),
                    "is_deadhead": bool(segs[0].get("is_deadhead", 0)),
                }
        if pos >= 0 and pos < len(chain) - 1:
            n = chain[pos + 1]
            segs = [s for s in n.get("segments", [])
                    if s.get("confidence", 1) >= 0.3
                    and s.get("from_station") != s.get("to_station")]
            if segs:
                next_train = {
                    "train_id": n["train_id"],
                    "from_station": segs[0].get("from_station", ""),
                    "to_station": segs[-1].get("to_station", ""),
                    "dep_time": segs[0].get("dep_time", ""),
                    "arr_time": segs[-1].get("arr_time", ""),
                    "is_deadhead": bool(segs[0].get("is_deadhead", 0)),
                }

        # Compact chain summary
        chain_summary = []
        for c in chain:
            segs = [s for s in c.get("segments", [])
                    if s.get("confidence", 1) >= 0.3
                    and s.get("from_station") != s.get("to_station")]
            if segs:
                chain_summary.append({
                    "train_id": c["train_id"],
                    "from": segs[0].get("from_station", ""),
                    "to": segs[-1].get("to_station", ""),
                    "dep": segs[0].get("dep_time", ""),
                    "arr": segs[-1].get("arr_time", ""),
                    "is_deadhead": bool(segs[0].get("is_deadhead", 0)),
                })

        return {
            "train_id": train_id,
            "turn_number": turn_number,
            "material_type": material_type,
            "prev": prev_train,
            "next": next_train,
            "chain": chain_summary,
            "position": pos,
            "total": len(chain),
        }

    def find_giro_starts_from_station(self, station: str,
                                       day_indices: list[int] = None,
                                       limit: int = 10) -> list[dict]:
        """Trova giro materiale che INIZIANO da una stazione specifica.
        Utile per trovare continuazioni giro dopo dormita fuori residenza.
        Ritorna lista di {turn_number, first_train, chain_summary}."""
        from collections import OrderedDict
        cur = self._cursor()
        station_up = station.upper().strip()

        # Trova i material_turn che hanno segmenti partenti da questa stazione
        # con il dep_time più basso (= primo treno del giro)
        query = self._q("""
            SELECT ts.material_turn_id, ts.day_index, ts.train_id,
                   ts.dep_time, ts.arr_time, ts.from_station, ts.to_station,
                   mt.turn_number
            FROM train_segment ts
            JOIN material_turn mt ON ts.material_turn_id = mt.id
            WHERE UPPER(ts.from_station) = ?
            AND ts.confidence > 0.3
            AND ts.from_station != ts.to_station
        """)
        params: list = [station_up]
        if day_indices:
            placeholders = ",".join([self._q("?")] * len(day_indices))
            query += f" AND ts.day_index IN ({placeholders})"
            params.extend(day_indices)
        query += self._q(" ORDER BY ts.dep_time LIMIT ?")
        params.append(200)

        cur.execute(query, params)
        rows = [self._dict(r) for r in cur.fetchall()]

        # Per ogni material_turn+day_index, controlla se il primo treno parte da station
        seen = set()
        results = []
        for row in rows:
            key = (row["material_turn_id"], row["day_index"])
            if key in seen:
                continue
            seen.add(key)

            # Ottieni tutti i segmenti di questa variante
            cur.execute(
                self._q(
                    "SELECT train_id, dep_time, arr_time, from_station, to_station, "
                    "is_deadhead, seq FROM train_segment "
                    "WHERE material_turn_id = ? AND day_index = ? "
                    "AND confidence > 0.3 AND from_station != to_station "
                    "ORDER BY dep_time, seq"
                ),
                (row["material_turn_id"], row["day_index"]),
            )
            segs = [self._dict(r) for r in cur.fetchall()]
            if not segs:
                continue

            # Il PRIMO segmento deve partire dalla stazione cercata
            if segs[0]["from_station"].upper().strip() != station_up:
                continue

            # Raggruppa per train_id
            trains: dict[str, list] = OrderedDict()
            for s in segs:
                tid = s["train_id"]
                if tid not in trains:
                    trains[tid] = []
                trains[tid].append(s)

            chain = []
            for tid, tsegs in trains.items():
                chain.append({
                    "train_id": tid,
                    "from": tsegs[0]["from_station"],
                    "to": tsegs[-1]["to_station"],
                    "dep": tsegs[0]["dep_time"],
                    "arr": tsegs[-1]["arr_time"],
                    "is_deadhead": bool(tsegs[0].get("is_deadhead", 0)),
                })

            results.append({
                "turn_number": row["turn_number"],
                "day_index": row["day_index"],
                "first_train": chain[0] if chain else None,
                "chain": chain,
                "total": len(chain),
            })

            if len(results) >= limit:
                break

        return results

    def validate_no_duplicate_trains(self, train_ids: list[str]) -> list[str]:
        """Controlla se ci sono train_id duplicati nella lista."""
        seen = set()
        duplicates = []
        for tid in train_ids:
            if tid in seen:
                duplicates.append(tid)
            seen.add(tid)
        return duplicates

    # ------------------------------------------------------------------
    # CONNECTIONS (treni in partenza da una stazione dopo un orario)
    # ------------------------------------------------------------------
    def find_connecting_trains(self, from_station: str, after_time: str,
                               to_station: str = None,
                               day_indices: list[int] = None,
                               exclude_trains: list[str] = None,
                               limit: int = 10) -> list[dict]:
        """Trova treni in partenza da from_station dopo after_time.
        Deduplica per train_id (tiene il primo per dep_time)."""
        # Costruisce WHERE dinamico
        where = "UPPER(from_station) = UPPER({p}) AND dep_time >= {p} AND confidence > 0.3 AND from_station != to_station"
        where = where.replace("{p}", "%s" if self.is_pg else "?")
        params: list = [from_station, after_time]

        if to_station:
            where += " AND UPPER(to_station) = UPPER(%s)" if self.is_pg else " AND UPPER(to_station) = UPPER(?)"
            params.append(to_station)

        if day_indices:
            ph = ",".join(["%s" if self.is_pg else "?"] * len(day_indices))
            where += f" AND day_index IN ({ph})"
            params.extend(day_indices)

        if exclude_trains:
            ph = ",".join(["%s" if self.is_pg else "?"] * len(exclude_trains))
            where += f" AND train_id NOT IN ({ph})"
            params.extend(exclude_trains)

        if self.is_pg:
            query = (
                f"SELECT DISTINCT ON (train_id) train_id, dep_time, arr_time, "
                f"from_station, to_station, day_index, confidence, id as _rid "
                f"FROM train_segment WHERE {where} "
                f"ORDER BY train_id, dep_time"
            )
            cur = self._cursor()
            cur.execute(query, params)
            rows = [self._dict(row) for row in cur.fetchall()]
            rows.sort(key=lambda r: r.get("dep_time", ""))
            return rows[:limit]
        else:
            query = (
                f"SELECT train_id, dep_time, arr_time, from_station, to_station, "
                f"day_index, confidence, MIN(rowid) as _rid "
                f"FROM train_segment WHERE {where} "
                f"GROUP BY train_id ORDER BY dep_time LIMIT ?"
            )
            params.append(limit)
            cur = self._cursor()
            cur.execute(query, params)
            return [self._dict(row) for row in cur.fetchall()]

    def find_trains_passing_through(self, station: str, after_time: str,
                                     target_station: str = None,
                                     day_indices: list[int] = None,
                                     exclude_trains: list[str] = None,
                                     limit: int = 20) -> list[dict]:
        """Trova treni che PASSANO per una stazione (non solo from_station).

        Usa self-join: cerca treni dove un segmento arriva alla stazione
        (to_station = station) e un segmento successivo parte dalla stazione
        (from_station = station). Restituisce il segmento di partenza.

        Se target_station e' specificato, filtra anche per treni che raggiungono
        quella destinazione (tramite un segmento con to_station = target).
        """
        p = "%s" if self.is_pg else "?"

        # Cerca treni dove esiste un segmento con to_station=station
        # e un altro segmento (stesso treno, seq successivo) con from_station=station
        # UNION con la ricerca diretta from_station=station (per completezza)
        if target_station:
            # Treni che passano per station E raggiungono target_station
            if self.is_pg:
                query = f"""
                    SELECT DISTINCT ON (sub.train_id) sub.train_id, sub.dep_time, sub.arr_time,
                           sub.from_station, sub.to_station, sub.day_index, sub.confidence, sub.id as _rid
                    FROM (
                        -- Treni con segmento from_station=station che hanno anche un segmento to_station=target
                        SELECT s1.train_id, s1.dep_time, s1.arr_time, s1.from_station, s1.to_station,
                               s1.day_index, s1.confidence, s1.id
                        FROM train_segment s1
                        WHERE UPPER(s1.from_station) = UPPER({p})
                        AND s1.dep_time >= {p}
                        AND s1.confidence > 0.3
                        AND s1.from_station != s1.to_station
                        AND EXISTS (
                            SELECT 1 FROM train_segment s2
                            WHERE s2.train_id = s1.train_id
                            AND UPPER(s2.to_station) = UPPER({p})
                            AND s2.seq >= s1.seq
                        )
                        UNION
                        -- Treni che arrivano a station e poi ripartono, con destinazione target
                        SELECT s2.train_id, s2.dep_time, s2.arr_time, s2.from_station, s2.to_station,
                               s2.day_index, s2.confidence, s2.id
                        FROM train_segment s1
                        JOIN train_segment s2 ON s1.train_id = s2.train_id AND s2.seq > s1.seq
                        WHERE UPPER(s1.to_station) = UPPER({p})
                        AND UPPER(s2.from_station) = UPPER({p})
                        AND s2.dep_time >= {p}
                        AND s2.confidence > 0.3
                        AND EXISTS (
                            SELECT 1 FROM train_segment s3
                            WHERE s3.train_id = s2.train_id
                            AND UPPER(s3.to_station) = UPPER({p})
                            AND s3.seq >= s2.seq
                        )
                    ) sub
                    ORDER BY sub.train_id, sub.dep_time
                """
                params = [station, after_time, target_station,
                          station, station, after_time, target_station]
            else:
                query = f"""
                    SELECT train_id, dep_time, arr_time, from_station, to_station,
                           day_index, confidence, MIN(rowid) as _rid
                    FROM (
                        SELECT s1.train_id, s1.dep_time, s1.arr_time, s1.from_station, s1.to_station,
                               s1.day_index, s1.confidence, s1.rowid
                        FROM train_segment s1
                        WHERE UPPER(s1.from_station) = UPPER({p})
                        AND s1.dep_time >= {p}
                        AND s1.confidence > 0.3
                        AND s1.from_station != s1.to_station
                        AND EXISTS (
                            SELECT 1 FROM train_segment s2
                            WHERE s2.train_id = s1.train_id
                            AND UPPER(s2.to_station) = UPPER({p})
                            AND s2.seq >= s1.seq
                        )
                        UNION
                        SELECT s2.train_id, s2.dep_time, s2.arr_time, s2.from_station, s2.to_station,
                               s2.day_index, s2.confidence, s2.rowid
                        FROM train_segment s1
                        JOIN train_segment s2 ON s1.train_id = s2.train_id AND s2.seq > s1.seq
                        WHERE UPPER(s1.to_station) = UPPER({p})
                        AND UPPER(s2.from_station) = UPPER({p})
                        AND s2.dep_time >= {p}
                        AND s2.confidence > 0.3
                        AND EXISTS (
                            SELECT 1 FROM train_segment s3
                            WHERE s3.train_id = s2.train_id
                            AND UPPER(s3.to_station) = UPPER({p})
                            AND s3.seq >= s2.seq
                        )
                    )
                    GROUP BY train_id ORDER BY dep_time LIMIT {p}
                """
                params = [station, after_time, target_station,
                          station, station, after_time, target_station, limit]
        else:
            # Solo treni che passano per station (qualsiasi destinazione)
            if self.is_pg:
                query = f"""
                    SELECT DISTINCT ON (sub.train_id) sub.train_id, sub.dep_time, sub.arr_time,
                           sub.from_station, sub.to_station, sub.day_index, sub.confidence, sub.id as _rid
                    FROM (
                        SELECT s1.train_id, s1.dep_time, s1.arr_time, s1.from_station, s1.to_station,
                               s1.day_index, s1.confidence, s1.id
                        FROM train_segment s1
                        WHERE UPPER(s1.from_station) = UPPER({p})
                        AND s1.dep_time >= {p}
                        AND s1.confidence > 0.3
                        AND s1.from_station != s1.to_station
                        UNION
                        SELECT s2.train_id, s2.dep_time, s2.arr_time, s2.from_station, s2.to_station,
                               s2.day_index, s2.confidence, s2.id
                        FROM train_segment s1
                        JOIN train_segment s2 ON s1.train_id = s2.train_id AND s2.seq > s1.seq
                        WHERE UPPER(s1.to_station) = UPPER({p})
                        AND UPPER(s2.from_station) = UPPER({p})
                        AND s2.dep_time >= {p}
                        AND s2.confidence > 0.3
                    ) sub
                    ORDER BY sub.train_id, sub.dep_time
                """
                params = [station, after_time, station, station, after_time]
            else:
                query = f"""
                    SELECT train_id, dep_time, arr_time, from_station, to_station,
                           day_index, confidence, MIN(rowid) as _rid
                    FROM (
                        SELECT s1.train_id, s1.dep_time, s1.arr_time, s1.from_station, s1.to_station,
                               s1.day_index, s1.confidence, s1.rowid
                        FROM train_segment s1
                        WHERE UPPER(s1.from_station) = UPPER({p})
                        AND s1.dep_time >= {p}
                        AND s1.confidence > 0.3
                        AND s1.from_station != s1.to_station
                        UNION
                        SELECT s2.train_id, s2.dep_time, s2.arr_time, s2.from_station, s2.to_station,
                               s2.day_index, s2.confidence, s2.rowid
                        FROM train_segment s1
                        JOIN train_segment s2 ON s1.train_id = s2.train_id AND s2.seq > s1.seq
                        WHERE UPPER(s1.to_station) = UPPER({p})
                        AND UPPER(s2.from_station) = UPPER({p})
                        AND s2.dep_time >= {p}
                        AND s2.confidence > 0.3
                    )
                    GROUP BY train_id ORDER BY dep_time LIMIT {p}
                """
                params = [station, after_time, station, station, after_time, limit]

        if day_indices:
            # Per day_indices, aggiungi filtro nella subquery
            # Questo e' complesso con UNION, quindi filtriamo dopo
            pass

        if exclude_trains:
            # Filtriamo dopo per semplicita'
            pass

        cur = self._cursor()
        cur.execute(query, params)
        rows = [self._dict(row) for row in cur.fetchall()]

        # Filtra post-query per day_indices e exclude_trains
        if day_indices:
            rows = [r for r in rows if r.get("day_index") in day_indices]
        if exclude_trains:
            ex_set = set(exclude_trains)
            rows = [r for r in rows if r["train_id"] not in ex_set]

        rows.sort(key=lambda r: r.get("dep_time", ""))
        if not self.is_pg:
            return rows  # limit gia' applicato nella query
        return rows[:limit]

    def find_return_trains(self, from_station: str, to_station: str,
                           after_time: str, limit: int = 5) -> list[dict]:
        """Find trains from from_station to to_station (direct + passing through).
        Searches across ALL day_indices. Deduplicates by train_id."""
        cur = self._cursor()

        # 1) Ricerca diretta (segmento from→to)
        if self.is_pg:
            cur.execute("""
                SELECT DISTINCT ON (train_id) train_id, dep_time, arr_time,
                       from_station, to_station, day_index, confidence, id as _rid
                FROM train_segment
                WHERE UPPER(from_station) = UPPER(%s)
                AND UPPER(to_station) = UPPER(%s)
                AND dep_time >= %s
                AND confidence > 0.3
                AND from_station != to_station
                ORDER BY train_id, dep_time
            """, (from_station, to_station, after_time))
            direct = [self._dict(row) for row in cur.fetchall()]
        else:
            cur.execute("""
                SELECT train_id, dep_time, arr_time, from_station, to_station,
                       day_index, confidence, MIN(rowid) as _rid
                FROM train_segment
                WHERE UPPER(from_station) = UPPER(?)
                AND UPPER(to_station) = UPPER(?)
                AND dep_time >= ?
                AND confidence > 0.3
                AND from_station != to_station
                GROUP BY train_id
                ORDER BY dep_time
                LIMIT ?
            """, (from_station, to_station, after_time, limit * 2))
            direct = [self._dict(row) for row in cur.fetchall()]

        # 2) Ricerca treni che passano attraverso (self-join)
        passing = self.find_trains_passing_through(
            station=from_station, after_time=after_time,
            target_station=to_station, limit=limit * 2
        )

        # Merge e deduplica
        seen = set(t["train_id"] for t in direct)
        for t in passing:
            if t["train_id"] not in seen:
                t["passes_through"] = True  # marca come treno di passaggio
                direct.append(t)
                seen.add(t["train_id"])

        direct.sort(key=lambda r: r.get("dep_time", ""))
        return direct[:limit]

    def get_day_index_groups(self) -> dict:
        """Analyze day_indices to infer day type groups (LV/SAB/DOM).
        Groups by how many segments each day_index has - the most populated
        are likely LV (weekday), medium = SAB, least = DOM/FEST."""
        cur = self._cursor()
        cur.execute("""
            SELECT day_index, COUNT(*) as seg_count, COUNT(DISTINCT train_id) as train_count
            FROM train_segment
            WHERE confidence > 0.3
            GROUP BY day_index
            ORDER BY seg_count DESC
        """)
        rows = [self._dict(r) for r in cur.fetchall()]
        if not rows:
            return {"LV": [], "SAB": [], "DOM": [], "all": []}

        # Heuristic: top 40% by segment count = LV, next 30% = SAB, rest = DOM
        total = len(rows)
        lv_cutoff = max(1, int(total * 0.4))
        sab_cutoff = max(lv_cutoff + 1, int(total * 0.7))

        return {
            "LV": [r["day_index"] for r in rows[:lv_cutoff]],
            "SAB": [r["day_index"] for r in rows[lv_cutoff:sab_cutoff]],
            "DOM": [r["day_index"] for r in rows[sab_cutoff:]],
            "all": rows,
        }

    # ------------------------------------------------------------------
    # PDC TURN (Turni PdC rete RFI — schema v2)
    # ------------------------------------------------------------------
    # Schema: pdc_turn → pdc_turn_day → pdc_block
    #                 → pdc_train_periodicity
    # Vedi .claude/skills/turno-pdc-reader.md per le regole di lettura.

    def insert_pdc_turn(self, codice: str, planning: str, impianto: str,
                        profilo: str = "Condotta",
                        valid_from: str = "", valid_to: str = "",
                        source_file: str = "",
                        import_id: Optional[int] = None,
                        data_pubblicazione: str = "") -> int:
        """Inserisce un nuovo turno PdC. Ritorna l'ID.

        import_id lega il turno al record pdc_import del caricamento.
        Legacy callers che passano None lasceranno import_id = NULL.
        """
        cur = self._cursor()
        return self._lastrowid(
            cur,
            "INSERT INTO pdc_turn "
            "(codice, planning, impianto, profilo, valid_from, valid_to, "
            " source_file, imported_at, import_id, data_pubblicazione) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (codice, planning, impianto, profilo, valid_from, valid_to,
             source_file, datetime.now().isoformat(),
             import_id, data_pubblicazione),
        )

    def insert_pdc_turn_day(self, pdc_turn_id: int, day_number: int,
                            periodicita: str, start_time: str = "",
                            end_time: str = "", lavoro_min: int = 0,
                            condotta_min: int = 0, km: int = 0,
                            notturno: bool = False, riposo_min: int = 0,
                            is_disponibile: bool = False) -> int:
        """Inserisce una giornata (numero + periodicita') del turno."""
        cur = self._cursor()
        return self._lastrowid(
            cur,
            "INSERT INTO pdc_turn_day "
            "(pdc_turn_id, day_number, periodicita, start_time, end_time, "
            " lavoro_min, condotta_min, km, notturno, riposo_min, is_disponibile) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (pdc_turn_id, day_number, periodicita, start_time, end_time,
             lavoro_min, condotta_min, km, 1 if notturno else 0,
             riposo_min, 1 if is_disponibile else 0),
        )

    def insert_pdc_block(self, pdc_turn_day_id: int, seq: int,
                         block_type: str, train_id: str = "",
                         vettura_id: str = "", from_station: str = "",
                         to_station: str = "", start_time: str = "",
                         end_time: str = "",
                         accessori_maggiorati: bool = False) -> int:
        """Inserisce un blocco Gantt nella giornata.

        block_type ∈ {'train', 'coach_transfer', 'cv_partenza',
                      'cv_arrivo', 'meal', 'scomp', 'available'}"""
        cur = self._cursor()
        return self._lastrowid(
            cur,
            "INSERT INTO pdc_block "
            "(pdc_turn_day_id, seq, block_type, train_id, vettura_id, "
            " from_station, to_station, start_time, end_time, "
            " accessori_maggiorati) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (pdc_turn_day_id, seq, block_type, train_id, vettura_id,
             from_station, to_station, start_time, end_time,
             1 if accessori_maggiorati else 0),
        )

    def insert_pdc_train_periodicity(self, pdc_turn_id: int, train_id: str,
                                     periodicita_text: str = "",
                                     non_circola_dates: Optional[list] = None,
                                     circola_extra_dates: Optional[list] = None) -> int:
        """Inserisce le note di periodicita' di un treno citato nel turno.

        non_circola_dates / circola_extra_dates: liste di 'YYYY-MM-DD'."""
        cur = self._cursor()
        return self._lastrowid(
            cur,
            "INSERT INTO pdc_train_periodicity "
            "(pdc_turn_id, train_id, periodicita_text, "
            " non_circola_dates, circola_extra_dates) "
            "VALUES (?, ?, ?, ?, ?)",
            (pdc_turn_id, train_id, periodicita_text,
             json.dumps(non_circola_dates or []),
             json.dumps(circola_extra_dates or [])),
        )

    def clear_pdc_data(self) -> None:
        """Svuota tutte le tabelle PdC, rispettando l'ordine FK.

        DEPRECATO dopo schema v2.1 (versioning import). Mantenuto per
        retro-compatibilita' (CLI, rollback totale). Il flusso upload
        normale ora usa save_parsed_turns_as_import() che preserva lo
        storico via superseded_by_import_id.
        """
        cur = self._cursor()
        cur.execute("DELETE FROM pdc_block")
        cur.execute("DELETE FROM pdc_train_periodicity")
        cur.execute("DELETE FROM pdc_turn_day")
        cur.execute("DELETE FROM pdc_turn")
        cur.execute("DELETE FROM pdc_import")
        self.conn.commit()

    # ------------------------------------------------------------------
    # VERSIONING IMPORT (schema v2.1)
    # ------------------------------------------------------------------

    def insert_pdc_import(self, filename: str, data_stampa: str = "",
                          data_pubblicazione: str = "", valido_dal: str = "",
                          valido_al: str = "", n_turni: int = 0,
                          n_pagine_pdf: int = 0,
                          imported_by: Optional[int] = None) -> int:
        """Crea un record pdc_import e ritorna l'id. Un nuovo import
        rappresenta un caricamento di PDF PdC; i suoi turni avranno
        import_id = id ritornato."""
        cur = self._cursor()
        return self._lastrowid(
            cur,
            "INSERT INTO pdc_import "
            "(filename, data_stampa, data_pubblicazione, valido_dal, "
            " valido_al, n_turni, n_pagine_pdf, imported_at, imported_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (filename, data_stampa, data_pubblicazione, valido_dal,
             valido_al, n_turni, n_pagine_pdf,
             datetime.now().isoformat(), imported_by),
        )

    def list_pdc_imports(self) -> list[dict]:
        """Elenco storico degli import PdC, piu' recenti prima."""
        cur = self._cursor()
        cur.execute(self._q(
            "SELECT * FROM pdc_import ORDER BY imported_at DESC"
        ))
        return [self._dict(r) for r in cur.fetchall()]

    def get_pdc_import(self, import_id: int) -> Optional[dict]:
        cur = self._cursor()
        cur.execute(self._q("SELECT * FROM pdc_import WHERE id = ?"),
                    (import_id,))
        return self._dict(cur.fetchone())

    def mark_superseded_turns(self, new_import_id: int) -> int:
        """Marca superseded tutti i turni attivi (non ancora superseded)
        che hanno stesso (codice, impianto) dei turni del nuovo import.

        Non tocca i turni attivi che non compaiono nel nuovo import
        (restano attivi; la UI li puo' mostrare come "non piu' pubblicati"
        e l'utente decide se archiviarli manualmente).

        Ritorna il numero di turni marcati.
        """
        cur = self._cursor()
        # Costruiamo SET di chiavi del nuovo import
        cur.execute(self._q(
            "SELECT DISTINCT codice, impianto FROM pdc_turn "
            "WHERE import_id = ?"
        ), (new_import_id,))
        new_keys = {(self._dict(r)["codice"], self._dict(r)["impianto"])
                    for r in cur.fetchall()}
        if not new_keys:
            return 0

        # Trova turni attivi con stesse chiavi, diverso import
        placeholders = ",".join(["(?, ?)"] * len(new_keys))
        flat = [v for pair in new_keys for v in pair]
        q = (
            "SELECT id FROM pdc_turn "
            "WHERE superseded_by_import_id IS NULL "
            "  AND import_id <> ? "
            f"  AND (codice, impianto) IN ({placeholders})"
        )
        # SQLite accetta tuple-in, PostgreSQL anche; funziona su entrambi
        cur.execute(self._q(q), (new_import_id, *flat))
        ids_to_mark = [self._dict(r)["id"] for r in cur.fetchall()]
        if not ids_to_mark:
            return 0

        placeholders_ids = ",".join(["?"] * len(ids_to_mark))
        cur.execute(
            self._q(
                f"UPDATE pdc_turn SET superseded_by_import_id = ? "
                f"WHERE id IN ({placeholders_ids})"
            ),
            (new_import_id, *ids_to_mark),
        )
        self.conn.commit()
        return len(ids_to_mark)

    def diff_import_candidates(self, parsed_turns: list) -> dict:
        """Dry-run: senza modificare il DB, calcola il diff fra i turni
        parsati dal nuovo PDF e i turni attivi correnti.

        parsed_turns = list[ParsedPdcTurn] (ha .codice, .impianto)

        Ritorna:
          {
            "new":         [{"codice","impianto"} ...],       # codici nuovi
            "updated":     [{"codice","impianto"} ...],       # stesso codice: verranno superseded
            "only_in_old": [{"codice","impianto"} ...],       # attivi ora, non nel nuovo PDF
            "counts": {"new": N, "updated": N, "only_in_old": N}
          }
        """
        new_keys = {(t.codice, t.impianto) for t in parsed_turns}

        cur = self._cursor()
        cur.execute(self._q(
            "SELECT codice, impianto FROM pdc_turn "
            "WHERE superseded_by_import_id IS NULL"
        ))
        active_keys = {(self._dict(r)["codice"], self._dict(r)["impianto"])
                       for r in cur.fetchall()}

        new_only = sorted(new_keys - active_keys)
        updated  = sorted(new_keys & active_keys)
        only_old = sorted(active_keys - new_keys)

        def pack(keys):
            return [{"codice": c, "impianto": i} for (c, i) in keys]

        return {
            "new": pack(new_only),
            "updated": pack(updated),
            "only_in_old": pack(only_old),
            "counts": {
                "new": len(new_only),
                "updated": len(updated),
                "only_in_old": len(only_old),
            },
        }

    def get_pdc_stats(self, include_inactive: bool = False) -> dict:
        """Statistiche aggregate dei turni PdC caricati.

        Di default considera solo i turni attivi (superseded_by_import_id IS NULL).
        Usa include_inactive=True per statistiche sullo storico completo.
        """
        cur = self._cursor()
        turn_where = "" if include_inactive else "WHERE superseded_by_import_id IS NULL"
        day_join_where = "" if include_inactive else "WHERE t.superseded_by_import_id IS NULL"

        cur.execute(f"SELECT COUNT(*) AS n FROM pdc_turn {turn_where}")
        turni = self._dict(cur.fetchone())["n"]
        if not turni:
            return {
                "loaded": False, "turni": 0, "days": 0, "blocks": 0,
                "impianti": [], "trains": 0,
            }
        cur.execute(
            "SELECT COUNT(*) AS n FROM pdc_turn_day d "
            "JOIN pdc_turn t ON t.id = d.pdc_turn_id "
            f"{day_join_where}"
        )
        days = self._dict(cur.fetchone())["n"]
        cur.execute(
            "SELECT COUNT(*) AS n FROM pdc_block b "
            "JOIN pdc_turn_day d ON d.id = b.pdc_turn_day_id "
            "JOIN pdc_turn t ON t.id = d.pdc_turn_id "
            f"{day_join_where}"
        )
        blocks = self._dict(cur.fetchone())["n"]
        cur.execute(
            "SELECT COUNT(DISTINCT b.train_id) AS n FROM pdc_block b "
            "JOIN pdc_turn_day d ON d.id = b.pdc_turn_day_id "
            "JOIN pdc_turn t ON t.id = d.pdc_turn_id "
            "WHERE b.block_type = 'train' AND b.train_id <> '' "
            + ("" if include_inactive else "AND t.superseded_by_import_id IS NULL")
        )
        trains = self._dict(cur.fetchone())["n"]
        cur.execute(
            f"SELECT DISTINCT impianto FROM pdc_turn {turn_where} "
            "ORDER BY impianto"
        )
        impianti = [self._dict(r)["impianto"] for r in cur.fetchall()]
        cur.execute(f"SELECT MIN(valid_from) AS v FROM pdc_turn {turn_where}")
        valid_from = self._dict(cur.fetchone())["v"]
        cur.execute(f"SELECT MAX(valid_to) AS v FROM pdc_turn {turn_where}")
        valid_to = self._dict(cur.fetchone())["v"]
        cur.execute(f"SELECT MAX(imported_at) AS v FROM pdc_turn {turn_where}")
        imported_at = self._dict(cur.fetchone())["v"]
        return {
            "loaded": True, "turni": turni, "days": days, "blocks": blocks,
            "trains": trains, "impianti": impianti,
            "valid_from": valid_from, "valid_to": valid_to,
            "imported_at": imported_at,
        }

    def list_pdc_turns(self, impianto: Optional[str] = None,
                       profilo: Optional[str] = None,
                       include_inactive: bool = False) -> list[dict]:
        """Elenco dei turni PdC, filtrabile per impianto/profilo.

        include_inactive=False (default): solo turni attivi
        (superseded_by_import_id IS NULL).
        """
        cur = self._cursor()
        conditions = []
        params: list = []
        if not include_inactive:
            conditions.append("superseded_by_import_id IS NULL")
        if impianto:
            conditions.append("UPPER(impianto) = UPPER(?)")
            params.append(impianto)
        if profilo:
            conditions.append("profilo = ?")
            params.append(profilo)
        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        cur.execute(
            self._q(f"SELECT * FROM pdc_turn{where} "
                    "ORDER BY impianto, codice"),
            tuple(params),
        )
        return [self._dict(r) for r in cur.fetchall()]

    def get_pdc_turn(self, turn_id: int) -> Optional[dict]:
        """Dettaglio singolo turno."""
        cur = self._cursor()
        cur.execute(self._q("SELECT * FROM pdc_turn WHERE id = ?"), (turn_id,))
        return self._dict(cur.fetchone())

    def get_pdc_turn_days(self, pdc_turn_id: int) -> list[dict]:
        """Elenco giornate di un turno, ordinate per (day_number, periodicita)."""
        cur = self._cursor()
        cur.execute(
            self._q(
                "SELECT * FROM pdc_turn_day WHERE pdc_turn_id = ? "
                "ORDER BY day_number, periodicita"
            ),
            (pdc_turn_id,),
        )
        return [self._dict(r) for r in cur.fetchall()]

    def get_pdc_blocks(self, pdc_turn_day_id: int) -> list[dict]:
        """Blocchi Gantt di una giornata, ordinati per seq."""
        cur = self._cursor()
        cur.execute(
            self._q(
                "SELECT * FROM pdc_block WHERE pdc_turn_day_id = ? "
                "ORDER BY seq"
            ),
            (pdc_turn_day_id,),
        )
        return [self._dict(r) for r in cur.fetchall()]

    def get_pdc_train_periodicity(self, pdc_turn_id: int) -> list[dict]:
        """Note periodicita' treni di un turno."""
        cur = self._cursor()
        cur.execute(
            self._q(
                "SELECT * FROM pdc_train_periodicity WHERE pdc_turn_id = ? "
                "ORDER BY train_id"
            ),
            (pdc_turn_id,),
        )
        rows = []
        for r in cur.fetchall():
            d = self._dict(r)
            # Deserializza JSON
            d["non_circola_dates"] = json.loads(d.get("non_circola_dates") or "[]")
            d["circola_extra_dates"] = json.loads(d.get("circola_extra_dates") or "[]")
            rows.append(d)
        return rows

    def find_pdc_train(self, train_id: str,
                       include_inactive: bool = False) -> list[dict]:
        """Cerca un treno nei blocchi PdC. Ritorna ogni giornata che lo include.

        include_inactive=False (default): cerca solo nei turni attivi.
        """
        cur = self._cursor()
        where_active = "" if include_inactive else "AND t.superseded_by_import_id IS NULL"
        cur.execute(self._q(f"""
            SELECT t.id AS turn_id, t.codice, t.impianto, t.profilo,
                   d.id AS day_id, d.day_number, d.periodicita,
                   d.start_time, d.end_time,
                   b.id AS block_id, b.seq, b.block_type, b.train_id,
                   b.from_station, b.to_station,
                   b.start_time AS block_start, b.end_time AS block_end,
                   b.accessori_maggiorati
            FROM pdc_block b
            JOIN pdc_turn_day d ON d.id = b.pdc_turn_day_id
            JOIN pdc_turn t ON t.id = d.pdc_turn_id
            WHERE b.block_type = 'train' AND b.train_id = ?
              {where_active}
            ORDER BY t.impianto, t.codice, d.day_number, d.periodicita, b.seq
        """), (train_id,))
        return [self._dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # UTILITY
    # ------------------------------------------------------------------
    def clear_all(self):
        cur = self._cursor()
        # Ordine: prima i figli (che hanno FK verso material_turn), poi il padre.
        # Necessario per PostgreSQL che enforce le FK (SQLite no per default).
        cur.execute("DELETE FROM non_train_event")
        cur.execute("DELETE FROM train_segment")
        cur.execute("DELETE FROM day_variant")
        cur.execute("DELETE FROM material_turn")
        # Non cancellare saved_shift (i turni salvati sono persistenti)
        self.conn.commit()

    def segment_count(self) -> int:
        cur = self._cursor()
        cur.execute("SELECT COUNT(*) as cnt FROM train_segment")
        row = cur.fetchone()
        return row["cnt"] if isinstance(row, dict) else row[0]

    def close(self):
        self.conn.close()
