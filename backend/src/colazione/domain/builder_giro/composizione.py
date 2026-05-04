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
    ComposizioneItem,
    IsAccoppiamentoAmmesso,
    risolvi_corsa,
)

# =====================================================================
# Protocol — duck-typing input
# =====================================================================


class _RegolaLike(Protocol):
    """Una regola del programma materiale (riusa lo stesso shape di
    `risolvi_corsa._RegolaLike`, Sprint 5.5)."""

    id: int
    filtri_json: list[Any]
    composizione_json: list[Any]
    is_composizione_manuale: bool
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
    con ``is_validato_utente=False`` e ``metadata_json`` popolato.

    Sprint 5.5: l'evento ora identifica esplicitamente **quale**
    materiale entra/esce (``materiale_tipo_codice``). Una transizione
    da ``[526]`` a ``[526, 425]`` genera un evento aggancio del 425.
    Una transizione swap (``[526]`` → ``[425]``) genera 2 eventi:
    sgancio del 526 + aggancio del 425.

    Attributi:
        tipo: ``'aggancio'`` (delta > 0) o ``'sgancio'`` (delta < 0).
        materiale_tipo_codice: il rotabile coinvolto nell'evento
            (Sprint 5.5).
        pezzi_delta: variazione signed di ``n_pezzi`` per quel
            materiale.
        stazione_proposta: stazione candidata per l'evento (default:
            origine del blocco corrente).
        posizione_dopo_blocco: indice (0-based) del blocco precedente
            nella giornata. L'evento sta tra blocco[i] e blocco[i+1].
        note_builder: spiegazione testuale per UI/tooltip.
        is_validato_utente: ``False`` di default; UI lo mette a
            ``True`` quando il pianificatore conferma.
    """

    tipo: TipoEvento
    materiale_tipo_codice: str
    pezzi_delta: int
    stazione_proposta: str
    posizione_dopo_blocco: int
    note_builder: str
    is_validato_utente: bool = False
    # Sprint 7.9 MR β2-3: sourcing descrittivo per UI.
    # ``source_descrizione``: per AGGANCIO, da dove arrivano i pezzi.
    # Esempi: "Pezzi da treno 24812 (arrivato CENTRALE 09:55)",
    # "Pezzi da deposito FIO" (= no sourcing trovato, fallback dotazione),
    # "Pezzi NON SOURCEABLE — dotazione satura" (= warning capacity).
    # Per SGANCIO: ``None`` (l'aggancio è il caso interessante).
    source_descrizione: str | None = None
    # ``dest_descrizione``: per SGANCIO, dove vanno i pezzi sganciati.
    # Esempi: "Pezzi a sosta MISR (regola programma)",
    # "Pezzi verso treno 24820 (riaggancio CENTRALE 11:30)",
    # "Pezzi orfani — riassegnazione manuale necessaria" (warning).
    # Per AGGANCIO: ``None``.
    dest_descrizione: str | None = None
    # ``capacity_warning``: True se il sourcing ha violato la dotazione
    # azienda (es. richiesti più ETR526 di quanti l'azienda ne ha).
    # UI evidenzia in rosso.
    capacity_warning: bool = False


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
    """Una giornata: catena posizionata + blocchi assegnati + eventi.

    Sprint 7.5 (refactor bug 5 MR 2): aggiunto ``dates_apply`` come
    pass-through di ``GiornataGiro.dates_apply``. Rappresenta tutte le
    date in cui la giornata-tipo del ciclo si applica nel calendario.
    Default ``()`` per backward-compatibility con costruzioni dirette
    nei test pre-cluster (consumer usa ``dates_apply_or_data``).
    """

    data: date
    catena_posizionata: CatenaPosizionata
    blocchi_assegnati: tuple[BloccoAssegnato, ...]
    eventi_composizione: tuple[EventoComposizione, ...] = field(default_factory=tuple)
    materiali_tipo_giornata: frozenset[str] = field(default_factory=frozenset)
    dates_apply: tuple[date, ...] = ()

    @property
    def dates_apply_or_data(self) -> tuple[date, ...]:
        """Date applicabili, fallback a ``(data,)`` se non popolato.

        Specchio di ``GiornataGiro.dates_apply_or_data``: pre-cluster
        torna ``(data,)`` (singola data calendaristica), post-cluster
        torna l'intero set di date in cui la giornata-tipo si applica.
        """
        return self.dates_apply if self.dates_apply else (self.data,)


@dataclass(frozen=True)
class GiroAssegnato:
    """Output completo: `Giro` (4.4.3) + assegnazioni + warning.

    I campi `localita_codice`, `chiuso`, `motivo_chiusura`,
    `km_cumulati` ricalcano `Giro` per pass-through al chiamante.
    """

    localita_codice: str
    giornate: tuple[GiornataAssegnata, ...]
    chiuso: bool
    motivo_chiusura: MotivoChiusura
    km_cumulati: float = 0.0
    corse_residue: tuple[CorsaResidua, ...] = field(default_factory=tuple)
    incompatibilita_materiale: tuple[IncompatibilitaMateriale, ...] = field(default_factory=tuple)


# =====================================================================
# Funzione 1 — assegna_materiali
# =====================================================================


def assegna_materiali(
    giro: Giro,
    regole: Sequence[_RegolaLike],
    is_accoppiamento_ammesso: IsAccoppiamentoAmmesso | None = None,
    vincoli_inviolabili: Sequence[Any] = (),
    stazioni_lookup: dict[str, str] | None = None,
) -> GiroAssegnato:
    """Assegna composizione a ogni corsa del giro chiamando ``risolvi_corsa``.

    Algoritmo:

    1. Per ogni `GiornataGiro`, scorri le corse della catena.
    2. Per ogni corsa: ``risolvi_corsa(corsa, regole, giornata.data,
       is_accoppiamento_ammesso)``.
       - Se ``None`` → la corsa va in ``corse_residue`` (warning).
       - Se ``AssegnazioneRisolta`` → blocco assegnato.
       - Se ``RegolaAmbiguaError`` o ``ComposizioneNonAmmessaError`` →
         bubble up (caller decide).
    3. ``materiali_tipo_giornata`` = unione di tutti i materiali usati
       da tutte le composizioni della giornata (Sprint 5.5).
       ``IncompatibilitaMateriale`` viene registrata se l'**unione**
       supera 1 elemento. Una composizione doppia ``[526, 425]`` su
       una corsa NON è incompatibile in sé (è una doppia voluta);
       diventa incompatibilità solo se in altri blocchi della stessa
       giornata appare ``[E464]`` o simili.
    4. ``eventi_composizione`` resta vuoto (popolato da
       `rileva_eventi_composizione`).

    Args:
        giro: ``Giro`` da multi-giornata.
        regole: lista regole del programma materiale (caricata
            dal chiamante; nessun lazy-load ORM).
        is_accoppiamento_ammesso: callback opzionale per validare le
            composizioni doppie (Sprint 5.5).

    Returns:
        ``GiroAssegnato`` con assegnazioni + corse residue +
        incompatibilità.

    Raises:
        RegolaAmbiguaError: se una corsa ha regole ambigue.
        ComposizioneNonAmmessaError: se una composizione viola gli
            accoppiamenti ammessi (Sprint 5.5).
    """
    giornate_out: list[GiornataAssegnata] = []
    residue: list[CorsaResidua] = []
    incompat: list[IncompatibilitaMateriale] = []

    for giornata in giro.giornate:
        blocchi: list[BloccoAssegnato] = []
        tipi_materiale: set[str] = set()

        for corsa in giornata.catena_posizionata.catena.corse:
            assegnazione = risolvi_corsa(
                corsa,
                regole,
                giornata.data,
                is_accoppiamento_ammesso,
                vincoli_inviolabili=vincoli_inviolabili,
                stazioni_lookup=stazioni_lookup,
            )
            if assegnazione is None:
                residue.append(CorsaResidua(data=giornata.data, corsa=corsa))
                continue
            blocchi.append(BloccoAssegnato(corsa=corsa, assegnazione=assegnazione))
            # Sprint 5.5: unione di tutti i materiali della composizione.
            tipi_materiale.update(assegnazione.materiali_codici)

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
                # Sprint 7.5 (bug 5 MR 2): pass-through del clustering A1.
                # Pre-cluster `giornata.dates_apply == ()`, post-cluster
                # contiene tutte le date in cui questa giornata-tipo si
                # applica.
                dates_apply=giornata.dates_apply,
            )
        )

    return GiroAssegnato(
        localita_codice=giro.localita_codice,
        giornate=tuple(giornate_out),
        chiuso=giro.chiuso,
        motivo_chiusura=giro.motivo_chiusura,
        km_cumulati=giro.km_cumulati,
        corse_residue=tuple(residue),
        incompatibilita_materiale=tuple(incompat),
    )


# =====================================================================
# Funzione 2 — rileva_eventi_composizione
# =====================================================================


def _composizione_to_dict(
    composizione: tuple[ComposizioneItem, ...],
) -> dict[str, int]:
    """Converte una composizione in mapping ``{materiale_codice: n_pezzi}``.

    Sprint 5.5: serve a rilevare delta per-tipo. Se un materiale appare
    2+ volte nella tupla (improbabile dopo Pydantic ma non vietato),
    le quantità si sommano.
    """
    out: dict[str, int] = {}
    for item in composizione:
        out[item.materiale_tipo_codice] = out.get(item.materiale_tipo_codice, 0) + item.n_pezzi
    return out


def rileva_eventi_composizione(giro_assegnato: GiroAssegnato) -> GiroAssegnato:
    """Inserisce `EventoComposizione` per ogni delta di composizione
    per-materiale tra blocchi assegnati consecutivi della stessa
    giornata (Sprint 5.5 — riscritto).

    Algoritmo:

    1. Per ogni giornata, scorre i ``blocchi_assegnati`` mantenendo
       il dict ``prev_per_tipo: {codice: n_pezzi}``.
    2. Per ogni blocco, calcola ``curr_per_tipo`` analogo.
    3. Per ogni materiale in ``prev_keys ∪ curr_keys``:
       - ``delta = curr.get(m, 0) - prev.get(m, 0)``
       - se ``delta > 0``: evento ``aggancio`` per il materiale m
       - se ``delta < 0``: evento ``sgancio`` per il materiale m
       - se ``delta == 0``: niente evento

       Ordine eventi per blocco: prima sganci poi agganci (così si
       svuota il convoglio prima di rimettere materiali nuovi).
       Materiali ordinati lex per determinismo.

    Esempi:

    - ``[526]`` → ``[526, 425]``: 1 evento aggancio 425 (+1 pezzo)
    - ``[526, 425]`` → ``[526]``: 1 evento sgancio 425 (-1 pezzo)
    - ``[526]`` → ``[526, 526]``: 1 evento aggancio 526 (+1 pezzo)
      (raddoppio doppia)
    - ``[526]`` → ``[425]``: 2 eventi (sgancio 526, aggancio 425, swap)

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
        prev_per_tipo: dict[str, int] = {}

        for i, blocco in enumerate(giornata.blocchi_assegnati):
            curr_per_tipo = _composizione_to_dict(blocco.assegnazione.composizione)
            if i > 0:
                # Calcola delta per ogni materiale presente prev OR curr.
                tutti_codici = sorted(set(prev_per_tipo) | set(curr_per_tipo))
                # Sgancio prima (delta < 0), poi aggancio (delta > 0).
                sganci: list[EventoComposizione] = []
                agganci: list[EventoComposizione] = []
                for m in tutti_codici:
                    delta = curr_per_tipo.get(m, 0) - prev_per_tipo.get(m, 0)
                    if delta == 0:
                        continue
                    tipo: TipoEvento = "aggancio" if delta > 0 else "sgancio"
                    ev = EventoComposizione(
                        tipo=tipo,
                        materiale_tipo_codice=m,
                        pezzi_delta=delta,
                        stazione_proposta=blocco.corsa.codice_origine,
                        posizione_dopo_blocco=i - 1,
                        note_builder=(
                            f"Transizione composizione su {m}: "
                            f"{prev_per_tipo.get(m, 0)} → {curr_per_tipo.get(m, 0)} "
                            f"pezzi al blocco {i}."
                        ),
                        is_validato_utente=False,
                    )
                    (sganci if delta < 0 else agganci).append(ev)
                eventi.extend(sganci)
                eventi.extend(agganci)
            prev_per_tipo = curr_per_tipo

        giornate_out.append(dataclasses.replace(giornata, eventi_composizione=tuple(eventi)))

    return dataclasses.replace(giro_assegnato, giornate=tuple(giornate_out))


# =====================================================================
# Orchestrator
# =====================================================================


def assegna_e_rileva_eventi(
    giri: Sequence[Giro],
    regole: Sequence[_RegolaLike],
    is_accoppiamento_ammesso: IsAccoppiamentoAmmesso | None = None,
    vincoli_inviolabili: Sequence[Any] = (),
    stazioni_lookup: dict[str, str] | None = None,
) -> list[GiroAssegnato]:
    """Pipeline completa: ``assegna_materiali`` + ``rileva_eventi_composizione``
    su tutti i giri in input.

    Args:
        giri: lista di ``Giro`` da multi-giornata.
        regole: regole del programma.
        is_accoppiamento_ammesso: callback Sprint 5.5 (opzionale).
        vincoli_inviolabili: lista di Vincolo (entry 96). Se non vuota,
            le corse incompatibili col materiale di una regola
            cadono come residue invece che bloccare la creazione.
        stazioni_lookup: ``{codice: nome}`` per i pattern dei vincoli.
    """
    return [
        rileva_eventi_composizione(
            assegna_materiali(
                g,
                regole,
                is_accoppiamento_ammesso,
                vincoli_inviolabili=vincoli_inviolabili,
                stazioni_lookup=stazioni_lookup,
            )
        )
        for g in giri
    ]


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
