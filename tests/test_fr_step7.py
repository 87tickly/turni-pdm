"""
Test Step 7 (23/04/2026) — FR candidate + registry.

Verifica:
- day_assembler marca giornata fr_candidate=True se stazione finale e'
  in fr_candidate_stations (non ancora approvata)
- giornata rimane is_fr=True con fr_candidate=False se stazione in
  fr_stations (approvata)
- fr_registry: approve / list / revoke / approve_batch
"""
from __future__ import annotations

import sqlite3

import pytest

from src.turn_builder import day_assembler, fr_registry
from src.turn_builder.cv_registry import ensure_schema as ensure_cv_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("""
        CREATE TABLE pdc_fr_approved (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pdc_id TEXT NOT NULL,
            station TEXT NOT NULL,
            approved_at TEXT DEFAULT CURRENT_TIMESTAMP,
            notes TEXT DEFAULT '',
            UNIQUE(pdc_id, station)
        )
    """)
    ensure_cv_schema(c)  # non strettamente necessario ma non da' fastidio
    yield c
    c.close()


def _seg(tid, frm, to, dep, arr, mtid=1):
    return {
        "train_id": tid, "from_station": frm, "to_station": to,
        "dep_time": dep, "arr_time": arr, "material_turn_id": mtid,
        "day_index": 1, "is_deadhead": False,
    }


def _seed(trains, frm, to, first_dep, last_arr, cond):
    return {
        "trains": trains, "from_station": frm, "to_station": to,
        "first_dep_min": first_dep, "last_arr_min": last_arr,
        "condotta_min": cond, "score": 100.0,
    }


# ---------------------------------------------------------------------------
# fr_registry: read/write
# ---------------------------------------------------------------------------

def test_approve_e_list(conn):
    fr_registry.approve(conn, "PDC_A", "ASTI")
    approved = fr_registry.list_approved(conn, "PDC_A")
    assert approved == {"ASTI"}


def test_approve_duplicato_idempotente(conn):
    fr_registry.approve(conn, "PDC_A", "ASTI")
    fr_registry.approve(conn, "PDC_A", "ASTI")
    assert len(fr_registry.list_approved(conn, "PDC_A")) == 1


def test_approve_lowercase_normalizzato(conn):
    fr_registry.approve(conn, "PDC_A", "asti")
    assert fr_registry.list_approved(conn, "PDC_A") == {"ASTI"}


def test_revoke(conn):
    fr_registry.approve(conn, "PDC_A", "ASTI")
    fr_registry.approve(conn, "PDC_A", "PAVIA")
    fr_registry.revoke(conn, "PDC_A", "ASTI")
    assert fr_registry.list_approved(conn, "PDC_A") == {"PAVIA"}


def test_approve_batch_ritorna_nuovi(conn):
    fr_registry.approve(conn, "PDC_A", "ASTI")
    added = fr_registry.approve_batch(conn, "PDC_A", ["ASTI", "PAVIA", "NOVARA"])
    assert added == 2   # ASTI gia' esisteva, PAVIA + NOVARA nuove


def test_pdc_diversi_non_condividono(conn):
    fr_registry.approve(conn, "PDC_A", "ASTI")
    fr_registry.approve(conn, "PDC_B", "PAVIA")
    assert fr_registry.list_approved(conn, "PDC_A") == {"ASTI"}
    assert fr_registry.list_approved(conn, "PDC_B") == {"PAVIA"}


# ---------------------------------------------------------------------------
# day_assembler: fr_candidate behavior
# ---------------------------------------------------------------------------

def test_fr_approvata_non_e_candidata():
    # Seed che termina in ASTI senza possibilita' di rientro (niente segs
    # ASTI->ALE nell'all_day_segments). ASTI e' in fr_stations (approvata).
    # -> is_fr=True, fr_candidate=False.
    seed_t = _seg("S1", "ALE", "ASTI", "11:00", "12:30")
    seed = _seed([seed_t], "ALE", "ASTI", 11 * 60, 12 * 60 + 30, 90)
    result = day_assembler.assemble_day(
        seed=seed, deposito="ALE", all_day_segments=[seed_t],
        fr_stations={"ASTI"},
    )
    assert result is not None
    assert result["is_fr"] is True
    assert result["fr_candidate"] is False
    assert result["fr_station"] == "ASTI"


def test_fr_candidata_non_approvata():
    # ASTI NON in fr_stations ma in fr_candidate_stations -> marcata candidata
    seed_t = _seg("S1", "ALE", "ASTI", "11:00", "12:30")
    seed = _seed([seed_t], "ALE", "ASTI", 11 * 60, 12 * 60 + 30, 90)
    result = day_assembler.assemble_day(
        seed=seed, deposito="ALE", all_day_segments=[seed_t],
        fr_stations=set(),
        fr_candidate_stations={"ASTI"},
    )
    assert result is not None
    assert result["is_fr"] is True
    assert result["fr_candidate"] is True
    assert result["fr_station"] == "ASTI"


def test_fr_ne_approvata_ne_candidata_scartata():
    # Nessuna FR configurata -> giornata impossibile da chiudere -> None
    seed_t = _seg("S1", "ALE", "ASTI", "11:00", "12:30")
    seed = _seed([seed_t], "ALE", "ASTI", 11 * 60, 12 * 60 + 30, 90)
    result = day_assembler.assemble_day(
        seed=seed, deposito="ALE", all_day_segments=[seed_t],
    )
    assert result is None


def test_rientro_disponibile_non_attiva_fr():
    # Esiste un segmento di rientro ASTI->ALE. Anche se ASTI e' in
    # fr_candidate_stations, il rientro viene preferito (FR = fallback).
    # Ret dep 13:30 così c'è gap 60min per slot 3 refez (turno strutturato,
    # niente fallback slot 4/5).
    seed_t = _seg("S1", "ALE", "ASTI", "11:00", "12:30")
    ret = _seg("R1", "ASTI", "ALE", "13:30", "14:30")
    seed = _seed([seed_t], "ALE", "ASTI", 11 * 60, 12 * 60 + 30, 90)
    result = day_assembler.assemble_day(
        seed=seed, deposito="ALE", all_day_segments=[seed_t, ret],
        fr_candidate_stations={"ASTI"},
    )
    assert result is not None
    assert result["is_fr"] is False
    assert result["fr_candidate"] is False
    assert result["returns_depot"] is True
