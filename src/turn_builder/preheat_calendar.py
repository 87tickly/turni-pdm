"""
Calendario preriscaldo — periodo in cui il simbolo `●NUMERO` del PDF
turno materiale si traduce in ACCp maggiorato (80 min invece dei 40
standard).

Richiesta utente (23/04/2026): il preriscaldo rinforzato si applica solo
nel periodo invernale, **da 1 dicembre a fine febbraio incluso**. Fuori
da questo periodo, un treno marcato `●` si tratta come una condotta
normale (ACCp = 40 min).

Modulo isolato, zero dipendenze dal resto del progetto. Usato dal modulo
`accessori.py` (Step 4) quando calcola i valori ACCp per ogni segmento.
"""
from __future__ import annotations

from datetime import date


# Mesi in cui il preriscaldo rinforzato e' attivo (dic, gen, feb).
PREHEAT_MONTHS: frozenset[int] = frozenset({12, 1, 2})


def is_preheat_period(d: date) -> bool:
    """True se la data cade nel periodo di preriscaldo rinforzato
    (dic-feb). False altrimenti.

    Bordi inclusi: 1 dicembre ritorna True, 30 novembre False;
    28/29 febbraio True, 1 marzo False.
    """
    return d.month in PREHEAT_MONTHS


def preheat_period_label(d: date) -> str:
    """Etichetta leggibile dello stato preriscaldo per una data.
    Utile in UI / log. Ritorna 'INVERNO' o 'ESTATE'."""
    return "INVERNO" if is_preheat_period(d) else "ESTATE"
