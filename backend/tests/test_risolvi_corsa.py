"""Test puri Sprint 4.2 — `risolvi_corsa` + helper.

Tutti i test sono **senza DB**: usano dataclass minimali per
simulare corse e regole. Coprono:

- `determina_giorno_tipo`: festività, weekend, feriale.
- `matches_filtro` per ogni operatore (eq, in, between, gte, lte) e
  per `fascia_oraria` (parsing time strings).
- `matches_all` (AND, lista vuota).
- `risolvi_corsa`: nessuna regola, una sola, priorità, specificità,
  tie-break per id (Sprint 7.9 MR 11B entry 120), edge case.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from typing import Any

import pytest

from colazione.domain.builder_giro import (
    ComposizioneItem,
    ComposizioneNonAmmessaError,
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
    """Regola minimale per test.

    Sprint 5.5: la regola ha ora ``composizione_json`` come lista di
    dict ``[{"materiale_tipo_codice": str, "n_pezzi": int}, ...]``.
    Per backward compat con i test esistenti, accetta anche i parametri
    legacy ``materiale_tipo_codice`` + ``numero_pezzi``: se forniti e
    ``composizione_json`` non è popolato, costruisce composizione da
    quelli (1 elemento).
    """

    id: int
    filtri_json: list[dict[str, Any]] = field(default_factory=list)
    materiale_tipo_codice: str = "ALe711"
    numero_pezzi: int = 3
    priorita: int = 60
    composizione_json: list[dict[str, Any]] = field(default_factory=list)
    is_composizione_manuale: bool = False

    def __post_init__(self) -> None:
        if not self.composizione_json:
            self.composizione_json = [
                {
                    "materiale_tipo_codice": self.materiale_tipo_codice,
                    "n_pezzi": self.numero_pezzi,
                }
            ]


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
    assert out is not None
    assert out.regola_id == 1
    assert out.composizione == (ComposizioneItem("ALe711", 3),)
    assert out.numero_pezzi_totali == 3
    assert out.materiali_codici == frozenset({"ALe711"})


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
    assert out.composizione[0].materiale_tipo_codice == "ETR526"


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


def test_risolvi_corsa_priorita_specificita_identiche_tie_break_id() -> None:
    """Sprint 7.9 MR 11B (entry 120): priorità + specificità identiche
    → tie-break deterministico per ``id ascending``. Niente più
    ``RegolaAmbiguaError``.
    """
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
    out = risolvi_corsa(c, [r1, r2], date(2026, 4, 20))
    assert out is not None
    assert out.regola_id == 1  # id più basso vince
    # L'ordine di input non conta: anche [r2, r1] → id=1
    out2 = risolvi_corsa(c, [r2, r1], date(2026, 4, 20))
    assert out2 is not None
    assert out2.regola_id == 1


def test_risolvi_corsa_tie_break_anche_con_terza_regola_lower_prio() -> None:
    """Tie-break tra le top-2 con priorità + specificità identiche;
    la terza regola con priorità più bassa è irrilevante."""
    c = FakeCorsa(codice_linea="S5", categoria="RE")
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
    r3 = FakeRegola(
        id=3,
        filtri_json=[],
        priorita=10,
    )
    out = risolvi_corsa(c, [r1, r2, r3], date(2026, 4, 20))
    assert out is not None
    assert out.regola_id == 1


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
    assert out.numero_pezzi_totali == 3


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
    assert out.numero_pezzi_totali == 6


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
    assert out.composizione[0].materiale_tipo_codice == "ETR526"


# =====================================================================
# Sprint 5.5 — Composizione lista + validazione accoppiamento
# =====================================================================


def test_risolvi_corsa_composizione_singola_da_json() -> None:
    """Una regola single-material genera AssegnazioneRisolta con
    composizione di 1 elemento."""
    c = FakeCorsa(codice_linea="S5")
    r = FakeRegola(
        id=1,
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "S5"}],
        composizione_json=[{"materiale_tipo_codice": "ETR526", "n_pezzi": 1}],
    )
    out = risolvi_corsa(c, [r], date(2026, 4, 20))
    assert out is not None
    assert len(out.composizione) == 1
    assert out.composizione[0] == ComposizioneItem("ETR526", 1)
    assert out.is_composizione_manuale is False


def test_risolvi_corsa_composizione_doppia_ammessa() -> None:
    """Composizione doppia ETR526+ETR425 con callback che la ammette."""
    c = FakeCorsa(direttrice="MILANO-TIRANO")
    r = FakeRegola(
        id=1,
        filtri_json=[{"campo": "direttrice", "op": "eq", "valore": "MILANO-TIRANO"}],
        composizione_json=[
            {"materiale_tipo_codice": "ETR526", "n_pezzi": 1},
            {"materiale_tipo_codice": "ETR425", "n_pezzi": 1},
        ],
    )

    # Callback che ammette ETR425+ETR526 (normalizzato lex)
    def is_ammesso(a: str, b: str) -> bool:
        return (a, b) == ("ETR425", "ETR526")

    out = risolvi_corsa(c, [r], date(2026, 4, 20), is_ammesso)
    assert out is not None
    assert len(out.composizione) == 2
    assert out.materiali_codici == frozenset({"ETR425", "ETR526"})
    assert out.numero_pezzi_totali == 2


def test_risolvi_corsa_composizione_doppia_non_ammessa_raises() -> None:
    """Composizione doppia non in materiale_accoppiamento_ammesso →
    ComposizioneNonAmmessaError."""
    c = FakeCorsa(direttrice="MILANO-TIRANO")
    r = FakeRegola(
        id=42,
        filtri_json=[{"campo": "direttrice", "op": "eq", "valore": "MILANO-TIRANO"}],
        composizione_json=[
            {"materiale_tipo_codice": "ETR526", "n_pezzi": 1},
            {"materiale_tipo_codice": "ALe711", "n_pezzi": 1},
        ],
    )

    def is_ammesso(a: str, b: str) -> bool:
        return False  # niente è ammesso

    with pytest.raises(ComposizioneNonAmmessaError) as excinfo:
        risolvi_corsa(c, [r], date(2026, 4, 20), is_ammesso)
    err = excinfo.value
    assert err.regola_id == 42
    # Coppia normalizzata lex: ALe711 < ETR526
    assert err.coppia_non_ammessa == ("ALe711", "ETR526")


def test_risolvi_corsa_doppia_non_ammessa_bypassata_da_manuale() -> None:
    """is_composizione_manuale=True → bypass del check, niente errore."""
    c = FakeCorsa(direttrice="X")
    r = FakeRegola(
        id=7,
        filtri_json=[{"campo": "direttrice", "op": "eq", "valore": "X"}],
        composizione_json=[
            {"materiale_tipo_codice": "ETR526", "n_pezzi": 1},
            {"materiale_tipo_codice": "TAF", "n_pezzi": 1},
        ],
        is_composizione_manuale=True,
    )

    def is_ammesso(a: str, b: str) -> bool:
        return False  # rifiuterebbe tutto, ma manuale=True bypassa

    out = risolvi_corsa(c, [r], date(2026, 4, 20), is_ammesso)
    assert out is not None
    assert out.is_composizione_manuale is True
    assert len(out.composizione) == 2


def test_risolvi_corsa_doppia_self_pair_validata() -> None:
    """Composizione 526+526 (doppia stesso materiale) richiede comunque
    la coppia (526, 526) in materiale_accoppiamento_ammesso."""
    c = FakeCorsa(direttrice="X")
    r = FakeRegola(
        id=1,
        filtri_json=[{"campo": "direttrice", "op": "eq", "valore": "X"}],
        composizione_json=[
            {"materiale_tipo_codice": "ETR526", "n_pezzi": 1},
            {"materiale_tipo_codice": "ETR526", "n_pezzi": 1},
        ],
    )

    def is_ammesso_solo_526526(a: str, b: str) -> bool:
        return (a, b) == ("ETR526", "ETR526")

    out = risolvi_corsa(c, [r], date(2026, 4, 20), is_ammesso_solo_526526)
    assert out is not None
    assert len(out.composizione) == 2


def test_risolvi_corsa_singola_no_validazione_accoppiamento() -> None:
    """Composizione di 1 elemento: il callback non viene chiamato
    (non ci sono coppie da validare)."""
    c = FakeCorsa(codice_linea="S5")
    r = FakeRegola(
        id=1,
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "S5"}],
        composizione_json=[{"materiale_tipo_codice": "ALe711", "n_pezzi": 3}],
    )

    callback_calls: list[tuple[str, str]] = []

    def is_ammesso(a: str, b: str) -> bool:
        callback_calls.append((a, b))
        return True

    out = risolvi_corsa(c, [r], date(2026, 4, 20), is_ammesso)
    assert out is not None
    assert callback_calls == [], "Callback non deve essere chiamato per composizione singola"


def test_risolvi_corsa_callback_none_skip_validazione() -> None:
    """Callback None → niente validazione (default per testing semplice)."""
    c = FakeCorsa(direttrice="X")
    r = FakeRegola(
        id=1,
        filtri_json=[{"campo": "direttrice", "op": "eq", "valore": "X"}],
        composizione_json=[
            {"materiale_tipo_codice": "ETR526", "n_pezzi": 1},
            {"materiale_tipo_codice": "ALe711", "n_pezzi": 1},
        ],
    )
    # is_accoppiamento_ammesso=None (default) → no errore
    out = risolvi_corsa(c, [r], date(2026, 4, 20))
    assert out is not None
    assert len(out.composizione) == 2
