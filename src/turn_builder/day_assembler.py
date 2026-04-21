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

from ..validator.rules import _time_to_min
from . import position_finder


# Parametri giornata
PRESENTATION_MIN = 15  # 15' di accessori iniziali prima del primo segmento
END_MIN = 10           # 10' di accessori finali dopo l'ultimo segmento
MAX_DAY_DURATION = 520  # 8h40 max prestazione (vincolo contrattuale ~8h30)


def _seg_is_deadhead(seg: dict) -> bool:
    return bool(seg.get("is_deadhead", False))


def _seg_duration(seg: dict) -> int:
    dep = _time_to_min(seg["dep_time"])
    arr = _time_to_min(seg["arr_time"])
    if arr < dep:
        arr += 1440
    return arr - dep


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
        pos_options = position_finder.find_position_path(
            all_day_segments,
            from_station=dep,
            to_station=seed_from,
            arrive_by_min=seed_first_dep - 5,  # 5' cambio al primo seed
            depart_after_min=0,
            exclude_train_ids=used,
        )
        if not pos_options:
            return None  # impossibile posizionare
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
        ret_options = position_finder.find_return_path(
            all_day_segments,
            from_station=seed_to,
            deposito=dep,
            depart_after_min=seed_last_arr + 5,
            exclude_train_ids=used,
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

    # --- ASSEMBLA SEQUENZA ORDINATA ---
    all_segments = positioning + productive + retur

    # Calcoli sommari
    first_dep_min = (_time_to_min(all_segments[0]["dep_time"])
                     if all_segments else 0)
    last_arr_min = (_time_to_min(all_segments[-1]["arr_time"])
                    if all_segments else 0)
    if last_arr_min < first_dep_min:
        last_arr_min += 1440

    # Prestazione = presentation + (last_arr - first_dep) + end
    prestazione_min = last_arr_min - first_dep_min + PRESENTATION_MIN + END_MIN

    # Condotta = solo segmenti produttivi (no deadhead)
    condotta_min = sum(_seg_duration(s) for s in all_segments
                       if not _seg_is_deadhead(s))

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
