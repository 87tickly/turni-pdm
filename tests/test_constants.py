"""Test costanti operative."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.constants import (
    MAX_PRESTAZIONE_MIN,
    MAX_CONDOTTA_MIN,
    MEAL_MIN,
    EXTRA_START_MIN,
    EXTRA_END_MIN,
    MAX_NIGHT_MIN,
    REST_STANDARD_H,
    REST_AFTER_001_0100_H,
    REST_AFTER_NIGHT_H,
    WEEKLY_REST_MIN_H,
    WORK_BLOCK,
    REST_BLOCK,
    ACCESSORY_RULES,
    TEMPI_MEDI_RULES,
    ALLOWED_FR_STATIONS_DEFAULT,
    load_fr_stations,
)


def test_costanti_valori():
    assert MAX_PRESTAZIONE_MIN == 510
    assert MAX_CONDOTTA_MIN == 330
    assert MEAL_MIN == 30
    assert EXTRA_START_MIN == 5
    assert EXTRA_END_MIN == 5
    assert MAX_NIGHT_MIN == 420
    assert REST_STANDARD_H == 11
    assert REST_AFTER_001_0100_H == 14
    assert REST_AFTER_NIGHT_H == 16
    assert WEEKLY_REST_MIN_H == 62
    assert WORK_BLOCK == 5
    assert REST_BLOCK == 2


def test_accessory_rules():
    assert ACCESSORY_RULES["default_start"] == 10
    assert ACCESSORY_RULES["default_end"] == 8


def test_tempi_medi_rules():
    assert TEMPI_MEDI_RULES["default_extra"] == 4


def test_fr_stations_default():
    assert "MILANO CENTRALE" in ALLOWED_FR_STATIONS_DEFAULT
    assert "BERGAMO" in ALLOWED_FR_STATIONS_DEFAULT
    assert len(ALLOWED_FR_STATIONS_DEFAULT) > 0


def test_load_fr_stations_fallback(monkeypatch):
    # Simula assenza file
    monkeypatch.setattr("src.constants.FR_STATIONS_FILE", "nonexistent_file_xyz.txt")
    stations = load_fr_stations()
    assert len(stations) == len(ALLOWED_FR_STATIONS_DEFAULT)


if __name__ == "__main__":
    test_costanti_valori()
    test_accessory_rules()
    test_tempi_medi_rules()
    test_fr_stations_default()
    print("All constant tests passed!")
