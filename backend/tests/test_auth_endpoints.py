"""Test endpoint auth (Sprint 2.2-2.4).

Richiede:
- Postgres locale up (docker compose up -d db)
- Migrazioni 0001 + 0002 + 0003 applicate (utenti `admin` / `pianificatore_giro_demo`)

Le password testate sono quelle di default seed (`admin12345`,
`demo12345`). Se si imposta `ADMIN_DEFAULT_PASSWORD` / `DEMO_PASSWORD`
i test falliscono — coerente con la natura "smoke" dei test.
"""

import os

import pytest
from fastapi.testclient import TestClient

from colazione.auth.tokens import (
    ACCESS_TOKEN_TYPE,
    create_refresh_token,
    decode_token,
)
from colazione.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_DB_TESTS") == "1",
    reason="DB not configured for tests",
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


# ----- /api/auth/login -----


def test_login_success_admin(client: TestClient) -> None:
    res = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin12345"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in_min"] > 0
    assert body["access_token"]
    assert body["refresh_token"]

    # Access token contiene flag admin + ruolo
    payload = decode_token(body["access_token"], expected_type=ACCESS_TOKEN_TYPE)
    assert payload["username"] == "admin"
    assert payload["is_admin"] is True
    assert "ADMIN" in payload["roles"]


def test_login_success_demo_user(client: TestClient) -> None:
    res = client.post(
        "/api/auth/login",
        json={"username": "pianificatore_giro_demo", "password": "demo12345"},
    )
    assert res.status_code == 200, res.text
    payload = decode_token(res.json()["access_token"], expected_type=ACCESS_TOKEN_TYPE)
    assert payload["is_admin"] is False
    assert "PIANIFICATORE_GIRO" in payload["roles"]


def test_login_wrong_password(client: TestClient) -> None:
    res = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong"},
    )
    assert res.status_code == 401
    assert res.json()["detail"] == "credenziali non valide"


def test_login_unknown_user(client: TestClient) -> None:
    res = client.post(
        "/api/auth/login",
        json={"username": "ghost", "password": "whatever"},
    )
    assert res.status_code == 401


def test_login_missing_fields(client: TestClient) -> None:
    """Pydantic validation: username/password obbligatori."""
    res = client.post("/api/auth/login", json={"username": "admin"})
    assert res.status_code == 422


# ----- /api/auth/refresh -----


def test_refresh_success(client: TestClient) -> None:
    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin12345"},
    )
    refresh_token = login.json()["refresh_token"]

    res = client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert res.status_code == 200, res.text
    new_access = res.json()["access_token"]
    payload = decode_token(new_access, expected_type=ACCESS_TOKEN_TYPE)
    assert payload["username"] == "admin"


def test_refresh_rejects_access_token(client: TestClient) -> None:
    """Access token usato come refresh → 401."""
    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin12345"},
    )
    access_token = login.json()["access_token"]

    res = client.post(
        "/api/auth/refresh",
        json={"refresh_token": access_token},
    )
    assert res.status_code == 401


def test_refresh_rejects_garbage(client: TestClient) -> None:
    res = client.post(
        "/api/auth/refresh",
        json={"refresh_token": "not-a-real-jwt"},
    )
    assert res.status_code == 401


def test_refresh_rejects_unknown_user(client: TestClient) -> None:
    """Refresh per user_id che non esiste → 401."""
    fake = create_refresh_token(user_id=99999)
    res = client.post(
        "/api/auth/refresh",
        json={"refresh_token": fake},
    )
    assert res.status_code == 401


# ----- /api/auth/me -----


def test_me_requires_auth(client: TestClient) -> None:
    res = client.get("/api/auth/me")
    assert res.status_code == 401


def test_me_with_valid_token(client: TestClient) -> None:
    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin12345"},
    )
    access = login.json()["access_token"]

    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["username"] == "admin"
    assert body["is_admin"] is True
    assert "ADMIN" in body["roles"]


def test_me_rejects_refresh_as_access(client: TestClient) -> None:
    """Refresh token usato come bearer access → 401."""
    refresh = create_refresh_token(user_id=1)
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {refresh}"})
    assert res.status_code == 401
    # decode_token solleva InvalidTokenError per type errato
    assert (
        "type errato" in res.json()["detail"].lower()
        or "non valido" in res.json()["detail"].lower()
    )


def test_me_rejects_wrong_scheme(client: TestClient) -> None:
    res = client.get("/api/auth/me", headers={"Authorization": "Basic abc:def"})
    assert res.status_code == 401
