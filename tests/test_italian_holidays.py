"""Test modulo calendario festivita' italiane."""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.italian_holidays import (
    easter_sunday,
    easter_monday,
    italian_national_holidays,
    italian_holidays,
    is_italian_holiday,
    weekday_for_periodicity,
    matches_periodicity,
    upcoming_holidays,
    WEEKDAY_LETTERS,
    FIXED_HOLIDAYS,
    LOCAL_PATRONS,
)


# ------------------------------------------------------------------
# Pasqua (Computus)
# ------------------------------------------------------------------

def test_easter_sunday_known_years():
    """Date di Pasqua verificate contro calendario liturgico ufficiale."""
    assert easter_sunday(2024) == date(2024, 3, 31)
    assert easter_sunday(2025) == date(2025, 4, 20)
    assert easter_sunday(2026) == date(2026, 4, 5)
    assert easter_sunday(2027) == date(2027, 3, 28)
    assert easter_sunday(2028) == date(2028, 4, 16)
    assert easter_sunday(2030) == date(2030, 4, 21)


def test_easter_is_always_sunday():
    """Invariante: Pasqua e' sempre di domenica."""
    for year in range(2020, 2050):
        assert easter_sunday(year).weekday() == 6, f"Pasqua {year} non domenica"


def test_easter_monday_is_day_after():
    """Pasquetta = Pasqua + 1 giorno, sempre lunedi'."""
    for year in (2024, 2025, 2026, 2027):
        em = easter_monday(year)
        es = easter_sunday(year)
        assert em.toordinal() == es.toordinal() + 1
        assert em.weekday() == 0  # lunedi


# ------------------------------------------------------------------
# Festivita' nazionali
# ------------------------------------------------------------------

def test_national_holidays_count():
    """Ogni anno ha 12 festivita' nazionali: 10 fisse + Pasqua + Pasquetta."""
    for year in (2024, 2025, 2026, 2027):
        assert len(italian_national_holidays(year)) == 12


def test_national_holidays_2026_contents():
    """Le 12 festivita' 2026 sono esattamente quelle attese."""
    h = italian_national_holidays(2026)
    expected = {
        date(2026, 1, 1),    # Capodanno
        date(2026, 1, 6),    # Epifania
        date(2026, 4, 5),    # Pasqua
        date(2026, 4, 6),    # Pasquetta
        date(2026, 4, 25),   # Liberazione
        date(2026, 5, 1),    # Festa del Lavoro
        date(2026, 6, 2),    # Festa della Repubblica
        date(2026, 8, 15),   # Ferragosto
        date(2026, 11, 1),   # Tutti i Santi
        date(2026, 12, 8),   # Immacolata
        date(2026, 12, 25),  # Natale
        date(2026, 12, 26),  # Santo Stefano
    }
    assert h == expected


def test_fixed_holidays_list():
    """FIXED_HOLIDAYS deve contenere esattamente 10 feste (tutte tranne Pasqua/Pasquetta)."""
    assert len(FIXED_HOLIDAYS) == 10
    # Date ben formate (1 <= mese <= 12, 1 <= giorno <= 31)
    for m, d, _name in FIXED_HOLIDAYS:
        assert 1 <= m <= 12
        assert 1 <= d <= 31


# ------------------------------------------------------------------
# is_italian_holiday
# ------------------------------------------------------------------

def test_is_holiday_true_cases():
    assert is_italian_holiday(date(2026, 1, 1))    # Capodanno
    assert is_italian_holiday(date(2026, 4, 25))   # Liberazione (sabato)
    assert is_italian_holiday(date(2026, 4, 6))    # Pasquetta
    assert is_italian_holiday(date(2026, 12, 25))  # Natale


def test_is_holiday_false_cases():
    assert not is_italian_holiday(date(2026, 4, 24))   # venerdi normale
    assert not is_italian_holiday(date(2026, 4, 26))   # domenica NON festiva ufficiale
    assert not is_italian_holiday(date(2026, 12, 24))  # vigilia
    assert not is_italian_holiday(date(2026, 12, 7))   # Sant'Ambrogio SENZA local


def test_is_holiday_with_local_milano():
    """Sant'Ambrogio (7/12) e' festivo solo con include_local='milano'."""
    d = date(2026, 12, 7)  # lunedi
    assert not is_italian_holiday(d)
    assert is_italian_holiday(d, include_local="milano")
    assert is_italian_holiday(d, include_local="MILANO")  # case-insensitive
    assert not is_italian_holiday(d, include_local="torino")  # patrono diverso


def test_local_patrons_table():
    """Ogni patrono locale ha (mese, giorno, nome) validi."""
    assert len(LOCAL_PATRONS) >= 10
    for city, (m, d, name) in LOCAL_PATRONS.items():
        assert city == city.lower()
        assert 1 <= m <= 12
        assert 1 <= d <= 31
        assert name  # non vuoto


# ------------------------------------------------------------------
# weekday_for_periodicity
# ------------------------------------------------------------------

def test_weekday_letters_mapping():
    """WEEKDAY_LETTERS segue ordine Python: 0=lunedi..6=domenica."""
    assert WEEKDAY_LETTERS == ("L", "M", "X", "G", "V", "S", "D")


def test_weekday_normal_days():
    """Giorni normali: lettera standard."""
    # lunedi 20 aprile 2026 (non festivo)
    assert weekday_for_periodicity(date(2026, 4, 20)) == "L"
    assert weekday_for_periodicity(date(2026, 4, 21)) == "M"
    assert weekday_for_periodicity(date(2026, 4, 22)) == "X"
    assert weekday_for_periodicity(date(2026, 4, 23)) == "G"
    assert weekday_for_periodicity(date(2026, 4, 24)) == "V"
    assert weekday_for_periodicity(date(2026, 4, 18)) == "S"  # sabato non festivo
    assert weekday_for_periodicity(date(2026, 4, 19)) == "D"  # domenica


def test_weekday_holiday_forces_D():
    """Festivo infrasettimanale -> D, anche se cade di sabato/feriale."""
    # 25/04/2026 e' sabato + Liberazione -> D
    assert weekday_for_periodicity(date(2026, 4, 25)) == "D"
    # 01/05/2026 e' venerdi + Festa del Lavoro -> D
    assert weekday_for_periodicity(date(2026, 5, 1)) == "D"
    # 25/12/2026 e' venerdi + Natale -> D
    assert weekday_for_periodicity(date(2026, 12, 25)) == "D"
    # 06/04/2026 e' lunedi + Pasquetta -> D
    assert weekday_for_periodicity(date(2026, 4, 6)) == "D"


def test_weekday_sunday_always_D():
    """La domenica e' sempre D, anche senza considerare festivita'."""
    # Prima domenica di 2026 (04/01)
    assert weekday_for_periodicity(date(2026, 1, 4)) == "D"
    # Domenica generica
    assert weekday_for_periodicity(date(2026, 3, 15)) == "D"


def test_weekday_with_local_patron():
    """Con patrono locale, la data diventa D anche senza feste nazionali."""
    # 07/12/2026 e' lunedi
    assert weekday_for_periodicity(date(2026, 12, 7)) == "L"
    assert weekday_for_periodicity(date(2026, 12, 7), include_local="milano") == "D"


# ------------------------------------------------------------------
# matches_periodicity
# ------------------------------------------------------------------

def test_matches_periodicity_normal_monday():
    """Lunedi normale matcha le periodicita' che includono L."""
    d = date(2026, 4, 20)  # lunedi non festivo
    assert matches_periodicity(d, "LMXGVSD")
    assert matches_periodicity(d, "LMXGVS")
    assert matches_periodicity(d, "LMXGV")
    assert not matches_periodicity(d, "SD")
    assert not matches_periodicity(d, "D")
    assert not matches_periodicity(d, "S")


def test_matches_periodicity_holiday_on_saturday():
    """25/04/2026 (sabato festivo) matcha solo le periodicita' con D."""
    d = date(2026, 4, 25)
    assert matches_periodicity(d, "LMXGVSD")
    assert matches_periodicity(d, "SD")
    assert matches_periodicity(d, "D")
    assert not matches_periodicity(d, "LMXGVS")   # il sabato normale, ma qui e' D
    assert not matches_periodicity(d, "LMXGV")
    assert not matches_periodicity(d, "S")


def test_matches_periodicity_sunday():
    """Domenica normale matcha D, SD, LMXGVSD."""
    d = date(2026, 3, 15)  # domenica non festiva nazionale
    assert matches_periodicity(d, "LMXGVSD")
    assert matches_periodicity(d, "SD")
    assert matches_periodicity(d, "D")
    assert not matches_periodicity(d, "LMXGVS")
    assert not matches_periodicity(d, "LMXGV")


# ------------------------------------------------------------------
# upcoming_holidays
# ------------------------------------------------------------------

def test_upcoming_holidays_single_year():
    """Intervallo di un intero anno -> 12 festivita' nazionali."""
    out = upcoming_holidays(date(2026, 1, 1), date(2026, 12, 31))
    assert len(out) == 12
    assert out == sorted(out)  # gia' ordinate


def test_upcoming_holidays_partial_range():
    """Intervallo marzo-aprile 2026 -> Pasqua + Pasquetta + Liberazione = 3."""
    out = upcoming_holidays(date(2026, 3, 1), date(2026, 4, 30))
    assert out == [date(2026, 4, 5), date(2026, 4, 6), date(2026, 4, 25)]


def test_upcoming_holidays_cross_year():
    """Intervallo dic 2025 - gen 2026 -> Natale + S.Stefano 2025 + Capodanno + Epifania 2026."""
    out = upcoming_holidays(date(2025, 12, 20), date(2026, 1, 10))
    assert date(2025, 12, 25) in out
    assert date(2025, 12, 26) in out
    assert date(2026, 1, 1) in out
    assert date(2026, 1, 6) in out
    assert len(out) == 4


# ------------------------------------------------------------------
# Cache behavior
# ------------------------------------------------------------------

def test_italian_holidays_cache_is_stable():
    """Chiamate ripetute ritornano lo stesso set (cached)."""
    a = italian_national_holidays(2026)
    b = italian_national_holidays(2026)
    assert a is b  # stessa istanza frozen


def test_italian_holidays_with_local_differs():
    """Con e senza local il risultato deve differire."""
    base = italian_holidays(2026)
    with_mi = italian_holidays(2026, include_local="milano")
    assert date(2026, 12, 7) not in base
    assert date(2026, 12, 7) in with_mi
    assert len(with_mi) == len(base) + 1


if __name__ == "__main__":
    # Permette anche esecuzione diretta: python tests/test_italian_holidays.py
    import inspect

    passed = 0
    failed = 0
    for name, fn in inspect.getmembers(sys.modules[__name__], inspect.isfunction):
        if name.startswith("test_"):
            try:
                fn()
                passed += 1
            except AssertionError as e:
                print(f"FAIL {name}: {e}")
                failed += 1
    print(f"\n{passed} passed, {failed} failed")
