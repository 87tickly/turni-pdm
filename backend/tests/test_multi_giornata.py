"""Test puri Sprint 4.4.3 — `costruisci_giri_multigiornata`.

Tutti i test sono **senza DB**: usano dataclass minimali per simulare
corse, località, e costruiscono `CatenaPosizionata` direttamente
(non passano da `costruisci_catene` + `posiziona_su_localita`, per
isolare il sub).

Coprono:

- Casi base: mappa vuota, 1 catena chiusa, 1 catena non chiusa.
- Cross-notte: 2 catene legate (G1 non chiusa + G2 che parte dalla
  stazione di arrivo) → giro 2-giornate.
- Continuazione mancante: G1 non chiusa ma niente in G2 → giro
  appeso, motivo `non_chiuso`.
- Forza chiusura: catena di N giornate non chiuse + cap basso →
  motivo `max_giornate`.
- Vincoli su località diverse (non si legano), su geografia (origine
  non matcha → no continuazione).
- Tie-break + determinismo.
- Esempio realistico Trenord (5 giornate ciclo settimanale).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import date, time

import pytest

from colazione.domain.builder_giro import (
    Catena,
    CatenaPosizionata,
    GiornataGiro,
    Giro,
    ParamMultiGiornata,
    costruisci_giri_multigiornata,
)

# =====================================================================
# Fixture
# =====================================================================


@dataclass
class FakeCorsa:
    codice_origine: str
    codice_destinazione: str
    ora_partenza: time
    ora_arrivo: time
    numero_treno: str = ""


def _c(o: str, d: str, p: tuple[int, int], a: tuple[int, int]) -> FakeCorsa:
    return FakeCorsa(o, d, time(*p), time(*a))


def _cat_pos(
    *,
    localita: str,
    stazione: str,
    corse: tuple[FakeCorsa, ...],
    chiusa: bool,
) -> CatenaPosizionata:
    """Helper: costruisce direttamente una CatenaPosizionata per i test."""
    return CatenaPosizionata(
        localita_codice=localita,
        stazione_collegata=stazione,
        vuoto_testa=None,
        catena=Catena(corse=corse),
        vuoto_coda=None,
        chiusa_a_localita=chiusa,
    )


D_LUN = date(2026, 4, 27)
D_MAR = date(2026, 4, 28)
D_MER = date(2026, 4, 29)
D_GIO = date(2026, 4, 30)
D_VEN = date(2026, 5, 1)


# =====================================================================
# Casi base
# =====================================================================


def test_mappa_vuota_zero_giri() -> None:
    assert costruisci_giri_multigiornata({}) == []


def test_una_catena_chiusa_un_giro_una_giornata() -> None:
    cat = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("MI_FIO", "BG", (8, 0), (9, 0)), _c("BG", "MI_FIO", (10, 0), (11, 0))),
        chiusa=True,
    )
    giri = costruisci_giri_multigiornata({D_LUN: [cat]})
    assert len(giri) == 1
    assert len(giri[0].giornate) == 1
    assert giri[0].chiuso is True
    assert giri[0].motivo_chiusura == "naturale"
    assert giri[0].localita_codice == "FIO"


def test_una_catena_non_chiusa_senza_continuazione_non_chiuso() -> None:
    cat = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("MI_FIO", "BG", (8, 0), (9, 0)),),
        chiusa=False,
    )
    giri = costruisci_giri_multigiornata({D_LUN: [cat]})
    assert len(giri) == 1
    assert len(giri[0].giornate) == 1
    assert giri[0].chiuso is False
    assert giri[0].motivo_chiusura == "non_chiuso"


# =====================================================================
# Cross-notte: legature multi-giornata
# =====================================================================


def test_due_catene_legate_giro_due_giornate_chiuso() -> None:
    """Lunedì non chiude a BG; martedì parte da BG → si legano."""
    g1 = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("MI_FIO", "BG", (20, 0), (21, 0)),),
        chiusa=False,
    )
    g2 = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("BG", "MI_FIO", (6, 0), (7, 0)),),
        chiusa=True,
    )
    giri = costruisci_giri_multigiornata({D_LUN: [g1], D_MAR: [g2]})
    assert len(giri) == 1
    assert len(giri[0].giornate) == 2
    assert giri[0].giornate[0].data == D_LUN
    assert giri[0].giornate[1].data == D_MAR
    assert giri[0].chiuso is True
    assert giri[0].motivo_chiusura == "naturale"


def test_continuazione_mancante_giro_appeso_non_chiuso() -> None:
    """Lunedì non chiude a BG; martedì non c'è nulla che parta da BG."""
    g1 = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("MI_FIO", "BG", (20, 0), (21, 0)),),
        chiusa=False,
    )
    g2 = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("MI_FIO", "VA", (8, 0), (9, 0)),),  # parte da MI_FIO, non BG
        chiusa=True,
    )
    giri = costruisci_giri_multigiornata({D_LUN: [g1], D_MAR: [g2]})
    # Due giri separati: G1 appeso, G2 standalone
    assert len(giri) == 2
    appeso = next(g for g in giri if not g.chiuso)
    standalone = next(g for g in giri if g.chiuso)
    assert appeso.motivo_chiusura == "non_chiuso"
    assert standalone.motivo_chiusura == "naturale"


def test_localita_diverse_non_si_legano() -> None:
    """Stessa stazione di partenza ma località diverse: non si legano."""
    g1 = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("MI_FIO", "BG", (20, 0), (21, 0)),),
        chiusa=False,
    )
    # Continuazione geografica perfetta MA località diversa (NOVATE)
    g2 = _cat_pos(
        localita="NOVATE",
        stazione="MI_NOV",
        corse=(_c("BG", "MI_NOV", (6, 0), (7, 0)),),
        chiusa=True,
    )
    giri = costruisci_giri_multigiornata({D_LUN: [g1], D_MAR: [g2]})
    assert len(giri) == 2
    g1_out = next(gi for gi in giri if gi.localita_codice == "FIO")
    assert g1_out.motivo_chiusura == "non_chiuso"


def test_tre_giornate_legate() -> None:
    """G1 → G2 → G3, tutte legate, ultima chiude."""
    g1 = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("MI_FIO", "BG", (20, 0), (21, 0)),),
        chiusa=False,
    )
    g2 = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("BG", "BS", (8, 0), (9, 0)),),
        chiusa=False,
    )
    g3 = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("BS", "MI_FIO", (8, 0), (10, 0)),),
        chiusa=True,
    )
    giri = costruisci_giri_multigiornata({D_LUN: [g1], D_MAR: [g2], D_MER: [g3]})
    assert len(giri) == 1
    assert len(giri[0].giornate) == 3
    assert giri[0].chiuso is True


# =====================================================================
# Forza chiusura n_giornate_max
# =====================================================================


def test_forza_chiusura_max_giornate() -> None:
    """3 giornate non chiuse + cap=2 → giro di 2 giornate motivo max_giornate."""
    g1 = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("MI_FIO", "BG", (20, 0), (21, 0)),),
        chiusa=False,
    )
    g2 = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("BG", "BS", (8, 0), (9, 0)),),
        chiusa=False,
    )
    g3 = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("BS", "CR", (8, 0), (9, 0)),),
        chiusa=False,
    )
    giri = costruisci_giri_multigiornata(
        {D_LUN: [g1], D_MAR: [g2], D_MER: [g3]},
        ParamMultiGiornata(n_giornate_max=2),
    )
    # G1+G2 fanno il primo giro (cap raggiunto); G3 standalone (1 giornata, non chiuso)
    assert len(giri) == 2
    primo = next(gi for gi in giri if len(gi.giornate) == 2)
    assert primo.motivo_chiusura == "max_giornate"
    assert primo.chiuso is False


def test_n_giornate_max_uno_singola_giornata() -> None:
    """cap=1 → ogni catena è un giro singolo, anche se legabili."""
    g1 = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("MI_FIO", "BG", (20, 0), (21, 0)),),
        chiusa=False,
    )
    g2 = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("BG", "MI_FIO", (6, 0), (7, 0)),),
        chiusa=True,
    )
    giri = costruisci_giri_multigiornata(
        {D_LUN: [g1], D_MAR: [g2]}, ParamMultiGiornata(n_giornate_max=1)
    )
    assert len(giri) == 2
    g1_out = next(gi for gi in giri if gi.giornate[0].data == D_LUN)
    assert g1_out.motivo_chiusura == "max_giornate"


# =====================================================================
# Tie-break + determinismo
# =====================================================================


def test_due_catene_lunedi_una_continuazione_la_prima_vince() -> None:
    """Due catene non chiuse il lunedì che terminano in BG, una sola
    continuazione martedì: la prima per ora_partenza (più precoce)
    si lega."""
    g1_alba = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("MI_FIO", "BG", (5, 0), (6, 0)),),
        chiusa=False,
    )
    g1_sera = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("MI_FIO", "BG", (20, 0), (21, 0)),),
        chiusa=False,
    )
    g2 = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("BG", "MI_FIO", (6, 0), (7, 0)),),
        chiusa=True,
    )
    giri = costruisci_giri_multigiornata({D_LUN: [g1_alba, g1_sera], D_MAR: [g2]})
    # g1_alba (parte alle 5) vince e si lega a g2 → giro 2-giornate
    # g1_sera resta appeso
    assert len(giri) == 2
    legato = next(gi for gi in giri if len(gi.giornate) == 2)
    appeso = next(gi for gi in giri if len(gi.giornate) == 1)
    assert legato.giornate[0].catena_posizionata is g1_alba
    assert appeso.giornate[0].catena_posizionata is g1_sera
    assert appeso.motivo_chiusura == "non_chiuso"


def test_determinismo_due_chiamate_stesso_output() -> None:
    g1 = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("MI_FIO", "BG", (20, 0), (21, 0)),),
        chiusa=False,
    )
    g2 = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("BG", "MI_FIO", (6, 0), (7, 0)),),
        chiusa=True,
    )
    out1 = costruisci_giri_multigiornata({D_LUN: [g1], D_MAR: [g2]})
    out2 = costruisci_giri_multigiornata({D_LUN: [g1], D_MAR: [g2]})
    assert out1 == out2


# =====================================================================
# Date non contigue
# =====================================================================


def test_data_successiva_mancante_giro_chiuso_per_appeso() -> None:
    """G1 lunedì non chiuso, mappa salta martedì → giro appeso."""
    g1 = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("MI_FIO", "BG", (20, 0), (21, 0)),),
        chiusa=False,
    )
    # Mercoledì c'è una catena ma il salto di un giorno la rende
    # non utilizzabile come continuazione di G1 (cerchiamo D_MAR).
    g2_mer = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("BG", "MI_FIO", (6, 0), (7, 0)),),
        chiusa=True,
    )
    giri = costruisci_giri_multigiornata({D_LUN: [g1], D_MER: [g2_mer]})
    # G1 appeso (D_MAR mancante), G2 standalone
    assert len(giri) == 2
    appeso = next(gi for gi in giri if not gi.chiuso)
    assert appeso.motivo_chiusura == "non_chiuso"


# =====================================================================
# Frozen
# =====================================================================


def test_param_default_5() -> None:
    assert ParamMultiGiornata().n_giornate_max == 5


def test_param_frozen() -> None:
    p = ParamMultiGiornata()
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.n_giornate_max = 99  # type: ignore[misc]


def test_giro_frozen() -> None:
    cat = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("MI_FIO", "BG", (8, 0), (9, 0)),),
        chiusa=True,
    )
    giri = costruisci_giri_multigiornata({D_LUN: [cat]})
    with pytest.raises(dataclasses.FrozenInstanceError):
        giri[0].chiuso = False  # type: ignore[misc]


def test_giornata_giro_frozen() -> None:
    cat = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("MI_FIO", "BG", (8, 0), (9, 0)),),
        chiusa=True,
    )
    g = GiornataGiro(data=D_LUN, catena_posizionata=cat)
    with pytest.raises(dataclasses.FrozenInstanceError):
        g.data = D_MAR  # type: ignore[misc]


# =====================================================================
# Esempio realistico
# =====================================================================


def test_esempio_ciclo_5_giornate_settimanale() -> None:
    """Ciclo 5 giornate Lun→Ven, ogni giornata cross-notte fino al venerdì
    sera che chiude a Fiorenza. Modello realistico ALe711.
    """
    # Lun: MI_FIO → ... → BG (non chiude)
    g_lun = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("MI_FIO", "BG", (20, 0), (21, 30)),),
        chiusa=False,
    )
    # Mar: BG → ... → BS (non chiude)
    g_mar = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("BG", "BS", (8, 0), (9, 0)),),
        chiusa=False,
    )
    # Mer: BS → ... → CR (non chiude)
    g_mer = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("BS", "CR", (8, 0), (9, 30)),),
        chiusa=False,
    )
    # Gio: CR → ... → VR (non chiude)
    g_gio = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("CR", "VR", (8, 0), (10, 0)),),
        chiusa=False,
    )
    # Ven: VR → ... → MI_FIO (CHIUDE)
    g_ven = _cat_pos(
        localita="FIO",
        stazione="MI_FIO",
        corse=(_c("VR", "MI_FIO", (18, 0), (21, 0)),),
        chiusa=True,
    )
    giri = costruisci_giri_multigiornata(
        {D_LUN: [g_lun], D_MAR: [g_mar], D_MER: [g_mer], D_GIO: [g_gio], D_VEN: [g_ven]}
    )
    assert len(giri) == 1
    assert len(giri[0].giornate) == 5
    assert giri[0].chiuso is True
    assert giri[0].motivo_chiusura == "naturale"
    # Verifica date in sequenza
    assert [g.data for g in giri[0].giornate] == [D_LUN, D_MAR, D_MER, D_GIO, D_VEN]
    # Verifica oggetto Giro è frozen e tipato
    assert isinstance(giri[0], Giro)
