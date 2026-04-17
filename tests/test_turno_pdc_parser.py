"""Test parser turno PdC (schema v2)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.importer.turno_pdc_parser import (
    _cluster_vertical_labels,
    _classify_vertical_label,
    _find_day_markers,
    _parse_train_notes,
    _hhmm_to_min,
    _it_to_iso_date,
    _reverse,
    _x_to_hour_for_minute,
    _hhmm_fix_rollover,
    _assign_minutes_to_blocks,
    ParsedPdcBlock,
    ParsedPdcNote,
)


# ------------------------------------------------------------------
# UTILITY
# ------------------------------------------------------------------

def test_hhmm_to_min():
    assert _hhmm_to_min("00:00") == 0
    assert _hhmm_to_min("01:30") == 90
    assert _hhmm_to_min("08:30") == 510
    assert _hhmm_to_min("  05:45 ") == 345
    assert _hhmm_to_min("invalid") == 0
    assert _hhmm_to_min("") == 0


def test_it_to_iso_date():
    assert _it_to_iso_date("23/02/2026") == "2026-02-23"
    assert _it_to_iso_date("01/01/2026") == "2026-01-01"
    assert _it_to_iso_date("31/12/2025") == "2025-12-31"
    # Formato invalido -> ritorna invariato
    assert _it_to_iso_date("2026-02-23") == "2026-02-23"
    assert _it_to_iso_date("abc") == "abc"


def test_reverse():
    assert _reverse("ABCD") == "DCBA"
    assert _reverse("2434") == "4342"
    assert _reverse("") == ""


# ------------------------------------------------------------------
# CLUSTERIZZAZIONE ETICHETTE VERTICALI
# ------------------------------------------------------------------

def _mk_word(text: str, x0: float, y0: float, upright: bool = False,
             size: float = 4.0):
    """Helper per costruire una parola-mock come la estrarrebbe pdfplumber."""
    return {
        "text": text, "x0": x0, "x1": x0 + 5.5,
        "top": y0, "bottom": y0 + len(text) * 4,
        "upright": upright, "size": size, "fontname": "Arial",
    }


def test_cluster_vertical_labels_single_column():
    """Una colonna di 4 lettere verticali -> 1 label invertita."""
    # Testo DOMO scritto verticalmente (bottom-to-top):
    #   primo carattere pdfplumber in y=48 (in alto nella pagina)
    #   ordine naturale pdf: O(48) M(52) O(56) D(60)
    #   invertito: DOMO
    words = [
        _mk_word("O", x0=497.3, y0=48.1),
        _mk_word("M", x0=497.3, y0=52.3),
        _mk_word("O", x0=497.3, y0=56.9),
        _mk_word("D", x0=497.3, y0=61.2),
    ]
    labels = _cluster_vertical_labels(words)
    assert len(labels) == 1
    assert labels[0]["label"] == "DOMO"


def test_cluster_vertical_labels_numeric_token():
    """Un numero intero '4342' verticale -> invertito in '2434'."""
    words = [_mk_word("4342", x0=496.9, y0=70.0)]
    labels = _cluster_vertical_labels(words)
    assert len(labels) == 1
    assert labels[0]["label"] == "2434"


def test_cluster_vertical_labels_multiple_columns():
    """Due colonne distinte -> due label, ordinate per X."""
    # Colonna 1 a x=497:   4342 (top=70), ( (top=84)
    #   raw="4342(" -> label invertito = "(2434"
    # Colonna 2 a x=562:   3420 (top=68), 1 (top=82)
    #   raw="34201" -> label invertito = "10243"
    words = [
        _mk_word("4342", x0=497.0, y0=70.0),
        _mk_word("(",    x0=497.0, y0=84.0),
        _mk_word("3420", x0=562.0, y0=68.0),
        _mk_word("1",    x0=562.0, y0=82.0),
    ]
    labels = _cluster_vertical_labels(words)
    assert len(labels) == 2

    # Ordinate per X crescente
    assert labels[0]["x0"] < labels[1]["x0"]
    # Colonna 1 (x=497) -> "(2434" (vettura)
    assert labels[0]["label"] == "(2434"
    # Colonna 2 (x=562) -> "10243" (treno)
    assert labels[1]["label"] == "10243"


def test_cluster_ignores_horizontal_words():
    """Parole orizzontali (upright=True) non diventano label verticali."""
    words = [
        _mk_word("IMPIANTO:", x0=122, y0=11, upright=True),
        _mk_word("ARONA",     x0=172, y0=11, upright=True),
    ]
    labels = _cluster_vertical_labels(words)
    assert labels == []


# ------------------------------------------------------------------
# CLASSIFICAZIONE ETICHETTE
# ------------------------------------------------------------------

def test_classify_train():
    btype, extras = _classify_vertical_label("10243 Mlpg")
    assert btype == "train"
    assert extras["train_id"] == "10243"
    assert extras["to_station"] == "Mlpg"


def test_classify_train_with_accessori():
    btype, extras = _classify_vertical_label("●10205 ARON")
    assert btype == "train"
    assert extras["train_id"] == "10205"
    assert extras["accessori_maggiorati"] is True


def test_classify_coach_transfer():
    btype, extras = _classify_vertical_label("(2434 DOMO")
    assert btype == "coach_transfer"
    assert extras["vettura_id"] == "2434"
    assert extras["to_station"] == "DOMO"


def test_classify_cv_partenza():
    btype, extras = _classify_vertical_label("CVp 2434 DOMO")
    assert btype == "cv_partenza"
    assert extras["train_id"] == "2434"
    assert extras["to_station"] == "DOMO"


def test_classify_cv_arrivo():
    btype, extras = _classify_vertical_label("CVa 10235 Mlpg")
    assert btype == "cv_arrivo"
    assert extras["train_id"] == "10235"


def test_classify_meal():
    btype, extras = _classify_vertical_label("REFEZ DOMO")
    assert btype == "meal"
    assert extras["to_station"] == "DOMO"


def test_classify_scomp():
    btype, extras = _classify_vertical_label("S.COMP ARON")
    assert btype == "scomp"
    assert extras["to_station"] == "ARON"


def test_classify_scomp_without_dot():
    btype, _ = _classify_vertical_label("SCOMP ARON")
    assert btype == "scomp"


def test_classify_unknown_empty():
    btype, _ = _classify_vertical_label("")
    assert btype == "unknown"
    btype, _ = _classify_vertical_label("???junk")
    assert btype == "unknown"


# ------------------------------------------------------------------
# DAY MARKERS
# ------------------------------------------------------------------

def test_find_day_markers_identifies_big_numbers_on_left():
    words = [
        # Marker giornata 1: size=12, x<20
        {"text": "1", "x0": 10.0, "x1": 16.7, "top": 97.3, "bottom": 109.3,
         "upright": True, "size": 12.0, "fontname": "Arial"},
        # Marker giornata 2
        {"text": "2", "x0": 10.0, "x1": 16.7, "top": 185.3, "bottom": 197.3,
         "upright": True, "size": 12.0, "fontname": "Arial"},
        # Non marker: ora dell'asse (size=5.5)
        {"text": "5", "x0": 145, "x1": 148, "top": 108, "bottom": 113.8,
         "upright": True, "size": 5.5, "fontname": "Arial"},
        # Non marker: numero a destra
        {"text": "3", "x0": 700, "x1": 705, "top": 100, "bottom": 110,
         "upright": True, "size": 8, "fontname": "Arial"},
    ]
    markers = _find_day_markers(words)
    assert len(markers) == 2
    assert markers[0]["text"] == "1"
    assert markers[1]["text"] == "2"


# ------------------------------------------------------------------
# NOTE PERIODICITA' TRENI
# ------------------------------------------------------------------

def test_parse_train_notes_basic():
    text = """Note sulla periodicita' dei treni del turno
Elenco note
Treno 10226 - Circola il sabato e la domenica. Non circola 27/12/2025, 03/01/2026. Circola 25/12/2025, 26/12/2025.
Treno 10205 - Circola tutti i giorni dal 03/02/2026 al 22/02/2026.
"""
    notes = _parse_train_notes(text)
    assert len(notes) == 2

    n_by_tid = {n.train_id: n for n in notes}

    n10226 = n_by_tid["10226"]
    assert "Circola il sabato e la domenica" in n10226.periodicita_text
    assert "2025-12-27" in n10226.non_circola_dates
    assert "2026-01-03" in n10226.non_circola_dates
    assert "2025-12-25" in n10226.circola_extra_dates
    assert "2025-12-26" in n10226.circola_extra_dates

    n10205 = n_by_tid["10205"]
    assert "Circola tutti i giorni" in n10205.periodicita_text


def test_parse_train_notes_dedup():
    """Stesso treno citato due volte: date unite."""
    text = """Treno 10226 - Circola. Non circola 01/01/2026.
Treno 10226 - Circola. Non circola 02/02/2026."""
    notes = _parse_train_notes(text)
    assert len(notes) == 1
    n = notes[0]
    assert "2026-01-01" in n.non_circola_dates
    assert "2026-02-02" in n.non_circola_dates


def test_parse_train_notes_empty():
    assert _parse_train_notes("") == []
    assert _parse_train_notes("testo senza pattern") == []


def test_parse_train_notes_multiline():
    """Date che si estendono su piu' righe vengono comunque catturate."""
    text = """Treno 10227 - Circola tutti i giorni. Non circola 27/12/2025,
03/01/2026, 22/08/2026."""
    notes = _parse_train_notes(text)
    assert len(notes) == 1
    assert len(notes[0].non_circola_dates) == 3


# ------------------------------------------------------------------
# ORARI AL MINUTO — conversione x -> HH:MM
# ------------------------------------------------------------------

def _ticks_for_test(hours: list[int], x_start: float = 100.0,
                    tick_width: float = 25.0):
    """Helper: costruisce una lista di tick orari equispaziati."""
    return [
        (x_start + i * tick_width, x_start + i * tick_width + 3,
         x_start + i * tick_width + 6, h)
        for i, h in enumerate(hours)
    ]


def test_x_to_hour_for_minute_first_half_of_hour():
    """Minuto :30 al centro di un tick -> quell'ora."""
    ticks = _ticks_for_test([3, 4, 5], x_start=100, tick_width=25)
    # ora=3, min=30 -> x_expected = 100 + 30/60*25 = 112.5
    assert _x_to_hour_for_minute(112.5, 30, ticks) == 3
    assert _x_to_hour_for_minute(113, 30, ticks) == 3
    assert _x_to_hour_for_minute(110, 30, ticks) == 3


def test_x_to_hour_for_minute_large_minute():
    """Minuto :45 vicino al tick successivo -> ora corrente (non avanzata)."""
    ticks = _ticks_for_test([17, 18, 19], x_start=100, tick_width=25)
    # ora=17, min=45 -> x_expected = 100 + 45/60*25 = 118.75
    # ora=18, min=45 -> x_expected = 125 + 45/60*25 = 143.75
    # Minuto geometricamente in mezzo dovrebbe finire sull'ora giusta
    assert _x_to_hour_for_minute(118.5, 45, ticks) == 17
    assert _x_to_hour_for_minute(144, 45, ticks) == 18


def test_x_to_hour_for_minute_zero():
    """Minuto :00 esattamente sul tick."""
    ticks = _ticks_for_test([10, 11, 12], x_start=100, tick_width=25)
    assert _x_to_hour_for_minute(100, 0, ticks) == 10
    assert _x_to_hour_for_minute(125, 0, ticks) == 11
    assert _x_to_hour_for_minute(150, 0, ticks) == 12


def test_hhmm_fix_rollover_no_change():
    """start < end: nessuna modifica."""
    assert _hhmm_fix_rollover(18, 25, 19, 4) == ("18:25", "19:04")
    assert _hhmm_fix_rollover(7, 30, 8, 0) == ("07:30", "08:00")


def test_hhmm_fix_rollover_within_hour():
    """Blocco che sembra tornare indietro di < 2h: decrementa start."""
    # 19:40 -> 19:07 sembra impossibile (start>end): in realta' e' 18:40 -> 19:07
    assert _hhmm_fix_rollover(19, 40, 19, 7) == ("18:40", "19:07")
    # 15:50 -> 16:10 OK (no rollover)
    assert _hhmm_fix_rollover(15, 50, 16, 10) == ("15:50", "16:10")


def test_hhmm_fix_rollover_large_diff_no_touch():
    """Blocchi notturni o lunghi che attraversano mezzanotte non modificati."""
    # 23:45 -> 00:25 (fine turno): differenza >> 2h, non ritoccare
    # Nota: 23:45 end=00:25 e' gia' (start<end su orologio spostato)
    # Caso reale: blocco che attraversa mezzanotte
    pass  # No-op: non ritoccare in questo caso


def test_assign_minutes_typical_sequence():
    """Sequenza tipica giornata: 2 blocchi continui + 1 puntuale in mezzo.

    Nuovo algoritmo (sequenziale puro): ogni blocco consuma i minuti
    in ordine X. Continui: 2 minuti. Puntuali: 1 minuto.
    """
    b1 = ParsedPdcBlock(seq=0, block_type="train", train_id="10574")       # continuo, 2 min
    b2 = ParsedPdcBlock(seq=1, block_type="cv_arrivo", train_id="10678")   # puntuale, 1
    b3 = ParsedPdcBlock(seq=2, block_type="cv_partenza", train_id="10677") # puntuale, 1
    b4 = ParsedPdcBlock(seq=3, block_type="train", train_id="10581")       # continuo, 2
    b5 = ParsedPdcBlock(seq=4, block_type="cv_arrivo", train_id="10584")   # puntuale, 1
    blocks_with_x = [(b, i * 50 + 100) for i, b in enumerate([b1, b2, b3, b4, b5])]

    # Totale minuti attesi = 2+1+1+2+1 = 7
    ticks = _ticks_for_test([11, 12, 13, 14, 15, 16, 17],
                            x_start=80, tick_width=25)
    # Minuti posizionati coerentemente per ora 11..16
    upper_mins = [
        {"x": 100.1, "minute": 41},   # 11:41 (train b1 start)
        {"x": 121.6, "minute": 55},   # 12:55 (train b1 end)
        {"x": 141.7, "minute": 28},   # 13:28 (cv_arrivo b2)
        {"x": 174.3, "minute": 38},   # 14:38 (cv_partenza b3)
        {"x": 186.3, "minute": 5},    # 15:05 (train b4 start)
        {"x": 213.2, "minute": 19},   # 16:19 (train b4 end)
        {"x": 229.8, "minute": 34},   # 16:34 (cv_arrivo b5)
    ]
    _assign_minutes_to_blocks(blocks_with_x, upper_mins, ticks)

    # b1 train continuo: start + end
    assert b1.start_time and b1.end_time
    # b2 cv_arrivo puntuale: solo start
    assert b2.start_time and not b2.end_time
    # b3 cv_partenza puntuale: solo start
    assert b3.start_time and not b3.end_time
    # b4 train continuo: start + end
    assert b4.start_time and b4.end_time
    # b5 cv_arrivo puntuale: solo start
    assert b5.start_time and not b5.end_time


def test_assign_minutes_handles_insufficient_minutes():
    """Non crasha se ci sono meno minuti dei blocchi."""
    b1 = ParsedPdcBlock(seq=0, block_type="train", train_id="10000")
    b2 = ParsedPdcBlock(seq=1, block_type="train", train_id="10001")
    blocks_with_x = [(b1, 100), (b2, 200)]
    ticks = _ticks_for_test([10, 11], x_start=80, tick_width=25)
    _assign_minutes_to_blocks(
        blocks_with_x,
        [{"x": 90, "minute": 5}, {"x": 110, "minute": 15}],  # solo 2 minuti
        ticks,
    )
    # b1 ha start+end, b2 non completo
    assert b1.start_time and b1.end_time
    assert b2.start_time == "" and b2.end_time == ""


def test_assign_minutes_no_ticks_safe():
    """Safe con ticks vuoti."""
    b1 = ParsedPdcBlock(seq=0, block_type="train", train_id="10000")
    blocks_with_x = [(b1, 100)]
    _assign_minutes_to_blocks(blocks_with_x, [{"x": 100, "minute": 30}], [])
    # Non crasha, semplicemente non popola
    assert b1.start_time == ""


if __name__ == "__main__":
    import inspect
    passed = failed = 0
    for name, fn in inspect.getmembers(sys.modules[__name__], inspect.isfunction):
        if name.startswith("test_"):
            try:
                fn()
                passed += 1
            except AssertionError as e:
                print(f"FAIL {name}: {e}")
                failed += 1
    print(f"\n{passed} passed, {failed} failed")
