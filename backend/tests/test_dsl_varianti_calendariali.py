"""Test parser DSL etichette parlanti Trenord — Sprint 8.3 S9."""

from __future__ import annotations

from datetime import date

import pytest

from colazione.domain.calendario import festivita_italiane
from colazione.domain.dsl_varianti_calendariali import (
    _parse_date_list,
    parse_variante_dsl,
)

# Festività 2026 (test reference year)
_FEST_2026 = frozenset(d for d, _ in festivita_italiane(2026))


# =====================================================================
# Helper _parse_date_list
# =====================================================================


class TestParseDateList:
    def test_singola_data_dd_m(self) -> None:
        assert _parse_date_list("22/3", anno_default=2026) == [date(2026, 3, 22)]

    def test_singola_data_dd_mm(self) -> None:
        assert _parse_date_list("22/03", anno_default=2026) == [date(2026, 3, 22)]

    def test_due_date_separator_e(self) -> None:
        assert _parse_date_list("1/5 e 2/6", anno_default=2026) == [
            date(2026, 5, 1),
            date(2026, 6, 2),
        ]

    def test_lista_separatore_virgola(self) -> None:
        assert _parse_date_list("22/3, 12/4", anno_default=2026) == [
            date(2026, 3, 22),
            date(2026, 4, 12),
        ]

    def test_misto_virgola_e(self) -> None:
        out = _parse_date_list("22/3, 12/4, 1/5 e 2/6", anno_default=2026)
        assert out == [
            date(2026, 3, 22),
            date(2026, 4, 12),
            date(2026, 5, 1),
            date(2026, 6, 2),
        ]

    def test_data_con_anno_2_cifre(self) -> None:
        assert _parse_date_list("4/5/26", anno_default=2025) == [date(2026, 5, 4)]

    def test_data_malformata_ignorata(self) -> None:
        # 32/13 (giorno e mese non validi) → silently ignored
        assert _parse_date_list("32/13", anno_default=2026) == []


# =====================================================================
# parse_variante_dsl — categorie base
# =====================================================================


class TestSintassiBase:
    def test_gg_tutti(self) -> None:
        f = parse_variante_dsl("GG", anno_default=2026)
        assert f is not None
        assert f(date(2026, 3, 15), _FEST_2026)
        assert f(date(2026, 12, 25), _FEST_2026)

    def test_giornaliero_alias(self) -> None:
        f = parse_variante_dsl("giornaliero", anno_default=2026)
        assert f is not None
        assert f(date(2026, 3, 15), _FEST_2026)

    def test_vuoto_o_none_ritorna_none(self) -> None:
        assert parse_variante_dsl("", anno_default=2026) is None
        assert parse_variante_dsl(None, anno_default=2026) is None
        assert parse_variante_dsl("   ", anno_default=2026) is None


class TestSoloData:
    def test_solo_data_specifica(self) -> None:
        f = parse_variante_dsl("Solo 4/5/26", anno_default=2026)
        assert f is not None
        assert f(date(2026, 5, 4), _FEST_2026)
        assert not f(date(2026, 5, 5), _FEST_2026)

    def test_solo_data_anno_4_cifre(self) -> None:
        f = parse_variante_dsl("Solo 4/5/2026", anno_default=2026)
        assert f is not None
        assert f(date(2026, 5, 4), _FEST_2026)


# =====================================================================
# Si eff. <date list>
# =====================================================================


class TestSiEff:
    def test_si_eff_due_date(self) -> None:
        f = parse_variante_dsl("Si eff. 22/3, 12/4", anno_default=2026)
        assert f is not None
        assert f(date(2026, 3, 22), _FEST_2026)
        assert f(date(2026, 4, 12), _FEST_2026)
        assert not f(date(2026, 3, 23), _FEST_2026)

    def test_si_eff_separator_e(self) -> None:
        f = parse_variante_dsl("Si eff. 1/5 e 2/6", anno_default=2026)
        assert f is not None
        assert f(date(2026, 5, 1), _FEST_2026)
        assert f(date(2026, 6, 2), _FEST_2026)


# =====================================================================
# LV <range> [esclusi <date list>]
# =====================================================================


class TestLV:
    def test_lv_1_5_lavorativi_lun_ven(self) -> None:
        f = parse_variante_dsl("LV 1:5", anno_default=2026)
        assert f is not None
        # Lunedì 2/3/2026 NON festivo
        assert f(date(2026, 3, 2), _FEST_2026)
        # Venerdì 6/3 NON festivo
        assert f(date(2026, 3, 6), _FEST_2026)
        # Sabato 7/3 = fuori range LV 1:5
        assert not f(date(2026, 3, 7), _FEST_2026)
        # Domenica 8/3 = fuori range
        assert not f(date(2026, 3, 8), _FEST_2026)
        # Pasquetta 6/4/2026 (lunedì festivo): escluso perché festivo
        assert not f(date(2026, 4, 6), _FEST_2026)

    def test_lv_6_solo_sabati_non_festivi(self) -> None:
        f = parse_variante_dsl("LV 6", anno_default=2026)
        assert f is not None
        # Sabato 7/3 NON festivo
        assert f(date(2026, 3, 7), _FEST_2026)
        # Sabato 25/4 = Liberazione (festivo) → escluso
        assert not f(date(2026, 4, 25), _FEST_2026)
        # Lunedì → fuori range
        assert not f(date(2026, 3, 2), _FEST_2026)

    def test_lv_generico_lavorativo(self) -> None:
        f = parse_variante_dsl("LV", anno_default=2026)
        assert f is not None
        # Lun-ven non festivi
        assert f(date(2026, 3, 2), _FEST_2026)  # lun
        # Sabato escluso (LV default è 1:5)
        assert not f(date(2026, 3, 7), _FEST_2026)

    def test_lv_1_5_con_esclusioni(self) -> None:
        f = parse_variante_dsl("LV 1:5 escl. 4/3", anno_default=2026)
        assert f is not None
        # Mercoledì 4/3 escluso esplicitamente
        assert not f(date(2026, 3, 4), _FEST_2026)
        # Mercoledì 11/3 ancora valido
        assert f(date(2026, 3, 11), _FEST_2026)

    def test_lv_esclusi_multipli(self) -> None:
        f = parse_variante_dsl(
            "LV esclusi 21/3, 28/3, 11/4", anno_default=2026
        )
        assert f is not None
        # 21/3 = sabato (fuori range LV default 1:5 anyway)
        # 28/3 = sabato
        # 11/4 = sabato
        # I 3 sabati sono comunque fuori range, ma l'esclusione esplicita non guasta
        assert not f(date(2026, 3, 21), _FEST_2026)


# =====================================================================
# F [escluso FpF] [esclusi <date list>]
# =====================================================================


class TestF:
    def test_f_solo_festivi(self) -> None:
        f = parse_variante_dsl("F", anno_default=2026)
        assert f is not None
        # Domenica 1/3
        assert f(date(2026, 3, 1), _FEST_2026)
        # Pasquetta 6/4 (lunedì festivo)
        assert f(date(2026, 4, 6), _FEST_2026)
        # 25/4 sabato + Liberazione = festivo
        assert f(date(2026, 4, 25), _FEST_2026)
        # Lunedì 2/3 non festivo
        assert not f(date(2026, 3, 2), _FEST_2026)

    def test_f_escluso_fpf(self) -> None:
        # Festività 2026: Pasqua 5/4 (dom) → Pasquetta 6/4 (lun, festivo).
        # Quindi Pasqua è FpF (festivo che precede festivo).
        # Anche 25/4 sabato Liberazione precede 26/4 dom → 25/4 è FpF.
        f = parse_variante_dsl("F escluso FpF", anno_default=2026)
        assert f is not None
        # Domenica normale 8/3 → festivo, NON FpF (lun 9/3 NON festivo)
        assert f(date(2026, 3, 8), _FEST_2026)
        # Pasqua 5/4 → festivo MA FpF → escluso
        assert not f(date(2026, 4, 5), _FEST_2026)
        # Pasquetta 6/4 → festivo, NON FpF (martedì 7/4 NON festivo)
        assert f(date(2026, 4, 6), _FEST_2026)
        # 25/4 sabato Liberazione → FpF (precede dom 26/4) → escluso
        assert not f(date(2026, 4, 25), _FEST_2026)

    def test_f_escluso_fpf_ed_escl_date(self) -> None:
        # Esempio reale Trenord MR-1110-DESIGN
        f = parse_variante_dsl(
            "F escluso FpF ed escl. 22/3, 12/4, 1/5 e 2/6",
            anno_default=2026,
        )
        assert f is not None
        # 22/3 dom → festivo + escluso esplicito
        assert not f(date(2026, 3, 22), _FEST_2026)
        # 12/4 dom → escluso esplicito
        assert not f(date(2026, 4, 12), _FEST_2026)
        # 1/5 ven Festa Lavoro → festivo, escluso esplicito
        assert not f(date(2026, 5, 1), _FEST_2026)
        # Domenica 8/3 → festivo, NON FpF, NON escluso → ok
        assert f(date(2026, 3, 8), _FEST_2026)


# =====================================================================
# Circola Sabato Festivo
# =====================================================================


class TestCircolaSabatoFestivo:
    def test_circola_sabato_festivo(self) -> None:
        f = parse_variante_dsl("Circola Sabato Festivo", anno_default=2026)
        assert f is not None
        # 25/4 sabato Liberazione = sabato festivo
        assert f(date(2026, 4, 25), _FEST_2026)
        # Sabato 7/3 NON festivo
        assert not f(date(2026, 3, 7), _FEST_2026)
        # Domenica festiva → no (non sabato)
        assert not f(date(2026, 3, 8), _FEST_2026)


# =====================================================================
# Sintassi non riconosciuta → None
# =====================================================================


class TestNonRiconosciuta:
    @pytest.mark.parametrize(
        "txt",
        [
            "ABC",
            "LMVGS",  # vecchia sintassi non LV
            "qualcosa di strano",
        ],
    )
    def test_pattern_non_riconosciuto_ritorna_none(self, txt: str) -> None:
        assert parse_variante_dsl(txt, anno_default=2026) is None


# =====================================================================
# Integration con enumera_date_giornata
# =====================================================================


def test_enumera_date_giornata_usa_parser_DSL_per_LV_1_5() -> None:
    """Verifica che il parser DSL sia integrato in enumera_date_giornata."""
    from colazione.domain.giornate_concrete import enumera_date_giornata

    out = enumera_date_giornata(
        numero_giornata=1,
        variante_calendario="LV 1:5",
        ciclo_giorni=7,
        data_inizio_programma=date(2026, 3, 30),  # lun
        data_fine_programma=date(2026, 4, 27),
        festivita=_FEST_2026,
    )
    # Lunedì 30/3, 13/4, 20/4, 27/4 (lun NON festivo). 6/4 Pasquetta esclusa.
    assert date(2026, 3, 30) in out
    assert date(2026, 4, 13) in out
    assert date(2026, 4, 20) in out
    assert date(2026, 4, 27) in out
    assert date(2026, 4, 6) not in out  # Pasquetta esclusa


def test_enumera_date_giornata_usa_parser_DSL_per_F_escluso_FpF() -> None:
    """Pattern reale Trenord."""
    from colazione.domain.giornate_concrete import enumera_date_giornata

    out = enumera_date_giornata(
        numero_giornata=1,
        variante_calendario="F escluso FpF",
        ciclo_giorni=1,  # ogni giorno candidato
        data_inizio_programma=date(2026, 4, 1),
        data_fine_programma=date(2026, 4, 30),
        festivita=_FEST_2026,
    )
    # Festivi aprile 2026: dom 5/4 (Pasqua, FpF), lun 6/4 (Pasquetta),
    # dom 12/4, dom 19/4, sab 25/4 (Liberazione, FpF), dom 26/4.
    # F escluso FpF rimuove 5/4 e 25/4.
    assert date(2026, 4, 6) in out  # Pasquetta sì
    assert date(2026, 4, 5) not in out  # Pasqua no (FpF)
    assert date(2026, 4, 25) not in out  # 25/4 sabato (FpF)
    assert date(2026, 4, 12) in out  # dom normale
    assert date(2026, 4, 26) in out  # dom dopo 25/4
