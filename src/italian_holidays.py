"""
Calendario festivita' italiane.

Usato dai turni PdC per interpretare la periodicita' `D`:
- `D` significa Domenica OPPURE festivo infrasettimanale
- Il calendario nazionale italiano va applicato anche ai giorni feriali
  che cadono in data festiva (es. 25 aprile su un martedi' e' `D`)

Patroni locali disponibili ma OPZIONALI per impianto:
- la configurazione attiva puo' scegliere se il patrono del capoluogo
  va trattato come `D` o no (Trenord applica caso per caso).

Modulo isolato: nessun import dal resto del progetto, e' un utility puro.

Funzioni pubbliche:
- easter_sunday(year) -> date          algoritmo di Gauss / Computus
- italian_national_holidays(year)      set di tutte le feste nazionali
- is_italian_holiday(d, local=None)    True se festivo nazionale (o patrono)
- weekday_for_periodicity(d, local=None)  ritorna L|M|X|G|V|S|D (D se festivo)
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Iterable, Optional


# ── Lettere periodicita' per indice weekday (lunedi=0, domenica=6) ──
# Corrispondono al codice usato nei turni PdC: LMXGVSD
WEEKDAY_LETTERS: tuple[str, ...] = ("L", "M", "X", "G", "V", "S", "D")


# ── Festivita' fisse: (mese, giorno, nome) ──
FIXED_HOLIDAYS: tuple[tuple[int, int, str], ...] = (
    (1, 1, "Capodanno"),
    (1, 6, "Epifania"),
    (4, 25, "Liberazione"),
    (5, 1, "Festa del Lavoro"),
    (6, 2, "Festa della Repubblica"),
    (8, 15, "Ferragosto"),
    (11, 1, "Tutti i Santi"),
    (12, 8, "Immacolata Concezione"),
    (12, 25, "Natale"),
    (12, 26, "Santo Stefano"),
)


# ── Patroni locali delle principali citta' italiane ──
# Chiave: sigla lowercase della citta'; valore: (mese, giorno, nome)
# Fonte: tradizione civica italiana; la prassi aziendale Trenord puo'
# trattare diversamente — include solo se richiesto esplicitamente.
LOCAL_PATRONS: dict[str, tuple[int, int, str]] = {
    "milano":   (12,  7, "Sant'Ambrogio"),
    "torino":   (6,  24, "San Giovanni Battista"),
    "roma":     (6,  29, "Santi Pietro e Paolo"),
    "napoli":   (9,  19, "San Gennaro"),
    "venezia":  (4,  25, "San Marco"),         # coincide con Liberazione
    "firenze":  (6,  24, "San Giovanni Battista"),
    "bologna":  (10,  4, "San Petronio"),
    "palermo":  (7,  15, "Santa Rosalia"),
    "bari":     (12,  6, "San Nicola"),
    "genova":   (6,  24, "San Giovanni Battista"),
    "verona":   (5,  21, "San Zeno"),
    "trieste":  (11,  3, "San Giusto"),
    "cagliari": (10, 30, "San Saturnino"),
    "catania":  (2,   5, "Sant'Agata"),
}


# ------------------------------------------------------------------
# Pasqua (algoritmo di Gauss / Computus — forma anonima)
# ------------------------------------------------------------------

def easter_sunday(year: int) -> date:
    """Ritorna la domenica di Pasqua per l'anno dato (calendario gregoriano).

    Implementa il "Computus" nella forma anonima (Meeus / Jones / Butcher).
    Valido per gli anni 1583..4099.
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


def easter_monday(year: int) -> date:
    """Lunedi' dell'Angelo (Pasquetta) = Pasqua + 1 giorno."""
    easter = easter_sunday(year)
    return date.fromordinal(easter.toordinal() + 1)


# ------------------------------------------------------------------
# Feste nazionali dell'anno (cached per anno)
# ------------------------------------------------------------------

@lru_cache(maxsize=64)
def italian_national_holidays(year: int) -> frozenset[date]:
    """Set di TUTTE le festivita' nazionali italiane per l'anno dato.

    Include: 10 feste fisse + Pasqua + Pasquetta.
    Cached via lru_cache: chiamate successive allo stesso anno sono O(1).
    """
    out: set[date] = set()
    for month, day, _name in FIXED_HOLIDAYS:
        out.add(date(year, month, day))
    out.add(easter_sunday(year))
    out.add(easter_monday(year))
    return frozenset(out)


@lru_cache(maxsize=256)
def _local_patron_holidays(year: int, local: str) -> frozenset[date]:
    """Set di festivita' aggiuntive dovute al patrono locale della citta'."""
    key = local.strip().lower()
    if key not in LOCAL_PATRONS:
        return frozenset()
    month, day, _name = LOCAL_PATRONS[key]
    try:
        return frozenset({date(year, month, day)})
    except ValueError:
        # data invalida (es. 29/2 in anni non bisestili)
        return frozenset()


def italian_holidays(year: int,
                     include_local: Optional[str] = None) -> frozenset[date]:
    """Nazionali + eventuale patrono locale, per l'anno dato."""
    base = italian_national_holidays(year)
    if include_local:
        return base | _local_patron_holidays(year, include_local)
    return base


# ------------------------------------------------------------------
# Check puntuale
# ------------------------------------------------------------------

def is_italian_holiday(d: date, include_local: Optional[str] = None) -> bool:
    """True se `d` e' festivo nazionale italiano (o patrono locale se richiesto).

    Le domeniche NON sono considerate festivo da questa funzione — e'
    responsabilita' di `weekday_for_periodicity` trattarle come `D`.
    """
    return d in italian_holidays(d.year, include_local)


# ------------------------------------------------------------------
# Weekday -> lettera periodicita' PdC
# ------------------------------------------------------------------

def weekday_for_periodicity(d: date,
                            include_local: Optional[str] = None) -> str:
    """Lettera periodicita' del turno PdC per la data `d`.

    Regola:
    - Domenica          -> 'D'
    - Festivo infrasett.-> 'D' (anche se cade di sabato o feriale)
    - Sabato            -> 'S'
    - Venerdi'          -> 'V'
    - Giovedi'          -> 'G'
    - Mercoledi'        -> 'X'
    - Martedi'          -> 'M'
    - Lunedi'           -> 'L'

    Un festivo che cade di domenica resta 'D' (nessun conflitto).
    """
    if is_italian_holiday(d, include_local):
        return "D"
    return WEEKDAY_LETTERS[d.weekday()]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def matches_periodicity(d: date, periodicita: str,
                        include_local: Optional[str] = None) -> bool:
    """True se la variante con codice `periodicita` (es. 'LMXGVSD', 'D', 'SD')
    si applica alla data `d`.

    Match: la lettera calcolata per la data e' contenuta in `periodicita`.
    Esempio: `D` matcha 'D', 'SD', 'LMXGVSD'; non matcha 'LMXGV' o 'LMXGVS'.
    """
    letter = weekday_for_periodicity(d, include_local)
    return letter in periodicita.upper()


def upcoming_holidays(start: date, end: date,
                      include_local: Optional[str] = None) -> list[date]:
    """Elenco ordinato delle festivita' nell'intervallo [start, end]."""
    out: set[date] = set()
    for year in range(start.year, end.year + 1):
        out.update(italian_holidays(year, include_local))
    return sorted(d for d in out if start <= d <= end)
