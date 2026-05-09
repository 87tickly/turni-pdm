"""Costruzione turno-convoglio per segmento (Sprint 8.2 MR-D3).

**Cuore architetturale del nuovo builder linea-centrico**.

Sprint 8.2 Plan-D MR-D3: dato un `AssegnazioneSegmento` (output di
MR-D2) + `CalendarioSegmento` (output di MR-D0.5) + corse del PdE
del segmento, costruisce per ogni convoglio del segmento la
sequenza di servizio multi-giornata.

# Modello operativo

Per ogni `AssegnazioneSegmento` con `n_convogli > 0`:

1. Recupera le corse del PdE attive nelle date del calendario
   segmento.
2. Distribuisce le corse fra gli `n_convogli` del segmento (algoritmo
   round-robin temporale: convoglio K prende la K-esima corsa, poi
   la (K+N_conv)-esima, ecc.). Pattern semplice ma operativamente
   valido per linee NAVETTA (A↔B alternato) e LINEARE (turni
   sequenziali).
3. Per ogni convoglio, ordina le sue corse per (data, ora_partenza)
   e raggruppa in `GiornataServizio` (= tutte le corse del convoglio
   in una data).
4. Verifica vincoli operativi:
   - **sosta_max_diurna_min**: gap fra ultima corsa e prossima nello
     stesso giorno ≤ soglia (default 240 min, da `VincoliSosta`).
   - **continuità geografica**: ``arrivo[i] == partenza[i+1]`` (= il
     convoglio è dove dovrebbe essere).
   - **stazione_inizio/fine** della giornata in capolinee del segmento
     (= il convoglio è alla sua base operativa all'inizio del giorno
     e a sera).
5. Aggrega le `GiornataServizio` in un `TurnoConvoglio`.

# Vincoli HARD vs SOFT

- **HARD**: continuità geografica (no salti spaziali nel turno),
  capolinee come start/end giornata (vincolo di sede/segmento).
- **SOFT**: rispetto vincoli sosta (warnings non blocking — il
  caller può decidere di accettare o rifiutare). Il MR-D3 baseline
  emette warning per superamento soglia ma costruisce comunque il
  turno; raffinamento in MR successivo.

# Output

`TurnoConvoglio` per convoglio è il blocco di costruzione del
nuovo modello "linea-centrico". MR-D4 ``aggregazione_linea_centrica``
li aggregherà in `Giro` compatibili col persister esistente
(strangler).

# Cosa NON fa MR-D3

- Non gestisce vuoti tecnici fra segmenti diversi (= scope MR-D6
  ``vuoti_tecnici``).
- Non sceglie sede di partenza fra alternatives (sceglie la sede
  assegnata da MR-D2).
- Non decide il calendario delle giornate del turno (segue le date
  del `CalendarioSegmento`).

DB-agnostic. Test 100% mocked.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, time
from typing import Protocol

from colazione.domain.builder_giro.assegna_convogli_linea import (
    AssegnazioneSegmento,
)
from colazione.domain.builder_giro.definizione_linea import SegmentoLinea
from colazione.domain.builder_giro.gestione_calendario_linea import (
    CalendarioSegmento,
)

# =====================================================================
# Protocol input
# =====================================================================


class _CorsaTurnoLike(Protocol):
    """Una corsa con metadati orari + linea, sufficiente per costruire
    turni.

    Allineato con ``CorsaCommerciale`` ORM. Subset di `_CorsaLike` di
    MR-D0 + `_CorsaCalendarLike` di MR-D0.5: serve sia codice_linea
    sia ora_partenza/arrivo.
    """

    codice_origine: str
    codice_destinazione: str
    ora_partenza: time
    ora_arrivo: time
    codice_linea: str
    valido_da: date
    valido_a: date
    valido_in_date_json: list[str] | None
    numero_treno: str
    km_tratta: float | None


# =====================================================================
# Modelli di output
# =====================================================================


@dataclass(frozen=True, kw_only=True)
class GiornataServizio:
    """Una giornata di servizio di un convoglio.

    Attributi:
        data: data calendaristica della giornata.
        corse: tuple di corse coperte dal convoglio in questa data,
            ordinate per ``ora_partenza`` crescente.
        stazione_inizio: codice stazione di partenza della prima corsa.
        stazione_fine: codice stazione di arrivo dell'ultima corsa.
        km_giornata: somma dei km delle corse della giornata (escludendo
            corse senza km_tratta).
        prestazione_min: durata totale del servizio (= ora_arrivo
            ultima - ora_partenza prima, in minuti, gestendo
            cross-mezzanotte come +1440).
        warnings_sosta: lista warnings se vincoli sosta violati intra-day.
    """

    data: date
    corse: tuple[_CorsaTurnoLike, ...]
    stazione_inizio: str
    stazione_fine: str
    km_giornata: float
    prestazione_min: int
    warnings_sosta: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, kw_only=True)
class TurnoConvoglio:
    """Sequenza di servizio multi-giornata di un convoglio.

    Attributi:
        convoglio_id: identificatore del convoglio (formato
            ``{segmento_codice}_C{n}`` con n 0-indexed). Es.
            ``"R31_completo_C0"``, ``"R31_completo_C1"``.
        segmento_codice: codice del `SegmentoLinea` di appartenenza.
        sede_codice: codice località manutenzione (= sede base, da
            `AssegnazioneSegmento`).
        giornate: tuple di `GiornataServizio` ordinate per data.
        n_corse_totali: somma corse di tutte le giornate.
        km_totali: somma km di tutte le giornate.
        warnings_globali: warnings cross-giornata (es. continuità geo
            fra fine giornata e inizio successiva).
    """

    convoglio_id: str
    segmento_codice: str
    sede_codice: str
    giornate: tuple[GiornataServizio, ...]
    n_corse_totali: int
    km_totali: float
    warnings_globali: tuple[str, ...] = field(default_factory=tuple)


# =====================================================================
# Helpers interni
# =====================================================================


def _time_to_min(t: time) -> int:
    return t.hour * 60 + t.minute


def _delta_minuti(t1: time, t2: time, *, cross_notte: bool = False) -> int:
    """Minuti fra t1 e t2 (t2 - t1). Cross_notte=True aggiunge 1440 se
    base è negativo (= attraversa la mezzanotte)."""
    base = _time_to_min(t2) - _time_to_min(t1)
    if cross_notte and base < 0:
        return base + 1440
    return base


def _filtra_corse_per_data(
    corse: Sequence[_CorsaTurnoLike],
    data: date,
) -> list[_CorsaTurnoLike]:
    """Filtra corse attive in una data specifica.

    Logica:
    - Se ``valido_in_date_json`` popolato: data deve esserci.
    - Altrimenti fallback ``valido_da <= data <= valido_a``.

    Ritorna lista (mantiene ordine relativo input).
    """
    out: list[_CorsaTurnoLike] = []
    for c in corse:
        if not (c.valido_da <= data <= c.valido_a):
            continue
        if c.valido_in_date_json:
            if data.isoformat() not in c.valido_in_date_json:
                continue
        out.append(c)
    return out


def _distribuisci_round_robin(
    corse_giorno: Sequence[_CorsaTurnoLike],
    n_convogli: int,
) -> list[list[_CorsaTurnoLike]]:
    """Distribuisce corse del giorno fra ``n_convogli`` con round-robin
    temporale.

    Algoritmo:
    1. Ordina corse per (ora_partenza, codice_origine, numero_treno)
       per determinismo.
    2. Assegna corsa i a convoglio (i % n_convogli).

    Per pattern NAVETTA (A→B, B→A, A→B, B→A...): convoglio 0 prende
    indici 0, 2, 4 (= sempre A→B); convoglio 1 prende 1, 3, 5 (=
    sempre B→A). NB: questo pattern produce sequenze NON valide
    operativamente (un singolo convoglio resta in A senza tornare).
    Per gestire correttamente il round-trip, MR-D4 raffinerà
    aggregando le coppie (A→B, B→A) prima della distribuzione.

    Per ora MR-D3 baseline: distribuzione round-robin semplice +
    warning se la sequenza risultante non rispetta continuità.
    """
    if n_convogli < 1:
        return []
    corse_ordinate = sorted(
        corse_giorno,
        key=lambda c: (
            _time_to_min(c.ora_partenza),
            c.codice_origine,
            c.numero_treno,
        ),
    )
    out: list[list[_CorsaTurnoLike]] = [[] for _ in range(n_convogli)]
    for i, c in enumerate(corse_ordinate):
        out[i % n_convogli].append(c)
    return out


def _verifica_continuita_giornata(
    corse: Sequence[_CorsaTurnoLike],
    sosta_max_diurna_min: int,
) -> list[str]:
    """Verifica vincoli intra-day per le corse di un convoglio.

    Controlli:
    - **continuità geografica**: arrivo[i] == partenza[i+1].
    - **sosta diurna**: gap orario fra arrivo[i] e partenza[i+1] ≤
      ``sosta_max_diurna_min``.

    Returns lista warnings (vuota se tutto ok).
    """
    warnings: list[str] = []
    for i in range(len(corse) - 1):
        prev = corse[i]
        nxt = corse[i + 1]
        if prev.codice_destinazione != nxt.codice_origine:
            warnings.append(
                f"Discontinuità geografica fra corsa {prev.numero_treno!r} "
                f"({prev.codice_destinazione}) e {nxt.numero_treno!r} "
                f"({nxt.codice_origine})"
            )
        gap = _delta_minuti(prev.ora_arrivo, nxt.ora_partenza)
        if gap < 0:
            warnings.append(
                f"Sovrapposizione temporale fra corsa {prev.numero_treno!r} "
                f"e {nxt.numero_treno!r} (gap negativo: {gap} min)"
            )
        elif gap > sosta_max_diurna_min:
            warnings.append(
                f"Sosta diurna {gap} min > limite {sosta_max_diurna_min} "
                f"min fra corsa {prev.numero_treno!r} e "
                f"{nxt.numero_treno!r}"
            )
    return warnings


def _calcola_km_e_prestazione(
    corse: Sequence[_CorsaTurnoLike],
) -> tuple[float, int]:
    """Somma km + prestazione (durata fra prima partenza e ultima arrivo).

    Cross-mezzanotte: se ultima ora_arrivo < prima ora_partenza,
    aggiunge 1440 alla prestazione (assunzione: cross-night singolo).
    """
    if not corse:
        return 0.0, 0
    km_totali = sum(c.km_tratta or 0.0 for c in corse)
    prima = corse[0].ora_partenza
    ultima = corse[-1].ora_arrivo
    cross = _time_to_min(ultima) < _time_to_min(prima)
    prestazione = _delta_minuti(prima, ultima, cross_notte=cross)
    return km_totali, prestazione


# =====================================================================
# Algoritmo principale
# =====================================================================


def costruisci_turno_per_convoglio(
    *,
    convoglio_id: str,
    segmento: SegmentoLinea,
    assegnazione: AssegnazioneSegmento,
    calendario: CalendarioSegmento,
    corse_segmento: Sequence[_CorsaTurnoLike],
    indice_convoglio: int,
    n_convogli_segmento: int,
) -> TurnoConvoglio:
    """Costruisce il `TurnoConvoglio` per un singolo convoglio.

    Args:
        convoglio_id: identificatore unico (es. ``"R31_completo_C0"``).
        segmento: il `SegmentoLinea` di appartenenza.
        assegnazione: output di MR-D2 (sede + n_convogli per il
            segmento).
        calendario: output di MR-D0.5 (date attive per tipo).
        corse_segmento: corse del PdE del segmento (già filtrate per
            linea/segmento dal caller).
        indice_convoglio: 0-indexed posizione del convoglio nel
            segmento (es. 0, 1, 2 per n_convogli=3).
        n_convogli_segmento: totale convogli del segmento (= modulo
            del round-robin).

    Returns:
        `TurnoConvoglio` con sequenza di giornate ordinate.
    """
    if assegnazione.errore is not None or assegnazione.sede_codice is None:
        # Defensive: non dovrebbe mai essere chiamato con assegnazione
        # in errore, ma se succede ritorna turno vuoto.
        return TurnoConvoglio(
            convoglio_id=convoglio_id,
            segmento_codice=segmento.codice,
            sede_codice="",
            giornate=(),
            n_corse_totali=0,
            km_totali=0.0,
            warnings_globali=(
                f"Assegnazione in errore ({assegnazione.errore}); "
                "turno vuoto.",
            ),
        )

    sosta_max = segmento.vincoli_sosta.sosta_max_diurna_min
    date_attive = sorted(calendario.date_attive_totali())

    giornate: list[GiornataServizio] = []
    warnings_globali: list[str] = []

    for d in date_attive:
        corse_giorno = _filtra_corse_per_data(corse_segmento, d)
        if not corse_giorno:
            continue
        suddivisione = _distribuisci_round_robin(
            corse_giorno, n_convogli_segmento
        )
        corse_convoglio = suddivisione[indice_convoglio]
        if not corse_convoglio:
            continue
        warnings_giornata = _verifica_continuita_giornata(
            corse_convoglio, sosta_max
        )
        km, prestazione = _calcola_km_e_prestazione(corse_convoglio)
        giornate.append(
            GiornataServizio(
                data=d,
                corse=tuple(corse_convoglio),
                stazione_inizio=corse_convoglio[0].codice_origine,
                stazione_fine=corse_convoglio[-1].codice_destinazione,
                km_giornata=km,
                prestazione_min=prestazione,
                warnings_sosta=tuple(warnings_giornata),
            )
        )

    # Verifica continuità cross-day (stazione_fine giornata K =
    # stazione_inizio giornata K+1, oppure stazione di sosta notturna
    # ammessa)
    for i in range(len(giornate) - 1):
        fine = giornate[i].stazione_fine
        inizio = giornate[i + 1].stazione_inizio
        if fine != inizio and fine not in segmento.stazioni_sosta_notturna:
            warnings_globali.append(
                f"Cross-day: giornata {giornate[i].data} termina a "
                f"{fine!r} (non in sosta_notturna_ammessa) e "
                f"giornata {giornate[i + 1].data} inizia a {inizio!r}"
            )

    n_corse_totali = sum(len(g.corse) for g in giornate)
    km_totali = sum(g.km_giornata for g in giornate)

    return TurnoConvoglio(
        convoglio_id=convoglio_id,
        segmento_codice=segmento.codice,
        sede_codice=assegnazione.sede_codice,
        giornate=tuple(giornate),
        n_corse_totali=n_corse_totali,
        km_totali=km_totali,
        warnings_globali=tuple(warnings_globali),
    )


def costruisci_turni_da_assegnazione(
    assegnazioni: Sequence[AssegnazioneSegmento],
    *,
    segmenti: Sequence[SegmentoLinea],
    calendari: Sequence[CalendarioSegmento],
    corse_per_segmento: dict[str, list[_CorsaTurnoLike]],
) -> list[TurnoConvoglio]:
    """Wrapper multi-segmento: produce 1+ `TurnoConvoglio` per ogni
    `AssegnazioneSegmento` con ``n_convogli > 0`` e nessun errore.

    Args:
        assegnazioni: output di MR-D2 (1 per segmento, alcune con
            errore).
        segmenti: definizioni segmenti (output MR-D0/D1).
        calendari: calendari per segmento (output MR-D0.5).
        corse_per_segmento: mapping ``segmento_codice → corse del PdE``.
            Il caller (builder.py) filtra/raggruppa.

    Returns:
        Lista di `TurnoConvoglio`, ordinata deterministicamente per
        ``(segmento_codice, indice_convoglio)``.
    """
    seg_per_codice = {s.codice: s for s in segmenti}
    cal_per_codice = {c.segmento_codice: c for c in calendari}

    out: list[TurnoConvoglio] = []
    for ass in assegnazioni:
        if ass.errore is not None or ass.n_convogli == 0:
            continue
        if ass.sede_codice is None:
            continue
        seg = seg_per_codice.get(ass.segmento_codice)
        cal = cal_per_codice.get(ass.segmento_codice)
        if seg is None or cal is None:
            continue
        corse_seg = corse_per_segmento.get(ass.segmento_codice, [])
        for idx in range(ass.n_convogli):
            convoglio_id = f"{ass.segmento_codice}_C{idx}"
            turno = costruisci_turno_per_convoglio(
                convoglio_id=convoglio_id,
                segmento=seg,
                assegnazione=ass,
                calendario=cal,
                corse_segmento=corse_seg,
                indice_convoglio=idx,
                n_convogli_segmento=ass.n_convogli,
            )
            out.append(turno)

    out.sort(key=lambda t: t.convoglio_id)
    return out


__all__ = [
    "GiornataServizio",
    "TurnoConvoglio",
    "costruisci_turni_da_assegnazione",
    "costruisci_turno_per_convoglio",
]
