"""Calendario festività italiane (calcolato dinamicamente per qualsiasi anno).

Convenzione PdE Trenord: nei range "Circola dal X al Y" il treno circola
in tutti i giorni del periodo, **eccetto le festività italiane standard**
che sono auto-soppresse. Per circolare in una festività, il PdE deve
indicarla esplicitamente come "Circola DD/MM/YYYY" (override).

Festività italiane civili (D.P.R. 28 dicembre 1985, n. 792):
- Fisse: 1/1, 6/1, 25/4, 1/5, 2/6, 15/8, 1/11, 8/12, 25/12, 26/12
- Mobili: Pasqua e Lunedì dell'Angelo (Pasquetta), calcolate con
  l'algoritmo gaussiano-gregoriano.

Note:
- Il Patrono locale (es. Sant'Ambrogio a Milano il 7/12) NON è incluso:
  è una festività cittadina, non nazionale, e i treni regionali
  Trenord seguono il calendario nazionale.
- La Pasqua è calcolata via algoritmo "Computus" (Gauss). Verificato per
  2024-2030.
"""

from __future__ import annotations

from datetime import date, timedelta


def easter_sunday(year: int) -> date:
    """Data della Domenica di Pasqua per l'anno indicato (calendario gregoriano).

    Algoritmo "Computus" di Carl Friedrich Gauss (1800), valido dal 1583
    in poi senza correzioni. Verificato per 2024-2030.
    """
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    ll = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ll) // 451
    month = (h + ll - 7 * m + 114) // 31
    day = ((h + ll - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def italian_holidays(year: int) -> set[date]:
    """Insieme delle 12 festività civili italiane per l'anno indicato.

    Include:
    - 1 gennaio (Capodanno)
    - 6 gennaio (Epifania)
    - Domenica di Pasqua (mobile)
    - Lunedì dell'Angelo / Pasquetta (mobile)
    - 25 aprile (Festa della Liberazione)
    - 1 maggio (Festa del Lavoro)
    - 2 giugno (Festa della Repubblica)
    - 15 agosto (Ferragosto / Assunzione)
    - 1 novembre (Tutti i Santi / Ognissanti)
    - 8 dicembre (Immacolata Concezione)
    - 25 dicembre (Natale)
    - 26 dicembre (Santo Stefano)
    """
    pasqua = easter_sunday(year)
    pasquetta = pasqua + timedelta(days=1)
    return {
        date(year, 1, 1),
        date(year, 1, 6),
        pasqua,
        pasquetta,
        date(year, 4, 25),
        date(year, 5, 1),
        date(year, 6, 2),
        date(year, 8, 15),
        date(year, 11, 1),
        date(year, 12, 8),
        date(year, 12, 25),
        date(year, 12, 26),
    }


def italian_holidays_in_range(start: date, end: date) -> set[date]:
    """Tutte le festività italiane comprese in `[start, end]` (inclusivo)."""
    result: set[date] = set()
    for year in range(start.year, end.year + 1):
        for h in italian_holidays(year):
            if start <= h <= end:
                result.add(h)
    return result
