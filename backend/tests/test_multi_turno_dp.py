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


def test_scegli_depot_match_su_stazione_partenza() -> None:
    """Strategia 1: depot.stazione_principale = stazione_da del primo
    blocco → quel depot vince."""
    blocchi = [
        _make_blocco(seq=1, da="ALES", a="VOG", inizio=time(8, 0), fine=time(10, 0)),
    ]
    depositi = [
        _make_depot("ALESSANDRIA", "ALES"),
        _make_depot("VOGHERA", "VOG"),
        _make_depot("PAVIA", "PAV"),
    ]
    chosen = _scegli_deposito_per_segmento(blocchi, depositi)
    assert chosen is not None
    assert chosen.codice == "ALESSANDRIA"


def test_scegli_depot_strategia_2_match_su_stazione_arrivo() -> None:
    """Strategia 2: stazione_da non matcha, ma stazione_a sì → quel
    depot vince (PdC chiude in casa di un deposito)."""
    blocchi = [
        _make_blocco(seq=1, da="X", a="VOG", inizio=time(8, 0), fine=time(10, 0)),
    ]
    depositi = [
        _make_depot("ALESSANDRIA", "ALES"),
        _make_depot("VOGHERA", "VOG"),
    ]
    chosen = _scegli_deposito_per_segmento(blocchi, depositi)
    assert chosen is not None
    assert chosen.codice == "VOGHERA"


def test_scegli_depot_nessun_match_ritorna_none() -> None:
    """Nessuna stazione del segmento corrisponde a un deposito → None
    (fallback legacy nel chiamante)."""
    blocchi = [
        _make_blocco(seq=1, da="X", a="Y", inizio=time(8, 0), fine=time(10, 0)),
    ]
    depositi = [
        _make_depot("ALESSANDRIA", "ALES"),
        _make_depot("VOGHERA", "VOG"),
    ]
    assert _scegli_deposito_per_segmento(blocchi, depositi) is None


def test_scegli_depot_lista_depositi_vuota() -> None:
    blocchi = [
        _make_blocco(seq=1, da="A", a="B", inizio=time(8, 0), fine=time(10, 0)),
    ]
    assert _scegli_deposito_per_segmento(blocchi, []) is None


def test_scegli_depot_blocchi_vuoti() -> None:
    depositi = [_make_depot("ALESSANDRIA", "ALES")]
    assert _scegli_deposito_per_segmento([], depositi) is None


def test_scegli_depot_ignora_depositi_senza_stazione_principale() -> None:
    """Depot con stazione_principale_codice = None viene saltato anche
    se il suo codice coincide con la stazione del segmento (perché
    non possiamo scambiare lì)."""
    blocchi = [
        _make_blocco(seq=1, da="ALES", a="VOG", inizio=time(8, 0), fine=time(10, 0)),
    ]
    depositi = [
        _make_depot("ALESSANDRIA", None),  # stazione NULL → escluso
        _make_depot("VOGHERA", "VOG"),
    ]
    chosen = _scegli_deposito_per_segmento(blocchi, depositi)
    # Non matcha ALESSANDRIA (stazione None), matcha VOGHERA come
    # stazione_a (strategia 2).
    assert chosen is not None
    assert chosen.codice == "VOGHERA"
