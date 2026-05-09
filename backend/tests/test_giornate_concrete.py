"""Test enumera_date_giornata — Sprint 8.2 MR-PD7b-1."""

from __future__ import annotations

from datetime import date

import pytest

from colazione.domain.calendario import festivita_italiane
from colazione.domain.giornate_concrete import enumera_date_giornata

# 2026: festività italiane note per i test
_FEST_2026 = frozenset(d for d, _ in festivita_italiane(2026))


class TestCandidateCiclo:
    """Calcolo posizione_ciclo da data."""

    def test_ciclo_7gg_giornata_1_lun_a_lun_marzo_2026(self) -> None:
        # 2026-03-02 = lunedì. Ciclo 7gg ancorato lì → giornata 1 = ogni lunedì.
        out = enumera_date_giornata(
            numero_giornata=1,
            variante_calendario=None,
            ciclo_giorni=7,
            data_inizio_programma=date(2026, 3, 2),
            data_fine_programma=date(2026, 3, 31),
            festivita=frozenset(),
        )
        assert out == [
            date(2026, 3, 2),
            date(2026, 3, 9),
            date(2026, 3, 16),
            date(2026, 3, 23),
            date(2026, 3, 30),
        ]

    def test_ciclo_5gg_giornata_3(self) -> None:
        out = enumera_date_giornata(
            numero_giornata=3,
            variante_calendario=None,
            ciclo_giorni=5,
            data_inizio_programma=date(2026, 3, 2),
            data_fine_programma=date(2026, 3, 16),
            festivita=frozenset(),
        )
        # Ciclo 5gg da lun 2/3: giornata 3 cade ogni 5 giorni a partire dal 4/3.
        # 4/3 (mer), 9/3 (lun), 14/3 (sab). Stop su 16/3.
        assert out == [
            date(2026, 3, 4),
            date(2026, 3, 9),
            date(2026, 3, 14),
        ]

    def test_giornata_fuori_range_warning_lista_vuota(self) -> None:
        out = enumera_date_giornata(
            numero_giornata=10,  # > ciclo_giorni
            variante_calendario=None,
            ciclo_giorni=5,
            data_inizio_programma=date(2026, 3, 2),
            data_fine_programma=date(2026, 3, 31),
            festivita=frozenset(),
        )
        assert out == []

    def test_data_fine_prima_di_inizio_lista_vuota(self) -> None:
        out = enumera_date_giornata(
            numero_giornata=1,
            variante_calendario=None,
            ciclo_giorni=5,
            data_inizio_programma=date(2026, 4, 1),
            data_fine_programma=date(2026, 3, 1),
            festivita=frozenset(),
        )
        assert out == []


class TestFiltroVariante:
    """Filtro per variante_calendario."""

    def test_variante_GG_tutte(self) -> None:
        out = enumera_date_giornata(
            numero_giornata=1,
            variante_calendario="GG",
            ciclo_giorni=7,
            data_inizio_programma=date(2026, 3, 2),
            data_fine_programma=date(2026, 3, 16),
            festivita=frozenset(),
        )
        assert len(out) == 3  # 3 lunedì

    def test_variante_LV_filtra_festivi(self) -> None:
        # Aprile 2026: 6/4 = Pasquetta (lunedì festivo). Ciclo 7gg da
        # 30/3 (lunedì): giornata 1 = lunedì. Senza filtro = 4 lunedì
        # (30/3, 6/4, 13/4, 20/4). Con filtro LV escludo 6/4.
        out = enumera_date_giornata(
            numero_giornata=1,
            variante_calendario="LV",
            ciclo_giorni=7,
            data_inizio_programma=date(2026, 3, 30),
            data_fine_programma=date(2026, 4, 27),
            festivita=_FEST_2026,
        )
        # Lunedì 30/3 lavorativo, 6/4 PASQUETTA festivo escluso,
        # 13/4 lavorativo, 20/4 lavorativo, 27/4 lavorativo.
        assert date(2026, 4, 6) not in out
        assert date(2026, 3, 30) in out
        assert date(2026, 4, 13) in out

    def test_variante_F_solo_festivi(self) -> None:
        # Periodo aprile 2026, ciclo 7gg da lunedì 30/3, giornata 1 lunedì.
        # 6/4 = Pasquetta lunedì. Solo questa data passa il filtro F.
        out = enumera_date_giornata(
            numero_giornata=1,
            variante_calendario="F",
            ciclo_giorni=7,
            data_inizio_programma=date(2026, 3, 30),
            data_fine_programma=date(2026, 4, 27),
            festivita=_FEST_2026,
        )
        assert out == [date(2026, 4, 6)]

    def test_variante_S_solo_sabati(self) -> None:
        # Periodo intero marzo, ciclo 1gg (= ogni giorno). Variante S =
        # solo sabati.
        out = enumera_date_giornata(
            numero_giornata=1,
            variante_calendario="S",
            ciclo_giorni=1,
            data_inizio_programma=date(2026, 3, 1),
            data_fine_programma=date(2026, 3, 31),
            festivita=frozenset(),
        )
        # Sabati di marzo 2026: 7, 14, 21, 28
        assert out == [
            date(2026, 3, 7),
            date(2026, 3, 14),
            date(2026, 3, 21),
            date(2026, 3, 28),
        ]

    def test_variante_D_solo_domeniche(self) -> None:
        out = enumera_date_giornata(
            numero_giornata=1,
            variante_calendario="D",
            ciclo_giorni=1,
            data_inizio_programma=date(2026, 3, 1),
            data_fine_programma=date(2026, 3, 31),
            festivita=frozenset(),
        )
        # Domeniche di marzo 2026: 1, 8, 15, 22, 29
        assert out == [
            date(2026, 3, 1),
            date(2026, 3, 8),
            date(2026, 3, 15),
            date(2026, 3, 22),
            date(2026, 3, 29),
        ]

    def test_variante_PF_solo_prefestivi(self) -> None:
        # Sabati = prefestivo (vigilia di domenica).
        out = enumera_date_giornata(
            numero_giornata=1,
            variante_calendario="PF",
            ciclo_giorni=1,
            data_inizio_programma=date(2026, 3, 1),
            data_fine_programma=date(2026, 3, 14),
            festivita=_FEST_2026,
        )
        # Marzo 2026: sabati 7, 14 = prefestivo (vigilia di domenica 8, 15).
        # Anche venerdì potrebbe essere prefestivo se sabato è festivo,
        # ma in marzo 2026 nessuna festività.
        assert date(2026, 3, 7) in out
        assert date(2026, 3, 14) in out

    def test_variante_non_riconosciuta_sovra_include(self) -> None:
        """Fallback conservativo: testo qualsiasi → tutte le candidate."""
        out = enumera_date_giornata(
            numero_giornata=1,
            variante_calendario="LV 1:5 escl. 22/3",  # sintassi parlante non MVP
            ciclo_giorni=7,
            data_inizio_programma=date(2026, 3, 2),
            data_fine_programma=date(2026, 3, 16),
            festivita=frozenset(),
        )
        # Senza parser DSL completo, il fallback restituisce TUTTE le 3
        # candidate (lunedì 2/3, 9/3, 16/3) — sovra-include MVP.
        assert len(out) == 3


@pytest.mark.parametrize(
    "variante",
    ["lv", "Lv", "LV", "lavorativo", "LAVORATIVO", "Lavorativo"],
)
def test_variante_case_insensitive(variante: str) -> None:
    """La sintassi è case-insensitive (parser fa .upper())."""
    out = enumera_date_giornata(
        numero_giornata=1,
        variante_calendario=variante,
        ciclo_giorni=7,
        data_inizio_programma=date(2026, 3, 2),
        data_fine_programma=date(2026, 3, 9),
        festivita=_FEST_2026,
    )
    # 2 lunedì (2/3 e 9/3), entrambi lavorativi
    assert len(out) == 2
