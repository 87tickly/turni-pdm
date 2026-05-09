"""Test per pipeline_linea_centrica.py (Sprint 8.2 MR-D5).

End-to-end pure-domain D0..D4. Smoke test su input sintetici;
validazione su prog 17/14 reali = scope MR-D7.

Test focus:
- Pipeline completa: corse → giri (smoke 1 linea + 1 sede)
- Segmenti multi-linea + multi-sede
- SEVERO #2 in azione: linea fuori area sede → errore
- Capacity overflow: dotazione insufficiente
- Determinismo idempotente
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

import pytest

from colazione.domain.builder_giro.pipeline_linea_centrica import (
    ParamPipelineLineaCentrica,
    esegui_pipeline_linea_centrica,
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
    valido_da: date
    valido_a: date
    valido_in_date_json: list[str] | None
    numero_treno: str
    km_tratta: float | None


def _corsa(
    o: str,
    d: str,
    h_p: int,
    m_p: int,
    h_a: int,
    m_a: int,
    *,
    treno: str = "T",
    linea: str = "R31",
    valido_da: date = date(2026, 6, 1),
    valido_a: date = date(2026, 6, 30),
    valido_in_date: list[str] | None = None,
    km: float | None = 50.0,
) -> _CorsaFake:
    return _CorsaFake(
        codice_origine=o,
        codice_destinazione=d,
        ora_partenza=time(h_p, m_p),
        ora_arrivo=time(h_a, m_a),
        codice_linea=linea,
        valido_da=valido_da,
        valido_a=valido_a,
        valido_in_date_json=valido_in_date,
        numero_treno=treno,
        km_tratta=km,
    )


# =====================================================================
# Param validation
# =====================================================================


def test_param_periodo_invertito_invalido() -> None:
    with pytest.raises(ValueError, match="periodo"):
        ParamPipelineLineaCentrica(
            sedi_disponibili={"FIO": "S_FIO"},
            periodo_da=date(2026, 6, 30),
            periodo_a=date(2026, 6, 1),
        )


def test_param_sedi_vuoto_invalido() -> None:
    with pytest.raises(ValueError, match="sedi_disponibili"):
        ParamPipelineLineaCentrica(
            sedi_disponibili={},
            periodo_da=date(2026, 6, 1),
            periodo_a=date(2026, 6, 30),
        )


# =====================================================================
# Smoke: 1 linea, 1 sede
# =====================================================================


def test_smoke_una_linea_una_sede_produce_giri() -> None:
    """1 linea ALES↔FIO, 1 sede FIO. Pipeline produce ≥1 giro chiuso."""
    corse = [
        _corsa("S_FIO", "S_ALES", 8, 0, 9, 30, treno="T1", km=80.0),
        _corsa("S_ALES", "S_FIO", 10, 0, 11, 30, treno="T2", km=80.0),
    ]
    params = ParamPipelineLineaCentrica(
        sedi_disponibili={"FIO": "S_FIO"},
        periodo_da=date(2026, 6, 8),  # lunedì
        periodo_a=date(2026, 6, 12),  # venerdì
        materiale_per_segmento={"R31_completo": "ETR522"},
    )
    result = esegui_pipeline_linea_centrica(corse, params)
    assert len(result.giri) >= 1
    # Tutti i giri sono FIO
    assert all(g.localita_codice == "FIO" for g in result.giri)
    # Tutti chiusi (corse tornano a S_FIO)
    assert result.n_giri_chiusi() >= 1


def test_smoke_zero_segmenti_assegnati_fuori_area() -> None:
    """Linea con capolinee fuori area sede + sede fuori area linea →
    nessun segmento assegnato (constraint HARD SEVERO #2).
    """
    corse = [
        _corsa("S_TORINO", "S_GENOVA", 8, 0, 10, 0, treno="T1", linea="RT"),
        _corsa("S_GENOVA", "S_TORINO", 11, 0, 13, 0, treno="T2", linea="RT"),
    ]
    params = ParamPipelineLineaCentrica(
        sedi_disponibili={"FIO": "S_FIO"},
        area_per_stazione={
            "S_FIO": 1,  # area Milano
            "S_TORINO": 50,
            "S_GENOVA": 60,
        },
        materiale_per_segmento={"RT_completo": "ETR522"},
        periodo_da=date(2026, 6, 8),
        periodo_a=date(2026, 6, 8),
    )
    result = esegui_pipeline_linea_centrica(corse, params)
    # Segmento non assegnato (capolinea fuori area sede)
    assert result.n_segmenti_non_assegnati() == 1
    # Nessun giro generato
    assert result.giri == []


def test_smoke_capacity_overflow_detected() -> None:
    """Dotazione 0 → segmento marca capacity_overflow."""
    corse = [
        _corsa("S_FIO", "S_X", 8, 0, 9, 30, treno="T1"),
        _corsa("S_X", "S_FIO", 10, 0, 11, 30, treno="T2"),
    ]
    params = ParamPipelineLineaCentrica(
        sedi_disponibili={"FIO": "S_FIO"},
        dotazione_per_materiale={"ETR522": 0},  # zero capacity!
        materiale_per_segmento={"R31_completo": "ETR522"},
        periodo_da=date(2026, 6, 8),
        periodo_a=date(2026, 6, 8),
    )
    result = esegui_pipeline_linea_centrica(corse, params)
    errori = [
        a.errore for a in result.assegnazione.assegnazioni if a.errore
    ]
    assert "capacity_overflow" in errori


def test_smoke_due_linee_due_sedi_compatibili() -> None:
    """2 linee distinte (R31 a Milano, R6 a Cremona) + 2 sedi → 2 giri."""
    corse = [
        _corsa("S_FIO", "S_X", 8, 0, 9, 30, treno="R1", linea="R31"),
        _corsa("S_X", "S_FIO", 10, 0, 11, 30, treno="R2", linea="R31"),
        _corsa("S_CRE", "S_Y", 8, 0, 9, 0, treno="C1", linea="R6"),
        _corsa("S_Y", "S_CRE", 10, 0, 11, 0, treno="C2", linea="R6"),
    ]
    params = ParamPipelineLineaCentrica(
        sedi_disponibili={"FIO": "S_FIO", "CRE": "S_CRE"},
        materiale_per_segmento={
            "R31_completo": "ETR522",
            "R6_completo": "ATR125",
        },
        periodo_da=date(2026, 6, 8),
        periodo_a=date(2026, 6, 8),
    )
    result = esegui_pipeline_linea_centrica(corse, params)
    sedi_giri = {g.localita_codice for g in result.giri}
    assert sedi_giri == {"FIO", "CRE"}


# =====================================================================
# Determinismo
# =====================================================================


def test_pipeline_idempotente() -> None:
    """Stesso input → stesso output."""
    corse = [
        _corsa("S_FIO", "S_X", 8, 0, 9, 30, treno="T1"),
        _corsa("S_X", "S_FIO", 10, 0, 11, 30, treno="T2"),
    ]
    params = ParamPipelineLineaCentrica(
        sedi_disponibili={"FIO": "S_FIO"},
        materiale_per_segmento={"R31_completo": "ETR522"},
        periodo_da=date(2026, 6, 8),
        periodo_a=date(2026, 6, 9),
    )
    out1 = esegui_pipeline_linea_centrica(corse, params)
    out2 = esegui_pipeline_linea_centrica(corse, params)
    assert out1.giri == out2.giri
    assert out1.assegnazione == out2.assegnazione


# =====================================================================
# Aggregazioni intermedie esposte
# =====================================================================


def test_pipeline_espone_linee_e_turni_per_debug() -> None:
    """Risultato espone linee, assegnazione, turni per logging/debug."""
    corse = [
        _corsa("S_FIO", "S_X", 8, 0, 9, 30, treno="T1"),
        _corsa("S_X", "S_FIO", 10, 0, 11, 30, treno="T2"),
    ]
    params = ParamPipelineLineaCentrica(
        sedi_disponibili={"FIO": "S_FIO"},
        materiale_per_segmento={"R31_completo": "ETR522"},
        periodo_da=date(2026, 6, 8),
        periodo_a=date(2026, 6, 8),
    )
    result = esegui_pipeline_linea_centrica(corse, params)
    assert len(result.linee) == 1
    assert result.linee[0].codice_linea == "R31"
    assert len(result.assegnazione.assegnazioni) == 1
    assert len(result.turni) == 1


def test_pipeline_festivita_default_carica_anno_periodo() -> None:
    """Senza festivita_set, la pipeline carica festivita_per_anno()."""
    corse = [
        _corsa("S_FIO", "S_X", 8, 0, 9, 30, treno="T1"),
    ]
    params = ParamPipelineLineaCentrica(
        sedi_disponibili={"FIO": "S_FIO"},
        materiale_per_segmento={"R31_completo": "ETR522"},
        periodo_da=date(2026, 6, 8),
        periodo_a=date(2026, 6, 8),
        # festivita_set non specificato
    )
    # Non deve crashare
    result = esegui_pipeline_linea_centrica(corse, params)
    assert result is not None


# =====================================================================
# Edge cases
# =====================================================================


def test_pipeline_corse_vuote() -> None:
    """Lista corse vuota → output vuoto pulito."""
    params = ParamPipelineLineaCentrica(
        sedi_disponibili={"FIO": "S_FIO"},
        periodo_da=date(2026, 6, 8),
        periodo_a=date(2026, 6, 8),
    )
    result = esegui_pipeline_linea_centrica([], params)
    assert result.giri == []
    assert result.linee == []
    assert result.turni == []


def test_pipeline_regola_id_propagato_a_giri() -> None:
    """regola_per_segmento propagato a CatenaPosizionata.regola_id."""
    corse = [
        _corsa("S_FIO", "S_X", 8, 0, 9, 30, treno="T1"),
        _corsa("S_X", "S_FIO", 10, 0, 11, 30, treno="T2"),
    ]
    params = ParamPipelineLineaCentrica(
        sedi_disponibili={"FIO": "S_FIO"},
        materiale_per_segmento={"R31_completo": "ETR522"},
        regola_per_segmento={"R31_completo": 42},
        periodo_da=date(2026, 6, 8),
        periodo_a=date(2026, 6, 8),
    )
    result = esegui_pipeline_linea_centrica(corse, params)
    assert len(result.giri) == 1
    assert result.giri[0].giornate[0].catena_posizionata.regola_id == 42
