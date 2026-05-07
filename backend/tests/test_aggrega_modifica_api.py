"""Test integration API
``POST /api/programmi/{id}/giri/aggrega-modifica`` (Sprint 8.0 MR-5,
entry 228).

Iterazione 1: solo auth + 404 + 400 (programma in bozza, payload
inconsistente, gruppo inesistente). Test happy-path "le regole sono
aggiornate e i giri vengono rigenerati per le sedi toccate" richiede
setup esteso (programma con regole + composizione + DB seedato di
corse) → iterazione 2.
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
                "DELETE FROM programma_materiale "
                "WHERE nome LIKE 'TEST_AGGMOD_%'"
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
    mat_old: str = "ETR526",
    loc_old: str = "IMPMAN_MILANO_FIORENZA",
    mat_new: str | None = None,
    loc_new: str | None = None,
) -> dict[str, str | bool | None]:
    return {
        "materiale_tipo_codice_old": mat_old,
        "localita_codice_old": loc_old,
        "materiale_tipo_codice_new": mat_new,
        "localita_codice_new": loc_new,
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
# Auth + 404
# =====================================================================


async def test_aggrega_modifica_senza_token_401(client: TestClient) -> None:
    res = client.post(
        "/api/programmi/1/giri/aggrega-modifica",
        json=_payload(mat_new="ETR421"),
    )
    assert res.status_code == 401


async def test_aggrega_modifica_programma_inesistente_404(
    client: TestClient,
) -> None:
    token = _login(client, "admin", "admin12345")
    res = client.post(
        "/api/programmi/99999/giri/aggrega-modifica",
        headers=_auth(token),
        json=_payload(mat_new="ETR421"),
    )
    assert res.status_code == 404


# =====================================================================
# Validazioni 400
# =====================================================================


async def test_aggrega_modifica_programma_in_bozza_400(
    client: TestClient,
) -> None:
    """Programma non attivo → 400."""
    prog_id = await _crea_programma(nome="TEST_AGGMOD_bozza", stato="bozza")
    token = _login(client, "admin", "admin12345")
    res = client.post(
        f"/api/programmi/{prog_id}/giri/aggrega-modifica",
        headers=_auth(token),
        json=_payload(mat_new="ETR421"),
    )
    assert res.status_code == 400
    assert "attivo" in res.json()["detail"].lower()


async def test_aggrega_modifica_nessun_cambio_400(
    client: TestClient,
) -> None:
    """Nessuna modifica richiesta (new None o uguale a old) → 400."""
    prog_id = await _crea_programma(
        nome="TEST_AGGMOD_no_cambio", stato="attivo"
    )
    token = _login(client, "admin", "admin12345")

    # Caso 1: entrambi i _new sono None.
    res = client.post(
        f"/api/programmi/{prog_id}/giri/aggrega-modifica",
        headers=_auth(token),
        json=_payload(),
    )
    assert res.status_code == 400
    assert "modifica" in res.json()["detail"].lower()

    # Caso 2: i _new sono uguali ai _old.
    res = client.post(
        f"/api/programmi/{prog_id}/giri/aggrega-modifica",
        headers=_auth(token),
        json=_payload(
            mat_old="ETR526",
            loc_old="IMPMAN_MILANO_FIORENZA",
            mat_new="ETR526",
            loc_new="IMPMAN_MILANO_FIORENZA",
        ),
    )
    assert res.status_code == 400


async def test_aggrega_modifica_gruppo_inesistente_400(
    client: TestClient,
) -> None:
    """Programma senza regole / gruppo non match → 400 'nessuna regola'."""
    prog_id = await _crea_programma(
        nome="TEST_AGGMOD_no_regole", stato="attivo"
    )
    token = _login(client, "admin", "admin12345")
    res = client.post(
        f"/api/programmi/{prog_id}/giri/aggrega-modifica",
        headers=_auth(token),
        json=_payload(mat_new="ETR421"),
    )
    assert res.status_code == 400
    assert "nessuna regola" in res.json()["detail"].lower()


async def test_aggrega_modifica_payload_invalido_422(
    client: TestClient,
) -> None:
    """Payload con campi mancanti → 422 (Pydantic)."""
    prog_id = await _crea_programma(
        nome="TEST_AGGMOD_payload_invalido", stato="attivo"
    )
    token = _login(client, "admin", "admin12345")

    # mat_old mancante.
    res = client.post(
        f"/api/programmi/{prog_id}/giri/aggrega-modifica",
        headers=_auth(token),
        json={
            "localita_codice_old": "IMPMAN_MILANO_FIORENZA",
            "materiale_tipo_codice_new": "ETR421",
        },
    )
    assert res.status_code == 422

    # mat_old vuoto (min_length=1).
    res = client.post(
        f"/api/programmi/{prog_id}/giri/aggrega-modifica",
        headers=_auth(token),
        json={
            "materiale_tipo_codice_old": "",
            "localita_codice_old": "IMPMAN_MILANO_FIORENZA",
            "materiale_tipo_codice_new": "ETR421",
        },
    )
    assert res.status_code == 422
