"""Fusione cluster A1 simili (Sprint 7.9 MR 12).

Funzione **pura** che, dati i ``GiroAssegnato`` post-clustering A1,
fonde i cluster con sequenze di catene **simili** (Jaccard ≥ soglia)
in un unico cluster con:

- date di applicazione = unione delle date dei cluster fusi (per ogni
  giornata K)
- sequenza canonica = del cluster con più date totali (= "spina
  dorsale" più popolata)

Motivazione (decisione utente 2026-05-03 entry 114):

> "il cluster molto spesso perde treni nelle varie varianti, quindi
> abbiamo un piccolo problema di bug. crea solo una giornata festiva
> con un treno isolato. non popola abbastanza treni"

Il clustering A1 esistente (``multi_giornata.py``) raggruppa per
**identità esatta** della sequenza di catene cross-notte. Una piccola
variazione (un treno che non gira il sabato, un cambio orario in una
data, una corsa aggiunta solo certi giorni) genera un cluster nuovo.
Risultato osservato: 90% delle varianti con 1 sola data
(programma 9259), giri "poveri" con 1-2 treni (giro 75032 linea
Tirano), giornate festive isolate senza spiegazione (giro 75034
CHIAVENNA singola).

La fusione MR 12 è un **post-processing** tra clustering A1 e
aggregazione A2: riconosce che cluster con la stessa "spina dorsale"
(≥ 70% treni in comune) rappresentano lo stesso pattern di servizio
con piccole variazioni calendariali, e li unifica.

Soglia Jaccard di default: 0.7. Configurabile via ``soglia`` per i
test e per future tarature.

**Trade-off accettato**: la sequenza canonica del cluster fuso usa
i treni del cluster più popolato; le piccole eccezioni di sequenza
degli altri cluster vengono perse a favore di una rappresentazione
compatta tipo PDF Trenord 1134.

Il modulo è **DB-agnostic** — opera solo su ``GiroAssegnato``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import date
from typing import Any

from colazione.domain.builder_giro.composizione import (
    GiornataAssegnata,
    GiroAssegnato,
)


# =====================================================================
# Helpers
# =====================================================================


def _treni_del_cluster(giro: GiroAssegnato) -> frozenset[Any]:
    """Insieme dei treni (id corsa_commerciale) del cluster.

    Considera tutte le corse di tutte le catene di tutte le giornate.
    Usato come "fingerprint" del cluster per il calcolo Jaccard.
    """
    treni: set[Any] = set()
    for giornata in giro.giornate:
        for corsa in giornata.catena_posizionata.catena.corse:
            treni.add(id(corsa) if not hasattr(corsa, "id") else corsa.id)
    return frozenset(treni)


def _materiale_codice_giro(giro: GiroAssegnato) -> str | None:
    """Primo ``materiale_tipo_codice`` usato dal giro (None se orfano).

    Mirror di ``aggregazione_a2._materiale_codice_giro`` per
    indipendenza del modulo.
    """
    for giornata in giro.giornate:
        for blocco in giornata.blocchi_assegnati:
            if blocco.assegnazione.composizione:
                return blocco.assegnazione.composizione[0].materiale_tipo_codice
    return None


def _date_totali_cluster(giro: GiroAssegnato) -> int:
    """Totale date di applicazione (somma su tutte le giornate).

    Cluster con più date sono considerati "principali" per la scelta
    della sequenza canonica nella fusione.
    """
    return sum(len(g.dates_apply_or_data) for g in giro.giornate)


def _jaccard(a: frozenset[Any], b: frozenset[Any]) -> float:
    """Similarità di Jaccard tra due insiemi: |A ∩ B| / |A ∪ B|.

    Range [0, 1]. ``1`` = insiemi identici. ``0`` = disgiunti.
    Per insiemi entrambi vuoti torna ``1.0`` (caso degenere convenzionale).
    """
    if not a and not b:
        return 1.0
    intersezione = len(a & b)
    unione = len(a | b)
    return intersezione / unione if unione else 0.0


# =====================================================================
# Union-Find
# =====================================================================


class _UnionFind:
    """DSU classico per raggruppare cluster simili in componenti connesse."""

    def __init__(self, n: int) -> None:
        self.parent: list[int] = list(range(n))
        self.rank: list[int] = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x: int, y: int) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1


# =====================================================================
# Fusione di N cluster simili
# =====================================================================


def _fonde_giornate(
    giornata_principale: GiornataAssegnata,
    giornate_da_fondere: list[GiornataAssegnata],
) -> GiornataAssegnata:
    """Fonde N giornate (= stessa K-esima giornata di cluster diversi).

    La giornata principale fornisce la sequenza di catene canonica
    (treni, eventi, materiali). Le altre contribuiscono solo le
    ``dates_apply_or_data``, che vengono unite a quelle della
    principale.
    """
    date_unite: set[date] = set(giornata_principale.dates_apply_or_data)
    for g in giornate_da_fondere:
        date_unite.update(g.dates_apply_or_data)

    return replace(
        giornata_principale,
        dates_apply=tuple(sorted(date_unite)),
    )


def _fonde_cluster_componente(cluster_lista: list[GiroAssegnato]) -> GiroAssegnato:
    """Fonde N cluster A1 in un unico cluster.

    - Cluster principale = quello con più date totali (tie-break: prima
      data_apply minima).
    - Per ogni giornata K del cluster fuso: sequenza canonica del
      principale, ``dates_apply`` = unione delle date_apply
      della K-esima giornata di tutti i cluster del componente.

    Tutti i cluster del componente devono avere la stessa lunghezza
    (= n. giornate) e materiale_tipo + sede, garantito dal raggruppamento
    a monte.
    """
    if len(cluster_lista) == 1:
        return cluster_lista[0]

    def _data_minima(g: GiroAssegnato) -> date:
        date_g: list[date] = []
        for giornata in g.giornate:
            date_g.extend(giornata.dates_apply_or_data)
        return min(date_g) if date_g else date.max

    principale = max(
        cluster_lista,
        key=lambda g: (_date_totali_cluster(g), -_data_minima(g).toordinal()),
    )
    altri = [g for g in cluster_lista if g is not principale]

    nuove_giornate = tuple(
        _fonde_giornate(
            principale.giornate[k],
            [g.giornate[k] for g in altri],
        )
        for k in range(len(principale.giornate))
    )

    # Concatena residue + incompatibilità di TUTTI i cluster del componente.
    all_corse_residue = list(principale.corse_residue)
    all_incompat = list(principale.incompatibilita_materiale)
    for g in altri:
        all_corse_residue.extend(g.corse_residue)
        all_incompat.extend(g.incompatibilita_materiale)

    return replace(
        principale,
        giornate=nuove_giornate,
        corse_residue=tuple(all_corse_residue),
        incompatibilita_materiale=tuple(all_incompat),
    )


# =====================================================================
# API pubblica
# =====================================================================


SOGLIA_JACCARD_DEFAULT: float = 0.7


def fonde_cluster_simili(
    giri_a1: list[GiroAssegnato],
    soglia: float = SOGLIA_JACCARD_DEFAULT,
) -> list[GiroAssegnato]:
    """Fonde cluster A1 con sequenze simili in cluster unificati.

    Algoritmo:
    1. Raggruppa per chiave (materiale, sede, n_giornate). Cluster con
       lunghezze diverse non possono fondersi (la struttura giornata-K
       perderebbe coerenza).
    2. Per ogni gruppo, calcola la similarità Jaccard tra coppie di
       cluster sulla base dell'insieme dei treni (id corsa_commerciale).
    3. Costruisce componenti connesse con Union-Find (similarity ≥
       ``soglia`` → unione).
    4. Per ogni componente, produce un cluster fuso (vedi
       ``_fonde_cluster_componente``).

    Args:
        giri_a1: lista di ``GiroAssegnato`` post-clustering A1.
        soglia: soglia Jaccard. Default 0.7. Più bassa = fusione più
            aggressiva, meno fedele alle eccezioni.

    Returns:
        Lista di cluster fusi. Numero ≤ input. L'ordine non è garantito
        (deterministico ma non significativo).
    """
    if not giri_a1:
        return []

    # Raggruppa per chiave fusion-compatibile.
    per_chiave: dict[tuple[str, str, int], list[GiroAssegnato]] = defaultdict(list)
    senza_materiale: list[GiroAssegnato] = []
    for g in giri_a1:
        materiale = _materiale_codice_giro(g)
        if materiale is None:
            # Giro orfano (solo corse residue): pass-through senza fusione.
            senza_materiale.append(g)
            continue
        per_chiave[(materiale, g.localita_codice, len(g.giornate))].append(g)

    output: list[GiroAssegnato] = []
    for gruppo in per_chiave.values():
        n = len(gruppo)
        if n == 1:
            output.append(gruppo[0])
            continue

        # Pre-calcolo treni per ogni cluster del gruppo.
        treni_per_cluster = [_treni_del_cluster(g) for g in gruppo]

        # Union-Find su coppie con Jaccard ≥ soglia.
        uf = _UnionFind(n)
        for i in range(n):
            for j in range(i + 1, n):
                if _jaccard(treni_per_cluster[i], treni_per_cluster[j]) >= soglia:
                    uf.union(i, j)

        # Raccoglie cluster per componente.
        per_componente: dict[int, list[GiroAssegnato]] = defaultdict(list)
        for i, g in enumerate(gruppo):
            per_componente[uf.find(i)].append(g)

        for cluster_componente in per_componente.values():
            output.append(_fonde_cluster_componente(cluster_componente))

    output.extend(senza_materiale)
    return output
