"""Test per ``domain/builder_giro/definizione_linea.py`` (Sprint 8.2 MR-D0).

Modello formale `Linea` + `SegmentoLinea` + `VincoliSosta`. Plan-D
opzione A radicale, riscrittura linea-centrica. SEVERO ha votato il
piano 7/10 con raccomandazione obbligatoria di iniziare da questo
modulo come fondazione per MR-D1..D8.

Test focus:
- Validazione param (n_giorni, capolinee min, ecc.)
- Classificazione tipo segmento (LINEARE / NAVETTA / MISTO)
- Identificazione segmenti da corse raggruppate per linea
- Lookup segmento per corsa
- Determinismo (ordinamento, idempotenza)
- Vincoli di sosta (raccomandazione SEVERO #1)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

import pytest

from colazione.domain.builder_giro.definizione_linea import (
    Linea,
    SegmentoLinea,
    TipoSegmento,
    VincoliSosta,
    identifica_segmenti_da_corse,
    raggruppa_corse_per_linea,
    trova_segmento_per_corsa,
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


def _corsa(
    o: str, d: str, hp: int, mp: int, ha: int, ma: int, linea: str = "R31"
) -> _CorsaFake:
    return _CorsaFake(
        codice_origine=o,
        codice_destinazione=d,
        ora_partenza=time(hp, mp),
        ora_arrivo=time(ha, ma),
        codice_linea=linea,
    )


# =====================================================================
# VincoliSosta validation
# =====================================================================


def test_vincoli_sosta_default() -> None:
    v = VincoliSosta()
    assert v.sosta_max_diurna_min == 240
    assert v.sosta_max_notturna_min == 720
    assert v.sosta_min_notturna_min == 300


def test_vincoli_sosta_diurna_negativa_invalida() -> None:
    with pytest.raises(ValueError, match="sosta_max_diurna_min"):
        VincoliSosta(sosta_max_diurna_min=-1)


def test_vincoli_sosta_notturna_min_maggiore_di_max_invalida() -> None:
    """sosta_max_notturna < sosta_min_notturna → errore (incoerente)."""
    with pytest.raises(ValueError, match="sosta_max_notturna_min"):
        VincoliSosta(sosta_max_notturna_min=200, sosta_min_notturna_min=300)


def test_vincoli_sosta_override_completo() -> None:
    """Override esplicito: 4h diurna / 14h notturna max / 6h notturna min."""
    v = VincoliSosta(
        sosta_max_diurna_min=240,
        sosta_max_notturna_min=14 * 60,
        sosta_min_notturna_min=6 * 60,
    )
    assert v.sosta_max_diurna_min == 240
    assert v.sosta_max_notturna_min == 14 * 60
    assert v.sosta_min_notturna_min == 6 * 60


# =====================================================================
# SegmentoLinea validation
# =====================================================================


def test_segmento_codice_vuoto_invalido() -> None:
    with pytest.raises(ValueError, match="codice"):
        SegmentoLinea(
            codice="",
            tipo=TipoSegmento.LINEARE,
            capolinee=frozenset({"S_A", "S_B"}),
            stazioni_sosta_notturna=frozenset({"S_A", "S_B"}),
            vincoli_sosta=VincoliSosta(),
            n_corse_per_die_media=2.0,
        )


def test_segmento_capolinee_singolo_invalido() -> None:
    with pytest.raises(ValueError, match="capolinee"):
        SegmentoLinea(
            codice="X",
            tipo=TipoSegmento.LINEARE,
            capolinee=frozenset({"S_A"}),
            stazioni_sosta_notturna=frozenset({"S_A"}),
            vincoli_sosta=VincoliSosta(),
            n_corse_per_die_media=1.0,
        )


def test_segmento_sosta_notturna_vuota_invalida() -> None:
    with pytest.raises(ValueError, match="stazioni_sosta_notturna"):
        SegmentoLinea(
            codice="X",
            tipo=TipoSegmento.LINEARE,
            capolinee=frozenset({"S_A", "S_B"}),
            stazioni_sosta_notturna=frozenset(),
            vincoli_sosta=VincoliSosta(),
            n_corse_per_die_media=2.0,
        )


def test_segmento_n_corse_negativo_invalido() -> None:
    with pytest.raises(ValueError, match="n_corse_per_die_media"):
        SegmentoLinea(
            codice="X",
            tipo=TipoSegmento.LINEARE,
            capolinee=frozenset({"S_A", "S_B"}),
            stazioni_sosta_notturna=frozenset({"S_A"}),
            vincoli_sosta=VincoliSosta(),
            n_corse_per_die_media=-1.0,
        )


# =====================================================================
# Linea validation
# =====================================================================


def _segmento_minimal(codice: str = "TEST_001") -> SegmentoLinea:
    return SegmentoLinea(
        codice=codice,
        tipo=TipoSegmento.LINEARE,
        capolinee=frozenset({"S_A", "S_B"}),
        stazioni_sosta_notturna=frozenset({"S_A", "S_B"}),
        vincoli_sosta=VincoliSosta(),
        n_corse_per_die_media=2.0,
    )


def test_linea_senza_segmenti_invalida() -> None:
    with pytest.raises(ValueError, match="segmento"):
        Linea(codice_linea="R31", descrizione="x", segmenti=())


def test_linea_codice_vuoto_invalido() -> None:
    with pytest.raises(ValueError, match="codice_linea"):
        Linea(
            codice_linea="",
            descrizione="x",
            segmenti=(_segmento_minimal(),),
        )


def test_linea_segmenti_codici_duplicati_invalida() -> None:
    s1 = _segmento_minimal("S1")
    s2 = _segmento_minimal("S1")  # stesso codice!
    with pytest.raises(ValueError, match="duplicati"):
        Linea(codice_linea="R31", descrizione="x", segmenti=(s1, s2))


# =====================================================================
# identifica_segmenti_da_corse — baseline MR-D0 (1 segmento per linea)
# =====================================================================


def test_identifica_linea_singola_lineare() -> None:
    """R31 con 4 corse simmetriche A↔B su 1 giorno → 1 linea, 1 segmento LINEARE."""
    corse = [
        _corsa("S_A", "S_B", 8, 0, 9, 0),
        _corsa("S_B", "S_A", 10, 0, 11, 0),
        _corsa("S_A", "S_B", 14, 0, 15, 0),
        _corsa("S_B", "S_A", 16, 0, 17, 0),
    ]
    linee = identifica_segmenti_da_corse(
        {"R31": corse}, n_giorni_perimetro=1
    )
    assert len(linee) == 1
    linea = linee[0]
    assert linea.codice_linea == "R31"
    assert len(linea.segmenti) == 1
    seg = linea.segmenti[0]
    assert seg.codice == "R31_completo"
    assert seg.tipo == TipoSegmento.LINEARE
    assert seg.capolinee == frozenset({"S_A", "S_B"})
    assert seg.n_corse_per_die_media == 4.0


def test_identifica_navetta_round_trip_alta_frequenza() -> None:
    """8 corse/die A↔B (4 round-trip) su 1 giorno → tipo NAVETTA."""
    corse = [
        _corsa("S_X", "S_Y", 6, 0, 6, 30),
        _corsa("S_Y", "S_X", 7, 0, 7, 30),
        _corsa("S_X", "S_Y", 9, 0, 9, 30),
        _corsa("S_Y", "S_X", 10, 0, 10, 30),
        _corsa("S_X", "S_Y", 12, 0, 12, 30),
        _corsa("S_Y", "S_X", 13, 0, 13, 30),
        _corsa("S_X", "S_Y", 15, 0, 15, 30),
        _corsa("S_Y", "S_X", 16, 0, 16, 30),
    ]
    linee = identifica_segmenti_da_corse(
        {"S13": corse}, n_giorni_perimetro=1
    )
    seg = linee[0].segmenti[0]
    assert seg.tipo == TipoSegmento.NAVETTA
    assert seg.n_corse_per_die_media == 8.0


def test_identifica_lineare_bassa_frequenza_no_navetta() -> None:
    """4 corse/die A↔B (2 round-trip) → LINEARE non NAVETTA."""
    corse = [
        _corsa("S_A", "S_B", 8, 0, 9, 0),
        _corsa("S_B", "S_A", 10, 0, 11, 0),
        _corsa("S_A", "S_B", 14, 0, 15, 0),
        _corsa("S_B", "S_A", 16, 0, 17, 0),
    ]
    linee = identifica_segmenti_da_corse(
        {"R10": corse}, n_giorni_perimetro=1
    )
    assert linee[0].segmenti[0].tipo == TipoSegmento.LINEARE


def test_identifica_misto_tre_o_piu_coppie() -> None:
    """3+ coppie distinte → MISTO."""
    corse = [
        _corsa("S_A", "S_B", 8, 0, 9, 0),
        _corsa("S_B", "S_C", 10, 0, 11, 0),
        _corsa("S_C", "S_A", 12, 0, 13, 0),
    ]
    linee = identifica_segmenti_da_corse(
        {"R99": corse}, n_giorni_perimetro=1
    )
    assert linee[0].segmenti[0].tipo == TipoSegmento.MISTO


def test_identifica_n_giorni_zero_invalido() -> None:
    with pytest.raises(ValueError, match="n_giorni_perimetro"):
        identifica_segmenti_da_corse({}, n_giorni_perimetro=0)


def test_identifica_linea_vuota_skippata() -> None:
    """Linea senza corse → skip (defensive)."""
    linee = identifica_segmenti_da_corse(
        {"R31": []}, n_giorni_perimetro=1
    )
    assert linee == []


def test_identifica_determinismo_ordine_alfabetico() -> None:
    """Più linee → output ordinato alfabeticamente per codice_linea."""
    corse_r31 = [
        _corsa("S_A", "S_B", 8, 0, 9, 0, linea="R31"),
        _corsa("S_B", "S_A", 10, 0, 11, 0, linea="R31"),
    ]
    corse_re13 = [
        _corsa("S_X", "S_Y", 8, 0, 9, 0, linea="RE13"),
        _corsa("S_Y", "S_X", 10, 0, 11, 0, linea="RE13"),
    ]
    corse_s5 = [
        _corsa("S_M", "S_N", 8, 0, 9, 0, linea="S5"),
        _corsa("S_N", "S_M", 10, 0, 11, 0, linea="S5"),
    ]
    linee = identifica_segmenti_da_corse(
        {"RE13": corse_re13, "R31": corse_r31, "S5": corse_s5},
        n_giorni_perimetro=1,
    )
    assert [linea.codice_linea for linea in linee] == ["R31", "RE13", "S5"]


def test_identifica_descrizioni_override() -> None:
    """Mapping descrizioni custom usato se presente."""
    corse = [
        _corsa("S_A", "S_B", 8, 0, 9, 0),
        _corsa("S_B", "S_A", 10, 0, 11, 0),
    ]
    linee = identifica_segmenti_da_corse(
        {"R31": corse},
        n_giorni_perimetro=1,
        descrizioni_linea={"R31": "Alessandria - Mortara - Milano"},
    )
    assert linee[0].descrizione == "Alessandria - Mortara - Milano"


def test_identifica_descrizioni_default_a_codice() -> None:
    """Senza descrizione, codice_linea è la descrizione di default."""
    corse = [
        _corsa("S_A", "S_B", 8, 0, 9, 0),
        _corsa("S_B", "S_A", 10, 0, 11, 0),
    ]
    linee = identifica_segmenti_da_corse(
        {"R31": corse}, n_giorni_perimetro=1
    )
    assert linee[0].descrizione == "R31"


def test_identifica_sosta_notturna_override_per_linea() -> None:
    """Override stazioni sosta notturna per linea specifica."""
    corse = [
        _corsa("S_A", "S_B", 8, 0, 9, 0),
        _corsa("S_B", "S_A", 10, 0, 11, 0),
    ]
    linee = identifica_segmenti_da_corse(
        {"R31": corse},
        n_giorni_perimetro=1,
        stazioni_sosta_notturna_per_linea={
            "R31": frozenset({"S_DEPOSITO_FIO"})
        },
    )
    assert linee[0].segmenti[0].stazioni_sosta_notturna == frozenset(
        {"S_DEPOSITO_FIO"}
    )


def test_identifica_sosta_notturna_default_a_capolinee() -> None:
    """Senza override, sosta notturna = capolinee del segmento."""
    corse = [
        _corsa("S_A", "S_B", 8, 0, 9, 0),
        _corsa("S_B", "S_A", 10, 0, 11, 0),
    ]
    linee = identifica_segmenti_da_corse(
        {"R31": corse}, n_giorni_perimetro=1
    )
    seg = linee[0].segmenti[0]
    assert seg.stazioni_sosta_notturna == seg.capolinee


def test_identifica_vincoli_default_propagati() -> None:
    """vincoli_default propagato a tutti i segmenti generati."""
    corse = [
        _corsa("S_A", "S_B", 8, 0, 9, 0),
        _corsa("S_B", "S_A", 10, 0, 11, 0),
    ]
    vincoli = VincoliSosta(
        sosta_max_diurna_min=180,
        sosta_max_notturna_min=600,
        sosta_min_notturna_min=240,
    )
    linee = identifica_segmenti_da_corse(
        {"R31": corse}, n_giorni_perimetro=1, vincoli_default=vincoli
    )
    assert linee[0].segmenti[0].vincoli_sosta == vincoli


# =====================================================================
# trova_segmento_per_corsa
# =====================================================================


def test_trova_segmento_match_codice_linea() -> None:
    corse = [
        _corsa("S_A", "S_B", 8, 0, 9, 0, linea="R31"),
        _corsa("S_B", "S_A", 10, 0, 11, 0, linea="R31"),
    ]
    linee = identifica_segmenti_da_corse(
        {"R31": corse}, n_giorni_perimetro=1
    )
    target_corsa = _corsa("S_A", "S_B", 14, 0, 15, 0, linea="R31")
    seg = trova_segmento_per_corsa(target_corsa, linee)
    assert seg is not None
    assert seg.codice == "R31_completo"


def test_trova_segmento_no_match_ritorna_none() -> None:
    corse = [
        _corsa("S_A", "S_B", 8, 0, 9, 0, linea="R31"),
        _corsa("S_B", "S_A", 10, 0, 11, 0, linea="R31"),
    ]
    linee = identifica_segmenti_da_corse(
        {"R31": corse}, n_giorni_perimetro=1
    )
    altra_linea = _corsa("S_A", "S_B", 14, 0, 15, 0, linea="RE13")
    assert trova_segmento_per_corsa(altra_linea, linee) is None


# =====================================================================
# raggruppa_corse_per_linea
# =====================================================================


def test_raggruppa_corse_per_linea_smista_correttamente() -> None:
    corse = [
        _corsa("S_A", "S_B", 8, 0, 9, 0, linea="R31"),
        _corsa("S_X", "S_Y", 8, 0, 9, 0, linea="RE13"),
        _corsa("S_A", "S_B", 10, 0, 11, 0, linea="R31"),
        _corsa("S_X", "S_Y", 10, 0, 11, 0, linea="RE13"),
    ]
    grouped = raggruppa_corse_per_linea(corse)
    assert sorted(grouped.keys()) == ["R31", "RE13"]
    assert len(grouped["R31"]) == 2
    assert len(grouped["RE13"]) == 2


def test_raggruppa_corse_vuoto() -> None:
    assert raggruppa_corse_per_linea([]) == {}


# =====================================================================
# Idempotenza / immutabilità
# =====================================================================


def test_identifica_idempotente() -> None:
    """Due chiamate consecutive con stesso input → stesso output."""
    corse = [
        _corsa("S_A", "S_B", 8, 0, 9, 0),
        _corsa("S_B", "S_A", 10, 0, 11, 0),
    ]
    out1 = identifica_segmenti_da_corse(
        {"R31": corse}, n_giorni_perimetro=1
    )
    out2 = identifica_segmenti_da_corse(
        {"R31": corse}, n_giorni_perimetro=1
    )
    assert out1 == out2


def test_linea_e_segmento_sono_frozen() -> None:
    """Tentare di mutare → AttributeError (frozen dataclass)."""
    seg = _segmento_minimal()
    with pytest.raises(AttributeError):
        seg.codice = "ALTRO"  # type: ignore[misc]
    linea = Linea(
        codice_linea="R31",
        descrizione="x",
        segmenti=(seg,),
    )
    with pytest.raises(AttributeError):
        linea.codice_linea = "RE13"  # type: ignore[misc]
