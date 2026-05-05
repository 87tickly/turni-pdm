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
async def test_scegli_depot_chiusura_in_casa_no_api_call() -> None:
    """Strategia 1 (preferenziale): se il segmento chiude in
    una stazione che è deposito → vince senza API call.
    Il PdC va a casa naturalmente, niente vettura serve."""
    import httpx

    blocchi = [
        _make_blocco(seq=1, da="X", a="VOG", inizio=time(8, 0), fine=time(10, 0)),
    ]
    depositi = [
        _make_depot("ALESSANDRIA", "ALES"),
        _make_depot("VOGHERA", "VOG"),
    ]
    transport = httpx.MockTransport(_empty_response_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        chosen, vettura = await _scegli_deposito_per_segmento(
            blocchi, depositi, ora_chiusura_min=11 * 60, live_client=client
        )
    assert chosen is not None
    assert chosen.codice == "VOGHERA"
    assert vettura is None  # niente vettura: PdC chiude in casa


@pytest.mark.asyncio
async def test_scegli_depot_partenza_con_vettura_disponibile() -> None:
    """Strategia 2: il segmento chiude in stazione X (non depot),
    ma una vettura è disponibile dalla X al deposito di partenza
    → quel depot vince con la vettura allegata."""
    import httpx

    blocchi = [
        _make_blocco(seq=1, da="ALES", a="X", inizio=time(8, 0), fine=time(10, 0)),
    ]
    depositi = [
        _make_depot("ALESSANDRIA", "ALES"),
    ]
    handler = _build_handler_with_treno(
        stazione_partenza="X",
        stazione_arrivo="ALES",
        partenza_iso="2026-05-05T10:30:00Z",
        arrivo_iso="2026-05-05T11:30:00Z",
    )
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        chosen, vettura = await _scegli_deposito_per_segmento(
            blocchi, depositi, ora_chiusura_min=10 * 60, live_client=client
        )
    assert chosen is not None
    assert chosen.codice == "ALESSANDRIA"
    assert vettura is not None
    assert vettura.numero == "9999"
    assert vettura.partenza_min == 10 * 60 + 30
    assert vettura.arrivo_min == 11 * 60 + 30


@pytest.mark.asyncio
async def test_scegli_depot_partenza_senza_vettura_scartato() -> None:
    """Sprint 7.10 MR α.5.fix: il bug dell'utente.

    Segmento parte da SONDR (=depot SONDRIO) e chiude a LECCO. Se
    nessun treno passa LECCO→SONDRIO entro la finestra → SONDRIO
    è scartato. Se LECCO è anche depot, vince LECCO (Strategia 1).
    Altrimenti ritorna None (fallback legacy)."""
    import httpx

    blocchi = [
        _make_blocco(seq=1, da="SONDR", a="LECCO", inizio=time(8, 0), fine=time(20, 0)),
    ]
    depositi = [
        _make_depot("SONDRIO", "SONDR"),
        # Niente LECCO depot in questo test → no Strategia 1.
    ]
    # API ritorna sempre lista vuota → nessuna vettura trovata.
    transport = httpx.MockTransport(_empty_response_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        chosen, vettura = await _scegli_deposito_per_segmento(
            blocchi, depositi, ora_chiusura_min=21 * 60, live_client=client
        )
    # SONDRIO scartato dal quality gate, nessun fallback in casa →
    # ritorna None (= fallback legacy nel chiamante).
    assert chosen is None
    assert vettura is None


@pytest.mark.asyncio
async def test_scegli_depot_chiusura_in_casa_vince_su_partenza() -> None:
    """Sprint 7.10 MR α.5.fix: nuova priorità. Se il segmento parte
    da ALES (= depot ALESSANDRIA) E chiude a LECCO (= depot LECCO),
    vince LECCO (chiusura in casa, Strategia 1) — non ALES, perché
    non vogliamo costringere il PdC a fare vettura quando può
    chiudere in casa naturalmente."""
    import httpx

    blocchi = [
        _make_blocco(seq=1, da="ALES", a="LECCO", inizio=time(8, 0), fine=time(10, 0)),
    ]
    depositi = [
        _make_depot("ALESSANDRIA", "ALES"),
        _make_depot("LECCO", "LECCO"),
    ]
    transport = httpx.MockTransport(_empty_response_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        chosen, vettura = await _scegli_deposito_per_segmento(
            blocchi, depositi, ora_chiusura_min=11 * 60, live_client=client
        )
    assert chosen is not None
    assert chosen.codice == "LECCO"  # priorità chiusura
    assert vettura is None


@pytest.mark.asyncio
async def test_scegli_depot_lista_depositi_vuota() -> None:
    import httpx

    blocchi = [
        _make_blocco(seq=1, da="A", a="B", inizio=time(8, 0), fine=time(10, 0)),
    ]
    transport = httpx.MockTransport(_empty_response_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        chosen, vettura = await _scegli_deposito_per_segmento(
            blocchi, [], ora_chiusura_min=11 * 60, live_client=client
        )
    assert chosen is None
    assert vettura is None


@pytest.mark.asyncio
async def test_scegli_depot_blocchi_vuoti() -> None:
    import httpx

    depositi = [_make_depot("ALESSANDRIA", "ALES")]
    transport = httpx.MockTransport(_empty_response_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        chosen, vettura = await _scegli_deposito_per_segmento(
            [], depositi, ora_chiusura_min=11 * 60, live_client=client
        )
    assert chosen is None
    assert vettura is None


@pytest.mark.asyncio
async def test_scegli_depot_ignora_depositi_senza_stazione_principale() -> None:
    """Depot con stazione_principale_codice = None viene saltato:
    senza stazione popolata non possiamo né verificare vettura né
    fare match su stazione di chiusura."""
    import httpx

    blocchi = [
        _make_blocco(seq=1, da="ALES", a="VOG", inizio=time(8, 0), fine=time(10, 0)),
    ]
    depositi = [
        _make_depot("ALESSANDRIA", None),  # stazione NULL → escluso
        _make_depot("VOGHERA", "VOG"),
    ]
    transport = httpx.MockTransport(_empty_response_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        chosen, vettura = await _scegli_deposito_per_segmento(
            blocchi, depositi, ora_chiusura_min=11 * 60, live_client=client
        )
    # VOGHERA è la stazione di chiusura (Strategia 1).
    assert chosen is not None
    assert chosen.codice == "VOGHERA"
    assert vettura is None
