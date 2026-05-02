"""Test puri Sprint 7.7 MR 2 — `domain/calendario.py`.

Verifica:

- Pasqua gregoriana per anni noti (2025-2030 e cross-check 1995/2025).
- Pasquetta = Pasqua + 1.
- Festività italiane fisse (10 voci, ordinate).
- ``festivita_italiane`` include fisse + Pasqua + Pasquetta (12 voci).
- ``tipo_giorno`` classifica feriale/sabato/domenica/festivo con
  precedenza festivo su weekend.
"""

from __future__ import annotations

from datetime import date

from colazione.domain.calendario import (
    festivita_italiane,
    festivita_italiane_fisse,
    pasqua_gregoriana,
    pasquetta,
    tipo_giorno,
)


class TestPasquaGregoriana:
    """Date noti della Pasqua gregoriana (verificate astronomicamente)."""

    def test_2024(self) -> None:
        assert pasqua_gregoriana(2024) == date(2024, 3, 31)

    def test_2025(self) -> None:
        assert pasqua_gregoriana(2025) == date(2025, 4, 20)

    def test_2026(self) -> None:
        assert pasqua_gregoriana(2026) == date(2026, 4, 5)

    def test_2027(self) -> None:
        assert pasqua_gregoriana(2027) == date(2027, 3, 28)

    def test_2030(self) -> None:
        assert pasqua_gregoriana(2030) == date(2030, 4, 21)

    def test_anno_lontano_xx_secolo(self) -> None:
        # Riferimento: Pasqua 1995 = 16 aprile
        assert pasqua_gregoriana(1995) == date(1995, 4, 16)


def test_pasquetta_e_pasqua_piu_uno() -> None:
    assert pasquetta(2026) == date(2026, 4, 6)
    assert pasquetta(2027) == date(2027, 3, 29)


def test_festivita_fisse_ordinate_e_complete() -> None:
    fisse = festivita_italiane_fisse(2026)
    assert len(fisse) == 10
    # Ordinate cronologicamente
    date_only = [d for d, _ in fisse]
    assert date_only == sorted(date_only)
    # Capodanno e Santo Stefano agli estremi
    assert fisse[0] == (date(2026, 1, 1), "Capodanno")
    assert fisse[-1] == (date(2026, 12, 26), "Santo Stefano")


def test_festivita_italiane_include_pasqua_e_pasquetta() -> None:
    tutte = festivita_italiane(2026)
    assert len(tutte) == 12  # 10 fisse + Pasqua + Pasquetta
    nomi = {n for _, n in tutte}
    assert "Pasqua" in nomi
    assert "Lunedì dell'Angelo" in nomi
    # Ordine cronologico
    date_only = [d for d, _ in tutte]
    assert date_only == sorted(date_only)


class TestTipoGiorno:
    """`tipo_giorno` classifica feriale/sabato/domenica/festivo."""

    def test_feriale_lunedi_qualsiasi(self) -> None:
        assert tipo_giorno(date(2026, 5, 4), frozenset()) == "feriale"  # lunedì

    def test_sabato_no_festivo(self) -> None:
        assert tipo_giorno(date(2026, 5, 2), frozenset()) == "sabato"

    def test_domenica_no_festivo(self) -> None:
        assert tipo_giorno(date(2026, 5, 3), frozenset()) == "domenica"

    def test_festivo_in_settimana(self) -> None:
        # 1° maggio 2026 = venerdì + Festa del Lavoro → festivo
        festivita = frozenset({date(2026, 5, 1)})
        assert tipo_giorno(date(2026, 5, 1), festivita) == "festivo"

    def test_festivo_di_sabato_vince_su_sabato(self) -> None:
        # 25 aprile 2026 = sabato + Liberazione → festivo (precedenza)
        festivita = frozenset({date(2026, 4, 25)})
        assert tipo_giorno(date(2026, 4, 25), festivita) == "festivo"

    def test_festivo_di_domenica_vince_su_domenica(self) -> None:
        # 5 aprile 2026 = domenica + Pasqua → festivo
        festivita = frozenset({date(2026, 4, 5)})
        assert tipo_giorno(date(2026, 4, 5), festivita) == "festivo"
