"""Test per ``domain/builder_giro/analizza_linee.py`` (Sprint 8.2 MR-D1).

MR-D1 raffinerà la baseline MR-D0 splittando linee multi-tronco in
più ``SegmentoLinea`` distinti.

Test focus:
- Linea con 1 solo pattern (navetta o lineare semplice) → 1 segmento
  identico a baseline MR-D0
- Linea multi-tronco (R31 ALES↔MILANO + ALES↔MORTARA) → 2 segmenti:
  ``R31_completo`` + ``R31_tronco_S00470``
- Linea con coppie disgiunte (caso degenerato) → fallback baseline
- Determinismo (ordinamento)
- Override sosta notturna per segmento
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

import pytest

from colazione.domain.builder_giro.analizza_linee import (
    analizza_linea_e_splitta_segmenti,
    analizza_linee_da_corse,
)
from colazione.domain.builder_giro.definizione_linea import (
    TipoSegmento,
    VincoliSosta,
)

# =====================================================================
# Fixture helpers
# =====================================================================


@dataclass(frozen=True)
class _CorsaFake:
    codice_origine: str
    codice_destinazione: str
    ora_partenza: time
    ora_arrivo: time
    codice_linea: str


def _corsa(o: str, d: str, codice_linea: str = "R31") -> _CorsaFake:
    return _CorsaFake(
        codice_origine=o,
        codice_destinazione=d,
        ora_partenza=time(8, 0),
        ora_arrivo=time(9, 0),
        codice_linea=codice_linea,
    )


# =====================================================================
# Linea singolo pattern → 1 segmento (compat MR-D0)
# =====================================================================


def test_linea_solo_pattern_principale_un_segmento() -> None:
    """R31 con solo coppia ALES↔MILANO → 1 segmento ``R31_completo``."""
    corse = [
        _corsa("S_ALES", "S_MILANO"),
        _corsa("S_MILANO", "S_ALES"),
        _corsa("S_ALES", "S_MILANO"),
        _corsa("S_MILANO", "S_ALES"),
    ]
    linea = analizza_linea_e_splitta_segmenti(
        "R31", corse, n_giorni_perimetro=1
    )
    assert linea is not None
    assert linea.codice_linea == "R31"
    assert len(linea.segmenti) == 1
    seg = linea.segmenti[0]
    assert seg.codice == "R31_completo"
    assert seg.capolinee == frozenset({"S_ALES", "S_MILANO"})


def test_linea_navetta_round_trip_alta_frequenza() -> None:
    """Navetta S01860↔S01074 round-trip 8 volte → 1 segmento NAVETTA."""
    corse = [
        _corsa("S01860", "S01074", codice_linea="S13"),
        _corsa("S01074", "S01860", codice_linea="S13"),
    ] * 4
    linea = analizza_linea_e_splitta_segmenti(
        "S13", corse, n_giorni_perimetro=1
    )
    assert linea is not None
    assert len(linea.segmenti) == 1
    seg = linea.segmenti[0]
    assert seg.tipo == TipoSegmento.NAVETTA
    assert seg.codice == "S13_completo"


# =====================================================================
# Linea multi-tronco → 2 segmenti
# =====================================================================


def test_linea_multi_tronco_split_in_due_segmenti() -> None:
    """R31 con coppie ALES↔MILANO + ALES↔MORTARA →
    2 segmenti: completo + tronco condividendo ALES.
    """
    corse = [
        # ALES↔MILANO 4 corse principali
        _corsa("S_ALES", "S_MILANO"),
        _corsa("S_MILANO", "S_ALES"),
        _corsa("S_ALES", "S_MILANO"),
        _corsa("S_MILANO", "S_ALES"),
        # ALES↔MORTARA 2 corse tronco
        _corsa("S_ALES", "S_MORTARA"),
        _corsa("S_MORTARA", "S_ALES"),
    ]
    linea = analizza_linea_e_splitta_segmenti(
        "R31", corse, n_giorni_perimetro=1
    )
    assert linea is not None
    # I capolinee globali sono ALES e MILANO (ALES appare 6 volte,
    # MILANO 4 volte, MORTARA 2 volte → top-2 = ALES, MILANO)
    codici = sorted(s.codice for s in linea.segmenti)
    assert codici == ["R31_completo", "R31_tronco_S_ALES"]


def test_linea_multi_tronco_capolinee_segmenti_corretti() -> None:
    """Verifica che segmento principale ha {ALES, MILANO} e tronco
    ha {ALES, MORTARA}."""
    corse = [
        _corsa("S_ALES", "S_MILANO"),
        _corsa("S_MILANO", "S_ALES"),
        _corsa("S_ALES", "S_MILANO"),
        _corsa("S_MILANO", "S_ALES"),
        _corsa("S_ALES", "S_MORTARA"),
        _corsa("S_MORTARA", "S_ALES"),
    ]
    linea = analizza_linea_e_splitta_segmenti(
        "R31", corse, n_giorni_perimetro=1
    )
    assert linea is not None
    seg_completo = next(
        s for s in linea.segmenti if s.codice == "R31_completo"
    )
    seg_tronco = next(
        s for s in linea.segmenti if s.codice == "R31_tronco_S_ALES"
    )
    assert seg_completo.capolinee == frozenset({"S_ALES", "S_MILANO"})
    assert seg_tronco.capolinee == frozenset({"S_ALES", "S_MORTARA"})


def test_linea_multi_tronco_corse_per_die_distribuiti() -> None:
    """n_corse_per_die_media correttamente distribuito fra segmenti."""
    corse = [
        _corsa("S_ALES", "S_MILANO"),
        _corsa("S_MILANO", "S_ALES"),
        _corsa("S_ALES", "S_MILANO"),
        _corsa("S_MILANO", "S_ALES"),
        _corsa("S_ALES", "S_MORTARA"),
        _corsa("S_MORTARA", "S_ALES"),
    ]
    linea = analizza_linea_e_splitta_segmenti(
        "R31", corse, n_giorni_perimetro=1
    )
    assert linea is not None
    seg_completo = next(
        s for s in linea.segmenti if s.codice == "R31_completo"
    )
    seg_tronco = next(
        s for s in linea.segmenti if s.codice == "R31_tronco_S_ALES"
    )
    assert seg_completo.n_corse_per_die_media == 4.0
    assert seg_tronco.n_corse_per_die_media == 2.0


def test_linea_multi_tronco_su_entrambi_capolinee() -> None:
    """R31 con tronchi da entrambe le parti:
    ALES↔MILANO (principale)
    + ALES↔MORTARA (tronco lato ALES)
    + MILANO↔PAVIA (tronco lato MILANO)
    → 3 segmenti.
    """
    corse = [
        # ALES↔MILANO 6 corse
        _corsa("S_ALES", "S_MILANO"),
        _corsa("S_MILANO", "S_ALES"),
    ] * 3 + [
        # ALES↔MORTARA 2 corse
        _corsa("S_ALES", "S_MORTARA"),
        _corsa("S_MORTARA", "S_ALES"),
    ] + [
        # MILANO↔PAVIA 2 corse
        _corsa("S_MILANO", "S_PAVIA"),
        _corsa("S_PAVIA", "S_MILANO"),
    ]
    linea = analizza_linea_e_splitta_segmenti(
        "R31", corse, n_giorni_perimetro=1
    )
    assert linea is not None
    codici = sorted(s.codice for s in linea.segmenti)
    assert codici == [
        "R31_completo",
        "R31_tronco_S_ALES",
        "R31_tronco_S_MILANO",
    ]


# =====================================================================
# Casi degenerati
# =====================================================================


def test_linea_senza_corse_ritorna_none() -> None:
    assert (
        analizza_linea_e_splitta_segmenti(
            "R31", [], n_giorni_perimetro=1
        )
        is None
    )


def test_linea_con_branche_disgiunte_split_isolati() -> None:
    """Coppie disgiunte (S_A,S_B) + (S_C,S_D): la prima diventa
    principale (per ordinamento alfabetico nei tie di frequenza),
    la seconda diventa segmento isolato dedicato. 2 segmenti totali.
    """
    corse = [
        _corsa("S_A", "S_B", codice_linea="R99"),
        _corsa("S_C", "S_D", codice_linea="R99"),
    ]
    linea = analizza_linea_e_splitta_segmenti(
        "R99", corse, n_giorni_perimetro=1
    )
    assert linea is not None
    codici = sorted(s.codice for s in linea.segmenti)
    assert codici == ["R99_completo", "R99_isolato_S_C_S_D"]
    seg_completo = next(
        s for s in linea.segmenti if s.codice == "R99_completo"
    )
    seg_isolato = next(
        s for s in linea.segmenti if s.codice == "R99_isolato_S_C_S_D"
    )
    assert seg_completo.capolinee == frozenset({"S_A", "S_B"})
    assert seg_isolato.capolinee == frozenset({"S_C", "S_D"})


def test_n_giorni_zero_invalido() -> None:
    with pytest.raises(ValueError, match="n_giorni"):
        analizza_linea_e_splitta_segmenti(
            "R31",
            [_corsa("S_A", "S_B")],
            n_giorni_perimetro=0,
        )


# =====================================================================
# Override sosta notturna
# =====================================================================


def test_override_sosta_notturna_per_segmento() -> None:
    """Override stazioni_sosta_notturna_per_segmento applicato per
    codice segmento.
    """
    corse = [
        _corsa("S_ALES", "S_MILANO"),
        _corsa("S_MILANO", "S_ALES"),
    ]
    linea = analizza_linea_e_splitta_segmenti(
        "R31",
        corse,
        n_giorni_perimetro=1,
        stazioni_sosta_notturna_per_segmento={
            "R31_completo": frozenset({"S_DEPOSITO"})
        },
    )
    assert linea is not None
    assert linea.segmenti[0].stazioni_sosta_notturna == frozenset(
        {"S_DEPOSITO"}
    )


def test_sosta_default_a_capolinee() -> None:
    """Senza override, sosta = capolinee del segmento."""
    corse = [
        _corsa("S_ALES", "S_MILANO"),
        _corsa("S_MILANO", "S_ALES"),
    ]
    linea = analizza_linea_e_splitta_segmenti(
        "R31", corse, n_giorni_perimetro=1
    )
    assert linea is not None
    seg = linea.segmenti[0]
    assert seg.stazioni_sosta_notturna == seg.capolinee


# =====================================================================
# analizza_linee_da_corse (multi-linea)
# =====================================================================


def test_multi_linea_ordinamento_alfabetico() -> None:
    """Più linee → output ordinato alfabeticamente per codice_linea."""
    corse_r31 = [_corsa("S_A", "S_B", codice_linea="R31")] * 2
    corse_re13 = [_corsa("S_X", "S_Y", codice_linea="RE13")] * 2
    corse_s5 = [_corsa("S_M", "S_N", codice_linea="S5")] * 2
    linee = analizza_linee_da_corse(
        {"RE13": corse_re13, "R31": corse_r31, "S5": corse_s5},
        n_giorni_perimetro=1,
    )
    assert [linea.codice_linea for linea in linee] == [
        "R31",
        "RE13",
        "S5",
    ]


def test_multi_linea_descrizioni_propagate() -> None:
    corse = [_corsa("S_A", "S_B", codice_linea="R31")] * 2
    linee = analizza_linee_da_corse(
        {"R31": corse},
        n_giorni_perimetro=1,
        descrizioni_linea={"R31": "Alessandria - Mortara - Milano"},
    )
    assert linee[0].descrizione == "Alessandria - Mortara - Milano"


def test_multi_linea_n_giorni_zero_invalido() -> None:
    with pytest.raises(ValueError, match="n_giorni"):
        analizza_linee_da_corse({}, n_giorni_perimetro=0)


def test_multi_linea_linea_vuota_skippata() -> None:
    """Linea senza corse → skippata."""
    linee = analizza_linee_da_corse(
        {"R31": []}, n_giorni_perimetro=1
    )
    assert linee == []


def test_multi_linea_vincoli_default_propagati() -> None:
    corse = [_corsa("S_A", "S_B", codice_linea="R31")] * 2
    vincoli = VincoliSosta(
        sosta_max_diurna_min=180,
        sosta_max_notturna_min=600,
        sosta_min_notturna_min=240,
    )
    linee = analizza_linee_da_corse(
        {"R31": corse},
        n_giorni_perimetro=1,
        vincoli_default=vincoli,
    )
    assert linee[0].segmenti[0].vincoli_sosta == vincoli


# =====================================================================
# Idempotenza
# =====================================================================


def test_idempotenza_chiamata_doppia() -> None:
    corse = [
        _corsa("S_ALES", "S_MILANO"),
        _corsa("S_MILANO", "S_ALES"),
        _corsa("S_ALES", "S_MORTARA"),
    ]
    out1 = analizza_linea_e_splitta_segmenti(
        "R31", corse, n_giorni_perimetro=1
    )
    out2 = analizza_linea_e_splitta_segmenti(
        "R31", corse, n_giorni_perimetro=1
    )
    assert out1 == out2
