"""Test integration API
``DELETE /api/giri/{id}/blocchi/{blocco_id}`` (Sprint 8.0 MR-B.2,
entry 232).

Iterazione 1: solo auth + 404. Test happy-path "blocco vuoto eliminato
con re-numerazione seq + check fattibilità violazioni" richiede setup
esteso (giro con blocchi vuoti reali) → iterazione 2.
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


# =====================================================================
# Auth + 404
# =====================================================================


async def test_elimina_senza_token_401(client: TestClient) -> None:
    res = client.delete("/api/giri/1/blocchi/1")
    assert res.status_code == 401


async def test_elimina_giro_inesistente_404(client: TestClient) -> None:
    token = _login(client, "admin", "admin12345")
    res = client.delete(
        "/api/giri/99999999/blocchi/1",
        headers=_auth(token),
    )
    assert res.status_code == 404


async def test_elimina_query_params_dry_run_ok(client: TestClient) -> None:
    """`dry_run=true` è accettato schema-wise (poi 404 sul lookup)."""
    token = _login(client, "admin", "admin12345")
    res = client.delete(
        "/api/giri/99999998/blocchi/1?dry_run=true",
        headers=_auth(token),
    )
    assert res.status_code == 404  # giro inesistente, ma schema OK

    res = client.delete(
        "/api/giri/99999998/blocchi/1?force=true",
        headers=_auth(token),
    )
    assert res.status_code == 404
