"""Test validator regole operative."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.validator.rules import TurnValidator, DaySummary, Violation, _time_to_min, _fmt_min


def make_seg(train_id, from_st, dep, to_st, arr, is_deadhead=False):
    return {
        "train_id": train_id,
        "from_station": from_st,
        "dep_time": dep,
        "to_station": to_st,
        "arr_time": arr,
        "is_deadhead": is_deadhead,
    }


def test_condotta_simple():
    v = TurnValidator()
    segments = [
        make_seg("100", "A", "06:00", "B", "07:30"),
        make_seg("101", "B", "08:00", "C", "09:15"),
    ]
    condotta = v.compute_condotta(segments)
    # 90 + 75 = 165
    assert condotta == 165


def test_condotta_deadhead_excluded():
    v = TurnValidator()
    segments = [
        make_seg("100", "A", "06:00", "B", "07:30"),
        make_seg("DH", "B", "08:00", "C", "09:00", is_deadhead=True),
        make_seg("101", "C", "09:30", "D", "10:15"),
    ]
    condotta = v.compute_condotta(segments)
    # 90 + 0 (deadhead) + 45 = 135
    assert condotta == 135


def test_accessori():
    v = TurnValidator()
    assert v.compute_accessori() == 18  # 10 + 8


def test_tempi_medi():
    v = TurnValidator()
    assert v.compute_tempi_medi() == 4


def test_extra():
    v = TurnValidator()
    assert v.compute_extra() == 10  # 5 + 5


def test_night_minutes_diurno():
    v = TurnValidator()
    # Turno completamente diurno
    nm = v.compute_night_minutes("06:00", "14:00")
    assert nm == 0


def test_night_minutes_notturno():
    v = TurnValidator()
    # Turno che attraversa la fascia notturna 00:01-01:00
    nm = v.compute_night_minutes("23:00", "02:00")
    # Overlap con 00:01-01:00 = 59 minuti
    assert nm == 59


def test_night_minutes_parziale():
    v = TurnValidator()
    # Turno che finisce alle 00:30
    nm = v.compute_night_minutes("22:00", "00:30")
    # Overlap con 00:01-00:30 = 29 minuti
    assert nm == 29


def test_meal_slot_gap():
    v = TurnValidator()
    # Gap 12:00-13:00 cade nella finestra contrattuale 1 (11:30-15:30)
    segments = [
        make_seg("100", "A", "06:00", "B", "12:00"),
        make_seg("101", "B", "13:00", "C", "15:00"),  # 60 min gap in finestra pranzo
    ]
    start, end = v.find_meal_slot(segments)
    assert start == "12:00"
    assert end == "12:30"


def test_meal_slot_no_gap():
    v = TurnValidator()
    segments = [
        make_seg("100", "A", "06:00", "B", "07:30"),
        make_seg("101", "B", "07:40", "C", "09:00"),  # solo 10 min gap
    ]
    start, end = v.find_meal_slot(segments)
    # Dovrebbe essere a metà prestazione
    assert start is not None
    assert end is not None


def test_validate_day_ok():
    v = TurnValidator(deposito="A")
    segments = [
        make_seg("100", "A", "06:00", "B", "07:30"),
        make_seg("101", "B", "08:00", "A", "09:30"),
    ]
    summary = v.validate_day(segments, deposito="A")
    assert summary.condotta_min == 180  # 90 + 90
    assert summary.day_type == "DIURNA"
    assert not summary.is_fr
    # Nessuna violazione (sotto limiti)
    violations = [v for v in summary.violations if v.rule in ("MAX_PRESTAZIONE", "MAX_CONDOTTA")]
    assert len(violations) == 0


def test_validate_day_condotta_exceeded():
    v = TurnValidator()
    # 6 ore di condotta (360 min > 330 limite)
    segments = [
        make_seg("100", "A", "06:00", "B", "09:00"),  # 180 min
        make_seg("101", "B", "09:10", "C", "12:10"),   # 180 min
    ]
    summary = v.validate_day(segments)
    assert summary.condotta_min == 360
    condotta_v = [v for v in summary.violations if v.rule == "MAX_CONDOTTA"]
    assert len(condotta_v) == 1


def test_validate_day_fr():
    v = TurnValidator(deposito="MILANO CENTRALE")
    segments = [
        make_seg("100", "MILANO CENTRALE", "06:00", "BERGAMO", "07:30"),
    ]
    summary = v.validate_day(segments, deposito="MILANO CENTRALE")
    assert summary.is_fr  # Termina a BERGAMO, che è in FR stations
    assert summary.last_station == "BERGAMO"


def test_validate_day_no_rientro():
    v = TurnValidator(deposito="MILANO CENTRALE")
    segments = [
        make_seg("100", "MILANO CENTRALE", "06:00", "SONDRIO", "09:30"),
    ]
    summary = v.validate_day(segments, deposito="MILANO CENTRALE")
    no_rientro = [vv for vv in summary.violations if vv.rule == "NO_RIENTRO_BASE"]
    assert len(no_rientro) == 1


def test_rest_between_standard():
    v = TurnValidator()
    day1 = DaySummary(segments=[], end_time="14:00", day_type="DIURNA")
    day2 = DaySummary(segments=[], presentation_time="06:00")
    # 14:00 -> 06:00 next day = 16h >= 11h OK
    violations = v.validate_rest_between(day1, day2)
    assert len(violations) == 0


def test_rest_between_insufficient():
    v = TurnValidator()
    day1 = DaySummary(segments=[], end_time="22:00", day_type="DIURNA")
    day2 = DaySummary(segments=[], presentation_time="05:00")
    # 22:00 -> 05:00 = 7h < 11h
    violations = v.validate_rest_between(day1, day2)
    assert len(violations) == 1
    assert violations[0].rule == "MIN_REST"


def test_rest_after_night():
    v = TurnValidator()
    day1 = DaySummary(segments=[], end_time="02:00", day_type="NOTTURNA")
    day2 = DaySummary(segments=[], presentation_time="14:00")
    # 02:00 -> 14:00 = 12h < 16h richieste per notturno
    violations = v.validate_rest_between(day1, day2)
    assert len(violations) == 1


def test_calendar_5_2():
    v = TurnValidator()
    cal = v.build_calendar(10)
    turns = [e for e in cal if e["type"] == "TURN"]
    rests = [e for e in cal if e["type"] == "REST"]
    assert len(turns) == 10
    assert len(rests) == 4  # 2 blocchi di riposo


def test_calendar_5_2_partial():
    v = TurnValidator()
    cal = v.build_calendar(3)
    turns = [e for e in cal if e["type"] == "TURN"]
    rests = [e for e in cal if e["type"] == "REST"]
    assert len(turns) == 3


def test_weekly_rest_missing():
    v = TurnValidator()
    # Calendario senza riposo sufficiente
    calendar = [
        {"type": "TURN"}, {"type": "TURN"}, {"type": "TURN"},
        {"type": "TURN"}, {"type": "TURN"},
        {"type": "REST"},  # solo 24h
        {"type": "TURN"}, {"type": "TURN"},
    ]
    violations = v.validate_weekly_rest(calendar)
    assert len(violations) == 1
    assert violations[0].rule == "WEEKLY_REST_MISSING"


def test_weekly_rest_ok():
    v = TurnValidator()
    # 3 giorni di riposo consecutivi = 72h >= 62h
    calendar = [
        {"type": "TURN"}, {"type": "TURN"}, {"type": "TURN"},
        {"type": "TURN"}, {"type": "TURN"},
        {"type": "REST"}, {"type": "REST"}, {"type": "REST"},
    ]
    violations = v.validate_weekly_rest(calendar)
    assert len(violations) == 0


def test_fmt_min():
    assert _fmt_min(510) == "8h30"
    assert _fmt_min(330) == "5h30"
    assert _fmt_min(0) == "0h00"
    assert _fmt_min(65) == "1h05"


def test_time_to_min():
    assert _time_to_min("00:00") == 0
    assert _time_to_min("06:30") == 390
    assert _time_to_min("23:59") == 1439


if __name__ == "__main__":
    test_condotta_simple()
    test_condotta_deadhead_excluded()
    test_accessori()
    test_tempi_medi()
    test_extra()
    test_night_minutes_diurno()
    test_night_minutes_notturno()
    test_night_minutes_parziale()
    test_meal_slot_gap()
    test_meal_slot_no_gap()
    test_validate_day_ok()
    test_validate_day_condotta_exceeded()
    test_validate_day_fr()
    test_validate_day_no_rientro()
    test_rest_between_standard()
    test_rest_between_insufficient()
    test_rest_after_night()
    test_calendar_5_2()
    test_calendar_5_2_partial()
    test_weekly_rest_missing()
    test_weekly_rest_ok()
    test_fmt_min()
    test_time_to_min()
    print("All validator tests passed!")
