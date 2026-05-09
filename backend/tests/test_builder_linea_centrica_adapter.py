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
    _traduce_e_filtra_giri_linea_centrica,
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
    regola_id: int | None = 42,
    sede_operativa: str | None = None,
) -> Giro:
    catena = Catena(corse=(_CorsaFake(),))
    cat_pos = CatenaPosizionata(
        localita_codice=localita,
        stazione_collegata="S_FIO",
        vuoto_testa=None,
        catena=catena,
        vuoto_coda=None,
        chiusa_a_localita=chiuso,
        regola_id=regola_id,
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
        sede_operativa_codice=sede_operativa,
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


# =====================================================================
# Sprint 8.2 MR-D5f S2 — test traduce_e_filtra (chiude finding HIGH
# critica SEVERO 4/10 entry 270: "manca test sul ramo regola_id=None
# → scarto giro").
# =====================================================================


def test_traduce_e_filtra_caso_felice_giro_persiste() -> None:
    """Giro con regola_id valida + sede del run → persistito."""
    giro = _giro(localita="FIO", regola_id=42)
    out = _traduce_e_filtra_giri_linea_centrica(
        giri=(giro,),
        materiale_per_regola={42: "ETR522"},
        localita_codice_run="FIO",
    )
    giri_persistibili, n_no_mat, n_altra_sede, sedi_altre, warnings = out
    assert len(giri_persistibili) == 1
    assert giri_persistibili[0].materiale_tipo_codice == "ETR522"
    assert n_no_mat == 0
    assert n_altra_sede == 0
    assert sedi_altre == set()
    assert warnings == []


def test_traduce_e_filtra_regola_id_none_scarta_giro() -> None:
    """S2 RED-PHASE: giro con regola_id=None → scartato + warning +
    counter, NON in `giri_persistibili`. Chiude finding HIGH SEVERO
    sul ramo MR-D5e non testato.
    """
    giro = _giro(localita="FIO", regola_id=None)
    out = _traduce_e_filtra_giri_linea_centrica(
        giri=(giro,),
        materiale_per_regola={42: "ETR522"},
        localita_codice_run="FIO",
    )
    giri_persistibili, n_no_mat, n_altra_sede, sedi_altre, warnings = out
    assert giri_persistibili == []
    assert n_no_mat == 1
    assert n_altra_sede == 0
    assert sedi_altre == set()
    # Almeno 1 warning con il pattern "Giro linea-centrica scartato"
    assert any("Giro linea-centrica scartato" in w for w in warnings)
    # Aggregazione finale "N giri scartati per materiale non risolto"
    assert any(
        "scartati per materiale non risolto" in w for w in warnings
    )


def test_traduce_e_filtra_regola_id_non_in_dict_scarta_giro() -> None:
    """Giro con regola_id valida ma NON in `materiale_per_regola`
    → scartato (caso composizione_json vuota a monte)."""
    giro = _giro(localita="FIO", regola_id=999)
    out = _traduce_e_filtra_giri_linea_centrica(
        giri=(giro,),
        materiale_per_regola={42: "ETR522"},  # 999 NON presente
        localita_codice_run="FIO",
    )
    giri_persistibili, n_no_mat, n_altra_sede, _sedi, warnings = out
    assert giri_persistibili == []
    assert n_no_mat == 1
    assert n_altra_sede == 0
    assert any("regola_id=999" in w for w in warnings)


def test_traduce_e_filtra_giro_altra_sede_non_persistito() -> None:
    """MR-D5f filtro persistenza: giro per sede diversa dal run →
    contato in `n_altra_sede` ma NON persistito (modello cumulativo)."""
    giro = _giro(localita="CRE", regola_id=42)
    out = _traduce_e_filtra_giri_linea_centrica(
        giri=(giro,),
        materiale_per_regola={42: "ATR803"},
        localita_codice_run="FIO",  # run è FIO, giro è CRE
    )
    giri_persistibili, n_no_mat, n_altra_sede, sedi_altre, warnings = out
    assert giri_persistibili == []
    assert n_no_mat == 0
    assert n_altra_sede == 1
    assert sedi_altre == {"CRE"}
    assert any(
        "1 giri per sedi diverse da FIO" in w and "[CRE]" in w
        for w in warnings
    )


def test_traduce_e_filtra_misti_alcuni_persisti_altri_scartati() -> None:
    """3 giri: 1 sede del run OK, 1 altra sede, 1 senza regola →
    1 persistito, contatori coerenti, sedi_altre popolato."""
    giro_ok = _giro(localita="FIO", regola_id=42)
    giro_altra = _giro(localita="CRE", regola_id=42)
    giro_no_mat = _giro(localita="FIO", regola_id=None)
    out = _traduce_e_filtra_giri_linea_centrica(
        giri=(giro_ok, giro_altra, giro_no_mat),
        materiale_per_regola={42: "ETR522"},
        localita_codice_run="FIO",
    )
    giri_persistibili, n_no_mat, n_altra_sede, sedi_altre, _warnings = out
    assert len(giri_persistibili) == 1
    assert giri_persistibili[0].localita_codice == "FIO"
    assert n_no_mat == 1
    assert n_altra_sede == 1
    assert sedi_altre == {"CRE"}


def test_traduce_e_filtra_giri_vuoti_no_warnings() -> None:
    """Edge case: nessun giro in input → output pulito, no warnings."""
    out = _traduce_e_filtra_giri_linea_centrica(
        giri=(),
        materiale_per_regola={42: "ETR522"},
        localita_codice_run="FIO",
    )
    giri_persistibili, n_no_mat, n_altra_sede, sedi_altre, warnings = out
    assert giri_persistibili == []
    assert n_no_mat == 0
    assert n_altra_sede == 0
    assert sedi_altre == set()
    assert warnings == []


# =====================================================================
# Sprint 8.2 MR-D5h-DUAL — warning divergenza target/operativa
# =====================================================================


def test_traduce_e_filtra_emette_warning_divergenza_target_operativa() -> None:
    """MR-D5h-DUAL: giro persistito con sede_operativa_codice != None
    → warning aggregato `MR-D5h-DUAL: N giri assegnati a sede target X
    ma operativamente sostano a [Y]`."""
    giro = _giro(
        localita="FIO",  # sede target (regola)
        sede_operativa="LEC",  # MR-D2 ottimizza a LEC
        regola_id=47,
    )
    out = _traduce_e_filtra_giri_linea_centrica(
        giri=(giro,),
        materiale_per_regola={47: "ETR526"},
        localita_codice_run="FIO",
    )
    giri_persistibili, _, _, _, warnings = out
    assert len(giri_persistibili) == 1
    # Giro persistito (sede target = run)
    assert giri_persistibili[0].localita_codice == "FIO"
    # Warning divergenza presente
    assert any(
        "MR-D5h-DUAL" in w
        and "sede target FIO" in w
        and "[LEC]" in w
        for w in warnings
    )


def test_traduce_e_filtra_no_warning_se_target_uguale_operativa() -> None:
    """MR-D5h-DUAL: giro persistito con sede_operativa_codice=None
    (target == operativa) → NESSUN warning divergenza."""
    giro = _giro(
        localita="FIO",
        sede_operativa=None,  # no divergenza
        regola_id=42,
    )
    out = _traduce_e_filtra_giri_linea_centrica(
        giri=(giro,),
        materiale_per_regola={42: "ETR522"},
        localita_codice_run="FIO",
    )
    _, _, _, _, warnings = out
    assert not any("MR-D5h-DUAL" in w for w in warnings)


def test_traduce_e_filtra_warning_aggregato_n_giri_divergenti() -> None:
    """MR-D5h-DUAL: 3 giri target=FIO, 2 con sede_operativa=LEC, 1 con
    sede_operativa=CRE → warning unico aggregato "3 giri ... [CRE, LEC]".
    """
    giri = (
        _giro(localita="FIO", sede_operativa="LEC", regola_id=47),
        _giro(localita="FIO", sede_operativa="LEC", regola_id=47),
        _giro(localita="FIO", sede_operativa="CRE", regola_id=47),
    )
    out = _traduce_e_filtra_giri_linea_centrica(
        giri=giri,
        materiale_per_regola={47: "ETR526"},
        localita_codice_run="FIO",
    )
    giri_persistibili, _, _, _, warnings = out
    assert len(giri_persistibili) == 3
    divergenza_warns = [w for w in warnings if "MR-D5h-DUAL" in w]
    assert len(divergenza_warns) == 1  # warning aggregato unico
    w = divergenza_warns[0]
    assert "3 giri" in w
    # Sedi ordinate alfabeticamente
    assert "[CRE, LEC]" in w
