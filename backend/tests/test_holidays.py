"""Test calendario festività italiane (Sprint 3 — sub-modulo holidays)."""

from datetime import date

from colazione.importers.holidays import (
    easter_sunday,
    italian_holidays,
    italian_holidays_in_range,
)

# Date Pasqua note (verificate manualmente — fonte: USNO + calendario Vaticano)
EASTER_KNOWN = {
    2024: date(2024, 3, 31),
    2025: date(2025, 4, 20),
    2026: date(2026, 4, 5),
    2027: date(2027, 3, 28),
    2028: date(2028, 4, 16),
    2029: date(2029, 4, 1),
    2030: date(2030, 4, 21),
}


def test_easter_sunday_known_years() -> None:
    for year, expected in EASTER_KNOWN.items():
        assert easter_sunday(year) == expected, f"Pasqua {year}"


def test_italian_holidays_2026_count() -> None:
    """12 festività civili italiane standard."""
    h = italian_holidays(2026)
    assert len(h) == 12


def test_italian_holidays_2026_includes_fixed_dates() -> None:
    h = italian_holidays(2026)
    expected_fixed = {
        date(2026, 1, 1),  # Capodanno
        date(2026, 1, 6),  # Epifania
        date(2026, 4, 25),  # Liberazione
        date(2026, 5, 1),  # Lavoratori
        date(2026, 6, 2),  # Repubblica
        date(2026, 8, 15),  # Ferragosto
        date(2026, 11, 1),  # Ognissanti
        date(2026, 12, 8),  # Immacolata
        date(2026, 12, 25),  # Natale
        date(2026, 12, 26),  # Santo Stefano
    }
    assert expected_fixed.issubset(h)


def test_italian_holidays_2026_includes_easter_pasquetta() -> None:
    h = italian_holidays(2026)
    assert date(2026, 4, 5) in h  # Pasqua
    assert date(2026, 4, 6) in h  # Pasquetta


def test_italian_holidays_in_range_full_year() -> None:
    h = italian_holidays_in_range(date(2026, 1, 1), date(2026, 12, 31))
    assert len(h) == 12


def test_italian_holidays_in_range_partial() -> None:
    """Solo le festività dentro il range vengono ritornate."""
    h = italian_holidays_in_range(date(2026, 6, 1), date(2026, 9, 30))
    assert h == {date(2026, 6, 2), date(2026, 8, 15)}


def test_italian_holidays_in_range_crosses_year_boundary() -> None:
    """Range che attraversa fine anno include festività di entrambi gli anni."""
    h = italian_holidays_in_range(date(2025, 12, 14), date(2026, 1, 31))
    assert date(2025, 12, 25) in h  # Natale 2025
    assert date(2025, 12, 26) in h  # Santo Stefano 2025
    assert date(2026, 1, 1) in h  # Capodanno 2026
    assert date(2026, 1, 6) in h  # Epifania 2026
