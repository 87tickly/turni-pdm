"""
CV Registry — registro condiviso persistente per i Cambi Volante (CVp/CVa).

Regola di business (richiesta utente 22-23/04/2026):

  Tra due treni consecutivi sullo stesso materiale, con gap < 65 min
  (sotto soglia accessori pieni), c'e' un Cambio Volante. Se i due treni
  sono operati da PdC diversi (turni generati in momenti separati), il
  tempo di CV va **spartito** tra i due cosi' che ogni minuto sia
  coperto da qualcuno e nessuno conti due volte gli stessi minuti.

  Per farlo serve una **memoria condivisa**: quando un PdC viene
  generato ed prende il suo CVa, scrive nel registro. Quando il
  successivo PdC viene generato e prende il suo CVp, legge il registro
  per sapere quanto ha gia' preso l'altro e si prende il complemento.

Schema minimo (idempotente):

    cv_ledger(
        material_turn_id, day_index,
        train_in_id, train_out_id,    -- la transizione materiale
        train_in_arr_min, train_out_dep_min,
        tm_min,                       -- momento di subentro
        cva_pdc_id, cva_min,          -- il PdC che esce (CVa)
        cvp_pdc_id, cvp_min,          -- il PdC che entra (CVp)
        updated_at
    )
    UNIQUE(material_turn_id, day_index, train_in_id, train_out_id)

Vincoli:
  - min 10' per lato (ogni PdC deve stare almeno 10' sul mezzo)
  - cva_min + cvp_min == gap_totale (copertura completa, zero scoperti)
  - se stesso PdC su entrambi i treni, cva = gap_totale, cvp = 0
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from ..validator.rules import _time_to_min
from .accessori import GAP_THRESHOLD_MIN
from ..constants import DEPOSITI


# Vincoli contratto (minimi per lato)
CV_MIN_PER_SIDE = 10  # min 10' per lato (richiesta utente 23/04/2026)


# NORMATIVA-PDC.md §9.2 — un CV può avvenire SOLO in:
#   1. stazione sede deposito PdC (uno dei DEPOSITI)
#   2. MORTARA (già nei DEPOSITI come deroga storica)
#   3. stazione di capolinea inversione di marcia (es. TIRANO)
#
# Le stazioni nei segmenti sono nomi RFI tipo "MILANO PORTA GARIBALDI".
# Alcuni DEPOSITI sono codici aziendali (es. GARIBALDI_ALE) che vanno
# mappati via depot_to_station della configurazione aziendale.
CV_CAPOLINEA_INVERSIONE: set[str] = {
    "TIRANO",
}


def _build_cv_allowed_stations() -> set[str]:
    """Set delle stazioni in cui è ammesso un CV (§9.2).

    Combina:
      - nomi deposito (quando coincidono con nome stazione: ALESSANDRIA,
        PAVIA, BRESCIA…)
      - stazioni collegate ai depositi aziendali via depot_to_station
        (es. GARIBALDI_ALE → MILANO PORTA GARIBALDI)
      - capolinea inversione (TIRANO).

    Normalizzazione: .upper().strip() così il confronto è robusto.
    """
    from config.loader import get_active_config
    cfg = get_active_config()
    mapping = getattr(cfg, "depot_to_station", {}) or {}
    s: set[str] = set()
    for depot in DEPOSITI:
        s.add(depot.upper().strip())
        if depot in mapping:
            s.add(mapping[depot].upper().strip())
    for capolinea in CV_CAPOLINEA_INVERSIONE:
        s.add(capolinea.upper().strip())
    return s


_CV_ALLOWED_STATIONS: set[str] = _build_cv_allowed_stations()


def is_cv_station_allowed(station_name: str) -> bool:
    """True se la stazione è §9.2-ammessa per un CV."""
    if not station_name:
        return False
    return station_name.upper().strip() in _CV_ALLOWED_STATIONS


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cv_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_turn_id INTEGER NOT NULL,
    day_index INTEGER NOT NULL,
    train_in_id TEXT NOT NULL,
    train_out_id TEXT NOT NULL,
    train_in_arr_min INTEGER NOT NULL,
    train_out_dep_min INTEGER NOT NULL,
    tm_min INTEGER,
    cva_pdc_id TEXT,
    cva_min INTEGER DEFAULT 0,
    cvp_pdc_id TEXT,
    cvp_min INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(material_turn_id, day_index, train_in_id, train_out_id)
)
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Crea la tabella cv_ledger se non esiste. Idempotente."""
    conn.execute(SCHEMA_SQL)
    conn.commit()


# ---------------------------------------------------------------------------
# Rilevamento CV
# ---------------------------------------------------------------------------

def detect_cv(prev_seg: dict, next_seg: dict) -> Optional[dict]:
    """
    Ritorna i dati del CV se tra prev_seg e next_seg c'e' effettivamente
    un cambio volante, None altrimenti.

    Condizioni di CV:
      - stesso material_turn_id
      - train_id diverso (altrimenti e' lo stesso treno continuativo)
      - gap < GAP_THRESHOLD_MIN (sopra soglia diventa ACCp/ACCa pieni)
      - gap >= CV_MIN_PER_SIDE (serve almeno il tempo di un subentro)

    Ritorna:
      {
        "material_turn_id": int,
        "day_index": int,
        "train_in_id": str,
        "train_out_id": str,
        "train_in_arr_min": int,
        "train_out_dep_min": int,
        "gap_min": int,
      }
      oppure None.
    """
    if prev_seg.get("material_turn_id") != next_seg.get("material_turn_id"):
        return None
    if prev_seg.get("material_turn_id") is None:
        return None
    if prev_seg.get("train_id") == next_seg.get("train_id"):
        return None
    if prev_seg.get("day_index") != next_seg.get("day_index"):
        return None

    # NORMATIVA-PDC.md §9.2: il CV può avvenire SOLO in stazioni ammesse
    # (sedi deposito PdC, MORTARA, capolinea inversione). Se il punto
    # di incontro non è ammesso, niente CV: il caller tratterà il gap
    # come accessori pieni o PK.
    cv_station = prev_seg.get("to_station") or next_seg.get("from_station", "")
    if not is_cv_station_allowed(cv_station):
        return None

    prev_arr = _time_to_min(prev_seg["arr_time"])
    next_dep = _time_to_min(next_seg["dep_time"])
    # overnight handling: se next_dep "precede" prev_arr assumiamo rollover
    if next_dep < prev_arr:
        next_dep += 1440
    gap = next_dep - prev_arr

    if gap >= GAP_THRESHOLD_MIN:
        return None  # gap ampio -> ACCa/ACCp pieni, non CV
    if gap < CV_MIN_PER_SIDE:
        return None  # gap insufficiente anche per un solo lato di CV

    return {
        "material_turn_id": prev_seg["material_turn_id"],
        "day_index": prev_seg.get("day_index", 0),
        "train_in_id": prev_seg["train_id"],
        "train_out_id": next_seg["train_id"],
        "train_in_arr_min": prev_arr,
        "train_out_dep_min": next_dep,
        "gap_min": gap,
        "cv_station": (cv_station or "").upper().strip(),
    }


# ---------------------------------------------------------------------------
# Split Tm (momento di subentro)
# ---------------------------------------------------------------------------

def compute_cv_split(gap_min: int, same_pdc: bool = False) -> tuple[int, int]:
    """
    Ritorna (cva_min, cvp_min) — minuti assegnati al lato in uscita (CVa)
    e al lato in entrata (CVp) di un CV.

    Vincoli:
      - cva_min + cvp_min == gap_min (copertura completa)
      - se same_pdc: cva = gap_min, cvp = 0 (tutto al PdC unico)
      - se PdC diversi: min CV_MIN_PER_SIDE per lato, default 50/50

    Raise ValueError se gap < CV_MIN_PER_SIDE (CV impossibile).
    """
    if gap_min < CV_MIN_PER_SIDE:
        raise ValueError(
            f"gap {gap_min} min < {CV_MIN_PER_SIDE}: CV impossibile"
        )
    if same_pdc:
        return (gap_min, 0)
    # PdC diversi -> split. Servono CV_MIN_PER_SIDE per ciascuno.
    if gap_min < 2 * CV_MIN_PER_SIDE:
        # Gap troppo piccolo per split completo: sotto-caso documentato
        # del subentro stretto. cva assume il minimo, cvp il resto.
        return (CV_MIN_PER_SIDE, gap_min - CV_MIN_PER_SIDE)
    # Default: 50/50 con arrotondamento al CVa (uscita)
    half = gap_min // 2
    cva = max(CV_MIN_PER_SIDE, half)
    cvp = gap_min - cva
    if cvp < CV_MIN_PER_SIDE:
        cva = gap_min - CV_MIN_PER_SIDE
        cvp = CV_MIN_PER_SIDE
    return (cva, cvp)


# ---------------------------------------------------------------------------
# Persistenza (read / register)
# ---------------------------------------------------------------------------

def _key_filter_sql() -> str:
    return (
        " WHERE material_turn_id = ? AND day_index = ? "
        "   AND train_in_id = ? AND train_out_id = ? "
    )


def read_cv(conn: sqlite3.Connection, material_turn_id: int,
            day_index: int, train_in_id: str,
            train_out_id: str) -> Optional[dict]:
    """Ritorna lo stato corrente del CV per quella transizione, o None."""
    cur = conn.execute(
        "SELECT tm_min, cva_pdc_id, cva_min, cvp_pdc_id, cvp_min, "
        " train_in_arr_min, train_out_dep_min "
        "FROM cv_ledger " + _key_filter_sql(),
        (material_turn_id, day_index, train_in_id, train_out_id),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "tm_min": row[0],
        "cva_pdc_id": row[1],
        "cva_min": row[2] or 0,
        "cvp_pdc_id": row[3],
        "cvp_min": row[4] or 0,
        "train_in_arr_min": row[5],
        "train_out_dep_min": row[6],
    }


def register_cv_side(conn: sqlite3.Connection,
                      cv: dict,
                      side: str,
                      pdc_id: str,
                      duration_min: int) -> dict:
    """
    Registra un lato del CV (cva o cvp) per un dato PdC.

    Args:
        conn: connessione SQLite (ensure_schema gia' chiamato)
        cv: dict restituito da detect_cv (chiavi di transizione materiale)
        side: "cva" o "cvp"
        pdc_id: identificativo del PdC che prende questo lato
        duration_min: minuti assegnati a questo lato

    Ritorna lo stato aggiornato (come read_cv), con tm_min ricalcolato
    se entrambi i lati sono ora registrati.
    """
    assert side in ("cva", "cvp"), f"side invalid: {side}"

    # INSERT OR IGNORE: crea la riga base se non esiste ancora
    conn.execute(
        "INSERT OR IGNORE INTO cv_ledger "
        " (material_turn_id, day_index, train_in_id, train_out_id, "
        "  train_in_arr_min, train_out_dep_min) "
        " VALUES (?, ?, ?, ?, ?, ?)",
        (cv["material_turn_id"], cv["day_index"],
         cv["train_in_id"], cv["train_out_id"],
         cv["train_in_arr_min"], cv["train_out_dep_min"]),
    )

    col_pdc = f"{side}_pdc_id"
    col_dur = f"{side}_min"
    conn.execute(
        f"UPDATE cv_ledger SET {col_pdc} = ?, {col_dur} = ?, "
        "updated_at = CURRENT_TIMESTAMP " + _key_filter_sql(),
        (pdc_id, duration_min,
         cv["material_turn_id"], cv["day_index"],
         cv["train_in_id"], cv["train_out_id"]),
    )

    # Se entrambi i lati sono popolati, calcola Tm (momento di subentro)
    state = read_cv(conn, cv["material_turn_id"], cv["day_index"],
                    cv["train_in_id"], cv["train_out_id"])
    if state and state["cva_min"] > 0 and state["cvp_min"] > 0:
        tm = state["train_in_arr_min"] + state["cva_min"]
        conn.execute(
            "UPDATE cv_ledger SET tm_min = ? " + _key_filter_sql(),
            (tm, cv["material_turn_id"], cv["day_index"],
             cv["train_in_id"], cv["train_out_id"]),
        )

    conn.commit()
    return read_cv(conn, cv["material_turn_id"], cv["day_index"],
                   cv["train_in_id"], cv["train_out_id"])


def validate_coverage(state: dict, expected_gap: int) -> bool:
    """True se cva_min + cvp_min == expected_gap (copertura completa)."""
    if not state:
        return False
    return (state["cva_min"] or 0) + (state["cvp_min"] or 0) == expected_gap
