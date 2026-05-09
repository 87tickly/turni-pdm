"""Test unit vettura_resolver §7.2 — Sprint 8.2 MR-PD3.

Verifica la priorità ordinata VETTURA → MM → VOCTAXI con i 7 scenari
chiave. ``trova_treno_vettura`` è mockato per evitare chiamate reali
all'API ``live.arturo.travel``: i test sono pure-function lato
resolver. La copertura della chiamata API reale è in
``test_live_arturo_client.py``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from colazione.domain.builder_pdc.vettura_resolver import (
    DEPOT_MILANO_MM,
    MM_DURATA_FORFETTARIA_MIN,
    PRESTAZIONE_MAX_NOTTURNO_MIN,
    PRESTAZIONE_MAX_STANDARD_MIN,
    RETRY_API_MAX_TENTATIVI,
    VOCTAXI_DURATA_DEFAULT_MIN,
    SceltaMM,
    SceltaVettura,
    SceltaVOCTAXI,
    risolvi_rientro,
)
from colazione.integrations.live_arturo import PartenzeCache, TrenoVettura

# =====================================================================
# Helper costruzione TrenoVettura mock
# =====================================================================


def _treno(
    numero: str = "T1",
    *,
    da: str = "TIRANO",
    a: str = "MILANO_PG",
    partenza_min: int = 18 * 60,
    arrivo_min: int = 21 * 60,
) -> TrenoVettura:
    return TrenoVettura(
        numero=numero,
        categoria="RV",
        operatore="TN",
        stazione_partenza_codice=da,
        stazione_arrivo_codice=a,
        partenza_min=partenza_min,
        arrivo_min=arrivo_min,
        durata_min=(arrivo_min - partenza_min) % (24 * 60),
    )


@pytest.fixture
def fake_client() -> Any:
    return httpx.AsyncClient()


# =====================================================================
# Scenario 1 — vettura ok, non sfora cap → SceltaVettura
# =====================================================================


@pytest.mark.asyncio
async def test_vettura_ok_non_sfora_ritorna_scelza_vettura(
    fake_client: httpx.AsyncClient,
) -> None:
    """Vettura disponibile e prestazione finale ≤ 510 min standard."""
    treno = _treno(numero="2425", partenza_min=18 * 60, arrivo_min=20 * 60)

    with patch(
        "colazione.domain.builder_pdc.vettura_resolver.trova_treno_vettura",
        new=AsyncMock(return_value=treno),
    ):
        out = await risolvi_rientro(
            deposito_codice="GARIBALDI_TE",
            deposito_stazione_codice="MILANO_PG",
            stazione_chiusura_codice="TIRANO",
            ora_presa_min=12 * 60,  # 12:00 → fine 20:15 → 8h15 < 8h30 OK
            ora_chiusura_servizio_min=18 * 60 - 30,  # 17:30 fine ACCa
            is_cap_notturno=False,
            live_client=fake_client,
        )

    assert isinstance(out, SceltaVettura)
    assert out.tipo == "VETTURA"
    assert out.treno is treno
    # prestazione_finale = arrivo_vettura + 15min - presa = 20:15 - 12:00 = 8h15 = 495 min
    assert out.prestazione_finale_min == 8 * 60 + 15
    assert out.prestazione_finale_min <= PRESTAZIONE_MAX_STANDARD_MIN


# =====================================================================
# Scenario 2 — vettura sfora cap, deposito Milano → SceltaMM
# =====================================================================


@pytest.mark.asyncio
async def test_vettura_sfora_milano_ritorna_scelza_mm(
    fake_client: httpx.AsyncClient,
) -> None:
    """Vettura porta la prestazione oltre 8h30 ma deposito è Milano →
    fallback MM."""
    # Vettura arriva a 22:00 → fine 22:15 → presa 12:00 → 10h15 > 8h30
    treno = _treno(partenza_min=20 * 60, arrivo_min=22 * 60)

    with patch(
        "colazione.domain.builder_pdc.vettura_resolver.trova_treno_vettura",
        new=AsyncMock(return_value=treno),
    ):
        out = await risolvi_rientro(
            deposito_codice="GARIBALDI_TE",
            deposito_stazione_codice="MILANO_PG",
            stazione_chiusura_codice="TIRANO",
            ora_presa_min=12 * 60,
            ora_chiusura_servizio_min=19 * 60 + 30,
            is_cap_notturno=False,
            live_client=fake_client,
        )

    assert isinstance(out, SceltaMM)
    assert out.tipo == "MM"
    assert out.durata_min == MM_DURATA_FORFETTARIA_MIN
    assert "sfora" in out.motivo
    assert "Milano" in out.motivo


# =====================================================================
# Scenario 3 — vettura sfora cap, deposito periferico → SceltaVOCTAXI
# =====================================================================


@pytest.mark.asyncio
async def test_vettura_sfora_periferico_ritorna_scelza_voctaxi(
    fake_client: httpx.AsyncClient,
) -> None:
    """Vettura sfora cap, deposito periferico (non Milano-MM) →
    fallback diretto VOCTAXI (skip step 2)."""
    treno = _treno(partenza_min=20 * 60, arrivo_min=22 * 60)

    with patch(
        "colazione.domain.builder_pdc.vettura_resolver.trova_treno_vettura",
        new=AsyncMock(return_value=treno),
    ):
        out = await risolvi_rientro(
            deposito_codice="SONDRIO",  # non in DEPOT_MILANO_MM
            deposito_stazione_codice="SONDRIO",
            stazione_chiusura_codice="TIRANO",
            ora_presa_min=12 * 60,
            ora_chiusura_servizio_min=19 * 60 + 30,
            is_cap_notturno=False,
            live_client=fake_client,
        )

    assert isinstance(out, SceltaVOCTAXI)
    assert out.tipo == "VOCTAXI"
    assert out.durata_min == VOCTAXI_DURATA_DEFAULT_MIN
    assert "non in" in out.motivo or "non Milano" in out.motivo or "periferic" in out.motivo.lower()


# =====================================================================
# Scenario 4 — nessuna vettura disponibile, deposito Milano → SceltaMM
# =====================================================================


@pytest.mark.asyncio
async def test_nessuna_vettura_milano_ritorna_scelza_mm(
    fake_client: httpx.AsyncClient,
) -> None:
    """API ritorna None (nessun treno utile in finestra), deposito
    Milano → MM."""
    with patch(
        "colazione.domain.builder_pdc.vettura_resolver.trova_treno_vettura",
        new=AsyncMock(return_value=None),
    ):
        out = await risolvi_rientro(
            deposito_codice="FIORENZA",
            deposito_stazione_codice="MILANO_CERTOSA",
            stazione_chiusura_codice="MILANO_PG",
            ora_presa_min=6 * 60,
            ora_chiusura_servizio_min=14 * 60,
            is_cap_notturno=False,
            live_client=fake_client,
        )

    assert isinstance(out, SceltaMM)
    assert "nessuna vettura" in out.motivo.lower()


# =====================================================================
# Scenario 5 — nessuna vettura, deposito periferico → SceltaVOCTAXI
# =====================================================================


@pytest.mark.asyncio
async def test_nessuna_vettura_periferico_ritorna_scelza_voctaxi(
    fake_client: httpx.AsyncClient,
) -> None:
    """API ritorna None, deposito periferico → VOCTAXI."""
    with patch(
        "colazione.domain.builder_pdc.vettura_resolver.trova_treno_vettura",
        new=AsyncMock(return_value=None),
    ):
        out = await risolvi_rientro(
            deposito_codice="CREMONA",  # non Milano
            deposito_stazione_codice="CREMONA",
            stazione_chiusura_codice="MANTOVA",
            ora_presa_min=6 * 60,
            ora_chiusura_servizio_min=14 * 60,
            is_cap_notturno=False,
            live_client=fake_client,
        )

    assert isinstance(out, SceltaVOCTAXI)
    assert "nessuna vettura" in out.motivo.lower()


# =====================================================================
# Scenario 6 — chiusura coincide col deposito → no-op
# =====================================================================


@pytest.mark.asyncio
async def test_chiusura_uguale_deposito_ritorna_voctaxi_no_op(
    fake_client: httpx.AsyncClient,
) -> None:
    """Caso degenere: il PdC chiude già al deposito → no-op (durata 0)."""
    with patch(
        "colazione.domain.builder_pdc.vettura_resolver.trova_treno_vettura",
        new=AsyncMock(return_value=None),
    ) as mock_trova:
        out = await risolvi_rientro(
            deposito_codice="BERGAMO",
            deposito_stazione_codice="BERGAMO",
            stazione_chiusura_codice="BERGAMO",  # identica
            ora_presa_min=6 * 60,
            ora_chiusura_servizio_min=14 * 60,
            is_cap_notturno=False,
            live_client=fake_client,
        )
    # API non deve essere chiamata (short-circuit prima dello step 1)
    mock_trova.assert_not_called()

    assert isinstance(out, SceltaVOCTAXI)
    assert out.durata_min == 0
    assert "nullo" in out.motivo or "coincide" in out.motivo


# =====================================================================
# Scenario 7 — turno notturno (cap 420 invece di 510)
# =====================================================================


@pytest.mark.asyncio
async def test_vettura_notturno_cap_420(fake_client: httpx.AsyncClient) -> None:
    """Turno notturno (presa 02:00). Stessa vettura che starebbe sotto
    510 standard ma supera 420 notturno → fallback MM (Milano)."""
    # presa 02:00, arrivo vettura 09:30 → fine 09:45 → 7h45 = 465 min
    # > 420 (notturno cap) ma < 510 (standard cap)
    treno = _treno(partenza_min=8 * 60, arrivo_min=9 * 60 + 30)

    with patch(
        "colazione.domain.builder_pdc.vettura_resolver.trova_treno_vettura",
        new=AsyncMock(return_value=treno),
    ):
        out = await risolvi_rientro(
            deposito_codice="GARIBALDI_CADETTI",
            deposito_stazione_codice="MILANO_PG",
            stazione_chiusura_codice="VARESE",
            ora_presa_min=2 * 60,
            ora_chiusura_servizio_min=7 * 60 + 30,
            is_cap_notturno=True,
            live_client=fake_client,
        )

    # Cap notturno è 420 → vettura sfora → fallback MM (Milano)
    assert isinstance(out, SceltaMM)
    assert str(PRESTAZIONE_MAX_NOTTURNO_MIN) in out.motivo


# =====================================================================
# Sanity check costanti
# =====================================================================


def test_depot_milano_mm_contiene_5_voci() -> None:
    """Sanity: la lista DEPOT_MILANO_MM ha le voci attese da NORMATIVA
    §2.2 (3× GARIBALDI_*, 2× GRECO_*, FIORENZA = 6 voci)."""
    assert "GARIBALDI_ALE" in DEPOT_MILANO_MM
    assert "GARIBALDI_CADETTI" in DEPOT_MILANO_MM
    assert "GARIBALDI_TE" in DEPOT_MILANO_MM
    assert "GRECO_TE" in DEPOT_MILANO_MM
    assert "GRECO_S9" in DEPOT_MILANO_MM
    assert "FIORENZA" in DEPOT_MILANO_MM
    assert "BERGAMO" not in DEPOT_MILANO_MM
    assert "SONDRIO" not in DEPOT_MILANO_MM


# =====================================================================
# Sprint 8.2 MR-PD-FIX-SEVERO 3a (A3) — robustezza errori API live
# =====================================================================


@pytest.mark.asyncio
async def test_a3_eccezione_imprevista_difensivo_no_crash(
    fake_client: httpx.AsyncClient,
) -> None:
    """Difensivo A3: live_arturo per contratto non solleva (vedi docstring
    live_arturo.py righe 21-24), ma se in futuro una regressione lo rompe
    il resolver NON deve propagare l'eccezione al chiamante (= endpoint
    MR-PD5 → 500 evitato).

    Mock con side_effect=RuntimeError simula bug futuro in live_arturo.
    Il try/except broad cattura, marca api_failed=True, dopo 1 retry
    (anche fallito) si ritorna a fallback graceful (MM o VOCTAXI a
    seconda del deposito).
    """
    mock = AsyncMock(side_effect=RuntimeError("simulated future bug in live_arturo"))

    with patch(
        "colazione.domain.builder_pdc.vettura_resolver.trova_treno_vettura",
        new=mock,
    ):
        out = await risolvi_rientro(
            deposito_codice="GARIBALDI_TE",
            deposito_stazione_codice="MILANO_PG",
            stazione_chiusura_codice="TIRANO",
            ora_presa_min=12 * 60,
            ora_chiusura_servizio_min=19 * 60 + 30,
            is_cap_notturno=False,
            live_client=fake_client,
            cache=None,  # senza cache: signal solo via Exception
        )

    # Il resolver è arrivato in fondo senza propagare l'eccezione.
    assert isinstance(out, SceltaMM)  # deposito Milano → MM fallback
    # Mock chiamato 2 volte (1 + RETRY_API_MAX_TENTATIVI=1).
    assert mock.call_count == 1 + RETRY_API_MAX_TENTATIVI
    # Motivo arricchito col flag API non raggiungibile.
    assert "API live non raggiungibile" in out.motivo


@pytest.mark.asyncio
async def test_a3_cache_errori_signal_attiva_retry(
    fake_client: httpx.AsyncClient,
) -> None:
    """Signal A3: live_arturo._fetch_partenze incrementa cache.errori dopo
    retry interno fallito. Il resolver legge il delta vs baseline e
    decide il retry resolver-level (1 retry con backoff + bypass cache
    entry None).

    Simulazione: mock incrementa cache.errori e ritorna None ad ogni
    chiamata (= API persistentemente down). Resolver tentativi attesi:
    1 + RETRY_API_MAX_TENTATIVI = 2.
    """
    cache = PartenzeCache()
    call_count = {"n": 0}

    async def fake_trova(**kwargs: Any) -> TrenoVettura | None:
        call_count["n"] += 1
        c = kwargs.get("cache")
        if c is not None:
            c.errori += 1
            # Simula caching del None (live_arturo lo fa su HTTPError)
            stz = kwargs["stazione_partenza_codice"]
            c.by_stazione[stz] = None
        return None

    with patch(
        "colazione.domain.builder_pdc.vettura_resolver.trova_treno_vettura",
        new=AsyncMock(side_effect=fake_trova),
    ):
        out = await risolvi_rientro(
            deposito_codice="SONDRIO",  # NON Milano → step 3 VOCTAXI
            deposito_stazione_codice="SONDRIO",
            stazione_chiusura_codice="TIRANO",
            ora_presa_min=12 * 60,
            ora_chiusura_servizio_min=19 * 60 + 30,
            is_cap_notturno=False,
            live_client=fake_client,
            cache=cache,
        )

    # Mock chiamato 1 + RETRY_API_MAX_TENTATIVI = 2 volte.
    assert call_count["n"] == 1 + RETRY_API_MAX_TENTATIVI
    # Cache.errori incrementato 2 volte (una per chiamata).
    assert cache.errori == 1 + RETRY_API_MAX_TENTATIVI
    # Bypass cache: dopo il retry, l'entry per la stazione è stata
    # ri-popolata con None nel secondo tentativo (no entry stale).
    assert cache.by_stazione.get("TIRANO") is None
    # Output graceful con motivo arricchito.
    assert isinstance(out, SceltaVOCTAXI)
    assert "API live non raggiungibile" in out.motivo


# =====================================================================
# Sprint 8.2 MR-PD-FIX-SEVERO 3b A1 — registro vetture cross-PdC
# =====================================================================


@pytest.mark.asyncio
async def test_a1_registro_propaga_esclusi_a_trova_treno_vettura(
    fake_client: httpx.AsyncClient,
) -> None:
    """Verifica che il resolver passi il set ``esclusi`` corretto a
    ``trova_treno_vettura`` quando registro+data_operativa valorizzati.

    Setup: registro contiene vettura ('2425', 'TN', 2026-03-15).
    Mock trova_treno_vettura riceve esclusi = {('2425', 'TN')} e ritorna
    None (= simula filtro applicato, nessun candidato resta).
    Output atteso: SceltaMM (deposito Milano) o VOCTAXI.
    """
    from datetime import date

    from colazione.domain.builder_pdc.registro_vetture import (
        RegistroVettureAssegnate,
    )

    registro = RegistroVettureAssegnate()
    registro.assegna(
        numero_treno="2425",
        operatore="TN",
        data_operativa=date(2026, 3, 15),
    )

    captured_esclusi: dict[str, frozenset[tuple[str, str | None]] | None] = {
        "value": None
    }

    async def fake_trova(**kwargs: Any) -> TrenoVettura | None:
        captured_esclusi["value"] = kwargs.get("esclusi")
        return None  # simula filtro applicato

    with patch(
        "colazione.domain.builder_pdc.vettura_resolver.trova_treno_vettura",
        new=AsyncMock(side_effect=fake_trova),
    ):
        out = await risolvi_rientro(
            deposito_codice="GARIBALDI_TE",
            deposito_stazione_codice="MILANO_PG",
            stazione_chiusura_codice="TIRANO",
            ora_presa_min=12 * 60,
            ora_chiusura_servizio_min=19 * 60 + 30,
            is_cap_notturno=False,
            live_client=fake_client,
            registro=registro,
            data_operativa=date(2026, 3, 15),
        )

    # Esclusi propagato con la chiave corretta.
    assert captured_esclusi["value"] is not None
    assert ("2425", "TN") in captured_esclusi["value"]
    # Output graceful (no crash, no doppione).
    assert isinstance(out, SceltaMM)


@pytest.mark.asyncio
async def test_a1_registro_assente_esclusi_none(
    fake_client: httpx.AsyncClient,
) -> None:
    """Backward compat: senza registro/data_operativa, esclusi=None
    (nessun filtro), comportamento legacy preservato."""
    from datetime import date  # noqa: F401 - import di parità con test sopra

    captured: dict[str, frozenset[tuple[str, str | None]] | None] = {"value": ...}  # type: ignore[dict-item]

    async def fake_trova(**kwargs: Any) -> TrenoVettura | None:
        captured["value"] = kwargs.get("esclusi")
        return None

    with patch(
        "colazione.domain.builder_pdc.vettura_resolver.trova_treno_vettura",
        new=AsyncMock(side_effect=fake_trova),
    ):
        await risolvi_rientro(
            deposito_codice="FIORENZA",
            deposito_stazione_codice="MILANO_CERTOSA",
            stazione_chiusura_codice="MILANO_PG",
            ora_presa_min=6 * 60,
            ora_chiusura_servizio_min=14 * 60,
            is_cap_notturno=False,
            live_client=fake_client,
            # registro/data_operativa omessi → backward compat
        )

    assert captured["value"] is None  # nessun filtro applicato


@pytest.mark.asyncio
async def test_a3_cache_assente_no_signal_no_retry_inutile(
    fake_client: httpx.AsyncClient,
) -> None:
    """Senza cache E senza eccezioni il resolver non ha signal per
    distinguere "API failed" da "nessun treno utile in finestra".
    Comportamento conservativo: NESSUN retry inutile (treno is None +
    not api_failed → break immediato dopo prima chiamata).

    Caso reale: chiamata API riesce ma niente treno passante in finestra
    accettabile → fallback MM/VOCTAXI legittimo, no retry serve.
    """
    mock = AsyncMock(return_value=None)

    with patch(
        "colazione.domain.builder_pdc.vettura_resolver.trova_treno_vettura",
        new=mock,
    ):
        out = await risolvi_rientro(
            deposito_codice="FIORENZA",
            deposito_stazione_codice="MILANO_CERTOSA",
            stazione_chiusura_codice="MILANO_PG",
            ora_presa_min=6 * 60,
            ora_chiusura_servizio_min=14 * 60,
            is_cap_notturno=False,
            live_client=fake_client,
            cache=None,
        )

    # 1 sola chiamata: no retry inutile.
    assert mock.call_count == 1
    # Output regolare (no flag api_failed nel motivo).
    assert isinstance(out, SceltaMM)
    assert "API live non raggiungibile" not in out.motivo
    assert "nessuna vettura utile" in out.motivo
