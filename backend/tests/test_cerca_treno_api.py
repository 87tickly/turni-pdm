"""Test integration API ``GET /api/programmi/{id}/cerca-treno`` (entry 214).

Verifica auth, status code, partial match case-insensitive, raggruppamento
per ``(tipo, corsa_id)``, presenza di ``blocchi[].variante_etichetta``.
Setup riusa lo schema di ``test_genera_giri_api.py`` (azienda Trenord seed
+ stazioni S99NNN + località TEST_LOC_API).
"""

from __future__ import annotations

import os
from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from colazione.db import dispose_engine, session_scope
from colazione.main import app
from colazione.models.anagrafica import LocalitaManutenzione, Stazione
from colazione.models.corse import CorsaCommerciale
from colazione.models.programmi import (
    ProgrammaMateriale,
    ProgrammaRegolaAssegnazione,
)

pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_DB_TESTS") == "1",
    reason="DB not configured for tests",
)


LOC_CODICE = "TEST_LOC_CRC"
LOC_BREVE = "TCRC"
PROG_NAME = "TEST_CRC_cerca_treno"


# =====================================================================
# Setup helpers (clone snello di test_genera_giri_api.py)
# =====================================================================


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


async def _wipe() -> None:
    async with session_scope() as session:
        await session.execute(text("DELETE FROM turno_pdc"))
        await session.execute(text("DELETE FROM giro_materiale"))
        await session.execute(text("DELETE FROM corsa_materiale_vuoto"))
        await session.execute(
            text("DELETE FROM corsa_commerciale WHERE numero_treno LIKE 'TCRC_%'")
        )
        await session.execute(
            text(
                "DELETE FROM programma_regola_assegnazione WHERE programma_id IN ("
                "SELECT id FROM programma_materiale WHERE nome LIKE 'TEST_CRC_%'"
                ")"
            )
        )
        await session.execute(
            text("DELETE FROM programma_materiale WHERE nome LIKE 'TEST_CRC_%'")
        )
        await session.execute(
            text("DELETE FROM localita_manutenzione WHERE codice LIKE 'TEST_LOC_CRC'")
        )
        await session.execute(text("DELETE FROM stazione WHERE codice LIKE 'S98%'"))


@pytest.fixture(autouse=True)
async def clean_state() -> None:
    await _wipe()
    yield
    await _wipe()


@pytest.fixture(scope="module", autouse=True)
async def cleanup_engine() -> None:
    yield
    await dispose_engine()


async def _setup_db_e_genera() -> tuple[int, str]:
    """Crea programma con 2 corse + esegue genera-giri.

    Ritorna ``(programma_id, token_admin)``.
    """
    async with session_scope() as session:
        az_row = (
            await session.execute(
                text("SELECT id FROM azienda WHERE codice = 'trenord'")
            )
        ).first()
        assert az_row is not None
        az_id = int(az_row[0])

        for codice in {"S98001", "S98002"}:
            session.add(Stazione(codice=codice, nome=codice, azienda_id=az_id))
        await session.flush()

        loc = LocalitaManutenzione(
            codice=LOC_CODICE,
            codice_breve=LOC_BREVE,
            nome_canonico=LOC_CODICE,
            stazione_collegata_codice="S98001",
            azienda_id=az_id,
        )
        session.add(loc)

        prog = ProgrammaMateriale(
            azienda_id=az_id,
            nome=PROG_NAME,
            valido_da=date(2026, 1, 1),
            valido_a=date(2026, 12, 31),
            stato="attivo",
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
        prog_id = int(prog.id)

        session.add(
            ProgrammaRegolaAssegnazione(
                programma_id=prog_id,
                filtri_json=[
                    {
                        "campo": "numero_treno",
                        "op": "in",
                        "valore": ["TCRC_28335", "TCRC_28336"],
                    }
                ],
                composizione_json=[
                    {"materiale_tipo_codice": "ALe711", "n_pezzi": 3}
                ],
                materiale_tipo_codice="ALe711",
                numero_pezzi=3,
                priorita=10,
            )
        )

        for nt, o, d, p, a in [
            ("TCRC_28335", "S98001", "S98002", (8, 0), (9, 0)),
            ("TCRC_28336", "S98002", "S98001", (10, 0), (11, 0)),
        ]:
            session.add(
                CorsaCommerciale(
                    azienda_id=az_id,
                    row_hash=("test_" + nt).ljust(64, "0")[:64],
                    numero_treno=nt,
                    codice_origine=o,
                    codice_destinazione=d,
                    ora_partenza=time(*p),
                    ora_arrivo=time(*a),
                    valido_da=date(2026, 1, 1),
                    valido_a=date(2026, 12, 31),
                    valido_in_date_json=["2026-04-27"],
                )
            )

    return prog_id, ""


def _login(client: TestClient, username: str, password: str) -> str:
    res = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert res.status_code == 200
    return str(res.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


_GEN_PARAMS: dict[str, str | int] = {
    "data_inizio": "2026-04-27",
    "n_giornate": 1,
    "localita_codice": LOC_CODICE,
}


async def _genera(client: TestClient, prog_id: int, token: str) -> None:
    res = client.post(
        f"/api/programmi/{prog_id}/genera-giri",
        params=_GEN_PARAMS,
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text


# =====================================================================
# Auth
# =====================================================================


async def test_cerca_treno_senza_token_401(client: TestClient) -> None:
    res = client.get("/api/programmi/1/cerca-treno", params={"q": "28"})
    assert res.status_code == 401


async def test_cerca_treno_programma_inesistente_404(client: TestClient) -> None:
    token = _login(client, "admin", "admin12345")
    res = client.get(
        "/api/programmi/99999/cerca-treno",
        params={"q": "28"},
        headers=_auth(token),
    )
    assert res.status_code == 404


# =====================================================================
# Happy path
# =====================================================================


async def test_cerca_treno_partial_match_trova_corse(client: TestClient) -> None:
    """``q=TCRC_2833`` deve matchare TCRC_28335 e TCRC_28336."""
    prog_id, _ = await _setup_db_e_genera()
    token = _login(client, "admin", "admin12345")
    await _genera(client, prog_id, token)

    res = client.get(
        f"/api/programmi/{prog_id}/cerca-treno",
        params={"q": "TCRC_2833"},
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    items = res.json()
    assert isinstance(items, list)
    # 2 corse distinte attese
    numeri = sorted(it["numero_treno"] for it in items)
    assert numeri == ["TCRC_28335", "TCRC_28336"]
    # Tutte commerciali
    assert {it["tipo"] for it in items} == {"commerciale"}
    # Almeno 1 blocco per corsa
    for it in items:
        assert len(it["blocchi"]) >= 1
        b0 = it["blocchi"][0]
        assert b0["giro_id"] > 0
        assert b0["numero_turno"]
        assert b0["giornata"] >= 1
        assert b0["seq"] >= 1


async def test_cerca_treno_case_insensitive(client: TestClient) -> None:
    """``ilike`` → match case-insensitive su ``numero_treno``."""
    prog_id, _ = await _setup_db_e_genera()
    token = _login(client, "admin", "admin12345")
    await _genera(client, prog_id, token)

    res = client.get(
        f"/api/programmi/{prog_id}/cerca-treno",
        params={"q": "tcrc_28335"},  # lowercase
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    items = res.json()
    assert len(items) == 1
    assert items[0]["numero_treno"] == "TCRC_28335"


async def test_cerca_treno_no_match_lista_vuota(client: TestClient) -> None:
    prog_id, _ = await _setup_db_e_genera()
    token = _login(client, "admin", "admin12345")
    await _genera(client, prog_id, token)

    res = client.get(
        f"/api/programmi/{prog_id}/cerca-treno",
        params={"q": "INESISTENTE"},
        headers=_auth(token),
    )
    assert res.status_code == 200
    assert res.json() == []


async def test_cerca_treno_response_shape(client: TestClient) -> None:
    """Verifica struttura completa della response per UI frontend."""
    prog_id, _ = await _setup_db_e_genera()
    token = _login(client, "admin", "admin12345")
    await _genera(client, prog_id, token)

    res = client.get(
        f"/api/programmi/{prog_id}/cerca-treno",
        params={"q": "TCRC_28335"},
        headers=_auth(token),
    )
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    it = items[0]
    expected_keys = {
        "corsa_id",
        "tipo",
        "numero_treno",
        "stazione_da_codice",
        "stazione_a_codice",
        "ora_partenza",
        "ora_arrivo",
        "blocchi",
    }
    assert set(it.keys()) == expected_keys
    assert it["stazione_da_codice"] == "S98001"
    assert it["stazione_a_codice"] == "S98002"
    blocco_keys = {
        "blocco_id",
        "giro_id",
        "numero_turno",
        "giornata",
        "variante_index",
        "variante_etichetta",
        "seq",
    }
    assert set(it["blocchi"][0].keys()) == blocco_keys
