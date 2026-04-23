"""
Test Step 3 (23/04/2026) — Calendario preriscaldo.

Richiesta utente: preriscaldo rinforzato attivo da 1 dicembre a fine
febbraio (incluso). Fuori periodo: False.
"""
from __future__ import annotations

from datetime import date

from src.turn_builder.preheat_calendar import (
    is_preheat_period, preheat_period_label, PREHEAT_MONTHS,
)


def test_inside_period_december():
    assert is_preheat_period(date(2026, 12, 1)) is True
    assert is_preheat_period(date(2026, 12, 15)) is True
    assert is_preheat_period(date(2026, 12, 31)) is True


def test_inside_period_january():
    assert is_preheat_period(date(2027, 1, 1)) is True
    assert is_preheat_period(date(2027, 1, 31)) is True


def test_inside_period_february():
    # Anno non bisestile
    assert is_preheat_period(date(2026, 2, 1)) is True
    assert is_preheat_period(date(2026, 2, 28)) is True
    # Anno bisestile: 29 feb deve essere True
    assert is_preheat_period(date(2028, 2, 29)) is True


def test_outside_period_march():
    assert is_preheat_period(date(2026, 3, 1)) is False
    assert is_preheat_period(date(2026, 3, 15)) is False
    assert is_preheat_period(date(2026, 3, 31)) is False


def test_outside_period_november():
    assert is_preheat_period(date(2026, 11, 30)) is False
    assert is_preheat_period(date(2026, 11, 1)) is False


def test_outside_period_summer():
    for month in (4, 5, 6, 7, 8, 9, 10):
        assert is_preheat_period(date(2026, month, 15)) is False, \
            f"Mese {month} non dovrebbe essere periodo preriscaldo"


def test_months_constant():
    # Garanzia di stabilita' per chi importa PREHEAT_MONTHS
    assert PREHEAT_MONTHS == frozenset({12, 1, 2})


def test_label():
    assert preheat_period_label(date(2026, 12, 15)) == "INVERNO"
    assert preheat_period_label(date(2026, 7, 15)) == "ESTATE"
