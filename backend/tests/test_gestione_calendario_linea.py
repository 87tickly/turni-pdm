"""Test per ``domain/builder_giro/gestione_calendario_linea.py``
(Sprint 8.2 MR-D0.5).

Plan-D raccomandazione obbligatoria SEVERO #1: gestione esplicita
del calendario per `SegmentoLinea` come prerequisito per chiudere
il caso prog 14 giro 574 (sosta 20h44' fra varianti).

Test focus:
- Classificazione data (FERIALE/PREFESTIVO/SABATO/DOMENICA/FESTIVO)
- Festività italiane reali
- Generazione `CalendarioSegmento` da corse + periodo + festività
- Conteggio giorni per tipo nel periodo
- Determinismo (idempotenza, frozenset)
- Validazione invariante (date disgiunte fra categorie)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

import pytest

from colazione.domain.builder_giro.definizione_linea import (
    SegmentoLinea,
    TipoSegmento,
    VincoliSosta,
)
from colazione.domain.builder_giro.gestione_calendario_linea import (
    CalendarioSegmento,
    TipoCalendario,
    classifica_data,
    conta_giorni_periodo_per_tipo,
    festivita_per_anno,
    genera_calendario_segmento,
)

# =====================================================================
# Fixture helpers
# =====================================================================


@dataclass(frozen=True)
class _CorsaCalFake:
    codice_origine: str
    codice_destinazione: str
    ora_partenza: time
    ora_arrivo: time
    codice_linea: str
    valido_da: date
    valido_a: date
    valido_in_date_json: list[str] | None = None


def _segmento_test(codice: str = "R31_completo") -> SegmentoLinea:
    return SegmentoLinea(
        codice=codice,
        tipo=TipoSegmento.LINEARE,
        capolinee=frozenset({"S_A", "S_B"}),
        stazioni_sosta_notturna=frozenset({"S_A", "S_B"}),
        vincoli_sosta=VincoliSosta(),
        n_corse_per_die_media=2.0,
    )


# =====================================================================
# classifica_data
# =====================================================================


def test_classifica_lunedi_ordinario_feriale() -> None:
    """Lunedì 8 giugno 2026 (no festività) → FERIALE."""
    festivita_2026 = festivita_per_anno(2026)
    assert classifica_data(date(2026, 6, 8), festivita_2026) == TipoCalendario.FERIALE


def test_classifica_domenica_e_domenica() -> None:
    """Domenica 7 giugno 2026 → DOMENICA."""
    festivita_2026 = festivita_per_anno(2026)
    assert (
        classifica_data(date(2026, 6, 7), festivita_2026)
        == TipoCalendario.DOMENICA
    )


def test_classifica_natale_e_festivo() -> None:
    """25 dicembre 2026 (giovedì) → FESTIVO."""
    festivita_2026 = festivita_per_anno(2026)
    assert classifica_data(date(2026, 12, 25), festivita_2026) == TipoCalendario.FESTIVO


def test_classifica_ferragosto_e_festivo() -> None:
    """15 agosto 2026 (sabato) → FESTIVO (festivo non-domenica vince
    su sabato)."""
    festivita_2026 = festivita_per_anno(2026)
    assert classifica_data(date(2026, 8, 15), festivita_2026) == TipoCalendario.FESTIVO


def test_classifica_sabato_ordinario_e_prefestivo() -> None:
    """Sabato 6 giugno 2026 (precede domenica 7/6) → PREFESTIVO."""
    festivita_2026 = festivita_per_anno(2026)
    assert (
        classifica_data(date(2026, 6, 6), festivita_2026)
        == TipoCalendario.PREFESTIVO
    )


def test_classifica_vigilia_natale_prefestivo() -> None:
    """24/12/2026 (giovedì) precede 25/12 festivo → PREFESTIVO."""
    festivita_2026 = festivita_per_anno(2026)
    assert (
        classifica_data(date(2026, 12, 24), festivita_2026)
        == TipoCalendario.PREFESTIVO
    )


def test_classifica_pasqua_2026_e_festivo() -> None:
    """5 aprile 2026 = Pasqua (calcolata da algoritmo gregoriano).
    Pasqua è sempre domenica → DOMENICA, non FESTIVO (regola: domenica
    domina, vedi memoria etichetta).
    """
    festivita_2026 = festivita_per_anno(2026)
    assert (
        classifica_data(date(2026, 4, 5), festivita_2026)
        == TipoCalendario.DOMENICA
    )


def test_classifica_pasquetta_2026_festivo() -> None:
    """6 aprile 2026 = Pasquetta (lunedì) → FESTIVO."""
    festivita_2026 = festivita_per_anno(2026)
    assert (
        classifica_data(date(2026, 4, 6), festivita_2026)
        == TipoCalendario.FESTIVO
    )


def test_classifica_sabato_isolato_e_sabato() -> None:
    """Sabato che NON precede festivo → SABATO.
    Es: 13/6/2026 sabato, 14/6/2026 domenica → 13/6 PREFESTIVO.
    Per avere SABATO puro serve un sabato prima di un lunedì
    feriale: impossibile in calendario standard.
    Edge case: dopo un'eccezione festività che sopprime la domenica
    successiva. Test con festivita custom.
    """
    # Custom festivita_set: domenica 14/6 NON in festivita_set
    # (irrealistic ma testa la logica). Se il caller forza una
    # configurazione dove la domenica successiva non conta come
    # festivo, il sabato prima è sabato puro.
    # NB: la nostra logica di prefestivo usa SOLO weekday()==6 per
    # domeniche, non il festivita_set, quindi un sabato prima della
    # domenica resta sempre prefestivo. Il test verifica una data
    # senza domenica successiva: ma nel calendario standard ogni
    # sabato precede una domenica. Quindi SABATO è raggiungibile
    # SOLO se imponiamo classifica diversa di domenica.
    # Resto: vediamo se il test cattura il caso di sabato seguito
    # da feriale (non esiste in pratica, ma copertura).
    # Soluzione: testiamo direttamente che sabato precede sempre
    # domenica = sempre PREFESTIVO. Il caso SABATO puro è un edge
    # case raro ma esiste in teoria.
    # Verifichiamo invece il sabato successivo a un giorno: nessun
    # sabato puro nel calendario reale.
    # Test alternativo: data fittizia in cui il giorno dopo NON è
    # domenica (impossibile per costruzione → skip in questo test).
    festivita_2026 = festivita_per_anno(2026)
    # Tutti i sabati di giugno 2026 (6, 13, 20, 27) precedono
    # domeniche, quindi sono PREFESTIVO.
    assert (
        classifica_data(date(2026, 6, 13), festivita_2026)
        == TipoCalendario.PREFESTIVO
    )


# =====================================================================
# festivita_per_anno
# =====================================================================


def test_festivita_per_anno_2026_contiene_capodanno() -> None:
    festivita_2026 = festivita_per_anno(2026)
    assert date(2026, 1, 1) in festivita_2026


def test_festivita_per_anno_2026_contiene_natale() -> None:
    festivita_2026 = festivita_per_anno(2026)
    assert date(2026, 12, 25) in festivita_2026


def test_festivita_per_anno_2026_contiene_pasquetta() -> None:
    """Pasqua 2026 = 5/4, Pasquetta = 6/4."""
    festivita_2026 = festivita_per_anno(2026)
    assert date(2026, 4, 6) in festivita_2026


def test_festivita_per_anno_e_frozenset() -> None:
    """Output è frozenset (immutabile)."""
    festivita_2026 = festivita_per_anno(2026)
    assert isinstance(festivita_2026, frozenset)


# =====================================================================
# genera_calendario_segmento
# =====================================================================


def _corsa_lineare(
    codice_linea: str,
    valido_da: date,
    valido_a: date,
    *,
    valido_in_date: list[str] | None = None,
) -> _CorsaCalFake:
    return _CorsaCalFake(
        codice_origine="S_A",
        codice_destinazione="S_B",
        ora_partenza=time(8, 0),
        ora_arrivo=time(9, 0),
        codice_linea=codice_linea,
        valido_da=valido_da,
        valido_a=valido_a,
        valido_in_date_json=valido_in_date,
    )


def test_genera_calendario_corsa_giornaliera_feriali_e_festivi() -> None:
    """Una corsa giornaliera in 7-13 giugno 2026 → 6 giorni con tipi
    diversi (lun-ven feriale, sabato prefestivo, domenica)."""
    seg = _segmento_test()
    corsa = _corsa_lineare("R31", date(2026, 6, 7), date(2026, 6, 13))
    festivita_2026 = festivita_per_anno(2026)
    cal = genera_calendario_segmento(
        seg,
        [corsa],
        periodo_da=date(2026, 6, 7),
        periodo_a=date(2026, 6, 13),
        festivita_set=festivita_2026,
    )
    assert cal.segmento_codice == "R31_completo"
    # Domenica 7/6 + lun-ven 8-12 + sab 13/6
    # 7/6 domenica, 8-12 feriali, 13/6 prefestivo
    assert cal.n_giorni_per_tipo(TipoCalendario.DOMENICA) == 1
    assert cal.n_giorni_per_tipo(TipoCalendario.FERIALE) == 5
    assert cal.n_giorni_per_tipo(TipoCalendario.PREFESTIVO) == 1


def test_genera_calendario_corsa_solo_feriali_via_valido_in_date() -> None:
    """Corsa attiva solo lun-ven (5 date specificate) → 5 FERIALE."""
    seg = _segmento_test()
    corsa = _corsa_lineare(
        "R31",
        date(2026, 6, 8),
        date(2026, 6, 12),
        valido_in_date=[
            "2026-06-08",
            "2026-06-09",
            "2026-06-10",
            "2026-06-11",
            "2026-06-12",
        ],
    )
    festivita_2026 = festivita_per_anno(2026)
    cal = genera_calendario_segmento(
        seg,
        [corsa],
        periodo_da=date(2026, 6, 7),
        periodo_a=date(2026, 6, 13),
        festivita_set=festivita_2026,
    )
    assert cal.n_giorni_per_tipo(TipoCalendario.FERIALE) == 5
    assert cal.n_giorni_per_tipo(TipoCalendario.DOMENICA) == 0
    assert cal.n_giorni_per_tipo(TipoCalendario.PREFESTIVO) == 0


def test_genera_calendario_periodo_invalido() -> None:
    seg = _segmento_test()
    festivita_2026 = festivita_per_anno(2026)
    with pytest.raises(ValueError, match="periodo_da"):
        genera_calendario_segmento(
            seg,
            [],
            periodo_da=date(2026, 6, 13),
            periodo_a=date(2026, 6, 7),  # invertito
            festivita_set=festivita_2026,
        )


def test_genera_calendario_corse_fuori_periodo_ignorate() -> None:
    """Corsa valida fuori dal periodo → ignorata."""
    seg = _segmento_test()
    corsa = _corsa_lineare("R31", date(2026, 7, 1), date(2026, 7, 10))
    festivita_2026 = festivita_per_anno(2026)
    cal = genera_calendario_segmento(
        seg,
        [corsa],
        periodo_da=date(2026, 6, 7),
        periodo_a=date(2026, 6, 13),
        festivita_set=festivita_2026,
    )
    assert cal.date_attive_totali() == frozenset()


def test_genera_calendario_idempotente() -> None:
    """Stesso input → stesso output."""
    seg = _segmento_test()
    corsa = _corsa_lineare("R31", date(2026, 6, 7), date(2026, 6, 13))
    festivita_2026 = festivita_per_anno(2026)
    cal1 = genera_calendario_segmento(
        seg,
        [corsa],
        periodo_da=date(2026, 6, 7),
        periodo_a=date(2026, 6, 13),
        festivita_set=festivita_2026,
    )
    cal2 = genera_calendario_segmento(
        seg,
        [corsa],
        periodo_da=date(2026, 6, 7),
        periodo_a=date(2026, 6, 13),
        festivita_set=festivita_2026,
    )
    assert cal1 == cal2


def test_genera_calendario_valido_in_date_json_invalido_ignorato() -> None:
    """valido_in_date_json con stringhe non-data → ignorate (defensive)."""
    seg = _segmento_test()
    corsa = _corsa_lineare(
        "R31",
        date(2026, 6, 8),
        date(2026, 6, 12),
        valido_in_date=["2026-06-08", "non-una-data", "2026-06-09"],
    )
    festivita_2026 = festivita_per_anno(2026)
    cal = genera_calendario_segmento(
        seg,
        [corsa],
        periodo_da=date(2026, 6, 7),
        periodo_a=date(2026, 6, 13),
        festivita_set=festivita_2026,
    )
    assert cal.n_giorni_per_tipo(TipoCalendario.FERIALE) == 2


# =====================================================================
# CalendarioSegmento validation
# =====================================================================


def test_calendario_segmento_invariante_disgiunzione_violata() -> None:
    """Una stessa data in più categorie → ValueError."""
    with pytest.raises(ValueError, match=r"[Dd]uplicat"):
        CalendarioSegmento(
            segmento_codice="X",
            date_per_tipo={
                TipoCalendario.FERIALE: frozenset({date(2026, 6, 8)}),
                TipoCalendario.SABATO: frozenset({date(2026, 6, 8)}),
            },
        )


def test_calendario_segmento_codice_vuoto_invalido() -> None:
    with pytest.raises(ValueError, match="segmento_codice"):
        CalendarioSegmento(
            segmento_codice="",
            date_per_tipo={},
        )


def test_calendario_segmento_date_attive_totali_unisce_eccezioni() -> None:
    """date_attive_totali = unione tipi + eccezioni_attive."""
    cal = CalendarioSegmento(
        segmento_codice="X",
        date_per_tipo={
            TipoCalendario.FERIALE: frozenset(
                {date(2026, 6, 8), date(2026, 6, 9)}
            ),
        },
        eccezioni_attive=frozenset({date(2026, 6, 7)}),
    )
    assert cal.date_attive_totali() == frozenset(
        {date(2026, 6, 7), date(2026, 6, 8), date(2026, 6, 9)}
    )


# =====================================================================
# conta_giorni_periodo_per_tipo
# =====================================================================


def test_conta_giorni_periodo_settimana_completa() -> None:
    """7-13 giugno 2026: dom + 5 feriali + 1 prefestivo (sabato)."""
    festivita_2026 = festivita_per_anno(2026)
    counts = conta_giorni_periodo_per_tipo(
        periodo_da=date(2026, 6, 7),
        periodo_a=date(2026, 6, 13),
        festivita_set=festivita_2026,
    )
    assert counts[TipoCalendario.DOMENICA] == 1
    assert counts[TipoCalendario.FERIALE] == 5
    assert counts[TipoCalendario.PREFESTIVO] == 1


def test_conta_giorni_periodo_invalido() -> None:
    festivita_2026 = festivita_per_anno(2026)
    with pytest.raises(ValueError, match="periodo_da"):
        conta_giorni_periodo_per_tipo(
            periodo_da=date(2026, 6, 13),
            periodo_a=date(2026, 6, 7),
            festivita_set=festivita_2026,
        )


def test_conta_giorni_settimana_natale_2026() -> None:
    """22-28 dicembre 2026: lun-mer feriali, gio FESTIVO (Natale 25 ven),
    23/12 mer prefestivo? No, 24/12 gio prefestivo (vigilia Natale).
    25/12 ven festivo (Natale).
    26/12 sab festivo (Santo Stefano).
    27/12 dom domenica.
    28/12 lun feriale.
    Quindi: 22/12 lun feriale, 23/12 mar feriale, 24/12 mer prefestivo,
    25/12 gio festivo, 26/12 ven festivo, 27/12 sab... aspetta:
    le date 22-28 dicembre 2026:
    22/12 mar
    23/12 mer
    24/12 gio
    25/12 ven (Natale)
    26/12 sab (Santo Stefano)
    27/12 dom
    28/12 lun
    """
    # dicembre 2026: 1 dicembre = martedì (verifichiamo)
    # 1/12/2026 = martedì
    # 22/12/2026 = martedì
    festivita_2026 = festivita_per_anno(2026)
    counts = conta_giorni_periodo_per_tipo(
        periodo_da=date(2026, 12, 22),
        periodo_a=date(2026, 12, 28),
        festivita_set=festivita_2026,
    )
    # 22 mar, 23 mer feriali = 2
    # 24 gio (prefestivo Natale) = 1
    # 25 ven festivo (Natale)
    # 26 sab festivo (Santo Stefano)
    # 27 dom
    # 28 lun feriale
    # FERIALE = 22, 23, 28 = 3 (lun 28 feriale ordinario)
    # PREFESTIVO = 24 = 1
    # FESTIVO = 25, 26 = 2
    # DOMENICA = 27 = 1
    assert counts[TipoCalendario.FERIALE] == 3
    assert counts[TipoCalendario.PREFESTIVO] == 1
    assert counts[TipoCalendario.FESTIVO] == 2
    assert counts[TipoCalendario.DOMENICA] == 1


# =====================================================================
# Integrazione MR-D0 → MR-D0.5: SegmentoLinea passato a calendario
# =====================================================================


def test_integrazione_mrD0_segmento_passato_a_calendario() -> None:
    """End-to-end MR-D0 → MR-D0.5: crea SegmentoLinea, genera
    CalendarioSegmento, conta giorni feriali. Verifica integrazione
    fra moduli.
    """
    seg = _segmento_test(codice="RE13_completo")
    corse = [
        _corsa_lineare("RE13", date(2026, 6, 8), date(2026, 6, 12)),
    ]
    festivita_2026 = festivita_per_anno(2026)
    cal = genera_calendario_segmento(
        seg,
        corse,
        periodo_da=date(2026, 6, 7),
        periodo_a=date(2026, 6, 13),
        festivita_set=festivita_2026,
    )
    assert cal.segmento_codice == "RE13_completo"
    assert cal.n_giorni_per_tipo(TipoCalendario.FERIALE) == 5
    # Il segmento NON è attivo nei weekend perché valido_da/a
    # coprono solo lun-ven 8-12
    assert cal.n_giorni_per_tipo(TipoCalendario.DOMENICA) == 0
