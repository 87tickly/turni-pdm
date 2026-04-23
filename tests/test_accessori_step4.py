"""
Test Step 4 (23/04/2026) — Modulo accessori (gap materiale >= 65 min).

Richiesta utente: accessori inseriti guardando il giro materiale.
Gap materiale prima (dopo) del segmento >= 65 min -> ACCp (ACCa) pieno.
Sotto soglia -> accessorio 0.
"""
from __future__ import annotations

from datetime import date

from src.turn_builder.accessori import (
    compute_material_gaps,
    determine_accessori,
    apply_accessori,
    GAP_THRESHOLD_MIN,
    ACCP_CONDOTTA, ACCA_CONDOTTA,
    ACCP_VETTURA, ACCA_VETTURA,
    ACCP_PRERISCALDO,
)


def _seg(tid, frm, to, dep, arr, mtid=1, day_index=1, seq=0,
         is_deadhead=False, is_preheat=False):
    return {
        "train_id": tid,
        "from_station": frm,
        "to_station": to,
        "dep_time": dep,
        "arr_time": arr,
        "material_turn_id": mtid,
        "day_index": day_index,
        "seq": seq,
        "is_deadhead": is_deadhead,
        "is_preheat": is_preheat,
    }


# ---------------------------------------------------------------------------
# compute_material_gaps
# ---------------------------------------------------------------------------

def test_gap_primo_segmento_del_giorno():
    # Solo 1 segmento -> gap_before=None e gap_after=None.
    s = _seg("T1", "ALE", "MI", "10:00", "11:00")
    gb, ga = compute_material_gaps([s], s)
    assert gb is None
    assert ga is None


def test_gap_segmento_centrale():
    # 3 segmenti sullo stesso materiale. Target = middle.
    # T1 arr 10:00, T2 dep 11:30, T2 arr 12:30, T3 dep 14:00
    s1 = _seg("T1", "ALE", "MI", "09:00", "10:00")
    s2 = _seg("T2", "MI", "PAV", "11:30", "12:30")
    s3 = _seg("T3", "PAV", "ALE", "14:00", "15:00")
    gb, ga = compute_material_gaps([s1, s2, s3], s2)
    assert gb == 90   # 11:30 - 10:00
    assert ga == 90   # 14:00 - 12:30


def test_gap_ignora_refezione():
    # La refezione virtuale non deve contare nella catena materiale.
    refez = {"train_id": "REFEZ", "from_station": "MI", "to_station": "MI",
             "dep_time": "12:00", "arr_time": "12:30", "is_refezione": True}
    s1 = _seg("T1", "ALE", "MI", "09:00", "10:00")
    s2 = _seg("T2", "MI", "PAV", "13:30", "14:30")
    gb, ga = compute_material_gaps([s1, refez, s2], s2)
    # Gap = 13:30 - 10:00 = 210 min (refez esclusa)
    assert gb == 210


def test_gap_overnight_arrivo_successivo_mezzanotte():
    # Target arriva alle 23:00, successivo parte alle 01:00 (giorno dopo
    # nel tempo di treno, ma stesso day_index). Uso seq per disambiguare
    # l'ordine (come fa il parser PDF in produzione). Gap = 2h = 120 min.
    s1 = _seg("T1", "ALE", "MI", "22:00", "23:00", seq=1)
    s2 = _seg("T2", "MI", "ALE", "01:00", "02:00", seq=2)
    gb, ga = compute_material_gaps([s1, s2], s1)
    assert ga == 120


# ---------------------------------------------------------------------------
# determine_accessori
# ---------------------------------------------------------------------------

D_WINTER = date(2026, 12, 15)   # periodo preriscaldo attivo
D_SUMMER = date(2026, 7, 15)    # periodo non preriscaldo


def test_condotta_gap_ampio_entrambi():
    s = _seg("T1", "ALE", "MI", "10:00", "11:00")
    r = determine_accessori(s, gap_before=80, gap_after=90, day_date=D_SUMMER)
    assert r["accp_min"] == ACCP_CONDOTTA  # 40
    assert r["acca_min"] == ACCA_CONDOTTA  # 40


def test_condotta_gap_before_sotto_soglia():
    s = _seg("T1", "ALE", "MI", "10:00", "11:00")
    r = determine_accessori(s, gap_before=60, gap_after=90, day_date=D_SUMMER)
    assert r["accp_min"] == 0       # gap <65 -> niente ACCp
    assert r["acca_min"] == ACCA_CONDOTTA


def test_vettura_gap_ampio():
    s = _seg("T1", "ALE", "MI", "10:00", "11:00", is_deadhead=True)
    r = determine_accessori(s, gap_before=100, gap_after=100, day_date=D_SUMMER)
    assert r["accp_min"] == ACCP_VETTURA  # 15
    assert r["acca_min"] == ACCA_VETTURA  # 10


def test_preriscaldo_inverno():
    s = _seg("T1", "ALE", "MI", "05:00", "06:30", is_preheat=True)
    r = determine_accessori(s, gap_before=200, gap_after=100, day_date=D_WINTER)
    assert r["accp_min"] == ACCP_PRERISCALDO  # 80
    # ACCa condotta standard (il preriscaldo e' solo in partenza)
    assert r["acca_min"] == ACCA_CONDOTTA


def test_preriscaldo_estate_non_si_applica():
    # Segmento e' is_preheat ma data e' estate -> ACCp torna a condotta standard.
    s = _seg("T1", "ALE", "MI", "05:00", "06:30", is_preheat=True)
    r = determine_accessori(s, gap_before=200, gap_after=100, day_date=D_SUMMER)
    assert r["accp_min"] == ACCP_CONDOTTA  # 40, non 80


def test_gap_none_assume_ampio():
    # gap_before=None (primo segmento del giorno) -> accessori applicati.
    s = _seg("T1", "ALE", "MI", "10:00", "11:00")
    r = determine_accessori(s, gap_before=None, gap_after=None, day_date=D_SUMMER)
    assert r["accp_min"] == ACCP_CONDOTTA
    assert r["acca_min"] == ACCA_CONDOTTA


def test_boundary_gap_esatto_65_e_64():
    s = _seg("T1", "ALE", "MI", "10:00", "11:00")
    # 65 esatti -> accessorio applicato
    r65 = determine_accessori(s, gap_before=65, gap_after=65, day_date=D_SUMMER)
    assert r65["accp_min"] == ACCP_CONDOTTA
    assert r65["acca_min"] == ACCA_CONDOTTA
    # 64 -> no accessorio
    r64 = determine_accessori(s, gap_before=64, gap_after=64, day_date=D_SUMMER)
    assert r64["accp_min"] == 0
    assert r64["acca_min"] == 0


# ---------------------------------------------------------------------------
# apply_accessori (orchestratore)
# ---------------------------------------------------------------------------

def test_apply_accessori_full_flow():
    # Giro materiale 3 treni. Target = middle, condotta.
    # Gap prima = 90 (>= 65), gap dopo = 40 (< 65).
    s1 = _seg("T1", "ALE", "MI", "09:00", "10:00")
    s2 = _seg("T2", "MI", "PAV", "11:30", "12:30")
    s3 = _seg("T3", "PAV", "ALE", "13:10", "14:00")
    result = apply_accessori([s1, s2, s3], s2, D_SUMMER)
    assert result["accp_min"] == ACCP_CONDOTTA  # gap_before=90 OK
    assert result["acca_min"] == 0               # gap_after=40 no
    assert result["gap_before"] == 90
    assert result["gap_after"] == 40


def test_apply_accessori_preheat_inverno():
    # Treno ● in dic con gap ampi -> 80 min ACCp
    s1 = _seg("T1", "ALE", "MI", "03:00", "04:00")
    s2 = _seg("T2", "MI", "ALE", "05:30", "06:30", is_preheat=True)
    s3 = _seg("T3", "ALE", "MI", "09:00", "10:00")  # gap dopo = 150 min
    result = apply_accessori([s1, s2, s3], s2, D_WINTER)
    assert result["accp_min"] == ACCP_PRERISCALDO
    assert result["gap_before"] == 90   # 05:30 - 04:00
    assert result["gap_after"] == 150   # 09:00 - 06:30


def test_constants_sanity():
    # Guardrail: i valori numerici sono quelli concordati.
    assert GAP_THRESHOLD_MIN == 65
    assert ACCP_CONDOTTA == 40
    assert ACCA_CONDOTTA == 40
    assert ACCP_VETTURA == 15
    assert ACCA_VETTURA == 10
    assert ACCP_PRERISCALDO == 80
