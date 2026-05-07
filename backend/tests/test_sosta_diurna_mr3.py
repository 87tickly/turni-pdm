"""Test ``_minuti_diurni_sosta_intergiornata`` (entry 222 MR-3).

Helper puro Python: niente DB, niente fixture. Verifica i 4 casi
canonici della fascia notturna 22:00-06:00.
"""

from __future__ import annotations

from datetime import time

from colazione.domain.builder_giro.multi_giornata import (
    _minuti_diurni_sosta_intergiornata,
)


def test_sosta_pura_notte_22_06_diurno_zero() -> None:
    """Arrivo 22:00, partenza 06:00 → sosta 8h tutta notturna → 0 diurni."""
    assert (
        _minuti_diurni_sosta_intergiornata(time(22, 0), time(6, 0)) == 0
    )


def test_sosta_lunga_09_07_diurno_14h() -> None:
    """Arrivo 09:00, partenza 07:00 → 22h totali, di cui:
    - 09:00-22:00 = 13h diurne
    - 22:00-06:00 = 8h notturne
    - 06:00-07:00 = 1h diurna
    → 14h diurne = 840 min.
    """
    assert (
        _minuti_diurni_sosta_intergiornata(time(9, 0), time(7, 0)) == 840
    )


def test_sosta_serale_21_05_diurno_1h() -> None:
    """Arrivo 21:00, partenza 05:00 → 8h, di cui:
    - 21:00-22:00 = 1h diurna
    - 22:00-05:00 = 7h notturne
    → 60 min diurni.
    """
    assert (
        _minuti_diurni_sosta_intergiornata(time(21, 0), time(5, 0)) == 60
    )


def test_sosta_mista_18_08_diurno_8h() -> None:
    """Arrivo 18:00, partenza 08:00 → 14h, di cui:
    - 18:00-22:00 = 4h diurne
    - 22:00-06:00 = 8h notturne
    - 06:00-08:00 = 2h diurne
    → 6h diurne = 360 min.
    """
    assert (
        _minuti_diurni_sosta_intergiornata(time(18, 0), time(8, 0)) == 360
    )


def test_sosta_corta_arrivo_22_partenza_06_diurno_zero() -> None:
    """Edge case: arrivo esattamente 22:00 e partenza 06:00 = inizio
    e fine fascia notturna → diurno 0.
    """
    assert (
        _minuti_diurni_sosta_intergiornata(time(22, 0), time(6, 0)) == 0
    )


def test_sosta_diurna_pura_dopo_06_prima_22() -> None:
    """Arrivo 10:00, partenza 11:00 (giorno dopo) → 25h totali,
    notte 8h, diurno 17h = 1020 min. Caso "patologico" molto raro
    (giro che lascia il convoglio fermo per oltre 24h).
    """
    assert (
        _minuti_diurni_sosta_intergiornata(time(10, 0), time(11, 0))
        == 25 * 60 - 8 * 60
    )


def test_soglia_5h_decision_boundary() -> None:
    """Verifica che ``(arrivo, partenza)`` con 300 min diurni
    esattamente non sfori la soglia (vincolo MR-3 è ``> 300`` = strict).
    Es. 17:00 → 06:00 = 13h, di cui 5h diurne (17-22) + 8h notte
    + 0h diurne (parte K+1 finisce a 06:00). Diurno = 300 esatto.
    """
    assert (
        _minuti_diurni_sosta_intergiornata(time(17, 0), time(6, 0)) == 300
    )
