"""
Test Step 2 (23/04/2026) — Fase C refezione in day_assembler.

Verifica che la refezione venga piazzata nei 5 slot in ordine di
preferenza, che rispetti le finestre contrattuali 11:30-15:30 e
18:30-22:30, e che la giornata venga scartata se nessuno slot e' valido.
"""
from __future__ import annotations

from src.turn_builder import day_assembler


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


def _make_seed(trains, from_st, to_st, first_dep, last_arr, cond):
    return {
        "trains": trains,
        "from_station": from_st,
        "to_station": to_st,
        "first_dep_min": first_dep,
        "last_arr_min": last_arr,
        "condotta_min": cond,
        "score": 100.0,
    }


# ---------------------------------------------------------------------------
# Slot 1 — dentro il seed (2 treni con gap in finestra)
# ---------------------------------------------------------------------------

def test_slot1_inside_seed_two_trains():
    # Seed 2 treni: t1 arriva 12:00, t2 parte 13:30. Gap=90', start 12:10
    # cade in finestra 11:30-15:30 → refezione slot 1.
    t1 = _seg("T1", "ALE", "MI", "10:30", "12:00")
    t2 = _seg("T2", "MI", "ALE", "13:30", "14:30")
    seed = _make_seed([t1, t2], "ALE", "ALE",
                      10 * 60 + 30, 14 * 60 + 30, 150)
    result = day_assembler.assemble_day(
        seed=seed, deposito="ALE", all_day_segments=[t1, t2],
    )
    assert result is not None
    segs = result["segments"]
    # refezione deve essere tra t1 e t2
    assert len(segs) == 3
    assert segs[0]["train_id"] == "T1"
    assert segs[1].get("is_refezione") is True
    assert segs[1]["dep_time"] == "12:10"
    assert segs[1]["arr_time"] == "12:40"
    assert segs[1]["from_station"] == "MI"
    assert segs[2]["train_id"] == "T2"
    # condotta non include refezione
    assert result["condotta_min"] == 150  # 90 + 60


# ---------------------------------------------------------------------------
# Slot 2 — tra posizionamento e seed
# ---------------------------------------------------------------------------

def test_slot2_between_pos_and_seed():
    # Pos arriva MI 10:00, seed parte MI 13:00. Gap 3h, refez slot 2.
    pos = _seg("P1", "ALE", "MI", "08:30", "10:00")
    seed_t = _seg("S1", "MI", "ALE", "13:00", "14:30")
    seed = _make_seed([seed_t], "MI", "ALE",
                      13 * 60, 14 * 60 + 30, 90)
    result = day_assembler.assemble_day(
        seed=seed, deposito="ALE", all_day_segments=[pos, seed_t],
    )
    assert result is not None
    segs = result["segments"]
    # [pos, refez, seed]
    assert len(segs) == 3
    assert segs[0]["train_id"] == "P1"
    assert segs[1].get("is_refezione") is True
    # Refez inizia alle 11:30 (inizio finestra, perche' earliest=10:10 < 11:30)
    assert segs[1]["dep_time"] == "11:30"
    assert segs[1]["arr_time"] == "12:00"
    assert segs[1]["from_station"] == "MI"
    assert segs[2]["train_id"] == "S1"


# ---------------------------------------------------------------------------
# Slot 3 — tra seed e rientro
# ---------------------------------------------------------------------------

def test_slot3_between_seed_and_return():
    # Seed arriva MI 12:00, rientro parte MI 15:00. Gap 3h in finestra.
    # Niente slot 1 (seed 1 treno). Niente slot 2 (no positioning).
    seed_t = _seg("S1", "ALE", "MI", "10:00", "12:00")
    ret = _seg("R1", "MI", "ALE", "15:00", "16:00")
    seed = _make_seed([seed_t], "ALE", "MI",
                      10 * 60, 12 * 60, 120)
    result = day_assembler.assemble_day(
        seed=seed, deposito="ALE", all_day_segments=[seed_t, ret],
    )
    assert result is not None
    segs = result["segments"]
    # [seed, refez, return]
    assert len(segs) == 3
    assert segs[0]["train_id"] == "S1"
    assert segs[1].get("is_refezione") is True
    assert segs[1]["dep_time"] == "12:10"
    assert segs[1]["from_station"] == "MI"
    assert segs[2]["train_id"] == "R1"


# ---------------------------------------------------------------------------
# Slot 4 — all'inizio del turno (solo seed isolato)
# ---------------------------------------------------------------------------

def test_slot4_at_start_of_turn():
    # Turno parte 13:00. Refezione termina 12:50, inizia 12:20. Cade in
    # finestra 11:30-15:30 → slot 4.
    # Seed 1 treno direttamente dal deposito, nessun posizionamento,
    # nessun rientro. Seed isolato → slot 4 permesso come ultima risorsa.
    seed_t = _seg("S1", "ALE", "ALE", "13:00", "14:00")
    seed = _make_seed([seed_t], "ALE", "ALE",
                      13 * 60, 14 * 60, 60)
    result = day_assembler.assemble_day(
        seed=seed, deposito="ALE", all_day_segments=[seed_t],
    )
    assert result is not None
    segs = result["segments"]
    # [refez, seed]
    assert len(segs) == 2
    assert segs[0].get("is_refezione") is True
    assert segs[0]["dep_time"] == "12:20"
    assert segs[0]["arr_time"] == "12:50"
    assert segs[0]["from_station"] == "ALE"
    assert segs[1]["train_id"] == "S1"


# ---------------------------------------------------------------------------
# Slot 5 — alla fine del turno (solo seed isolato)
# ---------------------------------------------------------------------------

def test_slot5_at_end_of_turn():
    # Seed mattutino isolato (no pos, no ret). Slot 4 first_dep=10:00 →
    # start=9:20 fuori finestra. Slot 5: last_arr=14:20+10=14:30 dentro
    # finestra → accetta.
    seed_t = _seg("S1", "ALE", "ALE", "10:00", "14:20")
    seed = _make_seed([seed_t], "ALE", "ALE",
                      10 * 60, 14 * 60 + 20, 260)
    result = day_assembler.assemble_day(
        seed=seed, deposito="ALE", all_day_segments=[seed_t],
    )
    assert result is not None
    segs = result["segments"]
    # [seed, refez]
    assert len(segs) == 2
    assert segs[0]["train_id"] == "S1"
    assert segs[1].get("is_refezione") is True
    assert segs[1]["dep_time"] == "14:30"  # 14:20 + 10
    assert segs[1]["arr_time"] == "15:00"


# ---------------------------------------------------------------------------
# NUOVO: slot 4/5 NON accettabili per turno strutturato (pos+seed+ret)
# Richiesta 23/04/2026: se la giornata ha struttura reale e slot 1-3 non
# chiudono, scartare invece di usare 4/5 (refez all'estremo del turno).
# ---------------------------------------------------------------------------

def test_structured_turn_no_slot45_fallback():
    # Turno "realistico": seed MI→ALE, positioning ALE→MI, no CV.
    # Strutturato → se slot 1-3 non chiudono, ritorna None.
    # Qui costruisco uno scenario dove slot 2 non chiude (gap troppo
    # piccolo) e slot 3 non esiste (seed_to == deposito).
    pos_seg = _seg("P1", "ALE", "MI", "12:00", "12:55")
    seed_t = _seg("S1", "MI", "ALE", "13:00", "14:00")
    seed = _make_seed([seed_t], "MI", "ALE",
                      13 * 60, 14 * 60, 60)
    result = day_assembler.assemble_day(
        seed=seed, deposito="ALE",
        all_day_segments=[pos_seg, seed_t],
    )
    # Gap pos arr (12:55) → seed dep (13:00) = 5 min, troppo stretto per
    # slot 2 (serve almeno 50 min). Slot 3 non esiste. Seed=1 treno.
    # Turno strutturato (ha positioning) → scartato (no fallback slot 4/5).
    assert result is None


# ---------------------------------------------------------------------------
# Scenario: nessuno slot valido → giornata scartata
# ---------------------------------------------------------------------------

def test_no_slot_fits_day_discarded():
    # Seed mattutino 08:00-09:30, nessun rientro/posizionamento, nessun
    # gap interno. first_dep 08:00 → slot 4 start=07:20 fuori finestra.
    # last_arr 09:30 → slot 5 start=09:40 fuori finestra. → None.
    seed_t = _seg("S1", "ALE", "ALE", "08:00", "09:30")
    seed = _make_seed([seed_t], "ALE", "ALE",
                      8 * 60, 9 * 60 + 30, 90)
    result = day_assembler.assemble_day(
        seed=seed, deposito="ALE", all_day_segments=[seed_t],
    )
    assert result is None


# ---------------------------------------------------------------------------
# Preferenza: slot 1 vince su slot 3 quando entrambi validi
# ---------------------------------------------------------------------------

def test_slot1_preferred_over_slot3():
    # Seed 2 treni con gap 90' slot 1 attivabile + rientro con gap 60'
    # slot 3 pure attivabile. Prestazione totale 5h (sotto limite 8h30).
    # Deve vincere slot 1 (priorita' di preferenza).
    t1 = _seg("T1", "ALE", "MI", "10:30", "11:30")
    t2 = _seg("T2", "MI", "PAV", "13:00", "13:30")
    ret = _seg("R1", "PAV", "ALE", "14:30", "15:30")
    seed = _make_seed([t1, t2], "ALE", "PAV",
                      10 * 60 + 30, 13 * 60 + 30, 90)
    result = day_assembler.assemble_day(
        seed=seed, deposito="ALE", all_day_segments=[t1, t2, ret],
    )
    assert result is not None
    segs = result["segments"]
    # Refez deve essere tra t1 e t2 (slot 1), non tra t2 e ret (slot 3).
    refez_segs = [s for s in segs if s.get("is_refezione")]
    assert len(refez_segs) == 1
    refez = refez_segs[0]
    # earliest = t1_arr + 10 = 11:40 (gia' in finestra)
    assert refez["dep_time"] == "11:40"
    assert refez["from_station"] == "MI"


# ---------------------------------------------------------------------------
# Finestra sera (18:30-22:30) funziona anche per slot 1
# ---------------------------------------------------------------------------

def test_evening_window_slot1():
    # Seed 2 treni con gap tra 18:30 e 22:30.
    t1 = _seg("T1", "ALE", "MI", "17:00", "18:20")
    t2 = _seg("T2", "MI", "ALE", "19:30", "20:30")
    seed = _make_seed([t1, t2], "ALE", "ALE",
                      17 * 60, 20 * 60 + 30, 140)
    result = day_assembler.assemble_day(
        seed=seed, deposito="ALE", all_day_segments=[t1, t2],
    )
    assert result is not None
    refez = [s for s in result["segments"] if s.get("is_refezione")][0]
    assert refez["dep_time"] == "18:30"  # clamp alla finestra sera
    assert refez["arr_time"] == "19:00"
