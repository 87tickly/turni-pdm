"""Test integration end-to-end PIANO α Sprint 8.2 — Sprint 8.3 S7.

Verifica che i validatori del piano α (riposo intraturno §11.5, riposo
settimanale §11.4, registro vetture cross-PdC §15) siano effettivamente
collegati all'endpoint ``POST /api/giri/{id}/genera-turno-pdc?builder_strategy=deposito_first``
e che producano metadati attesi + persistenza DB corretta.

Re-usa fixture ``_crea_giro_completo_per_deposito_first``,
``_ensure_depot_test_pd5``, ``_crea_programma_in_stato`` da
test_api_programmi_conferma.

Mock ``trova_treno_vettura`` per evitare chiamate live.arturo.travel
reali (default ``None`` = fallback VOCTAXI; alcuni test ritornano un
treno mock per validare la persistenza ``numero_treno_vettura``).
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from colazione.db import session_scope
from colazione.integrations.live_arturo import TrenoVettura
from colazione.main import app

# Re-uso helper esistenti per non duplicare fixture
from tests.test_api_programmi_conferma import (
    _admin_token,
    _crea_giro_chiusura_diversa_dal_deposito,
    _crea_giro_completo_per_deposito_first,
    _crea_programma_in_stato,
    _h,
    _wipe_programmi,
)

pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_DB_TESTS") == "1",
    reason="DB not configured for tests",
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
async def _clean_programmi() -> None:
    """Cleanup pre-test riusato da test_api_programmi_conferma per
    evitare residui dal precedente run (turni T-TEST_DEPOT_PD5-* +
    programmi TEST_PIPELINE_*)."""
    await _wipe_programmi()


# =====================================================================
# §11.5 riposo intraturno + §11.4 riposo settimanale: metadata
# =====================================================================


@pytest.mark.asyncio
async def test_piano_alpha_metadata_riposo_intraturno_presente(
    client: TestClient,
) -> None:
    """Verifica che il metadata del turno persistito contenga il campo
    ``riposo_intraturno_violazioni`` (anche se vuoto) — = il validatore
    §11.5 MR-PD7b-2 entry 281 viene effettivamente eseguito."""
    pid = await _crea_programma_in_stato(
        "alpha_riposo_intra", "MATERIALE_CONFERMATO"
    )
    giro_id, depot_id, _ = await _crea_giro_completo_per_deposito_first(
        pid, "G-ALPHA-INTRA"
    )

    with patch(
        "colazione.domain.builder_pdc.vettura_resolver.trova_treno_vettura",
        new=AsyncMock(return_value=None),
    ):
        res = client.post(
            f"/api/giri/{giro_id}/genera-turno-pdc"
            f"?builder_strategy=deposito_first&deposito_pdc_id={depot_id}"
            "&force=true",
            headers=_h(_admin_token(client)),
        )
    assert res.status_code == 200, res.text
    turno_id = res.json()[0]["turno_pdc_id"]

    async with session_scope() as session:
        meta = (
            await session.execute(
                text(
                    "SELECT generation_metadata_json FROM turno_pdc "
                    "WHERE id = :tid"
                ),
                {"tid": turno_id},
            )
        ).scalar_one()
    # Campo presente (chiave esiste anche se la lista è vuota = no violazioni)
    assert "riposo_intraturno_violazioni" in meta
    assert isinstance(meta["riposo_intraturno_violazioni"], list)


@pytest.mark.asyncio
async def test_piano_alpha_metadata_riposo_settimanale_presente(
    client: TestClient,
) -> None:
    """Verifica che il metadata contenga ``riposo_settimanale_violazioni`` —
    = validatore §11.4 MR-PD7b-3 entry 282 effettivamente collegato."""
    pid = await _crea_programma_in_stato(
        "alpha_riposo_sett", "MATERIALE_CONFERMATO"
    )
    giro_id, depot_id, _ = await _crea_giro_completo_per_deposito_first(
        pid, "G-ALPHA-SETT"
    )

    with patch(
        "colazione.domain.builder_pdc.vettura_resolver.trova_treno_vettura",
        new=AsyncMock(return_value=None),
    ):
        res = client.post(
            f"/api/giri/{giro_id}/genera-turno-pdc"
            f"?builder_strategy=deposito_first&deposito_pdc_id={depot_id}"
            "&force=true",
            headers=_h(_admin_token(client)),
        )
    assert res.status_code == 200, res.text
    turno_id = res.json()[0]["turno_pdc_id"]

    async with session_scope() as session:
        meta = (
            await session.execute(
                text(
                    "SELECT generation_metadata_json FROM turno_pdc "
                    "WHERE id = :tid"
                ),
                {"tid": turno_id},
            )
        ).scalar_one()
    assert "riposo_settimanale_violazioni" in meta
    assert isinstance(meta["riposo_settimanale_violazioni"], list)


# =====================================================================
# Persistenza riposo_min su giornata (§11.5)
# =====================================================================


@pytest.mark.asyncio
async def test_piano_alpha_giornata_riposo_min_persistito_non_zero(
    client: TestClient,
) -> None:
    """``turno_pdc_giornata.riposo_min`` deve essere popolato dal
    validatore §11.5 (non più placeholder 0 di pre-MR-PD7b-2 entry 281).

    Per ciclo di 1 giornata, il riposo_min_post = stima settimanale
    conservativa (gap_singola_notte + 24h), che è ≥ 24*60 = 1440 min.
    """
    pid = await _crea_programma_in_stato(
        "alpha_riposo_min_persist", "MATERIALE_CONFERMATO"
    )
    giro_id, depot_id, _ = await _crea_giro_completo_per_deposito_first(
        pid, "G-ALPHA-MINPERSIST"
    )

    with patch(
        "colazione.domain.builder_pdc.vettura_resolver.trova_treno_vettura",
        new=AsyncMock(return_value=None),
    ):
        res = client.post(
            f"/api/giri/{giro_id}/genera-turno-pdc"
            f"?builder_strategy=deposito_first&deposito_pdc_id={depot_id}"
            "&force=true",
            headers=_h(_admin_token(client)),
        )
    assert res.status_code == 200, res.text
    turno_id = res.json()[0]["turno_pdc_id"]

    async with session_scope() as session:
        riposo_min_values = list(
            (
                await session.execute(
                    text(
                        "SELECT riposo_min FROM turno_pdc_giornata "
                        "WHERE turno_pdc_id = :tid ORDER BY numero_giornata"
                    ),
                    {"tid": turno_id},
                )
            ).scalars()
        )
    assert len(riposo_min_values) == 1
    # Stima settimanale wrap-around conservativa = ≥ 24h = 1440 min.
    # Pre-MR-PD7b-2 sarebbe stato 0 (placeholder). Ora è popolato.
    assert riposo_min_values[0] >= 24 * 60, (
        f"riposo_min={riposo_min_values[0]} < 24h: validatore §11.5 "
        f"non collegato? (entry 281)"
    )


# =====================================================================
# Persistenza numero_treno_vettura (§15 cross-PdC)
# =====================================================================


@pytest.mark.asyncio
async def test_piano_alpha_blocco_vettura_numero_treno_persistito(
    client: TestClient,
) -> None:
    """Sprint 8.4 S2 (chiude HIGH critica entry 295): il blocco VETTURA
    persistito deve avere ``numero_treno_vettura`` valorizzato quando
    ``trova_treno_vettura`` ritorna un treno reale.

    **Pre-fix entry 295** (S7 entry 289): il test era *vacuo* perché
    usava ``_crea_giro_completo_per_deposito_first`` (chiusura == deposito
    = staz_a) → builder short-circuit Caso A → NESSUN blocco VETTURA
    creato → loop su 0 righe sempre passing. Il bug HIGH-CRITICAL S1
    sarebbe sopravvissuto a questo test.

    **Post-fix S2**: usa la nuova fixture ``_crea_giro_chiusura_diversa_dal_deposito``
    che produce un giro con chiusura in ``staz_b`` ≠ depot.staz_principale
    (= staz_a) → builder attiva Caso B → ``risolvi_rientro`` § 7.2 →
    blocco VETTURA persistito → assertion **NON-VACUA** su
    ``numero_treno_vettura == "9999"``.

    Verifica end-to-end:
    - migration 0046 (campo `numero_treno_vettura` esiste, c8d9e0f1a2b3)
    - builder `_inserisci_blocco_rientro` (entry 279) popola il campo
    - persister `persisti_un_turno_pdc` salva il campo (entry 281)
    """
    pid = await _crea_programma_in_stato(
        "alpha_vett_numero", "MATERIALE_CONFERMATO"
    )
    giro_id, depot_id, _, depot_stazione, staz_chiusura = (
        await _crea_giro_chiusura_diversa_dal_deposito(
            pid, "G-ALPHA-VETT-CASO-B"
        )
    )

    # Treno mock con orari coerenti per rientro post-ACCa (10:40):
    # parte 12:30 (gap 110min < 120 cap), arriva 13:30 (60min vettura).
    # Prestazione totale = 13:45 - 07:05 = 6h40 < 510min cap standard ✓
    treno_mock = TrenoVettura(
        numero="9999",
        categoria="RV",
        operatore="TN",
        stazione_partenza_codice=staz_chiusura,
        stazione_arrivo_codice=depot_stazione,
        partenza_min=12 * 60 + 30,
        arrivo_min=13 * 60 + 30,
        durata_min=60,
    )

    with patch(
        "colazione.domain.builder_pdc.vettura_resolver.trova_treno_vettura",
        new=AsyncMock(return_value=treno_mock),
    ):
        res = client.post(
            f"/api/giri/{giro_id}/genera-turno-pdc"
            f"?builder_strategy=deposito_first&deposito_pdc_id={depot_id}"
            "&force=true",
            headers=_h(_admin_token(client)),
        )
    assert res.status_code == 200, res.text
    turno_id = res.json()[0]["turno_pdc_id"]

    async with session_scope() as session:
        rows = list(
            (
                await session.execute(
                    text(
                        "SELECT b.tipo_evento, b.numero_treno_vettura, "
                        "b.stazione_da_codice, b.stazione_a_codice "
                        "FROM turno_pdc_blocco b "
                        "JOIN turno_pdc_giornata g ON b.turno_pdc_giornata_id = g.id "
                        "WHERE g.turno_pdc_id = :tid AND b.tipo_evento = 'VETTURA'"
                    ),
                    {"tid": turno_id},
                )
            ).all()
        )

    # Sprint 8.4 S2: assertion NON-VACUA. Almeno 1 blocco VETTURA deve
    # esistere (la fixture chiude ≠ deposito, mock vettura disponibile).
    assert len(rows) >= 1, (
        f"Atteso ≥1 blocco VETTURA persistito (giro chiude in "
        f"{staz_chiusura} ≠ depot {depot_stazione}, mock vettura "
        f"ritorna treno reale). Trovati: {len(rows)}. Test vacuo "
        f"come pre-S2 critica entry 295."
    )

    for tipo, numero, da, a in rows:
        assert tipo == "VETTURA"
        assert numero == "9999", (
            "Blocco VETTURA persistito senza numero_treno_vettura "
            "atteso 9999 (= treno mock). Campo non popolato "
            "(entry 279/281 regression)"
        )
        # Il blocco rientra dal punto di chiusura giro al deposito.
        assert da == staz_chiusura, (
            f"VETTURA stazione_da={da} != staz_chiusura={staz_chiusura}"
        )
        assert a == depot_stazione, (
            f"VETTURA stazione_a={a} != depot_stazione={depot_stazione}"
        )


# =====================================================================
# Sanity check: builder_strategy='deposito_first' nel metadata
# =====================================================================


@pytest.mark.asyncio
async def test_piano_alpha_builder_strategy_in_metadata(
    client: TestClient,
) -> None:
    """Sanity ridondante con smoke MR-PD5 entry 271, ma utile come
    invariante per chiunque cambi il path opt-in."""
    pid = await _crea_programma_in_stato(
        "alpha_strategy", "MATERIALE_CONFERMATO"
    )
    giro_id, depot_id, _ = await _crea_giro_completo_per_deposito_first(
        pid, "G-ALPHA-STRAT"
    )

    with patch(
        "colazione.domain.builder_pdc.vettura_resolver.trova_treno_vettura",
        new=AsyncMock(return_value=None),
    ):
        res = client.post(
            f"/api/giri/{giro_id}/genera-turno-pdc"
            f"?builder_strategy=deposito_first&deposito_pdc_id={depot_id}"
            "&force=true",
            headers=_h(_admin_token(client)),
        )
    assert res.status_code == 200, res.text
    turno_id = res.json()[0]["turno_pdc_id"]

    async with session_scope() as session:
        meta: dict[str, Any] = (
            await session.execute(
                text(
                    "SELECT generation_metadata_json FROM turno_pdc "
                    "WHERE id = :tid"
                ),
                {"tid": turno_id},
            )
        ).scalar_one()

    assert meta.get("builder_strategy") == "deposito_first"
    # Metadata "violazioni_giornate_scartate" presente = chiunque debug
    # turni scartati ha info immediata
    assert "violazioni_giornate_scartate" in meta
