"""
Test Step 1 (22/04/2026) — Vincoli base v4 raffinati.

Verifica:
- MAX_HOPS = 1, MAX_HOPS_FALLBACK = 2, MIN_CHANGE_MIN = 10
- day_assembler: se hop=1 non trova posizionamento/rientro, prova hop=2
- con hop=1 disponibile, hop=2 non viene usato (preferenza al percorso piu' corto)
"""
from __future__ import annotations

from src.turn_builder import position_finder, day_assembler, seed_enumerator


def _seg(tid, frm, to, dep, arr, mtid=1):
    return {
        "train_id": tid,
        "from_station": frm,
        "to_station": to,
        "dep_time": dep,
        "arr_time": arr,
        "material_turn_id": mtid,
        "is_deadhead": False,
    }


def test_constants_updated():
    assert position_finder.MAX_HOPS == 1
    assert position_finder.MAX_HOPS_FALLBACK == 2
    assert position_finder.MIN_CHANGE_MIN == 10


def test_hop1_direct_path_used_when_available():
    # ALE -> MI diretto (hop=1). Un path 2-hop ALE->TO->MI esiste ma non deve
    # essere preferito se il diretto c'e'.
    segs = [
        _seg("T1", "ALE", "MI", "08:00", "09:00"),      # diretto
        _seg("T2", "ALE", "TO", "08:00", "08:20"),      # 2-hop parte 1
        _seg("T3", "TO", "MI", "08:40", "09:20"),       # 2-hop parte 2
    ]
    options = position_finder.find_position_path(
        segs, from_station="ALE", to_station="MI",
        arrive_by_min=10 * 60, depart_after_min=0,
        max_hops=position_finder.MAX_HOPS,
    )
    assert len(options) == 1
    assert len(options[0]) == 1  # hop=1
    assert options[0][0]["train_id"] == "T1"


def test_hop2_fallback_when_no_direct():
    # Nessun diretto ALE->MI, solo ALE->TO e TO->MI. hop=1 deve restituire
    # vuoto; la chiamata col fallback MAX_HOPS_FALLBACK trova il percorso 2-hop.
    segs = [
        _seg("T2", "ALE", "TO", "08:00", "08:20"),
        _seg("T3", "TO", "MI", "08:40", "09:20"),
    ]
    opt1 = position_finder.find_position_path(
        segs, from_station="ALE", to_station="MI",
        arrive_by_min=10 * 60, depart_after_min=0,
        max_hops=position_finder.MAX_HOPS,
    )
    assert opt1 == []  # hop=1 non trova
    opt2 = position_finder.find_position_path(
        segs, from_station="ALE", to_station="MI",
        arrive_by_min=10 * 60, depart_after_min=0,
        max_hops=position_finder.MAX_HOPS_FALLBACK,
    )
    assert len(opt2) == 1
    assert len(opt2[0]) == 2  # hop=2


def test_min_change_10min_enforced():
    # Cambio di 8 minuti (< 10) non deve essere accettato.
    segs = [
        _seg("T1", "ALE", "TO", "08:00", "08:20"),
        _seg("T2", "TO", "MI", "08:28", "09:00"),  # gap=8 min, troppo stretto
    ]
    opt = position_finder.find_position_path(
        segs, from_station="ALE", to_station="MI",
        arrive_by_min=10 * 60, depart_after_min=0,
        max_hops=2,
    )
    assert opt == []

    # Cambio di 10 min esatti deve passare.
    segs2 = [
        _seg("T1", "ALE", "TO", "08:00", "08:20"),
        _seg("T2", "TO", "MI", "08:30", "09:00"),  # gap=10 min esatti
    ]
    opt2 = position_finder.find_position_path(
        segs2, from_station="ALE", to_station="MI",
        arrive_by_min=10 * 60, depart_after_min=0,
        max_hops=2,
    )
    assert len(opt2) == 1


def test_day_assembler_fallback_chain():
    # Scenario: deposito ALE, seed su MI->ALE (1 treno), posizionamento solo
    # via 2-hop (ALE->TO->MI). Il day_assembler deve trovare il turno grazie
    # al fallback hop=2.
    seed_train = _seg("SEED", "MI", "ALE", "13:00", "14:30", mtid=99)
    pos1 = _seg("P1", "ALE", "TO", "08:00", "08:30")
    pos2 = _seg("P2", "TO", "MI", "09:00", "10:00")
    all_day = [seed_train, pos1, pos2]

    seed = {
        "trains": [seed_train],
        "from_station": "MI",
        "to_station": "ALE",
        "first_dep_min": 13 * 60,
        "last_arr_min": 14 * 60 + 30,
        "condotta_min": 90,
        "score": 100.0,
    }

    result = day_assembler.assemble_day(
        seed=seed, deposito="ALE", all_day_segments=all_day,
    )
    assert result is not None
    # Ho 2 segmenti posizionamento (hop=2) + 1 produttivo
    assert result["n_positioning"] == 2
    assert len(result["segments"]) == 3
