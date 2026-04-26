"""Catena single-day greedy chain (Sprint 4.4.1).

Funzione **pura** che, data una lista di corse di un giorno-tipo +
parametri, produce catene massimali di corse incatenate per:

- continuità geografica (arrivo[i] = partenza[i+1])
- gap minimo tra arrivo precedente e partenza successiva (default 5')

Spec: ``docs/LOGICA-COSTRUZIONE.md`` §3.2 (greedy chain in
``costruisci_giri_da_localita``).

Limiti del sub-sprint 4.4.1 (per restare focalizzati):

- **single-day**: una catena chiude al primo blocco che attraversa la
  mezzanotte (``ora_arrivo < ora_partenza``). La concatenazione
  cross-notte è in Sprint 4.4.3.
- **senza località manutenzione**: niente blocchi ``materiale_vuoto``
  di apertura/chiusura. Quelli sono in Sprint 4.4.2.
- **senza assegnazione regole**: niente verifica composizione/materiale.
  Quella è in Sprint 4.4.4.
- **gap unico**: un solo ``gap_min`` indipendente dal tipo stazione.
  La spec §3.3 differenzia 5' capolinea / 15' intermedia / 20' deposito
  ma servirebbero metadati sulla stazione (capolinea sì/no) che oggi
  non abbiamo. Raffinamento futuro.

Il modulo è **DB-agnostic**: accetta qualunque oggetto col duck-typing
giusto (Protocol ``_CorsaLike``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import time
from typing import Any, Protocol

# =====================================================================
# Protocol — duck-typing dell'input
# =====================================================================


class _CorsaLike(Protocol):
    """Una corsa: ORM ``CorsaCommerciale`` o dataclass test."""

    codice_origine: str
    codice_destinazione: str
    ora_partenza: time
    ora_arrivo: time


# =====================================================================
# Parametri + Output
# =====================================================================


@dataclass(frozen=True)
class ParamCatena:
    """Parametri per la costruzione delle catene.

    Attributi:
        gap_min: minuti minimi tra ``ora_arrivo`` di una corsa e
            ``ora_partenza`` della successiva. Default 5'.
    """

    gap_min: int = 5


# Singleton condivisibile (frozen → safe come default arg).
_DEFAULT_PARAM = ParamCatena()


@dataclass(frozen=True)
class Catena:
    """Catena ordinata di corse contigue.

    Garantisce per ogni coppia consecutiva ``(a, b)``:

    - ``a.codice_destinazione == b.codice_origine``
    - ``minuti(b.ora_partenza) >= minuti(a.ora_arrivo) + gap_min``

    Una catena è single-day: se l'ultima corsa attraversa la mezzanotte
    (``ora_arrivo < ora_partenza``), la catena si chiude lì. La
    concatenazione cross-notte è in Sprint 4.4.3.
    """

    corse: tuple[Any, ...]


# =====================================================================
# Helpers interni
# =====================================================================


def _time_to_min(t: time) -> int:
    """``time`` → minuti dall'inizio giornata (0..1439)."""
    return t.hour * 60 + t.minute


def _attraversa_mezzanotte(corsa: _CorsaLike) -> bool:
    """``True`` se la corsa termina dopo la mezzanotte (arrivo < partenza)."""
    return corsa.ora_arrivo < corsa.ora_partenza


def _trova_prossima(
    pool: Sequence[_CorsaLike],
    visitate: set[int],
    ultima: _CorsaLike,
    gap_min: int,
) -> _CorsaLike | None:
    """Heuristic greedy: la corsa libera col matching geografico + gap che
    parte prima.

    A parità di ``ora_partenza`` vince la prima incontrata nel ``pool``,
    che è già ordinato → output deterministico.
    """
    soglia_min = _time_to_min(ultima.ora_arrivo) + gap_min

    miglior: _CorsaLike | None = None
    miglior_partenza_min: int | None = None

    for c in pool:
        if id(c) in visitate:
            continue
        if c.codice_origine != ultima.codice_destinazione:
            continue
        partenza_min = _time_to_min(c.ora_partenza)
        if partenza_min < soglia_min:
            continue
        if miglior_partenza_min is None or partenza_min < miglior_partenza_min:
            miglior = c
            miglior_partenza_min = partenza_min

    return miglior


# =====================================================================
# Algoritmo top-level
# =====================================================================


def costruisci_catene(
    corse: Sequence[_CorsaLike],
    params: ParamCatena = _DEFAULT_PARAM,
) -> list[Catena]:
    """Costruisce catene massimali greedy a partire dalla lista corse.

    Algoritmo (vedi ``LOGICA-COSTRUZIONE.md`` §3.2):

    1. Ordina le corse per ``ora_partenza``.
    2. Greedy: prende la prima corsa libera, la usa come testa di una
       nuova catena.
    3. Estende: cerca la prima corsa libera con
       ``codice_origine == ultima.codice_destinazione`` e
       ``ora_partenza >= ultima.ora_arrivo + gap_min``. Se trovata,
       la aggiunge alla catena e ripete.
    4. Chiude la catena se: (a) nessuna successione possibile,
       (b) l'ultima corsa attraversa la mezzanotte.
    5. Ricomincia con la successiva corsa libera, finché il pool è
       esaurito.

    Args:
        corse: lista di corse single-day, tipicamente già filtrata per
            giorno-tipo (es. tutte le corse feriali) e per tipo
            materiale (compatibilità dello stesso convoglio).
        params: ``ParamCatena`` con i parametri (default gap_min=5').

    Returns:
        Lista di ``Catena``. Ogni corsa appare in **esattamente una**
        catena. L'ordine delle catene segue l'ora di partenza della
        prima corsa.

    Esempi:
        Lista vuota → nessuna catena:

        >>> costruisci_catene([])
        []

        Una sola corsa → una catena di un blocco:

        >>> from dataclasses import dataclass
        >>> @dataclass
        ... class C:
        ...     codice_origine: str
        ...     codice_destinazione: str
        ...     ora_partenza: time
        ...     ora_arrivo: time
        >>> c = C("MI", "BG", time(8, 0), time(9, 0))
        >>> [len(cc.corse) for cc in costruisci_catene([c])]
        [1]
    """
    if not corse:
        return []

    pool_ordinato = sorted(corse, key=lambda c: _time_to_min(c.ora_partenza))
    visitate: set[int] = set()
    catene: list[Catena] = []

    for prima in pool_ordinato:
        if id(prima) in visitate:
            continue

        blocchi: list[_CorsaLike] = [prima]
        visitate.add(id(prima))

        while True:
            ultima = blocchi[-1]
            if _attraversa_mezzanotte(ultima):
                # Chiusura forzata: oltre mezzanotte con `time` puro
                # non si ragiona. Multi-giornata in Sprint 4.4.3.
                break

            prossima = _trova_prossima(pool_ordinato, visitate, ultima, params.gap_min)
            if prossima is None:
                break

            blocchi.append(prossima)
            visitate.add(id(prossima))

        catene.append(Catena(corse=tuple(blocchi)))

    return catene
