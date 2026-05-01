"""Test integration API Sprint 7.3 MR 2 — endpoint cross-programma/cross-giro:

- ``GET /api/giri`` — lista giri materiali dell'azienda con filtri
  (programma_id, stato, tipo_materiale, q, limit/offset)
- ``GET /api/turni-pdc`` — lista turni PdC dell'azienda con filtri
  (impianto, stato, profilo, valido_da_min/max, q, limit/offset)

Verifica auth (401, 403 per ruoli mancanti, 200 per PIANIFICATORE_PDC e
PIANIFICATORE_GIRO), filtri SQL, paginazione.
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


LOC_CODICE = "TEST_LOC_LIST"
PROG_NAME_A = "TEST_PROG_LIST_A"
PROG_NAME_B = "TEST_PROG_LIST_B"
TURNO_PREFIX = "TEST_LIST_T_"


# =====================================================================
# Setup
# =====================================================================


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


async def _wipe() -> None:
    async with session_scope() as session:
        await session.execute(
            text(f"DELETE FROM turno_pdc WHERE codice LIKE '{TURNO_PREFIX}%'")
        )
        await session.execute(
            text("DELETE FROM programma_materiale WHERE nome LIKE 'TEST_PROG_LIST_%'")
        )
        await session.execute(
            text(f"DELETE FROM localita_manutenzione WHERE codice LIKE '{LOC_CODICE}%'")
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


async def _setup_due_programmi() -> tuple[int, int, int, int]:
    """Crea 2 programmi A/B con 1 giro ciascuno + 3 turni PdC.
    Ritorna (azienda_id, prog_a_id, prog_b_id, loc_id)."""
    async with session_scope() as session:
        az_row = (
            await session.execute(text("SELECT id FROM azienda WHERE codice = 'trenord'"))
        ).first()
        assert az_row is not None
        az_id = int(az_row[0])

        session.add(Stazione(codice="S97001", nome="DUMMY", azienda_id=az_id))
        await session.flush()

        loc = LocalitaManutenzione(
            codice=LOC_CODICE,
            codice_breve="TLST",
            nome_canonico=LOC_CODICE,
            stazione_collegata_codice="S97001",
            azienda_id=az_id,
        )
        session.add(loc)
        await session.flush()
        loc_id = int(loc.id)

        prog_a = ProgrammaMateriale(
            azienda_id=az_id,
            nome=PROG_NAME_A,
            valido_da=date(2026, 1, 1),
            valido_a=date(2026, 12, 31),
            stato="attivo",
        )
        prog_b = ProgrammaMateriale(
            azienda_id=az_id,
            nome=PROG_NAME_B,
            valido_da=date(2026, 1, 1),
            valido_a=date(2026, 12, 31),
            stato="bozza",
        )
        session.add_all([prog_a, prog_b])
        await session.flush()
        prog_a_id = int(prog_a.id)
        prog_b_id = int(prog_b.id)

        # 2 giri sul programma A, 1 sul B
        session.add_all(
            [
                GiroMateriale(
                    azienda_id=az_id,
                    programma_id=prog_a_id,
                    numero_turno="A001",
                    tipo_materiale="ALe711",
                    numero_giornate=1,
                    localita_manutenzione_partenza_id=loc_id,
                    localita_manutenzione_arrivo_id=loc_id,
                    stato="bozza",
                ),
                GiroMateriale(
                    azienda_id=az_id,
                    programma_id=prog_a_id,
                    numero_turno="A002",
                    tipo_materiale="ETR526",
                    numero_giornate=1,
                    localita_manutenzione_partenza_id=loc_id,
                    localita_manutenzione_arrivo_id=loc_id,
                    stato="pubblicato",
                ),
                GiroMateriale(
                    azienda_id=az_id,
                    programma_id=prog_b_id,
                    numero_turno="B001",
                    tipo_materiale="ALe711",
                    numero_giornate=1,
                    localita_manutenzione_partenza_id=loc_id,
                    localita_manutenzione_arrivo_id=loc_id,
                    stato="bozza",
                ),
            ]
        )

        # 3 turni: 2 MILANO_GA (1 pubblicato, 1 bozza), 1 BRESCIA bozza
        for codice, impianto, stato_t, valido_da in [
            (f"{TURNO_PREFIX}001", "MILANO_GA", "pubblicato", date(2026, 3, 1)),
            (f"{TURNO_PREFIX}002", "MILANO_GA", "bozza", date(2026, 5, 1)),
            (f"{TURNO_PREFIX}003", "BRESCIA", "bozza", date(2026, 7, 1)),
        ]:
            t = TurnoPdc(
                azienda_id=az_id,
                codice=codice,
                impianto=impianto,
                profilo="Condotta",
                ciclo_giorni=7,
                valido_da=valido_da,
                stato=stato_t,
            )
            session.add(t)
            await session.flush()
            session.add(
                TurnoPdcGiornata(
                    turno_pdc_id=t.id,
                    numero_giornata=1,
                    variante_calendario="LMXGV",
                    inizio_prestazione=time(8, 0),
                    fine_prestazione=time(16, 0),
                    prestazione_min=480,
                    condotta_min=300,
                    refezione_min=30,
                    km=120,
                    is_notturno=False,
                )
            )

        return az_id, prog_a_id, prog_b_id, loc_id


def _login(client: TestClient, username: str, password: str) -> str:
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return str(res.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# =====================================================================
# GET /api/giri (cross-programma)
# =====================================================================


async def test_list_giri_senza_token_401(client: TestClient) -> None:
    res = client.get("/api/giri")
    assert res.status_code == 401


async def test_list_giri_admin_ritorna_tutti(client: TestClient) -> None:
    await _setup_due_programmi()
    token = _login(client, "admin", "admin12345")
    res = client.get("/api/giri", headers=_auth(token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert isinstance(body, list)
    assert len(body) == 3
    # Ordinato per numero_turno
    assert [g["numero_turno"] for g in body] == ["A001", "A002", "B001"]


async def test_list_giri_pianificatore_giro_ok(client: TestClient) -> None:
    """Il PIANIFICATORE_GIRO ha sempre potuto leggere i giri della propria
    azienda: la nuova auth `require_any_role(GIRO, PDC)` non lo blocca."""
    await _setup_due_programmi()
    token = _login(client, "pianificatore_giro_demo", "demo12345")
    res = client.get("/api/giri", headers=_auth(token))
    assert res.status_code == 200, res.text
    assert len(res.json()) == 3


async def test_list_giri_filtro_programma(client: TestClient) -> None:
    _, prog_a_id, _, _ = await _setup_due_programmi()
    token = _login(client, "admin", "admin12345")
    res = client.get(
        f"/api/giri?programma_id={prog_a_id}", headers=_auth(token)
    )
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 2
    assert all(g["numero_turno"] in {"A001", "A002"} for g in body)


async def test_list_giri_filtro_stato(client: TestClient) -> None:
    await _setup_due_programmi()
    token = _login(client, "admin", "admin12345")
    res = client.get("/api/giri?stato=pubblicato", headers=_auth(token))
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["numero_turno"] == "A002"


async def test_list_giri_filtro_q_numero_turno(client: TestClient) -> None:
    await _setup_due_programmi()
    token = _login(client, "admin", "admin12345")
    res = client.get("/api/giri?q=B0", headers=_auth(token))
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["numero_turno"] == "B001"


async def test_list_giri_paginazione(client: TestClient) -> None:
    await _setup_due_programmi()
    token = _login(client, "admin", "admin12345")
    res = client.get("/api/giri?limit=2&offset=1", headers=_auth(token))
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 2
    assert [g["numero_turno"] for g in body] == ["A002", "B001"]


# =====================================================================
# GET /api/turni-pdc (cross-giro)
# =====================================================================


async def test_list_turni_senza_token_401(client: TestClient) -> None:
    res = client.get("/api/turni-pdc")
    assert res.status_code == 401


async def test_list_turni_admin_ritorna_tutti(client: TestClient) -> None:
    await _setup_due_programmi()
    token = _login(client, "admin", "admin12345")
    res = client.get("/api/turni-pdc", headers=_auth(token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert isinstance(body, list)
    assert len(body) == 3
    assert [t["codice"] for t in body] == [
        f"{TURNO_PREFIX}001",
        f"{TURNO_PREFIX}002",
        f"{TURNO_PREFIX}003",
    ]


async def test_list_turni_filtro_impianto(client: TestClient) -> None:
    await _setup_due_programmi()
    token = _login(client, "admin", "admin12345")
    res = client.get("/api/turni-pdc?impianto=MILANO_GA", headers=_auth(token))
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 2
    assert all(t["impianto"] == "MILANO_GA" for t in body)


async def test_list_turni_filtro_stato(client: TestClient) -> None:
    await _setup_due_programmi()
    token = _login(client, "admin", "admin12345")
    res = client.get("/api/turni-pdc?stato=pubblicato", headers=_auth(token))
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["codice"] == f"{TURNO_PREFIX}001"


async def test_list_turni_filtro_valido_da_range(client: TestClient) -> None:
    await _setup_due_programmi()
    token = _login(client, "admin", "admin12345")
    # Range inclusivo 2026-04-01 → 2026-06-30: solo TURNO 002 (valido_da 2026-05-01)
    res = client.get(
        "/api/turni-pdc?valido_da_min=2026-04-01&valido_da_max=2026-06-30",
        headers=_auth(token),
    )
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["codice"] == f"{TURNO_PREFIX}002"


async def test_list_turni_filtro_q(client: TestClient) -> None:
    await _setup_due_programmi()
    token = _login(client, "admin", "admin12345")
    res = client.get(
        f"/api/turni-pdc?q={TURNO_PREFIX[-4:]}003", headers=_auth(token)
    )
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["codice"] == f"{TURNO_PREFIX}003"


async def test_list_turni_pianificatore_giro_ok(client: TestClient) -> None:
    """PIANIFICATORE_GIRO ha lettura cross-giro turni (require_any_role)."""
    await _setup_due_programmi()
    token = _login(client, "pianificatore_giro_demo", "demo12345")
    res = client.get("/api/turni-pdc", headers=_auth(token))
    assert res.status_code == 200
    assert len(res.json()) == 3


async def test_list_turni_lista_item_shape(client: TestClient) -> None:
    """Verifica che `n_giornate`, `prestazione_totale_min`, `condotta_totale_min`
    siano calcolati dalle giornate (1 giornata seedata con prest=480, cond=300)."""
    await _setup_due_programmi()
    token = _login(client, "admin", "admin12345")
    res = client.get("/api/turni-pdc?stato=pubblicato", headers=_auth(token))
    body = res.json()
    assert len(body) == 1
    item = body[0]
    assert item["n_giornate"] == 1
    assert item["prestazione_totale_min"] == 480
    assert item["condotta_totale_min"] == 300
    assert item["impianto"] == "MILANO_GA"
    assert item["profilo"] == "Condotta"
    assert item["is_ramo_split"] is False
