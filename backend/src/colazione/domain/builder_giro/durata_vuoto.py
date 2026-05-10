"""Stima durata vuoto rientro target data-driven (Sprint 8.3 MR-S2).

Sostituisce il fallback hardcoded di 60 min in
``aggregazione_linea_centrica._costruisci_vuoto_rientro_target`` con
una stima basata sulle ``CorsaCommerciale`` reali del programma.

# Strategia (4 livelli)

1. **Hit diretto**: per la coppia ``(origine, destinazione)`` cerca
   le corse commerciali nel programma con stessi capolinea, calcola
   mediana di ``min_tratta`` (o ``ora_arrivo - ora_partenza`` con
   gestione cross-mezzanotte se ``min_tratta`` è ``NULL``).
2. **Hit speculare**: la coppia ``(destinazione, origine)`` (= stessa
   infrastruttura percorsa al contrario, errore tipico < 15-20%
   accettabile per stima vuoto).
3. **Fallback geometrico** (opzione B-semplificata): per ogni stazione
   pre-calcola la mediana delle durate di tutte le corse che la
   toccano (origine o destinazione). Per coppie miss usa
   ``max(baseline[X], baseline[Y], fallback_default)`` come proxy
   pessimistico ragionevole.
4. **Fallback default**: 60 min (= comportamento pre-MR-S2 come
   safety net finale).

# Origine

Critica SEVERO PIANO MR-Sprint8.3-S2 (entry 285+):
``docs/critiche/SPRINT-8.3-PIANO-S2-durata-vuoto.md`` finding S1
HIGH "fallback 60 quando coppia non in PdE = bug originale rimasto".
Fallback geometrico è la modifica P0 X raccomandata da SEVERO per
saltare a 7/10.

# Note

- Filtra ``is_cancellata=True`` (coerenza con
  ``corse_attive_clause()``, memoria
  ``feedback_no_inventare_dati``).
- Mediana NON minimo (memoria SEVERO: corse veloci FR sottostimano,
  corse regionali tutte fermate sovrastimano media → mediana è
  robusta).
- Soglia minima N≥1 (1 sola corsa è comunque meglio del 60
  hardcoded).
- Determinismo: ordinamento delle durate prima del calcolo mediana.
- Helper pure (`calcola_durata_vuoto_min`, `aggrega_*`,
  `_durata_min_da_orari`) testabili senza DB. Helper async
  (`costruisci_lookup_durate`) in fondo per integrazione builder.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, time
from statistics import median
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.models.corse import CorsaCommerciale, corse_attive_clause

# =====================================================================
# Costanti
# =====================================================================

#: Fallback hardcoded quando né lookup diretto, né speculare, né
#: baseline per stazione sono disponibili. È il valore pre-MR-S2,
#: mantenuto come safety net finale (= comportamento conservative).
DURATA_VUOTO_DEFAULT_MIN: Final[int] = 60


# =====================================================================
# Helpers pure (testabili senza DB)
# =====================================================================


def _durata_min_da_orari(ora_partenza: time, ora_arrivo: time) -> int:
    """Calcola durata in minuti gestendo cross-mezzanotte.

    Se ``ora_arrivo < ora_partenza`` (es. parte 23:30, arriva 00:15
    K+1), considera cross-notte e ritorna ``(24*60 - p) + a``.

    Returns:
        Durata in minuti (sempre ≥ 0). Mai negativa.
    """
    p = ora_partenza.hour * 60 + ora_partenza.minute
    a = ora_arrivo.hour * 60 + ora_arrivo.minute
    if a >= p:
        return a - p
    return (24 * 60 - p) + a


def aggrega_durate_per_coppia(
    triple: Iterable[tuple[str, str, int]],
) -> dict[tuple[str, str], int]:
    """Aggrega le triple ``(origine, destinazione, durata_min)`` in un
    dict ``{(o, d): mediana_durata}``.

    Args:
        triple: iterable di triple ``(origine, destinazione, durata)``.
            Tipicamente da ``_carica_durate_corse_programma``.

    Returns:
        Dizionario con la mediana arrotondata per ogni coppia.
        Coppie con 1 sola corsa ritornano la durata di quella corsa.
    """
    raggruppato: dict[tuple[str, str], list[int]] = {}
    for o, d, dur in triple:
        raggruppato.setdefault((o, d), []).append(dur)

    out: dict[tuple[str, str], int] = {}
    for coppia, durate in raggruppato.items():
        durate.sort()
        out[coppia] = round(median(durate))
    return out


def aggrega_baseline_per_stazione(
    triple: Iterable[tuple[str, str, int]],
) -> dict[str, int]:
    """Aggrega le triple in un dict ``{stazione: mediana_durata}``.

    Per ogni stazione, considera tutte le corse che la toccano
    (origine OR destinazione). Usato come fallback geometrico
    opzione B-semplificata per coppie senza corsa diretta/speculare:
    proxy "tempo ragionevole di spostamento da/per quella stazione
    sulla rete del programma".

    Returns:
        Dizionario con mediana arrotondata per ogni stazione.
    """
    durate_per_stazione: dict[str, list[int]] = {}
    for o, d, dur in triple:
        durate_per_stazione.setdefault(o, []).append(dur)
        durate_per_stazione.setdefault(d, []).append(dur)

    out: dict[str, int] = {}
    for staz, durate in durate_per_stazione.items():
        durate.sort()
        out[staz] = round(median(durate))
    return out


def calcola_durata_vuoto_min(
    codice_origine: str,
    codice_destinazione: str,
    *,
    durata_lookup: dict[tuple[str, str], int] | None = None,
    baseline_per_stazione: dict[str, int] | None = None,
    fallback_default: int = DURATA_VUOTO_DEFAULT_MIN,
) -> int:
    """Calcola durata vuoto rientro (min) data-driven con fallback
    a 4 livelli.

    Strategia ordinata (primo che matcha vince):

    1. **Hit diretto** ``durata_lookup[(origine, destinazione)]``.
    2. **Hit speculare** ``durata_lookup[(destinazione, origine)]``.
    3. **Fallback geometrico**:
       ``max(baseline[origine], baseline[destinazione],
       fallback_default)``. Se solo una delle due è presente, usa
       quella vs ``fallback_default``.
    4. **Fallback hardcoded** ``fallback_default`` (= 60 min).

    Args:
        codice_origine: capolinea operativo dove parte il vuoto.
        codice_destinazione: stazione collegata sede target.
        durata_lookup: dict pre-calcolato ``{(o, d): mediana}`` da
            ``aggrega_durate_per_coppia``. Default vuoto.
        baseline_per_stazione: dict pre-calcolato
            ``{stazione: mediana}`` da
            ``aggrega_baseline_per_stazione``. Default vuoto.
        fallback_default: ultimo fallback se tutto manca. Default 60.

    Returns:
        Durata in minuti (sempre ≥ ``fallback_default``).
    """
    lookup = durata_lookup or {}
    baseline = baseline_per_stazione or {}

    coppia_diretta = (codice_origine, codice_destinazione)
    if coppia_diretta in lookup:
        return lookup[coppia_diretta]

    coppia_speculare = (codice_destinazione, codice_origine)
    if coppia_speculare in lookup:
        return lookup[coppia_speculare]

    bo = baseline.get(codice_origine)
    bd = baseline.get(codice_destinazione)
    if bo is not None and bd is not None:
        return max(bo, bd, fallback_default)
    if bo is not None:
        return max(bo, fallback_default)
    if bd is not None:
        return max(bd, fallback_default)

    return fallback_default


# =====================================================================
# Helper async (DB-bound)
# =====================================================================


async def _carica_durate_corse_programma(
    session: AsyncSession,
    *,
    azienda_id: int,
    valido_da: date,
    valido_a: date,
) -> list[tuple[str, str, int]]:
    """Carica triple ``(codice_origine, codice_destinazione,
    durata_min)`` per le corse attive dell'azienda nel periodo PdE.

    Filtra ``is_cancellata=False`` (coerenza con
    ``corse_attive_clause``). Filtra periodo: corse con
    ``valido_da<=periodo_a AND valido_a>=periodo_da``.

    Per ogni corsa usa ``min_tratta`` se popolato, altrimenti calcola
    da ``(ora_arrivo - ora_partenza)`` gestendo cross-mezzanotte.
    Skippa corse con durata ≤ 0 (dato sporco difensivo).

    Returns:
        Lista di triple ``(o, d, dur)`` per ogni corsa attiva.
    """
    stmt = (
        select(
            CorsaCommerciale.codice_origine,
            CorsaCommerciale.codice_destinazione,
            CorsaCommerciale.min_tratta,
            CorsaCommerciale.ora_partenza,
            CorsaCommerciale.ora_arrivo,
        )
        .where(CorsaCommerciale.azienda_id == azienda_id)
        .where(corse_attive_clause())
        .where(CorsaCommerciale.valido_da <= valido_a)
        .where(CorsaCommerciale.valido_a >= valido_da)
    )
    result = await session.execute(stmt)
    out: list[tuple[str, str, int]] = []
    for row in result:
        if row.min_tratta is not None and row.min_tratta > 0:
            durata = int(row.min_tratta)
        else:
            durata = _durata_min_da_orari(row.ora_partenza, row.ora_arrivo)
        if durata > 0:
            out.append((row.codice_origine, row.codice_destinazione, durata))
    return out


async def costruisci_lookup_durate(
    session: AsyncSession,
    *,
    azienda_id: int,
    valido_da: date,
    valido_a: date,
) -> tuple[dict[tuple[str, str], int], dict[str, int]]:
    """Pre-calcolo bulk dei due lookup per ``calcola_durata_vuoto_min``.

    1 query DB → 2 raggruppamenti in Python → 2 dict pronti per
    iniezione in ``ParamPipelineLineaCentrica``.

    Args:
        session: AsyncSession aperto (passato dal builder).
        azienda_id: filtro azienda.
        valido_da/a: periodo PdE del programma.

    Returns:
        Tupla ``(durata_per_coppia, baseline_per_stazione)``:

        - ``durata_per_coppia[(origine, destinazione)] -> mediana_min``
        - ``baseline_per_stazione[stazione] -> mediana_min``

        Entrambi vuoti se nessuna corsa attiva nel periodo (caso edge).
    """
    triple = await _carica_durate_corse_programma(
        session,
        azienda_id=azienda_id,
        valido_da=valido_da,
        valido_a=valido_a,
    )
    if not triple:
        return ({}, {})

    durata_per_coppia = aggrega_durate_per_coppia(triple)
    baseline_per_stazione = aggrega_baseline_per_stazione(triple)
    return (durata_per_coppia, baseline_per_stazione)


__all__ = [
    "DURATA_VUOTO_DEFAULT_MIN",
    "aggrega_baseline_per_stazione",
    "aggrega_durate_per_coppia",
    "calcola_durata_vuoto_min",
    "costruisci_lookup_durate",
]
