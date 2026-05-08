"""Test per ``risolvi_corsa_esplorativo`` (Sprint 8.1 MR-A3, entry 244).

Vincolo soft tier-based decisione utente Q1=b 2026-05-08:
- Tier 0 (esatto) = match AND-rigido (legacy `risolvi_corsa`).
- Tier 1 (materiale compatibile) = filtri ignorati, vincoli rispettati,
  penalty TIER_1_PENALTY (50).

Sblocca caso bloccante "regola unica linea=R11 → 0 giri": corse di
altre linee oggi scartate, domani assegnate ETR421 al Tier 1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from typing import Any

import pytest

from colazione.domain.builder_giro.risolvi_corsa import (
    TIER_1_PENALTY,
    AssegnazioneRisolta,
    risolvi_corsa,
    risolvi_corsa_esplorativo,
)

# =====================================================================
# Fixture
# =====================================================================


@dataclass(frozen=True)
class _CorsaFake:
    numero_treno: str = "10000"
    codice_origine: str = "S_A"
    codice_destinazione: str = "S_B"
    ora_partenza: time = time(8, 0)
    ora_arrivo: time = time(9, 0)
    codice_linea: str = "R11"
    valido_in_date_json: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _RegolaFake:
    id: int
    filtri_json: list[dict[str, Any]] = field(default_factory=list)
    composizione_json: list[dict[str, Any]] = field(
        default_factory=lambda: [{"materiale_tipo_codice": "ETR421", "n_pezzi": 1}]
    )
    is_composizione_manuale: bool = False
    priorita: int = 60


# =====================================================================
# Tier 0: match esatto = identico al legacy
# =====================================================================


def test_tier0_match_esatto_uguale_legacy() -> None:
    """Quando la regola matcha sui filtri, l'esplorativo si comporta
    come il legacy: stessa regola, stessa composizione, tier=0,
    penalty=0.
    """
    corsa = _CorsaFake(codice_linea="R11")
    regola = _RegolaFake(
        id=1,
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "R11"}],
    )
    out = risolvi_corsa_esplorativo(corsa, [regola], date(2026, 6, 1))
    assert out is not None
    assert out.regola_id == 1
    assert out.tier_applicato == 0
    assert out.penalty == 0
    assert out.composizione[0].materiale_tipo_codice == "ETR421"
    # Confronto con legacy: stesso output (modulo tier/penalty default).
    legacy = risolvi_corsa(corsa, [regola], date(2026, 6, 1))
    assert legacy is not None
    assert out.regola_id == legacy.regola_id
    assert out.composizione == legacy.composizione


# =====================================================================
# Tier 1: filtri non match, ma materiale compatibile
# =====================================================================


def test_tier1_caso_utente_linea_diversa() -> None:
    """Caso utente bloccante: regola unica linea=R11 + corsa S5 →
    Tier 1 assegna ETR421 con penalty.
    """
    corsa_s5 = _CorsaFake(codice_linea="S5", numero_treno="11111")
    regola_r11 = _RegolaFake(
        id=42,
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "R11"}],
    )
    out = risolvi_corsa_esplorativo(corsa_s5, [regola_r11], date(2026, 6, 1))
    assert out is not None
    assert out.regola_id == 42
    assert out.tier_applicato == 1
    assert out.penalty == TIER_1_PENALTY
    assert out.composizione[0].materiale_tipo_codice == "ETR421"


def test_tier1_priorita_piu_alta_vince() -> None:
    """Più regole candidate Tier 1: vince priorità più alta."""
    corsa = _CorsaFake(codice_linea="S11")
    r_low = _RegolaFake(
        id=1,
        priorita=30,
        composizione_json=[{"materiale_tipo_codice": "ETR421", "n_pezzi": 1}],
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "R11"}],
    )
    r_high = _RegolaFake(
        id=2,
        priorita=80,
        composizione_json=[{"materiale_tipo_codice": "ETR522", "n_pezzi": 1}],
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "S5"}],
    )
    out = risolvi_corsa_esplorativo(corsa, [r_low, r_high], date(2026, 6, 1))
    assert out is not None
    assert out.regola_id == 2
    assert out.composizione[0].materiale_tipo_codice == "ETR522"
    assert out.tier_applicato == 1


def test_tier1_tie_break_id_ascendente() -> None:
    """Stessa priorità + stessa specificità → vince id più basso
    (tie-break deterministico identico al legacy)."""
    corsa = _CorsaFake(codice_linea="S11")
    r_a = _RegolaFake(
        id=10,
        priorita=60,
        composizione_json=[{"materiale_tipo_codice": "ETR421", "n_pezzi": 1}],
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "R11"}],
    )
    r_b = _RegolaFake(
        id=5,
        priorita=60,
        composizione_json=[{"materiale_tipo_codice": "ETR522", "n_pezzi": 1}],
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "S5"}],
    )
    out = risolvi_corsa_esplorativo(corsa, [r_a, r_b], date(2026, 6, 1))
    assert out is not None
    assert out.regola_id == 5  # id più basso
    assert out.tier_applicato == 1


# =====================================================================
# Edge cases: fallback corretto
# =====================================================================


def test_lista_regole_vuota_ritorna_none() -> None:
    out = risolvi_corsa_esplorativo(_CorsaFake(), [], date(2026, 6, 1))
    assert out is None


def test_regola_senza_composizione_ritorna_none_anche_tier1() -> None:
    """Regola con composizione_json=[] non assegnabile in nessun tier."""
    corsa = _CorsaFake(codice_linea="S5")
    regola_orfana = _RegolaFake(
        id=99,
        composizione_json=[],
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "R11"}],
    )
    out = risolvi_corsa_esplorativo(corsa, [regola_orfana], date(2026, 6, 1))
    # Tier 0 fallisce sui filtri, Tier 1 fallisce su composizione vuota
    # (corsa orfana → caller scarta).
    assert out is None


def test_tier0_preferito_a_tier1_quando_disponibili_entrambi() -> None:
    """Se 1 regola match esattamente e 1 no, vince quella esatta."""
    corsa = _CorsaFake(codice_linea="R11")
    r_match = _RegolaFake(
        id=1,
        priorita=30,  # bassa priorità ma match
        composizione_json=[{"materiale_tipo_codice": "ETR421", "n_pezzi": 1}],
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "R11"}],
    )
    r_no_match_high_prio = _RegolaFake(
        id=2,
        priorita=80,  # alta priorità ma non match
        composizione_json=[{"materiale_tipo_codice": "ETR522", "n_pezzi": 1}],
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "S5"}],
    )
    out = risolvi_corsa_esplorativo(
        corsa, [r_match, r_no_match_high_prio], date(2026, 6, 1)
    )
    assert out is not None
    assert out.regola_id == 1  # match esatto vince anche se priorità più bassa
    assert out.tier_applicato == 0
    assert out.penalty == 0


# =====================================================================
# Composizione doppia + accoppiamento
# =====================================================================


def test_tier1_accoppiamento_validato() -> None:
    """Composizione doppia con materiali NON accoppiabili → eccezione."""
    corsa = _CorsaFake(codice_linea="S5")
    regola_doppia = _RegolaFake(
        id=1,
        composizione_json=[
            {"materiale_tipo_codice": "ETR526", "n_pezzi": 1},
            {"materiale_tipo_codice": "E464", "n_pezzi": 1},
        ],
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "R11"}],
        is_composizione_manuale=False,
    )
    # Callback che NEGA tutti gli accoppiamenti.
    nessuno_ammesso: Any = lambda _a, _b: False  # noqa: E731
    from colazione.domain.builder_giro.risolvi_corsa import (
        ComposizioneNonAmmessaError,
    )

    with pytest.raises(ComposizioneNonAmmessaError):
        risolvi_corsa_esplorativo(
            corsa,
            [regola_doppia],
            date(2026, 6, 1),
            is_accoppiamento_ammesso=nessuno_ammesso,
        )


def test_a3bis_tier1_esclude_is_composizione_manuale() -> None:
    """Sprint 8.1 MR-A3-bis (entry 248) MED-NINO-2 fix: Tier 1
    ESCLUDE regole con ``is_composizione_manuale=True``.

    Razionale: regole manuali sono override mirati dal pianificatore
    per scope specifici (composizioni custom non validate da
    accoppiamento_ammesso). Promuoverle a fallback Tier 1 generico
    sarebbe un bypass del design — userebbe la regola "speciale"
    per casi out-of-scope.

    Tier 0 (match esatto sui filtri) le accetta normalmente; Tier 1
    le skippa.
    """
    # Tier 0: corsa che matcha la regola manuale (linea R11).
    corsa_match = _CorsaFake(codice_linea="R11")
    regola_manuale = _RegolaFake(
        id=1,
        composizione_json=[
            {"materiale_tipo_codice": "ETR526", "n_pezzi": 1},
        ],
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "R11"}],
        is_composizione_manuale=True,
    )
    out_t0 = risolvi_corsa_esplorativo(
        corsa_match, [regola_manuale], date(2026, 6, 1)
    )
    assert out_t0 is not None
    assert out_t0.tier_applicato == 0  # Tier 0 accetta is_composizione_manuale
    assert out_t0.is_composizione_manuale is True

    # Tier 1: corsa fuori match (linea S5). Regola manuale → SKIP a Tier 1.
    corsa_no_match = _CorsaFake(codice_linea="S5")
    out_t1 = risolvi_corsa_esplorativo(
        corsa_no_match, [regola_manuale], date(2026, 6, 1)
    )
    assert out_t1 is None  # Tier 1 esclude regole manuali


# =====================================================================
# AssegnazioneRisolta default backward-compat
# =====================================================================


def test_assegnazione_risolta_default_tier_e_penalty() -> None:
    """Costruita senza i nuovi campi: tier=0, penalty=0 (retrocompat)."""
    from colazione.domain.builder_giro.risolvi_corsa import ComposizioneItem

    a = AssegnazioneRisolta(
        regola_id=1,
        composizione=(ComposizioneItem("ETR421", 1),),
    )
    assert a.tier_applicato == 0
    assert a.penalty == 0


def test_legacy_risolvi_corsa_non_setta_tier_o_penalty() -> None:
    """Il legacy `risolvi_corsa` mantiene tier=0/penalty=0 di default
    (non viene a sapere dell'esistenza di tier > 0).
    """
    corsa = _CorsaFake(codice_linea="R11")
    regola = _RegolaFake(
        id=1,
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "R11"}],
    )
    out = risolvi_corsa(corsa, [regola], date(2026, 6, 1))
    assert out is not None
    assert out.tier_applicato == 0
    assert out.penalty == 0


# =====================================================================
# Re-export
# =====================================================================


def test_re_export_da_builder_giro_init() -> None:
    from colazione.domain import builder_giro

    assert builder_giro.risolvi_corsa_esplorativo is risolvi_corsa_esplorativo
    assert builder_giro.TIER_1_PENALTY == TIER_1_PENALTY


# =====================================================================
# Sprint 8.1 MR-A3-bis (entry 248) — fix CRITICAL-1 + HIGH-3
# =====================================================================


def test_a3bis_critical1_tier_1_penalty_allineato_matrice() -> None:
    """CRITICAL-1 fix: TIER_1_PENALTY = 20 allineato a matrice
    `vincoli_soft.tier_vincoli_default()` peso LINEA tier
    'materiale_compatibile' (tier 1). Era 50 magic number senza
    giustificazione (50 ∉ {20, 40, 70} della matrice).
    """
    assert TIER_1_PENALTY == 20


def test_a3bis_high3_tie_break_tier1_no_len_filtri() -> None:
    """HIGH-3 fix: tie-break Tier 1 NON usa ``len(filtri_json)``.
    Al Tier 1 i filtri sono ignorati, ordinare per "specificità"
    è bias su metadato non valutato.

    Setup: 2 regole stessa priorità con filtri diversi (1 vs 5).
    La corsa non matcha né l'una né l'altra (linea fuori scope).
    Pre-fix: vinceva la regola con più filtri (len_filtri DESC).
    Post-fix: vince id ASC = regola id più basso (creata prima).
    """
    corsa_no_match = _CorsaFake(codice_linea="S99")
    r_pochi_filtri = _RegolaFake(
        id=10,  # id alto
        priorita=60,
        composizione_json=[{"materiale_tipo_codice": "ETR421", "n_pezzi": 1}],
        # 1 filtro
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "R11"}],
    )
    r_molti_filtri = _RegolaFake(
        id=5,  # id basso
        priorita=60,
        composizione_json=[{"materiale_tipo_codice": "ETR522", "n_pezzi": 1}],
        # 5 filtri
        filtri_json=[
            {"campo": "codice_linea", "op": "eq", "valore": "S5"},
            {"campo": "fascia_oraria", "op": "between", "valore": ["08:00", "12:00"]},
            {"campo": "giorno_tipo", "op": "in", "valore": ["feriale"]},
            {"campo": "categoria", "op": "eq", "valore": "REG"},
            {"campo": "stagione", "op": "eq", "valore": "estiva"},
        ],
    )
    out = risolvi_corsa_esplorativo(
        corsa_no_match,
        [r_pochi_filtri, r_molti_filtri],
        date(2026, 6, 1),
    )
    assert out is not None
    # Pre-fix: r_molti_filtri (len=5) avrebbe vinto.
    # Post-fix: id ASC → r_molti_filtri.id=5 < r_pochi_filtri.id=10
    # → r_molti_filtri vince per id, NON per len_filtri.
    # Per testare che len_filtri NON conta, scambio gli id:
    assert out.regola_id == 5  # id ASC vincente, indipendente da len_filtri


def test_a3bis_high3_tie_break_id_asc_anche_se_meno_filtri() -> None:
    """Conferma: id più basso vince anche con MENO filtri (=
    len_filtri NON è criterio).
    """
    corsa = _CorsaFake(codice_linea="S99")
    r_id_basso_pochi_filtri = _RegolaFake(
        id=3,
        priorita=60,
        composizione_json=[{"materiale_tipo_codice": "ETR421", "n_pezzi": 1}],
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "R11"}],
    )
    r_id_alto_molti_filtri = _RegolaFake(
        id=42,
        priorita=60,
        composizione_json=[{"materiale_tipo_codice": "ETR522", "n_pezzi": 1}],
        filtri_json=[
            {"campo": "codice_linea", "op": "eq", "valore": "S5"},
            {"campo": "fascia_oraria", "op": "between", "valore": ["08:00", "12:00"]},
            {"campo": "giorno_tipo", "op": "in", "valore": ["feriale"]},
        ],
    )
    out = risolvi_corsa_esplorativo(
        corsa,
        [r_id_basso_pochi_filtri, r_id_alto_molti_filtri],
        date(2026, 6, 1),
    )
    assert out is not None
    assert out.regola_id == 3  # id più basso vince, len_filtri irrilevante
    assert out.composizione[0].materiale_tipo_codice == "ETR421"
