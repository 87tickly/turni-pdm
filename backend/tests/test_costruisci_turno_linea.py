"""Test per ``domain/builder_giro/costruisci_turno_linea.py`` (MR-D3).

Cuore architetturale del nuovo builder linea-centrico. Costruisce
sequenze di servizio multi-giornata per convoglio rispettando
vincoli operativi.

Test focus:
- Costruzione turno singolo convoglio (1 giornata, multi-giornata)
- Distribuzione round-robin di corse fra n_convogli
- Vincoli sosta intra-day (warning se superato)
- Continuità geografica cross-day
- Calcolo km + prestazione
- Filtraggio corse per data
- Edge cases: assegnazione in errore, segmento senza corse
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

from colazione.domain.builder_giro.assegna_convogli_linea import (
    AssegnazioneSegmento,
)
from colazione.domain.builder_giro.costruisci_turno_linea import (
    costruisci_turni_da_assegnazione,
    costruisci_turno_per_convoglio,
)
from colazione.domain.builder_giro.definizione_linea import (
    SegmentoLinea,
    TipoSegmento,
    VincoliSosta,
)
from colazione.domain.builder_giro.gestione_calendario_linea import (
    CalendarioSegmento,
    TipoCalendario,
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
    valido_da: date = date(2026, 6, 1),
    valido_a: date = date(2026, 6, 30),
    valido_in_date: list[str] | None = None,
    km: float | None = 50.0,
    linea: str = "R31",
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


def _segmento(
    codice: str = "R31_completo",
    *,
    capolinee: set[str] | None = None,
    sosta_max_diurna_min: int = 240,
) -> SegmentoLinea:
    return SegmentoLinea(
        codice=codice,
        tipo=TipoSegmento.LINEARE,
        capolinee=frozenset(capolinee or {"S_A", "S_B"}),
        stazioni_sosta_notturna=frozenset(capolinee or {"S_A", "S_B"}),
        vincoli_sosta=VincoliSosta(sosta_max_diurna_min=sosta_max_diurna_min),
        n_corse_per_die_media=4.0,
    )


def _calendario(
    codice: str,
    date_feriali: set[date] | None = None,
) -> CalendarioSegmento:
    if date_feriali is None:
        date_feriali = {date(2026, 6, 8), date(2026, 6, 9)}
    return CalendarioSegmento(
        segmento_codice=codice,
        date_per_tipo={TipoCalendario.FERIALE: frozenset(date_feriali)},
    )


def _assegnazione(
    codice: str,
    sede: str = "FIO",
    n_conv: int = 1,
) -> AssegnazioneSegmento:
    return AssegnazioneSegmento(
        segmento_codice=codice,
        sede_codice=sede,
        n_convogli=n_conv,
        materiale="ETR522",
        errore=None,
    )


# =====================================================================
# Costruzione turno singolo convoglio - giornata
# =====================================================================


def test_turno_un_convoglio_una_giornata_due_corse_continuative() -> None:
    """1 convoglio, 1 giornata, 2 corse continuative A→B→A."""
    seg = _segmento(capolinee={"S_A", "S_B"})
    cal = _calendario("R31_completo", date_feriali={date(2026, 6, 8)})
    ass = _assegnazione("R31_completo")
    corse = [
        _corsa("S_A", "S_B", 8, 0, 9, 0, treno="T1"),
        _corsa("S_B", "S_A", 10, 0, 11, 0, treno="T2"),
    ]
    turno = costruisci_turno_per_convoglio(
        convoglio_id="R31_completo_C0",
        segmento=seg,
        assegnazione=ass,
        calendario=cal,
        corse_segmento=corse,
        indice_convoglio=0,
        n_convogli_segmento=1,
    )
    assert turno.convoglio_id == "R31_completo_C0"
    assert turno.sede_codice == "FIO"
    assert len(turno.giornate) == 1
    g = turno.giornate[0]
    assert g.stazione_inizio == "S_A"
    assert g.stazione_fine == "S_A"
    assert len(g.corse) == 2
    assert g.km_giornata == 100.0  # 2 corse × 50km
    assert g.prestazione_min == 180  # 8:00 → 11:00 = 180 min
    assert g.warnings_sosta == ()  # no violazioni


def test_turno_due_giornate_consecutive() -> None:
    """1 convoglio attivo 2 date consecutive con stessa coppia."""
    seg = _segmento()
    cal = _calendario(
        "R31_completo",
        date_feriali={date(2026, 6, 8), date(2026, 6, 9)},
    )
    ass = _assegnazione("R31_completo")
    corse = [
        _corsa("S_A", "S_B", 8, 0, 9, 0, treno="T1"),
        _corsa("S_B", "S_A", 10, 0, 11, 0, treno="T2"),
    ]
    turno = costruisci_turno_per_convoglio(
        convoglio_id="R31_completo_C0",
        segmento=seg,
        assegnazione=ass,
        calendario=cal,
        corse_segmento=corse,
        indice_convoglio=0,
        n_convogli_segmento=1,
    )
    assert len(turno.giornate) == 2
    assert turno.n_corse_totali == 4
    assert turno.km_totali == 200.0


def test_turno_corse_filtrate_per_valido_in_date_json() -> None:
    """Corsa con valido_in_date_json: solo le date elencate sono attive."""
    seg = _segmento()
    cal = _calendario(
        "R31_completo",
        date_feriali={date(2026, 6, 8), date(2026, 6, 9)},
    )
    ass = _assegnazione("R31_completo")
    corse = [
        _corsa(
            "S_A", "S_B", 8, 0, 9, 0, treno="T1",
            valido_in_date=["2026-06-08"],  # solo l'8
        ),
        _corsa(
            "S_B", "S_A", 10, 0, 11, 0, treno="T2",
            valido_in_date=["2026-06-08"],
        ),
    ]
    turno = costruisci_turno_per_convoglio(
        convoglio_id="R31_completo_C0",
        segmento=seg,
        assegnazione=ass,
        calendario=cal,
        corse_segmento=corse,
        indice_convoglio=0,
        n_convogli_segmento=1,
    )
    # Solo 1 giornata attiva (8/6); il 9/6 le corse non sono valide
    assert len(turno.giornate) == 1
    assert turno.giornate[0].data == date(2026, 6, 8)


# =====================================================================
# Distribuzione round-robin
# =====================================================================


def test_round_robin_due_convogli_navetta() -> None:
    """4 corse navetta A↔B alternate, 2 convogli round-robin:
    convoglio 0 prende corse 0,2 (= A→B sempre); convoglio 1 prende
    corse 1,3 (= B→A sempre).
    NB: questo produce sequenze con discontinuità → warning atteso.
    """
    seg = _segmento(capolinee={"S_A", "S_B"})
    cal = _calendario("R31_completo", date_feriali={date(2026, 6, 8)})
    ass = _assegnazione("R31_completo", n_conv=2)
    corse = [
        _corsa("S_A", "S_B", 8, 0, 9, 0, treno="T1"),
        _corsa("S_B", "S_A", 9, 30, 10, 30, treno="T2"),
        _corsa("S_A", "S_B", 11, 0, 12, 0, treno="T3"),
        _corsa("S_B", "S_A", 12, 30, 13, 30, treno="T4"),
    ]
    turno_0 = costruisci_turno_per_convoglio(
        convoglio_id="R31_completo_C0",
        segmento=seg,
        assegnazione=ass,
        calendario=cal,
        corse_segmento=corse,
        indice_convoglio=0,
        n_convogli_segmento=2,
    )
    # Convoglio 0 prende corse a indice 0, 2 = T1 (A→B) + T3 (A→B)
    assert [c.numero_treno for c in turno_0.giornate[0].corse] == ["T1", "T3"]
    # Discontinuità: T1 finisce a B, T3 parte da A → warning
    assert any(
        "Discontinuità" in w
        for w in turno_0.giornate[0].warnings_sosta
    )


def test_round_robin_un_convoglio_prende_tutto() -> None:
    """n_convogli=1 → un solo convoglio prende tutte le corse."""
    seg = _segmento()
    cal = _calendario("R31_completo", date_feriali={date(2026, 6, 8)})
    ass = _assegnazione("R31_completo", n_conv=1)
    corse = [
        _corsa("S_A", "S_B", 8, 0, 9, 0, treno="T1"),
        _corsa("S_B", "S_A", 10, 0, 11, 0, treno="T2"),
        _corsa("S_A", "S_B", 12, 0, 13, 0, treno="T3"),
    ]
    turno = costruisci_turno_per_convoglio(
        convoglio_id="R31_completo_C0",
        segmento=seg,
        assegnazione=ass,
        calendario=cal,
        corse_segmento=corse,
        indice_convoglio=0,
        n_convogli_segmento=1,
    )
    assert len(turno.giornate[0].corse) == 3


# =====================================================================
# Vincoli intra-day
# =====================================================================


def test_warning_sosta_diurna_eccessiva() -> None:
    """Gap fra corse > sosta_max_diurna_min → warning."""
    seg = _segmento(sosta_max_diurna_min=60)  # max 1h
    cal = _calendario("R31_completo", date_feriali={date(2026, 6, 8)})
    ass = _assegnazione("R31_completo")
    corse = [
        _corsa("S_A", "S_B", 8, 0, 9, 0, treno="T1"),
        # 4h sosta > 1h → warning
        _corsa("S_B", "S_A", 13, 0, 14, 0, treno="T2"),
    ]
    turno = costruisci_turno_per_convoglio(
        convoglio_id="R31_completo_C0",
        segmento=seg,
        assegnazione=ass,
        calendario=cal,
        corse_segmento=corse,
        indice_convoglio=0,
        n_convogli_segmento=1,
    )
    assert any(
        "Sosta diurna" in w
        for w in turno.giornate[0].warnings_sosta
    )


def test_no_warning_se_sosta_entro_limite() -> None:
    """Gap entro limite → niente warning."""
    seg = _segmento(sosta_max_diurna_min=240)
    cal = _calendario("R31_completo", date_feriali={date(2026, 6, 8)})
    ass = _assegnazione("R31_completo")
    corse = [
        _corsa("S_A", "S_B", 8, 0, 9, 0, treno="T1"),
        _corsa("S_B", "S_A", 10, 0, 11, 0, treno="T2"),  # 1h sosta
    ]
    turno = costruisci_turno_per_convoglio(
        convoglio_id="R31_completo_C0",
        segmento=seg,
        assegnazione=ass,
        calendario=cal,
        corse_segmento=corse,
        indice_convoglio=0,
        n_convogli_segmento=1,
    )
    assert turno.giornate[0].warnings_sosta == ()


# =====================================================================
# Continuità cross-day
# =====================================================================


def test_warning_cross_day_se_fine_diversa_da_inizio_e_no_sosta() -> None:
    """Giornata K finisce a S_X (no in sosta_notturna), giornata K+1
    inizia a S_A → warning cross-day.
    """
    seg = SegmentoLinea(
        codice="R31_completo",
        tipo=TipoSegmento.LINEARE,
        capolinee=frozenset({"S_A", "S_B"}),
        stazioni_sosta_notturna=frozenset({"S_A", "S_B"}),  # X non in sosta
        vincoli_sosta=VincoliSosta(),
        n_corse_per_die_media=4.0,
    )
    cal = _calendario(
        "R31_completo",
        date_feriali={date(2026, 6, 8), date(2026, 6, 9)},
    )
    ass = _assegnazione("R31_completo")
    corse = [
        # 8/6: una sola corsa A→X (finisce fuori sosta_notturna)
        _corsa(
            "S_A", "S_X", 8, 0, 9, 0, treno="T1",
            valido_in_date=["2026-06-08"],
        ),
        # 9/6: una sola corsa A→B
        _corsa(
            "S_A", "S_B", 8, 0, 9, 0, treno="T2",
            valido_in_date=["2026-06-09"],
        ),
    ]
    turno = costruisci_turno_per_convoglio(
        convoglio_id="R31_completo_C0",
        segmento=seg,
        assegnazione=ass,
        calendario=cal,
        corse_segmento=corse,
        indice_convoglio=0,
        n_convogli_segmento=1,
    )
    # Cross-day: 8/6 finisce a S_X, 9/6 inizia a S_A.
    # S_X non in sosta_notturna_ammessa → warning globale
    assert any(
        "Cross-day" in w for w in turno.warnings_globali
    )


# =====================================================================
# Edge cases
# =====================================================================


def test_assegnazione_in_errore_ritorna_turno_vuoto() -> None:
    """Se assegnazione ha errore → turno vuoto con warning."""
    seg = _segmento()
    cal = _calendario("R31_completo")
    ass = AssegnazioneSegmento(
        segmento_codice="R31_completo",
        sede_codice=None,
        n_convogli=0,
        materiale="ETR522",
        errore="no_sede_compatibile",
    )
    turno = costruisci_turno_per_convoglio(
        convoglio_id="R31_completo_C0",
        segmento=seg,
        assegnazione=ass,
        calendario=cal,
        corse_segmento=[],
        indice_convoglio=0,
        n_convogli_segmento=1,
    )
    assert turno.giornate == ()
    assert any("errore" in w for w in turno.warnings_globali)


def test_segmento_senza_corse_in_data_giornate_vuote() -> None:
    """Calendario ha date ma corse sono fuori periodo → turno con
    0 giornate.
    """
    seg = _segmento()
    cal = _calendario("R31_completo", date_feriali={date(2026, 6, 8)})
    ass = _assegnazione("R31_completo")
    corse = [
        # Corsa valida solo 7/7 (fuori dal calendario 8/6)
        _corsa(
            "S_A", "S_B", 8, 0, 9, 0, treno="T1",
            valido_da=date(2026, 7, 7),
            valido_a=date(2026, 7, 7),
        ),
    ]
    turno = costruisci_turno_per_convoglio(
        convoglio_id="R31_completo_C0",
        segmento=seg,
        assegnazione=ass,
        calendario=cal,
        corse_segmento=corse,
        indice_convoglio=0,
        n_convogli_segmento=1,
    )
    assert turno.giornate == ()
    assert turno.n_corse_totali == 0


# =====================================================================
# Wrapper multi-segmento
# =====================================================================


def test_costruisci_turni_da_assegnazione_multi_segmenti() -> None:
    """Wrapper produce 1+ turni per ogni assegnazione valida."""
    seg1 = _segmento("R31_completo")
    seg2 = _segmento("S13_completo", capolinee={"S_X", "S_Y"})
    cal1 = _calendario("R31_completo", date_feriali={date(2026, 6, 8)})
    cal2 = _calendario("S13_completo", date_feriali={date(2026, 6, 8)})
    ass1 = _assegnazione("R31_completo", n_conv=2)
    ass2 = _assegnazione("S13_completo", n_conv=1)
    corse_r31 = [
        _corsa("S_A", "S_B", 8, 0, 9, 0, treno="R1"),
        _corsa("S_B", "S_A", 10, 0, 11, 0, treno="R2"),
    ]
    corse_s13 = [_corsa("S_X", "S_Y", 7, 0, 7, 30, treno="S1")]

    turni = costruisci_turni_da_assegnazione(
        [ass1, ass2],
        segmenti=[seg1, seg2],
        calendari=[cal1, cal2],
        corse_per_segmento={
            "R31_completo": corse_r31,
            "S13_completo": corse_s13,
        },
    )
    # 2 convogli R31 + 1 convoglio S13 = 3 turni totali
    assert len(turni) == 3
    ids = [t.convoglio_id for t in turni]
    assert ids == sorted(ids)  # ordinati alfabeticamente
    assert "R31_completo_C0" in ids
    assert "R31_completo_C1" in ids
    assert "S13_completo_C0" in ids


def test_costruisci_turni_skippa_assegnazioni_in_errore() -> None:
    """Assegnazione con errore → nessun turno generato."""
    seg = _segmento()
    cal = _calendario("R31_completo")
    ass_ok = _assegnazione("R31_completo")
    ass_ko = AssegnazioneSegmento(
        segmento_codice="OTHER",
        sede_codice=None,
        n_convogli=0,
        materiale="ETR522",
        errore="capacity_overflow",
    )
    turni = costruisci_turni_da_assegnazione(
        [ass_ok, ass_ko],
        segmenti=[seg],
        calendari=[cal],
        corse_per_segmento={
            "R31_completo": [
                _corsa("S_A", "S_B", 8, 0, 9, 0, treno="T1"),
            ],
        },
    )
    # Solo R31 produce un turno (1 convoglio)
    assert len(turni) == 1
    assert turni[0].segmento_codice == "R31_completo"


def test_costruisci_turni_segmento_senza_corse_skippato() -> None:
    """corse_per_segmento mancante per un codice → turno vuoto."""
    seg = _segmento()
    cal = _calendario("R31_completo")
    ass = _assegnazione("R31_completo")
    turni = costruisci_turni_da_assegnazione(
        [ass],
        segmenti=[seg],
        calendari=[cal],
        corse_per_segmento={},  # vuoto
    )
    assert len(turni) == 1
    assert turni[0].n_corse_totali == 0


# =====================================================================
# Calcolo km + prestazione
# =====================================================================


def test_km_totali_somma_corse() -> None:
    seg = _segmento()
    cal = _calendario("R31_completo", date_feriali={date(2026, 6, 8)})
    ass = _assegnazione("R31_completo")
    corse = [
        _corsa("S_A", "S_B", 8, 0, 9, 0, treno="T1", km=70.0),
        _corsa("S_B", "S_A", 10, 0, 11, 0, treno="T2", km=70.0),
    ]
    turno = costruisci_turno_per_convoglio(
        convoglio_id="R31_completo_C0",
        segmento=seg,
        assegnazione=ass,
        calendario=cal,
        corse_segmento=corse,
        indice_convoglio=0,
        n_convogli_segmento=1,
    )
    assert turno.km_totali == 140.0


def test_prestazione_cross_mezzanotte() -> None:
    """Corsa che attraversa mezzanotte → prestazione gestita +1440."""
    seg = _segmento(sosta_max_diurna_min=600)
    cal = _calendario("R31_completo", date_feriali={date(2026, 6, 8)})
    ass = _assegnazione("R31_completo")
    corse = [
        _corsa("S_A", "S_B", 22, 0, 23, 0, treno="T1"),
        _corsa("S_B", "S_A", 23, 30, 1, 0, treno="T2"),  # cross notte
    ]
    turno = costruisci_turno_per_convoglio(
        convoglio_id="R31_completo_C0",
        segmento=seg,
        assegnazione=ass,
        calendario=cal,
        corse_segmento=corse,
        indice_convoglio=0,
        n_convogli_segmento=1,
    )
    # Prima 22:00 → ultima arrivo 01:00 = 3h = 180 min cross-mezzanotte
    assert turno.giornate[0].prestazione_min == 180


def test_km_none_trattato_come_zero() -> None:
    """Corsa con km_tratta=None → contribuisce 0."""
    seg = _segmento()
    cal = _calendario("R31_completo", date_feriali={date(2026, 6, 8)})
    ass = _assegnazione("R31_completo")
    corse = [
        _corsa("S_A", "S_B", 8, 0, 9, 0, treno="T1", km=None),
    ]
    turno = costruisci_turno_per_convoglio(
        convoglio_id="R31_completo_C0",
        segmento=seg,
        assegnazione=ass,
        calendario=cal,
        corse_segmento=corse,
        indice_convoglio=0,
        n_convogli_segmento=1,
    )
    assert turno.km_totali == 0.0


# =====================================================================
# Determinismo
# =====================================================================


def test_idempotenza_stesso_input_stesso_output() -> None:
    seg = _segmento()
    cal = _calendario("R31_completo", date_feriali={date(2026, 6, 8)})
    ass = _assegnazione("R31_completo")
    corse = [
        _corsa("S_A", "S_B", 8, 0, 9, 0, treno="T1"),
        _corsa("S_B", "S_A", 10, 0, 11, 0, treno="T2"),
    ]
    out1 = costruisci_turno_per_convoglio(
        convoglio_id="R31_completo_C0",
        segmento=seg,
        assegnazione=ass,
        calendario=cal,
        corse_segmento=corse,
        indice_convoglio=0,
        n_convogli_segmento=1,
    )
    out2 = costruisci_turno_per_convoglio(
        convoglio_id="R31_completo_C0",
        segmento=seg,
        assegnazione=ass,
        calendario=cal,
        corse_segmento=corse,
        indice_convoglio=0,
        n_convogli_segmento=1,
    )
    assert out1 == out2


def test_giornate_ordinate_per_data() -> None:
    """Output ordinato per data crescente."""
    seg = _segmento()
    cal = _calendario(
        "R31_completo",
        date_feriali={date(2026, 6, 10), date(2026, 6, 8), date(2026, 6, 9)},
    )
    ass = _assegnazione("R31_completo")
    corse = [
        _corsa("S_A", "S_B", 8, 0, 9, 0, treno="T1"),
    ]
    turno = costruisci_turno_per_convoglio(
        convoglio_id="R31_completo_C0",
        segmento=seg,
        assegnazione=ass,
        calendario=cal,
        corse_segmento=corse,
        indice_convoglio=0,
        n_convogli_segmento=1,
    )
    date_ordinate = [g.data for g in turno.giornate]
    assert date_ordinate == sorted(date_ordinate)
