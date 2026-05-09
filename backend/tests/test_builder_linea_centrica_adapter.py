"""Test adapter Giro → GiroAggregato per pipeline linea-centrica
(Sprint 8.2 MR-D5b).

L'adapter `_giro_linea_centrica_a_aggregato` fa il bridge fra
``Giro`` (output MR-D4) e ``GiroAggregato`` (input persister legacy).

Test focus:
- Mapping campi base (localita, materiale, chiuso, motivo, km)
- Aggregazione GiornataGiro → GiornataAggregata + 1 VarianteGiornata
- Propagazione dates_apply
- ``blocchi_assegnati`` + ``eventi_composizione`` empty (linea-centrica
  non genera composizioni miste)

Test integration con DB = scope MR-D7 e2e.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

from colazione.domain.builder_giro.aggregazione_a2 import (
    GiroAggregato,
)
from colazione.domain.builder_giro.builder import (
    _giro_linea_centrica_a_aggregato,
)
from colazione.domain.builder_giro.catena import Catena
from colazione.domain.builder_giro.multi_giornata import (
    GiornataGiro,
    Giro,
)
from colazione.domain.builder_giro.posizionamento import CatenaPosizionata

# =====================================================================
# Fixture helpers
# =====================================================================


@dataclass(frozen=True)
class _CorsaFake:
    codice_origine: str = "S_A"
    codice_destinazione: str = "S_B"
    ora_partenza: time = time(8, 0)
    ora_arrivo: time = time(9, 0)
    km_tratta: float | None = 50.0
    numero_treno: str = "T1"


def _giro(
    *,
    localita: str = "FIO",
    chiuso: bool = True,
    motivo: str = "naturale",
    km: float = 100.0,
    n_giornate: int = 1,
    dates_apply: tuple[date, ...] | None = None,
) -> Giro:
    catena = Catena(corse=(_CorsaFake(),))
    cat_pos = CatenaPosizionata(
        localita_codice=localita,
        stazione_collegata="S_FIO",
        vuoto_testa=None,
        catena=catena,
        vuoto_coda=None,
        chiusa_a_localita=chiuso,
        regola_id=42,
    )
    giornate = tuple(
        GiornataGiro(
            data=date(2026, 6, 8 + i),
            catena_posizionata=cat_pos,
            dates_apply=dates_apply if dates_apply is not None else (),
        )
        for i in range(n_giornate)
    )
    return Giro(
        localita_codice=localita,
        giornate=giornate,
        chiuso=chiuso,
        motivo_chiusura=motivo,  # type: ignore[arg-type]
        km_cumulati=km,
    )


# =====================================================================
# Test adapter
# =====================================================================


def test_adapter_mappa_campi_base() -> None:
    """Localita, materiale, chiuso, motivo, km cumulati → GiroAggregato."""
    giro = _giro(localita="FIO", chiuso=True, motivo="naturale", km=250.5)
    agg = _giro_linea_centrica_a_aggregato(
        giro, materiale_tipo_codice="ETR522"
    )
    assert isinstance(agg, GiroAggregato)
    assert agg.localita_codice == "FIO"
    assert agg.materiale_tipo_codice == "ETR522"
    assert agg.chiuso is True
    assert agg.motivo_chiusura == "naturale"
    assert agg.km_cumulati == 250.5


def test_adapter_giornate_diventano_aggregate_con_una_variante() -> None:
    """N GiornataGiro → N GiornataAggregata, ognuna con 1 VarianteGiornata."""
    giro = _giro(n_giornate=3)
    agg = _giro_linea_centrica_a_aggregato(
        giro, materiale_tipo_codice="ETR522"
    )
    assert len(agg.giornate) == 3
    for k, gnata in enumerate(agg.giornate, start=1):
        assert gnata.numero_giornata == k
        assert len(gnata.varianti) == 1


def test_adapter_blocchi_assegnati_popolati_mr_d5c() -> None:
    """MR-D5c (fix HIGH-1 SEVERO): blocchi_assegnati ora popolati con
    1 BloccoAssegnato per ogni corsa. ComposizioneItem = singolo
    materiale (linea-centrica single-mat). regola_id propagato.
    """
    giro = _giro(n_giornate=2)
    agg = _giro_linea_centrica_a_aggregato(
        giro, materiale_tipo_codice="ETR522"
    )
    for gnata in agg.giornate:
        for var in gnata.varianti:
            # Ogni corsa della catena → 1 BloccoAssegnato
            assert len(var.blocchi_assegnati) == len(
                var.catena_posizionata.catena.corse
            )
            for blocco in var.blocchi_assegnati:
                assert blocco.assegnazione.regola_id == 42
                assert (
                    blocco.assegnazione.composizione[0].materiale_tipo_codice
                    == "ETR522"
                )
                assert blocco.assegnazione.composizione[0].n_pezzi == 1
            # Eventi composizione restano vuoti (no aggancio/sgancio cross-mat)
            assert var.eventi_composizione == ()


def test_adapter_blocchi_assegnati_regola_id_none_fallback_a_zero() -> None:
    """Defensive: se regola_id è None (caso degenerato), fallback a 0
    invece di crash. Non dovrebbe mai capitare in produzione perché
    la pipeline linea-centrica popola regola_per_segmento.
    """
    catena = Catena(corse=(_CorsaFake(),))
    cat_pos = CatenaPosizionata(
        localita_codice="FIO",
        stazione_collegata="S_FIO",
        vuoto_testa=None,
        catena=catena,
        vuoto_coda=None,
        chiusa_a_localita=True,
        regola_id=None,  # ← caso degenerato
    )
    giornata = GiornataGiro(
        data=date(2026, 6, 8),
        catena_posizionata=cat_pos,
        dates_apply=(),
    )
    giro = Giro(
        localita_codice="FIO",
        giornate=(giornata,),
        chiuso=True,
        motivo_chiusura="naturale",
        km_cumulati=50.0,
    )
    agg = _giro_linea_centrica_a_aggregato(
        giro, materiale_tipo_codice="ETR522"
    )
    blocco = agg.giornate[0].varianti[0].blocchi_assegnati[0]
    assert blocco.assegnazione.regola_id == 0  # placeholder sentinel


def test_adapter_dates_apply_propagati() -> None:
    """Se Giro ha dates_apply popolato, viene passato alla VarianteGiornata."""
    giro = _giro(
        n_giornate=1,
        dates_apply=(date(2026, 6, 8), date(2026, 6, 15), date(2026, 6, 22)),
    )
    agg = _giro_linea_centrica_a_aggregato(
        giro, materiale_tipo_codice="ETR522"
    )
    var = agg.giornate[0].varianti[0]
    assert var.dates_apply == (
        date(2026, 6, 8),
        date(2026, 6, 15),
        date(2026, 6, 22),
    )


def test_adapter_dates_apply_default_a_data_canonica() -> None:
    """Se dates_apply vuoto, fallback alla data canonica (single date)."""
    giro = _giro(n_giornate=1, dates_apply=())
    agg = _giro_linea_centrica_a_aggregato(
        giro, materiale_tipo_codice="ETR522"
    )
    var = agg.giornate[0].varianti[0]
    assert var.dates_apply == (date(2026, 6, 8),)


def test_adapter_giro_non_chiuso() -> None:
    """Giro non_chiuso → GiroAggregato non chiuso, motivo propagato."""
    giro = _giro(chiuso=False, motivo="non_chiuso")
    agg = _giro_linea_centrica_a_aggregato(
        giro, materiale_tipo_codice="ETR522"
    )
    assert agg.chiuso is False
    assert agg.motivo_chiusura == "non_chiuso"


def test_adapter_catena_posizionata_preserved() -> None:
    """CatenaPosizionata della GiornataGiro passata identica alla
    VarianteGiornata."""
    giro = _giro(n_giornate=1)
    cat_pos_originale = giro.giornate[0].catena_posizionata
    agg = _giro_linea_centrica_a_aggregato(
        giro, materiale_tipo_codice="ETR522"
    )
    var = agg.giornate[0].varianti[0]
    assert var.catena_posizionata is cat_pos_originale
