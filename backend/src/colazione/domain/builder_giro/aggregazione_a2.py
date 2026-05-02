"""Aggregazione A2 — fonde più ``GiroAssegnato`` (cluster A1) in cicli
materiali aggregati con varianti calendariali per giornata.

Sprint 7.7 MR 5 (decisione utente "B1" del 2026-05-02). Background:

> "Devi fare B1, è lo stesso turno, ma in determinate giornate il
> materiale fa giri diversi perché in quei giorni quei treni non ci
> sono."

Modello di riferimento: PDF Trenord turno 1134 (ETR204 FIO 8 giornate)
in cui la giornata 9 ha 4 varianti calendariali (``LV 1:5``, ``F``,
``LV 6 escl. 21-28/3, 11/4``, ``Si eff. 21-28/3, 11/4``) — sequenze
di blocchi diverse, date di applicazione disgiunte, stesso ciclo
materiale.

Chiave A2: ``(materiale_tipo_codice, localita_codice, n_giornate)``.
Tutti i ``GiroAssegnato`` (output post-clustering A1) con la stessa
chiave A2 vengono fusi in UN ``GiroAggregato``. Le N giornate del
ciclo aggregato hanno M varianti, una per ciascun ``GiroAssegnato``
del cluster A2 — l'indice della giornata K è preservato (= index
``[K-1]`` nella lista ``GiroAssegnato.giornate``).

**Disgiunzione delle date** per costruzione: il clustering A1
(``_cluster_giri_a1``) garantisce che due cluster A1 distinti abbiano
sequenze di catene diverse → date di partenza disgiunte → quindi le
``GiornataAssegnata.dates_apply_or_data`` per la stessa giornata-K
di cluster diversi non si sovrappongono.

**Stats aggregate**: il giro aggregato eredita ``chiuso``,
``motivo_chiusura``, ``km_cumulati`` dal cluster CANONICO (= primo
ordinato per data di partenza minima). Aggregati più sofisticati
(media ponderata su `dates_apply`) sono raffinabili nei MR
successivi.

Il modulo è **DB-agnostic**.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from colazione.domain.builder_giro.composizione import (
    BloccoAssegnato,
    CorsaResidua,
    EventoComposizione,
    GiornataAssegnata,
    GiroAssegnato,
    IncompatibilitaMateriale,
)
from colazione.domain.builder_giro.multi_giornata import MotivoChiusura
from colazione.domain.builder_giro.posizionamento import CatenaPosizionata


# =====================================================================
# Output dataclass
# =====================================================================


@dataclass(frozen=True)
class VarianteGiornata:
    """Una variante calendariale di una giornata-tipo.

    Sprint 7.7 MR 5: corrisponde a 1 ``GiornataAssegnata`` di un
    cluster A1 nel cluster A2. La sequenza di blocchi è propria
    (= il convoglio fa "questo specifico percorso" in queste date).

    Attributi:
        catena_posizionata: catena posizionata della variante
            (con eventuali vuoti testa/coda).
        blocchi_assegnati: blocchi corsa con composizione assegnata.
        eventi_composizione: aggancio/sgancio rilevati da MR 4.4.4.
        dates_apply: date concrete in cui questa variante si applica.
            Per costruzione disgiunto da quelle delle altre varianti
            della stessa giornata.
    """

    catena_posizionata: CatenaPosizionata
    blocchi_assegnati: tuple[BloccoAssegnato, ...]
    eventi_composizione: tuple[EventoComposizione, ...]
    dates_apply: tuple[date, ...]


@dataclass(frozen=True)
class GiornataAggregata:
    """Una giornata di un ``GiroAggregato``: 1+ varianti.

    ``numero_giornata`` è 1-based.
    """

    numero_giornata: int
    varianti: tuple[VarianteGiornata, ...]


@dataclass(frozen=True)
class GiroAggregato:
    """Output del clustering A2: 1 ciclo materiale per chiave
    ``(materiale_tipo_codice, localita_codice, n_giornate)``.

    Sostituisce ``GiroAssegnato`` come unità persistita dal MR 5.
    """

    localita_codice: str
    materiale_tipo_codice: str
    giornate: tuple[GiornataAggregata, ...]
    chiuso: bool
    motivo_chiusura: MotivoChiusura
    km_cumulati: float = 0.0
    corse_residue: tuple[CorsaResidua, ...] = field(default_factory=tuple)
    incompatibilita_materiale: tuple[IncompatibilitaMateriale, ...] = field(
        default_factory=tuple
    )
    # Numero di cluster A1 originali fusi nel giro aggregato. ``1``
    # significa "nessuna variante multipla per nessuna giornata"
    # (caso degenere); ``> 1`` = almeno una giornata ha varianti.
    n_cluster_a1: int = 1


# =====================================================================
# Helper interni
# =====================================================================


def _materiale_codice_giro(giro: GiroAssegnato) -> str | None:
    """Primo ``materiale_tipo_codice`` usato dal giro.

    Mirror di ``persister.primo_tipo_materiale`` ma duplicato qui per
    mantenere il modulo DB-agnostic e indipendente. Ritorna ``None``
    se il giro non ha alcun blocco assegnato (= solo corse residue).
    """
    for giornata in giro.giornate:
        for blocco in giornata.blocchi_assegnati:
            if blocco.assegnazione.composizione:
                return blocco.assegnazione.composizione[0].materiale_tipo_codice
    return None


def _data_partenza_minima(giro: GiroAssegnato) -> date:
    """Prima data di applicazione del giro (per ordinamento canonico).

    Cerca il minimo tra le date di applicazione delle giornate
    (dates_apply_or_data fallback alla data calendaristica).
    """
    candidati: list[date] = []
    for g in giro.giornate:
        candidati.extend(g.dates_apply_or_data)
    return min(candidati) if candidati else date.max


def _giornata_a_variante(g: GiornataAssegnata) -> VarianteGiornata:
    """Converte una ``GiornataAssegnata`` in ``VarianteGiornata``."""
    return VarianteGiornata(
        catena_posizionata=g.catena_posizionata,
        blocchi_assegnati=g.blocchi_assegnati,
        eventi_composizione=g.eventi_composizione,
        dates_apply=g.dates_apply_or_data,
    )


# =====================================================================
# API pubblica
# =====================================================================


def aggrega_a2(giri_a1: list[GiroAssegnato]) -> list[GiroAggregato]:
    """Aggrega i ``GiroAssegnato`` per chiave A2.

    Pipeline:

    1. Filtra i giri "orfani" (senza ``materiale_tipo_codice``
       determinabile, = solo corse residue): vengono scartati.
    2. Raggruppa per ``(materiale_tipo_codice, localita_codice,
       n_giornate)``.
    3. Per ogni gruppo: ordina i giri per data di partenza minima
       (canonico = primo). Per ogni numero_giornata K=1..N, raccoglie
       le ``GiornataAssegnata[K-1]`` di tutti i giri del gruppo e le
       converte in varianti (``variant_index`` = ordine canonico).
    4. Eredita ``chiuso``, ``motivo_chiusura``, ``km_cumulati`` dal
       canonico. Concatena ``corse_residue`` e
       ``incompatibilita_materiale`` di tutti i giri del gruppo.

    Args:
        giri_a1: lista di ``GiroAssegnato`` post-clustering A1.

    Returns:
        Lista di ``GiroAggregato``, ordinata per chiave A2
        (deterministico). Cluster con un solo cluster A1 originale
        producono comunque un ``GiroAggregato`` (con ``n_cluster_a1=1``
        e 1 sola variante per giornata).

    Esempi:
        Input vuoto:

        >>> aggrega_a2([])
        []
    """
    # 1. Raggruppa per chiave A2.
    per_chiave: dict[tuple[str, str, int], list[GiroAssegnato]] = {}
    for g in giri_a1:
        materiale = _materiale_codice_giro(g)
        if materiale is None:
            # Giro orfano (solo corse residue): scartato dall'A2.
            continue
        chiave = (materiale, g.localita_codice, len(g.giornate))
        per_chiave.setdefault(chiave, []).append(g)

    # 2. Costruisci un GiroAggregato per ciascuna chiave.
    aggregati: list[GiroAggregato] = []
    for (materiale, localita, n_giornate), giri_cluster in per_chiave.items():
        # Ordina canonico per data di partenza minima → variant_index 0
        # = giro che inizia prima nel calendario.
        giri_ordinati = sorted(giri_cluster, key=_data_partenza_minima)
        canonico = giri_ordinati[0]

        # Per ogni numero_giornata K, raccogli le varianti.
        giornate_aggregate: list[GiornataAggregata] = []
        for k in range(n_giornate):
            varianti = tuple(
                _giornata_a_variante(giro.giornate[k]) for giro in giri_ordinati
            )
            giornate_aggregate.append(
                GiornataAggregata(numero_giornata=k + 1, varianti=varianti)
            )

        # Aggregati: corse residue + incompatibilità di TUTTI i cluster.
        all_corse_residue: list[CorsaResidua] = []
        all_incompat: list[IncompatibilitaMateriale] = []
        for giro in giri_ordinati:
            all_corse_residue.extend(giro.corse_residue)
            all_incompat.extend(giro.incompatibilita_materiale)

        aggregati.append(
            GiroAggregato(
                localita_codice=localita,
                materiale_tipo_codice=materiale,
                giornate=tuple(giornate_aggregate),
                chiuso=canonico.chiuso,
                motivo_chiusura=canonico.motivo_chiusura,
                km_cumulati=canonico.km_cumulati,
                corse_residue=tuple(all_corse_residue),
                incompatibilita_materiale=tuple(all_incompat),
                n_cluster_a1=len(giri_ordinati),
            )
        )

    # 3. Output ordinato per chiave (deterministico).
    aggregati.sort(
        key=lambda a: (a.materiale_tipo_codice, a.localita_codice, len(a.giornate))
    )
    return aggregati
