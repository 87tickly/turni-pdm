"""Aggregazione A2 — fonde più ``GiroAssegnato`` (cluster A1) in cicli
materiali aggregati con varianti calendariali per giornata.

Sprint 7.7 MR 5 (decisione utente "B1" del 2026-05-02) per il modello
varianti-per-giornata. Sprint 7.8 MR 2.5 aveva poi unificato cluster
di lunghezze diverse nello stesso turno (chiave senza ``n_giornate``)
per evitare frammentazione. **Sprint 7.9 MR α (decisione utente
2026-05-04) ripristina ``n_giornate`` nella chiave**: in MR 2.5 si era
esagerato — fondere cluster di lunghezze diverse generava turni
incoerenti per data, con varianti che esistevano solo su alcune
giornate (warning UI "ciclo non si estende qui" + ⚠ congruenza notte).

Decisione utente 2026-05-04:

> "il turno è relativo a un solo materiale no a molteplici materiali.
> quindi va fixato e trovato l'algoritmo giusto." (sul fatto che
> selezionando una variante in giornata K si vedeva un convoglio
> diverso in giornata K+1)

Conseguenza: cluster A1 di lunghezze diverse → turni A2 distinti.
Trenord usa lo stesso pattern (turno 1134 = 8 giornate ETR204, turno
1135/1136/... per pattern di lunghezza ridotta). Più turni totali, ma
ognuno coerente per costruzione: presa una data X qualunque
appartenente al turno, seguendo le N giornate si ricostruisce la
traiettoria fisica continua di UN solo convoglio.

**Chiave A2 (Sprint 7.9 MR α)**: ``(materiale_tipo_codice,
localita_codice, n_giornate)`` con ``n_giornate = len(g.giornate)``.
Tutti i ``GiroAssegnato`` con stessa terna confluiscono in UN
``GiroAggregato`` di lunghezza ``n_giornate``, con M varianti per
ciascuna delle N giornate (M = numero di cluster A1 di quella terna).

**Bin-packing convogli paralleli (Sprint 7.9 MR 10, entry 109)** —
intatto, opera DENTRO il gruppo per chiave A2: cluster con date di
applicazione SOVRAPPOSTE (= convogli fisici diversi in parallelo)
restano in turni separati anche a parità di chiave A2.

**Disgiunzione delle date** per costruzione del clustering A1: due
cluster A1 distinti hanno sequenze di catene diverse → date di
partenza disgiunte. Con la nuova chiave A2 vincoliamo anche le
lunghezze a coincidere, quindi ogni giornata-K del turno aggregato
ha SEMPRE la stessa cardinalità di varianti (= numero di cluster A1
nel gruppo) — non c'è più "buco" su giornate finali.

**Stats aggregate**: il giro aggregato eredita ``chiuso``,
``motivo_chiusura``, ``km_cumulati`` dal cluster CANONICO (= primo
ordinato per data minima — tutti i cluster nel gruppo hanno stessa
lunghezza, quindi non serve più tie-break per len).

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


def _date_occupazione(giro: GiroAssegnato) -> set[date]:
    """Date in cui il convoglio del cluster A1 è occupato.

    Usato dal bin-packing MR 10 (Sprint 7.9 entry 109) per separare
    convogli paralleli: due cluster con date di occupazione che si
    sovrappongono devono finire in turni materiali distinti (ognuno =
    un convoglio fisico), non in varianti dello stesso turno.
    """
    occupate: set[date] = set()
    for g in giro.giornate:
        occupate.update(g.dates_apply_or_data)
    return occupate


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
    """Aggrega i ``GiroAssegnato`` per chiave A2 ``(materiale, sede,
    n_giornate)``.

    Sprint 7.9 MR α — ripristino di ``n_giornate`` nella chiave (vedi
    docstring del modulo). Cluster A1 di lunghezze diverse vanno in
    turni A2 separati, garantendo che ogni giornata-K abbia varianti
    coerenti per costruzione: presa una data X del turno e seguite
    tutte le N giornate, la traiettoria del convoglio è fisicamente
    continua.

    Pipeline:

    1. Filtra i giri "orfani" (senza ``materiale_tipo_codice``
       determinabile, = solo corse residue): vengono scartati.
    2. Raggruppa per ``(materiale_tipo_codice, localita_codice,
       n_giornate)``. Tutti i cluster nello stesso gruppo hanno
       stessa lunghezza per costruzione.
    3. Bin-packing convogli paralleli (Sprint 7.9 MR 10, entry 109)
       DENTRO ogni gruppo: cluster con date di occupazione sovrapposte
       → turni separati (= convogli fisici in parallelo). Cluster con
       date disgiunte → varianti calendariali dello stesso turno.
    4. Per ogni turno, costruisce un ``GiroAggregato`` di N giornate
       (= ``n_giornate`` della chiave). Ogni giornata-K ha M varianti
       (= numero di cluster A1 fusi nel turno).
    5. Eredita ``chiuso``, ``motivo_chiusura``, ``km_cumulati`` dal
       canonico (= primo cluster per data minima). Concatena
       ``corse_residue`` e ``incompatibilita_materiale`` di TUTTI i
       cluster del turno.

    Args:
        giri_a1: lista di ``GiroAssegnato`` post-clustering A1.

    Returns:
        Lista di ``GiroAggregato``, ordinata per chiave ``(materiale,
        sede, n_giornate, data_minima_canonico)``. Numero di giri
        ≥ numero di terne distinte (≥ a causa del bin-packing).

    Esempi:
        Input vuoto:

        >>> aggrega_a2([])
        []
    """
    # 1. Raggruppa per chiave A2 (Sprint 7.9 MR α: include n_giornate).
    per_chiave: dict[tuple[str, str, int], list[GiroAssegnato]] = {}
    for g in giri_a1:
        materiale = _materiale_codice_giro(g)
        if materiale is None:
            # Giro orfano (solo corse residue): scartato dall'A2.
            continue
        chiave = (materiale, g.localita_codice, len(g.giornate))
        per_chiave.setdefault(chiave, []).append(g)

    # 2. Bin-packing convogli paralleli (Sprint 7.9 MR 10, entry 109).
    #
    # Decisione utente 2026-05-03: "se l'algoritmo crea 3 varianti
    # applicate nello stesso giorno è un bene, ma deve allora creare
    # 3 turni diversi con le proprie giornate specifiche". Cluster A1
    # con date di applicazione SOVRAPPOSTE rappresentano convogli
    # fisici DIVERSI in parallelo — turni separati. Cluster con date
    # disgiunte → varianti calendariali dello stesso turno.
    #
    # Sprint 7.9 MR α: opera DENTRO ogni gruppo per chiave A2 (stessa
    # terna materiale+sede+n_giornate). Cluster di lunghezze diverse
    # sono già in gruppi distinti.
    aggregati: list[GiroAggregato] = []
    for (materiale, localita, _n), giri_cluster in per_chiave.items():
        # Ordina per data minima asc (tutti i cluster hanno stessa
        # lunghezza nel gruppo: niente più tie-break per len).
        giri_ordinati = sorted(giri_cluster, key=_data_partenza_minima)

        # Bin-packing greedy: assegna ogni cluster al primo turno con
        # date di occupazione disgiunte. Se non esiste, apre un turno
        # nuovo.
        turni: list[list[GiroAssegnato]] = []
        date_per_turno: list[set[date]] = []
        for giro in giri_ordinati:
            date_giro = _date_occupazione(giro)
            assegnato = False
            for i, date_t in enumerate(date_per_turno):
                if date_t.isdisjoint(date_giro):
                    turni[i].append(giro)
                    date_per_turno[i].update(date_giro)
                    assegnato = True
                    break
            if not assegnato:
                turni.append([giro])
                date_per_turno.append(date_giro)

        # 3. Per ogni turno, costruisci un GiroAggregato con le sue N
        #    giornate-pattern (tutte coperte per costruzione: i cluster
        #    nel turno hanno tutti stessa lunghezza).
        for cluster_turno in turni:
            canonico = cluster_turno[0]
            n_giornate = len(canonico.giornate)

            giornate_aggregate: list[GiornataAggregata] = []
            for k in range(n_giornate):
                varianti = tuple(
                    _giornata_a_variante(giro.giornate[k])
                    for giro in cluster_turno
                )
                giornate_aggregate.append(
                    GiornataAggregata(numero_giornata=k + 1, varianti=varianti)
                )

            corse_residue_turno: list[CorsaResidua] = []
            incompat_turno: list[IncompatibilitaMateriale] = []
            for giro in cluster_turno:
                corse_residue_turno.extend(giro.corse_residue)
                incompat_turno.extend(giro.incompatibilita_materiale)

            aggregati.append(
                GiroAggregato(
                    localita_codice=localita,
                    materiale_tipo_codice=materiale,
                    giornate=tuple(giornate_aggregate),
                    chiuso=canonico.chiuso,
                    motivo_chiusura=canonico.motivo_chiusura,
                    km_cumulati=canonico.km_cumulati,
                    corse_residue=tuple(corse_residue_turno),
                    incompatibilita_materiale=tuple(incompat_turno),
                    n_cluster_a1=len(cluster_turno),
                )
            )

    # 4. Output ordinato per (materiale, sede, n_giornate desc, data
    #    minima canonico). N_giornate desc → turno "principale" (più
    #    lungo) prima dei suoi pattern di chiusura più corti, a parità
    #    di materiale+sede.
    aggregati.sort(
        key=lambda a: (
            a.materiale_tipo_codice,
            a.localita_codice,
            -len(a.giornate),
            min(
                (d for g in a.giornate for v in g.varianti for d in v.dates_apply),
                default=date.max,
            ),
        )
    )
    return aggregati
