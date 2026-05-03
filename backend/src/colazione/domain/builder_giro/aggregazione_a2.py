"""Aggregazione A2 — fonde più ``GiroAssegnato`` (cluster A1) in cicli
materiali aggregati con varianti calendariali per giornata.

Sprint 7.7 MR 5 (decisione utente "B1" del 2026-05-02) per il modello
varianti-per-giornata. Sprint 7.8 MR 2.5 (decisione utente
2026-05-03) ribalta la chiave A2 per chiudere la frammentazione:

> "non è che tutte le giornate sono 8 possiamo mettere un minimo di
> partenza fino a un max di 12, eccezion fatta quando dobbiamo
> chiudere i treni che potrebbe capitare che escano solo 2 giornate"

> "se ti chiedo un turno 421+421 lui deve generare un tot di giornate"

Modello di riferimento: PDF Trenord turno 1134 (ETR204 FIO 8 giornate)
— UN turno con N giornate-pattern, ciascuna con M varianti
calendariali. Il convoglio fisico ESEGUE giornata 1 → 2 → ... → N,
poi ricomincia. Pre-7.8 MR 2.5 il modello produceva N turni separati,
uno per ogni lunghezza emergente dal builder (1, 2, ..., 12) =
frammentazione.

Chiave A2 (Sprint 7.8 MR 2.5): ``(materiale_tipo_codice,
localita_codice)``. Tutti i ``GiroAssegnato`` con la stessa coppia
materiale+sede confluiscono in UN ``GiroAggregato`` con
``n_giornate = max(len(g.giornate) for g in cluster)``.

Allineamento giornate (Sprint 7.8 MR 2.5):

- I cluster A1 di lunghezza ``L < canonical`` contribuiscono varianti
  alle PRIME L giornate-pattern. Per le giornate K > L, il cluster non
  contribuisce variante (le sue date non hanno copertura per quelle
  giornate del ciclo — sono pattern "di chiusura" sotto soft floor o
  tronchi naturali).
- Cluster con lunghezza == canonical contribuiscono varianti a TUTTE
  le N giornate del ciclo.

**Disgiunzione delle date** per costruzione del clustering A1: due
cluster A1 distinti hanno sequenze di catene diverse → date di
partenza disgiunte. Pre-7.8 MR 2.5 questo era garantito a livello
giornata-K (chiave includeva n_giornate); ora resta garantito a
livello cluster_di_origine ma due cluster di lunghezza diversa
possono avere lo stesso pattern G1=G1 (prima giornata identica).
Questo è OK: due varianti diverse della giornata K=1 con sequenze
identiche e date disgiunte sono semanticamente equivalenti — il
caller può fonderle se vuole (oggi le tiene separate per tracciare
il cluster A1 di provenienza).

**Stats aggregate**: il giro aggregato eredita ``chiuso``,
``motivo_chiusura``, ``km_cumulati`` dal cluster CANONICO (= cluster
con ``len(giornate) == canonical``, primo ordinato per data minima).

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
    """Aggrega i ``GiroAssegnato`` per chiave A2 ``(materiale, sede)``.

    Sprint 7.8 MR 2.5 — refactor della chiave A2: ``n_giornate`` non
    fa più parte della chiave. Tutti i cluster A1 con la stessa coppia
    ``(materiale, sede)`` confluiscono in UN ``GiroAggregato`` di
    lunghezza pari al massimo cluster (canonical). I cluster più corti
    contribuiscono varianti alle prime K giornate.

    Pipeline:

    1. Filtra i giri "orfani" (senza ``materiale_tipo_codice``
       determinabile, = solo corse residue): vengono scartati.
    2. Raggruppa per ``(materiale_tipo_codice, localita_codice)``.
    3. Per ogni gruppo:
       - ``canonical_len`` = max(``len(g.giornate)``).
       - Ordina i cluster per ``(-len, data_partenza_minima)`` →
         primo è il cluster canonico (max lunghezza, più antico).
       - Per ogni K = 0..canonical_len-1, raccoglie le
         ``GiornataAssegnata[K]`` SOLO dai cluster che hanno
         ``len(giornate) > K``.
    4. Eredita ``chiuso``, ``motivo_chiusura``, ``km_cumulati`` dal
       canonico. Concatena ``corse_residue`` e
       ``incompatibilita_materiale`` di TUTTI i cluster.

    Args:
        giri_a1: lista di ``GiroAssegnato`` post-clustering A1.

    Returns:
        Lista di ``GiroAggregato``, ordinata per chiave
        ``(materiale, sede)``. Numero di giri = numero di coppie
        distinte materiale×sede del programma (tipicamente 1 per
        regola ETR421+ETR421 su sede FIO → 1 giro aggregato).

    Esempi:
        Input vuoto:

        >>> aggrega_a2([])
        []
    """
    # 1. Raggruppa per chiave A2 (Sprint 7.8 MR 2.5: senza n_giornate).
    per_chiave: dict[tuple[str, str], list[GiroAssegnato]] = {}
    for g in giri_a1:
        materiale = _materiale_codice_giro(g)
        if materiale is None:
            # Giro orfano (solo corse residue): scartato dall'A2.
            continue
        chiave = (materiale, g.localita_codice)
        per_chiave.setdefault(chiave, []).append(g)

    # 2. Costruisci un GiroAggregato per ciascuna chiave.
    aggregati: list[GiroAggregato] = []
    for (materiale, localita), giri_cluster in per_chiave.items():
        # Sprint 7.8 MR 2.5: canonical = max lunghezza, tie-break su
        # data minima. I cluster più lunghi tendono a essere "il
        # ciclo principale", i più corti sono varianti residue.
        canonical_len = max(len(g.giornate) for g in giri_cluster)
        giri_ordinati = sorted(
            giri_cluster,
            key=lambda g: (-len(g.giornate), _data_partenza_minima(g)),
        )
        canonico = giri_ordinati[0]

        # Per ogni K=0..canonical_len-1, raccogli SOLO le varianti dei
        # cluster con `len(giornate) > K`. I cluster più corti
        # contribuiscono varianti alle prime giornate-pattern; non
        # forniscono variante per le giornate K successive (= per le
        # date di quel cluster, il convoglio NON fa quelle giornate).
        giornate_aggregate: list[GiornataAggregata] = []
        for k in range(canonical_len):
            varianti = tuple(
                _giornata_a_variante(giro.giornate[k])
                for giro in giri_ordinati
                if k < len(giro.giornate)
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
        key=lambda a: (a.materiale_tipo_codice, a.localita_codice)
    )
    return aggregati
