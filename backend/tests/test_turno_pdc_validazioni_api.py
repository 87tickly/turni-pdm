"""Test integration API Sprint 7.3 MR 4 — flag validazione live nel
dettaglio turno PdC.

Verifica che `GET /api/turni-pdc/{id}` esponga:
- per ogni giornata: `prestazione_violata`, `condotta_violata`,
  `refezione_mancante` calcolati on-the-fly
- a livello turno: `n_giornate_violanti`, `n_violazioni_hard`,
  `n_violazioni_soft`, `validazioni_ciclo` (passthrough da
  generation_metadata_json.violazioni)
"""

from __future__ import annotations

import os
from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from colazione.db import dispose_engine, session_scope
from colazione.main import app
from colazione.models.turni_pdc import TurnoPdc, TurnoPdcGiornata

pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_DB_TESTS") == "1",
    reason="DB not configured for tests",
)


TURNO_PREFIX = "TEST_VLD_"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


async def _wipe() -> None:
    async with session_scope() as session:
        await session.execute(
            text(f"DELETE FROM turno_pdc WHERE codice LIKE '{TURNO_PREFIX}%'")
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


async def _crea_turno(
    codice: str,
    giornate_specs: list[
        tuple[int, int, bool]
    ],  # (prestazione_min, condotta_min, is_notturno)
    refezioni: list[int] | None = None,  # per ogni giornata: refezione_min (default 30)
    metadata: dict | None = None,
) -> int:
    async with session_scope() as session:
        az_row = (
            await session.execute(text("SELECT id FROM azienda WHERE codice = 'trenord'"))
        ).first()
        assert az_row is not None
        az_id = int(az_row[0])

        turno = TurnoPdc(
            azienda_id=az_id,
            codice=codice,
            impianto="MILANO_GA",
            profilo="Condotta",
            ciclo_giorni=7,
            valido_da=date(2026, 1, 1),
            stato="bozza",
            generation_metadata_json=metadata or {},
        )
        session.add(turno)
        await session.flush()

        for i, (prest, cond, notturno) in enumerate(giornate_specs):
            ref = refezioni[i] if refezioni is not None else 30
            session.add(
                TurnoPdcGiornata(
                    turno_pdc_id=turno.id,
                    numero_giornata=i + 1,
                    variante_calendario="LMXGV",
                    inizio_prestazione=time(8, 0),
                    fine_prestazione=time(16, 0),
                    prestazione_min=prest,
                    condotta_min=cond,
                    refezione_min=ref,
                    km=120,
                    is_notturno=notturno,
                )
            )

        return int(turno.id)


def _login(client: TestClient, username: str, password: str) -> str:
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200
    return str(res.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# =====================================================================
# Flag validazione per giornata
# =====================================================================


async def test_giornata_dentro_cap_no_violazioni(client: TestClient) -> None:
    """Giornata 480/240 standard, refezione 30 → tutti flag False."""
    turno_id = await _crea_turno(
        f"{TURNO_PREFIX}OK", [(480, 240, False)], refezioni=[30]
    )
    token = _login(client, "admin", "admin12345")
    res = client.get(f"/api/turni-pdc/{turno_id}", headers=_auth(token))
    assert res.status_code == 200, res.text
    body = res.json()
    g = body["giornate"][0]
    assert g["prestazione_violata"] is False
    assert g["condotta_violata"] is False
    assert g["refezione_mancante"] is False
    assert body["n_giornate_violanti"] == 0
    assert body["n_violazioni_hard"] == 0
    assert body["n_violazioni_soft"] == 0


async def test_giornata_prestazione_oltre_cap_standard(client: TestClient) -> None:
    """600 min standard > cap 510 → prestazione_violata=True."""
    turno_id = await _crea_turno(f"{TURNO_PREFIX}PR", [(600, 240, False)])
    token = _login(client, "admin", "admin12345")
    body = client.get(f"/api/turni-pdc/{turno_id}", headers=_auth(token)).json()
    assert body["giornate"][0]["prestazione_violata"] is True
    assert body["n_violazioni_hard"] == 1
    assert body["n_giornate_violanti"] == 1


async def test_giornata_prestazione_oltre_cap_notturno(client: TestClient) -> None:
    """450 min notturno > cap 420 → violata. Stessa giornata standard
    sotto cap 510 → non violata."""
    turno_id = await _crea_turno(f"{TURNO_PREFIX}NOT", [(450, 240, True)])
    token = _login(client, "admin", "admin12345")
    body = client.get(f"/api/turni-pdc/{turno_id}", headers=_auth(token)).json()
    assert body["giornate"][0]["prestazione_violata"] is True
    assert body["giornate"][0]["is_notturno"] is True


async def test_giornata_condotta_oltre_cap(client: TestClient) -> None:
    """340 min condotta > cap 330 → condotta_violata=True."""
    turno_id = await _crea_turno(f"{TURNO_PREFIX}CD", [(500, 340, False)])
    token = _login(client, "admin", "admin12345")
    body = client.get(f"/api/turni-pdc/{turno_id}", headers=_auth(token)).json()
    assert body["giornate"][0]["condotta_violata"] is True
    assert body["n_violazioni_hard"] == 1


async def test_giornata_refezione_mancante(client: TestClient) -> None:
    """Prestazione 400 (>360) ma refezione 0 → refezione_mancante=True (soft)."""
    turno_id = await _crea_turno(
        f"{TURNO_PREFIX}RF", [(400, 240, False)], refezioni=[0]
    )
    token = _login(client, "admin", "admin12345")
    body = client.get(f"/api/turni-pdc/{turno_id}", headers=_auth(token)).json()
    assert body["giornate"][0]["refezione_mancante"] is True
    assert body["n_violazioni_hard"] == 0  # soft, non hard
    assert body["n_violazioni_soft"] == 1
    # n_giornate_violanti conta solo violazioni hard
    assert body["n_giornate_violanti"] == 0


async def test_giornata_corta_no_refezione_richiesta(client: TestClient) -> None:
    """Prestazione 300 (≤360) e refezione 0 → refezione_mancante=False
    (sotto la soglia di 6h che attiva la richiesta)."""
    turno_id = await _crea_turno(
        f"{TURNO_PREFIX}SH", [(300, 200, False)], refezioni=[0]
    )
    token = _login(client, "admin", "admin12345")
    body = client.get(f"/api/turni-pdc/{turno_id}", headers=_auth(token)).json()
    assert body["giornate"][0]["refezione_mancante"] is False


async def test_giornata_multipla_violazioni_aggregati(client: TestClient) -> None:
    """3 giornate: G1 OK, G2 prestazione+condotta violate, G3 refezione mancante.
    Aggregati: 1 giornata violante (G2), 2 hard, 1 soft."""
    turno_id = await _crea_turno(
        f"{TURNO_PREFIX}MX",
        [
            (480, 240, False),  # G1 OK
            (600, 360, False),  # G2 prest+cond violate
            (400, 240, False),  # G3 refez mancante
        ],
        refezioni=[30, 30, 0],
    )
    token = _login(client, "admin", "admin12345")
    body = client.get(f"/api/turni-pdc/{turno_id}", headers=_auth(token)).json()
    assert len(body["giornate"]) == 3
    assert body["n_giornate_violanti"] == 1  # solo G2
    assert body["n_violazioni_hard"] == 2  # prestazione + condotta in G2
    assert body["n_violazioni_soft"] == 1  # refezione G3


async def test_validazioni_ciclo_passthrough_da_metadata(client: TestClient) -> None:
    """`validazioni_ciclo` riflette i tag stringa in
    `generation_metadata_json.violazioni`."""
    turno_id = await _crea_turno(
        f"{TURNO_PREFIX}CY",
        [(480, 240, False)],
        metadata={
            "violazioni": ["riposo_settimanale_corto", "fr_oltre_3_su_28gg"],
            "altro": 42,
        },
    )
    token = _login(client, "admin", "admin12345")
    body = client.get(f"/api/turni-pdc/{turno_id}", headers=_auth(token)).json()
    assert body["validazioni_ciclo"] == [
        "riposo_settimanale_corto",
        "fr_oltre_3_su_28gg",
    ]
