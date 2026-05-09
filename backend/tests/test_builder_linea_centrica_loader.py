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


# =====================================================================
# Sprint 8.2 MR-D5h-bis — fix collisione regole (S1 HIGH BLOCKING)
# Chiude critica SEVERO 6/10 entry 278: pre-fix tutte le linee
# venivano sovrascritte dalla regola 53 (multi-direttrice).
# =====================================================================


def test_mappature_specificity_regola_specifica_vince_su_ampia_mr_d5h_bis() -> None:
    """Regola con 1 sola direttrice (specifica) deve vincere su regola
    con 8 direttrici (ampia) sulla stessa linea condivisa. Riproduce
    il caso prog 17: regola 47 ETR526 [TIRANO] vs regola 53 ETR204
    [TIRANO + 7 altre]."""
    regola_specifica = _StubRegola(
        id=47,
        filtri_json=[{"campo": "direttrice", "valore": ["TIRANO-MI"]}],
        composizione_json=_comp("ETR526"),
    )
    regola_ampia = _StubRegola(
        id=53,
        filtri_json=[
            {
                "campo": "direttrice",
                "valore": [
                    "TIRANO-MI",
                    "BG-Carnate",
                    "ALES-MI",
                    "BS-CR",
                    "MI-LO",
                    "PV-MI",
                    "VR-MI",
                    "FE-MI",
                ],
            }
        ],
        composizione_json=_comp("ETR204"),
    )
    corse = [
        _StubCorsa(codice_linea="R5", direttrice="TIRANO-MI"),
        _StubCorsa(codice_linea="R11", direttrice="BG-Carnate"),
    ]
    out = _costruisci_mappature_regole_linee(
        regole=[regola_specifica, regola_ampia], corse=corse
    )
    mat_seg, reg_seg, _ = out
    # Linea condivisa TIRANO → assegnata alla regola SPECIFICA (47, ETR526)
    assert mat_seg["R5_completo"] == "ETR526", (
        "Regola specifica deve vincere su ampia (skip-if-exists)"
    )
    assert reg_seg["R5_completo"] == 47
    # Linea NON condivisa BG-Carnate (solo regola 53) → ETR204
    assert mat_seg["R11_completo"] == "ETR204"
    assert reg_seg["R11_completo"] == 53


def test_mappature_specificity_ordine_input_irrilevante() -> None:
    """Test che l'ordine di input delle regole NON influisce sull'esito
    (era il bug pre-MR-D5h-bis: last-write per ordine arbitrario)."""
    r_spec = _StubRegola(
        id=47,
        filtri_json=[{"campo": "direttrice", "valore": ["TIRANO-MI"]}],
        composizione_json=_comp("ETR526"),
    )
    r_ampia = _StubRegola(
        id=53,
        filtri_json=[
            {"campo": "direttrice", "valore": ["TIRANO-MI", "BG", "ALES"]}
        ],
        composizione_json=_comp("ETR204"),
    )
    corse = [
        _StubCorsa(codice_linea="R5", direttrice="TIRANO-MI"),
    ]
    # Ordine A: specifica prima
    out_a = _costruisci_mappature_regole_linee(
        regole=[r_spec, r_ampia], corse=corse
    )
    # Ordine B: ampia prima
    out_b = _costruisci_mappature_regole_linee(
        regole=[r_ampia, r_spec], corse=corse
    )
    # Same result: regola specifica vince in entrambi
    assert out_a[0] == out_b[0]
    assert out_a[1] == out_b[1]
    assert out_a[0]["R5_completo"] == "ETR526"


def test_mappature_specificity_tie_break_id_minore() -> None:
    """2 regole con stessa specificity (1 direttrice) e linea condivisa
    → vince r.id minore (tie-break deterministic)."""
    r_low_id = _StubRegola(
        id=10,
        filtri_json=[{"campo": "direttrice", "valore": ["X"]}],
        composizione_json=_comp("ETR1"),
    )
    r_high_id = _StubRegola(
        id=99,
        filtri_json=[{"campo": "direttrice", "valore": ["X"]}],
        composizione_json=_comp("ETR2"),
    )
    corse = [_StubCorsa(codice_linea="L1", direttrice="X")]
    out = _costruisci_mappature_regole_linee(
        regole=[r_high_id, r_low_id],  # ordine inverso
        corse=corse,
    )
    mat_seg, reg_seg, _ = out
    # r.id=10 vince per tie-break id ASC
    assert mat_seg["L1_completo"] == "ETR1"
    assert reg_seg["L1_completo"] == 10


def test_mappature_specificity_codice_linea_diretto_piu_specifico_di_direttrice() -> None:
    """Regola con `codice_linea=[R5]` (1 linea diretta) ha specificity 1.
    Regola con direttrice che espande in 5 linee ha specificity 5.
    Il filtro diretto vince sulla direttrice ampia."""
    r_diretto = _StubRegola(
        id=10,
        filtri_json=[{"campo": "codice_linea", "valore": ["R5"]}],
        composizione_json=_comp("ETR_DIRETTO"),
    )
    r_direttrice = _StubRegola(
        id=20,
        filtri_json=[{"campo": "direttrice", "valore": ["BIG-Direttrice"]}],
        composizione_json=_comp("ETR_AMPIO"),
    )
    corse = [
        _StubCorsa(codice_linea="R5", direttrice="BIG-Direttrice"),
        _StubCorsa(codice_linea="R6", direttrice="BIG-Direttrice"),
        _StubCorsa(codice_linea="R7", direttrice="BIG-Direttrice"),
        _StubCorsa(codice_linea="R8", direttrice="BIG-Direttrice"),
        _StubCorsa(codice_linea="R9", direttrice="BIG-Direttrice"),
    ]
    out = _costruisci_mappature_regole_linee(
        regole=[r_diretto, r_direttrice], corse=corse
    )
    mat_seg, _, _ = out
    # R5 → vinta da r_diretto (specificity 1 vs 5)
    assert mat_seg["R5_completo"] == "ETR_DIRETTO"
    # R6-R9 → vinte da r_direttrice (uniche coperte)
    assert mat_seg["R6_completo"] == "ETR_AMPIO"
    assert mat_seg["R9_completo"] == "ETR_AMPIO"


@pytest.mark.xfail(
    reason=(
        "MR-D5h-bis S5 (entry 278) — limite documentato: regole con SOLO "
        "filtro `categoria` o `tipologia` (senza linea o direttrice) hanno "
        "specificity 2^31-1 (= wildcard, in fondo). Le linee NON vengono "
        "mappate perché non c'è espansione `categoria → linee`. "
        "Risoluzione: scope MR-D7 (resolver per-corsa). Test passerà "
        "quando MR-D7 implementerà l'espansione."
    ),
    strict=True,
)
def test_mappature_filtro_categoria_only_xfail_mr_d7() -> None:
    """xfail: documenta che regole con solo filtro `categoria` non
    producono mapping. Comportamento accettato fino a MR-D7."""
    regola = _StubRegola(
        id=1,
        filtri_json=[{"campo": "categoria", "valore": ["R"]}],
        composizione_json=_comp("ETR204"),
    )
    corse = [_StubCorsa(codice_linea="R5", direttrice=None)]
    out = _costruisci_mappature_regole_linee(regole=[regola], corse=corse)
    mat_seg, _, _ = out
    # Atteso (post-MR-D7): R5 → ETR204 perché categoria=R matcha
    # Pre-MR-D7: mat_seg vuoto (la specificity è wildcard, no espansione)
    assert mat_seg["R5_completo"] == "ETR204"


@pytest.mark.xfail(
    reason=(
        "MR-D5h-bis S6 (entry 278) — limite documentato: il warning "
        "MR-D5h-DUAL `_traduce_e_filtra_giri_linea_centrica` aggrega tutte "
        "le sedi operative divergenti in una stringa unica `[CRE, LEC]`. "
        "Per MR-D6 (vuoti tecnici rientro) servirebbe granularità per "
        "giro: `giro_id → sede_operativa_codice`. Risoluzione: scope MR-D6."
    ),
    strict=True,
)
def test_mappature_warning_sede_granulare_per_giro_xfail_mr_d6() -> None:
    """xfail: documenta che il warning MR-D5h-DUAL nascente da
    `_traduce_e_filtra_giri_linea_centrica` aggrega le sedi operative
    senza granularità per giro. Test passerà quando MR-D6 esporrà
    `BuilderResultResponse.giri_con_sede_operativa: list[dict]`."""
    # Stub di test: verifica esistenza dell'attributo che MR-D6 deve
    # aggiungere a `BuilderResult` (non esiste pre-MR-D6).
    from colazione.domain.builder_giro.builder import BuilderResult

    result = BuilderResult(
        giri_ids=[],
        n_giri_creati=0,
        n_corse_processate=0,
        n_corse_residue=0,
        n_giri_chiusi=0,
        n_giri_non_chiusi=0,
        n_eventi_composizione=0,
        n_incompatibilita_materiale=0,
    )
    # Atteso (post-MR-D6): attributo esiste, lista vuota di default
    assert hasattr(result, "giri_con_sede_operativa")
    assert getattr(result, "giri_con_sede_operativa", None) == []


def test_mappature_caso_prog_17_reale_simulato() -> None:
    """Riproduce esattamente la collisione di prog 17 (entry 278):
    regola 47 ETR526 vs regola 53 ETR204 multi-direttrice. Atteso:
    R5/RE5 (TIRANO) → ETR526 (regola 47), R11/R12 (BG) → MD/ETR522
    (regole 50/51), R31 → ETR204 (regola 53 unica copertura)."""
    regole = [
        _StubRegola(  # ETR526 TIRANO (1 direttrice)
            id=47,
            filtri_json=[
                {"campo": "direttrice", "valore": ["TIRANO-SONDRIO-LECCO-MILANO"]}
            ],
            composizione_json=_comp("ETR526"),
        ),
        _StubRegola(  # MD BG-CARNATE (1 direttrice)
            id=50,
            filtri_json=[
                {"campo": "direttrice", "valore": ["BERGAMO-CARNATE-MILANO"]}
            ],
            composizione_json=_comp("MD"),
        ),
        _StubRegola(  # ETR204 multi-direttrice (8 valori)
            id=53,
            filtri_json=[
                {
                    "campo": "direttrice",
                    "valore": [
                        "BERGAMO-TREVIGLIO",
                        "CHIAVENNA-COLICO",
                        "TIRANO-SONDRIO-LECCO-MILANO",  # collide regola 47
                        "BERGAMO-CARNATE-MILANO",  # collide regola 50
                        "MANTOVA-CREMONA-LODI-MILANO",
                    ],
                }
            ],
            composizione_json=_comp("ETR204"),
        ),
    ]
    corse = [
        _StubCorsa(codice_linea="R5", direttrice="TIRANO-SONDRIO-LECCO-MILANO"),
        _StubCorsa(codice_linea="RE5", direttrice="TIRANO-SONDRIO-LECCO-MILANO"),
        _StubCorsa(codice_linea="R11", direttrice="BERGAMO-CARNATE-MILANO"),
        _StubCorsa(codice_linea="R12", direttrice="BERGAMO-CARNATE-MILANO"),
        _StubCorsa(codice_linea="R8", direttrice="BERGAMO-TREVIGLIO"),  # solo R53
        _StubCorsa(codice_linea="R7", direttrice="CHIAVENNA-COLICO"),  # solo R53
    ]
    out = _costruisci_mappature_regole_linee(regole=regole, corse=corse)
    mat_seg, _, _ = out
    # TIRANO → ETR526 (regola 47 specifica vince su 53 ampia)
    assert mat_seg["R5_completo"] == "ETR526"
    assert mat_seg["RE5_completo"] == "ETR526"
    # BG-CARNATE → MD (regola 50 specifica vince su 53 ampia)
    assert mat_seg["R11_completo"] == "MD"
    assert mat_seg["R12_completo"] == "MD"
    # BG-TREVIGLIO + CHIAVENNA → ETR204 (solo regola 53 le copre)
    assert mat_seg["R8_completo"] == "ETR204"
    assert mat_seg["R7_completo"] == "ETR204"
