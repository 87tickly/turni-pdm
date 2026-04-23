"""
Week Assembler — orchestra l'assemblaggio di un ciclo settimanale 5+2.

Per ogni giorno lavorativo:
  1. Tenta i seed candidati (ordinati per score) via day_assembler
  2. Accetta il primo che rispetta i vincoli riposo dal giorno precedente
     (11h standard, 14h se fine giornata precedente in 00:01-01:00,
      16h dopo turno notturno)
  3. Se nessuno funziona, marca il giorno come "scoperto" (None)

I 2 giorni di riposo chiudono il ciclo.

Questo modulo NON fa ottimizzazione (genetic/SA): e' un greedy pulito
che accetta il primo seed valido. L'ottimizzazione avverra' a Step 9
riciclando le primitive da auto_builder.py.

Vincoli implementati:
  - Riposo tra turni: 11h / 14h / 16h (da src/constants.py)
  - FR per settimana: max 1 approvata; candidate contate a parte
  - Ore settimanali: calcolate, non imposte hard (scoring a Step 9)

NON implementato qui (future):
  - Ciclo 5+2 ruotato su 7 giorni (LMXGVS + D riposo) — per ora genera
    solo "5 giorni lavorativi" consecutivi
  - Contatore FR 28 giorni (richiede persistenza storica del PdC)
  - Score globale (rinviato a Step 9 dove si integra con auto_builder)
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Callable, Optional
import sqlite3

from ..constants import (
    REST_STANDARD_H,
    REST_AFTER_001_0100_H,
    REST_AFTER_NIGHT_H,
    NIGHT_START,
    NIGHT_END,
)
from ..validator.rules import _time_to_min
from . import day_assembler


MAX_FR_PER_WEEK = 1  # max 1 FR approvata per settimana (richiesta utente)


# ---------------------------------------------------------------------------
# Utility: classificazione giornata per riposo richiesto
# ---------------------------------------------------------------------------

def _day_ends_in_001_0100_window(day_result: dict) -> bool:
    """True se la giornata termina tra 00:01 e 01:00 (esclusi).
    last_arr_min e' in minuti dalla mezzanotte del giorno della giornata.
    Se ha superato le 24h (overnight), prendiamo il modulo 1440."""
    if not day_result:
        return False
    last = day_result.get("last_arr_min", 0) % 1440
    night_start_m = _time_to_min(NIGHT_START)  # 1 = 00:01
    night_end_m = _time_to_min(NIGHT_END)      # 60 = 01:00
    return night_start_m <= last <= night_end_m


def _day_is_notturno(day_result: dict) -> bool:
    """True se la giornata contiene segmenti operativi tra 00:01 e 06:00.
    Definizione semplificata: guardiamo se un segmento (condotta o vettura,
    escluso refez) inizia o finisce in quella fascia."""
    if not day_result:
        return False
    night_start_m = _time_to_min(NIGHT_START)  # 1
    night_cutoff_m = 6 * 60  # 06:00 = fine fascia critica
    for seg in day_result.get("segments", []):
        if seg.get("is_refezione"):
            continue
        dep = _time_to_min(seg["dep_time"])
        arr = _time_to_min(seg["arr_time"])
        if arr < dep:
            arr += 1440
        # Un segmento tocca la fascia se [dep % 1440, arr % 1440] interseca
        dep_day = dep % 1440
        arr_day = arr % 1440
        # Caso semplice non-overnight: controlla sovrapposizione con [1, 360]
        if dep_day <= arr_day:
            if max(dep_day, night_start_m) < min(arr_day, night_cutoff_m):
                return True
        else:
            # Overnight: [dep_day, 1440] U [0, arr_day]
            if dep_day <= night_cutoff_m or arr_day >= night_start_m:
                return True
    return False


def required_rest_min(day_result: dict) -> int:
    """Minuti di riposo richiesti DOPO questa giornata prima della
    successiva. Si applica la regola piu' stringente che si attiva."""
    if not day_result:
        return REST_STANDARD_H * 60
    if _day_is_notturno(day_result):
        return REST_AFTER_NIGHT_H * 60
    if _day_ends_in_001_0100_window(day_result):
        return REST_AFTER_001_0100_H * 60
    return REST_STANDARD_H * 60


# ---------------------------------------------------------------------------
# Assemblaggio settimana
# ---------------------------------------------------------------------------

def assemble_week(
    pdc_id: str,
    deposito: str,
    days_input: list[dict],
    fr_stations: Optional[set] = None,
    fr_candidate_stations: Optional[set] = None,
    get_material_segments: Optional[Callable] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> dict:
    """
    Assembla una settimana lavorativa (5 giorni) secondo il metodo v4.

    Args:
        pdc_id: identificativo del PdC (usato per lettura FR approvate
            dal DB se conn fornita, e per eventuale registrazione CV)
        deposito: impianto del PdC
        days_input: lista di 5 dict con:
            {
              "date": date,
              "seed_candidates": list[seed_dict] ordinati per score desc,
              "all_day_segments": list (pool segmenti del giorno),
            }
        fr_stations: FR gia' approvate per il PdC (dal DB). Se None e conn
            fornita, caricate da pdc_fr_approved.
        fr_candidate_stations: stazioni da proporre come candidate FR
        get_material_segments: callback accessori
        conn: connessione DB per letture FR e eventuale persistenza CV

    Returns:
        {
          "pdc_id": str,
          "days": [day_result_or_None, ...],     # 5 elementi + 2 riposo None
          "metrics": {
            "n_lavorative_ok": int,    # giornate con day_result valido
            "n_scoperte": int,         # giornate saltate
            "prestazione_tot_min": int,
            "condotta_tot_min": int,
            "hours_week": float,
            "n_fr_approvate": int,
            "n_fr_candidate": int,
            "rest_violations": list[str],  # messaggi diagnostici
          }
        }
    """
    # Carica FR approvate da DB se non passate esplicitamente
    if fr_stations is None:
        if conn is not None:
            from . import fr_registry
            fr_stations = fr_registry.list_approved(conn, pdc_id)
        else:
            fr_stations = set()

    # Primo giro: 5 giorni lavorativi
    results: list[Optional[dict]] = []
    rest_violations: list[str] = []
    n_fr_approvate = 0
    n_fr_candidate = 0
    prev_day_end_abs_min: Optional[int] = None   # minuti ass dal lunedi' 00:00
    prev_day_required_rest: int = 0

    for idx, day in enumerate(days_input):
        day_date = day.get("date")
        seed_candidates = day.get("seed_candidates", [])
        all_day_segs = day.get("all_day_segments", [])

        # Vincolo FR settimanale: se ho gia' consumato MAX_FR_PER_WEEK
        # approvate, rimuovo FR approvate per questo giorno (forza rientro
        # o scarto). Candidate restano disponibili perche' sono proposte.
        effective_fr = fr_stations if n_fr_approvate < MAX_FR_PER_WEEK else set()

        # Prova i seed in ordine di score finche' uno rispetta il riposo
        chosen_result: Optional[dict] = None
        for seed in seed_candidates:
            day_res = day_assembler.assemble_day(
                seed=seed,
                deposito=deposito,
                all_day_segments=all_day_segs,
                fr_stations=effective_fr,
                fr_candidate_stations=fr_candidate_stations,
                day_date=day_date,
                get_material_segments=get_material_segments,
            )
            if day_res is None:
                continue

            # Check vincolo riposo dal giorno precedente
            if prev_day_end_abs_min is not None:
                day_start_abs = idx * 1440 + day_res["first_dep_min"]
                actual_rest = day_start_abs - prev_day_end_abs_min
                if actual_rest < prev_day_required_rest:
                    # Non rispetta il riposo: scarta questo seed e prova il prossimo
                    continue

            chosen_result = day_res
            break

        results.append(chosen_result)

        if chosen_result is not None:
            # Aggiorna contatori FR
            if chosen_result.get("is_fr"):
                if chosen_result.get("fr_candidate"):
                    n_fr_candidate += 1
                else:
                    n_fr_approvate += 1
            # Calcola fine giornata in minuti assoluti
            prev_day_end_abs_min = idx * 1440 + chosen_result["last_arr_min"]
            prev_day_required_rest = required_rest_min(chosen_result)
        else:
            # Giornata scoperta: riposa almeno standard prima della successiva
            prev_day_required_rest = REST_STANDARD_H * 60

    # Aggiungo i 2 giorni di riposo
    results.extend([None, None])

    # Metriche
    prestazione_tot = sum(d["prestazione_min"] for d in results if d)
    condotta_tot = sum(d["condotta_min"] for d in results if d)
    n_ok = sum(1 for d in results if d is not None)
    n_scoperte = 5 - n_ok  # su 5 giorni lavorativi attesi

    return {
        "pdc_id": pdc_id,
        "days": results,
        "metrics": {
            "n_lavorative_ok": n_ok,
            "n_scoperte": n_scoperte,
            "prestazione_tot_min": prestazione_tot,
            "condotta_tot_min": condotta_tot,
            "hours_week": round(prestazione_tot / 60, 2),
            "n_fr_approvate": n_fr_approvate,
            "n_fr_candidate": n_fr_candidate,
            "rest_violations": rest_violations,
        },
    }
