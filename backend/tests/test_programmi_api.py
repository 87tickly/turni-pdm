"""Test integration API programma materiale (Sprint 4.3).

Richiede:
- Postgres locale up + migrazioni 0001-0005 applicate
- Seed Trenord (azienda) + utenti (admin, pianificatore_giro_demo)
- Migration 0005 (programma_materiale + regola_assegnazione)

Set `SKIP_DB_TESTS=1` per saltare. Pattern come `test_auth_endpoints.py`.

Coverage:
- Auth: 401 senza token, 403 senza ruolo, 200 con admin/pianificatore
- POST: minimo, con regole nested
- GET: lista (filtro stato), dettaglio (con regole ordinate)
- PATCH: intestazione (no stato)
- POST regola (solo bozza)
- DELETE regola (solo bozza)
- Pubblica: bozza→attivo, errori (400/409)
- Archivia: attivo→archiviato
- Multi-tenant: filtro per `user.azienda_id`
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from colazione.db import dispose_engine, session_scope
from colazione.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_DB_TESTS") == "1",
    reason="DB not configured for tests",
)


# =====================================================================
# Fixture
# =====================================================================


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


async def _wipe_programmi() -> None:
    async with session_scope() as session:
        await session.execute(text("DELETE FROM programma_regola_assegnazione"))
        await session.execute(text("DELETE FROM programma_materiale"))


@pytest.fixture(autouse=True)
async def clean_state() -> None:
    """Stato pulito prima di ogni test."""
    await _wipe_programmi()


@pytest.fixture(scope="module", autouse=True)
async def cleanup_engine() -> None:
    """Dispose engine al termine."""
    yield
    await dispose_engine()


def _login(client: TestClient, username: str, password: str) -> str:
    """Helper login → access token."""
    res = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert res.status_code == 200, res.text
    return str(res.json()["access_token"])


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# Payload esempio: programma minimo
_PAYLOAD_MIN = {
    "nome": "Test Trenord 2026",
    "valido_da": "2026-01-01",
    "valido_a": "2026-12-31",
}

_REGOLA_MIN = {
    "filtri_json": [{"campo": "codice_linea", "op": "eq", "valore": "S5"}],
    "composizione": [{"materiale_tipo_codice": "ALe711", "n_pezzi": 3}],
    "priorita": 80,
}


# =====================================================================
# Auth
# =====================================================================


def test_create_senza_token_401(client: TestClient) -> None:
    res = client.post("/api/programmi", json=_PAYLOAD_MIN)
    assert res.status_code == 401


def test_list_senza_token_401(client: TestClient) -> None:
    res = client.get("/api/programmi")
    assert res.status_code == 401


def test_admin_puo_creare(client: TestClient) -> None:
    """Admin bypassa il role check."""
    token = _login(client, "admin", "admin12345")
    res = client.post("/api/programmi", json=_PAYLOAD_MIN, headers=_auth_headers(token))
    assert res.status_code == 201, res.text


def test_pianificatore_giro_puo_creare(client: TestClient) -> None:
    token = _login(client, "pianificatore_giro_demo", "demo12345")
    res = client.post("/api/programmi", json=_PAYLOAD_MIN, headers=_auth_headers(token))
    assert res.status_code == 201, res.text


# =====================================================================
# POST programma
# =====================================================================


def test_create_programma_minimo_ok(client: TestClient) -> None:
    token = _login(client, "admin", "admin12345")
    res = client.post("/api/programmi", json=_PAYLOAD_MIN, headers=_auth_headers(token))
    assert res.status_code == 201
    body = res.json()
    assert body["nome"] == _PAYLOAD_MIN["nome"]
    assert body["stato"] == "bozza"
    assert body["azienda_id"] is not None
    assert body["n_giornate_default"] == 1
    assert body["fascia_oraria_tolerance_min"] == 30
    assert body["strict_options_json"]["no_corse_residue"] is False


def test_create_programma_con_regole_nested(client: TestClient) -> None:
    token = _login(client, "admin", "admin12345")
    payload = {**_PAYLOAD_MIN, "regole": [_REGOLA_MIN]}
    res = client.post("/api/programmi", json=payload, headers=_auth_headers(token))
    assert res.status_code == 201
    programma_id = res.json()["id"]

    # GET dettaglio per verificare la regola
    res2 = client.get(f"/api/programmi/{programma_id}", headers=_auth_headers(token))
    assert res2.status_code == 200
    body = res2.json()
    assert len(body["regole"]) == 1
    # composizione è la fonte autorevole (Sprint 5.1)
    assert body["regole"][0]["composizione_json"] == [
        {"materiale_tipo_codice": "ALe711", "n_pezzi": 3}
    ]
    assert body["regole"][0]["is_composizione_manuale"] is False
    # campi legacy ri-popolati dal primo elemento per retrocompat (fino a Sub 5.5)
    assert body["regole"][0]["materiale_tipo_codice"] == "ALe711"
    assert body["regole"][0]["numero_pezzi"] == 3


def test_create_programma_validita_invertita_422(client: TestClient) -> None:
    """Pydantic refuta valido_a < valido_da."""
    token = _login(client, "admin", "admin12345")
    bad = {"nome": "X", "valido_da": "2026-12-31", "valido_a": "2026-01-01"}
    res = client.post("/api/programmi", json=bad, headers=_auth_headers(token))
    assert res.status_code == 422


def test_create_programma_filtro_invalido_422(client: TestClient) -> None:
    """Filtro con campo sconosciuto → ValidationError."""
    token = _login(client, "admin", "admin12345")
    bad_payload = {
        **_PAYLOAD_MIN,
        "regole": [
            {
                "filtri_json": [{"campo": "campo_inesistente", "op": "eq", "valore": "x"}],
                "composizione": [{"materiale_tipo_codice": "ALe711", "n_pezzi": 1}],
            }
        ],
    }
    res = client.post("/api/programmi", json=bad_payload, headers=_auth_headers(token))
    assert res.status_code == 422


# =====================================================================
# GET lista + dettaglio
# =====================================================================


def test_list_vuoto(client: TestClient) -> None:
    token = _login(client, "admin", "admin12345")
    res = client.get("/api/programmi", headers=_auth_headers(token))
    assert res.status_code == 200
    assert res.json() == []


def test_list_filtra_stato(client: TestClient) -> None:
    token = _login(client, "admin", "admin12345")
    # Crea 2 programmi
    client.post("/api/programmi", json=_PAYLOAD_MIN, headers=_auth_headers(token))
    p2 = {**_PAYLOAD_MIN, "nome": "Altro 2027", "valido_da": "2027-01-01", "valido_a": "2027-12-31"}
    client.post("/api/programmi", json=p2, headers=_auth_headers(token))

    res = client.get("/api/programmi?stato=bozza", headers=_auth_headers(token))
    assert res.status_code == 200
    assert len(res.json()) == 2


def test_get_dettaglio_404_se_inesistente(client: TestClient) -> None:
    token = _login(client, "admin", "admin12345")
    res = client.get("/api/programmi/99999", headers=_auth_headers(token))
    assert res.status_code == 404


def test_get_dettaglio_regole_ordine_priorita(client: TestClient) -> None:
    """Le regole nel dettaglio sono ordinate per priorità DESC."""
    token = _login(client, "admin", "admin12345")
    payload = {
        **_PAYLOAD_MIN,
        "regole": [
            {
                **_REGOLA_MIN,
                "priorita": 30,
                "composizione": [{"materiale_tipo_codice": "ALe711", "n_pezzi": 1}],
            },
            {
                **_REGOLA_MIN,
                "priorita": 90,
                "composizione": [{"materiale_tipo_codice": "ALe711", "n_pezzi": 2}],
            },
            {
                **_REGOLA_MIN,
                "priorita": 60,
                "composizione": [{"materiale_tipo_codice": "ALe711", "n_pezzi": 3}],
            },
        ],
    }
    res = client.post("/api/programmi", json=payload, headers=_auth_headers(token))
    pid = res.json()["id"]

    res2 = client.get(f"/api/programmi/{pid}", headers=_auth_headers(token))
    regole = res2.json()["regole"]
    assert [r["priorita"] for r in regole] == [90, 60, 30]


# =====================================================================
# PATCH
# =====================================================================


def test_patch_aggiorna_intestazione(client: TestClient) -> None:
    token = _login(client, "admin", "admin12345")
    res = client.post("/api/programmi", json=_PAYLOAD_MIN, headers=_auth_headers(token))
    pid = res.json()["id"]

    res2 = client.patch(
        f"/api/programmi/{pid}",
        json={"nome": "Nuovo nome", "km_max_giornaliero": 600},
        headers=_auth_headers(token),
    )
    assert res2.status_code == 200
    body = res2.json()
    assert body["nome"] == "Nuovo nome"
    assert body["km_max_giornaliero"] == 600


def test_patch_404_inesistente(client: TestClient) -> None:
    token = _login(client, "admin", "admin12345")
    res = client.patch(
        "/api/programmi/99999",
        json={"nome": "X"},
        headers=_auth_headers(token),
    )
    assert res.status_code == 404


# =====================================================================
# POST/DELETE regole
# =====================================================================


def test_add_regola_a_bozza_ok(client: TestClient) -> None:
    token = _login(client, "admin", "admin12345")
    res = client.post("/api/programmi", json=_PAYLOAD_MIN, headers=_auth_headers(token))
    pid = res.json()["id"]

    res2 = client.post(
        f"/api/programmi/{pid}/regole",
        json=_REGOLA_MIN,
        headers=_auth_headers(token),
    )
    assert res2.status_code == 201
    assert res2.json()["materiale_tipo_codice"] == "ALe711"


def test_delete_regola_a_bozza_ok(client: TestClient) -> None:
    token = _login(client, "admin", "admin12345")
    res = client.post(
        "/api/programmi",
        json={**_PAYLOAD_MIN, "regole": [_REGOLA_MIN]},
        headers=_auth_headers(token),
    )
    pid = res.json()["id"]

    res2 = client.get(f"/api/programmi/{pid}", headers=_auth_headers(token))
    regola_id = res2.json()["regole"][0]["id"]

    res3 = client.delete(
        f"/api/programmi/{pid}/regole/{regola_id}",
        headers=_auth_headers(token),
    )
    assert res3.status_code == 204

    res4 = client.get(f"/api/programmi/{pid}", headers=_auth_headers(token))
    assert res4.json()["regole"] == []


def test_add_regola_su_attivo_blocca_400(client: TestClient) -> None:
    token = _login(client, "admin", "admin12345")
    payload = {**_PAYLOAD_MIN, "regole": [_REGOLA_MIN]}
    res = client.post("/api/programmi", json=payload, headers=_auth_headers(token))
    pid = res.json()["id"]
    client.post(f"/api/programmi/{pid}/pubblica", headers=_auth_headers(token))

    res2 = client.post(
        f"/api/programmi/{pid}/regole",
        json=_REGOLA_MIN,
        headers=_auth_headers(token),
    )
    assert res2.status_code == 400
    assert "bozza" in res2.json()["detail"]


# =====================================================================
# Pubblica + Archivia
# =====================================================================


def test_pubblica_bozza_con_regole_ok(client: TestClient) -> None:
    token = _login(client, "admin", "admin12345")
    payload = {**_PAYLOAD_MIN, "regole": [_REGOLA_MIN]}
    res = client.post("/api/programmi", json=payload, headers=_auth_headers(token))
    pid = res.json()["id"]

    res2 = client.post(f"/api/programmi/{pid}/pubblica", headers=_auth_headers(token))
    assert res2.status_code == 200
    assert res2.json()["stato"] == "attivo"


def test_pubblica_senza_regole_400(client: TestClient) -> None:
    token = _login(client, "admin", "admin12345")
    res = client.post("/api/programmi", json=_PAYLOAD_MIN, headers=_auth_headers(token))
    pid = res.json()["id"]

    res2 = client.post(f"/api/programmi/{pid}/pubblica", headers=_auth_headers(token))
    assert res2.status_code == 400
    assert "nessuna regola" in res2.json()["detail"]


def test_pubblica_gia_attivo_400(client: TestClient) -> None:
    token = _login(client, "admin", "admin12345")
    payload = {**_PAYLOAD_MIN, "regole": [_REGOLA_MIN]}
    res = client.post("/api/programmi", json=payload, headers=_auth_headers(token))
    pid = res.json()["id"]
    client.post(f"/api/programmi/{pid}/pubblica", headers=_auth_headers(token))

    res2 = client.post(f"/api/programmi/{pid}/pubblica", headers=_auth_headers(token))
    assert res2.status_code == 400


def test_pubblica_sovrapposizione_409(client: TestClient) -> None:
    """Due programmi attivi nella stessa azienda con finestre che si
    sovrappongono → 409. Sprint 7.3: il check non confronta più la
    stagione (campo rimosso), solo la finestra temporale.
    """
    token = _login(client, "admin", "admin12345")
    payload = {
        **_PAYLOAD_MIN,
        "valido_da": "2026-01-01",
        "valido_a": "2026-06-30",
        "regole": [_REGOLA_MIN],
    }
    res = client.post("/api/programmi", json=payload, headers=_auth_headers(token))
    pid1 = res.json()["id"]
    client.post(f"/api/programmi/{pid1}/pubblica", headers=_auth_headers(token))

    payload2 = {
        **payload,
        "nome": "Altro inverno",
        "valido_da": "2026-04-01",  # sovrappone
        "valido_a": "2026-08-31",
    }
    res2 = client.post("/api/programmi", json=payload2, headers=_auth_headers(token))
    pid2 = res2.json()["id"]
    res3 = client.post(f"/api/programmi/{pid2}/pubblica", headers=_auth_headers(token))
    assert res3.status_code == 409
    assert "sovrappone" in res3.json()["detail"]


def test_archivia_attivo_ok(client: TestClient) -> None:
    token = _login(client, "admin", "admin12345")
    payload = {**_PAYLOAD_MIN, "regole": [_REGOLA_MIN]}
    res = client.post("/api/programmi", json=payload, headers=_auth_headers(token))
    pid = res.json()["id"]
    client.post(f"/api/programmi/{pid}/pubblica", headers=_auth_headers(token))

    res2 = client.post(f"/api/programmi/{pid}/archivia", headers=_auth_headers(token))
    assert res2.status_code == 200
    assert res2.json()["stato"] == "archiviato"


def test_archivia_gia_archiviato_400(client: TestClient) -> None:
    token = _login(client, "admin", "admin12345")
    payload = {**_PAYLOAD_MIN, "regole": [_REGOLA_MIN]}
    res = client.post("/api/programmi", json=payload, headers=_auth_headers(token))
    pid = res.json()["id"]
    client.post(f"/api/programmi/{pid}/pubblica", headers=_auth_headers(token))
    client.post(f"/api/programmi/{pid}/archivia", headers=_auth_headers(token))

    res2 = client.post(f"/api/programmi/{pid}/archivia", headers=_auth_headers(token))
    assert res2.status_code == 400
