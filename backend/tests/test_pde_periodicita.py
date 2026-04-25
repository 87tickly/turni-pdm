"""Test parser periodicità testuale (Sprint 3.4)."""

from datetime import date

from colazione.importers.pde import (
    PeriodicitaParsed,
    compute_valido_in_date,
    parse_periodicita,
)

# ---------- parse_periodicita ----------


def test_empty_text_returns_default() -> None:
    p = parse_periodicita("")
    assert p == PeriodicitaParsed()
    assert p.is_tutti_giorni is False


def test_tutti_i_giorni_simple() -> None:
    p = parse_periodicita("Circola tutti i giorni.")
    assert p.is_tutti_giorni is True
    assert p.apply_intervals == []
    assert p.skip_intervals == []


def test_tutti_i_giorni_with_skip_interval() -> None:
    """Pattern frequente: 'Circola tutti i giorni. Non circola dal X al Y.'"""
    p = parse_periodicita("Circola tutti i giorni. Non circola dal 01/12/2025 al 13/12/2025.")
    assert p.is_tutti_giorni is True
    assert p.skip_intervals == [(date(2025, 12, 1), date(2025, 12, 13))]
    assert p.apply_intervals == []


def test_apply_interval_only() -> None:
    p = parse_periodicita("Circola dal 14/01/2026 al 17/01/2026.")
    assert p.is_tutti_giorni is False
    assert p.apply_intervals == [(date(2026, 1, 14), date(2026, 1, 17))]
    assert p.skip_intervals == []


def test_apply_dates_short_list() -> None:
    p = parse_periodicita("Circola 12/01/2026, 13/01/2026.")
    assert p.is_tutti_giorni is False
    assert p.apply_dates == {date(2026, 1, 12), date(2026, 1, 13)}
    assert p.apply_intervals == []


def test_tutti_giorni_with_interval_is_not_default() -> None:
    """'Circola tutti i giorni dal X al Y' → apply_interval, NON is_tutti_giorni."""
    p = parse_periodicita(
        "Circola tutti i giorni dal 02/03/2026 al 22/03/2026. Circola 28/03/2026."
    )
    assert p.is_tutti_giorni is False  # ha intervallo, non è "default tutti"
    assert p.apply_intervals == [(date(2026, 3, 2), date(2026, 3, 22))]
    assert p.apply_dates == {date(2026, 3, 28)}


def test_long_apply_dates_list() -> None:
    """Lista di date estratte da Periodicità reale Trenord (ridotta)."""
    text = (
        "Circola 19/12/2025, 20/12/2025, 26/12/2025, 27/12/2025, "
        "02/01/2026, 03/01/2026, 09/01/2026."
    )
    p = parse_periodicita(text)
    assert p.is_tutti_giorni is False
    assert p.apply_dates == {
        date(2025, 12, 19),
        date(2025, 12, 20),
        date(2025, 12, 26),
        date(2025, 12, 27),
        date(2026, 1, 2),
        date(2026, 1, 3),
        date(2026, 1, 9),
    }


def test_skip_interval_plus_skip_dates() -> None:
    """'Non circola dal X al Y, DD/MM/YYYY' (intervallo + date miste)."""
    text = (
        "Circola tutti i giorni. Non circola dal 01/12/2025 al 13/12/2025, 25/12/2025, 01/01/2026."
    )
    p = parse_periodicita(text)
    assert p.is_tutti_giorni is True
    assert p.skip_intervals == [(date(2025, 12, 1), date(2025, 12, 13))]
    assert p.skip_dates == {date(2025, 12, 25), date(2026, 1, 1)}


def test_dates_inside_interval_not_double_counted() -> None:
    """Le date all'interno di un intervallo non finiscono in apply_dates."""
    text = "Circola dal 01/06/2026 al 03/06/2026."
    p = parse_periodicita(text)
    assert p.apply_intervals == [(date(2026, 6, 1), date(2026, 6, 3))]
    # 01/06, 02/06, 03/06 sono nell'intervallo: non in apply_dates
    assert p.apply_dates == set()


# ---------- filtro giorno-della-settimana ----------


def test_filtro_sabato_e_domenica() -> None:
    """'Circola il sabato e la domenica' → filtro globale {sab, dom}."""
    p = parse_periodicita("Circola il sabato e la domenica.")
    assert p.filtro_giorni_settimana == {5, 6}
    assert p.is_tutti_giorni is False
    assert p.apply_intervals == []


def test_filtro_solo_sabato() -> None:
    p = parse_periodicita("Circola il sabato.")
    assert p.filtro_giorni_settimana == {5}


def test_filtro_combinato_con_intervalli_override() -> None:
    """Filtro globale + override per intervalli espliciti.

    Pattern reale Trenord (treno 786):
    'Circola il sabato e la domenica. Circola tutti i giorni dal 05/02
    al 22/02. Non circola DD/MM. Circola DD/MM, DD/MM, ...'
    """
    text = (
        "Circola il sabato e la domenica. "
        "Circola tutti i giorni dal 05/02/2026 al 22/02/2026. "
        "Non circola 07/03/2026, 08/03/2026. "
        "Circola 01/01/2026, 06/01/2026."
    )
    p = parse_periodicita(text)
    assert p.filtro_giorni_settimana == {5, 6}
    assert p.apply_intervals == [(date(2026, 2, 5), date(2026, 2, 22))]
    assert p.skip_dates == {date(2026, 3, 7), date(2026, 3, 8)}
    assert p.apply_dates == {date(2026, 1, 1), date(2026, 1, 6)}


def test_filtro_non_setta_se_intervallo_presente() -> None:
    """Frase con weekday + intervallo non setta filtro globale."""
    p = parse_periodicita("Circola tutti i giorni dal 05/02/2026 al 22/02/2026.")
    assert p.filtro_giorni_settimana == set()
    assert p.apply_intervals == [(date(2026, 2, 5), date(2026, 2, 22))]


# ---------- compute_valido_in_date con filtro giorni-settimana ----------


def test_compute_filtro_solo_sabato_e_domenica() -> None:
    """Filtro {5,6}: solo sab e dom in [valido_da, valido_a]."""
    p = PeriodicitaParsed(filtro_giorni_settimana={5, 6})
    # 02/02/2026 (lun) → 08/02/2026 (dom): 7/2 sab + 8/2 dom = 2
    dates = compute_valido_in_date(date(2026, 2, 2), date(2026, 2, 8), p)
    assert dates == {date(2026, 2, 7), date(2026, 2, 8)}


def test_compute_filtro_with_apply_interval_override() -> None:
    """Apply interval supera il filtro globale (override completo)."""
    p = PeriodicitaParsed(
        filtro_giorni_settimana={5, 6},  # solo sab/dom
        apply_intervals=[(date(2026, 2, 9), date(2026, 2, 13))],  # lun-ven
    )
    dates = compute_valido_in_date(date(2026, 2, 2), date(2026, 2, 15), p)
    # Sab/dom 7-8/2 + interval lun-ven 9-13/2 + sab/dom 14-15/2
    expected = {
        date(2026, 2, 7),
        date(2026, 2, 8),
        date(2026, 2, 9),
        date(2026, 2, 10),
        date(2026, 2, 11),
        date(2026, 2, 12),
        date(2026, 2, 13),
        date(2026, 2, 14),
        date(2026, 2, 15),
    }
    assert dates == expected


# ---------- compute_valido_in_date ----------


def test_compute_tutti_giorni_within_range() -> None:
    p = PeriodicitaParsed(is_tutti_giorni=True)
    dates = compute_valido_in_date(date(2026, 1, 1), date(2026, 1, 5), p)
    assert dates == {
        date(2026, 1, 1),
        date(2026, 1, 2),
        date(2026, 1, 3),
        date(2026, 1, 4),
        date(2026, 1, 5),
    }


def test_compute_tutti_giorni_minus_skip() -> None:
    p = PeriodicitaParsed(
        is_tutti_giorni=True,
        skip_intervals=[(date(2026, 1, 2), date(2026, 1, 3))],
    )
    dates = compute_valido_in_date(date(2026, 1, 1), date(2026, 1, 5), p)
    assert dates == {date(2026, 1, 1), date(2026, 1, 4), date(2026, 1, 5)}


def test_compute_apply_interval_only() -> None:
    p = PeriodicitaParsed(apply_intervals=[(date(2026, 6, 1), date(2026, 6, 3))])
    dates = compute_valido_in_date(date(2026, 1, 1), date(2026, 12, 31), p)
    assert dates == {date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3)}


def test_compute_apply_dates_filtered_by_range() -> None:
    """Date apply fuori da [valido_da, valido_a] vengono scartate."""
    p = PeriodicitaParsed(apply_dates={date(2025, 1, 1), date(2026, 6, 1)})
    dates = compute_valido_in_date(date(2026, 1, 1), date(2026, 12, 31), p)
    assert dates == {date(2026, 6, 1)}  # 2025-01-01 fuori range


def test_compute_skip_overrides_apply() -> None:
    """skip_dates ha precedenza su apply (anche se la data è in apply_interval)."""
    p = PeriodicitaParsed(
        apply_intervals=[(date(2026, 6, 1), date(2026, 6, 5))],
        skip_dates={date(2026, 6, 3)},
    )
    dates = compute_valido_in_date(date(2026, 1, 1), date(2026, 12, 31), p)
    assert date(2026, 6, 3) not in dates
    assert dates == {
        date(2026, 6, 1),
        date(2026, 6, 2),
        date(2026, 6, 4),
        date(2026, 6, 5),
    }


def test_compute_clip_interval_to_validity() -> None:
    """Intervalli che sforano [valido_da, valido_a] vengono troncati."""
    p = PeriodicitaParsed(apply_intervals=[(date(2025, 12, 28), date(2026, 1, 5))])
    dates = compute_valido_in_date(date(2026, 1, 1), date(2026, 12, 31), p)
    assert min(dates) == date(2026, 1, 1)
    assert max(dates) == date(2026, 1, 5)
    assert len(dates) == 5
