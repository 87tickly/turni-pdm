"""
Test Step 5 (23/04/2026) — CV registry con rilevamento + persistenza.

Verifica:
- detect_cv: identifica correttamente i CV (stesso materiale, train_id
  diverso, gap < 65 min, gap >= 10 min)
- compute_cv_split: split 50/50 default, stesso PdC -> tutto uno, gap
  ristretto -> uno prende minimo, altro il resto
- register_cv_side / read_cv: persistenza corretta su SQLite in-memory
- memoria condivisa: due PdC diversi registrano, Tm calcolato al secondo
"""
from __future__ import annotations

import sqlite3

import pytest

from src.turn_builder.cv_registry import (
    ensure_schema, detect_cv, compute_cv_split,
    register_cv_side, read_cv, validate_coverage,
    CV_MIN_PER_SIDE,
)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    ensure_schema(c)
    yield c
    c.close()


def _seg(tid, frm, to, dep, arr, mtid=1, day_index=1):
    return {
        "train_id": tid, "from_station": frm, "to_station": to,
        "dep_time": dep, "arr_time": arr,
        "material_turn_id": mtid, "day_index": day_index,
    }


# ---------------------------------------------------------------------------
# detect_cv
# ---------------------------------------------------------------------------

def test_detect_cv_gap_30min_stesso_materiale():
    prev = _seg("T1", "ALESSANDRIA", "MILANO PORTA GARIBALDI", "10:00", "11:00")
    nxt = _seg("T2", "MILANO PORTA GARIBALDI", "ALESSANDRIA", "11:30", "12:30")
    cv = detect_cv(prev, nxt)
    assert cv is not None
    assert cv["material_turn_id"] == 1
    assert cv["train_in_id"] == "T1"
    assert cv["train_out_id"] == "T2"
    assert cv["gap_min"] == 30


def test_detect_cv_gap_65_accessori_pieni_no_cv():
    # Gap 65 min = soglia: esattamente a soglia si applicano gli accessori
    # pieni, NON un CV.
    prev = _seg("T1", "ALESSANDRIA", "MILANO PORTA GARIBALDI", "10:00", "11:00")
    nxt = _seg("T2", "MILANO PORTA GARIBALDI", "ALESSANDRIA", "12:05", "13:00")
    cv = detect_cv(prev, nxt)
    assert cv is None


def test_detect_cv_gap_troppo_piccolo_no_cv():
    # Gap 5 min < CV_MIN_PER_SIDE (10) -> nessun CV gestibile
    prev = _seg("T1", "ALESSANDRIA", "MILANO PORTA GARIBALDI", "10:00", "11:00")
    nxt = _seg("T2", "MILANO PORTA GARIBALDI", "ALESSANDRIA", "11:05", "12:00")
    cv = detect_cv(prev, nxt)
    assert cv is None


def test_detect_cv_materiale_diverso_no_cv():
    prev = _seg("T1", "ALESSANDRIA", "MILANO PORTA GARIBALDI", "10:00", "11:00", mtid=1)
    nxt = _seg("T2", "MILANO PORTA GARIBALDI", "ALESSANDRIA", "11:30", "12:30", mtid=2)
    assert detect_cv(prev, nxt) is None


def test_detect_cv_stesso_train_id_no_cv():
    # Stesso train_id = continuazione dello stesso treno, non CV
    prev = _seg("T1", "ALESSANDRIA", "MILANO PORTA GARIBALDI", "10:00", "11:00")
    nxt = _seg("T1", "MILANO PORTA GARIBALDI", "ALESSANDRIA", "11:30", "12:30")
    assert detect_cv(prev, nxt) is None


def test_detect_cv_materiale_none_no_cv():
    prev = _seg("T1", "ALESSANDRIA", "MILANO PORTA GARIBALDI", "10:00", "11:00", mtid=None)
    nxt = _seg("T2", "MILANO PORTA GARIBALDI", "ALESSANDRIA", "11:30", "12:30", mtid=None)
    assert detect_cv(prev, nxt) is None


# ---------------------------------------------------------------------------
# NORMATIVA-PDC.md §9.2: CV ammesso solo in stazioni specifiche
# ---------------------------------------------------------------------------

def test_detect_cv_stazione_non_ammessa_no_cv():
    """CV a stazione NON §9.2 → detect_cv ritorna None (il caller userà
    accessori/PK). Es. LECCO MAGGIANICO è fermata intermedia senza
    deposito, il CV lì NON è ammesso."""
    prev = _seg("T1", "ALESSANDRIA", "LECCO MAGGIANICO", "10:00", "11:00")
    nxt = _seg("T2", "LECCO MAGGIANICO", "ALESSANDRIA", "11:30", "12:30")
    assert detect_cv(prev, nxt) is None


def test_detect_cv_tirano_capolinea_inversione_ammesso():
    """TIRANO è capolinea inversione §9.2.3 → CV ammesso."""
    prev = _seg("T1", "MILANO CENTRALE", "TIRANO", "10:00", "12:30")
    nxt = _seg("T2", "TIRANO", "MILANO CENTRALE", "12:55", "15:25")
    cv = detect_cv(prev, nxt)
    assert cv is not None
    assert cv["cv_station"] == "TIRANO"


def test_detect_cv_lecco_sede_deposito_ammesso():
    """LECCO è sede deposito §9.2.1 → CV ammesso."""
    prev = _seg("T1", "MILANO PORTA GARIBALDI", "LECCO", "10:00", "11:00")
    nxt = _seg("T2", "LECCO", "TIRANO", "11:30", "13:30")
    cv = detect_cv(prev, nxt)
    assert cv is not None
    assert cv["cv_station"] == "LECCO"


def test_detect_cv_mortara_deroga_ammesso():
    """MORTARA è deroga §9.2.2 → CV ammesso."""
    prev = _seg("T1", "PAVIA", "MORTARA", "10:00", "11:00")
    nxt = _seg("T2", "MORTARA", "ALESSANDRIA", "11:30", "12:30")
    cv = detect_cv(prev, nxt)
    assert cv is not None
    assert cv["cv_station"] == "MORTARA"


# ---------------------------------------------------------------------------
# compute_cv_split
# ---------------------------------------------------------------------------

def test_split_stesso_pdc_prende_tutto():
    cva, cvp = compute_cv_split(gap_min=40, same_pdc=True)
    assert cva == 40
    assert cvp == 0


def test_split_diversi_pdc_default_5050():
    cva, cvp = compute_cv_split(gap_min=40, same_pdc=False)
    assert cva + cvp == 40
    assert cva >= CV_MIN_PER_SIDE
    assert cvp >= CV_MIN_PER_SIDE
    # 40/2 = 20 esatti
    assert cva == 20
    assert cvp == 20


def test_split_gap_minimo_20_due_lati_da_10():
    cva, cvp = compute_cv_split(gap_min=20, same_pdc=False)
    assert cva == 10
    assert cvp == 10


def test_split_gap_stretto_sotto_20_sbilancia():
    # gap=15: 10 al minimo + 5 all'altro (che scende sotto minimo
    # contrattuale, sotto-caso documentato)
    cva, cvp = compute_cv_split(gap_min=15, same_pdc=False)
    assert cva == CV_MIN_PER_SIDE   # 10
    assert cvp == 5
    assert cva + cvp == 15


def test_split_gap_troppo_piccolo_raises():
    with pytest.raises(ValueError):
        compute_cv_split(gap_min=5, same_pdc=False)


# ---------------------------------------------------------------------------
# Persistenza + memoria condivisa (il cuore dello Step 5)
# ---------------------------------------------------------------------------

def test_register_single_side(conn):
    prev = _seg("T1", "ALESSANDRIA", "MILANO PORTA GARIBALDI", "10:00", "11:00")
    nxt = _seg("T2", "MILANO PORTA GARIBALDI", "ALESSANDRIA", "11:40", "12:30")
    cv = detect_cv(prev, nxt)
    assert cv is not None

    state = register_cv_side(conn, cv, side="cva",
                              pdc_id="PDC_A", duration_min=20)
    assert state["cva_pdc_id"] == "PDC_A"
    assert state["cva_min"] == 20
    assert state["cvp_pdc_id"] is None
    assert state["cvp_min"] == 0
    assert state["tm_min"] is None  # Tm si calcola solo quando entrambi


def test_register_both_sides_tm_calcolato(conn):
    # Gap 40 min. PdC A prende 20 ACCa, PdC B prende 20 ACCp.
    # Tm = arr + cva = 660 + 20 = 680 (11:20)
    prev = _seg("T1", "ALESSANDRIA", "MILANO PORTA GARIBALDI", "10:00", "11:00")
    nxt = _seg("T2", "MILANO PORTA GARIBALDI", "ALESSANDRIA", "11:40", "12:30")
    cv = detect_cv(prev, nxt)
    assert cv["gap_min"] == 40

    # PdC A registra prima (uscita)
    register_cv_side(conn, cv, side="cva", pdc_id="PDC_A", duration_min=20)
    # PdC B registra dopo (entrata). Legge il registro, sa che A ha preso 20,
    # quindi si prende 20 min per completare copertura.
    state_after_a = read_cv(conn, cv["material_turn_id"], cv["day_index"],
                             cv["train_in_id"], cv["train_out_id"])
    remaining = cv["gap_min"] - (state_after_a["cva_min"] or 0)
    state = register_cv_side(conn, cv, side="cvp",
                              pdc_id="PDC_B", duration_min=remaining)

    assert state["cva_min"] == 20
    assert state["cvp_min"] == 20
    assert state["cva_pdc_id"] == "PDC_A"
    assert state["cvp_pdc_id"] == "PDC_B"
    # Tm = 11:00 + 20 min = 11:20 (minuti 660 + 20 = 680)
    assert state["tm_min"] == 680
    assert validate_coverage(state, cv["gap_min"]) is True


def test_update_esistente_non_duplica(conn):
    # Se lo stesso PdC riscrive il suo lato, la riga non si duplica
    prev = _seg("T1", "ALESSANDRIA", "MILANO PORTA GARIBALDI", "10:00", "11:00")
    nxt = _seg("T2", "MILANO PORTA GARIBALDI", "ALESSANDRIA", "11:30", "12:30")
    cv = detect_cv(prev, nxt)

    register_cv_side(conn, cv, side="cva", pdc_id="PDC_A", duration_min=10)
    register_cv_side(conn, cv, side="cva", pdc_id="PDC_A", duration_min=15)
    cur = conn.execute("SELECT COUNT(*) FROM cv_ledger")
    assert cur.fetchone()[0] == 1
    state = read_cv(conn, cv["material_turn_id"], cv["day_index"],
                    cv["train_in_id"], cv["train_out_id"])
    assert state["cva_min"] == 15


def test_read_cv_miss_ritorna_none(conn):
    assert read_cv(conn, 999, 1, "X", "Y") is None


def test_ensure_schema_idempotente(conn):
    # Chiamare due volte non crasha
    ensure_schema(conn)
    ensure_schema(conn)
    # Tabella esiste
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='cv_ledger'"
    )
    assert cur.fetchone() is not None
