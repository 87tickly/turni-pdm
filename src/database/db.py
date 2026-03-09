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
    train_id: str
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
                total_segments INTEGER DEFAULT 0
            )
        """)

        # -- train_segment
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

        # -- pdc_turno
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS pdc_turno (
                id {pk},
                depot TEXT NOT NULL,
                turno_code TEXT NOT NULL,
                turno_id TEXT DEFAULT '',
                valid_from TEXT DEFAULT '',
                valid_to TEXT DEFAULT '',
                source_file TEXT DEFAULT '',
                imported_at TEXT DEFAULT ''
            )
        """)

        # -- pdc_prog
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS pdc_prog (
                id {pk},
                pdc_turno_id INTEGER NOT NULL,
                prog_number INTEGER NOT NULL,
                day_type TEXT NOT NULL DEFAULT 'LMXGVSD',
                start_time TEXT DEFAULT '',
                end_time TEXT DEFAULT '',
                lavoro_min INTEGER DEFAULT 0,
                condotta_min INTEGER DEFAULT 0,
                km INTEGER DEFAULT 0,
                notturno INTEGER DEFAULT 0,
                riposo_min INTEGER DEFAULT 0,
                is_rest INTEGER DEFAULT 0,
                note TEXT DEFAULT '',
                FOREIGN KEY (pdc_turno_id) REFERENCES pdc_turno(id) ON DELETE CASCADE
            )
        """)

        # -- pdc_prog_train
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS pdc_prog_train (
                id {pk},
                pdc_prog_id INTEGER NOT NULL,
                train_id TEXT NOT NULL,
                FOREIGN KEY (pdc_prog_id) REFERENCES pdc_prog(id) ON DELETE CASCADE
            )
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_pdc_depot ON pdc_turno(depot)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pdc_train ON pdc_prog_train(train_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pdc_prog_turno ON pdc_prog(pdc_turno_id)")

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
                self.conn.execute(self._q(sql))
            self.conn.commit()

    def _seed_admin(self):
        """Se la tabella users e' vuota, inserisce l'utente admin di default."""
        cur = self._cursor()
        cur.execute("SELECT COUNT(*) as cnt FROM users")
        row = cur.fetchone()
        count = row["cnt"] if isinstance(row, dict) else row[0]
        if count == 0:
            import bcrypt
            password_hash = bcrypt.hashpw("Manu1982!".encode(), bcrypt.gensalt()).decode()
            cur.execute(
                self._q(
                    "INSERT INTO users (username, password_hash, is_admin, created_at) "
                    "VALUES (?, ?, ?, ?)"
                ),
                ("anto", password_hash, 1, datetime.now().isoformat()),
            )
            self.conn.commit()

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
                             total_segments: int = 0) -> int:
        cur = self._cursor()
        new_id = self._lastrowid(
            cur,
            "INSERT INTO material_turn (turn_number, source_file, total_segments) "
            "VALUES (?, ?, ?)",
            (turn_number, source_file, total_segments),
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
            " source_page, is_deadhead) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                seg.train_id, seg.from_station, seg.dep_time,
                seg.to_station, seg.arr_time, seg.material_turn_id,
                seg.day_index, seg.seq, seg.confidence, seg.raw_text,
                seg.source_page, int(seg.is_deadhead),
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
            " source_page, is_deadhead) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        data = [
            (
                s.train_id, s.from_station, s.dep_time,
                s.to_station, s.arr_time, s.material_turn_id,
                s.day_index, s.seq, s.confidence, s.raw_text,
                s.source_page, int(s.is_deadhead),
            )
            for s in segments
        ]
        cur.executemany(sql, data)
        self.conn.commit()

    def query_train(self, train_id: str) -> list[dict]:
        cur = self._cursor()
        cur.execute(
            self._q(
                "SELECT * FROM train_segment WHERE train_id = ? "
                "ORDER BY day_index, seq"
            ),
            (train_id,),
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

        # 1. Trova material_turn_id e day_index del treno cercato
        cur.execute(
            self._q(
                "SELECT DISTINCT day_index, material_turn_id "
                "FROM train_segment WHERE train_id = ?"
            ),
            (train_id,),
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

            # Costruisci catena all'indietro dal treno cercato
            chain = [train_id] if train_id in train_info else []
            if chain:
                # Indietro: trova chi arriva dove parte il treno corrente
                current = train_id
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
                current = train_id
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
        """Returns material_turn info (turn_number) for a train."""
        cur = self._cursor()
        cur.execute(self._q("""
            SELECT mt.id, mt.turn_number, mt.total_segments, mt.source_file
            FROM train_segment ts
            JOIN material_turn mt ON ts.material_turn_id = mt.id
            WHERE ts.train_id = ?
            LIMIT 1
        """), (train_id,))
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
                    "chain": [], "turn_number": None, "position": -1, "total": 0}

        chain = cycle["cycle"]
        turn_number = None
        mt = cycle.get("material_turn")
        if mt:
            turn_number = mt.get("turn_number")

        # Find position of this train in the chain
        pos = -1
        for i, c in enumerate(chain):
            if c["train_id"] == train_id:
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
        query = self._q(
            "SELECT train_id, dep_time, arr_time, from_station, to_station, "
            "day_index, confidence, MIN(id) as _rid "
            "FROM train_segment "
            "WHERE UPPER(from_station) = UPPER(?) AND dep_time >= ? "
            "AND confidence > 0.3 AND from_station != to_station"
        )
        params: list = [from_station, after_time]

        if to_station:
            query += self._q(" AND UPPER(to_station) = UPPER(?)")
            params.append(to_station)

        if day_indices:
            placeholders = ",".join([self._q("?")] * len(day_indices))
            query += f" AND day_index IN ({placeholders})"
            params.extend(day_indices)

        if exclude_trains:
            placeholders = ",".join([self._q("?")] * len(exclude_trains))
            query += f" AND train_id NOT IN ({placeholders})"
            params.extend(exclude_trains)

        query += self._q(" GROUP BY train_id ORDER BY dep_time LIMIT ?")
        params.append(limit)

        cur = self._cursor()
        cur.execute(query, params)
        return [self._dict(row) for row in cur.fetchall()]

    def find_return_trains(self, from_station: str, to_station: str,
                           after_time: str, limit: int = 5) -> list[dict]:
        """Find trains from from_station to to_station (for depot return).
        Searches across ALL day_indices. Deduplicates by train_id."""
        cur = self._cursor()
        cur.execute(self._q("""
            SELECT train_id, dep_time, arr_time, from_station, to_station,
                   day_index, confidence, MIN(id) as _rid
            FROM train_segment
            WHERE UPPER(from_station) = UPPER(?)
            AND UPPER(to_station) = UPPER(?)
            AND dep_time >= ?
            AND confidence > 0.3
            AND from_station != to_station
            GROUP BY train_id
            ORDER BY dep_time
            LIMIT ?
        """), (from_station, to_station, after_time, limit))
        return [self._dict(row) for row in cur.fetchall()]

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
    # PDC TURNO (Turni PdC rete RFI)
    # ------------------------------------------------------------------
    def import_pdc_turni(self, turni: list, source_file: str = ""):
        """Importa turni PdC nel DB. Cancella i dati precedenti."""
        cur = self._cursor()
        # Pulisci tabelle PdC
        cur.execute("DELETE FROM pdc_prog_train")
        cur.execute("DELETE FROM pdc_prog")
        cur.execute("DELETE FROM pdc_turno")

        now = datetime.now().isoformat()

        for turno in turni:
            turno_db_id = self._lastrowid(
                cur,
                "INSERT INTO pdc_turno (depot, turno_code, turno_id, valid_from, valid_to, "
                "                       source_file, imported_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (turno.depot, turno.turno_code, turno.turno_id,
                 turno.valid_from, turno.valid_to, source_file, now),
            )

            for prog in turno.progs:
                prog_db_id = self._lastrowid(
                    cur,
                    "INSERT INTO pdc_prog (pdc_turno_id, prog_number, day_type, "
                    "                     start_time, end_time, lavoro_min, condotta_min, "
                    "                     km, notturno, riposo_min, is_rest, note) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (turno_db_id, prog.prog_number, prog.day_type,
                     prog.start_time, prog.end_time, prog.lavoro_min,
                     prog.condotta_min, prog.km, 1 if prog.notturno else 0,
                     prog.riposo_min, 1 if prog.is_rest else 0, prog.note),
                )

                for tid in prog.train_ids:
                    cur.execute(
                        self._q(
                            "INSERT INTO pdc_prog_train (pdc_prog_id, train_id) "
                            "VALUES (?, ?)"
                        ),
                        (prog_db_id, tid),
                    )

        self.conn.commit()
        cur2 = self._cursor()
        cur2.execute("SELECT COUNT(*) as cnt FROM pdc_turno")
        row = cur2.fetchone()
        return row["cnt"] if isinstance(row, dict) else row[0]

    def pdc_find_train(self, train_id: str) -> list[dict]:
        """Cerca un treno nei turni PdC. Restituisce tutti i PROG che lo contengono."""
        cur = self._cursor()
        cur.execute(self._q("""
            SELECT t.depot, t.turno_code, t.turno_id, t.valid_from, t.valid_to,
                   p.id as prog_id, p.prog_number, p.day_type, p.start_time, p.end_time,
                   p.lavoro_min, p.condotta_min, p.km, p.notturno, p.is_rest,
                   p.note
            FROM pdc_prog_train pt
            JOIN pdc_prog p ON p.id = pt.pdc_prog_id
            JOIN pdc_turno t ON t.id = p.pdc_turno_id
            WHERE pt.train_id = ?
            ORDER BY t.depot, p.prog_number, p.day_type
        """), (train_id,))
        results = []
        for row in cur.fetchall():
            rd = self._dict(row)
            # Trova tutti i treni di questo PROG
            cur2 = self._cursor()
            cur2.execute(
                self._q("SELECT train_id FROM pdc_prog_train WHERE pdc_prog_id = ?"),
                (rd["prog_id"],),
            )
            prog_trains = [self._dict(r)["train_id"] for r in cur2.fetchall()]

            results.append({
                "depot": rd["depot"],
                "turno_code": rd["turno_code"],
                "turno_id": rd["turno_id"],
                "valid_from": rd["valid_from"],
                "valid_to": rd["valid_to"],
                "prog_number": rd["prog_number"],
                "day_type": rd["day_type"],
                "start_time": rd["start_time"],
                "end_time": rd["end_time"],
                "lavoro_min": rd["lavoro_min"],
                "condotta_min": rd["condotta_min"],
                "km": rd["km"],
                "notturno": bool(rd["notturno"]),
                "is_rest": bool(rd["is_rest"]),
                "note": rd["note"],
                "other_trains": prog_trains,
            })
        return results

    def pdc_get_stats(self) -> dict:
        """Statistiche dei turni PdC importati."""
        cur = self._cursor()
        cur.execute("SELECT COUNT(*) as cnt FROM pdc_turno")
        turni_count = self._dict(cur.fetchone())["cnt"]
        if turni_count == 0:
            return {"loaded": False, "turni": 0, "progs": 0, "trains": 0, "depots": []}

        cur.execute("SELECT COUNT(*) as cnt FROM pdc_prog")
        progs_count = self._dict(cur.fetchone())["cnt"]
        cur.execute("SELECT COUNT(DISTINCT train_id) as cnt FROM pdc_prog_train")
        trains_count = self._dict(cur.fetchone())["cnt"]
        cur.execute("SELECT DISTINCT depot FROM pdc_turno ORDER BY depot")
        depots = [self._dict(r)["depot"] for r in cur.fetchall()]

        # Data validita'
        cur.execute("SELECT MIN(valid_from) as v FROM pdc_turno")
        valid_from = self._dict(cur.fetchone())["v"]
        cur.execute("SELECT MAX(valid_to) as v FROM pdc_turno")
        valid_to = self._dict(cur.fetchone())["v"]
        cur.execute("SELECT MAX(imported_at) as v FROM pdc_turno")
        imported_at = self._dict(cur.fetchone())["v"]

        return {
            "loaded": True,
            "turni": turni_count,
            "progs": progs_count,
            "trains": trains_count,
            "depots": depots,
            "valid_from": valid_from,
            "valid_to": valid_to,
            "imported_at": imported_at,
        }

    def pdc_get_depot_turno(self, depot: str) -> list[dict]:
        """Restituisce tutti i PROG di un deposito."""
        cur = self._cursor()
        cur.execute(self._q("""
            SELECT t.depot, t.turno_code, t.turno_id, t.valid_from, t.valid_to,
                   p.id as prog_id, p.prog_number, p.day_type, p.start_time, p.end_time,
                   p.lavoro_min, p.condotta_min, p.km, p.notturno, p.is_rest, p.note
            FROM pdc_prog p
            JOIN pdc_turno t ON t.id = p.pdc_turno_id
            WHERE UPPER(t.depot) = UPPER(?)
            ORDER BY p.prog_number, p.day_type
        """), (depot,))

        results = []
        for row in cur.fetchall():
            rd = self._dict(row)
            # Treni di questo prog
            cur2 = self._cursor()
            cur2.execute(
                self._q("SELECT train_id FROM pdc_prog_train WHERE pdc_prog_id = ?"),
                (rd["prog_id"],),
            )
            trains = [self._dict(r)["train_id"] for r in cur2.fetchall()]
            results.append({
                "depot": rd["depot"],
                "turno_code": rd["turno_code"],
                "prog_number": rd["prog_number"],
                "day_type": rd["day_type"],
                "start_time": rd["start_time"],
                "end_time": rd["end_time"],
                "lavoro_min": rd["lavoro_min"],
                "condotta_min": rd["condotta_min"],
                "km": rd["km"],
                "is_rest": bool(rd["is_rest"]),
                "trains": trains,
            })
        return results

    # ------------------------------------------------------------------
    # UTILITY
    # ------------------------------------------------------------------
    def clear_all(self):
        cur = self._cursor()
        cur.execute("DELETE FROM non_train_event")
        cur.execute("DELETE FROM train_segment")
        cur.execute("DELETE FROM material_turn")
        cur.execute("DELETE FROM day_variant")
        # Non cancellare saved_shift (i turni salvati sono persistenti)
        self.conn.commit()

    def segment_count(self) -> int:
        cur = self._cursor()
        cur.execute("SELECT COUNT(*) as cnt FROM train_segment")
        row = cur.fetchone()
        return row["cnt"] if isinstance(row, dict) else row[0]

    def close(self):
        self.conn.close()
