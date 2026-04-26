"""Test integration API Sprint 4.4.5b — `POST /api/programmi/{id}/genera-giri`.

Verifica auth, status code, validazione query params, mapping errori
(404/400/409/422), happy path con response shape.

Setup via DB diretto (azienda Trenord seed + stazioni S99NNN + località
TEST_LOC_API + programma TEST_API).
"""

from __future__ import annotations

import os
from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from colazione.db import dispose_engine, session_scope
from colazione.main import app
from colazione.models.anagrafica import LocalitaManutenzione, Stazione
from colazione.models.corse import CorsaCommerciale
from colazione.models.programmi import (
    ProgrammaMateriale,
    ProgrammaRegolaAssegnazione,
)

pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_DB_TESTS") == "1",
    reason="DB not configured for tests",
)


LOC_CODICE = "TEST_LOC_API"
LOC_BREVE = "TAPI"
PROG_NAME = "TEST_API_genera_giri"


# =====================================================================
# Setup
# =====================================================================


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


async def _wipe() -> None:
    async with session_scope() as session:
        await session.execute(text("DELETE FROM giro_materiale"))
        await session.execute(text("DELETE FROM corsa_materiale_vuoto"))
        await session.execute(
            text("DELETE FROM corsa_commerciale WHERE numero_treno LIKE 'TEST_%'")
        )
        await session.execute(
            text(
                "DELETE FROM programma_regola_assegnazione WHERE programma_id IN ("
                "SELECT id FROM programma_materiale WHERE nome LIKE 'TEST_%'"
                ")"
            )
        )
        await session.execute(text("DELETE FROM programma_materiale WHERE nome LIKE 'TEST_%'"))
        await session.execute(text("DELETE FROM localita_manutenzione WHERE codice LIKE 'TEST_%'"))
        await session.execute(text("DELETE FROM stazione WHERE codice LIKE 'S99%'"))


@pytest.fixture(autouse=True)
async def clean_state() -> None:
    """Wipe pre + post-test (evita FK leftover su test successivi)."""
    await _wipe()
    yield
    await _wipe()


@pytest.fixture(scope="module", autouse=True)
async def cleanup_engine() -> None:
    yield
    await dispose_engine()


async def _setup_db_completo(stato_programma: str = "attivo") -> int:
    """Crea stazioni + località + programma + regola + 2 corse. Ritorna programma_id."""
    async with session_scope() as session:
        # azienda_id pianificatore_giro_demo
        # (recupero dinamico per non dipendere dal sequence)
        az_row = (
            await session.execute(text("SELECT id FROM azienda WHERE codice = 'trenord'"))
        ).first()
        assert az_row is not None
        az_id = int(az_row[0])

        for codice in {"S99001", "S99002"}:
            session.add(Stazione(codice=codice, nome=codice, azienda_id=az_id))
        await session.flush()

        loc = LocalitaManutenzione(
            codice=LOC_CODICE,
            codice_breve=LOC_BREVE,
            nome_canonico=LOC_CODICE,
            stazione_collegata_codice="S99001",
            azienda_id=az_id,
        )
        session.add(loc)

        prog = ProgrammaMateriale(
            azienda_id=az_id,
            nome=PROG_NAME,
            valido_da=date(2026, 1, 1),
            valido_a=date(2026, 12, 31),
            stato=stato_programma,
            n_giornate_default=5,
            fascia_oraria_tolerance_min=30,
            strict_options_json={
                "no_corse_residue": False,
                "no_overcapacity": False,
                "no_aggancio_non_validato": False,
                "no_orphan_blocks": False,
                "no_giro_non_chiuso_a_localita": False,
                "no_km_eccesso": False,
            },
        )
        session.add(prog)
        await session.flush()
        prog_id = int(prog.id)

        session.add(
            ProgrammaRegolaAssegnazione(
                programma_id=prog_id,
                filtri_json=[],
                materiale_tipo_codice="ALe711",
                numero_pezzi=3,
                priorita=10,
            )
        )

        for nt, o, d, p, a in [
            ("TEST_API_1", "S99001", "S99002", (8, 0), (9, 0)),
            ("TEST_API_2", "S99002", "S99001", (10, 0), (11, 0)),
        ]:
            session.add(
                CorsaCommerciale(
                    azienda_id=az_id,
                    row_hash=("test_" + nt).ljust(64, "0")[:64],
                    numero_treno=nt,
                    codice_origine=o,
                    codice_destinazione=d,
                    ora_partenza=time(*p),
                    ora_arrivo=time(*a),
                    valido_da=date(2026, 1, 1),
                    valido_a=date(2026, 12, 31),
                    valido_in_date_json=["2026-04-27"],
                )
            )

        return prog_id


def _login(client: TestClient, username: str, password: str) -> str:
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200
    return str(res.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


_PARAMS_OK: dict[str, str | int] = {
    "data_inizio": "2026-04-27",
    "n_giornate": 1,
    "localita_codice": LOC_CODICE,
}


# =====================================================================
# Auth
# =====================================================================


async def test_genera_senza_token_401(client: TestClient) -> None:
    res = client.post("/api/programmi/1/genera-giri", params=_PARAMS_OK)
    assert res.status_code == 401


async def test_admin_puo_generare(client: TestClient) -> None:
    prog_id = await _setup_db_completo()
    token = _login(client, "admin", "admin12345")
    res = client.post(
        f"/api/programmi/{prog_id}/genera-giri",
        params=_PARAMS_OK,
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text


async def test_pianificatore_puo_generare(client: TestClient) -> None:
    prog_id = await _setup_db_completo()
    token = _login(client, "pianificatore_giro_demo", "demo12345")
    res = client.post(
        f"/api/programmi/{prog_id}/genera-giri",
        params=_PARAMS_OK,
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text


# =====================================================================
# Errori 4xx
# =====================================================================


async def test_programma_inesistente_404(client: TestClient) -> None:
    token = _login(client, "admin", "admin12345")
    res = client.post(
        "/api/programmi/99999/genera-giri",
        params=_PARAMS_OK,
        headers=_auth(token),
    )
    assert res.status_code == 404
    assert "non trovato" in res.json()["detail"].lower()


async def test_localita_inesistente_404(client: TestClient) -> None:
    prog_id = await _setup_db_completo()
    token = _login(client, "admin", "admin12345")
    params = dict(_PARAMS_OK, localita_codice="NON_ESISTE")
    res = client.post(
        f"/api/programmi/{prog_id}/genera-giri",
        params=params,
        headers=_auth(token),
    )
    assert res.status_code == 404


async def test_programma_in_bozza_400(client: TestClient) -> None:
    """Programma non attivo → 400."""
    prog_id = await _setup_db_completo(stato_programma="bozza")
    token = _login(client, "admin", "admin12345")
    res = client.post(
        f"/api/programmi/{prog_id}/genera-giri",
        params=_PARAMS_OK,
        headers=_auth(token),
    )
    assert res.status_code == 400
    assert "attivo" in res.json()["detail"].lower()


async def test_giri_esistenti_409_senza_force(client: TestClient) -> None:
    prog_id = await _setup_db_completo()
    token = _login(client, "admin", "admin12345")

    # Prima generazione → 200
    res1 = client.post(
        f"/api/programmi/{prog_id}/genera-giri", params=_PARAMS_OK, headers=_auth(token)
    )
    assert res1.status_code == 200

    # Seconda → 409
    res2 = client.post(
        f"/api/programmi/{prog_id}/genera-giri", params=_PARAMS_OK, headers=_auth(token)
    )
    assert res2.status_code == 409
    assert "force" in res2.json()["detail"].lower()


async def test_force_true_ok(client: TestClient) -> None:
    prog_id = await _setup_db_completo()
    token = _login(client, "admin", "admin12345")

    client.post(f"/api/programmi/{prog_id}/genera-giri", params=_PARAMS_OK, headers=_auth(token))

    # Seconda con force → 200
    params_force = dict(_PARAMS_OK, force="true")
    res = client.post(
        f"/api/programmi/{prog_id}/genera-giri", params=params_force, headers=_auth(token)
    )
    assert res.status_code == 200


async def test_n_giornate_zero_422(client: TestClient) -> None:
    """Query validation: n_giornate ge=1 deve fallire 422."""
    prog_id = await _setup_db_completo()
    token = _login(client, "admin", "admin12345")
    bad = dict(_PARAMS_OK, n_giornate=0)
    res = client.post(f"/api/programmi/{prog_id}/genera-giri", params=bad, headers=_auth(token))
    assert res.status_code == 422


# =====================================================================
# Happy path response shape
# =====================================================================


async def test_response_shape_completa(client: TestClient) -> None:
    prog_id = await _setup_db_completo()
    token = _login(client, "admin", "admin12345")
    res = client.post(
        f"/api/programmi/{prog_id}/genera-giri",
        params=_PARAMS_OK,
        headers=_auth(token),
    )
    assert res.status_code == 200
    body = res.json()
    # Shape stats
    assert "giri_ids" in body
    assert "n_giri_creati" in body
    assert "n_corse_processate" in body
    assert "n_corse_residue" in body
    assert "n_giri_chiusi" in body
    assert "n_giri_non_chiusi" in body
    assert "n_eventi_composizione" in body
    assert "warnings" in body
    # Valori sensati per il setup
    assert body["n_giri_creati"] == 1
    assert body["n_corse_processate"] == 2
    assert body["n_corse_residue"] == 0
    assert body["n_giri_chiusi"] == 1
    assert isinstance(body["giri_ids"], list)
    assert len(body["giri_ids"]) == 1
