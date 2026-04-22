"""
Seed Enumerator — enumera "seed produttivi" per una giornata.

Un seed produttivo = 1 o 2 treni-condotta che insieme totalizzano 2h-5h
di condotta. Rappresenta la "spina dorsale" della giornata del PdC.
Intorno al seed, il day_assembler aggiunge posizionamento iniziale
(vettura) e rientro.

Concetto (richiesta utente): un turno reale ALESSANDRIA ha tipicamente:
- 1-2 treni IN CONDOTTA (core produttivo, 2-3h)
- 3-5 segmenti IN VETTURA (posizionamento + rientro)
- 1 refezione

Il builder precedente cercava catene di 2-5 treni TUTTI in condotta dal
deposito. Sbagliato. Ora partiamo dai treni-condotta target e costruiamo
intorno.

Input: lista di segmenti candidati (gia' filtrati per abilitazione +
zona + orario minimo).
Output: lista di "seed" candidati, ordinati per bonta' euristica.
"""
from __future__ import annotations

from ..validator.rules import _time_to_min


# Parametri seed (richiesta utente: condotta 2h min - 5h max, target 4h)
SEED_MIN_CONDOTTA = 120  # 2h
SEED_MAX_CONDOTTA = 300  # 5h
SEED_TARGET_CONDOTTA = 240  # 4h (richiesta utente 22/04: "tranquillamente 4h, max 5h")
SEED_MAX_GAP_MIN = 420  # max 7h tra primi treno e ultimo (per accogliere refezione lunga)
SEED_MIN_GAP_INTER_MIN = 5  # 5 min min tra treno e treno del seed


def _seg_dur(seg: dict) -> int:
    """Durata segmento in minuti (gestisce overnight)."""
    dep = _time_to_min(seg["dep_time"])
    arr = _time_to_min(seg["arr_time"])
    if arr < dep:
        arr += 1440
    return arr - dep


def _seg_is_productive(seg: dict) -> bool:
    """Un segmento e' 'produttivo' (condotta) se non marcato deadhead."""
    return not seg.get("is_deadhead", False)


def enumerate_seeds(candidate_segments: list,
                    max_seeds: int = 100) -> list:
    """
    Enumera seed produttivi: combinazioni di 1 o 2 treni-condotta con
    condotta totale in [SEED_MIN_CONDOTTA, SEED_MAX_CONDOTTA].

    Args:
        candidate_segments: lista segmenti del giorno (filtrati).
            Ciascuno e' un dict con keys: train_id, from_station,
            to_station, dep_time, arr_time, material_turn_id, ...
        max_seeds: limite output per controllo complessita'.

    Returns:
        lista di dict:
          {
              "trains": [seg1] o [seg1, seg2],
              "condotta_min": int,
              "from_station": str (inizio primo treno),
              "to_station": str (fine ultimo treno),
              "first_dep_min": int (ora inizio primo treno),
              "last_arr_min": int (ora fine ultimo treno),
              "score": float (euristica)
          }
        Ordinata per score desc.
    """
    # Solo segmenti produttivi (no deadhead)
    productive = [s for s in candidate_segments if _seg_is_productive(s)]
    if not productive:
        return []

    seeds = []

    # --- Seed di 1 treno (condotta 120-300 min) ---
    for seg in productive:
        dur = _seg_dur(seg)
        if SEED_MIN_CONDOTTA <= dur <= SEED_MAX_CONDOTTA:
            dep_m = _time_to_min(seg["dep_time"])
            arr_m = _time_to_min(seg["arr_time"])
            if arr_m < dep_m:
                arr_m += 1440
            seeds.append({
                "trains": [seg],
                "condotta_min": dur,
                "from_station": seg.get("from_station", "").upper(),
                "to_station": seg.get("to_station", "").upper(),
                "first_dep_min": dep_m,
                "last_arr_min": arr_m,
                "score": _score_seed(dur, 1),
            })

    # --- Seed di 2 treni concatenati ---
    # Per evitare esplosione: per ogni seg1 prendiamo solo treni seg2
    # compatibili (from_station == seg1.to_station) con timing valido.
    # Se train_id uguale saltiamo (stesso treno).
    by_from: dict = {}
    for s in productive:
        k = s.get("from_station", "").upper()
        by_from.setdefault(k, []).append(s)

    for seg1 in productive:
        dur1 = _seg_dur(seg1)
        if dur1 >= SEED_MAX_CONDOTTA:
            continue  # troppo lungo da solo
        dep1 = _time_to_min(seg1["dep_time"])
        arr1 = _time_to_min(seg1["arr_time"])
        if arr1 < dep1:
            arr1 += 1440
        end_st = seg1.get("to_station", "").upper()
        # Candidati seg2: stessa from del mio end, dep > arr1 + gap min
        for seg2 in by_from.get(end_st, []):
            if seg2.get("train_id", "") == seg1.get("train_id", ""):
                continue
            dep2 = _time_to_min(seg2["dep_time"])
            if dep2 < arr1 + SEED_MIN_GAP_INTER_MIN:
                continue
            gap_inter = dep2 - arr1
            if gap_inter > SEED_MAX_GAP_MIN:
                continue
            dur2 = _seg_dur(seg2)
            total_cond = dur1 + dur2
            if not (SEED_MIN_CONDOTTA <= total_cond <= SEED_MAX_CONDOTTA):
                continue
            arr2 = _time_to_min(seg2["arr_time"])
            if arr2 < dep2:
                arr2 += 1440
            span = arr2 - dep1
            if span > 1000:  # 16h e' troppo per una giornata PdC
                continue
            seeds.append({
                "trains": [seg1, seg2],
                "condotta_min": total_cond,
                "from_station": seg1.get("from_station", "").upper(),
                "to_station": seg2.get("to_station", "").upper(),
                "first_dep_min": dep1,
                "last_arr_min": arr2,
                "score": _score_seed(total_cond, 2),
            })

    # Ordina per score decrescente e limita
    seeds.sort(key=lambda s: -s["score"])
    return seeds[:max_seeds]


def _score_seed(condotta_min: int, n_trains: int) -> float:
    """
    Euristica per ordinare i seed.
    - Premia condotta vicina al target (180 min = 3h)
    - Leggera preferenza per seed a 2 treni (piu' ricchi)
    - Range utile 120-300 min
    """
    diff = abs(condotta_min - SEED_TARGET_CONDOTTA)
    score = 500 - diff * 2.0
    if n_trains == 2:
        score += 50  # piccolo bonus diversita'
    return score
