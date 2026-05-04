"""Sprint 7.9 MR β2-3 — sourcing thread agganci/sganci.

Funzione **pura** che arricchisce gli ``EventoComposizione`` di tutti
i giri di una sede con info descrittive su DA DOVE arrivano i pezzi
agganciati e DOVE vanno quelli sganciati. Non modella ancora
threadID strutturati (= scope MR β2-4) ma popola i campi
``source_descrizione`` / ``dest_descrizione`` / ``capacity_warning``
del dataclass ``EventoComposizione`` per consumo UI.

Algoritmo:

1. **Costruisce indice catene** per (data, sede): per ogni catena di
   ogni giro, registra prima/ultima corsa con (stazione, ora, numero
   treno commerciale).
2. **Per ogni AGGANCIO** (+N pezzi materiale M alla stazione X
   all'ora T):
   - Cerca catene **sorgente** che terminano a X entro [T-15min,
     T-1min], stessa sede, materiale compatibile.
   - Se trovata: ``source_descrizione = "Pezzi da treno {treno}
     (arrivato {stazione} {ora})"``.
   - Se NON trovata: fallback "deposito sede" + check dotazione
     azienda. Se ``pezzi_in_uso[M] >= dotazione[M]`` →
     ``capacity_warning=True`` con descrizione esplicita.
3. **Per ogni SGANCIO** (-N pezzi materiale M alla stazione X
   all'ora T):
   - Cerca catene **destinazione** che partono da X entro [T+1min,
     T+15min] e potrebbero usare il materiale sganciato.
   - Se trovata: ``dest_descrizione = "Pezzi verso treno {treno}
     (riaggancio {stazione} {ora})"``.
   - Se NON trovata: fallback "rientro deposito sede". Le regole
     ``regola_invio_sosta`` (es. invio a Misr) sono scope futuro
     β2-7 — qui usiamo solo il deposito di manutenzione.

Limitazioni note:

- **Sourcing greedy**: la prima catena candidata vince; non gestisce
  conflitti (= due agganci che cercherebbero la stessa catena
  sorgente). Risolto con strategia "first-come" deterministica
  ordinata per ora aggancio crescente.
- **Capacity check semplificato**: confronta count blocchi corsa
  che usano il materiale vs dotazione totale, non istante-per-istante.
  Quello vero è β2-5.
- **Niente FK in DB**: i risultati popolano solo i campi descrittivi
  testuali del dataclass. Le FK strutturate
  (`thread_origine_blocco_id`) arrivano in β2-4.

Il modulo è **DB-agnostic**.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date, time
from typing import Any

from colazione.domain.builder_giro.composizione import (
    EventoComposizione,
    GiornataAssegnata,
    GiroAssegnato,
)


# =====================================================================
# Indici interni
# =====================================================================


@dataclass(frozen=True)
class _CatenaTerminale:
    """Punto di terminazione di una catena (per sourcing aggancio)."""

    data_giorno: date
    stazione: str
    ora: time
    numero_treno: str
    materiali_disponibili: frozenset[str]


@dataclass(frozen=True)
class _CatenaIniziale:
    """Punto di partenza di una catena (per sourcing sgancio)."""

    data_giorno: date
    stazione: str
    ora: time
    numero_treno: str
    materiali_richiesti: frozenset[str]


def _time_to_min(t: time) -> int:
    return t.hour * 60 + t.minute


def _materiali_giornata(g: GiornataAssegnata) -> frozenset[str]:
    """Materiali usati in una giornata (somma blocchi assegnati)."""
    out: set[str] = set()
    for blocco in g.blocchi_assegnati:
        for item in blocco.assegnazione.composizione:
            out.add(item.materiale_tipo_codice)
    return frozenset(out)


def _costruisci_indice_pool(
    giri: Iterable[GiroAssegnato],
) -> tuple[list[_CatenaTerminale], list[_CatenaIniziale]]:
    """Indicizza le catene del pool per data → terminali + iniziali."""
    terminali: list[_CatenaTerminale] = []
    iniziali: list[_CatenaIniziale] = []
    for giro in giri:
        for giornata in giro.giornate:
            corse = giornata.catena_posizionata.catena.corse
            if not corse:
                continue
            materiali = _materiali_giornata(giornata)
            prima = corse[0]
            ultima = corse[-1]
            # Estrai numero treno con safe-cast (può essere None per
            # vuoti generati, anche se qui dovrebbero essere solo
            # commerciali).
            terminali.append(
                _CatenaTerminale(
                    data_giorno=giornata.data,
                    stazione=ultima.codice_destinazione,
                    ora=ultima.ora_arrivo,
                    numero_treno=str(getattr(ultima, "numero_treno", "?")),
                    materiali_disponibili=materiali,
                )
            )
            iniziali.append(
                _CatenaIniziale(
                    data_giorno=giornata.data,
                    stazione=prima.codice_origine,
                    ora=prima.ora_partenza,
                    numero_treno=str(getattr(prima, "numero_treno", "?")),
                    materiali_richiesti=materiali,
                )
            )
    return terminali, iniziali


# =====================================================================
# Sourcing per singolo evento
# =====================================================================


GAP_AGGANCIO_MIN = 1
GAP_AGGANCIO_MAX = 15
GAP_SGANCIO_MIN = 1
GAP_SGANCIO_MAX = 15


def _trova_sorgente_aggancio(
    evento: EventoComposizione,
    ora_aggancio: time,
    data_giorno: date,
    terminali: list[_CatenaTerminale],
    consumati: set[int],
) -> _CatenaTerminale | None:
    """Cerca una catena terminale candidata per fornire i pezzi
    dell'aggancio.

    Vincoli:
    - Stessa stazione di ``evento.stazione_proposta``.
    - Stessa data del giorno.
    - Termina entro [aggancio - GAP_MAX, aggancio - GAP_MIN] minuti.
    - Materiale dell'evento presente in ``materiali_disponibili``.
    - Non già consumata da un altro aggancio (id in ``consumati``).

    Tie-break: catena più recente (= chiusura più vicina all'aggancio).
    """
    aggancio_min = _time_to_min(ora_aggancio)
    candidati: list[tuple[int, _CatenaTerminale]] = []
    for idx, term in enumerate(terminali):
        if idx in consumati:
            continue
        if term.data_giorno != data_giorno:
            continue
        if term.stazione != evento.stazione_proposta:
            continue
        if evento.materiale_tipo_codice not in term.materiali_disponibili:
            continue
        gap = aggancio_min - _time_to_min(term.ora)
        if gap < GAP_AGGANCIO_MIN or gap > GAP_AGGANCIO_MAX:
            continue
        candidati.append((gap, term))
    if not candidati:
        return None
    # Tie-break: gap più piccolo (chiusura più vicina).
    candidati.sort(key=lambda x: x[0])
    return candidati[0][1]


def _trova_destinazione_sgancio(
    evento: EventoComposizione,
    ora_sgancio: time,
    data_giorno: date,
    iniziali: list[_CatenaIniziale],
    consumati: set[int],
) -> _CatenaIniziale | None:
    """Simmetrico: cerca una catena iniziale che riprende i pezzi
    sganciati."""
    sgancio_min = _time_to_min(ora_sgancio)
    candidati: list[tuple[int, _CatenaIniziale]] = []
    for idx, init in enumerate(iniziali):
        if idx in consumati:
            continue
        if init.data_giorno != data_giorno:
            continue
        if init.stazione != evento.stazione_proposta:
            continue
        if evento.materiale_tipo_codice not in init.materiali_richiesti:
            continue
        gap = _time_to_min(init.ora) - sgancio_min
        if gap < GAP_SGANCIO_MIN or gap > GAP_SGANCIO_MAX:
            continue
        candidati.append((gap, init))
    if not candidati:
        return None
    candidati.sort(key=lambda x: x[0])
    return candidati[0][1]


# =====================================================================
# API pubblica
# =====================================================================


def arricchisci_sourcing(
    giri: list[GiroAssegnato],
    sede_codice_breve: str,
    dotazione: dict[str, int | None],
) -> tuple[list[GiroAssegnato], list[str]]:
    """Arricchisce gli ``EventoComposizione`` dei giri con info sourcing.

    Args:
        giri: lista di ``GiroAssegnato`` (output di
            ``assegna_e_rileva_eventi``).
        sede_codice_breve: codice breve sede (es. ``"FIO"``) per le
            descrizioni "Pezzi da deposito FIO" / "Pezzi a deposito FIO".
        dotazione: mappa ``materiale_codice → pezzi_disponibili``.
            ``None`` = capacity illimitata. Materiali assenti dal dict
            = capacity sconosciuta (no warning).

    Returns:
        ``(giri_arricchiti, warnings_list)``.

    Idempotente: chiamare due volte produce stesso risultato (i campi
    ``source_descrizione``/``dest_descrizione`` vengono sovrascritti).
    """
    warnings: list[str] = []
    terminali, iniziali = _costruisci_indice_pool(giri)
    # Tracking idx già "consumati" — evita che 2 agganci puntino alla
    # stessa catena sorgente.
    sorgenti_consumate: set[int] = set()
    destinazioni_consumate: set[int] = set()
    # Tracking pezzi in uso da deposito (fallback) per capacity check
    # MVP: count cumulativo per materiale.
    pezzi_da_deposito: dict[str, int] = {}

    nuovi_giri: list[GiroAssegnato] = []
    for giro in giri:
        nuove_giornate: list[GiornataAssegnata] = []
        for giornata in giro.giornate:
            # Ordina eventi cronologicamente per dare determinismo al
            # consumo di sorgenti (chi aggancia prima vince).
            eventi_ordinati = sorted(
                enumerate(giornata.eventi_composizione),
                key=lambda ie: _ora_evento_blocco(
                    giornata, ie[1].posizione_dopo_blocco
                ),
            )
            nuovi_eventi_per_idx: dict[int, EventoComposizione] = {}
            for orig_idx, ev in eventi_ordinati:
                ora_evento = _ora_evento_blocco(giornata, ev.posizione_dopo_blocco)
                if ev.tipo == "aggancio":
                    sorgente = _trova_sorgente_aggancio(
                        ev,
                        ora_evento,
                        giornata.data,
                        terminali,
                        sorgenti_consumate,
                    )
                    if sorgente is not None:
                        idx_sorgente = next(
                            i for i, t in enumerate(terminali) if t is sorgente
                        )
                        sorgenti_consumate.add(idx_sorgente)
                        descrizione = (
                            f"Pezzi da treno {sorgente.numero_treno} "
                            f"(arrivato {sorgente.stazione} "
                            f"{sorgente.ora.strftime('%H:%M')})"
                        )
                        nuovi_eventi_per_idx[orig_idx] = replace(
                            ev, source_descrizione=descrizione
                        )
                    else:
                        # Fallback: pezzi dal deposito + capacity check.
                        pezzi_da_deposito[ev.materiale_tipo_codice] = (
                            pezzi_da_deposito.get(ev.materiale_tipo_codice, 0)
                            + ev.pezzi_delta
                        )
                        cap = dotazione.get(ev.materiale_tipo_codice)
                        capacity_warn = (
                            cap is not None
                            and pezzi_da_deposito[ev.materiale_tipo_codice] > cap
                        )
                        if capacity_warn:
                            descrizione = (
                                f"Pezzi NON SOURCEABLE — "
                                f"dotazione {cap} ETR esaurita "
                                f"(richiesti {pezzi_da_deposito[ev.materiale_tipo_codice]})"
                            )
                            warnings.append(
                                f"AGGANCIO non risolto a "
                                f"{ev.stazione_proposta} "
                                f"{ora_evento.strftime('%H:%M')} per "
                                f"{ev.materiale_tipo_codice}: dotazione "
                                f"satura ({pezzi_da_deposito[ev.materiale_tipo_codice]}/{cap})"
                            )
                        else:
                            descrizione = (
                                f"Pezzi da deposito {sede_codice_breve}"
                            )
                        nuovi_eventi_per_idx[orig_idx] = replace(
                            ev,
                            source_descrizione=descrizione,
                            capacity_warning=capacity_warn,
                        )
                elif ev.tipo == "sgancio":
                    destinazione = _trova_destinazione_sgancio(
                        ev,
                        ora_evento,
                        giornata.data,
                        iniziali,
                        destinazioni_consumate,
                    )
                    if destinazione is not None:
                        idx_dest = next(
                            i for i, init in enumerate(iniziali) if init is destinazione
                        )
                        destinazioni_consumate.add(idx_dest)
                        descrizione = (
                            f"Pezzi verso treno {destinazione.numero_treno} "
                            f"(riaggancio {destinazione.stazione} "
                            f"{destinazione.ora.strftime('%H:%M')})"
                        )
                    else:
                        descrizione = (
                            f"Pezzi a deposito {sede_codice_breve}"
                        )
                    nuovi_eventi_per_idx[orig_idx] = replace(
                        ev, dest_descrizione=descrizione
                    )

            nuovi_eventi = tuple(
                nuovi_eventi_per_idx.get(i, ev)
                for i, ev in enumerate(giornata.eventi_composizione)
            )
            nuove_giornate.append(replace(giornata, eventi_composizione=nuovi_eventi))
        nuovi_giri.append(replace(giro, giornate=tuple(nuove_giornate)))

    return nuovi_giri, warnings


def _ora_evento_blocco(giornata: GiornataAssegnata, posizione: int) -> time:
    """Ora evento = ora_partenza del blocco corsa SUCCESSIVO alla posizione.

    L'evento sta tra blocco[posizione] e blocco[posizione+1]. Convenzione
    Trenord: si "ancora" all'inizio della nuova corsa (= alla partenza
    del primo treno commerciale dopo il delta composizione).
    """
    blocchi = giornata.blocchi_assegnati
    next_idx = posizione + 1
    if next_idx >= len(blocchi):
        # Edge case: evento dopo l'ultimo blocco → usa l'arrivo
        # dell'ultimo (chiusura giornata).
        next_idx = len(blocchi) - 1
    ora: time = blocchi[next_idx].corsa.ora_partenza
    return ora


__all__ = ["arricchisci_sourcing"]
