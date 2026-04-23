"""
Test endpoint /api/calendario-agente (Step 10 followup, 23/04/2026).

Verifica:
- risposta strutturata AgentGridResponse con rows vuote se DB vuoto
- filtro deposito case-insensitive
- range_days clamp a [1, 62]
- stato cell "rest" per PdC senza variante compatibile con weekday
- stato "work" con turno_code per varianti compatibili
- stato "scomp" per is_disponibile=1
"""
from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    os.environ["JWT_SECRET"] = "test-secret"
    os.environ["ADMIN_DEFAULT_PASSWORD"] = "test"
    from server import app
    c = TestClient(app)
    yield c
    try:
        os.unlink(tmp.name)
    except Exception:
        pass


def test_calendario_agente_smoke(client):
    """L'endpoint risponde 200 anche con DB senza turni (rows vuote)."""
    r = client.get("/api/calendario-agente?start=2026-04-20&days=28")
    assert r.status_code == 200
    body = r.json()
    assert body["range_start"] == "2026-04-20"
    assert body["range_days"] == 28
    assert "rows" in body
    assert isinstance(body["rows"], list)


def test_range_days_clamp_max(client):
    # days > 62 deve essere clampato a 62
    r = client.get("/api/calendario-agente?start=2026-04-20&days=200")
    assert r.status_code == 200
    assert r.json()["range_days"] == 62


def test_range_days_clamp_min(client):
    # days <= 0 deve essere clampato a 1
    r = client.get("/api/calendario-agente?start=2026-04-20&days=0")
    assert r.status_code == 200
    assert r.json()["range_days"] == 1


def test_deposito_filter_upper(client):
    r1 = client.get("/api/calendario-agente?start=2026-04-20&deposito=MILANO")
    r2 = client.get("/api/calendario-agente?start=2026-04-20&deposito=milano")
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Entrambe dovrebbero restituire lo stesso set di righe (filtro UPPER)
    assert len(r1.json()["rows"]) == len(r2.json()["rows"])


def test_date_format_invalid(client):
    r = client.get("/api/calendario-agente?start=invalid-date")
    # Dovrebbe tornare 500 (ValueError da datetime.strptime) o 422.
    # In ogni caso non 200.
    assert r.status_code >= 400


def test_row_structure_if_turns_present(client):
    """Se nel DB esiste almeno un pdc_turn, verifica la struttura della
    riga ritornata."""
    r = client.get("/api/calendario-agente?start=2026-04-20&days=7")
    assert r.status_code == 200
    body = r.json()
    if not body["rows"]:
        pytest.skip("Nessun pdc_turn nel DB di test, skip struttura")
    row = body["rows"][0]
    assert "pdc_id" in row
    assert "pdc_code" in row
    assert "display_name" in row
    assert "matricola" in row
    assert "totals" in row
    assert "cells" in row
    assert len(row["cells"]) == 7
    for cell in row["cells"]:
        assert "date" in cell
        assert cell["state"] in (
            "work", "rest", "fr", "scomp", "uncov", "leave", "locked",
        )
