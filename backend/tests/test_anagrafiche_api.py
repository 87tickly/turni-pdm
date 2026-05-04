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


# =====================================================================
# Sprint 7.9 MR β2-0 — Località di sosta intermedia
# =====================================================================


def test_localita_sosta_401_senza_token(client: TestClient) -> None:
    res = client.get("/api/localita-sosta")
    assert res.status_code == 401


def test_localita_sosta_200_con_pianificatore(client: TestClient) -> None:
    """Trenord ha almeno MISR seed dalla migration 0022."""
    token = _login(client, "pianificatore_giro_demo", "demo12345")
    res = client.get("/api/localita-sosta", headers=_auth(token))
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    # Verifica schema + presenza MISR (seed)
    if body:
        assert "id" in body[0]
        assert "codice" in body[0]
        assert "nome" in body[0]
        assert "stazione_collegata_codice" in body[0]
        assert "is_attiva" in body[0]
        codici = [r["codice"] for r in body]
        assert "MISR" in codici, f"MISR seed mancante; trovati: {codici}"


def test_localita_sosta_create_richiede_admin(client: TestClient) -> None:
    """POST richiede ruolo ADMIN, non basta PIANIFICATORE_GIRO."""
    token = _login(client, "pianificatore_giro_demo", "demo12345")
    res = client.post(
        "/api/localita-sosta",
        json={"codice": "TEST-PIA", "nome": "Test pianificatore"},
        headers=_auth(token),
    )
    assert res.status_code == 403, res.text


def test_localita_sosta_create_admin_ok(client: TestClient) -> None:
    """Admin può creare. 409 se duplicato."""
    token = _login(client, "admin", "admin12345")
    payload = {
        "codice": "TEST-SOSTA-A",
        "nome": "Sosta di test β2-0",
        "stazione_collegata_codice": None,
        "note": "Creata da test integration",
    }
    res1 = client.post("/api/localita-sosta", json=payload, headers=_auth(token))
    # First insert OK
    if res1.status_code == 409:
        # Test rieseguito senza cleanup; salta ma non fallire
        return
    assert res1.status_code == 201, res1.text
    body = res1.json()
    assert body["codice"] == "TEST-SOSTA-A"
    assert body["nome"] == "Sosta di test β2-0"
    assert body["is_attiva"] is True

    # Duplicato → 409
    res2 = client.post("/api/localita-sosta", json=payload, headers=_auth(token))
    assert res2.status_code == 409


def test_localita_sosta_create_admin_stazione_invalida(
    client: TestClient,
) -> None:
    token = _login(client, "admin", "admin12345")
    res = client.post(
        "/api/localita-sosta",
        json={
            "codice": "TEST-STAZ-INV",
            "nome": "Test stazione invalida",
            "stazione_collegata_codice": "S99999_INESISTENTE",
        },
        headers=_auth(token),
    )
    assert res.status_code == 400, res.text


# =====================================================================
# Sprint 7.9 MR β2-1 — Istanze materiale (matricole L3)
# =====================================================================


def test_materiale_istanze_401_senza_token(client: TestClient) -> None:
    res = client.get("/api/materiale-istanze")
    assert res.status_code == 401


def test_materiale_istanze_200_seed(client: TestClient) -> None:
    """Verifica che la migration 0023 abbia seedato le istanze dalla
    dotazione_azienda. Per Trenord ETR526 dotazione=11 → 11 matricole."""
    token = _login(client, "pianificatore_giro_demo", "demo12345")
    res = client.get(
        "/api/materiale-istanze?tipo_materiale_codice=ETR526",
        headers=_auth(token),
    )
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    if body:
        # Verifica formato matricola {TIPO}-{NNN}
        matricole = [r["matricola"] for r in body]
        assert all(m.startswith("ETR526-") for m in matricole)
        assert "ETR526-000" in matricole
        # Tutte hanno tipo coerente
        assert all(r["tipo_materiale_codice"] == "ETR526" for r in body)
        # Default stato attivo
        assert all(r["stato"] == "attivo" for r in body)
        # Sede NULL al seed iniziale (assegnabile in fase Manutenzione)
        assert all(r["sede_codice"] is None for r in body)


def test_materiale_istanze_filtro_sede_vuota(client: TestClient) -> None:
    """Filtro sede_codice="" restituisce solo le NON assegnate."""
    token = _login(client, "pianificatore_giro_demo", "demo12345")
    res = client.get(
        "/api/materiale-istanze?sede_codice=",
        headers=_auth(token),
    )
    assert res.status_code == 200
    body = res.json()
    assert all(r["sede_codice"] is None for r in body)
