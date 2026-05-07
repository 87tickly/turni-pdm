"""Test integration API ``POST /api/giri/{id}/blocchi/{id}/sposta``
(Sprint 8.0 MR-B.1, entry 230).

Iterazione 1: solo auth + 404 + 422 (validazione payload). Test
happy-path "blocco spostato con re-numerazione seq" richiede setup
esteso (giro con > 1 giornate + blocchi con stazioni concrete) →
iterazione 2.
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


def _payload(
    *,
    giornata_target: int = 2,
    variant_index_target: int = 0,
    seq_target: int | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, object]:
    body: dict[str, object] = {
        "giornata_target": giornata_target,
        "variant_index_target": variant_index_target,
        "dry_run": dry_run,
        "force": force,
    }
    if seq_target is not None:
        body["seq_target"] = seq_target
    return body


# =====================================================================
# Auth + 404
# =====================================================================


async def test_sposta_senza_token_401(client: TestClient) -> None:
    res = client.post(
        "/api/giri/1/blocchi/1/sposta",
        json=_payload(),
    )
    assert res.status_code == 401


async def test_sposta_giro_inesistente_404(client: TestClient) -> None:
    token = _login(client, "admin", "admin12345")
    res = client.post(
        "/api/giri/99999999/blocchi/1/sposta",
        headers=_auth(token),
        json=_payload(),
    )
    assert res.status_code == 404


# =====================================================================
# 422 Pydantic validation
# =====================================================================


async def test_sposta_payload_invalido_422(client: TestClient) -> None:
    token = _login(client, "admin", "admin12345")

    # giornata_target mancante.
    res = client.post(
        "/api/giri/1/blocchi/1/sposta",
        headers=_auth(token),
        json={"variant_index_target": 0},
    )
    assert res.status_code == 422

    # giornata_target = 0 (ge=1).
    res = client.post(
        "/api/giri/1/blocchi/1/sposta",
        headers=_auth(token),
        json=_payload(giornata_target=0),
    )
    assert res.status_code == 422

    # variant_index_target = -1 (ge=0).
    res = client.post(
        "/api/giri/1/blocchi/1/sposta",
        headers=_auth(token),
        json=_payload(variant_index_target=-1),
    )
    assert res.status_code == 422

    # seq_target = 0 (ge=1, optional ma se passato deve essere >= 1).
    res = client.post(
        "/api/giri/1/blocchi/1/sposta",
        headers=_auth(token),
        json=_payload(seq_target=0),
    )
    assert res.status_code == 422

    # extra field rifiutato (model_config extra="forbid").
    res = client.post(
        "/api/giri/1/blocchi/1/sposta",
        headers=_auth(token),
        json={
            "giornata_target": 1,
            "variant_index_target": 0,
            "campo_inesistente": "x",
        },
    )
    assert res.status_code == 422
