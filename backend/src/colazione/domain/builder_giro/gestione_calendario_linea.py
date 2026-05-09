"""Gestione calendario per `SegmentoLinea` (Sprint 8.2 MR-D0.5).

Sprint 8.2 Plan-D, raccomandazione obbligatoria SEVERO #1: il caso
prog 14 giro 574 (sosta 20h44' a Voghera) si manifesta perché le
varianti calendariali di un segmento sono trattate come "dati
opachi". Servono primitive esplicite per:

1. Classificare ogni data del periodo PdE in una categoria operativa
   (feriale, prefestivo, festivo).
2. Filtrare le corse di un segmento per categoria, ottenendo le
   "varianti calendariali" del segmento.
3. Stimare per ogni segmento il numero di giorni di applicazione
   per categoria (input per MR-D2 assegnazione convogli).

Riuso massimo dell'infrastruttura esistente:

- ``colazione.domain.calendario`` espone già ``tipo_giorno()`` e
  ``festivita_italiane()`` — non duplicare.
- ``colazione.domain.builder_giro.etichetta.calcola_etichetta_variante``
  produce già la label UI delle varianti — non duplicare.

Questo modulo aggiunge:

- ``TipoCalendario``: enum con le categorie operative usate dal
  builder linea-centrico (più granulare di ``tipo_giorno``: distingue
  prefestivo dal feriale, scolastico dall'estivo).
- ``CalendarioSegmento``: dataclass che descrive il pattern
  applicativo di un `SegmentoLinea` (quali categorie di giorno
  sono attive, eccezioni puntuali).
- ``classifica_data()``: classifica una data nelle categorie del
  builder.
- ``genera_calendario_segmento()``: dati corse + periodo + festività,
  produce il `CalendarioSegmento` derivato dai pattern di
  applicazione delle corse.

Il modulo è **DB-agnostic**: festività passate come `frozenset[date]`,
nessuna dipendenza ORM.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from enum import StrEnum
from typing import Protocol

from colazione.domain.builder_giro.definizione_linea import SegmentoLinea
from colazione.domain.calendario import (
    festivita_italiane,
)

# =====================================================================
# Protocol
# =====================================================================


class _CorsaCalendarLike(Protocol):
    """Una corsa con metadati di applicabilità calendariale.

    Allineato con ``CorsaCommerciale`` ORM:

    - ``valido_da`` / ``valido_a``: range di validità del periodo PdE.
    - ``valido_in_date_json``: lista di date concrete in cui la corsa
      circola (può essere ``None`` se la corsa segue il pattern di
      default della periodicità).

    Per i test l'interfaccia è duck-typed: basta un dataclass con
    questi attributi.
    """

    codice_origine: str
    codice_destinazione: str
    ora_partenza: time
    ora_arrivo: time
    codice_linea: str
    valido_da: date
    valido_a: date
    valido_in_date_json: list[str] | None


# =====================================================================
# Tipi enumerati
# =====================================================================


class TipoCalendario(StrEnum):
    """Categoria operativa di un giorno per il builder linea-centrico.

    Più granulare di ``tipo_giorno()`` di ``colazione.domain.calendario``:

    - ``FERIALE``: lunedì-venerdì, NON prefestivo, NON festivo.
    - ``PREFESTIVO``: vigilia di festivo (sabato che precede domenica
      o festivo, oppure giorno feriale che precede festivo non-domenica).
    - ``SABATO``: sabato non-prefestivo (raro, es. sabato fra due
      giorni feriali).
    - ``DOMENICA``: domenica (sempre festivo, ma distinta per
      etichettatura UI).
    - ``FESTIVO``: festivo non-domenica (es. 25/12, 1/1, Pasqua).

    L'enum è **operativa**: il builder usa queste categorie per
    raggruppare giorni con pattern di servizio simile.
    """

    FERIALE = "feriale"
    PREFESTIVO = "prefestivo"
    SABATO = "sabato"
    DOMENICA = "domenica"
    FESTIVO = "festivo"


# =====================================================================
# Modello formale
# =====================================================================


@dataclass(frozen=True, kw_only=True)
class CalendarioSegmento:
    """Descrive il pattern calendariale di un `SegmentoLinea`.

    Generato da ``genera_calendario_segmento()`` analizzando le date
    di applicazione delle corse del segmento.

    Attributi:
        segmento_codice: codice del `SegmentoLinea` di riferimento.
        date_per_tipo: mapping ``TipoCalendario → frozenset[date]``
            con le date in cui il segmento è attivo, raggruppate per
            categoria. Es: ``{FERIALE: {2026-06-08, 2026-06-09, ...},
            DOMENICA: {2026-06-07, 2026-06-14, ...}}``.
        eccezioni_attive: insieme di date ``YYYY-MM-DD`` in cui il
            segmento è attivo MA che NON ricadono nel pattern
            standard (es. ferragosto attivo per servizio turistico,
            o un sabato in cui esce un'eccezione PdE). Disgiunto
            dalle date_per_tipo standard.
        eccezioni_inattive: insieme di date in cui il segmento NON è
            attivo MA che cadrebbero nel pattern standard (es. il
            13/12 cade di domenica e per pattern dovrebbe esserci
            servizio festivo, ma il PdE lo sopprime).

    Invariante: ``date_per_tipo[tipo] ∩ date_per_tipo[altro_tipo]
    == ∅`` per ogni coppia tipo ≠ altro_tipo. Una data appartiene a
    UNA sola categoria.
    """

    segmento_codice: str
    date_per_tipo: dict[TipoCalendario, frozenset[date]]
    eccezioni_attive: frozenset[date] = field(default_factory=frozenset)
    eccezioni_inattive: frozenset[date] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.segmento_codice:
            raise ValueError("CalendarioSegmento.segmento_codice non può essere vuoto")
        # Verifica disgiunzione fra categorie
        tutte_le_date: list[date] = []
        for date_set in self.date_per_tipo.values():
            tutte_le_date.extend(date_set)
        if len(tutte_le_date) != len(set(tutte_le_date)):
            duplicati = sorted(
                d for d in set(tutte_le_date) if tutte_le_date.count(d) > 1
            )
            raise ValueError(
                f"CalendarioSegmento {self.segmento_codice!r}: una stessa "
                f"data appare in più categorie. Duplicati: {duplicati}"
            )

    def date_attive_totali(self) -> frozenset[date]:
        """Tutte le date in cui il segmento è attivo (unione tipi +
        eccezioni attive).
        """
        attive: set[date] = set()
        for date_set in self.date_per_tipo.values():
            attive |= date_set
        attive |= self.eccezioni_attive
        return frozenset(attive)

    def n_giorni_per_tipo(self, tipo: TipoCalendario) -> int:
        """Numero di date in cui il segmento è attivo per categoria.
        """
        return len(self.date_per_tipo.get(tipo, frozenset()))


# =====================================================================
# Classificazione data
# =====================================================================


def _e_prefestivo(d: date, festivita_set: frozenset[date]) -> bool:
    """``True`` se ``d`` è prefestivo: vigilia di una festa.

    Convenzione operativa Trenord (memoria
    ``feedback_etichetta_categoria_variante.md``):

    - sabato prima di domenica (sempre): ``d.weekday() == 5``.
    - giorno qualsiasi precedente a un festivo non-domenica
      (es. 24/12 prefestivo perché 25/12 è Natale).

    Una domenica NON è prefestivo (è festivo). Un festivo non-domenica
    è festivo, non prefestivo.
    """
    if d.weekday() == 6:  # domenica
        return False
    if d in festivita_set:
        return False
    successivo = d + timedelta(days=1)
    if successivo.weekday() == 6:  # sabato → domenica
        return d.weekday() == 5
    return successivo in festivita_set


def classifica_data(
    d: date,
    festivita_set: frozenset[date],
) -> TipoCalendario:
    """Classifica una data nella categoria operativa del builder.

    Convenzione:
    - domenica → ``DOMENICA``
    - festivo non-domenica → ``FESTIVO``
    - prefestivo (vigilia) → ``PREFESTIVO``
    - sabato non-prefestivo → ``SABATO``
    - resto → ``FERIALE``

    Args:
        d: data da classificare.
        festivita_set: insieme di date festive per l'azienda
            (italiane fisse + Pasqua + locali). Il caller carica
            da ``FestivitaUfficiale`` e passa qui come ``frozenset[date]``.

    Returns:
        ``TipoCalendario`` della data.
    """
    if d.weekday() == 6:
        return TipoCalendario.DOMENICA
    if d in festivita_set:
        return TipoCalendario.FESTIVO
    if _e_prefestivo(d, festivita_set):
        return TipoCalendario.PREFESTIVO
    if d.weekday() == 5:
        return TipoCalendario.SABATO
    return TipoCalendario.FERIALE


def festivita_per_anno(anno: int) -> frozenset[date]:
    """Festività italiane fisse + Pasqua + Pasquetta per l'anno.

    Helper di convenienza che riusa ``colazione.domain.calendario.
    festivita_italiane()``. Quel modulo ritorna ``list[tuple[date, str]]``
    (data + nome festa per UI); qui scartiamo i nomi e ritorniamo
    solo le date come ``frozenset[date]`` per i confronti efficienti
    in ``classifica_data``.
    """
    return frozenset(d for d, _nome in festivita_italiane(anno))


# =====================================================================
# Generazione calendario segmento
# =====================================================================


def _date_corsa(
    corsa: _CorsaCalendarLike,
    *,
    periodo_da: date,
    periodo_a: date,
) -> frozenset[date]:
    """Estrae le date in cui la corsa è attiva nel periodo.

    Logica:
    - Se ``valido_in_date_json`` è popolato (lista di date ISO),
      filtra a quelle nel periodo. Pattern PdE Trenord standard
      (memoria ``feedback_pde_periodicita_verita.md``).
    - Altrimenti, fallback a ``[valido_da, valido_a]`` intersecato
      col periodo (corsa giornaliera).

    Returns:
        frozenset di date in cui la corsa è effettivamente attiva
        nel periodo PdE indicato.
    """
    inizio = max(corsa.valido_da, periodo_da)
    fine = min(corsa.valido_a, periodo_a)
    if inizio > fine:
        return frozenset()

    if corsa.valido_in_date_json:
        date_corsa: set[date] = set()
        for s in corsa.valido_in_date_json:
            try:
                d = date.fromisoformat(s)
            except (ValueError, TypeError):
                continue
            if inizio <= d <= fine:
                date_corsa.add(d)
        return frozenset(date_corsa)

    # Fallback: corsa attiva ogni giorno del range
    out: set[date] = set()
    d = inizio
    while d <= fine:
        out.add(d)
        d += timedelta(days=1)
    return frozenset(out)


def genera_calendario_segmento(
    segmento: SegmentoLinea,
    corse_segmento: Sequence[_CorsaCalendarLike],
    *,
    periodo_da: date,
    periodo_a: date,
    festivita_set: frozenset[date],
) -> CalendarioSegmento:
    """Genera il `CalendarioSegmento` da corse + periodo + festività.

    Algoritmo:
    1. Per ogni corsa, estrai le date di applicazione nel periodo
       (``_date_corsa``).
    2. Unione di tutte le date attive del segmento.
    3. Per ogni data attiva, classifica con ``classifica_data`` e
       aggiungi al `date_per_tipo[tipo]`.
    4. Calcola eccezioni:
       - ``eccezioni_attive``: date attive che NON cadono nel pattern
         "regolare" del segmento (heuristica: se il segmento ha tipo
         FERIALE dominante e la data è festiva, è eccezione attiva).
       - ``eccezioni_inattive``: scope futuro MR-D1 (richiede
         pattern di riferimento del segmento).

    Args:
        segmento: il `SegmentoLinea` di riferimento (per `codice`).
        corse_segmento: corse appartenenti al segmento.
        periodo_da/periodo_a: range del periodo PdE.
        festivita_set: festività attive per l'azienda.

    Returns:
        `CalendarioSegmento` con date raggruppate per tipo.

    Raises:
        ValueError: se ``periodo_da > periodo_a``.

    Determinismo: le date in ``date_per_tipo[tipo]`` sono frozenset,
    quindi unordered ma deterministically equal.
    """
    if periodo_da > periodo_a:
        raise ValueError(
            f"periodo_da ({periodo_da}) deve essere <= periodo_a ({periodo_a})"
        )

    date_attive: set[date] = set()
    for c in corse_segmento:
        date_attive |= _date_corsa(
            c, periodo_da=periodo_da, periodo_a=periodo_a
        )

    raggruppamento: dict[TipoCalendario, set[date]] = defaultdict(set)
    for d in date_attive:
        tipo = classifica_data(d, festivita_set)
        raggruppamento[tipo].add(d)

    return CalendarioSegmento(
        segmento_codice=segmento.codice,
        date_per_tipo={
            tipo: frozenset(date_set)
            for tipo, date_set in raggruppamento.items()
        },
    )


def conta_giorni_periodo_per_tipo(
    *,
    periodo_da: date,
    periodo_a: date,
    festivita_set: frozenset[date],
) -> dict[TipoCalendario, int]:
    """Conta quanti giorni di ciascun tipo cadono nel periodo PdE.

    Indipendente dalle corse: utile per stimare denominatori (es.
    ``corse_per_die_media``) o valutare se un segmento copre tutti i
    feriali del periodo.

    Args:
        periodo_da/periodo_a: range del periodo PdE (inclusivi).
        festivita_set: festività attive per l'azienda.

    Returns:
        mapping ``TipoCalendario → conteggio giorni``. Le categorie
        senza giorni nel periodo non sono nel dict.
    """
    if periodo_da > periodo_a:
        raise ValueError(
            f"periodo_da ({periodo_da}) deve essere <= periodo_a ({periodo_a})"
        )

    counters: dict[TipoCalendario, int] = defaultdict(int)
    d = periodo_da
    while d <= periodo_a:
        counters[classifica_data(d, festivita_set)] += 1
        d += timedelta(days=1)
    return dict(counters)


__all__ = [
    "CalendarioSegmento",
    "TipoCalendario",
    "classifica_data",
    "conta_giorni_periodo_per_tipo",
    "festivita_per_anno",
    "genera_calendario_segmento",
]
