"""Test reader PdE (Sprint 3.1)."""

from pathlib import Path

import pytest

from colazione.importers.pde import read_pde_file

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SAMPLE_XLSX = FIXTURE_DIR / "pde_sample.xlsx"


def test_read_xlsx_fixture_exists() -> None:
    assert SAMPLE_XLSX.exists(), f"Fixture mancante: {SAMPLE_XLSX}"


def test_read_xlsx_returns_38_rows() -> None:
    rows = read_pde_file(SAMPLE_XLSX)
    assert len(rows) == 38


def test_read_xlsx_header_columns() -> None:
    rows = read_pde_file(SAMPLE_XLSX)
    first = rows[0]
    # 124 colonne attese (PdE Trenord)
    assert len(first) == 124
    # Colonne identificative presenti
    for col in ["Treno 1", "Cod Origine", "Ora Or", "Periodicità", "Valido da"]:
        assert col in first


def test_read_xlsx_row_value_types() -> None:
    """Verifica tipi nativi normalizzati da openpyxl."""
    rows = read_pde_file(SAMPLE_XLSX)
    r = rows[0]
    # Periodicità deve essere stringa
    assert isinstance(r["Periodicità"], str)
    # Treno 1 può essere int (openpyxl normalizza float integer-valued)
    assert r["Treno 1"] is not None


def test_read_unsupported_format_raises() -> None:
    with pytest.raises(ValueError, match="Formato non supportato"):
        read_pde_file(Path("/tmp/fake.csv"))
