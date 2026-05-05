"""Test unit Sprint 7.10 MR α.5 — client live.arturo.travel.

Coverage:

- ``_estrai_candidato`` (parser pure delle response /api/partenze)
- ``_hhmm_to_min`` (parsing orari ISO/HH:MM)
- ``trova_treno_vettura`` con ``httpx.MockTransport``: scenari
  "treno trovato", "nessun passante", "API down", "JSON malformato".

Niente DB, niente network esterno.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from colazione.integrations.live_arturo import (
    TrenoVettura,
    _estrai_candidato,
    _hhmm_to_min,
    trova_treno_vettura,
)


# =====================================================================
# _hhmm_to_min
# =====================================================================


def test_hhmm_to_min_iso_z() -> None:
    """Sprint 7.10 MR α.5: parsing ISO con Z."""
    assert _hhmm_to_min("2026-05-05T11:48:00Z") == 11 * 60 + 48


def test_hhmm_to_min_iso_offset() -> None:
    assert _hhmm_to_min("2026-05-05T11:48:00+02:00") == 11 * 60 + 48


def test_hhmm_to_min_hh_mm() -> None:
    assert _hhmm_to_min("11:48") == 11 * 60 + 48


def test_hhmm_to_min_hh_mm_ss() -> None:
    assert _hhmm_to_min("11:48:00") == 11 * 60 + 48


def test_hhmm_to_min_none_o_malformato() -> None:
    assert _hhmm_to_min(None) is None
    assert _hhmm_to_min("") is None
    assert _hhmm_to_min("foo") is None


# =====================================================================
# _estrai_candidato
# =====================================================================


def _make_treno(
    *,
    numero: str = "2814",
    fermate: list[dict[str, Any]],
    categoria: str = "REG",
    operatore: str | None = "TRENORD",
) -> dict[str, Any]:
    return {
        "numero": numero,
        "categoria": categoria,
        "operatore": operatore,
        "fermate": fermate,
    }


def test_estrai_candidato_trovato_partenza_arrivo_in_finestra() -> None:
    """Treno parte da S01700 alle 12:00, ferma a S01520 alle 13:00:
    se il PdC chiude alle 11:50 in S01700, è candidato (attesa 10min)."""
    treno = _make_treno(
        fermate=[
            {"stazione_id": "S01700", "programmato_partenza": "2026-05-05T12:00:00Z", "programmato_arrivo": None},
            {"stazione_id": "S01520", "programmato_partenza": "2026-05-05T13:00:00Z", "programmato_arrivo": "2026-05-05T13:00:00Z"},
        ],
    )
    cand = _estrai_candidato(
        treno,
        stazione_partenza_codice="S01700",
        stazione_arrivo_codice="S01520",
        ora_min_partenza=11 * 60 + 50,
        max_attesa_min=120,
    )
    assert cand is not None
    assert cand.numero == "2814"
    assert cand.partenza_min == 12 * 60
    assert cand.arrivo_min == 13 * 60
    assert cand.durata_min == 60
    assert cand.stazione_partenza_codice == "S01700"
    assert cand.stazione_arrivo_codice == "S01520"


def test_estrai_candidato_attesa_oltre_max() -> None:
    """Treno parte alle 14:00 ma il PdC chiude alle 11:00: attesa 180min,
    sopra max 120 → scartato."""
    treno = _make_treno(
        fermate=[
            {"stazione_id": "S01700", "programmato_partenza": "2026-05-05T14:00:00Z", "programmato_arrivo": None},
            {"stazione_id": "S01520", "programmato_partenza": "2026-05-05T15:00:00Z", "programmato_arrivo": "2026-05-05T15:00:00Z"},
        ],
    )
    assert _estrai_candidato(
        treno,
        stazione_partenza_codice="S01700",
        stazione_arrivo_codice="S01520",
        ora_min_partenza=11 * 60,
        max_attesa_min=120,
    ) is None


def test_estrai_candidato_arrivo_non_servito() -> None:
    """Il treno parte da S01700 ma NON ferma a S01520 → scartato."""
    treno = _make_treno(
        fermate=[
            {"stazione_id": "S01700", "programmato_partenza": "2026-05-05T12:00:00Z", "programmato_arrivo": None},
            {"stazione_id": "S99999", "programmato_partenza": None, "programmato_arrivo": "2026-05-05T13:00:00Z"},
        ],
    )
    assert _estrai_candidato(
        treno,
        stazione_partenza_codice="S01700",
        stazione_arrivo_codice="S01520",
        ora_min_partenza=11 * 60 + 50,
        max_attesa_min=120,
    ) is None


def test_estrai_candidato_arrivo_prima_di_partenza() -> None:
    """Edge case: la fermata di arrivo cercata è prima di partenza nella
    sequenza → non valido (il treno è in direzione opposta)."""
    treno = _make_treno(
        fermate=[
            {"stazione_id": "S01520", "programmato_partenza": "2026-05-05T11:30:00Z", "programmato_arrivo": "2026-05-05T11:30:00Z"},
            {"stazione_id": "S01700", "programmato_partenza": "2026-05-05T12:00:00Z", "programmato_arrivo": None},
        ],
    )
    assert _estrai_candidato(
        treno,
        stazione_partenza_codice="S01700",
        stazione_arrivo_codice="S01520",
        ora_min_partenza=11 * 60 + 50,
        max_attesa_min=120,
    ) is None


def test_estrai_candidato_fermate_vuote() -> None:
    treno = {"numero": "1", "categoria": "REG", "operatore": "X", "fermate": []}
    assert _estrai_candidato(
        treno,
        stazione_partenza_codice="S01700",
        stazione_arrivo_codice="S01520",
        ora_min_partenza=12 * 60,
        max_attesa_min=120,
    ) is None


# =====================================================================
# trova_treno_vettura — integration con MockTransport
# =====================================================================


@pytest.mark.asyncio
async def test_trova_treno_vettura_sceglie_partenza_piu_imminente() -> None:
    """Più candidati → vince quello con partenza_min minore."""
    response_data = [
        _make_treno(
            numero="LATE",
            fermate=[
                {"stazione_id": "S01700", "programmato_partenza": "2026-05-05T13:00:00Z", "programmato_arrivo": None},
                {"stazione_id": "S01520", "programmato_partenza": None, "programmato_arrivo": "2026-05-05T14:00:00Z"},
            ],
        ),
        _make_treno(
            numero="EARLY",
            fermate=[
                {"stazione_id": "S01700", "programmato_partenza": "2026-05-05T12:15:00Z", "programmato_arrivo": None},
                {"stazione_id": "S01520", "programmato_partenza": None, "programmato_arrivo": "2026-05-05T13:00:00Z"},
            ],
        ),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/partenze/S01700"
        return httpx.Response(200, json=response_data)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        treno = await trova_treno_vettura(
            stazione_partenza_codice="S01700",
            stazione_arrivo_codice="S01520",
            ora_min_partenza=12 * 60,
            client=client,
        )
    assert treno is not None
    assert treno.numero == "EARLY"


@pytest.mark.asyncio
async def test_trova_treno_vettura_nessun_passante() -> None:
    """Lista vuota → None."""
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=[]))
    async with httpx.AsyncClient(transport=transport) as client:
        treno = await trova_treno_vettura(
            stazione_partenza_codice="S01700",
            stazione_arrivo_codice="S01520",
            ora_min_partenza=12 * 60,
            client=client,
        )
    assert treno is None


@pytest.mark.asyncio
async def test_trova_treno_vettura_api_500() -> None:
    """API ritorna 500 → None (non propaga eccezione)."""
    transport = httpx.MockTransport(lambda r: httpx.Response(500, text="boom"))
    async with httpx.AsyncClient(transport=transport) as client:
        treno = await trova_treno_vettura(
            stazione_partenza_codice="S01700",
            stazione_arrivo_codice="S01520",
            ora_min_partenza=12 * 60,
            client=client,
        )
    assert treno is None


@pytest.mark.asyncio
async def test_trova_treno_vettura_json_malformato() -> None:
    """JSON malformato → None."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json", headers={"content-type": "application/json"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        treno = await trova_treno_vettura(
            stazione_partenza_codice="S01700",
            stazione_arrivo_codice="S01520",
            ora_min_partenza=12 * 60,
            client=client,
        )
    assert treno is None


@pytest.mark.asyncio
async def test_trova_treno_vettura_arrivo_non_servito() -> None:
    """Treno c'è ma non passa per la stazione_arrivo_codice → None."""
    response_data = [
        _make_treno(
            fermate=[
                {"stazione_id": "S01700", "programmato_partenza": "2026-05-05T12:00:00Z", "programmato_arrivo": None},
                {"stazione_id": "S99999", "programmato_partenza": None, "programmato_arrivo": "2026-05-05T13:00:00Z"},
            ],
        ),
    ]
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=response_data))
    async with httpx.AsyncClient(transport=transport) as client:
        treno = await trova_treno_vettura(
            stazione_partenza_codice="S01700",
            stazione_arrivo_codice="S01520",
            ora_min_partenza=12 * 60,
            client=client,
        )
    assert treno is None


def test_treno_vettura_dataclass_immutabile() -> None:
    """`TrenoVettura` è frozen (non modificabile dopo costruzione)."""
    t = TrenoVettura(
        numero="1",
        categoria="REG",
        operatore="TRENORD",
        stazione_partenza_codice="A",
        stazione_arrivo_codice="B",
        partenza_min=720,
        arrivo_min=780,
        durata_min=60,
    )
    with pytest.raises(Exception):
        t.numero = "2"  # type: ignore[misc]
