"""Multi-giornata cross-notte (Sprint 4.4.3 → esteso Sprint 5.4 con
cumulo km + trigger km_max_ciclo → esteso Sprint 7.5 con clustering A1).

Funzione **pura** che concatena `CatenaPosizionata` di giornate
consecutive in `Giro` multi-giornata, gestendo i giri che
attraversano la mezzanotte senza tornare in deposito; e applica un
clustering A1-strict per fondere Giri con sequenza identica in 1 unico
giro canonico con ``dates_apply`` unito (refactor bug 5).

Spec:

- ``docs/PROGRAMMA-MATERIALE.md`` §6.7 (cross-notte gestito da subito,
  decisione utente "B subito").
- ``docs/LOGICA-COSTRUZIONE.md`` §3.4 (ciclo multi-giornata).
- ``docs/SPRINT-5-RIPENSAMENTO.md`` §5.4 (km cumulati + trigger).
- ``docs/MODELLO-DATI.md`` §LIV 2 (giornata-tipo astratta + varianti
  per pattern calendario; bug 5 chiude la divergenza tra
  "giornata=data" e "giornata-tipo del ciclo").

Logica cross-notte:

Una `CatenaPosizionata` (output di posizionamento) ha un flag
``chiusa_a_localita``. Se ``True``, il giro chiude in giornata e
diventa un `Giro` di una sola giornata. Se ``False``, il convoglio
fisico **non torna in deposito a mezzanotte**: nella giornata
successiva una catena dovrà partire dalla stazione di arrivo
dell'ultima corsa e dalla stessa località manutenzione.

Chiusura del giro:

1. **Naturale**: l'ultima giornata ha ``chiusa_a_localita=True``.
2. **Max giornate**: si raggiunge ``n_giornate_max`` (forza chiusura,
   warning per il pianificatore — strict flag ``no_giro_appeso``).
3. **Km cap** (Sprint 5.4): si raggiunge ``km_max_ciclo`` cumulativo.
   Il convoglio sta in linea da troppi km, va a manutenzione (anche
   se la giornata non chiude geograficamente).
4. **Non chiusa**: nessuna continuazione disponibile e siamo sotto
   tutti i cap (warning, il giro resta "appeso").

Cumulo km (Sprint 5.4):

Ogni giornata aggiunge la somma dei `km_tratta` delle sue corse al
totale del giro. La logica è duck-typed: se la corsa non ha l'attributo
``km_tratta`` o vale ``None``, contribuisce 0. Coerente con il dato
PdE: ``CorsaCommerciale.km_tratta: Decimal | None``.

Clustering A1 (Sprint 7.5, refactor bug 5):

Dopo il building cross-notte, l'output viene clusterizzato per chiave
A1-strict — due Giri con stessa località e stessa sequenza di
``(numero_treno, ora_partenza, ora_arrivo, codice_origine,
codice_destinazione)`` per ogni corsa di ogni giornata (più
``vuoto_testa``/``vuoto_coda`` identici) sono lo stesso pattern e si
fondono in 1 Giro canonico. Il campo ``GiornataGiro.dates_apply``
contiene tutte le date in cui la giornata-tipo si applica (= unione
delle date dei filoni del cluster). Risolve il bug 5 (giornata-data
collassata su giornata-tipo del ciclo).

Limiti residui:

- **Niente identificazione corsa di rientro programmata**: quando si
  raggiunge ``km_cap`` o ``max_giornate`` e la giornata corrente non
  arriva alla sede, il giro resta "non chiuso geograficamente".
  L'estensione "cerca attivamente una corsa che riporti il treno
  verso la whitelist sede" è scope futuro (raffinamento Sub 5.4 v2).
- **Niente persistenza**: solo dataclass in/out. La traduzione su
  ``models.giri.GiroMateriale`` resta in `persister.py`.

Il modulo è **DB-agnostic**.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time, timedelta
from typing import Any, Literal

from colazione.domain.builder_giro.posizionamento import CatenaPosizionata

# =====================================================================
# Tipi + Output
# =====================================================================


MotivoChiusura = Literal["naturale", "max_giornate", "km_cap", "non_chiuso"]


@dataclass(frozen=True)
class ParamMultiGiornata:
    """Parametri per la concatenazione multi-giornata.

    Sprint 5.6 (refactor algoritmo): la chiusura del giro è dinamica.
    Il loop estende cross-notte FINCHÉ NON valgono ENTRAMBE le
    condizioni "km_cap_raggiunto AND vicino_sede" — `chiusa_a_localita`
    di una singola giornata NON ferma il loop (resta come info).

    Attributi:
        n_giornate_max: safety net per evitare loop infiniti pathologici
            (es. dato corrupto, calendario ciclico). Default 30. Il
            vero termine del giro sono ``km_max_ciclo + vicino_sede``.
        km_max_ciclo: km cumulati massimi sul ciclo intero. ``None``
            = nessun cap (allora il giro chiude solo per safety o
            assenza di continuazione). Tipici 5000-10000.
        whitelist_sede: codici stazione "vicine alla sede manutentiva"
            del programma. Quando l'ultima corsa di una giornata arriva
            in una di queste, il treno è "vicino sede" (criterio per
            chiusura naturale completa).
    """

    n_giornate_max: int = 5
    km_max_ciclo: float | None = None
    whitelist_sede: frozenset[str] = field(default_factory=frozenset)


_DEFAULT_PARAM = ParamMultiGiornata()


@dataclass(frozen=True)
class GiornataGiro:
    """Una giornata di un `Giro`: data canonica + catena posizionata + dates_apply.

    Sprint 7.5 (refactor bug 5): aggiunto ``dates_apply`` per
    rappresentare tutte le date in cui questa giornata-tipo del ciclo
    si applica. Il clustering A1 fonde Giri-tentativo con sequenza
    identica e popola ``dates_apply`` con l'unione delle date dei
    filoni del cluster.

    Attributi:
        data: data canonica della giornata. Per i Giri prodotti dal
            clustering è la prima data del cluster (deterministica);
            per i Giri-tentativo pre-cluster è la data calendaristica
            singola.
        catena_posizionata: la catena (corse + vuoti) della giornata.
            Per i Giri post-cluster è la catena del filone canonico —
            in A1-strict tutti i filoni del cluster hanno catene
            identiche, quindi la scelta è inessenziale.
        dates_apply: tupla ordinata di date in cui la giornata-tipo si
            applica. Vuota = non popolata (consumer usa
            ``dates_apply_or_data``). Popolata dal clustering con la
            lista completa.
    """

    data: date
    catena_posizionata: CatenaPosizionata
    dates_apply: tuple[date, ...] = ()

    @property
    def dates_apply_or_data(self) -> tuple[date, ...]:
        """Date applicabili, fallback a ``(data,)`` se non popolato.

        Pre-clustering (output di ``_costruisci_giri_per_data``) il
        campo è vuoto e il consumer ottiene la singola ``data``
        calendaristica. Post-clustering il campo contiene tutte le
        date del cluster ordinate.
        """
        return self.dates_apply if self.dates_apply else (self.data,)


@dataclass(frozen=True)
class Giro:
    """Output multi-giornata del builder pure (DB-agnostic).

    Mappa su ORM ``GiroMateriale + GiroGiornata + GiroBlocco`` in
    `persister.py` (Sprint 7.7 MR 3: ``GiroVariante`` rimosso).

    Attributi:
        localita_codice: codice località manutenzione del giro
            (la stessa per tutte le giornate).
        giornate: tupla ordinata di giornate (G1, G2, ...). Almeno 1.
        chiuso: ``True`` se l'ultima giornata chiude a località
            (``catena_posizionata.chiusa_a_localita=True``). Allineato a
            ``motivo_chiusura == 'naturale'``.
        motivo_chiusura: ``'naturale'`` | ``'max_giornate'`` |
            ``'km_cap'`` | ``'non_chiuso'``. Utile per pianificatore +
            strict mode.
        km_cumulati: somma dei ``km_tratta`` di tutte le corse di tutte
            le giornate (Sprint 5.4). Corse senza ``km_tratta``
            contribuiscono 0. Float per semplicità (l'ORM mantiene
            Decimal).
    """

    localita_codice: str
    giornate: tuple[GiornataGiro, ...]
    chiuso: bool
    motivo_chiusura: MotivoChiusura
    km_cumulati: float = 0.0


# =====================================================================
# Helpers
# =====================================================================


def _time_to_min(t: time) -> int:
    """``time`` → minuti dall'inizio giornata (per sort deterministico)."""
    return t.hour * 60 + t.minute


def _km_giornata(cat_pos: CatenaPosizionata) -> float:
    """Somma ``km_tratta`` delle corse di una giornata.

    Duck-typed: corse senza ``km_tratta`` o con valore ``None``
    contribuiscono 0. Coerente con il dato PdE (
    ``CorsaCommerciale.km_tratta: Decimal | None``).
    """
    total = 0.0
    for c in cat_pos.catena.corse:
        km = getattr(c, "km_tratta", None)
        if km is not None:
            total += float(km)
    return total


def _trova_continuazione(
    catene_data: list[CatenaPosizionata],
    visitate: set[int],
    staz_arrivo: str,
    localita_codice: str,
) -> CatenaPosizionata | None:
    """Trova una catena nella data successiva che continua il giro.

    Vincoli:
    - non già visitata
    - **stessa località manutenzione** (è lo stesso convoglio fisico)
    - prima corsa parte da ``staz_arrivo`` (stazione di arrivo
      dell'ultima corsa della giornata precedente)

    Tie-break: prima per ``ora_partenza`` della prima corsa
    (deterministico, scelta del candidato che parte prima).
    """
    candidati = [
        c
        for c in catene_data
        if id(c) not in visitate
        and c.localita_codice == localita_codice
        and c.catena.corse[0].codice_origine == staz_arrivo
    ]
    if not candidati:
        return None
    return min(
        candidati,
        key=lambda c: _time_to_min(c.catena.corse[0].ora_partenza),
    )


# =====================================================================
# Helpers chiave A1 — Sprint 7.5 (refactor bug 5)
# =====================================================================


def _corsa_key(c: Any) -> tuple[Any, ...]:
    """Chiave A1-strict di una corsa commerciale.

    Include i 5 campi che identificano univocamente la corsa nella
    sequenza del giro: ``numero_treno``, ``codice_origine``,
    ``codice_destinazione``, ``ora_partenza``, ``ora_arrivo``. Due
    corse con la stessa chiave sono considerate "la stessa fase" del
    pattern del giro.

    Decisione utente A1 (vedi TN-UPDATE 2026-04-30): criterio strict —
    una corsa di differenza fra due Giri li mantiene distinti.
    """
    return (
        str(getattr(c, "numero_treno", "") or ""),
        c.codice_origine,
        c.codice_destinazione,
        _time_to_min(c.ora_partenza),
        _time_to_min(c.ora_arrivo),
    )


def _vuoto_key(v: Any) -> tuple[Any, ...] | None:
    """Chiave A1-strict di un vuoto tecnico testa/coda (o None).

    Inclusi: stazioni, orari, motivo, flag ``cross_notte_giorno_precedente``.
    Due vuoti diversi mantengono i Giri distinti — coerente con
    ``A1`` strict (i vuoti sono inferenze del builder, ma la differenza
    di motivo/orario indica una decisione operativa diversa).
    """
    if v is None:
        return None
    return (
        v.codice_origine,
        v.codice_destinazione,
        _time_to_min(v.ora_partenza),
        _time_to_min(v.ora_arrivo),
        getattr(v, "motivo", None),
        getattr(v, "cross_notte_giorno_precedente", False),
    )


def _giornata_key(gg: GiornataGiro) -> tuple[Any, ...]:
    """Chiave A1-strict di una giornata: vuoto_testa + corse + vuoto_coda."""
    cat = gg.catena_posizionata
    return (
        _vuoto_key(cat.vuoto_testa),
        tuple(_corsa_key(c) for c in cat.catena.corse),
        _vuoto_key(cat.vuoto_coda),
    )


def _chiave_a1_giro(g: Giro) -> tuple[Any, ...]:
    """Chiave A1-strict di un Giro: località + sequenza canonica per giornata.

    Due Giri con la stessa chiave hanno **identica** sequenza di corse
    e vuoti per **ogni** giornata. ``_cluster_giri_a1`` li fonde in 1
    Giro canonico con ``dates_apply`` unito.
    """
    return (
        g.localita_codice,
        tuple(_giornata_key(gg) for gg in g.giornate),
    )


# =====================================================================
# Clustering A1 — Sprint 7.5 (refactor bug 5)
# =====================================================================


def _cluster_giri_a1(giri_tentativi: list[Giro]) -> list[Giro]:
    """Cluster A1: fonde Giri-tentativo con sequenza identica.

    Per ogni gruppo di Giri con la stessa ``_chiave_a1_giro``:

    1. Sceglie come canonico il giro con la data di partenza minima
       (deterministico).
    2. Costruisce un nuovo ``Giro`` con le stesse giornate del canonico,
       ma popolando ``GiornataGiro.dates_apply`` con l'unione ordinata
       delle date che cadono in posizione k nei filoni del cluster.

    In A1 strict tutti i filoni del cluster hanno catene identiche
    posizione per posizione, quindi:

    - ``catena_posizionata`` del canonico è rappresentativa di tutti
    - ``chiuso``, ``motivo_chiusura``, ``km_cumulati`` sono uguali

    Output ordinato per data della prima giornata del giro (determinismo).
    """
    if not giri_tentativi:
        return []

    cluster_map: dict[tuple[Any, ...], list[Giro]] = {}
    for g in giri_tentativi:
        k = _chiave_a1_giro(g)
        cluster_map.setdefault(k, []).append(g)

    out: list[Giro] = []
    for _chiave, giri_cluster in cluster_map.items():
        canonico = min(giri_cluster, key=lambda g: g.giornate[0].data)
        n_g = len(canonico.giornate)

        nuove_giornate: list[GiornataGiro] = []
        for k_idx in range(n_g):
            dates_apply_k = tuple(
                sorted({g.giornate[k_idx].data for g in giri_cluster})
            )
            gg_canonico = canonico.giornate[k_idx]
            nuove_giornate.append(
                GiornataGiro(
                    data=gg_canonico.data,
                    catena_posizionata=gg_canonico.catena_posizionata,
                    dates_apply=dates_apply_k,
                )
            )

        out.append(
            Giro(
                localita_codice=canonico.localita_codice,
                giornate=tuple(nuove_giornate),
                chiuso=canonico.chiuso,
                motivo_chiusura=canonico.motivo_chiusura,
                km_cumulati=canonico.km_cumulati,
            )
        )

    out.sort(key=lambda g: g.giornate[0].data)
    return out


# =====================================================================
# Algoritmo top-level
# =====================================================================


def _costruisci_giri_per_data(
    catene_per_data: dict[date, list[CatenaPosizionata]],
    params: ParamMultiGiornata,
) -> list[Giro]:
    """Pre-cluster: costruisce un ``Giro`` per ogni data di partenza.

    Produce **Giri-tentativo** ognuno con ``GiornataGiro.dates_apply=()``
    (la data canonica è la singola data calendaristica). Il clustering
    A1 in `_cluster_giri_a1` fonde i Giri equivalenti.

    Algoritmo invariato dal Sprint 5.6 (cross-notte + km_cap dinamico
    + safety net).
    """
    if not catene_per_data:
        return []

    date_ordinate = sorted(catene_per_data.keys())
    visitate: set[int] = set()
    giri: list[Giro] = []

    for d_inizio in date_ordinate:
        # Sort deterministico delle catene del giorno per ora di prima
        # partenza (FIFO sui convogli che entrano in servizio prima).
        catene_data = sorted(
            catene_per_data[d_inizio],
            key=lambda c: _time_to_min(c.catena.corse[0].ora_partenza),
        )

        for cat_pos in catene_data:
            if id(cat_pos) in visitate:
                continue

            giornate: list[GiornataGiro] = [GiornataGiro(data=d_inizio, catena_posizionata=cat_pos)]
            visitate.add(id(cat_pos))
            km_cumulati = _km_giornata(cat_pos)

            # Loop di estensione cross-notte. Sprint 5.6: due semantiche
            # selezionate da `km_max_ciclo`:
            #
            # - **Modo dinamico** (`km_max_ciclo` definito): estende
            #   SEMPRE finché km_cap raggiunto AND vicino_sede (chiusura
            #   ideale). `chiusa_a_localita` di una giornata NON ferma
            #   il loop (resta come metadato per persister/Feature 4).
            #
            # - **Modo legacy** (`km_max_ciclo` None): backward compat
            #   per test puri pre-Sprint 5.6 — break su
            #   `chiusa_a_localita=True`. In produzione i programmi
            #   COLAZIONE settano sempre `km_max_ciclo` → modo dinamico.
            modo_dinamico = params.km_max_ciclo is not None

            while True:
                ultima_g = giornate[-1]
                ultima_corsa = ultima_g.catena_posizionata.catena.corse[-1]
                staz_arrivo = ultima_corsa.codice_destinazione

                if modo_dinamico:
                    km_cap_raggiunto = km_cumulati >= float(params.km_max_ciclo or 0.0)
                    vicino_sede = staz_arrivo in params.whitelist_sede
                    # Chiusura ideale: entrambe le condizioni
                    if km_cap_raggiunto and vicino_sede:
                        break
                else:
                    # Modo legacy: break su chiusa_a_localita
                    if ultima_g.catena_posizionata.chiusa_a_localita:
                        break

                # Safety net per loop infiniti pathologici (vale per
                # entrambi i modi)
                if len(giornate) >= params.n_giornate_max:
                    break

                d_prossima = d_inizio + timedelta(days=len(giornate))
                if d_prossima not in catene_per_data:
                    break

                prossima = _trova_continuazione(
                    catene_per_data[d_prossima],
                    visitate,
                    staz_arrivo,
                    cat_pos.localita_codice,
                )
                if prossima is None:
                    break

                giornate.append(GiornataGiro(data=d_prossima, catena_posizionata=prossima))
                visitate.add(id(prossima))
                km_cumulati += _km_giornata(prossima)

            # Determina motivo chiusura.
            #
            # Modo dinamico (km_max_ciclo definito):
            # - naturale     = km_cap raggiunto AND vicino_sede (ideale)
            # - km_cap       = km_cap raggiunto MA fuori sede (sub-ottimale)
            # - max_giornate = safety net hit
            # - non_chiuso   = no continuazione disponibile pre-cap
            #
            # Modo legacy (km_max_ciclo=None):
            # - naturale     = ultima giornata chiude geograficamente a sede
            # - max_giornate = safety net hit
            # - non_chiuso   = no continuazione disponibile
            ultima_corsa_finale = giornate[-1].catena_posizionata.catena.corse[-1]
            staz_arrivo_finale = ultima_corsa_finale.codice_destinazione

            motivo: MotivoChiusura
            if modo_dinamico:
                km_cap_raggiunto = km_cumulati >= float(params.km_max_ciclo or 0.0)
                vicino_sede = staz_arrivo_finale in params.whitelist_sede
                if km_cap_raggiunto and vicino_sede:
                    motivo = "naturale"
                elif km_cap_raggiunto:
                    motivo = "km_cap"
                elif len(giornate) >= params.n_giornate_max:
                    motivo = "max_giornate"
                else:
                    motivo = "non_chiuso"
            else:
                # Modo legacy
                chiusa_geo = giornate[-1].catena_posizionata.chiusa_a_localita
                if chiusa_geo:
                    motivo = "naturale"
                elif len(giornate) >= params.n_giornate_max:
                    motivo = "max_giornate"
                else:
                    motivo = "non_chiuso"
            chiuso = motivo == "naturale"

            giri.append(
                Giro(
                    localita_codice=cat_pos.localita_codice,
                    giornate=tuple(giornate),
                    chiuso=chiuso,
                    motivo_chiusura=motivo,
                    km_cumulati=km_cumulati,
                )
            )

    return giri


def costruisci_giri_multigiornata(
    catene_per_data: dict[date, list[CatenaPosizionata]],
    params: ParamMultiGiornata = _DEFAULT_PARAM,
) -> list[Giro]:
    """Concatena catene posizionate in giri multi-giornata + clustering A1.

    Pipeline (Sprint 7.5, refactor bug 5):

    1. ``_costruisci_giri_per_data``: produce un ``Giro`` per ogni data
       di partenza, concatenando cross-notte (logica Sprint 5.6
       invariata: km_cap dinamico, whitelist sede, safety net).
    2. ``_cluster_giri_a1``: fonde i Giri-tentativo con chiave A1
       identica in 1 ``Giro`` canonico per cluster, con
       ``GiornataGiro.dates_apply`` popolato dall'unione delle date
       dei filoni del cluster.

    Conseguenza per il bug 5: dove il vecchio algoritmo produceva N
    Giri uno per data calendaristica (ognuno con 1 sola variante con
    ``validita_dates_apply_json`` "intersezione menzogna"), ora produce
    M ≤ N Giri canonici, ciascuno rappresentativo di un pattern unico
    di sequenza, con ``dates_apply`` reali ottenuti per costruzione.

    Args:
        catene_per_data: mappa ``data → lista catene posizionate``.
            Le catene di una stessa data sono indipendenti tra loro
            (rappresentano convogli diversi).
        params: ``ParamMultiGiornata``.

    Returns:
        Lista di ``Giro`` post-cluster, ordinata per data della prima
        giornata. Ogni ``GiornataGiro.dates_apply`` è popolato (≥ 1
        elemento). Equivalenza A1: due Giri di output non hanno mai la
        stessa ``_chiave_a1_giro``.

    Esempi:
        Mappa vuota → nessun giro:

        >>> costruisci_giri_multigiornata({})
        []
    """
    giri_tentativi = _costruisci_giri_per_data(catene_per_data, params)
    return _cluster_giri_a1(giri_tentativi)
