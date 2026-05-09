"""Test per ``domain/builder_giro/chiusura_post.py`` (Sprint 8.1 MR-A2).

Closure post-pass: per ogni giro con motivo_chiusura='non_chiuso',
tenta chiusura con vuoto di rientro intra-area metropolitana. Se non
trova area metropolitana comune, marca 'ciclo_aperto_irrisolto'.
Tutti gli altri motivi pass-through invariato.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from typing import Any

import pytest

from colazione.domain.builder_giro.catena import Catena
from colazione.domain.builder_giro.chiusura_post import (
    ParamChiusuraPost,
    chiudi_giri_aperti,
)
from colazione.domain.builder_giro.multi_giornata import GiornataGiro, Giro
from colazione.domain.builder_giro.posizionamento import (
    BloccoMaterialeVuoto,
    CatenaPosizionata,
)

# =====================================================================
# Fixture helpers (corse e giri sintetici)
# =====================================================================


@dataclass(frozen=True)
class _CorsaFake:
    codice_origine: str
    codice_destinazione: str
    ora_partenza: time
    ora_arrivo: time
    km_tratta: float | None = None


def _make_giro(
    *,
    localita: str = "FIO",
    stazione_collegata: str = "S_CERTOSA",
    corse: tuple[_CorsaFake, ...] | None = None,
    chiuso: bool = False,
    motivo: Any = "non_chiuso",
    vuoto_coda: BloccoMaterialeVuoto | None = None,
    chiusa_a_localita: bool = False,
    km: float = 100.0,
) -> Giro:
    """Costruisce un Giro 1-giornata sintetico."""
    if corse is None:
        corse = (
            _CorsaFake(
                codice_origine="S_PARTENZA",
                codice_destinazione="S_ARRIVO",
                ora_partenza=time(8, 0),
                ora_arrivo=time(10, 30),
                km_tratta=80.0,
            ),
        )
    catena = Catena(corse=corse)
    cat_pos = CatenaPosizionata(
        localita_codice=localita,
        stazione_collegata=stazione_collegata,
        vuoto_testa=None,
        catena=catena,
        vuoto_coda=vuoto_coda,
        chiusa_a_localita=chiusa_a_localita,
    )
    giornata = GiornataGiro(data=date(2026, 5, 8), catena_posizionata=cat_pos)
    return Giro(
        localita_codice=localita,
        giornate=(giornata,),
        chiuso=chiuso,
        motivo_chiusura=motivo,
        km_cumulati=km,
    )


# =====================================================================
# Pass-through: motivi diversi da 'non_chiuso'
# =====================================================================


@pytest.mark.parametrize(
    "motivo", ["naturale", "max_giornate", "km_cap", "sotto_min"]
)
def test_giri_chiusi_pass_through(motivo: str) -> None:
    g = _make_giro(motivo=motivo, chiuso=motivo == "naturale")
    params = ParamChiusuraPost(
        whitelist_sede=frozenset({"S_CERTOSA"}),
        area_per_stazione={"S_ARRIVO": 1, "S_CERTOSA": 1},
    )
    out = chiudi_giri_aperti([g], params)
    assert len(out) == 1
    assert out[0] is g  # passa-through identità


@pytest.mark.parametrize(
    "motivo", ["chiuso_con_vuoto", "ciclo_aperto_irrisolto"]
)
def test_idempotenza_post_pass(motivo: str) -> None:
    """Chiamata su lista già processata: pass-through invariato."""
    g = _make_giro(motivo=motivo)
    params = ParamChiusuraPost(
        whitelist_sede=frozenset({"S_CERTOSA"}),
        area_per_stazione={"S_ARRIVO": 1, "S_CERTOSA": 1},
    )
    out = chiudi_giri_aperti([g], params)
    assert out[0] is g


# =====================================================================
# Chiusura con vuoto di rientro
# =====================================================================


def test_chiusura_intra_area_genera_vuoto_coda() -> None:
    """Ultima stazione in stessa area metropolitana di una whitelist
    → genera vuoto coda + marca 'chiuso_con_vuoto'.
    """
    g = _make_giro(
        corse=(
            _CorsaFake(
                "S_PARTENZA", "S_CENTRALE", time(8, 0), time(10, 30), 80.0
            ),
        ),
    )
    params = ParamChiusuraPost(
        whitelist_sede=frozenset({"S_CERTOSA"}),
        area_per_stazione={"S_CENTRALE": 1, "S_CERTOSA": 1},
        gap_vuoto_rientro_min=10,
    )
    out = chiudi_giri_aperti([g], params)
    assert len(out) == 1
    g_chiuso = out[0]
    assert g_chiuso.motivo_chiusura == "chiuso_con_vuoto"
    assert g_chiuso.chiuso is True
    cat_pos = g_chiuso.giornate[-1].catena_posizionata
    assert cat_pos.vuoto_coda is not None
    assert cat_pos.vuoto_coda.codice_origine == "S_CENTRALE"
    assert cat_pos.vuoto_coda.codice_destinazione == "S_CERTOSA"
    assert cat_pos.vuoto_coda.ora_partenza == time(10, 30)
    assert cat_pos.vuoto_coda.ora_arrivo == time(10, 40)
    assert cat_pos.vuoto_coda.motivo == "coda"
    assert cat_pos.chiusa_a_localita is True


def test_chiusura_target_alfabetico_deterministico() -> None:
    """Più whitelist nella stessa area: scegli la prima alfabetica."""
    g = _make_giro(
        corse=(
            _CorsaFake(
                "S_PARTENZA", "S_CENTRALE", time(8, 0), time(10, 30)
            ),
        ),
    )
    params = ParamChiusuraPost(
        whitelist_sede=frozenset({"S_GARIBALDI", "S_CERTOSA", "S_LAMBRATE"}),
        area_per_stazione={
            "S_CENTRALE": 1,
            "S_CERTOSA": 1,
            "S_GARIBALDI": 1,
            "S_LAMBRATE": 1,
        },
    )
    out = chiudi_giri_aperti([g], params)
    cat_pos = out[0].giornate[-1].catena_posizionata
    assert cat_pos.vuoto_coda is not None
    assert cat_pos.vuoto_coda.codice_destinazione == "S_CERTOSA"


def test_chiusura_cross_mezzanotte_accettata() -> None:
    """Vuoto coda che sfora mezzanotte è generato comunque (fine giro)."""
    g = _make_giro(
        corse=(
            _CorsaFake(
                "S_PARTENZA", "S_CENTRALE", time(20, 0), time(23, 55)
            ),
        ),
    )
    params = ParamChiusuraPost(
        whitelist_sede=frozenset({"S_CERTOSA"}),
        area_per_stazione={"S_CENTRALE": 1, "S_CERTOSA": 1},
        gap_vuoto_rientro_min=15,
    )
    out = chiudi_giri_aperti([g], params)
    cat_pos = out[0].giornate[-1].catena_posizionata
    assert cat_pos.vuoto_coda is not None
    # 23:55 + 15 = 00:10 (ora successiva), wrap-around accettato
    assert cat_pos.vuoto_coda.ora_arrivo == time(0, 10)
    assert out[0].motivo_chiusura == "chiuso_con_vuoto"


# =====================================================================
# Marker ciclo_aperto_irrisolto
# =====================================================================


def test_no_area_in_comune_genera_marker() -> None:
    """Ultima staz in area diversa da whitelist → ciclo_aperto_irrisolto."""
    g = _make_giro(
        corse=(
            _CorsaFake("S_PARTENZA", "S_TIRANO", time(8, 0), time(11, 0)),
        ),
    )
    params = ParamChiusuraPost(
        whitelist_sede=frozenset({"S_CERTOSA"}),
        area_per_stazione={
            "S_TIRANO": 99,  # area diversa
            "S_CERTOSA": 1,
        },
    )
    out = chiudi_giri_aperti([g], params)
    assert out[0].motivo_chiusura == "ciclo_aperto_irrisolto"
    assert out[0].chiuso is False
    # Vuoto coda NON aggiunto
    assert out[0].giornate[-1].catena_posizionata.vuoto_coda is None


def test_staz_arrivo_fuori_da_qualsiasi_area_genera_marker() -> None:
    g = _make_giro(
        corse=(
            _CorsaFake("S_PARTENZA", "S_REMOTA", time(8, 0), time(11, 0)),
        ),
    )
    params = ParamChiusuraPost(
        whitelist_sede=frozenset({"S_CERTOSA"}),
        area_per_stazione={"S_CERTOSA": 1},  # S_REMOTA non mappata
    )
    out = chiudi_giri_aperti([g], params)
    assert out[0].motivo_chiusura == "ciclo_aperto_irrisolto"


def test_whitelist_vuota_genera_marker() -> None:
    g = _make_giro(
        corse=(
            _CorsaFake("S_PARTENZA", "S_CENTRALE", time(8, 0), time(10, 30)),
        ),
    )
    params = ParamChiusuraPost(
        whitelist_sede=frozenset(),
        area_per_stazione={"S_CENTRALE": 1},
    )
    out = chiudi_giri_aperti([g], params)
    assert out[0].motivo_chiusura == "ciclo_aperto_irrisolto"


def test_area_per_stazione_vuoto_genera_marker() -> None:
    g = _make_giro(
        corse=(
            _CorsaFake("S_PARTENZA", "S_CENTRALE", time(8, 0), time(10, 30)),
        ),
    )
    params = ParamChiusuraPost(
        whitelist_sede=frozenset({"S_CERTOSA"}),
        area_per_stazione={},
    )
    out = chiudi_giri_aperti([g], params)
    assert out[0].motivo_chiusura == "ciclo_aperto_irrisolto"


def test_giro_senza_giornate_genera_marker() -> None:
    """Defensive: giro malformato senza giornate → marker, no crash."""
    g = Giro(
        localita_codice="FIO",
        giornate=(),
        chiuso=False,
        motivo_chiusura="non_chiuso",
        km_cumulati=0.0,
    )
    params = ParamChiusuraPost(whitelist_sede=frozenset({"S_CERTOSA"}))
    out = chiudi_giri_aperti([g], params)
    assert out[0].motivo_chiusura == "ciclo_aperto_irrisolto"


def test_giornata_senza_corse_genera_marker() -> None:
    """Defensive: giornata con catena vuota → marker."""
    cat_pos = CatenaPosizionata(
        localita_codice="FIO",
        stazione_collegata="S_CERTOSA",
        vuoto_testa=None,
        catena=Catena(corse=()),
        vuoto_coda=None,
        chiusa_a_localita=False,
    )
    g = Giro(
        localita_codice="FIO",
        giornate=(GiornataGiro(date(2026, 5, 8), cat_pos),),
        chiuso=False,
        motivo_chiusura="non_chiuso",
    )
    params = ParamChiusuraPost(
        whitelist_sede=frozenset({"S_CERTOSA"}),
        area_per_stazione={"S_CERTOSA": 1},
    )
    out = chiudi_giri_aperti([g], params)
    assert out[0].motivo_chiusura == "ciclo_aperto_irrisolto"


# =====================================================================
# Arrivo già in whitelist (MR-B1 entry 254: marca naturale, non passthrough)
# =====================================================================


def test_b1_arrivo_in_whitelist_via_corsa_marca_naturale() -> None:
    """Sprint 8.1 MR-B1 (entry 254): se l'ultima corsa commerciale
    arriva direttamente in whitelist sede ma il marker upstream è
    'non_chiuso', il post-pass corregge a 'naturale' (il giro è di
    fatto chiuso a casa).
    """
    g = _make_giro(
        corse=(
            _CorsaFake("S_PARTENZA", "S_CERTOSA", time(8, 0), time(10, 30)),
        ),
    )
    params = ParamChiusuraPost(
        whitelist_sede=frozenset({"S_CERTOSA"}),
        area_per_stazione={"S_CERTOSA": 1},
    )
    out = chiudi_giri_aperti([g], params)
    assert out[0].motivo_chiusura == "naturale"
    assert out[0].chiuso is True


def test_b1_arrivo_in_whitelist_via_vuoto_coda_marca_naturale() -> None:
    """Sprint 8.1 MR-B1 (entry 254): caso reale prog 17 produzione
    (giri 1449, 1452): il builder upstream ha già aggiunto un
    `vuoto_coda` di rientro a CERTOSA, ma il marker resta
    'non_chiuso'. Il post-pass corregge a 'naturale' osservando che
    `_ultima_stazione_giro` (che usa `vuoto_coda.codice_destinazione`
    se presente) ricade in whitelist sede.
    """
    vuoto_coda = BloccoMaterialeVuoto(
        codice_origine="S_ROGOREDO",
        codice_destinazione="S_CERTOSA",
        ora_partenza=time(23, 34),
        ora_arrivo=time(0, 4),
        motivo="coda",
        cross_notte_giorno_precedente=False,
    )
    g = _make_giro(
        corse=(
            _CorsaFake("S_MORTARA", "S_ROGOREDO", time(22, 33), time(23, 34)),
        ),
        vuoto_coda=vuoto_coda,
    )
    params = ParamChiusuraPost(
        whitelist_sede=frozenset({"S_CERTOSA"}),
        area_per_stazione={"S_CERTOSA": 1},
    )
    out = chiudi_giri_aperti([g], params)
    assert out[0].motivo_chiusura == "naturale"
    assert out[0].chiuso is True
    # Vuoto coda upstream preservato (non duplicato)
    assert (
        out[0].giornate[-1].catena_posizionata.vuoto_coda is vuoto_coda
    )


# =====================================================================
# Immutabilità input
# =====================================================================


def test_input_non_mutato() -> None:
    """La funzione è pura: l'input non viene modificato."""
    g_in = _make_giro(
        corse=(
            _CorsaFake("S_PARTENZA", "S_CENTRALE", time(8, 0), time(10, 30)),
        ),
    )
    motivo_originale = g_in.motivo_chiusura
    chiuso_originale = g_in.chiuso
    vuoto_coda_originale = g_in.giornate[-1].catena_posizionata.vuoto_coda

    params = ParamChiusuraPost(
        whitelist_sede=frozenset({"S_CERTOSA"}),
        area_per_stazione={"S_CENTRALE": 1, "S_CERTOSA": 1},
    )
    _ = chiudi_giri_aperti([g_in], params)

    # Input invariato
    assert g_in.motivo_chiusura == motivo_originale
    assert g_in.chiuso is chiuso_originale
    assert (
        g_in.giornate[-1].catena_posizionata.vuoto_coda is vuoto_coda_originale
    )


# =====================================================================
# Lista vuota
# =====================================================================


def test_lista_vuota() -> None:
    params = ParamChiusuraPost(whitelist_sede=frozenset())
    assert chiudi_giri_aperti([], params) == []


# =====================================================================
# Re-export
# =====================================================================


def test_re_export_da_builder_giro_init() -> None:
    from colazione.domain import builder_giro

    assert builder_giro.ParamChiusuraPost is ParamChiusuraPost
    assert builder_giro.chiudi_giri_aperti is chiudi_giri_aperti
