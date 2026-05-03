"""Test puri Sprint 4.4.1 — `costruisci_catene` (greedy chain single-day).

Tutti i test sono **senza DB**: usano una dataclass minimale che
implementa il Protocol ``_CorsaLike`` di ``catena.py`` (4 attributi:
codice_origine, codice_destinazione, ora_partenza, ora_arrivo).

Coprono:

- Casi base: lista vuota, singola corsa.
- Concatenamento: due corse incatenabili, gap esatto = soglia,
  gap troppo corto, geografia incompatibile.
- Ordinamento input non garantito.
- Cross-notte: ``ora_arrivo < ora_partenza`` chiude la catena.
- Esempio realistico Trenord (S5 mattina, sequenza 4 corse).
- Determinismo: due chiamate identiche danno stesso output.
- Tie-break: a parità di geografia, vince la partenza più precoce.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import time

import pytest

from colazione.domain.builder_giro import (
    Catena,
    ParamCatena,
    costruisci_catene,
)

# =====================================================================
# Fixture
# =====================================================================


@dataclass
class FakeCorsa:
    """Corsa minimale per test (4 attributi del Protocol _CorsaLike)."""

    codice_origine: str
    codice_destinazione: str
    ora_partenza: time
    ora_arrivo: time
    numero_treno: str = ""  # solo per identificazione nei test


def _c(
    o: str,
    d: str,
    p: tuple[int, int],
    a: tuple[int, int],
    n: str = "",
) -> FakeCorsa:
    """Shortcut: ``_c("MI", "BG", (8, 0), (9, 0))``."""
    return FakeCorsa(o, d, time(*p), time(*a), n)


# =====================================================================
# Casi base
# =====================================================================


def test_lista_vuota_zero_catene() -> None:
    assert costruisci_catene([]) == []


def test_singola_corsa_una_catena_un_blocco() -> None:
    c = _c("MI", "BG", (8, 0), (9, 0))
    catene = costruisci_catene([c])
    assert len(catene) == 1
    assert catene[0] == Catena(corse=(c,))


# =====================================================================
# Concatenamento
# =====================================================================


def test_due_corse_compatibili_si_incatenano() -> None:
    a = _c("MI", "BG", (8, 0), (9, 0))
    b = _c("BG", "BS", (9, 30), (10, 30))
    catene = costruisci_catene([a, b])
    assert len(catene) == 1
    assert catene[0].corse == (a, b)


def test_due_corse_geografia_incompatibile_due_catene() -> None:
    a = _c("MI", "BG", (8, 0), (9, 0))
    b = _c("CO", "VA", (10, 0), (11, 0))
    catene = costruisci_catene([a, b])
    assert len(catene) == 2
    assert all(len(cc.corse) == 1 for cc in catene)


def test_gap_troppo_corto_non_incatena() -> None:
    a = _c("MI", "BG", (8, 0), (9, 0))
    # arrivo 09:00 + gap 5' → soglia 09:05; partenza 09:03 < soglia
    b = _c("BG", "BS", (9, 3), (10, 0))
    catene = costruisci_catene([a, b], ParamCatena(gap_min=5))
    assert len(catene) == 2


def test_gap_esattamente_uguale_al_minimo_incatena() -> None:
    """Soglia inclusiva: ``partenza >= arrivo + gap_min`` (non strict ``>``)."""
    a = _c("MI", "BG", (8, 0), (9, 0))
    b = _c("BG", "BS", (9, 5), (10, 0))
    catene = costruisci_catene([a, b], ParamCatena(gap_min=5))
    assert len(catene) == 1
    assert catene[0].corse == (a, b)


def test_gap_min_zero_incatena_consecutive() -> None:
    a = _c("MI", "BG", (8, 0), (9, 0))
    b = _c("BG", "BS", (9, 0), (10, 0))
    catene = costruisci_catene([a, b], ParamCatena(gap_min=0))
    assert len(catene) == 1


def test_gap_oltre_max_chiude_la_catena() -> None:
    """Sprint 7.9 entry 112 (decisione utente 2026-05-03):
    se la corsa successiva parte oltre `gap_max` minuti dopo l'arrivo
    della precedente, la catena si chiude.

    Caso reale (giro 74847 G3 v0): treni 2301 (06:58 arrivo Voghera)
    e 2304 (19:01 partenza Voghera) → gap 12h, sosta intermedia non
    operativa per Trenord.
    """
    a = _c("MI", "VOGHERA", (6, 28), (6, 58))
    # Partenza 19:01 = arrivo + 12h 3min (= 723 min). Default gap_max=360
    # → la catena dovrebbe chiudersi.
    b = _c("VOGHERA", "MI", (19, 1), (19, 57))
    catene = costruisci_catene([a, b])
    assert len(catene) == 2, (
        "Con gap 12h e gap_max=360 default, le 2 corse devono restare "
        "in catene separate"
    )


def test_gap_entro_max_incatena() -> None:
    """gap di 5h59 (= 359 min) entro gap_max=360 → catena unica."""
    a = _c("MI", "BG", (8, 0), (9, 0))
    # 9:00 + 5h59 = 14:59 → entro gap_max=360
    b = _c("BG", "BS", (14, 59), (15, 30))
    catene = costruisci_catene([a, b])
    assert len(catene) == 1
    assert catene[0].corse == (a, b)


def test_gap_max_personalizzato() -> None:
    """`gap_max` configurabile via ParamCatena: con gap_max=120 (2h)
    una sosta di 3h chiude la catena.
    """
    a = _c("MI", "BG", (8, 0), (9, 0))
    b = _c("BG", "BS", (12, 0), (12, 30))  # gap 3h = 180 min
    # Default gap_max=360 → catena unica
    assert len(costruisci_catene([a, b])) == 1
    # gap_max=120 → 2 catene (gap 180 > 120)
    catene = costruisci_catene([a, b], ParamCatena(gap_max=120))
    assert len(catene) == 2


# =====================================================================
# Ordinamento input
# =====================================================================


def test_input_non_ordinato_per_partenza() -> None:
    a = _c("MI", "BG", (8, 0), (9, 0), "A")
    b = _c("BG", "BS", (9, 30), (10, 30), "B")
    # Inseriti in ordine inverso → output deve incatenarli comunque
    catene = costruisci_catene([b, a])
    assert len(catene) == 1
    assert catene[0].corse == (a, b)


def test_ordine_catene_segue_prima_partenza() -> None:
    a = _c("MI", "BG", (8, 0), (9, 0))
    c = _c("RM", "FI", (11, 0), (12, 0))
    catene = costruisci_catene([c, a])
    assert len(catene) == 2
    assert catene[0].corse[0] is a
    assert catene[1].corse[0] is c


# =====================================================================
# Cross-notte (limite single-day di 4.4.1)
# =====================================================================


def test_corsa_attraversa_mezzanotte_chiude_catena() -> None:
    """``arrivo < partenza`` → la catena si chiude lì, niente prosecuzione."""
    # 23:30 → 00:30 dopo mezzanotte
    a = _c("MI", "BG", (23, 30), (0, 30))
    # Geografia + orario sarebbero compatibili (b parte dopo a in time
    # naturale, ma 'a' è già cross-notte: 4.4.1 chiude qui)
    b = _c("BG", "BS", (1, 0), (2, 0))
    catene = costruisci_catene([a, b])
    # Sorting per ora_partenza in time → b (01:00) prima di a (23:30)
    assert len(catene) == 2
    assert all(len(cc.corse) == 1 for cc in catene)


def test_corsa_normale_seguita_da_cross_notte_si_incatena_solo_la_prima_coppia() -> None:
    """La cross-notte può essere ULTIMO blocco di una catena, non passante."""
    a = _c("MI", "BG", (20, 0), (21, 0))
    # Cross-notte attaccata ad 'a': BG → BS partenza 21:30, arrivo 00:30
    b = _c("BG", "BS", (21, 30), (0, 30))
    # Successiva BS → CR alle 03:00 (geografia OK, ma 'b' cross-notte chiude)
    c = _c("BS", "CR", (3, 0), (4, 0))
    catene = costruisci_catene([a, b, c])
    # Sorting per partenza time: c(03:00), a(20:00), b(21:30)
    # Iter 1 (c): catena (c,) — niente prosecuzione (no MI o BG che parte da CR)
    # Iter 2 (a): catena (a, b) — 'b' attraversa mezzanotte → chiude
    # Iter 3 (b): già visitata, skip
    assert len(catene) == 2
    catena_a = next(cc for cc in catene if cc.corse[0] is a)
    catena_c = next(cc for cc in catene if cc.corse[0] is c)
    assert catena_a.corse == (a, b)
    assert catena_c.corse == (c,)


# =====================================================================
# Tie-break + determinismo
# =====================================================================


def test_tie_break_partenza_piu_precoce_vince() -> None:
    """A parità di origine matchante, vince la successiva con partenza minore."""
    a = _c("MI", "BG", (8, 0), (9, 0))
    b1 = _c("BG", "BS", (9, 30), (10, 30), "primo")
    b2 = _c("BG", "BS", (9, 35), (10, 35), "secondo")
    catene = costruisci_catene([a, b1, b2])
    # b1 vince per partenza più precoce → catena (a, b1)
    # b2 inizia una catena separata (singolo blocco)
    assert len(catene) == 2
    catena_principale = next(cc for cc in catene if cc.corse[0] is a)
    assert catena_principale.corse == (a, b1)
    assert any(cc.corse == (b2,) for cc in catene)


def test_determinismo_due_chiamate_stesso_output() -> None:
    a = _c("MI", "BG", (8, 0), (9, 0))
    b = _c("BG", "BS", (9, 30), (10, 30))
    c = _c("MI", "VA", (11, 0), (12, 0))
    out1 = costruisci_catene([a, b, c])
    out2 = costruisci_catene([a, b, c])
    assert out1 == out2


# =====================================================================
# Esempio realistico
# =====================================================================


def test_esempio_s5_mattina_4_corse_una_sola_catena() -> None:
    """Sequenza realistica linea S5: Cadorna → Saronno → Varese e ritorno."""
    # Cadorna → Saronno
    c1 = _c("S01066", "S05900", (6, 30), (7, 0), "10001")
    # Saronno → Varese (gap 15')
    c2 = _c("S05900", "S01747", (7, 15), (8, 0), "10003")
    # Varese → Saronno (gap 30')
    c3 = _c("S01747", "S05900", (8, 30), (9, 15), "10005")
    # Saronno → Cadorna (gap 15')
    c4 = _c("S05900", "S01066", (9, 30), (10, 0), "10007")
    catene = costruisci_catene([c1, c2, c3, c4])
    assert len(catene) == 1
    assert catene[0].corse == (c1, c2, c3, c4)


def test_due_origini_separate_due_catene_indipendenti() -> None:
    """Due 'rotabili' che fanno percorsi indipendenti."""
    # Materiale 1: MI ↔ BG
    a1 = _c("MI", "BG", (8, 0), (9, 0))
    a2 = _c("BG", "MI", (9, 30), (10, 30))
    # Materiale 2: VA ↔ CO (stessa fascia oraria)
    b1 = _c("VA", "CO", (8, 15), (9, 15))
    b2 = _c("CO", "VA", (9, 45), (10, 45))
    catene = costruisci_catene([a1, a2, b1, b2])
    assert len(catene) == 2
    catena_mi = next(cc for cc in catene if cc.corse[0] is a1)
    catena_va = next(cc for cc in catene if cc.corse[0] is b1)
    assert catena_mi.corse == (a1, a2)
    assert catena_va.corse == (b1, b2)


# =====================================================================
# ParamCatena
# =====================================================================


def test_paramcatena_default_5_minuti() -> None:
    p = ParamCatena()
    assert p.gap_min == 5


def test_paramcatena_frozen() -> None:
    """``ParamCatena`` è immutabile (frozen dataclass)."""
    p = ParamCatena()
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.gap_min = 99  # type: ignore[misc]


def test_catena_frozen() -> None:
    """``Catena`` è immutabile."""
    c = Catena(corse=())
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.corse = (1,)  # type: ignore[misc]
