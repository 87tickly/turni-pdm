"""Test integration ``/api/personale-pdc/*`` — Sprint 8.0 MR 3 (entry 168).

Setup minimo: utente PERSONALE_PDC creato on-the-fly + assertion
che chiama l'endpoint con vari ruoli e verifica auth/empty-state.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from colazione.auth.password import hash_password
from colazione.db import dispose_engine, session_scope
from colazione.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_DB_TESTS") == "1",
    reason="DB not configured for tests",
)


_USER_PREFIX = "_test_personale_pdc_"
_TEST_PASSWORD = "pwd_test_personale_pdc_8_0"

_TEST_ROLES: tuple[tuple[str, str], ...] = (
    ("personale_pdc", "PERSONALE_PDC"),
    ("pianificatore_pdc", "PIANIFICATORE_PDC"),
    ("gestione_personale", "GESTIONE_PERSONALE"),
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


async def _ensure_test_users() -> None:
    pwd_hash = hash_password(_TEST_PASSWORD)
    async with session_scope() as session:
        for suffix, ruolo in _TEST_ROLES:
            username = f"{_USER_PREFIX}{suffix}"
            await session.execute(
                text(
                    "INSERT INTO app_user (username, password_hash, is_admin, "
                    "azienda_id) "
                    "SELECT CAST(:u AS VARCHAR), :h, FALSE, "
                    "  (SELECT id FROM azienda WHERE codice = 'trenord') "
                    "WHERE NOT EXISTS ("
                    "  SELECT 1 FROM app_user WHERE username = CAST(:u AS VARCHAR))"
                ),
                {"u": username, "h": pwd_hash},
            )
            await session.execute(
                text(
                    "INSERT INTO app_user_ruolo (app_user_id, ruolo) "
                    "SELECT u.id, CAST(:r AS VARCHAR) FROM app_user u "
                    "WHERE u.username = CAST(:u AS VARCHAR) "
                    "  AND NOT EXISTS ("
                    "    SELECT 1 FROM app_user_ruolo r "
                    "    WHERE r.app_user_id = u.id "
                    "      AND r.ruolo = CAST(:r AS VARCHAR))"
                ),
                {"u": username, "r": ruolo},
            )


async def _wipe_test_users() -> None:
    async with session_scope() as session:
        await session.execute(
            text("DELETE FROM app_user WHERE username LIKE :p"),
            {"p": f"{_USER_PREFIX}%"},
        )


@pytest.fixture(scope="module", autouse=True)
async def _module_setup() -> None:
    await _ensure_test_users()
    yield
    await _wipe_test_users()
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


def test_mio_turno_personale_senza_persona_collegata_ritorna_lista_vuota(
    client: TestClient,
) -> None:
    """L'utente PERSONALE_PDC esiste ma non ha una ``persona`` con
    ``user_id`` valorizzato → 200 con []."""
    token = _login(
        client, f"{_USER_PREFIX}personale_pdc", _TEST_PASSWORD
    )
    res = client.get("/api/personale-pdc/mio-turno", headers=_h(token))
    assert res.status_code == 200, res.text
    assert res.json() == []


def test_mio_turno_pianificatore_pdc_ammesso_per_debug(
    client: TestClient,
) -> None:
    """``PIANIFICATORE_PDC`` è ammesso (debug/visualizzazione cross-utente)."""
    token = _login(
        client, f"{_USER_PREFIX}pianificatore_pdc", _TEST_PASSWORD
    )
    res = client.get("/api/personale-pdc/mio-turno", headers=_h(token))
    assert res.status_code == 200


def test_mio_turno_gestione_personale_403(client: TestClient) -> None:
    """``GESTIONE_PERSONALE`` non ha accesso (vede aggregati nelle proprie
    route, non il "mio turno" del singolo PdC)."""
    token = _login(
        client, f"{_USER_PREFIX}gestione_personale", _TEST_PASSWORD
    )
    res = client.get("/api/personale-pdc/mio-turno", headers=_h(token))
    assert res.status_code == 403


def test_mio_turno_admin_bypassa(client: TestClient) -> None:
    """Admin bypassa il role check (anche se non ha persona collegata)."""
    token = _login(client, "admin", "admin12345")
    res = client.get("/api/personale-pdc/mio-turno", headers=_h(token))
    assert res.status_code == 200
    assert res.json() == []


def test_mio_turno_senza_token_401(client: TestClient) -> None:
    res = client.get("/api/personale-pdc/mio-turno")
    assert res.status_code == 401
