"""Test puri MR-1110 sotto-MR 4 — ``genera_etichetta_parlante``.

Coprono i 7 casi dell'algoritmo decisionale + acceptance turno
1110 G6 (6 etichette dal PDF Trenord).

Niente DB, niente fixture giornata-tipo: solo set di date e
festività italiane note (entry calendario).
"""

from __future__ import annotations

from datetime import date, timedelta

from colazione.domain.builder_giro.etichetta import genera_etichetta_parlante
from colazione.domain.calendario import (
    festivi_precedenti_festivo,
    festivita_italiane,
)

# =====================================================================
# Setup periodo + festività 2026
# =====================================================================

PERIODO_2026 = (date(2026, 1, 1), date(2026, 12, 31))

# Festività italiane 2026 (10 fisse + Pasqua + Pasquetta).
# Aggiungiamo le domeniche al set perché _classifica_giorno_4_categorie
# le tratta implicitamente come festivi.
def _festivita_2026() -> frozenset[date]:
    out: set[date] = set()
    for d, _nome in festivita_italiane(2026):
        out.add(d)
    return frozenset(out)


FESTIVITA_2026 = _festivita_2026()


def _giorni_periodo() -> list[date]:
    inizio, fine = PERIODO_2026
    n = (fine - inizio).days
    return [inizio + timedelta(days=i) for i in range(n + 1)]


# =====================================================================
# Casi base
# =====================================================================


def test_set_vuoto() -> None:
    assert (
        genera_etichetta_parlante(
            frozenset(), PERIODO_2026, FESTIVITA_2026
        )
        == "(nessuna data)"
    )


def test_singola_data_solo_dmyy() -> None:
    out = genera_etichetta_parlante(
        frozenset({date(2026, 5, 1)}), PERIODO_2026, FESTIVITA_2026
    )
    assert out == "Solo 1/5/26"


# =====================================================================
# Pattern strutturali esatti
# =====================================================================


def test_lv_1_5_completo() -> None:
    """Tutte le date lavorative 1-5 del periodo → 'LV 1:5'."""
    lv_1_5_set = frozenset(
        d
        for d in _giorni_periodo()
        if d.weekday() in (0, 1, 2, 3, 4) and d not in FESTIVITA_2026
    )
    out = genera_etichetta_parlante(lv_1_5_set, PERIODO_2026, FESTIVITA_2026)
    assert out == "LV 1:5"


def test_lv_6_completo() -> None:
    """Tutti i sabati lavorativi (non festa) del periodo → 'LV 6'."""
    lv_6_set = frozenset(
        d
        for d in _giorni_periodo()
        if d.weekday() == 5 and d not in FESTIVITA_2026
    )
    out = genera_etichetta_parlante(lv_6_set, PERIODO_2026, FESTIVITA_2026)
    assert out == "LV 6"


def test_circola_sabato_festivo() -> None:
    """Tutti i sabati che cadono festività → 'Circola Sabato Festivo'."""
    sabati_festivi = frozenset(
        d
        for d in _giorni_periodo()
        if d.weekday() == 5 and d in FESTIVITA_2026
    )
    # In 2026: 25/4 (Liberazione) cade di sabato. Verifichiamo.
    assert date(2026, 4, 25) in sabati_festivi
    out = genera_etichetta_parlante(
        sabati_festivi, PERIODO_2026, FESTIVITA_2026
    )
    assert out == "Circola Sabato Festivo"


def test_f_completo_tutti_festivi() -> None:
    """Tutte le date festive (festa + domenica) del periodo → 'F'."""
    festivi_completi = frozenset(
        d
        for d in _giorni_periodo()
        # festivo = lun-ven festa OR domenica OR (NB sabato festa va in
        # sabato_festivo)
        if (d.weekday() in (0, 1, 2, 3, 4) and d in FESTIVITA_2026)
        or d.weekday() == 6
    )
    out = genera_etichetta_parlante(
        festivi_completi, PERIODO_2026, FESTIVITA_2026
    )
    assert out == "F"


def test_f_escluso_fpf() -> None:
    """Tutti i festivi del periodo MENO i FpF → 'F escluso FpF'.

    FpF 2026: Pasqua (5/4 precede Pasquetta 6/4 — ma 5/4 è domenica),
    Natale (25/12 precede S.Stefano 26/12).
    """
    festivi_completi = frozenset(
        d
        for d in _giorni_periodo()
        if (d.weekday() in (0, 1, 2, 3, 4) and d in FESTIVITA_2026)
        or d.weekday() == 6
    )
    fpf = festivi_precedenti_festivo(FESTIVITA_2026) & festivi_completi
    assert len(fpf) >= 1, "Almeno Natale 25/12 dovrebbe essere FpF"

    festivi_meno_fpf = festivi_completi - fpf
    out = genera_etichetta_parlante(
        festivi_meno_fpf, PERIODO_2026, FESTIVITA_2026
    )
    assert out == "F escluso FpF"


# =====================================================================
# Pattern con esclusioni (≤ MAX_INLINE)
# =====================================================================


def test_lv_1_5_escl_poche() -> None:
    """LV 1:5 escluse 2 date specifiche → 'LV 1:5 escl. ...'."""
    lv_1_5_set = frozenset(
        d
        for d in _giorni_periodo()
        if d.weekday() in (0, 1, 2, 3, 4) and d not in FESTIVITA_2026
    )
    # Escludi 2 lavorativi specifici
    esclusi = {date(2026, 3, 16), date(2026, 11, 10)}
    dates_apply = frozenset(lv_1_5_set - esclusi)
    out = genera_etichetta_parlante(
        dates_apply, PERIODO_2026, FESTIVITA_2026
    )
    assert out == "LV 1:5 escl. 16/3, 10/11"


def test_f_escluso_fpf_ed_escl_specifiche() -> None:
    """Tutti i festivi escluso FpF + 2 date specifiche →
    'F escluso FpF ed escl. ...'.
    """
    festivi_completi = frozenset(
        d
        for d in _giorni_periodo()
        if (d.weekday() in (0, 1, 2, 3, 4) and d in FESTIVITA_2026)
        or d.weekday() == 6
    )
    fpf = festivi_precedenti_festivo(FESTIVITA_2026) & festivi_completi
    # Escludi FpF + 1 maggio (festa lavoratori) + 2 giugno (festa
    # repubblica), che sono normalmente festivi
    extra_esclusi = {date(2026, 5, 1), date(2026, 6, 2)}
    dates_apply = frozenset(festivi_completi - fpf - extra_esclusi)
    out = genera_etichetta_parlante(
        dates_apply, PERIODO_2026, FESTIVITA_2026
    )
    # 1/5 = ven (lavorativo cat ma in festivita → festivo cat); 2/6 =
    # mar (lavorativo cat ma in festivita → festivo cat)
    assert "F escluso FpF ed escl." in out
    assert "1/5" in out and "2/6" in out


# =====================================================================
# Finestra continua + Si eff. + fallback
# =====================================================================


def test_finestra_continua_dal_al() -> None:
    """7 date consecutive → 'Dal D/M al D/M'."""
    dates = frozenset(
        date(2026, 6, i) for i in range(15, 22)
    )  # 15/6 - 21/6 (7 giorni)
    out = genera_etichetta_parlante(dates, PERIODO_2026, FESTIVITA_2026)
    assert out == "Dal 15/6 al 21/6"


def test_si_eff_pochi_giorni_misti() -> None:
    """3 date specifiche miste cat → 'Si eff. ...'."""
    dates = frozenset(
        {date(2026, 3, 22), date(2026, 4, 12), date(2026, 7, 4)}
    )
    out = genera_etichetta_parlante(dates, PERIODO_2026, FESTIVITA_2026)
    assert out == "Si eff. 22/3, 12/4, 4/7"


def test_misto_fallback_molte_date_categorie_diverse() -> None:
    """Molte date di categorie miste senza pattern strutturale →
    'Misto: ... (N date)'.
    """
    # Tante date sparse: alcune lv_1_5, alcune festive, alcune sabati
    dates: set[date] = set()
    for i in range(20):
        # Lavorativi: 5/2 + i*7
        dates.add(date(2026, 2, 5) + timedelta(days=i * 7))
    # Aggiungi 1 festivo (15/8 sabato → sabato_festivo)
    dates.add(date(2026, 8, 15))
    out = genera_etichetta_parlante(
        frozenset(dates), PERIODO_2026, FESTIVITA_2026
    )
    assert out.startswith("Misto:")
    assert "date)" in out


# =====================================================================
# Acceptance turno 1110 G6 (PDF Trenord — 6 etichette)
# =====================================================================


def test_acceptance_turno_1110_lv_1_5() -> None:
    """Variante 1 turno 1110 G6: 'LV 1:5'."""
    lv_1_5 = frozenset(
        d
        for d in _giorni_periodo()
        if d.weekday() in (0, 1, 2, 3, 4) and d not in FESTIVITA_2026
    )
    assert (
        genera_etichetta_parlante(lv_1_5, PERIODO_2026, FESTIVITA_2026)
        == "LV 1:5"
    )


def test_acceptance_turno_1110_circola_sabato_festivo() -> None:
    """Variante 4 turno 1110 G6: 'Circola Sabato Festivo'."""
    sf = frozenset(
        d
        for d in _giorni_periodo()
        if d.weekday() == 5 and d in FESTIVITA_2026
    )
    assert (
        genera_etichetta_parlante(sf, PERIODO_2026, FESTIVITA_2026)
        == "Circola Sabato Festivo"
    )


def test_acceptance_turno_1110_si_eff_22_3_12_4() -> None:
    """Variante 5 turno 1110 G6: 'Si eff. 22/3, 12/4'."""
    dates = frozenset({date(2026, 3, 22), date(2026, 4, 12)})
    assert (
        genera_etichetta_parlante(dates, PERIODO_2026, FESTIVITA_2026)
        == "Si eff. 22/3, 12/4"
    )


def test_acceptance_turno_1110_si_eff_1_5_e_2_6() -> None:
    """Variante 6 turno 1110 G6: 'Si eff. 1/5, 2/6' (formattazione
    semplificata)."""
    dates = frozenset({date(2026, 5, 1), date(2026, 6, 2)})
    assert (
        genera_etichetta_parlante(dates, PERIODO_2026, FESTIVITA_2026)
        == "Si eff. 1/5, 2/6"
    )


def test_acceptance_turno_1110_lv_6_solo_sabati_lavorativi() -> None:
    """Variante 3 turno 1110 G6: 'LV 6'."""
    lv_6 = frozenset(
        d
        for d in _giorni_periodo()
        if d.weekday() == 5 and d not in FESTIVITA_2026
    )
    assert (
        genera_etichetta_parlante(lv_6, PERIODO_2026, FESTIVITA_2026)
        == "LV 6"
    )
