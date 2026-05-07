"""Test integration API
``POST /api/giri/{id}/blocchi/aggiungi-vuoto`` (Sprint 8.0 MR-B.2.2,
entry 235).

Iter 1: solo auth + 404 + 422 (validazione payload).
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
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert res.status_code == 200
    return str(res.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "giornata_target": 1,
        "variant_index_target": 0,
        "stazione_da_codice": "S00001",
        "stazione_a_codice": "S00002",
        "ora_inizio": "10:00",
        "ora_fine": "10:30",
        "descrizione": "Vuoto manuale test",
        "dry_run": False,
        "force": False,
    }
    base.update(overrides)
    return base


# =====================================================================
# Auth + 404
# =====================================================================


async def test_aggiungi_senza_token_401(client: TestClient) -> None:
    res = client.post(
        "/api/giri/1/blocchi/aggiungi-vuoto",
        json=_payload(),
    )
    assert res.status_code == 401


async def test_aggiungi_giro_inesistente_404(client: TestClient) -> None:
    token = _login(client, "admin", "admin12345")
    res = client.post(
        "/api/giri/99999999/blocchi/aggiungi-vuoto",
        headers=_auth(token),
        json=_payload(),
    )
    assert res.status_code == 404


# =====================================================================
# 422 validation
# =====================================================================


async def test_aggiungi_payload_invalido_422(client: TestClient) -> None:
    token = _login(client, "admin", "admin12345")

    # giornata_target mancante.
    res = client.post(
        "/api/giri/1/blocchi/aggiungi-vuoto",
        headers=_auth(token),
        json={
            "variant_index_target": 0,
            "stazione_da_codice": "S00001",
            "stazione_a_codice": "S00002",
            "ora_inizio": "10:00",
            "ora_fine": "10:30",
        },
    )
    assert res.status_code == 422

    # ora_fine mancante.
    res = client.post(
        "/api/giri/1/blocchi/aggiungi-vuoto",
        headers=_auth(token),
        json=_payload(ora_fine=None),
    )
    assert res.status_code == 422

    # stazione_da vuota.
    res = client.post(
        "/api/giri/1/blocchi/aggiungi-vuoto",
        headers=_auth(token),
        json=_payload(stazione_da_codice=""),
    )
    assert res.status_code == 422

    # variant_index_target = -1.
    res = client.post(
        "/api/giri/1/blocchi/aggiungi-vuoto",
        headers=_auth(token),
        json=_payload(variant_index_target=-1),
    )
    assert res.status_code == 422

    # extra field rifiutato.
    res = client.post(
        "/api/giri/1/blocchi/aggiungi-vuoto",
        headers=_auth(token),
        json={**_payload(), "extra_field": "x"},
    )
    assert res.status_code == 422


async def test_aggiungi_orari_invalidi_400(client: TestClient) -> None:
    """Formato orario sbagliato → 400 dal _parse_time_input."""
    token = _login(client, "admin", "admin12345")
    # Schema-wise OK (string), ma il parser interno rifiuta.
    # Nota: questi test partono da un giro inesistente (99999999), il
    # 404 arriva prima del parse. Per testare il 400 reale servirebbe
    # un giro valido → iterazione 2 con DB seedato.
    res = client.post(
        "/api/giri/99999999/blocchi/aggiungi-vuoto",
        headers=_auth(token),
        json=_payload(ora_inizio="25:99"),
    )
    assert res.status_code == 404  # giro non trovato prima del parse
