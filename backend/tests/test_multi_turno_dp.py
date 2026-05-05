"""Test unit Sprint 7.10 MR α.2 — DP segmentazione multi-turno.

Coverage delle funzioni pure di ``multi_turno.py``:

- ``_dp_segmenta_giornata`` — DP locale per giornata-giro
- ``_scegli_deposito_per_segmento`` — heuristic post-DP

Niente DB: i test costruiscono ``GiroBlocco`` unbound (objects ORM
non in sessione) e ``Depot`` in-memory.
"""

from __future__ import annotations

from datetime import time
from typing import Any

import httpx
import pytest

from colazione.domain.builder_pdc.multi_turno import (
    _dp_segmenta_giornata,
    _scegli_deposito_per_segmento,
)
from colazione.models.anagrafica import Depot
from colazione.models.giri import GiroBlocco


def _make_blocco(
    *,
    seq: int,
    da: str,
    a: str,
    inizio: time,
    fine: time,
    blocco_id: int = 0,
) -> GiroBlocco:
    """Costruisce un GiroBlocco in-memory (no DB) per i test."""
    b = GiroBlocco(
        seq=seq,
        tipo_blocco="commerciale",
        stazione_da_codice=da,
        stazione_a_codice=a,
        ora_inizio=inizio,
        ora_fine=fine,
        giro_variante_id=1,
    )
    b.id = blocco_id or seq
    return b


def _make_depot(codice: str, stazione_principale: str | None) -> Depot:
    d = Depot(
        codice=codice,
        display_name=codice,
        azienda_id=1,
        tipi_personale_ammessi="PdC",
        is_attivo=True,
        stazione_principale_codice=stazione_principale,
    )
    d.id = hash(codice) % 100000
    return d


# =====================================================================
# _dp_segmenta_giornata
# =====================================================================


def test_dp_giornata_breve_un_solo_segmento() -> None:
    """Giornata da 4h totali entro cap → 1 segmento (no split)."""
    blocchi = [
        _make_blocco(seq=1, da="A", a="B", inizio=time(8, 0), fine=time(10, 0)),
        _make_blocco(seq=2, da="B", a="A", inizio=time(10, 30), fine=time(12, 0)),
    ]
    result = _dp_segmenta_giornata(blocchi, stazioni_cv={"A", "B"})
    # Anche se A e B sono entrambi CV ammessi, il DP minimizza il
    # numero di segmenti → 1 segmento, non 2.
    assert result == [(0, 1)]


def test_dp_giornata_eccede_cap_con_split_valido() -> None:
    """Giornata di 8 corse da 1h30 ciascuna (12h condotta totale ben oltre
    cap 5h30): se la stazione intermedia D è CV, deve splittare in più
    segmenti, ognuno entro cap."""
    # 8 corse da 90 min con 10 min di gap fra consecutive → ~13h totali.
    blocchi: list[GiroBlocco] = []
    minuto = 5 * 60  # parte alle 05:00
    stazioni_seq = ["A", "B", "C", "D", "C", "D", "C", "D", "A"]
    for i in range(8):
        h_start = minuto // 60
        m_start = minuto % 60
        durata = 90
        h_end = (minuto + durata) // 60
        m_end = (minuto + durata) % 60
        blocchi.append(
            _make_blocco(
                seq=i + 1,
                da=stazioni_seq[i],
                a=stazioni_seq[i + 1],
                inizio=time(h_start % 24, m_start),
                fine=time(h_end % 24, m_end),
                blocco_id=i + 1,
            )
        )
        minuto += durata + 10

    # Solo la stazione D è ammessa come CV (= unica anchor possibile
    # dopo il blocco 0 che è sempre anchor).
    result = _dp_segmenta_giornata(blocchi, stazioni_cv={"D"})
    # Con cap condotta 5h30 e 8 corse da 1h30 → max ~3 corse per
    # segmento → almeno 3 segmenti.
    assert result is not None
    assert len(result) >= 3
    # Copertura completa, no overlap, ordinata.
    for k, (start, end) in enumerate(result):
        assert start <= end
        if k > 0:
            assert start == result[k - 1][1] + 1
    assert result[0][0] == 0
    assert result[-1][1] == 7


def test_dp_giornata_eccede_cap_nessun_cv_ritorna_none() -> None:
    """Giornata fuori cap MA nessuna stazione CV → impossibile segmentare,
    ritorna None (fallback al monolitico fuori cap nel chiamante)."""
    # 4 corse da 100 min con gap 30 min → ~9h totali, > cap 5h30 condotta.
    blocchi = [
        _make_blocco(seq=1, da="A", a="B", inizio=time(5, 0), fine=time(6, 40)),
        _make_blocco(seq=2, da="B", a="C", inizio=time(7, 10), fine=time(8, 50)),
        _make_blocco(seq=3, da="C", a="D", inizio=time(9, 20), fine=time(11, 0)),
        _make_blocco(seq=4, da="D", a="E", inizio=time(11, 30), fine=time(13, 10)),
    ]
    # Nessuna stazione in CV → l'unica anchor possibile è il blocco 0
    # (= primo blocco della giornata). Quindi l'unico segmento candidato
    # è [0..3] interno, che eccede cap → DP ritorna None.
    result = _dp_segmenta_giornata(blocchi, stazioni_cv=set())
    assert result is None


def test_dp_giornata_vuota() -> None:
    assert _dp_segmenta_giornata([], stazioni_cv={"A"}) == []


def test_dp_giornata_un_solo_blocco_entro_cap() -> None:
    blocchi = [
        _make_blocco(seq=1, da="A", a="B", inizio=time(8, 0), fine=time(10, 0)),
    ]
    assert _dp_segmenta_giornata(blocchi, stazioni_cv=set()) == [(0, 0)]


# =====================================================================
# _scegli_deposito_per_segmento
# =====================================================================


# Sprint 7.10 MR α.5.fix: la heuristic deposito è ora async e
# include un quality gate VETTURA (= depot accettato solo se chiude
# in casa OR esiste treno passante per il rientro). Test usano
# httpx.MockTransport per simulare l'API live arturo.


def _empty_response_handler(request: httpx.Request) -> httpx.Response:
    """Handler MockTransport: API live ritorna lista vuota → niente
    vettura mai trovata. Usato quando il test si concentra sulla
    Strategia 1 (chiusura in casa, no API call)."""
    return httpx.Response(200, json=[])


def _build_handler_with_treno(
    *,
    stazione_partenza: str,
    stazione_arrivo: str,
    partenza_iso: str,
    arrivo_iso: str,
):
    """Costruisce un handler MockTransport che ritorna 1 treno
    matching (stazione_partenza, stazione_arrivo) negli orari dati."""

    def handler(request: httpx.Request) -> httpx.Response:
        if f"/api/partenze/{stazione_partenza}" not in request.url.path:
            return httpx.Response(200, json=[])
        return httpx.Response(
            200,
            json=[
                {
                    "numero": "9999",
                    "categoria": "REG",
                    "operatore": "TRENORD",
                    "fermate": [
                        {
                            "stazione_id": stazione_partenza,
                            "programmato_partenza": partenza_iso,
                            "programmato_arrivo": None,
                        },
                        {
                            "stazione_id": stazione_arrivo,
                            "programmato_partenza": None,
                            "programmato_arrivo": arrivo_iso,
                        },
                    ],
                },
            ],
        )

    return handler


@pytest.mark.asyncio
async def test_scegli_depot_casa_casa_no_api_call() -> None:
    """Sprint 7.10 MR α.8: scenario "casa-casa". Apertura == chiusura
    == depot → no vetture, no dormite."""
    blocchi = [
        _make_blocco(seq=1, da="VOG", a="VOG", inizio=time(8, 0), fine=time(10, 0)),
    ]
    depositi = [_make_depot("VOGHERA", "VOG")]
    transport = httpx.MockTransport(_empty_response_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        h = await _scegli_deposito_per_segmento(
            blocchi,
            depositi,
            ora_apertura_min=7 * 60,
            ora_chiusura_min=11 * 60,
            live_client=client,
        )
    assert h is not None
    assert h.depot.codice == "VOGHERA"
    assert h.vettura_partenza is None
    assert h.vettura_rientro is None
    assert h.dormita_partenza is False
    assert h.dormita_rientro is False


@pytest.mark.asyncio
async def test_scegli_depot_chiusura_in_casa_lontano_apertura_dormita() -> None:
    """Sprint 7.10 MR α.8 — il caso del bug utente VC/Alessandria.

    Segmento parte da VC (Vercelli, NON depot) e chiude ad ALES
    (depot ALESSANDRIA). Strategia "lontano-casa": serve vettura
    PARTENZA ALES→VC. Se nessuna vettura mattutina disponibile,
    DORMITA all'inizio (PdC arrivato la sera prima a Vercelli)."""
    blocchi = [
        _make_blocco(seq=1, da="VC", a="ALES", inizio=time(5, 5), fine=time(11, 0)),
    ]
    depositi = [_make_depot("ALESSANDRIA", "ALES")]
    # API ritorna lista vuota → nessuna vettura ALES→VC.
    transport = httpx.MockTransport(_empty_response_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        h = await _scegli_deposito_per_segmento(
            blocchi,
            depositi,
            ora_apertura_min=4 * 60 + 10,  # presa = 04:10
            ora_chiusura_min=11 * 60 + 55,
            live_client=client,
        )
    assert h is not None
    assert h.depot.codice == "ALESSANDRIA"
    # Vettura partenza non trovata → DORMITA partenza.
    assert h.vettura_partenza is None
    assert h.dormita_partenza is True
    # Chiusura in casa, nessuna vettura/dormita rientro serve.
    assert h.vettura_rientro is None
    assert h.dormita_rientro is False


@pytest.mark.asyncio
async def test_scegli_depot_dormita_con_treno_serale() -> None:
    """Sprint 7.10 MR α.8.1: nel caso DORMITA partenza, se esiste un
    treno serale del giorno prima (>= 19:00) che porta dal depot alla
    stazione di apertura, lo includiamo come `vettura_partenza`
    insieme al flag `dormita_partenza=True`.

    Decisione utente 2026-05-05: *"puoi anche mettere un treno che
    termina nella località di dormita. Certo non metterlo alle 17"*.

    Configuro il MockTransport in modo che la vettura mattutina NON
    esista (lista vuota per la fascia mattutina) ma il treno serale
    sì (>= 19:00). Il parser MockTransport è il `_build_handler_with_treno`
    standard che non distingue ora_min_partenza nel handler — quindi
    il test mostra che con un treno alle 20:00 vince come "serale".
    """
    blocchi = [
        _make_blocco(seq=1, da="VC", a="ALES", inizio=time(5, 5), fine=time(11, 0)),
    ]
    depositi = [_make_depot("ALESSANDRIA", "ALES")]
    # Treno serale ALES → VC alle 20:00, arriva a VC alle 21:00.
    handler = _build_handler_with_treno(
        stazione_partenza="ALES",
        stazione_arrivo="VC",
        partenza_iso="2026-05-05T20:00:00Z",
        arrivo_iso="2026-05-05T21:00:00Z",
    )
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        h = await _scegli_deposito_per_segmento(
            blocchi,
            depositi,
            ora_apertura_min=4 * 60 + 10,  # presa = 04:10
            ora_chiusura_min=11 * 60 + 55,
            live_client=client,
        )
    assert h is not None
    assert h.depot.codice == "ALESSANDRIA"
    # La vettura mattutina (arrivo entro 04:10-5min) non c'è perché
    # il treno parte alle 20:00 → margine fuori, scartato.
    # Ma il treno serale viene trovato come fallback.
    assert h.vettura_partenza is not None
    assert h.vettura_partenza.partenza_min == 20 * 60
    assert h.vettura_partenza.arrivo_min == 21 * 60
    # E comunque DORMITA: il PdC dorme la notte a VC.
    assert h.dormita_partenza is True


@pytest.mark.asyncio
async def test_scegli_depot_lontano_casa_con_vettura_partenza() -> None:
    """Variante del precedente: la vettura ALES→VC ESISTE in finestra,
    quindi `vettura_partenza` valorizzata e niente DORMITA."""
    blocchi = [
        _make_blocco(seq=1, da="VC", a="ALES", inizio=time(8, 0), fine=time(11, 0)),
    ]
    depositi = [_make_depot("ALESSANDRIA", "ALES")]
    handler = _build_handler_with_treno(
        stazione_partenza="ALES",
        stazione_arrivo="VC",
        partenza_iso="2026-05-05T05:30:00Z",
        arrivo_iso="2026-05-05T06:30:00Z",
    )
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        h = await _scegli_deposito_per_segmento(
            blocchi,
            depositi,
            ora_apertura_min=7 * 60 + 5,  # presa = 07:05
            ora_chiusura_min=12 * 60,
            live_client=client,
        )
    assert h is not None
    assert h.depot.codice == "ALESSANDRIA"
    assert h.vettura_partenza is not None
    assert h.vettura_partenza.partenza_min == 5 * 60 + 30
    assert h.vettura_partenza.arrivo_min == 6 * 60 + 30
    assert h.dormita_partenza is False


@pytest.mark.asyncio
async def test_scegli_depot_casa_lontano_con_vettura_rientro() -> None:
    """Scenario "casa-lontano": apertura == depot, chiusura ≠ depot.
    Vettura RIENTRO trovata → ok."""
    blocchi = [
        _make_blocco(seq=1, da="ALES", a="X", inizio=time(8, 0), fine=time(10, 0)),
    ]
    depositi = [_make_depot("ALESSANDRIA", "ALES")]
    handler = _build_handler_with_treno(
        stazione_partenza="X",
        stazione_arrivo="ALES",
        partenza_iso="2026-05-05T11:30:00Z",  # dopo ora_chiusura+5
        arrivo_iso="2026-05-05T12:30:00Z",
    )
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        h = await _scegli_deposito_per_segmento(
            blocchi,
            depositi,
            ora_apertura_min=7 * 60 + 5,
            ora_chiusura_min=10 * 60 + 55,
            live_client=client,
        )
    assert h is not None
    assert h.depot.codice == "ALESSANDRIA"
    # Apertura == depot, niente vettura partenza.
    assert h.vettura_partenza is None
    assert h.dormita_partenza is False
    # Chiusura ≠ depot, vettura rientro trovata.
    assert h.vettura_rientro is not None


@pytest.mark.asyncio
async def test_scegli_depot_lista_depositi_vuota() -> None:
    blocchi = [
        _make_blocco(seq=1, da="A", a="B", inizio=time(8, 0), fine=time(10, 0)),
    ]
    transport = httpx.MockTransport(_empty_response_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        h = await _scegli_deposito_per_segmento(
            blocchi,
            [],
            ora_apertura_min=7 * 60,
            ora_chiusura_min=11 * 60,
            live_client=client,
        )
    assert h is None


@pytest.mark.asyncio
async def test_scegli_depot_blocchi_vuoti() -> None:
    depositi = [_make_depot("ALESSANDRIA", "ALES")]
    transport = httpx.MockTransport(_empty_response_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        h = await _scegli_deposito_per_segmento(
            [],
            depositi,
            ora_apertura_min=0,
            ora_chiusura_min=0,
            live_client=client,
        )
    assert h is None


@pytest.mark.asyncio
async def test_scegli_depot_ignora_depositi_senza_stazione_principale() -> None:
    """Depot con stazione_principale_codice = None viene saltato."""
    blocchi = [
        _make_blocco(seq=1, da="ALES", a="VOG", inizio=time(8, 0), fine=time(10, 0)),
    ]
    depositi = [
        _make_depot("ALESSANDRIA", None),  # stazione NULL → escluso
        _make_depot("VOGHERA", "VOG"),
    ]
    transport = httpx.MockTransport(_empty_response_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        h = await _scegli_deposito_per_segmento(
            blocchi,
            depositi,
            ora_apertura_min=7 * 60 + 5,
            ora_chiusura_min=10 * 60 + 55,
            live_client=client,
        )
    # VOGHERA = stazione_a (chiusura), Strategia 1 vince.
    assert h is not None
    assert h.depot.codice == "VOGHERA"
    assert h.vettura_partenza is None
    assert h.vettura_rientro is None
