"""Test ``GET /api/admin/pipeline-overview`` — Sprint 8.0 MR 6 (entry 171)."""

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
async def _module_teardown() -> None:
    yield
    await dispose_engine()


def _login(client: TestClient, username: str, password: str) -> str:
    res = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert res.status_code == 200, res.text
    return str(res.json()["access_token"])


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_pipeline_overview_admin_ok(client: TestClient) -> None:
    token = _login(client, "admin", "admin12345")
    res = client.get("/api/admin/pipeline-overview", headers=_h(token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert "programmi" in body
    assert "counters_per_stato_pdc" in body
    assert "counters_per_stato_manutenzione" in body
    assert "n_bloccati" in body
    assert isinstance(body["programmi"], list)


def test_pipeline_overview_pianificatore_403(client: TestClient) -> None:
    """Ruolo non admin → 403 (require_admin)."""
    token = _login(client, "pianificatore_giro_demo", "demo12345")
    res = client.get("/api/admin/pipeline-overview", headers=_h(token))
    assert res.status_code == 403


def test_pipeline_overview_senza_token_401(client: TestClient) -> None:
    res = client.get("/api/admin/pipeline-overview")
    assert res.status_code == 401
