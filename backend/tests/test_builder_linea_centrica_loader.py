"""Test loader e helpers del ramo linea-centrica (Sprint 8.2 MR-D5f→f-tris).

Chiude finding HIGH S2 + S3 della critica SEVERO 5/10
(`docs/critiche/SPRINT-8.2-MR-D5f-trio-codice-committato.md`):
- ``_carica_sedi_attive_azienda``: nessun test prima
- ``direttrice_to_linee`` mapping (cuore del fix MR-D5f-tris): nessun test

Approccio: mock ``AsyncSession.execute`` con ``unittest.mock.AsyncMock``
+ stub `LocalitaManutenzione` (no DB). Pattern preso da
``tests/test_vettura_resolver.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from colazione.domain.builder_giro.builder import (
    _carica_sedi_attive_azienda,
    _costruisci_mappature_regole_linee,
)

# =====================================================================
# Stub LocalitaManutenzione minimale
# =====================================================================


@dataclass
class _StubLocalita:
    codice: str
    stazione_collegata_codice: str | None
    is_attiva: bool = True
    azienda_id: int = 2
    codice_breve: str = "XX"


def _mock_session(rows: list[_StubLocalita]) -> Any:
    """Crea un mock AsyncSession che ritorna `rows` da execute().scalars().all().

    Pattern: ``execute()`` ritorna un Result object (mock); il Result ha
    ``scalars()`` (sync) che ritorna ScalarResult (mock); ScalarResult
    ha ``.all()`` (sync) che ritorna la lista.
    """
    session = MagicMock()
    scalar_result = MagicMock()
    scalar_result.all = MagicMock(return_value=list(rows))
    result = MagicMock()
    result.scalars = MagicMock(return_value=scalar_result)
    session.execute = AsyncMock(return_value=result)
    return session


# =====================================================================
# Sprint 8.2 MR-D5h-A pre-requisiti: test S2 (HIGH SEVERO)
# =====================================================================


@pytest.mark.asyncio
async def test_carica_sedi_attive_caso_felice() -> None:
    """3 sedi tutte attive con stazione_collegata → dict 3 entries."""
    rows = [
        _StubLocalita(codice="IMPMAN_FIO", stazione_collegata_codice="S_FIO"),
        _StubLocalita(codice="IMPMAN_CRE", stazione_collegata_codice="S_CRE"),
        _StubLocalita(codice="IMPMAN_LEC", stazione_collegata_codice="S_LEC"),
    ]
    session = _mock_session(rows)
    out = await _carica_sedi_attive_azienda(session, azienda_id=2)
    assert out == {
        "IMPMAN_FIO": "S_FIO",
        "IMPMAN_CRE": "S_CRE",
        "IMPMAN_LEC": "S_LEC",
    }


@pytest.mark.asyncio
async def test_carica_sedi_attive_filtra_stazione_null() -> None:
    """Sede con stazione_collegata=None NON è inclusa (defensive double
    filter: query SQL già filtra ma il loop conferma per type safety).
    """
    rows = [
        _StubLocalita(codice="IMPMAN_FIO", stazione_collegata_codice="S_FIO"),
        _StubLocalita(
            codice="POOL_TILO", stazione_collegata_codice=None
        ),  # esempio reale: TILO Svizzera
    ]
    session = _mock_session(rows)
    out = await _carica_sedi_attive_azienda(session, azienda_id=2)
    assert out == {"IMPMAN_FIO": "S_FIO"}
    assert "POOL_TILO" not in out


@pytest.mark.asyncio
async def test_carica_sedi_attive_lista_vuota() -> None:
    """0 sedi nel DB → dict vuoto, no exception."""
    session = _mock_session([])
    out = await _carica_sedi_attive_azienda(session, azienda_id=2)
    assert out == {}


@pytest.mark.asyncio
async def test_carica_sedi_attive_query_chiamata_una_volta() -> None:
    """Sanity: la helper chiama execute() esattamente 1 volta (no N+1)."""
    rows = [_StubLocalita(codice="IMPMAN_FIO", stazione_collegata_codice="S_FIO")]
    session = _mock_session(rows)
    await _carica_sedi_attive_azienda(session, azienda_id=2)
    assert session.execute.call_count == 1


@pytest.mark.asyncio
async def test_carica_sedi_attive_dict_keys_sono_codice() -> None:
    """Le chiavi del dict sono `codice` (non `codice_breve` o id)."""
    rows = [
        _StubLocalita(
            codice="IMPMAN_MILANO_FIORENZA",
            stazione_collegata_codice="S01640",
            codice_breve="FIO",
        ),
    ]
    session = _mock_session(rows)
    out = await _carica_sedi_attive_azienda(session, azienda_id=2)
    assert "IMPMAN_MILANO_FIORENZA" in out
    assert "FIO" not in out  # codice_breve NON usato come chiave
    assert out["IMPMAN_MILANO_FIORENZA"] == "S01640"


# =====================================================================
# Sprint 8.2 MR-D5h-A pre-requisiti: test S3 (HIGH SEVERO)
# Helper `_costruisci_mappature_regole_linee` estratta da builder.py
# =====================================================================


@dataclass
class _StubRegola:
    id: int
    filtri_json: list[dict[str, Any]]
    composizione_json: list[dict[str, Any]]
    materiale_tipo_codice: str | None = None


@dataclass
class _StubCorsa:
    codice_linea: str | None
    direttrice: str | None


def _comp(materiale: str, n: int = 1) -> list[dict[str, Any]]:
    return [{"materiale_tipo_codice": materiale, "n_pezzi": n}]


def test_mappature_caso_codice_linea_diretto() -> None:
    """Caso classico (legacy): regola con filtro `codice_linea` →
    mapping diretto."""
    regola = _StubRegola(
        id=10,
        filtri_json=[{"campo": "codice_linea", "valore": ["R31"]}],
        composizione_json=_comp("ETR526"),
    )
    out = _costruisci_mappature_regole_linee(
        regole=[regola],
        corse=[],  # non serve perché filter è codice_linea diretto
    )
    mat_seg, reg_seg, mat_reg = out
    assert mat_seg == {"R31_completo": "ETR526"}
    assert reg_seg == {"R31_completo": 10}
    assert mat_reg == {10: "ETR526"}


def test_mappature_caso_direttrice_espande_linee_mr_d5f_tris() -> None:
    """Cuore del fix MR-D5f-tris: regola con `direttrice` viene
    espansa via mapping pre-calcolato dalle corse."""
    regola = _StubRegola(
        id=47,
        filtri_json=[
            {"campo": "direttrice", "valore": ["TIRANO-SONDRIO-LECCO-MILANO"]}
        ],
        composizione_json=_comp("ETR526"),
    )
    corse = [
        _StubCorsa(codice_linea="R5", direttrice="TIRANO-SONDRIO-LECCO-MILANO"),
        _StubCorsa(codice_linea="RE5", direttrice="TIRANO-SONDRIO-LECCO-MILANO"),
        _StubCorsa(codice_linea="R31", direttrice="ALTRA-DIRETTRICE"),  # esclusa
    ]
    out = _costruisci_mappature_regole_linee(regole=[regola], corse=corse)
    mat_seg, reg_seg, mat_reg = out
    # R5 e RE5 mappati, R31 NO (altra direttrice)
    assert mat_seg == {"R5_completo": "ETR526", "RE5_completo": "ETR526"}
    assert reg_seg == {"R5_completo": 47, "RE5_completo": 47}
    assert mat_reg == {47: "ETR526"}


def test_mappature_caso_misto_codice_linea_e_direttrice() -> None:
    """Regola con ENTRAMBI i filtri → linee unione."""
    regola = _StubRegola(
        id=99,
        filtri_json=[
            {"campo": "codice_linea", "valore": ["R11"]},
            {"campo": "direttrice", "valore": ["BERGAMO-CARNATE-MILANO"]},
        ],
        composizione_json=_comp("ETR522"),
    )
    corse = [
        _StubCorsa(codice_linea="R12", direttrice="BERGAMO-CARNATE-MILANO"),
        _StubCorsa(codice_linea="RE6", direttrice="BERGAMO-CARNATE-MILANO"),
    ]
    out = _costruisci_mappature_regole_linee(regole=[regola], corse=corse)
    mat_seg, _, _ = out
    # R11 da codice_linea + R12, RE6 da direttrice
    assert set(mat_seg.keys()) == {
        "R11_completo",
        "R12_completo",
        "RE6_completo",
    }


def test_mappature_caso_direttrice_string_singolo() -> None:
    """`valore` può essere stringa singola, non solo lista."""
    regola = _StubRegola(
        id=1,
        filtri_json=[{"campo": "direttrice", "valore": "BS-PIADENA-PARMA"}],
        composizione_json=_comp("ATR803"),
    )
    corse = [
        _StubCorsa(codice_linea="R27", direttrice="BS-PIADENA-PARMA"),
    ]
    out = _costruisci_mappature_regole_linee(regole=[regola], corse=corse)
    mat_seg, _, _ = out
    assert mat_seg == {"R27_completo": "ATR803"}


def test_mappature_caso_regola_senza_materiale_skippata() -> None:
    """Regola con composizione vuota (no materiale risolvibile) →
    NON aggiunta alle mappature, neanche `materiale_per_regola`.
    """
    regola_vuota = _StubRegola(
        id=666,
        filtri_json=[{"campo": "codice_linea", "valore": ["R5"]}],
        composizione_json=[],  # no composizione
        materiale_tipo_codice=None,  # legacy field anche None
    )
    out = _costruisci_mappature_regole_linee(regole=[regola_vuota], corse=[])
    mat_seg, reg_seg, mat_reg = out
    assert mat_seg == {}
    assert reg_seg == {}
    assert mat_reg == {}


def test_mappature_caso_direttrice_non_in_corse_set_vuoto() -> None:
    """Direttrice citata da regola ma nessuna corsa la ha →
    `linee_regola` vuoto (no mapping)."""
    regola = _StubRegola(
        id=53,
        filtri_json=[{"campo": "direttrice", "valore": ["DIRETTRICE-INESISTENTE"]}],
        composizione_json=_comp("ETR204"),
    )
    out = _costruisci_mappature_regole_linee(regole=[regola], corse=[])
    mat_seg, reg_seg, mat_reg = out
    # mat_reg popolato (regola valida) ma mat_seg vuoto (no linee)
    assert mat_seg == {}
    assert reg_seg == {}
    assert mat_reg == {53: "ETR204"}


def test_mappature_caso_filtri_non_dict_skippato() -> None:
    """Defensive: filtri_json contiene elementi non-dict → skip."""
    regola = _StubRegola(
        id=1,
        filtri_json=[
            "non un dict",  # type: ignore[list-item]
            {"campo": "codice_linea", "valore": ["R5"]},
        ],
        composizione_json=_comp("ETR526"),
    )
    out = _costruisci_mappature_regole_linee(regole=[regola], corse=[])
    mat_seg, _, _ = out
    assert mat_seg == {"R5_completo": "ETR526"}


def test_mappature_caso_n_regole_segmenti_unione() -> None:
    """N regole, segmenti di linee diverse → mapping unione."""
    r1 = _StubRegola(
        id=1,
        filtri_json=[{"campo": "codice_linea", "valore": ["R5"]}],
        composizione_json=_comp("ETR526"),
    )
    r2 = _StubRegola(
        id=2,
        filtri_json=[{"campo": "codice_linea", "valore": ["R11"]}],
        composizione_json=_comp("ETR522"),
    )
    out = _costruisci_mappature_regole_linee(regole=[r1, r2], corse=[])
    mat_seg, reg_seg, mat_reg = out
    assert mat_seg == {"R5_completo": "ETR526", "R11_completo": "ETR522"}
    assert reg_seg == {"R5_completo": 1, "R11_completo": 2}
    assert mat_reg == {1: "ETR526", 2: "ETR522"}


def test_mappature_caso_regole_vuote() -> None:
    """0 regole → 3 dict vuoti."""
    out = _costruisci_mappature_regole_linee(regole=[], corse=[])
    mat_seg, reg_seg, mat_reg = out
    assert mat_seg == {}
    assert reg_seg == {}
    assert mat_reg == {}
