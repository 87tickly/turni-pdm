"""Test integration API anagrafiche read-side (Sprint 5.6 R1).

Endpoint:
- GET /api/stazioni
- GET /api/materiali
- GET /api/depots
- GET /api/direttrici
- GET /api/localita-manutenzione

Pattern come `test_programmi_api.py`. Auth: 401 no token, 200 con
pianificatore_giro_demo o admin. Multi-tenant: solo dati dell'azienda
del JWT.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from colazione.db import dispose_engine
from colazione.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_DB_TESTS") == "1",
    reason="DB not configured for tests",
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module", autouse=True)
async def cleanup_engine() -> None:
    yield
    await dispose_engine()


def _login(client: TestClient, username: str, password: str) -> str:
    res = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert res.status_code == 200, res.text
    return str(res.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_stazioni_401_senza_token(client: TestClient) -> None:
    res = client.get("/api/stazioni")
    assert res.status_code == 401


def test_stazioni_200_con_pianificatore(client: TestClient) -> None:
    token = _login(client, "pianificatore_giro_demo", "demo12345")
    res = client.get("/api/stazioni", headers=_auth(token))
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    # Lista può essere vuota in test fresh; verifica solo lo schema
    if body:
        assert "codice" in body[0]
        assert "nome" in body[0]


def test_materiali_200(client: TestClient) -> None:
    token = _login(client, "pianificatore_giro_demo", "demo12345")
    res = client.get("/api/materiali", headers=_auth(token))
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)


def test_depots_200(client: TestClient) -> None:
    token = _login(client, "pianificatore_giro_demo", "demo12345")
    res = client.get("/api/depots", headers=_auth(token))
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    # Trenord ha 25 depot seed (vedi 0002_seed_trenord)
    assert len(body) >= 1
    assert "codice" in body[0]
    assert "stazione_principale_codice" in body[0]


def test_direttrici_200(client: TestClient) -> None:
    token = _login(client, "pianificatore_giro_demo", "demo12345")
    res = client.get("/api/direttrici", headers=_auth(token))
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    # Lista di stringhe (anche vuota se PdE non importato)


def test_localita_manutenzione_200(client: TestClient) -> None:
    token = _login(client, "pianificatore_giro_demo", "demo12345")
    res = client.get("/api/localita-manutenzione", headers=_auth(token))
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    # Trenord ha 7 sedi seed
    if body:
        assert "codice" in body[0]
        assert "codice_breve" in body[0]
        assert "stazione_collegata_codice" in body[0]
