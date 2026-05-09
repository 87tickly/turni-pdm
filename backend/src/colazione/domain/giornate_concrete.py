"""Materializzazione di una giornata-tipo in date concrete — Sprint 8.2 MR-PD7b-1.

Risponde alla domanda: data una `TurnoPdcGiornata` (numero_giornata +
variante_calendario testuale) + il calendario del programma, **quali
date concrete** rappresenta?

Necessario per:
- Validazione §11.4 riposo settimanale (MR-PD7b-3) che richiede
  conteggio "giorni solari interi" dentro la finestra di riposo.
- Validazione cross-turno aggregata per persona (futura, MR-PD7+).
- Registro vetture cross-PdC con data_operativa concreta (MR-PD-FIX-SEVERO 3b
  S4 TODO, attualmente wild card MVP).

Scope MVP: parser sintassi LIMITATA per `validita_testo`. Le etichette
parlanti complesse Trenord ("LV 1:5", "F escluso FpF ed escl. 22/3,
12/4", ecc.) sono parziale; per testi non riconosciuti l'helper ritorna
**tutte le date candidate** (= sovra-include, conservativo).

Sintassi supportata MVP:
- ``""`` o ``"GG"`` o ``None``: tutte le date candidate (giornaliero).
- ``"LMXGV"`` o ``"LV"``: lavorativi (tipo_giorno_categoria=="lavorativo").
- ``"S"`` o ``"sabato"``: solo sabati (weekday==5).
- ``"D"`` o ``"domenica"``: solo domeniche (weekday==6).
- ``"F"`` o ``"festivo"``: solo festivi (tipo_giorno_categoria=="festivo").
- ``"PF"`` o ``"prefestivo"``: solo prefestivi.
- Qualsiasi altro testo: fallback **tutte le date candidate** + log warning.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from colazione.domain.calendario import tipo_giorno_categoria

logger = logging.getLogger(__name__)


def enumera_date_giornata(
    *,
    numero_giornata: int,
    variante_calendario: str | None,
    ciclo_giorni: int,
    data_inizio_programma: date,
    data_fine_programma: date,
    festivita: frozenset[date],
) -> list[date]:
    """Calcola le date concrete in cui la giornata-tipo si applica.

    Algoritmo:
    1. **Candidate del ciclo**: itera tutte le date del periodo
       ``[data_inizio, data_fine]``. Per ogni ``d``, calcola
       ``posizione_ciclo = ((d - data_inizio).days % ciclo_giorni) + 1``.
       Se ``posizione_ciclo == numero_giornata``: ``d`` è candidata.
    2. **Filtra per variante**: applica il filtro categoria/weekday in
       base a ``variante_calendario`` (vedi sintassi in module docstring).

    Args:
        numero_giornata: 1-based, posizione della giornata nel ciclo
            (1..ciclo_giorni).
        variante_calendario: testo `validita_testo` da `GiroVariante`.
            Sintassi MVP limitata; testi non riconosciuti → sovra-include.
        ciclo_giorni: durata totale del ciclo turno (es. 5, 7, 14).
        data_inizio_programma: prima data del periodo di programmazione
            (inclusa). Usata come "ancoraggio" del ciclo (giornata 1).
        data_fine_programma: ultima data del periodo (inclusa).
        festivita: set delle date festive nazionali + locali rilevanti
            per gli anni coperti dal periodo. Per costruirlo usare
            ``calendario.festivita_italiane(anno)`` + festività azienda.

    Returns:
        Lista ordinata cronologicamente delle date concrete in cui la
        giornata-tipo + variante si applica. Vuota se nessuna data
        candidata o filtro categoria nessuna match.

    Esempi:

        Periodo 2026-03-01..2026-03-31, ciclo 7gg, giornata 1 lavorativo
        ("LMXGV") → tutti i lunedì non festivi di marzo:

        >>> from datetime import date
        >>> dates = enumera_date_giornata(
        ...     numero_giornata=1,
        ...     variante_calendario="LMXGV",
        ...     ciclo_giorni=7,
        ...     data_inizio_programma=date(2026, 3, 2),  # 2026-03-02 = lunedì
        ...     data_fine_programma=date(2026, 3, 31),
        ...     festivita=frozenset(),
        ... )
        >>> [d.strftime("%a %d/%m") for d in dates]
        ['Mon 02/03', 'Mon 09/03', 'Mon 16/03', 'Mon 23/03', 'Mon 30/03']
    """
    if numero_giornata < 1 or numero_giornata > ciclo_giorni:
        logger.warning(
            "enumera_date_giornata: numero_giornata=%d fuori range "
            "[1..%d], ritorno lista vuota",
            numero_giornata,
            ciclo_giorni,
        )
        return []
    if data_inizio_programma > data_fine_programma:
        return []

    # 1. Candidate del ciclo
    candidate: list[date] = []
    cur = data_inizio_programma
    while cur <= data_fine_programma:
        offset_days = (cur - data_inizio_programma).days
        posizione = (offset_days % ciclo_giorni) + 1
        if posizione == numero_giornata:
            candidate.append(cur)
        cur += timedelta(days=1)

    # 2. Filtro variante
    return _filtra_per_variante(candidate, variante_calendario, festivita)


def _filtra_per_variante(
    candidate: list[date],
    variante: str | None,
    festivita: frozenset[date],
) -> list[date]:
    """Applica il filtro categoria/weekday in base alla variante.

    Sintassi MVP: vedi module docstring. Fallback per testi non
    riconosciuti = tutte le candidate (sovra-include conservativo).
    """
    if variante is None:
        return candidate
    v = variante.strip().upper()
    if v in ("", "GG"):
        return candidate

    # Match esplicito su sintassi MVP
    if v in ("LMXGV", "LV", "LAVORATIVO"):
        return [d for d in candidate if tipo_giorno_categoria(d, festivita) == "lavorativo"]
    if v in ("S", "SABATO"):
        return [d for d in candidate if d.weekday() == 5]
    if v in ("D", "DOMENICA"):
        return [d for d in candidate if d.weekday() == 6]
    if v in ("F", "FESTIVO"):
        return [d for d in candidate if tipo_giorno_categoria(d, festivita) == "festivo"]
    if v in ("PF", "PREFESTIVO"):
        return [d for d in candidate if tipo_giorno_categoria(d, festivita) == "prefestivo"]

    # Fallback: testo non riconosciuto, sovra-include
    logger.info(
        "enumera_date_giornata: variante '%s' non riconosciuta dal "
        "parser MVP, fallback sovra-include (tutte le %d candidate)",
        variante,
        len(candidate),
    )
    return candidate


__all__ = ["enumera_date_giornata"]
