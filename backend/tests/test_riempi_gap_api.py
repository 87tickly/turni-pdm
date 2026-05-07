"""Test integration API ``POST /api/programmi/{id}/riempi-gap`` (entry 219).

Iterazione 1: solo auth + 404 + scenario "programma senza gap riempibili".
I test happy-path con scenario complesso (giro con gap esatto coprible da
corsa scartata) richiedono setup manuale dei blocchi → iterazione 2.
"""

from __future__ import annotations

import os
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from colazione.db import dispose_engine, session_scope
from colazione.main import app
from colazione.models.programmi import ProgrammaMateriale

pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_DB_TESTS") == "1",
    reason="DB not configured for tests",
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


async def _wipe() -> None:
    async with session_scope() as session:
        await session.execute(text("DELETE FROM turno_pdc"))
        await session.execute(text("DELETE FROM giro_materiale"))
        await session.execute(text("DELETE FROM corsa_materiale_vuoto"))
        await session.execute(
            text("DELETE FROM programma_materiale WHERE nome LIKE 'TEST_RG_%'")
        )


@pytest.fixture(autouse=True)
async def clean_state() -> None:
    await _wipe()
    yield
    await _wipe()


@pytest.fixture(scope="module", autouse=True)
async def cleanup_engine() -> None:
    yield
    await dispose_engine()


def _login(client: TestClient, username: str, password: str) -> str:
    res = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert res.status_code == 200
    return str(res.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# =====================================================================
# Auth + 404
# =====================================================================


async def test_riempi_gap_senza_token_401(client: TestClient) -> None:
    res = client.post("/api/programmi/1/riempi-gap")
    assert res.status_code == 401


async def test_riempi_gap_programma_inesistente_404(client: TestClient) -> None:
    token = _login(client, "admin", "admin12345")
    res = client.post(
        "/api/programmi/99999/riempi-gap", headers=_auth(token)
    )
    assert res.status_code == 404


# =====================================================================
# Edge: programma senza regole → 0 inserimenti
# =====================================================================


async def test_riempi_gap_programma_senza_regole(client: TestClient) -> None:
    """Senza regole non c'è perimetro → endpoint torna 0."""
    async with session_scope() as session:
        az_row = (
            await session.execute(
                text("SELECT id FROM azienda WHERE codice = 'trenord'")
            )
        ).first()
        assert az_row is not None
        az_id = int(az_row[0])
        prog = ProgrammaMateriale(
            azienda_id=az_id,
            nome="TEST_RG_no_regole",
            valido_da=date(2026, 4, 1),
            valido_a=date(2026, 4, 30),
            stato="attivo",
            n_giornate_default=5,
            fascia_oraria_tolerance_min=30,
            strict_options_json={
                "no_corse_residue": False,
                "no_overcapacity": False,
                "no_aggancio_non_validato": False,
                "no_orphan_blocks": False,
                "no_giro_appeso": False,
                "no_km_eccesso": False,
            },
        )
        session.add(prog)
        await session.flush()
        prog_id = int(prog.id)

    token = _login(client, "admin", "admin12345")

    # dry_run default
    res = client.post(
        f"/api/programmi/{prog_id}/riempi-gap", headers=_auth(token)
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["applied"] is False
    assert body["n_corse_inserite"] == 0
    assert body["n_corse_ancora_scoperte"] == 0
    assert body["inserimenti"] == []


async def test_riempi_gap_dry_run_default_true(client: TestClient) -> None:
    """Verifica che ``dry_run`` di default sia ``True`` → ``applied=False``."""
    async with session_scope() as session:
        az_row = (
            await session.execute(
                text("SELECT id FROM azienda WHERE codice = 'trenord'")
            )
        ).first()
        assert az_row is not None
        az_id = int(az_row[0])
        prog = ProgrammaMateriale(
            azienda_id=az_id,
            nome="TEST_RG_dry_default",
            valido_da=date(2026, 4, 1),
            valido_a=date(2026, 4, 30),
            stato="attivo",
            n_giornate_default=5,
            fascia_oraria_tolerance_min=30,
            strict_options_json={
                "no_corse_residue": False,
                "no_overcapacity": False,
                "no_aggancio_non_validato": False,
                "no_orphan_blocks": False,
                "no_giro_appeso": False,
                "no_km_eccesso": False,
            },
        )
        session.add(prog)
        await session.flush()
        prog_id = int(prog.id)

    token = _login(client, "admin", "admin12345")
    res = client.post(
        f"/api/programmi/{prog_id}/riempi-gap", headers=_auth(token)
    )
    assert res.status_code == 200
    assert res.json()["applied"] is False

    # Esplicito dry_run=false (apply) → applied=True (anche con 0 inserimenti)
    res = client.post(
        f"/api/programmi/{prog_id}/riempi-gap?dry_run=false",
        headers=_auth(token),
    )
    assert res.status_code == 200
    assert res.json()["applied"] is True
