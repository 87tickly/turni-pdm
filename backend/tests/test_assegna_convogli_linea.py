"""Test per ``domain/builder_giro/assegna_convogli_linea.py`` (MR-D2).

Plan-D MR-D2 contiene la **raccomandazione obbligatoria SEVERO #2**:
"nessun ciclo aperto fuori area Milano" come constraint HARD.
Il modulo realizza l'allocatore vincolato del nuovo builder
linea-centrico.

Test focus:
- Vincolo HARD #1: compatibilità sede-segmento (sosta notturna OR
  area metropolitana condivisa)
- Vincolo HARD #2: capacity flotta per materiale
- Calcolo n_convogli minimo (formula round-trip)
- Most-constrained-first ordering
- Determinismo (output stabile cross-run)
- Errori: no_sede_compatibile, capacity_overflow
"""

from __future__ import annotations

import pytest

from colazione.domain.builder_giro.assegna_convogli_linea import (
    ParamAssegnazione,
    assegna_convogli_segmenti,
)
from colazione.domain.builder_giro.definizione_linea import (
    SegmentoLinea,
    TipoSegmento,
    VincoliSosta,
)

# =====================================================================
# Fixture helpers
# =====================================================================


def _seg(
    codice: str,
    capolinee: set[str],
    *,
    sosta_notturna: set[str] | None = None,
    n_corse_die: float = 4.0,
    tipo: TipoSegmento = TipoSegmento.LINEARE,
) -> SegmentoLinea:
    return SegmentoLinea(
        codice=codice,
        tipo=tipo,
        capolinee=frozenset(capolinee),
        stazioni_sosta_notturna=frozenset(sosta_notturna or capolinee),
        vincoli_sosta=VincoliSosta(),
        n_corse_per_die_media=n_corse_die,
    )


# =====================================================================
# ParamAssegnazione validation
# =====================================================================


def test_param_sedi_vuoto_invalido() -> None:
    with pytest.raises(ValueError, match="sedi_disponibili"):
        ParamAssegnazione(sedi_disponibili={})


def test_param_ore_servizio_negative_invalido() -> None:
    with pytest.raises(ValueError, match="ore_servizio_die"):
        ParamAssegnazione(
            sedi_disponibili={"FIO": "S_CERTOSA"}, ore_servizio_die=-1
        )


def test_param_round_trip_zero_invalido() -> None:
    with pytest.raises(ValueError, match="tempo_round_trip"):
        ParamAssegnazione(
            sedi_disponibili={"FIO": "S_CERTOSA"},
            tempo_round_trip_default_min=0,
        )


def test_param_default_validi() -> None:
    p = ParamAssegnazione(sedi_disponibili={"FIO": "S_CERTOSA"})
    assert p.ore_servizio_die == 18.0
    assert p.tempo_round_trip_default_min == 120


# =====================================================================
# Vincolo HARD #1: compatibilità sede-segmento
# =====================================================================


def test_sede_compatibile_via_sosta_notturna_diretta() -> None:
    """Sede stazione_collegata IN sosta_notturna_segmento → compat."""
    seg = _seg(
        "R31_completo",
        capolinee={"S_ALES", "S_MILANO"},
        sosta_notturna={"S_CERTOSA", "S_ALES"},  # CERTOSA include FIO
    )
    params = ParamAssegnazione(
        sedi_disponibili={"FIO": "S_CERTOSA"},
        materiale_per_segmento={"R31_completo": "ETR522"},
    )
    out = assegna_convogli_segmenti([seg], params)
    assert out.assegnazioni[0].sede_codice == "FIO"
    assert out.assegnazioni[0].errore is None


def test_sede_compatibile_via_area_metropolitana() -> None:
    """Sede non in sosta_notturna ma stessa area di un capolinea → compat."""
    seg = _seg(
        "R31_completo",
        capolinee={"S_MILANO_CENTRALE", "S_ALES"},
        sosta_notturna={"S_ALES", "S_MILANO_CENTRALE"},
    )
    params = ParamAssegnazione(
        sedi_disponibili={"FIO": "S_CERTOSA"},
        # CERTOSA e MILANO_CENTRALE entrambe area=1 (Milano)
        area_per_stazione={"S_CERTOSA": 1, "S_MILANO_CENTRALE": 1, "S_ALES": 99},
        materiale_per_segmento={"R31_completo": "ETR522"},
    )
    out = assegna_convogli_segmenti([seg], params)
    assert out.assegnazioni[0].sede_codice == "FIO"
    assert out.assegnazioni[0].errore is None


def test_sede_incompatibile_capolinee_fuori_area() -> None:
    """Sede senza overlap né sosta né area → errore HARD SEVERO #2."""
    seg = _seg(
        "RE13_remoto",
        capolinee={"S_ALES", "S_GENOVA"},
        sosta_notturna={"S_ALES", "S_GENOVA"},
    )
    params = ParamAssegnazione(
        # FIO è a Milano, sede assoluta lontana da ALES/GENOVA
        sedi_disponibili={"FIO": "S_CERTOSA"},
        area_per_stazione={
            "S_CERTOSA": 1,  # Milano area
            "S_ALES": 50,  # area Alessandria
            "S_GENOVA": 60,  # area Genova
        },
        materiale_per_segmento={"RE13_remoto": "ETR522"},
    )
    out = assegna_convogli_segmenti([seg], params)
    assert out.assegnazioni[0].sede_codice is None
    assert out.assegnazioni[0].errore == "no_sede_compatibile"


def test_severo_constraint_2_no_ciclo_aperto_fuori_area() -> None:
    """Caso documentato della raccomandazione SEVERO #2:
    una linea con capolinee tutti fuori area-Milano NON deve essere
    assegnata a una sede in area-Milano. Il modulo blocca l'assegnazione
    invece di permetterla con penalità soft.
    """
    seg = _seg(
        "PAVIA_TORINO",
        capolinee={"S_PAVIA", "S_TORINO"},
        sosta_notturna={"S_PAVIA", "S_TORINO"},
    )
    params = ParamAssegnazione(
        sedi_disponibili={"FIO": "S_CERTOSA"},
        area_per_stazione={
            "S_CERTOSA": 1,  # Milano
            "S_PAVIA": 30,
            "S_TORINO": 40,
        },
        materiale_per_segmento={"PAVIA_TORINO": "ETR522"},
    )
    out = assegna_convogli_segmenti([seg], params)
    assert out.assegnazioni[0].errore == "no_sede_compatibile"
    assert "SEVERO #2" in " ".join(out.warnings)


# =====================================================================
# Vincolo HARD #2: capacity flotta per materiale
# =====================================================================


def test_capacity_overflow_singola_sede() -> None:
    """Flotta troppo piccola per coprire i segmenti → errore."""
    seg1 = _seg("S1", {"S_A", "S_B"}, n_corse_die=20.0)  # ~2 convogli
    seg2 = _seg("S2", {"S_A", "S_B"}, n_corse_die=20.0)  # ~2 convogli
    params = ParamAssegnazione(
        sedi_disponibili={"FIO": "S_A"},
        dotazione_per_materiale={"ETR522": 2},  # solo 2 disponibili
        materiale_per_segmento={"S1": "ETR522", "S2": "ETR522"},
    )
    out = assegna_convogli_segmenti([seg1, seg2], params)
    # Primo segmento ok, secondo overflow
    errori = [a.errore for a in out.assegnazioni if a.errore]
    assert "capacity_overflow" in errori


def test_capacity_ok_se_sotto_dotazione() -> None:
    """Flotta sufficiente → tutti assegnati."""
    seg1 = _seg("S1", {"S_A", "S_B"}, n_corse_die=4.0)
    seg2 = _seg("S2", {"S_A", "S_B"}, n_corse_die=4.0)
    params = ParamAssegnazione(
        sedi_disponibili={"FIO": "S_A"},
        dotazione_per_materiale={"ETR522": 10},
        materiale_per_segmento={"S1": "ETR522", "S2": "ETR522"},
    )
    out = assegna_convogli_segmenti([seg1, seg2], params)
    assert all(a.errore is None for a in out.assegnazioni)
    assert out.n_convogli_per_materiale["ETR522"] >= 2


def test_capacity_materiale_non_in_dotazione_ok() -> None:
    """Materiale senza limite in dotazione → assunto illimitato."""
    seg = _seg("S1", {"S_A", "S_B"}, n_corse_die=100.0)
    params = ParamAssegnazione(
        sedi_disponibili={"FIO": "S_A"},
        # niente dotazione_per_materiale → no limite
        materiale_per_segmento={"S1": "ETR_FAKE"},
    )
    out = assegna_convogli_segmenti([seg], params)
    assert out.assegnazioni[0].errore is None


# =====================================================================
# Calcolo n_convogli minimo (formula round-trip)
# =====================================================================


def test_n_convogli_navetta_alta_frequenza() -> None:
    """16 corse/die round-trip 2h, ore_servizio 18h →
    corse_per_convoglio = 2*18/2 = 18, n = ceil(16/18) = 1."""
    seg = _seg("S13", {"S_A", "S_B"}, n_corse_die=16.0)
    params = ParamAssegnazione(sedi_disponibili={"FIO": "S_A"})
    out = assegna_convogli_segmenti([seg], params)
    assert out.assegnazioni[0].n_convogli == 1


def test_n_convogli_servizio_intenso() -> None:
    """40 corse/die round-trip 2h, ore_servizio 18h →
    corse_per_convoglio = 18, n = ceil(40/18) = 3."""
    seg = _seg("HEAVY", {"S_A", "S_B"}, n_corse_die=40.0)
    params = ParamAssegnazione(sedi_disponibili={"FIO": "S_A"})
    out = assegna_convogli_segmenti([seg], params)
    assert out.assegnazioni[0].n_convogli == 3


def test_n_convogli_minimo_uno_se_corse_positive() -> None:
    """Anche per pochissime corse → almeno 1 convoglio."""
    seg = _seg("RARE", {"S_A", "S_B"}, n_corse_die=0.5)
    params = ParamAssegnazione(sedi_disponibili={"FIO": "S_A"})
    out = assegna_convogli_segmenti([seg], params)
    assert out.assegnazioni[0].n_convogli == 1


def test_n_convogli_zero_se_n_corse_zero() -> None:
    """Segmento senza corse → 0 convogli."""
    seg = _seg("EMPTY", {"S_A", "S_B"}, n_corse_die=0.0)
    params = ParamAssegnazione(sedi_disponibili={"FIO": "S_A"})
    out = assegna_convogli_segmenti([seg], params)
    assert out.assegnazioni[0].n_convogli == 0


# =====================================================================
# Most-constrained-first
# =====================================================================


def test_most_constrained_first_segmento_con_meno_candidati_prima() -> None:
    """Segmento con 1 sola sede compatibile va processato prima di
    uno con 2+ sedi (heuristic constraint propagation).
    """
    # seg1: compatibile solo con FIO (sosta notturna esplicita)
    seg1 = _seg(
        "ONLY_FIO",
        capolinee={"S_X", "S_Y"},
        sosta_notturna={"S_X", "S_CERTOSA"},
    )
    # seg2: compatibile con entrambe (area Milano)
    seg2 = _seg(
        "BOTH",
        capolinee={"S_MIL", "S_X"},
        sosta_notturna={"S_X", "S_MIL"},
    )
    params = ParamAssegnazione(
        sedi_disponibili={"FIO": "S_CERTOSA", "MILANO_NORD": "S_MIL"},
        area_per_stazione={"S_CERTOSA": 1, "S_MIL": 1},
        materiale_per_segmento={"ONLY_FIO": "ETR522", "BOTH": "ETR522"},
    )
    out = assegna_convogli_segmenti([seg2, seg1], params)
    # Indipendentemente dall'ordine input, ONLY_FIO è processato prima
    # (più constrained) e va a FIO (unica compatibile)
    only_fio = next(
        a for a in out.assegnazioni if a.segmento_codice == "ONLY_FIO"
    )
    assert only_fio.sede_codice == "FIO"


# =====================================================================
# Determinismo
# =====================================================================


def test_determinismo_chiamate_doppie_stesso_output() -> None:
    """Stesso input → stesso output, anche con multipli segmenti."""
    seg1 = _seg("A", {"S_A", "S_B"}, n_corse_die=4.0)
    seg2 = _seg("B", {"S_A", "S_B"}, n_corse_die=4.0)
    seg3 = _seg("C", {"S_A", "S_B"}, n_corse_die=4.0)
    params = ParamAssegnazione(
        sedi_disponibili={"FIO": "S_A", "MILANO": "S_B"},
        area_per_stazione={"S_A": 1, "S_B": 1},
        materiale_per_segmento={"A": "ETR522", "B": "ETR522", "C": "ETR522"},
    )
    out1 = assegna_convogli_segmenti([seg1, seg2, seg3], params)
    out2 = assegna_convogli_segmenti([seg1, seg2, seg3], params)
    assert out1 == out2


def test_determinismo_tie_break_sede_alfabetico() -> None:
    """A parità di compatibilità, sceglie sede alfabeticamente prima."""
    seg = _seg("S1", {"S_A", "S_B"}, n_corse_die=4.0)
    params = ParamAssegnazione(
        # ZULU e ALPHA: stessa compatibilità
        sedi_disponibili={"ZULU_DEPOT": "S_A", "ALPHA_DEPOT": "S_A"},
        materiale_per_segmento={"S1": "ETR522"},
    )
    out = assegna_convogli_segmenti([seg], params)
    assert out.assegnazioni[0].sede_codice == "ALPHA_DEPOT"


# =====================================================================
# Edge cases
# =====================================================================


def test_lista_segmenti_vuota() -> None:
    params = ParamAssegnazione(sedi_disponibili={"FIO": "S_A"})
    out = assegna_convogli_segmenti([], params)
    assert out.assegnazioni == ()
    assert out.n_convogli_per_sede == {}
    assert out.warnings == ()


def test_n_segmenti_con_errore_aggregato() -> None:
    """RisultatoAssegnazione.n_segmenti_con_errore conta correttamente."""
    seg_ok = _seg("OK", {"S_A", "S_B"}, sosta_notturna={"S_A"}, n_corse_die=4.0)
    seg_ko = _seg("KO", {"S_X", "S_Y"}, n_corse_die=4.0)
    params = ParamAssegnazione(
        sedi_disponibili={"FIO": "S_A"},
        # nessuna area_per_stazione → S_X/S_Y non hanno overlap
        materiale_per_segmento={"OK": "ETR522", "KO": "ETR522"},
    )
    out = assegna_convogli_segmenti([seg_ok, seg_ko], params)
    assert out.n_segmenti_con_errore() == 1


# =====================================================================
# Statistiche aggregate
# =====================================================================


def test_n_convogli_per_sede_aggregato() -> None:
    """Più segmenti sulla stessa sede sommano i convogli."""
    seg1 = _seg("S1", {"S_A", "S_B"}, n_corse_die=20.0)  # ~2 conv
    seg2 = _seg("S2", {"S_A", "S_C"}, n_corse_die=20.0)  # ~2 conv
    params = ParamAssegnazione(
        sedi_disponibili={"FIO": "S_A"},
        materiale_per_segmento={"S1": "ETR522", "S2": "ETR522"},
    )
    out = assegna_convogli_segmenti([seg1, seg2], params)
    assert out.n_convogli_per_sede["FIO"] >= 2


def test_n_convogli_per_materiale_aggregato() -> None:
    """Materiali diversi conteggiati separatamente."""
    seg1 = _seg("S1", {"S_A", "S_B"}, n_corse_die=4.0)
    seg2 = _seg("S2", {"S_A", "S_B"}, n_corse_die=4.0)
    params = ParamAssegnazione(
        sedi_disponibili={"FIO": "S_A"},
        materiale_per_segmento={"S1": "ETR522", "S2": "ATR125"},
    )
    out = assegna_convogli_segmenti([seg1, seg2], params)
    assert "ETR522" in out.n_convogli_per_materiale
    assert "ATR125" in out.n_convogli_per_materiale
