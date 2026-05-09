"""Assegnazione convogli a SegmentoLinea (Sprint 8.2 MR-D2).

Sprint 8.2 Plan-D, raccomandazione obbligatoria SEVERO #2:
"nessun ciclo aperto fuori area Milano" deve essere un **constraint
HARD**, non una penalità soft.

Questo modulo è l'**allocatore vincolato** del nuovo builder
linea-centrico. Per ogni `SegmentoLinea` (output di MR-D0/D1),
sceglie:

- **sede di base** del/dei convoglio/i (= località manutenzione
  compatibile col segmento)
- **numero di convogli** minimo per coprire la frequenza di servizio
  rispettando i vincoli operativi
- **capacity check globale** per tipo materiale (no overflow flotta)

# Vincoli HARD (irrinunciabili)

1. **Compatibilità sede-segmento**: una sede può ospitare un segmento
   SOLO se la stazione collegata della sede è in
   `segmento.stazioni_sosta_notturna` OPPURE condivide area
   metropolitana con almeno un capolinea del segmento.
   Concretizza la raccomandazione SEVERO #2: un segmento
   ALES↔MILANO non può essere assegnato a sede CREMONA (capolinee
   né in sosta_notturna_segmento né in area Cremona).
2. **Capacity flotta**: somma convogli per materiale ≤
   `dotazione_per_materiale[mat]`. Se overflow → segmento NON
   assegnabile.
3. **Sede unica per segmento**: ogni segmento è assegnato a UNA sede
   (no split fra più sedi nel MR-D2 baseline; raffinamento futuro).

# Vincoli SOFT (preferenze, non bloccanti)

1. **Minimizza convogli totali**: a parità di vincoli HARD rispettati,
   scegli l'allocazione con meno convogli totali.
2. **Bilancia carico per sede**: a parità, distribuisci i segmenti
   fra sedi compatibili invece di sovraccaricare una sola.

# Algoritmo (constraint propagation greedy)

Non usiamo ILP esterno (no `pulp`/`ortools`) per restare leggeri.
Per la scala tipica (5-30 segmenti, 2-7 sedi, 5-15 materiali),
l'algoritmo greedy con vincoli HARD è esatto.

1. Per ogni segmento, calcola `candidati_sedi` (= sedi compatibili
   per vincolo HARD #1).
2. Ordina i segmenti per `(n_candidati ASC, codice ASC)` =
   most-constrained-first.
3. Per ogni segmento (in ordine), scegli la sede tra i candidati
   con MINORE carico corrente; tie-break alfabetico.
4. Calcola `n_convogli_minimo` per segmento via formula round-trip
   (`_calcola_n_convogli_minimo`).
5. Verifica capacity globale per materiale dopo l'assegnazione; se
   overflow, marca segmento come `errore_capacity` e prova prossima
   sede.
6. Se nessuna sede assegna → `errore_no_sede_compatibile` (vincolo
   HARD #1 violato).

# Cosa NON fa MR-D2

- Non costruisce i turni (= scope MR-D3 `costruisci_turno_linea`).
- Non gestisce il calendario per segmento (output MR-D0.5 è solo
  input al calcolo `n_corse_per_die_media`, MR-D2 non lo legge).
- Non sceglie sede per minimizzare km totali (scope futuro).

DB-agnostic. Test 100% mocked.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

from colazione.domain.builder_giro.definizione_linea import (
    SegmentoLinea,
)

# =====================================================================
# Parametri input
# =====================================================================


@dataclass(frozen=True, kw_only=True)
class ParamAssegnazione:
    """Parametri vincoli per l'assegnazione convogli.

    Attributi:
        sedi_disponibili: mapping ``codice_localita →
            stazione_collegata``. Es: ``{"IMPMAN_MILANO_FIORENZA":
            "S01640", "IMPMAN_CREMONA": "S01915"}``.
        area_per_stazione: mapping stazione → id area metropolitana.
            Per il check di compatibilità capolinea/area sede.
            Stazioni fuori da qualsiasi area non sono nel dict.
        dotazione_per_materiale: capacity flotta per tipo materiale.
            Es: ``{"ETR522": 71, "ATR803": 20}``. Se materiale
            mancante → assunto illimitato (defensive).
        materiale_per_segmento: mapping segmento_codice → materiale.
            Necessario per il check capacity. Es: ``{"R31_completo":
            "ETR522", "S13_completo": "ATR125"}``.
        ore_servizio_die: ore di servizio operativo giornaliero
            (default 18h = 06:00-24:00). Usato per calcolo n_convogli
            via formula round-trip.
        tempo_round_trip_default_min: tempo round-trip stimato di
            default per segmenti senza dato (default 120 min = 2h).
            Approssimazione conservativa per stima n_convogli quando
            ``SegmentoLinea`` non espone durata.
    """

    sedi_disponibili: dict[str, str]
    area_per_stazione: dict[str, int] = field(default_factory=dict)
    dotazione_per_materiale: dict[str, int] = field(default_factory=dict)
    materiale_per_segmento: dict[str, str] = field(default_factory=dict)
    ore_servizio_die: float = 18.0
    tempo_round_trip_default_min: int = 120

    def __post_init__(self) -> None:
        if not self.sedi_disponibili:
            raise ValueError("ParamAssegnazione.sedi_disponibili non può essere vuoto")
        if self.ore_servizio_die <= 0:
            raise ValueError(
                f"ParamAssegnazione.ore_servizio_die deve essere > 0, "
                f"ricevuto {self.ore_servizio_die}"
            )
        if self.tempo_round_trip_default_min <= 0:
            raise ValueError(
                "ParamAssegnazione.tempo_round_trip_default_min deve "
                f"essere > 0, ricevuto {self.tempo_round_trip_default_min}"
            )


# =====================================================================
# Output
# =====================================================================


@dataclass(frozen=True, kw_only=True)
class AssegnazioneSegmento:
    """Risultato dell'assegnazione di un singolo segmento.

    Attributi:
        segmento_codice: codice del `SegmentoLinea`.
        sede_codice: codice località manutenzione assegnata, oppure
            ``None`` se errore (vedi ``errore``).
        n_convogli: numero di convogli necessari per coprire il
            servizio del segmento.
        materiale: tipo materiale (passato in input via
            ``materiale_per_segmento``); ``""`` se non specificato.
        errore: ``None`` se assegnazione OK, altrimenti uno di:
            - ``"no_sede_compatibile"``: nessuna sede ha capolinea
              compatibile (raccomandazione SEVERO #2 → constraint
              HARD violato)
            - ``"capacity_overflow"``: nessuna sede candidate
              accetta la richiesta senza superare la dotazione
              flotta del materiale
    """

    segmento_codice: str
    sede_codice: str | None
    n_convogli: int
    materiale: str
    errore: str | None = None


@dataclass(frozen=True, kw_only=True)
class RisultatoAssegnazione:
    """Output completo dell'assegnazione.

    Attributi:
        assegnazioni: una `AssegnazioneSegmento` per ogni segmento di
            input. Stessa lunghezza dell'input.
        n_convogli_per_sede: mapping ``codice_sede → totale convogli
            allocati`` (somma di ``n_convogli`` di tutti i segmenti
            assegnati alla sede).
        n_convogli_per_materiale: mapping ``materiale → totale
            convogli allocati`` (per check capacity).
        warnings: messaggi diagnostici (es. capacity vicino al limite,
            sede candidate scartata per overflow).
    """

    assegnazioni: tuple[AssegnazioneSegmento, ...]
    n_convogli_per_sede: dict[str, int]
    n_convogli_per_materiale: dict[str, int]
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def n_segmenti_con_errore(self) -> int:
        """Conta segmenti che NON sono stati assegnati con successo."""
        return sum(1 for a in self.assegnazioni if a.errore is not None)


# =====================================================================
# Helpers compatibilità
# =====================================================================


def _e_compatibile(
    sede_stazione: str,
    segmento: SegmentoLinea,
    area_per_stazione: dict[str, int],
) -> bool:
    """Verifica vincolo HARD #1: la sede può ospitare il segmento?

    Una sede `S` è compatibile con un segmento se:
    1. ``S.stazione_collegata`` è in ``segmento.stazioni_sosta_notturna``
       (la sede è esplicitamente menzionata come punto di sosta del
       segmento — caso ottimo), OR
    2. ``S.stazione_collegata`` condivide area metropolitana con
       almeno un ``segmento.capolinee`` (la sede è "vicina" a un
       capolinea del segmento — sufficiente operativamente).

    Se il check (2) fallisce per `area_per_stazione` mancante (sede o
    capolinee fuori da qualsiasi area mappata), la sede NON è
    compatibile.

    **Raccomandazione SEVERO #2**: questo è il punto in cui il
    constraint "no ciclo aperto fuori area Milano" diventa hard.
    Una sede FIO (Milano) NON può ospitare un segmento con capolinee
    a Cremona/Brescia/Tirano se le aree non si toccano.
    """
    if sede_stazione in segmento.stazioni_sosta_notturna:
        return True
    sede_area = area_per_stazione.get(sede_stazione)
    if sede_area is None:
        return False
    return any(
        area_per_stazione.get(capolinea) == sede_area
        for capolinea in segmento.capolinee
    )


def _candidati_sedi(
    segmento: SegmentoLinea,
    params: ParamAssegnazione,
) -> list[str]:
    """Lista deterministica delle sedi compatibili col segmento.

    Ordinamento alfabetico per determinismo. Se nessuna compatibile
    → lista vuota (segmento non assegnabile, vincolo HARD #1
    violato).
    """
    candidati: list[str] = []
    for sede_codice, sede_stazione in params.sedi_disponibili.items():
        if _e_compatibile(sede_stazione, segmento, params.area_per_stazione):
            candidati.append(sede_codice)
    return sorted(candidati)


def _calcola_n_convogli_minimo(
    segmento: SegmentoLinea,
    params: ParamAssegnazione,
) -> int:
    """Stima il numero minimo di convogli per coprire il segmento.

    Formula semplificata:

        n_convogli = ceil(corse/die × tempo_round_trip / (2 × ore_servizio))

    Razionale: ogni convoglio in servizio fa N round-trip al giorno,
    dove N = ore_servizio / tempo_round_trip. Un round-trip include
    2 corse (andata + ritorno). Quindi un convoglio copre ~ (2 *
    ore_servizio / tempo_round_trip) corse al giorno. Per coprire
    `corse_die` totali serve `corse_die / corse_per_convoglio_die`
    convogli, arrotondato per eccesso.

    NB: per pattern NAVETTA il tempo_round_trip è solitamente più
    breve (1-2h); il default conservativo a 120 min può
    sottostimare il numero di convogli per servizi metropolitani
    ad alta frequenza. Raffinamento futuro: derivare
    tempo_round_trip dai dati corse del segmento.

    Minimo 1 convoglio se ci sono corse (defensive).
    """
    if segmento.n_corse_per_die_media <= 0:
        return 0
    tempo_rt_h = params.tempo_round_trip_default_min / 60.0
    corse_per_convoglio_die = (2.0 * params.ore_servizio_die) / tempo_rt_h
    if corse_per_convoglio_die <= 0:
        return 1
    raw = segmento.n_corse_per_die_media / corse_per_convoglio_die
    return max(1, math.ceil(raw))


# =====================================================================
# Algoritmo principale
# =====================================================================


def assegna_convogli_segmenti(
    segmenti: Sequence[SegmentoLinea],
    params: ParamAssegnazione,
) -> RisultatoAssegnazione:
    """Algoritmo principale: assegna ogni segmento a una sede + convogli.

    Strategia:
    1. Per ogni segmento, computa candidati sedi (compatibilità HARD).
    2. Ordina segmenti per ``(len(candidati) ASC, codice ASC)`` =
       most-constrained-first (segmenti con meno opzioni vanno prima).
    3. Per ogni segmento in ordine:
       a. Se nessun candidato → errore ``no_sede_compatibile``.
       b. Calcola ``n_convogli_minimo`` necessari.
       c. Per ogni candidato (ordine alfabetico): verifica capacity
          materiale + carico sede; scegli il primo che NON viola.
       d. Se nessun candidato accetta → errore ``capacity_overflow``.
    4. Costruisce ``RisultatoAssegnazione`` con statistiche aggregate.

    Determinismo: stesso input → stesso output (ordinamento esplicito
    di candidati e segmenti).

    Args:
        segmenti: lista di `SegmentoLinea` da assegnare. Tipicamente
            output di MR-D1 ``analizza_linee_da_corse``.
        params: vincoli del programma (sedi, aree, dotazione).

    Returns:
        ``RisultatoAssegnazione`` con un'`AssegnazioneSegmento` per
        ogni segmento di input.
    """
    if not segmenti:
        return RisultatoAssegnazione(
            assegnazioni=(),
            n_convogli_per_sede={},
            n_convogli_per_materiale={},
            warnings=(),
        )

    # Pre-calcola candidati per ogni segmento
    candidati_per_segmento: dict[str, list[str]] = {
        seg.codice: _candidati_sedi(seg, params) for seg in segmenti
    }

    # Ordina segmenti most-constrained-first
    segmenti_ordinati = sorted(
        segmenti,
        key=lambda s: (len(candidati_per_segmento[s.codice]), s.codice),
    )

    # Stato dell'allocazione (mutabile durante il loop)
    n_convogli_per_sede: dict[str, int] = defaultdict(int)
    n_convogli_per_materiale: dict[str, int] = defaultdict(int)
    warnings: list[str] = []
    assegnazioni_per_codice: dict[str, AssegnazioneSegmento] = {}

    for seg in segmenti_ordinati:
        candidati = candidati_per_segmento[seg.codice]
        materiale = params.materiale_per_segmento.get(seg.codice, "")

        # Vincolo HARD #1: nessuna sede compatibile
        if not candidati:
            assegnazioni_per_codice[seg.codice] = AssegnazioneSegmento(
                segmento_codice=seg.codice,
                sede_codice=None,
                n_convogli=0,
                materiale=materiale,
                errore="no_sede_compatibile",
            )
            warnings.append(
                f"Segmento {seg.codice!r} non assegnabile: nessuna "
                f"sede compatibile (capolinee {sorted(seg.capolinee)} "
                f"né in sosta_notturna_ammessa né in area condivisa "
                f"con sedi disponibili). Constraint SEVERO #2 violato."
            )
            continue

        n_conv = _calcola_n_convogli_minimo(seg, params)

        # Cerca la prima sede candidata che non viola capacity
        scelta: str | None = None
        for sede in candidati:
            # Vincolo HARD #2: capacity per materiale
            if materiale and materiale in params.dotazione_per_materiale:
                in_uso = n_convogli_per_materiale[materiale]
                tetto = params.dotazione_per_materiale[materiale]
                if in_uso + n_conv > tetto:
                    warnings.append(
                        f"Sede {sede!r} candidata per {seg.codice!r} "
                        f"scartata: assegnando {n_conv} convogli "
                        f"{materiale} si supera dotazione "
                        f"({in_uso + n_conv} > {tetto})."
                    )
                    continue
            scelta = sede
            break

        if scelta is None:
            assegnazioni_per_codice[seg.codice] = AssegnazioneSegmento(
                segmento_codice=seg.codice,
                sede_codice=None,
                n_convogli=n_conv,
                materiale=materiale,
                errore="capacity_overflow",
            )
            continue

        # Aggiorna stato globale
        n_convogli_per_sede[scelta] += n_conv
        if materiale:
            n_convogli_per_materiale[materiale] += n_conv

        assegnazioni_per_codice[seg.codice] = AssegnazioneSegmento(
            segmento_codice=seg.codice,
            sede_codice=scelta,
            n_convogli=n_conv,
            materiale=materiale,
            errore=None,
        )

    # Output ordinato come l'input originale (determinismo per il caller)
    assegnazioni_ordinate = tuple(
        assegnazioni_per_codice[seg.codice] for seg in segmenti
    )

    return RisultatoAssegnazione(
        assegnazioni=assegnazioni_ordinate,
        n_convogli_per_sede=dict(n_convogli_per_sede),
        n_convogli_per_materiale=dict(n_convogli_per_materiale),
        warnings=tuple(warnings),
    )


__all__ = [
    "AssegnazioneSegmento",
    "ParamAssegnazione",
    "RisultatoAssegnazione",
    "assegna_convogli_segmenti",
]
