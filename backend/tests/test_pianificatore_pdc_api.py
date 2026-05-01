"""Test integration API Sprint 7.3 MR 1 — `GET /api/pianificatore-pdc/overview`.

Verifica auth (401/403), shape response, KPI con DB vuoto e DB popolato,
calcolo violazioni hard (prestazione standard / notturno / condotta).

Setup minimo: azienda Trenord seed + stazione + località + programma
materiale + N giri/turni inseriti via SQLAlchemy diretto.
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
from colazione.models.giri import GiroMateriale
from colazione.models.programmi import ProgrammaMateriale
from colazione.models.turni_pdc import TurnoPdc, TurnoPdcGiornata

pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_DB_TESTS") == "1",
    reason="DB not configured for tests",
)


LOC_CODICE = "TEST_LOC_PDC_OV"
LOC_BREVE = "TPDC"
PROG_NAME = "TEST_PROG_PDC_OV"
TURNO_PREFIX = "TEST_PDC_OV_"


# =====================================================================
# Setup
# =====================================================================


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


async def _wipe() -> None:
    """Wipe FK-safe.

    Cascade order:
    - turno_pdc.codice LIKE 'TEST_PDC_OV_%' (CASCADE → giornate)
    - programma_materiale.nome LIKE 'TEST_%' (CASCADE → giri)
    - localita_manutenzione (RESTRICT su giri, già rimossi)
    - stazione S98%
    """
    async with session_scope() as session:
        await session.execute(
            text(f"DELETE FROM turno_pdc WHERE codice LIKE '{TURNO_PREFIX}%'")
        )
        await session.execute(
            text("DELETE FROM programma_materiale WHERE nome LIKE 'TEST_%'")
        )
        await session.execute(
            text(f"DELETE FROM localita_manutenzione WHERE codice LIKE '{LOC_CODICE}%'")
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


async def _get_azienda_id() -> int:
    async with session_scope() as session:
        row = (
            await session.execute(text("SELECT id FROM azienda WHERE codice = 'trenord'"))
        ).first()
        assert row is not None
        return int(row[0])


async def _setup_minimo() -> tuple[int, int, int]:
    """Crea stazione, località, programma. Ritorna (azienda_id, loc_id, prog_id)."""
    az_id = await _get_azienda_id()
    async with session_scope() as session:
        session.add(Stazione(codice="S98001", nome="DUMMY", azienda_id=az_id))
        await session.flush()

        loc = LocalitaManutenzione(
            codice=LOC_CODICE,
            codice_breve=LOC_BREVE,
            nome_canonico=LOC_CODICE,
            stazione_collegata_codice="S98001",
            azienda_id=az_id,
        )
        session.add(loc)
        await session.flush()
        loc_id = int(loc.id)

        prog = ProgrammaMateriale(
            azienda_id=az_id,
            nome=PROG_NAME,
            valido_da=date(2026, 1, 1),
            valido_a=date(2026, 12, 31),
            stato="attivo",
        )
        session.add(prog)
        await session.flush()
        prog_id = int(prog.id)

        return az_id, loc_id, prog_id


async def _crea_giro(
    az_id: int, loc_id: int, prog_id: int, numero_turno: str
) -> int:
    """Crea un giro materiale fittizio. Ritorna giro_materiale_id."""
    async with session_scope() as session:
        giro = GiroMateriale(
            azienda_id=az_id,
            programma_id=prog_id,
            numero_turno=numero_turno,
            tipo_materiale="ALe711",
            numero_giornate=1,
            localita_manutenzione_partenza_id=loc_id,
            localita_manutenzione_arrivo_id=loc_id,
            stato="bozza",
        )
        session.add(giro)
        await session.flush()
        return int(giro.id)


async def _crea_turno_pdc(
    az_id: int,
    codice: str,
    impianto: str,
    prestazione_min: int,
    condotta_min: int,
    is_notturno: bool = False,
) -> int:
    """Crea un TurnoPdc + 1 giornata con i metric forniti."""
    async with session_scope() as session:
        turno = TurnoPdc(
            azienda_id=az_id,
            codice=codice,
            impianto=impianto,
            profilo="Condotta",
            ciclo_giorni=7,
            valido_da=date(2026, 1, 1),
            stato="bozza",
        )
        session.add(turno)
        await session.flush()
        session.add(
            TurnoPdcGiornata(
                turno_pdc_id=turno.id,
                numero_giornata=1,
                variante_calendario="LMXGV",
                inizio_prestazione=time(8, 0),
                fine_prestazione=time(16, 0),
                prestazione_min=prestazione_min,
                condotta_min=condotta_min,
                refezione_min=30,
                km=120,
                is_notturno=is_notturno,
            )
        )
        return int(turno.id)


def _login(client: TestClient, username: str, password: str) -> str:
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return str(res.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# =====================================================================
# Auth
# =====================================================================


async def test_overview_senza_token_401(client: TestClient) -> None:
    res = client.get("/api/pianificatore-pdc/overview")
    assert res.status_code == 401


async def test_overview_ruolo_pianificatore_giro_403(client: TestClient) -> None:
    """L'utente seed `pianificatore_giro_demo` ha solo PIANIFICATORE_GIRO,
    non PIANIFICATORE_PDC: deve ricevere 403."""
    token = _login(client, "pianificatore_giro_demo", "demo12345")
    res = client.get("/api/pianificatore-pdc/overview", headers=_auth(token))
    assert res.status_code == 403
    assert "PIANIFICATORE_PDC" in res.json()["detail"]


# =====================================================================
# Happy path — DB vuoto
# =====================================================================


async def test_overview_admin_db_vuoto(client: TestClient) -> None:
    """Admin bypassa il check ruolo. KPI tutti a 0 con DB vuoto."""
    await _setup_minimo()
    token = _login(client, "admin", "admin12345")
    res = client.get("/api/pianificatore-pdc/overview", headers=_auth(token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["giri_materiali_count"] == 0
    assert body["turni_pdc_per_impianto"] == []
    assert body["turni_con_violazioni_hard"] == 0
    assert body["revisioni_cascading_attive"] == 0


# =====================================================================
# Happy path — KPI con dati
# =====================================================================


async def test_overview_kpi_con_dati(client: TestClient) -> None:
    """Verifica n. giri, breakdown impianto e count violazioni con un mix:
    - 2 giri materiali
    - 2 turni MILANO_GA + 1 BRESCIA
    - 1 dei 3 turni ha prestazione 600 min (> cap 510 standard) → 1 violazione.
    """
    az_id, loc_id, prog_id = await _setup_minimo()
    await _crea_giro(az_id, loc_id, prog_id, "G001")
    await _crea_giro(az_id, loc_id, prog_id, "G002")

    await _crea_turno_pdc(az_id, f"{TURNO_PREFIX}T1", "MILANO_GA", 480, 250)
    await _crea_turno_pdc(az_id, f"{TURNO_PREFIX}T2", "MILANO_GA", 600, 250)
    await _crea_turno_pdc(az_id, f"{TURNO_PREFIX}T3", "BRESCIA", 420, 280)

    token = _login(client, "admin", "admin12345")
    res = client.get("/api/pianificatore-pdc/overview", headers=_auth(token))
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["giri_materiali_count"] == 2
    assert body["turni_pdc_per_impianto"] == [
        {"impianto": "BRESCIA", "count": 1},
        {"impianto": "MILANO_GA", "count": 2},
    ]
    assert body["turni_con_violazioni_hard"] == 1
    assert body["revisioni_cascading_attive"] == 0


# =====================================================================
# Violazioni — copertura dei 3 cap
# =====================================================================


async def test_overview_violazione_condotta(client: TestClient) -> None:
    """Condotta > 330 min (5h30) → violazione hard anche se prestazione OK."""
    az_id, _, _ = await _setup_minimo()
    await _crea_turno_pdc(az_id, f"{TURNO_PREFIX}TC", "MILANO_FIO", 500, 360)

    token = _login(client, "admin", "admin12345")
    res = client.get("/api/pianificatore-pdc/overview", headers=_auth(token))
    body = res.json()
    assert body["turni_con_violazioni_hard"] == 1


async def test_overview_violazione_notturna(client: TestClient) -> None:
    """Cap notturno 420 min vs cap standard 510. Una giornata notturna a
    450 min è violazione, una standard a 450 no."""
    az_id, _, _ = await _setup_minimo()
    await _crea_turno_pdc(
        az_id, f"{TURNO_PREFIX}TN1", "MILANO_GA", 450, 200, is_notturno=True
    )
    await _crea_turno_pdc(
        az_id, f"{TURNO_PREFIX}TN2", "MILANO_GA", 450, 200, is_notturno=False
    )

    token = _login(client, "admin", "admin12345")
    res = client.get("/api/pianificatore-pdc/overview", headers=_auth(token))
    body = res.json()
    assert body["turni_con_violazioni_hard"] == 1


async def test_overview_un_turno_con_piu_violazioni_conta_uno(client: TestClient) -> None:
    """Una giornata che viola sia prestazione che condotta non duplica il
    turno nel count (count distinct)."""
    az_id, _, _ = await _setup_minimo()
    await _crea_turno_pdc(az_id, f"{TURNO_PREFIX}TX", "MILANO_GA", 700, 400)

    token = _login(client, "admin", "admin12345")
    res = client.get("/api/pianificatore-pdc/overview", headers=_auth(token))
    body = res.json()
    assert body["turni_con_violazioni_hard"] == 1
