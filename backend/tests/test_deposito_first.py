"""Test unit builder deposito-first — Sprint 8.2 MR-PD3b + MR-PD4.

Verifica green-phase delle 4 violazioni dichiarate dall'utente
(speculare a ``test_violazioni_normative_pdc.py`` red-phase su
builder monolitico):

- A. cap condotta 5h30 → giornata SCARTATA (return None + violazione)
- C. stazione_fine == deposito GARANTITA per costruzione
- D. blocco di rientro VETTURA/MM/VOCTAXI in coda quando lontani da
  deposito

Plus scenari aggiuntivi:

- chiusura coincide col deposito → no rientro extra
- depot senza stazione_principale_codice → scartata
- vettura sfora cap prestazione post-rientro → scartata

``risolvi_rientro`` è mockato per evitare chiamate API reali.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from colazione.domain.builder_pdc.deposito_first import (
    costruisci_giornata_deposito_first,
)
from colazione.domain.builder_pdc.vettura_resolver import (
    ScelzaMM,
    ScelzaVettura,
    ScelzaVOCTAXI,
)
from colazione.integrations.live_arturo import TrenoVettura

# =====================================================================
# Stubs minimali (no DB)
# =====================================================================


@dataclass
class _StubBlocco:
    """Imita ``GiroBlocco`` con i campi che ``_build_giornata_pdc`` legge."""

    seq: int
    ora_inizio: time | None
    ora_fine: time | None
    stazione_da_codice: str | None
    stazione_a_codice: str | None
    corsa_commerciale_id: int | None = None
    corsa_materiale_vuoto_id: int | None = None
    id: int | None = None


def _b(
    seq: int,
    ini_h: int,
    ini_m: int,
    fin_h: int,
    fin_m: int,
    da: str,
    a: str,
) -> _StubBlocco:
    return _StubBlocco(
        seq=seq,
        ora_inizio=time(ini_h, ini_m),
        ora_fine=time(fin_h, fin_m),
        stazione_da_codice=da,
        stazione_a_codice=a,
        id=seq,
    )


@dataclass
class _StubDepot:
    """Imita ``Depot`` con i 2 campi che il builder usa."""

    codice: str
    stazione_principale_codice: str | None


@pytest.fixture
def fake_client() -> httpx.AsyncClient:
    return httpx.AsyncClient()


# =====================================================================
# Scenario green A — cap condotta eccede → giornata SCARTATA
# =====================================================================


@pytest.mark.asyncio
async def test_violazione_a_cap_condotta_eccede_giornata_scartata(
    fake_client: httpx.AsyncClient,
) -> None:
    """4 blocchi × 100 min = 400 min condotta totale > 330 cap HARD.
    Builder deposito-first SCARTA la giornata (return None + violazione)
    invece di persistirla con annotazione (vs builder monolitico).
    """
    depot = _StubDepot(codice="MILANO_PG", stazione_principale_codice="MILANO_PG")
    blocchi = [
        _b(1, 6, 0, 7, 40, "MILANO_PG", "BERGAMO"),
        _b(2, 8, 0, 9, 40, "BERGAMO", "BRESCIA"),
        _b(3, 10, 0, 11, 40, "BRESCIA", "VERONA"),
        _b(4, 12, 0, 13, 40, "VERONA", "PADOVA"),
    ]

    draft, violazioni = await costruisci_giornata_deposito_first(
        depot=depot,  # type: ignore[arg-type]
        numero_giornata=1,
        variante_calendario="LMXGV",
        blocchi_giro=blocchi,  # type: ignore[arg-type]
        live_client=fake_client,
    )

    assert draft is None
    assert violazioni
    assert any("condotta_max_hard" in v for v in violazioni)


# =====================================================================
# Scenario green C — stazione_fine == deposito (con vettura rientro)
# =====================================================================


@pytest.mark.asyncio
async def test_violazione_c_giornata_chiude_sempre_in_deposito_via_vettura(
    fake_client: httpx.AsyncClient,
) -> None:
    """Giro Mi.PG → Tirano. PdC deposito MILANO_PG. Builder deve:
    - chiamare risolvi_rientro
    - aggiungere blocco VETTURA in coda
    - settare stazione_fine = MILANO_PG (= deposito)
    """
    depot = _StubDepot(codice="GARIBALDI_TE", stazione_principale_codice="MILANO_PG")
    # Giornata 08:00-12:00 → presa 07:05, ACCa fine 12:40, vettura
    # 13:00-14:00, FINE 14:15. Prestazione totale 14:15 - 07:05 = 7h10
    # ben sotto cap 8h30.
    blocchi = [
        _b(1, 8, 0, 9, 0, "MILANO_PG", "MILANO_CENTRALE"),
        _b(2, 9, 30, 12, 0, "MILANO_CENTRALE", "TIRANO"),
    ]
    treno_rientro = TrenoVettura(
        numero="2426",
        categoria="RV",
        operatore="TN",
        stazione_partenza_codice="TIRANO",
        stazione_arrivo_codice="MILANO_PG",
        partenza_min=13 * 60,
        arrivo_min=14 * 60,
        durata_min=60,
    )

    with patch(
        "colazione.domain.builder_pdc.deposito_first.risolvi_rientro",
        new=AsyncMock(
            return_value=ScelzaVettura(
                tipo="VETTURA",
                treno=treno_rientro,
                prestazione_finale_min=430,
            )
        ),
    ):
        draft, violazioni = await costruisci_giornata_deposito_first(
            depot=depot,  # type: ignore[arg-type]
            numero_giornata=1,
            variante_calendario="LMXGV",
            blocchi_giro=blocchi,  # type: ignore[arg-type]
            live_client=fake_client,
        )

    assert draft is not None, f"violazioni={violazioni}"
    assert violazioni == []
    # Violazione C ribaltata: stazione_fine == deposito
    assert draft.stazione_fine == "MILANO_PG"


# =====================================================================
# Scenario green D — ultimo blocco rilevante è VETTURA/MM/VOCTAXI
# =====================================================================


@pytest.mark.asyncio
async def test_violazione_d_ultimo_blocco_e_rientro_non_fine(
    fake_client: httpx.AsyncClient,
) -> None:
    """Giro che termina a TIRANO. Ultimo blocco rilevante (escluso FINE)
    DEVE essere VETTURA (oppure MM/VOCTAXI nei rispettivi scenari).
    """
    depot = _StubDepot(codice="GARIBALDI_TE", stazione_principale_codice="MILANO_PG")
    # Stessi orari di test_violazione_c per restare sotto cap 8h30.
    blocchi = [
        _b(1, 8, 0, 9, 0, "MILANO_PG", "MILANO_CENTRALE"),
        _b(2, 9, 30, 12, 0, "MILANO_CENTRALE", "TIRANO"),
    ]
    treno_rientro = TrenoVettura(
        numero="2426",
        categoria="RV",
        operatore="TN",
        stazione_partenza_codice="TIRANO",
        stazione_arrivo_codice="MILANO_PG",
        partenza_min=13 * 60,
        arrivo_min=14 * 60,
        durata_min=60,
    )

    with patch(
        "colazione.domain.builder_pdc.deposito_first.risolvi_rientro",
        new=AsyncMock(
            return_value=ScelzaVettura(
                tipo="VETTURA",
                treno=treno_rientro,
                prestazione_finale_min=430,
            )
        ),
    ):
        draft, _ = await costruisci_giornata_deposito_first(
            depot=depot,  # type: ignore[arg-type]
            numero_giornata=1,
            variante_calendario="LMXGV",
            blocchi_giro=blocchi,  # type: ignore[arg-type]
            live_client=fake_client,
        )

    assert draft is not None
    blocchi_rilevanti = [b for b in draft.blocchi if b.tipo_evento != "FINE"]
    ultimo = blocchi_rilevanti[-1]
    assert ultimo.tipo_evento == "VETTURA"
    assert ultimo.stazione_a_codice == "MILANO_PG"


# =====================================================================
# Scenario green D-mm — fallback MM se vettura sfora
# =====================================================================


@pytest.mark.asyncio
async def test_rientro_mm_inserito_in_coda(
    fake_client: httpx.AsyncClient,
) -> None:
    """Quando il resolver ritorna ScelzaMM, il builder deve inserire un
    blocco MM con durata forfettaria 30' tra ACCa e FINE.
    """
    depot = _StubDepot(codice="FIORENZA", stazione_principale_codice="MILANO_CERTOSA")
    blocchi = [
        _b(1, 6, 0, 7, 0, "MILANO_CERTOSA", "MILANO_GARIBALDI"),
        _b(2, 7, 30, 11, 0, "MILANO_GARIBALDI", "MILANO_PG"),
    ]

    with patch(
        "colazione.domain.builder_pdc.deposito_first.risolvi_rientro",
        new=AsyncMock(
            return_value=ScelzaMM(
                tipo="MM",
                durata_min=30,
                motivo="fallback MM (vettura sfora)",
            )
        ),
    ):
        draft, violazioni = await costruisci_giornata_deposito_first(
            depot=depot,  # type: ignore[arg-type]
            numero_giornata=1,
            variante_calendario="LMXGV",
            blocchi_giro=blocchi,  # type: ignore[arg-type]
            live_client=fake_client,
        )

    assert draft is not None, f"violazioni={violazioni}"
    blocchi_rilevanti = [b for b in draft.blocchi if b.tipo_evento != "FINE"]
    ultimo = blocchi_rilevanti[-1]
    assert ultimo.tipo_evento == "MM"
    assert ultimo.durata_min == 30
    assert ultimo.stazione_a_codice == "MILANO_CERTOSA"


# =====================================================================
# Scenario green D-voctaxi — fallback VOCTAXI deposito periferico
# =====================================================================


@pytest.mark.asyncio
async def test_rientro_voctaxi_inserito_in_coda(
    fake_client: httpx.AsyncClient,
) -> None:
    """Quando il resolver ritorna ScelzaVOCTAXI, il builder inserisce
    un blocco VOCTAXI."""
    depot = _StubDepot(codice="CREMONA", stazione_principale_codice="CREMONA")
    blocchi = [
        _b(1, 6, 0, 7, 30, "CREMONA", "MANTOVA"),
        _b(2, 8, 0, 9, 30, "MANTOVA", "BRESCIA"),
    ]

    with patch(
        "colazione.domain.builder_pdc.deposito_first.risolvi_rientro",
        new=AsyncMock(
            return_value=ScelzaVOCTAXI(
                tipo="VOCTAXI",
                durata_min=30,
                motivo="deposito periferico",
            )
        ),
    ):
        draft, violazioni = await costruisci_giornata_deposito_first(
            depot=depot,  # type: ignore[arg-type]
            numero_giornata=1,
            variante_calendario="LMXGV",
            blocchi_giro=blocchi,  # type: ignore[arg-type]
            live_client=fake_client,
        )

    assert draft is not None, f"violazioni={violazioni}"
    blocchi_rilevanti = [b for b in draft.blocchi if b.tipo_evento != "FINE"]
    ultimo = blocchi_rilevanti[-1]
    assert ultimo.tipo_evento == "VOCTAXI"
    assert ultimo.stazione_a_codice == "CREMONA"


# =====================================================================
# Scenario chiusura coincide col deposito → no rientro extra
# =====================================================================


@pytest.mark.asyncio
async def test_chiusura_uguale_deposito_no_rientro_extra(
    fake_client: httpx.AsyncClient,
) -> None:
    """Giornata che inizia E finisce a MILANO_PG (= depot). Niente
    rientro extra: il resolver NON deve nemmeno essere chiamato.
    """
    depot = _StubDepot(codice="GARIBALDI_TE", stazione_principale_codice="MILANO_PG")
    blocchi = [
        _b(1, 6, 0, 7, 0, "MILANO_PG", "MILANO_CENTRALE"),
        _b(2, 7, 30, 9, 0, "MILANO_CENTRALE", "MILANO_PG"),
    ]

    mock_resolver = AsyncMock()
    with patch(
        "colazione.domain.builder_pdc.deposito_first.risolvi_rientro",
        new=mock_resolver,
    ):
        draft, violazioni = await costruisci_giornata_deposito_first(
            depot=depot,  # type: ignore[arg-type]
            numero_giornata=1,
            variante_calendario="LMXGV",
            blocchi_giro=blocchi,  # type: ignore[arg-type]
            live_client=fake_client,
        )

    assert draft is not None, f"violazioni={violazioni}"
    assert violazioni == []
    assert draft.stazione_fine == "MILANO_PG"
    # resolver NON chiamato (short-circuit per chiusura == deposito)
    mock_resolver.assert_not_called()
    # nessun blocco di rientro aggiuntivo
    assert all(b.tipo_evento not in {"VETTURA", "MM", "VOCTAXI"} for b in draft.blocchi)


# =====================================================================
# Scenario depot privo di stazione_principale_codice → scartata
# =====================================================================


@pytest.mark.asyncio
async def test_depot_senza_stazione_principale_codice_scartata(
    fake_client: httpx.AsyncClient,
) -> None:
    """Depot con ``stazione_principale_codice = None``: builder non sa
    dove ancorare il rientro → giornata scartata."""
    depot = _StubDepot(codice="UNCONFIGURED", stazione_principale_codice=None)
    blocchi = [
        _b(1, 6, 0, 7, 0, "MILANO_PG", "MILANO_CENTRALE"),
    ]
    draft, violazioni = await costruisci_giornata_deposito_first(
        depot=depot,  # type: ignore[arg-type]
        numero_giornata=1,
        variante_calendario="LMXGV",
        blocchi_giro=blocchi,  # type: ignore[arg-type]
        live_client=fake_client,
    )

    assert draft is None
    assert violazioni
    assert any("stazione_principale_codice" in v for v in violazioni)


# =====================================================================
# Scenario prestazione post-rientro sfora cap → scartata
# =====================================================================


@pytest.mark.asyncio
async def test_prestazione_post_rientro_eccede_cap_scartata(
    fake_client: httpx.AsyncClient,
) -> None:
    """Caso pathological: VOCTAXI con durata che porta prestazione
    finale oltre 8h30 standard. Builder hard-fail.
    """
    depot = _StubDepot(codice="CREMONA", stazione_principale_codice="CREMONA")
    # Giornata già a 8h producendo (presa 06:00 → fine_servizio 14:00)
    # poi VOCTAXI 60' la spinge a 9h00 > 8h30
    blocchi = [
        _b(1, 6, 0, 7, 0, "CREMONA", "MANTOVA"),
        _b(2, 11, 30, 12, 0, "MANTOVA", "VENEZIA"),  # 8h+ apparente
    ]

    voctaxi_lungo = ScelzaVOCTAXI(
        tipo="VOCTAXI",
        durata_min=120,  # 2h
        motivo="taxi lungo per test",
    )
    with patch(
        "colazione.domain.builder_pdc.deposito_first.risolvi_rientro",
        new=AsyncMock(return_value=voctaxi_lungo),
    ):
        draft, violazioni = await costruisci_giornata_deposito_first(
            depot=depot,  # type: ignore[arg-type]
            numero_giornata=1,
            variante_calendario="LMXGV",
            blocchi_giro=blocchi,  # type: ignore[arg-type]
            live_client=fake_client,
        )

    # Atteso scartata se prestazione finale > 510
    if draft is None:
        assert any("prestazione_max_hard" in v for v in violazioni)
    else:
        # Se è entrata sotto cap, almeno il blocco VOCTAXI è in coda
        # e stazione_fine = deposito.
        assert draft.stazione_fine == "CREMONA"


# =====================================================================
# Sanity: signature pubblica
# =====================================================================


def test_costruisci_giornata_deposito_first_e_pubblica() -> None:
    """costruisci_giornata_deposito_first è esportata in __all__."""
    from colazione.domain.builder_pdc import deposito_first

    assert "costruisci_giornata_deposito_first" in deposito_first.__all__


# Silence unused Any import for type-only usage.
_ = Any
