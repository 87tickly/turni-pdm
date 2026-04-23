"""
Test Step 8 (23/04/2026) — week_assembler (livello settimanale 5+2).

Verifica:
- Orchestrazione 5 giorni lavorativi + 2 riposo
- Vincolo riposo 11h tra giornate
- Vincolo FR max 1 approvata/settimana
- Metriche aggregate (ore, condotta tot)
- Fallback quando un giorno non ha seed validi (scoperto)
"""
from __future__ import annotations

from datetime import date

from src.turn_builder import week_assembler


def _seg(tid, frm, to, dep, arr, mtid=1, day_index=1):
    return {
        "train_id": tid, "from_station": frm, "to_station": to,
        "dep_time": dep, "arr_time": arr,
        "material_turn_id": mtid, "day_index": day_index,
        "is_deadhead": False,
    }


def _seed(trains, frm, to, first_dep, last_arr, cond, score=100.0):
    return {
        "trains": trains, "from_station": frm, "to_station": to,
        "first_dep_min": first_dep, "last_arr_min": last_arr,
        "condotta_min": cond, "score": score,
    }


def _day_input(day_date, seed_trains_list):
    """Costruisce input giornata con seed di 1 treno condotta."""
    seeds = []
    all_segs = []
    for trains in seed_trains_list:
        first_dep = trains[0]["dep_time"]
        last_arr = trains[-1]["arr_time"]
        from src.turn_builder.seed_enumerator import _time_to_min
        fd_min = _time_to_min(first_dep)
        la_min = _time_to_min(last_arr)
        if la_min < fd_min:
            la_min += 1440
        cond = sum((_time_to_min(t["arr_time"]) - _time_to_min(t["dep_time"]))
                   % 1440 for t in trains)
        seeds.append(_seed(trains, trains[0]["from_station"],
                           trains[-1]["to_station"], fd_min, la_min, cond))
        all_segs.extend(trains)
    return {"date": day_date, "seed_candidates": seeds,
            "all_day_segments": all_segs}


def _make_refez_segment_windowed(day_dep_min):
    """Ritorna un segmento che garantisce finestra refez (slot 4): crea
    un seed che parta alle 13:00 cosi' che refez start=12:20 sia in finestra."""
    pass  # helper placeholder


# ---------------------------------------------------------------------------
# Test base: settimana completa
# ---------------------------------------------------------------------------

def test_settimana_5_giorni_ok():
    # 5 giornate identiche: seed 1 treno ALE-ALE 13:00-14:30. refez slot 4
    # (12:20-12:50 in finestra). Ogni giornata fini' alle 14:30. Prossima
    # parte alle 13:00 del giorno dopo: gap = 24*60 - 14:30 + 13:00 =
    # 1440 - 870 + 780 = 1350 min = 22.5h > 11h. OK riposo.
    days = []
    for d in range(5):
        t = _seg("T" + str(d), "ALE", "ALE", "13:00", "14:30", mtid=1+d)
        days.append(_day_input(date(2026, 4, 20 + d), [[t]]))

    result = week_assembler.assemble_week(
        pdc_id="PDC_A", deposito="ALE", days_input=days,
    )
    assert len(result["days"]) == 7  # 5 lav + 2 riposo
    assert result["metrics"]["n_lavorative_ok"] == 5
    assert result["metrics"]["n_scoperte"] == 0
    assert result["days"][5] is None
    assert result["days"][6] is None
    assert result["metrics"]["hours_week"] > 0


def test_riposo_11h_violato_scarta_seed():
    # Giorno 1: termina alle 22:00. Giorno 2 seed parte alle 06:00 il giorno
    # dopo. Gap = 24-22+6 = 8h. Violato (< 11h). Questo seed deve essere
    # scartato. Se non ci sono alternative, giornata scoperta.
    d1_train = _seg("T1", "ALE", "ALE", "13:00", "22:00", mtid=1)
    d2_early = _seg("T2_early", "ALE", "ALE", "06:00", "08:00", mtid=2)
    # Alternativa giornata 2: parte alle 12:00 (riposo 14h OK)
    d2_late = _seg("T2_late", "ALE", "ALE", "13:00", "15:00", mtid=3)

    days = [
        _day_input(date(2026, 4, 20), [[d1_train]]),
        # Seed in ordine: prima early (violerebbe riposo) poi late (OK)
        {
            "date": date(2026, 4, 21),
            "seed_candidates": [
                _seed([d2_early], "ALE", "ALE", 6 * 60, 8 * 60, 120),
                _seed([d2_late], "ALE", "ALE", 13 * 60, 15 * 60, 120),
            ],
            "all_day_segments": [d2_early, d2_late],
        },
        # 3 giorni riempitivi simili
        _day_input(date(2026, 4, 22),
                   [[_seg("T3", "ALE", "ALE", "13:00", "15:00", mtid=4)]]),
        _day_input(date(2026, 4, 23),
                   [[_seg("T4", "ALE", "ALE", "13:00", "15:00", mtid=5)]]),
        _day_input(date(2026, 4, 24),
                   [[_seg("T5", "ALE", "ALE", "13:00", "15:00", mtid=6)]]),
    ]

    result = week_assembler.assemble_week(
        pdc_id="PDC_A", deposito="ALE", days_input=days,
    )
    # Giornata 2 DEVE aver scelto il seed late (riposo OK), NON early.
    # Con refezione slot 4 il first_dep del turno e' 40 min prima del
    # treno: 12:20 (not 06:00 che avrebbe refez fuori finestra).
    d2 = result["days"][1]
    assert d2 is not None
    assert d2["first_dep_min"] >= 12 * 60  # dopo mezzogiorno, non mattina


def test_fr_max_una_per_settimana():
    # Tre giornate che finiscono in FR "ASTI" (approvata). Solo la prima
    # deve essere accettata come FR; le successive NON devono usare quel
    # FR slot (devono o trovare rientro o essere scartate).
    # Per semplicita' uso giornate terminanti in ASTI senza rientro possibile.
    segs_d1 = [_seg("T1", "ALE", "ASTI", "10:00", "11:30", mtid=1)]
    segs_d2 = [_seg("T2", "ALE", "ASTI", "10:00", "11:30", mtid=2)]
    segs_d3 = [_seg("T3", "ALE", "ASTI", "10:00", "11:30", mtid=3)]

    days = [
        _day_input(date(2026, 4, 20), [segs_d1]),
        _day_input(date(2026, 4, 21), [segs_d2]),
        _day_input(date(2026, 4, 22), [segs_d3]),
        _day_input(date(2026, 4, 23),
                   [[_seg("T4", "ALE", "ALE", "13:00", "15:00", mtid=4)]]),
        _day_input(date(2026, 4, 24),
                   [[_seg("T5", "ALE", "ALE", "13:00", "15:00", mtid=5)]]),
    ]

    result = week_assembler.assemble_week(
        pdc_id="PDC_A", deposito="ALE", days_input=days,
        fr_stations={"ASTI"},
    )
    # Dovrebbe esserci al massimo 1 FR approvata
    assert result["metrics"]["n_fr_approvate"] <= 1


def test_giornata_scoperta_quando_nessun_seed_valido():
    # Giorno 2 senza seed candidates -> scoperta
    d1 = _seg("T1", "ALE", "ALE", "13:00", "15:00", mtid=1)
    days = [
        _day_input(date(2026, 4, 20), [[d1]]),
        {"date": date(2026, 4, 21), "seed_candidates": [],
         "all_day_segments": []},
        _day_input(date(2026, 4, 22),
                   [[_seg("T3", "ALE", "ALE", "13:00", "15:00", mtid=3)]]),
        _day_input(date(2026, 4, 23),
                   [[_seg("T4", "ALE", "ALE", "13:00", "15:00", mtid=4)]]),
        _day_input(date(2026, 4, 24),
                   [[_seg("T5", "ALE", "ALE", "13:00", "15:00", mtid=5)]]),
    ]

    result = week_assembler.assemble_week(
        pdc_id="PDC_A", deposito="ALE", days_input=days,
    )
    assert result["days"][1] is None
    assert result["metrics"]["n_lavorative_ok"] == 4
    assert result["metrics"]["n_scoperte"] == 1


# ---------------------------------------------------------------------------
# Test classificazione giornate per riposo richiesto
# ---------------------------------------------------------------------------

def test_required_rest_standard():
    day = {"last_arr_min": 14 * 60 + 30, "segments": [
        {"dep_time": "10:00", "arr_time": "14:30", "is_refezione": False,
         "is_deadhead": False},
    ]}
    assert week_assembler.required_rest_min(day) == 11 * 60


def test_required_rest_dopo_notturno():
    # Turno che tocca 02:00-03:00 (fascia notturna 00:01-06:00)
    day = {"last_arr_min": 3 * 60, "segments": [
        {"dep_time": "22:00", "arr_time": "03:00", "is_refezione": False,
         "is_deadhead": False},
    ]}
    rest = week_assembler.required_rest_min(day)
    # Deve attivare REST_AFTER_NIGHT_H (16h) — 960 min
    assert rest == 16 * 60


def test_required_rest_fine_in_001_0100():
    # Turno finisce alle 00:30 (dentro finestra 00:01-01:00) ma non tocca
    # la fascia 00:01-06:00 oltre il solo arrivo.
    # NB: arriving at 00:30 means segment may touch 00:01-06:00 anyway
    # (end is after start). Quindi puo' essere classificato come notturno.
    # Test semplificato: verifichiamo che sia >= 14h (sia 14 che 16 ok).
    day = {"last_arr_min": 30, "segments": [
        {"dep_time": "20:00", "arr_time": "00:30", "is_refezione": False,
         "is_deadhead": False},
    ]}
    rest = week_assembler.required_rest_min(day)
    assert rest >= 14 * 60


def test_required_rest_day_none_default():
    # Giorno None -> riposo standard
    assert week_assembler.required_rest_min(None) == 11 * 60
