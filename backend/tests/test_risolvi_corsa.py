"""Test puri Sprint 4.2 — `risolvi_corsa` + helper.

Tutti i test sono **senza DB**: usano dataclass minimali per
simulare corse e regole. Coprono:

- `determina_giorno_tipo`: festività, weekend, feriale.
- `matches_filtro` per ogni operatore (eq, in, between, gte, lte) e
  per `fascia_oraria` (parsing time strings).
- `matches_all` (AND, lista vuota).
- `risolvi_corsa`: nessuna regola, una sola, priorità, specificità,
  ambiguità (`RegolaAmbiguaError`), edge case.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from typing import Any

import pytest

from colazione.domain.builder_giro import (
    AssegnazioneRisolta,
    RegolaAmbiguaError,
    determina_giorno_tipo,
    estrai_valore_corsa,
    matches_all,
    matches_filtro,
    risolvi_corsa,
)

# =====================================================================
# Fixture dataclass minimali
# =====================================================================


@dataclass
class FakeCorsa:
    """Corsa minimale per test (specchia `CorsaCommerciale` ORM)."""

    numero_treno: str = "12345"
    rete: str | None = "RFI"
    categoria: str | None = "RE"
    codice_linea: str | None = "S5"
    direttrice: str | None = "MILANO-BERGAMO"
    codice_origine: str = "S01066"
    codice_destinazione: str = "S01747"
    is_treno_garantito_feriale: bool = False
    is_treno_garantito_festivo: bool = False
    ora_partenza: time = time(10, 0)


@dataclass
class FakeRegola:
    """Regola minimale per test."""

    id: int
    filtri_json: list[dict[str, Any]] = field(default_factory=list)
    materiale_tipo_codice: str = "ALe711"
    numero_pezzi: int = 3
    priorita: int = 60


# =====================================================================
# determina_giorno_tipo
# =====================================================================


def test_giorno_tipo_capodanno_giovedi_festivo() -> None:
    """1/1/2026 è giovedì → festivo per la regola festività."""
    assert determina_giorno_tipo(date(2026, 1, 1)) == "festivo"


def test_giorno_tipo_natale_lunedi_2023_festivo() -> None:
    """25/12/2023 (lunedì) → festivo."""
    assert determina_giorno_tipo(date(2023, 12, 25)) == "festivo"


def test_giorno_tipo_25_aprile_sabato_festivo() -> None:
    """25/4/2026 (sabato) è festa Liberazione → festivo (vince su sabato)."""
    assert determina_giorno_tipo(date(2026, 4, 25)) == "festivo"


def test_giorno_tipo_pasqua_2026_festivo() -> None:
    """Pasqua 2026 cade il 5/4 (domenica) → festivo."""
    assert determina_giorno_tipo(date(2026, 4, 5)) == "festivo"


def test_giorno_tipo_pasquetta_2026_festivo() -> None:
    """Pasquetta 2026: 6/4 (lunedì) → festivo."""
    assert determina_giorno_tipo(date(2026, 4, 6)) == "festivo"


def test_giorno_tipo_sabato_normale() -> None:
    assert determina_giorno_tipo(date(2026, 4, 18)) == "sabato"


def test_giorno_tipo_domenica_normale_festivo() -> None:
    assert determina_giorno_tipo(date(2026, 4, 19)) == "festivo"


def test_giorno_tipo_lunedi_normale_feriale() -> None:
    assert determina_giorno_tipo(date(2026, 4, 20)) == "feriale"


def test_giorno_tipo_venerdi_normale_feriale() -> None:
    assert determina_giorno_tipo(date(2026, 4, 17)) == "feriale"


# =====================================================================
# estrai_valore_corsa
# =====================================================================


def test_estrai_giorno_tipo_dal_parametro() -> None:
    """`giorno_tipo` non è un attributo della corsa, viene dalla data."""
    c = FakeCorsa()
    assert estrai_valore_corsa("giorno_tipo", c, "feriale") == "feriale"
    assert estrai_valore_corsa("giorno_tipo", c, "sabato") == "sabato"


def test_estrai_fascia_oraria_da_ora_partenza() -> None:
    c = FakeCorsa(ora_partenza=time(7, 30))
    assert estrai_valore_corsa("fascia_oraria", c, "feriale") == time(7, 30)


def test_estrai_codice_linea_via_getattr() -> None:
    c = FakeCorsa(codice_linea="RE51")
    assert estrai_valore_corsa("codice_linea", c, "feriale") == "RE51"


def test_estrai_treno_garantito_bool() -> None:
    c = FakeCorsa(is_treno_garantito_feriale=True)
    assert estrai_valore_corsa("is_treno_garantito_feriale", c, "feriale") is True


# =====================================================================
# matches_filtro — eq
# =====================================================================


def test_filtro_eq_codice_linea_match() -> None:
    c = FakeCorsa(codice_linea="S5")
    f = {"campo": "codice_linea", "op": "eq", "valore": "S5"}
    assert matches_filtro(f, c, "feriale") is True


def test_filtro_eq_codice_linea_no_match() -> None:
    c = FakeCorsa(codice_linea="S5")
    f = {"campo": "codice_linea", "op": "eq", "valore": "S6"}
    assert matches_filtro(f, c, "feriale") is False


def test_filtro_eq_treno_garantito_bool() -> None:
    c = FakeCorsa(is_treno_garantito_feriale=True)
    f = {"campo": "is_treno_garantito_feriale", "op": "eq", "valore": True}
    assert matches_filtro(f, c, "feriale") is True


# =====================================================================
# matches_filtro — in
# =====================================================================


def test_filtro_in_categoria_match() -> None:
    c = FakeCorsa(categoria="RE")
    f = {"campo": "categoria", "op": "in", "valore": ["RE", "R"]}
    assert matches_filtro(f, c, "feriale") is True


def test_filtro_in_categoria_no_match() -> None:
    c = FakeCorsa(categoria="S")
    f = {"campo": "categoria", "op": "in", "valore": ["RE", "R"]}
    assert matches_filtro(f, c, "feriale") is False


def test_filtro_in_giorno_tipo() -> None:
    c = FakeCorsa()
    f = {"campo": "giorno_tipo", "op": "in", "valore": ["feriale", "sabato"]}
    assert matches_filtro(f, c, "feriale") is True
    assert matches_filtro(f, c, "festivo") is False


# =====================================================================
# matches_filtro — between, gte, lte (fascia_oraria)
# =====================================================================


def test_filtro_between_fascia_dentro_range() -> None:
    c = FakeCorsa(ora_partenza=time(10, 30))
    f = {
        "campo": "fascia_oraria",
        "op": "between",
        "valore": ["04:00", "15:59"],
    }
    assert matches_filtro(f, c, "feriale") is True


def test_filtro_between_fascia_estremi_inclusi() -> None:
    f = {
        "campo": "fascia_oraria",
        "op": "between",
        "valore": ["04:00", "15:59:59"],
    }
    assert matches_filtro(f, FakeCorsa(ora_partenza=time(4, 0)), "feriale") is True
    assert matches_filtro(f, FakeCorsa(ora_partenza=time(15, 59, 59)), "feriale") is True


def test_filtro_between_fascia_fuori_range() -> None:
    c = FakeCorsa(ora_partenza=time(16, 30))
    f = {
        "campo": "fascia_oraria",
        "op": "between",
        "valore": ["04:00", "15:59"],
    }
    assert matches_filtro(f, c, "feriale") is False


def test_filtro_gte_fascia_oraria() -> None:
    c = FakeCorsa(ora_partenza=time(16, 0))
    f = {"campo": "fascia_oraria", "op": "gte", "valore": "16:00"}
    assert matches_filtro(f, c, "feriale") is True

    c2 = FakeCorsa(ora_partenza=time(15, 59))
    assert matches_filtro(f, c2, "feriale") is False


def test_filtro_lte_fascia_oraria() -> None:
    c = FakeCorsa(ora_partenza=time(15, 59))
    f = {"campo": "fascia_oraria", "op": "lte", "valore": "16:00"}
    assert matches_filtro(f, c, "feriale") is True


# =====================================================================
# matches_filtro — operatore sconosciuto
# =====================================================================


def test_filtro_op_sconosciuto_raises() -> None:
    c = FakeCorsa()
    f = {"campo": "codice_linea", "op": "regex", "valore": "S.*"}
    with pytest.raises(ValueError, match="non supportato"):
        matches_filtro(f, c, "feriale")


# =====================================================================
# matches_all (AND)
# =====================================================================


def test_matches_all_lista_vuota_true() -> None:
    """Lista vuota di filtri → matcha tutto (regola fallback)."""
    assert matches_all([], FakeCorsa(), "feriale") is True


def test_matches_all_tutti_match_true() -> None:
    c = FakeCorsa(codice_linea="S5", categoria="RE", ora_partenza=time(10, 0))
    filtri = [
        {"campo": "codice_linea", "op": "eq", "valore": "S5"},
        {"campo": "categoria", "op": "eq", "valore": "RE"},
        {"campo": "fascia_oraria", "op": "between", "valore": ["04:00", "15:59"]},
    ]
    assert matches_all(filtri, c, "feriale") is True


def test_matches_all_uno_falso_false() -> None:
    c = FakeCorsa(codice_linea="S5", categoria="S")
    filtri = [
        {"campo": "codice_linea", "op": "eq", "valore": "S5"},
        {"campo": "categoria", "op": "eq", "valore": "RE"},  # ← falso
    ]
    assert matches_all(filtri, c, "feriale") is False


# =====================================================================
# risolvi_corsa — casi base
# =====================================================================


def test_risolvi_corsa_nessuna_regola_ritorna_none() -> None:
    c = FakeCorsa()
    assert risolvi_corsa(c, [], date(2026, 4, 20)) is None


def test_risolvi_corsa_una_regola_match() -> None:
    c = FakeCorsa(codice_linea="S5")
    r = FakeRegola(
        id=1,
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "S5"}],
        materiale_tipo_codice="ALe711",
        numero_pezzi=3,
        priorita=60,
    )
    out = risolvi_corsa(c, [r], date(2026, 4, 20))
    assert out == AssegnazioneRisolta(regola_id=1, materiale_tipo_codice="ALe711", numero_pezzi=3)


def test_risolvi_corsa_una_regola_no_match() -> None:
    c = FakeCorsa(codice_linea="S5")
    r = FakeRegola(id=1, filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "S6"}])
    assert risolvi_corsa(c, [r], date(2026, 4, 20)) is None


def test_risolvi_corsa_regola_fallback_vuoti() -> None:
    """Regola con filtri_json=[] matcha tutto (fallback)."""
    c = FakeCorsa()
    r = FakeRegola(id=99, filtri_json=[], priorita=10)
    out = risolvi_corsa(c, [r], date(2026, 4, 20))
    assert out is not None
    assert out.regola_id == 99


# =====================================================================
# risolvi_corsa — priorità + specificità
# =====================================================================


def test_risolvi_corsa_priorita_piu_alta_vince() -> None:
    """Due regole matchano: vince quella con priorità più alta."""
    c = FakeCorsa(codice_linea="S5", numero_treno="12345")
    r_low = FakeRegola(
        id=1,
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "S5"}],
        materiale_tipo_codice="ALe711",
        numero_pezzi=3,
        priorita=60,
    )
    r_high = FakeRegola(
        id=2,
        filtri_json=[{"campo": "numero_treno", "op": "eq", "valore": "12345"}],
        materiale_tipo_codice="ETR526",
        numero_pezzi=4,
        priorita=100,
    )
    out = risolvi_corsa(c, [r_low, r_high], date(2026, 4, 20))
    assert out is not None
    assert out.regola_id == 2
    assert out.materiale_tipo_codice == "ETR526"


def test_risolvi_corsa_a_parita_priorita_vince_piu_specifica() -> None:
    """Stessa priorità → vince quella con più filtri (più specifica)."""
    c = FakeCorsa(codice_linea="S5", ora_partenza=time(10, 0))
    r_meno_specifica = FakeRegola(
        id=1,
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "S5"}],
        priorita=80,
        materiale_tipo_codice="ALe711",
        numero_pezzi=3,
    )
    r_piu_specifica = FakeRegola(
        id=2,
        filtri_json=[
            {"campo": "codice_linea", "op": "eq", "valore": "S5"},
            {"campo": "fascia_oraria", "op": "between", "valore": ["04:00", "15:59"]},
        ],
        priorita=80,
        materiale_tipo_codice="ALe711",
        numero_pezzi=3,
    )
    out = risolvi_corsa(c, [r_meno_specifica, r_piu_specifica], date(2026, 4, 20))
    assert out is not None
    assert out.regola_id == 2  # la più specifica


# =====================================================================
# risolvi_corsa — ambiguità
# =====================================================================


def test_risolvi_corsa_ambiguita_raises() -> None:
    """Top-2 con priorità + specificità identiche → RegolaAmbiguaError."""
    c = FakeCorsa(codice_linea="S5", categoria="RE", numero_treno="9999")
    r1 = FakeRegola(
        id=1,
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "S5"}],
        priorita=60,
    )
    r2 = FakeRegola(
        id=2,
        filtri_json=[{"campo": "categoria", "op": "eq", "valore": "RE"}],
        priorita=60,
    )
    with pytest.raises(RegolaAmbiguaError) as excinfo:
        risolvi_corsa(c, [r1, r2], date(2026, 4, 20))
    err = excinfo.value
    assert err.regole_ids == [1, 2] or err.regole_ids == [2, 1]
    assert err.corsa_id == "9999"


def test_risolvi_corsa_ambiguita_tre_regole_solo_top_2() -> None:
    """L'ambiguità si valuta solo top-2, non sulla terza."""
    c = FakeCorsa(codice_linea="S5", categoria="RE")
    # Due regole indistinguibili → ambigua
    r1 = FakeRegola(
        id=1,
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "S5"}],
        priorita=60,
    )
    r2 = FakeRegola(
        id=2,
        filtri_json=[{"campo": "categoria", "op": "eq", "valore": "RE"}],
        priorita=60,
    )
    # Una terza regola con priorità più bassa: irrilevante
    r3 = FakeRegola(
        id=3,
        filtri_json=[],
        priorita=10,
    )
    with pytest.raises(RegolaAmbiguaError):
        risolvi_corsa(c, [r1, r2, r3], date(2026, 4, 20))


def test_risolvi_corsa_priorita_diversa_no_ambiguita() -> None:
    """Stessa specificità ma priorità diverse → vince la più alta."""
    c = FakeCorsa(codice_linea="S5", categoria="RE")
    r1 = FakeRegola(
        id=1,
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "S5"}],
        priorita=80,
    )
    r2 = FakeRegola(
        id=2,
        filtri_json=[{"campo": "categoria", "op": "eq", "valore": "RE"}],
        priorita=60,
    )
    out = risolvi_corsa(c, [r1, r2], date(2026, 4, 20))
    assert out is not None
    assert out.regola_id == 1


# =====================================================================
# risolvi_corsa — esempio Trenord realistico (S5 fascia pendolare)
# =====================================================================


def test_risolvi_corsa_s5_mattina_3_pezzi() -> None:
    """S5 feriale alle 10:00 → 3× ALe711 (regola mattina)."""
    c = FakeCorsa(codice_linea="S5", ora_partenza=time(10, 0))
    r_mattina = FakeRegola(
        id=1,
        filtri_json=[
            {"campo": "codice_linea", "op": "eq", "valore": "S5"},
            {"campo": "fascia_oraria", "op": "between", "valore": ["04:00", "15:59"]},
            {"campo": "giorno_tipo", "op": "in", "valore": ["feriale"]},
        ],
        priorita=80,
        materiale_tipo_codice="ALe711",
        numero_pezzi=3,
    )
    r_pomeriggio = FakeRegola(
        id=2,
        filtri_json=[
            {"campo": "codice_linea", "op": "eq", "valore": "S5"},
            {"campo": "fascia_oraria", "op": "between", "valore": ["16:00", "23:59"]},
            {"campo": "giorno_tipo", "op": "in", "valore": ["feriale"]},
        ],
        priorita=80,
        materiale_tipo_codice="ALe711",
        numero_pezzi=6,
    )
    out = risolvi_corsa(c, [r_mattina, r_pomeriggio], date(2026, 4, 20))  # lunedì = feriale
    assert out is not None
    assert out.regola_id == 1
    assert out.numero_pezzi == 3


def test_risolvi_corsa_s5_pomeriggio_6_pezzi() -> None:
    """S5 feriale alle 17:30 → 6× ALe711 (regola pomeriggio = aggancio)."""
    c = FakeCorsa(codice_linea="S5", ora_partenza=time(17, 30))
    r_mattina = FakeRegola(
        id=1,
        filtri_json=[
            {"campo": "codice_linea", "op": "eq", "valore": "S5"},
            {"campo": "fascia_oraria", "op": "between", "valore": ["04:00", "15:59"]},
            {"campo": "giorno_tipo", "op": "in", "valore": ["feriale"]},
        ],
        priorita=80,
        materiale_tipo_codice="ALe711",
        numero_pezzi=3,
    )
    r_pomeriggio = FakeRegola(
        id=2,
        filtri_json=[
            {"campo": "codice_linea", "op": "eq", "valore": "S5"},
            {"campo": "fascia_oraria", "op": "between", "valore": ["16:00", "23:59"]},
            {"campo": "giorno_tipo", "op": "in", "valore": ["feriale"]},
        ],
        priorita=80,
        materiale_tipo_codice="ALe711",
        numero_pezzi=6,
    )
    out = risolvi_corsa(c, [r_mattina, r_pomeriggio], date(2026, 4, 20))
    assert out is not None
    assert out.regola_id == 2
    assert out.numero_pezzi == 6


def test_risolvi_corsa_s5_sabato_default() -> None:
    """S5 sabato → fallback (regola sabato/festivo, non mattina/pomeriggio).

    Regole feriale non matchano; quella di default (`giorno_tipo` weekend)
    matcha → 3 pezzi.
    """
    c = FakeCorsa(codice_linea="S5", ora_partenza=time(10, 0))
    r_feriale_mattina = FakeRegola(
        id=1,
        filtri_json=[
            {"campo": "codice_linea", "op": "eq", "valore": "S5"},
            {"campo": "fascia_oraria", "op": "between", "valore": ["04:00", "15:59"]},
            {"campo": "giorno_tipo", "op": "in", "valore": ["feriale"]},
        ],
        priorita=80,
        numero_pezzi=3,
    )
    r_weekend = FakeRegola(
        id=99,
        filtri_json=[
            {"campo": "codice_linea", "op": "eq", "valore": "S5"},
            {"campo": "giorno_tipo", "op": "in", "valore": ["sabato", "festivo"]},
        ],
        priorita=60,
        numero_pezzi=3,
    )
    # 18 aprile 2026 è sabato non festivo
    out = risolvi_corsa(c, [r_feriale_mattina, r_weekend], date(2026, 4, 18))
    assert out is not None
    assert out.regola_id == 99


def test_risolvi_corsa_treno_specifico_vince_su_linea() -> None:
    """Una regola `numero_treno` (priorità 100) batte una `codice_linea` (60)."""
    c = FakeCorsa(numero_treno="12345", codice_linea="S5")
    r_linea = FakeRegola(
        id=1,
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "S5"}],
        priorita=60,
        materiale_tipo_codice="ALe711",
        numero_pezzi=3,
    )
    r_specifica = FakeRegola(
        id=2,
        filtri_json=[{"campo": "numero_treno", "op": "eq", "valore": "12345"}],
        priorita=100,
        materiale_tipo_codice="ETR526",
        numero_pezzi=4,
    )
    out = risolvi_corsa(c, [r_linea, r_specifica], date(2026, 4, 20))
    assert out is not None
    assert out.regola_id == 2
    assert out.materiale_tipo_codice == "ETR526"
