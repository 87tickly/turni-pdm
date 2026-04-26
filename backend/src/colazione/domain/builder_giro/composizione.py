"""Assegnazione regole + rilevamento eventi composizione (Sprint 4.4.4).

Funzioni **pure** che, dati i `Giro` di Sprint 4.4.3 + le regole del
programma materiale, producono `GiroAssegnato`:

1. ``assegna_materiali(giro, regole) → GiroAssegnato``: per ogni
   blocco corsa chiama ``risolvi_corsa()`` (Sprint 4.2). Le corse
   senza regola applicabile finiscono in ``corse_residue``.
   Se una giornata usa più ``materiale_tipo``, registra
   ``incompatibilita_materiale`` (vìola `LOGICA-COSTRUZIONE.md`
   §3.3 punto 3).
2. ``rileva_eventi_composizione(giro_assegnato) → GiroAssegnato``:
   scorre i blocchi assegnati di ogni giornata, calcola delta
   ``numero_pezzi`` tra blocchi consecutivi e inserisce
   ``EventoComposizione`` di tipo ``'aggancio'`` (delta > 0) o
   ``'sgancio'`` (delta < 0) con ``is_validato_utente=False``.
3. ``assegna_e_rileva_eventi(giri, regole) → list[GiroAssegnato]``:
   orchestrator che combina i due passi.

Spec:

- ``docs/PROGRAMMA-MATERIALE.md`` §5 (composizione dinamica: builder
  propone, utente decide).
- ``docs/LOGICA-COSTRUZIONE.md`` §3.3 (vincolo composizione coerente).

Limiti del sub-sprint 4.4.4:

- **Eventi solo intra-giornata**: i delta cross-notte tra giornate
  consecutive del giro multi-giornata NON generano eventi qui.
  L'orchestrator (4.4.5) deciderà se materializzarli.
- **Stazione proposta = origine blocco corrente**: euristica semplice.
  Il pianificatore conferma o sposta in editor giro UI.
- **`RegolaAmbiguaError` bubble up**: la decisione di gestione spetta
  al chiamante (4.4.5 builder business logic).

Il modulo è **DB-agnostic**.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal, Protocol

from colazione.domain.builder_giro.multi_giornata import (
    Giro,
    MotivoChiusura,
)
from colazione.domain.builder_giro.posizionamento import CatenaPosizionata
from colazione.domain.builder_giro.risolvi_corsa import (
    AssegnazioneRisolta,
    risolvi_corsa,
)

# =====================================================================
# Protocol — duck-typing input
# =====================================================================


class _RegolaLike(Protocol):
    """Una regola del programma materiale (riusa lo stesso shape di
    `risolvi_corsa._RegolaLike`)."""

    id: int
    filtri_json: list[Any]
    materiale_tipo_codice: str
    numero_pezzi: int
    priorita: int


# =====================================================================
# Output: blocchi, eventi, giornate, giri
# =====================================================================


TipoEvento = Literal["aggancio", "sgancio"]


@dataclass(frozen=True)
class BloccoAssegnato:
    """Una corsa commerciale + l'assegnazione regola vincente.

    Attributi:
        corsa: oggetto corsa (ORM o dataclass test).
        assegnazione: ``AssegnazioneRisolta`` da ``risolvi_corsa``.
    """

    corsa: Any
    assegnazione: AssegnazioneRisolta


@dataclass(frozen=True)
class EventoComposizione:
    """Aggancio o sgancio rilevato tra due blocchi corsa consecutivi.

    Persiste in DB come `giro_blocco` di tipo ``'aggancio'``/``'sgancio'``
    con ``is_validato_utente=False`` e ``metadata_json`` popolato
    (Sprint 4.4.5 persistenza).

    Attributi:
        tipo: ``'aggancio'`` (delta > 0) o ``'sgancio'`` (delta < 0).
        pezzi_delta: variazione signed di ``numero_pezzi``.
        stazione_proposta: stazione candidata per l'evento (default:
            origine del blocco corrente). Il pianificatore può
            spostarla in UI.
        posizione_dopo_blocco: indice (0-based) del blocco precedente
            nella giornata. L'evento sta tra blocco[i] e blocco[i+1].
        note_builder: spiegazione testuale per UI/tooltip.
        is_validato_utente: ``False`` di default; UI lo mette a
            ``True`` quando il pianificatore conferma.
    """

    tipo: TipoEvento
    pezzi_delta: int
    stazione_proposta: str
    posizione_dopo_blocco: int
    note_builder: str
    is_validato_utente: bool = False


@dataclass(frozen=True)
class CorsaResidua:
    """Una corsa per cui ``risolvi_corsa`` non ha trovato regole."""

    data: date
    corsa: Any


@dataclass(frozen=True)
class IncompatibilitaMateriale:
    """Una giornata del giro usa più di un ``materiale_tipo_codice``.

    Vìola ``LOGICA-COSTRUZIONE.md`` §3.3 punto 3 (composizione coerente
    intra-giornata). Warning per il pianificatore — strict mode lo
    decide nel builder.
    """

    data: date
    tipi_materiale: frozenset[str]


@dataclass(frozen=True)
class GiornataAssegnata:
    """Una giornata: catena posizionata + blocchi assegnati + eventi."""

    data: date
    catena_posizionata: CatenaPosizionata
    blocchi_assegnati: tuple[BloccoAssegnato, ...]
    eventi_composizione: tuple[EventoComposizione, ...] = field(default_factory=tuple)
    materiali_tipo_giornata: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class GiroAssegnato:
    """Output completo: `Giro` (4.4.3) + assegnazioni + warning.

    I campi `localita_codice`, `chiuso`, `motivo_chiusura` ricalcano
    `Giro` per pass-through al chiamante.
    """

    localita_codice: str
    giornate: tuple[GiornataAssegnata, ...]
    chiuso: bool
    motivo_chiusura: MotivoChiusura
    corse_residue: tuple[CorsaResidua, ...] = field(default_factory=tuple)
    incompatibilita_materiale: tuple[IncompatibilitaMateriale, ...] = field(default_factory=tuple)


# =====================================================================
# Funzione 1 — assegna_materiali
# =====================================================================


def assegna_materiali(giro: Giro, regole: Sequence[_RegolaLike]) -> GiroAssegnato:
    """Assegna materiale a ogni corsa del giro chiamando ``risolvi_corsa``.

    Algoritmo:

    1. Per ogni `GiornataGiro`, scorri le corse della catena.
    2. Per ogni corsa: ``risolvi_corsa(corsa, regole, giornata.data)``.
       - Se ``None`` → la corsa va in ``corse_residue`` (warning).
       - Se ``AssegnazioneRisolta`` → blocco assegnato.
       - Se ``RegolaAmbiguaError`` → bubble up (caller decide).
    3. Se la giornata usa > 1 ``materiale_tipo`` → registra
       ``IncompatibilitaMateriale``.
    4. ``eventi_composizione`` resta vuoto (popolato da
       `rileva_eventi_composizione`).

    Args:
        giro: ``Giro`` da Sprint 4.4.3.
        regole: lista regole del programma materiale (caricata
            dal chiamante; nessun lazy-load ORM).

    Returns:
        ``GiroAssegnato`` con assegnazioni + corse residue +
        incompatibilità.

    Raises:
        RegolaAmbiguaError: se una corsa ha regole ambigue
            (re-raise da ``risolvi_corsa``).
    """
    giornate_out: list[GiornataAssegnata] = []
    residue: list[CorsaResidua] = []
    incompat: list[IncompatibilitaMateriale] = []

    for giornata in giro.giornate:
        blocchi: list[BloccoAssegnato] = []
        tipi_materiale: set[str] = set()

        for corsa in giornata.catena_posizionata.catena.corse:
            assegnazione = risolvi_corsa(corsa, regole, giornata.data)
            if assegnazione is None:
                residue.append(CorsaResidua(data=giornata.data, corsa=corsa))
                continue
            blocchi.append(BloccoAssegnato(corsa=corsa, assegnazione=assegnazione))
            tipi_materiale.add(assegnazione.materiale_tipo_codice)

        if len(tipi_materiale) > 1:
            incompat.append(
                IncompatibilitaMateriale(
                    data=giornata.data,
                    tipi_materiale=frozenset(tipi_materiale),
                )
            )

        giornate_out.append(
            GiornataAssegnata(
                data=giornata.data,
                catena_posizionata=giornata.catena_posizionata,
                blocchi_assegnati=tuple(blocchi),
                eventi_composizione=(),
                materiali_tipo_giornata=frozenset(tipi_materiale),
            )
        )

    return GiroAssegnato(
        localita_codice=giro.localita_codice,
        giornate=tuple(giornate_out),
        chiuso=giro.chiuso,
        motivo_chiusura=giro.motivo_chiusura,
        corse_residue=tuple(residue),
        incompatibilita_materiale=tuple(incompat),
    )


# =====================================================================
# Funzione 2 — rileva_eventi_composizione
# =====================================================================


def rileva_eventi_composizione(giro_assegnato: GiroAssegnato) -> GiroAssegnato:
    """Inserisce `EventoComposizione` per ogni delta ``numero_pezzi``
    tra blocchi assegnati consecutivi della stessa giornata.

    Algoritmo (vedi ``PROGRAMMA-MATERIALE.md`` §5.3):

    1. Per ogni giornata, scorre i ``blocchi_assegnati`` mantenendo
       ``prev_pezzi``.
    2. Per ogni blocco, calcola ``delta = curr_pezzi - prev_pezzi``.
    3. Se ``delta != 0``: crea un ``EventoComposizione`` con:
       - ``tipo``: ``'aggancio'`` se delta > 0, ``'sgancio'`` se < 0
       - ``stazione_proposta``: ``corsa.codice_origine`` del blocco
         corrente
       - ``posizione_dopo_blocco``: indice del blocco precedente
       - ``is_validato_utente``: ``False``
    4. Eventi cross-notte tra giornate diverse sono **fuori scope**
       (li gestirà 4.4.5 orchestrator).

    Args:
        giro_assegnato: output di ``assegna_materiali`` (eventi
            ancora vuoti).

    Returns:
        ``GiroAssegnato`` con ``eventi_composizione`` popolati.
        Nuovo oggetto (frozen dataclass via ``dataclasses.replace``).
    """
    giornate_out: list[GiornataAssegnata] = []

    for giornata in giro_assegnato.giornate:
        eventi: list[EventoComposizione] = []
        prev_pezzi: int | None = None

        for i, blocco in enumerate(giornata.blocchi_assegnati):
            curr_pezzi = blocco.assegnazione.numero_pezzi
            if prev_pezzi is not None and curr_pezzi != prev_pezzi:
                delta = curr_pezzi - prev_pezzi
                tipo: TipoEvento = "aggancio" if delta > 0 else "sgancio"
                eventi.append(
                    EventoComposizione(
                        tipo=tipo,
                        pezzi_delta=delta,
                        stazione_proposta=blocco.corsa.codice_origine,
                        posizione_dopo_blocco=i - 1,
                        note_builder=(
                            f"Transizione composizione: {prev_pezzi} → {curr_pezzi} "
                            f"pezzi al blocco {i}."
                        ),
                        is_validato_utente=False,
                    )
                )
            prev_pezzi = curr_pezzi

        giornate_out.append(dataclasses.replace(giornata, eventi_composizione=tuple(eventi)))

    return dataclasses.replace(giro_assegnato, giornate=tuple(giornate_out))


# =====================================================================
# Orchestrator
# =====================================================================


def assegna_e_rileva_eventi(
    giri: Sequence[Giro], regole: Sequence[_RegolaLike]
) -> list[GiroAssegnato]:
    """Pipeline completa: ``assegna_materiali`` + ``rileva_eventi_composizione``
    su tutti i giri in input.

    Equivalente a::

        [rileva_eventi_composizione(assegna_materiali(g, regole)) for g in giri]

    Esposto come funzione separata per chiarezza nel chiamante.
    """
    return [rileva_eventi_composizione(assegna_materiali(g, regole)) for g in giri]


__all__ = [
    "BloccoAssegnato",
    "CorsaResidua",
    "EventoComposizione",
    "GiornataAssegnata",
    "GiroAssegnato",
    "IncompatibilitaMateriale",
    "TipoEvento",
    "assegna_e_rileva_eventi",
    "assegna_materiali",
    "rileva_eventi_composizione",
]
