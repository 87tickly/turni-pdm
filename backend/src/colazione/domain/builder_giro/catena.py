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
        gap_max: minuti MASSIMI tra ``ora_arrivo`` di una corsa e
            ``ora_partenza`` della successiva. Sopra questa soglia la
            catena si chiude (= il convoglio non resta fermo in
            stazione, fa altri servizi o rientra in deposito). Default
            360' (6h), decisione utente Sprint 7.9 entry 112: in giorno
            feriale una sosta intermedia > 6h non è realistica.
            Pre-entry 112 il valore era effettivo "infinito" (niente
            check), che produceva catene con sosta 12h+ a stazioni
            intermedie tipo Voghera.
        area_per_stazione: Sprint 8.0 MR-E (entry 236) — mapping
            ``stazione_codice → area_metropolitana_id``. Quando
            presente, il check di continuità geografica accetta una
            corsa successiva la cui ``codice_origine`` appartiene alla
            STESSA area della ``codice_destinazione`` della precedente
            (es. MI.Centrale → MI.Garibaldi entrambe in area "milano").
            La concatenazione richiede comunque il check temporale
            ``gap_min/gap_max``. Default ``None`` = solo continuità
            stretta. Decisione utente entry 234: risolvere problema
            turni mono-corsa per Milano multi-stazione.
    """

    gap_min: int = 5
    # Sprint 8.0 MR-3 (entry 222): da 360 (6h) a 300 (5h). Decisione
    # utente 2026-05-07 entry 222: "almeno che non ci siano soste
    # notturne, non voglio vedere soste superiori alle 5 ore,
    # soprattutto nei giorni feriali e nelle ore diurne". Le catene
    # intra-giornata sono per definizione diurne (cross-notte è in
    # multi-giornata), quindi 5h è il massimo qui. Le soste notturne
    # tra giornate restano libere via il check
    # ``minuti_diurni_sosta_intergiornata`` in ``multi_giornata.py``.
    gap_max: int = 300
    # Sprint 8.0 MR-E entry 236: mappa stazione → area metropolitana.
    # Non è dict[str, int | None]: usiamo dict[str, int] e l'assenza
    # di una chiave significa "non in nessuna area".
    area_per_stazione: dict[str, int] | None = None


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


def _stazioni_intra_area(
    a: str,
    b: str,
    area_per_stazione: dict[str, int] | None,
) -> bool:
    """Sprint 8.0 MR-E (entry 236): ``True`` se ``a`` e ``b`` sono in
    una stessa area metropolitana (es. MI.Centrale e MI.Garibaldi).

    Se ``area_per_stazione`` è ``None`` o una delle 2 stazioni non è in
    alcuna area → ``False`` (= no rilassamento, serve match esatto).
    """
    if area_per_stazione is None:
        return False
    area_a = area_per_stazione.get(a)
    area_b = area_per_stazione.get(b)
    if area_a is None or area_b is None:
        return False
    return area_a == area_b


def _trova_prossima(
    pool: Sequence[_CorsaLike],
    visitate: set[int],
    ultima: _CorsaLike,
    gap_min: int,
    gap_max: int,
    area_per_stazione: dict[str, int] | None = None,
) -> _CorsaLike | None:
    """Heuristic greedy: la corsa libera col matching geografico + gap che
    parte prima, dentro la finestra ``[gap_min, gap_max]``.

    A parità di ``ora_partenza`` vince la prima incontrata nel ``pool``,
    che è già ordinato → output deterministico.

    Sprint 8.0 MR-E (entry 236): con ``area_per_stazione`` non-None, il
    matching geografico accetta anche corse la cui ``codice_origine``
    è in una **stessa area metropolitana** della
    ``codice_destinazione`` di ``ultima``. A parità tra match esatto e
    match-area, vince il match esatto (più stretto).
    """
    arrivo_min = _time_to_min(ultima.ora_arrivo)
    soglia_min = arrivo_min + gap_min
    soglia_max = arrivo_min + gap_max
    arrivo_codice = ultima.codice_destinazione

    miglior: _CorsaLike | None = None
    miglior_partenza_min: int | None = None
    miglior_match_esatto = False

    for c in pool:
        if id(c) in visitate:
            continue
        is_match_esatto = c.codice_origine == arrivo_codice
        is_match_area = (
            not is_match_esatto
            and _stazioni_intra_area(arrivo_codice, c.codice_origine, area_per_stazione)
        )
        if not is_match_esatto and not is_match_area:
            continue
        partenza_min = _time_to_min(c.ora_partenza)
        if partenza_min < soglia_min:
            continue
        if partenza_min > soglia_max:
            continue
        # Tie-break: match esatto vince su match-area a parità di
        # partenza. Match-area accettato solo se nessun match esatto
        # con ora_partenza ≤.
        if miglior_partenza_min is None:
            miglior = c
            miglior_partenza_min = partenza_min
            miglior_match_esatto = is_match_esatto
            continue
        # Strettamente prima → vince comunque.
        if partenza_min < miglior_partenza_min:
            miglior = c
            miglior_partenza_min = partenza_min
            miglior_match_esatto = is_match_esatto
            continue
        # Stessa partenza_min: preferisci match esatto se attuale è area.
        if (
            partenza_min == miglior_partenza_min
            and is_match_esatto
            and not miglior_match_esatto
        ):
            miglior = c
            miglior_match_esatto = True

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

            prossima = _trova_prossima(
                pool_ordinato,
                visitate,
                ultima,
                params.gap_min,
                params.gap_max,
                params.area_per_stazione,
            )
            if prossima is None:
                break

            blocchi.append(prossima)
            visitate.add(id(prossima))

        catene.append(Catena(corse=tuple(blocchi)))

    return catene
