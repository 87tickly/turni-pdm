"""Test integration API wizard "materiale + linee → giri"
(Sprint 8.0 MR-C, entry 229).

- ``GET /api/programmi/{id}/linee-distinct``: lista linee del PdE.
- ``POST /api/programmi/{id}/giri/wizard-da-linee``: crea regole +
  rigenera giri.

Iterazione 1: solo auth + 404 + 400 (programma in bozza, payload
inconsistente). Test happy-path "le regole vengono create + i giri
sono rigenerati con tutte le corse delle linee" richiede setup
esteso (PdE seedato + dotazione + sede manutenzione reale) →
iterazione 2.
"""

from __future__ import annotations

import os
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from colazione.db import dispose_engine, session_scope
from colazione.main import app
from colazione.models.programmi import ProgrammaMateriale

pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_DB_TESTS") == "1",
    reason="DB not configured for tests",
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


async def _wipe() -> None:
    async with session_scope() as session:
        await session.execute(text("DELETE FROM turno_pdc"))
        await session.execute(text("DELETE FROM giro_materiale"))
        await session.execute(text("DELETE FROM corsa_materiale_vuoto"))
        await session.execute(
            text(
                "DELETE FROM programma_regola_assegnazione "
                "WHERE programma_id IN ("
                "  SELECT id FROM programma_materiale "
                "  WHERE nome LIKE 'TEST_WZL_%'"
                ")"
            )
        )
        await session.execute(
            text(
                "DELETE FROM programma_materiale "
                "WHERE nome LIKE 'TEST_WZL_%'"
            )
        )


@pytest.fixture(autouse=True)
async def clean_state() -> None:
    await _wipe()
    yield
    await _wipe()


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
    materiale: str = "ETR522",
    localita: str = "IMPMAN_MILANO_FIORENZA",
    linee: list[str] | None = None,
) -> dict[str, object]:
    return {
        "materiale_tipo_codice": materiale,
        "localita_codice": localita,
        "linee": linee if linee is not None else ["S5", "S9"],
        "confirm_delete_pdc": False,
    }


async def _crea_programma(
    *, nome: str, stato: str = "attivo"
) -> int:
    async with session_scope() as session:
        az_row = (
            await session.execute(
                text("SELECT id FROM azienda WHERE codice = 'trenord'")
            )
        ).first()
        assert az_row is not None
        az_id = int(az_row[0])
        prog = ProgrammaMateriale(
            azienda_id=az_id,
            nome=nome,
            valido_da=date(2026, 4, 1),
            valido_a=date(2026, 4, 30),
            stato=stato,
            n_giornate_default=5,
            fascia_oraria_tolerance_min=30,
            strict_options_json={
                "no_corse_residue": False,
                "no_overcapacity": False,
                "no_aggancio_non_validato": False,
                "no_orphan_blocks": False,
                "no_giro_appeso": False,
                "no_km_eccesso": False,
            },
        )
        session.add(prog)
        await session.flush()
        return int(prog.id)


# =====================================================================
# GET linee-distinct: auth + 404
# =====================================================================


async def test_linee_distinct_senza_token_401(client: TestClient) -> None:
    res = client.get("/api/programmi/1/linee-distinct")
    assert res.status_code == 401


async def test_linee_distinct_programma_inesistente_404(
    client: TestClient,
) -> None:
    token = _login(client, "admin", "admin12345")
    res = client.get(
        "/api/programmi/99999/linee-distinct", headers=_auth(token)
    )
    assert res.status_code == 404


async def test_linee_distinct_programma_vuoto_lista_corretta(
    client: TestClient,
) -> None:
    """Programma valido: lista è una list[{codice_linea, n_corse}].
    Può essere vuota (se il PdE non ha corse nel periodo) o piena.
    """
    prog_id = await _crea_programma(
        nome="TEST_WZL_linee_vuoto", stato="attivo"
    )
    token = _login(client, "admin", "admin12345")
    res = client.get(
        f"/api/programmi/{prog_id}/linee-distinct", headers=_auth(token)
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert isinstance(body, list)
    for item in body:
        assert "codice_linea" in item
        assert "n_corse" in item
        assert isinstance(item["codice_linea"], str)
        assert isinstance(item["n_corse"], int)
        assert item["n_corse"] >= 0


# =====================================================================
# POST wizard-da-linee: auth + 404 + 400 + 422
# =====================================================================


async def test_wizard_senza_token_401(client: TestClient) -> None:
    res = client.post(
        "/api/programmi/1/giri/wizard-da-linee",
        json=_payload(),
    )
    assert res.status_code == 401


async def test_wizard_programma_inesistente_404(
    client: TestClient,
) -> None:
    token = _login(client, "admin", "admin12345")
    res = client.post(
        "/api/programmi/99999/giri/wizard-da-linee",
        headers=_auth(token),
        json=_payload(),
    )
    assert res.status_code == 404


async def test_wizard_programma_in_bozza_400(client: TestClient) -> None:
    prog_id = await _crea_programma(
        nome="TEST_WZL_bozza", stato="bozza"
    )
    token = _login(client, "admin", "admin12345")
    res = client.post(
        f"/api/programmi/{prog_id}/giri/wizard-da-linee",
        headers=_auth(token),
        json=_payload(),
    )
    assert res.status_code == 400
    assert "attivo" in res.json()["detail"].lower()


async def test_wizard_lista_linee_vuota_dopo_normalizzazione_400(
    client: TestClient,
) -> None:
    """Linee = [' ', ''] → tutte filtrate → 400."""
    prog_id = await _crea_programma(
        nome="TEST_WZL_linee_vuote", stato="attivo"
    )
    token = _login(client, "admin", "admin12345")
    res = client.post(
        f"/api/programmi/{prog_id}/giri/wizard-da-linee",
        headers=_auth(token),
        json=_payload(linee=["   ", ""]),
    )
    # Pydantic min_length=1 sulla lista non blocca (ha 2 elementi),
    # ma la normalizzazione li filtra → 400 dal nostro check.
    assert res.status_code == 400
    assert "linee" in res.json()["detail"].lower()


async def test_wizard_payload_invalido_422(client: TestClient) -> None:
    """Payload con campi mancanti → 422 (Pydantic)."""
    prog_id = await _crea_programma(
        nome="TEST_WZL_payload_invalido", stato="attivo"
    )
    token = _login(client, "admin", "admin12345")

    # materiale_tipo_codice mancante.
    res = client.post(
        f"/api/programmi/{prog_id}/giri/wizard-da-linee",
        headers=_auth(token),
        json={
            "localita_codice": "IMPMAN_MILANO_FIORENZA",
            "linee": ["S5"],
        },
    )
    assert res.status_code == 422

    # linee = [] (Pydantic min_length=1).
    res = client.post(
        f"/api/programmi/{prog_id}/giri/wizard-da-linee",
        headers=_auth(token),
        json=_payload(linee=[]),
    )
    assert res.status_code == 422

    # materiale stringa vuota.
    res = client.post(
        f"/api/programmi/{prog_id}/giri/wizard-da-linee",
        headers=_auth(token),
        json=_payload(materiale=""),
    )
    assert res.status_code == 422
