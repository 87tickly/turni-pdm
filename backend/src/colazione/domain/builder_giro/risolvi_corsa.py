"""Risoluzione corsa → assegnazione (Sprint 4.2).

Funzione **pura** che, data una corsa + un programma materiale + una
data, ritorna l'assegnazione vincente (rotabile + n. pezzi) secondo le
regole con priorità più alta + specificità.

Spec: `docs/PROGRAMMA-MATERIALE.md` §4.

Il modulo è **DB-agnostic**: accetta oggetti che hanno gli attributi
giusti (ORM, dataclass, qualunque). Le sue responsabilità:

1. Determinare `giorno_tipo` dalla data (feriale/sabato/festivo) usando
   `italian_holidays`.
2. Filtrare le regole del programma che matchano la corsa (AND di
   tutti i filtri).
3. Ordinare per (priorità DESC, specificità DESC).
4. Detect ambiguità top-2 → `RegolaAmbiguaError`.
5. Ritornare `AssegnazioneRisolta` o `None` se nessuna regola matcha.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, time
from typing import Any, Protocol

from colazione.importers.holidays import italian_holidays

# =====================================================================
# Errori
# =====================================================================


class RegolaAmbiguaError(Exception):
    """Due (o più) regole con identica priorità + specificità → ambiguità.

    Il pianificatore deve disambiguare in UI, alzando la priorità di
    una regola o aggiungendo un filtro più specifico.

    Attributi:
        corsa_id: identificatore della corsa che ha generato l'ambiguità
            (es. `numero_treno`).
        regole_ids: id delle regole top-2 indistinguibili.
    """

    def __init__(self, *, corsa_id: Any, regole_ids: list[int]) -> None:
        super().__init__(
            f"Regole ambigue per corsa {corsa_id!r}: regole {regole_ids} hanno "
            "priorità + specificità identiche. Disambigua manualmente "
            "(alza la priorità di una o aggiungi filtri)."
        )
        self.corsa_id = corsa_id
        self.regole_ids = regole_ids


# =====================================================================
# Output
# =====================================================================


@dataclass(frozen=True)
class AssegnazioneRisolta:
    """Risultato della risoluzione: regola vincente + assegnazione."""

    regola_id: int
    materiale_tipo_codice: str
    numero_pezzi: int


# =====================================================================
# Protocol — duck-typing dei tipi di input
# =====================================================================


class _RegolaLike(Protocol):
    """Una regola (ORM `ProgrammaRegolaAssegnazione` o dataclass test).

    `materiale_tipo_codice` e `numero_pezzi` sono nullable da Sprint 5.1
    (migration 0007) — campi legacy in fase di deprecazione. Ma le regole
    create dopo 0007 li hanno popolati dal primo elemento di
    `composizione_json` (handler API) e quelle pre-esistenti dal backfill.
    Quindi runtime sono sempre non-null. Sub 5.5 li rimuoverà del tutto.
    """

    id: int
    filtri_json: list[Any]
    materiale_tipo_codice: str | None
    numero_pezzi: int | None
    priorita: int


# Il tipo della corsa è `Any` di proposito: i campi richiesti dipendono
# dai filtri usati nelle regole (lazy duck-typing). Il chiamante è
# responsabile di passare un oggetto con gli attributi necessari (vedi
# `CAMPI_AMMESSI` in `schemas/programmi.py`).
_CorsaLike = Any


# =====================================================================
# Determina giorno_tipo da data
# =====================================================================


def determina_giorno_tipo(d: date) -> str:
    """Una data → ``'feriale'`` | ``'sabato'`` | ``'festivo'``.

    Regole (in ordine di priorità):

    1. Festività italiana (vedi `holidays.italian_holidays`) → festivo
    2. Domenica (`weekday()==6`) → festivo
    3. Sabato (`weekday()==5`) non festivo → sabato
    4. Lun-Ven non festivi → feriale

    Esempi:
        >>> determina_giorno_tipo(date(2026, 1, 1))  # Capodanno (giovedì)
        'festivo'
        >>> determina_giorno_tipo(date(2026, 4, 25))  # Liberazione (sabato)
        'festivo'
        >>> determina_giorno_tipo(date(2026, 4, 18))  # sabato normale
        'sabato'
        >>> determina_giorno_tipo(date(2026, 4, 20))  # lunedì normale
        'feriale'
    """
    if d in italian_holidays(d.year):
        return "festivo"
    weekday = d.weekday()
    if weekday == 6:
        return "festivo"
    if weekday == 5:
        return "sabato"
    return "feriale"


# =====================================================================
# Estrazione valore + parsing time
# =====================================================================


def estrai_valore_corsa(campo: str, corsa: _CorsaLike, giorno_tipo: str) -> Any:
    """Mapping nome-campo del filtro → attributo della corsa (o derivato)."""
    if campo == "giorno_tipo":
        return giorno_tipo
    if campo == "fascia_oraria":
        # Si confronta con `ora_partenza` della corsa (decisione utente
        # in `PROGRAMMA-MATERIALE.md` §6.3: la partenza decide).
        return corsa.ora_partenza
    return getattr(corsa, campo)


def _parse_time_str(s: Any) -> time:
    """Parsa stringa 'HH:MM' o 'HH:MM:SS' in `time`. Pass-through se già `time`."""
    if isinstance(s, time):
        return s
    if not isinstance(s, str):
        raise TypeError(f"fascia_oraria valore deve essere stringa, ricevuto {type(s).__name__}")
    parts = s.split(":")
    if len(parts) not in (2, 3):
        raise ValueError(f"fascia_oraria {s!r} non in formato HH:MM o HH:MM:SS")
    return time(
        int(parts[0]),
        int(parts[1]),
        int(parts[2]) if len(parts) == 3 else 0,
    )


# =====================================================================
# Match filtro singolo / regola completa
# =====================================================================


def matches_filtro(filtro: dict[str, Any], corsa: _CorsaLike, giorno_tipo: str) -> bool:
    """Un singolo filtro matcha la corsa?

    Il filtro è un dict con chiavi `campo`, `op`, `valore` (validato
    a monte da Pydantic in `schemas/programmi.py`).
    """
    campo = filtro["campo"]
    op = filtro["op"]
    valore_filtro = filtro["valore"]

    valore_corsa = estrai_valore_corsa(campo, corsa, giorno_tipo)

    if op == "eq":
        return bool(valore_corsa == valore_filtro)

    if op == "in":
        return valore_corsa in valore_filtro

    if op == "between":
        lo, hi = valore_filtro
        if campo == "fascia_oraria":
            lo = _parse_time_str(lo)
            hi = _parse_time_str(hi)
        return bool(lo <= valore_corsa <= hi)

    if op == "gte":
        rhs = valore_filtro
        if campo == "fascia_oraria":
            rhs = _parse_time_str(rhs)
        return bool(valore_corsa >= rhs)

    if op == "lte":
        rhs = valore_filtro
        if campo == "fascia_oraria":
            rhs = _parse_time_str(rhs)
        return bool(valore_corsa <= rhs)

    raise ValueError(f"operatore non supportato: {op!r}")


def matches_all(filtri: list[dict[str, Any]], corsa: _CorsaLike, giorno_tipo: str) -> bool:
    """Tutti i filtri devono matchare (AND).

    Lista vuota → ``True`` (regola di fallback: matcha tutto).
    """
    for f in filtri:
        if not matches_filtro(f, corsa, giorno_tipo):
            return False
    return True


# =====================================================================
# Risoluzione top-level
# =====================================================================


def risolvi_corsa(
    corsa: _CorsaLike,
    regole: Sequence[_RegolaLike],
    data: date,
) -> AssegnazioneRisolta | None:
    """Risolve l'assegnazione (rotabile + n_pezzi) di una corsa in una data.

    Algoritmo (vedi `PROGRAMMA-MATERIALE.md` §4.1):

    1. Determina `giorno_tipo` dalla `data`.
    2. Filtra le `regole` candidate (AND di tutti i filtri).
    3. Se nessuna candidata → `None`.
    4. Ordina per `(priorita DESC, specificita DESC)`.
    5. Se top-2 hanno priorità+specificità identiche → `RegolaAmbiguaError`.
    6. Ritorna l'assegnazione della top.

    Args:
        corsa: oggetto con i campi della corsa (vedi
            `schemas/programmi.CAMPI_AMMESSI`).
        regole: lista di regole del programma, **già caricata** (no lazy
            ORM). Tipicamente `programma.regole`.
        data: data per cui si risolve.

    Returns:
        `AssegnazioneRisolta` con regola vincente, oppure `None` se
        nessuna regola matcha (corsa "residua" — vedi strict mode).

    Raises:
        RegolaAmbiguaError: se top-2 regole sono indistinguibili.
        ValueError: se un filtro ha operatore sconosciuto (validation
            falled at insert time, ma double-check qui).
    """
    giorno_tipo = determina_giorno_tipo(data)

    candidate = [r for r in regole if matches_all(r.filtri_json, corsa, giorno_tipo)]
    if not candidate:
        return None

    # Ordine: priorità più alta vince; a parità, più specifica (più filtri).
    candidate.sort(key=lambda r: (r.priorita, len(r.filtri_json)), reverse=True)

    top = candidate[0]
    if len(candidate) > 1:
        second = candidate[1]
        if top.priorita == second.priorita and len(top.filtri_json) == len(second.filtri_json):
            raise RegolaAmbiguaError(
                corsa_id=getattr(corsa, "numero_treno", None),
                regole_ids=[top.id, second.id],
            )

    # Legacy fields nullable da migration 0007: tutte le regole post-5.1
    # li hanno popolati dal primo elemento di composizione_json (handler API
    # o backfill). Asserzione difensiva per soddisfare il typing fino a Sub
    # 5.5 (quando il Protocol leggerà direttamente composizione_json).
    if top.materiale_tipo_codice is None or top.numero_pezzi is None:
        raise RuntimeError(
            f"Regola {top.id}: campi legacy (materiale_tipo_codice, "
            "numero_pezzi) NULL post-migration 0007. Verifica backfill."
        )
    return AssegnazioneRisolta(
        regola_id=top.id,
        materiale_tipo_codice=top.materiale_tipo_codice,
        numero_pezzi=top.numero_pezzi,
    )
