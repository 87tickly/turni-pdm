"""Multi-giornata cross-notte (Sprint 4.4.3).

Funzione **pura** che concatena `CatenaPosizionata` di giornate
consecutive in `Giro` multi-giornata, gestendo i giri che
attraversano la mezzanotte senza tornare in deposito.

Spec:

- ``docs/PROGRAMMA-MATERIALE.md`` §6.7 (cross-notte gestito da subito,
  decisione utente "B subito").
- ``docs/LOGICA-COSTRUZIONE.md`` §3.4 (ciclo multi-giornata).

Logica cross-notte:

Una `CatenaPosizionata` (output di Sprint 4.4.2) ha un flag
``chiusa_a_localita``. Se ``True``, il giro chiude in giornata e
diventa un `Giro` di una sola giornata. Se ``False``, il convoglio
fisico **non torna in deposito a mezzanotte**: nella giornata
successiva una catena dovrà partire dalla stazione di arrivo
dell'ultima corsa e dalla stessa località manutenzione.

Chiusura del giro:

1. **Naturale**: l'ultima giornata ha ``chiusa_a_localita=True``.
2. **Max giornate**: si raggiunge ``n_giornate_max`` (forza chiusura,
   warning per il pianificatore — strict flag
   ``no_giro_non_chiuso_a_localita``).
3. **Non chiusa**: nessuna continuazione disponibile e siamo sotto
   ``n_giornate_max`` (warning, il giro resta "appeso").

Limiti del sub-sprint 4.4.3:

- **Niente check km_max_giornaliero**: il dato km/distanza non è
  ancora cablato nelle dataclass dominio. Sarà aggiunto in 4.4.4 o
  4.4.5 quando il builder lavorerà su corse con metadati km.
- **Niente persistenza**: solo dataclass in/out. La traduzione su
  ``models.giri.GiroMateriale`` è in 4.4.5.

Il modulo è **DB-agnostic**.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, timedelta
from typing import Literal

from colazione.domain.builder_giro.posizionamento import CatenaPosizionata

# =====================================================================
# Tipi + Output
# =====================================================================


MotivoChiusura = Literal["naturale", "max_giornate", "non_chiuso"]


@dataclass(frozen=True)
class ParamMultiGiornata:
    """Parametri per la concatenazione multi-giornata.

    Attributi:
        n_giornate_max: numero massimo di giornate per giro (forza
            chiusura). Default 5 (allineato a ciclo Trenord 5+2).
            Il programma materiale ha ``n_giornate_default``: il
            chiamante lo passa qui.
    """

    n_giornate_max: int = 5


_DEFAULT_PARAM = ParamMultiGiornata()


@dataclass(frozen=True)
class GiornataGiro:
    """Una giornata di un `Giro`: data calendaristica + catena posizionata."""

    data: date
    catena_posizionata: CatenaPosizionata


@dataclass(frozen=True)
class Giro:
    """Output multi-giornata del builder pure (DB-agnostic).

    Mappa su ORM ``GiroMateriale + GiroGiornata + GiroVariante +
    GiroBlocco`` in Sprint 4.4.5 (persistenza).

    Attributi:
        localita_codice: codice località manutenzione del giro
            (la stessa per tutte le giornate).
        giornate: tupla ordinata di giornate (G1, G2, ...). Almeno 1.
        chiuso: ``True`` se l'ultima giornata chiude a località
            (``catena_posizionata.chiusa_a_localita=True``). Allineato a
            ``motivo_chiusura == 'naturale'``.
        motivo_chiusura: ``'naturale'`` | ``'max_giornate'`` |
            ``'non_chiuso'``. Utile per pianificatore + strict mode.
    """

    localita_codice: str
    giornate: tuple[GiornataGiro, ...]
    chiuso: bool
    motivo_chiusura: MotivoChiusura


# =====================================================================
# Helpers
# =====================================================================


def _time_to_min(t: time) -> int:
    """``time`` → minuti dall'inizio giornata (per sort deterministico)."""
    return t.hour * 60 + t.minute


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
# Algoritmo top-level
# =====================================================================


def costruisci_giri_multigiornata(
    catene_per_data: dict[date, list[CatenaPosizionata]],
    params: ParamMultiGiornata = _DEFAULT_PARAM,
) -> list[Giro]:
    """Concatena catene posizionate in giri multi-giornata.

    Algoritmo:

    1. Itera sulle date in ordine cronologico.
    2. Per ogni catena non già usata, inizia un nuovo giro.
    3. Estende il giro alla data successiva se:
       - la giornata corrente NON chiude a località
         (``chiusa_a_localita=False``)
       - non si è raggiunto ``n_giornate_max``
       - esiste una catena nella data successiva con stessa località
         e prima corsa che parte dalla stazione di arrivo dell'ultima
         corsa
    4. Determina ``motivo_chiusura`` finale:
       - ``'naturale'`` se l'ultima giornata chiude a località
       - ``'max_giornate'`` se si è forzata chiusura per cap
       - ``'non_chiuso'`` se mancava continuazione (giro appeso)

    Args:
        catene_per_data: mappa ``data → lista catene posizionate``.
            Le catene di una stessa data sono indipendenti tra loro
            (rappresentano convogli diversi).
        params: ``ParamMultiGiornata``.

    Returns:
        Lista di ``Giro``. L'ordine segue la data di inizio + l'ora
        della prima corsa (determinismo).

    Esempi:
        Mappa vuota → nessun giro:

        >>> costruisci_giri_multigiornata({})
        []
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

            # Loop di estensione cross-notte
            while True:
                ultima_g = giornate[-1]
                if ultima_g.catena_posizionata.chiusa_a_localita:
                    break
                if len(giornate) >= params.n_giornate_max:
                    break

                d_prossima = d_inizio + timedelta(days=len(giornate))
                if d_prossima not in catene_per_data:
                    break

                ultima_corsa = ultima_g.catena_posizionata.catena.corse[-1]
                staz_arrivo = ultima_corsa.codice_destinazione

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

            # Determina motivo chiusura
            chiuso = giornate[-1].catena_posizionata.chiusa_a_localita
            motivo: MotivoChiusura
            if chiuso:
                motivo = "naturale"
            elif len(giornate) >= params.n_giornate_max:
                motivo = "max_giornate"
            else:
                motivo = "non_chiuso"

            giri.append(
                Giro(
                    localita_codice=cat_pos.localita_codice,
                    giornate=tuple(giornate),
                    chiuso=chiuso,
                    motivo_chiusura=motivo,
                )
            )

    return giri
