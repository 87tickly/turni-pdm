"""
Day Assembler — assembla una giornata completa per il PdC.

Architettura v4 (richiesta utente 21/04/2026). Il builder precedente
generava catene di treni-condotta dal deposito. Il v4 ribalta la logica:

  A) SEED   : 1-2 treni-condotta (core produttivo, 2-5h condotta)
  B) POS.   : posizionamento deposito -> inizio seed (vettura, 0-3 hop)
  C) GAP    : gap interni al seed -> vettura di collegamento o refezione
  D) RIENT. : rientro fine seed -> deposito (vettura/condotta/FR)
  E) VALID  : prestazione, condotta, refezione, riposo

Questo modulo espone assemble_day(seed, deposito, all_day_segments, ...)
che produce una SEQUENZA COMPLETA DI SEGMENTI ordinati per orario, con
il flag is_deadhead correttamente impostato (True per vettura, False
per condotta).

La sequenza viene poi passata al validator esistente per score + regole.
"""
from __future__ import annotations

from typing import Optional

from ..validator.rules import _time_to_min, _min_to_time
from ..constants import (
    MEAL_MIN,
    MEAL_WINDOW_1_START, MEAL_WINDOW_1_END,
    MEAL_WINDOW_2_START, MEAL_WINDOW_2_END,
)
from . import position_finder


# Parametri giornata
PRESENTATION_MIN = 15  # 15' di accessori iniziali prima del primo segmento
END_MIN = 10           # 10' di accessori finali dopo l'ultimo segmento
MAX_DAY_DURATION = 520  # 8h40 max prestazione (vincolo contrattuale ~8h30)

# Step 2 (23/04/2026) — fase C refezione
# Richiesta utente: refezione sempre posta, almeno 10' dopo arrivo di un
# treno (o dopo ACCa/ACCp quando cableremo gli accessori a Step 6).
# Se nessuno dei 5 slot rispetta le finestre contrattuali, la giornata
# viene scartata.
REFEZ_GAP_AFTER_ARR = 10   # min 10' dopo arrivo treno precedente
REFEZ_GAP_BEFORE_DEP = 10  # min 10' tra fine refezione e partenza treno successivo
REFEZ_WINDOWS = [
    (MEAL_WINDOW_1_START, MEAL_WINDOW_1_END),  # 11:30-15:30
    (MEAL_WINDOW_2_START, MEAL_WINDOW_2_END),  # 18:30-22:30
]


def _seg_is_deadhead(seg: dict) -> bool:
    return bool(seg.get("is_deadhead", False))


def _seg_is_refezione(seg: dict) -> bool:
    return bool(seg.get("is_refezione", False))


def _seg_duration(seg: dict) -> int:
    dep = _time_to_min(seg["dep_time"])
    arr = _time_to_min(seg["arr_time"])
    if arr < dep:
        arr += 1440
    return arr - dep


def _refez_fits_in_window(start_min: int, duration: int = MEAL_MIN) -> bool:
    """True se [start_min, start_min+duration] cade interamente in una
    delle finestre contrattuali di refezione."""
    end_min = start_min + duration
    for w_start, w_end in REFEZ_WINDOWS:
        if start_min >= w_start and end_min <= w_end:
            return True
    return False


def _make_refez_segment(station: str, start_min: int,
                         duration: int = MEAL_MIN) -> dict:
    """Crea un segmento virtuale di refezione. Non e' condotta ne' vettura:
    e' una pausa in stazione di durata fissa (30' standard)."""
    return {
        "train_id": "REFEZ",
        "from_station": station,
        "to_station": station,
        "dep_time": _min_to_time(start_min),
        "arr_time": _min_to_time(start_min + duration),
        "material_turn_id": None,
        "is_deadhead": False,
        "is_refezione": True,
    }


def _find_refez_start_in_gap(earliest_min: int,
                              latest_min: int) -> Optional[int]:
    """Cerca il minuto di inizio refezione dentro [earliest, latest] tale
    che la refezione intera [start, start+MEAL_MIN] cada dentro una delle
    finestre contrattuali. Preferenza: prima finestra cronologicamente
    disponibile, start piu' presto possibile entro quella finestra.
    Ritorna None se nessuna soluzione."""
    if earliest_min > latest_min:
        return None
    best = None
    for w_start, w_end in REFEZ_WINDOWS:
        # La refezione puo' iniziare in [max(earliest, w_start),
        #                                 min(latest, w_end - MEAL_MIN)]
        t_min = max(earliest_min, w_start)
        t_max = min(latest_min, w_end - MEAL_MIN)
        if t_min <= t_max:
            if best is None or t_min < best:
                best = t_min
    return best


def _try_gap_slot(prev_seg: dict, next_seg: dict,
                   slot_num: int) -> Optional[dict]:
    """Tenta di piazzare la refezione nel gap tra due segmenti adiacenti.
    Usato per slot 1, 2, 3."""
    prev_arr = _time_to_min(prev_seg["arr_time"])
    next_dep = _time_to_min(next_seg["dep_time"])
    if next_dep < prev_arr:
        next_dep += 1440
    earliest = prev_arr + REFEZ_GAP_AFTER_ARR
    latest = next_dep - REFEZ_GAP_BEFORE_DEP - MEAL_MIN
    start = _find_refez_start_in_gap(earliest, latest)
    if start is None:
        return None
    station = (prev_seg.get("to_station", "") or "").upper()
    return {"segment": _make_refez_segment(station, start),
            "slot": slot_num}


def _try_place_refezione(positioning: list, productive: list,
                          retur: list, deposito: str) -> Optional[dict]:
    """
    Prova a piazzare la refezione in uno dei 5 slot possibili, in ordine
    di preferenza (richiesta utente 22-23/04/2026):

      1. Dentro il gap tra i due treni del seed (se seed=2 treni)
      2. Tra posizionamento e seed
      3. Tra seed e rientro
      4. All'inizio del turno (se cade in finestra)
      5. Alla fine del turno (se cade in finestra)

    Per slot 1/2/3 la refezione puo' scorrere dentro il gap per trovare
    una posizione dentro finestra. Per slot 4/5 la posizione e' fissa
    (ancorata al primo/ultimo segmento) e deve cadere in finestra "as is".

    Ritorna:
      dict {"segment": <refez_seg>, "slot": <1|2|3|4|5>} se trovato
      None se nessuno slot valido (giornata da scartare)
    """
    # Slot 1: dentro il seed (solo se seed=2 treni)
    if len(productive) == 2:
        result = _try_gap_slot(productive[0], productive[1], 1)
        if result:
            return result

    # Slot 2: tra posizionamento e seed
    if positioning:
        result = _try_gap_slot(positioning[-1], productive[0], 2)
        if result:
            return result

    # Slot 3: tra seed e rientro
    if retur:
        result = _try_gap_slot(productive[-1], retur[0], 3)
        if result:
            return result

    # Slot 4: all'inizio del turno (posizione fissa, ancorata al primo seg)
    first_seg = positioning[0] if positioning else productive[0]
    first_dep = _time_to_min(first_seg["dep_time"])
    start4 = first_dep - REFEZ_GAP_BEFORE_DEP - MEAL_MIN
    if start4 >= 0 and _refez_fits_in_window(start4):
        station = (first_seg.get("from_station", "") or deposito).upper()
        return {"segment": _make_refez_segment(station, start4), "slot": 4}

    # Slot 5: alla fine del turno (posizione fissa, ancorata all'ultimo seg)
    last_seg = retur[-1] if retur else productive[-1]
    last_arr = _time_to_min(last_seg["arr_time"])
    start5 = last_arr + REFEZ_GAP_AFTER_ARR
    if _refez_fits_in_window(start5):
        station = (last_seg.get("to_station", "") or deposito).upper()
        return {"segment": _make_refez_segment(station, start5), "slot": 5}

    return None


def assemble_day(
    seed: dict,
    deposito: str,
    all_day_segments: list,
    used_train_ids: set = None,
    allow_fr_end: bool = True,
    fr_stations: set = None,
) -> Optional[dict]:
    """
    Assembla una giornata completa dato un seed produttivo.

    Args:
        seed: dict da seed_enumerator con {trains, from_station,
              to_station, first_dep_min, last_arr_min, condotta_min}
        deposito: impianto del PdC (es. 'ALESSANDRIA')
        all_day_segments: tutti i segmenti del giorno (abilitati,
              no filtro zona; usati per posizionamento + rientro)
        used_train_ids: treni gia' consumati (escludi)
        allow_fr_end: se True, accetta giornate che finiscono in
              stazione FR autorizzata (no rientro)
        fr_stations: set di stazioni FR autorizzate (case-insensitive)

    Returns:
        dict con {
          "segments": list di segmenti ordinati (produttivi + vettura),
          "from_station": stazione inizio giornata (deposito o prima vettura),
          "to_station": stazione fine giornata,
          "first_dep_min": inizio primo segmento,
          "last_arr_min": fine ultimo segmento,
          "prestazione_min": first_dep-presentation .. last_arr+end,
          "condotta_min": totale condotta (solo seed produttivo),
          "n_positioning": numero segmenti vettura di posizionamento,
          "n_return": numero segmenti vettura di rientro,
          "returns_depot": bool,
          "is_fr": bool,
        }
        None se nessuna combinazione valida trovata.
    """
    dep = (deposito or "").upper().strip()
    if not dep or not seed or not seed.get("trains"):
        return None
    used = set(used_train_ids or [])
    # Aggiungi train_id del seed agli esclusi per pos/return
    for t in seed["trains"]:
        used.add(t.get("train_id", ""))
    fr = {s.upper() for s in (fr_stations or set())}

    seed_from = seed["from_station"].upper()
    seed_to = seed["to_station"].upper()
    seed_first_dep = seed["first_dep_min"]
    seed_last_arr = seed["last_arr_min"]

    # --- POSIZIONAMENTO: dal deposito a seed_from ---
    if seed_from == dep:
        # Nessun posizionamento necessario
        positioning = []
    else:
        # Regola hop (22/04/2026): prova hop=1, fallback hop=2 solo se vuoto.
        # arrive_by usa MIN_CHANGE_MIN (10') per il cambio verso il primo seed.
        pos_options = position_finder.find_position_path(
            all_day_segments,
            from_station=dep,
            to_station=seed_from,
            arrive_by_min=seed_first_dep - position_finder.MIN_CHANGE_MIN,
            depart_after_min=0,
            exclude_train_ids=used,
            max_hops=position_finder.MAX_HOPS,
        )
        if not pos_options:
            pos_options = position_finder.find_position_path(
                all_day_segments,
                from_station=dep,
                to_station=seed_from,
                arrive_by_min=seed_first_dep - position_finder.MIN_CHANGE_MIN,
                depart_after_min=0,
                exclude_train_ids=used,
                max_hops=position_finder.MAX_HOPS_FALLBACK,
            )
        if not pos_options:
            return None  # impossibile posizionare nemmeno con fallback
        # Scegli il posizionamento che arriva piu' tardi possibile
        # (riduce tempo morto) ma rispetta il vincolo arrive_by
        positioning = max(
            pos_options,
            key=lambda path: _time_to_min(path[-1]["arr_time"])
            if _time_to_min(path[-1]["arr_time"]) >= _time_to_min(path[0]["dep_time"])
            else _time_to_min(path[-1]["arr_time"]) + 1440,
        )
        # Marca tutti i segmenti posizionamento come deadhead
        for s in positioning:
            s["is_deadhead"] = True
        # Aggiungi train_id ad used
        for s in positioning:
            used.add(s.get("train_id", ""))

    # --- SEED PRODUTTIVO: aggiunto tale e quale (is_deadhead=False) ---
    # Assicuriamo che is_deadhead sia False (produttivo)
    productive = []
    for t in seed["trains"]:
        t_copy = {**t}
        t_copy["is_deadhead"] = False
        productive.append(t_copy)

    # --- RIENTRO: da seed_to al deposito ---
    if seed_to == dep:
        # Seed gia' torna al deposito
        retur = []
        returns_depot = True
        is_fr = False
    else:
        # Regola hop (22/04/2026): prova hop=1, fallback hop=2 solo se vuoto.
        # depart_after usa MIN_CHANGE_MIN (10') dopo arrivo seed.
        ret_options = position_finder.find_return_path(
            all_day_segments,
            from_station=seed_to,
            deposito=dep,
            depart_after_min=seed_last_arr + position_finder.MIN_CHANGE_MIN,
            exclude_train_ids=used,
            max_hops=position_finder.MAX_HOPS,
        )
        if not ret_options:
            ret_options = position_finder.find_return_path(
                all_day_segments,
                from_station=seed_to,
                deposito=dep,
                depart_after_min=seed_last_arr + position_finder.MIN_CHANGE_MIN,
                exclude_train_ids=used,
                max_hops=position_finder.MAX_HOPS_FALLBACK,
            )
        if ret_options:
            retur = ret_options[0]  # primo = arrivo piu' presto
            for s in retur:
                s["is_deadhead"] = True
            returns_depot = True
            is_fr = False
        else:
            # Nessun rientro trovato. Accetta solo se FR legittimo
            if allow_fr_end and seed_to in fr:
                retur = []
                returns_depot = False
                is_fr = True
            else:
                return None  # impossibile chiudere

    # --- FASE C: REFEZIONE (Step 2, 23/04/2026) ---
    # La refezione e' OBBLIGATORIA. Se non c'e' slot valido, la giornata
    # viene scartata.
    refez_result = _try_place_refezione(positioning, productive, retur, dep)
    if refez_result is None:
        return None
    refez_seg = refez_result["segment"]
    refez_slot = refez_result["slot"]

    # --- ASSEMBLA SEQUENZA ORDINATA (refezione inserita nello slot giusto) ---
    if refez_slot == 1:
        # Dentro il seed: tra productive[0] e productive[1]
        all_segments = positioning + [productive[0], refez_seg, productive[1]] + retur
    elif refez_slot == 2:
        # Tra posizionamento e seed
        all_segments = positioning + [refez_seg] + productive + retur
    elif refez_slot == 3:
        # Tra seed e rientro
        all_segments = positioning + productive + [refez_seg] + retur
    elif refez_slot == 4:
        # All'inizio del turno
        all_segments = [refez_seg] + positioning + productive + retur
    elif refez_slot == 5:
        # Alla fine del turno
        all_segments = positioning + productive + retur + [refez_seg]
    else:
        all_segments = positioning + productive + retur  # fallback difensivo

    # Calcoli sommari
    first_dep_min = (_time_to_min(all_segments[0]["dep_time"])
                     if all_segments else 0)
    last_arr_min = (_time_to_min(all_segments[-1]["arr_time"])
                    if all_segments else 0)
    if last_arr_min < first_dep_min:
        last_arr_min += 1440

    # Prestazione = presentation + (last_arr - first_dep) + end
    prestazione_min = last_arr_min - first_dep_min + PRESENTATION_MIN + END_MIN

    # Condotta = solo segmenti produttivi (no deadhead, no refezione)
    condotta_min = sum(_seg_duration(s) for s in all_segments
                       if not _seg_is_deadhead(s) and not _seg_is_refezione(s))

    # Vincolo hard: prestazione <= 8h40 ~ 520 min (slack sul 8h30 contratto)
    if prestazione_min > MAX_DAY_DURATION:
        return None

    # Determina stazione inizio/fine effettive
    day_from = (all_segments[0].get("from_station", "") or "").upper() if all_segments else dep
    day_to = (all_segments[-1].get("to_station", "") or "").upper() if all_segments else dep

    return {
        "segments": all_segments,
        "from_station": day_from,
        "to_station": day_to,
        "first_dep_min": first_dep_min,
        "last_arr_min": last_arr_min,
        "prestazione_min": prestazione_min,
        "condotta_min": condotta_min,
        "n_positioning": len(positioning),
        "n_return": len(retur),
        "returns_depot": returns_depot,
        "is_fr": is_fr,
    }
