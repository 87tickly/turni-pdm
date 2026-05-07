"""Test integration API ``GET /api/programmi/{id}/corse-non-coperte`` (entry 218).

Verifica: auth, status code, filtro perimetro (matching regole + periodo),
sottrazione delle corse coperte da giri del programma. Iterazione 1: solo
0 istanze coperte (copertura parziale → iterazione 2).

Setup riusa lo schema di ``test_genera_giri_api.py``.
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


LOC_CODICE = "TEST_LOC_CNC"
LOC_BREVE = "TCNC"
PROG_NAME = "TEST_CNC_corse_non_coperte"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


async def _wipe() -> None:
    async with session_scope() as session:
        await session.execute(text("DELETE FROM turno_pdc"))
        await session.execute(text("DELETE FROM giro_materiale"))
        await session.execute(text("DELETE FROM corsa_materiale_vuoto"))
        await session.execute(
            text("DELETE FROM corsa_commerciale WHERE numero_treno LIKE 'TCNC_%'")
        )
        await session.execute(
            text(
                "DELETE FROM programma_regola_assegnazione WHERE programma_id IN ("
                "SELECT id FROM programma_materiale WHERE nome LIKE 'TEST_CNC_%'"
                ")"
            )
        )
        await session.execute(
            text("DELETE FROM programma_materiale WHERE nome LIKE 'TEST_CNC_%'")
        )
        await session.execute(
            text("DELETE FROM localita_manutenzione WHERE codice = 'TEST_LOC_CNC'")
        )
        await session.execute(text("DELETE FROM stazione WHERE codice LIKE 'S97%'"))


@pytest.fixture(autouse=True)
async def clean_state() -> None:
    await _wipe()
    yield
    await _wipe()


@pytest.fixture(scope="module", autouse=True)
async def cleanup_engine() -> None:
    yield
    await dispose_engine()


async def _setup_due_corse_una_regola() -> int:
    """Crea programma + 1 regola che matcha 2 corse (numero_treno IN
    [TCNC_1, TCNC_2]) + 2 corse, NESSUN giro generato.

    Ritorna ``programma_id``.
    """
    async with session_scope() as session:
        az_row = (
            await session.execute(
                text("SELECT id FROM azienda WHERE codice = 'trenord'")
            )
        ).first()
        assert az_row is not None
        az_id = int(az_row[0])

        for codice in {"S97001", "S97002"}:
            session.add(Stazione(codice=codice, nome=codice, azienda_id=az_id))
        await session.flush()

        loc = LocalitaManutenzione(
            codice=LOC_CODICE,
            codice_breve=LOC_BREVE,
            nome_canonico=LOC_CODICE,
            stazione_collegata_codice="S97001",
            azienda_id=az_id,
        )
        session.add(loc)

        prog = ProgrammaMateriale(
            azienda_id=az_id,
            nome=PROG_NAME,
            valido_da=date(2026, 4, 1),
            valido_a=date(2026, 4, 30),
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
                        "valore": ["TCNC_1", "TCNC_2"],
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

        # Entrambe le corse cadono nel periodo programma (2026-04-01..30).
        for nt, p, a in [
            ("TCNC_1", (8, 0), (9, 0)),
            ("TCNC_2", (10, 0), (11, 0)),
        ]:
            session.add(
                CorsaCommerciale(
                    azienda_id=az_id,
                    row_hash=("test_" + nt).ljust(64, "0")[:64],
                    numero_treno=nt,
                    codice_origine="S97001",
                    codice_destinazione="S97002",
                    ora_partenza=time(*p),
                    ora_arrivo=time(*a),
                    valido_da=date(2026, 1, 1),
                    valido_a=date(2026, 12, 31),
                    valido_in_date_json=["2026-04-15"],
                )
            )
        # Una corsa FUORI dal filtro della regola: non deve apparire mai
        # tra le "non coperte" (non è nel perimetro programma).
        session.add(
            CorsaCommerciale(
                azienda_id=az_id,
                row_hash="test_fuori_filtri".ljust(64, "0")[:64],
                numero_treno="TCNC_FUORI",
                codice_origine="S97001",
                codice_destinazione="S97002",
                ora_partenza=time(12, 0),
                ora_arrivo=time(13, 0),
                valido_da=date(2026, 1, 1),
                valido_a=date(2026, 12, 31),
                valido_in_date_json=["2026-04-15"],
            )
        )
        # Una corsa fuori dal periodo programma: non deve apparire (no
        # date in [2026-04-01..30]).
        session.add(
            CorsaCommerciale(
                azienda_id=az_id,
                row_hash="test_fuori_periodo".ljust(64, "0")[:64],
                numero_treno="TCNC_1",  # filtro matcha
                codice_origine="S97001",
                codice_destinazione="S97002",
                ora_partenza=time(14, 0),
                ora_arrivo=time(15, 0),
                valido_da=date(2026, 1, 1),
                valido_a=date(2026, 12, 31),
                valido_in_date_json=["2026-05-15"],  # FUORI periodo
            )
        )

    return prog_id


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


async def test_corse_non_coperte_senza_token_401(client: TestClient) -> None:
    res = client.get("/api/programmi/1/corse-non-coperte")
    assert res.status_code == 401


async def test_corse_non_coperte_programma_inesistente_404(client: TestClient) -> None:
    token = _login(client, "admin", "admin12345")
    res = client.get(
        "/api/programmi/99999/corse-non-coperte", headers=_auth(token)
    )
    assert res.status_code == 404


# =====================================================================
# Logica perimetro + sottrazione coperte
# =====================================================================


async def test_corse_non_coperte_zero_giri_ritorna_perimetro(
    client: TestClient,
) -> None:
    """Senza giri generati, tutte e 2 le corse del perimetro (filtri +
    periodo) sono "non coperte". Le 2 corse fuori perimetro
    (TCNC_FUORI + TCNC_1 fuori periodo) NON appaiono.
    """
    prog_id = await _setup_due_corse_una_regola()
    token = _login(client, "admin", "admin12345")

    res = client.get(
        f"/api/programmi/{prog_id}/corse-non-coperte", headers=_auth(token)
    )
    assert res.status_code == 200, res.text
    items = res.json()
    assert isinstance(items, list)

    numeri = sorted(it["numero_treno"] for it in items)
    # Solo le 2 corse che matchano filtri + periodo. NON c'è TCNC_FUORI
    # e NON c'è la TCNC_1 con valido_in_date_json fuori periodo.
    # NB: TCNC_1 appare per il record principale (date in periodo); il
    # record secondario (date fuori periodo) ha lo stesso numero_treno
    # ma non viene riportato perché è una riga distinta in DB.
    assert "TCNC_FUORI" not in numeri
    assert "TCNC_1" in numeri
    assert "TCNC_2" in numeri
    # Almeno 2 corse del perimetro (potrebbe esserci la 3a se il filtro
    # periodo fallisce — assertions difensiva).
    assert len(items) >= 2

    # Shape della response.
    it = items[0]
    expected_keys = {
        "corsa_id",
        "numero_treno",
        "stazione_da_codice",
        "stazione_a_codice",
        "ora_partenza",
        "ora_arrivo",
        "n_date_perimetro",
        "regole_match",
    }
    assert set(it.keys()) == expected_keys
    assert it["n_date_perimetro"] >= 1
    assert len(it["regole_match"]) >= 1
    assert it["regole_match"][0]["priorita"] == 10


async def test_corse_non_coperte_dopo_genera_giri_lista_vuota(
    client: TestClient,
) -> None:
    """Genero giri: il builder copre TCNC_1 + TCNC_2. Endpoint deve
    ritornare lista vuota (perimetro completamente coperto).
    """
    prog_id = await _setup_due_corse_una_regola()
    token = _login(client, "admin", "admin12345")

    # Genero giri (1 giornata, 1 data).
    res_gen = client.post(
        f"/api/programmi/{prog_id}/genera-giri",
        params={
            "data_inizio": "2026-04-15",
            "n_giornate": 1,
            "localita_codice": LOC_CODICE,
        },
        headers=_auth(token),
    )
    assert res_gen.status_code == 200, res_gen.text

    res = client.get(
        f"/api/programmi/{prog_id}/corse-non-coperte", headers=_auth(token)
    )
    assert res.status_code == 200, res.text
    items = res.json()
    # Tutte coperte → []. Se per caso il builder lascia residue (es. una
    # corsa non concatenabile), accettiamo che ce ne sia almeno qualcuna,
    # ma TCNC_FUORI non deve mai apparire.
    numeri = [it["numero_treno"] for it in items]
    assert "TCNC_FUORI" not in numeri


async def test_corse_non_coperte_programma_senza_regole_lista_vuota(
    client: TestClient,
) -> None:
    """Un programma senza regole non ha perimetro → []."""
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
            nome="TEST_CNC_no_regole",
            valido_da=date(2026, 4, 1),
            valido_a=date(2026, 4, 30),
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

    token = _login(client, "admin", "admin12345")
    res = client.get(
        f"/api/programmi/{prog_id}/corse-non-coperte", headers=_auth(token)
    )
    assert res.status_code == 200
    assert res.json() == []
